#!/usr/bin/env python3
"""Parse and relocate reviewed Nix source references, without evaluating Nix.

Only manifest-listed files are read. Dynamic references, runtime strings and
missing inputs remain explicit. The generated tree is for analysis, not activation.
"""
import argparse
import hashlib
from importlib.metadata import version
import json
from pathlib import Path, PurePosixPath
import posixpath
import re

from tree_sitter import Language, Parser
import tree_sitter_nix


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def parser():
    if {name: version(name) for name in ("tree-sitter", "tree-sitter-nix")} != {
            "tree-sitter": "0.25.2", "tree-sitter-nix": "0.1.0"}:
        raise ValueError("PARSER_VERSION_MISMATCH")
    return Parser(Language(tree_sitter_nix.language()))


def walk(node):
    yield node
    for child in node.named_children:
        yield from walk(child)


def absolute(name, value):
    if value.startswith("/"):
        return posixpath.normpath(value)
    if value.startswith("./") or value.startswith("../"):
        return posixpath.normpath(posixpath.join("/", posixpath.dirname(name), value))
    return None


def classify(node, raw):
    parent = node.parent
    while parent is not None:
        if parent.type == "formal":
            return "function-default-not-necessarily-used"
        if parent.type == "binding":
            key = parent.child_by_field_name("attrpath")
            if key and raw[key.start_byte:key.end_byte] == b"imports":
                return "module-import-expression"
        if parent.type == "apply_expression":
            function = parent.child_by_field_name("function")
            if function:
                text = raw[function.start_byte:function.end_byte]
                if text in (b"import", b"builtins.import", b"builtins.readFile", b"builtins.path", b"builtins.storePath"):
                    return text.decode("ascii")
        parent = parent.parent
    return "source-path-expression-not-an-established-import"


def rewrite(name, raw, known_files, known_directories, nix_parser):
    tree = nix_parser.parse(raw)
    if tree.root_node.has_error:
        raise ValueError("SOURCE_SYNTAX_ERROR")
    references, edits, substitutions = [], [], []
    for node in walk(tree.root_node):
        if node.type not in ("path_expression", "string_expression", "spath_expression"):
            continue
        token = raw[node.start_byte:node.end_byte].decode("utf-8")
        if node.type == "spath_expression":
            references.append({"line": node.start_point.row + 1, "literal": token,
                               "kind": "search-path-requires-a-lock", "resolved": None})
            continue
        if node.type == "string_expression":
            if any(child.type == "interpolation" for child in node.named_children):
                continue
            try:
                value = json.loads(token)
            except (ValueError, TypeError):
                continue
            # Runtime paths (/var/lib, /run, /dev...) must not be relocated.
            # Relative string references need explicit semantic review.
            if not value.startswith(("/root/", "/etc/nixos/")):
                continue
        else:
            if any(child.type == "interpolation" for child in node.named_children):
                continue
            value = token
        destination = absolute(name, value)
        if destination is None:
            continue
        target = destination.lstrip("/")
        available = target in known_files or target in known_directories
        item = {"line": node.start_point.row + 1, "literal": token, "resolved": destination,
                "kind": classify(node, raw), "available": available,
                "target_type": "file" if target in known_files else "partial-directory" if target in known_directories else "uncollected"}
        references.append(item)
        if available and value.startswith("/"):
            relocated = posixpath.relpath(target, posixpath.dirname(name) or ".")
            if not relocated.startswith("."):
                relocated = "./" + relocated
            # toString retains string semantics while anchoring the path to the
            # source file, unlike a relative string interpreted from the cwd.
            replacement = "(toString " + relocated + ")" if node.type == "string_expression" else relocated
            edits.append((node.start_byte, node.end_byte, replacement.encode()))
            substitutions.append({"start_byte": node.start_byte, "end_byte": node.end_byte,
                                  "before": token, "after": replacement, "target": target})
    result = raw
    for start, end, replacement in sorted(edits, reverse=True):
        result = result[:start] + replacement + result[end:]
    if nix_parser.parse(result).root_node.has_error:
        raise ValueError("NORMALIZED_SYNTAX_ERROR")
    # These are unresolved textual occurrences, not additional proven imports.
    residual = [{"line": index, "kind": "remaining-text-reference-needs-review"}
                for index, line in enumerate(result.decode().splitlines(), 1)
                if re.search(r"/(root|etc/nixos)/", line)]
    return result, references, substitutions, residual


def verified_sources(extracted, expected_review):
    review_path = extracted / "review.json"
    if any(parent.is_symlink() for parent in [review_path, *review_path.parents]):
        raise ValueError("LINKED_REVIEW")
    review_raw = review_path.read_bytes()
    if digest(review_raw) != expected_review:
        raise ValueError("REVIEW_DIGEST_MISMATCH")
    review = json.loads(review_raw)
    files = {item["path"]: item for item in review["files"]}
    if len(files) != len(review["files"]):
        raise ValueError("DUPLICATE_PATH")
    directories = {str(parent) for name in files for parent in PurePosixPath(name).parents if str(parent) != "."}
    contents = {}
    for name, item in files.items():
        path = PurePosixPath(name)
        if path.is_absolute() or str(path) != name or any(part in ("..", ".") for part in path.parts):
            raise ValueError("INVALID_SOURCE_PATH")
        source = extracted / "source" / name
        if any(parent.is_symlink() for parent in [source, *source.parents]):
            raise ValueError("LINKED_SOURCE")
        raw = source.read_bytes()
        if len(raw) != item["bytes"] or digest(raw) != item["sha256"]:
            raise ValueError("SOURCE_DIGEST_MISMATCH")
        contents[name] = raw
    return review, files, directories, contents


def normalize(extracted, expected_review, output):
    review, files, directories, contents = verified_sources(extracted, expected_review)
    nix_parser = parser()
    generated, entries = {}, []
    for name, raw in sorted(contents.items()):
        if name.endswith(".nix"):
            transformed, refs, changes, residual = rewrite(name, raw, set(files), directories, nix_parser)
        else:
            transformed, refs, changes, residual = raw, [], [], []
        generated[name] = transformed
        entries.append({"path": name, "source_sha256": digest(raw), "normalized_sha256": digest(transformed),
                        "received_change": files[name]["change"], "references": refs,
                        "substitutions": changes, "residual_text_references": residual})
    report = {"schema_version": 1, "operation": "mrjam-reviewed-source-normalization-v1",
              "review_sha256": expected_review, "authority": review["authority"],
              "generation_binding": review["generation_binding"], "entrypoint": review["entrypoint"],
              "declared_state_version": review["declared_state_version"],
              "files": entries, "nix_files_parsed": sum(name.endswith(".nix") for name in files),
              "normalization_changes": sum(len(e["substitutions"]) for e in entries),
              "complete_dependency_graph": False, "evaluated": False, "activatable": False,
              "limits": ["Literal references include function defaults and inactive branches",
                         "Dynamic imports, interpolated paths and runtime scripts require separate review",
                         "No missing file, directory, archive, secret or data is fetched or opened",
                         "Path relocation is analysis, not proof of semantic equivalence or deployment readiness"]}
    output.mkdir(parents=False, exist_ok=False)
    for name, raw in generated.items():
        dest = output / "source" / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        with dest.open("xb") as stream:
            stream.write(raw)
    (output / "normalization.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--extracted", type=Path, required=True)
    cli.add_argument("--review-sha256", required=True)
    cli.add_argument("--output", type=Path, required=True)
    args = cli.parse_args()
    report = normalize(args.extracted, args.review_sha256, args.output)
    print(json.dumps({k: report[k] for k in ("operation", "review_sha256", "nix_files_parsed",
                                           "normalization_changes", "complete_dependency_graph", "evaluated", "activatable")}))

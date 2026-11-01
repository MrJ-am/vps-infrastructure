#!/usr/bin/env python3
"""Summarize reviewed source references and exact code matches. No evaluation."""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path

from normalize_sources import digest, parser, rewrite, verified_sources


def analyze(extracted, expected_review, reference):
    review, files, directories, contents = verified_sources(extracted, expected_review)
    known = defaultdict(list)
    # Read only retained code extensions, never historical JSON/data/archives.
    for candidate in sorted(reference.rglob("*")):
        if candidate.suffix not in (".nix", ".py", ".sh", ".conf") or candidate.is_symlink() or not candidate.is_file():
            continue
        if any(p.is_symlink() for p in candidate.parents):
            raise ValueError("LINKED_REFERENCE")
        known[digest(candidate.read_bytes())].append(str(candidate.relative_to(reference)))
    matches = {name: known[digest(raw)] for name, raw in sorted(contents.items()) if digest(raw) in known}
    missing = defaultdict(list)
    counts = Counter()
    nix_parser = parser()
    for name, raw in sorted(contents.items()):
        if not name.endswith(".nix"):
            continue
        _, refs, substitutions, _ = rewrite(name, raw, set(files), directories, nix_parser)
        counts["nix_files_parsed"] += 1
        counts["literal_references"] += len(refs)
        counts["substitutions"] += len(substitutions)
        counts["files_with_substitutions"] += bool(substitutions)
        for item in refs:
            if item["kind"] == "search-path-requires-a-lock":
                counts["unlocked_search_references"] += 1
            elif item["target_type"] == "partial-directory":
                counts["partial_directory_references"] += 1
            elif not item["available"]:
                missing[item["resolved"]].append({"source": name, "line": item["line"], "kind": item["kind"]})
    counts["uncollected_literal_targets"] = len(missing)
    counts["distinct_received_source_hashes"] = len({digest(raw) for raw in contents.values()})
    return {"schema_version": 1, "authority": "local-static-code-analysis",
            "review_sha256": expected_review, "received_authority": review["authority"],
            "source_commit_authenticated": False, "generation_binding": "unverified",
            "received_files": len(files), "reference_code_extensions": [".nix", ".py", ".sh", ".conf"],
            "exact_byte_matches": matches, "matched_files": len(matches), "counts": dict(counts),
            "uncollected_literal_targets": dict(sorted(missing.items())),
            "limits": ["A literal target is not necessarily an active dependency", "A default may be overridden at its call site",
                       "A directory in the receipt is only partially collected", "An exact file match does not establish a Git revision",
                       "No uncollected target is opened or retrieved", "No received module or script is evaluated or executed"]}


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--extracted", type=Path, required=True)
    cli.add_argument("--review-sha256", required=True)
    cli.add_argument("--reference-code", type=Path, required=True)
    args = cli.parse_args()
    print(json.dumps(analyze(args.extracted, args.review_sha256, args.reference_code), indent=2, sort_keys=True))

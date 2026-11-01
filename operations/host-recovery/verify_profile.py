#!/usr/bin/env python3
"""Check curated machine facts against literal Nix syntax, without Nix evaluation."""
import argparse
import json
from pathlib import Path

from normalize_sources import digest, parser, verified_sources


def text(node, raw):
    return raw[node.start_byte:node.end_byte].decode("utf-8")


def string(node, raw):
    if node.type != "string_expression" or any(c.type == "interpolation" for c in node.named_children):
        raise ValueError("NON_LITERAL_STRING")
    return json.loads(text(node, raw))


def attrpath(node, raw):
    return tuple(text(c, raw) if c.type == "identifier" else string(c, raw)
                 for c in node.named_children if c.type != "comment")


def bindings(node, raw, prefix=()):
    if node.type != "attrset_expression":
        raise ValueError("NOT_A_LITERAL_ATTRIBUTE_SET")
    result = {}
    for binding_set in node.named_children:
        if binding_set.type == "comment":
            continue
        if binding_set.type != "binding_set":
            raise ValueError("UNSUPPORTED_BINDING_SET")
        for binding in binding_set.named_children:
            if binding.type == "comment":
                continue
            if binding.type != "binding":
                raise ValueError("UNSUPPORTED_BINDING")
            key = prefix + attrpath(binding.child_by_field_name("attrpath"), raw)
            value = binding.child_by_field_name("expression")
            if value is None:
                raise ValueError("MISSING_BINDING_EXPRESSION")
            entries = bindings(value, raw, key) if value.type == "attrset_expression" else {key: value}
            if result.keys() & entries.keys():
                raise ValueError("DUPLICATE_BINDING")
            result.update(entries)
    return result


def literal(node, raw):
    if node.type == "string_expression":
        return string(node, raw)
    if node.type == "list_expression":
        return [literal(c, raw) for c in node.named_children if c.type != "comment"]
    if node.type == "attrset_expression":
        items = bindings(node, raw)
        if any(len(key) != 1 for key in items):
            raise ValueError("NESTED_VALUE_NOT_SUPPORTED")
        return {key[0]: literal(value, raw) for key, value in items.items()}
    if node.type == "variable_expression" and text(node, raw) in ("true", "false", "null"):
        return json.loads(text(node, raw))
    if node.type == "apply_expression":
        children = [c for c in node.named_children if c.type != "comment"]
        # Recognize one declaration wrapper syntactically; do not call it.
        if len(children) == 2 and text(children[0], raw) == "lib.mkDefault":
            return literal(children[1], raw)
    raise ValueError("NON_LITERAL_VALUE")


def declaration(raw):
    tree = parser().parse(raw)
    if tree.root_node.has_error:
        raise ValueError("SOURCE_SYNTAX_ERROR")
    children = [c for c in tree.root_node.named_children if c.type != "comment"]
    if len(children) != 1:
        raise ValueError("UNSUPPORTED_SOURCE_ROOT")
    node = children[0]
    if node.type == "function_expression":
        node = node.named_children[-1]
    return bindings(node, raw)


def verify(extracted, expected_review, profile):
    review, files, _, contents = verified_sources(extracted, expected_review)
    for name, expected in profile["source_hashes"].items():
        if name not in files or digest(contents[name]) != expected:
            raise ValueError("PROFILE_SOURCE_DIGEST_MISMATCH")
    machine = profile["state_version_source"]
    hardware = str(Path(machine).with_name("hardware-configuration.nix"))
    network = ("systemd", "network", "networks", "05-matheval-eth0")
    fields = {
        "state_version": (machine, ("system", "stateVersion")),
        "hostname": (machine, ("networking", "hostName")),
        "system": (hardware, ("nixpkgs", "hostPlatform")),
        "grub_device": (machine, ("boot", "loader", "grub", "device")),
        "root_device": (hardware, ("fileSystems", "/", "device")),
        "root_fs_type": (hardware, ("fileSystems", "/", "fsType")),
        "interface": (machine, network + ("matchConfig", "Name")),
        "mac_address": (machine, network + ("matchConfig", "MACAddress")),
        "addresses": (machine, network + ("address",)),
        "gateways": (machine, network + ("routes",)),
        "dns": (machine, network + ("dns",)),
        "root_public_key": (machine, ("users", "users", "root", "openssh", "authorizedKeys", "keys")),
    }
    parsed = {name: declaration(contents[name]) for name in (machine, hardware)}
    checks = {}
    for field, (source, path) in fields.items():
        node = parsed[source][path]
        value = literal(node, contents[source])
        expected = profile[field]
        if field == "gateways":
            value = [route["Gateway"] for route in value]
        if field == "root_public_key":
            expected = [expected]
        if value != expected:
            raise ValueError("PROFILE_VALUE_MISMATCH:" + field)
        checks[field] = {"source": source, "sha256": files[source]["sha256"],
                         "line": node.start_point.row + 1, "matches": True}
    if review["declared_state_version"] != {"value": profile["state_version"], "source": machine}:
        raise ValueError("REVIEW_STATE_VERSION_MISMATCH")
    return {"schema_version": 1, "authority": "local-static-code-check",
            "review_sha256": expected_review, "checks": checks, "nix_evaluated": False,
            "generation_binding": "unverified", "production_access": False}


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--extracted", type=Path, required=True)
    cli.add_argument("--review-sha256", required=True)
    cli.add_argument("--profile", type=Path, required=True)
    args = cli.parse_args()
    result = verify(args.extracted, args.review_sha256, json.loads(args.profile.read_text()))
    print(json.dumps(result, indent=2, sort_keys=True))

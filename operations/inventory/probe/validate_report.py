#!/usr/bin/env python3
"""Filter a bounded inventory report on the administrative host, before sharing.

Python 3.11+, standard library only; invoke with -I -S and no arguments.
Input is stdin, output is one closed JSON object. No probe is executed here.
The adjacent schema is pinned, not selected by the report or by a CLI option.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys


MAX_REPORT_BYTES = 16_384
MAX_SCHEMA_BYTES = 65_536
SCHEMA_SHA256 = "86f9a82d9f9f4881156b5fa10afd41a0ee912930cd62df3f347fcc29f0e202f5"


class InvalidReport(ValueError):
    """Never print the exception or any content from the input."""


def unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    value = {}
    for key, item in pairs:
        if key in value:
            raise InvalidReport()
        value[key] = item
    return value


def integer(token: str) -> int:
    if len(token) > 20:
        raise InvalidReport()
    return int(token)


def forbidden_number(_token: str) -> object:
    raise InvalidReport()


def decode(raw: bytes) -> object:
    return json.loads(
        raw.decode("utf-8"), object_pairs_hook=unique_object,
        parse_int=integer, parse_float=forbidden_number,
        parse_constant=forbidden_number,
    )


def matches(value: object, rule: dict, schema: dict) -> bool:
    """Interpret only the exact pinned schema's closed subset; no remote refs."""
    if "$ref" in rule:
        if rule != {"$ref": "#/$defs/unknown"}:
            raise InvalidReport()
        return matches(value, schema["$defs"]["unknown"], schema)
    if "oneOf" in rule:
        if set(rule) - {"oneOf", "$defs", "$schema", "title"}:
            raise InvalidReport()
        return sum(matches(value, option, schema) for option in rule["oneOf"]) == 1
    if "const" in rule:
        if set(rule) != {"const"}:
            raise InvalidReport()
        return type(value) is type(rule["const"]) and value == rule["const"]
    if "enum" in rule:
        if set(rule) != {"enum"}:
            raise InvalidReport()
        return any(type(value) is type(item) and value == item for item in rule["enum"])
    kind = rule.get("type")
    if kind == "object":
        if set(rule) != {"type", "additionalProperties", "required", "properties"}:
            raise InvalidReport()
        if rule["additionalProperties"] is not False or set(rule["required"]) != set(rule["properties"]):
            raise InvalidReport()
        return (
            type(value) is dict and set(value) == set(rule["required"])
            and all(matches(value[key], item, schema) for key, item in rule["properties"].items())
        )
    if kind == "integer":
        if set(rule) != {"type", "minimum", "maximum"}:
            raise InvalidReport()
        return type(value) is int and rule["minimum"] <= value <= rule["maximum"]
    if kind == "boolean":
        if set(rule) != {"type"}:
            raise InvalidReport()
        return type(value) is bool
    if kind == "array":
        if set(rule) != {"type", "minItems", "maxItems", "items"}:
            raise InvalidReport()
        return (
            type(value) is list and rule["minItems"] <= len(value) <= rule["maxItems"]
            and all(matches(item, rule["items"], schema) for item in value)
        )
    raise InvalidReport()


def validate(raw: bytes, schema_raw: bytes) -> dict:
    if not raw or len(raw) > MAX_REPORT_BYTES or len(schema_raw) > MAX_SCHEMA_BYTES:
        raise InvalidReport()
    if hashlib.sha256(schema_raw).hexdigest() != SCHEMA_SHA256:
        raise InvalidReport()
    schema, report = decode(schema_raw), decode(raw)
    if not matches(report, schema, schema):
        raise InvalidReport()
    return report


def main() -> int:
    if len(sys.argv) != 1:
        print('{"status":"rejected","code":"UNSUPPORTED_ARGUMENTS"}')
        return 2
    try:
        # The size cap applies before parsing; input and exception strings are
        # never included in errors. The schema is part of the reviewed bundle.
        raw = sys.stdin.buffer.read(MAX_REPORT_BYTES + 1)
        with Path(__file__).resolve().with_name("inventory.schema.json").open("rb") as handle:
            schema_raw = handle.read(MAX_SCHEMA_BYTES + 1)
        report = validate(raw, schema_raw)
    except Exception:
        print('{"status":"rejected","code":"INVALID_REPORT"}')
        return 1
    print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    return 1 if report.get("status") == "error" else 0


if __name__ == "__main__":
    raise SystemExit(main())

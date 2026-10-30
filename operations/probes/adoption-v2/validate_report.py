#!/usr/bin/env python3
"""Independent bounded output filter. It does not import or execute the probe."""
import hashlib
import json
import os
from pathlib import Path
import re
import resource
import signal
import sys

SCHEMA_SHA256 = "4cd2b1949bb2229a3254ae5f0dd98608ce5683bf5e7bee28a297ad95b3d03036"
MAX_INPUT = 8192
MAX_SCHEMA = 65536
MAX_SECONDS = 5


def _reject_value(_value):
    raise ValueError()


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError()
        result[key] = value
    return result


def decode(value):
    return json.loads(value, object_pairs_hook=_pairs, parse_float=_reject_value, parse_constant=_reject_value)


def _matches(value, schema, definitions, depth=0):
    if depth > 32:
        return False
    if "$ref" in schema:
        ref = schema["$ref"]
        if not re.fullmatch(r"#/\$defs/[a-z_]+", ref):
            return False
        return _matches(value, definitions[ref.rsplit("/", 1)[1]], definitions, depth + 1)
    if "oneOf" in schema:
        return sum(_matches(value, item, definitions, depth + 1) for item in schema["oneOf"]) == 1
    types = schema["type"] if type(schema["type"]) is list else [schema["type"]]
    expected = {"object": dict, "array": list, "string": str, "integer": int, "boolean": bool, "null": type(None)}
    if not any(type(value) is expected[name] for name in types):
        return False
    if "const" in schema and (type(value) is not type(schema["const"]) or value != schema["const"]):
        return False
    if "enum" in schema and value not in schema["enum"]:
        return False
    if value is None:
        return True
    if type(value) is dict:
        properties = schema["properties"]
        return (schema["additionalProperties"] is False and set(value) == set(properties)
                and all(_matches(value[key], rule, definitions, depth + 1) for key, rule in properties.items()))
    if type(value) is list:
        return False  # This pinned schema admits no arrays.
    if type(value) is str:
        return (len(value) <= schema.get("maxLength", 128)
                and ("pattern" not in schema or re.fullmatch(schema["pattern"], value) is not None))
    if type(value) is int:
        return schema.get("minimum", value) <= value <= schema.get("maximum", value)
    return True


def valid(value, schema):
    if not _matches(value, schema, schema["$defs"]):
        return False
    current, profile = value["generation"]["current"], value["generation"]["profile"]
    if profile["state"] == "observed":
        expected = None if current["state"] != "observed" else current["store_hash"] == profile["store_hash"]
        if profile["matches_current"] is not expected:
            return False
    if value["account"]["state"] != "observed":
        if value["paths"]["work"]["owner_matches"] is not None or value["paths"]["work"]["group_matches"] is not None:
            return False
    elif value["paths"]["work"]["state"] == "observed":
        if value["paths"]["work"]["owner_matches"] is None or value["paths"]["work"]["group_matches"] is None:
            return False
    for name, item in value["paths"].items():
        if name != "work" and item["state"] == "observed":
            if item["owner_matches"] is None or item["group_matches"] is None:
                return False
    return True


def load_schema():
    # The one adjacent source schema is the only file the filter reads.
    path = Path(__file__).absolute().parent / "adoption.schema.json"
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    with os.fdopen(fd, "rb") as stream:
        raw = stream.read(MAX_SCHEMA + 1)
    if len(raw) > MAX_SCHEMA or hashlib.sha256(raw).hexdigest() != SCHEMA_SHA256:
        raise ValueError()
    return decode(raw)


def _deadline(_signal, _frame):
    raise TimeoutError()


def _cap(which, limit):
    soft, hard = resource.getrlimit(which)
    limit = min([limit] + [v for v in (soft, hard) if v != resource.RLIM_INFINITY])
    resource.setrlimit(which, (limit, limit))


def main():
    code = "INVALID_REPORT"
    try:
        if len(sys.argv) != 1:
            code = "UNSUPPORTED_ARGUMENTS"
            raise ValueError()
        signal.signal(signal.SIGALRM, _deadline)
        signal.setitimer(signal.ITIMER_REAL, MAX_SECONDS)
        _cap(resource.RLIMIT_CORE, 0)
        _cap(resource.RLIMIT_CPU, 2)
        _cap(resource.RLIMIT_AS, 128 * 1024 * 1024)
        _cap(resource.RLIMIT_NOFILE, 64)
        schema = load_schema()
        raw = sys.stdin.buffer.read(MAX_INPUT + 1)
        if len(raw) > MAX_INPUT:
            raise ValueError()
        report = decode(raw)
        if not valid(report, schema):
            raise ValueError()
        print(json.dumps(report, separators=(",", ":"), sort_keys=True))
        return 0
    except Exception:
        print(json.dumps({"status": "rejected", "code": code}, separators=(",", ":")))
        return 65
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)


if __name__ == "__main__":
    raise SystemExit(main())

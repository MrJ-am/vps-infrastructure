"""Parse the two synthetic Nix sources; this is not a NixOS evaluation."""

from pathlib import Path
from importlib.metadata import version
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / ".syntax-tools"))

try:
    from tree_sitter import Language, Parser
    import tree_sitter_nix
except ImportError:
    print(json.dumps({"status": "unavailable", "check": "nix_syntax", "code": "PARSER_NOT_INSTALLED"}))
    raise SystemExit(78)

parser = Parser(Language(tree_sitter_nix.language()))
versions = {"tree-sitter": version("tree-sitter"), "tree-sitter-nix": version("tree-sitter-nix")}
if versions != {"tree-sitter": "0.25.2", "tree-sitter-nix": "0.1.0"}:
    print(json.dumps({"status": "unavailable", "check": "nix_syntax", "code": "PARSER_VERSION_MISMATCH"}))
    raise SystemExit(78)
results = {}
for relative in ("nixos/mrjam-rust.nix", "tests/module-evaluation.nix"):
    tree = parser.parse((ROOT / relative).read_bytes())
    results[relative] = "fail" if tree.root_node.has_error else "pass"

print(json.dumps({"status": "pass" if all(value == "pass" for value in results.values()) else "fail", "check": "nix_syntax_only", "versions": versions, "results": results}, sort_keys=True))
raise SystemExit(0 if all(value == "pass" for value in results.values()) else 1)


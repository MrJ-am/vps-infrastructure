"""Synthetic Pandoc contract. Does not claim Forgejo sanitizer/SSO qualification."""
import json
import pathlib
import subprocess
import sys
import tempfile


def render(executable, source, directory):
    result = subprocess.run(
        [executable],
        input=source.encode(),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=directory,
        env={
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "GITEA_PREFIX_SRC": "https://forge.example.invalid/owner/repo/src/commit/synthetic/docs",
        },
        check=True,
        timeout=25,
    )
    return result.stdout.decode("utf-8", "strict")


def main():
    executable = sys.argv[1]
    with tempfile.TemporaryDirectory(prefix="mrjam-forgejo-render-") as path:
        directory = pathlib.Path(path)
        witness = directory / "synthetic-include.txt"
        witness.write_text("MRJAM_SYNTHETIC_FILE_MUST_NOT_BE_READ")
        html = render(executable, """#+TITLE: Synthetic contract
* A heading
A fraction $\\frac{1}{2}$.

\\[ \\sum_{k=1}^{n} k \\]

[[file:../README.org][Relative link]]
[[https://example.invalid/target][Absolute link]]
""", directory)
        include = render(executable, f'#+INCLUDE: "{witness}"\n', directory)
        results = {
            "heading": '<h1' in html and "A heading" in html,
            "inline_math": 'class="math inline"' in html and "frac" in html,
            "display_math": 'class="math display"' in html and "sum" in html,
            "relative_links": 'https://forge.example.invalid/owner/repo/src/commit/synthetic/docs/../README.org' in html,
            "absolute_links": 'href="https://example.invalid/target"' in html,
            "sandbox_include_refused": "MRJAM_SYNTHETIC_FILE_MUST_NOT_BE_READ" not in include,
        }
        if not all(results.values()):
            raise AssertionError(json.dumps(results, sort_keys=True))
        print(json.dumps({
            "schema_version": 1,
            "scope": "synthetic-Pandoc-only",
            "results": results,
            "forgejo_sanitizer_qualified": False,
            "browser_mathjax_qualified": False,
            "sso_qualified": False,
        }, sort_keys=True))


if __name__ == "__main__":
    main()

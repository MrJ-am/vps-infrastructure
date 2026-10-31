#!/usr/bin/env python3
"""Check local HTML/CSS asset references before recording a frontend artifact."""
from __future__ import annotations

import argparse
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
import re
from urllib.parse import unquote, urlsplit

from prepare import Refused, regular_bytes


def resolve(source: str, reference: str) -> str | None:
    parsed = urlsplit(reference)
    if parsed.scheme == "data" or not parsed.path and parsed.fragment:
        return None
    if parsed.scheme or parsed.netloc:
        raise Refused("REMOTE_ASSET_DEPENDENCY_REFUSED")
    path = unquote(parsed.path)
    if "\\" in path or "\0" in path:
        raise Refused("ASSET_REFERENCE_PATH_REFUSED")
    parts = [] if path.startswith("/") else list(PurePosixPath(source).parent.parts)
    for part in path.split("/"):
        if part in ("", "."):
            continue
        if part == "..":
            if not parts:
                raise Refused("ASSET_REFERENCE_ESCAPE")
            parts.pop()
        else:
            parts.append(part)
    return "/".join(parts)


class AssetReferences(HTMLParser):
    def __init__(self):
        super().__init__()
        self.references = []

    def handle_starttag(self, tag, attributes):
        values = dict(attributes)
        if tag in {"script", "img", "source", "video", "audio"} and values.get("src"):
            self.references.append(values["src"])
        if tag == "link" and values.get("rel") in {"stylesheet", "icon", "preload", "modulepreload"} and values.get("href"):
            self.references.append(values["href"])


def check(root: Path) -> int:
    count = 0
    for path in root.rglob("*"):
        if path.suffix not in {".html", ".css"}:
            continue
        source = path.relative_to(root).as_posix()
        text = regular_bytes(root, source, 8 * 1024 * 1024).decode()
        if path.suffix == ".html":
            parser = AssetReferences()
            parser.feed(text)
            references = parser.references
        else:
            references = [match.strip().strip("\"'") for match in re.findall(r"url\(\s*([^)]*?)\s*\)", text)]
        for reference in references:
            target = resolve(source, reference)
            if target is not None:
                regular_bytes(root, target, 16 * 1024 * 1024)
                count += 1
    return count


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site", required=True, type=Path)
    args = parser.parse_args()
    print("LOCAL_ASSET_REFERENCES_VERIFIED", check(args.site))

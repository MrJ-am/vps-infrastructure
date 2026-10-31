from pathlib import Path
import tempfile
import unittest

from check_frontend_site import check, resolve
from prepare import Refused


class AssetClosureTests(unittest.TestCase):
    def test_normalized_local_css_and_root_html(self):
        self.assertEqual(resolve("assets/style.css", "../fonts/a.woff2?v=1"), "fonts/a.woff2")
        self.assertEqual(resolve("nested/index.html", "/app.js"), "app.js")
        self.assertIsNone(resolve("a.css", "#inline"))
        self.assertIsNone(resolve("a.css", "data:image/svg+xml,example"))

    def test_remote_and_escape_refused(self):
        for value in ("https://cdn.invalid/a.js", "//cdn.invalid/a.js", "../outside", "/../../outside"):
            with self.assertRaises(Refused):
                resolve("index.html", value)

    def test_missing_referenced_font_refuses_package(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "index.html").write_text('<link rel="stylesheet" href="/style.css"><a href="https://docs.invalid">link</a>')
            (root / "style.css").write_text('@font-face{src:url("font.woff2")}')
            with self.assertRaises(FileNotFoundError):
                check(root)
            (root / "font.woff2").write_bytes(b"synthetic font bytes")
            self.assertEqual(check(root), 2)


if __name__ == "__main__":
    unittest.main()

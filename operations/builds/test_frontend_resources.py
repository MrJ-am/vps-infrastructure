import base64
import hashlib
import io
import tarfile
import unittest

from fetch_frontend_resources import package_files
from prepare import Refused


class ResourceArchiveTests(unittest.TestCase):
    def archive(self, name="package/dist/katex.min.js", kind=tarfile.REGTYPE, duplicate=False):
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
            for _ in range(2 if duplicate else 1):
                member = tarfile.TarInfo(name)
                member.type = kind
                member.linkname = "/etc/passwd" if kind == tarfile.SYMTYPE else ""
                member.size = 1 if kind == tarfile.REGTYPE else 0
                archive.addfile(member, io.BytesIO(b"x") if kind == tarfile.REGTYPE else None)
        return buffer.getvalue()

    def selection(self, archive):
        return {"katex-dist/katex.min.js": {"sha256": hashlib.sha256(b"x").hexdigest(), "provenance": {
            "archive_sha256": hashlib.sha256(archive).hexdigest(),
            "integrity": "sha512-" + base64.b64encode(hashlib.sha512(archive).digest()).decode(),
        }}}

    def test_exact_pinned_file(self):
        archive = self.archive()
        self.assertEqual(package_files(archive, self.selection(archive)), {"katex-dist/katex.min.js": b"x"})

    def test_unchanged_integrity_rejects_changed_archive(self):
        archive = self.archive()
        with self.assertRaisesRegex(Refused, "PUBLIC_PACKAGE_INTEGRITY_MISMATCH"):
            package_files(archive + b"changed", self.selection(archive))

    def test_unexpected_duplicate_traversal_and_symlink_rejected(self):
        for archive in [self.archive(name="package/dist/extra.js"), self.archive(duplicate=True),
                        self.archive(name="package/../dist/katex.min.js"), self.archive(kind=tarfile.SYMTYPE)]:
            with self.assertRaises(Refused):
                package_files(archive, self.selection(archive))

    def test_selected_content_hash_not_recomputed_on_mismatch(self):
        archive = self.archive()
        selected = self.selection(archive)
        selected["katex-dist/katex.min.js"]["sha256"] = "0" * 64
        with self.assertRaisesRegex(Refused, "PUBLIC_PACKAGE_FILE_HASH_MISMATCH"):
            package_files(archive, selected)


if __name__ == "__main__":
    unittest.main()

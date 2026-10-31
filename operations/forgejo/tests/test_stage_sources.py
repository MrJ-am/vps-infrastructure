"""Public source publication contract; temporary fixtures, never host paths."""
import copy
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1]/"stage_sources.py"
spec = importlib.util.spec_from_file_location("stage_sources", SCRIPT)
s = importlib.util.module_from_spec(spec)
spec.loader.exec_module(s)
RULES = "1" * 40


class Publication(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.root = self.base/"input"
        self.root.mkdir(mode=0o555)
        self.root.chmod(0o555)
        self.store = self.base/"store"
        self.store.mkdir()
        self.lock = self.base/"lock"
        self.lock.write_bytes(b"")
        self.lock.chmod(0o440)
        self.owner = os.getuid()
        self.number = 0

    def tearDown(self):
        for base, dirs, _ in os.walk(self.base, followlinks=False):
            Path(base).chmod(0o700)
        self.tmp.cleanup()

    def bundle(self, contents=None, rules=RULES, edit=None):
        self.number += 1
        name = str(self.number).zfill(32) + "-synthetic-source"
        root = self.store/name
        root.mkdir()
        contents = contents or {"src/main.txt": b"INVENTED_PUBLIC_CODE\n"}
        files = []
        for path, raw in contents.items():
            p = root/path
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(raw)
            files.append({"path":path, "bytes":len(raw), "sha256":hashlib.sha256(raw).hexdigest()})
        value = {"schema_version":1,"rules_revision":rules,"files":files}
        if edit:
            edit(value)
        raw = json.dumps(value, sort_keys=True).encode()
        (root/"manifest.json").write_bytes(raw)
        for base, _, names in os.walk(root, topdown=False):
            for n in names:
                (Path(base)/n).chmod(0o444)
            Path(base).chmod(0o555)
        return {"sha256":hashlib.sha256(raw).hexdigest(), "source_store":"/nix/store/"+name}, root

    def config(self, *entries):
        return {"schema_version":1,"rules_revision":RULES,"proposals":list(entries)}

    def run_config(self, *entries):
        return s.reconcile(self.config(*entries), self.root, self.lock, owner=self.owner, store=self.store)

    def reject(self, code, *entries):
        with self.assertRaisesRegex(s.Refused, "^"+code+"$"):
            self.run_config(*entries)
        self.assertEqual(stat.S_IMODE(self.root.stat().st_mode), 0o555)

    def test_published_bytes_permissions_and_unchanged_worker(self):
        e, source = self.bundle()
        result = self.run_config(e)
        self.assertEqual(result["created"], 1)
        self.assertFalse(result["production_authorized"])
        final = s.worker.verify_input(self.root,e["sha256"],RULES,owner=self.owner)
        self.assertEqual((final/"src/main.txt").read_bytes(), (source/"src/main.txt").read_bytes())
        self.assertEqual((final/"src/main.txt").stat().st_nlink,1)
        self.assertEqual(stat.S_IMODE((final/"src/main.txt").stat().st_mode),0o444)

    def test_repeat_preserves_published_inodes_times_and_bytes(self):
        e, _ = self.bundle()
        self.run_config(e)
        target = self.root/e["sha256"]/"src/main.txt"
        before = target.stat()
        result = self.run_config(e)
        after = target.stat()
        self.assertEqual((before.st_ino,before.st_mtime_ns,before.st_ctime_ns),(after.st_ino,after.st_mtime_ns,after.st_ctime_ns))
        self.assertEqual((result["created"],result["retired"]),(0,0))

    def test_repeat_rechecks_selected_store_bytes_without_changing_publication(self):
        e, root = self.bundle({"code": b"ORIGINAL"})
        self.run_config(e)
        target = self.root/e["sha256"]/"code"
        before = target.stat()
        (root/"code").chmod(0o644)
        (root/"code").write_bytes(b"MODIFIED")
        (root/"code").chmod(0o444)
        self.reject("FILE_HASH_MISMATCH", e)
        self.assertEqual(target.read_bytes(), b"ORIGINAL")
        self.assertEqual((target.stat().st_ino, target.stat().st_mtime_ns), (before.st_ino, before.st_mtime_ns))

    def test_store_hardlinks_are_copied_to_single_links(self):
        e, root = self.bundle({"a":b"SAME", "b":b"SAME"})
        root.chmod(0o755)
        (root/"b").unlink()
        os.link(root/"a",root/"b")
        root.chmod(0o555)
        self.assertEqual((root/"a").stat().st_nlink,2)
        self.run_config(e)
        self.assertEqual((self.root/e["sha256"]/"a").stat().st_nlink,1)
        self.assertNotEqual((self.root/e["sha256"]/"a").stat().st_ino,(self.root/e["sha256"]/"b").stat().st_ino)

    def test_failed_second_bundle_never_publishes_first_or_retires_old(self):
        old, _ = self.bundle({"old":b"RETAIN"})
        self.run_config(old)
        first, _ = self.bundle({"first":b"NEW"})
        bad, root = self.bundle({"bad":b"BAD"})
        (root/"bad").chmod(0o644)
        (root/"bad").write_bytes(b"XXX")
        (root/"bad").chmod(0o444)
        self.reject("FILE_HASH_MISMATCH",first,bad)
        self.assertEqual({p.name for p in self.root.iterdir()},{old["sha256"]})
        self.assertEqual((self.root/old["sha256"]/"old").read_bytes(),b"RETAIN")

    def test_retirement_only_after_all_new_proposals_are_published(self):
        a, _ = self.bundle({"a":b"A"})
        b, _ = self.bundle({"b":b"B"})
        self.run_config(a,b)
        c, _ = self.bundle({"c":b"C"})
        d, _ = self.bundle({"d":b"D"})
        result = self.run_config(c,d)
        self.assertEqual((result["created"],result["retired"]),(2,2))
        self.assertEqual({p.name for p in self.root.iterdir()},{c["sha256"],d["sha256"]})

    def test_busy_lock_prevents_all_mutation(self):
        e, _ = self.bundle()
        before = self.root.stat()
        with self.lock.open("rb") as f:
            fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
            self.reject("BUSY",e)
        self.assertEqual(before.st_mtime_ns,self.root.stat().st_mtime_ns)
        self.assertEqual(list(self.root.iterdir()),[])

    def test_partial_private_stage_recovered(self):
        e, _ = self.bundle()
        self.root.chmod(0o755)  # A killed writer leaves an unaccepted root mode.
        stage = self.root/".staging"
        stage.mkdir(mode=0o700)
        (stage/"partial").write_bytes(b"INCOMPLETE_CODE")
        result = self.run_config(e)
        self.assertTrue(result["recovered_interrupted_stage"])
        self.assertFalse(stage.exists())
        s.worker.verify_input(self.root,e["sha256"],RULES,owner=self.owner)

    def test_stage_symlink_refused_without_touching_external_file(self):
        e, _ = self.bundle()
        self.root.chmod(0o755)
        stage = self.root/".staging"
        stage.mkdir(mode=0o700)
        victim = self.base/"outside"
        victim.write_bytes(b"KEEP")
        (stage/"bad").symlink_to(victim)
        self.root.chmod(0o555)
        self.reject("UNSAFE_STAGE",e)
        self.assertEqual(victim.read_bytes(),b"KEEP")

    def test_interrupted_rename_leaves_valid_old_and_new_then_recovers(self):
        old, _ = self.bundle({"old":b"OLD"})
        self.run_config(old)
        a, _ = self.bundle({"a":b"A"})
        b, _ = self.bundle({"b":b"B"})
        rename = os.rename
        calls = []
        def interrupt(source,target):
            calls.append(target)
            if len(calls)==2:
                raise OSError("invented interrupted rename")
            return rename(source,target)
        with patch.object(s.os,"rename",interrupt), self.assertRaises(OSError):
            self.run_config(a,b)
        self.assertEqual({p.name for p in self.root.iterdir()},{old["sha256"],a["sha256"]})
        for e in (old,a):
            s.worker.verify_input(self.root,e["sha256"],RULES,owner=self.owner)
        self.run_config(a,b)
        self.assertEqual({p.name for p in self.root.iterdir()},{a["sha256"],b["sha256"]})

    def test_wrong_digest_and_rules(self):
        e, _ = self.bundle()
        wrong = dict(e,sha256="a"*64)
        self.reject("MANIFEST_MISMATCH",wrong)
        other, _ = self.bundle(rules="2"*40)
        self.reject("RULES_MISMATCH",other)

    def test_extra_file_empty_directory_and_symlink_rejected(self):
        for kind in ("file","directory","symlink"):
            with self.subTest(kind=kind):
                e, root = self.bundle()
                root.chmod(0o755)
                if kind=="file":
                    (root/"extra").write_bytes(b"X")
                    (root/"extra").chmod(0o444)
                elif kind=="directory":
                    (root/"extra").mkdir(mode=0o555)
                else:
                    (root/"extra").symlink_to(root/"src")
                root.chmod(0o555)
                self.reject("UNDECLARED_SOURCE",e)

    def test_declared_symlink_fifo_and_writable_source_rejected(self):
        for kind in ("symlink","fifo","writable"):
            with self.subTest(kind=kind):
                e, root = self.bundle({"payload":b"X"})
                root.chmod(0o755)
                if kind=="writable":
                    (root/"payload").chmod(0o644)
                else:
                    (root/"payload").unlink()
                    if kind=="symlink":
                        (root/"payload").symlink_to("manifest.json")
                    else:
                        os.mkfifo(root/"payload",0o444)
                root.chmod(0o555)
                self.reject("UNTRUSTED_SOURCE",e)

    def test_manifest_path_traversal_duplicate_and_oversize_refused(self):
        for change,code in ((lambda m:m["files"][0].update(path="../escape"),"INVALID_PATH"),
                            (lambda m:m["files"].append(m["files"][0].copy()),"DUPLICATE_PATH"),
                            (lambda m:m["files"][0].update(bytes=s.MAX_BYTES+1),"INVALID_FILE")):
            e, _ = self.bundle(edit=change)
            self.reject(code,e)

    def test_unknown_existing_entry_and_corrupted_old_source_refused(self):
        e, _ = self.bundle()
        self.root.chmod(0o755)
        (self.root/"do-not-remove").write_bytes(b"KEEP")
        self.root.chmod(0o555)
        self.reject("UNKNOWN_PUBLISHED_ENTRY",e)
        self.assertEqual((self.root/"do-not-remove").read_bytes(),b"KEEP")
        self.root.chmod(0o755)
        (self.root/"do-not-remove").unlink()
        self.root.chmod(0o555)
        self.run_config(e)
        target=self.root/e["sha256"]/"src/main.txt"
        target.chmod(0o644)
        target.write_bytes(b"TAMPERED")
        target.chmod(0o444)
        new,_=self.bundle({"new":b"NEW"})
        self.reject("FILE_SIZE_MISMATCH",new)
        self.assertTrue(target.exists())

    def test_closed_catalog_and_retention(self):
        e,_=self.bundle()
        configs=[dict(self.config(e),extra=True),self.config(e,e),self.config(e,e,e),
                 dict(self.config(e),schema_version=True),self.config(dict(e,source_store="/tmp/arbitrary"))]
        for config in configs:
            with self.subTest(config=config),self.assertRaises(s.Refused):
                s.catalog(config)
        with self.assertRaises(s.Refused):
            s.worker.parse(b'{"schema_version":1,"schema_version":1}')

    def test_cli_refuses_arguments_with_closed_output(self):
        result=subprocess.run([sys.executable,"-I","-S",str(SCRIPT),"/arbitrary"],capture_output=True,timeout=5)
        self.assertEqual(result.returncode,2)
        self.assertEqual(json.loads(result.stdout),{"decision":"reject","code":"INVALID_INVOCATION"})
        self.assertEqual(result.stderr,b"")


if __name__ == "__main__":
    unittest.main()

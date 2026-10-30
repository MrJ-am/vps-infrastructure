"""Synthetic qualification only: never execute the real metadata probe."""
import base64
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from unittest import mock


SOURCE = Path(__file__).resolve().parents[1]


def module(name):
    spec = importlib.util.spec_from_file_location(name, SOURCE / f"{name}.py")
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


runner = module("runner")
adoption = module("adoption")
ssh = module("effective_ssh")
keys = module("public_keys")
PUBLIC = "ssh-ed25519 " + base64.b64encode(b"\0\0\0\x0bssh-ed25519\0\0\0\x20" + bytes(range(32))).decode() + " synthetic-only"
PAYLOAD = runner.MAGIC + b"".join((SOURCE / "probe" / name).read_bytes() for name, _, _ in runner.RUNTIME)


def fixture(rule, schema):
    """A fabricated lowest-bound report from the exact closed schema."""
    if "$ref" in rule:
        return fixture(schema["$defs"]["unknown"], schema)
    if "oneOf" in rule:
        return fixture(rule["oneOf"][0], schema)
    if "const" in rule:
        return rule["const"]
    if "enum" in rule:
        return rule["enum"][0]
    if rule["type"] == "object":
        return {key: fixture(value, schema) for key, value in rule["properties"].items()}
    if rule["type"] == "integer":
        return rule["minimum"]
    if rule["type"] == "boolean":
        return False
    if rule["type"] == "array":
        return [fixture(rule["items"], schema) for _ in range(rule["minItems"])]
    raise AssertionError("unsupported schema fixture")


SCHEMA = json.loads((SOURCE / "probe/inventory.schema.json").read_text())
REPORT = json.dumps(fixture(SCHEMA, SCHEMA)).encode()


class Protocol(unittest.TestCase):
    def test_exact_original_blobs_and_protocol(self):
        runner.unpack(PAYLOAD)
        self.assertEqual(len(PAYLOAD), runner.INPUT_SIZE)
        for name, length, digest in runner.RUNTIME:
            raw = (SOURCE / "probe" / name).read_bytes()
            self.assertEqual((len(raw), hashlib.sha256(raw).hexdigest()), (length, digest))

    def test_each_blob_mutation_and_bad_envelope_fail(self):
        offset = len(runner.MAGIC)
        altered = [b"", PAYLOAD[:-1], PAYLOAD + b"\0", b"x" + PAYLOAD[1:]]
        for _, length, _ in runner.RUNTIME:
            value = bytearray(PAYLOAD)
            value[offset] ^= 1
            altered.append(bytes(value))
            offset += length
        for value in altered:
            with self.subTest(length=len(value)), self.assertRaises(runner.Refused) as error:
                runner.unpack(value)
            self.assertEqual(error.exception.code, 65)

    def test_local_mutable_bundle_refused(self):
        with self.assertRaises(runner.Refused):
            runner.trusted_bundle(SOURCE / "probe")

    def test_command_has_only_immutable_inputs(self):
        path = Path("/nix/store/synthetic-package/libexec/probe")
        command = runner.pipeline_command({"python": "/nix/store/python/bin/python3", "bash": "/nix/store/bash/bin/bash"}, path)
        self.assertEqual(command[:5], ["/nix/store/bash/bin/bash", "--noprofile", "--norc", "-p", "-c"])
        self.assertIn("set -o pipefail", command[-1])
        self.assertNotIn("/var/lib", command[-1])
        self.assertNotIn("work", command[-1])

    def test_identity_exact_and_no_supplementary_groups(self):
        config = {"uid": 4242, "gid": 4243}
        with mock.patch.multiple(runner.os, getuid=lambda:4242, geteuid=lambda:4242, getgid=lambda:4243, getegid=lambda:4243, getgroups=lambda:[4243]):
            self.assertTrue(runner.identity_allowed(config))
            self.assertFalse(runner.identity_allowed({"uid": True, "gid": 4243}))
            with mock.patch.object(runner.os, "getgroups", return_value=[4243, 10]):
                self.assertFalse(runner.identity_allowed(config))

    def test_entry_refuses_root_or_arguments_before_loading_config(self):
        with mock.patch.object(runner.sys, "argv", ["runner", "anything"]), mock.patch.object(runner.Path, "read_text", side_effect=AssertionError("config read")):
            self.assertEqual(runner.main(), 64)
        with mock.patch.object(runner.sys, "argv", ["runner"]), mock.patch.object(runner.os, "getuid", return_value=0):
            self.assertEqual(runner.main(), 64)

    def test_second_validation_accepts_only_synthetic_closed_report(self):
        result = json.loads(runner.validated_report(REPORT, SOURCE / "probe"))
        self.assertEqual(result["authority"], "unverified_observation")
        self.assertEqual(result, json.loads(REPORT))
        for raw in (b"secret-marker", b'{"unknown":"marker"}', b'{"schema_version":1,"status":"error","code":"INTERNAL_ERROR"}', REPORT + b"x"):
            with self.subTest(raw_length=len(raw)), self.assertRaises(runner.Refused):
                runner.validated_report(raw, SOURCE / "probe")


class Pipeline(unittest.TestCase):
    def command(self, source):
        return [sys.executable, "-I", "-S", "-c", source]

    def test_clean_environment(self):
        with mock.patch.dict(os.environ, {"BASH_ENV": "/tmp/not-used", "PYTHONPATH": "/tmp/not-used", "SSH_ORIGINAL_COMMAND": "free-shell"}):
            value = runner.run_pipeline(self.command("import os,json;print(json.dumps(dict(os.environ)))"), 2)
        self.assertEqual(json.loads(value), {"LANG": "C", "LC_ALL": "C", "LC_CTYPE": "C.UTF-8"} if "LC_CTYPE" in json.loads(value) else {"LANG": "C", "LC_ALL": "C"})

    def test_cap_failure_timeout_and_no_retained_work(self):
        before = set(SOURCE.iterdir())
        cases = [("print('x'*100)", 68, 2, 8), ("raise SystemExit(1)", 67, 2, 1024), ("import time;time.sleep(5)", 69, .1, 1024), ("pass", 68, 2, 1024)]
        for source, expected, timeout, cap in cases:
            with self.subTest(expected=expected), self.assertRaises(runner.Refused) as caught:
                runner.run_pipeline(self.command(source), timeout, cap)
            self.assertEqual(caught.exception.code, expected)
            self.assertEqual(runner.child_ids(), [])
        self.assertEqual(set(SOURCE.iterdir()), before)

    def test_detached_descendant_is_reaped_before_success(self):
        with tempfile.TemporaryDirectory() as temp:
            pidfile = Path(temp) / "pid"
            source = "import subprocess,sys; p=subprocess.Popen([sys.executable,'-I','-S','-c','import time;time.sleep(30)'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True);open(%r,'w').write(str(p.pid));print('synthetic')" % str(pidfile)
            self.assertEqual(runner.run_pipeline(self.command(source), 2), b"synthetic\n")
            self.assertFalse(Path("/proc", pidfile.read_text()).exists())
            self.assertEqual(runner.child_ids(), [])

    def test_prctl_failure_refuses_before_child(self):
        fake = mock.Mock()
        fake.prctl.return_value = -1
        with mock.patch.object(runner.ctypes, "CDLL", return_value=fake), mock.patch.object(runner.subprocess, "Popen") as launch:
            with self.assertRaises(runner.Refused):
                runner.run_pipeline(self.command("print('never')"), 2)
            launch.assert_not_called()


@unittest.skipUnless(os.getuid() == 0, "root ownership fixture requires Cloud test UID 0; no host state changes")
class Lock(unittest.TestCase):
    def test_lock_reentry_symlink_and_unsafe_parent(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path = root / "lock"
            path.touch(mode=0o440)
            first = runner.operation_lock(path, os.getgid())
            try:
                with self.assertRaises(BlockingIOError):
                    runner.operation_lock(path, os.getgid())
            finally:
                os.close(first)
            linked = root / "symlink"
            linked.symlink_to(path)
            with self.assertRaises(OSError):
                runner.operation_lock(linked, os.getgid())
            root.chmod(0o770)
            with self.assertRaises(runner.Refused):
                runner.operation_lock(path, os.getgid())


class PublicPolicy(unittest.TestCase):
    def test_only_plain_dedicated_ed25519_public_keys(self):
        self.assertTrue(keys.valid(PUBLIC))
        for value in ("", PUBLIC + "\n", PUBLIC + " extra", 'command="sh" ' + PUBLIC, "ssh-ed25519 AAAA", "-----BEGIN PRIVATE KEY-----"):
            self.assertFalse(keys.valid(value))

    def test_effective_ssh_contract_rejects_every_weakening(self):
        valid = "\n".join(f"{key} {value}" for key, value in ssh.REQUIRED.items()) + "\nacceptenv LANG LC_*\n"
        self.assertTrue(ssh.allowed(valid.encode()))
        for key, value in ssh.REQUIRED.items():
            bad = valid.replace(f"{key} {value}\n", f"{key} synthetic-wrong\n")
            with self.subTest(key=key):
                self.assertFalse(ssh.allowed(bad.encode()))
        for extra in ("acceptenv BASH_ENV\n", "allowusers other\n", "denygroups mrjam-*\n", "forcecommand sh\n"):
            self.assertFalse(ssh.allowed((valid + extra).encode()))

    def test_ssh_validator_never_repeats_rejected_input(self):
        result = subprocess.run([sys.executable, "-I", "-S", str(SOURCE / "effective_ssh.py")], input=b"sensitive-synthetic-marker", capture_output=True, check=False)
        self.assertEqual(result.returncode, 1)
        self.assertNotIn(b"sensitive-synthetic-marker", result.stdout + result.stderr)
        self.assertEqual(json.loads(result.stdout)["code"], "SSH_POLICY_MISMATCH")

    def test_gss_field_may_be_unreported_only_under_exact_publickey_policy(self):
        base = "\n".join(f"{key} {value}" for key, value in ssh.REQUIRED.items()) + "\n"
        self.assertTrue(ssh.allowed(base.encode()))
        self.assertTrue(ssh.allowed((base + "gssapiauthentication no\n").encode()))
        self.assertFalse(ssh.allowed((base + "gssapiauthentication yes\n").encode()))
        self.assertFalse(ssh.allowed((base + "gssapiauthentication no\ngssapiauthentication no\n").encode()))
        for value in ("any", "publickey,password", "publickey password", "gssapi-with-mic"):
            self.assertFalse(ssh.allowed(base.replace("authenticationmethods publickey\n", "authenticationmethods " + value + "\n").encode()))
        self.assertFalse(ssh.allowed(base.replace("pubkeyauthentication yes\n", "pubkeyauthentication no\n").encode()))


class Adoption(unittest.TestCase):
    def test_declines_unknown_or_invented_ids_without_nss_reads(self):
        for config in ({}, {"uid": None, "gid": None}, {"uid": True, "gid": 1}, {"uid": 0, "gid": 1}):
            with mock.patch.object(adoption.pwd, "getpwnam", side_effect=AssertionError("NSS read")):
                self.assertFalse(adoption.check(config))

    def test_exact_legacy_login_template_only(self):
        text = '''#!/run/current-system/sw/bin/bash -p
set +x
exec 2>/dev/null
[[ "$UID" -ne 0 && "$EUID" -ne 0 ]] || exit 64
[[ "$#" -eq 2 && "$1" == -c && "$2" == mrjam-inventory-v1 ]] || exit 64
[[ "${SSH_ORIGINAL_COMMAND-}" == mrjam-inventory-v1 ]] || exit 64
exec /run/current-system/sw/bin/env -i LANG=C LC_ALL=C \\
  '/nix/store/00000000000000000000000000000000-python3-3.13/bin/python3' -I -S '/var/lib/mrjam-inventory-access/runner.py'
'''
        self.assertTrue(adoption.legacy_login(text))
        self.assertFalse(adoption.legacy_login(text + "true\n"))
        self.assertFalse(adoption.legacy_login(text.replace(" -I -S ", " ")))

    def test_preflight_has_closed_failure_and_no_mutation(self):
        result = subprocess.run([sys.executable, "-I", "-S", str(SOURCE / "adoption.py"), "--repair"], capture_output=True, check=False)
        self.assertEqual(result.returncode, 64)
        self.assertEqual(json.loads(result.stdout), {"status":"refused", "code":"UNSUPPORTED_ARGUMENTS"})


@unittest.skipUnless(os.getuid() == 0, "synthetic owner/ID adoption fixture requires Cloud container UID 0")
class AdoptionFilesystem(unittest.TestCase):
    def test_before_adoption_and_idempotent_objects_then_collisions(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "access"
            for directory in (root, root / "home", root / "home/.ssh", root / "work"):
                directory.mkdir(mode=0o755)
                directory.chmod(0o755)
            (root / "work").chmod(0o700)
            os.chown(root / "work", 4242, 4243)
            keyfile = Path(temp) / "ssh/keys"
            keyfile.parent.mkdir(mode=0o755)
            lockdir = Path(temp) / "runtime-lock"
            legacy = b"synthetic legacy code, never executed"
            rendered = 'restrict,command="mrjam-inventory-v1" ' + PUBLIC + "\n"
            for path, data, mode in ((root / "runner.py", legacy, 0o444), (root / "login", b"synthetic login, never executed", 0o555), (root / "home/.ssh/authorized_keys", rendered.encode(), 0o644)):
                path.write_bytes(data)
                path.chmod(mode)
            config = {"uid":4242, "gid":4243, "publicKeys":[PUBLIC], "legacyRunnerSha256":hashlib.sha256(legacy).hexdigest()}
            user = types.SimpleNamespace(pw_uid=4242, pw_gid=4243, pw_dir=str(root / "home"), pw_shell=str(root / "login"))
            with mock.patch.multiple(adoption, ROOT=root, KEYS=keyfile, LOCKDIR=lockdir), mock.patch.object(adoption.pwd, "getpwnam", return_value=user), mock.patch.object(adoption.grp, "getgrnam", return_value=types.SimpleNamespace(gr_gid=4243, gr_mem=[])), mock.patch.object(adoption.os, "getgrouplist", return_value=[4243]), mock.patch.object(adoption, "legacy_login", return_value=True):
                self.assertTrue(adoption.check(config))
                with mock.patch.object(adoption.grp, "getgrnam", return_value=types.SimpleNamespace(gr_gid=4243, gr_mem=["synthetic-other-user"])):
                    self.assertFalse(adoption.check(config))
                keyfile.write_text(rendered)
                keyfile.chmod(0o444)
                lockdir.mkdir(mode=0o750)
                os.chown(lockdir, 0, 4243)
                lock = lockdir / "operation.lock"
                lock.touch(mode=0o440)
                os.chown(lock, 0, 4243)
                self.assertTrue(adoption.check(config))
                lock.chmod(0o660)
                self.assertFalse(adoption.check(config))
                lock.chmod(0o440)
                self.assertTrue(adoption.check(config))
                keyfile.chmod(0o644)
                self.assertFalse(adoption.check(config))
                keyfile.chmod(0o444)
                os.link(lock, lockdir / "alias")
                self.assertFalse(adoption.check(config))


@unittest.skipUnless(os.getuid() == 0 and shutil.which("bash"), "synthetic drop-UID login fixture needs Bash and Cloud UID 0")
class Login(unittest.TestCase):
    def test_forced_operation_and_hostile_environment(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            root.chmod(0o755)
            (root / "libexec").mkdir()
            (root / "libexec/runner.py").write_text("import json,os;print(json.dumps(dict(os.environ),sort_keys=True))")
            login = root / "login"
            bash_root = str(Path(shutil.which("bash")).resolve().parents[1])
            coreutils_root = str(Path(shutil.which("env")).resolve().parents[1])
            python_root = str(Path(sys.executable).resolve().parents[1])
            login.write_text((SOURCE / "login.sh.in").read_text().replace("@bash@", bash_root).replace("@coreutils@", coreutils_root).replace("@python@", python_root).replace("@out@", str(root)))
            login.chmod(0o555)
            malicious = root / "malicious"
            malicious.write_text("echo ENV_INJECTED\n")
            env = {"SSH_ORIGINAL_COMMAND": "mrjam-inventory-v1", "BASH_ENV":str(malicious), "ENV":str(malicious), "PYTHONPATH":str(root)}
            result = subprocess.run([str(login), "-c", "mrjam-inventory-v1"], env=env, user=65534, group=65534, extra_groups=[], capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout), {"LANG":"C", "LC_ALL":"C"})
            for args, original in (([], "mrjam-inventory-v1"), (["-c", "sh"], "mrjam-inventory-v1"), (["-c", "mrjam-inventory-v1"], "sh")):
                env["SSH_ORIGINAL_COMMAND"] = original
                denied = subprocess.run([str(login), *args], env=env, user=65534, group=65534, extra_groups=[], capture_output=True)
                self.assertEqual((denied.returncode, denied.stdout, denied.stderr), (64, b"", b""))


if __name__ == "__main__":
    unittest.main()

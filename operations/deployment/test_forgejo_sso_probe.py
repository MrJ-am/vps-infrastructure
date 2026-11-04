import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("sso_probe", Path(__file__).with_name("forgejo_sso_probe.py"))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
SUBJECT = "11111111-2222-3333-4444-555555555555"
SECRET = "INVENTED_PRIVATE_VALUE_NEVER_EXPORTED"
CLIENT = {"clientId":"mrjam-forgejo", "clientSecret":SECRET, "ownerSubject":SUBJECT}


class ClosedProbe(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="sso-probe-", dir=Path.cwd())
        self.directory = Path(self.temporary.name)
        self.path = self.directory / "client.json"
        self.path.write_text(json.dumps(CLIENT))
        self.path.chmod(0o600)

    def tearDown(self):
        self.temporary.cleanup()

    def read(self):
        return m.subject_from_binding(self.path, uid=os.getuid(), gid=os.getgid())

    def test_exact_protected_binding(self):
        self.assertEqual(self.read(), SUBJECT)

    def test_binding_schema_duplicates_and_injection_refused(self):
        for value in [dict(CLIENT, endpoint="https://invented.invalid"),
                      dict(CLIENT, clientId="other"), dict(CLIENT, ownerSubject="';SELECT pg_sleep(50);--"),
                      dict(CLIENT, clientSecret="short")]:
            self.path.write_text(json.dumps(value))
            with self.assertRaises(m.Refused): self.read()
        self.path.write_text('{"clientId":"mrjam-forgejo","clientId":"other"}')
        with self.assertRaises(m.Refused): self.read()

    def test_symlink_hardlink_and_permissions_refused(self):
        target = self.directory / "private"
        self.path.rename(target)
        self.path.symlink_to(target)
        with self.assertRaises(OSError): self.read()
        self.path.unlink()
        os.link(target, self.path)
        with self.assertRaises(m.Refused): self.read()
        target.unlink()
        self.path.chmod(0o644)
        with self.assertRaises(m.Refused): self.read()
        self.path.chmod(0o600)
        self.directory.chmod(0o750)
        with self.assertRaises(m.Refused): self.read()

    def test_oversized_and_parent_symlink_refused(self):
        self.path.write_bytes(b" "*16385)
        with self.assertRaises(m.Refused): self.read()
        alias = self.directory / "alias"
        alias.symlink_to(self.directory)
        with self.assertRaises(OSError):
            m.subject_from_binding(alias / "client.json", uid=os.getuid(), gid=os.getgid())

    def test_fixed_command_drops_to_postgres_and_no_subject_in_argv(self):
        with patch.object(m, "subject_from_binding", return_value=SUBJECT), patch.object(m.subprocess, "run") as run:
            run.return_value.returncode = 0
            run.return_value.stdout = json.dumps(dict.fromkeys(m.CHECKS, True)).encode()
            self.assertTrue(all(m.inspect().values()))
        argv = run.call_args.args[0]
        options = run.call_args.kwargs
        self.assertEqual(argv[0], m.PSQL)
        self.assertEqual((options["user"], options["group"], options["extra_groups"]), (71, 71, []))
        self.assertNotIn(SUBJECT, " ".join(argv))
        self.assertIn(SUBJECT.encode(), options["input"])
        self.assertNotIn(SECRET.encode(), options["input"])
        self.assertEqual(options["stderr"], subprocess.DEVNULL)
        self.assertEqual(options["timeout"], 15)
        self.assertEqual(set(options["env"]), {"HOME","USER","LOGNAME","LANG","LC_ALL","TZ"})

    def test_closed_result_rejects_extra_fields_or_non_booleans(self):
        good = dict.fromkeys(m.CHECKS, True)
        self.assertEqual(m.parse_result(json.dumps(good).encode()), good)
        for bad in [dict(good, cfg=SECRET), dict(good, client_id_preserved=1), dict(good, owner_binding_preserved=SUBJECT)]:
            with self.assertRaises(m.Refused): m.parse_result(json.dumps(bad).encode())

    def test_cli_failure_never_exports_exception_or_private_values(self):
        output = io.StringIO()
        with patch.object(m.sys, "argv", ["probe"]), patch.object(m.os, "geteuid", return_value=0), \
             patch.object(m, "inspect", side_effect=RuntimeError(SECRET + SUBJECT)), \
             patch.object(m.resource, "setrlimit"), patch.object(m.signal, "signal"), \
             patch.object(m.signal, "alarm"), contextlib.redirect_stdout(output):
            self.assertEqual(m.main(), 1)
        result = json.loads(output.getvalue())
        self.assertEqual(result["code"], "SSO_CHECK_UNAVAILABLE")
        self.assertEqual(result["checks"], {})
        self.assertNotIn(SECRET, output.getvalue())
        self.assertNotIn(SUBJECT, output.getvalue())

    def test_arguments_refused_before_any_read(self):
        with patch.object(m.sys, "argv", ["probe", "arbitrary"]), patch.object(m, "inspect") as inspect:
            self.assertEqual(m.main(), 64)
            inspect.assert_not_called()


@unittest.skipUnless(shutil.which("initdb") and shutil.which("psql"), "PostgreSQL binaries are required")
class ActualReadOnlyPostgres(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="sso-pg-", dir=Path.cwd())
        cls.base = Path(cls.temporary.name)
        cls.env = dict(os.environ, PGHOST=str(cls.base), PGPORT="55447", PGDATABASE="postgres")
        subprocess.run(["initdb", "-D", str(cls.base/"db"), "-A", "trust", "--no-locale"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        subprocess.run(["pg_ctl", "-D", str(cls.base/"db"), "-l", str(cls.base/"private.log"),
                        "-o", f"-k {cls.base} -p 55447 -c listen_addresses=''", "-w", "start"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

    @classmethod
    def tearDownClass(cls):
        subprocess.run(["pg_ctl", "-D", str(cls.base/"db"), "-m", "immediate", "-w", "stop"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        cls.temporary.cleanup()

    @classmethod
    def sql(cls, script):
        result = subprocess.run(["psql", "-X", "-w", "-qAt", "--set=ON_ERROR_STOP=1"],
                                input=script.encode() if isinstance(script, str) else script,
                                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=cls.env, check=True)
        return result.stdout

    def setUp(self):
        self.sql('''DROP TABLE IF EXISTS public.login_source, public."user";
CREATE TABLE public.login_source(id bigint PRIMARY KEY,type integer,name text,is_active boolean,cfg text);
CREATE TABLE public."user"(lower_name text,login_type integer,login_source bigint,login_name text,
 is_admin boolean,is_active boolean,prohibit_login boolean,must_change_password boolean,type integer);
''')
        cfg = json.dumps({"Provider":"openidConnect", "ClientID":"mrjam-forgejo",
                          "ClientSecret":SECRET, "OpenIDConnectAutoDiscoveryURL":m.DISCOVERY})
        self.sql("INSERT INTO public.login_source VALUES(7,6,'Kanidm',true,'" + cfg + "');"
                 "INSERT INTO public.\"user\" VALUES('mrjam',6,7,'" + SUBJECT + "',true,true,false,false,0);")

    def probe(self):
        data = self.sql(m.query(SUBJECT))
        self.assertNotIn(SECRET.encode(), data)
        self.assertNotIn(SUBJECT.encode(), data)
        return m.parse_result(data)

    def test_matching_binding_and_rows_unchanged(self):
        snapshot = 'SELECT md5(string_agg(row_to_json(x)::text,\'|\')) FROM (SELECT * FROM public.login_source) x;'
        before = self.sql(snapshot)
        self.assertTrue(all(self.probe().values()))
        self.assertEqual(before, self.sql(snapshot))

    def test_wrong_provider_issuer_and_subject_refused(self):
        self.sql("UPDATE public.login_source SET cfg=jsonb_set(cfg::jsonb,'{OpenIDConnectAutoDiscoveryURL}',"
                 "'\"https://invented.invalid/discovery\"')::text;")
        self.sql("UPDATE public.\"user\" SET login_name='66666666-7777-8888-9999-000000000000';")
        result = self.probe()
        self.assertFalse(result["discovery_preserved"])
        self.assertFalse(result["owner_binding_preserved"])

    def test_second_provider_and_local_password_fallback_refused(self):
        self.sql("INSERT INTO public.login_source VALUES(8,6,'Unexpected',true,'{}');"
                 "UPDATE public.\"user\" SET login_type=1,login_source=0;")
        result = self.probe()
        self.assertFalse(result["one_active_native_provider"])
        self.assertFalse(result["owner_local_login_disabled"])
        self.assertFalse(result["owner_binding_preserved"])

    def test_empty_or_duplicate_cfg_and_disabled_owner_refused(self):
        self.sql("UPDATE public.login_source SET cfg='{\"ClientID\":\"mrjam-forgejo\",\"ClientID\":\"other\"}';"
                 "UPDATE public.\"user\" SET prohibit_login=true;")
        result = self.probe()
        self.assertFalse(result["client_id_preserved"])
        self.assertFalse(result["provider_secret_present"])
        self.assertFalse(result["owner_login_enabled"])

    def test_missing_provider_or_ambiguous_owner_refused(self):
        self.sql("INSERT INTO public.\"user\" SELECT 'mrjam-admin',login_type,login_source,login_name,is_admin,"
                 "is_active,prohibit_login,must_change_password,type FROM public.\"user\";")
        self.assertFalse(self.probe()["owner_binding_preserved"])
        self.sql("DELETE FROM public.login_source;")
        self.assertFalse(self.probe()["one_active_native_provider"])


if __name__ == "__main__":
    unittest.main()

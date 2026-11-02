"""Synthetic-only disclosure/refusal tests. Never call collect on this machine."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("preflight_adoption", Path(__file__).with_name("preflight_adoption.py"))
target = importlib.util.module_from_spec(spec)
spec.loader.exec_module(target)
SECRET = "SYNTHETIC_PRIVATE_VALUE"
CONTACT = "synthetic-private-contact@example.invalid"
NGINX = "/nix/store/" + "0" * 32 + "-nginx.conf"
ROOT = "/nix/store/" + "1" * 32 + "-public-assets"
DOMAIN = "principiipetit.io"
ACCOUNT = "a" * 20
CERTIFICATE = "b" * 20
SCRIPT = "/nix/store/" + "2" * 32 + "-unit-script-acme-order-renew-" + DOMAIN + "-start/bin/acme-order-renew-" + DOMAIN + "-start"


def acme_properties():
    return {
        "StateDirectory": " ".join(("acme/" + DOMAIN, "acme/.lego/" + DOMAIN,
                                    "acme/.lego/" + DOMAIN + "/" + CERTIFICATE, "acme/.lego/accounts/" + ACCOUNT)),
        "BindPaths": " ".join(("/var/lib/acme/.lego/accounts/" + ACCOUNT + ":/tmp/accounts:rbind",
                               "/var/lib/acme/" + DOMAIN + ":/tmp/out:rbind",
                               "/var/lib/acme/.lego/" + DOMAIN + "/" + CERTIFICATE + ":/tmp/certificates:rbind")),
        "ExecStart": "{ path=" + SCRIPT + " ; argv[]=" + SCRIPT + " ; ignore_errors=no ; }"}


def acme_script(extra="", domain=DOMAIN):
    common = "--accept-tos --path . --email '" + CONTACT + "' --http --http.webroot /var/lib/acme/acme-challenge "
    common += "--key-type ec256 -d " + domain + " -d www.principiipetit.io " + extra
    return "#!/bin/sh\n# " + SECRET + "\nif ! lego " + common + " renew --no-random-sleep --dynamic; then\nfalse\n"
    # The second line is assembled by complete_script below.


def complete_script(extra="", domain=DOMAIN):
    first = acme_script(extra, domain)
    arguments = first.split("if ! lego ", 1)[1].split(" renew ", 1)[0]
    return first + "elif ! lego " + arguments + " run; then\nfalse\nfi\n"


class AdoptionPreflightTests(unittest.TestCase):
    def test_01_arguments_refused_before_collection(self):
        result = subprocess.run([sys.executable, str(Path(target.__file__)), "--arbitrary"],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=5)
        self.assertEqual(result.returncode, 64)
        self.assertEqual(result.stdout + result.stderr, b"")

    def test_02_metadata_never_opens_or_follows_final_link(self):
        with tempfile.TemporaryDirectory() as folder:
            value = Path(folder) / "invented-private"
            value.write_text(SECRET)
            link = Path(folder) / "link"
            link.symlink_to(value)
            with patch.object(target.os, "open", side_effect=AssertionError("content forbidden")):
                self.assertEqual(target.metadata(str(link))["kind"], "symlink")
                result = target.metadata(str(value))
                self.assertEqual(result["kind"], "file")
                self.assertNotIn(SECRET, json.dumps(result))

    def test_03_regular_reader_rejects_symlink_traversal_fifo_and_limit(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "file"
            path.write_text("x" * 17)
            link = Path(folder) / "link"
            link.symlink_to(path)
            directory_link = Path(folder) / "linked-dir"
            directory_link.symlink_to(folder)
            fifo = Path(folder) / "fifo"
            os.mkfifo(fifo)
            for item in (str(path), str(link), str(directory_link / "file"), str(fifo), folder + "/../private"):
                with self.subTest(item=item), self.assertRaises((ValueError, OSError)):
                    target.read_regular(item, 16)
            path.write_bytes(b"\xff")
            with self.assertRaises(ValueError):
                target.read_regular(str(path), 16)
            with self.assertRaises(ValueError):
                target.read_regular("/etc/private", 16, immutable=True)

    def test_04_accounts_and_range_never_export_names_or_contact_fields_from_records(self):
        class Record:
            pw_uid, pw_gid, gr_gid = 946, 947, 947
            pw_gecos = CONTACT
            gr_mem = [SECRET]
        with patch.object(target.pwd, "getpwnam", return_value=Record()), \
                patch.object(target.grp, "getgrnam", return_value=Record()), \
                patch.object(target.pwd, "getpwuid", side_effect=KeyError), \
                patch.object(target.grp, "getgrgid", side_effect=OSError):
            output = target.accounts()
        self.assertEqual(set(output["id_availability"]), {str(i) for i in range(940, 971)})
        self.assertEqual(output["id_availability"]["940"], {"uid_available": True, "gid_available": None})
        self.assertIn("vision-auth", output["groups"])
        self.assertNotIn(CONTACT, json.dumps(output))
        self.assertNotIn(SECRET, json.dumps(output))

    def test_05_catalog_only_literal_read_only_catalog_boolean_query(self):
        with patch.object(target, "run", return_value=(0, "|".join(["t", "f"] * 9))) as command:
            output = target.catalog()
        args = command.call_args.args[0]
        self.assertEqual(args[-1], target.CATALOG_SQL)
        self.assertIn("BEGIN READ ONLY;", args[-1])
        self.assertTrue(args[-1].endswith("ROLLBACK;"))
        self.assertEqual(args[:4], ["runuser", "-u", "postgres", "--"])
        self.assertIn("--host=/run/postgresql", args)
        self.assertEqual(set(output["databases"]), set(target.DATABASES))
        self.assertEqual(set(output["roles"]), set(target.ROLES))
        self.assertEqual(set(__import__("re").findall(r"FROM ([a-z_.]+)", target.CATALOG_SQL)),
                         {"pg_catalog.pg_roles", "pg_catalog.pg_database"})
        for answer in (None, (1, "t"), (0, "t|" + SECRET), (0, "|".join(["t"] * 19)), (0, "t\nf")):
            with self.subTest(answer=answer), patch.object(target, "run", return_value=answer):
                self.assertEqual(target.catalog(), target.UNKNOWN)

    def test_06_nginx_non_mrj_hosts_roots_and_location_aliases_preserved(self):
        config = "http { server { server_name principiipetit.io www.principiipetit.io; root " + ROOT + ";"
        config += "location ^~ /matheval/ { proxy_pass http://127.0.0.1:3000; }"
        config += "location = /style.css { alias " + ROOT + "/style.css; }"
        config += "private_setting '" + SECRET + "'; }"
        config += "server { server_name logique.echos.systems; root /srv/logique/current; } }"
        with patch.object(target, "properties", return_value={"ExecStart": "nginx -c " + NGINX + " ;"}), \
                patch.object(target, "read_regular", return_value=config) as reader:
            output = target.nginx_metadata()
        self.assertEqual(output["public_hosts"][DOMAIN][0]["root"], ROOT)
        self.assertEqual(output["public_hosts"][DOMAIN][0]["locations"], [{"selector": "= /style.css", "alias": ROOT + "/style.css"}])
        self.assertEqual(output["public_hosts"]["logique.echos.systems"][0]["root"], "/srv/logique/current")
        reader.assert_called_once_with(NGINX, 1024 * 1024, immutable=True)
        self.assertNotIn(SECRET, json.dumps(output))

    def test_07_nginx_rejects_ambiguous_source_and_paths(self):
        for value in ("nginx -c /etc/private", "nginx -c " + NGINX + " -c " + NGINX,
                      "nginx -c " + NGINX + "/../private", "nginx -c " + NGINX + ".private"):
            with self.subTest(value=value), patch.object(target, "properties", return_value={"ExecStart": value}), \
                    patch.object(target, "read_regular", side_effect=AssertionError("no read")):
                self.assertEqual(target.nginx_metadata(), target.UNKNOWN)
        for path in (ROOT + "/../private", "/var/lib/private", ROOT + "/$secret", "/srv/logique/../private"):
            self.assertIsNone(target.public_path(path))
        for config in ("server { server_name principiipetit.io; root " + ROOT + "; root " + ROOT + "; }",
                       "server { server_name principiipetit.io;", "server { server_name principiipetit.io; server_name log.mrj.am; }"):
            with patch.object(target, "properties", return_value={"ExecStart": "nginx -c " + NGINX}), \
                    patch.object(target, "read_regular", return_value=config):
                self.assertEqual(target.nginx_metadata(), target.UNKNOWN)

    def test_08_nginx_comments_cannot_inject_public_mappings_and_private_roots_are_omitted(self):
        config = "# server { server_name principiipetit.io; root " + ROOT + "; }\n"
        config += "server { server_name log.mrj.am; root /var/lib/private/" + SECRET + ";"
        config += "include /etc/private; location / { return 200 '{\"hidden\":\"" + SECRET + "\"}'; } }"
        with patch.object(target, "properties", return_value={"ExecStart": "nginx -c " + NGINX}), \
                patch.object(target, "read_regular", return_value=config) as reader:
            output = target.nginx_metadata()
        self.assertEqual(set(output["public_hosts"]), {"log.mrj.am"})
        self.assertTrue(output["public_hosts"]["log.mrj.am"][0]["unreported_mapping_present"])
        self.assertTrue(output["public_hosts"]["log.mrj.am"][0]["includes_present"])
        self.assertEqual(reader.call_count, 1)
        self.assertNotIn(SECRET, json.dumps(output))

    def test_09_acme_hashes_require_consistent_bindings(self):
        values = acme_properties()
        self.assertEqual(target.acme_layout(values, DOMAIN), (ACCOUNT, CERTIFICATE))
        for changed in (dict(values, StateDirectory=values["StateDirectory"] + " acme/private"),
                        dict(values, BindPaths=values["BindPaths"].replace(ACCOUNT, "c" * 20)),
                        dict(values, StateDirectory=values["StateDirectory"].replace(ACCOUNT, "../private"))):
            with self.assertRaises(ValueError):
                target.acme_layout(changed, DOMAIN)

    def test_10_acme_only_selected_immutable_script_is_admitted(self):
        values = acme_properties()
        self.assertEqual(target.acme_script_path(values["ExecStart"], DOMAIN), SCRIPT)
        for changed in (values["ExecStart"] + values["ExecStart"], values["ExecStart"].replace(SCRIPT, "/etc/private"),
                        values["ExecStart"].replace("argv[]=" + SCRIPT, "argv[]=" + SCRIPT + " " + SECRET),
                        values["ExecStart"].replace("/bin/", "/../bin/")):
            with self.assertRaises(ValueError):
                target.acme_script_path(changed, DOMAIN)

    def test_11_acme_options_export_no_contact_or_unknown_flag_value(self):
        output = target.acme_options(complete_script("--extra-private=" + SECRET), DOMAIN)
        self.assertEqual(output["domain"], DOMAIN)
        self.assertEqual(output["sans"], ["www.principiipetit.io"])
        self.assertEqual(output["key_type"], "ec256")
        self.assertTrue(output["extra_flags_present"])
        self.assertNotIn(CONTACT, json.dumps(output))
        self.assertNotIn(SECRET, json.dumps(output))
        self.assertFalse(target.acme_options(complete_script(), DOMAIN)["extra_flags_present"])

    def test_12_acme_ambiguous_or_secret_shaped_public_values_refused(self):
        source = complete_script()
        for changed in (source + source, source.replace("--key-type ec256", "--key-type ec256 --key-type rsa4096"),
                        source.replace("--key-type ec256", "--key-type " + SECRET),
                        source.replace("--http.webroot /var/lib/acme/acme-challenge", "--http.webroot /var/lib/private/" + SECRET),
                        source.replace("--key-type", "--server https://private.invalid/" + SECRET + " --key-type"),
                        source.replace("run;", "renew;"), source.replace(" -d " + DOMAIN, " -d private.invalid")):
            with self.subTest(changed=changed[:20]), self.assertRaises(ValueError):
                target.acme_options(changed, DOMAIN)

    def test_13_account_presence_counts_metadata_only_and_never_exports_filenames(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "keys").mkdir()
            (root / "keys" / (CONTACT + ".key")).write_text(SECRET)
            (root / "account.json").write_text(SECRET)
            real_open = os.open
            descriptor = real_open(folder, os.O_RDONLY | os.O_DIRECTORY)
            def directories_only(path, flags, *args, **kwargs):
                self.assertTrue(flags & os.O_DIRECTORY, "key/registration content open forbidden")
                return real_open(path, flags, *args, **kwargs)
            with patch.object(target, "open_components", return_value=descriptor), \
                    patch.object(target.os, "open", side_effect=directories_only):
                output = target.account_material(ACCOUNT)
            self.assertEqual(output, {"state": "observed", "unique_key_present": True,
                                      "unique_registration_present": True, "matching_unique_pair": True})
            self.assertNotIn(CONTACT, json.dumps(output))
            self.assertNotIn(SECRET, json.dumps(output))

    def test_14_account_symlinks_duplicate_pairs_and_missing_are_not_success(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "leak.key").symlink_to("/etc/private")
            with patch.object(target, "open_components", return_value=os.open(folder, os.O_RDONLY | os.O_DIRECTORY)):
                self.assertEqual(target.account_material(ACCOUNT), target.UNKNOWN)
            (root / "leak.key").unlink()
            for name in ("one.key", "two.key", "account.json"):
                (root / name).write_text(SECRET)
            with patch.object(target, "open_components", return_value=os.open(folder, os.O_RDONLY | os.O_DIRECTORY)):
                output = target.account_material(ACCOUNT)
            self.assertFalse(output["unique_key_present"])
            self.assertFalse(output["matching_unique_pair"])
        with patch.object(target, "open_components", side_effect=FileNotFoundError):
            self.assertEqual(target.account_material(ACCOUNT)["state"], "absent")
        self.assertEqual(target.account_material("../private"), target.UNKNOWN)

    def test_15_timer_closed_calendar_jitter_and_ambiguity(self):
        values = {"TimersCalendar": "{ OnCalendar=*-*-* 00:00:00 ; next_elapse=SECRET ; }", "RandomizedDelayUSec": "1d"}
        with patch.object(target, "properties", return_value=values):
            self.assertEqual(target.acme_timer(DOMAIN), {"state": "observed", "calendar": "*-*-* 00:00:00", "randomized_delay": "1d"})
        for changed in (dict(values, TimersCalendar=values["TimersCalendar"] * 2),
                        dict(values, RandomizedDelayUSec=SECRET), dict(values, TimersCalendar="OnCalendar=" + SECRET)):
            with patch.object(target, "properties", return_value=changed):
                self.assertEqual(target.acme_timer(DOMAIN), target.UNKNOWN)

    def test_16_failed_commands_and_duplicate_properties_are_unknown(self):
        for value in (None, (1, SECRET), (0, "LoadState=loaded\nLoadState=loaded\nActiveState=active")):
            with patch.object(target, "run", return_value=value):
                with self.assertRaises(ValueError):
                    target.properties("known.service", ("LoadState", "ActiveState"))
        with patch.object(target, "properties", side_effect=ValueError):
            self.assertTrue(all(value == target.UNKNOWN for value in target.unit_states().values()))

    def test_17_host_profile_only_emits_comparisons(self):
        def documents(arguments):
            if arguments[0] == "findmnt":
                return {"filesystems": [{"uuid": target.EXPECTED_ROOT_UUID, "fstype": "ext4"}]}
            if "address" in arguments:
                return [{"ifname": "eth0", "address": target.EXPECTED_MAC, "addr_info": [
                    {"local": "187.77.95.158", "prefixlen": 24, "scope": "global"},
                    {"local": "2a02:4780:41:cf57::1", "prefixlen": 48, "scope": "global"}]}]
            return [{"dev": "eth0", "dst": "default", "gateway": "187.77.95.254" if "-4" in arguments else "2a02:4780:41::1"}]
        with patch.object(target, "command_json", side_effect=documents), \
                patch.object(target, "run", return_value=(0, "Link 2 (eth0): 153.92.2.6 1.1.1.1 8.8.4.4")), \
                patch.object(target.socket, "gethostname", return_value="nixos"), \
                patch.object(target.os, "lstat", side_effect=FileNotFoundError):
            output = target.host_comparisons()
        self.assertTrue(output["addresses_match"] and output["gateways_match"] and output["dns_matches"])
        self.assertTrue(all(value is None or isinstance(value, bool) for value in output.values()))
        for forbidden in target.EXPECTED_ADDRESSES | target.EXPECTED_GATEWAYS | target.EXPECTED_DNS:
            self.assertNotIn(forbidden, json.dumps(output))

    def test_18_embeddings_exact_public_references_and_no_free_arguments(self):
        python = "/nix/store/" + "3" * 32 + "-python3-3.14.8/bin/python3"
        script, model = ROOT + "/scripts/embeddings.py", ROOT + "/model"
        args = " ".join((python, script, "--modele", model))
        values = {"LoadState": "loaded", "ActiveState": "active", "ExecStart": "{ path=" + python + " ; argv[]=" + args + " ; }"}
        with patch.object(target, "properties", return_value=values):
            self.assertEqual(target.embeddings_metadata(), {"state": "observed", "loaded": True, "active": True,
                                                             "python": python, "script": script, "model": model})
        for changed in (values["ExecStart"].replace(model, "/var/lib/private"),
                        values["ExecStart"].replace(model, model + " --token " + SECRET),
                        values["ExecStart"].replace("/scripts/", "/../scripts/"),
                        values["ExecStart"] * 2):
            with patch.object(target, "properties", return_value=dict(values, ExecStart=changed)):
                self.assertEqual(target.embeddings_metadata(), target.UNKNOWN)

    def test_19_runner_bounds_stdout_and_wall_time(self):
        self.assertIsNone(target.run([sys.executable, "-c", "print('x'*70000)"]))
        before = time.monotonic()
        with patch.object(target, "DEADLINE", time.monotonic() + 0.05):
            self.assertIsNone(target.run([sys.executable, "-c", "import time; time.sleep(10)"]))
        self.assertLess(time.monotonic() - before, 2)

    def test_20_complete_acme_observation_keeps_source_and_contact_private(self):
        with patch.object(target, "properties", return_value=acme_properties()), \
                patch.object(target, "read_regular", return_value=complete_script()) as reader, \
                patch.object(target, "account_material", return_value={"state": "observed", "matching_unique_pair": True}), \
                patch.object(target, "acme_timer", return_value={"state": "unknown"}):
            output = target.acme_metadata(DOMAIN)
        self.assertEqual(output["state"], "observed")
        self.assertEqual(output["account_hash"], ACCOUNT)
        self.assertEqual(output["certificate_directory_hash"], CERTIFICATE)
        reader.assert_called_once_with(SCRIPT, 131072, immutable=True)
        for private in (SECRET, CONTACT, SCRIPT, "ExecStart", "StateDirectory", "BindPaths"):
            self.assertNotIn(private, json.dumps(output))

    def test_21_public_domains_are_discovered_bounded_without_emails_regex_or_wildcards(self):
        self.assertTrue(target.public_domain("style.echos.systems"))
        self.assertTrue(target.public_domain("logo.principiipetit.io"))
        for invalid in (CONTACT, "*.mrj.am", "~^secret.*", "mrj.am/private", "mrj-auth.internal", "localhost",
                        "mrj..am", "-bad.mrj.am", "bad-.mrj.am", "a" * 64 + ".mrj.am"):
            self.assertFalse(target.public_domain(invalid))
        source = "server { server_name style.echos.systems logo.principiipetit.io *.mrj.am " + CONTACT + "; root " + ROOT + "; }"
        with patch.object(target, "properties", return_value={"ExecStart": "nginx -c " + NGINX}), \
                patch.object(target, "read_regular", return_value=source):
            output = target.nginx_metadata()
        self.assertEqual(set(output["public_hosts"]), {"style.echos.systems", "logo.principiipetit.io"})
        source = "server { server_name " + " ".join("site-" + str(i) + ".mrj.am" for i in range(33)) + "; }"
        with patch.object(target, "properties", return_value={"ExecStart": "nginx -c " + NGINX}), \
                patch.object(target, "read_regular", return_value=source):
            self.assertEqual(target.nginx_metadata(), target.UNKNOWN)

    def test_22_account_registration_must_be_parent_of_the_unique_keys_directory(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "keys").mkdir()
            (root / "other").mkdir()
            (root / "keys" / (CONTACT + ".key")).write_text(SECRET)
            (root / "other" / "account.json").write_text(SECRET)
            with patch.object(target, "open_components", return_value=os.open(folder, os.O_RDONLY | os.O_DIRECTORY)):
                output = target.account_material(ACCOUNT)
            self.assertTrue(output["unique_key_present"] and output["unique_registration_present"])
            self.assertFalse(output["matching_unique_pair"])


    def test_23_layout_catalog_rejects_free_outputs_and_command_failure(self):
        for value in (None, (1, ""), (0, CONTACT), (0, "t|f"), (0, "t|" * 8),
                      (0, "|".join(["t"] * 7 + [SECRET]))):
            with patch.object(target, "run", return_value=value):
                self.assertEqual(target.catalog_layout(), target.UNKNOWN)
        with patch.object(target, "run", return_value=(0, "|".join(["t"] * 8))) as call:
            result = target.catalog_layout()
        self.assertEqual(set(result["catalog_only"]), set(target.LAYOUT_FIELDS))
        self.assertTrue(all(result["catalog_only"].values()))
        command = call.call_args[0][0]
        self.assertIn("--dbname=vision", command)
        self.assertEqual(command[-1], target.LAYOUT_SQL)
        self.assertIn("BEGIN READ ONLY;", command[-1])
        self.assertIn("ROLLBACK;", command[-1])
        self.assertNotIn("FROM audition.", command[-1])
        self.assertNotIn("FROM vision_gestion.", command[-1])

    def test_24_hostname_only_accepts_a_machine_label(self):
        for value in (CONTACT, SECRET + "/private", "bad.name", "a" * 64, "", "bad\nname"):
            with patch.object(target.socket, "gethostname", return_value=value):
                self.assertEqual(target.public_hostname(), target.UNKNOWN)
        with patch.object(target.socket, "gethostname", return_value="synthetic-vps"):
            self.assertEqual(target.public_hostname(), {"state": "observed", "value": "synthetic-vps"})


    def test_25_code_metadata_never_exports_non_store_or_raw_output(self):
        with patch.object(target, "run", return_value=(0, SECRET)):
            result = target.embedding_code_metadata()
        self.assertTrue(all(item == target.UNKNOWN for item in result.values()))
        self.assertNotIn(SECRET, json.dumps(result))
        root = next(iter(target.EMBEDDING_ROOTS.values()))
        with patch.object(target, "run", side_effect=[(0, "sha256:" + "0" * 52),
                (0, root + ".drv"), (0, "/var/lib/mrjam-metier/log/sessions.sqlite")] * 3) as call:
            result = target.embedding_code_metadata()
        self.assertTrue(all(item == target.UNKNOWN for item in result.values()))
        self.assertTrue(all(args[0][0][-1] in target.EMBEDDING_ROOTS.values() for args in call.call_args_list))

    def test_26_generation_refuses_arbitrary_targets(self):
        with patch.object(target.os.path, "realpath", return_value="/var/lib/private"):
            self.assertEqual(target.generation_metadata(), target.UNKNOWN)

    def test_27_schema_probe_emits_only_closed_catalog_and_migration_metadata(self):
        with patch.object(target, "run", side_effect=[(0,"|".join(["t"]*5)),
                (0,"|".join(["t"]*9)), (0,"1"*25+"00|t|t")]) as calls:
            output = target.schema_metadata()
        self.assertEqual(output["vision_migration_metadata"]["known_versions_present"], list(range(1,26)))
        self.assertTrue(output["matheval"]["catalog_only"]["session_activity_column"])
        self.assertEqual([call.args[0][-1] for call in calls.call_args_list],
                         [target.VISION_SCHEMA_SQL,target.MATHEVAL_SCHEMA_SQL,target.VISION_VERSIONS_SQL])
        for call in calls.call_args_list:
            self.assertTrue(call.args[0][-1].startswith("BEGIN READ ONLY;"))
            self.assertTrue(call.args[0][-1].endswith("ROLLBACK;"))

    def test_28_schema_probe_never_reads_business_rows_and_refuses_unbounded_output(self):
        for sql in (target.VISION_SCHEMA_SQL,target.MATHEVAL_SCHEMA_SQL):
            self.assertNotRegex(sql, r"FROM (public|vision_gestion|audition)\.")
        for response in (SECRET, "1"*28+"|t|t", "1"*27+"|t|"+CONTACT, "1"*27+"|t|t\n"):
            with patch.object(target, "run", side_effect=[(0,"|".join(["t"]*5)),
                    (0,"|".join(["f"]*9)),(0,response)]):
                output=target.schema_metadata()
            self.assertEqual(output["vision_migration_metadata"],target.UNKNOWN)
            self.assertNotIn(SECRET,json.dumps(output))
            self.assertNotIn(CONTACT,json.dumps(output))
        with patch.object(target,"run",return_value=(0,SECRET)) as calls:
            output=target.schema_metadata()
        self.assertEqual(calls.call_count,2)
        self.assertTrue(all(item==target.UNKNOWN for item in output.values()))


if __name__ == "__main__":
    unittest.main()

"""Real native online export and offline restoration, invented local identities."""
import gzip
import http.client
from http.cookies import SimpleCookie
import json
import os
from pathlib import Path
import socket
import ssl
import subprocess
import sys
import tempfile
import time


class Refused(RuntimeError):
    pass


def require(condition, code):
    if not condition:
        raise Refused(code)


def command(arguments, destination=None):
    result = subprocess.run(arguments, stdin=subprocess.DEVNULL,
                            stdout=destination or subprocess.PIPE, stderr=subprocess.PIPE,
                            check=False, timeout=120)
    require(result.returncode == 0, "SYNTHETIC_NATIVE_COMMAND_FAILED")
    return result.stdout


class TLS(http.client.HTTPConnection):
    def __init__(self, port, certificate):
        super().__init__("127.0.0.1", port, timeout=10)
        self.context = ssl.create_default_context(cafile=certificate)

    def connect(self):
        self.sock = self.context.wrap_socket(socket.create_connection(("127.0.0.1", self.port), timeout=10),
                                             server_hostname="log.mrj.am")


class Native:
    def __init__(self, root, command_path, certificate, key):
        self.root, self.command_path, self.certificate = Path(root), command_path, certificate
        self.root.mkdir(mode=0o700)
        with socket.socket() as reserved:
            reserved.bind(("127.0.0.1", 0))
            self.port = reserved.getsockname()[1]
        self.config = self.root / "server.toml"
        self.config.write_text("\n".join([
            'version = "2"', 'domain = "log.mrj.am"', 'origin = "https://log.mrj.am"',
            'bindaddress = "127.0.0.1:' + str(self.port) + '"',
            'db_path = ' + json.dumps(str(self.root / "kanidm.db")),
            'tls_chain = ' + json.dumps(str(certificate)), 'tls_key = ' + json.dumps(str(key)),
            'adminbindpath = ' + json.dumps(str(self.root / "admin.sock")),
            'log_level = "info"', '[online_backup]', 'enabled = false',
            'path = ' + json.dumps(str(self.root / "backups")), 'schedule = "00 22 * * *"',
            'versions = 1', 'compression = "gzip"']) + "\n")
        self.process = None
        self.log = None

    def start(self):
        self.log = (self.root / "private-synthetic.log").open("ab")
        self.process = subprocess.Popen([self.command_path, "server", "-c", str(self.config)],
            stdin=subprocess.DEVNULL, stdout=self.log, stderr=subprocess.STDOUT)
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            require(self.process.poll() is None, "SYNTHETIC_NATIVE_START_FAILED")
            try:
                if self.request("/status")[0] == 200:
                    return
            except (OSError, http.client.HTTPException):
                pass
            time.sleep(0.2)
        raise Refused("SYNTHETIC_NATIVE_START_TIMEOUT")

    def stop(self):
        if self.process and self.process.poll() is None:
            self.process.terminate()
            self.process.wait(timeout=30)
        if self.log:
            self.log.close()

    def request(self, path, body=None, bearer=None, cookie=None):
        connection = TLS(self.port, self.certificate)
        headers = {"Host": "log.mrj.am", "Accept": "application/json", "Connection": "close"}
        if body is not None:
            headers["Content-Type"] = "application/json"
        if bearer:
            headers["Authorization"] = "Bearer " + bearer
        if cookie:
            headers["Cookie"] = cookie
        try:
            connection.request("POST" if body is not None else "GET", path,
                               None if body is None else json.dumps(body).encode(), headers)
            response = connection.getresponse()
            data = response.read(1024 * 1024 + 1)
            require(len(data) <= 1024 * 1024, "SYNTHETIC_NATIVE_RESPONSE_LIMIT")
            return response.status, response.getheaders(), data
        finally:
            connection.close()

    def api(self, path, body=None, bearer=None):
        status, _, body = self.request(path, body, bearer)
        require(status == 200, "SYNTHETIC_NATIVE_API_FAILED")
        return json.loads(body) if body else None

    def recover(self):
        value = json.loads(command([self.command_path, "-c", str(self.config), "scripting", "recover-account", "idm_admin"]))
        require(value.get("status") == "ok" and isinstance(value.get("output"), str), "SYNTHETIC_RECOVERY_FAILED")
        return value["output"]

    def login(self, password):
        jar = {}
        steps = [({"step": {"init2": {"username": "idm_admin", "issue": "token", "privileged": True}}}, "choose"),
                 ({"step": {"begin": "password"}}, "continue"),
                 ({"step": {"cred": {"password": password}}}, "success")]
        for request, expected in steps:
            status, headers, body = self.request("/v1/auth", request, cookie="; ".join(k + "=" + v for k, v in jar.items()))
            require(status == 200, "SYNTHETIC_NATIVE_LOGIN_FAILED")
            for name, value in headers:
                if name.lower() == "set-cookie":
                    parsed = SimpleCookie()
                    parsed.load(value)
                    jar.update({key: item.value for key, item in parsed.items()})
            document = json.loads(body)
            require(expected in document.get("state", {}), "SYNTHETIC_NATIVE_LOGIN_STATE_FAILED")
        return document["state"]["success"]


def qualify(kanidmd, openssl, result_path):
    os.umask(0o077)
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        key, certificate = root / "tls.key", root / "tls.pem"
        command([openssl, "req", "-x509", "-newkey", "ec", "-pkeyopt", "ec_paramgen_curve:prime256v1",
                 "-nodes", "-subj", "/CN=log.mrj.am", "-addext", "subjectAltName=DNS:log.mrj.am",
                 "-keyout", str(key), "-out", str(certificate), "-days", "1"])
        original = Native(root / "original", kanidmd, certificate, key)
        restored = Native(root / "restored", kanidmd, certificate, key)
        try:
            original.start()
            password = original.recover()
            token = original.login(password)
            original.api("/v1/person", {"attrs": {"name": ["synthetic_backup_person"],
                "displayname": ["Invented Backup Person"]}}, token)
            before = original.api("/v1/person/synthetic_backup_person", bearer=token)
            backup = root / "kanidm.json.gz"
            with backup.open("xb") as output:
                command([kanidmd, "-c", str(original.config), "scripting", "backup"], output)
            require(original.process.poll() is None, "NATIVE_EXPORT_STOPPED_PROVIDER")
            # Validate the complete actual gzip stream, without printing entries.
            with gzip.open(backup, "rb") as stream:
                require(bool(stream.read()), "NATIVE_EXPORT_EMPTY")
            original.stop()
            command([kanidmd, "-c", str(restored.config), "database", "restore", str(backup)])
            require((restored.root / "kanidm.db").is_file(), "NATIVE_RESTORE_DATABASE_ABSENT")
            restored.start()
            restored_token = restored.login(password)
            after = restored.api("/v1/person/synthetic_backup_person", bearer=restored_token)
            for name in ("uuid", "name", "displayname"):
                require(before["attrs"][name] == after["attrs"][name], "NATIVE_RESTORE_PRINCIPAL_CHANGED")
            result = {"schema_version": 1, "synthetic_only": True, "production_access": False,
                      "passed": True, "groups": 4, "native_version": "1.11.2",
                      "checks": ["real-native-tls-and-invented-person", "online-scripting-export-valid-gzip",
                                 "offline-native-restoration", "retained-principal-uuid-and-admin-credential"],
                      "limitations": ["Local processes, not the production systemd sandbox or recipient key"]}
            Path(result_path).write_text(json.dumps(result, sort_keys=True) + "\n")
        finally:
            original.stop()
            restored.stop()


if __name__ == "__main__":
    try:
        require(len(sys.argv) == 4, "SYNTHETIC_ARGUMENTS_REFUSED")
        qualify(*sys.argv[1:])
    except Exception:
        print('{"error":"SYNTHETIC_NATIVE_BACKUP_QUALIFICATION_FAILED"}', file=sys.stderr)
        raise SystemExit(1)

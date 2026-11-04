"""Invented VM only; independent black-box Unix and real-provider assertions."""
import hashlib
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import re
import socket
import stat
import subprocess
import sys
import ssl
import time

sys.path.insert(0, "/etc")
import workers_fixture as w

SOCKET = "/run/mrjam-identity-deletion/delete.sock"
TOKEN = Path("/var/lib/mrjam-identite/kanidm-replay.token")
TRACE = Path("/var/lib/kanidm/adapter-spy.json")


def require(condition, code):
    if not condition:
        raise RuntimeError(code)


def subject():
    return w.read("adapter.json")["subject"]


def packet(value=None):
    return json.dumps(value or {"issuer": w.ISSUER, "subject": subject()}, separators=(",", ":")).encode() + b"\n"


def client(stalled=False):
    payload = sys.stdin.buffer.read(1025)
    require(len(payload) <= 1024, "CLIENT_FIXTURE_LIMIT")
    with socket.socket(socket.AF_UNIX) as sock:
        sock.settimeout(15)
        sock.connect(SOCKET)
        sock.sendall(payload)
        if not stalled:
            sock.shutdown(socket.SHUT_WR)
        response = bytearray()
        while True:
            try:
                part = sock.recv(64)
            except ConnectionResetError:
                raise RuntimeError("TRANSPORT_RESET_AFTER_RESPONSE" if response else "TRANSPORT_RESET_WITHOUT_RESPONSE") from None
            if not part:
                break
            response.extend(part)
            require(len(response) <= 32, "UNBOUNDED_RESPONSE")
    require(response.endswith(b"\n") and response.count(b"\n") == 1, "RESPONSE_FRAME")
    value = json.loads(response)
    require(value in ({"status": "deleted"}, {"status": "absent"}, {"error": "refused"}, {"error": "unavailable"}), "RESPONSE_VOCABULARY")
    sys.stdout.buffer.write(response)


def request(payload=None, uid=944, stalled=False):
    result = subprocess.run([sys.executable, "-B", __file__, "stalled-client" if stalled else "client"], input=packet() if payload is None else payload, capture_output=True,
                            timeout=17, user=uid, group=944, extra_groups=[944])
    if result.returncode != 0 or result.stderr:
        closed = re.fullmatch(rb"SYNTHETIC_DELETE_FAILED:([A-Za-z_]+)\n", result.stderr)
        raise RuntimeError("UNIX_CLIENT_" + closed[1].decode().upper() if closed else "UNIX_CLIENT_FAILED")
    return json.loads(result.stdout)


def exists(identifier):
    status, _, body = w.native().request("/v1/person/" + identifier, bearer=w.read("native.json")["idm"])
    require(status in (200, 404), "NATIVE_LOOKUP_FAILED")
    return status == 200 and json.loads(body) is not None


def prepare():
    # Match the production adapter's upstream scope exactly. The historical
    # native-worker fixture has an additional mail-read membership; it is not
    # reused as this adapter's credential.
    n = w.native()
    administrative = w.read("native.json")["idm"]
    name = "synthetic_socket_deletion"
    n.api("/v1/service_account", {"attrs": {"name": [name], "displayname": ["Invented socket deletion"],
                                           "entry_managed_by": ["idm_service_account_admins"]}}, bearer=administrative)
    n.api("/v1/group/idm_people_admins/_attr/member", [name], bearer=administrative)
    token = n.api("/v1/service_account/" + name + "/_api_token",
                  {"label": "invented-socket-only", "expiry": int(time.time()) + 3600, "read_write": True}, bearer=administrative)
    own = n.api("/v1/self", bearer=token)["youare"]["attrs"]
    require({group.removesuffix("@log.mrj.am") for group in own["memberof"]}
            == {"idm_people_admins", "idm_high_privilege", "idm_all_accounts"}, "UPSTREAM_ROLE_MISMATCH")
    w.private_file(TOKEN, token, mode=0o600)
    token_digest = hashlib.sha256(TOKEN.read_bytes()).hexdigest()
    n.api("/v1/person", {"attrs": {"name": ["synthetic_adapter_target"], "displayname": ["Invented deletion target"],
                                   "mail": ["target@synthetic.invalid"]}}, bearer=w.read("native.json")["idm"])
    identifier = n.api("/v1/person/synthetic_adapter_target", bearer=w.read("native.json")["idm"])["attrs"]["uuid"][0]
    w.save("adapter.json", {"subject": identifier, "token_sha256": token_digest})


def metadata():
    directory = Path(SOCKET).parent.stat()
    item = Path(SOCKET).stat()
    require((directory.st_uid, directory.st_gid, stat.S_IMODE(directory.st_mode)) == (948, 944, 0o750), "RUNTIME_DIRECTORY_METADATA")
    require(stat.S_ISSOCK(item.st_mode) and (item.st_uid, item.st_gid, stat.S_IMODE(item.st_mode)) == (948, 944, 0o660), "SOCKET_METADATA")
    pid = int(w.command(["systemctl", "show", "mrjam-identity-deletion", "-p", "MainPID", "--value"]))
    fields = dict(line.split(":", 1) for line in Path("/proc", str(pid), "status").read_text().splitlines() if ":" in line)
    require(set(fields["Uid"].split()) == {"948"} and set(fields["Gid"].split()) == {"944"}, "ADAPTER_PROCESS_IDENTITY")
    require(fields["CapEff"].strip() == "0000000000000000", "ADAPTER_RETAINED_CAPABILITIES")
    # systemctl show renders this D-Bus tuple differently from its unit syntax.
    # Check the selected unit and every drop-in rather than guessing that display.
    selected_unit = w.command(["systemctl", "cat", "mrjam-vision-replay"])
    credentials = [line for line in selected_unit.splitlines() if line.startswith(b"LoadCredential=")]
    require(credentials == [b"LoadCredential=admissions:/var/lib/synthetic-worker-credentials/closure"],
            "REPLAY_PROVIDER_CREDENTIAL")
    # Readability is tested as replay, including inside the adapter mount namespace.
    probe = "import os; p='/run/credentials/mrjam-identity-deletion.service/kanidm'; os.setgroups([]); os.setgid(944); os.setuid(944); open(p,'rb').read(1)"
    result = subprocess.run(["nsenter", "--mount=/proc/" + str(pid) + "/ns/mnt", "--", sys.executable, "-c", probe], capture_output=True)
    require(result.returncode != 0, "REPLAY_CAN_READ_ADAPTER_CREDENTIAL")
    result = subprocess.run([sys.executable, "-c", "open('/var/lib/mrjam-identite/kanidm-replay.token','rb').read(1)"],
                            user=944, group=944, extra_groups=[], capture_output=True)
    require(result.returncode != 0, "REPLAY_CAN_READ_SOURCE_CREDENTIAL")


def negatives():
    good = {"issuer": w.ISSUER, "subject": subject()}
    for uid in (0, 949):
        require(request(packet(good), uid) == {"error": "refused"}, "WRONG_PEER_ACCEPTED")
    bad = [packet(dict(good, **{key: value})) for key, value in (
        ("operation", "reset"), ("operation", "list"), ("group", "idm_admins"), ("token", "invented"),
        ("url", "https://outside.invalid/"), ("method", "POST"), ("path", "/v1/group/idm_admins"),
        ("password", "invented"), ("issuer", "https://wrong.invalid"), ("subject", subject().upper()),
        ("subject", "../../group/idm_admins"), ("subject", "a" * 36))]
    bad += [b'{"issuer":' + json.dumps(w.ISSUER).encode() + b',"issuer":' + json.dumps(w.ISSUER).encode()
            + b',"subject":' + json.dumps(subject()).encode() + b'}\n',
            packet(good) + packet(good), packet(good).rstrip(b"\n"), b"{\n", b"", b"x" * 257 + b"\n"]
    for payload in bad:
        require(request(payload) == {"error": "refused"}, "INVALID_REQUEST_ACCEPTED")
    started = time.monotonic()
    require(request(b"{", stalled=True) == {"error": "refused"}, "STALLED_REQUEST_ACCEPTED")
    require(time.monotonic() - started < 5, "STALLED_REQUEST_UNBOUNDED")


def ready():
    require(request(uid=0) == {"error": "refused"}, "ADAPTER_NOT_READY")


def preserved():
    require(exists(subject()), "REFUSAL_CHANGED_TARGET")
    require(exists(w.read("synthetic_survivor.json")["subject"]), "REFUSAL_CHANGED_SURVIVOR")


def unavailable():
    require(request() == {"error": "unavailable"}, "OUTAGE_CLAIMED_SUCCESS")


def deleted():
    require(request() == {"status": "deleted"}, "EXISTING_PERSON_NOT_DELETED")
    require(not exists(subject()), "NATIVE_PERSON_STILL_PRESENT")
    require(request() in ({"status": "deleted"}, {"status": "absent"}), "DELETE_NOT_IDEMPOTENT")
    require(exists(w.read("synthetic_survivor.json")["subject"]), "DELETE_CHANGED_SURVIVOR")


def spy():
    TRACE.write_text("[]")
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass
        def handle_request(self):
            events = json.loads(TRACE.read_text())
            events.append({"method": self.command, "path": self.path, "host_valid": self.headers.get("Host") == "log.mrj.am",
                           "bearer_present": self.headers.get("Authorization", "").startswith("Bearer ")})
            TRACE.write_text(json.dumps(events))
            self.send_response(204)
            self.send_header("Connection", "close")
            self.end_headers()
        do_DELETE = do_GET = do_POST = do_PUT = do_PATCH = handle_request
    server = HTTPServer(("127.0.0.1", 8443), Handler)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain("/etc/synthetic-identity-tls/fullchain.pem", "/etc/synthetic-identity-tls/key.pem")
    server.socket = context.wrap_socket(server.socket, server_side=True)
    server.serve_forever()


def spy_check():
    negatives()
    require(json.loads(TRACE.read_text()) == [], "REFUSAL_REACHED_UPSTREAM")
    require(request() == {"status": "deleted"}, "SPY_DELETE_NOT_ACCEPTED")
    require(json.loads(TRACE.read_text()) == [{"method": "DELETE", "path": "/v1/person/" + subject(),
                                             "host_valid": True, "bearer_present": True}], "UPSTREAM_CAPABILITY_TOO_BROAD")


def closure_start():
    identifier = w.read("synthetic_cycle.json")["subject"]
    w.save("partial.json", {"subject": identifier})
    w.closure_request()


def closure_partial():
    w.closure_partial()
    require(exists(w.read("closure.json")["subject"]), "EARLY_PROVIDER_DELETION")


def replayed():
    d = w.read("closure.json")
    require(w.snapshot(d["accounts"][0]) == {"compte": None, "profil": None, "fiches": None}, "REPLAY_RETAINED_CONTENT")
    require(not exists(d["subject"]), "REPLAY_RETAINED_NATIVE_PERSON")
    require(w.sql("SELECT (applique_sha256=archive_sha256)::int FROM vision_effacements.fermetures WHERE sujet='" + d["subject"] + "'", "vision_journal") == "1", "REPLAY_MISSING_RECEIPT")
    require(w.snapshot("synthetic_survivor") == w.read("survivor.json") and exists(w.read("synthetic_survivor.json")["subject"]), "REPLAY_CHANGED_SURVIVOR")


def no_leak():
    data = w.command(["journalctl", "--no-pager", "-o", "cat", "-u", "mrjam-identity-deletion", "-u", "mrjam-vision-replay"])
    for secret in [TOKEN.read_bytes().strip(), subject().encode(), w.CLOSURE.encode()]:
        require(secret not in data, "PRIVATE_DIAGNOSTICS")
    require(hashlib.sha256(TOKEN.read_bytes()).hexdigest() == w.read("adapter.json")["token_sha256"], "SOURCE_CREDENTIAL_CHANGED")


ACTIONS = {"prepare": prepare, "metadata": metadata, "negatives": negatives, "preserved": preserved,
           "unavailable": unavailable, "deleted": deleted, "client": client, "stalled-client": lambda: client(stalled=True), "ready": ready, "spy": spy, "spy-check": spy_check,
           "closure-start": closure_start, "closure-partial": closure_partial, "replayed": replayed, "no-leak": no_leak}
if __name__ == "__main__":
    try:
        require(len(sys.argv) == 2 and sys.argv[1] in ACTIONS, "FIXTURE_SCOPE")
        ACTIONS[sys.argv[1]]()
    except Exception as error:
        code = str(error) if isinstance(error, RuntimeError) and re.fullmatch(r"[A-Z_]+", str(error)) else type(error).__name__
        print("SYNTHETIC_DELETE_FAILED:" + code, file=sys.stderr)
        raise SystemExit(1)

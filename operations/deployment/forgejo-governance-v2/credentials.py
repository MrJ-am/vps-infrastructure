"""Git credential IPC: private Unix socket, token only in process/pipe memory.

The helper has no endpoint argument. Git supplies its fixed loopback origin and
repository through stdin; the broker separately restricts it to the active repo.
No token file, environment variable, command argument or diagnostic is produced.
"""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import socket
import socketserver
import stat
import struct
import sys
import threading

DIRECTORY = Path("/var/lib/mrjam-forgejo-bootstrap")
SOCKET = DIRECTORY / "git-credential.sock"
ACCOUNT = "mrjam-governance-bootstrap"
NAMES = frozenset(("Signature", "apprendre-a-demontrer", "etp-vie-affective", "matheval",
                   "mrjam-plateforme", "mrjam-validation", "style-mrjam", "vision", "vps-infrastructure"))


def require(value):
    if not value:
        raise ValueError()


def read_request(raw):
    require(type(raw) is bytes and len(raw) <= 1024)
    result = {}
    for line in raw.decode("ascii").splitlines():
        if not line:
            break
        key, separator, value = line.partition("=")
        if key == "capability[]":
            require(value in ("authtype", "state"))
            continue
        if key == "wwwauth[]":
            require(value == 'Basic realm="Gitea"')
            continue
        require(separator and key not in result and key in ("protocol", "host", "path", "username"))
        result[key] = value
    require(result.get("protocol") == "http" and result.get("host") == "127.0.0.1:3004")
    require(result.get("username", ACCOUNT) == ACCOUNT)
    name = result.get("path", "")
    require(name.startswith("MrJ-am/") and name.endswith(".git"))
    name = name[7:-4]
    require(name in NAMES)
    return name


def receive(stream):
    chunks = bytearray()
    while True:
        value = stream.recv(1025 - len(chunks))
        if not value:
            return bytes(chunks)
        chunks.extend(value)
        require(len(chunks) <= 1024)


@contextmanager
def broker(token, repository, *, socket_path=SOCKET, owner=0):
    require(repository in NAMES and type(token) is str and len(token) == 40
            and all(c in "0123456789abcdef" for c in token))
    info = socket_path.parent.lstat()
    require(stat.S_ISDIR(info.st_mode) and info.st_uid == owner and stat.S_IMODE(info.st_mode) == 0o700)
    # A stale socket from a killed invocation is inert. Remove only an actual
    # socket owned by us, never a file/link; bootstrap's exclusive lock is held.
    if socket_path.exists() or socket_path.is_symlink():
        info = socket_path.lstat()
        require(stat.S_ISSOCK(info.st_mode) and info.st_uid == owner)
        socket_path.unlink()
    class Handler(socketserver.BaseRequestHandler):
        def handle(self):
            try:
                self.request.settimeout(5)
                _pid, uid, _gid = struct.unpack("3i", self.request.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
                require(uid == owner)
                require(read_request(receive(self.request)) == repository)
                self.request.sendall(("username=" + ACCOUNT + "\npassword=" + token + "\n\n").encode("ascii"))
            except Exception:
                # Empty refusal. No request, credential or raw exception leaks.
                pass
    server = socketserver.UnixStreamServer(str(socket_path), Handler)
    os.chmod(socket_path, 0o600)
    identity = socket_path.lstat()
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
    thread.start()
    try:
        yield
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=6)
        current = socket_path.lstat()
        require((current.st_dev, current.st_ino) == (identity.st_dev, identity.st_ino))
        socket_path.unlink()


def helper(*, socket_path=SOCKET, owner=0):
    if len(sys.argv) != 2 or sys.argv[1] not in ("get", "store", "erase") or os.geteuid() != owner:
        return 64
    if sys.argv[1] != "get":
        return 0
    try:
        raw = sys.stdin.buffer.read(1025)
        read_request(raw)
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(5)
            client.connect(str(socket_path))
            client.sendall(raw)
            client.shutdown(socket.SHUT_WR)
            answer = receive(client)
        require(answer.startswith(("username=" + ACCOUNT + "\npassword=").encode())
                and answer.endswith(b"\n\n") and len(answer) <= 160)
        # stdout is the private Git credential-helper pipe, never the entrypoint
        # result or a shell invocation by an agent. Git is run with output hidden.
        sys.stdout.buffer.write(answer)
        return 0
    except Exception:
        return 1

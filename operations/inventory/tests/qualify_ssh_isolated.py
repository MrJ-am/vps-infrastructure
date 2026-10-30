"""Real SSH refusals in a disposable --network=none Cloud container only.

This is a local test driver, never an install/adoption/production interface.
It creates only ephemeral synthetic identities and keys in that container.
No successful inventory payload is sent and no real probe is executed.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import pwd
import grp
import signal
import socket
import subprocess
import tempfile
import time


def require(condition, code):
    if not condition:
        raise RuntimeError(code)


def call(command, **kwargs):
    return subprocess.run(command, stdin=kwargs.pop("stdin", None), capture_output=True, timeout=kwargs.pop("timeout", 8), check=False, **kwargs)


def qualify(receipt):
    require(os.environ.get("MRJAM_SYNTHETIC_CONTAINER") == "1" and os.getuid() == 0 and Path("/.dockerenv").exists(), "DISPOSABLE_CONTAINER_REQUIRED")
    require({entry.name for entry in Path("/sys/class/net").iterdir()} == {"lo"}, "NETWORK_NONE_REQUIRED")
    # The public nixos/nix image links these three files into /nix/store, whose
    # volume is shared by local builds. Detach the /etc links atomically BEFORE
    # editing the disposable account fixture. Never append through those links.
    public_image_files = {
        "passwd":"fa1c644ecaac4c60e6be4d7a39560856bfdedc86d49c1375314285f66508917f",
        "group":"d52a3e02e11273bf5a8ae7eefc4cd139fbd7eecd6ef3bec223142b8ce9ff01bb",
        "shadow":"2cbd3cba9b6ba3022720d33b321c59d277d40b8f767f76a0a1c300041cfaca6c",
    }
    for name, digest in public_image_files.items():
        path = Path("/etc") / name
        data = path.read_bytes()  # Public image bytes only, checked before use.
        require(hashlib.sha256(data).hexdigest() == digest, "PUBLIC_IMAGE_ACCOUNT_FILE_MISMATCH")
        overlay = path.with_name(name + ".mrjam-synthetic")
        with overlay.open("xb") as handle:
            handle.write(data)
        overlay.chmod(0o600 if name == "shadow" else 0o644)
        os.replace(overlay, path)
        require(not path.is_symlink(), "ACCOUNT_FIXTURE_NOT_DETACHED")
    products = json.loads(receipt.read_text())
    def output(suffix):
        values = [Path(item["outputs"]["out"]) for item in products if item["drvPath"].endswith(suffix)]
        require(len(values) == 1 and values[0].is_relative_to("/nix/store"), "PINNED_ARTIFACT_MISSING")
        return values[0]
    package = output("-mrjam-inventory-v1.drv")
    config_source = output("-sshd.conf-final.drv")
    openssh = output("-openssh-10.6p1.drv")
    runtime = json.loads((package / "libexec/runtime.json").read_text())
    require(runtime["uid"] == runtime["gid"] == 990 and all("synthetic" in key for key in runtime["publicKeys"]), "SYNTHETIC_PACKAGE_REQUIRED")
    ssh, sshd, keygen = (str(openssh / "bin" / name) for name in ("ssh", "sshd", "ssh-keygen"))
    account = "mrjam-inventory"
    require(all(entry.pw_name != account and entry.pw_uid != 990 for entry in pwd.getpwall()), "SYNTHETIC_ACCOUNT_COLLISION")
    require(all(entry.gr_name != account and entry.gr_gid != 990 for entry in grp.getgrall()), "SYNTHETIC_GROUP_COLLISION")
    home = Path("/var/lib/mrjam-inventory-access/home")
    for path, mode in ((home.parent, 0o755), (home, 0o755), (home / ".ssh", 0o755), (Path("/etc/ssh"), 0o755), (Path("/run/sshd"), 0o755), (Path("/var/empty"), 0o755)):
        require(not path.is_symlink(), "SYNTHETIC_PATH_MUST_NOT_BE_SYMLINK")
        path.mkdir(parents=True, exist_ok=True)
        path.chmod(mode)
    # NP is an intentionally invalid password marker in this PAM-disabled fixture.
    # Password authentication remains disabled. No pre-existing shadow is read.
    with Path("/etc/passwd").open("a") as handle:
        handle.write(f"{account}:x:990:990:Synthetic SSH fixture:{home}:{package}/bin/mrjam-inventory-login\n")
    with Path("/etc/group").open("a") as handle:
        handle.write(f"{account}:x:990:\n")
    with Path("/etc/shadow").open("a") as handle:
        handle.write(f"{account}:NP:1:0:99999:7:::\n")
    require(all(entry.pw_name != "sshd" and entry.pw_uid != 991 for entry in pwd.getpwall()), "PRIVSEP_FIXTURE_COLLISION")
    require(all(entry.gr_name != "sshd" and entry.gr_gid != 991 for entry in grp.getgrall()), "PRIVSEP_GROUP_FIXTURE_COLLISION")
    with Path("/etc/passwd").open("a") as handle:
        handle.write("sshd:x:991:991:Synthetic SSH privilege separation:/var/empty:/bin/false\n")
    with Path("/etc/group").open("a") as handle:
        handle.write("sshd:x:991:\n")
    lockdir = Path("/run/mrjam-inventory-lock")
    lockdir.mkdir(mode=0o750)
    os.chown(lockdir, 0, 990)
    lock = lockdir / "operation.lock"
    lock.touch()
    lock.chmod(0o440)
    os.chown(lock, 0, 990)
    results = []
    with tempfile.TemporaryDirectory(prefix="mrjam-ssh-synthetic-") as temporary:
        root = Path(temporary)
        for name in ("host", "client", "alternative"):
            generated = call([keygen, "-q", "-t", "ed25519", "-N", "", "-C", "ephemeral-synthetic-only", "-f", str(root / name)])
            require(generated.returncode == 0, "SYNTHETIC_KEY_GENERATION_FAILED")
        public = (root / "client.pub").read_text().strip()
        authorized = Path("/etc/ssh/mrjam-inventory-authorized-keys")
        authorized.write_text('restrict,command="mrjam-inventory-v1" ' + public + "\n")
        authorized.chmod(0o444)
        # An alternative home key must remain ineffective with the unique /etc source.
        (home / ".ssh/authorized_keys").write_text((root / "alternative.pub").read_text())
        (home / ".ssh/authorized_keys").chmod(0o644)
        (home / ".ssh/rc").write_text("echo SYNTHETIC_USER_RC_RAN\n")
        (home / ".ssh/rc").chmod(0o644)
        adaptations = {"port", "listenaddress", "hostkey", "usepam", "pidfile", "loglevel"}
        original = config_source.read_text()
        lines = [line for line in original.splitlines() if not line.split() or line.split()[0].lower() not in adaptations]
        fixture = "\n".join(["Port 2222", "ListenAddress 127.0.0.1", f"HostKey {root}/host", "UsePAM no", f"PidFile {root}/sshd.pid", "LogLevel ERROR", *lines, ""])
        config = root / "sshd_config"
        config.write_text(fixture)
        checked = call([sshd, "-t", "-f", str(config)])
        require(checked.returncode == 0, "GENERATED_SSHD_CONFIG_INVALID: " + checked.stderr[:2048].decode("utf-8", "replace"))
        results.append("sshd-t-generated-config-with-explicit-container-adaptations")
        effective = call([sshd, "-T", "-f", str(config), "-C", "user=mrjam-inventory,host=synthetic,addr=127.0.0.1,laddr=127.0.0.1,lport=2222"])
        require(effective.returncode == 0, "EFFECTIVE_SSHD_CONFIG_FAILED")
        observed = {key.lower():value for key,value in (line.split(None, 1) for line in effective.stdout.decode().splitlines())}
        validated = call([str(package / "bin/mrjam-inventory-effective_ssh")], input=effective.stdout)
        if validated.returncode != 0:
            spec = importlib.util.spec_from_file_location("fixture_policy", package / "libexec/effective_ssh.py")
            policy = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(policy)
            mismatches = {key:observed.get(key) for key,value in policy.REQUIRED.items() if observed.get(key) != value}
            raise RuntimeError("EFFECTIVE_SSHD_POLICY_REFUSED: " + json.dumps({"mismatches":mismatches,"bytes":len(effective.stdout),"fields":sorted(observed)}, sort_keys=True))
        results.append("sshd-T-accepted-by-packaged-policy-filter")
        server = subprocess.Popen([sshd, "-D", "-e", "-f", str(config)], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, start_new_session=True)
        common = [ssh, "-F", "/dev/null", "-p", "2222", "-o", "BatchMode=yes", "-o", "IdentitiesOnly=yes", "-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=/dev/null", "-o", "GlobalKnownHostsFile=/dev/null", "-o", "LogLevel=INFO", "-o", "ConnectTimeout=2"]
        destination = "mrjam-inventory@127.0.0.1"
        def client(arguments, payload=b"invalid-synthetic-payload", identity="client"):
            return call([*common, "-i", str(root / identity), *arguments], input=payload)
        try:
            deadline = time.monotonic() + 3
            while True:
                require(server.poll() is None, "SYNTHETIC_SSHD_STOPPED")
                try:
                    with socket.create_connection(("127.0.0.1", 2222), timeout=.1):
                        break
                except OSError:
                    require(time.monotonic() < deadline, "SYNTHETIC_SSHD_START_TIMEOUT")
                    time.sleep(.02)
            invalid = client(["-T", destination, "mrjam-inventory-v1"])
            require(invalid.returncode == 65 and invalid.stdout == b"", "AUTHENTICATED_INVALID_PAYLOAD_NOT_REFUSED")
            results.append("authenticated-fixed-operation-invalid-payload-exit65-no-output")
            for name, arguments in (("free-command", ["-T", destination, "echo SYNTHETIC_FREE_COMMAND"]), ("shell", ["-T", destination]), ("subsystem", ["-T", "-s", destination, "sftp"])):
                denied = client(arguments)
                require(denied.returncode == 64 and denied.stdout == b"", "REFUSAL_FAILED_" + name.upper())
                results.append(name + "-refused-exit64-no-output")
            pty = client(["-tt", destination, "mrjam-inventory-v1"])
            require(pty.returncode != 0 and pty.stdout == b"" and b"PTY allocation request failed" in pty.stderr, "PTY_REQUEST_NOT_REFUSED")
            results.append("pty-request-refused")
            denied = client(["-T", "-W", "127.0.0.1:2222", destination])
            require(denied.returncode == 255 and denied.stdout == b"" and b"administratively prohibited" in denied.stderr, "DIRECT_TCP_FORWARD_NOT_REFUSED: " + json.dumps({"exit":denied.returncode,"stdout_bytes":len(denied.stdout),"synthetic_stderr":denied.stderr[:2048].decode("utf-8","replace")}))
            results.append("direct-tcp-forward-refused")
            denied = client(["-N", "-o", "ExitOnForwardFailure=yes", "-R", "127.0.0.1:2223:127.0.0.1:2222", destination])
            require(denied.returncode == 255 and denied.stdout == b"" and b"remote port forwarding failed" in denied.stderr, "REMOTE_TCP_FORWARD_NOT_REFUSED")
            results.append("remote-tcp-forward-refused")
            denied = client(["-N", "-o", "ExitOnForwardFailure=yes", "-R", f"{root}/unused-remote.sock:{root}/unused-local.sock", destination])
            require(denied.returncode == 255 and denied.stdout == b"" and b"remote port forwarding failed" in denied.stderr, "REMOTE_UNIX_FORWARD_NOT_REFUSED")
            results.append("remote-unix-forward-refused")
            denied = client(["-T", destination, "mrjam-inventory-v1"], identity="alternative")
            require(denied.returncode == 255 and denied.stdout == b"" and b"Permission denied" in denied.stderr, "ALTERNATIVE_HOME_KEY_NOT_REFUSED")
            results.append("alternative-home-key-authentication-refused")
            holder = subprocess.Popen([*common, "-i", str(root / "client"), "-T", destination, "mrjam-inventory-v1"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            try:
                holder.stdin.write(b"synthetic-partial-input")
                holder.stdin.flush()
                time.sleep(.15)
                busy = client(["-T", destination, "mrjam-inventory-v1"])
                require(busy.returncode == 75 and busy.stdout == b"", "CONCURRENT_OPERATION_NOT_REFUSED")
                holder.stdin.close()
                holder.wait(timeout=3)
                require(holder.returncode == 65 and holder.stdout.read() == b"", "HOLDER_INVALID_INPUT_NOT_REFUSED")
                results.append("concurrent-operation-refused-exit75")
            finally:
                if holder.poll() is None:
                    holder.kill()
                    holder.wait(timeout=2)
                for stream in (holder.stdin, holder.stdout, holder.stderr):
                    stream.close()
        finally:
            os.killpg(server.pid, signal.SIGTERM)
            try:
                server.wait(timeout=3)
            except subprocess.TimeoutExpired:
                os.killpg(server.pid, signal.SIGKILL)
                server.wait(timeout=2)
            server.stderr.close()
    base_verified = call(["/nix/var/nix/profiles/default/bin/nix-store", "--verify-path", "/nix/store/kis5v17r29vz5k2bwh5hsrhz4rhj3bvl-base-system"], timeout=30)
    require(base_verified.returncode == 0, "PUBLIC_IMAGE_STORE_CHANGED_BY_FIXTURE")
    return {"schema_version":1, "authority":"local_synthetic_qualification", "status":"passed", "package":str(package), "sshd_config":str(config_source), "openssh":str(openssh), "source_config_sha256":hashlib.sha256(original.encode()).hexdigest(), "checks":results, "optional_field_observations":{"gssapiauthentication":observed.get("gssapiauthentication", "not_reported")}, "public_image_store_verify_exit":base_verified.returncode, "fixture_adaptations":["loopback-only port2222", "ephemeral synthetic host/client keys", "synthetic account uid990 gid990 and sshd privilege-separation uid991", "public-image passwd/group/shadow detached into disposable overlay before editing", "UsePAM=no; production PAM unqualified", "authorized key file synthetic replacement; no Spectre key", "temporary pid and logging settings"], "not_executed":["valid inventory payload", "production SSH", "NixOS activation", "PAM authentication", "agent/X11 forwarding handshake", "production adoption/rollback"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifacts", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(qualify(args.artifacts), sort_keys=True))


if __name__ == "__main__":
    main()

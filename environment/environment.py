#!/usr/bin/env python3
"""Private Codex development tools and disposable synthetic services.

This is a development helper, not a production capability boundary. It never
connects to the VPS and never configures repository or production permissions.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shlex
import shutil
import socket
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.request

BASE = Path(__file__).resolve().parent
LOCAL = BASE / ".local"
try:
    LOCK = json.loads((BASE / "toolchains.lock.json").read_text())
except (OSError, ValueError):
    print('{"status":"error","code":"LOCKFILE_UNAVAILABLE"}')
    raise SystemExit(1) from None
LABEL_KEY = "org.mrjam.environment"
LABEL_VALUE = "codex-synthetic-v1"
NETWORK = "mrjam-codex-synthetic-local"
CONTAINERS = {
    "postgres": "mrjam-codex-synthetic-postgres",
    "nginx": "mrjam-codex-synthetic-nginx",
}
DATABASE_URL = (
    "postgresql://mrjam_synthetic:mrjam_synthetic_only@127.0.0.1:55432/"
    "mrjam_synthetic"
)
DOCKER_SELECTORS = (
    "DOCKER_HOST", "DOCKER_CONTEXT", "DOCKER_TLS", "DOCKER_TLS_VERIFY",
    "DOCKER_CERT_PATH",
)
MAX_DOWNLOAD = 1024 * 1024 * 1024


class SetupError(Exception):
    """An error code from this file, never a captured process diagnostic."""


class FixedErrorArgumentParser(argparse.ArgumentParser):
    """Do not echo arbitrary arguments in diagnostics."""

    def error(self, message: str) -> None:
        report("error", code="INVALID_ARGUMENTS")
        raise SystemExit(2)


def report(status: str, **fields: object) -> None:
    print(json.dumps({"status": status, **fields}, sort_keys=True), flush=True)


def command(argv: list[str], *, env: dict[str, str] | None = None,
            timeout: int = 60, cwd: Path = BASE) -> tuple[int, str]:
    try:
        result = subprocess.run(
            argv, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, errors="replace", timeout=timeout, check=False,
        )
        return result.returncode, result.stdout
    except (OSError, subprocess.TimeoutExpired):
        return 125, ""


def require_command(argv: list[str], code: str, **kwargs: object) -> str:
    status, output = command(argv, **kwargs)
    if status:
        raise SetupError(code)
    return output


def docker(argv: list[str], *, timeout: int = 60) -> tuple[int, str]:
    env = os.environ.copy()
    for name in DOCKER_SELECTORS:
        env.pop(name, None)
    # Preserve DOCKER_CONFIG, proxy variables, injected headers and CA trust.
    return command(
        ["docker", "--host=unix:///var/run/docker.sock", *argv],
        env=env, timeout=timeout,
    )


def require_docker(argv: list[str], code: str, *, timeout: int = 60) -> str:
    status, output = docker(argv, timeout=timeout)
    if status:
        raise SetupError(code)
    return output


def check_platform() -> None:
    if platform.system() != "Linux" or platform.machine() not in ("x86_64", "amd64"):
        raise SetupError("PLATFORM_UNSUPPORTED")
    if sys.version_info < (3, 11):
        raise SetupError("PYTHON_3_11_REQUIRED")


def version_ok(argv: list[str], expected: str, *, prefix: str = "",
               env: dict[str, str] | None = None) -> bool:
    status, output = command(argv, env=env, timeout=15)
    pattern = re.escape(prefix + expected) + r"(?: \([0-9A-Za-z .-]+\))?"
    return status == 0 and re.fullmatch(pattern, output.strip()) is not None


def check_node() -> None:
    if not version_ok(["node", "--version"], LOCK["node"], prefix="v"):
        raise SetupError("NODE_PIN_MISMATCH")
    if not version_ok(["npm", "--version"], LOCK["npm"]):
        raise SetupError("NPM_PIN_MISMATCH")


def rust_candidates() -> list[tuple[Path, dict[str, str]]]:
    candidates: list[tuple[Path, dict[str, str]]] = []
    found = shutil.which("rustc")
    if found:
        candidates.append((Path(found).parent, os.environ.copy()))
    candidates.append((LOCAL / "rust" / "bin", os.environ.copy()))
    # Existing workshop cache: optional, never required in a new environment.
    shared = Path("/workspace/.tools")
    if (shared / "cargo/bin/rustc").is_file():
        env = os.environ.copy()
        env["CARGO_HOME"] = str(shared / "cargo")
        env["RUSTUP_HOME"] = str(shared / "rustup")
        candidates.append((shared / "cargo/bin", env))
    return candidates


def find_rust() -> tuple[Path, dict[str, str]] | None:
    for directory, env in rust_candidates():
        rustc = directory / "rustc"
        cargo = directory / "cargo"
        if not rustc.is_file() or not cargo.is_file():
            continue
        env = {**env, "PATH": str(directory) + os.pathsep + env.get("PATH", "")}
        if (version_ok([str(rustc), "--version"], LOCK["rust"]["version"],
                       prefix="rustc ", env=env)
                and version_ok([str(cargo), "--version"], LOCK["rust"]["version"],
                               prefix="cargo ", env=env)):
            return directory, env
    return None


def download_verified(url: str, destination: Path, expected: str) -> None:
    if not re.fullmatch(r"[0-9a-f]{64}", expected):
        raise SetupError("INVALID_DOWNLOAD_PIN")
    if not url.startswith("https://static.rust-lang.org/dist/"):
        raise SetupError("DOWNLOAD_SOURCE_NOT_ALLOWED")
    digest = hashlib.sha256()
    total = 0
    try:
        with urllib.request.urlopen(url, timeout=30) as response, destination.open("wb") as out:
            while block := response.read(1024 * 1024):
                total += len(block)
                if total > MAX_DOWNLOAD:
                    raise SetupError("DOWNLOAD_LIMIT_EXCEEDED")
                digest.update(block)
                out.write(block)
    except (OSError, ValueError):
        destination.unlink(missing_ok=True)
        raise SetupError("RUST_DOWNLOAD_FAILED") from None
    if digest.hexdigest() != expected:
        destination.unlink(missing_ok=True)
        raise SetupError("RUST_DIGEST_MISMATCH")


def install_rust() -> None:
    if find_rust():
        report("ok", step="rust", action="reused")
        return
    if not hasattr(tarfile, "data_filter"):
        raise SetupError("PYTHON_TAR_FILTER_REQUIRED")
    if shutil.disk_usage(LOCAL).free < 3 * 1024 ** 3:
        raise SetupError("RUST_DISK_BUDGET_UNAVAILABLE")
    report("running", step="rust_install")
    with tempfile.TemporaryDirectory(prefix="rust-install-", dir=LOCAL) as temp:
        staging = Path(temp)
        archive = staging / "rust.tar.xz"
        download_verified(LOCK["rust"]["url"], archive, LOCK["rust"]["sha256"])
        try:
            with tarfile.open(archive) as packed:
                packed.extractall(staging, filter="data")
        except (tarfile.TarError, OSError):
            raise SetupError("RUST_ARCHIVE_INVALID") from None
        source = staging / (
            f"rust-{LOCK['rust']['version']}-{LOCK['rust']['target']}"
        )
        require_command([
            "bash", str(source / "install.sh"),
            "--prefix=" + str(LOCAL / "rust"), "--disable-ldconfig",
            "--components=rustc,rust-std-x86_64-unknown-linux-gnu,cargo,"
            "rustfmt-preview,clippy-preview",
        ], "RUST_INSTALL_FAILED", timeout=600, cwd=source)
    if not find_rust():
        raise SetupError("RUST_INSTALL_VERIFICATION_FAILED")
    report("ok", step="rust", action="installed")


def npm_versions_ok() -> bool:
    for package, expected in LOCK["npm_packages"].items():
        try:
            actual = json.loads((BASE / "node_modules" / package / "package.json").read_text())
        except (OSError, ValueError):
            return False
        if actual.get("version") != expected:
            return False
    return True


def npm_fingerprint() -> str:
    digest = hashlib.sha256()
    for name in ("package.json", "package-lock.json"):
        digest.update((BASE / name).read_bytes())
    return digest.hexdigest()


def npm_lock_current() -> bool:
    try:
        return (LOCAL / "npm.fingerprint").read_text().strip() == npm_fingerprint()
    except OSError:
        return False


def browser_environment() -> dict[str, str]:
    return {**os.environ, "PLAYWRIGHT_BROWSERS_PATH": str(LOCAL / "browsers")}


def bundle_digest(directory: Path, ignored: set[str]) -> tuple[str, int]:
    digest = hashlib.sha256()
    count = 0
    for path in sorted(directory.rglob("*")):
        if path.is_dir() or path.name in ignored:
            continue
        relative = path.relative_to(directory).as_posix().encode()
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        if path.is_symlink():
            kind = b"L"
            content_digest = hashlib.sha256(path.readlink().as_posix().encode()).digest()
        else:
            kind = b"F"
            content_hash = hashlib.sha256()
            with path.open("rb") as source:
                while block := source.read(1024 * 1024):
                    content_hash.update(block)
            content_digest = content_hash.digest()
        digest.update(kind)
        digest.update(content_digest)
        count += 1
    return digest.hexdigest(), count


def browser_bundles_ok() -> bool:
    try:
        pins = json.loads((BASE / "browser-bundles.lock.json").read_text())
        ignored = set(pins["ignored_marker_names"])
        for name, expected in pins["bundles"].items():
            if not re.fullmatch(r"[a-z_]+-[0-9]+", name):
                return False
            actual, count = bundle_digest(LOCAL / "browsers" / name, ignored)
            if actual != expected["sha256"] or count != expected["files"]:
                return False
        return bool(pins["bundles"])
    except (OSError, ValueError, KeyError):
        return False


def install_npm() -> None:
    stamp = LOCAL / "npm.fingerprint"
    expected = npm_fingerprint()
    if not (stamp.is_file() and stamp.read_text().strip() == expected and npm_versions_ok()):
        report("running", step="npm_install")
        require_command(
            ["npm", "ci", "--ignore-scripts", "--no-audit", "--no-fund"],
            "NPM_INSTALL_FAILED", timeout=600,
        )
        if not npm_versions_ok():
            raise SetupError("NPM_PIN_MISMATCH")
        stamp.write_text(expected + "\n")
    report("ok", step="npm", action="verified")


def browser_ready() -> bool:
    if not browser_bundles_ok():
        return False
    status, output = command(
        ["node", str(BASE / "browser-check.mjs")],
        env=browser_environment(), timeout=60,
    )
    return status == 0 and output.strip() == '{"status":"ok","check":"synthetic_browser"}'


def install_browser() -> None:
    if browser_ready():
        report("ok", step="browser", action="reused")
        return
    report("running", step="chromium_install")
    require_command([
        "node", str(BASE / "node_modules/playwright/cli.js"), "install", "chromium",
    ], "BROWSER_DOWNLOAD_FAILED", env=browser_environment(), timeout=600)
    if not browser_bundles_ok():
        raise SetupError("BROWSER_BUNDLE_DIGEST_MISMATCH")
    if not browser_ready():
        # Never run apt/sudo or change OS packages implicitly.
        raise SetupError("BROWSER_OS_DEPENDENCIES_OR_LAUNCH_FAILED")
    report("ok", step="browser", action="installed")


def images_ready() -> bool:
    return all(docker(["image", "inspect", LOCK[name]["image"]])[0] == 0
               for name in CONTAINERS)


def install_images() -> None:
    require_docker(["info", "--format", "{{.ServerVersion}}"], "LOCAL_DOCKER_UNAVAILABLE")
    for name in CONTAINERS:
        image = LOCK[name]["image"]
        repository = {"postgres": "docker.io/pgvector/pgvector", "nginx": "docker.io/library/nginx"}[name]
        if not re.fullmatch(re.escape(repository) + r"@sha256:[0-9a-f]{64}", image):
            raise SetupError("IMAGE_PIN_INVALID")
        if docker(["image", "inspect", image])[0]:
            report("running", step=name + "_image_pull")
            require_docker(["pull", image], "IMAGE_PULL_FAILED", timeout=600)
        report("ok", step=name + "_image", action="verified")


def write_activation() -> None:
    rust = find_rust()
    if rust is None:
        raise SetupError("RUST_PIN_MISMATCH")
    directory, env = rust
    lines = ["# Generated local tool paths; no production secret or target."]
    for name in ("CARGO_HOME", "RUSTUP_HOME"):
        if name in env:
            lines.append(f"export {name}={shlex.quote(env[name])}")
    prefix = str(directory) + os.pathsep + str(BASE / "node_modules/.bin")
    lines += [
        "export PATH=" + shlex.quote(prefix) + ':"$PATH"',
        "export PLAYWRIGHT_BROWSERS_PATH=" + shlex.quote(str(LOCAL / "browsers")),
        "export MRJAM_SYNTHETIC_DATABASE_URL=" + shlex.quote(DATABASE_URL),
    ]
    (LOCAL / "activate.sh").write_text("\n".join(lines) + "\n")


def check_tools(*, with_services: bool) -> bool:
    check_platform()
    check_node()
    statuses: dict[str, bool] = {"node": True, "npm": True, "rust": find_rust() is not None}
    rust = find_rust()
    if rust:
        directory, env = rust
        statuses["rustfmt"] = command([str(directory / "cargo"), "fmt", "--version"], env=env)[0] == 0
        statuses["clippy"] = command([str(directory / "cargo"), "clippy", "--version"], env=env)[0] == 0
    else:
        statuses.update(rustfmt=False, clippy=False)
    statuses["npm_packages"] = npm_versions_ok()
    statuses["npm_lock"] = npm_lock_current()
    statuses["elm"] = version_ok([str(BASE / "node_modules/.bin/elm"), "--version"], "0.19.1")
    statuses["elm_review"] = version_ok([str(BASE / "node_modules/.bin/elm-review"), "--version"], LOCK["npm_packages"]["elm-review"])
    statuses["elm_test"] = version_ok([str(BASE / "node_modules/.bin/elm-test"), "--version"], LOCK["npm_packages"]["elm-test"])
    statuses["playwright"] = version_ok([str(BASE / "node_modules/.bin/playwright"), "--version"], LOCK["npm_packages"]["@playwright/test"], prefix="Version ")
    statuses["browser"] = browser_ready() if statuses["npm_packages"] else False
    statuses["local_docker"] = docker(["info", "--format", "{{.ServerVersion}}"])[0] == 0
    statuses["images"] = images_ready() if statuses["local_docker"] else False
    if with_services:
        statuses.update(service_status())
    report("ok" if all(statuses.values()) else "incomplete", checks=statuses)
    return all(statuses.values())


def config_fingerprint() -> str:
    digest = hashlib.sha256((BASE / "toolchains.lock.json").read_bytes())
    digest.update((BASE / "nginx.synthetic.conf").read_bytes())
    return digest.hexdigest()


def owned(kind: str, name: str) -> bool:
    status, output = docker([
        kind, "inspect", "--format", '{{ index .Labels "' + LABEL_KEY + '" }}'
        if kind == "network" else '{{ index .Config.Labels "' + LABEL_KEY + '" }}', name,
    ])
    return status == 0 and output.strip() == LABEL_VALUE


def container_compatible(name: str) -> bool:
    if not owned("container", name):
        return False
    status, output = docker([
        "container", "inspect", "--format",
        '{{ index .Config.Labels "org.mrjam.config" }}', name,
    ])
    return status == 0 and output.strip() == config_fingerprint()


def run_arguments(service: str) -> list[str]:
    common = [
        "run", "--detach", "--pull=never", "--name", CONTAINERS[service],
        "--label", LABEL_KEY + "=" + LABEL_VALUE,
        "--label", "org.mrjam.config=" + config_fingerprint(),
        "--network", NETWORK, "--read-only", "--cap-drop=ALL",
        "--security-opt=no-new-privileges=true", "--pids-limit=128", "--cpus=1",
        "--log-driver=none", "--tmpfs", "/tmp:rw,nosuid,nodev,noexec,size=64m",
    ]
    if service == "postgres":
        return common + [
            "--user=999:999", "--memory=768m", "--shm-size=64m",
            "--publish", "127.0.0.1:55432:5432",
            # PostgreSQL 17 declares a VOLUME at this exact path. Mount it
            # explicitly so Docker does not allocate an anonymous disk volume.
            "--tmpfs", "/var/lib/postgresql/data:rw,nosuid,nodev,noexec,size=512m,uid=999,gid=999",
            "--tmpfs", "/var/run/postgresql:rw,nosuid,nodev,noexec,size=16m,uid=999,gid=999",
            "--env", "POSTGRES_USER=mrjam_synthetic",
            "--env", "POSTGRES_DB=mrjam_synthetic",
            "--env", "POSTGRES_PASSWORD=mrjam_synthetic_only",
            "--env", "PGDATA=/var/lib/postgresql/data",
            LOCK[service]["image"], "postgres", "-c", "max_connections=32",
            "-c", "shared_buffers=64MB", "-c", "log_statement=none",
            "-c", "log_min_messages=panic",
        ]
    if service == "nginx":
        return common + [
            "--user=101:101", "--memory=128m", "--publish", "127.0.0.1:18080:8080",
            "--mount", "type=bind,src=" + str(BASE / "nginx.synthetic.conf")
            + ",dst=/etc/nginx/nginx.conf,readonly",
            "--entrypoint=nginx", LOCK[service]["image"], "-g", "daemon off;",
        ]
    raise SetupError("UNKNOWN_SYNTHETIC_SERVICE")


def service_status() -> dict[str, bool]:
    postgres = CONTAINERS["postgres"]
    pg_ok = False
    pg_version_ok = False
    vector_ok = False
    if container_compatible(postgres):
        status, output = docker([
            "exec", postgres, "psql", "--no-psqlrc", "--username=mrjam_synthetic",
            "--dbname=mrjam_synthetic", "--tuples-only", "--no-align",
            "--command=SELECT current_database() = 'mrjam_synthetic';",
        ])
        pg_ok = status == 0 and output.strip() == "t"
        if pg_ok:
            try:
                with socket.create_connection(("127.0.0.1", 55432), timeout=3):
                    pass
            except OSError:
                pg_ok = False
        status, output = docker([
            "exec", postgres, "psql", "--no-psqlrc", "--username=mrjam_synthetic",
            "--dbname=mrjam_synthetic", "--tuples-only", "--no-align",
            "--command=SELECT current_setting('server_version_num'), "
            "COALESCE((SELECT extversion FROM pg_extension WHERE extname='vector'), 'missing');",
        ])
        if status == 0:
            values = output.strip().split("|")
            pg_version_ok = len(values) == 2 and values[0] == str(LOCK["postgres"]["server_version_num"])
            vector_ok = len(values) == 2 and values[1] == LOCK["postgres"]["pgvector"]
    http_ok = False
    if container_compatible(CONTAINERS["nginx"]):
        try:
            # Explicit loopback bypass for the local test, never an external host.
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            with opener.open("http://127.0.0.1:18080/__synthetic__/ready", timeout=3) as response:
                http_ok = response.status == 200 and response.read(128) == b"MRJAM_SYNTHETIC_OK\n"
        except OSError:
            pass
    return {"postgres_synthetic": pg_ok, "postgres_version": pg_version_ok,
            "postgres_pgvector": vector_ok, "nginx_synthetic": http_ok}


def initialize_postgres_fixture() -> bool:
    """Initialize only the named disposable database through the owned local container."""
    postgres = CONTAINERS["postgres"]
    if not container_compatible(postgres):
        raise SetupError("SYNTHETIC_CONTAINER_COLLISION")
    if docker(["exec", postgres, "pg_isready", "--username=mrjam_synthetic",
               "--dbname=mrjam_synthetic"])[0]:
        return False
    # No arbitrary URL, SQL file or database name is accepted by this helper.
    require_docker([
        "exec", postgres, "psql", "--no-psqlrc", "--username=mrjam_synthetic",
        "--dbname=mrjam_synthetic", "--set=ON_ERROR_STOP=1",
        "--command=DO $synthetic$ BEGIN "
        "IF current_database() <> 'mrjam_synthetic' OR current_user <> 'mrjam_synthetic' "
        "THEN RAISE EXCEPTION 'SYNTHETIC_DATABASE_REQUIRED'; END IF; END $synthetic$; "
        "CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public;",
    ], "SYNTHETIC_VECTOR_INITIALIZATION_FAILED")
    return True


def services_up() -> None:
    require_docker(["info", "--format", "{{.ServerVersion}}"], "LOCAL_DOCKER_UNAVAILABLE")
    if not images_ready():
        raise SetupError("PINNED_IMAGES_NOT_INSTALLED")
    if docker(["network", "inspect", NETWORK])[0] == 0:
        if not owned("network", NETWORK):
            raise SetupError("SYNTHETIC_NETWORK_COLLISION")
        internal = require_docker(["network", "inspect", "--format", "{{.Internal}}", NETWORK], "NETWORK_CHECK_FAILED")
        if internal.strip() != "false":
            raise SetupError("SYNTHETIC_NETWORK_CANNOT_PUBLISH_LOOPBACK")
    else:
        require_docker([
            "network", "create", "--label", LABEL_KEY + "=" + LABEL_VALUE,
            NETWORK,
        ], "NETWORK_CREATE_FAILED")
    for service, name in CONTAINERS.items():
        if docker(["container", "inspect", name])[0] == 0:
            if not container_compatible(name):
                raise SetupError("SYNTHETIC_CONTAINER_COLLISION")
            networks = require_docker([
                "container", "inspect", "--format", "{{json .NetworkSettings.Networks}}", name,
            ], "SYNTHETIC_NETWORK_CHECK_FAILED")
            if NETWORK not in json.loads(networks):
                require_docker(["network", "connect", NETWORK, name], "SYNTHETIC_NETWORK_CONNECT_FAILED")
            require_docker(["start", name], "SYNTHETIC_START_FAILED")
        else:
            require_docker(run_arguments(service), "SYNTHETIC_CREATE_FAILED")
    for _ in range(30):
        if initialize_postgres_fixture() and all(service_status().values()):
            report("ok", action="synthetic_services_ready", ports={"postgres": 55432, "nginx": 18080})
            return
        time.sleep(1)
    raise SetupError("SYNTHETIC_READINESS_FAILED")


def services_down() -> None:
    # Explicitly disposable data only. No named volume, database export or backup.
    for name in CONTAINERS.values():
        if docker(["container", "inspect", name])[0] != 0:
            continue
        if not owned("container", name):
            raise SetupError("SYNTHETIC_CONTAINER_COLLISION")
        require_docker(["rm", "--force", name], "SYNTHETIC_REMOVE_FAILED")
    if docker(["network", "inspect", NETWORK])[0] == 0:
        if not owned("network", NETWORK):
            raise SetupError("SYNTHETIC_NETWORK_COLLISION")
        require_docker(["network", "rm", NETWORK], "SYNTHETIC_NETWORK_REMOVE_FAILED")
    report("ok", action="synthetic_services_removed")


def main() -> int:
    parser = FixedErrorArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="operation", required=True)
    setup = sub.add_parser("setup")
    mode = setup.add_mutually_exclusive_group(required=True)
    mode.add_argument("--install", action="store_true")
    mode.add_argument("--check", action="store_true")
    check = sub.add_parser("check")
    check.add_argument("--services", action="store_true")
    services = sub.add_parser("services")
    services.add_argument("action", choices=("up", "status", "down"))
    args = parser.parse_args()
    try:
        if args.operation == "check" or (args.operation == "setup" and args.check):
            return 0 if check_tools(with_services=getattr(args, "services", False)) else 1
        check_platform()
        LOCAL.mkdir(mode=0o700, exist_ok=True)
        with (LOCAL / "setup.lock").open("w") as guard:
            fcntl.flock(guard, fcntl.LOCK_EX | fcntl.LOCK_NB)
            if args.operation == "setup":
                check_node()
                install_rust()
                install_npm()
                install_browser()
                install_images()
                write_activation()
                return 0 if check_tools(with_services=False) else 1
            if args.action == "up":
                services_up()
            elif args.action == "down":
                services_down()
            else:
                statuses = service_status()
                report("ok" if all(statuses.values()) else "incomplete", checks=statuses)
                return 0 if all(statuses.values()) else 1
        return 0
    except SetupError as error:
        report("error", code=str(error))
        return 1
    except BlockingIOError:
        report("error", code="ENVIRONMENT_OPERATION_IN_PROGRESS")
        return 1
    except (OSError, ValueError, KeyError):
        report("error", code="ENVIRONMENT_CONFIGURATION_ERROR")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

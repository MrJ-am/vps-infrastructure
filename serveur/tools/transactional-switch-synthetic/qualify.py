#!/usr/bin/env python3
"""Measure local Nginx cutover/rollback only; never connect to a VPS.

Three disposable Nginx containers serve invented slot markers. An injected
candidate failure must restore the still-running previous backend within five
seconds. This does not qualify Rust, SQL compatibility or production sessions.
"""
import http.client
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
import uuid

IMAGE = "docker.io/library/nginx@sha256:47928bf67eb62a1863cb08d9ecb52d3e704304ba614eaee17884204677702951"
LABEL = "org.mrjam.scope=transactional-switch-synthetic"
BUDGET = 5.0


def docker(*arguments, timeout=15):
    environment = dict(os.environ)
    for key in ("DOCKER_HOST", "DOCKER_CONTEXT", "DOCKER_TLS", "DOCKER_TLS_VERIFY", "DOCKER_CERT_PATH"):
        environment.pop(key, None)
    result = subprocess.run(
        ["docker", "--host=unix:///var/run/docker.sock", *arguments],
        env=environment, capture_output=True, timeout=timeout, check=True,
    )
    return result.stdout.decode().strip()


def require(value, code):
    if not value:
        raise RuntimeError(code)


def config(content):
    return """pid /tmp/nginx.pid;
error_log /dev/null crit;
events { worker_connections 128; }
http {
  access_log off;
  client_body_temp_path /tmp/client;
  proxy_temp_path /tmp/proxy;
  fastcgi_temp_path /tmp/fastcgi;
  uwsgi_temp_path /tmp/uwsgi;
  scgi_temp_path /tmp/scgi;
""" + content + "\n}\n"


def write(root, name, content):
    path = root / name
    path.write_text(content)
    path.chmod(0o644)


def probe(port):
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=0.3)
    try:
        connection.request("GET", "/", headers={"Connection": "close"})
        response = connection.getresponse()
        marker = response.read(1024).decode()
        return response.status, marker
    except (OSError, http.client.HTTPException):
        return 0, ""
    finally:
        connection.close()


def wait_for(port, marker, deadline):
    while time.monotonic() < deadline:
        if probe(port) == (200, marker):
            return
        time.sleep(0.01)
    raise RuntimeError("SLOT_NOT_READY_WITHIN_DEADLINE")


def rehearse():
    containers = []
    network = None
    with tempfile.TemporaryDirectory(prefix="mrjam-nginx-switch-") as temporary:
        root = Path(temporary)
        root.chmod(0o755)
        try:
            # No pull or daemon startup; the reviewed image must be preloaded.
            docker("image", "inspect", IMAGE)
            network = docker("network", "create", "--label", LABEL, "mrjam-switch-" + uuid.uuid4().hex)
            require(re.fullmatch(r"[0-9a-f]{64}", network), "NETWORK_ID_REFUSED")
            for slot in ("blue", "green"):
                write(root, slot + ".conf", config(
                    f'server {{ listen 8080; location / {{ return 200 "SYNTHETIC_{slot.upper()}"; }} }}'
                ))
                write(root, slot + ".upstream", f"server {slot}:8080;\n")
            gateway = """
upstream selected { include /fixtures/active.upstream; }
server { listen 8080; location / {
  proxy_pass http://selected;
  proxy_connect_timeout 200ms;
  proxy_read_timeout 300ms;
  proxy_next_upstream off;
} }
"""
            write(root, "gateway.conf", config(gateway))
            for slot in ("blue", "green"):
                write(root, "validate-" + slot + ".conf", config(
                    gateway.replace("active.upstream", slot + ".upstream")
                ))
            write(root, "active.upstream", "server blue:8080;\n")
            ports = {}
            for name in ("blue", "green", "gateway"):
                container = docker(
                    "run", "--detach", "--pull=never", "--label", LABEL,
                    "--network", network, "--network-alias", name,
                    "--read-only", "--cap-drop=ALL", "--security-opt=no-new-privileges=true",
                    "--user=101:101", "--memory=128m", "--pids-limit=64", "--log-driver=none",
                    "--tmpfs", "/tmp:rw,nosuid,nodev,noexec,size=16m",
                    "--publish", "127.0.0.1::8080",
                    "--mount", f"type=bind,src={root},dst=/fixtures,readonly",
                    "--entrypoint=nginx", IMAGE,
                    "-c", "/fixtures/" + name + ".conf", "-g", "daemon off;",
                )
                require(re.fullmatch(r"[0-9a-f]{64}", container), "CONTAINER_ID_REFUSED")
                containers.append(container)
                binding = docker("port", container, "8080/tcp")
                require(re.fullmatch(r"127\.0\.0\.1:[0-9]+", binding), "NON_LOOPBACK_PORT_REFUSED")
                ports[name] = int(binding.split(":")[1])
            blue, green, gateway_id = containers
            # Readiness and both complete Nginx configurations precede cutover.
            wait_for(ports["blue"], "SYNTHETIC_BLUE", time.monotonic() + 10)
            wait_for(ports["green"], "SYNTHETIC_GREEN", time.monotonic() + 10)
            wait_for(ports["gateway"], "SYNTHETIC_BLUE", time.monotonic() + 10)
            for slot in ("blue", "green"):
                docker("exec", gateway_id, "nginx", "-t", "-c", "/fixtures/validate-" + slot + ".conf")

            def switch(slot, deadline):
                write(root, "next.upstream", f"server {slot}:8080;\n")
                os.replace(root / "next.upstream", root / "active.upstream")
                docker("exec", gateway_id, "nginx", "-s", "reload", "-c", "/fixtures/gateway.conf", timeout=BUDGET)
                wait_for(ports["gateway"], "SYNTHETIC_" + slot.upper(), deadline)

            started = time.monotonic()
            switch("green", started + BUDGET)
            cutover = time.monotonic() - started
            require(probe(ports["blue"]) == (200, "SYNTHETIC_BLUE"), "PREVIOUS_BACKEND_WAS_NOT_RETAINED")

            failure = time.monotonic()
            docker("stop", "--time=0", green, timeout=BUDGET)
            require(probe(ports["gateway"])[0] != 200, "INJECTED_FAILURE_NOT_OBSERVED")
            switch("blue", failure + BUDGET)
            rollback = time.monotonic() - failure
            require(cutover <= BUDGET and rollback <= BUDGET, "TRANSACTION_WINDOW_EXCEEDED")
            require(docker("inspect", "--format", "{{.State.Running}}", blue) == "true", "PREVIOUS_BACKEND_STOPPED")
            return {
                "status": "passed", "scope": "local-nginx-routing-only", "image": IMAGE,
                "budget_seconds": BUDGET, "cutover_seconds": round(cutover, 3),
                "failure_detection_and_rollback_seconds": round(rollback, 3),
                "previous_backend_retained": True, "injected_failure_detected": True,
                "rust_and_database_rollback_qualified": False, "production_access": False,
            }
        finally:
            for container in reversed(containers):
                docker("rm", "--force", container)
            if network:
                docker("network", "rm", network)


if __name__ == "__main__":
    try:
        require(len(sys.argv) == 1, "NO_ARGUMENTS_ALLOWED")
        result = rehearse()
        result["cleanup_verified"] = True
        print(json.dumps(result, sort_keys=True))
    except Exception as error:
        # No Docker configuration, credentials, raw command output or logs.
        code = str(error) if type(error) is RuntimeError else type(error).__name__
        print(json.dumps({"status": "failed", "scope": "local-nginx-routing-only", "code": code}))
        raise SystemExit(1)

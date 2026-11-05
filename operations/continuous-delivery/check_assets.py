"""Serve the built sites with the real binary, using no database or identity."""
import hashlib
import http.client
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time


def main(binary, runtime):
    configuration = json.loads(Path(runtime).read_text())
    configuration["required_capabilities"] = ["static-assets"]
    for key in ["mateval", "identity", "vision", "audition", "log"]:
        configuration[key] = None
    with tempfile.TemporaryDirectory() as temporary:
        path = Path(temporary, "runtime.json")
        path.write_text(json.dumps(configuration))
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        environment = dict(os.environ, MRJAM_LISTEN_ADDR="127.0.0.1:" + str(port),
                           MRJAM_INSTANCE="blue", MRJAM_WORKERS_ENABLED="false")
        process = subprocess.Popen([binary, "serve", "--config", str(path)], env=environment,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        def request(host, route):
            connection = http.client.HTTPConnection("127.0.0.1", port, timeout=1)
            try:
                connection.request("GET", route, headers={"Host": host})
                reply = connection.getresponse()
                return reply.status, reply.read(16 * 1024 * 1024 + 1)
            finally:
                connection.close()
        try:
            deadline = time.monotonic() + 10
            while True:
                if process.poll() is not None:
                    raise RuntimeError("Static runtime rejected the built assets: " + process.stderr.read(512).decode())
                try:
                    if request("127.0.0.1", "/readyz")[0] == 200:
                        break
                except OSError:
                    pass
                if time.monotonic() >= deadline:
                    raise RuntimeError("Static runtime did not become ready")
                time.sleep(0.05)
            for asset in configuration["assets"]:
                manifest = json.loads(Path(asset["directory"], "artifact.json").read_text())
                prefix = asset["payload_prefix"]
                status, payload = request(asset["host"], asset["mount"])
                expected = manifest["payload_sha256"][prefix + "index.html"]
                if status != 200 or hashlib.sha256(payload).hexdigest() != expected:
                    raise RuntimeError("HTTP site content does not match the built artifact")
            print(json.dumps({"real_server_sites_checked": len(configuration["assets"])}))
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
            process.stderr.close()


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])

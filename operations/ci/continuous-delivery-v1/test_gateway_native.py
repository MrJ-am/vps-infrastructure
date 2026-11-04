"""Real nginx reload, synthetic HTTP writes and an in-flight response."""
import concurrent.futures
import hashlib
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import time

from gateway_switch import Gateway, Refused


def main(nginx, output):
    ledger = set()
    ledger_lock = threading.Lock()
    entered, release, stop = threading.Event(), threading.Event(), threading.Event()
    errors = []
    servers = []

    def handler(slot):
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass

            def do_GET(self):
                raw = slot.encode()
                self.send_response(200)
                self.send_header('Content-Length', str(len(raw)))
                self.end_headers()
                if self.path == '/slow':
                    entered.set()
                    release.wait(20)
                self.wfile.write(raw)

            def do_POST(self):
                length = int(self.headers.get('Content-Length', '0'))
                assert 0 < length <= 32
                raw = self.rfile.read(length)
                with ledger_lock:
                    duplicate = raw in ledger
                    ledger.add(raw)
                self.send_response(409 if duplicate else 201)
                self.send_header('Content-Length', '0')
                self.end_headers()
        return Handler

    for slot in ('blue', 'green'):
        server = ThreadingHTTPServer(('127.0.0.1', 0), handler(slot))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        servers.append(server)
    probe = socket.socket()
    probe.bind(('127.0.0.1', 0))
    port = probe.getsockname()[1]
    probe.close()

    def request(method='GET', path='/', body=None):
        connection = http.client.HTTPConnection('127.0.0.1', port, timeout=25)
        try:
            connection.request(method, path, body=body)
            response = connection.getresponse()
            return response.status, response.read()
        finally:
            connection.close()

    def verify(slot):
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            try:
                if request() == (200, slot.encode()):
                    return
            except OSError:
                pass
            time.sleep(.025)
        raise Refused('EXPECTED_ROUTE_NOT_READY')

    def traffic():
        index = 0
        while not stop.is_set():
            try:
                assert request('POST', '/write', str(index).encode())[0] == 201
            except Exception as error:
                errors.append(type(error).__name__)
            index += 1
            time.sleep(.005)
        return index

    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        os.chmod(root, 0o755)
        state = root / 'state'
        state.mkdir(mode=0o755)
        configs = {}
        for slot, server in zip(('blue', 'green'), servers):
            path = root / (slot + '.conf')
            path.write_text(f'''daemon off;
pid {root}/nginx.pid;
error_log {root}/error.log;
events {{ worker_connections 128; }}
http {{ access_log off; client_body_temp_path {root}/client-body;
proxy_temp_path {root}/proxy;
server {{ listen 127.0.0.1:{port}; location / {{
proxy_buffering off; proxy_http_version 1.1;
proxy_pass http://127.0.0.1:{server.server_port};
}} }} }}
''')
            configs[slot] = (str(path), hashlib.sha256(path.read_bytes()).hexdigest())
        (state / 'nginx.conf').symlink_to(configs['blue'][0])
        gateway = Gateway(state, configs, nginx, verify, owner=os.getuid())
        process = subprocess.Popen([nginx, '-c', str(state / 'nginx.conf')],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        checks = []
        try:
            verify('blue')
            master = (root / 'nginx.pid').read_text()
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
                load = pool.submit(traffic)
                slow = pool.submit(request, 'GET', '/slow')
                assert entered.wait(5)
                gateway.switch('blue', 'green')
                assert not slow.done(), 'in-flight request was terminated'
                assert (root / 'nginx.pid').read_text() == master
                release.set()
                assert slow.result(5) == (200, b'blue')
                checks.append('real-reload-new-route-preserves-in-flight-old-response-and-master')
                gateway.switch('green', 'blue')
                verify('blue')
                checks.append('graceful-return-to-previous-route')

                def reject_green(slot):
                    verify(slot)
                    if slot == 'green':
                        raise Refused('SYNTHETIC_READINESS_FAILURE')
                failed = Gateway(state, configs, nginx, reject_green, owner=os.getuid())
                try:
                    failed.switch('blue', 'green')
                    raise AssertionError('failed readiness accepted')
                except Refused as error:
                    assert str(error) == 'SYNTHETIC_READINESS_FAILURE'
                verify('blue')
                assert gateway.selected() == 'blue'
                checks.append('failed-post-switch-readiness-returns-without-stopping-backends')

                class Crash(BaseException):
                    pass
                class Interrupted(Gateway):
                    def checkpoint(self, previous, target, phase):
                        super().checkpoint(previous, target, phase)
                        if phase == 'selected':
                            raise Crash()
                interrupted = Interrupted(state, configs, nginx, verify, owner=os.getuid())
                try:
                    interrupted.switch('blue', 'green')
                except Crash:
                    pass
                assert gateway.selected() == 'green'
                gateway.recover()
                assert gateway.selected() == 'blue'
                verify('blue')
                checks.append('interrupted-selection-recovers-from-durable-record')

                original = Path(configs['green'][0]).read_bytes()
                Path(configs['green'][0]).write_bytes(original + b'corruption')
                try:
                    gateway.switch('blue', 'green')
                    raise AssertionError('changed configuration accepted')
                except Refused as error:
                    assert str(error) == 'CONFIGURATION_HASH_REFUSED'
                finally:
                    Path(configs['green'][0]).write_bytes(original)
                verify('blue')
                checks.append('tampered-installed-configuration-refused')
                invalid = root / 'invalid.conf'
                invalid.write_text('this is not nginx syntax;\n')
                invalid_registry = dict(configs)
                invalid_registry['green'] = (str(invalid), hashlib.sha256(invalid.read_bytes()).hexdigest())
                bad = Gateway(state, invalid_registry, nginx, verify, owner=os.getuid())
                before = (state / 'transition.json').read_bytes()
                try:
                    bad.switch('blue', 'green')
                    raise AssertionError('invalid nginx configuration accepted')
                except Refused as error:
                    assert str(error) == 'NGINX_OPERATION_REFUSED'
                assert (state / 'transition.json').read_bytes() == before
                assert gateway.selected() == 'blue'
                verify('blue')
                checks.append('invalid-syntax-refused-before-selector-or-journal-change')
                try:
                    gateway.switch('green', 'blue')
                    raise AssertionError('stale routing expectation accepted')
                except Refused as error:
                    assert str(error) == 'STALE_ROUTE'
                checks.append('stale-routing-expectation-refused')
                time.sleep(.2)
                stop.set()
                count = load.result(5)
                assert not errors and len(ledger) == count and count >= 20
                checks.append('continuous-writes-no-errors-loss-or-duplicate-effects')
            Path(output).write_text(json.dumps({'schema_version': 1, 'checks': checks,
                'synthetic_writes': count, 'write_errors': len(errors),
                'limitations': ['synthetic HTTP backends only', 'no production activation',
                    'not a full artifact admission, Rust session or deployment qualification']}, indent=2) + '\n')
        finally:
            stop.set()
            release.set()
            subprocess.run([nginx, '-s', 'quit', '-c', str(state / 'nginx.conf')],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
            process.wait(timeout=15)
            for server in servers:
                server.shutdown()
                server.server_close()


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])

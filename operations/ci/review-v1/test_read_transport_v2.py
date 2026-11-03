"""Real loopback HTTP with invented tokens; no Forgejo production access."""
import http.server
from pathlib import Path
import sys
import threading
import signal
import socketserver
import time
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "authority-v1"))
sys.path.insert(0, str(HERE))
import contract as V
import read_transport_v2 as T


class Tests(unittest.TestCase):
    def setUp(self):
        self.requests = []
        self.body, self.status, self.headers = b'{"version":"17.0.1"}', 200, {}
        case = self
        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *_): pass
            def do_GET(self):
                case.requests.append((self.path, self.command, self.headers.get("Authorization")))
                self.send_response(case.status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(case.body)))
                for key, value in case.headers.items(): self.send_header(key, value)
                self.end_headers()
                try: self.wfile.write(case.body)
                except (BrokenPipeError, ConnectionResetError): pass
        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=lambda: self.server.serve_forever(poll_interval=.01), daemon=True)
        self.thread.start()
        self.origin = "http://127.0.0.1:" + str(self.server.server_port)
        self.origin_patch = patch.object(T, "ORIGIN", self.origin)
        self.origin_patch.start()
        self.transport = T.Transport("invented-test-token-no-secret", "mrjam-plateforme", 12)

    def tearDown(self):
        self.origin_patch.stop()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(2)

    def test_real_get_token_fixed_route_and_selected_headers(self):
        self.headers = {"X-Total-Count": "1", "Set-Cookie": "synthetic=ignored"}
        value, headers = self.transport.get("/api/v1/version")
        self.assertEqual(value, {"version": "17.0.1"})
        self.assertEqual(headers, {"x-total-count": "1"})
        self.assertEqual(self.requests, [("/api/v1/version", "GET", "token invented-test-token-no-secret")])

    def test_redirect_is_refused_without_second_request(self):
        self.status = 302
        self.headers = {"Location": self.origin + "/must-not-follow"}
        with self.assertRaises(V.Refused): self.transport.get("/api/v1/version")
        self.assertEqual(len(self.requests), 1)

    def test_inherited_proxy_does_not_receive_request(self):
        with patch.dict("os.environ", {"http_proxy": "http://127.0.0.1:1", "HTTP_PROXY": "http://127.0.0.1:1", "no_proxy": "", "NO_PROXY": ""}):
            transport = T.Transport("invented-test-token-no-secret", "mrjam-plateforme", 12)
            transport.get("/api/v1/version")
        self.assertEqual(len(self.requests), 1)

    def test_foreign_routes_and_mutation_endpoints_refused_before_request(self):
        for path in ("https://elsewhere.invalid/", "/api/v1/users/alice/tokens",
                     "/api/v1/repos/MrJ-am/vision", self.transport.pull + "/merge",
                     self.transport.pull + "/reviews?limit=50&page=202",
                     self.transport.pull + "/reviews?limit=50&page=1&extra=true"):
            with self.subTest(path=path), self.assertRaisesRegex(V.Refused, "ROUTE_REFUSED"):
                self.transport.get(path)
        self.assertFalse(self.requests)
        self.assertFalse(hasattr(self.transport, "post"))

    def test_response_size_and_duplicate_json_refused(self):
        self.body = b'{"data":"' + b"x" * T.MAX_RESPONSE + b'"}'
        with self.assertRaisesRegex(V.Refused, "LIMIT"): self.transport.get("/api/v1/version")
        self.body = b'{"a":1,"a":2}'
        with self.assertRaisesRegex(V.Refused, "DUPLICATE"): self.transport.get("/api/v1/version")

    def test_error_body_and_credentials_never_enter_exception(self):
        self.status = 403
        self.body = b"private-looking synthetic error marker"
        with self.assertRaises(V.Refused) as raised: self.transport.get("/api/v1/version")
        self.assertEqual(str(raised.exception), "API_READ_REFUSED")
        self.assertNotIn("invented-test-token", str(raised.exception))

    def test_compressed_response_refused(self):
        self.headers = {"Content-Encoding": "gzip"}
        with self.assertRaisesRegex(V.Refused, "RESPONSE_REFUSED"): self.transport.get("/api/v1/version")

    def test_shared_deadline_bounds_slow_reads_and_closes_response(self):
        clock = [0]
        class Response:
            status = 200
            headers = {"Content-Type": "application/json"}
            closed = False
            def __enter__(self): return self
            def __exit__(self, *_): self.closed = True
            def read1(self, _):
                clock[0] += 31
                return b"{"
        response = Response()
        with patch.object(T.time, "monotonic", side_effect=lambda: clock[0]):
            transport = T.Transport("invented-test-token-no-secret", "mrjam-plateforme", 12)
            with patch.object(transport.opener, "open", return_value=response):
                with self.assertRaisesRegex(V.Refused, "DEADLINE"): transport.get("/api/v1/version")
        self.assertTrue(response.closed)

    def test_header_injection_and_boolean_pr_refused(self):
        for token, number in (("invented\nAuthorization: forged", 12), ("invented-test-token-no-secret", True)):
            with self.assertRaises(V.Refused): T.Transport(token, "mrjam-plateforme", number)


class RealDeadlineTests(unittest.TestCase):
    def slow_response(self, *, chunked):
        finished = threading.Event()
        class Handler(socketserver.BaseRequestHandler):
            def handle(self):
                try:
                    request = bytearray()
                    while b"\r\n\r\n" not in request and len(request) < 8192:
                        request.extend(self.request.recv(8192))
                    if chunked:
                        self.request.sendall(b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nTransfer-Encoding: chunked\r\nConnection: close\r\n\r\n")
                        slow = b"1;extension=" + b"x" * 200 + b"\r\nx\r\n0\r\n\r\n"
                    else:
                        slow = b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: 2\r\n\r\n{}"
                    for byte in slow:
                        self.request.sendall(bytes((byte,)))
                        time.sleep(.025)
                except OSError:
                    pass
                finally:
                    finished.set()
        server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": .01}, daemon=True)
        thread.start()
        saved = signal.getsignal(signal.SIGALRM)
        try:
            with patch.object(T, "ORIGIN", "http://127.0.0.1:" + str(server.server_address[1])), \
                    patch.object(T, "TRANSACTION_SECONDS", .15):
                client = T.Transport("invented-local-token-no-secret", "mrjam-plateforme", 12)
                started = time.monotonic()
                with self.assertRaisesRegex(V.Refused, "API_DEADLINE"):
                    client.get("/api/v1/version")
                elapsed = time.monotonic() - started
                self.assertLess(elapsed, .75)
                self.assertTrue(finished.wait(1), "owned socket not shut down")
                self.assertIs(signal.getsignal(signal.SIGALRM), saved)
                return elapsed
        finally:
            server.shutdown()
            server.server_close()
            thread.join(1)

    def test_real_slow_header_is_interrupted_without_process_signal(self):
        self.slow_response(chunked=False)

    def test_real_slow_chunk_size_line_is_interrupted_without_process_signal(self):
        self.slow_response(chunked=True)


if __name__ == "__main__": unittest.main()

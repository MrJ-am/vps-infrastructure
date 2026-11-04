"""Fixed-origin, read-only transport for one managed Forgejo pull request.

No credential file reader, CLI, cookie jar or write method. A future service
must supply its own adopted read-only token from LoadCredential.
"""
import http.client
import re
import socket
import threading
import time
import urllib.parse
import urllib.request

import contract as V
import review_contract_v2 as R

ORIGIN = "http://127.0.0.1:3004"
MAX_RESPONSE = 2 * 1024**2
TRANSACTION_SECONDS = 30


class DeadlineResponse:
    def __init__(self, response, connection, timer):
        self.response, self.connection, self.timer = response, connection, timer
        self.status, self.headers = response.status, response.headers

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.timer.cancel()
        try:
            self.response.close()
        finally:
            self.connection.close()

    def read1(self, size):
        return self.response.read1(size)


class DeadlineHTTP:
    """Own one direct connection; a watchdog shuts down only its socket.

    Socket timeouts alone cannot bound readline inside HTTP status/header and
    chunk parsing when a peer supplies bytes slowly. No process signal is used.
    """
    def __init__(self, deadline):
        self.deadline = deadline

    def open(self, request, timeout):
        origin = urllib.parse.urlsplit(ORIGIN)
        V.require(origin.scheme == "http" and origin.hostname == "127.0.0.1"
                  and origin.port is not None and not origin.username
                  and not origin.password and not origin.path
                  and not origin.query and not origin.fragment, "API_ORIGIN_REFUSED")
        V.require(request.get_method() == "GET"
                  and request.full_url == ORIGIN + request.selector, "API_ROUTE_REFUSED")
        connection = http.client.HTTPConnection("127.0.0.1", origin.port, timeout=timeout)
        timer = None
        try:
            connection.connect()
            remaining = self.deadline - time.monotonic()
            V.require(remaining > 0, "API_DEADLINE")
            owned_socket = connection.sock

            def expire():
                try:
                    owned_socket.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass

            timer = threading.Timer(remaining, expire)
            timer.daemon = True
            timer.start()
            connection.request("GET", request.selector, headers=dict(request.header_items()))
            response = connection.getresponse()
            return DeadlineResponse(response, connection, timer)
        except BaseException:
            if timer is not None:
                timer.cancel()
            connection.close()
            raise


class Transport:
    def __init__(self, token, repository, number):
        V.require(type(token) is str and re.fullmatch(r"[A-Za-z0-9_-]{20,256}", token), "API_CREDENTIAL_REFUSED")
        V.require(type(repository) is str and repository in R.REPOSITORIES, "API_REPOSITORY_REFUSED")
        R.identifier(number)
        self.token = token
        self.root = "/api/v1/repos/MrJ-am/" + repository
        self.pull = self.root + "/pulls/" + str(number)
        self.end = time.monotonic() + TRANSACTION_SECONDS
        # Ignore inherited proxy settings. Never follow response URLs or retain
        # cookies; only the fixed loopback Forgejo listener receives this token.
        self.opener = DeadlineHTTP(self.end)

    def allowed(self, path):
        if type(path) is not str:
            return False
        if path in ("/api/v1/version", "/api/v1/user", self.root, self.pull,
                    self.root + "/branches/main", self.root + "/branch_protections/main"):
            return True
        if re.fullmatch(re.escape(self.root) + r"/git/commits/[0-9a-f]{40}\?stat=false&verification=false&files=false", path):
            return True
        if re.fullmatch(re.escape(self.root) + r"/git/trees/[0-9a-f]{40}%5E%7Btree%7D\?page=1&per_page=1", path):
            return True
        review = re.fullmatch(re.escape(self.pull) + r"/reviews/([1-9][0-9]{0,18})", path)
        if review:
            return int(review[1]) <= 2**63 - 1
        for base in (self.pull + "/reviews", self.root + "/branch_protections"):
            page = re.fullmatch(re.escape(base) + r"\?limit=50&page=([1-9][0-9]{0,2})", path)
            if page:
                return int(page[1]) <= 201
        return False

    def get(self, path):
        V.require(self.allowed(path), "API_ROUTE_REFUSED")
        remaining = self.end - time.monotonic()
        V.require(remaining > 0, "API_DEADLINE")
        request = urllib.request.Request(ORIGIN + path, method="GET", headers={
            "Authorization": "token " + self.token,
            "Accept": "application/json", "Accept-Encoding": "identity",
            "User-Agent": "mrjam-review-observer/1",
        })
        try:
            with self.opener.open(request, timeout=min(5, remaining)) as response:
                V.require(not 300 <= response.status < 400, "API_REDIRECT_REFUSED")
                V.require(response.status == 200, "API_READ_REFUSED")
                V.require(response.headers.get("Content-Type", "").split(";", 1)[0].strip() == "application/json"
                          and response.headers.get("Content-Encoding", "identity") == "identity", "API_RESPONSE_REFUSED")
                data = bytearray()
                while True:
                    V.require(time.monotonic() < self.end, "API_DEADLINE")
                    # read1 keeps body reads small. The socket watchdog also
                    # bounds readline inside HTTP header/chunk parsing.
                    chunk = response.read1(min(16384, MAX_RESPONSE + 1 - len(data)))
                    if not chunk:
                        break
                    data.extend(chunk)
                    V.require(len(data) <= MAX_RESPONSE, "API_RESPONSE_LIMIT")
                V.require(time.monotonic() < self.end, "API_DEADLINE")
                value = V.parse(bytes(data), limit=MAX_RESPONSE)
                V.require(time.monotonic() < self.end, "API_DEADLINE")
                count = response.headers.get("X-Total-Count")
                headers = {} if count is None else {"x-total-count": count}
                return value, headers
        except V.Refused:
            raise
        except Exception:
            # Never return token-bearing requests, response bodies or exception
            # text to the caller's diagnostics.
            raise V.Refused("API_DEADLINE" if time.monotonic() >= self.end else "API_READ_REFUSED") from None

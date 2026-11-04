"""Fixed-origin, read-only transport for one managed Forgejo pull request.

No credential file reader, CLI, cookie jar or write method. A future service
must supply its own adopted read-only token from LoadCredential.
"""
import re
import time
import urllib.error
import urllib.request

import contract as V
import review_contract as R

ORIGIN = "http://127.0.0.1:3004"
MAX_RESPONSE = 2 * 1024**2


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, new_url):
        response.close()
        raise V.Refused("API_REDIRECT_REFUSED")


class Transport:
    def __init__(self, token, repository, number):
        V.require(type(token) is str and re.fullmatch(r"[A-Za-z0-9_-]{20,256}", token), "API_CREDENTIAL_REFUSED")
        V.require(type(repository) is str and repository in R.REPOSITORIES, "API_REPOSITORY_REFUSED")
        R.identifier(number)
        self.token = token
        self.root = "/api/v1/repos/MrJ-am/" + repository
        self.pull = self.root + "/pulls/" + str(number)
        self.end = time.monotonic() + 30
        # Ignore inherited proxy settings. Never follow response URLs or retain
        # cookies; only the fixed loopback Forgejo listener receives this token.
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())

    def allowed(self, path):
        if type(path) is not str:
            return False
        if path in ("/api/v1/version", "/api/v1/user", self.root, self.pull,
                    self.root + "/branches/main", self.root + "/branch_protections/main"):
            return True
        if re.fullmatch(re.escape(self.root) + r"/git/commits/[0-9a-f]{40}\?stat=false&verification=false&files=false", path):
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
                V.require(response.status == 200
                          and response.headers.get("Content-Type", "").split(";", 1)[0].strip() == "application/json"
                          and response.headers.get("Content-Encoding", "identity") == "identity", "API_RESPONSE_REFUSED")
                data = bytearray()
                while True:
                    V.require(time.monotonic() < self.end, "API_DEADLINE")
                    # read1 performs at most one underlying buffered read. A
                    # slow peer cannot keep a large read(size) alive forever.
                    chunk = response.read1(min(16384, MAX_RESPONSE + 1 - len(data)))
                    if not chunk:
                        break
                    data.extend(chunk)
                    V.require(len(data) <= MAX_RESPONSE, "API_RESPONSE_LIMIT")
                V.require(time.monotonic() < self.end, "API_DEADLINE")
                value = V.parse(bytes(data), limit=MAX_RESPONSE)
                count = response.headers.get("X-Total-Count")
                headers = {} if count is None else {"x-total-count": count}
                return value, headers
        except V.Refused:
            raise
        except urllib.error.HTTPError as error:
            error.close()
            raise V.Refused("API_READ_REFUSED") from None
        except Exception:
            # Never return token-bearing requests, response bodies or exception
            # text to the caller's diagnostics.
            raise V.Refused("API_READ_REFUSED") from None

"""Closed API projection tests; responses invented, no token or HTTP request."""
import copy
import datetime
from pathlib import Path
import sys
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import test_review_contract as fixtures
import api_projection as P
import contract as V


class API:
    def __init__(self, fixture, size=1):
        p, o = fixture.policy, fixture.observed
        self.root = "/api/v1/repos/MrJ-am/" + p["repository"]
        self.pull = self.root + "/pulls/12"
        row = o["reviews"][0]
        raw_review = {**row, "user": {"id": row["reviewer_id"]}, "team": None,
                      "updated_at": datetime.datetime.fromtimestamp(row["updated_at"], datetime.timezone.utc).isoformat()}
        raw_review.pop("reviewer_id")
        self.rows = [{**raw_review, "id": i + 1} for i in range(size)]
        self.data = {
            "/api/v1/version": {"version": "17.0.1"},
            self.root: {"id": 11, "full_name": "MrJ-am/mrjam-plateforme", "private": True,
                        "archived": False, "default_branch": "main"},
            self.pull: {"number": 12, "user": {"id": 202}, "state": "open", "draft": False,
                        "merged": False, "merge_base": o["merge_base"],
                        "base": {"repo_id": 11, "ref": "main", "sha": o["base_sha"]},
                        "head": {"repo_id": 11, "sha": o["head_sha"]},
                        "requested_reviewers": None, "requested_reviewers_teams": None,
                        "url": "https://invented.invalid/not-followed"},
            self.root + "/branches/main": {"commit": {"id": o["base_sha"]}},
            self.root + "/git/commits/" + o["head_sha"] + "?stat=false&verification=false&files=false": {
                "sha": o["head_sha"], "commit": {"tree": {"sha": o["head_tree"]}}},
        }
        self.calls = []
        self.changed = None
        self.page_hook = None

    def get(self, path):
        self.calls.append(path)
        if path.startswith(self.pull + "/reviews?limit=50&page="):
            page = int(path.rsplit("=", 1)[1])
            rows = copy.deepcopy(self.rows[(page - 1) * 50:page * 50])
            headers = {"x-total-count": str(len(self.rows))}
            return self.page_hook(page, rows, headers) if self.page_hook else (rows, headers)
        value = copy.deepcopy(self.data[path])
        if path == self.pull and self.calls.count(path) == 2 and self.changed:
            self.changed(value)
        return value, {}


class Tests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.Tests("runTest")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.api = API(self.fixture)

    def collect(self, api=None):
        f = self.fixture
        return P.collect(api or self.api, f.policy, 12, f.policy["previous_generation"], now=f.now)

    def test_exact_projection_ignores_response_urls(self):
        self.assertEqual(self.collect(), self.fixture.observed)
        self.assertTrue(all(path.startswith("/api/v1/") for path in self.api.calls))
        self.assertEqual(self.api.calls.count(self.api.pull), 2)

    def test_complete_two_page_collection(self):
        api = API(self.fixture, 51)
        value = self.collect(api)
        self.assertTrue(value["reviews_complete"])
        self.assertEqual(len(value["reviews"]), 51)
        self.assertEqual(sum("/reviews?" in path for path in api.calls), 2)

    def test_missing_or_changing_total_refused(self):
        api = API(self.fixture, 51)
        for hook in (lambda page, rows, headers: (rows, {}),
                     lambda page, rows, headers: (rows, {"x-total-count": str(51 if page == 1 else 52)})):
            api.page_hook = hook
            with self.assertRaises(V.Refused): self.collect(api)

    def test_duplicate_or_short_page_cannot_claim_completeness(self):
        api = API(self.fixture, 51)
        api.rows[-1]["id"] = 1
        with self.assertRaisesRegex(V.Refused, "DUPLICATE"): self.collect(api)
        api = API(self.fixture, 51)
        api.page_hook = lambda page, rows, headers: (rows[:-1], headers)
        with self.assertRaises(V.Refused): self.collect(api)

    def test_team_or_requested_human_review_refused(self):
        for field in ("requested_reviewers", "requested_reviewers_teams"):
            api = API(self.fixture)
            api.data[api.pull][field] = [{"id": 901}]
            with self.subTest(field=field), self.assertRaises(V.Refused): self.collect(api)

    def test_head_change_during_collection_refused(self):
        self.api.changed = lambda value: value["head"].update(sha="2" * 40)
        with self.assertRaisesRegex(V.Refused, "CHANGED"): self.collect()

    def test_foreign_repository_and_non_hex_head_never_select_route(self):
        for key, value in (("repo_id", 99), ("sha", "../../other")):
            api = API(self.fixture)
            api.data[api.pull]["head"][key] = value
            with self.assertRaises(V.Refused): self.collect(api)
            self.assertFalse(any("/git/commits/" in path for path in api.calls))

    def test_wrong_main_or_commit_tree_refused(self):
        self.api.data[self.api.root + "/branches/main"]["commit"]["id"] = "2" * 40
        with self.assertRaisesRegex(V.Refused, "BASE_CHANGED"): self.collect()
        api = API(self.fixture)
        for path, value in api.data.items():
            if "/git/commits/" in path: value["sha"] = "2" * 40
        with self.assertRaisesRegex(V.Refused, "COMMIT_CHANGED"): self.collect(api)

    def test_generation_and_api_version_refused(self):
        self.api.data["/api/v1/version"]["version"] = "18.0.0"
        with self.assertRaises(V.Refused): self.collect()
        with self.assertRaises(V.Refused):
            P.collect(self.api, self.fixture.policy, 12, "/wrong", now=self.fixture.now)


if __name__ == "__main__": unittest.main()

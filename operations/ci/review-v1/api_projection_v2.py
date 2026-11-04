"""Closed metadata projection from a trusted Forgejo17 API transport.

No HTTP client, token reader, mutation or CLI is defined here. The service must
provide its fixed-origin authenticated transport, never a candidate callback.
Review bodies remain internal for manifest binding. The future service must
emit only the checked decision, never this projection or raw API responses.
"""
import datetime
import re

import contract as V
import review_contract_v2 as R

PAGE_SIZE = 50
MAX_REVIEWS = 10000


def record(value):
    V.require(type(value) is dict, "API_OBJECT_REFUSED")
    return value


def sequence(value):
    V.require(value is None or type(value) is list, "API_LIST_REFUSED")
    return [] if value is None else value


def identifier(value):
    R.identifier(value)
    return value


def revision(value):
    V.text(value, V.REV)
    return value


def timestamp(value):
    V.require(type(value) is str and re.fullmatch(
        r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,9})?(?:Z|[+-][0-9]{2}:[0-9]{2})", value),
        "API_TIME_REFUSED")
    try:
        parsed = datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
        result = int(parsed.timestamp())
    except (ValueError, OverflowError):
        raise V.Refused("API_TIME_REFUSED") from None
    V.integer(result, 0, 2**63 - 1)
    return result


def pull_projection(raw, policy):
    raw = record(raw)
    base, head = record(raw["base"]), record(raw["head"])
    V.require(identifier(base["repo_id"]) == policy["repository_id"]
              and identifier(head["repo_id"]) == policy["repository_id"], "PR_REPOSITORY_REFUSED")
    # This first service accepts in-repository proposals only, not a foreign
    # fork selected through a response URL. Teams must be resolved first too.
    V.require(not sequence(raw["requested_reviewers_teams"]), "TEAM_REVIEW_OUTSTANDING")
    requested = sorted(identifier(record(item)["id"]) for item in sequence(raw["requested_reviewers"]))
    R.identifiers(requested)
    return {"repository_id": policy["repository_id"], "pull_request": identifier(raw["number"]),
            "author_id": identifier(record(raw["user"])["id"]), "state": raw["state"],
            "draft": raw["draft"], "merged": raw["merged"], "base_ref": base["ref"],
            "base_sha": revision(base["sha"]), "head_sha": revision(head["sha"]),
            "merge_base": revision(raw["merge_base"]), "requested_reviewer_ids": requested}


def review_projection(raw):
    raw = record(raw)
    V.require(raw["team"] is None, "TEAM_REVIEW_REFUSED")
    return {"id": identifier(raw["id"]), "reviewer_id": identifier(record(raw["user"])["id"]),
            "state": raw["state"], "body": raw["body"], "commit_id": revision(raw["commit_id"]),
            "stale": raw["stale"], "official": raw["official"], "dismissed": raw["dismissed"],
            "updated_at": timestamp(raw["updated_at"])}


def pending_requests(participants, reviews):
    # Forgejo17 LoadRequestedReviewers returns active decision participants,
    # including APPROVED, from max(id) per reviewer with dismissed=false.
    active = {}
    for row in sorted(reviews, key=lambda row: row["id"]):
        if row["state"] in ("APPROVED", "REQUEST_CHANGES", "REQUEST_REVIEW") and not row["dismissed"]:
            active[row["reviewer_id"]] = row
    V.require(participants == sorted(active), "REVIEW_PARTICIPANTS_CHANGED")
    return sorted(reviewer for reviewer, row in active.items() if row["state"] == "REQUEST_REVIEW")


def collect(api, policy, number, previous_generation, *, now):
    """Read fixed routes, complete review pagination and reread moving heads.

    api.get returns (JSON object, lower-case header mapping). Authentication,
    origin, byte/time budgets and credentials belong to the separate transport.
    No field returned by the API is followed as a URL or executable instruction.
    """
    R.policy(policy)
    identifier(number)
    V.integer(now, 0, 2**63 - 1)
    V.require(previous_generation == policy["previous_generation"], "GENERATION_REFUSED")
    root = "/api/v1/repos/MrJ-am/" + policy["repository"]
    pull_path = root + "/pulls/" + str(number)
    version, _ = api.get("/api/v1/version")
    V.require(record(version).get("version") == "17.0.1", "FORGEJO_VERSION_REFUSED")
    repository, _ = api.get(root)
    V.require(identifier(record(repository)["id"]) == policy["repository_id"]
              and repository["full_name"] == "MrJ-am/" + policy["repository"]
              and repository["private"] is True and repository["archived"] is False
              and repository["default_branch"] == "main", "REPOSITORY_REFUSED")
    raw, _ = api.get(pull_path)
    pull = pull_projection(raw, policy)
    V.require(pull["pull_request"] == number, "PR_NUMBER_REFUSED")
    branch, _ = api.get(root + "/branches/main")
    V.require(revision(record(record(branch)["commit"])["id"]) == pull["base_sha"], "BASE_CHANGED")
    commit, _ = api.get(root + "/git/commits/" + pull["head_sha"] + "?stat=false&verification=false&files=false")
    V.require(revision(record(commit)["sha"]) == pull["head_sha"], "COMMIT_CHANGED")
    # Forgejo17 commit.tree.sha names the COMMIT, not its tree object.
    # Resolve a fixed tree peel explicitly; do not follow the returned URL.
    tree_response, _ = api.get(root + "/git/trees/" + pull["head_sha"]
                               + "%5E%7Btree%7D?page=1&per_page=1")
    tree = revision(record(tree_response)["sha"])
    V.require(tree != pull["head_sha"], "TREE_RESOLUTION_REFUSED")
    reviews, count, seen = [], None, set()
    for page in range(1, MAX_REVIEWS // PAGE_SIZE + 2):
        rows, headers = api.get(pull_path + "/reviews?limit=50&page=" + str(page))
        V.require(type(rows) is list and len(rows) <= PAGE_SIZE, "REVIEW_PAGE_REFUSED")
        total = record(headers).get("x-total-count")
        V.require(type(total) is str and re.fullmatch(r"0|[1-9][0-9]{0,4}", total), "REVIEW_COUNT_REFUSED")
        total = int(total)
        V.require(total <= MAX_REVIEWS and (count is None or total == count), "REVIEW_COUNT_CHANGED")
        count = total
        for row in rows:
            projected = review_projection(row)
            V.require(projected["id"] not in seen, "DUPLICATE_REVIEW_PAGE")
            seen.add(projected["id"])
            reviews.append(projected)
        V.require(len(reviews) <= count, "REVIEW_COUNT_REFUSED")
        if len(reviews) == count:
            break
        V.require(len(rows) == PAGE_SIZE, "INCOMPLETE_REVIEW_PAGE")
    else:
        raise V.Refused("REVIEW_PAGE_LIMIT")
    # Head/base and review requests may move while pages are read. Refuse that
    # race here; the merge service must also recheck immediately before its POST.
    after, _ = api.get(pull_path)
    V.require(pull_projection(after, policy) == pull, "PULL_REQUEST_CHANGED")
    branch, _ = api.get(root + "/branches/main")
    V.require(revision(record(record(branch)["commit"])["id"]) == pull["base_sha"], "BASE_CHANGED")
    value = {"schema_version": 1, "forgejo_version": "17.0.1", **pull,
             "head_tree": tree, "reviews_complete": True, "reviews": reviews,
             "observed_at": now, "previous_generation": previous_generation}
    value["requested_reviewer_ids"] = pending_requests(pull["requested_reviewer_ids"], reviews)
    R.observation(value, now=now)
    return value

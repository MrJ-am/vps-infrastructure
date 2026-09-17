#!/usr/bin/env python3
"""GET publics uniquement ; TLS vérifié, aucune création de participation."""
import argparse
import hashlib
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from registry import ROOT, load


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def request(url):
    opener = urllib.request.build_opener(NoRedirect())
    req = urllib.request.Request(url, headers={"User-Agent": "vps-infrastructure-check/1", "Accept-Encoding": "identity"})
    try:
        response = opener.open(req, timeout=10)
    except urllib.error.HTTPError as exc:
        response = exc
    with response:
        body = response.read(16 * 1024 * 1024 + 1)
        if len(body) > 16 * 1024 * 1024:
            raise ValueError(f"Réponse trop grande : {url}")
        return response.code, response.headers, body


def validate_response(url, probe, response):
    status, headers, body = response
    if status != probe["status"]:
        raise ValueError(f"{url} : HTTP {status}, attendu {probe['status']}")
    content_type = headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
    if "contentType" in probe and content_type != probe["contentType"]:
        raise ValueError(f"{url} : type de contenu inattendu : {content_type}")
    if "json" in probe:
        value = json.loads(body)
        if not isinstance(value, dict) or any(value.get(k) != v for k, v in probe["json"].items()):
            raise ValueError(f"{url} : résultat JSON inattendu")
    result = {"status": status, "contentType": content_type}
    if probe.get("unchanged"):
        result["sha256"] = hashlib.sha256(body).hexdigest()
    return result


def redirect(url, allowed_hosts, expected_path):
    status, headers, _ = request(url)
    target = urllib.parse.urlsplit(urllib.parse.urljoin(url, headers.get("Location", "")))
    if (status not in (301, 308) or target.scheme != "https" or target.hostname not in allowed_hosts
            or target.port not in (None, 443) or target.username is not None
            or target.path != expected_path or target.query != urllib.parse.urlsplit(url).query):
        raise ValueError(f"Redirection inattendue : {url}")
    return {"status": status, "location": target.geturl()}


def check(projects):
    results = {}
    for site in projects.values():
        domain, prefix = site["domain"], site["prefix"]
        url = f"http://{domain}/"
        results[url] = redirect(url, [domain], "/")
        if prefix:
            for path in ("/", prefix):
                url = f"https://{domain}{path}"
                result = redirect(url, [domain], prefix + "/")
                if result["status"] != 308:
                    raise ValueError(f"{url} : redirection 308 attendue")
                results[url] = result
        for alias in site["aliases"]:
            url = f"https://{alias}{prefix}/?vps-check=1"
            results[url] = redirect(url, [domain], prefix + "/")
            url = f"http://{alias}{prefix}/?vps-check=1"
            results[url] = redirect(url, [alias, domain], prefix + "/")
        for probe in site["probes"]:
            url = f"https://{domain}{probe['path']}"
            results[url] = validate_response(url, probe, request(url))
    return results


def compare(before, after):
    # Un nouveau projet est permis ; aucun ancien contrôle ne peut disparaître.
    for url, expected in before.items():
        if url not in after or after[url] != expected:
            raise ValueError(f"Régression par rapport au relevé initial : {url}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, default=ROOT / "projects.json")
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    results = check(load(args.registry))
    if args.baseline:
        compare(json.loads(args.baseline.read_text()), results)
    if args.output:
        args.output.write_text(json.dumps(results, indent=2, ensure_ascii=False) + "\n")
    print(f"{len(results)} contrôles HTTP réussis ; certificats TLS vérifiés.")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, urllib.error.URLError) as exc:
        print(f"ÉCHEC : {exc}", file=sys.stderr)
        sys.exit(1)

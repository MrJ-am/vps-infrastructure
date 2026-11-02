"""Offline provider checks with invented text and the preserved public model."""
import hashlib
import http.client
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time

MODEL = Path("/nix/store/mwwjyy4vlrwp59a7srjy53x24viksa6z-vision-modele-multilingue-e8f8c211226b")
PYTHON = "/nix/store/dbnsh65c9fir9psk7waq3swb3mdh18cr-python3-3.13.15-env/bin/python"
ROOT = Path(__file__).resolve().parent


def digest(path):
    result = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1048576):
            result.update(block)
    return result.hexdigest()


def request(payload, path="/embedding"):
    connection = http.client.HTTPConnection("127.0.0.1", 39004, timeout=60)
    try:
        connection.request("POST", path, json.dumps(payload).encode(), {"Content-Type": "application/json"})
        response = connection.getresponse()
        return response.status, json.loads(response.read(65537))
    finally:
        connection.close()


def vector(value):
    status, result = request({"contenu": value})
    assert status == 200
    values = result["embedding"]
    assert len(values) == 384 and all(math.isfinite(n) for n in values)
    assert abs(sum(n * n for n in values) - 1) < 1e-5
    return result


def main():
    lock = json.loads((ROOT / "model.lock.json").read_text())
    expected = {item["chemin"]: item["sha256"] for item in lock["fichiers"]}
    actual = {str(path.relative_to(MODEL)): digest(path) for path in MODEL.rglob("*") if path.is_file()}
    assert actual == expected
    identity = hashlib.sha256()
    for relative in sorted(expected):
        identity.update(relative.encode())
        with (MODEL / relative).open("rb") as stream:
            while block := stream.read(1048576):
                identity.update(block)
    model_id = "contenu-fenetres-1:" + identity.hexdigest()
    started = time.monotonic()
    environment = dict(os.environ, HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", HF_HOME="/tmp/hf",
                       OMP_NUM_THREADS="2", TOKENIZERS_PARALLELISM="false")
    # This fixture uses only invented requests and public model bytes. Preserve
    # setup diagnostics locally; the production service keeps its logs closed.
    diagnostic = Path(sys.argv[1]).with_suffix(".provider.log").open("wb")
    process = subprocess.Popen([PYTHON, "-B", str(ROOT / "embeddings.py"), "--modele", str(MODEL)],
                               env=environment, stdout=subprocess.DEVNULL, stderr=diagnostic)
    try:
        deadline = time.monotonic() + 120
        while True:
            assert process.poll() is None, "PROVIDER_EXITED"
            try:
                status, _ = request({"contenu": ""})
                assert status == 400
                break
            except ConnectionRefusedError:
                if time.monotonic() >= deadline:
                    raise RuntimeError("PROVIDER_START_TIMEOUT")
                time.sleep(0.1)
        first = vector("Une démonstration relie des hypothèses à une conclusion.")
        assert first["modele"] == model_id
        assert vector("Une démonstration relie des hypothèses à une conclusion.") == first
        assert vector("A triangle has three sides.")["modele"] == model_id
        prefix = "Le triangle possède trois côtés. " * 90
        one = vector(prefix + "La fin décrit une preuve logique. " * 12)
        two = vector(prefix + "La fin décrit un jardin fleuri. " * 12)
        assert max(abs(a - b) for a, b in zip(one["embedding"], two["embedding"])) > 1e-5
        for invalid in ({}, {"contenu": None}, {"contenu": " "}, {"contenu": "x" * 12001}):
            assert request(invalid)[0] == 400
        assert request({"contenu": "exemple"}, "/other")[0] == 400
        result = {"schema_version": 1, "passed": True, "groups": 6, "synthetic_data_only": True,
                  "external_network": False, "dimensions": 384, "model_id": model_id,
                  "model_revision": lock["revision"], "model_store_path": str(MODEL),
                  "python_store_path": str(Path(PYTHON).parent.parent),
                  "provider_sha256": digest(ROOT / "embeddings.py"),
                  "fixture_sha256": digest(Path(__file__)), "elapsed_seconds": round(time.monotonic() - started, 2),
                  "production_activation": False}
        Path(sys.argv[1]).write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    finally:
        process.terminate()
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        diagnostic.close()


if __name__ == "__main__":
    main()

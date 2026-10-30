"""Build-time contract on non-secret preparation files, not a live Forgejo test."""
import configparser
import json
import pathlib
import sys


def check(root):
    review = root / "review"
    config = configparser.ConfigParser(interpolation=None)
    config.optionxform = str
    config.read(review / "forgejo-candidate.ini")
    assert config["server"]["HTTP_ADDR"] == "127.0.0.1"
    assert config["server"]["ROOT_URL"] == "https://forge.mrj.am/"
    assert config["service"].getboolean("REQUIRE_SIGNIN_VIEW")
    assert not config["service"].getboolean("ENABLE_INTERNAL_SIGNIN")
    assert not config["service"].getboolean("ENABLE_BASIC_AUTHENTICATION")
    assert not config["actions"].getboolean("ENABLED")
    assert config["repository"].getboolean("FORCE_PRIVATE")
    assert config["markup.orgmode"]["RENDER_CONTENT_MODE"] == "sanitized"
    assert config["markup.orgmode"]["RENDER_COMMAND"].startswith("/nix/store/")
    refs = json.loads((review / "runtime-references.json").read_text())
    assert refs["activation_allowed"] is False
    assert refs["database"]["create_database"] is False
    assert refs["identity"]["sso_adapter_qualified"] is False
    assert refs["runner"]["runtime_backend"] is None
    assert refs["missing_before_enable"]
    for secret in refs["secrets"]:
        assert secret["exact_existing_path"] is None
        if not secret.get("public", False):
            assert all(secret[field] is False for field in ("store", "git", "cloud"))
    runner = json.loads((review / "runner-policy.json").read_text())
    assert runner["enabled"] is False and runner["maximum_jobs"] == 1
    assert runner["production_mounts"] == []
    assert all(runner[field] is False for field in ("privileged", "docker_socket", "production_network", "signing_credentials"))
    assert runner["ephemeral"] is True
    assert not (root / "bin").exists()
    assert not (root / "etc").exists()


if __name__ == "__main__":
    check(pathlib.Path(sys.argv[1]))

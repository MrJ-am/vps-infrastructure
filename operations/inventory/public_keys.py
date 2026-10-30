"""Validate public keys only; never read a private key or echo a rejected value."""
import base64
import re


def valid(key):
    if not isinstance(key, str) or len(key) > 256 or not re.fullmatch(r"ssh-ed25519 [A-Za-z0-9+/=]+(?: [A-Za-z0-9._@+-]+)?", key):
        return False
    try:
        raw = base64.b64decode(key.split()[1], validate=True)
        return len(raw) == 51 and raw[:19] == b"\0\0\0\x0bssh-ed25519\0\0\0\x20"
    except Exception:
        return False

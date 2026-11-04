"""Code selection for the independent ViSe validator, never deployment authority.

The receiver must still validate the complete Git tree, object identities,
submodules, byte limits and active configuration with the shared tree gate.
Dependency lock changes require materialization and independent validation;
selecting a lock file does not authorize fetching or running install scripts.
"""
import re
from pathlib import PurePosixPath

EXACT = frozenset({
    'COPYING', 'LICENSE', 'backend/Cargo.toml', 'backend/Cargo.lock',
    'elm.json', 'package.json', 'package-lock.json', 'tsconfig.json',
})
SCOPES = (
    # Include Cargo's implicit build.rs and integration tests too, not only
    # src/: omitting them would compile a different source graph from Git.
    ('backend/', frozenset({'.rs', '.sql'})),
    ('bridge/', frozenset({'.ts'})),
    ('content/', frozenset({'.json'})),
    ('frontend/', frozenset({'.elm', '.html', '.css', '.js', '.json', '.svg', '.png',
                             '.webp', '.ico', '.webmanifest', '.woff', '.woff2'})),
    ('shared/elm/', frozenset({'.elm'})),
    ('shared/assets/', frozenset({'.css', '.js', '.svg', '.png', '.webp', '.woff', '.woff2'})),
    ('scripts/', frozenset({'.mjs'})),
    ('tests/', frozenset({'.ts', '.json'})),
)


def selected(name):
    if not isinstance(name, str) or not name or len(name) > 4096:
        return False
    if any(part in {'.', '..', ''} or not re.fullmatch(r'[A-Za-z0-9_+.-]+', part)
           for part in name.split('/')):
        return False
    return name in EXACT or any(name.startswith(prefix) and PurePosixPath(name).suffix in suffixes
                               for prefix, suffixes in SCOPES)

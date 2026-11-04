"""Capture Signature identity resources from exact, verified Git objects.

This is a source binding, not font/visual qualification or delivery authority.
The independent validator must still qualify generated fonts and consumers.
No checkout, candidate generator, network, filesystem write or deployment.
"""
import hashlib
import json
import source_snapshot as S

# Existing consumer names only. Never publish the repository or its TeX
# documents wholesale, and keep the font licence with the derived resources.
RESOURCES = {
    'signature.css': 'web/signature.css',
    'MrJamSignature.woff2': 'web/MrJamSignature.woff2',
    'EchoPoint.woff2': 'web/EchoPoint.woff2',
    'Echologo.svg': 'artwork/Echologo.svg',
    'Parisienne-Regular.ttf': 'fonts/Parisienne-Regular.ttf',
    'Parisienne-OFL.txt': 'fonts/Parisienne-OFL.txt',
}
INPUTS = frozenset(RESOURCES.values()) | {'mrjam.sty', 'web/geometry.json'}


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def capture(reader, revision):
    """Return manifest and bytes for a controller-observed Signature commit.

    The caller binds repository identity and ancestry to the observed proposal.
    Every input is verified against its Git blob; generated resource consistency
    beyond geometry's three source hashes is intentionally not asserted here.
    """
    tree = S.complete_tree(reader, revision)
    entries = {entry['path']: entry for entry in tree['tree']}
    S.require(INPUTS <= entries.keys(), 'SIGNATURE_INPUT_MISSING')
    S.require(all(entries[name]['type'] == 'blob' and entries[name]['mode'] == '100644'
                  for name in INPUTS), 'SIGNATURE_INPUT_MODE_REFUSED')
    blobs = S.select_blobs(reader, tree, lambda name: name in INPUTS)
    S.require(set(blobs) == INPUTS, 'SIGNATURE_INPUT_SET_REFUSED')
    try:
        geometry = json.loads(blobs['web/geometry.json'])
    except (ValueError, UnicodeError):
        raise S.Refused('SIGNATURE_GEOMETRY_REFUSED') from None
    S.require(type(geometry) is dict, 'SIGNATURE_GEOMETRY_REFUSED')
    for field, name in (('source_sha256', 'mrjam.sty'),
                        ('font_sha256', 'fonts/Parisienne-Regular.ttf'),
                        ('svg_sha256', 'artwork/Echologo.svg')):
        S.require(geometry.get(field) == digest(blobs[name]), 'SIGNATURE_GEOMETRY_STALE')
    manifest = {
        'schema_version': 1, 'repository': 'MrJ-am/Signature',
        'revision': revision, 'tree_sha': tree['sha'],
        'deployment_authorized': False,
        'inputs': {name: {'git_blob': entries[name]['sha'],
                          'sha256': digest(blobs[name]), 'bytes': len(blobs[name])}
                   for name in sorted(INPUTS)},
        'resources': dict(RESOURCES),
    }
    return manifest, {name: blobs[source] for name, source in RESOURCES.items()}

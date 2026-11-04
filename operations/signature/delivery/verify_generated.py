"""Compare independent regeneration to captured fonts and their text contract."""
import hashlib
import importlib.metadata
from decimal import Decimal
import json
from pathlib import Path
import sys
from fontTools.ttLib import TTFont

OUTPUTS = ('web/MrJamSignature.woff2', 'web/EchoPoint.woff2',
           'web/signature.css', 'web/geometry.json')


def require(value, code):
    if not value:
        raise ValueError(code)


def geometry(raw):
    """JSON numbers compare by exact decimal value, never by float rounding.

    10 and 10.0 describe the same geometry; booleans, duplicate keys and
    non-finite numbers do not. All other values and the whole shape must match.
    """
    require(len(raw) <= 65536, 'SIGNATURE_GEOMETRY_SIZE_REFUSED')
    def pairs(items):
        result = dict(items)
        require(len(result) == len(items), 'SIGNATURE_GEOMETRY_DUPLICATE_KEY')
        return result
    def constant(_):
        raise ValueError('SIGNATURE_GEOMETRY_NONFINITE')
    value = json.loads(raw, parse_int=Decimal, parse_float=Decimal,
                       object_pairs_hook=pairs, parse_constant=constant)
    def checked(item):
        if type(item) is dict:
            return all(checked(v) for v in item.values())
        if type(item) is list:
            return all(checked(v) for v in item)
        return type(item) in (str, Decimal)
    require(type(value) is dict and checked(value), 'SIGNATURE_GEOMETRY_TYPE_REFUSED')
    return value


def verify(source, generated):
    rows = {}
    for name in OUTPUTS:
        a, b = source/name, generated/name
        require(a.is_file() and not a.is_symlink() and b.is_file() and not b.is_symlink(),
                'SIGNATURE_GENERATED_FILE_REFUSED')
        require(0 < a.stat().st_size <= 32*1024**2 and 0 < b.stat().st_size <= 32*1024**2,
                'SIGNATURE_GENERATED_SIZE_REFUSED')
        original, rebuilt = a.read_bytes(), b.read_bytes()
        same = geometry(original) == geometry(rebuilt) if name == 'web/geometry.json' else original == rebuilt
        require(same, 'SIGNATURE_REGENERATION_MISMATCH: '+name)
        rows[name] = {'sha256': hashlib.sha256(rebuilt).hexdigest(), 'bytes': len(rebuilt),
                      'source_sha256': hashlib.sha256(original).hexdigest(),
                      'byte_identical': original == rebuilt}
    for family, text in (('MrJamSignature','MrJ.am'), ('EchoPoint','.')):
        with TTFont(generated/('web/'+family+'.woff2'), lazy=False) as font:
            require(font.flavor == 'woff2', 'SIGNATURE_FONT_FORMAT_REFUSED')
            require(set(font.getBestCmap()) == set(map(ord, text)), 'SIGNATURE_UNICODE_REFUSED')
            require(font['COLR'].version == 0 and len(font['CPAL'].palettes) == 2,
                    'SIGNATURE_COLOUR_CONTRACT_REFUSED')
            require(font['name'].getDebugName(1) == family, 'SIGNATURE_FONT_NAME_REFUSED')
            require('SIL Open Font License 1.1' in (font['name'].getDebugName(13) or ''),
                    'SIGNATURE_FONT_LICENCE_REFUSED')
    return {'schema_version': 1, 'deployment_authorized': False,
            'regeneration_verified': True, 'font_and_css_bytes_exact': True,
            'geometry_values_equal': True, 'unicode_mapping_verified': True,
            'tool_versions': {name: importlib.metadata.version(name)
                              for name in ('fonttools','brotli','skia-pathops','uharfbuzz')},
            'outputs': rows}


if __name__ == '__main__':
    require(len(sys.argv) == 4, 'SIGNATURE_ARGUMENTS_REFUSED')
    result = verify(Path(sys.argv[1]), Path(sys.argv[2]))
    Path(sys.argv[3]).write_text(json.dumps(result, sort_keys=True, indent=2)+'\n')

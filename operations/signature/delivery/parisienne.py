"""Deterministic WOFF2 conversion for Vision, preserving the original font."""
import hashlib
import io
from fontTools.pens.recordingPen import RecordingPen
from fontTools.ttLib import TTFont


def require(value, code):
    if not value:
        raise ValueError(code)


def equivalent(original, converted):
    """Allow WOFF2 storage changes, never changed outlines, hints or metrics."""
    with TTFont(io.BytesIO(original), recalcTimestamp=False) as a, \
         TTFont(io.BytesIO(converted), recalcTimestamp=False) as b:
        require(a.flavor is None and b.flavor == 'woff2', 'PARISIENNE_FORMAT_REFUSED')
        require(set(a.keys()) == set(b.keys()) and 'glyf' in a, 'PARISIENNE_TABLES_CHANGED')
        require(a.getGlyphOrder() == b.getGlyphOrder(), 'PARISIENNE_GLYPH_ORDER_CHANGED')
        for name in a.keys():
            if name not in ('GlyphOrder','head','glyf','loca'):
                require(a.getTableData(name) == b.getTableData(name), 'PARISIENNE_TABLE_CHANGED: '+name)
        # WOFF2 sets head flag 11 and recomputes the SFNT checksum. Creation and
        # modification times remain the captured original's, not wall-clock time.
        require(b['head'].flags == a['head'].flags | 0x800, 'PARISIENNE_FLAGS_CHANGED')
        ah, bh = bytearray(a.getTableData('head')), bytearray(b.getTableData('head'))
        for data in (ah,bh):
            data[8:12] = b'\0'*4
            data[16:18] = b'\0'*2
        require(ah == bh, 'PARISIENNE_HEADER_CHANGED')
        ag, bg = a.getGlyphSet(), b.getGlyphSet()
        for name in a.getGlyphOrder():
            x, y = RecordingPen(), RecordingPen()
            ag[name].draw(x); bg[name].draw(y)
            require(x.value == y.value, 'PARISIENNE_OUTLINE_CHANGED')
            for field in ('numberOfContours','xMin','yMin','xMax','yMax'):
                require(getattr(a['glyf'][name],field,None) == getattr(b['glyf'][name],field,None),
                        'PARISIENNE_GLYPH_BOUNDS_CHANGED')
            def instructions(glyph):
                return bytes(glyph.program.getBytecode()) if hasattr(glyph,'program') else b''
            require(instructions(a['glyf'][name]) == instructions(b['glyf'][name]),
                    'PARISIENNE_INSTRUCTIONS_CHANGED')


def convert(original):
    require(type(original) is bytes and 0 < len(original) <= 16*1024**2, 'PARISIENNE_INPUT_REFUSED')
    out = io.BytesIO()
    with TTFont(io.BytesIO(original), recalcTimestamp=False) as font:
        require(font.flavor is None and 'glyf' in font, 'PARISIENNE_INPUT_FORMAT_REFUSED')
        font.flavor = 'woff2'
        font.save(out)
    converted = out.getvalue()
    equivalent(original, converted)
    return converted, {'schema_version':1, 'source_sha256':hashlib.sha256(original).hexdigest(),
                       'sha256':hashlib.sha256(converted).hexdigest(), 'bytes':len(converted),
                       'outlines_metrics_hints_preserved':True, 'deployment_authorized':False}

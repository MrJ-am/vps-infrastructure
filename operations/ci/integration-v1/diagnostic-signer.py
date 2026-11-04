"""Synthetic failure observer: only a closed require code, never any value."""
import json,re,sys
sys.path.insert(0,'@authority@/lib')
import contract as C
import signer as A
original=C.require
def observed(condition,code='AUTHORITY_INPUT_REFUSED'):
    if not condition and type(code) is str and re.fullmatch(r'[A-Z_]{1,80}',code):
        print(json.dumps({'authority_diagnostic':code},sort_keys=True),file=sys.stderr,flush=True)
    return original(condition,code)
C.require=observed
raise SystemExit(A.main())

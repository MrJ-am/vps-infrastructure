"""Read only an invented credential view; emit booleans and a closed code."""
import json,os,sys
sys.path.insert(0,'@authority@/lib')
import contract as C
import signing_credential as K
try:
    readonly=bool(os.statvfs(K.PATH).f_flag&os.ST_RDONLY)
    K.read_key(K.PATH)
    result={'accepted':True,'readonly':readonly,'code':'ACCEPTED'};status=0
except C.Refused as error:
    result={'accepted':False,'readonly':readonly,'code':str(error)};status=1
except BaseException:
    result={'accepted':False,'readonly':False,'code':'SYNTHETIC_VIEW_UNAVAILABLE'};status=1
print(json.dumps({'synthetic_reader':result},sort_keys=True),flush=True)
raise SystemExit(status)

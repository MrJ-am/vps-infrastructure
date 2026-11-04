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
except BaseException as error:
    # This probe runs only in the invented VM, never against a production key.
    metadata=[]
    for path in ('/run','/run/credentials',os.path.dirname(K.PATH),K.PATH):
        try:
            info=os.lstat(path)
            metadata.append({'path':path,'uid':info.st_uid,'gid':info.st_gid,'mode':oct(info.st_mode&0o7777)})
        except OSError as failure:metadata.append({'path':path,'errno':failure.errno})
    print(json.dumps({'synthetic_view_diagnostic':metadata,'exception_type':type(error).__name__,'errno':getattr(error,'errno',None)}),flush=True)
    result={'accepted':False,'readonly':False,'code':'SYNTHETIC_VIEW_UNAVAILABLE'};status=1
print(json.dumps({'synthetic_reader':result},sort_keys=True),flush=True)
raise SystemExit(status)

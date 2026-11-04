"""Read only PR2 review/status metadata through an ephemeral repository lease."""
import importlib.util,json,os,sys
from pathlib import Path
sys.path.insert(0,'/nix/store/ifj6nyig0yvxsp024cgd8yylhxd4ql66-mrjam-vise-rules-audit-publisher-1/libexec')
import core,lease,proposal_entry as E,publish
assert len(sys.argv)==1 and os.geteuid()==0 and os.uname().nodename=='srv1982677'
class ReadOnly(publish.Transport):
    def endpoint_allowed(self,method,path):
        return method=='GET' and (super().endpoint_allowed(method,path)
            or path==publish.PULL+'/reviews?limit=50&page=1')
spec=importlib.util.spec_from_file_location('qualified_bootstrap',E.BOOTSTRAP)
bootstrap=importlib.util.module_from_spec(spec);spec.loader.exec_module(bootstrap)
binding=core.Binding(Path(E.BINDING).read_bytes(),E.BINDING_SHA256)
with lease.repository_lease(bootstrap) as token:
    api=ReadOnly(token,binding)
    observed=publish.observe(api,binding,bootstrap)
    status=publish.status(api,observed['author_id'])
    rows=api.request('GET',publish.PULL+'/reviews?limit=50&page=1') or []
    assert type(rows) is list and len(rows)<50
    result={'head':publish.HEAD,'status_id':status,'protection_exact':True,
        'reviews':[{k:r.get(k) for k in ('id','state','commit_id','official','stale','dismissed')}
            for r in rows]}
result['temporary_token_revoked']=True
print(json.dumps(result,sort_keys=True))

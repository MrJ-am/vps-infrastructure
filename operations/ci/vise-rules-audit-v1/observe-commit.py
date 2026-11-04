"""Fixed read-only diagnostic: selected Git hashes, never message/user/body."""
import importlib.util,json,os,re,sys
sys.path.insert(0,'/nix/store/36q79ns8mlnqvs2nfizyvr24nl75igsq-mrjam-vise-rules-audit-publisher-1/libexec')
import core,lease,proposal_entry as E,publish
from pathlib import Path
assert len(sys.argv)==1 and os.geteuid()==0 and os.uname().nodename=='srv1982677'
spec=importlib.util.spec_from_file_location('qualified_bootstrap',E.BOOTSTRAP)
bootstrap=importlib.util.module_from_spec(spec);spec.loader.exec_module(bootstrap)
binding=core.Binding(Path(E.BINDING).read_bytes(),E.BINDING_SHA256)
def sha(value):
    return value if type(value) is str and re.fullmatch('[0-9a-f]{40}',value) else None
with lease.repository_lease(bootstrap) as token:
    api=publish.Transport(token,binding)
    row=api.request('GET',publish.COMMIT)
    result={'sha':sha(row.get('sha')),
        'top_tree':sha(row.get('tree',{}).get('sha')),
        'commit_tree':sha(row.get('commit',{}).get('tree',{}).get('sha')),
        'parents':[sha(p.get('sha')) for p in row.get('parents',[])]}
result['temporary_token_revoked']=True
print(json.dumps(result,sort_keys=True))

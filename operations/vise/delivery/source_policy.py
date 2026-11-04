"""Independent ViSe source policy; no compilation, signing or production IO.

Compatible with the protected proposal preparer's policy interface, while
deliberately rejecting the monolith policy instead of inventing its checks.
"""
import hashlib,importlib.util,json,os,re,stat
from pathlib import Path,PurePosixPath
import source_scope as S

HEX40=re.compile(r'[0-9a-f]{40}\Z')
HEX64=re.compile(r'[0-9a-f]{64}\Z')
ROOT='sources/vise'
TREE='trees/vise.json'
MANIFESTS={'components/vise/backend/Cargo.toml','components/vise/backend/Cargo.lock'}
LIMIT=32*1024**2
OUT_OF_SCOPE=['platform: unchanged releases are not requalified by the ViSe pipeline']

class Refused(Exception):pass

def require(value,code):
    if not value:raise Refused(code)

def exact(value,fields):
    require(type(value) is dict and set(value)==set(fields),'VISE_POLICY_FIELDS_REFUSED')

def relative(value):
    require(type(value) is str and 0<len(value)<=4096 and '\\' not in value and '\0' not in value
        and all(p not in {'','.','..'} for p in value.split('/')),'VISE_SOURCE_PATH_REFUSED')
    return value

def read(path,maximum=LIMIT):
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    with os.fdopen(fd,'rb') as f:
        before=os.fstat(f.fileno())
        require(stat.S_ISREG(before.st_mode) and before.st_nlink==1 and before.st_size<=maximum,'VISE_SOURCE_FILE_REFUSED')
        raw=f.read(maximum+1);after=os.fstat(f.fileno())
        require(len(raw)==before.st_size and (before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns,before.st_ctime_ns)
            ==(after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns,after.st_ctime_ns),'VISE_SOURCE_CHANGED')
        return raw

def pairs(items):
    value={}
    for key,item in items:
        require(key not in value,'VISE_DUPLICATE_JSON_KEY');value[key]=item
    return value

def read_json(path):return json.loads(read(path),object_pairs_hook=pairs)
def sha(path):return hashlib.sha256(read(path)).hexdigest()

def checked_policy(value):
    exact(value,{'schema_version','status','profile','rules_revision','sources','frontends','rust_manifests','out_of_scope'})
    require(type(value['schema_version']) is int and value['schema_version']==2
        and value['status']=='proposed-not-independently-adopted' and value['profile']=='vise-v1','VISE_POLICY_PROFILE_REFUSED')
    require(type(value['rules_revision']) is str and HEX40.fullmatch(value['rules_revision']),'VISE_RULES_REVISION_REFUSED')
    require(type(value['sources']) is list and len(value['sources'])==1,'VISE_SOURCE_SET_REFUSED')
    s=value['sources'][0];exact(s,{'id','repository','revision','tree_sha','root','tree_json'})
    require(s['id']=='vise' and s['repository']=='MrJ-am/etp-vie-affective'
        and s['root']==ROOT and s['tree_json']==TREE,'VISE_SOURCE_IDENTITY_REFUSED')
    require(all(type(s[k]) is str and HEX40.fullmatch(s[k]) for k in ['revision','tree_sha']),'VISE_SOURCE_REVISION_REFUSED')
    require(value['frontends']==[] and value['out_of_scope']==OUT_OF_SCOPE,'VISE_POLICY_SCOPE_REFUSED')
    m=value['rust_manifests'];require(type(m) is dict and set(m)==MANIFESTS
        and all(type(v) is str and HEX64.fullmatch(v) for v in m.values()),'VISE_RUST_MANIFEST_REFUSED')
    return value

def source_selector(identifier,policy,previous,active_configuration):
    checked_policy(policy);require(identifier=='vise','VISE_SOURCE_IDENTITY_REFUSED')
    return lambda name: S.selected(name) or active_configuration(name)

def verify_sources(input_root,policy,gate_path):
    checked_policy(policy);root=Path(input_root)
    require(root.is_dir() and not root.is_symlink(),'VISE_SOURCE_ROOT_REFUSED')
    # Check every directory before opening descendants: O_NOFOLLOW alone only
    # protects the final component of an individual file path.
    actual=set();entry_count=0
    for directory,dirs,files in os.walk(root,followlinks=False):
        entry_count+=len(dirs)+len(files)
        require(entry_count<=16384 and len(Path(directory).relative_to(root).parts)<=64,'VISE_SOURCE_COUNT_REFUSED')
        for name in dirs:
            require(stat.S_ISDIR((Path(directory)/name).lstat().st_mode),'VISE_SOURCE_DIRECTORY_REFUSED')
        for name in files:actual.add(str((Path(directory)/name).relative_to(root)))
        require(len(actual)<=4097,'VISE_SOURCE_COUNT_REFUSED')
    manifest=read_json(root/'manifest.json');exact(manifest,{'schema_version','rules_revision','files'})
    require(type(manifest['schema_version']) is int and manifest['schema_version']==1
        and manifest['rules_revision']==policy['rules_revision'],'VISE_INPUT_RULES_REFUSED')
    require(type(manifest['files']) is list and 0<len(manifest['files'])<=4096,'VISE_SOURCE_COUNT_REFUSED')
    names=set();total=0
    for entry in manifest['files']:
        exact(entry,{'path','bytes','sha256'});name=relative(entry['path'])
        require(name not in names and name!='manifest.json','VISE_DUPLICATE_SOURCE')
        require(type(entry['bytes']) is int and 0<=entry['bytes']<=LIMIT
            and type(entry['sha256']) is str and HEX64.fullmatch(entry['sha256']),'VISE_SOURCE_METADATA_REFUSED')
        total+=entry['bytes'];require(total<=LIMIT,'VISE_SOURCE_BYTES_REFUSED')
        raw=read(root/name);require(len(raw)==entry['bytes'] and hashlib.sha256(raw).hexdigest()==entry['sha256'],'VISE_SOURCE_CONTENT_REFUSED')
        names.add(name)
    require(actual==names|{'manifest.json'},'VISE_UNDECLARED_INPUT')
    spec=importlib.util.spec_from_file_location('vise_protected_tree_gate',gate_path)
    gate=importlib.util.module_from_spec(spec);spec.loader.exec_module(gate)
    source=policy['sources'][0]
    entries=gate.validate_complete_tree(read_json(root/TREE),source['tree_sha'])
    blobs={e['path']:e for e in entries if e['type']=='blob'}
    require({name for name in blobs if PurePosixPath(name).name in {'Cargo.toml','Cargo.lock'}}
        =={'backend/Cargo.toml','backend/Cargo.lock'},'VISE_RUST_GRAPH_CHANGED')
    selected={name for name in blobs if S.selected(name) or gate.active_configuration(name)}
    expected={ROOT+'/'+name for name in selected}|{TREE,'source-bindings.json'}
    require(names==expected and S.EXACT<=selected,'VISE_SOURCE_SCOPE_INCOMPLETE')
    for name in selected:
        require(gate.git_blob(read(root/ROOT/name))==blobs[name]['sha'],'VISE_SOURCE_BLOB_MISMATCH')
    gate.inspect(entries,root/ROOT,{})
    identities=read_json(root/'source-bindings.json')
    exact(identities,{'schema_version','rules_revision','sources'})
    require(type(identities['schema_version']) is int,'VISE_SOURCE_BINDINGS_REFUSED')
    require(identities=={'schema_version':1,'rules_revision':policy['rules_revision'],
        'sources':[{k:source[k] for k in ['id','repository','revision','tree_sha']}]},'VISE_SOURCE_BINDINGS_REFUSED')
    for name,digest in policy['rust_manifests'].items():
        require(sha(root/ROOT/PurePosixPath(*PurePosixPath(name).parts[2:]))==digest,'VISE_RUST_MANIFEST_REFUSED')
    return {'vise':source},sha(root/'manifest.json')

"""Compose exact Git source changes under a controller-owned validation policy.

No checkout, candidate code, network, admission publication or deployment.
The caller supplies trusted base paths, source identities and object readers.
"""
import copy,hashlib,json,os,posixpath,shutil,stat
from pathlib import Path,PurePosixPath
import source_snapshot as S

def encode(value):return (json.dumps(value,sort_keys=True,indent=2)+'\n').encode()
def sha(raw):return hashlib.sha256(raw).hexdigest()

def selector(identifier,policy,previous,active_configuration):
    prefixes=set();exact=set(previous)
    for frontend in policy['frontends']:
        for asset in frontend['assets']:
            if asset['source']==identifier:exact.add(asset['path'])
        if frontend['source']==identifier:
            base=frontend['directory'];exact.add(posixpath.normpath(base+'/elm.json'))
            prefixes.add(posixpath.normpath(base+'/tests')+'/')
            for directory in frontend['source_directories']:
                if directory.startswith(('.dependances/','.style-mrjam/','.cache/')):continue
                prefixes.add(posixpath.normpath(base+'/'+directory)+'/')
        if frontend['style_source']==identifier:prefixes.add(frontend['style_directory']+'/')
    def selected(name):
        file=PurePosixPath(name)
        return (name in exact or active_configuration(name)
            or file.name in {'Cargo.toml','Cargo.lock','.gitmodules'}
            or (identifier in {'platform','mateval','vision','infrastructure'} and file.suffix in {'.rs','.sql'})
            or (file.suffix=='.elm' and any(name.startswith(p) for p in prefixes))
            or (identifier=='logique' and ((name.startswith('tests/') and file.name.startswith('test_') and name.endswith('.py'))
                or name in {'tests/contrats-reference.json','.openai/hosting.json'})))
    return selected

def base_files(root,digest,policy):
    root=Path(root);raw=(root/'manifest.json').read_bytes()
    S.require(sha(raw)==digest,'BASE_MANIFEST_REFUSED')
    manifest=policy.read_json(root/'manifest.json')
    policy.exact(manifest,('schema_version','rules_revision','files'))
    S.require(type(manifest['files']) is list and 0<len(manifest['files'])<=4096,'SOURCE_FILE_LIMIT')
    files={};total=0
    for entry in manifest['files']:
        policy.exact(entry,('path','bytes','sha256'));name=policy.relative(entry['path'])
        S.require(name not in files and name!='manifest.json','DUPLICATE_SOURCE')
        path=root/name;info=path.lstat()
        S.require(stat.S_ISREG(info.st_mode) and info.st_size==entry['bytes'] and info.st_size<=32*1024**2,'BASE_FILE_REFUSED')
        total+=info.st_size;S.require(total<=32*1024**2,'SOURCE_BYTES_LIMIT')
        data=path.read_bytes();S.require(sha(data)==entry['sha256'],'BASE_BYTES_REFUSED');files[name]=data
    return manifest,files

def prepare(base,base_digest,base_policy,updates,destination,*,validator_policy,gate,gate_path):
    P=validator_policy
    policy=copy.deepcopy(P.checked_policy(copy.deepcopy(base_policy)))
    manifest,files=base_files(base,base_digest,P)
    S.require(manifest['schema_version']==1 and manifest['rules_revision']==policy['rules_revision'],'BASE_RULES_REFUSED')
    sources={s['id']:s for s in policy['sources']}
    S.require(type(updates) is dict and updates and set(updates)<=set(sources),'SOURCE_UPDATE_SCOPE_REFUSED')
    for identifier,update in updates.items():
        S.require(type(update) is dict and set(update)=={'reader','base','head'},'SOURCE_UPDATE_FIELDS_REFUSED')
        source=sources[identifier];prefix=source['root']+'/'
        # main may have advanced since the last application release. Receive
        # the entire new tree, but only along the adopted source's ancestry.
        if update['base']!=source['revision']:
            S.ancestry(update['reader'],source['revision'],update['base'])
        previous={name[len(prefix):] for name in files if name.startswith(prefix)}
        select=getattr(P,'source_selector',selector)
        tree,blobs=S.snapshot(update['reader'],update['base'],update['head'],select(identifier,policy,previous,gate.active_configuration))
        gate.validate_complete_tree(tree,tree['sha'])
        files={name:data for name,data in files.items() if not name.startswith(prefix)}
        files.update({prefix+name:data for name,data in blobs.items()})
        files[source['tree_json']]=encode(tree)
        source.update(revision=update['head'],tree_sha=tree['sha'])
    for name in policy['rust_manifests']:
        parts=PurePosixPath(name).parts
        path=(sources[parts[1]]['root']+'/'+str(PurePosixPath(*parts[2:]))) if parts[0]=='components' else sources['platform']['root']+'/'+name
        S.require(path in files,'RUST_MANIFEST_ABSENT');policy['rust_manifests'][name]=sha(files[path])
    P.checked_policy(policy)
    # A commit with the same tree is still a distinct observed proposal.
    # Bind source identities inside the digest, not only in external policy.
    files['source-bindings.json']=encode({'schema_version':1,'rules_revision':policy['rules_revision'],
        'sources':[{k:source[k] for k in ('id','repository','revision','tree_sha')} for source in policy['sources']]})
    S.require(0<len(files)<=4096 and sum(map(len,files.values()))<=32*1024**2,'PROPOSAL_LIMIT')
    names=set(files)
    S.require(not any(str(parent) in names for name in names for parent in PurePosixPath(name).parents if str(parent)!='.'),'SOURCE_PATH_COLLISION')
    destination=Path(destination)
    S.require(destination.is_absolute() and destination.parent.resolve()==destination.parent,'DESTINATION_REFUSED')
    parent=destination.parent.stat()
    S.require(parent.st_uid==os.getuid() and stat.S_IMODE(parent.st_mode)==0o700,'DESTINATION_PARENT_REFUSED')
    destination.mkdir(mode=0o700)  # Never overwrite an existing result.
    try:
        for name,data in sorted(files.items()):
            P.relative(name);path=destination/name;path.parent.mkdir(parents=True,exist_ok=True)
            with path.open('xb') as output:output.write(data)
        result={'schema_version':1,'rules_revision':policy['rules_revision'],'files':[
            {'path':name,'bytes':len(data),'sha256':sha(data)} for name,data in sorted(files.items())]}
        raw=encode(result);(destination/'manifest.json').write_bytes(raw)
        # The very same independent source gate used by the live validator
        # checks complete trees, gitlinks, workspace membership and all bytes.
        P.verify_sources(destination,policy,gate_path)
        return {'policy':policy,'proposal_sha256':sha(raw),'files':len(files),'deployment_authorized':False}
    except BaseException:
        shutil.rmtree(destination)
        raise

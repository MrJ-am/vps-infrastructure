"""Measure new public artifact bytes against the separately qualified baseline."""
import hashlib,json,stat,tarfile
from pathlib import Path,PurePosixPath
ROOT=Path(__file__).resolve().parents[3]
HERE=ROOT/'operations/ci/current-validator-v1'
RUN=ROOT/'.local/ci-current-validator-v1-20261103/native-validation-001'
def sha(raw):return hashlib.sha256(raw).hexdigest()
def require(value):
    if not value:raise ValueError('PUBLIC_ARTIFACT_COMPARISON_REFUSED')
def main():
    result=json.loads((RUN/'result.json').read_bytes());require(result['status']=='passed' and result['required_steps_passed']==75)
    chosen=json.loads((HERE/'source-choice-20261103.json').read_bytes())['current_artifact_baseline']
    configured=json.loads((ROOT/'operations/hosts/mrjam-vps/application-artifacts.json').read_bytes())['outputs']
    require(all(configured[name]==value for name,value in chosen.items()))
    for entry in result['artifacts']:
        path=RUN/'artifacts'/entry['name'];require(path.stat().st_size==entry['bytes'] and sha(path.read_bytes())==entry['sha256'])
    server=chosen['server'];server_root=Path(server['store_path'])
    require(sha((server_root/'artifact.json').read_bytes())==server['manifest_sha256'])
    old_server=sha((server_root/'bin/mrjam-server').read_bytes());require(old_server==server['executable_sha256']['bin/mrjam-server'])
    new_server=sha((RUN/'artifacts/server').read_bytes())
    names={'audition':'frontend_audition','log':'frontend_log','logique':'frontend_logique','style-logo':'frontend_logo','mateval':'frontend_mateval','style':'frontend_style','vision':'frontend_vision'}
    inventories={name:{} for name in names};documents={};total=0
    with tarfile.open(RUN/'artifacts/frontend.tar',mode='r:') as archive:
        members=archive.getmembers();require(len(members)<=16384)
        for member in members:
            path=PurePosixPath(member.name)
            require(member.isfile() and str(path)==member.name and not path.is_absolute() and '..' not in path.parts and len(path.parts)>1 and path.parts[0] in names and member.mode==0o444 and member.mtime==0 and 0<=member.size<=64*1024*1024)
            total+=member.size;require(total<=64*1024*1024)
            name=path.parts[0];relative=str(PurePosixPath(*path.parts[1:]));require(relative not in inventories[name])
            data=archive.extractfile(member).read(member.size+1);require(len(data)==member.size)
            inventories[name][relative]=sha(data)
            if relative=='artifact.json':documents[name]=json.loads(data)
    comparison={}
    for name,key in names.items():
        root=Path(chosen[key]['store_path']);old={}
        for path in root.rglob('*'):
            metadata=path.lstat();require(stat.S_ISREG(metadata.st_mode) or stat.S_ISDIR(metadata.st_mode))
            if path.is_file():old[str(path.relative_to(root))]=sha(path.read_bytes())
        require(old['artifact.json']==chosen[key]['manifest_sha256'])
        new=inventories[name];require(name in documents)
        declared=documents[name];require(declared['payload_sha256']=={path:digest for path,digest in new.items() if path!='artifact.json'} and declared['deployment_authorized'] is False)
        require(declared['input_manifest_sha256']==result['proposal_sha256'])
        changed=sorted(path for path in old.keys()|new.keys() if old.get(path)!=new.get(path))
        metadata_old=json.loads((root/'artifact.json').read_bytes())
        fields=sorted(field for field in metadata_old.keys()|declared.keys() if metadata_old.get(field)!=declared.get(field))
        comparison[name]={'baseline_store_path':str(root),'old_files':len(old),'new_files':len(new),'same_file_set':set(old)==set(new),'all_files_byte_identical':old==new,'payload_files_byte_identical':{p:h for p,h in old.items() if p!='artifact.json'}=={p:h for p,h in new.items() if p!='artifact.json'},'changed_public_paths':changed,'artifact_metadata_fields_changed':fields,'new_artifact_manifest_sha256':new['artifact.json']}
    value={'schema_version':1,'scope':'measured-public-artifact-bytes-only','proposal_sha256':result['proposal_sha256'],'server':{'baseline_store_path':str(server_root),'baseline_sha256':old_server,'new_sha256':new_server,'byte_identical':old_server==new_server},'frontends':comparison,'production_access':False,'deployment_authorized':False,'limits':['Unequal executable bytes do not prove semantic equivalence or a defect; provenance and executed tests are reported separately.','This comparison does not connect the release manifest, reviews or deployment executor to the new artifacts.']}
    (RUN/'comparison.json').write_text(json.dumps(value,sort_keys=True,indent=2)+'\n')
    print(json.dumps({'server_byte_identical':value['server']['byte_identical'],'frontends_payload_byte_identical':{name:entry['payload_files_byte_identical'] for name,entry in comparison.items()}},sort_keys=True))
if __name__=='__main__':main()

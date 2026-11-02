"""Invented VM only. No fixture entry or broad API is shipped to production."""
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

PACKAGE=Path(os.environ["SYNTHETIC_GOVERNANCE_PACKAGE"])
SEED=Path(os.environ["SYNTHETIC_GOVERNANCE_SEED"])
BINDING=Path(os.environ["SYNTHETIC_GOVERNANCE_BINDING"])
sys.path.insert(0,str(PACKAGE/"libexec"))
import core
import credentials
spec=importlib.util.spec_from_file_location("bootstrap_fixture","/etc/forgejo-bootstrap-fixture.py")
fixture=importlib.util.module_from_spec(spec);spec.loader.exec_module(fixture)
bootstrap=fixture.core
binding=core.Binding(BINDING.read_bytes(),hashlib.sha256(BINDING.read_bytes()).hexdigest())
seed_refs={line.split(' ',1)[1]:line.split(' ',1)[0] for line in (SEED/'refs').read_text().splitlines()}
git=core.Git("/run/current-system/sw/bin/git",str(PACKAGE/"bin/mrjam-forgejo-git-credential"))
PROOF=fixture.ROOT


def require(value,code):
    if not value:raise RuntimeError(code)


def invoke(operation,success=True):
    result=subprocess.run([str(PACKAGE/"bin"/operation)],stdin=subprocess.DEVNULL,
                          stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=240)
    value=json.loads(result.stdout)
    if success:
        if value.get("code")=="SOURCE_IMPORT_REQUIRED":
            with bootstrap.governance_lease() as token:
                observation=core.reconcile.observe(core.reconcile.Transport(token),binding.policy("protect-main"))
                print(json.dumps({name:{"empty":row["empty"],"exists":True} if row else {"exists":False}
                                  for name,row in observation["repositories"].items()},sort_keys=True))
        require(result.returncode==0,"ENTRY_"+str(value.get("code","UNEXPECTED")))
    else:
        require(result.returncode!=0,"EXPECTED_REFUSAL_MISSING")
        require(set(value)=={"schema_version","code"} and re.fullmatch(r"[A-Z_]+",value["code"]),"NON_CLOSED_DIAGNOSTIC")
    require(result.stderr==b"","ENTRY_PRIVATE_DIAGNOSTIC")
    return value


def no_token():
    require(fixture.sql("SELECT count(*) FROM access_token")=="0","TOKEN_RETAINED")
    require(not credentials.SOCKET.exists(),"CREDENTIAL_SOCKET_RETAINED")


def prepare():
    core.STAGING.mkdir(mode=0o700)
    for name in core.NAMES:
        path=core.STAGING/(name+".bundle")
        shutil.copyfile(SEED/"source.bundle",path);path.chmod(0o600)
    value=invoke("mrjam-first-release-sources-probe")
    require(value=={"schema_version":1,"binding_sha256":binding.digest,"source_inputs_verified":True},"SOURCE_PROBE_SHAPE")
    no_token()


def absent_phase():
    invoke("mrjam-first-release-governance",False)
    no_token()
    require(fixture.personal()==(PROOF/"personal-before").read_text(),"PERSONAL_IDENTITY_CHANGED")


def seed_existing():
    with bootstrap.governance_lease() as token:
        require(fixture.api(token,"POST","/api/v1/orgs",{"username":"MrJ-am","visibility":"private"})[0]==201,"ORG_CREATE")
        require(fixture.api(token,"POST","/api/v1/orgs/MrJ-am/repos",
            {"name":"synthetic-unrelated","private":True,"auto_init":True,"default_branch":"main"})[0]==201,"SENTINEL_CREATE")
        require(fixture.api(token,"POST","/api/v1/orgs/MrJ-am/repos",
            {"name":"vision","private":True,"auto_init":False,"default_branch":"main"})[0]==201,"EXISTING_CREATE")
        source=copy.deepcopy(binding.repositories["vision"])
        source["main"]=(SEED/"first").read_text().strip()
        git.adopt("vision",source,token)
        with credentials.broker(token,"vision"):
            refs=git.remote_refs("vision")
        (PROOF/"existing-refs.json").write_text(json.dumps(refs))
        status,sentinel=fixture.api(token,"GET","/api/v1/repos/MrJ-am/synthetic-unrelated")
        require(status==200,"SENTINEL_READ")
        (PROOF/"sentinel.json").write_text(json.dumps({key:sentinel[key] for key in ("id","private","empty")}))
    no_token()


def adopt():
    parent=Path("/var/lib/mrjam-cutover");parent.mkdir(mode=0o700)
    state=parent/"first-deployment";state.mkdir(mode=0o700)
    phase=state/"phase.json";phase.write_text('{"schema_version":1,"phase":"state-adopted","elapsed_seconds":1}\n');phase.chmod(0o600)
    expected={"schema_version":1,"binding_sha256":binding.digest,"sources_bound":True,
              "protected_policy_verified":True,"temporary_credentials_revoked":True}
    require(invoke("mrjam-first-release-governance")==expected,"ADOPTION_ATTESTATION")
    verify()


def verify():
    with bootstrap.governance_lease() as token:
        api=core.reconcile.Transport(token)
        observed=core.reconcile.observe(api,binding.policy("protect-main"))
        require(all(row["private"] and not row["empty"] and not row["actions_enabled"]
                    and row["protection"]==core.reconcile.desired_protection()
                    for row in observed["repositories"].values()),"POLICY_READBACK")
        for name in core.NAMES:
            with credentials.broker(token,name):refs=git.remote_refs(name)
            require(all(refs.get(ref)==oid for ref,oid in core.target_refs(binding.repositories[name],seed_refs).items()),"SOURCE_READBACK")
        old=json.loads((PROOF/"existing-refs.json").read_text())
        with credentials.broker(token,"vision"):refs=git.remote_refs("vision")
        require(all(ref=="refs/heads/main" or refs.get(ref)==oid for ref,oid in old.items()),"EXISTING_HISTORY_LOST")
        status,sentinel=fixture.api(token,"GET","/api/v1/repos/MrJ-am/synthetic-unrelated")
        require(status==200 and {key:sentinel[key] for key in ("id","private","empty")}==json.loads((PROOF/"sentinel.json").read_text()),"SENTINEL_CHANGED")
    no_token()
    require(fixture.personal()==(PROOF/"personal-before").read_text(),"PERSONAL_IDENTITY_CHANGED")


def replay():
    value=invoke("mrjam-first-release-governance")
    require(value["binding_sha256"]==binding.digest and value["sources_bound"] is True,"REPLAY_FAILED")
    verify()


def protected_refusal():
    with bootstrap.governance_lease() as token:
        source=copy.deepcopy(binding.repositories["vision"]);source["main"]=(SEED/"future").read_text().strip()
        try:
            git.adopt("vision",source,token)
        except core.Refused as error:
            require(str(error)=="GIT_OPERATION_REFUSED","PROTECTION_NOT_EXERCISED")
        else:
            raise RuntimeError("PROTECTED_MAIN_ACCEPTED_ADMIN_PUSH")
        with credentials.broker(token,"vision"):
            require(git.remote_refs("vision")["refs/heads/main"]==binding.repositories["vision"]["main"],"MAIN_CHANGED")
    no_token()


def private_source_target():
    predicate="lower_name='vision' AND owner_id=(SELECT id FROM public.\"user\" WHERE lower_name='mrj-am')"
    fixture.sql("UPDATE public.repository SET is_private=false WHERE "+predicate)
    try:
        require(fixture.sql("SELECT is_private FROM public.repository WHERE "+predicate)=="f","PUBLIC_FIXTURE_TARGET")
        value=invoke("mrjam-first-release-governance",False)
        require(value["code"]=="PRIVATE_SOURCE_PUBLIC_TARGET_REFUSED","PRIVATE_SOURCE_NOT_CONTAINED")
        no_token()
    finally:
        fixture.sql("UPDATE public.repository SET is_private=true WHERE "+predicate)
    verify()


def tamper():
    path=core.STAGING/"vision.bundle"
    with path.open("ab") as stream:stream.write(b"invented tampering")
    value=invoke("mrjam-first-release-sources-probe",False)
    require(value["code"]=="BUNDLE_HASH_REFUSED","WRONG_SOURCE_REFUSAL")
    no_token()


ACTIONS={"prepare":prepare,"absent-phase":absent_phase,"seed-existing":seed_existing,"adopt":adopt,
         "replay":replay,"protected-refusal":protected_refusal,"private-target":private_source_target,"tamper":tamper}
if __name__=="__main__":
    try:
        require(len(sys.argv)==2 and sys.argv[1] in ACTIONS,"FIXTURE_SCOPE")
        ACTIONS[sys.argv[1]]()
    except Exception as error:
        code=str(error) if isinstance(error,RuntimeError) and re.fullmatch(r"[A-Z_]+",str(error)) else type(error).__name__
        print("SYNTHETIC_GOVERNANCE_FAILED:"+code,file=sys.stderr)
        raise SystemExit(1)

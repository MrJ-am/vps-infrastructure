"""Bounded qualification only: build content, never activate or accept a source."""
import hashlib,json,os,re,subprocess,sys
from pathlib import Path
RECIPE=Path(os.environ['MRJAM_QUALIFICATION_RECIPE'])
sys.path[:0]=[str(RECIPE/'operations/ci/continuous-delivery-v1'),
 '/nix/store/qmzbv6zskr9qzhh3ifqs010jz26q2jlh-mrjam-protected-admission-controller-1/lib',
 '/nix/store/ixhqrvgq1vixg0g0fc01lwkdprxxkmn7-mrjam-validation-admission-control-1/lib']
import generation_builder as B
OLD='/nix/store/y9ddjv4pfncss1gjnd4msfywfxr7s8b4-nixos-system-srv1982677-26.05pre-git'
CANDIDATE='/nix/store/0l3mivhq0j2sz7jrsbrrw4q30kb8pkww-mrjam-delivery-candidate-e06f030310ae-green'
EXPECTED_STAGE='/nix/store/27i5lsmml42p1xzc9nm81iakxyafr3b7-nixos-system-srv1982677-26.05pre-git'
EXPECTED_NEW='/nix/store/913dgifa3fn11b6cmdk0jpa4r60y2q6z-nixos-system-srv1982677-26.05pre-git'
NIX='/nix/store/i4bv0lvk0gfzllcy2kqgz3iam0aw4c4i-nix-2.34.8/bin/'
CTL='/nix/store/0xiinbh7pbj479i5v28mqnjrvhvbdibf-systemd-260.2/bin/systemctl'
UNITS=['nginx','postgresql','forgejo','mrjam-rust-blue','mrjam-rust-green','mrjam-forgejo-runner']
def observe():return os.path.realpath('/run/current-system')
def retained():
    result={}
    for unit in UNITS:
        p=subprocess.run([CTL,'show',unit+'.service','-p','MainPID','-p','ActiveState','-p','SubState'],capture_output=True,text=True)
        B.require(p.returncode==0 and len(p.stdout)<1024,'QUALIFICATION_UNIT_READ_REFUSED');result[unit]=p.stdout
    return result

def main():
    import fcntl
    B.require(os.getuid()==0 and os.uname().nodename=='srv1982677' and len(sys.argv)==1,'QUALIFICATION_HOST_REFUSED')
    with open('/var/lib/mrjam-cutover/first-deployment/transaction.lock','rb') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        B.require(observe()==OLD and os.path.realpath('/nix/var/nix/profiles/system')==OLD,'QUALIFICATION_BASE_CHANGED')
        work=B.O.W.private_directory(Path(os.environ['STATE_DIRECTORY']))
        routes=Path('/etc/nginx/nginx.conf').read_bytes()
        B.require(routes.count(b'127.0.0.1:38101')==11 and b'127.0.0.1:38102' not in routes,'QUALIFICATION_ROUTING_CHANGED')
        slots={}
        for slot in ('blue','green'):
            text=Path('/etc/systemd/system/mrjam-rust-'+slot+'.service').read_text()
            match=re.findall(r'^ExecStart=(/nix/store/[^\s]+)/bin/mrjam-server serve --config (/nix/store/[^\s]+)/runtime.json$',text,re.M)
            B.require(len(match)==1 and all(B.G.store(p) for p in match[0]),'QUALIFICATION_SLOT_REFUSED')
            slots[slot]=dict(zip(('server','runtime'),match[0]))
        state={'schema_version':1,'system':OLD,'active_slot':'blue','adopted':os.path.realpath('/etc/mrjam-delivery-adopted.json'),'slots':slots}
        before=retained()
        # systemd inspection is read-only. No call to start, stop, switch or boot.
        builder=B.Builder(RECIPE/'operations/ci/continuous-delivery-v1/delivery-generations.nix',NIX+'nix-instantiate',NIX+'nix-build')
        execute=builder.execute
        def progress(args):
            result=execute(args);print(json.dumps({'attribute':args[args.index('-A')+1],'completed':True}),flush=True);return result
        builder.execute=progress
        proof=builder.construct(work,state,CANDIDATE,observe=observe)
        B.require(proof['staged']==EXPECTED_STAGE and proof['promoted']==EXPECTED_NEW,'QUALIFICATION_GENERATIONS_CHANGED')
        B.require(retained()==before and Path('/etc/nginx/nginx.conf').read_bytes()==routes
            and observe()==OLD and os.path.realpath('/nix/var/nix/profiles/system')==OLD,'QUALIFICATION_PRODUCTION_CHANGED')
        proof.update(scope='VPS-content-construction-only',activated=False,retained_processes_unchanged=True,
            current_and_boot_unchanged=True,recipe=str(RECIPE))
        B.O.save(work/'qualification.json',proof)
        print(json.dumps({'code':'VPS_GENERATION_BUILDER_QUALIFIED','activated':False,'all_checks':all(proof['checks'].values())}),flush=True)
if __name__=='__main__':
    try:main()
    except Exception as error:
        code=str(error) if type(error).__name__=='Refused' and re.fullmatch('[A-Z_]{1,80}',str(error)) else 'VPS_BUILDER_QUALIFICATION_REFUSED'
        print(json.dumps({'code':code,'type':type(error).__name__}),flush=True);raise SystemExit(2) from None

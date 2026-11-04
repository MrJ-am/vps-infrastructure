"""ViSe compiler/frontend stage inside the protected worker's outer sandbox.

No attestation or successful full-validation report is produced by this stage.
The future full verifier must execute API, SQL and recovery checks afterwards.
"""
import hashlib,json,os,shutil,socket,stat,subprocess
from pathlib import Path
import source_policy as P,dependency_binding as D
import sandbox

def writable_tree(path):
    for p in [path,*path.rglob('*')]:
        if not p.is_symlink():p.chmod(p.stat().st_mode|0o600|(0o100 if p.is_dir() else 0))

def snapshot_server(job,destination):
    # Cargo hardlinks target/release to target/release/deps. Candidate processes
    # have exited; copy bounded bytes to the supervisor's private directory.
    for directory in [job/'target',job/'target/release']:
        P.require(stat.S_ISDIR(directory.lstat().st_mode),'VISE_SERVER_ARTIFACT_REFUSED')
    fd=os.open(job/'target/release/etp-carnet-server',os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    with os.fdopen(fd,'rb') as stream:
        before=os.fstat(stream.fileno())
        P.require(stat.S_ISREG(before.st_mode) and 0<before.st_size<=64*1024**2,'VISE_SERVER_ARTIFACT_REFUSED')
        raw=stream.read(64*1024**2+1);after=os.fstat(stream.fileno())
        fields=('st_dev','st_ino','st_size','st_mtime_ns','st_ctime_ns','st_nlink','st_mode')
        P.require(len(raw)==before.st_size and all(getattr(before,k)==getattr(after,k) for k in fields)
            and raw[:4]==b'\x7fELF','VISE_SERVER_ARTIFACT_REFUSED')
    destination.write_bytes(raw);destination.chmod(0o500)
    return raw

class Build:
    def __init__(self,runtime):
        P.require(os.getuid()!=0 and Path.cwd()==Path('/work'),'VISE_WORKER_REQUIRED')
        P.require([name for _,name in socket.if_nameindex()]==['lo'],'VISE_ISOLATED_NETWORK_REQUIRED')
        P.require(os.statvfs('/input').f_flag&os.ST_RDONLY,'VISE_READONLY_SOURCE_REQUIRED')
        sandbox.protect_supervisor()
        self.runtime=runtime;self.tools=runtime['tools'];self.steps=[]
        self.private=Path('/work/verifier-private');self.private.mkdir(mode=0o700)
        self.job=Path('/work/vise-job');self.job.mkdir(mode=0o700)
        (self.job/'home').mkdir(mode=0o700)
        self.passwd=self.private/'passwd'
        self.passwd.write_text(f"vise-validator:x:{os.getuid()}:{os.getgid()}:Synthetic validation:/job/home:/bin/sh\n")
        self.env={'HOME':'/job/home','PATH':runtime['path'],'LANG':'C.UTF-8','TMPDIR':'/tmp',
            'RUSTC':self.tools['rustc'],'RUSTDOC':self.tools['rustdoc'],'CC':self.tools['cc'],
            'AR':self.tools['ar'],'CARGO_BUILD_JOBS':'1','CARGO_INCREMENTAL':'0',
            'CARGO_NET_OFFLINE':'true','GHCRTS':'-N2',
            'NODE_OPTIONS':'--require='+runtime['support']+'/cpu-limit.cjs'}

    def check(self,name,argv,*,env=None,readonly=(),cwd='/source'):
        args=sandbox.command(self.tools['bwrap'],{'shell':self.tools['shell']},self.source,
            self.job,self.passwd,argv,{**self.env,**(env or {})},readonly=readonly,cwd=cwd)
        P.require(sandbox.run(args,timeout=1200)==0,'VISE_CHECK_FAILED_'+name.upper().replace('-','_'))
        self.steps.append({'name':name,'status':'passed'})

    def run(self):
        self.policy=P.checked_policy(P.read_json(Path(self.runtime['policy'])))
        sources,self.proposal=P.verify_sources(Path('/input'),self.policy,Path(self.runtime['tree_gate']))
        self.source=Path('/input')/sources['vise']['root']
        self.steps.append({'name':'complete-vise-source-tree','status':'passed'})
        for name,version in [('rustc','1.99.1'),('cargo','1.99.1'),('node','v24.19.0'),('elm','0.19.1')]:
            raw=subprocess.check_output([self.tools[name],'--version'],timeout=10,stderr=subprocess.DEVNULL,
                env={'PATH':self.runtime['path'],'HOME':str(self.private),'LANG':'C.UTF-8'})
            P.require(len(raw)<=4096 and (raw.decode().split()[1] if name in {'cargo','rustc'} else raw.decode().strip())==version,
                'VISE_TOOL_VERSION_REFUSED')
        self.steps.append({'name':'locked-toolchain-versions','status':'passed'})
        deps=Path(self.runtime['vise_dependencies']);D.verify(self.source,deps,isolated=True)
        self.steps.append({'name':'locked-cargo-npm-elm-dependencies','status':'passed'})
        P.require(not any(p.name=='.cargo' for p in self.source.rglob('*')),'VISE_CARGO_CONFIGURATION_REFUSED')
        (self.job/'cargo-home').mkdir(mode=0o700)
        config=self.private/'cargo-config.toml'
        config.write_text('[source.crates-io]\nreplace-with="vendored-sources"\n[source.vendored-sources]\ndirectory='+json.dumps(str(deps/'cargo-vendor'))+'\n[net]\noffline=true\n')
        self.check('rust-offline-release-build',[self.tools['cargo'],'build','--release','--frozen','--offline',
            '--manifest-path','backend/Cargo.toml'],env={'CARGO_HOME':'/job/cargo-home','CARGO_TARGET_DIR':'/job/target',
                'RUSTFLAGS':'--remap-path-prefix=/source=vise-source --remap-path-prefix=/job=vise-build --remap-path-prefix='+str(deps)+'=vise-dependencies'},
            readonly=[(config,'/job/cargo-home/config.toml')])
        self.server=self.private/'server';raw=snapshot_server(self.job,self.server)
        shutil.rmtree(self.job/'target')
        project=self.job/'project';shutil.copytree(self.source,project);writable_tree(project)
        shutil.copytree(deps/'node_modules',project/'node_modules',symlinks=True)
        (project/'node_modules/.bin').chmod(0o700)
        elm=project/'node_modules/.bin/elm';elm.unlink();elm.symlink_to(self.tools['elm'])
        shutil.copytree(deps/'elm-home',self.job/'elm-home',symlinks=True);writable_tree(self.job/'elm-home')
        env={'ELM_HOME':'/job/elm-home'}
        self.check('typescript-no-emit',[self.tools['node'],'node_modules/typescript/bin/tsc','--noEmit'],env=env,cwd='/job/project')
        self.check('vise-frontend-build',[self.tools['node'],'scripts/build.mjs'],env=env,cwd='/job/project')
        self.check('vise-component-tests',[self.tools['node'],'--import','tsx','--test','tests/crypto.test.ts',
            'tests/contenu.test.ts','tests/image.test.ts','tests/poll.test.ts'],env=env,cwd='/job/project')
        self.dist=project/'dist';P.require(self.dist.is_dir() and not self.dist.is_symlink(),'VISE_FRONTEND_ARTIFACT_REFUSED')
        count=total=0
        for p in self.dist.rglob('*'):
            info=p.lstat();P.require(stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode),'VISE_FRONTEND_ARTIFACT_REFUSED')
            count+=1;total+=info.st_size if stat.S_ISREG(info.st_mode) else 0
            P.require(count<=4096 and total<=64*1024**2,'VISE_FRONTEND_ARTIFACT_LIMIT')
        P.require((self.dist/'index.html').is_file(),'VISE_FRONTEND_ENTRYPOINT_REFUSED')
        return {'scope':'isolated-build-stage-only','proposal_sha256':self.proposal,
            'steps':self.steps,'server_sha256':hashlib.sha256(raw).hexdigest(),
            'full_validation_passed':False,'deployment_authorized':False}

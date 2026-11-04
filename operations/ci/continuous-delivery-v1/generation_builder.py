"""Sequential bounded-memory qualification and construction, without activation.

Caller holds the adoption lock and supplies an installed recipe and independently
verified candidate. The durable receipt binds exact inputs, views and results;
it is preparation evidence, never deployment authority.
"""
import json,os,subprocess
from pathlib import Path
import admission_orchestrator as O
import generation_views as G
from source_snapshot import require

class Builder:
    def __init__(self,recipe,nix_instantiate,nix_build,execute=None):
        self.recipe=Path(recipe)
        require(self.recipe.is_absolute() and self.recipe.name=='delivery-generations.nix','GENERATION_RECIPE_REFUSED')
        self.nix_instantiate=nix_instantiate;self.nix_build=nix_build
        require(all(type(p) is str and p.startswith('/nix/store/') for p in (nix_instantiate,nix_build)),
            'GENERATION_TOOL_REFUSED')
        self.execute=execute or self.command
    @staticmethod
    def command(args):
        p=subprocess.run(args,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
            timeout=900,env={'PATH':'/nonexistent','HOME':os.environ.get('STATE_DIRECTORY','/var/empty'),
                'NIX_REMOTE':'daemon','LANG':'C','LC_ALL':'C'})
        # Export a closed diagnosis only, never Nix's interpolated source text.
        if p.returncode and b'Read-only file system' in p.stderr:
            require(False,'GENERATION_STORE_READ_ONLY')
        if p.returncode and b'Permission denied' in p.stderr:
            require(False,'GENERATION_STORE_PERMISSION_REFUSED')
        require(p.returncode==0 and len(p.stdout)<=1048576,'GENERATION_COMMAND_REFUSED')
        return p.stdout
    def construct(self,work,state,candidate_path,*,observe):
        work=O.W.private_directory(work);G.state_checked(state)
        require(G.store(candidate_path),'GENERATION_CANDIDATE_PATH_REFUSED')
        require(observe()==state['system'],'GENERATION_LIVE_BASE_CHANGED')
        inputs={'schema_version':1,'state':state,'candidate':candidate_path,'recipe':str(self.recipe)}
        input_file=work/'inputs.json'
        if input_file.exists():
            require(O.W.read_file(input_file,65536)==O.encode(inputs),'GENERATION_INPUTS_CHANGED')
        else:O.save(input_file,inputs)
        candidate=json.loads((Path(candidate_path)/'descriptor.json').read_bytes())
        require(G.store(candidate['bundle']),'GENERATION_BUNDLE_PATH_REFUSED')
        bundle=json.loads((Path(candidate['bundle'])/'descriptor.json').read_bytes())
        state_file=work/'input-state.json';O.save(state_file,state);raw=O.W.read_file(state_file,65536)
        args=[str(self.recipe),'--argstr','stateFile',str(state_file),'--argstr','candidatePath',candidate_path]
        views={}
        for phase in ('current','stage','promotion'):
            # Fresh hosts must be able to register the fixed recipe's IFD
            # derivations, rather than relying on the developer's store cache.
            output=self.execute([self.nix_instantiate,'--eval','--read-write-mode','--strict','--json',*args,'-A','views.'+phase])
            require(len(output)<=65536,'GENERATION_VIEW_SIZE_REFUSED')
            views[phase]=json.loads(output)
            O.save(work/('view-'+phase+'.json'),views[phase])
        proof=G.verify(views,state,raw,candidate_path,candidate,bundle)
        require(observe()==state['system'],'GENERATION_LIVE_BASE_CHANGED')
        for phase,field in (('stage','staged'),('promotion','promoted')):
            output=self.execute([self.nix_build,*args,'-A','builds.'+phase,'--out-link',str(work/phase),
                '--option','builders','','--max-jobs','1','--cores','2'])
            require(output.decode('ascii').strip()==proof[field],'GENERATION_BUILD_RESULT_CHANGED')
        require(observe()==state['system'],'GENERATION_LIVE_BASE_CHANGED')
        proof.update(candidate=candidate_path,input_state_sha256=O.sha(raw),
            view_sha256={phase:O.sha(O.encode(v)) for phase,v in views.items()},built=True)
        O.save(work/'prepared.json',proof)
        return proof

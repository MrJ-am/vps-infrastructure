"""Sequential protected ViSe generation preparation; never service activation."""
import json
from pathlib import Path
import generation_builder as B
import host_views as V
import generation_layout as L

class Builder:
    def __init__(self,recipe,nix_instantiate,nix_build,*,execute=None,layout=None):
        self.recipe=Path(recipe)
        B.require(self.recipe.is_absolute() and self.recipe.name=='generations.nix','VISE_GENERATION_RECIPE_REFUSED')
        B.require(all(type(p) is str and p.startswith('/nix/store/') for p in (nix_instantiate,nix_build)),
            'VISE_GENERATION_TOOL_REFUSED')
        self.nix_instantiate=nix_instantiate;self.nix_build=nix_build
        self.execute=execute or B.Builder.command;self.layout=layout or L.verify

    def construct(self,work,state,candidate_path,*,observe):
        work=B.O.W.private_directory(work);B.G.state_checked(state)
        B.require(B.G.store(candidate_path),'VISE_GENERATION_CANDIDATE_REFUSED')
        def stable():B.require(observe()==state['system'],'VISE_GENERATION_LIVE_BASE_CHANGED')
        stable()
        inputs={'schema_version':1,'profile':'vise-v1','state':state,'candidate':candidate_path,'recipe':str(self.recipe)}
        input_file=work/'inputs.json'
        if input_file.exists():B.require(B.O.W.read_file(input_file,65536)==B.O.encode(inputs),'VISE_GENERATION_INPUTS_CHANGED')
        else:B.O.save(input_file,inputs)
        candidate=json.loads((Path(candidate_path)/'descriptor.json').read_bytes())
        state_file=work/'input-state.json';B.O.save(state_file,state);raw=B.O.W.read_file(state_file,65536)
        args=[str(self.recipe),'--argstr','stateFile',str(state_file),'--argstr','candidatePath',candidate_path]
        views={}
        for phase in ('current','candidate'):
            output=self.execute([self.nix_instantiate,'--eval','--read-write-mode','--strict','--json',*args,'-A','views.'+phase])
            B.require(len(output)<=65536,'VISE_GENERATION_VIEW_SIZE_REFUSED')
            views[phase]=json.loads(output);B.O.save(work/('view-'+phase+'.json'),views[phase])
        proof=V.verify(views,raw,candidate_path,candidate);stable()
        output=self.execute([self.nix_build,*args,'-A','build','--out-link',str(work/'generation'),
            '--option','builders','','--max-jobs','1','--cores','1'])
        B.require(output.decode('ascii').strip()==proof['system'],'VISE_GENERATION_BUILD_CHANGED')
        stable()
        checked=self.layout(state['system'],proof['system'],candidate_path,
            previous_adopted=state.get('vise',{}).get('adopted'))
        stable()
        proof.update(built=True,layout=checked,view_sha256={phase:B.O.sha(B.O.encode(v)) for phase,v in views.items()})
        B.O.save(work/'prepared.json',proof)
        return proof

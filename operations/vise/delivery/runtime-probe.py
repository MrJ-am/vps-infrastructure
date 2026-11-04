"""Build and synthetic runtime qualification; no signed delivery artifacts."""
import json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from build_stage import Build
from runtime_stage import Runtime
import source_policy as P

if __name__=='__main__':
    try:
        P.require(sys.argv[1:]==['/input'],'VISE_PROBE_ARGUMENTS_REFUSED')
        build=Build(json.loads(Path('@runtime@').read_bytes()))
        result=build.run();Runtime(build).run()
        result['scope']='isolated-build-and-synthetic-runtime-only'
        result['steps']=build.steps
        print(json.dumps(result,sort_keys=True),file=sys.stderr)
    except Exception as error:
        import re
        code=str(error) if re.fullmatch('VISE_[A-Z_]+',str(error)) else 'VISE_RUNTIME_PROBE_REFUSED'
        print(json.dumps({'code':code,'exception_type':type(error).__name__}),file=sys.stderr)
        raise SystemExit(1) from None

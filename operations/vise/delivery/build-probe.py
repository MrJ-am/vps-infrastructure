"""Local build-stage qualification; deliberately emits no collector artifacts."""
import json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from build_stage import Build

if __name__=='__main__':
    try:
        assert sys.argv[1:]==['/input']
        result=Build(json.loads(Path('@runtime@').read_bytes())).run()
        print(json.dumps(result,sort_keys=True),file=sys.stderr)
    except Exception as error:
        # Candidate command output is discarded by sandbox.run. Only a closed
        # status from the installed supervisor may leave this qualification.
        import re
        code=str(error) if re.fullmatch('VISE_[A-Z_]+',str(error)) else 'VISE_BUILD_PROBE_REFUSED'
        print(json.dumps({'code':code,'exception_type':type(error).__name__}),file=sys.stderr)
        raise SystemExit(1) from None

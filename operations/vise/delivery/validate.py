"""ViSe verifier content producer. Signing and release acceptance are separate."""
import json,stat,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from build_stage import Build
from runtime_stage import Runtime
import artifacts,source_policy as P

if __name__=='__main__':
    try:
        P.require(sys.argv[1:]==['/input'],'VISE_VALIDATOR_ARGUMENTS_REFUSED')
        P.require(stat.S_ISFIFO(Path('/output/channel').lstat().st_mode),'VISE_COLLECTOR_CHANNEL_REQUIRED')
        build=Build(json.loads(Path('@runtime@').read_bytes()))
        build.run();Runtime(build).run();artifacts.send(build)
    except Exception as error:
        import re
        code=str(error) if re.fullmatch('VISE_[A-Z_]+',str(error)) else 'VISE_VALIDATION_REFUSED'
        print(json.dumps({'code':code,'exception_type':type(error).__name__}),file=sys.stderr)
        raise SystemExit(1) from None

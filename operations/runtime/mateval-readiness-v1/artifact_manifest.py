import hashlib
import json
from pathlib import Path
import sys

root=Path(sys.argv[1])
patch=Path(sys.argv[2])
base={
    'schema_version':1,
    'artifact':'rust-server-mateval-typed-readiness-v1',
    'source_proposal_sha256':'8bf05fb9065a4c91e565ec0d37f24f2c556f315109823ccdef95c6354b423d6a',
    'source_commits':{
        'platform':'4e65423ceaae5e3c4cb8c057fac1a5bd193f5bf8',
        'mateval':'91b5b33541a39faade0c40792bfed5ad35ae80a1',
        'vision':'99eace9df76777c89bbd992952738b3f57608801'},
    'base_qualified_elf_sha256':'f896cd1c17cc85d331474622747f4c019258a1023dfb5963125b235f4a6236cd',
    'patch_sha256':hashlib.sha256(patch.read_bytes()).hexdigest(),
    'changed_files':['crates/server/src/database.rs','crates/server/tests/runtime_postgres.rs'],
    'mateval_types_sha256':'aed36e3ab6058d6756f3e8a6198b5a5df4c4af32e5d1eeef3f95eeed4312674c',
    'rust_toolchain_version':'1.99.1',
    'vendor_materialization_sha256':'6c4c957933bac12ded038377f3346a800366201a0ae743bce06dd21f87ab50b8',
    'checks':['cargo-fmt','workspace-all-features-release-native-postgresql-tests','clippy-all-targets-all-features'],
    'payload_sha256':{'bin/mrjam-server':hashlib.sha256((root/'bin/mrjam-server').read_bytes()).hexdigest()},
    'production_authorized':False,'historical_receipt_reused':False,
    'database_mutation_added':False,'codebook_read_added':False,
}
(root/'artifact.json').write_text(json.dumps(base,sort_keys=True,separators=(',',':'))+'\n')

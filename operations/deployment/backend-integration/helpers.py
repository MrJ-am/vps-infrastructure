"""Invented closed contracts; never evidence of an actual application."""
import json
from pathlib import Path
import sys
name=Path(sys.argv[0]).name
binding='a'*64
members={'admission':(True,True,False),'cycle':(False,True,False),'replay':(False,False,True)}
if name=='probe-standalone.py':
    result={'all_tokens_present':True,'tokens_distinct':True}
    for who,values in members.items():
        result[who]={'present':True,'authenticated_service':True,
                     **dict(zip(('onboarding_membership','mail_read_membership','people_admin_membership'),values))}
elif name=='preflight_obligations.py':
    refuse=Path('/run/integrated-case').read_text().strip()=='interrupt-return-before-snapshot'
    result={'cycle':{'state':'observed','markers_present':refuse},
            'closure':{'state':'observed','markers_present':False,'incomplete_present':False}}
elif name=='forgejo_sso_probe.py':
    result={'passed':True,'mutation_performed':False,'private_values_exported':False}
elif name=='mrjam-forgejo-probe':
    result={'technical_account_eligible':True,'technical_account_attested':True,'api_admin':True,'temporary_token_revoked':True}
elif name=='mrjam-forgejo-cleanup':
    result={'schema_version':1,'temporary_token_revoked':True}
elif name=='mrjam-first-release-sources-probe':
    result={'schema_version':1,'binding_sha256':binding,'source_inputs_verified':True}
elif name=='mrjam-first-release-governance':
    result={'schema_version':1,'binding_sha256':binding,'sources_bound':True,'protected_policy_verified':True,'temporary_credentials_revoked':True}
else:
    raise SystemExit(64)
print(json.dumps(result,sort_keys=True))

"""Verify that only the proved MAIL gate and closed diagnostics differ."""
from pathlib import Path

ROOT=Path(__file__).resolve().parent
source=(ROOT/'provision.py').read_text()
source=source.replace("\n\n# Diagnostic labels only; never include a token, account or API response.\nSTAGE = 'INITIALIZE'",'')
source='\n'.join(line for line in source.split('\n') if line.strip()!='global STAGE' and not line.strip().startswith('STAGE = '))
source=source.replace(",'stage':STAGE",'').replace(",'stage':'CLEANUP'",'')
source=source.replace("\nGROUP = 'idm_group_admins'",'')
source=source.replace("require(bool({ACCESS,GROUP} & members(self_attrs(api(access,'GET','/v1/self')),'memberof')))","require(ACCESS in members(self_attrs(api(access,'GET','/v1/self')),'memberof'))")
assert source==(ROOT.parent/'credentials'/'provision.py').read_text()
print('ONLY_MAIL_GATE_AND_CLOSED_DIAGNOSTICS_DIFFER')

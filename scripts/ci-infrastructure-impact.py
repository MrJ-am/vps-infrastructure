"""Sélecteur des qualifications d'exploitation centrales, sans attestation locale."""
import json
import os
import re
import subprocess
from fnmatch import fnmatchcase


def selection(fichiers, reference=False):
    jobs={'check':True,'keycloak':reference,'keycloak-unix-optimise':reference,'migration-vision':reference}
    for p in fichiers:
        commun=p in ('tests/nixpkgs.json','.github/workflows/check.yml','scripts/ci-infrastructure-impact.py','tests/test_ci_infrastructure_impact.py')
        if commun or any(fnmatchcase(p,m) for m in ('services/keycloak-mrjam/*','services/keycloak-mrjam/**/*','modules/identite*.nix','modules/mrj-auth.nix','services/mrj-auth/*','tests/keycloak*','tests/identite-amorcage*','scripts/vision-identite*','scripts/vision-mrjam-composants.nix','services/sources-mrjam.nix')):
            jobs['keycloak']=jobs['keycloak-unix-optimise']=True
        if commun or any(fnmatchcase(p,m) for m in ('modules/postgresql.nix','lib/databases.nix','databases.json','tests/*migration*','tests/*retour*','scripts/*migration*','scripts/vision-bascule*','scripts/vision-essai-reprise*','scripts/vision-retour*','operations/vision-retour*')):
            jobs['migration-vision']=True
    return jobs


def main():
    avant=os.environ.get('MRJAM_COMMIT_AVANT','')
    ref=os.environ.get('MRJAM_REFERENCE','')=='true'
    if not re.fullmatch('[a-f0-9]{40}',avant) or set(avant)=={'0'}:ref=True;files=[]
    else:files=subprocess.check_output(['git','diff','--name-only',avant,'HEAD'],text=True).splitlines()
    jobs=selection(files,ref)
    with open(os.environ['GITHUB_OUTPUT'],'a') as f:
        for job,val in jobs.items():f.write(job+'='+str(val).lower()+'\n')
    print(json.dumps({'jobs':jobs,'reference':ref,'suite_evitees':sum(not v for v in jobs.values())}))


if __name__=='__main__':main()

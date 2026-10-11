"""Diagnostic fermé de préparation : empreintes et clés, jamais les valeurs."""
import hashlib
from collections import Counter
import json
from pathlib import Path
import re
import subprocess
import sys


def empreinte(v):
    return hashlib.sha256(json.dumps(v,sort_keys=True).encode()).hexdigest()


def differences(a,b,chemin=''):
    if a==b:return []
    if isinstance(a,dict) and isinstance(b,dict):
        return [d for k in sorted(set(a)|set(b)) for d in differences(a.get(k),b.get(k),chemin+'/'+k)]
    r={'champ':chemin,'avant_sha256':empreinte(a),'apres_sha256':empreinte(b)}
    if chemin.startswith('/units/') and isinstance(a,str) and isinstance(b,str):
        def champs(t):
            return {k:v for l in t.splitlines() if '=' in l for k,v in [l.split('=',1)] if re.fullmatch('[A-Za-z0-9]+',k)}
        x,y=champs(a),champs(b)
        r['proprietes_modifiees']=[k for k in sorted(set(x)|set(y)) if x.get(k)!=y.get(k)]
    return [r]


def diagnostic_identmap(avant,apres):
    def lignes(t):return [l.split() for l in t.splitlines() if l.strip() and not l.lstrip().startswith('#')]
    a=lignes(avant);b=lignes(apres)
    roles=('vision','vision_administration','vision_cycle','vision_admission',
           'vision_fermeture','vision_entretien','matheval_app')
    ajouts=[['mrjam_metier','mrjam-metier',r] for r in roles]
    # N’émettre aucune valeur inconnue provenant de la configuration.
    return {'lignes_avant':len(a),'lignes_apres':len(b),
            'nombre_colonnes_apres':[len(l) for l in b],
            'ancien_prefixe_preserve':b[:len(a)]==a,
            'seuls_ajouts_attendus':Counter(map(tuple,b))==Counter(map(tuple,a+ajouts)),
            'positions_ajouts':{r:[i for i,l in enumerate(b) if l==ajout]
                               for r,ajout in zip(roles,ajouts)}}


def diagnostic_erreur(texte,tables_autorisees=()):
    # Pas de message de condition, requête SQL, ligne de source ni valeur locale.
    pile=[{'fichier':Path(n).name,'ligne':int(l)}
          for n,l in re.findall(r'File "([^"]+)", line (\d+)',texte)]
    dernier=texte.rstrip().splitlines()[-1] if texte.strip() else ''
    classe=dernier.split(':',1)[0]
    out={'exception':classe if re.fullmatch('[A-Za-z_][A-Za-z0-9_.]{0,80}',classe) else 'inconnue',
         'pile':pile[-12:]}
    m=re.fullmatch(r'ValueError: Contrat SQL divergent : ([a-z_][a-z0-9_]*\.[a-z_][a-z0-9_]*) (rls|force_rls|colonne_utilisateur)',dernier)
    if m and m[1] in tables_autorisees:
        out['contrat_sql']={'table':m[1],'champ':m[2]}
    return out


def metadonnees_rls(postgres,base,attendus):
    if base not in ('vision','matheval'):raise ValueError('Base hors périmètre')
    # Métadonnées uniquement, transaction en lecture seule ; aucune ligne métier.
    q="""BEGIN READ ONLY;
SELECT coalesce(json_agg(json_build_object('table',n.nspname||'.'||c.relname,
 'rls',c.relrowsecurity,'force_rls',c.relforcerowsecurity,
 'colonne_utilisateur',EXISTS(SELECT FROM pg_attribute WHERE attrelid=c.oid AND attname='utilisateur' AND NOT attisdropped),
 'politiques',(SELECT count(*) FROM pg_policy WHERE polrelid=c.oid))),'[]')
FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
WHERE c.relkind IN ('r','p') AND n.nspname IN ('public','vision_gestion');
COMMIT;"""
    p=subprocess.run(['runuser','-u','postgres','--',str(Path(postgres)/'bin/psql'),
        '-XAtq','--set=ON_ERROR_STOP=1','--host=/run/postgresql','--dbname='+base,'--file=-'],
        input=q,text=True,capture_output=True,timeout=30,check=True)
    rows=json.loads(p.stdout)
    return {r['table']:{k:r[k] for k in ('rls','force_rls','colonne_utilisateur','politiques')}
            for r in rows if r['table'] in attendus}


def main(revision):
    if not re.fullmatch('[a-f0-9]{40}',revision):raise ValueError('Révision refusée')
    d=Path('/root/mrjam-assemblages')/revision
    r=json.loads((d/'evaluation-privee.json').read_text())
    out={'revision':revision,'assertions':r['assertions'],
         'invariants_modifies':differences(r['invariantAvant'],r['invariantApres']),
         'preparation_presente':(d/'preparation.json').exists(),
         'activation_presente':(d/'activation.json').exists()}
    out['restauration_presente']=(d/'restauration.json').exists()
    inventaire=json.loads((d/'payload/vps/assemblage/tables-privees.json').read_text())
    tables_autorisees=set(inventaire['vision'])|set(inventaire['matheval'])
    out['metadonnees_rls_vision_actives']=metadonnees_rls(r['postgres'],'vision',inventaire['vision'])
    for nom in ('restauration','activation'):
        p=d/('erreur-'+nom+'-privee.log')
        if p.is_file():out['erreur_'+nom]=diagnostic_erreur(p.read_text(),tables_autorisees)
    if 'postgresAccesAvant' in r and 'postgresAccesApres' in r:
        out['identMap']=diagnostic_identmap(r['postgresAccesAvant']['identMap'],
                                          r['postgresAccesApres']['identMap'])
    # Messages statiques des assertions Nix ; pas les configurations ni les
    # unités, credentials, clés, contenu métier ou sorties SQL.
    if not r['assertions']:
        cert=json.loads((d/'payload/stage.json').read_text())
        avant=Path('/etc/nixos/configuration.nix').resolve()
        params={'configuration':str(avant),'paquet':cert['qualification']['sorties_nix']['metier'],
            'documentVision':str(Path('/srv/mrjam-assemblages')/revision/'vision'),
            'ressourcesMatheval':str(Path('/srv/mrjam-assemblages')/revision/'matheval'),
            'bankVersion':json.loads((d/'payload/matheval/research/bank.json').read_text())['version']}
        expr='let e=import '+str(d/'payload/vps/scripts/monolithe-evaluation.nix')+' {'+''.join(k+'='+json.dumps(v)+';' for k,v in params.items())+'}; in map (a: a.message) (builtins.filter (a: !a.assertion) e.c.assertions)'
        p=subprocess.run(['nix-instantiate','-I','nixpkgs='+cert['manifest']['toolchain']['production']['nixpkgs'],
            '--eval','--strict','--json','--expr',expr],capture_output=True,text=True,timeout=120)
        if p.returncode==0:out['assertions_refusees']=json.loads(p.stdout)
        else:out['diagnostic_assertions_code']=p.returncode
    print(json.dumps(out,ensure_ascii=False))


if __name__=='__main__':main(sys.argv[1])

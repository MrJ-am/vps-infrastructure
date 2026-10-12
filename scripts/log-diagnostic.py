"""Sondes Log fermées : phases, erreurs classées et empreintes, aucune valeur privée."""
import importlib.util,json,os,re,sys,subprocess
from pathlib import Path

def classifier(texte,ancien):
    r=ancien.erreur_nix(texte)
    r['attributs_absents']=[a for a in ('version','outPath','enable','paquet','text','users','services')
        if re.search(r'attribute [\'`"]'+a+r'[\'`"] missing',texte)]
    r['conversions']=[t for t in ('string','set','path','function','list')
        if re.search(r'(?:expected|is not|cannot coerce|cannot be coerced).*\b'+t+r'\b',texte)]
    r['options_kanidm']=sorted(set(re.findall(r'(?:services\.kanidm|infrastructure\.log)\.[A-Za-z0-9_.]+',texte)))
    # En-têtes d'options uniquement ; jamais les lignes Definition values.
    options=re.findall(r'The option [`\']([^`\']+)[`\']',texte)
    r['options']=sorted(set(o for o in options if re.fullmatch(
        r'(?:services|infrastructure|systemd|security|boot|users|environment|networking)\.[A-Za-z0-9_."/ =~-]{1,280}',o)))
    return r

def main(revision):
    if os.geteuid()!=0 or not re.fullmatch('[a-f0-9]{40}',revision):raise ValueError('Cible refusée')
    d=Path('/root/mrjam-assemblages')/revision
    spec=importlib.util.spec_from_file_location('diagnostic_existant',d/'payload/vps/scripts/monolithe-diagnostic.py')
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    f=d/'erreur-commande-privee.log'
    out={'revision':revision,'generation':str(Path('/run/current-system').resolve()),
        'generation_demarrage':str(Path('/nix/var/nix/profiles/system').resolve()),
        'preparation':(d/'preparation-log.json').is_file(),'activation_engagee':(d/'activation-log-privee.json').is_file(),
        'erreur_nix':classifier(f.read_text(),m) if f.is_file() else {}}
    for nom in ('preparation','operation'):
        f=d/('erreur-log-'+nom+'-privee.log')
        if f.is_file():
            texte=f.read_text();out['erreur_'+nom]=m.diagnostic_erreur(texte)
            cmd=re.search(r'RuntimeError: Commande refusée : (nix-instantiate|nix-build|systemctl), code ([0-9]+)',texte)
            if cmd:out['erreur_'+nom]['commande']={'outil':cmd[1],'code':int(cmd[2])}
    f=d/'evaluation-log-privee.json'
    if f.is_file():
        r=json.loads(f.read_text());out['services_preserves']=m.differences(r['protegeAvant'],r['protegeApres'])
    elif not out['activation_engagee']:
        # Même expression fermée du préparateur, en lecture seule, trace
        # conservée privée ; seuls positions/classes/champs sont publiés.
        cert=json.loads((d/'payload/stage.json').read_text());base=d/'payload/vps/scripts'
        spec=importlib.util.spec_from_file_location('stage_diag_log',base/'monolithe-preparer.py')
        stage=importlib.util.module_from_spec(spec);spec.loader.exec_module(stage)
        bank=json.loads((d/'payload/matheval/research/bank.json').read_text())
        params=dict(configuration=str(Path('/etc/nixos/configuration.nix').resolve()),
            paquet=cert['qualification']['sorties_nix']['metier'],
            documentVision='/srv/mrjam-assemblages/'+revision+'/vision',
            ressourcesMatheval='/srv/mrjam-assemblages/'+revision+'/matheval',
            bankVersion=bank['version'],kanidm=cert['qualification']['sorties_nix']['kanidm'])
        expr='(import '+str(base/'log-evaluation.nix')+' {'+''.join(k+'='+json.dumps(v)+';' for k,v in params.items())+'}).rapport'
        f=d/'diagnostic-nix-trace-privee.log'
        if f.is_file():
            out['trace_nix']=classifier(f.read_text(),m)
        else:
            r=subprocess.run(['nix-instantiate','-I','nixpkgs='+stage.NIXPKGS,'--eval','--strict','--show-trace','--json','--expr',expr],
                capture_output=True,text=True,timeout=90)
            f.write_text(r.stderr);f.chmod(0o600)
            out['trace_nix']=classifier(r.stderr,m)
            out['evaluation_code']=r.returncode
    print(json.dumps(out,ensure_ascii=False))

if __name__=='__main__':main(sys.argv[1])

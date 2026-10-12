"""Sondes Log fermées : phases, erreurs classées et empreintes, aucune valeur privée."""
import importlib.util,json,os,re,sys
from pathlib import Path

def classifier(texte,ancien):
    r=ancien.erreur_nix(texte)
    r['attributs_absents']=[a for a in ('version','outPath','enable','paquet','text','users','services')
        if re.search(r'attribute [\'`"]'+a+r'[\'`"] missing',texte)]
    r['conversions']=[t for t in ('string','set','path','function','list')
        if re.search(r'(?:expected|is not|cannot coerce|cannot be coerced).*\b'+t+r'\b',texte)]
    r['options_kanidm']=sorted(set(re.findall(r'(?:services\.kanidm|infrastructure\.log)\.[A-Za-z0-9_.]+',texte)))
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
        if f.is_file():out['erreur_'+nom]=m.diagnostic_erreur(f.read_text())
    f=d/'evaluation-log-privee.json'
    if f.is_file():
        r=json.loads(f.read_text());out['services_preserves']=m.differences(r['protegeAvant'],r['protegeApres'])
    print(json.dumps(out,ensure_ascii=False))

if __name__=='__main__':main(sys.argv[1])

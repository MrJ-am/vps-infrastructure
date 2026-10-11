"""Complément bloquant HTML/CSS/JS : bootstrap et adaptateurs précisément inventoriés."""
from html.parser import HTMLParser
import hashlib
import json
from pathlib import Path
import subprocess
from assemblage import RACINE, chemins_sources


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


class Bootstrap(HTMLParser):
    def __init__(self):
        super().__init__();self.errors=[];self.body=False;self.scripts=[];self.script=None;self.stack=[];self.containers=0

    def handle_starttag(self,tag,attributes):
        attrs=dict(attributes)
        if tag not in ('meta','link','br','img','input'):self.stack.append(tag)
        if tag=='body':self.body=True
        if tag=='script':self.script=''
        if tag=='style' or 'style' in attrs or 'class' in attrs:
            self.errors.append('présentation écrite dans le document d’amorçage')
        if self.body and tag not in ('body','div','script','noscript'):
            self.errors.append('interface construite hors Elm : '+tag)
        if self.body and tag=='div' and (not attrs.get('id') or any(k!='id' for k in attrs)):
            self.errors.append('conteneur d’amorçage non minimal')
        if self.body and tag=='div':
            self.containers+=1
            if self.containers>1:self.errors.append('plusieurs conteneurs d’interface hors Elm')

    def handle_data(self,data):
        if self.script is not None:self.script+=data
        elif self.body and data.strip() and self.stack and self.stack[-1]!='noscript':
            self.errors.append('texte d’interface construit hors Elm')

    def handle_endtag(self,tag):
        if tag=='script' and self.script is not None:
            if self.script.strip():self.scripts.append(self.script)
            self.script=None
        if tag=='body':self.body=False
        if self.stack and self.stack[-1]==tag:self.stack.pop()


def verifier(composant,sources=None):
    sources=sources or chemins_sources()
    inventory=json.loads((RACINE/'assemblage/elm-review/ressources.json').read_text())
    base=sources[composant];errors=[];js=[]
    prefixes=inventory['racines'][composant]
    fichiers=subprocess.check_output(['git','ls-files','-z','--cached','--others','--exclude-standard'],cwd=base).decode().split('\0')
    retraits=set(subprocess.check_output(['git','ls-files','-z','--deleted'],cwd=base).decode().split('\0'))
    for rel in fichiers:
        if not rel or not any(rel.startswith(root) for root in prefixes):continue
        p=base/rel
        if rel in retraits:continue  # retrait effectif local ; absent du checkout après commit
        if p.is_symlink():raise ValueError('Ressource source liée symboliquement : '+composant+'/'+rel)
        if p.suffix not in ('.html','.css','.js','.mjs'):continue
        key=composant+'/'+rel
        declared=inventory['bibliotheques_generees'].get(key)
        if declared:
            if sha(p)!=declared['sha256']:errors.append({'fichier':key,'erreur':'bibliothèque générée différente de sa provenance'})
            for rel_source,empreinte in declared.get('producteurs',{}).items():
                source=base/rel_source
                if not source.resolve().is_relative_to(base.resolve()) or source.is_symlink() or not source.is_file() or sha(source)!=empreinte:
                    errors.append({'fichier':key,'erreur':'producteur différent de sa provenance : '+rel_source})
            continue
        if p.suffix=='.css':
            errors.append({'fichier':key,'erreur':'feuille CSS de présentation non autorisée'})
        elif p.suffix=='.html':
            parser=Bootstrap();parser.feed(p.read_text())
            errors.extend({'fichier':key,'erreur':e} for e in parser.errors)
            for script in parser.scripts:js.append({'path':key,'content':script,'exceptions':[]})
        else:
            js.append({'path':key,'content':p.read_text(),'exceptions':inventory['adaptateurs_js'].get(key,[])})
    lock=json.loads((RACINE/'assemblage/elm-review/outils.lock.json').read_text())['parseur_js_existant']
    parser=sources['matheval']/lock['fichier']
    if sha(parser)!=lock['sha256']:raise ValueError('Parseur JS existant différent de sa provenance')
    implementation=sources['matheval']/lock['implementation']
    if sha(implementation)!=lock['implementation_sha256']:raise ValueError('Implementation du parseur JS différente')
    r=subprocess.run(['node',str(RACINE/'scripts/revoir-interop.cjs'),str(parser)],input=json.dumps(js),capture_output=True,text=True)
    if r.returncode not in (0,1):raise ValueError('Contrôle JS non exécuté : '+r.stderr[-1000:])
    errors.extend(json.loads(r.stdout))
    report=RACINE/'state/review-frontends'/(composant+'-ressources.json');report.parent.mkdir(parents=True,exist_ok=True)
    report.write_text(json.dumps({'resultat':'echec' if errors else 'succes','erreurs':errors},ensure_ascii=False,indent=2)+'\n')
    if errors:raise ValueError(f'{composant} : {len(errors)} violations HTML/CSS/JS ; {report}')
    print(composant+' : amorçage et interopérabilité contrôlés.')

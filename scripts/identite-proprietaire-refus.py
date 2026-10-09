"""Une seule reprise d'un POST explicitement refusé ; jamais une réponse perdue."""
import ast
import hashlib
import re

PRECEDENTE='0f8b9f382634b06e9ea941a3a0c7c66d8ec5a866'
SOURCES={'identite-proprietaire.py':'9cf48344197ee6b640e5adfce124e9e53186ee7aef6a3c15d1465a33e1453740',
    'vision-proprietaire-enroler.py':'f46fab95ea4d22f8efcfddb27dec097c508e044e0e05897a87ee5d1c5243a08d'}
RACINE='/root/vision-proprietaire-operations/'+PRECEDENTE+'/source/scripts/'
ARCHIVE='creation-refusee-'+PRECEDENTE
RECU='refus-creation-recu-'+PRECEDENTE

class RepriseRefusee(ValueError):pass
def exiger(ok,code):
    if not ok:raise RepriseRefusee(code)

def verifier(trace,sources,ancien,contact,etat,personnes,profil):
    exiger(set(sources)==set(SOURCES) and all(hashlib.sha256(sources[k].encode()).hexdigest()==v
        for k,v in SOURCES.items()),'reprise_source')
    exiger(trace.count('Traceback (most recent call last):')==1 and
        re.search(r'(?m)^urllib\.error\.HTTPError: HTTP Error 400: Bad Request\s*\Z',trace),
        'reprise_reponse')
    frames=re.findall(r'(?m)^  File "([^"]+)", line ([0-9]+), in ([^\n]+)$',trace)
    arbre=ast.parse(sources['identite-proprietaire.py'])
    appels=[n for n in ast.walk(arbre) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name)
        and n.func.id=='api' and len(n.args)==3 and isinstance(n.args[2],ast.Constant)
        and n.args[2].value=='POST' and isinstance(n.args[0],ast.BinOp)
        and isinstance(n.args[0].left,ast.Name) and n.args[0].left.id=='base'
        and isinstance(n.args[0].right,ast.Constant) and n.args[0].right.value=='/users']
    exiger(len(appels)==1,'reprise_source')
    appel=appels[0]
    positions=[i for i,(p,l,f) in enumerate(frames) if p==RACINE+'identite-proprietaire.py' and
        f=='preparer_compte' and appel.lineno<=int(l)<=appel.end_lineno]
    exiger(len(positions)==1 and any(p==RACINE+'vision-proprietaire-enroler.py' and f=='main'
        for p,l,f in frames[:positions[0]]) and any(p==RACINE+'vision-proprietaire-enroler.py'
        and f=='__call__' and int(l)==78 for p,l,f in frames[positions[0]+1:]),'reprise_etape')
    exiger(etat.get('creation-demandee')=={} and all(etat.get(k) is None for k in
        ('compte.json','courriel-demande','courriel-accepte',ARCHIVE,RECU)) and personnes==[],
        'reprise_etat')
    exiger(isinstance(ancien,dict) and isinstance(contact,dict) and set(ancien)==set(contact) and
        all(ancien[k]==contact[k] for k in ancien if k!='nom_connexion') and
        isinstance(ancien.get('nom_connexion'),str) and len(ancien['nom_connexion'])==2 and
        isinstance(contact.get('nom_connexion'),str) and 3<=len(contact['nom_connexion'])<=64,
        'reprise_contact')
    attributs=[a for a in profil.get('attributes',[]) if a.get('name')=='username']
    exiger(len(attributs)==1 and str(attributs[0].get('validations',{}).get('length',{}).get('min'))=='3'
        and str(attributs[0].get('validations',{}).get('length',{}).get('max'))=='255','reprise_profil')
    return dict(version=1,operation_refusee=PRECEDENTE,post_creation_refuse_http400=True,
        sources_verifiees=True,aucun_compte_humain=True,aucun_sujet_recu=True,
        aucun_courriel_demande=True,adresse_et_issuer_conserves=True,profil_minimum_verifie=True)

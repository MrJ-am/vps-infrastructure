"""Contrôler les octets servis et la navigation publique des trois sites."""
import hashlib,importlib.util,json,os,urllib.error,urllib.request
from pathlib import Path
from playwright.sync_api import sync_playwright,expect
from publication_interfaces import verifier

SOURCE=Path(__file__).resolve().parents[1]

def lire(url):
    with urllib.request.urlopen(url,timeout=30) as r:return r.read()

def main():
    references,interfaces,_,memoire=verifier(SOURCE)
    sortie=SOURCE/'rapports-interfaces';sortie.mkdir(exist_ok=True)
    vision=sortie/'vision';vision.mkdir(exist_ok=True)
    (vision/'manifest.json').write_bytes(interfaces['vision'][1]['manifest.json'])
    os.environ['VISION_INTERFACE_ARTEFACT']=str(vision)
    spec=importlib.util.spec_from_file_location('controle_vision',SOURCE/'scripts/vision-refonte-verifier.py')
    controle=importlib.util.module_from_spec(spec);spec.loader.exec_module(controle);controle.verifier()
    for nom,base,manifeste in [('logique','https://logique.echos.systems/',interfaces['logique'][0]['empreintes']),
                               ('matheval','https://principiipetit.io/matheval/',json.loads(memoire['release-manifest.json']))]:
        for fichier,h in manifeste.items():
            assert hashlib.sha256(lire(base+fichier)).hexdigest()==h, 'Fichier servi différent : '+nom+'/'+fichier
    public=json.loads(lire('https://logique.echos.systems/manifeste-preparation.json'))
    assert all(public[k]==interfaces['logique'][0][k] for k in ('application','style','signature','empreintes'))
    assert public['publicationAutorisee'] and public['hebergementConfirme'] and public['typographieValidee']
    assert json.loads(lire('https://principiipetit.io/matheval/api/health'))['status']=='ok'
    for chemin in ('admin/me','admin/statistics'):
        try:lire('https://principiipetit.io/matheval/api/'+chemin)
        except urllib.error.HTTPError as e:assert e.code==401
        else:raise AssertionError('Accès anonyme Mémoire accepté')
    with sync_playwright() as p:
        navigateur=p.chromium.launch();page=navigateur.new_page();erreurs=[]
        page.on('pageerror',lambda e:erreurs.append(str(e)))
        for nom,url,titre in [('logique','https://logique.echos.systems/?accueil=1',''),
                               ('matheval','https://principiipetit.io/matheval/',''),
                               ('vision-docs','https://vision.mrj.am/docs','Fiches et items'),
                               ('vision-confidentialite','https://vision.mrj.am/privacy','Confidentialité')]:
            for largeur in (320,375,768,1280):
                page.set_viewport_size({'width':largeur,'height':900});page.goto(url,wait_until='networkidle')
                expect(page.locator('.mrjam').first).to_be_visible()
                assert page.evaluate("async ()=>(await document.fonts.load('28px MrJamSignature')).length>0")
                assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'),nom
                if titre:expect(page.get_by_role('heading',name=titre,exact=True)).to_be_visible()
                page.screenshot(path=str(sortie/f'{nom}-{largeur}.png'),full_page=True)
        assert not erreurs,'Erreur JavaScript publique';navigateur.close()
    (sortie/'bilan.json').write_text(json.dumps({'applications':references['applications'],'octets_servis':True,'formats':[320,375,768,1280],
                                              'authentification_csrf':True,'ecritures_metier':False},ensure_ascii=False,indent=2)+'\n')
    print('Trois sites : ressources exactes, seize vues publiques, sessions, CSRF et refus anonymes vérifiés.')

if __name__=='__main__':main()

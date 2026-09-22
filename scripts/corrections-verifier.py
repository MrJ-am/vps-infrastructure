"""Contrôles publics de Logique, des domaines inconnus et des fichiers exacts."""
import hashlib
import json
from pathlib import Path
import urllib.error
import urllib.request
from playwright.sync_api import sync_playwright, expect

ORIGINE='https://logique.echos.systems'


def verifier_videos(page):
    """Constater les droits du fournisseur réel sans simuler son lecteur."""
    videos=page.evaluate("""() => window.courseData.tracks.flatMap(t => t.lessons
      .filter(l => l.video.provider === 'vimeo')
      .map(l => ({parcours:t.id,lecon:l.id,video:l.video.id})))""")
    vus=set();resultats=[]
    for video in videos:
        if video['video'] in vus:continue
        vus.add(video['video'])
        page.goto(ORIGINE+'/#/'+video['parcours']+'/'+video['lecon']+'/video')
        expect(page.locator('course-video iframe')).to_have_count(0)
        page.locator('course-video .video-play').click()
        page.wait_for_function("""() => {const v=document.querySelector('course-video');
          return v && !v.hasAttribute('aria-busy')}""",timeout=25000)
        duree=page.evaluate("""async () => {
          try {return await Promise.race([
            document.querySelector('course-video').player?.getDuration(),
            new Promise(r=>setTimeout(()=>r(null),15000))]);}
          catch {return null;}
        }""")
        disponible=isinstance(duree,(float,int)) and duree>0
        if disponible:
            page.get_by_role('button',name='Arrêter la vidéo',exact=True).click()
            expect(page.locator('course-video iframe')).to_have_count(0)
        else:
            # Les droits Vimeo ne sont pas détenus par Nginx : conserver le
            # diagnostic et exiger le secours prévu, sans masquer cette limite.
            expect(page.locator('course-video .video-fallback a')).to_be_visible()
        resultats.append({**video,'lectureIntegreeDisponible':disponible})
    Path('rapports-corrections').mkdir(exist_ok=True)
    Path('rapports-corrections/videos-reelles.json').write_text(json.dumps(resultats,ensure_ascii=False,indent=2)+'\n')
    print('Lecteurs Vimeo réels disponibles : '+str(sum(v['lectureIntegreeDisponible'] for v in resultats))+'/'+str(len(resultats)))


def verifier():
    source=Path('artefacts-controles/logique')
    attendu=json.loads((source/'manifeste-preparation.json').read_text())
    with urllib.request.urlopen(ORIGINE+'/manifeste-preparation.json',timeout=20) as r:
        servi=json.load(r)
    for cle in ('application','style','signature','empreintes'):
        assert servi[cle]==attendu[cle], 'Manifeste différent : '+cle
    assert servi['hebergementConfirme'] and servi['publicationAutorisee']
    for nom,empreinte in attendu['empreintes'].items():
        with urllib.request.urlopen(ORIGINE+'/'+nom,timeout=20) as r:
            assert hashlib.sha256(r.read()).hexdigest()==empreinte, 'Fichier différent : '+nom
    for chemin in ('/inexistant-20260922.js','/.env'):
        try:urllib.request.urlopen(ORIGINE+chemin,timeout=20)
        except urllib.error.HTTPError as e:assert e.code==404
        else:raise AssertionError('Ressource absente servie')
    # Un hôte arbitraire sur cette adresse doit être refusé, sans renvoyer Matheval.
    try:urllib.request.urlopen(urllib.request.Request('http://187.77.95.158/',headers={'Host':'domaine-inconnu.invalid'}),timeout=20)
    except urllib.error.HTTPError as e:assert e.code==421
    else:raise AssertionError('Hôte inconnu non refusé')
    with urllib.request.urlopen(ORIGINE+'/matheval/',timeout=20) as r:
        assert r.status==200 and r.url==ORIGINE+'/?accueil=1'
    with sync_playwright() as p:
        navigateur=p.chromium.launch()
        page=navigateur.new_page();erreurs=[];tiers=[]
        page.on('pageerror',lambda e:erreurs.append(str(e)))
        page.on('request',lambda r:tiers.append(r.url) if not r.url.startswith(ORIGINE+'/') else None)
        for dimensions in ({'width':320,'height':640},{'width':390,'height':844},{'width':844,'height':390},{'width':1440,'height':900}):
            page.set_viewport_size(dimensions)
            page.goto(ORIGINE+'/#/parcours',wait_until='networkidle')
            expect(page.locator('.mrjam')).to_have_text('MrJ.am')
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth+1')
        assert not erreurs, 'Erreur JavaScript'
        assert not tiers, 'Contact tiers avant activation'
        verifier_videos(page)
        navigateur.close()
    print('Logique : TLS réel, artefact exact, anciennes redirections récupérées, domaines inconnus refusés et quatre formats vérifiés.')


if __name__=='__main__':verifier()

#!/usr/bin/env python3
"""Constat HTTPS des octets effectivement servis et lecture du prototype publié."""
from pathlib import Path
import hashlib
import json
import ssl
import urllib.request
from playwright.sync_api import sync_playwright, expect
from logique_atelier import verifier


def verifier_graphique(page):
    gauche=page.locator('.mrjam-atelier-palette').bounding_box()
    droite=page.locator('#atelier-surface').bounding_box()
    assert gauche['x']==0 and droite['x']>=gauche['width']-1
    assert droite['height']>300 and droite['y']<450
    assert page.evaluate('document.documentElement.scrollHeight <= innerHeight + 2')
    assert page.locator('.mrjam-bloc-entete').first.evaluate('e=>getComputedStyle(e).backgroundColor')=='rgb(255, 203, 56)'
    assert page.locator('.mrjam-proposition').first.evaluate('e=>getComputedStyle(e).backgroundColor')=='rgb(88, 182, 83)'
    page.locator('#atelier-palette').get_by_role('button',name='Propositions',exact=True).click()
    source=page.locator('#atelier-palette').get_by_role('button',name='⇒',exact=True)
    destination=page.get_by_role('button',name='Modifier param:double:A',exact=True)
    source.scroll_into_view_if_needed();destination.scroll_into_view_if_needed()
    a=source.bounding_box();z=destination.bounding_box()
    page.mouse.move(a['x']+a['width']/2,a['y']+a['height']/2);page.mouse.down()
    page.mouse.move(z['x']+z['width']/2,z['y']+z['height']/2,steps=12);page.mouse.up()
    page.wait_for_function('JSON.parse(localStorage.getItem("mrjam.atelier-preuves.v1")).preuves[0].parametres.A.type === "implique"')
    expect(page.locator('[data-sous-formule="param:double:A|0"]')).to_have_count(1)
    page.get_by_role('button',name='Annuler',exact=True).click()
    expect(page.locator('#atelier-verification')).to_contain_text('✓ Preuve vérifiée')
    page.locator('#atelier-palette').get_by_role('button',name='Construire',exact=True).click()


def verifier_tactile(navigateur, base, sortie):
    contexte=navigateur.new_context(viewport={'width':390,'height':900},is_mobile=True,has_touch=True)
    page=contexte.new_page();page.goto(base+'#/atelier');expect(page.locator('#atelier')).to_be_visible()
    page.get_by_label('Exemple',exact=True).select_option('double')
    page.get_by_role('button',name='Construire l’énoncé',exact=True).click()
    entete=page.locator('[data-atelier-piece="regle:etI"] .mrjam-bloc-entete')
    entete.scroll_into_view_if_needed();a=entete.bounding_box();z=page.locator('#atelier-surface').bounding_box()
    x=a['x']+a['width']-10;y=a['y']+8;tx=z['x']+z['width']/2;ty=z['y']+z['height']*.68
    assert page.evaluate('p=>!document.elementFromPoint(p.x,p.y).closest("[data-atelier-source]")',{'x':x,'y':y})
    cdp=contexte.new_cdp_session(page)
    cdp.send('Input.dispatchTouchEvent',{'type':'touchStart','touchPoints':[{'x':x,'y':y}]})
    for i in range(1,17):
        cdp.send('Input.dispatchTouchEvent',{'type':'touchMove','touchPoints':[{'x':x+(tx-x)*i/16,'y':y+(ty-y)*i/16}]})
    expect(page.locator('.atelier-fantome')).to_have_count(1)
    cdp.send('Input.dispatchTouchEvent',{'type':'touchEnd','touchPoints':[]})
    page.wait_for_function('JSON.parse(localStorage.getItem("mrjam.atelier-preuves.v1")).preuves.length===1')
    expect(page.locator('.atelier-fantome')).to_have_count(0)
    page.screenshot(path=str(sortie/'atelier-tactile-390.png'),full_page=True)
    contexte.close()


def main():
    reference,manifeste,_=verifier()
    base='https://logique.echos.systems/'
    contexte=ssl.create_default_context()
    for nom,sha in manifeste['empreintes'].items():
        requete=urllib.request.Request(base+nom,headers={'Cache-Control':'no-cache'})
        with urllib.request.urlopen(requete,context=contexte,timeout=30) as reponse:
            assert reponse.status==200
            assert hashlib.sha256(reponse.read()).hexdigest()==sha,nom
    with urllib.request.urlopen(base+'manifeste-preparation.json',context=contexte,timeout=30) as reponse:
        publie=json.load(reponse)
    assert all(publie[k]==reference[k] for k in ('application','style','signature'))
    assert publie['hebergementConfirme'] and publie['publicationAutorisee'] and publie['typographieValidee']
    sortie=Path('rapports-logique-atelier');sortie.mkdir(exist_ok=True)
    with sync_playwright() as p:
        navigateur=p.chromium.launch()
        for largeur in (390,768,1440):
            page=navigateur.new_page(viewport={'width':largeur,'height':900})
            erreurs=[];page.on('pageerror',lambda e:erreurs.append(str(e)))
            page.goto(base+'#/atelier')
            expect(page.locator('#atelier')).to_be_visible()
            page.get_by_label('Exemple',exact=True).select_option('transitivite')
            page.get_by_role('button',name='Charger la solution manipulable',exact=True).click()
            expect(page.locator('#atelier-verification')).to_contain_text('✓ Preuve vérifiée')
            page.locator('[data-bloc="trans"]').get_by_role('button',name='Inspecter',exact=True).first.click()
            page.get_by_role('button',name='Créer un théorème',exact=True).click()
            page.get_by_label('Nom du théorème',exact=True).fill('Contrôle local de transitivité')
            page.get_by_role('button',name='Enregistrer dans Mes théorèmes',exact=True).click()
            page.wait_for_function('JSON.parse(localStorage.getItem("mrjam.atelier-preuves.v1")).bibliotheque.some(d=>d.nom==="Contrôle local de transitivité")')
            page.reload()
            expect(page.locator('#atelier-verification')).to_contain_text('✓ Preuve vérifiée')
            assert page.evaluate('JSON.parse(localStorage.getItem("mrjam.atelier-preuves.v1")).bibliotheque.some(d=>d.nom==="Contrôle local de transitivité")')
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 2')
            page.get_by_label('Exemple',exact=True).select_option('double')
            page.get_by_role('button',name='Charger la solution manipulable',exact=True).click()
            verifier_graphique(page)
            page.screenshot(path=str(sortie/f'atelier-https-{largeur}.png'),full_page=True)
            assert not erreurs,erreurs
            page.close()
        verifier_tactile(navigateur,base,sortie)
        navigateur.close()
    (sortie/'https.json').write_text(json.dumps({'application':reference['application'],'style':reference['style'],
        'fichiers_identiques':len(manifeste['empreintes']),'formats':[390,768,1440],
        'extraction_rechargement':True,'palette_gauche_canevas_droit':True,
        'regles_jaunes_propositions_vertes':True,'depot_direct_connecteur':True,
        'prise_tactile_hors_libelle':True,'depot_tactile_fond_libre':True,
        'ecriture_serveur':False},indent=2)+'\n')
    print('HTTPS : fichiers exacts, trois formats, palette gauche, blocs jaunes/verts, emboîtement, extraction et rechargement contrôlés.')


if __name__=='__main__':main()

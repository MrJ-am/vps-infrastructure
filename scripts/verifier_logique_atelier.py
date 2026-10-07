#!/usr/bin/env python3
"""Constat HTTPS des octets effectivement servis et lecture du prototype publié."""
from pathlib import Path
import hashlib
import json
import ssl
import urllib.request
from playwright.sync_api import sync_playwright, expect
from logique_atelier import verifier


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
            page.screenshot(path=str(sortie/f'atelier-https-{largeur}.png'),full_page=True)
            assert not erreurs,erreurs
            page.close()
        navigateur.close()
    (sortie/'https.json').write_text(json.dumps({'application':reference['application'],'style':reference['style'],
        'fichiers_identiques':len(manifeste['empreintes']),'formats':[390,768,1440],
        'extraction_rechargement':True,'ecriture_serveur':False},indent=2)+'\n')
    print('HTTPS : fichiers exacts, trois formats, extraction et rechargement contrôlés.')


if __name__=='__main__':main()

"""Empreintes des fichiers exécutés par les outils npm et navigateurs locaux.

Un lock décrit l'entrée attendue ; ces empreintes constatent l'installation et
les binaires réellement disponibles. Elles n'attestent pas un runner distant.
"""
import hashlib
import json
import os
from pathlib import Path
from assemblage import RACINE


def fichier(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for bloc in iter(lambda:f.read(1024*1024),b''):h.update(bloc)
    return h.hexdigest()


def arbre(root,autorises=None):
    root=Path(root)
    if root.is_symlink() or not root.is_dir():raise ValueError('Installation absente ou lien inattendu : '+str(root))
    bases=[Path(p).resolve() for p in autorises or [root]]
    h=hashlib.sha256();total=0
    for p in sorted(root.rglob('*')):
        if p.is_symlink():
            cible=p.resolve(strict=True)
            if not any(cible.is_relative_to(b) for b in bases):raise ValueError('Outil lié hors des installations autorisées')
            valeur='lien:'+os.readlink(p)
            if cible.is_file():valeur+=':'+fichier(cible)
        elif p.is_file():valeur=fichier(p)
        else:continue
        h.update(json.dumps([str(p.relative_to(root)),valeur],ensure_ascii=True).encode()+b'\n');total+=1
    return {'sha256':h.hexdigest(),'fichiers':total}


def npm(suite,sources):
    bases=[sources[k]/p for k,ps in suite.get('npm_installations',{}).items() for p in ps]
    return {k+'/'+p:arbre(sources[k]/p,bases) for k,ps in suite.get('npm_installations',{}).items() for p in ps}


def navigateurs(suite,sources):
    result={}
    installes=[]
    if suite.get('navigateurs_python'):
        installes.append(('python',RACINE/'state/outils-python/navigateur/lib/python3.12/site-packages/playwright/driver/package'))
    for k,p in suite.get('navigateurs_npm',{}).items():
        installes.append((k,sources[k]/p/'playwright-core'))
    cache=Path(os.environ.get('PLAYWRIGHT_BROWSERS_PATH',Path.home()/'.cache/ms-playwright'))
    if str(cache)=='0':raise ValueError('Cache navigateur hermétique non qualifié par ce profil')
    for nom,package in installes:
        config=json.loads((package/'browsers.json').read_text())
        for b in config['browsers']:
            if b['name'] not in suite.get('navigateurs', ['chromium','chromium-headless-shell','ffmpeg']):continue
            # Les profils sont Linux x86_64 ; les seules variantes des moteurs
            # retenus concernent macOS. Refuser une future variante Linux plutôt
            # que présumer la résolution de Playwright.
            if any(k.startswith(('ubuntu','debian','linux')) for k in b.get('revisionOverrides',{})):
                raise ValueError('Variante Linux du navigateur : profil explicite requis')
            revision=b['revision'];nom_cache=b['name'].replace('-','_')
            dossier=cache/(nom_cache+'-'+revision)
            result[nom+'/'+dossier.name]=arbre(dossier)
    for k in ('PLAYWRIGHT_CHROMIUM_EXECUTABLE','CHROMIUM'):
        if os.environ.get(k):result[k]={'sha256':fichier(Path(os.environ[k]).resolve(strict=True))}
    return result

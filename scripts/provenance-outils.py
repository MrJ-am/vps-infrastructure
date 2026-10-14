"""Empreintes des fichiers exécutés par les outils npm et navigateurs locaux.

Un lock décrit l'entrée attendue ; ces empreintes constatent l'installation et
les binaires réellement disponibles. Elles n'attestent pas un runner distant.
"""
import hashlib
import json
import os
import shutil
import platform
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
        node=os.environ.get('PLAYWRIGHT_NODEJS_PATH')
        commun=shutil.which('node')
        if not node or not commun or Path(node).resolve(strict=True)!=Path(commun).resolve(strict=True):
            raise ValueError('Playwright Python doit utiliser le même Node que npm ; aucun fallback embarqué')
        result['node_driver_commun']={'chemin':str(Path(node).resolve(strict=True)),
                                     'sha256':fichier(Path(node).resolve(strict=True))}
        installes.append(('python',RACINE/'state/outils-python/navigateur/lib/python3.12/site-packages/playwright/driver/package'))
    for k,p in suite.get('navigateurs_npm',{}).items():
        installes.append((k,sources[k]/p/'playwright-core'))
    cache=Path(os.environ.get('PLAYWRIGHT_BROWSERS_PATH',Path.home()/'.cache/ms-playwright'))
    if str(cache)=='0':raise ValueError('Cache navigateur hermétique non qualifié par ce profil')
    for nom,package in installes:
        config=json.loads((package/'browsers.json').read_text())
        for b in config['browsers']:
            if b['name'] not in suite.get('navigateurs', ['chromium','chromium-headless-shell','ffmpeg']):continue
            # Les lanceurs assemblés de ce profil utilisent tous CHROMIUM ou
            # PLAYWRIGHT_CHROMIUM_EXECUTABLE ; ne pas prétendre exécuter le cache.
            if suite.get('chromium_externe') and b['name'] in ('chromium','chromium-headless-shell'):
                continue
            revision=b['revision']
            if any(k.startswith(('ubuntu','debian','linux')) for k in b.get('revisionOverrides',{})):
                # Verrouiller la variante réellement choisie sur cette machine,
                # y compris quand seules les anciennes distributions diffèrent.
                os_release=platform.freedesktop_os_release()
                architecture={'x86_64':'x64','aarch64':'arm64'}.get(platform.machine())
                actuelle=os_release['ID']+os_release['VERSION_ID']+'-'+str(architecture)
                profil=suite.get('plateforme_playwright')
                if not architecture or profil!=actuelle or os.environ.get('PLAYWRIGHT_HOST_PLATFORM_OVERRIDE'):
                    raise ValueError('Variante Linux du navigateur : profil explicite correspondant requis')
                revision=b.get('revisionOverrides',{}).get(profil,revision)
                result['plateforme_playwright']=profil
            nom_cache=b['name'].replace('-','_')
            dossier=cache/(nom_cache+'-'+revision)
            result[nom+'/'+dossier.name]=arbre(dossier)
    for k in ('PLAYWRIGHT_CHROMIUM_EXECUTABLE','CHROMIUM'):
        if os.environ.get(k):result[k]={'sha256':fichier(Path(os.environ[k]).resolve(strict=True))}
    if suite.get('chromium_externe'):
        chemins=[os.environ.get(k) for k in ('CHROMIUM','PLAYWRIGHT_CHROMIUM_EXECUTABLE','CHROMIUM_PATH')]
        if not all(chemins) or len({str(Path(p).resolve(strict=True)) for p in chemins})!=1:
            raise ValueError('Fournir les trois chemins du même Chromium externe ; aucun fallback')
        executable=Path(chemins[0]).resolve(strict=True)
        result['chromium_externe']={'chemin':str(executable),'sha256':fichier(executable)}
        # /usr/bin/chromium est un lanceur shell, pas le moteur exécuté.
        if executable==Path('/usr/bin/chromium'):
            moteur=Path('/usr/lib/chromium')
            result['chromium_externe']['moteur']=arbre(moteur)
    return result

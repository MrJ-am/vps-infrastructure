"""Assemblage central Audition, sans installation ni publication implicites."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from assemblage import RACINE, chemins_sources, manifeste
from frontends import cache_style, contenus, sha


def construire():
    sources = chemins_sources(); m = manifeste(); edge = m['frontends_infrastructure']['audition']
    for nom, revision in [('style', edge['revision_style']), ('signature', edge['revision_signature'])]:
        if subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=sources[nom], text=True).strip() != revision:
            raise ValueError('Producteur Audition différent du verrou : ' + nom)
        if subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=no'], cwd=sources[nom]):
            raise ValueError('Producteur Audition modifié : ' + nom)
    commun = cache_style(sources['style'], edge['revision_style'])
    env = dict(os.environ, ELM_HOME=str(RACINE / 'state/elm-home'))
    subprocess.run(['python3', str(RACINE / 'scripts/revoir-frontends.py'), '--composant', 'audition'], check=True, env=env)
    elm = sources['matheval'] / 'docs/node_modules/.bin/elm'
    formatage = sources['matheval'] / 'docs/node_modules/.bin/elm-format'
    app = RACINE / 'interface-audition'
    subprocess.run([str(formatage), str(app / 'src'), str(app / 'tests'), '--validate'], check=True)
    with tempfile.TemporaryDirectory(prefix='audition-build-', dir=RACINE / 'state') as temp:
        stage = Path(temp)
        shutil.copytree(app / 'src', stage / 'src')
        shutil.copytree(app / 'tests', stage / 'tests')
        shutil.copytree(commun / 'src', stage / 'commun')
        d = json.loads((app / 'elm.json').read_text()); d['source-directories'] = ['src', 'commun']
        (stage / 'elm.json').write_text(json.dumps(d) + '\n')
        site = stage / 'site'; site.mkdir()
        subprocess.run([str(sources['matheval'] / 'docs/node_modules/.bin/elm-test'), '--compiler', str(elm), '--seed', '20261013'], cwd=stage, check=True, env=env)
        subprocess.run([str(elm), 'make', 'src/Main.elm', '--optimize', '--output=site/elm.js'], cwd=stage, check=True, env=env)
        for n in ('index.html', 'pont.js'): shutil.copyfile(app / n, site / n)
        assets = site / 'assets/mrjam'; assets.mkdir(parents=True)
        for n in ('signature.css', 'MrJamSignature.woff2', 'EchoPoint.woff2'):
            shutil.copyfile(sources['signature'] / 'web' / n, assets / n)
        for n in ('Parisienne-Regular.ttf', 'Parisienne-OFL.txt'):
            shutil.copyfile(sources['signature'] / 'fonts' / n, assets / n)
        for n in ('animations.js', 'mathematiques.js', 'ecriture.css'):
            shutil.copyfile(commun / 'public/assets/mrjam' / n, assets / n)
        (assets / 'palette').mkdir()
        shutil.copyfile(commun / 'public/assets/mrjam/palette/Palette-Audio.svg', assets / 'palette/Palette-Audio.svg')
        katex = sources['logique'] / 'node_modules/katex'
        if json.loads((katex / 'package.json').read_text())['version'] != '0.18.7':
            raise ValueError('Moteur mathématique différent du verrou existant')
        (site / 'vendor').mkdir()
        shutil.copytree(katex / 'dist', site / 'vendor/katex')
        h = contenus(site)
        rapport = {'format': 1, 'sources': {'application': contenus(app / 'src'),
            'tests': contenus(app / 'tests'), 'bootstrap': sha((app / 'index.html').read_bytes()),
            'interop': sha((app / 'pont.js').read_bytes()), 'elm_json': sha((app / 'elm.json').read_bytes()),
            'style': edge['revision_style'], 'signature': edge['revision_signature']},
            'fichiers': h, 'ensemble_sha256': sha(json.dumps(h, sort_keys=True).encode()),
            'publication': False, 'qualification_navigateur': False}
        destination = app / 'dist'
        # Remplacer uniquement cette sortie générée ; le candidat antérieur est
        # conservé à son empreinte dans state/frontends-candidats.
        archives = RACINE / 'state/frontends-candidats'; archives.mkdir(exist_ok=True)
        candidat = archives / ('audition-' + rapport['ensemble_sha256'][:16])
        if candidat.exists():
            if contenus(candidat) != h: raise ValueError('Candidat existant différent')
        else: shutil.copytree(site, candidat)
        if destination.is_symlink(): raise ValueError('Destination liée refusée')
        if destination.exists(): shutil.rmtree(destination)
        shutil.copytree(candidat, destination)
        (RACINE / 'state/audition-construction.json').write_text(json.dumps(rapport, indent=2) + '\n')
        print(json.dumps({'audition': 'construit', 'ensemble_sha256': rapport['ensemble_sha256'], 'publication': False}))
    return destination


if __name__ == '__main__': construire()

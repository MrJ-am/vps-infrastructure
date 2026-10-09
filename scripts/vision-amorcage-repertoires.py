"""Autoriser une seule règle tmpfiles nouvelle, en conservant celles du socle."""
from pathlib import Path
import re

REGLE = 'd /var/backup/mrjam-amorcage 0700 root root -'
UNITE = 'systemd-tmpfiles-resetup.service'


def exiger(condition):
    if not condition: raise ValueError('Règles de répertoires ou unité différentes du périmètre réservé')


def verifier(ancien, nouveau, racine_store=Path('/nix/store')):
    racine_store = racine_store.resolve()
    def lire(p):
        reel = p.resolve(strict=True)
        exiger(reel.is_relative_to(racine_store) and reel.is_file() and reel.stat().st_size <= 1048576)
        return reel.read_text()
    def unite(systeme):
        texte = lire(Path(systeme)/'etc/systemd/system'/UNITE)
        exiger(len(re.findall(r'(?m)^X-Restart-Triggers=', texte)) == 1)
        return re.sub(r'(?m)^X-Restart-Triggers=[^\n]*\n?', '', texte)
    exiger(unite(ancien) == unite(nouveau))
    def configurations(systeme):
        p = Path(systeme)/'etc/tmpfiles.d'; valeurs = list(p.iterdir())
        exiger(len(valeurs) <= 256 and all(v.name.endswith('.conf') for v in valeurs))
        return {v.name:lire(v).splitlines() for v in valeurs}
    avant = configurations(ancien); apres = configurations(nouveau)
    exiger(set(avant) == set(apres))
    additions = 0
    for nom, lignes in avant.items():
        exiger(all(l.strip() != REGLE for l in lignes))
        nouvelles = apres[nom]
        ajouts = [l for l in nouvelles if l.strip() == REGLE]
        exiger(lignes == [l for l in nouvelles if l.strip() != REGLE])
        additions += len(ajouts)
    exiger(additions == 1)
    return True

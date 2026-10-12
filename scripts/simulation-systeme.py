"""Lire le format réel dry-activate, sans ignorer le préfixe 'would'."""
import re


def actions(texte):
    result={n:set() for n in ('stop','restart','reload','start')}
    formes={'stopping':'stop','restarting':'restart','reloading':'reload','starting':'start'}
    for verbe,participe,noms in re.findall(r'(?:would (stop|restart|reload|start)|\b(stopping|restarting|reloading|starting)) the following units: ([^\n]+)',texte):
        result[verbe or formes[participe]].update(re.findall(r'[A-Za-z0-9_.@:-]+\.(?:service|timer|target)',noms))
    return result


def verifier(texte,proteges):
    if 'would activate the configuration' not in texte or len(texte)>1024*1024:
        raise ValueError('Simulation absente ou hors format')
    if re.search(r'would (?:restart systemd|stop swap)',texte):
        raise ValueError('Interruption du socle annoncée')
    a=actions(texte)
    if (a['stop']|a['restart']) & set(proteges):
        raise ValueError('Arrêt ou redémarrage de service préservé annoncé')
    return a

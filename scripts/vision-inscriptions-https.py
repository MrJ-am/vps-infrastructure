"""Confirmer publiquement l'ouverture et les champs exacts de la notice."""
import importlib.util
import json
from pathlib import Path
import ssl

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('https_inscriptions', ROOT / 'scripts/vision-essai-https.py')
h = importlib.util.module_from_spec(spec); spec.loader.exec_module(h)


def verifier_notice(configuration):
    attendu = dict(responsable='Jean-Christophe Jameux', contact='RGPD@MrJ.am',
        pays_hebergement='Allemagne', version='vision-20261010',
        sauvegardes_jours=30, inscriptions_ouvertes=True)
    if not isinstance(configuration, dict) or configuration.get('mode') != 'oidc':
        raise ValueError('Configuration publique refusée')
    notice = configuration.get('notice')
    if not isinstance(notice, dict) or notice != attendu or notice.get('inscriptions_ouvertes') is not True:
        raise ValueError('Notice publique refusée')
    return dict(notice_publique_verifiee=True, inscriptions=True, coordonnees_confirmées=True)


if __name__ == '__main__':
    try:
        contexte = ssl.create_default_context(); contexte.minimum_version = ssl.TLSVersion.TLSv1_2
        import urllib.request
        opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=contexte), h.h.SansRedirection())
        code, _, corps = h.demander(opener, 'https://vision.mrj.am', '/auth/configuration')
        if code != 200: raise ValueError()
        print(json.dumps(verifier_notice(json.loads(corps))))
    except Exception:
        raise SystemExit('Notice publique d’ouverture refusée ; aucune réponse affichée.')

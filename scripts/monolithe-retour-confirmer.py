"""Finaliser un retour déjà effectué ; aucune copie, migration ou relance.

Incident constaté : Keycloak a changé de PID, alors que génération/profil,
configuration, publications et anciens services sont revenus à la référence.
Refuser tout autre écart ; consigner cette relance, sans prétendre l'annuler.
"""
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import re
import sys


def confirmer(d,stage,activer):
    plan=json.loads((d/'activation.json').read_text())
    prepare=json.loads((d/'preparation.json').read_text())
    stage.exiger(plan['phase']=='service-demarre' and not (d/'termine.json').exists(),
                 'Retour non concerné par cette réconciliation')
    actuel=stage.etat(d);avant=prepare['avant']
    stage.exiger({k:v for k,v in actuel.items() if k!='tiers_pids'}==
                 {k:v for k,v in avant.items() if k!='tiers_pids'},'Configuration de retour divergente')
    relances=[k for k in set(avant['tiers_pids'])|set(actuel['tiers_pids'])
              if avant['tiers_pids'].get(k)!=actuel['tiers_pids'].get(k)]
    stage.exiger(set(relances)<= {'keycloak'},'Autre service tiers modifié')
    stage.exiger(stage.commande(['systemctl','show','mrjam-metier','-p','MainPID','--value'],d).strip()==b'0',
                 'Serveur commun encore actif')
    for n,v in plan['unites_avant'].items():
        stage.exiger(stage.commande(['systemctl','show',n,'-p','ActiveState','--value'],d).decode().strip()==v,
                     'Ancien service non revenu à son état : '+n)
    stage.commande(['systemctl','is-active',*stage.TIERS],d)
    # Le timer ne doit plus recopier un ancien état commun sur les nouvelles
    # écritures des services historiques déjà remis en activité.
    stage.commande(['systemctl','stop','mrjam-retour-'+d.name[:12]+'.timer'],d)
    resultat={'format':1,'revision':d.name,'retour_code':True,'restauration_ancienne_sql':False,
              'derniers_etats_durables_recopies':True,'retour_deja_effectue_verifie':True,
              'nouvelles_copies_effectuees':False,'processus_tiers_relances':sorted(relances)}
    activer.ecrire(d/'retour.json',resultat)
    return resultat


def main(revision):
    if os.geteuid()!=0 or not re.fullmatch('[a-f0-9]{40}',revision):raise ValueError('Opérateur refusé')
    sys.dont_write_bytecode=True;os.umask(0o077)
    d=Path('/root/mrjam-assemblages')/revision
    spec=importlib.util.spec_from_file_location('retour_ancien',d/'payload/vps/scripts/monolithe-activer.py')
    activer=importlib.util.module_from_spec(spec);spec.loader.exec_module(activer)
    with open('/root/mrjam-assemblage.lock','a') as f:
        fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
        print(json.dumps(confirmer(d,activer.stage,activer),ensure_ascii=False))


if __name__=='__main__':main(sys.argv[1])

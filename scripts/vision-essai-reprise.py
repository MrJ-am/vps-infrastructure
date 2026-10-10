"""Dispositif de reprise locale : timer indépendant et générateur au démarrage.

Installation seulement par l'essai qualifié distinct.
"""
from pathlib import Path
import os
import re
import shlex
import subprocess
import time


CLIENTS=('nginx.service','vision.service','mrj-auth.service','keycloak.service',
    'mrjam-amorcage-identite.service','vision-bootstrap.service','vision-migrate.service',
    'vision-gestion.service','vision-cycle.service','mrjam-admission.service',
    'mrjam-fermeture.service','mrjam-courriel.service','vision-purge.service','mrjam-sauvegarde.service')


def fichiers(d,outils,unite,*,unites=Path('/run/systemd/system'),clients=CLIENTS):
    if not re.fullmatch(r'vision-essai-retour-[a-f0-9]{12}',unite):raise ValueError('Unité de reprise refusée')
    if not (0<len(clients)<=16 and all(re.fullmatch(r'[a-z0-9-]+\.service',c) for c in clients)):
        raise ValueError('Clients de reprise refusés')
    q=shlex.quote
    gate='90-vision-retour-'+d.name[:12]+'.conf'
    pre=f'''#!{outils}/bash
set -euo pipefail
umask 077
export PATH={q(str(outils)+':/run/wrappers/bin')}
d={q(str(d))}
exec 9>"$d/finalisation.lock"
flock 9
test ! -e "$d/enregistre" || exit 0
test ! -e "$d/retour-termine" || exit 0
# Fermer la finalisation AVANT de préparer les conditions : aucune fenêtre
# entre ExecStartPre et ExecStart ne peut laisser des conditions après succès.
tmp=$(mktemp "$d/marque.XXXXXXXX")
printf '1\\n' > "$tmp"
sync -f "$tmp"
mv -Tf "$tmp" "$d/retour-commence"
sync -f "$d"
for unite in {' '.join(clients)}; do
  rep={q(str(unites))}"/$unite.d"
  test ! -L "$rep"
  mkdir -p "$rep"
  test "$(stat -c %u "$rep")" = 0
  test ! -L "$rep/{gate}"
  printf '[Unit]\\nConditionPathExists=!/\\n' > "$rep/{gate}"
  sync -f "$rep/{gate}"
done
systemctl daemon-reload
'''
    service=f'''[Unit]
Description=Retour indépendant de l'essai Vision
After=postgresql.service postgresql-setup.service
Before={' '.join(clients)}
ConditionPathExists={d}/commence
ConditionPathExists=!{d}/enregistre
ConditionPathExists=!{d}/retour-termine
StartLimitIntervalSec=60
StartLimitBurst=3
[Service]
Type=exec
User=root
UMask=0077
ExecStartPre={d}/reprise-fermer.sh
ExecStart={d}/retour.sh
RuntimeMaxSec=6min
TimeoutStopSec=45s
KillMode=control-group
Restart=on-failure
RestartSec=5s
StandardOutput=journal
StandardError=null
'''
    # Le générateur ne fait que publier une unité à chemins fermés et son lien.
    # Les unités générées sont ignorées par collect_unit_changes du Nixpkgs épinglé.
    generateur=f'''#!{outils}/bash
set -euo pipefail
umask 022
export PATH={q(str(outils)+':/run/wrappers/bin')}
d={q(str(d))}
test -e "$d/commence" || exit 0
test ! -e "$d/enregistre" || exit 0
test ! -e "$d/retour-termine" || exit 0
test "$#" = 3
test -d "$1"
cp "$d/reprise.service" "$1/{unite}.service"
mkdir -p "$1/multi-user.target.wants"
ln -s "../{unite}.service" "$1/multi-user.target.wants/{unite}.service"
'''
    timer=f'''[Unit]
Description=Délai indépendant de l'essai Vision
[Timer]
OnActiveSec=15min
AccuracySec=1s
Unit={unite}.service
'''
    return {'reprise-fermer.sh':pre,'reprise.service':service,
        'reprise-generateur.sh':generateur,'reprise.timer':timer}


def qualifier(d,outils,revision,commande,prive):
    """Même générateur et fermeture, deux unités jetables ; aucun service métier."""
    jeu=d/'repetition-prive';jeu.mkdir(mode=0o700)
    unite='vision-essai-retour-'+revision[:12]
    consommateur='vision-reprise-consommateur-'+revision[:12]+'.service'
    unites=Path('/run/systemd/system')
    for n in (unite+'.service',consommateur):
        if (unites/n).exists() or (unites/n).is_symlink():raise ValueError('Unité de répétition déjà présente')
    recette=fichiers(jeu,outils,unite,clients=(consommateur,))
    recette['retour.sh']='#!'+str(outils/'bash')+'\nset -eu\n'+str(outils/'sleep')+' 1\n'+str(outils/'touch')+' '+str(jeu/'retour-simule-execute')+'\n'
    fd=os.open(jeu,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:
        for n,s in recette.items():prive.ecrire(fd,n,s)
        prive.ecrire(fd,'commence','1\n')
    finally:os.close(fd)
    for n in ('reprise-fermer.sh','reprise-generateur.sh','retour.sh'):
        (jeu/n).chmod(0o700);commande(outils/'bash','-n',jeu/n)
    sorties=[]
    for nom in ('normal','avant','apres'):
        p=jeu/nom;p.mkdir(mode=0o700);sorties.append(p)
    commande(outils/'bash',jeu/'reprise-generateur.sh',*sorties)
    genere=sorties[0]/(unite+'.service')
    lien=sorties[0]/'multi-user.target.wants'/(unite+'.service')
    if genere.read_text()!=recette['reprise.service'] or not lien.is_symlink() or lien.resolve()!=genere:
        raise ValueError('Générateur de reprise divergent')
    consommateurs='[Unit]\nAfter='+unite+'.service\nRequires='+unite+'.service\n[Service]\nType=oneshot\nExecStart='+str(outils/'touch')+' '+str(jeu/'consommateur-ne-doit-pas-executer')+'\n'
    fd=os.open(unites,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:
        prive.ecrire(fd,unite+'.service',recette['reprise.service'])
        prive.ecrire(fd,consommateur,consommateurs)
    finally:os.close(fd)
    gate='90-vision-retour-'+jeu.name[:12]+'.conf'
    try:
        commande(outils/'systemctl','daemon-reload')
        commande(outils/'systemd-analyze','verify',unites/(unite+'.service'),unites/consommateur)
        commande(outils/'systemctl','start',consommateur)
        limite=time.monotonic()+5
        while not (jeu/'retour-simule-execute').exists() and time.monotonic()<limite:time.sleep(.2)
        if not (jeu/'retour-simule-execute').is_file() or not (jeu/'retour-commence').is_file():
            raise ValueError('Retour simulé non exécuté')
        if (jeu/'consommateur-ne-doit-pas-executer').exists():raise ValueError('Client non fermé')
        if commande(outils/'systemctl','show',consommateur,'--property=ConditionResult','--value')!='no':
            raise ValueError('Condition de fermeture absente')
        if commande(outils/'systemctl','show',consommateur,'--property=ActiveState','--value')!='inactive':
            raise ValueError('Client de répétition actif')
    finally:
        for n in (consommateur,unite+'.service'):
            subprocess.run([str(outils/'systemctl'),'stop',n],capture_output=True,timeout=20)
            subprocess.run([str(outils/'systemctl'),'reset-failed',n],capture_output=True,timeout=20)
            (unites/n).unlink()
        (unites/(consommateur+'.d')/gate).unlink(missing_ok=True)
        if (unites/(consommateur+'.d')).is_dir():(unites/(consommateur+'.d')).rmdir()
        commande(outils/'systemctl','daemon-reload')
    # Une machine finalisée ne doit pas réarmer la reprise au prochain boot.
    for marque in ('enregistre','retour-termine'):
        fd=os.open(jeu,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try:prive.ecrire(fd,marque,'1\n')
        finally:os.close(fd)
        nouveau=[]
        for n in ('normal','avant','apres'):
            p=jeu/(marque+'-'+n);p.mkdir(mode=0o700);nouveau.append(p)
        commande(outils/'bash',jeu/'reprise-generateur.sh',*nouveau)
        if list(nouveau[0].iterdir()):raise ValueError('Reprise après fin refusée')
        (jeu/marque).unlink()
    return dict(reprise_generateur_reconstruit=True,reprise_ordonnancement_systemd_natif=True,
        reprise_clients_fermes_avant_demarrage=True,reprise_marques_terminales_respectees=True,
        reprise_executee_en_fixture=True,machine_redemarree=False)

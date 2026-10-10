"""Réparer le seul cycle attesté ; même génération, aucune activation ni SQL."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import stat

SOURCE_MODIFIEE = False
SERVICES = ('sshd','nginx','postgresql','vision','matheval','mrj-auth')


def exiger(condition):
    if not condition: raise ValueError('Réparation de source refusée')


def reparer(root,d,activation,qualification,candidat,prive,construction,commande):
    global SOURCE_MODIFIEE
    s = importlib.util.spec_from_file_location('entree_configuration',root/'scripts/vision-entree-configuration.py')
    m = importlib.util.module_from_spec(s); s.loader.exec_module(m)
    preuve = json.loads((root/'operations/vision-bascule-diagnostic-affine.json').read_text())
    exiger(preuve['infrastructure'] == '4cb942c7e3749fe0290426694827b61264702a39' and
        preuve['execution'] == 38040462649 and preuve['job'] == 114179522422 and
        all(preuve[k] is True for k in ('sources_exactes','entree_importe_son_lien_courant','sauvegarde_configuration_reguliere','evaluation_ignoree_pour_cycle')) and
        all(preuve[k] is False for k in ('snapshots_prives_presents','cluster_isole_present','production_modifiee')))
    essai = Path('/root/vision-identite-amorcage-essais')/activation['infrastructure']
    construction.dossier_prive(essai)
    exiger(Path('/etc/nixos/configuration.nix').is_symlink() and Path('/etc/nixos/configuration.nix').resolve() == essai/'entree.nix')
    fd = os.open(essai,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:
        ancien = prive.lire(fd,'entree.nix',16384); plan = json.loads(prive.lire(fd,'plan.json',16384))
        sauvegarde_fd = os.open('configuration-avant.nix',os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=fd)
        try:
            info = os.fstat(sauvegarde_fd)
            exiger(stat.S_ISREG(info.st_mode) and info.st_uid == 0 and info.st_nlink == 1 and
                stat.S_IMODE(info.st_mode) in (0o600,0o644) and info.st_size <= 65536)
            sauvegarde = os.read(sauvegarde_fd,65537).decode()
        finally: os.close(sauvegarde_fd)
        exiger(plan['ancien'] == activation['systeme_ancien'] and plan['nouveau'] == activation['systeme_amorcage'])
        module = Path('/root/vision-identite-amorcage-operations')/qualification['infrastructure']/'source/modules/identite-amorcage.nix'
        nouveau = m.reparer(ancien,sauvegarde,plan['entree_empreinte'],essai,module,candidat['audit']['fournisseur'])
        dest = os.open(d,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try:
            prive.ecrire(dest,'entree-avant-reparation.nix',ancien)
            prive.ecrire(dest,'entree-reproductible.nix',nouveau)
            prive.ecrire(dest,'source-reparation-intention.json',json.dumps(dict(version=1,
                avant_sha256=hashlib.sha256(ancien.encode()).hexdigest(),
                apres_sha256=hashlib.sha256(nouveau.encode()).hexdigest())))
        finally: os.close(dest)
        systeme = activation['systeme_amorcage']; outils = Path(systeme)/'sw/bin'
        def pids():
            valeurs = {n:int(commande(outils/'systemctl','show',n,'--property=MainPID','--value').strip()) for n in SERVICES}
            exiger(all(v > 0 for v in valeurs.values())); return valeurs
        def profil():
            exiger(all(str(p.resolve()) == systeme for p in (Path('/run/current-system'),Path('/nix/var/nix/profiles/system'))))
        def evaluer(entree):
            valeur = json.loads(commande('nix-instantiate','--eval','--strict','--json',root/'scripts/vision-identite-amorcage-systeme.nix',
                '--argstr','configuration',entree,'-I','nixpkgs='+candidat['audit']['nixpkgs']))
            print(json.dumps(dict(generation_source_reproduite=valeur == systeme)),flush=True)
            exiger(valeur == systeme)
        avant_pids = pids(); profil(); evaluer(d/'entree-reproductible.nix')
        if ancien != nouveau:
            temporaire = 'entree-reparation-'+d.name[:12]+'.nix'
            prive.ecrire(fd,temporaire,nouveau)
            exiger(prive.lire(fd,'entree.nix',16384) == ancien and pids() == avant_pids)
            profil()
            os.replace(temporaire,'entree.nix',src_dir_fd=fd,dst_dir_fd=fd); SOURCE_MODIFIEE = True; os.fsync(fd)
        evaluer('/etc/nixos/configuration.nix'); profil(); exiger(pids() == avant_pids)
        commande(outils/'systemctl','is-active',*SERVICES)
        rapport = dict(version=1,source_configuration_reparee=True,source_modifiee_dans_cette_operation=SOURCE_MODIFIEE,
            original_verifie_par_empreinte=True,generation_reproduite_avant_apres=True,services_non_redemarres=True,
            donnees_production_modifiees=False,activation=False)
        dest = os.open(d,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try: prive.ecrire(dest,'source-reparee.json',json.dumps(rapport))
        finally: os.close(dest)
        print(json.dumps(rapport),flush=True); return rapport
    finally: os.close(fd)

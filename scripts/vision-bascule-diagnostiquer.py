"""Projection fermée du refus be738, sans SQL ni modification de production."""
import argparse
import ast
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import stat
import subprocess

ROOT = Path(__file__).resolve().parents[1]
REFUS = 'be738f9b43ddea6edb493b6520efbbfe055fd8e7'
DOSSIER = Path('/root/vision-bascule-preparations')/REFUS
EMPREINTES = {
    'vision-bascule-preparer.py': '42e2d5ef0f2f9a989bd16e423e55095a0ded62305d3809d2a680d39e12996d3e',
    'vision-multiutilisateur-preparer.py': '79bc15f3bbd242e29aa1f9321d90adf35145adeeec28e77c833c3a3c255143d3',
    'vision-multiutilisateur-config.nix': '9d9852de5d3b691c057c082fc8eb26274f07b10d83eab3cb97c7c8b7504fdb38',
}
EXCEPTIONS = frozenset(('ValueError','KeyError','TypeError','FileNotFoundError','PermissionError',
    'OSError','TimeoutExpired','JSONDecodeError','ReadError','FilterError','InterruptedError'))
MOTIFS = {
    'archive_empreinte': r'(?m)^ValueError: Source candidate différente$',
    'archive_revision': r'(?m)^ValueError: Révision Git de l’archive différente$',
    'archive_taille': r'(?m)^ValueError: Archive trop grande$',
    'archive_irreguliere': r'(?m)^ValueError: Archive non régulière$',
    'nix_assertion': r'Failed assertions|assertion.*failed',
    'nix_option': r'The option .* does not exist|has conflicting definition',
    'nix_store': r'is not allowed to refer to a store path|is not in the Nix store|not a valid store path',
    'nix_absence': r'No such file or directory|cannot find.*nixpkgs',
    'nix_attribut': r'attribute .* missing|attribute .* not found',
    'nix_type': r'cannot coerce|expected a|while a .* was expected|attempt to call something which is not a function',
    'nix_recursion': r'infinite recursion|stack overflow',
    'nix_chemin_absent': r'path .* does not exist|file .* was not found',
    'nix_impur': r'pure evaluation mode|forbidden in pure eval',
    'nix_argument': r'called with unexpected argument|without required argument',
    'nix_securite_paquet': r'marked as insecure|unfree license|not supported on',
    'nix_permission': r'Permission denied|Operation not permitted',
    'nix_syntaxe': r'syntax error|undefined variable',
}


def exiger(condition):
    if not condition: raise ValueError('Diagnostic préparatoire refusé')


def charger(nom, chemin):
    s = importlib.util.spec_from_file_location(nom, chemin)
    m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m


def classer(texte, sources, dossier=DOSSIER):
    """Seuls les noms de fichiers/fonctions prouvés par la source sont émis."""
    texte = re.sub(r'\x1b\[[0-9;]*[A-Za-z]', '', texte)
    cadres = []
    motif = r'(?m)^  File "'+re.escape(str(dossier/'source/scripts'))+r'/([^"/\n]+)", line ([0-9]{1,6}), in ([A-Za-z_][A-Za-z_0-9]*|<module>)$'
    for nom, ligne, fonction in re.findall(motif, texte):
        if nom not in sources or not nom.endswith('.py'): continue
        n = int(ligne); arbre = ast.parse(sources[nom])
        connus = [x for x in ast.walk(arbre) if isinstance(x,(ast.FunctionDef,ast.AsyncFunctionDef)) and x.name == fonction and x.lineno <= n <= x.end_lineno]
        if 1 <= n <= len(sources[nom].splitlines()) and (connus or fonction == '<module>'):
            cadres.append(dict(fichier=nom,ligne=n,fonction=fonction))
    return dict(cadres=cadres[:16],
        exceptions=sorted(set(re.findall(r'(?m)^(?:[A-Za-z_][A-Za-z_0-9]*\.)?([A-Za-z_][A-Za-z_0-9]*):',texte)) & EXCEPTIONS),
        categories=sorted(n for n,m in MOTIFS.items() if re.search(m,texte)))


def invariants(config, activation, resume, candidat):
    return dict(generation_identique=config.get('systeme') == activation['systeme_amorcage'],
        paquet_postgresql_identique=config.get('postgres_paquet') == resume['postgres_paquet'],
        postgresql17=config.get('postgres_majeure') == '17',
        postgresql_sans_tcp=config.get('postgres_tcp') is False and config.get('postgres_ecoute') == '',
        fournisseur_identique=config.get('fournisseur_source') == candidat['audit']['fournisseur'])


def classer_oom(lignes):
    """Seuls les événements kernel OOM du processus Nix exact sont retenus."""
    dates = []
    for ligne in lignes:
        v = json.loads(ligne)
        if re.search(r'(?:Out of memory|Memory cgroup out of memory): Killed process [0-9]+ \(nix-instantiate\)',v.get('MESSAGE','')):
            date = v.get('__REALTIME_TIMESTAMP','')
            if isinstance(date,str) and re.fullmatch('[0-9]{16}',date): dates.append(int(date))
    return dict(nix_instantiate_oom=len(dates),dates_oom_microsecondes=sorted(dates)[:8])


def importe_entree_courante(texte):
    # Forme exacte produite par entree_nix, sans émettre les chemins importés.
    return bool(re.search(r'\bimports = \[\s*"/etc/nixos/configuration\.nix"\s',texte))


def main(revision):
    exiger(os.geteuid() == 0 and re.fullmatch('[a-f0-9]{40}',revision))
    d = Path('/root/vision-bascule-diagnostics')/revision
    exiger(ROOT == d/'source'); os.umask(0o077)
    prive = charger('prive_diagnostic_bascule', ROOT/'scripts/identite-preparer.py')
    construction = charger('construction_diagnostic_bascule', ROOT/'scripts/vision-identite-construire.py')
    for p in (d.parent,d,ROOT,DOSSIER.parent,DOSSIER,DOSSIER/'source',DOSSIER/'source/scripts'):
        construction.dossier_prive(p)
    def lire(p,nom,maximum=1048576):
        fd = os.open(p,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try: return prive.lire(fd,nom,maximum)
        finally: os.close(fd)
    sources = {n:lire(DOSSIER/'source/scripts',n) for n in EMPREINTES}
    exiger(all(hashlib.sha256(sources[n].encode()).hexdigest() == h for n,h in EMPREINTES.items()))
    trace = lire(DOSSIER,'diagnostic-prive.log',262144)
    projection = classer(trace,sources)
    exiger(bool(projection['cadres']))
    candidat = json.loads((ROOT/'operations/vision-multiutilisateur-candidat.json').read_text())
    activation = json.loads((ROOT/'operations/vision-identite-amorcage-activation.json').read_text())
    essai = Path('/root/vision-identite-amorcage-essais')/activation['infrastructure']
    construction.dossier_prive(essai)
    entree = lire(essai,'entree.nix',16384)
    cycle = importe_entree_courante(entree) and Path('/etc/nixos/configuration.nix').resolve() == essai/'entree.nix'
    avant = essai/'configuration-avant.nix'
    sauvegarde_reguliere = avant.is_file() and not avant.is_symlink()
    qual = json.loads((ROOT/'operations/vision-identite-amorcage-qualification.json').read_text())
    exiger(re.fullmatch('[a-f0-9]{40}',qual['infrastructure']))
    resume = json.loads(lire(Path('/root/vision-identite-amorcage-operations')/qual['infrastructure'],'evaluation-privee.json'))
    # Ne pas répéter la construction de la génération complète pour diagnostiquer
    # l’évaluation : retirer cet attribut paresseusement, avant --strict.
    expression = 'builtins.removeAttrs ((import '+str(ROOT/'scripts/vision-multiutilisateur-config.nix')+') {'+ \
        'configuration="/etc/nixos/configuration.nix"; fournisseur='+json.dumps(candidat['audit']['fournisseur'])+';}) ["systeme"]'
    # Refuser l'évaluation d'un cycle déjà visible au niveau des fichiers.
    r = None if cycle else subprocess.run(['nix-instantiate','--eval','--strict','--json','--expr',expression,
        '-I','nixpkgs='+candidat['audit']['nixpkgs']],capture_output=True,timeout=180)
    evaluation = r is not None and r.returncode == 0 and len(r.stdout) < 16384 and len(r.stderr) < 262144
    controles = invariants(json.loads(r.stdout),activation,resume,candidat) if evaluation else {}
    controles.pop('generation_identique',None)
    nix = classer(r.stderr.decode(errors='replace'),{})['categories'] if r is not None else []
    journal = subprocess.run(['journalctl','-k','--since=2026-10-10 08:30:00 UTC','--until=2026-10-10 08:53:30 UTC',
        '--lines=400','--output=json','--no-pager'],capture_output=True,timeout=10)
    journal_disponible = journal.returncode == 0 and len(journal.stdout) <= 1048576
    oom = classer_oom(journal.stdout.decode().splitlines()) if journal_disponible else {}
    style = DOSSIER/'vision/interface/style.lock.json'
    style_conforme = False
    if style.exists():
        fd = os.open(style,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
        try:
            s = os.fstat(fd); exiger(stat.S_ISREG(s.st_mode) and s.st_uid == 0 and s.st_nlink == 1 and s.st_size < 65536)
            style_conforme = json.loads(os.read(fd,65536))['revision'] == candidat['style']
        finally: os.close(fd)
    disponible = next(int(l.split()[1]) for l in Path('/proc/meminfo').read_text().splitlines() if l.startswith('MemAvailable:'))
    espace = os.statvfs('/var/lib/postgresql')
    rapport = dict(version=1,infrastructure=revision,refus=REFUS,sources_exactes=True,**projection,
        evaluation_legere_reussie=evaluation,invariants=controles,categories_nix=nix,
        evaluation_code=r.returncode if r is not None and -64 <= r.returncode <= 255 else None,
        entree_importe_son_lien_courant=cycle,sauvegarde_configuration_reguliere=sauvegarde_reguliere,
        evaluation_ignoree_pour_cycle=cycle,
        journal_kernel_disponible=journal_disponible,**oom,
        style_extrait_conforme=style_conforme,configuration_sauvee=(DOSSIER/'systeme-actif.json').exists(),
        memoire_3gio=disponible >= 3*1024*1024,disque_2gio=espace.f_bavail*espace.f_frsize >= 2*1024**3,
        cluster_isole_present=(Path('/var/lib/postgresql')/('vision-bascule-'+REFUS[:12])).exists(),
        snapshots_prives_presents=any((DOSSIER/n).exists() for n in ('historique-prive.json','acl-avant.json','vision.dump.age','identite.dump.age')),
        preparation_achevee=(DOSSIER/'preparation.json').exists(),production_modifiee=False,activation=False,inscriptions=False)
    print(json.dumps(rapport),flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('revision'); a = p.parse_args()
    try: main(a.revision)
    except Exception:
        print(json.dumps(dict(diagnostic_bascule_refuse=True,production_modifiee=False)),flush=True)
        raise SystemExit(1)

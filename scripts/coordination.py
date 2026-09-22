#!/usr/bin/env python3
"""Registre Org partagé : lecture ciblée, accusés explicites, archivage vérifié."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import uuid

RACINE = Path(__file__).resolve().parents[1]
ETATS = {'TODO', 'LU', 'BLOQUE', 'DONE'}
CHAMPS = {'ID', 'EMETTEUR', 'PORTEE', 'DESTINATAIRES', 'CREE_LE', 'CONSOLIDATION'}
ACCUSE = {'LU_SHA256', 'LU_LE', 'CONTEXTE', 'PREUVE'}


def exiger(condition, message):
    if not condition:
        raise ValueError(message)


def maintenant():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def date_valide(texte):
    try:
        date = datetime.fromisoformat(texte)
        return date.utcoffset() is not None and date.utcoffset().total_seconds() == 0
    except ValueError:
        return False


def tiroir(texte):
    lignes = texte.splitlines(keepends=True)
    exiger(len(lignes) > 2 and lignes[1] == ':PROPERTIES:\n', 'Tiroir PROPERTIES absent')
    champs = {}
    for i, ligne in enumerate(lignes[2:], 2):
        if ligne == ':END:\n':
            return champs, ''.join(lignes[i + 1:])
        match = re.fullmatch(r':([A-Z_0-9]+): (.+)\n', ligne)
        exiger(match is not None, 'Propriété Org invalide')
        cle, valeur = match.groups()
        exiger(cle not in champs, 'Propriété dupliquée : ' + cle)
        champs[cle] = valeur
    raise ValueError('Tiroir non fermé')


def proprietes(champs):
    return ':PROPERTIES:\n' + ''.join(f':{k}: {v}\n' for k, v in champs.items()) + ':END:\n'


def decouper(texte):
    blocs = re.split(r'(?m)(?=^\* )', texte)
    return blocs[0], blocs[1:]


def analyser(bloc, projets):
    parties = re.split(r'(?m)(?=^\*\* )', bloc)
    entete = parties[0]
    champs, corps = tiroir(entete)
    exiger(set(champs) == CHAMPS, 'Champs de message inattendus')
    identifiant = champs['ID']
    exiger(re.fullmatch(r'[a-z0-9][a-z0-9-]{2,99}', identifiant), 'ID invalide')
    exiger(len(entete) <= 4000 and corps.strip(), identifiant + ' : corps absent ou trop long')
    exiger(not re.search(r'(?m)^\*', corps), 'Niveaux Org réservés aux messages/réponses')
    destinataires = champs['DESTINATAIRES'].split()
    exiger(destinataires and len(set(destinataires)) == len(destinataires), 'Destinataires invalides')
    exiger(set(destinataires) <= projets.keys(), 'Projet inconnu')
    exiger(champs['EMETTEUR'] in destinataires, 'Émetteur absent des destinataires')
    exiger(champs['PORTEE'] in {'globale', 'ciblee'}, 'Portée invalide')
    exiger(date_valide(champs['CREE_LE']), 'Date de création invalide')
    empreinte = hashlib.sha256(entete.encode()).hexdigest()
    reponses = {}
    for partie in parties[1:]:
        match = re.fullmatch(r'\*\* (TODO|LU|BLOQUE|DONE) ([a-z0-9-]+)\n', partie.splitlines(keepends=True)[0])
        exiger(match is not None, 'Sous-titre de réponse invalide')
        etat, projet = match.groups()
        exiger(projet in destinataires and projet not in reponses, 'Réponse inattendue ou dupliquée')
        accuse, commentaire = tiroir(partie)
        exiger(set(accuse) == ACCUSE, 'Champs d’accusé inattendus')
        exiger(len(partie) <= 2000 and not re.search(r'(?m)^\*', commentaire), 'Réponse trop longue ou structurée incorrectement')
        if etat == 'TODO':
            exiger(all(v == '-' for v in accuse.values()), 'TODO porte un ancien accusé')
        else:
            exiger(accuse['LU_SHA256'] == empreinte, identifiant + ' : accusé périmé pour ' + projet)
            exiger(date_valide(accuse['LU_LE']), 'Date de lecture invalide')
            exiger(datetime.fromisoformat(accuse['LU_LE']) >= datetime.fromisoformat(champs['CREE_LE']), 'Lecture antérieure au message')
            depot = re.escape(projets[projet]['depot'])
            exiger(re.fullmatch(depot + r'@[0-9a-f]{40}', accuse['CONTEXTE']), 'Contexte dépôt@commit invalide')
        if etat == 'BLOQUE':
            exiger(commentaire.strip(), 'Blocage non expliqué')
        if etat == 'DONE':
            exiger(accuse['PREUVE'] != '-', 'DONE sans preuve')
            exiger(not re.search(r'\[(?: |-)\]', commentaire), 'DONE avec tâches ouvertes')
        reponses[projet] = {'etat': etat, 'champs': accuse, 'commentaire': commentaire}
    exiger(set(reponses) == set(destinataires), identifiant + ' : réponse destinataire absente')
    return {'bloc': bloc, 'entete': entete, 'champs': champs, 'empreinte': empreinte, 'reponses': reponses}


def charger(racine):
    dossier = racine / 'coordination'
    projets = json.loads((dossier / 'projets.json').read_text())
    exiger(projets and all(re.fullmatch('[a-z0-9-]+', p) for p in projets), 'Registre projets invalide')
    for projet in projets.values():
        exiger(set(projet) == {'depot', 'branche'}, 'Champs projet invalides')
        exiger(re.fullmatch(r'MrJ-am/[A-Za-z0-9_.-]+', projet['depot']), 'Dépôt invalide')
        exiger(isinstance(projet['branche'], str) and projet['branche'], 'Branche absente')
    contrats = (dossier / 'CONTRATS.org').read_text()
    debut, blocs = decouper((dossier / 'REGISTRE.org').read_text())
    exiger(len(debut) <= 6000 and len(contrats) <= 8000, 'Synthèse ou protocole trop longs')
    ancres = set(re.findall(r'(?m)^:CUSTOM_ID: (\S+)$', contrats))
    messages, archives, ids = [], [], set()
    sources = [(None, b) for b in blocs]
    for fichier in sorted((dossier / 'archives').glob('*.org')):
        prefixe, contenu = decouper(fichier.read_text())
        exiger(not prefixe and len(contenu) == 1, 'Archive mal formée')
        sources.append((fichier, contenu[0]))
    for fichier, bloc in sources:
        message = analyser(bloc, projets)
        identifiant = message['champs']['ID']
        exiger(identifiant not in ids, 'ID dupliqué : ' + identifiant)
        ids.add(identifiant)
        consolidation = message['champs']['CONSOLIDATION']
        exiger(consolidation in {'a-faire', 'sans-objet'} or consolidation in {'CONTRATS.org#' + a for a in ancres}, 'Consolidation inconnue')
        if fichier:
            exiger(fichier.stem == identifiant and eligible(message), 'Archive prématurée ou mal nommée')
            archives.append(message)
        else:
            if message['champs']['PORTEE'] == 'globale':
                exiger(set(message['reponses']) == set(projets), 'Message global sans tous les projets actifs')
            messages.append(message)
    return projets, contrats, debut, messages, archives


def eligible(message):
    return message['champs']['CONSOLIDATION'] != 'a-faire' and all(r['etat'] == 'DONE' for r in message['reponses'].values())


def verifier_transition(racine, base, messages, archives, projets):
    def git(*arguments):
        return subprocess.run(['git', '-C', str(racine), *arguments], check=True, capture_output=True, text=True).stdout
    chemins = git('ls-tree', '-r', '--name-only', base).splitlines()
    presents = {m['champs']['ID']: m for m in messages + archives}
    if 'coordination/REGISTRE.org' in chemins:
        _, anciens = decouper(git('show', base + ':coordination/REGISTRE.org'))
        for bloc in anciens:
            ancien = analyser(bloc, projets)
            identifiant = ancien['champs']['ID']
            exiger(identifiant in presents, 'Message disparu : ' + identifiant)
            actuel = presents[identifiant]
            exiger(set(ancien['reponses']) <= set(actuel['reponses']), 'Destinataire retiré : ' + identifiant)
            if ancien['empreinte'] != actuel['empreinte']:
                exiger(all(r['etat'] == 'TODO' for r in actuel['reponses'].values()), 'Modification de fond sans nouvelle lecture')
            if actuel in archives:
                exiger(ancien['entete'] == actuel['entete'], 'Contenu modifié pendant archivage')
    for chemin in chemins:
        if chemin.startswith('coordination/archives/') and chemin.endswith('.org'):
            actuel = racine / chemin
            exiger(actuel.is_file() and actuel.read_text() == git('show', base + ':' + chemin), 'Archive modifiée : ' + chemin)


def enregistrer(racine, debut, messages):
    chemin = racine / 'coordination/REGISTRE.org'
    temporaire = chemin.with_suffix('.org.tmp')
    temporaire.write_text(debut + ''.join(m['bloc'] for m in messages))
    temporaire.replace(chemin)


def repondre(message, projet, etat, empreinte, contexte, preuve, commentaire, projets):
    exiger(projet in message['reponses'], 'Projet non destinataire')
    exiger(empreinte == message['empreinte'], 'Le message a changé : le relire')
    exiger(etat in ETATS - {'TODO'}, 'État de réponse invalide')
    exiger('\n' not in contexte + preuve, 'Propriété multiligne interdite')
    parties = [message['entete']]
    for nom, reponse in message['reponses'].items():
        if nom == projet:
            reponse = {'etat': etat, 'champs': dict(zip(
                ['LU_SHA256', 'LU_LE', 'CONTEXTE', 'PREUVE'],
                [empreinte, maintenant(), contexte, preuve])),
                'commentaire': reponse['commentaire'] if commentaire is None else commentaire.strip() + '\n\n'}
        parties.append(f"** {reponse['etat']} {nom}\n" + proprietes(reponse['champs']) + reponse['commentaire'])
    return analyser(''.join(parties), projets)


def archiver(racine, debut, messages, appliquer):
    selection = [m for m in messages if eligible(m)]
    if appliquer and selection:
        dossier = racine / 'coordination/archives'
        dossier.mkdir(exist_ok=True)
        for message in selection:
            chemin = dossier / (message['champs']['ID'] + '.org')
            with chemin.open('x') as fichier:
                fichier.write(message['bloc'])
        enregistrer(racine, debut, [m for m in messages if m not in selection])
    return [m['champs']['ID'] for m in selection]


def principal():
    analyseur = argparse.ArgumentParser(description=__doc__)
    analyseur.add_argument('--racine', type=Path, default=RACINE)
    commandes = analyseur.add_subparsers(dest='commande', required=True)
    verif = commandes.add_parser('verifier')
    verif.add_argument('--base', help='Commit Git précédent pour interdire pertes et archives modifiées')
    lecture = commandes.add_parser('lire')
    lecture.add_argument('projet')
    reponse = commandes.add_parser('repondre')
    reponse.add_argument('identifiant')
    reponse.add_argument('projet')
    reponse.add_argument('--etat', required=True, choices=['LU', 'BLOQUE', 'DONE'])
    reponse.add_argument('--empreinte', required=True)
    reponse.add_argument('--contexte', required=True)
    reponse.add_argument('--preuve', default='-')
    reponse.add_argument('--commentaire')
    archive = commandes.add_parser('archiver')
    archive.add_argument('--appliquer', action='store_true')
    nouveau = commandes.add_parser('creer')
    nouveau.add_argument('--emetteur', required=True)
    nouveau.add_argument('--portee', required=True, choices=['globale', 'ciblee'])
    nouveau.add_argument('--destinataires', nargs='+', default=[])
    nouveau.add_argument('--titre', required=True)
    nouveau.add_argument('--corps', required=True, type=Path, help='Fichier texte contenant impact, actions et références')
    nouveau.add_argument('--consolidation', default='a-faire')
    args = analyseur.parse_args()
    projets, contrats, debut, messages, archives = charger(args.racine)
    if args.commande == 'verifier':
        if args.base:
            verifier_transition(args.racine, args.base, messages, archives, projets)
        print(f'{len(messages)} messages ouverts ; {len(archives)} archives conformes.')
        if len(messages) > 20:
            print('ATTENTION : plus de 20 messages ouverts ; traiter les blocages sans effacer.')
    elif args.commande == 'lire':
        exiger(args.projet in projets, 'Projet inconnu')
        print(contrats)
        selection = [m for m in messages if args.projet in m['reponses']]
        for message in selection:
            print(message['entete'], end='')
            print('Empreinte à acquitter : ' + message['empreinte'])
            for projet, reponse in message['reponses'].items():
                print(f"- {projet} : {reponse['etat']}")
                if projet == args.projet or reponse['etat'] == 'BLOQUE':
                    print(reponse['commentaire'].strip())
        print(f'{len(selection)} messages pertinents. Aucun accusé écrit par cette lecture.')
    elif args.commande == 'repondre':
        selection = [m for m in messages if m['champs']['ID'] == args.identifiant]
        exiger(len(selection) == 1, 'Message actif introuvable')
        ancien = selection[0]
        neuf = repondre(ancien, args.projet, args.etat, args.empreinte, args.contexte, args.preuve, args.commentaire, projets)
        enregistrer(args.racine, debut, [neuf if m is ancien else m for m in messages])
        print('Réponse locale enregistrée ; vérifier, publier sans forcer et relire le main distant.')
    elif args.commande == 'archiver':
        print(json.dumps(archiver(args.racine, debut, messages, args.appliquer), ensure_ascii=False))
    elif args.commande == 'creer':
        destinataires = sorted(projets if args.portee == 'globale' else set(args.destinataires + [args.emetteur]))
        exiger(args.emetteur in projets and '\n' not in args.titre, 'Émetteur ou titre invalide')
        ancres = {'CONTRATS.org#' + a for a in re.findall(r'(?m)^:CUSTOM_ID: (\S+)$', contrats)}
        exiger(args.consolidation in {'a-faire', 'sans-objet'} | ancres, 'Consolidation invalide')
        identifiant = datetime.now(timezone.utc).strftime('%Y%m%d') + '-' + args.emetteur + '-' + uuid.uuid4().hex[:12]
        champs = dict(zip(['ID', 'EMETTEUR', 'PORTEE', 'DESTINATAIRES', 'CREE_LE', 'CONSOLIDATION'], [identifiant, args.emetteur, args.portee, ' '.join(destinataires), maintenant(), args.consolidation]))
        bloc = '* ' + args.titre + '\n' + proprietes(champs) + args.corps.read_text().strip() + '\n\n'
        for projet in destinataires:
            bloc += f'** TODO {projet}\n' + proprietes(dict.fromkeys(['LU_SHA256', 'LU_LE', 'CONTEXTE', 'PREUVE'], '-')) + '\n'
        messages.append(analyser(bloc, projets))
        enregistrer(args.racine, debut, messages)
        print(identifiant)


if __name__ == '__main__':
    try:
        principal()
    except (ValueError, OSError, subprocess.CalledProcessError) as erreur:
        print('Erreur : ' + str(erreur), file=sys.stderr)
        sys.exit(1)

# Coordination entre projets

Le point d'entrée est [coordination/REGISTRE.org](../coordination/REGISTRE.org),
sur `MrJ-am/vps-infrastructure`, branche `main`. Son début documente intégralement
le format. [CONTRATS.org](../coordination/CONTRATS.org) conserve la synthèse durable.
Les identifiants `vps`, `memoire`, `vision`, `logique`, `style`, `signature` sont
définis dans [projets.json](../coordination/projets.json).

Depuis une copie fraîche de l'infrastructure, avec Python 3.10 ou ultérieur :

```sh
python3 scripts/coordination.py lire vision
python3 scripts/coordination.py creer --emetteur vision --portee ciblee \
  --destinataires vps --titre 'Faire évoluer le contrat du service' \
  --corps /chemin/message.txt --consolidation a-faire
python3 scripts/coordination.py repondre IDENTIFIANT vision --etat LU \
  --empreinte EMPREINTE_AFFICHEE --contexte MrJ-am/vision@COMMIT_COMPLET
python3 scripts/coordination.py repondre IDENTIFIANT vision --etat DONE \
  --empreinte EMPREINTE_AFFICHEE --contexte MrJ-am/vision@COMMIT_COMPLET \
  --preuve 'Lien du commit ou contrôle attestant la fin du travail'
python3 scripts/coordination.py verifier
python3 scripts/coordination.py archiver
```

Remplacer les majuscules par les valeurs réellement lues ; la dernière commande
est une simulation. Ajouter `--appliquer` pour déplacer les messages éligibles.
Lire n'acquitte jamais automatiquement. Les commentaires servent à expliquer les
blocages et les résultats ; une nouvelle demande à un autre projet doit figurer
dans le corps d'un nouveau message, couvert par son empreinte.

L'outil ne contacte ni GitHub ni le VPS. En Work, les mêmes fichiers peuvent être
lus et modifiés par le connecteur GitHub, sans clone ni SSH. Télécharger ensemble
le script, les contrats, les projets et le registre au même commit, puis vérifier
localement les fichiers modifiés. Pour un archivage, fournir aussi les archives
nécessaires à la vérification ; la CI contrôle toujours l'ensemble du dépôt.

Une écriture est livrée uniquement après intégration sur `main`. Préparer un
commit sur branche dédiée basé sur le dernier `main`, avec seulement les fichiers
de coordination, puis avancer `main` sans force. Si la référence a changé,
repartir du nouveau parent et réappliquer uniquement sa réponse. Ne pas intégrer
une branche applicative ou une ancienne configuration VPS pour publier un message.
Relire ensuite la version distante et le résultat de la CI `coordination.yml`.

La CI contrôle les accusés, les destinataires, les tâches, les archives immuables
et les disparitions depuis le commit précédent. Sur `main`, elle archive ensuite
les échanges entièrement traités. Elle n'a aucun accès à `vps-production` et ne
déploie rien. L'archivage est conservateur : un échec d'entretien laisse le message
actif ; il ne remplace jamais un accusé manquant. Pas d'effacement à échéance.

À chaque nouvelle session, relire aussi le `AGENTS.md` de la branche par défaut,
même en travaillant sur une branche ancienne. À la création d'un projet, reprendre
le bloc « Coordination commune » d'un participant en remplaçant son identifiant,
l'inscrire dans `projets.json` et lui adresser un message d'accueil. Propager la
consigne aux branches de travail réellement actives ; les autres la retrouvent
par la branche par défaut. Les clones anciens et les conversations déjà actives
ne reçoivent aucune notification magique : ils appliquent la règle à leur reprise.

Les accusés sont des attestations explicites d'agents identifiés par projet et
révision, pas une preuve de compréhension. Les contrôles réduisent les oublis sans
pouvoir détecter tout impact sémantique oublié par l'auteur. La revue de l'impact,
les tests applicatifs et les autorisations de publication restent nécessaires.

# Essai réservé de l'identité

La génération est réellement construite :
[Actions 37941066602](https://github.com/MrJ-am/vps-infrastructure/actions/runs/37941066602),
opérateur `765ce372ccd61ad623e33bf8bb476a5c3be21fba`, job `113855262092`.
Le rapport exact `operations/vision-identite-amorcage-qualification.json`
et les rapports root de cette préparation sont exigés avant l'essai.
Génération : `/nix/store/39b7g3x42qp2q58idfv7nl6w5j3y78np-nixos-system-nixos-26.05.8639.c5c4a43b0e80`.
Unités/hôtes/PostgreSQL de production conservés ; un propriétaire historique,
quatorze tables inventoriées en lecture seule sans contenu ; six services,
nouvelle SSH et25HTTP/TLS réussis. Aucun switch ou compte humain à cette étape.

## Préparation et lancement

Le contrôle des répertoires est attesté par la reprise37958354048,
opérateur88dc20580cbfc3e790eb19f366794b8b94f87e9d : simulation, copie locale
et répétition du timer passent. Le worker demandé ne fournit pas de résultat
complet dans les dix minutes ; le retour est terminé et les25sites passent.
L'identité n'est pas enregistrée. Diagnostiquer ce processus arrêté via
le point d'entrée unique avant toute reprise adaptée à l'état privé laissé.

Le [point d'entrée unique](VISION-MISE-EN-SERVICE.md) appelle
`vision-identite-amorcage-activer.yml` comme étape réutilisable. Demande dédiée
sur `operations/vision` ou lancement de secours sur main, vps-production,
CI du commit opérateur exact et exclusion vps-administration. Il ne reprend
pas les anciennes migrations et ne modifie ni canal Nixpkgs ni SQL de Vision.

Le contrôleur exige les preuves root privées sans lien ou droits faibles,
le même socle, les PID essentiels et le port8085 libre. Un cluster d'amorçage
préexistant bloque : après un échec, auditer sa reprise sans l'effacer.
L'import privé est vérifié sans rotation. Seul le credential technique
amorcage-admin.secret est provisionné hors store, root0600,43caractères
aléatoires avec fin de ligne. Ce compte technique n'est pas le propriétaire
et ne donne aucun droit d'administration Vision.

Une entrée réversible importe la configuration à son chemin réel et le module
préparé, avec le même fournisseur storePath. Son évaluation doit reproduire
exactement la génération construite. L'entrée originale est conservée,
l'ancienne génération reçoit une racine GC. Le dry-activate reste root privé ;
toute interruption du socle ou modification d'un service étranger bloque.
L'arrêt de `systemd-tmpfiles-resetup.service` est admis seulement après
comparaison des fichiers immuables : une unique règle ajoutée crée
`/var/backup/mrjam-amorcage` root0700 ; tous les fichiers/règles antérieurs
restent identiques. Son unité est identique sauf le déclencheur de configuration.
Son rechargement ou redémarrage annoncé demeure un refus. Le contrôleur
classe automatiquement les échecs, sans recopier de journal privé.
Une copie Vision age locale et une répétition effective de timer privé sont
exigées avant d'armer le retour. Cette copie ne prouve pas un déchiffrement.

## Essai et retour

Le timer autonome est armé à quinze minutes avant le worker systemd indépendant
de SSH, limité à dix minutes. Le worker exécute le seul candidat construit avec
switch-to-configuration test ; entrée et démarrage restent initiaux. Ses
sorties/diagnostics restent root privés. Le retour n'a besoin ni de réseau,
Python, candidat ou SQL : verrou bref, arrêt du worker, restauration de l'entrée
et du profil, boot/test de l'ancienne génération et contrôles des six services.
Un retour terminé devient inopérant pour ne pas annuler une opération ultérieure.

Contrôles locaux : générations, PID et unités essentiels conservés,
release/fournisseur Vision identiques, unités actives, DynamicUser non root,
confinement systemd et8085 uniquement sur127.0.0.1 ; PostgreSQL privé17 UTF-8
sans TCP/peer, root refusé comme keycloak et rôle sans privilèges/mot de passe.
L'API locale vérifie realm/politiques/clients/redirections/version/SPI et
absence de personne. Le token et les réponses restent en mémoire privée.
Keycloak peut masquer le mot de passe SMTP : paramètres publics comparés et
masquage accepté, sans nouveau test ou envoi SMTP. Une copie d'identité age
root0600 est exigée après le démarrage.

Le runner vérifie nouvelle SSH,25sites, certificat réel log.mrj.am, issuer
et endpoints. Forwarded/X-Forwarded falsifiés doivent être sans effet.
Master/admin, santé/métriques et enregistrement dynamique doivent répondre404 ;
clés publiques et sources AGPL disponibles. Aucun compte ou jeton utilisé
par ces sondes publiques.

## Enregistrement et limites

Après les contrôles publics, la finalisation prend le même verrou, refuse tout
échec/retour commencé, recontrôle l'essai et l'entrée originale, remplace
atomiquement l'entrée et enregistre seulement le démarrage réservé. Le marqueur
durable neutralise le retour après ces contrôles, puis le timer est retiré.
Toute erreur préalable laisse le retour agir ; le workflow le demande aussi
immédiatement si SSH fonctionne. Les sites sont contrôlés même après échec.

Rapport public : révisions, chemins store et booléens ; artefact14jours.
Credentials/diagnostics/copies restent sur le VPS. Copie age locale ne prouve
ni possession de clé privée ni sauvegarde extérieure. Après une réussite,
l'ancien vérificateur refusera à juste titre cette nouvelle génération : préparer
un nouvel audit depuis la preuve d'amorçage, sans contourner l'ancien garde.
Vision garde son mode actuel. Enrôlement privé du propriétaire/email/MFA,
retrait technique et association iss/sub restent distincts ; inscriptions
et préconditions du mode commun fausses.

## Qualification

Le script de retour est exécuté avec profils de fixture et flock : restauration,
course avec finalisation, refus après retour et double déclenchement.
Tests dry-activate/credential/preuves/HTTP (issuer falsifié, redirection,
clé privée et admin public refusés). Le test Nix compare l'entrée persistante
à l'expression préparée. Le contrôle API local est aussi exécuté sur le vrai
Keycloak26.7.3/PostgreSQL17 dans des conteneurs sans réseau. Ces tests ne prouvent
pas systemd/ACME/HTTPS sur le VPS : seule une exécution Actions identifiée les atteste.

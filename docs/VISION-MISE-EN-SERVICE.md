# Mise en service Vision : un seul point d'entrée

Depuis le 9 octobre 2026, le propriétaire ne sert plus de relais entre chaque
contrôle technique. L'agent prépare, teste, demande et suit les opérations avec
[Vision — mise en service suivie](../.github/workflows/vision-mise-en-service.yml).
Le lancement manuel reste un secours, sur `main`, sans saisie de paramètres.

## Déclencher depuis les outils GitHub

Après intégration et réussite de la CI du commit **exact**, faire avancer la
branche `operations/vision` à ce commit, sans forcer, avec une comparaison de
son ancienne référence. Si elle n'existe pas, la créer depuis le parent du
commit intégré, puis l'avancer : une simple création de référence ne vaut pas
push et n'est pas une preuve de lancement. Lire ensuite le signal Actions
`Vision — demande d'opération`, puis l'exécution administrative `workflow_run`,
son SHA, les étapes et le rapport.

Cette branche contient exactement le code intégré, sans fichier de commandes,
adresse, mot de passe ou jeton. Elle sert de demande de lancement. Un push sur
`main`, une PR, un fork ou une autre branche ne déclenche pas cette opération.
Le signal n'extrait aucun code et ne reçoit aucun credential. Le workflow
administratif est chargé par GitHub depuis la branche par défaut et extrait
explicitement `main` : du code placé seulement sur la branche de demande ne
peut pas administrer le VPS. Le programme refuse un signal d'un autre dépôt,
d'un autre workflow ou dont le commit diffère du `main` actuel. Il exige la CI
réussie de ce commit avant tout credential VPS, puis revérifie la demande dans
l'étape réservée. La CI complète n'est pas répétée sur la branche de demande.

Les opérations restent exécutées depuis les runners, avec la clé existante,
la clé d'hôte épinglée, `vps-production` et l'exclusion `vps-administration`.
Aucun SSH depuis Work, aucun accès administratif supplémentaire et aucune
commande distante paramétrable. Publier du code et demander une opération
restent deux actions distinctes.

## Avancement et interventions

| Phase | Situation au regroupement | Suite |
|---|---|---|
| Courriels, restauration isolée, paquet et composants | Qualifications VPS réussies, références dans les documents correspondants | Réutiliser les preuves et vérifier les préconditions |
| Génération réservée | Construite réellement par Actions `37941066602` ; aucun service activé | Essai, retour autonome, contrôles et enregistrement dans un même enchaînement |
| Compte commun du propriétaire | Aucun compte humain créé | Préparer et qualifier l'enrôlement privé, puis demander au propriétaire son mot de passe et son second facteur |
| Rattachement historique et bascule Vision | Non exécutés | Ajouter une phase qualifiée à ce même point d'entrée ; l'agent la déclenchera et la suivra |
| Invitations à des tiers | Fermées | Vérifier séparément les préconditions juridiques et de sauvegarde avant ouverture |

Le premier enchaînement appelle la recette réservée déjà préparée : lecture
des preuves privées et du socle, copie locale chiffrée, simulation, répétition
du timer, retour autonome armé, essai indépendant de SSH, contrôles privés,
25 sondes HTTP/TLS et nouvelle SSH, HTTPS d'identité, puis enregistrement.
Les qualifications de construction précédentes ne sont pas refaites.

La phase courante vient uniquement de `operations/vision-mise-en-service.json`
sur le main qualifié : valeurs `amorcage` ou `diagnostic`, sans paramètre libre.
Le diagnostic lit seulement les journaux privés de la tentative identifiée,
classe les refus et revérifie le socle. Il ne modifie ni génération ni base.
Les phases restent des jobs explicites du même point d'entrée.

Le déclenchement autonome est attesté par le signal `37953863382` puis
[l'exécution 37953882332](https://github.com/MrJ-am/vps-infrastructure/actions/runs/37953882332).
Elle s'arrête pendant la simulation, avant l'essai ; l'entrée candidate
reproduit bien la génération construite, le contrôle final du socle et les
25 sondes passent. Le refus sera diagnostiqué par l'agent via ce même point
d'entrée, sans solliciter un nouveau lancement du propriétaire.

Le diagnostic `37955815952` établit l'arrêt prévu de
`systemd-tmpfiles-resetup.service`, d'une unité ACME et le redémarrage de Nginx,
avec aucune unité inconnue ; socle, six services/nouvelle SSH et25sondes passent.
La reprise ajoute un contrôle strict des répertoires avant d'autoriser ce seul
arrêt. Les règles anciennes et la commande de l'unité doivent être conservées ;
seule la création root0700 du répertoire de sauvegarde réservé est admise.
Les prochains refus seront aussi classés automatiquement dans l'exécution.

Le résumé Actions explique l'avancement et la suite ; les rapports ne
contiennent que références et booléens. Un enregistrement déjà terminé pour
le même opérateur est recontrôlé, sans nouvel essai ni rotation de secret.
Une préparation entamée ou un essai échoué s'arrête pour diagnostic : aucune
boucle de relance, nettoyage de données ou réparation automatique.

Ce regroupement n'affirme pas que l'enrôlement ou la bascule sont déjà
implémentés dans l'orchestrateur. Ajouter ces phases demande leurs contrôles
et preuves propres, pas une nouvelle série de clics du propriétaire.
Le garde `preconditionsValidees` du mode commun reste fermé. Vision conserve
ses données et accès historiques pendant l'amorçage ; aucun autre outil ne
change de comptes, routage, release ou style.

## Retour et preuves

La [recette réservée](IDENTITE-AMORCAGE-ESSAI.md) conserve son retour autonome,
son verrou et son marqueur durable. Le workflow appelant possède l'exclusion
globale ; l'appelé n'en reprend pas une seconde, ce qui bloquerait son propre
parent. Sur échec, les contrôles et le retour restent visibles dans l'exécution.
Un succès CI local ne prouve jamais une activation VPS. Consigner l'URL, le
commit et les contrôles réels après chaque opération réussie.

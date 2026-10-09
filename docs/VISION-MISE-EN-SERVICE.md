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
| Génération réservée | Construite réellement par Actions `37941066602` ; essais retournés, génération non enregistrée | Identifier le refus du service d'identité avant toute reprise |
| Compte commun du propriétaire | Aucun compte humain créé | Qualifier l'enrôlement privé, puis faire choisir le mot de passe et configurer le second facteur sur la page sécurisée ; aucun secret en conversation |
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

La reprise `37958354048`, commit88dc20580cbfc3e790eb19f366794b8b94f87e9d,
passe réellement ce contrôle, simulation, copie et répétition du timer. Le
worker est demandé avec le retour armé ; aucun résultat local complet n'arrive
dans les dix minutes. Le retour rétablit le socle et les25sondes passent.
Le diagnostic du même point d'entrée exige maintenant une tentative retournée
et un worker arrêté ; il classe aussi le journal privé et les états systemd.
Aucune boucle de relance ou suppression de cluster n'est autorisée.

Le diagnostic `37961581194` confirme un worker arrêté sans étape atteinte ni
cluster privé créé, socle et25sites conservés. L'attribut `self.worker` masque
la méthode à appeler : le contrôle de non-masquage échoue sur l'ancien code.
L'attribut devient `unite_essai`. Avant le prochain essai, le diagnostic doit
retrouver le TypeError à cet appel précis dans la seule tentative88dc retournée,
sans autre cause connue, étape engagée ou cluster présent. Il refuse toute
divergence ; la reprise qualifiée utilise un nouveau dossier de tentative,
avec la même génération et le retour autonome inchangé.

Cette preuve de dispatch est réellement passée dans `37963555297`. Le worker
corrigé démarre, mais une commande refuse la poursuite ; le retour rétablit
le socle et les25sites passent. Le diagnostic normal examine maintenant cette
seule tentativef9 retournée, avec cadres Python limités à son code connu et
états/journaux du namespace identite classés. L'ancienne preuve88dc reste
distincte et inchangée pour le contrôle de reprise antérieur. Aucun argument,
chemin privé, extrait ou donnée métier n'est transmis.

Le diagnostic `37966437838` refuse sa lecture complète ; six services et les
25sites sont vérifiés après ce refus. Un relevé secondaire indisponible doit
être marqué comme tel, sans masquer les cadres/classifications principales.
La sous-étape d'un refus est un nom fermé ; aucun message d'exception privé
ne sort. Le socle, le retour durable et l'arrêt du worker restent obligatoires.
Une donnée absente n'est jamais une preuve autorisant une reprise.

Le relevé `37967591960` établit la présence du cluster et l'étape
`essai_generation` avant le retour. Le contrôleur refuse toujours une reprise
sur ce cluster. Le diagnostic complémentaire lit les journaux techniques dans
les namespaces identite et par défaut, les attributs/PG_VERSION et
`pg_controldata` du seul cluster arrêté. Il ne lance ni service ni SQL.
Les cadres historiques sont liés aux trois SHA-256 publics de f9 dans un
dossier privé ; leur mode d'archive0664 est alors acceptable, sans droits monde,
lien ou contenu différent. Les nouvelles extractions respectent umask077.

Le diagnostic `37969887755` valide ces cadres historiques et le cluster17
privé proprement arrêté. L'échec classé concerne le service d'identité.
Les codes de sortie/étapes systemd sont des valeurs fermées, les classes
d'exception appartiennent à une liste prédéfinie. Le namespace identite
entier reste réservé à ces composants et sa sortie uniquement classifiée ;
aucun journal général du serveur. Le format des credentials et l'import
peuvent être contrôlés sans envoi ni restitution de leurs valeurs.

Le relevé `37971727525` donne une sortie143, import et credential valides,
aucune exception classée. La cause initiale reste inconnue : le gestionnaire
NixOS émet sur stderr son bilan d'unités échouées avant le retour4.
Le diagnostic privé contient déjà cette sortie ; seuls noms techniques
prédéfinis et nombre d'inconnus sont projetés. Aucun journal supplémentaire,
lancement ou relaxation des restrictions du service n'est nécessaire à cette
lecture. La sonde Java locale sans AF_NETLINK n'a pas confirmé cette piste.

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

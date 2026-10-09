# Import initial privé MrJ.am

Le workflow manuel `vision-identite-import-preparer.yml` prépare les fichiers
privés nécessaires au compte commun. Il **ne démarre pas Keycloak**, n'importe
aucun realm dans une base et ne crée pas de personne. L'identité du propriétaire,
son MFA et son rapprochement avec l'ancien compte Vision sont des étapes suivantes.

La préparation réelle [37927013329](https://github.com/MrJ-am/vps-infrastructure/actions/runs/37927013329),
opérateur `ce847e1519eac78b37352cd070eb949346d61a47`, réussit le 9 octobre à
11:59 UTC : cinq secrets et import vérifiés, aucune rotation/import en base,
six services/nouvelle SSH et 25 sondes passent. Le dossier privé reste sur le VPS.
[Preuve technique](../operations/vision-identite-import-qualification.json).

## Préconditions et opération

Le workflow exige `main`, l'environnement `vps-production`, la CI du commit exact
et le verrou commun `vps-administration`. Le driver vérifie avant et après la
génération active et par défaut, la release Vision et le Nixpkgs installé. Il
relit les rapports privés des opérations réelles de construction et qualification
Unix ; les preuves publiques seules ne suffisent pas. Paquet, candidats et
conditions fermées doivent correspondre exactement.

Le dossier `/var/lib/mrjam-identite` est root 0700. Il contient déjà le jeton
SMTP provisionné ; ce workflow ne le remplace pas et n'ouvre aucune connexion
SMTP. `scripts/identite-preparer.py` prépare cinq secrets de 256 bits et
`mrjam-realm.json`, tous root 0600, hors Git et store Nix. Ce dernier contient
la configuration SMTP privée, le client Vision et trois comptes de service
techniques avec leurs droits limités. Il ne contient aucune identité humaine.
Le hook de fermeture dispose d'un secret distinct. Les inscriptions natives
restent fermées.

Les opérations utilisent un verrou local et des ouvertures sans suivi de lien,
des fichiers réguliers privés à un seul lien et une lecture bornée. Le dossier
et les fichiers appartiennent à l'utilisateur exécutant ; le driver exige root.
Une reprise partielle conserve les clés déjà créées. Une relance vérifie le
contenu complet de l'import existant et les mêmes secrets, sans les modifier.
Une divergence, une clé absente d'un import existant, un mauvais droit ou une
configuration modifiée entraîne un refus, sans écrasement ni rotation. Il faut
alors préparer une opération distincte adaptée à l'état réel.

Les journaux d'erreur restent dans le dossier root privé de l'opération.
Actions et son artefact de quatorze jours ne reçoivent que le rapport technique :
révisions, version, chemin du paquet et booléens. Aucun secret, import, adresse
personnelle ou contenu SQL. Le contrôle final du socle, la nouvelle connexion
SSH, les six services et les 25 sondes HTTP/TLS sont exigés même après échec.

## Validation et suite

Les tests exercent la relance sans rotation ni modification, la reprise partielle,
les liens symboliques/physiques, FIFO et tailles excessives, les permissions
faibles, l'exclusion concurrente, un import altéré et le refus sans divulgation
d'un faux secret. La CI native importe aussi le realm assemblé dans Keycloak
26.7.3 synthétique et qualifie PKCE, MFA, récupération et lien magique.

La réussite de cette CI ne prouve pas la préparation du VPS. Consigner le run
manuel et son commit après exécution. Ne pas supprimer l'import privé ou les
secrets lors d'une autre étape et ne jamais les transmettre à Work. Les options
`importInitial` et `secretClient` du candidat utilisent ces fichiers par
credentials systemd, sans les copier dans le store.

Un import Keycloak initial ignore un realm déjà présent : il ne met pas à jour
une identité existante. Toute activation et création du propriétaire exigent
donc une procédure séparée, avec contrôle API local et inscriptions fermées.
La possession/MFA, l'association OIDC explicite, le retour autonome et les
conditions d'ouverture à des tiers restent à établir.

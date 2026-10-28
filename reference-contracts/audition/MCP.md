# Connecteur pédagogique Audition

Adresse canonique : `https://audition.mrj.am/mcp`. Transport JSON-RPC/POST stateless
du socle Vision, protocole par défaut `2025-06-18`. Cette adresse est préparée par
les sources ; une mise en ligne ne résulte pas d'une compilation locale.
Découverte OAuth : `/.well-known/oauth-protected-resource/mcp` et
`/.well-known/oauth-authorization-server`, audience `audition:mcp`.

Ajouter un connecteur MCP distant dans le LLM, choisir OAuth, se connecter avec Log
et accepter le consentement du connecteur dans Audition. Le broker existant utilise
PKCE S256, session host-only, rotation et révocation. Aucun jeton partagé entre élèves.
La session Vision ne devient pas une session Audition ; un grant lié à l'hôte voisin
n'ouvre pas Audition. La configuration OIDC autorise explicitement le retour Audition.

Commencer par `contexte`, puis `travaux` avec un identifiant de groupe renvoyé par le
serveur. Ne pas inventer des identifiants : les résultats ont des liens canoniques et
la recherche `retrouver` résout un objet autorisé vers son groupe. Lire le cadre de la
séance et sa politique avant de conduire le travail. Les appels web/MCP appliquent
les mêmes contrôles de ressources.

Exemple de consultation :

```json
{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"contexte","arguments":{"offset":0,"limite":50}}}
```

Parcours : enseignant `cours`/`activite` proposent du travail, relu et enregistré dans
l'interface web avant prescription ; `affecter` fixe élèves/échéance. Élève
`ouvrir_seance` retrouve ou crée sa séance unique, `consulter_seance` rend état,
politique, consignes effectives, version actuelle et prochaine action. `consigner`
enregistre atomiquement production, aides et observations. `transition` accepte
interrompre/reprendre/terminer selon l'état ; tous les critères de la version adoptée
doivent être observés avant clôture. Enseignant : `rapport`, `rectifier`, `remediation`.
Administration : groupes, habilitations, diagnostic et suppression contrôlée.

Exemple d'enregistrement (remplacer les identifiants/révisions par ceux reçus) :

```json
{
  "groupe": "id-groupe",
  "id": "id-seance",
  "revision": 3,
  "activite_version": 2,
  "politique_version": 1,
  "cle": "cle-stable-unique-de-cette-operation",
  "activite_a": 1792000000,
  "production": "Si x est positif ou négatif, le produit x×x est positif ; pour x=0 il vaut zéro.",
  "aides": [{"nature":"indice","contenu":"Examiner aussi x=0.","activite_a":1792000000}],
  "observations": [{"critere":"signe","etat":"reussite_aidee","points":2,"justification":"Les trois cas sont traités après l'indice."}]
}
```

Les schémas fermés sont retournés par `tools/list`. Les réponses de séance contiennent
`seance`, `activite`, `cours`, `activite_version`, `version_actuelle`, `politique`,
`contexte_modifie`, `informations_manquantes` et `actions_suivantes`. Une nouvelle
activité officielle est fournie séparément avant `adopter_contexte`. La production
ouverte conserve les critères et n'est pas remplacée par un QCM.

Listes : `elements`, `total`, `suivant`; reprendre avec `offset=suivant`, maximum100.
Une page est aussi bornée en octets. Les corps font au maximum64K, production16K
caractères, aides32 et observations64 par tentative, tentatives128 par séance.
Les limites de contexte sont retournées dans la politique. Pour une classe très
large, préciser une activité plutôt que construire un rapport de plus de10000lignes.

Erreurs métier : `structuredContent={erreur,statut,details,reprise}`, `isError=true`.
Codes : `groupe_interdit`, `objet_indisponible`, `conflit_revision`, `contexte_modifie`,
`proposition_non_validee`, `seance_non_ouverte`, `criteres_non_observes`,
`cle_reutilisee_avec_autre_operation`, `heure_activite_invalide`, `champs_invalides`.
Un401 exige une reconnexion ; un409 impose une relecture/adoption appropriée.
Après timeout : relire `consulter_seance`, puis réessayer exactement le même contenu
et la même clé. Une réponse perdue peut suivre une écriture réussie. Aucun succès
d'enregistrement ne doit être annoncé sans confirmation. Une notification JSON-RPC
ne déclenche pas silencieusement un outil d'écriture.

Les instructions pédagogiques demandent au modèle d'annoncer le cadre, laisser
répondre, juger avec traces, proposer des indices progressifs et signaler les
incertitudes. Elles ne certifient pas l'exactitude ni l'honnêteté du client. Le serveur
ne transmet pas un corrigé privé en espérant que le modèle ne le révélera pas.

Disponibilité fournisseur constatée le13octobre2026 : la [page officielle Mistral](https://mistral.ai/pricing/)
présente une offre gratuite avec connecteurs et une ligne «Custom MCP connectors»
en bêta. Cela ne prouve pas l'activation du connecteur personnalisé sur un compte
élève particulier ni un parcours OAuth Audition réussi. Aucun essai Mistral réel n'a
été effectué. Le [tarif étudiant](https://help.mistral.ai/en/articles/698530-i-m-a-student-or-a-teacher-am-i-eligible-for-a-discount)
est une offre Pro remisée ; ne pas l'imposer aux lycéens ni assimiler remise et accès
gratuit. Les [conditions EEE](https://legal.mistral.ai/terms/eu-consumers-terms-of-service/)
consultées indiquent13ans minimum, autorisation parentale/légale des mineurs selon
les conditions applicables, compte individuel et réglage de l'utilisation des données.
Ces conditions et quotas doivent être revérifiés pour les comptes réellement utilisés.

Le catalogue publie les propriétés des pages, ressources versionnées et séances,
et les limites des productions, aides et observations. `isError=true` ne certifie
pas une absence d'écriture. Les actions administratives sensibles demandent une
MFA récente ; HTTP403 `verification_renforcee_requise` conduit au retour Log
`/auth/connexion?verification=renforcee&retour=%2F%23administration`. Aucune erreur
de connexion n'est traduite en observation pédagogique.

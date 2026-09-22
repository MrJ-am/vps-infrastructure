# Journal HTTP et audit DDoS

Activé et vérifié le 22 septembre 2026, [exécution 35792035605](https://github.com/MrJ-am/vps-infrastructure/actions/runs/35792035605).
Sources `4345e4ef59765c156aec937fd3a2d4f646f188eb`, CI `35791604558`, préparation
`35791837515`. État, génération et preuves dans ETAT.md et operations/http-publication.json.

## Journal HTTP

Nginx écrit une ligne JSON par requête terminée dans journald, espace `http`,
étiquette `http_acces`. Horodatage, identifiant aléatoire Nginx, IP du pair,
site configuré, méthode, catégorie de route, statut HTTP/amont, durée, octets
et résultats des limiteurs. Cela couvre aussi les rejets avant l'application.
Les sous-requêtes d'authentification ne sont pas enregistrées séparément.

Pas de corps, réponse métier, Authorization, cookie, nom d'utilisateur,
Referer, User-Agent, paramètres URL ni identifiants métier. Les chemins sont
classés en catégories fixes (mcp, api, api-web, auth, matheval, ressource,
accueil, autre). Une redirection interne conserve la catégorie initiale.
L'adresse est celle du pair TCP : aucun X-Forwarded-For fourni par le client
n'est considéré comme preuve d'identité. Un futur proxy demande un contrat
explicite pour les adresses de confiance.

Les messages Nginx natifs sont limités à `crit` : les erreurs ordinaires
peuvent recopier une URL ou un nom d'utilisateur. Les statuts HTTP 4xx/5xx
restent visibles dans le journal structuré. Le diagnostic natif critique,
non reformattable par Nginx, reste susceptible de contenir du contexte de
requête : ne jamais transmettre un secret dans une URL. Aucun mode debug.

L'espace isolé ne chasse pas les journaux SSH/PostgreSQL. Stockage persistant,
compression, budget SystemMaxUse 128 Mio, fichiers de 8 Mio, au plus 16
fichiers archivés, conservation maximale 14 jours et rotation au plus tard
quotidienne. RuntimeMaxUse 16 Mio en mode temporaire ; réserves disque de
1 Gio (persistant) et 64 Mio (temporaire). Journald peut dépasser son budget
nominal de la taille des fichiers actifs : ce n'est pas un quota de partition
strict. La rétention réelle dépend du trafic et peut être beaucoup plus courte.

Limitation de journalisation à 1 000 messages par 30 s pour le service Nginx ;
le mécanisme journald peut ajuster son seuil selon l'espace libre. Sous
saturation, le transport syslog non bloquant et journald peuvent abandonner
des messages. Ce compromis protège les ressources et ne fournit pas un audit
exhaustif d'une attaque. Aucun export automatique de ces IP vers GitHub.
Les anciennes traces ne sont pas supprimées par cette installation.

Lecture administrative depuis le VPS, via une opération Actions autorisée :

```sh
journalctl --namespace=http -t http_acces --since '10 minutes ago' -o cat
journalctl --namespace=http --disk-usage
```

Un succès HTTP 200 MCP peut contenir une erreur JSON-RPC. Ce journal HTTP ne
remplace donc pas un futur journal applicatif des noms d'outils, erreurs de
paramètres et résultats MCP. Il ne permet pas de reconstituer les arguments.

## Protection actuellement déclarée

| Périmètre | Débit par IP | Rafale | Connexions en cours par IP |
|---|---:|---:|---:|
| Vision REST `/api/` | 5/s | 10 | 10 |
| Vision MCP `/mcp` | 5/s | 10 | 10 |
| Test mobile exact | 5/s | 3 | 2 |
| Sessions `/auth/` | 5/s | 5 | pas de limite explicite |
| Navigateur `/api/web/` | 5/s | 20 | pas de limite explicite |
| Matheval, sites et fichiers publics | pas de limite explicite | — | — |

La même zone par IP est partagée entre les routes protégées. Les refus sont
429. Les corps sont plafonnés, notamment MCP 64 Kio et auth 8 Kio. Les ports
applicatifs restent locaux ; les hôtes inconnus sont refusés. Cela réduit les
abus de quelques clients, mais pas le débit cumulé d'un réseau distribué.
Les limites de connexions HTTP ne comptent pas toutes les connexions TCP
avant réception complète des en-têtes. L'audit réel `35791837515` a confirmé ces directives et `tcp_syncookies=1`.
Aucun réglage explicite de workers, connexions générales ou délais ne figure
dans le Nginx généré : valeurs par défaut, notamment un worker, 512 connexions
par worker et délais de lecture d'en-têtes/corps de 60 s. Les connexions vers
les serveurs applicatifs comptent aussi dans cette capacité.
Avant ajout : 1 906 374 octets de fichiers sous /var/log/nginx et 17,8 Mio dans
le journal système ; aucun access_log personnalisé dans la configuration.
Le format d'accès implicite de Nginx n'offrait donc pas cette minimisation et
ce budget dédiés.

Aucun plafond global HTTP, bannissement automatique ni filtrage amont n'est
établi par ces sources. Une saturation de bande passante ou du traitement TLS
ne peut pas être arrêtée par les seules limites HTTP de ce VPS. La protection
Hostinger éventuelle n'a pas été auditée depuis le compte fournisseur.

Suites pertinentes : dimensionner les plafonds globaux et par route à partir
du trafic légitime, borner les délais/connexions, puis vérifier la protection
réseau de l'hébergeur. Un proxy anti-DDoS demanderait aussi de bloquer le
contournement direct de l'origine. Aucun de ces changements n'est effectué
implicitement par le présent ajout de journalisation.

## Déploiement

Workflow dédié `http-journal.yml`, demande `operations/http-journal.json` :
`preparer` puis `activer`, révision complète avec CI push réussie. Audit réel,
reproduction de la génération active, invariants de tous les sites/services,
Nixpkgs installé, sauvegardes chiffrées et copie privée des sessions. Nouvelle
opération sous `/root/http-preparations/`, retour autonome à vingt minutes,
contrôles collectifs et nouvelle connexion SSH avant enregistrement.

Les sondes vérifient 200, 401 et 429 et l'absence de marqueurs confidentiels
dans les lignes JSON. Vingt appels anonymes supplémentaires au MCP au maximum,
aucune charge massive ni écriture métier. Basic est contrôlé sans remplacement
ni révocation du token MCP permanent. Pas de reconstruction applicative.

Références : [journal Nginx](https://nginx.org/en/docs/http/ngx_http_log_module.html),
[syslog](https://nginx.org/en/docs/syslog.html),
[limitation de débit](https://nginx.org/en/docs/http/ngx_http_limit_req_module.html),
[connexions](https://nginx.org/en/docs/http/ngx_http_limit_conn_module.html),
[journald](https://www.freedesktop.org/software/systemd/man/252/journald.conf.html).

Références complémentaires : [valeurs globales Nginx](https://nginx.org/en/docs/ngx_core_module.html), [délais HTTP](https://nginx.org/en/docs/http/ngx_http_core_module.html).

# Audition — bibliothèques pédagogiques internes

Audition complète Vision sans modifier son modèle de révision. Le serveur central
charge trois systèmes ASDF depuis ce dépôt ; aucune bibliothèque ne démarre un
transport, connexion, migration ou tâche au chargement. Aucun service d'inférence,
abonnement ou comptage de jetons n'est ajouté. Les dépendances externes et leurs
versions restent celles de l'inventaire central.

`mrjam-audition/modele` porte validation, états, visibilité, politique et calculs.
`mrjam-audition/services` porte autorisations, transitions et transactions PostgreSQL
via `mrjam-native`. `mrjam-audition` adapte le transport MCP de Vision. HTTP appartient
à `mrjam-metier`, qui vérifie Log à chaque appel puis impose l'acteur et le canal.
Le navigateur et le LLM ne choisissent ni identité effective ni rôle.

Les comptes métiers centraux demeurent ceux résolus par Log ; les habilitations
Audition résident dans ses tables et sont attribuées explicitement. Un enseignant
accède à ses groupes, un élève à son travail et ses séances. L'administration
technique gère groupes/rattachements et diagnostic, sans accès aux productions.
Le refus s'applique aussi aux rejeux après révocation. Les comptes ne sont jamais
fusionnés par mail ni créés à partir d'une déclaration du client.

La base Vision existante héberge le schéma séparé `audition` et le login non
propriétaire `audition_app`, sans privilège sur les schémas des autres produits.
Les ressources sont des agrégats versionnés : cours, activité, affectation et séance.
Les observations et rectifications sont conservées dans les versions immuables de
séance. Les listes emploient une synthèse dérivée et ne chargent pas les productions
de toutes les séances. Les tables appliquent des politiques RLS ; le paramètre SQL
d'acteur provient de Log, sans prétendre authentifier face à du SQL arbitraire ou
une compromission du serveur.

Une requête métier est une transaction. Le verrou du groupe sérialise droits,
révision, idempotence et écriture ; une clé appartient à un acteur et à un contenu
canonique. Réutiliser une clé avec d'autres données est refusé. Une séance est unique
pour un élève et une affectation, y compris après clôture ; une remédiation est une
nouvelle prescription et non une réouverture implicite. Les limites de stockage et
de pagination sont explicites, jamais transformées en échec scolaire.

Une activité proposée par MCP reste une proposition. La validation intervient par
l'enregistrement web de l'enseignant. Une proposition nouvelle ne remplace pas la
dernière version officielle dans une séance ouverte. L'adoption d'une nouvelle
prescription est explicite et historisée ; les observations antérieures ne changent
pas de barème et ne suffisent pas à valider les nouveaux critères. L'élève ne reçoit
jamais le champ corrigé avant sa publication, y compris au prochain appel MCP.

Une tentative distingue production rapportée de l'élève, aides apportées et
interprétation attribuée au canal. Les cinq états sont non observé, en cours,
difficulté, réussite avec aide et réussite sans aide. Une aide interdit une réussite
autonome ; réussite complète exige des points égaux au maximum et aucune incertitude.
Le serveur ne prouve pas que le client rapporte honnêtement une réponse ou que son
jugement mathématique est exact. Les enseignants peuvent rectifier une interprétation,
avec auteur/justification et conservation de la production initiale.

Dates : secondes Unix UTC, heure d'activité obligatoire distincte de réception.
Reprise : nouvelle date de reprise, jamais réemploi de la date d'ouverture comme
date de tentative. Tolérance d'horloge : cinq minutes ; activité reprise jusqu'à
trente jours. Un rapport distingue versions/critères, effectifs, couverture, aides,
réussites et inconnues. La proportion utilise une dernière observation définie par
séance/critère ; aucun mélange de scores logarithmiques de barèmes différents.

Le logit en dB est translaté par `p0` seulement pour le QCM à une réponse correcte
parmi `m` propositions équiprobables. Une production ouverte n'a pas de référence
de hasard inventée. Zéro/un donnent des infinis explicites ; absence reste absente.
L'affichage conserve la correction entière en centinats, sans signe positif et sans
pseudo-observations. Le barème pondéré et la couverture ne deviennent pas des
probabilités de maîtrise.

Collecte : production/aides/observations utiles au travail affecté seulement, pas de
conversation privée ni raisonnement interne. Le journal technique reste celui du
serveur central, sans corps, identité métier ou credential. Les traces pédagogiques
et l'audit des habilitations sont distincts. Conservation : jusqu'à suppression
explicite du groupe par l'administration habilitée ; aucune purge automatique ou
promesse de conformité juridique n'est présentée comme vérifiée. Le retrait d'une
identité n'efface pas silencieusement le métier. La suppression de groupe inclut
objets, versions et reçus ; l'audit de l'action est conservé. Les sauvegardes et leur
rétention restent celles de l'exploitation centrale.

Les habilitations sensibles exigent la fraîcheur MFA du socle Log (900s). Les
reçus d'idempotence distinguent aussi le canal imposé par le serveur : rejouer
une proposition MCP comme écriture web ne vaut jamais validation. Les identités
métier conservent le point accepté par le socle ; aucun renommage de compte.
Les modifications de cours sont épinglées par `cours_version` dans l'activité :
l'enseignant enregistre à nouveau l'activité pour adopter explicitement le cours
révisé, puis l'élève adopte la nouvelle prescription dans une séance déjà ouverte.

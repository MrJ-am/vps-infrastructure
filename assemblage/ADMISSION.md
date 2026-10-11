L'approbation manuelle prévue par les règles d'admission est conservée dans le
serveur commun : `POST /api/gestion/approuver_admission`, objet JSON contenant
exactement `id`, `methode`, `reference` et `source_pays`. Méthodes existantes :
`entretien`, `verification_relation`, `controle_pays`. La référence rend compte
du contrôle humain réellement effectué ; l'API ne réalise ni n'invente ce contrôle.

La route conserve l'entrée d'administration Nginx : session vérifiée, preuve
renforcée existante et contrôle CSRF. SO_PEERCRED limite le transport privé à
Nginx. L'acteur vient de cette entrée, jamais du corps JSON. La migration Vision
026 vérifie à nouveau le rôle actif en SQL et garde le verrou de configuration
pendant l'écriture SQLite. Ordre des verrous : admission, puis configuration SQL,
comme les tâches d'admission ; aucun réseau pendant l'approbation. Une suspension
ou un changement de rôle déjà acquis est ainsi pris en compte. Le rôle SQL
d'administration ne peut pas lire les contenus pédagogiques.

Les confirmations d'adresse et de représentant restent nécessaires. Le secret de
reprise scientifique Matheval reste indépendant. La gestion courante s'appuie sur
le client navigateur authentifié et son CSRF ; aucun REPL ni nouvel accès Unix
public n'est ajouté. Les tests `admission-composant.lisp` vérifient le refus
anonyme, Bob sans droits, un acteur injecté dans le corps et l'approbation Alice
d'une fixture après consentement ; aucune admission de production n'est créée.

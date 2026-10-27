# ViSe : hébergement autonome

Domaine retenu : https://vise.mrj.am. Application et protocole :
MrJ-am/etp-vie-affective. La dernière empreinte de binaire/archives est dans
`assemblage/vise/target.json`, avec la révision source exacte.

Le processus Rust écoute uniquement `127.0.0.1:3017`. Nginx gère HTTPS/ACME.
Le serveur PostgreSQL général existant héberge la base séparée `etp_carnet`.
L’utilisateur Unix et le rôle SQL `etp_carnet` se connectent par socket local
avec authentification peer ; aucun mot de passe ni écoute TCP supplémentaire.
PostgreSQL17 nécessite un redémarrage bref pour modifier le chemin Nix du
fichier HBA ; l’instance et son dataDir ne sont pas remplacés. La seule règle HBA ajoutée autorise cette paire base/rôle. Toutes les règles
précédentes sont obtenues du module de base et conservées, y compris les refus.
Le rôle est sans privilèges globaux ; son provisionnement refuse un propriétaire
ou des privilèges inattendus. Aucun registre/ACL des autres bases n’est modifié.

## Promotion et retour

`vise-deploiement.yml` n’accepte que diagnostic/apply, sur main. Il réutilise
le canal administratif de `docs/ACCES.md`, vérifie l’archive qualifiée par SHA256,
réutilise la sauvegarde/restauration isolée centrale avec la génération constatée,
construit le candidat Nix puis arme un retour autonome avant la bascule.
La validation exige HTTPS, le maintien des PID applicatifs protégés, le refus d’accès SQL
transversal et une sauvegarde ViSe chiffrée déchiffrable. Code et configuration
reviennent ensemble en cas d’échec ; aucune ancienne base n’est restaurée sur
les écritures courantes. Le journal de suppressions reste conservé.

L’entrée Nix persistante importe `vise-base.nix` (copie exacte de l’entrée
précédente) et `vise-hosting/module.nix`. Le module réévalue la configuration
de base pour conserver les futures règles HBA des autres services. Ne pas
réintroduire ViSe dans cette base : cela créerait une boucle d’évaluation.
Le manifeste métier commun est inchangé.

## Persistance et sortie

Binaire et assets : `/var/lib/vise/releases/<sha256>/` (root, sans écriture
applicative). Journal actuel : `/var/lib/etp-carnet/deletions.log`.
Sauvegardes chiffrées SQL+journal : `/var/backup/vise/`, destinées au propriétaire
et à la clé SSH de l’hôte. Minuteur quotidien ; aucune purge automatique activée.
Valider une conservation limitée avant usage clinique. La restauration doit
utiliser le journal actuel le plus récent, jamais seulement celui d’un ancien dump.

La sortie emporte ce binaire statique, les assets, le dump de cette seule base
et le journal actuel ; elle n’emporte aucun composant des autres projets.
Le site reste un prototype à données fictives, sans certification clinique/HDS.

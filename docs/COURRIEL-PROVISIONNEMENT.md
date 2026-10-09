# Installer le courrier privé par Actions

Le code préparé est consultable dans `vision-courriel.yml` et
`scripts/courriel-provisionner.py`. Il installe le jeton Proton déjà fourni,
sans modifier une valeur différente, activer Keycloak ou ouvrir les comptes.
Il ne touche ni les MX, ni les domaines, ni les releases, ni les ACL SQL.

1. Publier ce workflow sur main après réussite de la CI exacte. Ajouter le
   secret Actions `VISION_PROTON_SMTP_TOKEN`, contenant **seulement** le jeton
   SMTP dédié à Automath, pas le mot de passe Proton. Le secret peut appartenir
   à l'environnement `vps-production` ou au dépôt privé. La connexion utilise
   la clé administrative existante ; aucune clé SSH supplémentaire n'est requise.
2. Lancer manuellement « Installer le courrier privé de Vision », sur main,
   en cochant le test. Le runner vérifie la clé d'hôte, transfère le commit
   exact, passe le jeton sur stdin et installe le JSON root 0600 dans
   `/var/lib/mrjam-identite`, répertoire 0700. Aucune donnée privée en artifact.
3. L'envoi exige STARTTLS et un certificat valide. Il utilise la clé publique
   age déjà déclarée pour les sauvegardes Vision, à la révision du workflow.
   Le résultat atteste seulement l'acceptation du relais. Vérifier la présence
   dans la boîte Proton, récupérer la pièce et la déchiffrer avec la clé privée
   correspondante hors VPS. Le témoin ne désigne aucun usager ; ne pas le
   soumettre au rejeu des effacements. Conserver uniquement la preuve technique.
4. Consigner URL Actions, commit, état du fichier privé et confirmation de
   réception/déchiffrement. Une clé privée manquante bloque la qualification
   des sauvegardes, même si l'envoi SMTP réussit. Un refus SMTP ne modifie
   aucun accès utilisateur ; le fichier privé reste disponible pour diagnostic
   opérateur et reprise. Ne pas afficher les réponses privées du relais.

Les outils Work actuels ne permettent ni de créer un secret Actions ni de
déclencher un nouveau workflow manuel. Le réseau Work n'autorise pas SMTP 587.
Ces deux actions d'interface GitHub sont donc les seules manipulations à faire
par l'exploitant pour cette étape ; aucune tentative SSH depuis Work.

Ce contrôle n'achève pas la migration multi-utilisateur. L'import privé,
l'identité initiale avec MFA, la restauration des bases, le retour des owners,
ACL et RLS, les contrats applicables et la réception du registre d'effacement
restent les conditions distinctes du dossier d'activation.

# Client de présentation Log

Lire les règles centrales dans `../AGENTS.md`, `../assemblage/FRONTENDS.md`
et `../assemblage/REPRISE.md`. Ce client appartient à vps-infrastructure ;
aucun dépôt, service ni workflow supplémentaire.

Présentation elm-ui, ressources Signature, composants/contextes et transitions
Animator de style-mrjam, à révisions exactes. Aucun HTML/CSS de présentation,
framework alternatif ou dépendance ajoutée implicitement. Les ports WebAuthn
éventuels restent des adaptateurs techniques bornés et testés.

Kanidm vérifie les authentificateurs, applique les politiques et émet les sessions.
Ne pas conserver de jeton dans l'état Elm ou le stockage navigateur ; aucune
trace de phrase de passe, code, défi personnel ou réponse brute. Lire les réponses
du protocole par `Log.Protocole.lire`, qui élimine les diagnostics JSON sensibles.
Un état de présentation ne constitue pas une preuve d'authentification serveur.
Préserver Unicode/espaces sans normalisation destructive et les sessions existantes.

Commande locale : `python3 scripts/assemblage.py tester --exact --suite log-protocole-elm`
depuis la racine d'infrastructure. La qualification actuelle porte sur le codec,
pas sur une vue ni une connexion réelle. Ne pas la promouvoir comme interface.

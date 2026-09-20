# Utiliser Vision depuis ChatGPT

Le contrat a importer est `https://vision.mrj.am/openapi.json`.
Il decrit uniquement des routes HTTPS versionnees et protegees par HTTP Basic.

Dans un GPT utilisant une action :

1. importer ou coller le schema OpenAPI ;
2. choisir l'authentification par cle d'API, de type **Basic** ;
3. si l'interface demande une valeur unique apres le mot `Basic`, fournir le
   Base64 de `identifiant:mot-de-passe`, sans recopier le prefixe `Basic ` ;
4. tester d'abord `getVisionHealth`, puis `sayHello`.

Le secret doit rester dans le gestionnaire d'authentification de ChatGPT. Ne
pas le placer dans le schema OpenAPI, les instructions du GPT, un depot Git ou
un message destine a etre partage.

Les routes initiales ne modifient aucune donnee. Toute future operation avec
effet de bord recevra une description explicite et un identifiant d'operation
stable avant d'etre rendue utilisable par ChatGPT.

## Endpoint MCP

Le serveur MCP est disponible a `https://vision.mrj.am/mcp`. Il utilise le
transport Streamable HTTP stateless et annonce ses schemas et annotations par
`tools/list`. L'authentification HTTP Basic actuelle convient aux tests directs
et aux clients qui savent produire cet en-tete.

Pour `record_review`, fournir `rating` uniquement apres une vraie tentative de
rappel : `1` signifie un echec, `2` un rappel difficile mais reussi, `3` un
rappel correct et `4` un rappel immediat et assure. FSRS-6 calcule alors la
prochaine echeance. Si la fatigue, une aide, une ambiguite ou la portee de la
question rendent l'observation peu probante, omettre `rating` et documenter le
contexte : la note qualitative sera conservee sans modifier l'etat FSRS.

Le mode Plugins de ChatGPT exige OAuth 2.1 pour des donnees privees et ne doit
donc pas etre branche anonymement sur les fiches personnelles. L'ajout d'OAuth
ou d'un tunnel MCP securise constitue une etape de connexion distincte ; il ne
faut pas rendre `/mcp` public sans authentification pour la contourner.

## Essai Mobile Live

Le point `GET /api/v1/mobile-live-test` est volontairement isole. Il utilise
des identifiants jetables differents de ceux de l'API et renvoie seulement la
preuve `VISION-MOBILE-LIVE-AUTH-OK`. Il n'accorde aucun acces aux autres routes
et ne lit ni n'ecrit aucune donnee.

Son contrat autonome est publie sous
`https://vision.mrj.am/mobile-live-test-openapi.json`. Le test sert
a determiner si Mobile Live sait produire lui-meme un en-tete HTTP Basic a
partir d'un identifiant et d'un mot de passe dictes. Les identifiants durables
de l'API ne doivent jamais etre dictes pour cet essai.

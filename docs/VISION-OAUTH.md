# Connexion OAuth de Vision pour Claude

Vision expose `https://vision.mrj.am/mcp` en HTTP streamable. Le connecteur
Claude découvre l'autorisation via
`/.well-known/oauth-protected-resource/mcp`, enregistre son client sur
`/oauth/register`, puis présente la page de consentement du compte Vision.
La connexion demande une preuve PKCE S256. Aucun mot de passe Vision n'est
remis à Claude ; les jetons OAuth sont distincts des tokens nommés et des
sessions navigateur.

Dans Claude, ajouter un connecteur MCP personnalisé en indiquant l'URL
`https://vision.mrj.am/mcp`, puis choisir « Se connecter ». Si la session
Vision n'est pas ouverte, la page d'autorisation propose d'abord la connexion
au compte. Lire les permissions affichées puis autoriser. Les cinq outils MCP
existants deviennent disponibles en lecture et en écriture.

La page `https://vision.mrj.am/auth/mcp` liste les tokens Bearer nommés et
les applications OAuth encore autorisées. Elle permet de révoquer Claude sans
révoquer Mistral ni Mammouth. L'accès OAuth expire au bout d'une heure ;
le renouvellement rotatif vaut au plus trente jours. Une rotation du fichier
d'identifiants Vision invalide les jetons. Les codes ne servent qu'une fois
et expirent après cinq minutes.

Le point `/mcp` accepte aussi HTTP Basic et les tokens Bearer nommés
préexistants. Un jeton MCP ne donne accès ni au navigateur ni à l'API REST.
Le consentement exige une session Vision et un CSRF valide. Une origine
explicitement étrangère ou `null` est refusée ; l'absence d'en-tête `Origin`
est acceptée pour les formulaires des navigateurs qui l'omettent. La révocation
requiert aussi l'origine Vision. Les condensats, jamais les secrets, sont enregistrés dans SQLite
sur le VPS. Les journaux HTTP ne contiennent pas les paramètres de requête ni
les en-têtes d'autorisation.

La CI vérifie l'enregistrement du client, la découverte, les redirections,
la preuve PKCE, la consommation unique du code, le renouvellement, la
séparation des accès et la révocation. Le contrôle de production crée un
client temporaire, vérifie l'initialisation MCP puis révoque ses jetons,
sans écrire de fiche.

Le correctif du consentement sans `Origin` est actif à la révision
`2800fb6b2ee88b9f3fbd4384b11daabfb6337122` : CI `35842065564`,
préparation `35842320109`, activation HTTPS `35842570603`. Cette dernière
vérifie le formulaire sans cet en-tête, PKCE, le MCP et les accès précédents.
La connexion réelle depuis le compte Claude reste à refaire par son propriétaire.

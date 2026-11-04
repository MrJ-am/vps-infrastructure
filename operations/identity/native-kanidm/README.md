# Contrôle natif local Kanidm 1.11.2

`bash operations/identity/native-kanidm/run-isolated.sh native-006.json` relance
le contrôle avec un nouveau reçu. Le lanceur monte le candidat courant en lecture
seule et enferme les processus dans un espace bubblewrap sans réseau extérieur,
home, sockets ni fichiers de production. Les seuls comptes, mots de passe,
certificats, bases et jetons utilisés sont créés dans le `/tmp` isolé, puis supprimés.
Le résultat contient les empreintes du candidat et du test ; il refuse tout
écrasement d'un reçu existant. Les chemins des outils sont verrouillés dans le
lanceur et doivent être disponibles.

Le passage `results/native-005.json` sur le binaire
`21dd879f5040fbde94a36ffea05ff7a1a055b0fa5a15ad0e45405d750bed243b` réussit
les huit étapes suivantes : démarrage
du vrai Kanidm sous TLS, création d'un client et d'une personne inventés,
discovery/JWKS, autorisation avec consentement et PKCE, vérification indépendante
ES256 par OpenSSL et introspection sans Basic, refresh signé et révocation,
parcours du broker pour Vision/Audition, panne/reprise et déconnexion. Le broker
refuse le rejeu du callback, le transfert d'une session entre hôtes et la gestion
administrative sans MFA qualifiée.

Les reçus `native-001.json` et `native-002.json` conservent l'échec initial : une
hypothèse supplémentaire imposait que Kanidm refuse le rejeu direct d'un code.
Kanidm 1.11.2 retourne en réalité HTTP 200 lorsque le client dispose encore du
secret et du vérificateur PKCE. La fonction amont
`check_oauth2_token_exchange_authorization_code` valide le code chiffré, son
expiration, PKCE et le redirect, puis crée un nouveau `session_id`, sans registre
de consommation. Ce constat reste une limite explicite dans le reçu final ; il
ne constitue pas un contrôle réussi. La protection exigée du broker reste testée :
son état de transaction est consommé et le second callback retourne HTTP 401.

Source amont consultée :
[Kanidm 547933867e87da737e79d26942dc9261adaa5ee9](https://github.com/kanidm/kanidm/blob/547933867e87da737e79d26942dc9261adaa5ee9/server/lib/src/idm/oauth2.rs),
avec les contrats HTTP de `server/core/src/https/oauth2.rs`, les structures de
`proto/src/oauth2.rs` et le client de `libs/client/src/lib.rs` à cette même révision.

Ce contrôle démontre l'interopérabilité locale du binaire identifié avec le
paquet Kanidm réel. Il ne qualifie ni les comptes de production, ni un enrôlement
MFA humain, ni Nginx, ni le SSO d'une application tierce, ni une bascule du VPS.
Les accès opérateur natifs servent seulement à préparer la base inventée.

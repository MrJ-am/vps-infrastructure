# Style MrJ.am : coordination des applications

## État de la préparation au 21 septembre 2026

Les branches `migration/style-mrjam` de Mémoire, Vision et Apprendre à démontrer contiennent les ateliers de référence et leurs messages `docs/STYLE-MRJAM.md`. Leurs sources applicatives et la production sont inchangées. Un noyau ElmUI avec API française, galerie et tests est préparé séparément. Le dépôt public `MrJ-am/style-mrjam` reste à créer et à publier ; aucun orchestrateur de style n’est encore activé.

Les contrôles de référence ont réussi : Apprendre à démontrer `35604499617`, Mémoire `35605792689`, Vision `35604770389`. Ils établissent l’état de départ, pas la réussite d’un portage qui reste à effectuer.

## Décisions du propriétaire

Toutes les interfaces passent en ElmUI. Préserver et harmoniser l’identité existante. Factoriser les composants et compositions communs dans `style-mrjam`, pas dans ce dépôt d’infrastructure. Les appels sont simples et français, tels que `bouton "Valider" Valider` ; les variantes correspondent à des rôles distincts.

Franciser les noms contrôlés avec prudence : compiler la référence, renommer un seul symbole avec tous ses usages, compiler et tester ses contrats avant le suivant. Les noms des protocoles, données persistantes ou dépendances imposées ne changent pas silencieusement.

`MrJ-am/Signature` reste la source du logo et de la signature, initialement à `17495b13cefa24473e37434b98336b27caec8cdf`. Le README public du style doit préciser que toute utilisation du logo est strictement réservée. Les ressources d’identité sont versionnées avec les applications et la signature reste le texte sélectionnable `MrJ.am`.

## Rôle de l’infrastructure

Chaque adoption du style doit reconstruire et redéployer tous les projets concernés. Préparer un manifeste privé avec la révision exacte du style, de Signature et de chaque application, ainsi que les empreintes des artefacts. Interdire les branches mobiles comme références de construction.

D’abord construire et tester tous les candidats ; n’activer aucun candidat si l’un des contrôles échoue. Ensuite publier ces mêmes artefacts, sans nouvelle reconstruction non contrôlée. Vérifier les versions servies, les accès, les fonctionnalités critiques et les ressources locales. Le dépôt public de style ne doit pas recevoir de secrets de déploiement ni pouvoir déclencher une activation depuis une pull request non fiable.

Confirmer les cibles existantes avant de câbler les déclenchements inter-dépôts. Matheval possède sa chaîne applicative ; Vision son contrat d’intégration VPS. Apprendre à démontrer déclare un hébergement statique via `.openai/hosting.json` : la production de `dist` ne prouve pas son déploiement. Le mécanisme d’autorisation inter-dépôts reste à configurer sans réutiliser arbitrairement les secrets existants.

Le redéploiement collectif n’est pas une transaction atomique entre plusieurs hébergeurs. Conserver les anciens artefacts applicatifs et prévoir le retour des applications déjà activées en cas d’échec ultérieur. Ne jamais restaurer une base pour annuler une modification d’interface. Les pages déjà ouvertes peuvent conserver leur ancien JavaScript : préserver les contrats d’API.

NixOS, Nginx, PostgreSQL, les droits, les domaines et les sauvegardes restent inchangés pendant cette préparation. Ne pas rejouer la migration système historique. Toutes les opérations distantes restent exécutées par GitHub Actions, sans SSH direct depuis ChatGPT Work.

## Messages de reprise

Pour chacun des trois projets, demander de lire son `docs/STYLE-MRJAM.md` et son `AGENTS.md` sur `migration/style-mrjam`. Ces messages sont des consignes de préparation, pas l’annonce d’une migration terminée. La fin effective devra être attestée par les commits de la bibliothèque et des applications, leurs tests, les publications et les contrôles des versions servies.

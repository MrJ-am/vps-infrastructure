# Périmètre exploitation — proposition, sans pouvoir de production

- Lire `inventaire-borne.org` avant de modifier l'inventaire.
- Exécuter les tests : `python3 -m unittest -v test_inventory.py test_validate_report.py` depuis ce dossier.
- Le filtre `validate_report.py` ne sonde rien ; ne transmettre que son rapport fermé. Son schéma est épinglé et ne se sélectionne pas par le candidat.
- Aucun accès distant, SQL arbitraire, lecture de journal/donnée, activation Nix ou SSH administratif pour un agent.
- L'interface publique d'`inventory.py` reste sans argument, à opérations et sorties fermées ; étendre ce périmètre nécessite la gouvernance prévue par le mandat.
- N'utiliser que des données synthétiques dans les tests. Les droits et versions du VPS restent inconnus tant qu'un rapport borné n'est pas reçu.
- Ces fichiers sont une proposition locale ; ils ne constituent ni une ACL ni une autorité de validation ou de déploiement.

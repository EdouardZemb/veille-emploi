@docs/modele/methode.md

# veille-emploi

Console de recherche d'emploi : collecte, score explicable, candidature, pilotage.

Pour Edouard seul. La console tourne sur son serveur et se consulte au téléphone, en application web installée.

## État

Ce dépôt de code est né le 04/11/2026 d'un seul commit (lot V2, la scission, M-0006 § 7), tiré de l'arbre de `veille-emploi-donnees` à `f6b1189`. Le dépôt privé d'avant la scission, renommé `veille-emploi-donnees`, garde l'historique, l'instance et les issues ouvertes. Les numéros d'issue et de PR d'avant la naissance (#2 à #40) sont les siens. Aligné sur `modele-projet` `v0.8.0` : cible `serveur`, nature `code`, mode de fusion `session` (`docs/modele/methode.md`, « Qui fusionne »).

L'instance réelle vit au dépôt de données, `veille-emploi-donnees`, privé : sa configuration (`config/`, que la console lit par `VEILLE_CONFIG` sans conteneur, ou par le montage `/config` en conteneur), ses secrets chiffrés, ses fichiers d'environnement, l'état du serveur et ses commandes. La chaîne du modèle déploie un couple : l'image de ce dépôt et un commit des données. Ce dépôt n'en porte rien : la porte de confidentialité le refuse, au hook comme en CI, et relit l'historique chaque semaine.

L'éditeur de lettre en est à l'étape E1 (PR #2) : l'historique des versions est branché ; l'identité des paragraphes et la porte de validation sont écrites, mais pas encore appelées (voir `docs/pistes.md`). Les 8 tests du traitement des 410 (issue #3) passent depuis le 03/11/2026 : la règle était la bonne, mais le garde-fou anti-panne comptait ses sept jours depuis l'horloge du poste au lieu de l'instant de la vérification, et les tests, figés au 29/09/2026, échouaient une semaine plus tard (constat LE-6).

Le lot #10 (la connexion par passkeys, qui remplace le mot de passe unique ; ADR `docs/decisions/0001-connexion-par-passkeys.md`) est fusionné le 27/10/2026 (PR #14). Une passkey se révoque sur le serveur, par `veille passkeys --retirer <n°>`. Ce qu'il fallait régler avant l'exposition sur Internet, relevé sur #11, est fait par la PR #20 : la limite de débit par client, le cookie `__Host-`, la CSP, l'origine normalisée, une nouvelle touche de passkey avant d'ajouter un appareil, et la purge des sessions et des liens expirés.

Le lot #11 (la console en conteneur et le staging ; ADR `docs/decisions/0002-la-console-en-conteneur.md`) est clos le 02/11/2026 : l'image, le planificateur de collecte, `/sante`, les instantanés, le jeu factice, la limite de débit, la CSP et le cookie `__Host-`. Les heures de sauvegarde sont à déclarer côté serveur avant la première étiquette de prod (ADR-0002). Le code a deux modes jusqu'à la fin du #12 : en conteneur (`VEILLE_EMPLOI_ENV` posée) ou, sans elle, la console du tailnet, par systemd. En conteneur, le planificateur ne rattrape pas une échéance de collecte manquée par un redémarrage (le minuteur systemd, lui, le faisait) : la suivante collecte.

Le lot V1 (#22) est clos le 02/11/2026 : le code tourne par défaut sur `exemple/`, une personne inventée (Camille Exemple). La CI lance `VERIFIER_CONFIG` sur `exemple/` dans l'image construite ; la CI du dépôt de données la lance sur sa `config/`, contre l'image publiée, et la chaîne du modèle sur `/config` avant chaque déploiement de prod.

Prochain : la fin du lot V2 (le staging et la console du tailnet sur les deux dépôts, puis la clôture), puis le #12 (la production et la bascule). La suite de l'éditeur est à placer par Edouard.

## Commandes

Sur le poste, où se fait le travail (un environnement par worktree) :

- `python -m venv .venv`, puis `.venv\Scripts\python -m pip install -e .[dev]` : l'environnement. Ajouter l'extra `pdf` là où WeasyPrint s'installe.
- `.venv\Scripts\python -m pytest -q` : la suite. Sous Windows, les tests qui demandent WeasyPrint, systemd utilisateur ou les groupes de processus POSIX se sautent ; la CI et le serveur les font tourner, avec `SUITE_COMPLETE=1`, qui leur interdit de se sauter (`tests/sauts.py`).
- `.venv\Scripts\python -m pip install -e .[dev,navigateur]`, puis `.venv\Scripts\python -m playwright install chromium`, puis `.venv\Scripts\python -m pytest -q -p no:cacheprovider tests_navigateur` : le parcours de connexion dans un vrai navigateur (`tests_navigateur/`). La CI le fait dans le job `navigateur` ; la suite du serveur ne le collecte pas.

Sur une console sans conteneur (la console du tailnet), depuis son clone, à la main d'Edouard. Les chemins réels du serveur, et le compte des tests qui y sont sautés, sont dans le `CLAUDE.md` du dépôt de données.

- `git pull --ff-only && ./.venv/bin/pip install -e ".[pdf]" && systemctl --user restart veille-web.service && ./.venv/bin/veille empreintes-kit` : mettre l'outil à jour. La collecte relit le code à chaque passage.
- `./.venv/bin/veille etat` : l'état de la console.
- `SUITE_COMPLETE=1 PYTHONDONTWRITEBYTECODE=1 ./.venv/bin/python -m pytest -q -rs -p no:cacheprovider` : la suite, entière. Attendu : 0 échec, et des tests sautés exprès. Six se sautent partout : les trois de `test_kit_fige` (« pas de kit ici »), et trois qui lisaient le kit réel : `test_aucun_gabarit_du_kit_ne_porte_de_caractere_douteux`, `test_aucun_gabarit_ne_porte_de_signature_de_mauvais_encodage` et `test_les_deux_cv_restent_telechargeables` (`test_dossier`). La suite ne lit que des fixtures (`VEILLE_ENV` désigne un fichier absent, `VEILLE_KIT` les gabarits de l'exemple) ; le kit réel se vérifie par `./.venv/bin/veille empreintes-kit`. Un échec sur WeasyPrint, systemd ou les groupes de processus est une dépendance perdue sur le serveur, pas un test à faire taire. La suite tourne dans un dossier temporaire, même si une variable `VEILLE_*` est exportée (`tests/test_isolation.py`).

Pour le conteneur (voir `docs/exploitation.md`) :

- `veille instantane creer <dossier>` et `veille instantane verifier <dossier>` : l'instantané de `/donnees` que le modèle sauvegarde et restaure (`deploiement/projet.env`). `verifier` rend 0 (sain), 2 (non sain) ou 64 (usage).
- `veille factice` : charge le jeu de `factice/` dans une base vide (le staging le fait seul au démarrage).
- `sh tests/deploiement/lancer.sh` : le banc de tests du déploiement, qui demande Docker.
- `copier update` sous Git Bash demande `MSYS_NO_PATHCONV=1`, sinon `/sante` est réécrit en chemin Windows. Le dossier `.superpowers/` est à sortir du dépôt le temps de la mise à jour : copier le prend pour un arbre sale.

Le reste des commandes est dans `README.md`.

## Ce qui fait foi

*Pour chaque sujet, l'endroit où la réponse se trouve. En cas de désaccord, c'est cet endroit qui a raison.*

- Le comportement, c'est le code et les tests.
- Les décisions, ce sont `docs/decisions/` et `docs/modele/decisions/`.
- La feuille de route, ce sont les issues (une milestone par étape) et `docs/pistes.md`. Les issues ouvertes avant la naissance (#6, #12) sont restées au dépôt de données.
- Les constats, c'est `docs/registre.md`, celui des deux dépôts : le dépôt de données n'a pas de registre. Les leçons d'avant le modèle sont dans `docs/METHODE.md`.
- Ce qui tourne sur le tailnet, c'est le clone du serveur, sur `principal` : une correction n'y arrive que par `git pull`.
- Les critères de score, ce sont le `config/criteres.yaml` du dépôt de données (la configuration de l'instance ; le code tourne par défaut sur `exemple/`) et `docs/CRITERES.md`. Le seuil de notification et la fréquence de collecte vivent en base (table `reglages`, réglés dans Réglages) ; `seuil_interessant` du YAML n'en est que la graine, importée au premier démarrage.
- Ce qui tourne dans le conteneur, c'est `deploiement/` (les fichiers gérés par le modèle, `projet.env`, `compose.projet.yml`, les `.cles`) et `docs/exploitation.md`.
- Le mode d'emploi, c'est `README.md` et les documents qu'il liste. Ce qui est propre à l'instance réelle (le serveur, ses chemins et ses adresses, les arbitrages et les constats sur sa base), c'est le dépôt de données : son `CLAUDE.md` et son `docs/`, où chaque document porte le nom de son document d'origine.

## Invariants — ne jamais violer

Les invariants communs sont dans `docs/modele/methode.md`. Ceux-ci sont propres au projet.

1. **On normalise pour comparer, jamais pour écrire.** Ce qui part chez un recruteur garde ses accents : les libellés d'un fichier de critères sont accentués (ceux de `exemple/criteres.yaml`, que `tests/test_accents.py` garde), et les fixtures de `tests/test_assemblage.py` le sont aussi depuis le correctif du 15/10. Les libellés de la configuration d'une instance, aucun test ne les garde : la suite ne la lit pas, et `veille config verifier` ne les contrôle pas (`docs/pistes.md`).
2. **Enregistrer n'est jamais bloqué ; envoyer peut l'être.** Un éditeur qui refuse de sauvegarder un texte intermédiaire est inutilisable, à plus forte raison au téléphone (`src/veille/porte.py`).
3. **Un contrôle qui n'a pas pu tourner est `indisponible`, jamais `ok`.** Un vert sans vérification trompe au moment précis où l'on s'y fie (`src/veille/porte.py`).
4. **Un retour arrière est une nouvelle version, jamais une suppression.** Ce qu'on remplace entre d'abord dans l'historique : écrasé à chaque affinement, l'ancien `lettre-assemblee.md` a fait restaurer un texte écrit par le modèle.
5. **Les secrets ne vont pas dans les tests.** Un fichier de test est versionné, lu, copié, envoyé ; `tests/test_javascript.py` y cherche les formes de secret (`docs/METHODE.md`).
6. **Une variable `VEILLE_*` ou `FT_*` inconnue arrête le programme.** Un nom mal tapé, ignoré en silence, a fait tourner un script sur la vraie base (`docs/METHODE.md`, `config.verifier_environnement()`).
7. **Les fins de ligne ne se normalisent pas en passant.** 40 fichiers sont en CRLF et 2 mêlent les deux, et une normalisation changerait les empreintes du kit et des gabarits : elle se fait dans une PR qui n'a que ce but.

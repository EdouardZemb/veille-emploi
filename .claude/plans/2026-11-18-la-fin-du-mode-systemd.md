# La fin du mode systemd (veille-emploi#34) — plan

> **Pour les agents :** compétence requise, *superpowers* `subagent-driven-development` (recommandée) ou `executing-plans`, tâche par tâche. Les étapes se cochent (`- [ ]`). Les étapes 👤 sont des gestes d'Edouard : la session les prépare et ne les lance pas. Une session lit le serveur, elle n'y écrit jamais.

**Objectif :** sans `VEILLE_EMPLOI_ENV`, la console devient un mode local, sans systemd : celui du poste, des tests et du test de restauration du modèle. Le code n'appelle plus `systemctl`, ne lit plus `config/.env` d'office et n'a plus `veille init` ; les clés des notifications naissent au démarrage dans tous les modes. Le dépôt de données perd `scripts/tailnet/` et ses textes de la console du tailnet ; le serveur perd ses restes (issue `veille-emploi#34`).

**Architecture :** le lot retire plus qu'il n'ajoute. Côté serveur, trois branches `environnement() is None` tombent (les clés, « Collecter maintenant », la fréquence) et le mode local prend le chemin du staging. Côté ligne de commande, le repli sur `config/.env` et `veille init` partent. Deux gardes s'ajoutent : un test qui refuse dans la source les mots du mode retiré, et une étape du job `image` qui lance l'image sans aucune variable. Les documents suivent, avec le geste de copie du kit en prod ; puis les gestes 👤 du serveur, un soir, avec la PR de `serveur` ; puis la PR du dépôt de données.

**Pile :** Python 3.13, FastAPI, SQLite ; JavaScript sans framework ; pytest ; Playwright (`tests_navigateur/`) ; Docker et GitHub Actions (job `image`) ; ssh depuis le poste, par `!`, pour les gestes 👤 du serveur.

**Spec :** l'issue `veille-emploi#34` (l'objectif, les dix critères d'acceptation, le hors-périmètre) ; les douze décisions d'Edouard du 18/11/2026, « Ok pour les défauts », reprises ci-dessous (« Le cadrage ») et citées « cadrage N » ; ses réponses du 18/11/2026 aux dix questions de la revue du plan, « ok pour les défauts », citées « réponse N » ; l'ADR-0002, § 1 ; la piste `docs/pistes.md:15`.

**Préalables :** le plan fusionné, dans le worktree `veille-emploi.worktrees\fin-systemd` : `git fetch origin`, puis `git switch --no-track -c feat/fin-systemd origin/principal` ; `python -m venv .venv`, `.venv\Scripts\python -m pip install -e .[dev,navigateur]`, `.venv\Scripts\python -m playwright install chromium`. `git rev-parse --git-path hooks` y rend `.githooks`.

## Mécanismes annoncés

- `src/veille/config.py:136-138` — `def environnement` — rend `None` sans `VEILLE_EMPLOI_ENV` : c'est le mode local, que le lot garde
- `src/veille/config.py:29` — `Les secrets vivent dans config/.env` — le commentaire des secrets nomme encore `config/.env`
- `src/veille/config.py:73` — `"VEILLE_ENV"` — `VEILLE_ENV` est une variable connue ; `VARIABLES_CONNUES` (`config.py:69-92`) garde aussi `VEILLE_EMPLOI_ENV`, et le lot n'y retire ni n'y ajoute rien
- `src/veille/config.py:199` — `_non_vide(montee)` — `/config` n'est lu qu'avec `VEILLE_EMPLOI_ENV` : le mode local sert `VEILLE_CONFIG`, ou l'exemple
- `src/veille/config.py:230-231` — `if environnement() != "prod":` — seule la prod refuse de démarrer sans configuration : le mode local démarre sur l'exemple
- `src/veille/app.py:56-64` — `if mode is not None:` — les clés des notifications ne naissent au démarrage qu'en conteneur ; le jeu factice, qu'en staging
- `src/veille/app.py:65` — `PLANIFICATEUR.demarrer()` — le planificateur démarre dans tous les modes
- `src/veille/app.py:106-109` — `def _sert_l_exemple_par_oubli` — sans `VEILLE_EMPLOI_ENV` ni configuration désignée, la page porte le bandeau et les gestes sur une offre refusent
- `src/veille/app.py:1218` — `except (ValueError, RuntimeError) as exc:` — la route de la fréquence rattrape le `RuntimeError` que seule l'écriture dans l'unité systemd lève
- `src/veille/app.py:1231` — `if environnement is not None and environnement != "prod":` — sans `VEILLE_EMPLOI_ENV`, « Collecter maintenant » passe ce refus
- `src/veille/app.py:1241-1249` — `"veille-collecte.service"` — sans `VEILLE_EMPLOI_ENV`, le bouton lance `systemctl --user start veille-collecte.service` par `subprocess.run` ; là où `systemctl` manque, l'appel lève `FileNotFoundError`
- `src/veille/app.py:1367` — `config.environnement() or "local"` — `/sante` dit `local` sans `VEILLE_EMPLOI_ENV`
- `src/veille/static/app.js:36` — `collecte_coupee: "La collecte est coupée sur cette console."` — ce que le bouton affiche sur un 409 `collecte_coupee`
- `src/veille/reglages.py:28-29` — `UNITE_TIMER = "veille-collecte.timer"` — le nom et le chemin de l'unité du minuteur
- `src/veille/reglages.py:33-58` — `"oncalendar":` — chaque fréquence porte une expression `OnCalendar`, que seul systemd lit ; ses `heures` servent au planificateur
- `src/veille/reglages.py:35` — `Trois fois par jour (7h15, 12h15, 18h15)` — les libellés qu'Edouard lit énumèrent les heures de leur fréquence
- `src/veille/reglages.py:93-96` — `def _systemctl` — le seul appel de `systemctl` du module
- `src/veille/reglages.py:99-101` — `def prochain_passage` — le prochain passage se calcule sur les `heures`, jamais sur `oncalendar`
- `src/veille/reglages.py:121-135` — `def _lire_frequence_conteneur` — la fréquence lue en base rend `cle`, `oncalendar`, `personnalise`, `prochain_passage`, `actif` (vrai en prod seulement), `mode`, `etat` et `choix`
- `src/veille/reglages.py:138-150` — `def lire_frequence` — la base en conteneur, l'unité sous systemd, et `indisponible` là où `systemctl` manque
- `src/veille/reglages.py:178-206` — `def ecrire_frequence` — la base en conteneur ; sinon, la réécriture de l'unité, `daemon-reload` et `restart`, ou un `RuntimeError`
- `src/veille/static/app.js:380-384` — `Fréquence indisponible` — Réglages affiche « Fréquence indisponible » et « Réglage personnalisé en place »
- `src/veille/planificateur.py:137-138` — `if config.environnement() != "prod":` — hors prod, le planificateur purge, mais ne collecte ni ne vérifie
- `src/veille/planificateur.py:1` — `sans minuteur systemd` — la docstring compare encore au minuteur systemd et à la console sans conteneur (`planificateur.py:1-18`, `:44`)
- `src/veille/collecte.py:3` — `que lance le minuteur systemd` — la docstring nomme le minuteur du serveur du tailnet
- `src/veille/notifications.py:31` — `RACINE / "config" / "vapid.json"` — sans `VEILLE_VAPID`, les clés vont dans `config/vapid.json` du clone
- `src/veille/notifications.py:92` — `CHEMIN_VAPID.parent.mkdir(parents=True, exist_ok=True)` — `generer_vapid` crée le dossier des clés s'il manque
- `src/veille/notifications.py:119` — `elle nait au demarrage de la console` — l'avertissement d'un push sans clé conseille encore `veille init`
- `src/veille/notifications.py:212` — `dans config/.env` — le repli mail sans identifiant renvoie à `config/.env`
- `src/veille/notifications.py:305` — `et le HTTPS du tailnet` — l'erreur d'une notification perdue renvoie à `config/.env` et au tailnet
- `src/veille/notifications.py:4` — `tailscale serve` — la docstring du module décrit l'exposition par le tailnet
- `src/veille/cli.py:29-31` — `racine / "config" / ".env"` — sans `VEILLE_ENV`, la ligne de commande lit le `config/.env` du clone
- `src/veille/cli.py:32-34` — `if not chemin.exists():` — un fichier absent est ignoré sans un mot ; un `VEILLE_ENV` vide désigne `.`, qui existe, et `read_text` sur ce dossier fait tomber l'import
- `src/veille/cli.py:39` — `os.environ.setdefault` — une variable déjà posée l'emporte sur le fichier
- `src/veille/cli.py:60-71` — `def cmd_init` — `veille init` prépare la base et génère les clés si le fichier manque
- `src/veille/cli.py:880` — `sp.add_parser("init"` — le parseur de `veille init`
- `src/veille/cli.py:3` — `veille init` — la docstring du module la liste
- `src/veille/cli.py:513` — `Renseigne VEILLE_KIT dans config/.env` — `veille kit` renvoie à `config/.env`
- `src/veille/cli.py:618-619` — `sans conteneur` — `veille tester-notification` cite encore `veille init`
- `src/veille/cli.py:640` — `configuration incomplete, voir config/.env` — `veille tester-mail` renvoie à `config/.env`
- `src/veille/cli.py:282-286` — `db.relances_dues()` — `veille etat` imprime les relances dues, titre et employeur compris
- `src/veille/empreintes.py:78-80` — `RACINE / "config" / ".env"` — sans `VEILLE_KIT`, le kit réel se cherche dans le fichier que désigne `VEILLE_ENV`, un `VEILLE_ENV` vide valant absent, sinon dans le `config/.env` du clone ; sans ce repli, un `VEILLE_ENV` vide vaudrait `.`, que `exists()` accepte et que `read_text` refuse
- `src/veille/empreintes.py:37` — `from .config import DOSSIER_CONFIG, RACINE` — `RACINE` ne sert dans `empreintes.py` qu'à ce repli
- `src/veille/affinement.py:57` — `que le service systemd charge deja` — les jetons de l'affinement sont dits lus dans `config/.env` par le service systemd
- `src/veille/affinement.py:65` — `BIN_LOCAL = Path.home()` — le dossier ajouté en tête du `PATH` du sous-processus
- `src/veille/affinement.py:459-462` — `environnement["PATH"]` — le sous-processus reçoit `~/.local/bin` devant le `PATH` de la console
- `src/veille/affinement.py:236` — `dans config/.env` — le refus d'un jeton absent renvoie à `config/.env`
- `src/veille/affinement.py:390` — `dans config/.env sous CLAUDE_CODE_OAUTH_TOKEN` — le message d'un échec d'authentification aussi
- `src/veille/affinement.py:91` — `tailscale` — une mesure datée du 02/10 nomme le proxy d'alors
- `src/veille/documents.py:119` — `VEILLE_KIT dans config/.env` — le message d'un kit absent renvoie à `config/.env`
- `src/veille/collectors/courriel.py:29` — `Configuration dans config/.env` — la docstring du collecteur
- `src/veille/collectors/france_travail.py:5` — `renseignes dans config/.env` — la docstring du collecteur
- `src/veille/enrichissement.py:19` — `jamais depuis veille-collecte.timer` — la règle nomme le minuteur
- `src/veille/auth.py:3` — `le tailnet` — le pourquoi des passkeys parle du tailnet
- `src/veille/debit.py:4` — `tailscale serve` — le pourquoi de la limite de débit aussi
- `src/veille/app.py:6-7` — `sur le serveur du tailnet` — la docstring de l'application décrit l'exposition par le tailnet
- `src/veille/app.py:77-78` — `tailscale` — le commentaire de la limite des routes anonymes aussi
- `src/veille/static/app.js:2301` — `vapid: "Le serveur` — la raison d'un push sans clé cite encore `veille init`
- `src/veille/templates/index.html:31-36` — `puis redémarre la console` — le bandeau de l'exemple servi par oubli parle du serveur
- `src/veille/planificateur.py:227` — `name="veille-collecte"` — le fil de « Collecter maintenant » porte ce nom, qui n'est pas une unité
- `src/veille/instantane.py:97` — `dossier / "vapid.json"` — l'instantané emporte `vapid.json` quand il existe : la copie d'une sauvegarde de la prod porte déjà la paire
- `deploiement/tester-restauration.sh:166-169` — `.statut == "ok"` — le test de restauration lance l'image sur la copie, sans aucune variable, et attend `statut` `ok`
- `deploiement/lib.sh:318-319` — `VEILLE_EMPLOI_OPTIONS_JETABLES=(--user 1000:1000 --read-only` — les options de ce lancement : uid 1000, racine en lecture seule, aucune capacité, 384 Mo
- `deploiement/lib.sh:166-168` — `local clone_donnees=` — la sonde lit `~/veille-emploi-donnees` en prod et `~/veille-emploi-donnees-staging` en staging
- `deploiement/systemd/veille-emploi-sonde.service.in:9-10` — `ExecStart=/bin/bash @CLONE@/deploiement/sonder.sh @ENV@` — l'unité de la sonde ne nomme que son clone, et seul `PATH` est dans son environnement
- `Dockerfile:43` — `VEILLE_VAPID=/donnees/vapid.json` — dans l'image, les clés vont dans `/donnees`
- `Dockerfile:36` — `RUN mkdir /donnees && chown 1000:1000 /donnees` — `/donnees` appartient à l'uid 1000 dans l'image
- `.github/actions/modele-image-construire/action.yml:50-53` — `-e VEILLE_EMPLOI_ENV=ci` — la CI ne lance l'image qu'avec `VEILLE_EMPLOI_ENV=ci` ; ce conteneur fait déjà naître les clés en uid 1000 sur une racine en lecture seule, mais rien n'éprouve un lancement sans variable
- `.github/workflows/ci.yml:14-16` — `cancel-in-progress` — un envoi sur une PR annule son exécution précédente
- `.github/workflows/ci.yml:50` — `de systemd ou de POSIX` — le commentaire de `SUITE_COMPLETE` nomme systemd
- `.github/workflows/ci.yml:169-171` — `docker rm -f -v veille-emploi` — le conteneur de la CI est retiré à la fin du job, quoi qu'il arrive
- `.dockerignore:9` — `donnees` — le dossier `donnees` n'entre pas dans l'image ; `config` non plus (`.dockerignore:12`)
- `.gitignore:2` — `donnees/` — `donnees/` est ignoré par git ; `config/.env` et `config/vapid.json` aussi (`.gitignore:3-5`)
- `tests/sauts.py:3` — `systemd utilisateur` — la docstring des sauts nomme systemd et le serveur
- `tests/test_reglages.py:25-36` — `def _systemd_utilisateur` — la sonde de systemd utilisateur des tests
- `tests/test_reglages.py:123-124` — `sauter(_systemd_utilisateur)` — le seul test qui se saute faute de systemd
- `tests/test_reglages.py:161` — `def test_frequence_indisponible_sans_systemctl` — la fréquence `indisponible` sans `systemctl`
- `tests/test_reglages.py:172` — `client.get("/api/reglages").status_code == 200` — la seule assertion d'un 200 sur `GET /api/reglages`, dans ce test que le lot retire
- `tests/test_reglages.py:175-189` — `"_systemctl"` — le test de la fréquence en conteneur remplace `reglages._systemctl`
- `tests/test_reglages.py:226-229` — `def test_chaque_frequence_a_des_heures_coherentes` — le seul recoupement des heures de chaque fréquence, par `oncalendar`
- `tests/test_planificateur.py:113-124` — `"_systemctl"` — `test_pas_de_collecte_hors_prod` remplace aussi `reglages._systemctl`
- `tests/test_planificateur.py:519` — `def systemctl(monkeypatch)` — la fixture qui retient les appels de `systemctl`
- `tests/test_planificateur.py:554` — `def test_collecter_maintenant_sous_systemd` — le bouton sans `VEILLE_EMPLOI_ENV` lance l'unité
- `tests/test_factice.py:161-162` — `@pytest.mark.parametrize("mode", ["prod", "staging"])` — les clés naissent au démarrage en prod et en staging
- `tests/test_factice.py:193-195` — `def test_sans_mode_les_cles_ne_naissent_pas` — sans mode, elles ne naissent pas
- `tests/test_push_plomberie.py:229` — `assert "veille init" in message` — l'avertissement sans clé doit nommer `veille init`
- `tests/test_cli_renvois.py:47-48` — `sans conteneur` — la sortie de `veille tester-notification` doit citer `veille init`
- `tests/test_affinement.py:324` — `assert "config/.env" in d.raison` — le refus d'un jeton absent doit nommer `config/.env`
- `tests/test_affinement.py:350` — `assert "config/.env" in m` — le message d'un échec d'authentification aussi
- `tests/test_affinement.py:355` — `def test_le_sous_processus_recoit_un_path_qui_trouve_claude` — le `PATH` du sous-processus doit commencer par `BIN_LOCAL`
- `tests/test_instance.py:107-119` — `configuration_non_designee` — sans `VEILLE_EMPLOI_ENV` ni configuration, le bouton rend 409 `configuration_non_designee`
- `tests/conftest.py:25` — `os.environ["VEILLE_ENV"]` — la suite pointe `VEILLE_ENV` sur un fichier absent
- `tests/conftest.py:21` — `os.environ["VEILLE_VAPID"]` — la suite pointe `VEILLE_VAPID` sur un fichier de son dossier temporaire
- `tests/test_isolation.py:29` — `def test_la_suite_ne_lit_pas_le_fichier_d_environnement_de_la_console` — sa docstring dit `config/.env` lu par défaut
- `tests/test_deploiement.py:335` — `"donnees", "donnees/veille.sqlite3", "donnees/kit/cv.pdf",` — l'image garde `donnees/` hors d'elle, vérifié par la base et le kit seulement
- `tests/test_deploiement.py:336` — `"config/vapid.json"` — l'image doit ignorer `config/.env`, `config/auth.json` et `config/vapid.json`
- `tests/test_deploiement.py:363` — `La console du tailnet garde config/.env` — la docstring d'un test des fichiers locaux
- `tests/test_javascript.py:108` — `console sans conteneur` — un commentaire d'un fichier aux fins de ligne mêlées
- `tests_navigateur/conftest.py:32-35` — `os.environ["VEILLE_HTTPS"] = "0"` — la console des tests du navigateur ne pose pas `VEILLE_EMPLOI_ENV`, et pointe `VEILLE_VAPID` sur un fichier temporaire
- `tests_navigateur/test_plus.py:1173-1174` — `if not notifications.CHEMIN_VAPID.exists():` — la fixture `cles_push` ne crée la paire que si elle manque
- `exemple/.env.exemple:2` — `Copie ce fichier en` — le modèle des secrets se recopie en `config/.env`
- `exemple/.env.exemple:71` — `EnvironmentFile` — il dit le fichier chargé par le service systemd
- `docs/exploitation.md:36` — `~/.local/share/veille-emploi/prod/donnees` — le dossier des données de la prod, sur le serveur, que son conteneur monte sur `/donnees`
- `docs/exploitation.md:105-106` — `Le test de restauration du modèle` — l'image lancée sans variable et une santé `ok` attendue
- `docs/exploitation.md:162` — `est un oubli de` — l'exemple servi sans `VEILLE_EMPLOI_ENV` est un oubli
- `docs/exploitation.md:680` — `<le clone du tailnet>` — le nom du clone de l'ancienne console
- `docs/exploitation.md:887` — `restent sur le serveur` — le clone du tailnet, ses données et `~/bascule-veille-emploi` restent jusqu'au retrait du mode systemd
- `docs/CANDIDATURE.md:80-99` — `Copier ton kit sur le serveur` — le geste de copie du kit vise le clone de la console, par `scp` puis `./.venv/bin/veille kit`
- `docs/DEMARRAGE.md:6` — `Les commandes se lancent dans le clone de la console sur le serveur` — le guide suppose une console dans un clone
- `docs/ALERTES.md:75` — `cd <le clone>` — la vérification des alertes se lance dans le clone
- `docs/CRITERES.md:20` — `cd <le clone>` — le recalcul après un changement de critères aussi
- `docs/DONNEES.md:157` — `veille-*.{service,timer}` — « Tout effacer » retire toute unité `veille-*`, celles du modèle comprises
- `docs/decisions/0002-la-console-en-conteneur.md:70` — `Le mode systemd est retiré après le #12` — le § 1 de l'ADR annonce ce lot
- `docs/pistes.md:15` — `Retirer le mode systemd après le #12` — la piste de ce lot
- `CLAUDE.md:19` — `Le code a deux modes` — l'État décrit les deux modes
- `CLAUDE.md:47` — `Sur une console sans conteneur, depuis son clone` — le bloc des commandes du mode systemd
- `deploiement/secrets/prod.cles:13` — `vides sur la console du tailnet` — un commentaire du projet parle au présent de la console retirée
- `pyproject.toml:54` — `only_mutate` — mutmut ne mute que `etats.py` et `preparation.py`
- `veille-emploi-donnees:README.md:13` — `scripts/tailnet/` — le README des données liste les scripts de la console du tailnet
- `veille-emploi-donnees:docs/exploitation.md:22` — `<le clone du tailnet>` — la table des rôles traduit ce nom
- `veille-emploi-donnees:docs/exploitation.md:24` — `le clone des données de la console du tailnet` — cette ligne de la table n'a pas de nom entre chevrons ; la session y lit la valeur de `<le clone des données du tailnet>` pour la note privée
- `veille-emploi-donnees:docs/exploitation.md:28` — `restent sur le serveur jusqu` — le clone du tailnet et celui de ses données attendent ce lot
- `veille-emploi-donnees:docs/exploitation.md:489` — `ls -d ~/bascule-veille-emploi` — les dossiers de l'instantané de la bascule attendent ce lot
- `veille-emploi-donnees:docs/exploitation.md:663` — `les attend tant` — la déclaration de `serveur` attend les fichiers d'unités tant qu'ils existent
- `veille-emploi-donnees:CLAUDE.md:100` — `Vers le 13/11/2026` — l'étape 9 du geste des deux clones, le retrait de la copie d'avant la scission, se dit encore à faire
- `veille-emploi-donnees:scripts/tailnet/installer.sh:53-64` — `WorkingDirectory=$RACINE` — `veille-web.service` écrit le chemin absolu du clone du tailnet : il est le témoin de la recherche de références
- `veille-emploi-donnees:scripts/tailnet/installer.sh:74-81` — `ExecStart=$RACINE/.venv/bin/veille collecter` — `veille-collecte.service` aussi
- `veille-emploi-donnees:scripts/tailnet/maj-jeton-claude.sh:3` — `Raccorde tous les consommateurs du serveur au jeton Claude` — ce script sert aussi d'autres services du serveur
- `serveur:services/veille-console.env:11` — `UNITES_UTILISATEUR=` — `serveur` déclare les cinq unités de la console du tailnet
- `serveur:inventaire/releve.py:924` — `SECRETS_SOUS_HOME = [` — le relevé de `serveur` nomme trois fichiers locaux du clone du tailnet
- `serveur:inventaire/releve.py:1100-1107` — `NON_DECLARE_AU_REGISTRE` — le relevé ne signale qu'un fichier présent : les lignes d'un fichier parti ne donnent plus rien
- `serveur:inventaire/systemd/inventaire-nocturne.timer:7` — `OnCalendar=*-*-* 05:30:00` — le relevé de `serveur` tourne chaque nuit à 05:30
- `serveur:inventaire/comparaison.py:128-134` — `unite-utilisateur` — une unité déclarée que systemd ne connaît pas donne une ligne `declare-absent`
- `serveur:inventaire/alertes.py:9-19` — `déclarés absents : <total>` — un total non nul est une alerte, qui fait échouer `serveur-inventaire` ; aucune ligne `ABSENT_DU_DISQUE` de la rubrique `secrets-registre` n'en est une aujourd'hui
- `serveur:docs/registre.md:28` — `LE-013` — la sortie prévue du LE-013 de `serveur` fera une alerte de chaque ligne `ABSENT_DU_DISQUE`, une fois retirée l'entrée de la console
- `serveur:docs/fiches/README.md:69` — `references()` — avant un retrait, `serveur` cherche ce qui nomme la cible dans les unités utilisateur et système, `~/bin`, `/usr/local/bin`, les composes et la crontab, en chemins et en nombres seulement
- `serveur:docs/fiches/README.md:82-85` — `secrets-registre` — il lit aussi cette rubrique du dernier relevé ; un changement du registre est un geste d'Edouard
- `serveur:docs/fiches/README.md:93` — `restes()` — il cherche ce qu'un outil a écrit sous le compte, en chemins et tailles
- `serveur:CLAUDE.md:95` — `services/veille-console.env` — le `CLAUDE.md` de `serveur` décrit la console du tailnet déclarée, et ses unités en attente de ce lot
- `serveur:CLAUDE.md:97-98` — `Sa copie` — la copie d'avant la scission y est dite retirée le 13/11/2026 ; la session y lit la valeur de `<la copie d'avant la scission>` pour la note privée

## Outils et cas limites

- `TestClient` de Starlette — sans `with`, il ne lance pas le cycle de vie : un test qui l'ouvre ainsi ne fait jamais naître les clés — `test_les_cles_push_naissent_au_demarrage_dans_tous_les_modes` passe par `_demarrer()` (`with TestClient(app)`), et vérifie la paire intacte au second démarrage (tâche 1)
- `TestClient`, une exception de la route — il la relaie au test au lieu d'un 500 : sous Windows, l'ancien bouton sans `VEILLE_EMPLOI_ENV` lève le `FileNotFoundError` de `systemctl`, et sur un Linux à systemd utilisateur il lancerait vraiment l'unité — l'étape 2 de la tâche 1 attend cette erreur, et ne se lance que sur le poste
- uvicorn, le cycle de vie — il ne sert aucune requête avant la fin de `cycle_de_vie` : une santé `ok` dit que les clés sont déjà écrites, ou que leur écriture a été tentée sans lever — l'étape « L'image démarre sans aucune variable » lit `/sante`, puis `test -s /donnees/vapid.json` (tâche 3)
- `monkeypatch.setattr` — il lève `AttributeError` sur un attribut absent : chaque test qui remplace `reglages._systemctl` casse dès que la fonction part, au lieu de passer sans rien garder ; de même pour `empreintes.RACINE`, dont l'import devient inutile — l'étape 2 de la tâche 1 lit ces erreurs, et `test_le_kit_ne_se_lit_plus_dans_le_config_env_du_clone` remplace `RACINE` avec `raising=False` (tâche 2)
- argparse, sous-commandes requises — une sous-commande inconnue sort par `SystemExit(2)`, son message sur la sortie d'erreur, sans rien lancer — `test_veille_init_n_existe_plus` (tâche 2)
- `pathlib.Path("")` — il vaut `.`, qui existe : un `VEILLE_ENV` vide désignerait le dossier courant, que `read_text` refuse en faisant tomber l'import de `veille.cli`, ou `veille empreintes-kit` — `test_un_veille_env_vide_ne_fait_pas_tomber_l_import`, et le cas du vide de `test_le_kit_ne_se_lit_plus_dans_le_config_env_du_clone` (tâche 2)
- `re`, le garde de la source — `\W+` entre deux mots trouve un mot coupé par une ligne, un `#` ou un `//`, et `re.IGNORECASE` une majuscule ; `_` est une lettre pour `\W`, si bien que `sans_conteneur` et `veille_init` ne comptent pas ; `init\b` écarte « initialise » ; une unité ne compte qu'avec son suffixe, si bien que le fil `veille-collecte` ne compte pas — `test_le_garde_trouve_chaque_motif`, un cas par motif, et `test_le_garde_laisse_ce_qui_ne_parle_pas_du_mode`, paramétrés (tâche 2)
- un sous-processus Python qui importe une copie de `src/veille` — un `veille` installé en mode éditable peut l'emporter sur la copie, et le test lirait le vrai clone — `test_sans_veille_env_le_config_env_du_clone_n_est_pas_lu` imprime `cli.__file__` et exige qu'il soit sous `tmp_path` (tâche 2)
- `docker run -v /donnees`, un volume anonyme — un volume neuf reçoit le contenu et le propriétaire du dossier de l'image (uid 1000, `Dockerfile:36`) : l'étape part d'un volume vide, sans base ni clés, là où le test de restauration monte la copie d'une sauvegarde, qui porte déjà `vapid.json` (`instantane.py:97`) ; elle éprouve le démarrage du mode local dans l'image, pas la restauration — l'étape « L'image démarre sans aucune variable » et ses mutants M1 et M2 (tâche 3) ; le premier test de restauration du dimanche après `v0.5.0` (tâche 8)
- `curl -fsS … | jq -e` sous le `bash -eo pipefail` d'Actions — `curl -f` échoue sur un 503 (`statut` `ko`), `jq -e` rend 1 sur `false` et 4 sans entrée ; juste après `docker run -d`, la console ne répond pas encore — l'étape attend un 200 jusqu'à 60 s avant de lire la santé, et son mutant M1 (`-e VEILLE_EMPLOI_ENV=ci`) la fait échouer sur `environnement` (tâche 3)
- `concurrency` de `ci.yml`, `cancel-in-progress` — l'envoi suivant annule l'exécution d'un mutant avant que son job `image` ait rendu son journal — la tâche 3, étape 3, attend la fin du job `image` de chaque mutant, conclu `failure` et non `cancelled`, avant l'envoi suivant
- `ssh` lancé par `!`, donc par Git Bash — entre guillemets doubles, `$` est développé sur le poste et `\"` devient `"`, alors que `~`, `*` et les apostrophes passent tels quels au shell du serveur, qui les développe — aucune commande 👤 de la tâche 5 ne porte de `$`, celle des composes écrit ses guillemets `\"`, et la lecture de l'inventaire par la session le vérifie avant toute suppression (tâche 5)
- `grep -F`, la recherche de références — un motif trouve aussi tout fichier qui nomme un chemin plus long qui le contient ; un vide vient aussi d'un motif mal traduit, d'une faute de frappe ou d'un dossier mal passé ; la recherche ne rend que des chemins et un nombre de lignes, jamais une ligne, qu'une crontab peut porter un secret — l'étape 3 de la tâche 5 exige d'abord son témoin, `veille-web.service` et `veille-collecte.service` trouvés sous `~/.config/systemd/user`, puis qu'aucun chemin trouvé, pour les trois motifs ensemble, ne soit hors des unités à retirer, ce qui vaut pour chacun
- `find -maxdepth 1`, la recherche des restes — elle ne voit qu'un niveau sous chaque dossier, ni les clones du tailnet ni une copie oubliée à côté d'eux — la tâche 5 cherche par `ls -d` les clones du tailnet et leurs voisins (`<le clone du tailnet>*`), les dossiers de l'instantané et `<la copie d'avant la scission>`
- `git status -sb` — il réécrit l'index du clone qu'il lit, et ne voit ni une remise ni une branche locale non envoyée — l'inventaire de la tâche 5 passe par `git --no-optional-locks`, et ajoute `stash list` et `log --branches --not --remotes` pour chaque clone

## Effets cherchés

- Le mode local démarre sans aucune variable, sa santé `ok` et `local` (cadrage 3 et 5, critère 6) — le test de restauration du modèle, chaque dimanche à 05:30, qui lance l'image de la prod sur la copie d'une sauvegarde sans aucune variable (`deploiement/tester-restauration.sh:166-169`) : il passe désormais par le mode local, et trouve la paire de la sauvegarde ; toute image lancée à la main sans `-e` — l'étape « L'image démarre sans aucune variable » du job `image`, éprouvée par les mutants M1 et M2 (tâche 3) ; après `v0.5.0`, le premier test de restauration du dimanche vert dans Healthchecks (tâche 8)
- Les clés naissent au démarrage du mode local (cadrage 5) — la console des tests du navigateur (job `navigateur`), dont chaque page porte une clé `data-vapid` dès le premier test, et dont l'état du push passe d'« indisponible » à « inactives » ; la suite, dont chaque `TestClient` ouvert par `with` écrit la paire dans le `VEILLE_VAPID` temporaire de `tests/conftest.py:21` — la suite entière et celle du navigateur, lancées à l'étape 4 de la tâche 1 ; les jobs `verifier` et `navigateur` de la PR
- Le chemin des clés par défaut devient `donnees/vapid.json` (décision 3, réponse 5) — un poste qui lance `veille servir` sans `VEILLE_VAPID` : les clés naissent dans `donnees/` du clone, ignoré par git (`.gitignore:2`) et par l'image (`.dockerignore:9`), et un `config/vapid.json` resté d'avant n'est plus lu ; l'image pose `VEILLE_VAPID` et ne change pas — `test_les_cles_vont_par_defaut_dans_donnees`, et `donnees/vapid.json` ajouté aux fichiers que l'image doit ignorer (`tests/test_deploiement.py:335`) (tâche 1)
- `veille init` retirée, `config/.env` plus lu d'office (cadrage 5 et 6, réponse 8) — le poste d'Edouard : `veille init` répond par l'erreur d'usage d'argparse, un `config/.env` laissé dans un clone n'est plus lu, ses secrets se désignent par `VEILLE_ENV`, et un `VEILLE_ENV` vide ou qui désigne un fichier absent est ignoré sans un mot ; l'image, où `/app/config/.env` n'a jamais été (`.dockerignore:12`), ne change pas ; `CLAUDE.md`, `docs/DEMARRAGE.md` et `exemple/.env.exemple` le disent — `test_veille_init_n_existe_plus`, `test_sans_veille_env_le_config_env_du_clone_n_est_pas_lu`, `test_un_veille_env_vide_ne_fait_pas_tomber_l_import` et `test_le_kit_ne_se_lit_plus_dans_le_config_env_du_clone` (tâche 2) ; la recherche de la tâche 4
- Réglages en mode local : la fréquence en base, sans « Fréquence indisponible » ni « Réglage personnalisé » (cadrage 3, décision 2) — l'écran Réglages d'une console du poste et de la console des tests du navigateur ; le JSON de `GET /api/reglages`, qui perd `oncalendar`, `personnalise`, `mode`, `etat` et `raison`, et qu'une page de l'image 0.4.0 restée ouverte lit comme des valeurs fausses, sans avertissement — `test_la_frequence_vit_en_base_dans_tous_les_modes`, `test_la_frequence_rend_ses_seules_cles` (la route comprise) et `test_reglages_ne_montre_plus_la_frequence_de_l_unite` (tâche 1) ; la suite du navigateur, dont la console est en mode local ; au staging, la non-régression (tâche 6, étape 5)
- « Collecter maintenant » refuse en mode local (cadrage 4) — l'écran Réglages d'une console du poste, qui dit « La collecte est coupée sur cette console. » (`app.js:36`) ; `veille collecter` reste en ligne de commande — `test_collecter_maintenant_selon_le_mode` et `test_en_prod_le_bouton_collecter_refuse_sans_configuration` (tâche 1) ; `test_collecte_refuse_sans_configuration_designee`, gardé
- Les tests propres à systemd partent (cadrage, ce qui découle du code) — la CI : le job `verifier` (`SUITE_COMPLETE=1`, `-rs`), dont la liste des sauts reste celle des six tests du kit ; la suite du poste sous Windows, qui ne saute plus rien faute de systemd ; `tests/sauts.py` et `CLAUDE.md` ne nomment plus systemd — le journal du job `verifier` de la PR (tâche 6, étape 1) ; la recherche de la tâche 4
- Les gestes des documents visent le conteneur de la prod, et la copie du kit s'écrit (réponse 6) — Edouard, à la main : chaque `./.venv/bin/veille …` des documents devient `docker exec veille-emploi-app-1 veille …` sur le serveur, ou une commande du poste ; `docs/exploitation.md` écrit la copie du kit vers le dossier des données de la prod, `DEMARRAGE.md` § 6 et `CANDIDATURE.md` y renvoient, et le dépôt de données la traduit — la recherche élargie de la tâche 4, étape 4, reprise par la revue finale (tâche 6) et sur le clone des données (tâche 7)
- Le ménage du serveur (cadrage 8, réponses 1 et 3) — le serveur : ses fichiers d'unités `veille-*` hors du modèle, le clone du tailnet et ses fichiers locaux, le clone des données du tailnet, les dossiers de l'instantané de la bascule ; la déclaration de `serveur` (`services/veille-console.env`), que son relevé de 05:30 compare au disque, son `CLAUDE.md`, et son registre des secrets si la porte de son LE-013 est posée — l'inventaire d'après (tâche 5, étape 4) : `list-unit-files` ne liste plus que des `veille-emploi-*`, et aucun des dossiers retirés n'existe ; la PR de `serveur`, verte avant les suppressions et fusionnée le soir même, une fois les unités parties : le contrôle `serveur-inventaire` vert le lendemain matin (tâche 5, étape 6)
- Le dépôt de données ne décrit plus la console du tailnet comme vivante (cadrage 10, réponse 7) — le dépôt de données : `scripts/tailnet/`, `README.md:13`, `CLAUDE.md`, `docs/` et les commentaires de `config/`, sans étiquette de données ; la table des rôles de son `docs/exploitation.md`, qui reçoit les deux noms neufs — la PR du second mandat, relue par un relecteur neuf, et la recherche élargie de la tâche 7 sur son clone

## Revues

- la revue de la tâche 1, par un relecteur neuf, avant la tâche 2 : Tâche 1
- la revue de la tâche 2, par un relecteur neuf, avant la tâche 3 : Tâche 2
- la revue de la tâche 3, par un relecteur neuf, avec le journal du job `image` et de ses deux mutants, avant la tâche 4 : Tâche 3
- la revue de la tâche 4, par un relecteur neuf, qui cherche les mots retirés dans tout le dépôt, avant la PR prête : Tâche 4
- la lecture de l'inventaire du serveur par la session, avant toute suppression : Tâche 5
- la revue finale, sur tout le diff du lot, par un relecteur neuf sur le modèle le plus capable, avec la recherche élargie dans tout le dépôt : Tâche 6
- la relecture des corrections de la revue finale, par un relecteur neuf : Tâche 6
- la relecture de la PR du dépôt de données, par un relecteur neuf, avant sa fusion : Tâche 7

## Le cadrage : les décisions d'Edouard du 18/11/2026

Douze questions, « Ok pour les défauts ».

1. Le prochain lot est la fin du mode systemd.
2. Un seul lot couvre le code, le dépôt de données et le ménage du serveur.
3. Sans `VEILLE_EMPLOI_ENV`, la console devient un mode « local » sans systemd. Il sert au poste, aux tests et au test de restauration du modèle, qui lance l'image sans variable et attend une santé `ok`. La fréquence de collecte s'y lit et s'y écrit en base, comme en conteneur. Les clés des notifications naissent au démarrage. Le planificateur ne collecte pas et ne lance pas la vérification.
4. Hors conteneur, « Collecter maintenant » refuse comme au staging (`collecte_coupee`, « la collecte est coupée »). `veille collecter` reste disponible en ligne de commande.
5. `veille init` est retirée : les clés naissent au démarrage dans tous les modes.
6. `config/.env` n'est plus lu d'office. Sur le poste, un fichier de secrets se désigne par `VEILLE_ENV`, qui reste.
7. L'affinement de la lettre reste hors de l'image, donc indisponible en prod. Le lot retire seulement ce que son code dit du service systemd : le `PATH` et `config/.env`.
8. Le serveur : d'abord un inventaire en lecture (les unités et les minuteurs réellement présents, et le clone que lit la sonde) ; ensuite, des suppressions sans archive : le clone du tailnet (avec sa base, son `config/.env` aux secrets en clair et son `config/vapid.json`), le clone des données qu'il lisait si la sonde ne s'en sert pas, les fichiers d'unités `veille-*` (désactivées les 11 et 12/11) et les dossiers de l'instantané de la bascule. Ce sont des gestes 👤 écrits dans le plan, faits avant la clôture.
9. Pas de rotation des secrets qui étaient en clair.
10. Le dépôt de données : une session ouverte dans son clone fait d'abord la PR du mandat du lot 3 (`veille-emploi-donnees#54`, fusionnée le 18/11/2026), puis celle de ce lot, sur un second mandat que la session principale écrit d'après ce plan. Pas d'étiquette de données.
11. Pas de nouvel ADR. Le § 1 de l'ADR-0002 reçoit une ligne datée qui renvoie au lot.
12. Le cycle : issue, plan et revue du plan, exécution par sous-agents, revue finale, staging vérifié au téléphone, clôture, puis 👤 `v0.5.0`.

Ce qui en découle sans avoir été demandé : les tests propres à systemd partent ; les documents et la ligne « Prochain » de `CLAUDE.md` sont réécrits ; `veille oublier-adresse` reste ; les unités de la sonde du modèle (`veille-emploi-sonde-*`) ne sont pas touchées.

## Les décisions du plan

Ce que la spec ne tranchait pas. Edouard les a acceptées le 18/11/2026, après la revue du plan (réponses 1 à 10, « ok pour les défauts »).

1. **`/sante` dit toujours `local`** sans `VEILLE_EMPLOI_ENV` (`app.py:1367`, inchangé) : le test de restauration ne lit que `statut`, et `local` nomme le mode (réponse 10).
2. **Réglages en mode local se conduit comme au staging** (réponse 10) : la fréquence en base, `actif` faux (seule la prod collecte). Le JSON de la fréquence garde `cle`, `prochain_passage`, `actif` et `choix`, chaque choix gardant `cle`, `libelle` et `detail` ; il perd `oncalendar`, `personnalise`, `mode`, `etat` et `raison`, et `FREQUENCES` perd `oncalendar`. `app.js` perd les blocs « Fréquence indisponible » et « Réglage personnalisé ». `api_changer_frequence` ne rattrape plus que `ValueError`.
3. **Le chemin par défaut des clés devient `donnees/vapid.json`** du clone (réponse 5) : `config.RACINE / "donnees"`, où sont déjà la base et les dossiers par défaut (`config.py:249` et `:254`), au lieu de `config/vapid.json`. Les clés naissent désormais au démarrage d'une console du poste : sous `config/`, elles y créeraient le dossier que le dépôt de code réserve à l'instance (M-0006, § 3). L'image pose `VEILLE_VAPID=/donnees/vapid.json` et ne change pas ; `tests/test_deploiement.py` garde `donnees/vapid.json` hors de l'image.
4. **L'exemple servi par oubli reste en mode local** (réponse 10 ; `_sert_l_exemple_par_oubli`, inchangé, sa docstring réécrite) : un poste qui sert l'exemple voit le bandeau et ne travaille pas une offre au nom de Camille Exemple ; le test de restauration ne lit que la santé ; les tests du navigateur, qui en dépendent, ne changent pas. L'identifiant `_refus_sans_configuration_hors_conteneur` garde son nom (treize emplois, tous dans `src/veille/app.py`).
5. **« Collecter maintenant »** : `config.environnement() != "prod"` rend 409 `collecte_coupee` ; le refus `configuration_non_designee` reste après lui, pour la prod, en défense : la prod refuse déjà de démarrer sans configuration (`config.py:230-235`).
6. **`config/.env`** (réponse 8) : `_charger_env` ne lit que le fichier que désigne `VEILLE_ENV`. Un `VEILLE_ENV` absent, vide, ou qui désigne un fichier absent ou un dossier, est ignoré sans un mot et sans faire tomber l'import : la suite en dépend (`tests/conftest.py:25`), et rien ne s'écrit sur une mauvaise base. `empreintes.dossier_kit` perd son repli et lit encore `VEILLE_ENV`, de la même façon. `VARIABLES_CONNUES` ne change pas.
7. **Pas d'extension de mutmut** (réponse 10) : les modules touchés perdent du code, et aucune logique de domaine neuve n'entre ; chaque test qui garde une valeur est éprouvé par un mutant à la main, nommé dans sa tâche.
8. **Un test garde la source** (réponse 10 ; `tests/test_mode_local.py`) : aucun fichier `.py`, `.js`, `.html` ou `.css` de `src/veille/`, ni aucun fichier de `exemple/`, ne nomme plus systemd, `systemctl`, `EnvironmentFile`, `config/.env`, `config/vapid.json`, `veille init`, « sans conteneur », le tailnet, `tailscale` ni les unités `veille-web.service`, `veille-collecte.timer`, `veille-collecte.service`, `veille-verification.timer` et `veille-verification.service`. Chaque motif a son cas positif. La mesure datée de `affinement.py:91` se réécrit sans nommer le proxy (« le proxy d'alors était nu »).
9. **Une étape de CI garde l'image lancée sans aucune variable** (réponse 10) : le job `image` lance `veille-emploi:ci` sans `-e`, avec les options du test de restauration, et exige `statut` `ok`, `environnement` `local` et `/donnees/vapid.json` écrit. Elle garde le critère 6 (l'image sans variable rend une santé `ok`) et le démarrage du mode local dans l'image ; aucune image ne se publie sans elle. Elle n'éprouve pas la restauration : le dimanche, la console trouve la paire dans la copie de la sauvegarde. L'écriture des clés en uid 1000 sur une racine en lecture seule est déjà prouvée par le conteneur `ci`. Son mutant M2 tient lieu du mutant de code (`if mode is not None:` rétabli dans l'image) : même symptôme, aucune paire dans `/donnees`.
10. **Les gestes du serveur se font un soir** (réponse 3), en parallèle des tâches 1 à 4, dont ils ne dépendent pas ; ils précèdent la tâche 7 et la clôture. Ils commencent par l'inventaire élargi. Ce plan, public, ne porte que des noms entre chevrons ; la session écrit les commandes traduites par la table des rôles du dépôt de données dans une note privée de `Documents\00-boite-de-reception\`, jamais dans un dépôt, et Edouard les lance de là.
11. **Le clone des données du tailnet est supprimé** si l'inventaire montre deux choses : les unités de la sonde lisent les clones par défaut (`deploiement/lib.sh:166-168`) ; la recherche de références de `serveur` (`serveur:docs/fiches/README.md:69`), lancée sur les deux clones du tailnet et sur `maj-jeton-claude`, trouve son témoin (les unités du tailnet) et rien hors des unités à retirer. Sinon, il reste, et la session le dit à Edouard. Des copies de la base du tailnet (des unités `veille-sauvegarde.*` et `~/sauvegardes`, que documentait l'ancien `docs/DONNEES.md:94-116`) : leurs fichiers d'unités partent avec les autres `veille-*` ; les copies elles-mêmes, la session les montre à Edouard, qui tranche avant toute suppression.
12. **La PR de `serveur` se fait dans ce lot** (réponse 1), d'un troisième mandat de la session principale, par une session ouverte dans le clone de `serveur` (mode `session`). Elle retire `services/veille-console.env`, met à jour le `CLAUDE.md` de `serveur` (`serveur:CLAUDE.md:94-97`) et, en simple ménage, les trois lignes de `SECRETS_SOUS_HOME` qui nomment le clone du tailnet (le relevé ne signale qu'un fichier présent, `serveur:inventaire/releve.py:1100-1107`). Son texte dit « Partie de EdouardZemb/veille-emploi#34 » et porte la section des écarts. Elle est ouverte et verte **avant** les suppressions, puis fusionnée le soir même, juste après la vérification d'après et avant le relevé de 05:30 : retirée plus tôt, la déclaration donnerait `non-declare` ; plus tard, les cinq unités sortiraient en `declare-absent`, et `serveur-inventaire` échouerait. Sa fusion suit la disparition des unités déclarées, quoi qu'il advienne des clones, et son texte s'aligne d'abord sur la note du ménage ; si aucune unité n'est partie, elle attend un autre soir. Si elle ne peut l'être avant 05:30, la nuit rouge est attendue : la session l'annonce à Edouard, et la PR se fusionne au plus tôt. Le registre des secrets de la machine reste à `serveur`, au titre de son LE-013, et sort de ce plan (réponse 2) : le troisième mandat le rappelle, et demande à `serveur` si la porte de ce LE-013 est posée (une alerte sur chaque ligne `ABSENT_DU_DISQUE`, `serveur:docs/registre.md:28`). Si elle l'est, le retrait des entrées du registre qui nomment le clone du tailnet devient un préalable de `serveur`, le même soir, avant 05:30 ; s'il ne peut se faire, la nuit rouge est annoncée, comme pour la PR. Si elle ne l'est pas, ces lignes ne rougissent rien (`serveur:inventaire/alertes.py:9-19`).
13. **`scripts/tailnet/maj-jeton-claude.sh` part avec le dossier** (réponse 4), bien qu'il raccorde aussi d'autres services du serveur au jeton Claude : le critère veut le dossier entier parti. Le fichier du jeton, sur le serveur, n'est pas touché ; son renouvellement relève de `serveur`. L'inventaire vérifie que rien n'appelle la copie du script que porte le clone des données du tailnet.
14. **Au dépôt de données, `docs/LIMITES.md`** perd son § 3 (le port de la console) et garde son § 4 (qui est sur le tailnet) : le tailnet sert encore l'accès au serveur (réponse 10).
15. **Deux noms neufs** : `<le clone des données du tailnet>` et `<la copie d'avant la scission>`, que la table des rôles du dépôt de données reçoit par le second mandat, à la tâche 7. D'ici là, pour la note privée de la tâche 5, la session lit le premier à la ligne 24 de cette table (`veille-emploi-donnees:docs/exploitation.md:24`), et le second dans la phrase de `serveur:CLAUDE.md:97-98`. `<le serveur>` et `<le clone du tailnet>` existent ; les dossiers de l'instantané gardent leur nom, `~/bascule-veille-emploi` puis `~/bascule-veille-emploi-<n>`, déjà écrit dans ce dépôt (`docs/exploitation.md:877`).
16. **La bascule devient un résumé daté** (réponse 9) : la section « La bascule depuis une console sans conteneur » de `docs/exploitation.md` décrit un passage qui n'est plus possible ; elle devient un paragraphe daté, qui ne dit que la bascule du 08/11/2026 et le retrait de la console du 11/11/2026, et renvoie au geste entier par `git show 6600f91:docs/exploitation.md`. La phrase du ménage du serveur s'y ajoute à la clôture, avec sa date et son résultat réel (tâche 8). Le geste de `veille oublier-adresse` (son étape 10) passe dans « Restaurer », dont il relève (une base servie à une autre adresse). Le dépôt de données fait de même de ses gestes morts, par `git show aaf5d76:docs/exploitation.md`.
17. **Aucune suite ne tourne plus sur le serveur** : le clone du tailnet en portait la seule. La suite entière, avec `SUITE_COMPLETE=1`, est celle du job `verifier`.
18. **La copie du kit en prod s'écrit en geste 👤** dans `docs/exploitation.md`, dans la tâche 4 (réponse 6) : `scp` depuis le poste vers le dossier des données de la prod (`docs/exploitation.md:36`, son sous-dossier `kit/`), puis `docker exec veille-emploi-app-1 veille kit`. `DEMARRAGE.md` § 6 et `CANDIDATURE.md` y renvoient ; le dépôt de données le traduit.
19. **Les commentaires de `config/` du dépôt de données** se corrigent dans sa PR, sans étiquette de données (réponse 7) : la PR dit qu'elle ne change que des commentaires, sans effet sur la note. Sa section « Écarts à la spec » reste « Aucun. » : la promesse que l'issue en tire, aucune étiquette de données, tient.

## Les écarts déclarés

Aucun : la section « Écarts à la spec » de chaque PR du lot porte « Aucun. » (réponse 10).

## Hors périmètre

- Ceux de l'issue : Node et la CLI Claude dans l'image ; les unités `veille-emploi-sonde-*` ; la rotation des secrets qui étaient en clair ; `veille oublier-adresse`, qui reste ; une étiquette de données.
- Les fichiers gérés par le modèle, dont `deploiement/tester-restauration.sh`, `deploiement/lib.sh`, `deploiement/systemd/`, `tests/deploiement/` et `.github/actions/modele-*` : les unités `veille-emploi-*` qu'ils nomment sont celles du modèle, qui restent.
- Le registre des secrets de la machine : il relève de `serveur`, au titre de son LE-013 (réponse 2) ; le troisième mandat le rappelle, et en fait un préalable de `serveur`, le soir du ménage, si la porte du LE-013 est posée (décision 12).
- Le fichier du jeton Claude des autres services du serveur, et les copies d'unités qu'a laissées `maj-jeton-claude.sh` : ils relèvent de `serveur`.
- Les autres services du serveur, étrangers au projet, et les dossiers de la prod et du staging que la recherche des restes listera (`~/.local/share/veille-emploi`, `~/.local/state/veille-emploi`, leurs clones) : jamais touchés.
- Renommer `_refus_sans_configuration_hors_conteneur` (décision 4).
- Les relevés datés et l'historique : `docs/registre.md`, `docs/METHODE.md`, l'ADR-0001, l'ADR-0003 et le corps de l'ADR-0002.

## Contraintes globales

- Aucune migration, aucune variable `VEILLE_*` neuve ni retirée (invariant 6 ; invariant commun 4) : l'image `0.4.0` lit la base que ce lot laisse, la clé `frequence` de la table `reglages` comprise ; le retour arrière reste le déploiement de l'étiquette d'avant.
- Le dépôt est public (M-0001) : aucun chemin réel du serveur, aucun nom de machine, aucune adresse, ni dans le code, ni dans les tests, ni dans les textes des PR ; les noms entre chevrons se traduisent par la table du dépôt de données.
- **Les fins de ligne ne se normalisent pas (invariant 7).** Restent en CRLF : `src/veille/affinement.py`, `src/veille/cli.py`, `src/veille/enrichissement.py`, `src/veille/collectors/courriel.py`, `src/veille/collectors/france_travail.py`, `src/veille/static/app.js`, `src/veille/templates/index.html`, `tests/test_dossier.py`, `exemple/.env.exemple`, `README.md`, `docs/DEMARRAGE.md`, `docs/CANDIDATURE.md`, `docs/CRITERES.md`. Restent en LF les autres fichiers touchés, dont `docs/ALERTES.md`. `tests/test_affinement.py` mêle les deux (ses 568 premières lignes en CRLF, la suite en LF) : on le modifie par Python en binaire, jamais par l'outil Edit, qui réécrit les fins de ligne d'un fichier mêlé ; `tests/test_javascript.py`, mêlé aussi, ne se modifie pas. Un fichier neuf est en LF. Jamais `sed -i` sur un fichier CRLF. Avant chaque commit, pour chaque fichier touché, `python -I -c "import sys;b=open(sys.argv[1],'rb').read();print(b.count(b'\r\n'), b.count(b'\n'))" <fichier>` rend deux nombres égaux (CRLF) ou un zéro en premier (LF), et pour `tests/test_affinement.py` le même écart qu'avant entre ses deux nombres (153 lignes en LF) : sa partie LF n'est pas touchée.
- Le test s'écrit d'abord, et il échoue ; un test qui garde une valeur est éprouvé par un mutant à la main. La suite du poste : `.venv\Scripts\python -m pytest -q -p no:cacheprovider` ; celle du navigateur : `.venv\Scripts\python -m pytest -q -p no:cacheprovider tests_navigateur`. Une suite lourde à la fois, au premier plan, et son code de sortie lu avant tout envoi.
- Les fichiers gérés par le modèle ne se modifient pas : `docs/modele/`, `scripts/modele/`, `.githooks/`, `.github/modele/`, `.github/workflows/modele-*.yml`, `.github/actions/modele-*`, `tests/deploiement/`, et les fichiers de `deploiement/` que rend le modèle. Sont au projet : `Dockerfile`, `.github/workflows/ci.yml`, `deploiement/projet.env`, `deploiement/compose.projet.yml`, `deploiement/secrets/*.cles`.
- Les gestes du serveur : un soir, jamais entre 2 h et 4 h 15, ni le dimanche matin (sauvegarde à 03:30, test de restauration le dimanche à 05:30) ; un `.env` ne s'affiche jamais ; chaque commande s'écrit `! /c/Windows/System32/OpenSSH/ssh <le serveur> "<commande>"`, une par bloc et par message, sans `$` ; chaque `systemctl` qui liste ou montre porte `--no-pager` (constat LE-12) ; chaque suppression nomme exactement ce qu'elle retire, jamais par une jointure large ; aucun `sudo`.
- Les commits : Conventional Commits, en français, en-tête de 100 caractères au plus, `git add` par chemins, message par fichier (`git commit -F`), les deux lignes d'attribution en pied. Jamais `--no-verify`. Qui fusionne : les PR de ce dépôt, la session de ce dépôt (mode `session`, `gh pr merge <n>` depuis le clone, sans `cd`) ; celle du dépôt de données, une session ouverte dans son clone ; celle de `serveur`, une session ouverte dans son clone.

## Points d'attention de la revue

1. **Le test de restauration du dimanche** passe désormais par le mode local : une erreur au démarrage sans variable l'enverrait en `/fail`. La paire, elle, vient de la copie de la sauvegarde (tâche 3, l'étape du job `image` ; tâche 8, le premier dimanche).
2. **Une suppression qui viserait une unité du modèle** : les fichiers `veille-emploi-*` sont dans le même dossier que ceux à retirer ; chaque nom s'écrit en entier, d'après l'inventaire, et `list-unit-files` d'après ne liste plus que les `veille-emploi-*` (tâche 5).
3. **Le clone des données de la sonde** ne se supprime jamais : seul `<le clone des données du tailnet>` part, et l'inventaire élargi montre d'abord ce que lisent les unités de la sonde, et que rien ne nomme les deux clones du tailnet ni `maj-jeton-claude` hors des unités à retirer (tâche 5, décision 11).
4. **Le relevé de `serveur` à 05:30** : la PR de `serveur` se fusionne le soir même, entre la disparition des unités et le relevé ; sinon, `serveur-inventaire` échoue sur cinq unités déclarées absentes. Si la porte du LE-013 de `serveur` est posée, le registre des secrets doit suivre le même soir (tâche 5, décision 12).
5. **Une page de l'image 0.4.0 restée ouverte** lit un JSON de fréquence sans `etat` ni `personnalise` : ses avertissements ne s'affichent pas, et rien ne casse (tâche 6, étape 5).
6. **Un retour arrière à `v0.4.0` après `v0.5.0`** : même base, même fréquence en base en conteneur, aucune variable retirée ; l'image 0.4.0 démarre comme avant.
7. **Un poste qui gardait `config/vapid.json`** : la paire renaît dans `donnees/`, et un abonnement push fait sur une console du poste est à refaire ; aucun téléphone réel n'y est abonné.

---

### Tâche 1 : le mode local, côté serveur

**Fichiers :**
- Modifier : `src/veille/app.py`, `src/veille/reglages.py`, `src/veille/notifications.py` (la ligne 31 seulement), `src/veille/static/app.js` (CRLF), `tests/test_factice.py`, `tests/test_notifications.py`, `tests/test_reglages.py`, `tests/test_planificateur.py`, `tests/test_instance.py`, `tests/test_deploiement.py`

**Interfaces :**
- Produit : `notifications.CHEMIN_VAPID = Path(os.environ.get("VEILLE_VAPID", RACINE / "donnees" / "vapid.json"))` (décision 3) ; dans `cycle_de_vie`, la paire naît si le fichier manque, dans tous les modes, et le jeu factice ne se charge qu'en `staging`.
- Produit : `reglages.lire_frequence() -> dict` aux seules clés `cle`, `prochain_passage`, `actif` (`environnement() == "prod"`) et `choix` ; `reglages.ecrire_frequence(cle)` écrit en base dans tous les modes, et lève `ValueError` pour une clé inconnue. Partent : `UNITE_TIMER`, `CHEMIN_TIMER`, `_systemctl`, `_lire_frequence_conteneur` (fondue dans `lire_frequence`), `_lire_frequence_systemd`, la clé `oncalendar` de `FREQUENCES`, et les imports devenus inutiles (décision 2).
- Produit : `POST /api/reglages/collecter` rend 409 `collecte_coupee` dès que `config.environnement() != "prod"`, puis, en prod, `_refus_sans_configuration()`, puis le planificateur ; plus de `subprocess` (décision 5). `api_changer_frequence` ne rattrape que `ValueError`.
- Les docstrings et les commentaires de ce que la tâche change sont réécrits : `cycle_de_vie` (`app.py:58`), `api_collecter_maintenant` (`app.py:1224-1228`), la docstring de `reglages.py` (`:1-10`) et le commentaire de `FREQUENCES` (`:31-32`).

- [ ] **Étape 1 : écrire les tests qui échouent.**
  - `tests/test_factice.py` : `test_les_cles_push_naissent_au_demarrage_dans_tous_les_modes`, paramétré sur `["prod", "staging", None]` (`None` : `monkeypatch.delenv("VEILLE_EMPLOI_ENV", raising=False)`), remplace `test_les_cles_push_naissent_au_demarrage_en_conteneur` et `test_sans_mode_les_cles_ne_naissent_pas` : la paire absente avant `_demarrer()`, présente après, et intacte après un second `_demarrer()`. Éprouvé par le mutant qui rétablit `if mode is not None:`.
  - `tests/test_notifications.py` : `test_les_cles_vont_par_defaut_dans_donnees` : un sous-processus `sys.executable -c "from veille import config, notifications; print(notifications.CHEMIN_VAPID == config.RACINE / 'donnees' / 'vapid.json')"`, son environnement sans `VEILLE_VAPID`, imprime `True`. Éprouvé par le mutant qui remet `"config"`.
  - `tests/test_deploiement.py:335` : `donnees/vapid.json` s'ajoute à la liste `prives` de `test_l_image_ignore_les_fichiers_prives`. Éprouvé par le mutant qui ajoute `!donnees/vapid.json` au `.dockerignore`.
  - `tests/test_reglages.py` :
    - `test_la_frequence_vit_en_base_dans_tous_les_modes`, paramétré sur `[None, "staging", "prod"]`, remplace `test_frequence_en_base_en_conteneur` : `lire_frequence()["cle"] == "trois_fois"` ; après `ecrire_frequence("une_fois")`, `lire_frequence()["cle"] == "une_fois"` et `db.lire_reglage("frequence") == "une_fois"` ; `actif` vaut `mode == "prod"`. Éprouvé par le mutant qui met `actif` à `environnement() != "prod"`.
    - `test_la_frequence_rend_ses_seules_cles` : `set(lire_frequence()) == {"cle", "prochain_passage", "actif", "choix"}`, et chaque choix a exactement `{"cle", "libelle", "detail"}` ; puis, sans `VEILLE_EMPLOI_ENV`, `GET /api/reglages` par le client connecté rend 200, et `set(r.json()["frequence"])` est le même ensemble (il remplace l'assertion de `tests/test_reglages.py:172`). Éprouvé par le mutant qui garde `oncalendar`.
    - `test_reglages_ne_montre_plus_la_frequence_de_l_unite` : le texte de `src/veille/static/app.js` ne contient ni `oncalendar`, ni « Fréquence indisponible », ni « Réglage personnalisé ». Éprouvé par le mutant qui remet le bloc « Fréquence indisponible ».
    - `test_les_frequences_proposees_sont_valides` perd son assertion sur `oncalendar` et vérifie que les `heures` de chaque fréquence sont non vides et croissantes, entre 0 et 23 h. Éprouvé par le mutant qui donne à `deux_fois` les heures `[(18, 15), (7, 15)]`.
    - `test_le_libelle_de_chaque_frequence_dit_ses_heures` remplace `test_chaque_frequence_a_des_heures_coherentes` : pour chaque libellé qui énumère ses heures (`(\d{1,2})h(\d{2})`), l'ensemble lu égale `heures` ; celui de `toutes_les_deux_heures` (« 7h à 21h ») dit la première et la dernière heure de `heures`. Éprouvé par le mutant qui change `(18, 15)` en `(19, 15)` dans `deux_fois`.
  - `tests/test_planificateur.py` : `test_collecter_maintenant_en_conteneur` devient `test_collecter_maintenant_selon_le_mode` : `None`, `staging` et `ci` rendent 409 `{"erreur": "collecte_coupee"}` sans rien lancer, puis la prod comme avant ; sans la fixture `systemctl`. Éprouvé par le mutant qui rétablit `environnement is not None and`.
  - `tests/test_instance.py` : `test_le_bouton_collecter_rend_une_erreur_lisible`, sans `VEILLE_EMPLOI_ENV`, attend désormais `collecte_coupee` ; `test_en_prod_le_bouton_collecter_refuse_sans_configuration` : `VEILLE_EMPLOI_ENV=prod`, `config.exiger_configuration` remplacé par une fonction qui ne fait rien (la console démarre), rien de désigné, le bouton rend 409 `configuration_non_designee` et `lances == []`. Éprouvé par le mutant qui retire l'appel de `_refus_sans_configuration()`.
- [ ] **Étape 2 : les lancer, sur le poste seulement.** `.venv\Scripts\python -m pytest -q -p no:cacheprovider tests/test_factice.py tests/test_notifications.py tests/test_reglages.py tests/test_planificateur.py tests/test_instance.py tests/test_deploiement.py`. Attendu : la paire absente en mode local ; `config/vapid.json` ; la fréquence `indisponible` et un `RuntimeError` à son écriture sans unité ; `configuration_non_designee` au lieu de `collecte_coupee` ; et, sans la fixture `systemctl`, l'ancien bouton sans `VEILLE_EMPLOI_ENV` lève le `FileNotFoundError` de `systemctl`, que `TestClient` relaie. Sur un Linux à systemd utilisateur, il lancerait vraiment l'unité : cette étape ne s'y lance pas.
- [ ] **Étape 3 : écrire le code**, d'après les interfaces. Retirer en même temps les tests et fixtures de systemd : `_systemd_utilisateur`, `test_lire_la_frequence_ne_casse_pas_sans_unite` et `test_frequence_indisponible_sans_systemctl` (`tests/test_reglages.py`) ; le remplacement de `reglages._systemctl` dans `test_pas_de_collecte_hors_prod`, la fixture `systemctl` et `test_collecter_maintenant_sous_systemd` (`tests/test_planificateur.py`) ; puis les imports devenus inutiles. Dans `app.js`, les lignes 380 à 384 partent.
- [ ] **Étape 4 : relancer** ces fichiers, puis la suite du poste, puis celle du navigateur : les clés naissent désormais à chaque démarrage d'une console de test, et l'état du push des pages passe d'« indisponible » à « inactives ». Attendu : tous verts, sauf les sauts attendus sous Windows. Un test qui supposait la paire absente se corrige dans cette tâche, et la revue le lit.
- [ ] **Étape 5 : commit.** `git add` des fichiers de la tâche, par chemins, puis `git commit -F <fichier>` : `feat(console): le mode local, sans systemd : clés au démarrage, fréquence en base, collecte coupée`.
- [ ] **Étape 6 : la PR en brouillon.** `git push -u origin feat/fin-systemd`, puis `gh pr create --draft --base principal --body-file <fichier>` : un titre de 93 caractères au plus, « Partie de #34 », la section « Écarts à la spec » à « Aucun. ». Le corps s'éprouve d'abord par `scripts/modele/texte_pr.py` en local (`docs/modele/methode.md`, « Éprouver le texte avant d'ouvrir la PR »), et se finit avant la fin de la CI.
- [ ] **Étape 7 : la revue de la tâche**, par un relecteur neuf, avec ce plan et l'issue. Ses corrections sont relues avant la tâche 2.

### Tâche 2 : la ligne de commande, les secrets du poste et les textes de la source

**Fichiers :**
- Créer : `tests/test_mode_local.py`
- Modifier : `src/veille/cli.py` (CRLF), `src/veille/empreintes.py`, `src/veille/affinement.py` (CRLF), `src/veille/notifications.py`, `src/veille/documents.py`, `src/veille/collectors/courriel.py` (CRLF), `src/veille/collectors/france_travail.py` (CRLF), `src/veille/config.py`, `src/veille/app.py`, `src/veille/planificateur.py`, `src/veille/collecte.py`, `src/veille/auth.py`, `src/veille/debit.py`, `src/veille/enrichissement.py` (CRLF), `src/veille/static/app.js` (CRLF), `src/veille/templates/index.html` (CRLF), `exemple/.env.exemple` (CRLF), `tests/test_cli_env.py`, `tests/test_kit_fige.py`, `tests/test_cli_renvois.py`, `tests/test_push_plomberie.py`, `tests/test_affinement.py` (mêlé), `tests/conftest.py`, `tests/test_isolation.py`, `tests/test_dossier.py` (CRLF), `tests/test_deploiement.py`, `tests/test_collecte.py`, `tests/test_instance.py`

**Interfaces :**
- Produit : `cli._charger_env()` lit `os.environ.get("VEILLE_ENV", "").strip()` ; vide ou absente, il ne fait rien ; sinon il ne lit le fichier que si `Path(...).is_file()` (décision 6, réponse 8). `empreintes.dossier_kit()` lit `VEILLE_KIT`, puis la ligne `VEILLE_KIT=` du fichier que désigne `VEILLE_ENV`, lu comme `_charger_env` le lit (`strip`, vide ignoré, `is_file()`), et rien d'autre ; son import de `RACINE`, devenu inutile, part. `veille init`, `cmd_init` et sa ligne de la docstring partent.
- Produit : `affinement` perd `BIN_LOCAL` et l'ajout au `PATH` : le sous-processus reçoit le `PATH` de la console tel quel. Ses messages (`:236`, `:390`) disent de poser le jeton « dans l'environnement de la console, ou dans le fichier que designe VEILLE_ENV », sans accents comme leurs voisins.
- Produit, mot pour mot : l'avertissement d'un push sans clé, « push impossible : pas de cle VAPID (elle nait au demarrage de la console) » ; la ligne de `veille tester-notification`, « cles VAPID absentes : elles naissent au demarrage de la console » ; la raison `vapid` de `app.js`, « Le serveur n'a pas de clé VAPID : elle naît au démarrage de la console. » ; le bandeau de l'exemple, « Cette console sert l'exemple, pas ta configuration : pose `VEILLE_CONFIG`, puis relance la console. »
- Produit : `tests/test_mode_local.py`, avec `MOTS_RETIRES` (les expressions régulières de la décision 8 : `systemctl`, `systemd`, `EnvironmentFile`, `config/\.env`, `config/vapid\.json`, `veille\W+init\b`, `sans\W+conteneur`, `tailnet`, `tailscale`, `veille-web\.service`, `veille-collecte\.(?:timer|service)`, `veille-verification\.(?:timer|service)`, sans égard à la casse) et `trouver(texte: str) -> list[str]`.

- [ ] **Étape 1 : écrire les tests qui échouent.**
  - `tests/test_mode_local.py` :
    - `test_la_source_ne_parle_plus_du_mode_systemd` : pour chaque fichier `.py`, `.js`, `.html` ou `.css` de `src/veille/` et chaque fichier de `exemple/`, `trouver(texte) == []`, le message nommant `<fichier>:<ligne>`. Éprouvé par le mutant qui remet « systemd » dans une docstring.
    - `test_le_garde_trouve_chaque_motif`, un cas par motif : `"systemctl --user"`, `"le minuteur\n  SystemD"`, `"EnvironmentFile=-x"`, `"lu dans config/.env"`, `"config/vapid.json"`, `"// veille\n// init"`, `"# sans\n# conteneur"`, `"le Tailnet"`, `"tailscale serve"`, `"veille-web.service"`, `"veille-collecte.timer"`, `"veille-collecte.service"`, `"veille-verification.timer"` et `"veille-verification.service"` : chacun est trouvé. Éprouvé par trois mutants : un motif retiré de `MOTS_RETIRES`, `\W+` remplacé par une espace, `re.IGNORECASE` retiré.
    - `test_le_garde_laisse_ce_qui_ne_parle_pas_du_mode`, paramétré sur `"sans_conteneur"`, `"veille_init"`, `"la veille initialise la base"` et `'name="veille-collecte"'` : aucun n'est trouvé. Éprouvé par trois mutants : `\W+` remplacé par `[\W_]+`, `init\b` par `init`, le suffixe des unités rendu facultatif.
  - `tests/test_cli_env.py` :
    - `test_sans_veille_env_le_config_env_du_clone_n_est_pas_lu` : `src/veille` copié sous `tmp_path/src/veille`, `tmp_path/config/.env` porte `VEILLE_KIT=<tmp_path/kit-du-clone>` ; un sous-processus, sans `VEILLE_ENV` ni `VEILLE_KIT`, insère `tmp_path/src` en tête de `sys.path`, importe `veille.cli`, imprime `cli.__file__` puis `os.environ.get("VEILLE_KIT")` : le premier est sous `tmp_path`, le second `None`. Son environnement garde les autres variables de la suite (`tests/conftest.py`), dont la configuration désignée. Éprouvé par le mutant qui rétablit le repli.
    - `test_un_veille_env_vide_ne_fait_pas_tomber_l_import` : un sous-processus avec `VEILLE_ENV=""` importe `veille.cli` et rend 0. Éprouvé par le mutant qui retire le test du vide.
    - `test_veille_init_n_existe_plus` : `pytest.raises(SystemExit)` sur `cli.principal(["init"])`, de code 2. Éprouvé par le mutant qui rétablit le parseur.
  - `tests/test_kit_fige.py` : `test_le_kit_ne_se_lit_plus_dans_le_config_env_du_clone` : `monkeypatch.setattr(empreintes, "RACINE", tmp_path, raising=False)`, un dossier `tmp_path/kit-du-clone`, `tmp_path/config/.env` qui le désigne, `VEILLE_KIT` et `VEILLE_ENV` retirées : `dossier_kit()` rend `None` ; avec `VEILLE_ENV=""`, il rend `None` ; avec `VEILLE_ENV` sur ce fichier, il rend le dossier. Éprouvé par le mutant qui rétablit le repli, qui lit alors le `RACINE` posé, et par celui qui remplace `is_file()` par `exists()` en retirant le test du vide.
  - `tests/test_affinement.py`, par Python en binaire : les assertions `"config/.env"` des lignes 324 et 350 deviennent `"VEILLE_ENV"`, éprouvées par le mutant qui remet `config/.env` dans les deux messages ; `test_le_sous_processus_recoit_un_path_qui_trouve_claude` devient `test_le_sous_processus_recoit_le_path_de_la_console` : `vu["env"]["PATH"]` égale le `PATH` posé ; éprouvé par le mutant qui remet un préfixe.
  - `tests/test_push_plomberie.py:229` devient `assert "veille init" not in message` ; `tests/test_cli_renvois.py:47-48` attend la ligne neuve, et `"veille init" not in sortie`. Éprouvés par le mutant qui remet « veille init » dans les deux messages.
- [ ] **Étape 2 : les lancer.** Attendu : le garde nomme chaque lieu de « Mécanismes annoncés » qui porte un mot retiré, le `config/.env` du clone est lu, un `VEILLE_ENV` vide fait tomber l'import, `veille init` répond.
- [ ] **Étape 3 : écrire le code** d'après les interfaces, puis réécrire chaque texte que le garde nomme : `config.py:29` et `:137` (« ou None en mode local ») ; les docstrings de `app.py:1-10`, `app.py:77-81`, `_sert_l_exemple_par_oubli` (« en mode local, sans `VEILLE_EMPLOI_ENV` »), `planificateur.py:1-18` et `:44`, `collecte.py:1-6`, `auth.py:1-6` (la console est publique, derrière le tunnel commun), `debit.py:3-7`, `notifications.py:1-8` ; `enrichissement.py:19` (« jamais depuis le planificateur ») ; les messages de `cli.py:513` et `:640`, `notifications.py:212` et `:305`, `documents.py:119`, et les docstrings des deux collecteurs, qui renvoient au fichier que désigne `VEILLE_ENV`, ou aux secrets de l'instance en conteneur ; la mesure de `affinement.py:88-94` (décision 8) et le commentaire de `:57-59` ; le commentaire du bandeau (`index.html:31-33`). `exemple/.env.exemple` : son en-tête dit de le copier hors du clone, de le désigner par `VEILLE_ENV`, en droits 600, et qu'en prod ces valeurs vivent dans le `secrets/prod.env.enc` du dépôt de données (`docs/exploitation.md`, « Secrets ») ; sa ligne 71 dit que la console le lit par `VEILLE_ENV`.
- [ ] **Étape 4 : les textes des tests**, sans changer ce qu'ils vérifient : `tests/conftest.py:23-24` (un `VEILLE_ENV` exporté sur le poste ferait entrer ses valeurs dans la suite), la docstring de `tests/test_isolation.py:30-33`, celles de `tests/test_cli_env.py:1-9` et `:62`, `_kit_reel` de `tests/test_dossier.py:648-668` (CRLF), `tests/test_deploiement.py:363-365` (un clone peut garder des fichiers locaux ignorés), `tests/test_collecte.py:3`, `tests/test_cli_renvois.py:5-6` et le commentaire de `tests/test_instance.py:305-308`. `tests/test_deploiement.py:336` reste : l'image doit ignorer un `config/.env` qu'un vieux clone garderait.
- [ ] **Étape 5 : relancer** ces fichiers, puis la suite du poste. Attendu : tous verts ; les fins de ligne comme avant, `tests/test_affinement.py` compris.
- [ ] **Étape 6 : commit et envoi.** `git commit -F <fichier>` : `feat(cli): veille init retirée, config/.env plus lu d'office, la source sans le mode systemd`, puis `git push origin feat/fin-systemd`.
- [ ] **Étape 7 : la revue de la tâche**, par un relecteur neuf. Ses corrections sont relues avant la tâche 3.

### Tâche 3 : l'image sans aucune variable, gardée en CI

**Fichiers :**
- Modifier : `.github/workflows/ci.yml`, `tests/sauts.py`

**Interfaces :**
- Produit : dans le job `image`, après « L'image sert l'exemple, sans l'instance » et avant la publication, l'étape « L'image démarre sans aucune variable » (décision 9) ; le journal de ce conteneur dans l'étape « Journal du conteneur » ; une étape `if: always()` qui le retire.

- [ ] **Étape 1 : l'étape.** Dans `ci.yml`, avec un commentaire qui nomme `deploiement/tester-restauration.sh` et dit ce que l'étape éprouve (décision 9) :

  ```yaml
  - name: L'image démarre sans aucune variable
    shell: bash
    run: |
      docker run -d --name veille-emploi-local -p 127.0.0.1:8461:8460 \
        --user 1000:1000 --read-only --tmpfs /tmp --cap-drop ALL \
        --security-opt no-new-privileges:true --memory 384m -v /donnees veille-emploi:ci
      for _ in $(seq 1 30); do
        curl -fsS http://127.0.0.1:8461/sante >/dev/null 2>&1 && break
        sleep 2
      done
      curl -fsS http://127.0.0.1:8461/sante | jq -e '.statut == "ok" and .environnement == "local"' \
        || { echo "::error::sans variable, /sante ne rend pas statut ok en mode local"; exit 1; }
      docker exec veille-emploi-local test -s /donnees/vapid.json \
        || { echo "::error::sans variable, les clés des notifications ne naissent pas"; exit 1; }
  ```

  « Journal du conteneur » ajoute `docker logs veille-emploi-local || true` ; « Supprimer le conteneur local », `if: always()`, lance `docker rm -f -v veille-emploi-local || true`. Le commentaire de `ci.yml:49-50` ne nomme plus systemd ; la docstring de `tests/sauts.py` non plus, ni le serveur (décision 17).
- [ ] **Étape 2 : envoyer**, puis lire le job `image` de la PR : l'étape passe.
- [ ] **Étape 3 : les deux mutants**, dans cet ordre, jamais par un envoi forcé : un commit qui pose M1 (`-e VEILLE_EMPLOI_ENV=ci` au `docker run` de l'étape), puis un commit qui retire M1 et pose M2 (`-e VEILLE_VAPID=/tmp/vapid.json`), puis un commit qui retire M2. Avant chaque envoi suivant, attendre la fin du job `image` du mutant et lire sa conclusion (`gh run view <id> --json jobs`) : `failure`, jamais `cancelled`, puisqu'un envoi annule l'exécution précédente d'une PR (`ci.yml:14-16`). M1 doit échouer sur le premier `::error::`, M2 sur le second. Les deux journaux sont donnés à la revue. La tête de la PR ne porte aucun mutant.
- [ ] **Étape 4 : commit**, s'il reste à faire : `ci: l'image lancée sans aucune variable, comme le test de restauration`.
- [ ] **Étape 5 : la revue de la tâche**, par un relecteur neuf, avec les journaux du job `image` et de ses deux mutants. Ses corrections sont relues avant la tâche 4.

### Tâche 4 : les documents du code

**Fichiers :**
- Modifier : `docs/exploitation.md`, `docs/DONNEES.md`, `docs/DEMARRAGE.md` (CRLF), `docs/LIMITES.md`, `docs/CRITERES.md` (CRLF), `docs/CANDIDATURE.md` (CRLF), `docs/ALERTES.md`, `docs/ENRICHISSEMENT.md`, `docs/pistes.md`, `deploiement/secrets/prod.cles`, `CLAUDE.md`

- [ ] **Étape 1 : `docs/exploitation.md`.**
  - « Les deux modes de marche » (`:87-111`) devient « Le mode local » : sans `VEILLE_EMPLOI_ENV`, celui du poste, des tests et du test de restauration du modèle ; `/sante` dit `local` ; la fréquence en base ; les clés nées au démarrage dans `VEILLE_VAPID` (`donnees/vapid.json` du clone, `/donnees/vapid.json` dans l'image) ; le planificateur purge, sans collecter ni vérifier ; « Collecter maintenant » refuse, `veille collecter` reste ; les secrets du poste par `VEILLE_ENV`. Le paragraphe du staging reste.
  - « La configuration désignée » : `:162` dit « En mode local » ; la liste « Pour une console sans conteneur » (`:172-182`) et le renvoi au geste de la console du tailnet (`:184-185`) partent.
  - `:217` perd sa parenthèse sur la bascule.
  - « La bascule depuis une console sans conteneur » (`:675-893`) devient un paragraphe daté (décision 16) : la bascule du 08/11/2026 et le retrait de la console du 11/11/2026, rien de plus ; le geste entier, par `git show 6600f91:docs/exploitation.md`. Il définit `<le clone du tailnet>` et `<le clone des données du tailnet>`, que traduit le dépôt de données. Le ménage du serveur ne s'y écrit qu'à la clôture, une fois fait (tâche 8). Le geste de `veille oublier-adresse` passe dans « Restaurer ».
  - Le geste 👤 de copie du kit en prod (décision 18), dans « Ce qui est propre à la console » : depuis PowerShell sur le poste, `scp -r "C:\chemin\vers\ton-kit\*" <le serveur>:.local/share/veille-emploi/prod/donnees/kit/` (un chemin relatif au dossier personnel, ce que lisent les deux protocoles de `scp`), puis `ssh <le serveur> "docker exec veille-emploi-app-1 veille kit"`, qui dit ce qui partirait ; un kit changé fait dire des écarts à `veille empreintes-kit` contre l'`empreintes-kit.json` de la configuration (`docs/CRITERES.md:62`), qui se refige au dépôt de données ; une pièce n'y est copiée que prête à partir (`docs/LIMITES.md`, « Une pièce du kit n'est copiée sur le serveur que prête à partir »).
- [ ] **Étape 2 : les autres documents.** Chaque `cd <le clone>` suivi de `./.venv/bin/veille …` devient `docker exec veille-emploi-app-1 veille …` sur le serveur, ou une commande du poste, selon ce que fait la commande.
  - `docs/DONNEES.md` : la section du conteneur reste ; les sections de la console du tailnet (`:37-122`) deviennent un court « Sur le poste, en mode local » (`donnees/` du clone, les secrets par `VEILLE_ENV`, aucune sauvegarde) ; « Effacer » vise le conteneur (`docker exec veille-emploi-app-1 …` pour une offre, « Tout arrêter » de `docs/exploitation.md` pour le reste) et `donnees/` du poste ; la jointure `veille-*` (`:157`), qui prendrait les unités du modèle, part.
  - `docs/DEMARRAGE.md` : `:6-7` (les commandes se lancent dans le conteneur de la prod, par `docker exec`, ou sur le poste) ; § 0 (`:24-25`), § 1.b (`:75`, `:85-87`), § 2 (`:125`, `:159-161`, `:179-181`) nomment les secrets de l'instance (« Secrets » de `docs/exploitation.md`) ou le fichier que désigne `VEILLE_ENV` ; § 3, les certificats du tailnet (`:193-215`), part ; § 4 (`:227-293`) se connecte et gère les passkeys par `docker exec veille-emploi-app-1 veille lien` et `veille passkeys` ; `:307` ne parle plus de systemd ; § 5 (`:333-334`) ; § 6 (`:357-377`) renvoie au geste de copie du kit de `docs/exploitation.md`.
  - `docs/CANDIDATURE.md` : « Copier ton kit sur le serveur » (`:80-99`) renvoie au même geste ; `:211-213` vérifie par `docker exec veille-emploi-app-1 veille kit` ; `:496` dit le jeton dans l'environnement de la console du poste.
  - `docs/ALERTES.md:73-79` et `docs/CRITERES.md:19-23` : leurs commandes visent le conteneur ; `veille config verifier` du poste, sur un dossier de configuration.
  - `docs/LIMITES.md` : § 1 bis (`:47`, le planificateur), § 2 (`:94-101`), § 3 (`:120-132`, la console sans conteneur part), § 4 (`:136-139`, l'adresse publique seule), § 6 (`:163`, les conteneurs et les unités `veille-emploi-*` du modèle), l'affinement (`:288-317` : le jeton dans l'environnement de la console du poste ; le paragraphe du `PATH` part).
  - `docs/ENRICHISSEMENT.md:145` : le minuteur du mode retiré.
  - `docs/pistes.md:15` part : la piste est faite, et sa mise en garde sur le test de restauration a sa réponse (le mode local, la tâche 3). `docs/pistes.md:16` dit « le planificateur » au lieu du « minuteur de collecte ».
  - `deploiement/secrets/prod.cles:13`, au passé.
- [ ] **Étape 3 : `CLAUDE.md`.** « Commandes » : la suite du poste ne nomme plus systemd, et porte la phrase des six tests du kit qui se sautent partout ; une ligne dit le mode local du poste (`veille servir` sans `VEILLE_EMPLOI_ENV`, ses données dans `donnees/`, ses secrets par `VEILLE_ENV`) ; le bloc « Sur une console sans conteneur… » (`:47-52`) part, et `veille empreintes-kit` passe dans le bloc du conteneur, par `docker exec veille-emploi-app-1` ; la ligne de `veille oublier-adresse` renvoie à « Restaurer ». « Ce qui fait foi » : la fréquence vit en base, dans tous les modes. L'État : la phrase des deux modes (`:19`), et sa parenthèse sur le minuteur systemd, disent le mode local. La ligne « Prochain » et l'état du lot attendent la clôture.
- [ ] **Étape 4 : la recherche.** L'outil Grep, en mode multiligne, sur tout le dépôt hors de `docs/modele/`, `scripts/modele/`, `.githooks/` et `.github/modele/`, motif `systemctl|systemd|EnvironmentFile|tailnet|tailscale|veille\s+init|config/\.env|config/vapid|veille-web|veille-collecte|veille-verification|sans\s+conteneur|mode\s+systemd|<le clone>|\.venv/bin/veille|clone\s+de\s+la\s+console`. Puis chaque `minuteur`, relu à la main. Restent justes : les unités `veille-emploi-*` du modèle et ses fichiers (`deploiement/`, `tests/deploiement/`, `docs/exploitation.md` « Unités » et « Tout arrêter ») ; les relevés datés et l'historique (`docs/registre.md`, `docs/METHODE.md:161` et `:260`, l'ADR-0001, l'ADR-0003, le corps de l'ADR-0002, le paragraphe daté de la bascule, `deploiement/secrets/prod.cles:8`, `docs/exploitation.md:974`, `docs/exploitation.md:139`, qui dit l'ancien minuteur au passé) ; `.gitignore:3-5` et `tests/test_deploiement.py:336`, qui gardent un vieux clone ; `docs/exploitation.md:469` (« sans conteneur en service ») ; `docs/LIMITES.md:53` (« jamais un minuteur », une règle qui vaut pour le planificateur) ; `README.md:20` (`.venv/bin/veille servir`, la console du poste) ; le fil `veille-collecte` (`planificateur.py:227`) ; `tests/test_javascript.py:108`, dans un fichier mêlé qu'on ne modifie pas ; le titre `## Le mode local` et ce plan. `python -X utf8 -B scripts/modele/documentation.py` rend 0.
- [ ] **Étape 5 : commit et envoi.** `git commit -F <fichier>` : `docs: le mode local, sans systemd, la copie du kit en prod et la bascule résumée`, puis `git push origin feat/fin-systemd`.
- [ ] **Étape 6 : la revue de la tâche**, par un relecteur neuf, qui cherche les mots retirés dans tout le dépôt, avec le motif de l'étape 4, renvois convertis compris. Ses corrections sont relues avant la PR prête.

### Tâche 5 : 👤 le ménage du serveur

Un soir, en parallèle des tâches 1 à 4 (décision 10, réponse 3) ; avant la tâche 7 et la clôture. Les noms entre chevrons se lisent dans la table des rôles du `docs/exploitation.md` du dépôt de données ; les deux noms neufs n'y entrent qu'à la tâche 7 : la session lit `<le clone des données du tailnet>` à la ligne 24 de cette table, et `<la copie d'avant la scission>` dans `serveur:CLAUDE.md:97-98` (décision 15). Dans un `grep`, un chemin s'écrit sans son `~/` de tête, une unité pouvant écrire `%h/…`.

- [ ] **Étape 1 : préparer.**
  - La session écrit les commandes des étapes 2 et 4, traduites, dans une note privée de `Documents\00-boite-de-reception\`.
  - La session principale écrit le troisième mandat (décision 12) : retirer `services/veille-console.env` ; mettre à jour `serveur:CLAUDE.md:94-97` ; retirer, en ménage, les trois lignes de `SECRETS_SOUS_HOME` qui nomment le clone du tailnet ; un texte de PR qui dit « Partie de EdouardZemb/veille-emploi#34 » et porte la section des écarts ; le rappel du registre des secrets, qui reste à `serveur` au titre de son LE-013, et la question de sa porte : posée, le retrait des entrées du registre qui nomment le clone du tailnet devient un préalable de `serveur`, le soir même, avant 05:30. Une session ouverte dans le clone de `serveur` ouvre la PR et attend qu'elle soit verte, **sans la fusionner**.
  - 👤 Un soir, hors du dimanche : la dernière sauvegarde de la prod et le dernier test de restauration sont verts dans Healthchecks.
- [ ] **Étape 2 : 👤 l'inventaire élargi, en lecture**, une commande par message. Les unités et les minuteurs :

  ```
  ! /c/Windows/System32/OpenSSH/ssh <le serveur> "systemctl --user list-unit-files 'veille*' --no-pager"
  ```
  ```
  ! /c/Windows/System32/OpenSSH/ssh <le serveur> "systemctl --user list-timers --all --no-pager"
  ```
  ```
  ! /c/Windows/System32/OpenSSH/ssh <le serveur> "systemctl --user show --no-pager -p Id -p LoadState -p ActiveState -p UnitFileState -p FragmentPath veille-web.service veille-collecte.timer veille-collecte.service veille-verification.timer veille-verification.service veille-sauvegarde.service veille-sauvegarde.timer"
  ```
  ```
  ! /c/Windows/System32/OpenSSH/ssh <le serveur> "ls -la ~/.config/systemd/user ~/.config/systemd/user/*.wants"
  ```
  ```
  ! /c/Windows/System32/OpenSSH/ssh <le serveur> "systemctl --user show --no-pager -p ExecStart -p Environment veille-emploi-sonde-prod.service veille-emploi-sonde-staging.service"
  ```

  La recherche de références de `serveur` (`serveur:docs/fiches/README.md:69`), recopiée sans `$`, sur les deux clones du tailnet et sur `maj-jeton-claude` :

  ```
  ! /c/Windows/System32/OpenSSH/ssh <le serveur> "grep -rIlF -e <le clone du tailnet, sans ~/> -e <le clone des données du tailnet, sans ~/> -e maj-jeton-claude -- ~/.config/systemd/user /etc/systemd/system ~/bin /usr/local/bin 2>/dev/null"
  ```
  ```
  ! /c/Windows/System32/OpenSSH/ssh <le serveur> "docker compose ls -a --format json | python3 -c 'import json, sys; [print(f) for p in json.load(sys.stdin) for f in p[\"ConfigFiles\"].split(\",\")]' | xargs -r grep -IlF -e <le clone du tailnet, sans ~/> -e <le clone des données du tailnet, sans ~/> -e maj-jeton-claude -- 2>/dev/null"
  ```
  ```
  ! /c/Windows/System32/OpenSSH/ssh <le serveur> "crontab -l 2>/dev/null | grep -cF -e <le clone du tailnet, sans ~/> -e <le clone des données du tailnet, sans ~/> -e maj-jeton-claude"
  ```

  Les restes sous le compte (`serveur:docs/fiches/README.md:93`), et les copies de la base que documentait le mode retiré :

  ```
  ! /c/Windows/System32/OpenSSH/ssh <le serveur> "find ~ ~/.cache ~/.local/share ~/.local/state ~/.config -maxdepth 1 -iname '*veille*' -exec du -sh {} + 2>/dev/null"
  ```
  ```
  ! /c/Windows/System32/OpenSSH/ssh <le serveur> "ls -la ~/sauvegardes"
  ```

  Les deux clones du tailnet, chacun par ces trois commandes (`<clone>` vaut `<le clone du tailnet>`, puis `<le clone des données du tailnet>`) :

  ```
  ! /c/Windows/System32/OpenSSH/ssh <le serveur> "git --no-optional-locks -C <clone> status -sb --ignored"
  ```
  ```
  ! /c/Windows/System32/OpenSSH/ssh <le serveur> "git --no-optional-locks -C <clone> stash list"
  ```
  ```
  ! /c/Windows/System32/OpenSSH/ssh <le serveur> "git --no-optional-locks -C <clone> log --branches --not --remotes --oneline"
  ```

  Les dossiers, leurs tailles, et le kit de la prod :

  ```
  ! /c/Windows/System32/OpenSSH/ssh <le serveur> "ls -d <le clone du tailnet>* ~/bascule-veille-emploi* <la copie d'avant la scission>"
  ```
  ```
  ! /c/Windows/System32/OpenSSH/ssh <le serveur> "du -sh <le clone du tailnet> <le clone des données du tailnet> ~/bascule-veille-emploi*"
  ```
  ```
  ! /c/Windows/System32/OpenSSH/ssh <le serveur> "docker exec veille-emploi-app-1 veille empreintes-kit"
  ```

  👤 La rubrique `secrets-registre` du dernier relevé de `serveur`, lue comme le prévoit sa procédure (`serveur:docs/fiches/README.md:82-85`), en chemins et en états seulement ; la note privée en écrit la commande. 🤖 Depuis le poste, `/sante` de la prod rend `statut` `ok` : la base de la prod est vivante, sans `veille etat`, qui imprime les relances dues, titre et employeur compris (`cli.py:282-286`).
- [ ] **Étape 3 : la lecture de l'inventaire par la session**, sur ce qu'Edouard colle, avant toute suppression. Elle vérifie :
  - les unités hors du modèle présentes, chacune `inactive`, son fichier sous `~/.config/systemd/user/`, et tout lien d'un `*.wants` ou tout dossier `<unité>.d` qui la vise ; `veille-sauvegarde.*`, s'il existe, s'y ajoute ;
  - les unités de la sonde, qui ne nomment que leur clone et `PATH` (`deploiement/systemd/veille-emploi-sonde.service.in:9-10`) : elles lisent donc les clones de données par défaut (`deploiement/lib.sh:166-168`), et `<le clone des données du tailnet>` n'en est pas (décision 11) ;
  - la recherche de références, son témoin d'abord : la première commande trouve au moins `veille-web.service` et `veille-collecte.service` sous `~/.config/systemd/user`, qui écrivent le chemin du clone ; sans eux, le motif est mal traduit ou la recherche n'a pas tourné, et le geste s'arrête. Puis aucun chemin hors des unités à retirer, et un compte de crontab à 0 ; rien n'appelle donc la copie de `maj-jeton-claude.sh` (décision 13) ;
  - les restes : seuls les clones et les dossiers de la prod et du staging (`~/veille-emploi*`, `~/.local/share/veille-emploi`, `~/.local/state/veille-emploi`), qui ne se touchent jamais, et les dossiers `~/bascule-veille-emploi*` ; tout autre nom se dit à Edouard ;
  - `~/sauvegardes` : une copie de la base du tailnet se montre à Edouard, qui tranche (décision 11) ;
  - les deux clones : ni commit d'avance, ni remise, ni branche locale non envoyée, ni fichier inconnu ; les fichiers locaux attendus sont `config/.env`, `config/vapid.json`, `donnees/` et `.venv/`, `config/auth.json` étant déjà parti (LE-013 de `serveur`) ;
  - le `ls -d` : les deux clones du tailnet, la liste exacte des dossiers de l'instantané et leurs tailles ; tout autre nom, voisin des clones, se dit à Edouard ; `<la copie d'avant la scission>` absente, comme `serveur` le dit (`serveur:CLAUDE.md:97`) : présente, la session le dit à Edouard, qui tranche ;
  - « Aucun ecart » pour le kit de la prod ;
  - la rubrique `secrets-registre` : chaque ligne qui nomme un des deux clones du tailnet se signale à la session de `serveur`, avant sa fusion.

  Un doute arrête le geste : Edouard tranche.
- [ ] **Étape 4 : 👤 les suppressions**, une par message, chacune nommant ce qu'elle retire, puis la vérification d'après :
  - les fichiers d'unités que l'inventaire a trouvés, chacun écrit en entier, jamais par une jointure, qui prendrait les unités `veille-emploi-*` du modèle. Pour les cinq unités déclarées, la commande s'écrit ainsi, et la note privée l'écrit d'après l'inventaire (sans un fichier absent, avec `veille-sauvegarde.service` et `veille-sauvegarde.timer` s'ils existent) :

    ```
    ! /c/Windows/System32/OpenSSH/ssh <le serveur> "rm -- ~/.config/systemd/user/veille-web.service ~/.config/systemd/user/veille-collecte.timer ~/.config/systemd/user/veille-collecte.service ~/.config/systemd/user/veille-verification.timer ~/.config/systemd/user/veille-verification.service"
    ```

    puis, s'il en a trouvé, chaque lien d'un `*.wants` et chaque dossier `<unité>.d`, nommés de même ;
  - `! /c/Windows/System32/OpenSSH/ssh <le serveur> "systemctl --user daemon-reload"`, puis, pour une unité que l'inventaire disait `failed`, `systemctl --user reset-failed <unité>` ;
  - `! /c/Windows/System32/OpenSSH/ssh <le serveur> "rm -rf -- <le clone du tailnet>"` : le clone, sa base, son `config/.env` et son `config/vapid.json` ;
  - `! /c/Windows/System32/OpenSSH/ssh <le serveur> "rm -rf -- <le clone des données du tailnet>"`, si l'étape 3 l'a permis ;
  - `! /c/Windows/System32/OpenSSH/ssh <le serveur> "rm -rf -- ~/bascule-veille-emploi"`, puis un message par dossier `~/bascule-veille-emploi-<n>` que l'inventaire a listé, son nom en entier ;
  - ce qu'Edouard a tranché à l'étape 3 (une copie de `~/sauvegardes`, `<la copie d'avant la scission>`), chacun nommé, le dossier `~/sauvegardes` ne partant, par `rmdir`, que vide.

  Un `Permission denied` arrête le geste : pas de `sudo`, la session le lit. La vérification d'après : `list-unit-files 'veille*' --no-pager` ne liste plus que des `veille-emploi-*` ; `list-timers --all --no-pager` montre les quatre minuteries `veille-emploi-*` avec leur échéance ; `ls -d` des dossiers retirés ne trouve rien ; la recherche des restes ne liste plus que ceux de la prod et du staging. 🤖 Depuis le poste, `/sante` de la prod et du staging rend `statut` `ok`.
- [ ] **Étape 5 : la session note**, pour la PR de `serveur`, la tâche 7 et la clôture : la date, ce qui a été supprimé et ce qui reste (le clone des données du tailnet compris, ou gardé et pourquoi), les tailles, jamais une valeur.
- [ ] **Étape 6 : la PR de `serveur`, fusionnée le soir même** (décision 12). Sa fusion suit la disparition des unités déclarées, quoi qu'il advienne des clones : `list-unit-files 'veille*' --no-pager` n'en liste plus aucune, et aucune ligne `declare-absent` n'est attendue après la fusion. Avant de fusionner, la session de `serveur` aligne le texte de son `CLAUDE.md` sur la note de l'étape 5. Si aucune unité n'est partie, la PR attend un autre soir ; si une partie seulement l'est, la session le dit à Edouard, qui tranche. Si la porte du LE-013 de `serveur` est posée, le retrait des entrées du registre qui nomment le clone du tailnet est fait d'abord, le même soir. La session de `serveur` fusionne juste après la vérification d'après, avant 05:30 ; sa sonde l'applique en cinq minutes. Si elle ne peut le faire avant 05:30, la session annonce à Edouard la nuit rouge attendue, et la PR se fusionne au plus tôt. Le lendemain matin, le contrôle `serveur-inventaire` est vert, et le relevé ne dit ces unités ni déclarées absentes ni non déclarées.

### Tâche 6 : la PR prête, la revue finale et le staging

- [ ] **Étape 1 : la PR prête.** Le corps relu d'abord, sa section « Écarts à la spec » à « Aucun. », éprouvée par `scripts/modele/texte_pr.py` en local. Puis `gh pr ready <n>`. Attendre tous les contrôles verts, `navigateur`, `image` et `texte-pr` compris ; le journal du job `verifier` (`-rs`) ne montre que les six sauts du kit, et aucun test de systemd.
- [ ] **Étape 2 : la revue finale**, par un relecteur neuf sur le modèle le plus capable, sur tout le diff du lot, avec ce plan, l'issue et les journaux des jobs `verifier` et `image`. Elle relit chaque ligne d'« Effets cherchés » là où l'effet arrive, dont le diff de `config.py` (aucun nom de variable retiré ni ajouté), relance sur tout le dépôt la recherche élargie de la tâche 4, étape 4, et relit chaque `minuteur`.
- [ ] **Étape 3 : les corrections**, en une vague, puis leur relecture par un relecteur neuf, sur le diff des corrections. La session fusionne ensuite : `gh pr merge <n> --squash --match-head-commit <sha>`, depuis le clone, sans `cd`.
- [ ] **Étape 4 : 🤖 le mode local sur le poste**, là où les effets du lot se voient. Dans le worktree, sur `principal` à jour, sans `VEILLE_EMPLOI_ENV` ni `VEILLE_VAPID` : `.venv\Scripts\veille servir`, puis `/sante` rend `statut` `ok` et `environnement` `local`, et `donnees/vapid.json` existe ; arrêter, puis retirer ce `donnees/`.
- [ ] **Étape 5 : 👤 le staging, au téléphone : une non-régression.** Le staging tourne avec `VEILLE_EMPLOI_ENV=staging` : chaque branche que le lot change est celle du mode local, que vérifient l'étape 4 et la CI. La session donne à Edouard le SHA du commit fusionné, et lui dit quand `/sante` du staging le rend (`revision`), une fois l'image `:main` publiée et déployée par la sonde. Edouard vérifie :
  - l'application, laissée ouverte pendant ce déploiement : Réglages s'affiche encore après, sans erreur ;
  - Réglages : la fréquence cochée, « Appliquer » sur une autre change « Prochain passage », puis la première se remet ; « Collecter maintenant » dit « La collecte est coupée sur cette console. » ;
  - « Envoyer une notification d'essai » : elle arrive.

### Tâche 7 : le dépôt de données

Après la tâche 5, dont il écrit la date, et après la PR du mandat du lot 3 (`veille-emploi-donnees#54`, fusionnée). La session principale écrit le second mandat d'après cette tâche ; une session ouverte dans le clone de `veille-emploi-donnees` fait la PR et la fusionne une fois tout vert (mode `session`, `gh pr merge <n>` depuis ce clone, sans `cd`). Sa PR dit « Partie de veille-emploi#34 », sans mot de fermeture ; elle dit aussi qu'elle ne change que des commentaires de `config/`, sans étiquette de données, et sa section « Écarts à la spec » porte « Aucun. » (décision 19).

- [ ] **Étape 1 : retirer** `scripts/tailnet/` en entier (`installer.sh`, `exposer-tailnet.sh`, `maj-jeton-claude.sh` : décision 13), par `git rm -r scripts/tailnet`, et la ligne `README.md:13`.
- [ ] **Étape 2 : réécrire**, en gardant les faits datés :
  - dans `CLAUDE.md`, ce qui décrit la console du tailnet comme vivante (relevé du 18/11/2026 : les lignes 18, 25, 28, 31, 40, 42, 45, 56, 67, 70, 76 et 81), et `:131-132` ; le geste des deux clones (`:83-109`) se réduit à son résultat daté, l'étape 9 comprise : la copie d'avant la scission retirée le 13/11/2026, d'après `serveur`, et vue absente par l'inventaire de la tâche 5 ;
  - `docs/DEMARRAGE.md` : § 3, l'exposition sur le tailnet, part ; les autres paragraphes visent la prod ; le geste de copie du kit traduit celui que la tâche 4 écrit dans le `docs/exploitation.md` du code ;
  - `docs/DONNEES.md:11-22`, `docs/FONCTIONNEMENT.md:8-17`, `docs/CANDIDATURE.md` (lignes 12, 22, 26, 30 et 97), `docs/CRITERES.md:13`, `docs/ALERTES.md:57` ;
  - `docs/LIMITES.md` : § 3 part, § 4 reste (décision 14) ; au § 6, les lignes 28 et 29 se réécrivent, la ligne 24, qui nomme les services d'un autre projet, reste ;
  - les commentaires de `config/criteres.yaml:5` et de `config/sources.yaml:16` et `:22`, qui n'arrivent en prod qu'avec la prochaine étiquette de données, sans urgence (décision 19).
- [ ] **Étape 3 : `docs/exploitation.md`.** La table des rôles garde les quatre lignes de la console du tailnet, dites retirées du serveur à la date de la tâche 5 ; la ligne du clone de ses données reçoit `<le clone des données du tailnet>`, et une ligne neuve porte `<la copie d'avant la scission>`. Ses lignes 27-28 disent le ménage fait. Les gestes morts (la configuration désignée de la console du tailnet, la bascule, les dossiers de l'instantané, le retrait de la console) deviennent des paragraphes datés, qui renvoient au geste entier par `git show aaf5d76:docs/exploitation.md` (décision 16), et le ménage de ce lot s'y écrit : sa date, ce qui a été supprimé, les tailles, jamais une valeur.
- [ ] **Étape 4 : la recherche**, sur le clone hors de `docs/modele/` : le motif élargi de la tâche 4, étape 4, plus `bascule-veille`, plus les valeurs des quatre lignes de la console du tailnet de la table des rôles ; puis chaque `minuteur`, relu à la main. Restent justes : les faits datés et l'historique, les lignes de la table dites retirées, la ligne 24 de `docs/LIMITES.md`, et `.gitignore`, qui garde un vieux clone.
- [ ] **Étape 5 : la relecture de la PR**, par un relecteur neuf, avant sa fusion.

### Tâche 8 : la clôture

- [ ] **Étape 1 : la PR de clôture**, sur une branche partie de `principal` à jour. Elle supprime ce plan ; ajoute au paragraphe daté de la bascule, dans `docs/exploitation.md`, la phrase du ménage du serveur, avec sa date et son résultat réel, d'après la note de la tâche 5, étape 5 (le clone des données du tailnet gardé, s'il l'a été) ; reporte dans `CLAUDE.md` ce qui doit survivre : l'état du lot (le mode local, la date du ménage du serveur, la PR du dépôt de données et celle de `serveur`), le paragraphe du lot #12 qui disait le clone du tailnet en attente, et la ligne « Prochain » : 👤 `v0.5.0`, puis la suite de l'éditeur, à placer par Edouard ; ajoute au § 1 de l'ADR-0002 la ligne datée qui renvoie au lot (cadrage 11) ; relit le README d'après `docs/modele/documentation.md` ; porte au registre (`docs/registre.md`), par `/consigner`, les leçons du lot encore sans ligne, celles du dépôt de données et du serveur comprises : au moins, si la revue finale le juge utile, le constat du mode systemd gardé une semaine après le retrait de sa console, et celui des fichiers d'unités que la déclaration de `serveur` attendait ; y clôt LE-12 si la recherche ne trouve plus, dans les deux dépôts, de geste `systemctl` qui liste ou montre sans `--no-pager` ; coche les critères de `veille-emploi#34` ; porte « Closes #34 », la section « Écarts à la spec » à « Aucun. », éprouvée par `scripts/modele/texte_pr.py` avec `"totalCount":1`, et la ligne `Tête relue : <SHA>` de la tête qu'a lue sa dernière relecture. La session la fusionne.
- [ ] **Étape 2 : 👤 l'étiquette `v0.5.0`**, sur le commit de la clôture, posée par Edouard. Puis, depuis le poste, `/sante` de la prod rend `"version":"0.5.0"`, et `modele-version` a publié l'image `0.5.0`. 👤 Le premier test de restauration du dimanche qui suit est vert dans Healthchecks : l'image `0.5.0`, lancée sans aucune variable, a rendu une santé `ok`. Puis le ménage du worktree.

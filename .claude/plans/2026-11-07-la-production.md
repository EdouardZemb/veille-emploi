# Le lot #12 : la production et la bascule — plan

> **Pour les agents :** compétence requise, *superpowers* `subagent-driven-development` (recommandée) ou `executing-plans`, tâche par tâche. Les étapes se cochent (`- [ ]`). Les tâches 👤 sont des gestes d'Edouard, écrits d'avance : la session les prépare, ne les lance pas, et vérifie ce qui se vérifie depuis le poste.

**Objectif :** la console en conteneur sert les vraies données en production, sur l'adresse publique, et la console du tailnet est retirée.

**Architecture :** le code ne change que là où la bascule le demande : un dossier de candidature se retrouve par son nom sous `CHEMIN_DOSSIERS`, et une commande efface les accès liés à l'ancienne adresse. Les données passent par la chaîne du modèle : un instantané pris dans le clone du tailnet, posé en prod par `restaurer.sh`. Tout le reste est un geste 👤 écrit d'avance, d'abord dans `docs/exploitation.md` du code (le mécanisme), puis dans celui du dépôt de données (le geste pas à pas, avec les vraies valeurs).

**Pile :** Python, FastAPI, SQLite (la console) ; les scripts Bash de `deploiement/` (la chaîne du modèle) ; `sops` et `age` (les secrets) ; Cloudflare et Healthchecks.

**Spec :** l'issue `veille-emploi-donnees#12` (ses critères d'acceptation) ; ADR-0002, §§ 7, 9 et 10 ; `docs/exploitation.md`, « La mise en service », « Mettre en ligne », « Restaurer » et « Secrets ».

**Préalables :** le staging est en service (#11) ; la scission est close (V2) ; le modèle est en `v0.9.0` (`veille-emploi#7`) ; les workflows du modèle sont enregistrés (EM-2).

## Les décisions de cadrage

Prises le 07/11/2026 (« OK pour les défauts ») :

1. Ce plan vit dans le dépôt de code, avec des marqueurs à la place de tout ce qui identifie l'instance : `<le serveur>`, `<domaine>`, `<sous_domaine>`, `<le clone du tailnet>`, `<le port du tailnet>`. Le geste avec les vraies valeurs va dans le `docs/exploitation.md` du dépôt de données (tâche 5).
2. Les chemins de dossier absolus se règlent dans le code, à la lecture seulement. La base n'est pas réécrite, et l'écriture ne change pas : l'image précédente lit ce qu'écrit la nouvelle (invariant commun 4).
3. Les passkeys, sessions, liens et abonnements push de l'adresse du tailnet s'effacent par une commande testée, `veille oublier-adresse`, lancée dans le conteneur de prod juste après la restauration.
4. Les secrets de prod : 👤 le relevé des noms de `config/.env` du tailnet ajuste `prod.cles` si besoin, puis `prod.env.enc` se refait en entier, avec les vraies valeurs et les adresses des deux contrôles Healthchecks des sauvegardes.
5. La première version de prod est `v0.1.0`, précédée de la première étiquette de données, `donnees-AAAA.MM.JJ.1`.
6. Le retrait du tailnet coupe `tailscale serve` et désactive les unités. Le clone du tailnet et ses données restent sur le serveur jusqu'au lot « fin du mode systemd », qui les retire : d'ici là, ils servent de copie de secours.

Hors périmètre, comme le dit l'issue : l'affinement dans le conteneur (en prod, le bouton répond que `VEILLE_SDK_AGENT` n'est pas posée), et la mise en commun de la connexion dans `modele-projet`. L'issue `veille-emploi-donnees#43` reste hors du lot.

## Contraintes globales

- Ce plan, les PR du code et leurs messages ne portent rien qui identifie l'instance : la porte de confidentialité du dépôt public les refuse. Les marqueurs ci-dessus en tiennent lieu.
- Aucun secret ne passe par la conversation : les valeurs vont de KeePassXC à `secrets.ps1`, en saisie masquée.
- Une session n'écrit jamais sur le serveur. Tout geste sur le serveur est 👤. Depuis le poste, la session vérifie ce qui se lit sans `ssh` : `curl` sur `/sante`, `gh api`, `gh run`.
- Aucun geste sur le serveur entre 2 h et 4 h 15, ni le dimanche matin : ce sont les fenêtres des sauvegardes et des tests de restauration.
- Les étiquettes sont à Edouard : la session les prépare et ne les envoie pas.
- Invariant 4 du projet : rien de ce que lit l'image précédente ne change de forme. `oublier-adresse` n'ajoute aucune variable `VEILLE_*` (invariant 6).
- Les commits suivent Conventional Commits, en français, avec un en-tête de 100 caractères au plus, un titre de PR de 93 caractères au plus, `git add` par chemins, et la fusion par squash. Un sujet = un worktree, dans `<dépôt>.worktrees\<sujet>`.
- Qui fusionne : une PR du code, cette session (mode `session`) ; une PR du dépôt de données, une session ouverte dans son clone, ou Edouard ; la PR de `serveur`, une session ouverte dans son clone, selon son mode `fusion`.
- La suite du code se lance sur le poste par `.venv\Scripts\python -m pytest -q -p no:cacheprovider` : une dizaine de minutes. Le test s'écrit d'abord, et il échoue.

## Points d'attention de la revue

Les cas que l'issue implique sans qu'une tâche les nomme, du plus probable au moins probable. Chacun a son test dans la tâche qui possède le code.

1. **Un dossier généré avant la bascule.** Sa valeur en base est un chemin absolu d'une autre arborescence : il s'ouvre quand même, par son nom, sous `CHEMIN_DOSSIERS` (tâche 2, `test_un_dossier_d_une_autre_arborescence_s_ouvre_par_son_nom`).
2. **Une valeur en base qui ne nomme pas de dossier** (`""`, `.`, `..`, `/`, ou qui finit par `..`) : on ne sort jamais de `CHEMIN_DOSSIERS`, et le geste répond comme sans dossier (tâche 2, le test paramétré et `test_un_dossier_nomme_point_point_est_introuvable`).
3. **Un chemin écrit avec des barres inverses** : son dernier segment est son nom, sur Linux comme sous Windows (tâche 2, `test_un_chemin_windows_donne_aussi_son_nom`).
4. **`oublier-adresse` sur une base neuve**, sans aucune ligne : la commande initialise la base et rend 0 avec `--oui` (tâche 3, `test_oublier_adresse_sur_une_base_vide`).
5. **`oublier-adresse` interrompue** : les quatre tables s'effacent en une seule transaction, et un échec ne laisse rien d'effacé (tâche 3, `test_oublier_adresse_tout_ou_rien`).

---

### Tâche 1 : 👤 le relevé des noms de `config/.env`

**Fichiers :** aucun. Le relevé décide si la tâche 4 change `deploiement/secrets/prod.cles`.

- [ ] 👤 Sur le serveur, dans `<le clone du tailnet>` : `grep -oE '^[A-Za-z_][A-Za-z0-9_]*=' config/.env | sort`. Les noms seulement, jamais les valeurs.
- [ ] 👤 Edouard colle la liste des noms dans la conversation.
- [ ] La session la compare aux secrets de la collecte de `prod.cles` (`FT_CLIENT_ID`, `FT_CLIENT_SECRET`, `VEILLE_IMAP_UTILISATEUR`, `VEILLE_IMAP_MOTDEPASSE`, `VEILLE_MAIL_DESTINATAIRE`). Ce qui n'est pas un secret n'entre pas dans `prod.cles` : `VEILLE_URL`, `VEILLE_CONFIG`, `VEILLE_SDK_AGENT`, les chemins. En conteneur, `compose.projet.yml` les pose, ou ils n'ont pas cours. Un secret lu par le code et absent de la liste entre dans `prod.cles`. Un nom de la liste que le code ne lit plus n'y entre pas.

**Vérification :** la liste des clés de prod est arrêtée, et la tâche 4 sait si `prod.cles` change.

### Tâche 2 : le dossier se retrouve par son nom

**Fichiers :**
- Modifier : `src/veille/dossier.py` (une fonction)
- Modifier : `src/veille/app.py`, les six lectures de `dossier_chemin` (vers les lignes 543-545, 569-571, 614-618, 794-797, 851-853 et 875-877). L'écriture, vers la ligne 832, ne change pas.
- Modifier : `tests/test_dossier.py`, `tests/test_app.py`, `tests/test_instance.py` (`_une_offre`)
- Modifier : `docs/pistes.md` : la piste « Les chemins des dossiers sont absolus en base » sort

**Interfaces :**
- Produit : `dossier.chemin_du_dossier(offre: Mapping[str, Any]) -> Path | None`. Elle rend `None` si `offre.get("dossier_chemin")` est vide, ou si son dernier segment non vide est `.` ou `..`, ou s'il n'en a aucun. Sinon, elle rend `CHEMIN_DOSSIERS / <dernier segment>`, où `/` et `\` séparent tous deux les segments. `CHEMIN_DOSSIERS` est l'attribut du module `dossier`, lu à l'appel : les tests qui le remplacent par `monkeypatch` restent justes. Elle ne vérifie pas que le dossier existe.

- [ ] **Étape 1 : les tests de la fonction**, dans `tests/test_dossier.py` :

```python
def test_le_dossier_se_retrouve_par_son_nom_sous_chemin_dossiers(monkeypatch, tmp_path):
    monkeypatch.setattr(dossier, "CHEMIN_DOSSIERS", tmp_path / "sortie")
    offre = {"dossier_chemin": "/home/ailleurs/console/donnees/dossiers/2026-10-01-testeuse"}
    assert dossier.chemin_du_dossier(offre) == tmp_path / "sortie" / "2026-10-01-testeuse"

def test_un_chemin_windows_donne_aussi_son_nom(monkeypatch, tmp_path):
    monkeypatch.setattr(dossier, "CHEMIN_DOSSIERS", tmp_path / "sortie")
    offre = {"dossier_chemin": "C:\\donnees\\dossiers\\2026-10-01-testeuse"}
    assert dossier.chemin_du_dossier(offre) == tmp_path / "sortie" / "2026-10-01-testeuse"

def test_un_nom_seul_reste_sous_chemin_dossiers(monkeypatch, tmp_path):
    monkeypatch.setattr(dossier, "CHEMIN_DOSSIERS", tmp_path / "sortie")
    assert dossier.chemin_du_dossier({"dossier_chemin": "2026-10-01-testeuse"}) == \
        tmp_path / "sortie" / "2026-10-01-testeuse"

@pytest.mark.parametrize("valeur", [None, "", ".", "..", "/", "dossiers/..", "\\"])
def test_une_valeur_qui_ne_nomme_pas_de_dossier_ne_donne_rien(valeur):
    assert dossier.chemin_du_dossier({"dossier_chemin": valeur}) is None
```

- [ ] **Étape 2 :** `.venv\Scripts\python -m pytest -q -p no:cacheprovider tests/test_dossier.py -k "chemin_dossiers or windows or nom_seul or ne_nomme_pas"` échoue (`AttributeError`).
- [ ] **Étape 3 :** écrire `chemin_du_dossier` dans `src/veille/dossier.py`, avec une docstring qui dit pourquoi : la base garde le chemin de la machine qui a généré le dossier, et une restauration change de machine.
- [ ] **Étape 4 :** les tests de l'étape 1 passent.
- [ ] **Étape 5 : les tests de la console**, dans `tests/test_app.py`, à côté de `test_dossier_refuse_de_sortir_de_son_repertoire` :
  - `test_un_dossier_d_une_autre_arborescence_s_ouvre_par_son_nom(connecte)` : générer le dossier d'une offre (`POST /api/offres/{oid}/dossier`), puis réécrire sa valeur en base par `db.maj_champs(oid, dossier_chemin="/ailleurs/donnees/dossiers/" + nom)`, où `nom` est `Path(db.lire_offre(oid)["dossier_chemin"]).name`. `GET /api/offres/{oid}/dossier/archive` rend 200, et le contenu commence par `b"PK"`. `GET /api/offres/{oid}/dossier/fiche-offre.md` rend 200.
  - `test_un_dossier_nomme_point_point_est_introuvable(connecte)` : `db.maj_champs(oid, dossier_chemin="..")`. L'archive et `GET …/dossier/fiche-offre.md` rendent 404.
- [ ] **Étape 6 :** ces deux tests échouent : le premier rend 404, l'archive cherchant sous `/ailleurs`.
- [ ] **Étape 7 :** dans `app.py`, chaque lecture passe par `dossier.chemin_du_dossier(offre)`. Un `None` donne la réponse que donnait une valeur absente à cet endroit : 400 « genere d'abord le dossier » à la ligne 543, 404 ailleurs, et des pièces vides pour l'entretien (794). La barrière anti-traversée de `api_fichier_dossier` reste, sur `chemin.resolve()`.
- [ ] **Étape 8 :** `_une_offre` de `tests/test_instance.py` crée son dossier sous `dossier.CHEMIN_DOSSIERS`, celui que pose `tests/conftest.py`, et non sous `tmp_path` : sans refus, chaque geste doit aller jusqu'à son travail, comme le dit sa docstring.
- [ ] **Étape 9 :** la suite entière passe. `grep -n 'offre\["dossier_chemin"\]' src/veille/app.py` ne rend rien.
- [ ] **Étape 10 :** la piste des chemins absolus sort de `docs/pistes.md`.
- [ ] **Étape 11 :** commit : `fix(dossier): un dossier se retrouve par son nom sous CHEMIN_DOSSIERS`.

**Vérification :** la suite est verte, et un dossier généré sous une autre arborescence s'ouvre dans la console.

### Tâche 3 : `veille oublier-adresse`

**Fichiers :**
- Modifier : `src/veille/db.py` (deux fonctions), `src/veille/cli.py` (une commande)
- Modifier : `tests/test_cli_connexion.py`

**Interfaces :**
- Produit : `db.compter_acces() -> dict[str, int]`, avec les clés `"passkeys"`, `"sessions"`, `"liens_connexion"` et `"abonnements_push"`, dans cet ordre, chacune portant le nombre de lignes de sa table.
- Produit : `db.effacer_acces() -> dict[str, int]` : efface toutes les lignes des quatre tables en une seule transaction (`with connexion()`), et rend le nombre de lignes effacées, avec les mêmes clés.
- Produit : `veille oublier-adresse [--oui]`. La commande appelle d'abord `db.initialiser()`. Sans `--oui`, elle imprime les quatre nombres, puis « Rien n'est effacé sans --oui. », et rend 64. Avec `--oui`, elle efface et imprime ce qui l'a été, puis « `veille lien` enregistre la passkey de la nouvelle adresse. », et rend 0. Sa docstring dit pourquoi : une passkey est liée au nom d'hôte, un abonnement push et une session à l'origine (ADR-0002, § 10, étape 4).

- [ ] **Étape 1 : les tests**, dans `tests/test_cli_connexion.py`, avec ses aides (`_sans_passkey`, `_passkey`), et `auth.ouvrir_session`, `db.creer_lien`, `db.enregistrer_abonnement` pour le reste :
  - `test_oublier_adresse_sans_oui_compte_et_n_efface_rien(capsys)` : une passkey, une session, un lien et un abonnement en base. `cli.principal(["oublier-adresse"]) == 64` ; `db.compter_acces()` est inchangé ; la sortie nomme chacun des quatre nombres.
  - `test_oublier_adresse_avec_oui_efface_les_quatre(capsys)` : même base, et une offre. `cli.principal(["oublier-adresse", "--oui"]) == 0` ; `db.compter_acces()` vaut 0 partout ; l'offre est toujours là, et `reglages` n'a pas changé.
  - `test_oublier_adresse_sur_une_base_vide()` : toutes les tables vides ; `cli.principal(["oublier-adresse", "--oui"]) == 0`.
  - `test_oublier_adresse_tout_ou_rien()`, sur le modèle de `test_retirer_une_passkey_tout_ou_rien` : un déclencheur `BEFORE DELETE ON abonnements_push` qui lève `RAISE(ABORT, …)`. `db.effacer_acces()` lève `sqlite3.Error`, et `db.compter_acces()` est inchangé. Le déclencheur se retire dans un `finally`.
- [ ] **Étape 2 :** `.venv\Scripts\python -m pytest -q -p no:cacheprovider tests/test_cli_connexion.py -k oublier` échoue.
- [ ] **Étape 3 :** écrire `compter_acces` et `effacer_acces` dans `db.py`, puis `cmd_oublier_adresse` dans `cli.py`, et son analyseur à côté de celui de `passkeys` (`--oui`, `action="store_true"`).
- [ ] **Étape 4 :** les tests passent, puis la suite entière.
- [ ] **Étape 5 :** commit : `feat(cli): veille oublier-adresse efface les accès d'une ancienne adresse`.

**Vérification :** la suite est verte, et `veille oublier-adresse --help` décrit la commande.

### Tâche 4 : la bascule écrite dans le code

**Fichiers :**
- Modifier : `docs/exploitation.md` : une section « La bascule depuis une console sans conteneur », après « Restaurer » ; et le paragraphe de `prod.cles` de « Secrets »
- Modifier : `docs/LIMITES.md`, §§ 3 et 4
- Modifier : `CLAUDE.md`, « Commandes », « Pour le conteneur » : `veille oublier-adresse [--oui]`
- Modifier, selon la tâche 1 : `deploiement/secrets/prod.cles`

- [ ] **Étape 1 : la section de `docs/exploitation.md`**, générique, avec des marqueurs. Elle dit, dans cet ordre :
  - **la fenêtre** : de l'étiquette `vX.Y.Z` à la restauration, avant la collecte suivante de la prod. Une prod vide collecte aux heures par défaut (`reglages.py`) : sans appareil abonné, le repli mail enverrait toutes les offres de la collecte au-dessus du seuil. La fenêtre s'ouvre juste après une collecte de l'ancienne console ;
  - **les étapes**, chacune avec sa commande et ce qu'elle doit rendre : la tâche 9, sans les valeurs de l'instance ;
  - **le retour arrière**, possible jusqu'au retrait, dans cet ordre (corrigé par la revue finale : l'ancien minuteur a `Persistent=true`). Arrêter la prod : `systemctl --user stop` de ses trois minuteries (la sonde, la sauvegarde et son test), puis la commande `stop app` de « Débloquer un déploiement ». Mettre en pause ses trois contrôles dans Healthchecks. Si la cause est dans le code, ramener le clone du tailnet au commit noté à l'étape 2 de la tâche 9. Enfin, relancer le minuteur de l'ancienne console (`systemctl --user enable --now veille-collecte.timer`, depuis la revue finale : l'étape 6 le désactive), qui peut collecter tout de suite et reprend sur ses données, intactes. La prod est abandonnée ; ses données restent dans son `/donnees` ;
  - **après le retrait**, le retour arrière est une restauration de la prod (« Restaurer »), et non plus l'ancienne console ;
  - le renvoi au geste pas à pas de l'instance réelle, dans le `docs/exploitation.md` du dépôt de données.
- [ ] **Étape 2 : `docs/LIMITES.md`.** Le § 3, « Jamais d'exposition publique », ne vaut plus : ADR-0002 a choisi l'adresse publique. Il dit désormais que la console en conteneur est servie sur l'adresse publique, par le tunnel du serveur, et que seules les passkeys la gardent. Ce qu'il disait de `tailscale serve` et de `funnel` reste, sous « la console sans conteneur, jusqu'à son retrait ». Le § 4 généralise : aucun réseau n'est une authentification, et `Depends(auth.exiger_session)` reste sur chaque route.
- [ ] **Étape 3 : les clés.** Si la tâche 1 a changé la liste, `prod.cles` la suit. Dans tous les cas, « faute du relevé des noms de config/.env du serveur : le lot #12 l'ajuste » sort de `prod.cles` et de « Secrets » : le relevé est fait.
- [ ] **Étape 4 :** `CLAUDE.md` nomme la commande. `python -B scripts/modele/documentation.py` rend 0. La suite passe, si `prod.cles` a changé (`tests/test_deploiement.py` le lit).
- [ ] **Étape 5 :** commit : `docs(exploitation): la bascule depuis une console sans conteneur`.
- [ ] **Étape 6 :** les tâches 2 à 4 forment une seule PR du code, une tâche par commit. Tous les contrôles sont verts, puis la session fusionne : `gh pr merge <n> --squash --match-head-commit <sha>`, depuis le clone, sans `cd`.

**Vérification :** la PR est fusionnée, et l'image `:sha-<tête>` est publiée (job `image` vert sur `principal`). Le staging la déploie, et `curl -s https://<sous_domaine>-staging.<domaine>/sante` dit `version` `main`.

### Tâche 5 : le geste pas à pas, dans le dépôt de données

**Fichiers :**
- Modifier, dans `veille-emploi-donnees` : `docs/exploitation.md`, avec une section « La bascule, geste par geste (lot #12) », et la table « Les rôles », qui gagne la prod

- [ ] **Étape 1 :** un worktree dans `veille-emploi-donnees.worktrees\bascule`, depuis `origin/principal`, avec `--no-track`.
- [ ] **Étape 2 :** la section reprend la tâche 9, dans son ordre, avec les vraies valeurs : le clone du tailnet, son port, l'adresse de la prod, les noms des contrôles. Pour chaque geste, la commande à coller, ce qu'elle doit rendre, et ce qu'on fait sinon. Puis le retour arrière, et le retrait (tâche 11).
- [ ] **Étape 3 :** commit `docs(exploitation): la bascule geste par geste`, PR, fusionnée par une session ouverte dans le clone des données, ou par Edouard.

**Vérification :** la PR est fusionnée. Le geste se lit d'un bout à l'autre sans rien chercher ailleurs.

### Tâche 6 : 👤 les secrets de prod et les contrôles Healthchecks

**Fichiers :** `secrets/prod.env.enc` du dépôt de données.

- [ ] 👤 Healthchecks : `veille-emploi-sauvegarde`, chaque jour à 03:30, 2 heures de grâce ; `veille-emploi-test-restauration`, chaque semaine, le dimanche à 05:30, 6 heures de grâce. Les deux au fuseau du serveur, et les adresses rangées dans KeePassXC.
- [ ] 👤 Dans le clone des données, sur le poste, après la fusion de la tâche 4 : `powershell -NoProfile -File scripts/modele/secrets.ps1 refaire secrets/prod.env.enc`. Chaque valeur est collée depuis KeePassXC, et le mot de passe d'application de Gmail sans ses espaces.
- [ ] Une session ouverte dans le clone des données commite le `.enc` dans une PR. `modele-donnees.yml` est vert : les clés sont celles de `prod.cles` sur `principal` du code. La PR est fusionnée par cette session, ou par Edouard.

**Vérification :** la PR est fusionnée, et sa CI est verte. Aucune valeur n'est passée par la conversation.

### Tâche 7 : les heures des sauvegardes, dans `serveur`

**Fichiers :** `projets/veille-emploi.env` du dépôt `serveur`.

- [ ] Une session ouverte dans le clone de `serveur` : `SAUVEGARDE=03:30`, `TEST_RESTAURATION=Sun 05:30` (ADR-0002, § 7 : 45 minutes après la sauvegarde d'`ancrage`, à 02:45, et 75 minutes après son test du dimanche, à 04:15 ; le modèle exige 30 et 60). Elle met aussi `REGISTRE.md` à jour, s'il nomme les contrôles. PR, prête, mais pas fusionnée avant le jour de la bascule.
- [ ] La route de prod, `<sous_domaine>.<domaine>`, déclarée dans `tunnel/routes.toml` de `serveur` et appliquée par Edouard (👤 `routes plan`, puis `routes appliquer`, depuis le poste). Elle peut l'être avant le jour de la bascule : c'est un préalable de la tâche 9.
- [ ] 👤 **Le jour de la bascule**, après 04:15, juste avant l'étape 1 de la tâche 9, et non la veille : Edouard fusionne la PR des heures. Dès la fusion, l'installeur du projet pose les minuteries de la sauvegarde et de son test ; sans prod déployée, `sauvegarder.sh` (« compose.env absent ») et `tester-restauration.sh` enverraient `/fail` à leur heure.
- [ ] 👤 Une dizaine de minutes plus tard, sur le serveur : le `grep` des deux heures dans `projets/veille-emploi.env` du clone de `serveur` les rend, `systemctl --user list-timers 'veille-emploi-*'` montre les minuteries de la sauvegarde et de son test, et le journal de la sonde du serveur ne signale aucun refus pour `veille-emploi`.
- [ ] 👤 Si la bascule n'atteint pas l'étape 5 ce jour-là, avant la nuit (2 h) : `systemctl --user stop veille-emploi-sauvegarde.timer veille-emploi-test-restauration.timer`. L'installeur du déploiement suivant les relance.

**Vérification :** la PR est fusionnée le jour de la bascule, **avant** l'étiquette `v0.1.0` : l'installeur refuse `non` dès que la prod se déploie.

### Tâche 8 : la revue finale, avant la bascule

- [ ] Un relecteur neuf relit tout ce que le lot a changé : `git diff 7ced445..origin/principal` du code, et les PR des tâches 5 et 6. Il lit contre l'issue, l'ADR-0002 (§ 10) et les points d'attention ci-dessus.
- [ ] Ce qu'il trouve se corrige dans une PR de revue finale, fusionnée comme les autres. Rien ne s'étiquette avant.

**Vérification :** aucun constat ouvert. La tête de `principal` du code est celle qu'on étiquettera.

### Tâche 9 : 👤 la bascule

**Préalables :** les tâches 1 à 8 sont faites, en particulier : `prod.env.enc` refait et fusionné dans le dépôt de données (tâche 6), les contrôles Healthchecks créés (tâche 6). 🤖 La route de prod existe (tâche 7) : `nslookup <sous_domaine>.<domaine>` se résout, une réponse de Cloudflare ; un 502 sur l'adresse est attendu tant qu'aucun conteneur de prod ne tourne. Le jour même, juste avant l'étape 1 : 👤 la PR de `serveur` qui déclare les heures des sauvegardes est fusionnée, après 04:15, et une dizaine de minutes plus tard, les deux heures et les deux minuteries se lisent sur le serveur (tâche 7). Un préalable manque : on ne commence pas. La fenêtre est ouverte : juste après une collecte de la console du tailnet (`systemctl --user list-timers veille-collecte.timer` dit la prochaine), au moins trois heures avant la collecte suivante de la prod aux heures par défaut, et hors des fenêtres du serveur.

- [ ] **1.** 👤 L'étiquette de données, sur la tête de `principal` du dépôt de données, depuis son clone : `git tag -a donnees-AAAA.MM.JJ.1 -m "donnees-AAAA.MM.JJ.1 : la configuration et les secrets de la première prod" <commit>`, puis `git push origin donnees-AAAA.MM.JJ.1`.
- [ ] **2.** 👤 D'abord, le commit en service, à noter pour le retour arrière : `git -C <le clone du tailnet> rev-parse HEAD`. Puis le clone du tailnet passe au commit à étiqueter, par la commande « mettre l'outil à jour » de `CLAUDE.md` ; la même commande `rev-parse` rend alors ce commit-là : l'instantané sera pris par le même code que la prod. La mise à jour finit par la ligne « Aucun ecart : le kit est celui qui a ete valide. » : le code 0 ne suffit pas, « Kit indisponible » rend 0 aussi. Sinon, la bascule s'arrête avant l'étiquette du code.
- [ ] **3.** 🤖 D'abord, l'image du commit est publiée : `gh api users/EdouardZemb/packages/container/veille-emploi/versions --jq '.[].metadata.container.tags[]' | grep -x "sha-<commit>"`, où `<commit>` est le commit complet (40 caractères), rend la ligne. Sinon, attendre la fin du job `image` de la CI : `modele-version.yml` refuse un commit sans cette image. Puis 👤 l'étiquette du code, depuis le clone du code : `git tag -a v0.1.0 -m "v0.1.0 : la première production" <commit>`, puis `git push origin v0.1.0`.
- [ ] **4.** 🤖 Le premier passage de `modele-version.yml`, qui n'a jamais tourné (EM-2) : `gh run list --workflow modele-version.yml --limit 1` est vert, et `gh api users/EdouardZemb/packages/container/veille-emploi/versions --jq '.[].metadata.container.tags[]'` liste `0.1.0`. Sinon, on s'arrête, et l'ancienne console tourne toujours ; mais l'étiquette reste, et la sonde de prod déploierait dès que l'image paraîtrait : 👤 les points 1 et 2 du retour arrière (ses minuteries arrêtées, ses contrôles en pause). `modele-version` ne se relance que dans une nouvelle fenêtre ; l'étape 4 se refait, puis la bascule reprend à l'étape 5.
- [ ] **5.** 👤 `systemctl --user start veille-emploi-sonde-prod.service`, pour ne pas attendre. 🤖 `curl -s https://<sous_domaine>.<domaine>/sante` dit `statut` `ok`, `environnement` `prod`, `version` `0.1.0` et `configuration` `montee`. Sinon, on s'arrête : l'ancienne console collecte toujours, et la prod, vide, s'arrête avant sa première échéance, par le retour arrière.
- [ ] **6.** 👤 L'ancienne console cesse de collecter : `systemctl --user disable --now veille-collecte.timer` (arrêté seulement, il repartirait au redémarrage du serveur ; le retour arrière le réactive). `list-timers` ne lui montre plus d'échéance. Le minuteur arrêté n'arrête pas une collecte en cours : `systemctl --user is-active veille-collecte.service` rend `inactive` (ou `failed`, si la dernière a échoué) ; sinon, attendre qu'elle finisse, et relancer la commande. Dès lors, on ne modifie plus rien dans l'ancienne console.
- [ ] **7.** 👤 L'instantané, dans le clone du tailnet, dans un dossier neuf (`creer` refuse un dossier qui n'est pas vide) : `./.venv/bin/veille instantane creer ~/bascule-veille-emploi` rend 0, puis `./.venv/bin/veille instantane verifier ~/bascule-veille-emploi` rend 0. `id -u` rend 1000, l'uid du conteneur. Puis le contrôle des dossiers, qui ne fait que lire la base de l'instantané (la commande est dans le dépôt de données) : aucune offre n'a un `dossier_chemin` dont le dernier segment manque dans `~/bascule-veille-emploi/dossiers` ; il imprime `0`. Enfin, `rm ~/bascule-veille-emploi/vapid.json` : le conteneur refait ses clés au redémarrage de la restauration, au sujet de l'adresse publique, puisque l'étape 10 efface tous les abonnements.
- [ ] **8.** 👤 La restauration, d'abord à blanc : `bash ~/veille-emploi/deploiement/restaurer.sh prod ~/bascule-veille-emploi` affiche son plan et rend 64. Puis la même commande avec `--oui` rend 0. Sa sortie dit « couple de l'instantané inconnu », et c'est attendu : l'instantané ne vient pas de la chaîne.
- [ ] **9.** 👤 Les données restaurées, avant le téléphone : `docker exec veille-emploi-app-1 veille etat` et `./.venv/bin/veille etat`, dans le clone du tailnet, comptent les mêmes offres, et `docker exec veille-emploi-app-1 veille empreintes-kit` dit « Aucun ecart : le kit est celui qui a ete valide. » et rend 0. Sinon, revenir en arrière, ou reprendre à l'étape 7 dans un dossier neuf (par exemple `~/bascule-veille-emploi-2`, dans les commandes des étapes 7 et 8), puis refaire les étapes suivantes.
- [ ] **10.** 👤 Les accès de l'ancienne adresse : `docker exec veille-emploi-app-1 veille oublier-adresse` compte et rend 64 ; puis la même commande avec `--oui` rend 0.
- [ ] **11.** 👤 Le téléphone : `docker exec veille-emploi-app-1 veille lien` donne le lien, à ouvrir sur le téléphone ; il reste hors de la conversation, c'est un jeton d'inscription. Installer l'application depuis la nouvelle adresse, créer la passkey, activer les notifications. Puis `docker exec veille-emploi-app-1 veille tester-notification --envoyer`, filtré (le dépôt de données donne le filtre : la sortie nomme le compte et le destinataire du mail), dit `envoyes : 1 | echecs : 0` et `remise : OK` : la notification arrive.
- [ ] **12.** 👤 Au téléphone, un dossier généré avant la bascule s'ouvre (tâche 2), une pièce du kit se télécharge, et le seuil de Réglages est celui d'avant. Sinon, comme à l'étape 9.
- [ ] **13.** 👤 La première collecte de la prod, à son échéance : `docker logs --since 30m veille-emploi-app-1` la montre, et l'état des sources, dans Réglages, est vert. Une offre au-dessus du seuil fait arriver une notification sur la nouvelle adresse. `veille-emploi-sonde-prod` est vert dans Healthchecks, comme il l'est resté depuis la demi-heure qui a suivi le déploiement (sinon, `HC_SONDE` du `prod.env.enc` n'est pas l'adresse de ce contrôle).

**Retour arrière,** jusqu'à la tâche 11 : celui de la section de la tâche 4, dans cet ordre. (1) La prod s'arrête : ses trois minuteries, puis `stop app`, s'il existe un conteneur. (2) Ses trois contrôles passent en pause dans Healthchecks. (3) Si la cause est dans le code, le clone du tailnet revient au commit noté à l'étape 2 (`git checkout <commit>`, puis l'installation et le redémarrage de « mettre l'outil à jour »). (4) `systemctl --user enable --now veille-collecte.timer`, qui peut collecter tout de suite (`Persistent=true`). Pour reprendre ensuite la bascule : si (3) a eu lieu, `git -C <le clone du tailnet> checkout principal` d'abord ; puis l'état de la prod décide de l'étape 5. Avec `deploye`, le conteneur d'abord (`docker start veille-emploi-app-1`), puis ses minuteries. Avec `echec` sans `deploye`, pas de `docker start` : un nouveau couple d'abord (une étiquette sur un nouveau commit, des données ou du code), puis la minuterie de la sonde. Sans l'un ni l'autre (jamais déployée), pas de `docker start` : la minuterie de la sonde seulement, et la sonde déploie. Ses contrôles sortent de la pause, et l'instantané de l'étape 7 va dans un dossier neuf.

**Vérification :** la prod sert les vraies données, la nouvelle adresse est installée au téléphone avec sa passkey et ses notifications, et la prod a collecté une fois.

### Tâche 10 : 👤 la première sauvegarde et le test de restauration

- [ ] 👤 Sur le serveur, hors des fenêtres : `bash ~/veille-emploi/deploiement/sauvegarder.sh prod` rend 0, et `veille-emploi-sauvegarde` passe au vert dans Healthchecks.
- [ ] 👤 `bash ~/veille-emploi/deploiement/tester-restauration.sh prod` rend 0, et `veille-emploi-test-restauration` passe au vert.
- [ ] 👤 `journalctl --user -u veille-emploi-sonde-prod | grep "ménage des images"` : la ligne de bilan du premier déploiement de prod. La session la transmet à `modele-projet`, qui l'attend.

**Vérification :** une sauvegarde de la prod existe, à distance, et elle se restaure.

### Tâche 11 : 👤 le retrait de la console du tailnet

**Préalables :** une journée entière de prod, avec ses trois collectes, une notification reçue sur la nouvelle adresse, et la tâche 10 verte.

- [ ] 👤 `sudo tailscale serve --https=<le port du tailnet> off`, puis `tailscale serve status` ne nomme plus ce port.
- [ ] 👤 `systemctl --user disable --now veille-web.service veille-collecte.timer veille-collecte.service`. Puis `systemctl --user list-units 'veille-web*' 'veille-collecte*' --all` ne montre aucune de ces trois unités active (le motif laisse de côté les unités `veille-emploi-*` de la prod).
- [ ] 👤 L'ancienne application est retirée du téléphone.
- [ ] Le clone du tailnet, ses données et `~/bascule-veille-emploi` restent : la décision 6 les confie au lot « fin du mode systemd ».

**Vérification :** l'ancienne adresse ne répond plus. Le retour arrière passe désormais par « Restaurer ».

### Tâche 12 : la clôture

**Fichiers :**
- Code : `CLAUDE.md` (État : la prod en service depuis le jour de la bascule, sur `v0.1.0`, la console du tailnet retirée, le mode systemd du code gardé jusqu'à son lot ; « Commandes » : la section de la console sans conteneur dit qu'elle n'a plus d'instance), `docs/DEMARRAGE.md` (§ 3, les certificats du tailnet : pour une console sans conteneur seulement), `docs/pistes.md` (« Retirer le mode systemd » gagne le retrait du clone du tailnet, de ses données et de `~/bascule-veille-emploi`), ce plan, supprimé
- Données : `CLAUDE.md` et `docs/exploitation.md` (la console du tailnet est retirée, la prod est en service), `README.md` s'il en parle
- Hors dépôt : `INDEX-PROJETS.md`, et la mémoire de la session

- [ ] Le README du code est relu, d'après `docs/modele/documentation.md` : c'est la case du gabarit de PR.
- [ ] Les constats du lot vont au registre du code, par `/consigner`.
- [ ] Une PR de clôture par dépôt. Celle du code est fusionnée par cette session, celle des données par une session de son clone, ou par Edouard. Ni l'une ni l'autre ne demande d'étiquette : elles ne changent que des textes.

**Vérification :** l'issue `veille-emploi-donnees#12` se ferme, chacun de ses critères pointant vers sa preuve.

---

## Vérification du lot

| Critère de l'issue | Où il se prouve |
|---|---|
| La migration des vraies données (base, kit, réglages, clés des notifications), écrite avec son retour arrière | tâches 2 à 5, puis 9 (étapes 7 à 12). Les clés des notifications ne sont pas reprises : le conteneur les refait au sujet de l'adresse publique (étape 7), décision par défaut de la revue finale, qu'Edouard peut renverser |
| 👤 Les secrets de prod et les deux contrôles des sauvegardes | tâches 1 et 6 |
| 👤 L'étiquette, et la prod vérifiée au téléphone (application, passkey, notifications) | tâche 9 (étapes 3 à 5, puis 11) |
| 👤 La première sauvegarde et le test de restauration | tâche 10 |
| L'ancien service en parallèle jusqu'à la vérification, puis 👤 son retrait | tâches 9 (étape 6) et 11 |
| README, `CLAUDE.md` et index à jour | tâche 12 |

## Exécution

- **Les tâches 2 à 4**, le code, par `subagent-driven-development` : un implémenteur par tâche, un relecteur après chacune, dans un seul worktree du code, `veille-emploi.worktrees\production`.
- **Les tâches 5 et 6**, les données : la session prépare la tâche 5 dans un worktree du dépôt de données. La tâche 6 attend le geste d'Edouard.
- **La tâche 7**, `serveur` : une session ouverte dans son clone.
- **Les tâches 1 et 9 à 11** sont des gestes d'Edouard. La session prépare chaque commande, attend ses sorties, et vérifie ce qui se lit depuis le poste.
- **Ordre :** 1, puis 2 à 4 ; 5, 6 et 7 en parallèle après 4 (la PR des heures de la tâche 7 ne se fusionne que le jour de la 9) ; 8 ; 9 dans sa fenêtre ; 10 ; 11, au plus tôt le lendemain ; 12.

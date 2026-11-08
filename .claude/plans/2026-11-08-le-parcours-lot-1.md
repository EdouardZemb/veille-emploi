# Lot 1 du parcours (ADR-0003) : les cinq états, la file « À faire » et la fiche par état — plan

> **Pour les agents :** compétence requise, *superpowers* `subagent-driven-development` (recommandée) ou `executing-plans`, tâche par tâche. Les étapes se cochent (`- [ ]`). Les tâches 👤 sont des gestes d'Edouard : la session les prépare et ne les lance pas.

**Objectif :** la console s'ouvre sur ce qui attend un geste, et chaque fiche ne propose plus que l'action de l'état de son offre (issue `veille-emploi#13`).

**Architecture :** un module pur, `src/veille/etats.py`, lit les onze statuts en cinq états, et compose la file « À faire » et les groupes de « Candidatures ». Trois routes en lecture le servent. L'interface reçoit deux vues neuves, « À faire » et « Candidatures », et une fiche par état. L'onglet « Plus » mène aux anciens écrans, inchangés. Chaque geste écrit un statut qui existe déjà, par les routes actuelles : ni migration ni colonne.

**Pile :** Python 3.13, FastAPI, SQLite ; JavaScript sans framework (`src/veille/static/app.js`) ; pytest ; Playwright (`tests_navigateur/`) ; mutmut 3.8.1 (CI Linux seulement).

**Spec :** `docs/decisions/0003-le-parcours-jusqu-a-la-candidature.md`, §§ 1 à 4, 7 et 8, pour la part du lot 1 ; les critères d'acceptation de `veille-emploi#13`.

**Préalables :** la clôture de `veille-emploi-donnees#12` est fusionnée : ce lot ne commence pas avant. Un worktree `veille-emploi.worktrees\parcours-lot1`, sur une branche `feat/parcours-lot1` partie de `origin/principal`, avec son environnement : `python -m venv .venv`, puis `.venv\Scripts\python -m pip install -e .[dev,navigateur]`, puis `.venv\Scripts\python -m playwright install chromium`.

## Les décisions du plan

Ce que l'ADR laisse ouvert, tranché ici :

1. `etats.py` porte toute la logique pure du lot : `etat_de`, la raison d'« À finir », la composition de la file et les groupes de « Candidatures ». La mutation (tâche 6) couvre ce fichier entier.
2. « À voir » montre au plus 50 offres. La réponse dit combien restent au-dessus du seuil, et combien sont dessous ; les deux nombres mènent à « Toutes les offres ».
3. Une offre archivée (son annonce a quitté le site) reste dans « Candidatures » et dans « À finir » si elle est `interessante`, `candidature_envoyee`, `relance_envoyee`, `reponse_recue` ou `entretien` : la candidature continue sans l'annonce, comme `db.relances_dues` le fait déjà. Une offre `nouveau` ou `a_traiter` archivée n'y paraît pas.
4. Dans ce lot, « Je postule » écrit `interessante` puis ouvre la fiche. La fiche « Je postule » sans dossier propose « Générer le dossier », le geste actuel. « Préparer ma candidature » vient au lot 2.
5. Un statut inconnu fait lever `etat_de` (`ValueError`), et un test vérifie que chaque valeur de `models.STATUTS` a son état : un statut ajouté sans état casse la suite, pas l'écran.
6. La notification push ouvre `/?filtre=nouveau` (`notifications.py`, inchangé) : ce paramètre mène désormais à « À faire ». Les autres valeurs de `filtre`, et `atout`, mènent toujours à « Toutes les offres », filtrée.
7. Le test de navigateur simule le dossier par `db.maj_champs(offre_id, dossier_chemin=…)` : la génération est déjà testée en Python, et le job `navigateur` n'a ni WeasyPrint ni configuration désignée.
8. Une seule PR d'implémentation, `feat/parcours-lot1`, un commit (au moins) par tâche. La session la fusionne une fois tout vert (mode `session`).

## Contraintes globales

- Aucune migration, aucune colonne, aucune variable `VEILLE_*` nouvelle (invariant 6). L'image `0.1.0` doit lire la base telle que ce lot l'écrit.
- Chaque geste écrit un statut de `models.STATUTS` par une route existante : `POST /api/offres/{id}/statut`, `POST /api/offres/{id}/constat`, `POST /api/offres/{id}/relance/envoyee`. Écarter exige toujours un motif.
- Les anciens écrans (Offres, Relances, Archive, À classer, Pilotage, Documents, Réglages) gardent leur comportement : ils sont seulement atteints par « Plus ». Le lot 3 les remaniera.
- Le dépôt est public : rien n'identifie l'instance, et toute donnée de test est inventée, avec des liens en `.exemple.invalid` (M-0001).
- **Les fins de ligne ne se normalisent pas (invariant 7).** Restent en CRLF : `src/veille/static/app.js`, `src/veille/static/style.css`, `src/veille/templates/index.html`, `src/veille/db.py`, `src/veille/models.py`, `README.md`, `docs/CANDIDATURE.md`. Restent en LF : `src/veille/app.py`, `src/veille/factice.py`, `pyproject.toml`, `.github/workflows/ci.yml`, `.gitignore`, `CLAUDE.md`, `docs/FONCTIONNEMENT.md`, `docs/DEMARRAGE.md`, les tests. Un fichier neuf est en LF. Avant chaque commit, pour chaque fichier touché : `python -I -c "import sys;b=open(sys.argv[1],'rb').read();print(b.count(b'\r\n'), b.count(b'\n'))" <fichier>` rend deux nombres égaux (CRLF) ou un zéro en premier (LF), comme avant.
- Le JavaScript : toute donnée d'offre passe par `echapper()` ; toute route appelée existe (`tests/test_javascript.py`) ; `node --check` passe.
- Au téléphone (390 × 844) : toute cible fait au moins 44 px de haut (`DOIGT`, `tests_navigateur/test_cibles_tactiles.py`), et aucune vue ne défile de côté.
- Le test s'écrit d'abord, et il échoue. La suite du poste : `.venv\Scripts\python -m pytest -q -p no:cacheprovider` (des sauts attendus sous Windows) ; celle du navigateur : `.venv\Scripts\python -m pytest -q -p no:cacheprovider tests_navigateur`.
- Les commits : Conventional Commits, en français, en-tête de 100 caractères au plus, `git add` par chemins, les deux lignes d'attribution en pied. Jamais `--no-verify`.

## Points d'attention de la revue

Ce que l'ADR implique sans qu'un critère le nomme, du plus probable au moins probable. Chacun a son test dans la tâche qui possède le code.

1. **On touche une notification** (`/?filtre=nouveau`) : la console s'ouvre sur « À faire », pas sur une liste filtrée cachée sous « Plus » (tâche 4, `test_une_notification_mene_a_a_faire`).
2. **Rien à montrer** (aucune offre au-dessus du seuil, aucune candidature) : une phrase le dit, jamais un écran blanc (tâche 4, `test_a_faire_vide_le_dit` ; tâche 5, `test_candidatures_vides_le_dit`).
3. **Un double toucher** sur « Plus tard » : un seul changement de statut, une seule ligne d'historique (tâche 4, `test_plus_tard_ne_compte_qu_une_fois`).
4. **Une candidature dont l'annonce a quitté le site** : elle reste dans « Candidatures », et sa relance dans « À finir » ; une offre `nouveau` archivée n'est jamais « À voir » (tâche 2, `test_une_candidature_archivee_reste_suivie`).
5. **Un intitulé très long** au téléphone : ni « À faire » ni la fiche ne défilent de côté (tâche 4, `test_a_faire_tient_dans_l_ecran` ; tâche 5, `test_la_fiche_tient_dans_l_ecran`).

---

### Tâche 1 : les états et la file, en Python pur

**Fichiers :**
- Créer : `src/veille/etats.py`
- Test : `tests/test_etats.py`

**Interfaces :**
- Consomme : `veille.models.STATUTS` (la liste des onze statuts).
- Produit :
  - `ETATS: tuple[str, ...] = ("a_voir", "je_postule", "envoyee", "entretien", "close")` et `MISE_DE_COTE = "mise_de_cote"` ;
  - `etat_de(offre: Mapping[str, Any]) -> str` ;
  - `raison_a_finir(offre: Mapping[str, Any], aujourd_hui: date) -> str | None`, qui rend `"relance_due"`, `"a_envoyer"`, `"a_preparer"` ou `None` ;
  - `composer_a_faire(offres: list[dict[str, Any]], seuil: float, aujourd_hui: date, limite_a_voir: int = 50) -> dict[str, Any]`, qui rend `{"a_finir": [...], "a_voir": [...], "a_voir_restantes": int, "plus_tard": [...]}` ;
  - `grouper_candidatures(offres: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]`, qui rend `{"je_postule": [...], "envoyee": [...], "entretien": [...]}`.
  - Chaque offre rendue est une **copie** qui porte `"etat"` ; celles d'« À finir » portent aussi `"raison"`, celles de « je_postule » portent `"dossier": bool`. Les dictionnaires reçus ne sont jamais modifiés.

- [ ] **Étape 1 : écrire les tests qui échouent**

```python
from datetime import date

import pytest

from veille import etats
from veille.models import STATUTS

AUJ = date(2026, 11, 20)


@pytest.mark.parametrize("statut, etat", [
    ("nouveau", "a_voir"), ("a_traiter", "a_voir"), ("interessante", "je_postule"),
    ("candidature_envoyee", "envoyee"), ("relance_envoyee", "envoyee"),
    ("reponse_recue", "envoyee"), ("entretien", "entretien"),
    ("ecartee", "close"), ("refus", "close"), ("accepte", "close"),
    ("differee", "mise_de_cote"),
])
def test_chaque_statut_a_son_etat(statut, etat):
    assert etats.etat_de({"statut": statut}) == etat


def test_aucun_statut_connu_n_est_sans_etat():
    for s in STATUTS:
        assert etats.etat_de({"statut": s}) in (*etats.ETATS, etats.MISE_DE_COTE)


@pytest.mark.parametrize("offre", [{}, {"statut": None}, {"statut": "inconnu"}])
def test_un_statut_inconnu_leve(offre):
    with pytest.raises(ValueError):
        etats.etat_de(offre)


@pytest.mark.parametrize("offre, raison", [
    ({"statut": "candidature_envoyee", "date_relance_due": "2026-11-20"}, "relance_due"),
    ({"statut": "candidature_envoyee", "date_relance_due": "2026-11-19"}, "relance_due"),
    ({"statut": "relance_envoyee", "date_relance_due": "2026-11-01"}, "relance_due"),
    ({"statut": "candidature_envoyee", "date_relance_due": "2026-11-21"}, None),
    ({"statut": "candidature_envoyee", "date_relance_due": None}, None),
    ({"statut": "reponse_recue", "date_relance_due": "2026-11-01"}, None),
    ({"statut": "interessante", "dossier_chemin": "2026-11-20_x_y"}, "a_envoyer"),
    ({"statut": "interessante", "dossier_chemin": ""}, "a_preparer"),
    ({"statut": "interessante", "dossier_chemin": None}, "a_preparer"),
    ({"statut": "nouveau"}, None),
    ({"statut": "entretien"}, None),
])
def test_la_raison_d_a_finir(offre, raison):
    assert etats.raison_a_finir(offre, AUJ) == raison
```

Puis les tests de la composition. Une aide `_o(id, statut, score=50, **champs)` rend `{"id": id, "statut": statut, "score": score, "date_collecte": "2026-11-01T08:00:00", **champs}`.

- `test_la_file_compose_ses_trois_groupes` : avec le seuil 45, les offres `_o(1, "nouveau", 80)`, `_o(2, "nouveau", 60)`, `_o(3, "nouveau", 30)`, `_o(4, "a_traiter", 70)`, `_o(5, "interessante", 50)`, `_o(6, "interessante", 40, dossier_chemin="d")`, `_o(7, "candidature_envoyee", date_relance_due="2026-11-19")`, `_o(8, "candidature_envoyee", date_relance_due="2026-11-30")`, `_o(9, "relance_envoyee", date_relance_due="2026-11-20")` donnent : les ids d'« À finir » `[7, 9, 6, 5]` (les relances dues par date croissante, puis « à envoyer », puis « à préparer », chacun par score décroissant), ceux d'« À voir » `[1, 2]`, ceux de « Plus tard » `[4]`, `a_voir_restantes == 0` ; chaque offre rendue porte `etat`, et celles d'« À finir » leurs raisons `["relance_due", "relance_due", "a_envoyer", "a_preparer"]`.
- `test_le_seuil_est_inclus` : une offre `nouveau` dont le score vaut le seuil est « À voir ».
- `test_a_voir_s_arrete_a_la_limite` : 55 offres `nouveau` au-dessus du seuil et `limite_a_voir=50` donnent 50 offres, les 50 meilleurs scores, et `a_voir_restantes == 5`.
- `test_a_score_egal_la_plus_recente_d_abord` : deux offres `nouveau` de même score, `date_collecte` `"2026-11-02…"` et `"2026-11-01…"`, sortent dans cet ordre.
- `test_la_composition_ne_touche_pas_les_offres_recues` : après l'appel, aucun dictionnaire reçu n'a la clé `etat`.
- `test_les_candidatures_se_groupent` : `je_postule` reçoit les `interessante`, avec `dossier` vrai seulement quand `dossier_chemin` est rempli ; `envoyee` reçoit `candidature_envoyee`, `relance_envoyee` et `reponse_recue`, par `date_relance_due` croissante, les dates absentes en dernier ; `entretien` reçoit `entretien` ; une offre `nouveau`, `ecartee` ou `differee` n'est dans aucun groupe.

- [ ] **Étape 2 : lancer les tests, ils échouent**

Lancer : `.venv\Scripts\python -m pytest -q -p no:cacheprovider tests/test_etats.py`
Attendu : échec à l'import, `veille.etats` n'existe pas.

- [ ] **Étape 3 : écrire `src/veille/etats.py`**

Une table `_ETAT_DU_STATUT: dict[str, str]`, la seule traduction ; `etat_de` y lit `offre.get("statut")` et lève `ValueError` sur une absence. Les dates se comparent en chaînes ISO (`date_relance_due <= aujourd_hui.isoformat()`), comme `db.relances_dues`. Aucune lecture de base, d'horloge ni de configuration : tout arrive en paramètre. La docstring du module renvoie à l'ADR-0003, § 1.

- [ ] **Étape 4 : lancer les tests, ils passent**

Lancer : `.venv\Scripts\python -m pytest -q -p no:cacheprovider tests/test_etats.py`
Attendu : tous verts.

- [ ] **Étape 5 : commit**

```bash
git add src/veille/etats.py tests/test_etats.py
git commit -F <fichier>   # feat(etats): cinq états lus sur les onze statuts, la file et les candidatures
```

### Tâche 2 : les routes en lecture

**Fichiers :**
- Modifier : `src/veille/db.py` (CRLF), à côté de `relances_dues`
- Modifier : `src/veille/app.py`, à côté de `/api/relances` et dans `api_offres`, `api_offre`
- Test : `tests/test_parcours_api.py`

**Interfaces :**
- Consomme : `etats.etat_de`, `etats.composer_a_faire`, `etats.grouper_candidatures` (tâche 1) ; `reglages.lire_seuil()` ; `db.motifs_ecartement()` ; `db.PREFIXE_AUTOMATIQUE`.
- Produit :
  - `db.offres_pour_a_faire(seuil: float) -> tuple[list[dict[str, Any]], int]` : les offres `interessante`, `candidature_envoyee` et `relance_envoyee`, archivées ou non, plus les `nouveau` non archivées dont le score atteint le seuil, plus les `a_traiter` non archivées ; et le nombre des `nouveau` non archivées sous le seuil. Ordre : `score DESC, date_collecte DESC`.
  - `db.offres_candidatures() -> list[dict[str, Any]]` : les offres `interessante`, `candidature_envoyee`, `relance_envoyee`, `reponse_recue` et `entretien`, archivées ou non.
  - `GET /api/a-faire` → `{"a_finir", "a_voir", "a_voir_restantes", "plus_tard", "sous_le_seuil", "seuil"}`.
  - `GET /api/candidatures` → `{"je_postule", "envoyee", "entretien"}`.
  - `GET /api/motifs?limite=6` → `{"motifs": [str, ...]}` : les motifs d'écartement les plus fréquents, sans ceux qui commencent par `db.PREFIXE_AUTOMATIQUE`, `limite` bornée à 1..20.
  - `GET /api/offres` et `GET /api/offres/{id}` : chaque offre porte `"etat"`.
  - Les trois routes neuves exigent la session (`Depends(auth.exiger_session)`).

- [ ] **Étape 1 : écrire les tests qui échouent**

La base de la suite est commune à tous les tests : chaque test crée ses offres, avec un lien unique en `https://offres.exemple.invalid/parcours/<uuid>`, et ne regarde que leurs ids. Une aide `_offre(statut="nouveau", score=None, **champs) -> int` enregistre une offre inventée (`db.enregistrer_offre(scorer(Offre(...)))`), pose le statut par `db.changer_statut`, le score par `UPDATE offres SET score=?`, et les autres champs par `db.maj_champs`. Le client et la session suivent `tests/test_app.py` (`TestClient`, `tests.aide_session.connecter`).

- `test_les_routes_du_parcours_exigent_la_session` : sans cookie, `/api/a-faire`, `/api/candidatures` et `/api/motifs` rendent 401.
- `test_a_faire_range_chaque_offre_dans_son_groupe` : avec `s = reglages.lire_seuil()`, une `nouveau` à `s + 10` est dans `a_voir`, une `nouveau` à `s - 10` n'y est pas et `sous_le_seuil >= 1`, une `a_traiter` est dans `plus_tard`, une `interessante` sans dossier est dans `a_finir` avec la raison `a_preparer` ; la réponse porte `seuil == s`.
- `test_une_candidature_archivee_reste_suivie` : une `candidature_envoyee` avec `date_relance_due` d'hier, archivée par `db.archiver(id, "retirée du site")`, est dans `a_finir` (raison `relance_due`) et dans `envoyee` de `/api/candidatures` ; une `nouveau` à `s + 10` archivée n'est pas dans `a_voir`.
- `test_candidatures_groupe_les_trois_etats` : une `interessante`, une `reponse_recue` et une `entretien` sont dans `je_postule`, `envoyee` et `entretien` ; une `refus` n'est nulle part.
- `test_les_motifs_frequents_sans_les_automatiques` : trois offres écartées avec `"motif inventé A"`, deux avec `"motif inventé B"`, une avec `db.PREFIXE_AUTOMATIQUE + "motif inventé C"` ; `/api/motifs?limite=20` place A avant B et ne contient aucun motif qui commence par `db.PREFIXE_AUTOMATIQUE` ; `/api/motifs?limite=0` rend au plus un motif.
- `test_l_offre_porte_son_etat` : `/api/offres/{id}` d'une `interessante` porte `etat == "je_postule"`, et chaque offre de `/api/offres` porte une clé `etat`.

- [ ] **Étape 2 : lancer les tests, ils échouent**

Lancer : `.venv\Scripts\python -m pytest -q -p no:cacheprovider tests/test_parcours_api.py`
Attendu : 404 sur les routes neuves, `KeyError: 'etat'`.

- [ ] **Étape 3 : écrire les deux fonctions de `db.py` et les trois routes, et ajouter `etat` aux deux routes d'offres**

Les fonctions de `db.py` passent par `_ligne_en_dict`, comme `relances_dues`. `/api/a-faire` appelle `etats.composer_a_faire(offres, seuil, date.today())` et y ajoute `sous_le_seuil` et `seuil`. Les routes ne font que lire.

- [ ] **Étape 4 : lancer les tests, puis toute la suite**

Lancer : `.venv\Scripts\python -m pytest -q -p no:cacheprovider tests/test_parcours_api.py`, puis `.venv\Scripts\python -m pytest -q -p no:cacheprovider`
Attendu : tout vert, sauf les sauts attendus sous Windows.

- [ ] **Étape 5 : vérifier les fins de ligne de `db.py` (CRLF), puis commit**

```bash
git add src/veille/db.py src/veille/app.py tests/test_parcours_api.py
git commit -F <fichier>   # feat(api): la file « À faire », les candidatures et les motifs fréquents
```

### Tâche 3 : le jeu factice, une offre par état

**Fichiers :**
- Modifier : `src/veille/factice.py` (la boucle des candidatures de `charger`)
- Modifier : `factice/candidatures.yaml`, `factice/LISEZMOI.md`
- Test : `tests/test_factice.py`

**Interfaces :**
- Consomme : `etats.etat_de` (tâche 1).
- Produit : une entrée de `candidatures.yaml` accepte `statut` (défaut `candidature_envoyee`), parmi `interessante`, `a_traiter`, `candidature_envoyee` et `entretien`, et `relance_due: true`, qui pose `date_relance_due` à la veille du chargement. Tout autre `statut` lève `RuntimeError("jeu factice : statut refusé : <statut>")`.

- [ ] **Étape 1 : écrire les tests qui échouent**, dans `tests/test_factice.py`, comme `test_charger_dans_une_base_vide` : la fixture `pdf_bouchon`, puis `factice.charger()` (la fixture automatique `_base_propre` donne une base neuve à chaque test) :
  - `test_le_jeu_factice_couvre_chaque_etat` : après le chargement, les états des offres du jeu comprennent `a_voir`, `je_postule`, `envoyee` et `entretien`, et au moins une offre `a_traiter` existe ;
  - `test_le_jeu_factice_a_une_relance_due` : au moins une offre du jeu a `date_relance_due` antérieure à aujourd'hui et un statut `candidature_envoyee` ;
  - `test_un_statut_factice_refuse_arrete_le_chargement` : `monkeypatch` remplace `factice._lire` par une fonction qui rend, pour `"candidatures.yaml"`, une candidature sur une offre du jeu avec `statut: refus`, et délègue les autres noms à l'original ; `factice.charger()` lève `RuntimeError`.
- [ ] **Étape 2 : lancer `tests/test_factice.py`, ils échouent.**
- [ ] **Étape 3 : modifier le chargeur et le jeu.** Ajouter à `candidatures.yaml` une offre `interessante`, une `a_traiter`, une `entretien`, et `relance_due: true` sur une `candidature_envoyee`. Choisir des offres que le score de l'exemple n'écarte pas ; les liens restent ceux d'`offres.yaml`. Une ligne de `LISEZMOI.md` décrit les deux clés.
- [ ] **Étape 4 : lancer `tests/test_factice.py` et `tests/test_etats.py`, ils passent.**
- [ ] **Étape 5 : commit**

```bash
git add src/veille/factice.py factice/candidatures.yaml factice/LISEZMOI.md tests/test_factice.py
git commit -F <fichier>   # feat(factice): une offre par état du parcours, et une relance due
```

### Tâche 4 : la navigation et la file « À faire »

**Fichiers :**
- Modifier : `src/veille/templates/index.html` (CRLF), `src/veille/static/app.js` (CRLF), `src/veille/static/style.css` (CRLF)
- Modifier : `tests_navigateur/test_cibles_tactiles.py` (la fixture `telephone`)
- Créer : `tests_navigateur/test_parcours_candidature.py`

**Interfaces :**
- Consomme : `GET /api/a-faire`, `GET /api/motifs` (tâche 2) ; dans `app.js` : `api`, `echapper`, `message`, `changerStatut`, `constater`, `rafraichir`, `CHARGEURS`, `chargerRelances`, `compterArchiveNouvelles`.
- Produit, dans `app.js` :
  - `afficherVue(nom: string)`, qui remplace l'écouteur actuel des `.onglet` : tout élément `[data-vue]` affiche `#vue-<nom>`, et l'onglet actif est `ONGLET_DE_VUE[nom] || nom`, où `ONGLET_DE_VUE` envoie `offres`, `relances`, `archive`, `classer`, `pilotage`, `documents`, `reglages` vers `plus` ;
  - `chargerAFaire()`, `carteAVoir(o)`, `ligneAFinir(o)`, `demanderNon(id)`, `chargerPlus()` ;
  - `const RAISONS = {relance_due: 'Relance due', a_envoyer: 'Dossier prêt à envoyer', a_preparer: 'Dossier à préparer'}` et `const LIBELLES_ETAT = {a_voir: 'À voir', je_postule: 'Je postule', envoyee: 'Envoyée', entretien: 'Entretien', close: 'Close', mise_de_cote: 'Mise de côté'}` ;
  - `listeContributions(o)`, tirée de `carteOffre`, qui l'utilise ensuite ;
  - les actions `data-action` : `postuler` (`changerStatut(id, 'interessante')`, puis la fiche à la tâche 5), `plus-tard` (`changerStatut(id, 'a_traiter')`), `non` (`demanderNon(id)`), `fiche` (la fiche à la tâche 5 ; d'ici là, `ouvrirDetail(id)`). Le bouton d'une action neuve se désactive le temps de la requête.
- Produit, dans `index.html` : deux onglets, `data-vue="a-faire"` (« À faire », actif) et `data-vue="plus"` (« Plus ») ; les sections `#vue-a-faire` (`#contenu-a-faire`) et `#vue-plus`, une liste de `button.lien-plus[data-vue]` : Toutes les offres (`offres`), Relances (avec `#pastille-relances`), Archive (avec `#pastille-archive`), À classer (avec `#pastille-classer`), Pilotage, Documents, Réglages. Chaque ancienne section commence par `button.retour-plus[data-vue="plus"]` (« ‹ Plus ») et naît cachée, `#vue-offres` comprise. L'en-tête garde « Notifications » et « Quitter ».

- [ ] **Étape 1 : écrire les tests de navigateur qui échouent**

`tests_navigateur/test_parcours_candidature.py` reprend la forme de `test_cibles_tactiles.py` : `TELEPHONE`, `DOIGT`, une session par `auth.ouvrir_session`, la collecte des erreurs de console (`assert erreurs == []`). Sa fixture de module `offres_parcours` ingère des offres inventées (source `parcours`, liens `https://exemple.invalid/parcours/<n>`), les met en `nouveau` et pose leur score à `reglages.lire_seuil() + 20` ; l'une a un intitulé de 200 caractères. Une offre `ecartee` avec le motif `"motif inventé du parcours"` existe aussi. Les tests ne regardent que les offres de cette source : la base est partagée avec `test_cibles_tactiles.py`.

- `test_la_console_s_ouvre_sur_a_faire` : `#vue-a-faire` est visible, et `.onglet.actif` a `data-vue="a-faire"`.
- `test_une_notification_mene_a_a_faire` : `/?filtre=nouveau` montre `#vue-a-faire`.
- `test_plus_mene_aux_anciens_ecrans` : « Plus », puis « Toutes les offres » montre `#vue-offres` et ses `.offre` ; « ‹ Plus » revient à `#vue-plus`, et « Plus » reste l'onglet actif.
- `test_une_carte_a_voir_porte_trois_boutons_du_doigt` : chaque `#vue-a-faire .carte-a-voir` a trois `.actions button` (« Je postule », « Plus tard », « Non »), chacun haut d'au moins `DOIGT`.
- `test_plus_tard_ne_compte_qu_une_fois` : un `dblclick` sur « Plus tard » d'une carte laisse l'offre `a_traiter`, avec une seule ligne `statut:a_traiter` dans `db.lire_offre(id)["evenements"]`, et la carte passe sous « Plus tard ».
- `test_non_propose_les_motifs_et_ecarte` : « Non » montre un bouton `"motif inventé du parcours"` ; le toucher, puis « Écarter », met l'offre en `ecartee` avec ce motif.
- `test_n_est_plus_en_ligne_archive` : « Non », puis « N'est plus en ligne », pose `archivee_le` sur l'offre.
- `test_a_faire_vide_le_dit` : `page.route("**/api/a-faire", …)` rend `{"a_finir": [], "a_voir": [], "a_voir_restantes": 0, "plus_tard": [], "sous_le_seuil": 0, "seuil": 45}` ; `#vue-a-faire` contient « Rien à faire pour l'instant ».
- `test_a_faire_tient_dans_l_ecran` : `document.documentElement.scrollWidth <= 390` sur « À faire ».

Dans `test_cibles_tactiles.py`, la fixture `telephone` ouvre « Plus » puis « Toutes les offres » avant d'attendre `#liste-offres .offre` : ses tests mesurent l'ancien écran, toujours en service. `test_les_onglets_ne_glissent_pas_sous_la_barre` reste tel quel.

- [ ] **Étape 2 : lancer les tests de navigateur, ils échouent**

Lancer : `.venv\Scripts\python -m pytest -q -p no:cacheprovider tests_navigateur`
Attendu : échec sur `#vue-a-faire` introuvable.

- [ ] **Étape 3 : écrire la navigation, la vue « À faire » et le panneau « Non »**

- **« À faire »** rend, dans l'ordre : « À finir » (une `button.offre.ligne-a-finir[data-action="fiche"][data-id]` par offre : sa raison, l'intitulé, l'employeur), omis s'il est vide ; « À voir » (les `article.offre.carte-a-voir` : l'intitulé dans un `button[data-action="fiche"]`, l'employeur, le lieu, le salaire comme `carteOffre`, les deux contributions positives les plus fortes de `explication`, et les trois boutons) ; sous « À voir », « Voir les N autres au-dessus du seuil › » et « Voir les M sous le seuil › », quand leur nombre n'est pas nul, qui ouvrent « Toutes les offres » ; « Plus tard », un `<details>` replié, omis s'il est vide. Si « À voir » est vide : « Aucune offre au-dessus du seuil de <seuil>. ». Si tout est vide : « Rien à faire pour l'instant : aucune offre au-dessus du seuil de <seuil>. ».
- **`demanderNon(id)`** ouvre `#fenetre` : le rappel que le motif est obligatoire, un bouton par motif de `/api/motifs?limite=6` (le toucher remplit le champ), le champ libre, « Écarter » (`changerStatut(id, 'ecartee', motif)`, refusé sans motif), « N'est plus en ligne » (`constater(id, false)`), « Annuler ».
- **`chargerPlus()`** met à jour les trois pastilles : `/api/relances`, `/api/classement` (le nombre de `propositions`) et `compterArchiveNouvelles()`.
- **Au démarrage** : `afficherVue('a-faire')`, sauf si `filtre` (autre que `nouveau`) ou `atout` est dans l'adresse, auquel cas les filtres se posent comme aujourd'hui et `afficherVue('offres')`. `CHARGEURS` reçoit `'a-faire': chargerAFaire` et `plus: chargerPlus`.
- **Le style** : `.lien-plus`, `.retour-plus`, `.ligne-a-finir` et les boutons des cartes font au moins 44 px de haut ; un intitulé long se coupe (`overflow-wrap: anywhere`).

- [ ] **Étape 4 : lancer les tests de navigateur, puis toute la suite**

Lancer : `.venv\Scripts\python -m pytest -q -p no:cacheprovider tests_navigateur`, puis `.venv\Scripts\python -m pytest -q -p no:cacheprovider`
Attendu : tout vert ; `tests/test_javascript.py` compris (routes, échappement, `node --check`).

- [ ] **Étape 5 : vérifier les fins de ligne des trois fichiers CRLF, puis commit**

```bash
git add src/veille/templates/index.html src/veille/static/app.js src/veille/static/style.css tests_navigateur/test_cibles_tactiles.py tests_navigateur/test_parcours_candidature.py
git commit -F <fichier>   # feat(console): la file « À faire », le panneau « Non » et l'onglet « Plus »
```

### Tâche 5 : la fiche par état et l'onglet « Candidatures »

**Fichiers :**
- Modifier : `src/veille/templates/index.html`, `src/veille/static/app.js`, `src/veille/static/style.css` (CRLF tous trois)
- Modifier : `tests_navigateur/test_parcours_candidature.py`

**Interfaces :**
- Consomme : `GET /api/candidatures`, `GET /api/offres/{id}` (tâche 2) ; `afficherVue`, `LIBELLES_ETAT`, `listeContributions`, `RAISONS` (tâche 4) ; les gestes existants `genererDossier`, `demanderCanal`, `ouvrirRelance`, `ouvrirEntretien`, `ouvrirDetail`.
- Produit :
  - l'onglet `data-vue="candidatures"`, entre « À faire » et « Plus », et la section `#vue-candidatures` (`#contenu-candidatures`) ;
  - `chargerCandidatures()` ; `ouvrirFiche(id)` ; `actionsDeFiche(o) -> string` ;
  - les actions `fiche` → `ouvrirFiche(id)`, `postuler` → `changerStatut(id, 'interessante')` puis `ouvrirFiche(id)`, `reponse` → `changerStatut(id, bouton.dataset.statut)` puis `ouvrirFiche(id)`, `revenir` → `changerStatut(id, 'nouveau')` puis `ouvrirFiche(id)`.

La fiche s'ouvre dans `#fenetre`, sous une racine `div.offre.fiche[data-id]`, pour que l'écouteur global des `[data-action]` y trouve l'id. Elle montre l'intitulé, l'employeur, le lieu, le score, le lien de l'annonce, le libellé de l'état, puis **une seule ligne d'actions**, celle de l'état (`actionsDeFiche`) :

| État de l'offre | Action principale | Autres actions de la ligne |
|---|---|---|
| `nouveau`, `differee` | Je postule (`postuler`) | Plus tard (`plus-tard`), Non (`non`) |
| `a_traiter` | Je postule | Non |
| `interessante` sans dossier | Générer le dossier (`dossier`) | — |
| `interessante` avec dossier | Je l'ai envoyée (`envoyee`) | le paquet d'envoi (`/api/offres/{id}/dossier/archive`), Régénérer le dossier (`dossier`) |
| `candidature_envoyee`, `relance_envoyee`, `reponse_recue` | Mot de relance (`relance`) | Réponse : Entretien, Refus, Acceptée (`reponse`, `data-statut` `entretien`, `refus`, `accepte`) ; la date de relance |
| `entretien` | Préparer l'entretien (`entretien`) | Réponse : Refus, Acceptée |
| `ecartee`, `refus`, `accepte` | — | le motif, s'il existe |

Sous la ligne, trois `<details>` repliés : « Pourquoi ce score » (`listeContributions`), « Notes » (le champ et « Enregistrer », par `POST /api/offres/{id}`), « Autres actions » (« Texte, exigences, vérification, historique › », qui ouvre `ouvrirDetail(id)`, et, hors de l'état « À voir », « Revenir à « À voir » » (`revenir`)).

« Candidatures » rend trois groupes : « Je postule » (« dossier prêt » ou « à préparer »), « Envoyée » (la date de relance), « Entretien ». Chaque ligne est une `button.offre[data-action="fiche"][data-id]`. Un groupe vide est omis ; si les trois le sont : « Aucune candidature en cours. ».

- [ ] **Étape 1 : écrire les tests qui échouent**, dans `tests_navigateur/test_parcours_candidature.py` :
  - `test_le_parcours_de_la_file_a_l_entretien` : sur une offre `nouveau` de la source `parcours`, « Je postule » ouvre la fiche, avec le libellé « Je postule » et un `[data-action="dossier"]` ; le test pose `db.maj_champs(id, dossier_chemin=<un dossier temporaire>)`, ferme la fiche, recharge « À faire », et touche sa ligne « Dossier prêt à envoyer » ; la fiche montre `[data-action="envoyee"]` ; « Je l'ai envoyée », puis le canal « LinkedIn », met l'offre en `candidature_envoyee` ; l'onglet « Candidatures » la montre sous « Envoyée » ; sa fiche, puis « Entretien », met l'offre en `entretien`, et la fiche montre `[data-action="entretien"]`.
  - `test_la_fiche_ne_montre_que_les_actions_de_son_etat` : la fiche d'une `candidature_envoyee` a `[data-action="relance"]` et trois `[data-action="reponse"]`, et aucun `[data-action="postuler"]` ni `[data-action="dossier"]`.
  - `test_les_boutons_de_la_fiche_se_touchent_du_doigt` : chaque bouton de la ligne d'actions et chaque `summary` de la fiche font au moins `DOIGT`.
  - `test_candidatures_vides_le_dit` : `page.route("**/api/candidatures", …)` rend trois listes vides ; `#vue-candidatures` contient « Aucune candidature en cours. ».
  - `test_la_fiche_tient_dans_l_ecran` : la fiche de l'offre à l'intitulé de 200 caractères laisse `document.documentElement.scrollWidth <= 390`.
- [ ] **Étape 2 : lancer les tests de navigateur, ils échouent.**
- [ ] **Étape 3 : écrire la fiche et « Candidatures »**, selon le tableau ci-dessus. `CHARGEURS` reçoit `candidatures: chargerCandidatures`. Un geste fait depuis la fiche la rouvre sur le nouvel état ; les gestes qui ouvrent leur propre fenêtre (`genererDossier`, `demanderCanal`, `ouvrirRelance`, `ouvrirEntretien`) gardent leur comportement.
- [ ] **Étape 4 : lancer les tests de navigateur, puis toute la suite ; tout est vert.**
- [ ] **Étape 5 : vérifier les fins de ligne, puis commit**

```bash
git add src/veille/templates/index.html src/veille/static/app.js src/veille/static/style.css tests_navigateur/test_parcours_candidature.py
git commit -F <fichier>   # feat(console): la fiche par état et l'onglet « Candidatures »
```

### Tâche 6 : la mutation en CI, sur `etats.py`

**Fichiers :**
- Modifier : `pyproject.toml`, `.github/workflows/ci.yml`, `.gitignore`

**Interfaces :**
- Consomme : `src/veille/etats.py` et `tests/test_etats.py` (tâche 1).
- Produit : un job `mutation` dans `ci.yml`, rouge dès qu'un mutant survit.

- [ ] **Étape 1 : la configuration.** Dans `pyproject.toml` :

```toml
[tool.mutmut]
paths_to_mutate = ["src/veille/etats.py"]
pytest_add_cli_args_test_selection = ["tests/test_etats.py"]
also_copy = ["exemple"]
```

et `/mutants/` dans `.gitignore`.

- [ ] **Étape 2 : le job.** Dans `ci.yml`, un job `mutation`, sur `ubuntu-latest`, avec les mêmes actions épinglées que le job `verifier` (`actions/checkout` et `actions/setup-python`, Python 3.13), qui lance :

```bash
pip install -e ".[dev]" "mutmut==3.8.1"
mutmut run
mutmut results | tee resultats.txt
! grep -E ': (survived|no tests|timeout|suspicious)$' resultats.txt
```

mutmut ne tourne pas sous Windows : ce job ne se vérifie qu'en CI.

- [ ] **Étape 3 : envoyer la branche, et lire le job `mutation`.** Lancer : `gh run list --branch feat/parcours-lot1 --limit 1`, puis `gh run view <id> --log` pour le job. Attendu : `mutmut results` liste des mutants `killed`, et le job est vert. Si le format de `mutmut results` diffère du motif de l'étape 2, ajuster le motif pour qu'il rate sur `survived`, et le dire dans la PR. Chaque mutant survivant appelle un test de plus dans `tests/test_etats.py`, jusqu'à zéro.
- [ ] **Étape 4 : commit**

```bash
git add pyproject.toml .github/workflows/ci.yml .gitignore tests/test_etats.py
git commit -F <fichier>   # ci: la mutation commence, sur les états du parcours
```

### Tâche 7 : la documentation du lot

**Fichiers :**
- Modifier : `docs/FONCTIONNEMENT.md`, `docs/DEMARRAGE.md`, `docs/CANDIDATURE.md` (CRLF), `CLAUDE.md` ; `README.md` (CRLF) seulement s'il nomme un onglet

- [ ] **Étape 1 : chercher chaque mention des anciens onglets.** Lancer l'outil Grep sur `docs/`, `README.md` et `CLAUDE.md`, avec le motif `onglet|Relances|Pilotage|A classer|À classer|Archive`.
- [ ] **Étape 2 : réécrire.** Dans `FONCTIONNEMENT.md`, le tableau des onglets devient : « À faire » (ce qui attend un geste, puis les offres à voir, puis « Plus tard »), « Candidatures » (Je postule, Envoyée, Entretien), « Plus » (les anciens écrans, jusqu'au lot 3), avec un renvoi à l'ADR-0003 et la table des cinq états. Ailleurs, « l'onglet Réglages » devient « Plus › Réglages », et de même pour Documents. `CLAUDE.md`, section « État » : une phrase sur le lot 1 de l'ADR-0003 (`veille-emploi#13`) et sur `etats.py`.
- [ ] **Étape 3 : vérifier.** `python -X utf8 -B scripts/modele/documentation.py` rend 0 ; les fins de ligne sont inchangées.
- [ ] **Étape 4 : commit**

```bash
git add docs/FONCTIONNEMENT.md docs/DEMARRAGE.md docs/CANDIDATURE.md CLAUDE.md
git commit -F <fichier>   # docs: la console à trois onglets (lot 1 de l'ADR-0003)
```

### Tâche 8 : la PR, la revue finale et la clôture

- [ ] **Étape 1 : la PR d'implémentation.** `git push -u origin feat/parcours-lot1`, puis `gh pr create --base principal --body-file <fichier>`, avec un titre de 93 caractères au plus et « Closes #13 » dans le corps, que l'on finit avant la fin de la CI. Attendre tous les contrôles verts, `mutation` et `navigateur` compris.
- [ ] **Étape 2 : la revue finale**, par un relecteur neuf sur le modèle le plus capable, sur tout le diff du lot, avec l'ADR-0003 et ce plan. Une seule vague de corrections, puis une relecture ciblée. La session fusionne la PR (`gh pr merge <n> --squash`, depuis le clone, sans `cd`).
- [ ] **Étape 3 : 👤 le staging, au téléphone.** Le staging se redéploie seul depuis `principal`, sur le jeu factice. Edouard vérifie : la console s'ouvre sur « À faire » ; « Plus tard », « Non » et « Je postule » font ce qu'ils disent ; la fiche ne montre que l'action de l'état ; « Candidatures » groupe les trois états ; « Plus » mène aux anciens écrans.
- [ ] **Étape 4 : la clôture.** Une PR qui supprime ce plan, reporte dans `CLAUDE.md` ce qui doit survivre, relit le README (`docs/modele/documentation.md`), et coche les critères de `veille-emploi#13`.
- [ ] **Étape 5 : 👤 l'étiquette `v0.2.0`**, sur le commit de la clôture, posée par Edouard. Puis, depuis le poste, `/sante` de la prod rend `"version":"0.2.0"`, et `modele-version` a publié l'image `0.2.0`.

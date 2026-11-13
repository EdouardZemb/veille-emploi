# Lot 2 du parcours (ADR-0003) : « Préparer ma candidature » — plan

> **Pour les agents :** compétence requise, *superpowers* `subagent-driven-development` (recommandée) ou `executing-plans`, tâche par tâche. Les étapes se cochent (`- [ ]`). Les étapes 👤 sont des gestes d'Edouard : la session les prépare et ne les lance pas.

**Objectif :** d'un toucher sur « Je postule », l'offre passe à son dossier, et la préparation ne s'arrête que sur ce qui manque : le texte de l'annonce, ou une information trop mince (issue `veille-emploi#14`).

**Architecture :** un module neuf, `src/veille/preparation.py`, enchaîne l'existant sans le changer (`enrichissement`, `completude`, `dossier`, `lettre`) et rend l'étape suivante. Une route, `POST /api/offres/{id}/preparer`, le sert. L'interface remplace, dans la file et dans la fiche, « Générer le dossier » par la préparation, et ajoute l'écran « Dossier prêt ». Les anciens écrans gardent leur bouton jusqu'au lot 3.

**Pile :** Python 3.13, FastAPI, SQLite ; JavaScript sans framework (`src/veille/static/app.js`) ; pytest ; Playwright (`tests_navigateur/`) ; mutmut 3.8.1 (CI Linux seulement).

**Spec :** `docs/decisions/0003-le-parcours-jusqu-a-la-candidature.md`, §§ 4, 5, 7 et 8, pour la part du lot 2 ; les critères d'acceptation de `veille-emploi#14`, et les quatre points reportés de la revue du lot 1, commentés sur `veille-emploi#14`.

**Préalables :** un worktree `veille-emploi.worktrees\parcours-lot2`, sur une branche `feat/parcours-lot2` partie de `origin/principal` (`git worktree add --no-track`), avec son environnement : `python -m venv .venv`, puis `.venv\Scripts\python -m pip install -e .[dev,navigateur]`, puis `.venv\Scripts\python -m playwright install chromium`. `git rev-parse --git-path hooks` y rend `.githooks`.

## Mécanismes annoncés

- `src/veille/enrichissement.py:235` — `def politique` — rend une `Politique(autorise, domaine, raison, conseil)` pour l'adresse de l'annonce, sans requête
- `src/veille/enrichissement.py:303` — `def verifier_cadence` — rend `(possible, message)` : la cadence de lecture automatique le permet-elle ?
- `src/veille/enrichissement.py:432` — `def recuperer` — rend `(texte, message)`, le texte vide quand la lecture échoue
- `src/veille/enrichissement.py:484` — `def appliquer_texte` — enregistre le texte complet, met `donnees_partielles` à faux et rend un `Rapport(ok, message, …)` ; refuse sans rien écrire un texte sous `LONGUEUR_MIN`
- `src/veille/enrichissement.py:325` — `LONGUEUR_MIN =` — le plancher de longueur d'un texte d'annonce, 150 caractères
- `src/veille/completude.py:104` — `def evaluer` — rend un `Bilan` dont les manques sont triés par points décroissants
- `src/veille/completude.py:33` — `SEUIL_DOSSIER = 55` — `suffisant_pour_dossier` vaut vrai à partir de ce score
- `src/veille/completude.py:57-84` — `class Bilan` — `Bilan(score, niveau, manques, acquis, suffisant_pour_dossier)` et `Manque(libelle, points, quoi_faire)`, chacun avec `as_dict()`
- `src/veille/dossier.py:667` — `def chemin_du_dossier` — le dossier de l'offre, retrouvé sous `CHEMIN_DOSSIERS` par le dernier segment de `dossier_chemin`, sans vérifier qu'il existe
- `src/veille/dossier.py:696` — `nom_dossier = f` — le dossier se nomme `<date du jour>_<employeur>_<titre>` : une génération du même jour réécrit le même dossier, celle d'un autre jour en crée un autre
- `src/veille/dossier.py:685` — `def generer` — réécrit `lettre-de-motivation.md` sans l'historiser, et rend `ResultatDossier(chemin, fichiers, gabarit_lettre, kit_provisoire, avertissements, pieces_envoi, …)`
- `src/veille/dossier.py:659` — `-candidature.zip` — le paquet d'envoi se nomme `<prefixe>-candidature.zip`, ses pièces sous leur nom d'envoi
- `src/veille/lettre.py:620` — `def historiser` — copie la lettre courante dans `lettre.historique/` sous `NNN-<horodatage>-<etiquette>.md`, et rend `None` sans lettre
- `src/veille/lettre.py:607` — `def versions` — les versions de `lettre.historique/`, de la plus ancienne à la plus récente
- `src/veille/lettre.py:50` — `NOM_HISTORIQUE =` — le dossier d'historique s'appelle `lettre.historique`
- `src/veille/rendu.py:166` — `def nom_pour_envoi` — le nom qu'un recruteur voit : `cv.fr.pdf` devient `<Prefixe>-CV-France.pdf`
- `src/veille/etats.py:34` — `def etat_de` — lit l'état d'une offre (`a_voir`, `mise_de_cote`, `je_postule`, `envoyee`, `entretien`, `close`) sur son statut
- `src/veille/db.py:350` — `def changer_statut` — écrit le statut et le journalise (`statut:<statut>`)
- `src/veille/db.py:342` — `def journaliser` — ajoute une ligne `(type, detail)` à l'historique de l'offre
- `src/veille/app.py:108` — `def _refus_sans_configuration_hors_conteneur` — rend un 409 `configuration_non_designee` quand la console sert l'exemple par oubli, `None` sinon
- `src/veille/app.py:737` — `def api_maj` — enregistre `contact_nom`, `contact_civilite`, `adresse_entreprise` et `reference_annonce` sur l'offre
- `src/veille/app.py:804` — `def api_dossier` — l'ancien geste « Générer le dossier », que les anciens écrans gardent jusqu'au lot 3
- `src/veille/app.py:843` — `def api_archive` — sert le paquet d'envoi
- `src/veille/app.py:877` — `filename=cible.name` — une pièce téléchargée seule garde son nom sur le disque, pas son nom d'envoi
- `src/veille/static/app.js:33` — `const ERREURS_API` — traduit un code d'erreur de l'API en phrase
- `src/veille/static/app.js:761` — `function gesteNeuf` — désactive le bouton pendant un geste, et le réactive sur une erreur
- `src/veille/static/app.js:709` — `function demanderCanal` — le panneau « Je l'ai envoyée », qui demande le canal puis écrit `candidature_envoyee`
- `src/veille/static/app.js:1572` — `async function blocAffinement` — le bloc « Affiner la lettre », ou une ligne qui dit pourquoi l'affinement est indisponible
- `src/veille/static/app.js:1592` — `function brancherAffinement` — branche ce bloc ; montre le temps écoulé pendant l'appel
- `src/veille/static/app.js:1660` — `function blocDestinataire` — les trois champs du destinataire et la référence de l'annonce
- `src/veille/static/app.js:1683` — `function brancherDestinataire` — propose la référence de l'annonce, puis enregistre les champs par `POST /api/offres/{id}`
- `src/veille/static/app.js:945` — `Générer le dossier</button>` — la fiche « Je postule » sans dossier propose encore l'ancien geste
- `src/veille/static/app.js:1437` — `a === 'postuler'` — « Je postule » écrit `interessante` puis ouvre la fiche, sans rien préparer
- `tests_navigateur/test_parcours_candidature.py:378` — `to_have_count(0)` — l'assertion inerte du lot 1 : `get_by_role` ne voit rien dans la fenêtre fermée
- `.github/workflows/ci.yml:108` — `Parcours de connexion` — l'étape du job `navigateur`, qui lance aussi le parcours de candidature
- `.github/workflows/ci.yml:72` — `Mutation de src/veille/etats.py` — l'étape du job `mutation`
- `pyproject.toml:53` — `only_mutate` — mutmut ne mute que `src/veille/etats.py`
- `pyproject.toml:54` — `pytest_add_cli_args_test_selection` — et ne lance que `tests/test_etats.py`

## Outils et cas limites

- mutmut 3.8.1 — le littéral d'un appel de journal (`log.warning("…")`) donne un mutant qu'aucun test ne tue, et le job exige zéro mutant d'un autre statut que `killed` — le job `mutation` de la CI (`mutmut results --all true`), avec `# pragma: no mutate` sur les seules lignes de journal (tâche 1)
- Playwright, `get_by_role` — ignore les éléments cachés : un `to_have_count(0)` dans une fenêtre fermée passe toujours — `test_non_nomme_l_offre_et_ecarte_la_bonne`, réécrit avec `locator('[data-motif=…]')` (tâche 4)
- Playwright, `page.route` — une requête retenue, puis servie plus tard par `fulfill`, reste en vol tant que le test ne la libère pas : c'est ce qui rend observables le bouton désactivé et son temps écoulé — `test_je_postule_lance_la_preparation_et_montre_le_temps` (tâche 4)
- `zipfile.ZipFile` — un paquet d'envoi absent lève `FileNotFoundError` au lieu de rendre une liste vide — `test_sans_paquet_d_envoi_le_dossier_pret_n_a_aucune_piece` (tâche 1)
- `shutil.copytree` — lève si la cible existe, et avec `dirs_exist_ok` fusionne deux historiques dont les numéros se heurtent — `test_un_historique_deja_present_n_est_pas_ecrase` (tâche 2)
- `TestClient` de FastAPI — une route `def` tourne dans le pool de fils, si bien que deux appels lancés de deux fils se chevauchent vraiment — `test_deux_preparations_de_la_meme_offre_ne_se_chevauchent_pas` (tâche 3)
- `FileResponse` de Starlette — un nom non ASCII part en `filename*=utf-8''…`, pas en `filename="…"` — `test_une_piece_se_telecharge_sous_son_nom_d_envoi`, qui lit le nom par `email.message.Message.get_filename` (tâche 3)

## Revues

- la revue de la tâche 1, par un relecteur neuf, avant la tâche 2 : Tâche 1
- la revue de la tâche 2, par un relecteur neuf, avant la tâche 3 : Tâche 2
- la revue de la tâche 3, par un relecteur neuf, avant la tâche 4 : Tâche 3
- la revue de la tâche 4, par un relecteur neuf, avant la tâche 5 : Tâche 4
- la revue de la tâche 5, par un relecteur neuf, avant la PR : Tâche 5
- la revue finale, sur tout le diff du lot, par un relecteur neuf sur le modèle le plus capable, avec la lecture des mutants survivants (ADR-0003, § 7) : Tâche 6
- la relecture des corrections de la revue finale, par un relecteur neuf : Tâche 6

## Les décisions du plan

Ce que l'ADR laisse ouvert, tranché ici :

1. **Quatre étapes.** `preparer` rend `texte`, `mince` ou `pret`, comme l'ADR, ou `echec`, la cause d'une génération en échec, que la fiche propose de réessayer.
2. **Un extrait, c'est `donnees_partielles` vrai.** Une description courte qui n'est pas un extrait ne se relit pas : elle va à `mince`, où « Description complète » est le manque le plus lourd. L'écran `mince` propose alors de coller le texte, en plus de « Générer quand même ».
3. **Les statuts que « Je postule » prend :** `nouveau`, `a_traiter` et `differee` passent en `interessante`. `differee` n'est pas nommé par le § 5, mais la fiche d'une offre mise de côté propose « Je postule » depuis le lot 1 : sans lui, le geste ne changerait rien. Une offre déjà `interessante` garde son statut. Toute offre d'un autre état (Envoyée, Entretien, Close) est refusée, sans rien écrire (`EtatIncompatible`, 409 `etat_incompatible`).
4. **Un dossier existant est rendu, pas refait.** Sans `regenerer`, une offre dont le dossier existe sur le disque rend `pret` sans générer. « Dossier prêt › », depuis la fiche, passe par la même route : un double appel ne régénère jamais.
5. **Régénérer ne redemande rien.** `regenerer=True` saute la lecture du texte et la complétude : le dossier a déjà été accepté une fois, peut-être par « Générer quand même ».
6. **Régénérer n'efface rien (invariant 4).** La lettre courante entre d'abord dans l'historique de son dossier, sous l'étiquette `avant-regeneration`. Si la génération crée un autre dossier (un autre jour), l'historique de l'ancien y est copié, sauf si le nouveau en a déjà un. L'ancien dossier reste sur le disque, et `dossier_chemin` passe au nouveau.
7. **Une pièce seule porte son nom d'envoi.** `dossier_pret` liste les fichiers du dossier dont le nom d'envoi est dans le paquet d'envoi ; la route d'un fichier gagne `?pour_envoi=true`, qui le sert sous ce nom. Un formulaire en ligne reçoit donc les mêmes noms que le zip.
8. **Une préparation à la fois par offre.** La route refuse une seconde préparation de la même offre tant que la première tourne (409 `preparation_en_cours`), en plus du bouton désactivé.
9. **La route refuse comme les autres gestes** quand la console sert l'exemple par oubli (409 `configuration_non_designee`) ; « Je postule » aussi, puisqu'il lance la préparation.
10. **Le navigateur simule `/preparer`**, comme la décision 7 du lot 1 : la console des tests de navigateur sert l'exemple par oubli et n'a pas WeasyPrint. La simulation écrit en base ce que la route écrirait (le statut, `dossier_chemin`). Le chemin réel, texte collé compris, est testé en Python sur la configuration de l'exemple (tâche 3).
11. **La fiche « Je postule » avec dossier** porte « Je l'ai envoyée » et « Dossier prêt › ». Le lien du paquet et « Régénérer le dossier » la quittent : les pièces sont sur « Dossier prêt », et l'on régénère en changeant le destinataire. Les anciens écrans (« Toutes les offres ») gardent « Générer le dossier » et `api_dossier` jusqu'au lot 3.
12. **Une PR d'implémentation**, `feat/parcours-lot2`, un commit au moins par tâche, qui dit « Partie de #14 ». La session la fusionne une fois tout vert (mode `session`).

## Contraintes globales

- Aucune migration, aucune colonne, aucune variable `VEILLE_*` nouvelle (invariant 6). L'image `0.2.1` doit lire la base telle que ce lot l'écrit.
- `preparation.py` n'appelle que l'existant, sans le changer : `enrichissement`, `completude`, `dossier`, `lettre`, `rendu`, `etats`, `db`.
- Invariant 2 : un texte fourni est enregistré avant toute génération, et une génération en échec ne le perd pas.
- Invariant 4 : ce que remplace une régénération, la lettre affinée comprise, entre d'abord dans l'historique.
- Le dépôt est public : toute donnée de test est inventée, avec des liens en `.exemple.invalid` (M-0001).
- **Les fins de ligne ne se normalisent pas (invariant 7).** Restent en CRLF : `src/veille/static/app.js`, `src/veille/static/style.css`, `README.md`, `docs/CANDIDATURE.md`. Restent en LF : `src/veille/app.py`, `pyproject.toml`, `.github/workflows/ci.yml`, `CLAUDE.md`, `docs/FONCTIONNEMENT.md`, `tests_navigateur/test_parcours_candidature.py`. Un fichier neuf est en LF. `tests/test_javascript.py` mêle les deux : on ne le modifie pas, et un test de JavaScript neuf va dans un fichier neuf. Sous Git Bash, jamais `sed -i` sur un fichier CRLF : un remplacement se fait par l'outil Edit, ou en Python en binaire. Avant chaque commit, pour chaque fichier touché : `python -I -c "import sys;b=open(sys.argv[1],'rb').read();print(b.count(b'\r\n'), b.count(b'\n'))" <fichier>` rend deux nombres égaux (CRLF) ou un zéro en premier (LF), comme avant.
- Le JavaScript : toute donnée d'offre passe par `echapper()` ; toute route appelée existe (`tests/test_javascript.py`) ; `node --check src/veille/static/app.js` passe.
- Au téléphone (390 × 844) : toute cible fait au moins 44 px de haut (`DOIGT`), et aucune vue ne défile de côté.
- Le test s'écrit d'abord, et il échoue. La suite du poste : `.venv\Scripts\python -m pytest -q -p no:cacheprovider` (des sauts attendus sous Windows) ; celle du navigateur : `.venv\Scripts\python -m pytest -q -p no:cacheprovider tests_navigateur`. Une suite lourde à la fois, au premier plan.
- Les commits : Conventional Commits, en français, en-tête de 100 caractères au plus, `git add` par chemins, message par fichier (`git commit -F`), les deux lignes d'attribution en pied. Jamais `--no-verify`.

## Points d'attention de la revue

Ce que l'ADR implique sans qu'un critère le nomme, du plus probable au moins probable. Chacun a son test dans la tâche qui possède le code.

1. **Le destinataire trouvé le lendemain** : la régénération crée un autre dossier daté, et l'historique de la lettre doit le suivre (tâche 2, `test_regenerer_un_autre_jour_emporte_l_historique`).
2. **Le destinataire ajouté après « Générer quand même »** : la régénération ne redemande pas `mince` (tâche 2, `test_regenerer_ne_redemande_ni_texte_ni_completude`).
3. **Une pièce envoyée seule** dans un formulaire en ligne : elle porte le nom qu'elle a dans le zip, jamais `cv.fr.pdf` (tâche 3, `test_une_piece_se_telecharge_sous_son_nom_d_envoi`).
4. **Un double toucher, ou deux onglets** : une seule préparation tourne (tâche 3, `test_deux_preparations_de_la_meme_offre_ne_se_chevauchent_pas` ; tâche 4, `test_je_postule_lance_la_preparation_et_montre_le_temps`).
5. **Une description courte qui n'est pas un extrait** : `mince` permet de coller le texte, pas seulement de forcer (tâche 4, `test_mince_propose_de_coller_le_texte_ou_de_generer`).

---

### Tâche 1 : la préparation et ses étapes

**Fichiers :**
- Créer : `src/veille/preparation.py`, `tests/test_preparation.py`
- Modifier : `pyproject.toml`, `.github/workflows/ci.yml`

**Interfaces :**
- Consomme : les mécanismes annoncés de `enrichissement`, `completude`, `dossier`, `rendu`, `etats` et `db`.
- Produit, dans `src/veille/preparation.py` :
  - `ETAPES: tuple[str, ...] = ("texte", "mince", "pret", "echec")` ;
  - `STATUTS_A_PRENDRE: tuple[str, ...] = ("nouveau", "a_traiter", "differee")` et `ETATS_PREPARABLES: tuple[str, ...] = ("a_voir", "mise_de_cote", "je_postule")` ;
  - `MANQUES_MONTRES = 3` ;
  - `class OffreInconnue(LookupError)` et `class EtatIncompatible(ValueError)` ;
  - `@dataclass class Etape` : `etape: str`, `message: str = ""`, `url: str = ""`, `manques: list[dict] = []`, `completude: dict | None = None`, `dossier: dict | None = None`, `genere: bool = False`, `avertissements: list[str] = []`, `kit_provisoire: bool = False`, et `as_dict() -> dict[str, Any]`, qui rend toujours ces neuf clés ;
  - `preparer(offre_id: int, texte: str | None = None, forcer: bool = False, regenerer: bool = False) -> Etape` ;
  - `dossier_pret(offre: Mapping[str, Any]) -> dict[str, Any] | None`, qui rend `None` sans dossier sur le disque, sinon `{"nom": str, "pieces": [{"nom": <nom d'envoi>, "fichier": <nom sur le disque>}], "archive": bool, "destinataire": {"civilite": str, "nom": str, "adresse": str, "reference": str}, "annonce": str}`, les pièces triées par nom d'envoi.
  - `Etape.url` porte toujours l'adresse de l'annonce, `url_canonique` sinon `url`. `pret` porte `dossier = dossier_pret(offre)` et `completude` ; `mince` porte `completude` et les `MANQUES_MONTRES` premiers manques (`Manque.as_dict()`).

- [ ] **Étape 1 : écrire les tests qui échouent**, dans `tests/test_preparation.py`, sur une base neuve par test (comme `_base_propre` de `tests/test_parcours_api.py`), `dossier.CHEMIN_DOSSIERS` sous `tmp_path`, et de faux voisins posés par `monkeypatch` sur `preparation.enrichissement.politique`, `.verifier_cadence`, `.recuperer`, `preparation.completude.evaluer` et `preparation.dossier.generer`. Le faux `generer` écrit un dossier (une lettre, une pièce PDF, le paquet d'envoi) et rend un objet aux champs de `ResultatDossier`. `appliquer_texte` reste le vrai. Les tests et ce qu'ils vérifient :
  - `test_un_texte_complet_mene_au_dossier_pret` : offre `nouveau` complète, bilan suffisant → `etape == "pret"`, `genere` vrai, `generer` appelé une fois, `politique` jamais, statut `interessante`, `dossier_chemin` posé, et les événements `statut:interessante` puis `dossier_genere` (détail : le gabarit) au journal ;
  - `test_un_extrait_d_une_source_autorisee_est_lu_puis_pret` : `donnees_partielles` vrai, source autorisée, cadence libre, un texte inventé de 400 caractères lu → la description en base est ce texte, `donnees_partielles` faux, `pret` ;
  - `test_une_source_interdite_mene_a_l_etape_texte` : `etape == "texte"`, `message == "raison inventée"` (la `raison` de la politique), `url` égale à l'adresse de l'offre ; ni `recuperer` ni `generer` appelés ; statut `interessante` ;
  - `test_une_cadence_depassee_mene_a_l_etape_texte` : `message` est celui de `verifier_cadence`, `recuperer` jamais appelé ;
  - `test_une_lecture_en_echec_mene_a_l_etape_texte` : `recuperer` rend `("", "lecture inventée en échec")` → `texte`, ce message ;
  - `test_un_texte_lu_trop_court_mene_a_l_etape_texte` : `recuperer` rend 20 caractères → `texte`, `message` égal à celui du `Rapport`, description inchangée ;
  - `test_un_texte_fourni_est_enregistre_avant_la_generation` : `texte` de 400 caractères fourni, `generer` lève `RuntimeError("panne inventée")` → `etape == "echec"`, `message == "panne inventée"`, la description est le texte, statut `interessante`, `dossier_chemin` vide, `politique` jamais appelée ;
  - `test_un_echec_sans_message_nomme_l_exception` : `RuntimeError()` → `message == "RuntimeError"` ;
  - `test_un_texte_fourni_trop_court_mene_a_l_etape_texte` : `texte="trop court"` → `texte`, message du `Rapport`, `generer` jamais appelé ;
  - `test_une_completude_mince_mene_a_l_etape_mince` : bilan à 40 avec quatre manques (35, 20, 10, 5 points) → `mince`, `manques` égale aux trois premiers en dictionnaires, dans l'ordre, `completude == bilan.as_dict()`, `generer` jamais appelé ;
  - `test_forcer_genere_malgre_une_completude_mince` : le même avec `forcer=True` → `pret` ;
  - `test_chaque_statut_a_prendre_passe_en_interessante`, paramétré sur `STATUTS_A_PRENDRE` ; et `test_une_offre_deja_interessante_ne_change_pas_de_statut` : aucun nouvel événement `statut:` au journal ;
  - `test_seuls_les_etats_preparables_se_preparent`, paramétré sur chaque statut de `models.STATUTS` : `EtatIncompatible` levée si et seulement si `etats.etat_de` n'est pas dans `ETATS_PREPARABLES`, et alors ni statut ni journal ne changent ;
  - `test_une_offre_inconnue_leve` : `OffreInconnue` ;
  - `test_l_etape_rend_toujours_ses_neuf_cles` ;
  - `test_le_dossier_pret_liste_les_pieces_du_paquet_d_envoi` : un dossier avec `cv.fr.pdf`, la lettre en PDF, `fiche-offre.md`, un `notes-inventees.pdf` absent du paquet, et `<prefixe>-candidature.zip` qui porte les deux premiers sous leur nom d'envoi → `pieces == [{"nom": rendu.nom_pour_envoi(f), "fichier": f}, …]` pour ces deux seulement, triées par nom ; `archive` vrai ;
  - `test_sans_paquet_d_envoi_le_dossier_pret_n_a_aucune_piece` : `pieces == []`, `archive` faux ;
  - `test_le_dossier_pret_dit_a_qui_la_lettre_est_adressee` : les quatre champs de l'offre dans `destinataire`, ou des chaînes vides ;
  - `test_sans_dossier_sur_le_disque_le_dossier_pret_est_none`.
- [ ] **Étape 2 : les lancer.** `.venv\Scripts\python -m pytest -q -p no:cacheprovider tests/test_preparation.py`. Attendu : `ModuleNotFoundError: veille.preparation`.
- [ ] **Étape 3 : écrire `preparation.py`.** `preparer`, dans cet ordre : lire l'offre (`OffreInconnue`) et son état (`EtatIncompatible`) ; passer en `interessante` un statut de `STATUTS_A_PRENDRE` (`db.changer_statut`) ; enregistrer un `texte` fourni (`appliquer_texte(offre_id, texte, "colle a la main")`), un refus rendant `texte` avec le message du `Rapport` ; relire l'offre ; si `donnees_partielles` : `politique`, puis `verifier_cadence`, puis `recuperer`, puis `appliquer_texte(…, f"recupere sur {domaine}")`, le premier refus rendant `texte` ; si la complétude est insuffisante et `forcer` faux : `mince` ; sinon `dossier.generer`, une exception rendant `echec` avec `str(e) or type(e).__name__`, puis `db.maj_champs(dossier_chemin=…)`, `db.journaliser(offre_id, "dossier_genere", gabarit)` et `pret`. `dossier_pret` lit la liste du paquet d'envoi par `zipfile.ZipFile(...).namelist()`, et garde les fichiers du dossier dont `rendu.nom_pour_envoi` y figure. Les lignes de journal (`log.…`), et elles seules, portent `# pragma: no mutate`.
- [ ] **Étape 4 : les relancer.** Attendu : tous verts.
- [ ] **Étape 5 : la mutation.** Dans `pyproject.toml`, `only_mutate = ["src/veille/etats.py", "src/veille/preparation.py"]` et `pytest_add_cli_args_test_selection = ["tests/test_etats.py", "tests/test_preparation.py"]`, et le commentaire du bloc à jour. Dans `.github/workflows/ci.yml`, l'étape `Mutation de src/veille/etats.py` devient `Mutation des états et de la préparation`, et l'étape `Parcours de connexion` du job `navigateur` devient `Parcours de connexion et de candidature` (point reporté 2). mutmut ne tourne pas sous Windows : le job se lit en CI, à la tâche 6.
- [ ] **Étape 6 : commit.** `git add src/veille/preparation.py tests/test_preparation.py pyproject.toml .github/workflows/ci.yml`, puis `git commit -F <fichier>` : `feat(preparation): préparer une candidature, de « Je postule » au dossier prêt`.
- [ ] **Étape 7 : la revue de la tâche**, par un relecteur neuf, sur le diff de la tâche, avec ce plan et l'ADR-0003, § 5. Ses corrections sont relues avant la tâche 2.

### Tâche 2 : régénérer sans rien perdre

**Fichiers :**
- Modifier : `src/veille/preparation.py`, `tests/test_preparation.py`

**Interfaces :**
- Consomme : `preparer`, `dossier_pret` et les faux voisins (tâche 1) ; `lettre.historiser`, `lettre.versions`, `lettre.texte_de_version`, `lettre.NOM_HISTORIQUE`, `dossier.chemin_du_dossier`.
- Produit : `ETIQUETTE_REGENERATION = "avant-regeneration"`, et le comportement de `preparer` sur un dossier existant (décisions 4 à 6). `preparer(regenerer=True)` journalise `dossier_regenere` (détail : le gabarit) au lieu de `dossier_genere`.

- [ ] **Étape 1 : écrire les tests qui échouent.** Le faux `generer` reçoit en paramètre le nom du dossier qu'il crée, pour simuler un autre jour.
  - `test_sans_regenerer_un_dossier_existant_est_rendu_sans_generer` : dossier présent → `pret`, `genere` faux, `generer` jamais appelé ; puis `dossier_chemin` vers un dossier absent → `generer` appelé, `genere` vrai ;
  - `test_regenerer_le_meme_jour_historise_la_lettre_remplacee` : la lettre « Lettre affinée inventée » dans le dossier D, le faux `generer` y écrit « Lettre régénérée inventée » → la dernière version de D porte l'étiquette `avant-regeneration` et le texte « Lettre affinée inventée », la lettre courante est la régénérée, `dossier_regenere` au journal ;
  - `test_regenerer_un_autre_jour_emporte_l_historique` : D a une version `001-…-assemblee.md` et la lettre affinée ; le faux `generer` crée E → les noms de `lettre.historique/` de E sont ceux de D (`001-…-assemblee.md`, `002-…-avant-regeneration.md`), la version 2 de E porte la lettre affinée, D garde sa lettre, et `dossier_chemin` nomme E ;
  - `test_un_historique_deja_present_n_est_pas_ecrase` : E a déjà un `lettre.historique/` → il reste tel quel ;
  - `test_regenerer_sans_lettre_genere_quand_meme` : D sans lettre → `pret`, aucune version ;
  - `test_regenerer_ne_redemande_ni_texte_ni_completude` : `donnees_partielles` vrai et bilan à 30, `regenerer=True` → `pret`, `politique` jamais appelée ; `evaluer` peut l'être, pour remplir `completude` ;
  - `test_une_regeneration_en_echec_garde_l_ancien_dossier` : `generer` lève → `echec`, `dossier_chemin` inchangé, la lettre de D intacte et historisée.
- [ ] **Étape 2 : les lancer.** Attendu : tous échouent, sauf `test_regenerer_sans_lettre_genere_quand_meme`, que la tâche 1 fait déjà passer.
- [ ] **Étape 3 : l'écrire.** Après l'enregistrement du texte : sans `regenerer`, un dossier présent (`chemin_du_dossier(offre)` existe) rend `pret` aussitôt, `genere` faux. Avec `regenerer`, sauter la lecture et la complétude, `lettre.historiser(ancien, ETIQUETTE_REGENERATION)` si l'ancien dossier existe, générer, puis, si le nouveau dossier diffère de l'ancien et n'a pas de `lettre.historique/`, copier celui de l'ancien (`shutil.copytree`, sans `dirs_exist_ok`).
- [ ] **Étape 4 : relancer** `tests/test_preparation.py`. Attendu : tous verts.
- [ ] **Étape 5 : commit.** `git add src/veille/preparation.py tests/test_preparation.py`, puis `git commit -F <fichier>` : `feat(preparation): régénérer sans rien perdre, l'historique de la lettre compris`.
- [ ] **Étape 6 : la revue de la tâche**, par un relecteur neuf, avec l'invariant 4 du projet. Ses corrections sont relues avant la tâche 3.

### Tâche 3 : les routes

**Fichiers :**
- Modifier : `src/veille/app.py`
- Créer : `tests/test_preparation_api.py`

**Interfaces :**
- Consomme : `preparation.preparer`, `OffreInconnue`, `EtatIncompatible`, `Etape.as_dict()` (tâches 1 et 2) ; `_refus_sans_configuration_hors_conteneur`, `_erreur`.
- Produit :
  - `class DemandePreparation(BaseModel)` : `texte: str | None = None`, `forcer: bool = False`, `regenerer: bool = False` ;
  - `POST /api/offres/{offre_id}/preparer`, qui rend `Etape.as_dict()`, 404 sur une offre inconnue, 409 `etat_incompatible`, 409 `preparation_en_cours` (décision 8) ou 409 `configuration_non_designee` (décision 9) ;
  - `GET /api/offres/{offre_id}/dossier/{nom_fichier}?pour_envoi=true`, qui sert la pièce sous `rendu.nom_pour_envoi(nom)`. Sans le paramètre, rien ne change.

- [ ] **Étape 1 : écrire les tests qui échouent**, sur la configuration de l'exemple que désigne `tests/conftest.py`, avec les vrais voisins sauf mention :
  - `test_preparer_exige_la_session` ;
  - `test_preparer_rend_le_dossier_pret` : une offre inventée, description de 400 caractères, `forcer=True` → `etape == "pret"`, `genere` vrai, `dossier.nom` non vide, `dossier_chemin` posé ;
  - `test_le_texte_colle_d_un_extrait_mene_au_dossier_pret` : une offre `donnees_partielles` d'adresse `https://offres.exemple.invalid/…` → `etape == "texte"` et `url` ; puis avec `texte` (400 caractères inventés) et `forcer=True` → `pret`, et la description en base est le texte ;
  - `test_preparer_une_offre_inconnue_rend_404` et `test_preparer_une_offre_envoyee_rend_409` (`{"erreur": "etat_incompatible"}`) ;
  - `test_deux_preparations_de_la_meme_offre_ne_se_chevauchent_pas` : un faux `preparer` qui attend un `threading.Event` ; un premier appel lancé d'un fil, puis un second → 409 `preparation_en_cours` ; l'événement libéré, le premier rend 200, et un troisième passe ;
  - `test_la_garde_se_libere_apres_une_erreur` : un faux `preparer` qui lève `EtatIncompatible`, puis un appel suivant passe ;
  - `test_preparer_refuse_sans_configuration_designee` : `app._sert_l_exemple_par_oubli` forcé à vrai → 409 `configuration_non_designee`, statut inchangé ;
  - `test_une_piece_se_telecharge_sous_son_nom_d_envoi` : après `pret`, `GET …/dossier/<fichier>?pour_envoi=true` → le nom lu dans `Content-Disposition` (`email.message.Message.get_filename`) est `rendu.nom_pour_envoi(fichier)` ; `test_sans_pour_envoi_une_piece_garde_son_nom` : le nom sur le disque.
- [ ] **Étape 2 : les lancer.** Attendu : 404 ou 405 sur `/preparer`, et le nom du disque sur `?pour_envoi=true`.
- [ ] **Étape 3 : les écrire** dans `app.py`, près des routes du dossier. La garde : un `set` des offres en préparation sous un `threading.Lock`, l'offre retirée dans un `finally`.
- [ ] **Étape 4 : relancer** `tests/test_preparation_api.py`, puis la suite du poste. Attendu : tous verts, les sauts attendus sous Windows.
- [ ] **Étape 5 : commit.** `git add src/veille/app.py tests/test_preparation_api.py`, puis `git commit -F <fichier>` : `feat(api): la route de la préparation, et les pièces sous leur nom d'envoi`.
- [ ] **Étape 6 : la revue de la tâche**, par un relecteur neuf. Ses corrections sont relues avant la tâche 4.

### Tâche 4 : l'interface, de « Je postule » au « Dossier prêt »

**Fichiers :**
- Modifier : `src/veille/static/app.js` (CRLF), `src/veille/static/style.css` (CRLF) s'il le faut, `tests_navigateur/test_parcours_candidature.py`

**Interfaces :**
- Consomme : `POST /api/offres/{id}/preparer`, `GET …/dossier/{fichier}?pour_envoi=true` (tâche 3) ; `blocDestinataire`, `brancherDestinataire`, `blocAffinement`, `brancherAffinement`, `demanderCanal`, `rafraichir`.
- Produit, dans `app.js` :
  - `preparerCandidature(id, bouton, options = {})`, `options` parmi `{texte, forcer, regenerer}` : le bouton désactivé, son texte `Préparation… N s` mis à jour chaque seconde, rendu tel quel à la fin s'il est encore dans la page ; puis l'écran de l'étape, et `rafraichir()` ;
  - `afficherEtapeTexte(id, r)`, `afficherEtapeMince(id, r)`, `afficherEtapeEchec(id, r, options)`, `afficherDossierPret(id, r)`, chacune dans `#fenetre` ;
  - `brancherDestinataire(id, apres)` : `apres`, facultatif, est appelé après l'enregistrement ; la vue détaillée l'appelle toujours sans lui ;
  - `ERREURS_API.etat_incompatible` et `ERREURS_API.preparation_en_cours`, chacun une phrase.
- Les gestes : `data-action="postuler"` (la carte « À voir » et la fiche) et `data-action="preparer"` (la fiche « Je postule ») appellent `preparerCandidature`. La fiche « Je postule » sans dossier porte « Préparer ma candidature » ; avec, « Je l'ai envoyée » et « Dossier prêt › » (décision 11). Les anciens écrans gardent `data-action="dossier"`.
- Les écrans :
  - `texte` : le titre « Il manque le texte de l'annonce », le message, « Ouvrir l'annonce › » (`target="_blank" rel="noopener noreferrer"`), une zone de texte, et « Préparer avec ce texte », qui ne part pas sur une zone vide ;
  - `mince` : le score et le seuil, les manques et leur `quoi_faire`, « Générer quand même » (`forcer`) et « Coller le texte de l'annonce », qui ouvre l'écran `texte` ;
  - `echec` : la cause, et « Réessayer », avec les mêmes options ;
  - `pret` : « Dossier prêt » ; l'avertissement du kit provisoire et les avertissements, s'il y en a ; « Adressée à » et le destinataire, ou une phrase qui dit qu'aucun n'est enregistré et qu'il apparaîtra en rouge dans le PDF ; chaque pièce, un lien `download` vers `?pour_envoi=true` ; « Tout en un zip », si le paquet existe ; « Voir l'annonce › » ; puis « Je l'ai envoyée » (`demanderCanal`), « Ajouter un destinataire » (ou « Modifier le destinataire »), qui montre `blocDestinataire` avec « Enregistrer et régénérer », puis `preparerCandidature(id, bouton, {regenerer: true})`, et « Affiner la lettre », qui montre `blocAffinement` sans rien régénérer (point reporté 4).

- [ ] **Étape 1 : écrire les tests qui échouent**, dans `tests_navigateur/test_parcours_candidature.py`. Une aide, `_simuler_preparation(page, offre_id, reponses) -> list[dict]`, route `**/api/offres/{offre_id}/preparer`, sert les réponses dans l'ordre, rend la liste des corps reçus, et écrit en base ce que la route écrirait : `interessante` pour un statut de `STATUTS_A_PRENDRE`, `dossier_chemin` sur `pret` (décision 10). `FICHES` reçoit une offre par test qui change un statut. Les tests :
  - `test_je_postule_lance_la_preparation_et_montre_le_temps` : la requête retenue, le bouton est désactivé et son texte répond à `\d+ s` ; servie (`texte`), l'écran `texte` s'ouvre ;
  - `test_le_texte_colle_mene_au_dossier_pret_puis_a_l_envoi` (ADR-0003, § 7) : la carte « À voir », « Je postule », l'écran `texte` (le message, le lien de l'annonce), un texte collé, « Préparer avec ce texte » → le second corps porte ce `texte` ; « Dossier prêt » montre deux pièces dont les liens finissent par `?pour_envoi=true` et portent `download`, le zip, « Adressée à » et le lien de l'annonce ; « Je l'ai envoyée », « LinkedIn » → statut `candidature_envoyee` ;
  - `test_un_texte_vide_ne_part_pas` : une seule requête ;
  - `test_mince_propose_de_coller_le_texte_ou_de_generer` : « Générer quand même » envoie `{"forcer": true}` ; « Coller le texte de l'annonce » montre la zone de texte ;
  - `test_un_echec_propose_de_reessayer` : la cause affichée ; « Réessayer » renvoie les mêmes options ; la fiche dit toujours « Je postule » ;
  - `test_ajouter_un_destinataire_enregistre_puis_regenere` : `POST /api/offres/{id}` avec `contact_nom`, puis `/preparer` avec `{"regenerer": true}`, dans cet ordre ;
  - `test_affiner_la_lettre_ne_regenere_pas` : « Affiner la lettre » montre « Proposer une version affinée » ou « Affinement indisponible », et aucune requête `/preparer` ne part ;
  - `test_la_fiche_je_postule_avec_dossier_mene_au_dossier_pret` : la ligne d'actions porte « Je l'ai envoyée » et « Dossier prêt › », ni lien de paquet ni « Régénérer » ;
  - `test_dossier_pret_se_touche_du_doigt_et_tient_dans_l_ecran` : chaque lien et bouton fait au moins `DOIGT`, et `scrollWidth` reste dans les 390 px.
  - Les tests du lot 1 qui passaient par l'ancien geste suivent : `test_le_parcours_de_la_file_a_l_entretien` simule `/preparer`, `test_generer_le_dossier_recharge_a_finir` devient `test_preparer_recharge_a_finir`, et `test_chaque_etat_a_sa_ligne_d_actions` attend les lignes de la décision 11.
  - Point reporté 1 : dans `test_non_nomme_l_offre_et_ecarte_la_bonne`, `fenetre.get_by_role("button", name="motif inventé de la première")` devient `fenetre.locator('[data-motif="motif inventé de la première"]')`. Le vérifier par un mutant : l'assertion retournée (`to_have_count(1)`) doit échouer.
- [ ] **Étape 2 : les lancer.** `.venv\Scripts\python -m pytest -q -p no:cacheprovider tests_navigateur`. Attendu : les tests neufs échouent ; les autres passent.
- [ ] **Étape 3 : écrire l'interface.** Le minuteur reprend la forme de `brancherAffinement`. Chaque donnée de la réponse passe par `echapper()`, les noms de fichier dans une adresse par `encodeURIComponent`.
- [ ] **Étape 4 : relancer** les tests du navigateur, `node --check src/veille/static/app.js`, et `tests/test_javascript.py`. Attendu : tous verts. `app.js` et `style.css` restent en CRLF.
- [ ] **Étape 5 : commit.** `git add src/veille/static/app.js tests_navigateur/test_parcours_candidature.py` (et `src/veille/static/style.css` s'il a changé), puis `git commit -F <fichier>` : `feat(console): « Je postule » prépare la candidature, et l'écran « Dossier prêt »`.
- [ ] **Étape 6 : la revue de la tâche**, par un relecteur neuf, avec l'ADR-0003, §§ 4 et 5. Ses corrections sont relues avant la tâche 5.

### Tâche 5 : la documentation et les points reportés

**Fichiers :**
- Modifier : `docs/CANDIDATURE.md` (CRLF), `README.md` (CRLF), `docs/FONCTIONNEMENT.md`, `CLAUDE.md`

- [ ] **Étape 1 : chercher chaque mention de l'ancien geste.** L'outil Grep sur `docs/`, `README.md` et `CLAUDE.md`, motif `Générer le dossier|Generer le dossier|Régénérer|lot 2`.
- [ ] **Étape 2 : réécrire.**
  - `docs/CANDIDATURE.md` : le titre et la section « Ce que « Générer le dossier » produit » parlent de « Préparer ma candidature » : ses étapes (le texte, l'information trop mince, le dossier prêt), « Dossier prêt » (les pièces une à une sous leur nom d'envoi, le zip), le destinataire jamais demandé avant, et la régénération qui historise la lettre remplacée. Le reste du document ne change pas.
  - `README.md` : la ligne de `docs/CANDIDATURE.md` nomme « Préparer ma candidature ».
  - `docs/FONCTIONNEMENT.md` : le paragraphe de la fiche dit ce que fait « Je postule » depuis ce lot ; et les trois retouches reportées (point 3) : « Autres actions » sans guillemets imbriqués ; « jusqu'au lot 3 de l'ADR-0003 » dit en clair (ces écrans attendent leur refonte) ; la cellule « À faire » ramenée à une phrase courte, le détail passant dans le paragraphe qui suit le tableau.
  - `CLAUDE.md`, section « État » : une phrase sur `preparation.py` et la route, et l'écran « Dossier prêt ».
- [ ] **Étape 3 : vérifier.** `python -X utf8 -B scripts/modele/documentation.py` rend 0 ; les fins de ligne sont inchangées.
- [ ] **Étape 4 : commit.** `git add docs/CANDIDATURE.md README.md docs/FONCTIONNEMENT.md CLAUDE.md`, puis `git commit -F <fichier>` : `docs: « Préparer ma candidature » (lot 2 de l'ADR-0003)`.
- [ ] **Étape 5 : la revue de la tâche**, par un relecteur neuf, qui cherche aussi les mots retirés (« Générer le dossier », « Régénérer ») dans tout le dépôt. Ses corrections sont relues avant la PR.

### Tâche 6 : la PR, la revue finale et le staging

- [ ] **Étape 1 : la PR d'implémentation.** `git push -u origin feat/parcours-lot2`, puis `gh pr create --base principal --body-file <fichier>`, un titre de 93 caractères au plus, « Partie de #14 », la section « Écarts à la spec » (la décision 3, avec l'accord d'Edouard s'il l'a donné), le corps fini avant la fin de la CI. Attendre tous les contrôles verts, `mutation` et `navigateur` compris. Le journal du job `mutation` liste des mutants `killed` de `preparation.py` ; chaque survivant appelle un test de plus dans `tests/test_preparation.py`.
- [ ] **Étape 2 : la revue finale**, par un relecteur neuf sur le modèle le plus capable, sur tout le diff du lot, avec l'ADR-0003, ce plan et le journal du job `mutation`.
- [ ] **Étape 3 : les corrections**, en une vague, puis leur relecture par un relecteur neuf, sur le diff des corrections. La session fusionne ensuite la PR : `gh pr merge <n> --squash --match-head-commit <sha>`, depuis le clone, sans `cd`.
- [ ] **Étape 4 : 👤 le staging, au téléphone.** Le staging se redéploie seul depuis `principal`. Ses offres factices ont des descriptions courtes : la plupart s'arrêtent à « Information trop mince ». Edouard vérifie :
  - sur une offre « À voir » : « Je postule » montre le temps qui passe, puis l'étape où la préparation s'arrête ;
  - « Coller le texte de l'annonce », un texte inventé de 400 caractères au moins, « Préparer avec ce texte » ; puis, s'il le faut, « Générer quand même » ;
  - « Dossier prêt » : une pièce téléchargée seule porte le nom qu'elle a dans le zip ; le zip se télécharge ;
  - « Ajouter un destinataire », un nom inventé, « Enregistrer et régénérer » : la lettre le porte ;
  - « Affiner la lettre » montre son bloc, ou dit pourquoi il est indisponible, sans régénérer ;
  - « Je l'ai envoyée » mène à « Envoyée » ;
  - la fiche « Je postule » d'une offre dont le dossier est prêt porte « Je l'ai envoyée » et « Dossier prêt › ».

### Tâche 7 : la clôture

- [ ] **Étape 1 : la PR de clôture.** Elle supprime ce plan, reporte dans `CLAUDE.md` ce qui doit survivre (l'état du lot 2, la ligne « Prochain »), relit le README d'après `docs/modele/documentation.md`, coche les critères de `veille-emploi#14`, porte « Closes #14 », la section « Écarts à la spec » et la ligne `Tête relue : <SHA>` de la tête qu'a lue sa dernière relecture.
- [ ] **Étape 2 : 👤 l'étiquette `v0.3.0`**, sur le commit de la clôture, posée par Edouard. Puis, depuis le poste, `/sante` de la prod rend `"version":"0.3.0"`, et `modele-version` a publié l'image `0.3.0`.

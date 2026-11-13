# Lot 2 du parcours (ADR-0003) : « Préparer ma candidature » — plan

> **Pour les agents :** compétence requise, *superpowers* `subagent-driven-development` (recommandée) ou `executing-plans`, tâche par tâche. Les étapes se cochent (`- [ ]`). Les étapes 👤 sont des gestes d'Edouard : la session les prépare et ne les lance pas.

**Objectif :** d'un toucher sur « Je postule », l'offre passe à son dossier, et la préparation ne s'arrête que sur ce qui manque : le texte de l'annonce, ou une information trop mince (issue `veille-emploi#14`).

**Architecture :** un module neuf, `src/veille/preparation.py`, enchaîne l'existant sans le changer (`enrichissement`, `completude`, `dossier`, `lettre`) et rend l'étape suivante. Une route, `POST /api/offres/{id}/preparer`, le sert. L'interface remplace, dans la file et dans la fiche, « Générer le dossier » par la préparation, et ajoute l'écran « Dossier prêt ». Les anciens écrans gardent leur bouton jusqu'au lot 3.

**Pile :** Python 3.13, FastAPI, SQLite ; JavaScript sans framework (`src/veille/static/app.js`) ; pytest ; Playwright (`tests_navigateur/`) ; mutmut 3.8.1 (CI Linux seulement).

**Spec :** `docs/decisions/0003-le-parcours-jusqu-a-la-candidature.md`, le Contexte (ce qu'est un extrait) et les §§ 4, 5, 7 et 8 pour la part du lot 2 ; les critères d'acceptation de `veille-emploi#14`, et les quatre points reportés de la revue du lot 1, commentés sur `veille-emploi#14`.

**Préalables :** un worktree `veille-emploi.worktrees\parcours-lot2`, sur une branche `feat/parcours-lot2` partie de `origin/principal` (`git worktree add --no-track`), avec son environnement : `python -m venv .venv`, puis `.venv\Scripts\python -m pip install -e .[dev,navigateur]`, puis `.venv\Scripts\python -m playwright install chromium`. `git rev-parse --git-path hooks` y rend `.githooks`.

## Mécanismes annoncés

- `src/veille/enrichissement.py:235` — `def politique` — rend une `Politique(autorise, domaine, raison, conseil)` ; passé la liste blanche, il lit le `robots.txt` du domaine (délai de 15 s, en cache 24 h)
- `src/veille/enrichissement.py:303` — `def verifier_cadence` — rend `(possible, message)` : la cadence de lecture automatique le permet-elle ?
- `src/veille/enrichissement.py:432` — `def recuperer` — rend `(texte, message)`, le texte vide quand la lecture échoue
- `src/veille/enrichissement.py:484` — `def appliquer_texte` — enregistre le texte complet (`enrichi_par` : son origine), met `donnees_partielles` à faux et rend un `Rapport(ok, message, …)` ; refuse sans rien écrire un texte sous `LONGUEUR_MIN`
- `src/veille/enrichissement.py:494` — `nettoyer_texte_detaille(texte)` — un texte vide fait lever le dépaquetage (`ValueError`) : `appliquer_texte` ne reçoit jamais de texte vide
- `src/veille/enrichissement.py:95` — `alerte_eliminatoire: str` — le `Rapport` dit quand le texte complet révèle un critère éliminatoire sur une offre qui était au-dessus du seuil
- `src/veille/db.py:442` — `automatique = statut == "nouveau"` — le texte enregistré peut écarter ou différer une offre dont le statut est automatique (`nouveau`, ou écartée et différée automatiquement), jamais une offre `interessante`
- `src/veille/enrichissement.py:325` — `LONGUEUR_MIN =` — le plancher de longueur d'un texte d'annonce, 150 caractères
- `src/veille/completude.py:104` — `def evaluer` — rend un `Bilan` dont les manques sont triés par points décroissants
- `src/veille/completude.py:33` — `SEUIL_DOSSIER = 55` — `suffisant_pour_dossier` vaut vrai à partir de ce score
- `src/veille/completude.py:57-84` — `class Bilan` — `Bilan(score, niveau, manques, acquis, suffisant_pour_dossier)` et `Manque(libelle, points, quoi_faire)`, chacun avec `as_dict()`
- `src/veille/dossier.py:667` — `def chemin_du_dossier` — le dossier de l'offre, retrouvé sous `CHEMIN_DOSSIERS` par le dernier segment de `dossier_chemin` ; `None` sans `dossier_chemin` ; ne vérifie pas que le dossier existe
- `src/veille/dossier.py:696` — `nom_dossier = f` — le dossier se nomme `<date du jour>_<employeur>_<titre>` : une génération du même jour réécrit le même dossier, celle d'un autre jour en crée un autre
- `src/veille/dossier.py:685` — `def generer` — réécrit `lettre-de-motivation.md` sans l'historiser, peut ne pas écrire de lettre, et rend `ResultatDossier(chemin, fichiers, gabarit_lettre, kit_provisoire, avertissements, pieces_envoi, …)`
- `src/veille/dossier.py:659` — `-candidature.zip` — le paquet d'envoi se nomme `<prefixe>-candidature.zip`, ses pièces sous leur nom d'envoi
- `src/veille/lettre.py:620` — `def historiser` — copie la lettre courante dans `lettre.historique/` sous `NNN-<horodatage>-<etiquette>.md`, et rend `None` sans lettre, sans créer le dossier d'historique
- `src/veille/lettre.py:607` — `def versions` — les versions de `lettre.historique/`, de la plus ancienne à la plus récente
- `src/veille/lettre.py:50` — `NOM_HISTORIQUE =` — le dossier d'historique s'appelle `lettre.historique`
- `src/veille/rendu.py:166` — `def nom_pour_envoi` — le nom qu'un recruteur voit : `cv.fr.pdf` devient `<Prefixe>-CV-France.pdf`, et tout nom qui contient « lettre » devient `<Prefixe>-Lettre-de-motivation.pdf`
- `src/veille/etats.py:34` — `def etat_de` — lit l'état d'une offre (`a_voir`, `mise_de_cote`, `je_postule`, `envoyee`, `entretien`, `close`) sur son statut
- `src/veille/db.py:350` — `def changer_statut` — écrit le statut et le journalise (`statut:<statut>`)
- `src/veille/db.py:342` — `def journaliser` — ajoute une ligne `(type, detail)` à l'historique de l'offre
- `src/veille/app.py:108` — `def _refus_sans_configuration_hors_conteneur` — rend un 409 `configuration_non_designee` quand la console sert l'exemple par oubli, `None` sinon
- `src/veille/app.py:737` — `def api_maj` — enregistre `contact_nom`, `contact_civilite`, `adresse_entreprise` et `reference_annonce` sur l'offre, une chaîne vide comprise
- `src/veille/app.py:804` — `def api_dossier` — l'ancien geste « Générer le dossier », que les anciens écrans gardent jusqu'au lot 3
- `src/veille/app.py:843` — `def api_archive` — sert le paquet d'envoi
- `src/veille/app.py:877` — `filename=cible.name` — une pièce téléchargée seule garde son nom sur le disque, pas son nom d'envoi
- `src/veille/static/app.js:33` — `const ERREURS_API` — traduit un code d'erreur de l'API en phrase
- `src/veille/static/app.js:761` — `function gesteNeuf` — désactive le bouton pendant un geste, et le réactive sur une erreur
- `src/veille/static/app.js:709` — `function demanderCanal` — le panneau « Je l'ai envoyée », qui demande le canal puis écrit `candidature_envoyee`
- `src/veille/static/app.js:1572` — `async function blocAffinement` — le bloc « Affiner la lettre », ou une ligne qui dit pourquoi l'affinement est indisponible
- `src/veille/static/app.js:1592` — `function brancherAffinement` — branche ce bloc ; montre le temps écoulé pendant l'appel
- `src/veille/static/app.js:1660` — `function blocDestinataire` — les trois champs du destinataire et la référence de l'annonce, préremplis par les champs de l'offre (`contact_nom`, `contact_civilite`, `adresse_entreprise`, `reference_annonce`) ; son bouton s'appelle « Enregistrer »
- `src/veille/static/app.js:1683` — `function brancherDestinataire` — propose la référence de l'annonce, puis enregistre toujours les quatre champs par `POST /api/offres/{id}`
- `src/veille/static/app.js:901` — `data-pour` — `remplirMotifs` ne remplit que la zone des motifs de l'offre nommée
- `src/veille/static/app.js:945` — `Générer le dossier</button>` — la fiche « Je postule » sans dossier propose encore l'ancien geste
- `src/veille/static/app.js:1437` — `a === 'postuler'` — « Je postule » écrit `interessante` puis ouvre la fiche, sans rien préparer
- `tests_navigateur/test_parcours_candidature.py:378` — `to_have_count(0)` — l'assertion inerte du lot 1 : `get_by_role` ne voit rien dans la fenêtre fermée
- `tests_navigateur/test_parcours_candidature.py:562-564` — `a[download]` — le lot 1 attend le lien du paquet dans la ligne d'actions de la fiche « Je postule » avec dossier
- `.github/workflows/ci.yml:108` — `Parcours de connexion` — l'étape du job `navigateur`, qui lance aussi le parcours de candidature
- `.github/workflows/ci.yml:72` — `Mutation de src/veille/etats.py` — l'étape du job `mutation`
- `pyproject.toml:53` — `only_mutate` — mutmut ne mute que `src/veille/etats.py`
- `pyproject.toml:54` — `pytest_add_cli_args_test_selection` — et ne lance que `tests/test_etats.py`

## Outils et cas limites

- mutmut 3.8.1 — il remplace aussi chaque argument d'un appel par `None` ou le retire, une fonction qu'aucun test de la sélection n'appelle donne des mutants « no tests », il ne mute pas les constantes du module, et le littéral d'un appel de journal donne un mutant qu'aucun test ne tue ; le job exige zéro mutant d'un autre statut que `killed` — le job `mutation` de la PR, lu dès la tâche 1 (PR en brouillon), avec `_verifier_etape` sur les neuf champs, des listes écrites en clair, et `# pragma: no mutate` sur les lignes de journal et sur un mutant équivalent prouvé, sa raison en commentaire (tâche 1)
- Playwright, `get_by_role` — ignore les éléments cachés : un `to_have_count(0)` dans une fenêtre fermée passe toujours — `test_non_nomme_l_offre_et_ecarte_la_bonne`, réécrit avec `locator('[data-motif=…]')`, éprouvé par un mutant du code qui retire la garde `data-pour` (tâche 4)
- Playwright, `page.route` — une requête retenue, puis servie plus tard par `fulfill`, reste en vol tant que le test ne la libère pas : c'est ce qui rend observables le bouton désactivé et son temps écoulé — `test_je_postule_lance_la_preparation_et_montre_le_temps` (tâche 4)
- Playwright, une assertion d'absence — compter les requêtes juste après un clic passe avant que la requête parte — `test_un_texte_vide_ne_part_pas` et `test_affiner_la_lettre_ne_regenere_pas` attendent d'abord le message ou le bloc (tâche 4)
- `zipfile.ZipFile` — un paquet absent lève `FileNotFoundError`, un paquet tronqué `BadZipFile`, et un `ZipFile` ouvert hors `with` peut garder le fichier ouvert sous Windows quand `generer` supprime les zips — `test_sans_paquet_d_envoi_le_dossier_pret_n_a_aucune_piece` et `test_un_paquet_tronque_vaut_un_paquet_absent` (tâche 1)
- `shutil.copytree` — lève si la cible existe, lève si la source n'existe pas, et avec `dirs_exist_ok` fusionne deux historiques dont les numéros se heurtent — `test_un_historique_deja_present_n_est_pas_ecrase` et `test_regenerer_un_autre_jour_sans_historique_dans_l_ancien` (tâche 2)
- `TestClient` de FastAPI — une route `def` tourne dans le pool de fils, si bien que deux appels lancés de deux fils se chevauchent vraiment ; mais si le second entre le premier dans un faux qui attend un événement, le test se bloque jusqu'au délai du job — `test_deux_preparations_de_la_meme_offre_ne_se_chevauchent_pas`, avec un événement « entré » et des attentes bornées (tâche 3)
- `FileResponse` de Starlette — un nom non ASCII part en `filename*=utf-8''…`, pas en `filename="…"` — `test_une_piece_se_telecharge_sous_son_nom_d_envoi`, avec un préfixe accentué inventé, qui lit le nom par `email.message.Message.get_filename` (tâche 3)

## Revues

- la revue de la tâche 1, par un relecteur neuf, avant la tâche 2 : Tâche 1
- la revue de la tâche 2, par un relecteur neuf, avant la tâche 3 : Tâche 2
- la revue de la tâche 3, par un relecteur neuf, avant la tâche 4 : Tâche 3
- la revue de la tâche 4, par un relecteur neuf, avant la tâche 5 : Tâche 4
- la revue de la tâche 5, par un relecteur neuf, avant la PR prête : Tâche 5
- la revue finale, sur tout le diff du lot, par un relecteur neuf sur le modèle le plus capable, avec la lecture des mutants survivants (ADR-0003, § 7) : Tâche 6
- la relecture des corrections de la revue finale, par un relecteur neuf : Tâche 6

## Les décisions du plan

Ce que l'ADR laisse ouvert, tranché ici. Les décisions 3, 4 et 11 sont des écarts à la lettre de l'ADR, que la PR déclare avec l'accord d'Edouard.

1. **Quatre étapes.** `preparer` rend `texte`, `mince` ou `pret`, comme l'ADR, ou `echec`, la cause d'une génération en échec, que la fiche propose de réessayer.
2. **Un extrait, c'est celui de l'ADR** (Contexte) : une description de moins de 400 caractères (`LONGUEUR_EXTRAIT = 400`), ou marquée `donnees_partielles`. Il passe par la lecture automatique, sinon par l'étape `texte`.
3. **Les statuts que « Je postule » prend :** `nouveau`, `a_traiter` et `differee` passent en `interessante`. Le § 5 ne nomme pas `differee`, mais la fiche d'une offre mise de côté propose « Je postule » depuis le lot 1 : sans lui, le geste n'y ferait rien. Une offre déjà `interessante` garde son statut. Toute offre d'un autre état (Envoyée, Entretien, Close) est refusée, sans rien écrire (`EtatIncompatible`, 409 `etat_incompatible`). Le statut s'écrit **avant** le texte : écrit après, un texte qui révèle un éliminatoire écarterait l'offre dont Edouard vient de dire « Je postule ».
4. **« Générer avec l'extrait ».** L'écran `texte` le propose : `forcer` saute alors la lecture du texte comme la complétude. Sans lui, une annonce dont on ne peut pas coller le texte (au téléphone, une annonce LinkedIn qui s'ouvre dans son application) n'aurait plus de chemin vers son dossier une fois l'ancien geste retiré, au lot 3. Le § 5 ne prévoit `forcer` qu'après `mince`.
5. **L'alerte éliminatoire se dit.** Quand le texte enregistré par la préparation la porte, `alerte_eliminatoire` est le premier des `avertissements` de l'étape rendue : l'offre reste « Je postule », et l'écran le montre.
6. **Un dossier existant est rendu, pas refait.** Sans `regenerer`, une offre dont le dossier existe sur le disque rend `pret` sans générer. « Dossier prêt › », depuis la fiche, passe par la même route : un double appel ne régénère jamais. Les avertissements et `kit_provisoire` ne valent qu'au passage qui génère.
7. **Régénérer ne redemande rien.** `regenerer=True` saute la lecture du texte et la complétude : le dossier a déjà été accepté une fois, peut-être par « Générer quand même ».
8. **Régénérer n'efface rien (invariant 4).** La lettre courante entre d'abord dans l'historique de son dossier, sous l'étiquette `avant-regeneration`. Si la génération crée un autre dossier (un autre jour), l'historique de l'ancien y est copié, s'il existe et si le nouveau n'en a pas. L'ancien dossier reste sur le disque, et `dossier_chemin` passe au nouveau.
9. **Une pièce seule porte son nom d'envoi.** `dossier_pret` liste les fichiers du dossier dont le nom d'envoi est dans le paquet d'envoi ; la route d'un fichier gagne `?pour_envoi=true`, qui le sert sous ce nom. Un formulaire en ligne reçoit les mêmes noms que le zip. Deux fichiers au même nom d'envoi sont signalés dans les avertissements.
10. **Une préparation à la fois par offre.** La route refuse une seconde préparation de la même offre tant que la première tourne (409 `preparation_en_cours`), en plus du bouton désactivé. Elle refuse aussi comme les autres gestes quand la console sert l'exemple par oubli (409 `configuration_non_designee`) ; « Je postule » aussi, puisqu'il lance la préparation.
11. **Le navigateur simule `/preparer`, sur des offres inventées par le test**, comme le lot 1 (sa décision 7), et non sur `factice/` : la console des tests de navigateur sert l'exemple par oubli, n'a pas WeasyPrint, et chaque test qui change un statut veut son offre. La simulation écrit en base ce que la route écrirait (le statut, `dossier_chemin`). Le chemin réel, texte collé compris, est testé en Python sur la configuration de l'exemple (tâche 3). Le § 7 dit « sur le jeu factice ».
12. **La fiche « Je postule » avec dossier** porte « Je l'ai envoyée » et « Dossier prêt › ». Le lien du paquet et « Régénérer le dossier » la quittent : les pièces sont sur « Dossier prêt », et l'on régénère en changeant le destinataire. « Dossier prêt » ne porte « Régénérer le dossier » que si le paquet d'envoi manque ou ne se lit pas (un dossier ancien, un paquet tronqué). Les anciens écrans (« Toutes les offres ») gardent « Générer le dossier » et `api_dossier` jusqu'au lot 3.
13. **Les adresses.** `politique` et `recuperer` reçoivent `url_canonique`, sinon `url`, comme `api_enrichir`. Le lien montré à Edouard, `Etape.url`, prend `url`, sinon `url_canonique`, comme la fiche ; vide, il n'est pas montré.
14. **Une PR d'implémentation**, `feat/parcours-lot2`, ouverte en brouillon dès la fin de la tâche 1 pour lire le job `mutation` à chaque envoi, et qui dit « Partie de #14 ». La session la passe prête après la tâche 5, et la fusionne une fois tout vert (mode `session`).

**Hors périmètre :** deux offres au même employeur et au même intitulé partagent un dossier le même jour, et la première génération de la seconde réécrit la lettre de la première sans l'historiser. Le défaut est celui de `generer`, d'avant ce lot : AM-4 au registre.

## Contraintes globales

- Aucune migration, aucune colonne, aucune variable `VEILLE_*` nouvelle (invariant 6). L'image `0.2.1` doit lire la base telle que ce lot l'écrit.
- `preparation.py` n'appelle que l'existant, sans le changer : `enrichissement`, `completude`, `dossier`, `lettre`, `rendu`, `etats`, `db`.
- Invariant 2 : un texte fourni est enregistré avant toute génération, et une génération en échec ne le perd pas.
- Invariant 4 : ce que remplace une régénération, la lettre affinée comprise, entre d'abord dans l'historique.
- Le dépôt est public : toute donnée de test est inventée, avec des liens en `.exemple.invalid` (M-0001).
- **Les fins de ligne ne se normalisent pas (invariant 7).** Restent en CRLF : `src/veille/static/app.js`, `src/veille/static/style.css`, `README.md`, `docs/CANDIDATURE.md`. Restent en LF : `src/veille/app.py`, `src/veille/completude.py`, `pyproject.toml`, `.github/workflows/ci.yml`, `CLAUDE.md`, `docs/FONCTIONNEMENT.md`, `docs/pistes.md`, `tests_navigateur/test_parcours_candidature.py`. Un fichier neuf est en LF. `tests/test_javascript.py` mêle les deux : on ne le modifie pas, et un test de JavaScript neuf va dans un fichier neuf. Sous Git Bash, jamais `sed -i` sur un fichier CRLF : un remplacement se fait par l'outil Edit, ou en Python en binaire. Avant chaque commit, pour chaque fichier touché : `python -I -c "import sys;b=open(sys.argv[1],'rb').read();print(b.count(b'\r\n'), b.count(b'\n'))" <fichier>` rend deux nombres égaux (CRLF) ou un zéro en premier (LF), comme avant.
- Le JavaScript : toute donnée d'offre passe par `echapper()`, un nom de fichier dans une adresse par `encodeURIComponent` ; toute route appelée existe (`tests/test_javascript.py`) ; `node --check src/veille/static/app.js` passe.
- Au téléphone (390 × 844) : toute cible fait au moins 44 px de haut (`DOIGT`), et aucune vue ne défile de côté.
- Le test s'écrit d'abord, et il échoue. La suite du poste : `.venv\Scripts\python -m pytest -q -p no:cacheprovider` (des sauts attendus sous Windows) ; celle du navigateur : `.venv\Scripts\python -m pytest -q -p no:cacheprovider tests_navigateur`. Une suite lourde à la fois, au premier plan.
- Les commits : Conventional Commits, en français, en-tête de 100 caractères au plus, `git add` par chemins, message par fichier (`git commit -F`), les deux lignes d'attribution en pied. Jamais `--no-verify`.

## Points d'attention de la revue

Ce que l'ADR implique sans qu'un critère le nomme, du plus probable au moins probable. Chacun a son test dans la tâche qui possède le code.

1. **Le destinataire trouvé le lendemain** : la régénération crée un autre dossier daté, et l'historique de la lettre doit le suivre, même quand l'ancien dossier n'en a pas (tâche 2, `test_regenerer_un_autre_jour_emporte_l_historique`, `test_regenerer_un_autre_jour_sans_historique_dans_l_ancien`).
2. **Modifier le seul nom du destinataire** : la formule d'appel, l'adresse et la référence restent (tâche 4, `test_ajouter_un_destinataire_enregistre_puis_regenere`).
3. **Une annonce LinkedIn dont le texte ne se copie pas** au téléphone : « Générer avec l'extrait » mène au dossier (tâche 1, `test_forcer_saute_aussi_l_etape_texte` ; tâche 4, `test_l_etape_texte_propose_de_generer_avec_l_extrait`).
4. **Une pièce envoyée seule** dans un formulaire en ligne : elle porte le nom qu'elle a dans le zip, jamais `cv.fr.pdf` (tâche 3, `test_une_piece_se_telecharge_sous_son_nom_d_envoi`).
5. **Un double toucher, ou deux onglets** : une seule préparation tourne (tâche 3, `test_deux_preparations_de_la_meme_offre_ne_se_chevauchent_pas` ; tâche 4, `test_je_postule_lance_la_preparation_et_montre_le_temps`).

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
  - `LONGUEUR_EXTRAIT = 400` et `MANQUES_MONTRES = 3` ;
  - `class OffreInconnue(LookupError)` et `class EtatIncompatible(ValueError)`, levées sans message ;
  - `@dataclass class Etape` : `etape: str`, `message: str = ""`, `url: str = ""`, `manques: list[dict[str, Any]] = field(default_factory=list)`, `completude: dict[str, Any] | None = None`, `dossier: dict[str, Any] | None = None`, `genere: bool = False`, `avertissements: list[str] = field(default_factory=list)`, `kit_provisoire: bool = False`, et `as_dict() -> dict[str, Any]`, qui rend toujours ces neuf clés ;
  - `preparer(offre_id: int, texte: str | None = None, forcer: bool = False, regenerer: bool = False) -> Etape` ; un `texte` vide ou blanc vaut `None` ;
  - `dossier_pret(offre: Mapping[str, Any]) -> dict[str, Any] | None`, qui rend `None` sans dossier sur le disque, sinon `{"nom": str, "pieces": [{"nom": <nom d'envoi>, "fichier": <nom sur le disque>}], "archive": bool, "destinataire": {"contact_nom": str, "contact_civilite": str, "adresse_entreprise": str, "reference_annonce": str}, "avertissements": list[str]}`, les pièces triées par nom d'envoi. `destinataire` porte les clés de l'offre, que `blocDestinataire` lit telles quelles (tâche 4).
  - `Etape.url` porte toujours le lien de l'annonce (décision 13). `pret` porte `dossier = dossier_pret(<l'offre relue après maj_champs>)` et `completude` ; `mince` porte `completude` et les `MANQUES_MONTRES` premiers manques (`Manque.as_dict()`).

- [ ] **Étape 1 : écrire les tests qui échouent**, dans `tests/test_preparation.py`, sur une base neuve par test (comme `_base_propre` de `tests/test_parcours_api.py`), `dossier.CHEMIN_DOSSIERS` sous `tmp_path`, et de faux voisins posés par `monkeypatch` sur `preparation.enrichissement.politique`, `.verifier_cadence`, `.recuperer`, `preparation.completude.evaluer` et `preparation.dossier.generer`. Le faux `generer` écrit un dossier (une lettre, `cv.fr.pdf`, le paquet d'envoi) et rend un objet aux champs de `ResultatDossier`, des avertissements et `kit_provisoire` inventés compris. `appliquer_texte` reste le vrai. Une aide, `_verifier_etape(e, **attendu)`, compare les neuf champs de l'étape, ceux qu'on ne nomme pas à leur valeur par défaut. Les offres inventées ont une `url` et une `url_canonique` différentes. Les tests et ce qu'ils vérifient :
  - `test_un_texte_complet_mene_au_dossier_pret` : offre `nouveau`, description de 400 caractères, bilan suffisant → `pret` ; `genere`, `completude`, `avertissements` et `kit_provisoire` égaux à ceux des faux ; `dossier["nom"]` est celui du dossier créé ; `dossier_chemin ==` son chemin ; `generer` appelé une fois, `politique` jamais ; statut `interessante` ; au journal, `statut:interessante` puis `dossier_genere` (détail : le gabarit) ;
  - `test_un_extrait_d_une_source_autorisee_est_lu_puis_pret` : `donnees_partielles` vrai, source autorisée, cadence libre, un texte inventé de 400 caractères lu → `politique` et `recuperer` reçoivent `url_canonique` ; la description en base est ce texte, `enrichi_par == "recupere sur <domaine inventé>"`, `donnees_partielles` faux ; `pret` ;
  - `test_une_description_courte_est_un_extrait` : `donnees_partielles` faux, description de 399 caractères → `politique` appelée ; à 400 caractères, jamais ;
  - `test_une_source_interdite_mene_a_l_etape_texte` : `texte`, `message == "raison inventée"` (la `raison` de la politique), `url` égale à `url` de l'offre ; ni `recuperer` ni `generer` appelés ; statut `interessante` ;
  - `test_une_cadence_depassee_mene_a_l_etape_texte` : `message` est celui de `verifier_cadence`, `recuperer` jamais appelé ;
  - `test_une_lecture_en_echec_mene_a_l_etape_texte` : `recuperer` rend `("", "lecture inventée en échec")` → `texte`, ce message ;
  - `test_un_texte_lu_trop_court_mene_a_l_etape_texte` : `recuperer` rend 20 caractères → `texte`, `message` égal à celui du `Rapport`, description inchangée ;
  - `test_un_texte_fourni_est_enregistre_avant_la_generation` : `texte` de 400 caractères fourni, `generer` lève `RuntimeError("panne inventée")` → `echec`, `message == "panne inventée"` ; la description est le texte, `enrichi_par == "colle a la main"` ; statut `interessante`, `dossier_chemin` vide, `politique` jamais appelée ;
  - `test_un_echec_sans_message_nomme_l_exception` : `RuntimeError()` → `message == "RuntimeError"` ;
  - `test_un_texte_fourni_trop_court_mene_a_l_etape_texte` : `texte="trop court"` → `texte`, message du `Rapport`, `generer` jamais appelé ;
  - `test_un_texte_vide_vaut_aucun_texte`, paramétré sur `""` et `"   "` : aucune exception, la description reste l'extrait, et la préparation suit son cours ;
  - `test_une_completude_mince_mene_a_l_etape_mince` : bilan à 40 avec quatre manques (35, 20, 10, 5 points) → `mince`, `manques` égale aux trois premiers en dictionnaires, dans l'ordre, `completude == bilan.as_dict()`, `generer` jamais appelé ;
  - `test_forcer_genere_malgre_une_completude_mince` : le même avec `forcer=True` → `pret` ;
  - `test_forcer_saute_aussi_l_etape_texte` : un extrait d'une source interdite, `forcer=True` → `pret`, ni `politique` ni `recuperer` appelés (décision 4) ;
  - `test_l_alerte_eliminatoire_du_texte_colle_se_dit` : une offre `nouveau` au-dessus du seuil, un texte fourni qui porte un éliminatoire inventé de `exemple/criteres.yaml` → statut `interessante` après la préparation (le statut s'écrit avant le texte), et l'alerte du `Rapport` est `avertissements[0]` ;
  - `test_les_statuts_a_prendre_passent_en_interessante`, paramétré sur la liste écrite en clair `("nouveau", "a_traiter", "differee")` ; et `test_une_offre_deja_interessante_ne_change_pas_de_statut` : aucun nouvel événement `statut:` au journal ;
  - `test_les_autres_etats_sont_refuses`, paramétré sur la liste écrite en clair `("candidature_envoyee", "relance_envoyee", "reponse_recue", "entretien", "refus", "accepte", "ecartee")` : `EtatIncompatible`, ni statut ni journal changés ; et `test_les_listes_font_le_tour_des_statuts` : les trois statuts à prendre, `interessante` et ces sept font exactement `models.STATUTS`. Éprouvé à la main : retirer `differee` de `STATUTS_A_PRENDRE` fait échouer un test ;
  - `test_une_offre_inconnue_leve` : `OffreInconnue` ;
  - `test_l_etape_rend_toujours_ses_neuf_cles` ;
  - `test_le_dossier_pret_liste_les_pieces_du_paquet_d_envoi` : un dossier avec `cv.fr.pdf`, la lettre en PDF, `fiche-offre.md`, un `notes-inventees.pdf` absent du paquet, et `<prefixe>-candidature.zip` qui porte les deux premiers sous leur nom d'envoi → `pieces == [{"nom": rendu.nom_pour_envoi(f), "fichier": f}, …]` pour ces deux seulement, triées par nom ; `nom` est celui du dossier ; `archive` vrai ;
  - `test_sans_paquet_d_envoi_le_dossier_pret_n_a_aucune_piece` et `test_un_paquet_tronque_vaut_un_paquet_absent` (quelques octets dans le `.zip`) : `pieces == []`, `archive` faux ;
  - `test_deux_pieces_au_meme_nom_d_envoi_sont_signalees` : `lettre-de-motivation.pdf` et un `lettre-de-recommandation-inventee.pdf` dans le paquet → un avertissement les nomme ;
  - `test_le_dossier_pret_dit_a_qui_la_lettre_est_adressee` : les quatre champs de l'offre dans `destinataire`, sous leurs clés, ou des chaînes vides ;
  - `test_sans_dossier_sur_le_disque_le_dossier_pret_est_none` : sans `dossier_chemin`, puis avec un `dossier_chemin` vers un dossier absent.
- [ ] **Étape 2 : les lancer.** `.venv\Scripts\python -m pytest -q -p no:cacheprovider tests/test_preparation.py`. Attendu : `ModuleNotFoundError: veille.preparation`.
- [ ] **Étape 3 : écrire `preparation.py`.** `preparer`, dans cet ordre : lire l'offre (`OffreInconnue`) et son état (`EtatIncompatible`) ; passer en `interessante` un statut de `STATUTS_A_PRENDRE` (`db.changer_statut`) ; enregistrer un `texte` fourni (`appliquer_texte(offre_id, texte, "colle a la main")`), un refus rendant `texte` avec le message du `Rapport`, une alerte gardée pour les avertissements ; relire l'offre ; sauf `forcer`, si c'est un extrait (décision 2) : `politique`, puis `verifier_cadence`, puis `recuperer`, puis `appliquer_texte(…, f"recupere sur {domaine}")`, le premier refus rendant `texte` ; sauf `forcer`, si la complétude est insuffisante : `mince` ; sinon `dossier.generer`, une exception rendant `echec` avec `str(e) or type(e).__name__`, puis `db.maj_champs(dossier_chemin=…)`, `db.journaliser(offre_id, "dossier_genere", gabarit)` et `pret`, `dossier_pret` lisant l'offre relue. `dossier_pret` lit la liste du paquet dans un `with zipfile.ZipFile(...)`, un `FileNotFoundError` ou un `BadZipFile` valant un paquet absent, et garde les fichiers du dossier dont `rendu.nom_pour_envoi` y figure. Aucune garde redondante : chaque condition a un test qui la départage.
- [ ] **Étape 4 : les relancer.** Attendu : tous verts.
- [ ] **Étape 5 : la mutation.** Dans `pyproject.toml`, `only_mutate = ["src/veille/etats.py", "src/veille/preparation.py"]` et `pytest_add_cli_args_test_selection = ["tests/test_etats.py", "tests/test_preparation.py"]`, et le commentaire du bloc à jour. Dans `.github/workflows/ci.yml`, l'étape `Mutation de src/veille/etats.py` devient `Mutation des états et de la préparation`, et l'étape `Parcours de connexion` du job `navigateur` devient `Parcours de connexion et de candidature` (point reporté 2).
- [ ] **Étape 6 : commit.** `git add src/veille/preparation.py tests/test_preparation.py pyproject.toml .github/workflows/ci.yml`, puis `git commit -F <fichier>` : `feat(preparation): préparer une candidature, de « Je postule » au dossier prêt`.
- [ ] **Étape 7 : la PR en brouillon.** `git push -u origin feat/parcours-lot2`, puis `gh pr create --draft --base principal --body-file <fichier>` : un titre de 93 caractères au plus, « Partie de #14 », la section « Écarts à la spec » avec les décisions 3, 4 et 11 et leurs dates d'accord, le corps fini avant la fin de la CI. Lire le job `mutation` (`gh run view <id> --log`) : chaque mutant d'un autre statut que `killed` appelle un test de plus, ou un `# pragma: no mutate` sur un mutant équivalent prouvé, sa raison en commentaire. mutmut ne tourne pas sous Windows.
- [ ] **Étape 8 : la revue de la tâche**, par un relecteur neuf, sur le diff de la tâche, avec ce plan, l'ADR-0003 (Contexte et § 5) et le journal du job `mutation`. Ses corrections sont relues avant la tâche 2.

### Tâche 2 : régénérer sans rien perdre

**Fichiers :**
- Modifier : `src/veille/preparation.py`, `tests/test_preparation.py`

**Interfaces :**
- Consomme : `preparer`, `dossier_pret`, `_verifier_etape` et les faux voisins (tâche 1) ; `lettre.historiser`, `lettre.versions`, `lettre.texte_de_version`, `lettre.NOM_HISTORIQUE`, `dossier.chemin_du_dossier`.
- Produit : `ETIQUETTE_REGENERATION = "avant-regeneration"`, et le comportement de `preparer` sur un dossier existant (décisions 6 à 8). `preparer(regenerer=True)` journalise `dossier_regenere` (détail : le gabarit) au lieu de `dossier_genere`.

- [ ] **Étape 1 : écrire les tests qui échouent.** Le faux `generer` reçoit en paramètre le nom du dossier qu'il crée, pour simuler un autre jour.
  - `test_sans_regenerer_un_dossier_existant_est_rendu_sans_generer` : dossier présent → `pret`, `genere` faux, `avertissements` vide, `generer` jamais appelé ; puis `dossier_chemin` vers un dossier absent → `generer` appelé, `genere` vrai ;
  - `test_regenerer_le_meme_jour_historise_la_lettre_remplacee` : la lettre « Lettre affinée inventée » dans le dossier D, le faux `generer` y écrit « Lettre régénérée inventée » → la dernière version de D porte l'étiquette `avant-regeneration` et le texte « Lettre affinée inventée », la lettre courante est la régénérée, `dossier_regenere` au journal ;
  - `test_regenerer_un_autre_jour_emporte_l_historique` : D a une version `001-…-assemblee.md` et la lettre affinée ; le faux `generer` crée E → les noms de `lettre.historique/` de E sont ceux de D (`001-…-assemblee.md`, `002-…-avant-regeneration.md`), la version 2 de E porte la lettre affinée, D garde sa lettre, `dossier_chemin` nomme E, et `e.dossier["nom"]` est celui de E ;
  - `test_regenerer_un_autre_jour_sans_historique_dans_l_ancien` : D sans lettre ni historique, le faux `generer` crée E → `pret`, `dossier_chemin` nomme E, E sans historique ;
  - `test_un_historique_deja_present_n_est_pas_ecrase` : E a déjà un `lettre.historique/` → il reste tel quel, D a reçu sa version `avant-regeneration`, et `dossier_chemin` nomme E ;
  - `test_regenerer_sans_dossier_genere_quand_meme` : `regenerer=True` sans `dossier_chemin`, puis avec un `dossier_chemin` vers un dossier absent → `pret`, aucune version ;
  - `test_regenerer_ne_redemande_ni_texte_ni_completude` : un extrait et un bilan à 30, `regenerer=True` → `pret`, `politique` jamais appelée ; `evaluer` peut l'être, pour remplir `completude` ;
  - `test_une_regeneration_en_echec_garde_l_ancien_dossier` : `generer` lève → `echec`, `dossier_chemin` inchangé, la lettre de D intacte et historisée.
- [ ] **Étape 2 : les lancer.** Attendu : tous échouent, sauf `test_regenerer_sans_dossier_genere_quand_meme`, que la tâche 1 fait déjà passer.
- [ ] **Étape 3 : l'écrire.** Après l'enregistrement du texte : sans `regenerer`, un dossier présent (`chemin is not None and chemin.exists()`) rend `pret` aussitôt, `genere` faux. Avec `regenerer`, sauter la lecture et la complétude, `lettre.historiser(ancien, ETIQUETTE_REGENERATION)` si `ancien` n'est pas `None` (`historiser` rend déjà `None` sans lettre), générer, puis, si le nouveau dossier diffère de l'ancien, que `ancien / NOM_HISTORIQUE` est un dossier et que le nouveau n'en a pas, copier celui de l'ancien (`shutil.copytree`, sans `dirs_exist_ok`).
- [ ] **Étape 4 : relancer** `tests/test_preparation.py`. Attendu : tous verts.
- [ ] **Étape 5 : commit et envoi.** `git add src/veille/preparation.py tests/test_preparation.py`, puis `git commit -F <fichier>` : `feat(preparation): régénérer sans rien perdre, l'historique de la lettre compris`, puis `git push origin feat/parcours-lot2`, et le job `mutation` lu comme à la tâche 1.
- [ ] **Étape 6 : la revue de la tâche**, par un relecteur neuf, avec l'invariant 4 du projet. Ses corrections sont relues avant la tâche 3.

### Tâche 3 : les routes

**Fichiers :**
- Modifier : `src/veille/app.py`
- Créer : `tests/test_preparation_api.py`

**Interfaces :**
- Consomme : `preparation.preparer`, `OffreInconnue`, `EtatIncompatible`, `Etape.as_dict()` (tâches 1 et 2) ; `_refus_sans_configuration_hors_conteneur`, `_erreur`.
- Produit :
  - `class DemandePreparation(BaseModel)` : `texte: str | None = None`, `forcer: bool = False`, `regenerer: bool = False` ;
  - `POST /api/offres/{offre_id}/preparer`, une route `def` qui appelle `preparation.preparer(...)` par l'attribut du module, et rend `Etape.as_dict()`, 404 sur une offre inconnue, 409 `etat_incompatible`, 409 `preparation_en_cours` ou 409 `configuration_non_designee` (décision 10) ;
  - `GET /api/offres/{offre_id}/dossier/{nom_fichier}?pour_envoi=true`, qui sert la pièce sous `rendu.nom_pour_envoi(nom)`. Sans le paramètre, rien ne change.

- [ ] **Étape 1 : écrire les tests qui échouent**, sur la configuration de l'exemple que désigne `tests/conftest.py`, avec les vrais voisins sauf mention :
  - `test_preparer_exige_la_session` ;
  - `test_preparer_rend_le_dossier_pret` : une offre inventée, description de 400 caractères, `forcer=True` → `etape == "pret"`, `genere` vrai, `dossier["nom"]` égal au dernier segment de `dossier_chemin` ;
  - `test_le_texte_colle_d_un_extrait_mene_au_dossier_pret` : une offre `donnees_partielles` d'adresse `https://offres.exemple.invalid/…` → `etape == "texte"` et `url` ; puis avec `texte` (400 caractères inventés) et `forcer=True` → `pret`, et la description en base est le texte ;
  - `test_preparer_une_offre_inconnue_rend_404` et `test_preparer_une_offre_envoyee_rend_409` (`{"erreur": "etat_incompatible"}`) ;
  - `test_deux_preparations_de_la_meme_offre_ne_se_chevauchent_pas` : un faux `preparer` qui pose un événement « entré » puis attend un événement « libéré » ; un premier appel lancé d'un fil ; le fil principal attend « entré » (`wait(timeout=5)`, retour vérifié), puis un second appel → 409 `preparation_en_cours` ; « libéré » posé, `join(timeout=5)` vérifié, le premier a rendu 200, et un troisième passe ;
  - `test_la_garde_se_libere_apres_une_erreur` : un faux `preparer` qui lève `EtatIncompatible`, puis un appel suivant passe ;
  - `test_preparer_refuse_sans_configuration_designee` : `app._sert_l_exemple_par_oubli` forcé à vrai → 409 `configuration_non_designee`, statut inchangé ;
  - `test_une_piece_se_telecharge_sous_son_nom_d_envoi` : après `pret`, un `cv.fr.pdf` inventé (quelques octets) déposé dans le dossier ; `GET …/dossier/cv.fr.pdf?pour_envoi=true` → le nom lu dans `Content-Disposition` (`email.message.Message.get_filename`) est `rendu.nom_pour_envoi("cv.fr.pdf")` ; puis le même avec `rendu.prefixe` remplacé par un préfixe accentué inventé, qui passe par `filename*=` ;
  - `test_sans_pour_envoi_une_piece_garde_son_nom` : `cv.fr.pdf`.
- [ ] **Étape 2 : les lancer.** Attendu : 404 ou 405 sur `/preparer`, et `cv.fr.pdf` sur `?pour_envoi=true`.
- [ ] **Étape 3 : les écrire** dans `app.py`, près des routes du dossier. La garde : un `set` des offres en préparation sous un `threading.Lock`, l'offre retirée dans un `finally`.
- [ ] **Étape 4 : relancer** `tests/test_preparation_api.py`, puis la suite du poste. Attendu : tous verts, les sauts attendus sous Windows.
- [ ] **Étape 5 : commit et envoi.** `git add src/veille/app.py tests/test_preparation_api.py`, puis `git commit -F <fichier>` : `feat(api): la route de la préparation, et les pièces sous leur nom d'envoi`, puis `git push origin feat/parcours-lot2`.
- [ ] **Étape 6 : la revue de la tâche**, par un relecteur neuf. Ses corrections sont relues avant la tâche 4.

### Tâche 4 : l'interface, de « Je postule » au « Dossier prêt »

**Fichiers :**
- Modifier : `src/veille/static/app.js` (CRLF), `src/veille/static/style.css` (CRLF) s'il le faut, `tests_navigateur/test_parcours_candidature.py`

**Interfaces :**
- Consomme : `POST /api/offres/{id}/preparer`, `GET …/dossier/{fichier}?pour_envoi=true` (tâche 3) ; `Etape` et `dossier_pret` (tâche 1) ; `blocDestinataire`, `brancherDestinataire`, `blocAffinement`, `brancherAffinement`, `demanderCanal`, `rafraichir`.
- Produit, dans `app.js` :
  - `preparerCandidature(id, bouton, options = {})`, `options` parmi `{texte, forcer, regenerer}` : le bouton désactivé, son texte `Préparation… N s` mis à jour chaque seconde, rendu tel quel à la fin s'il est encore dans la page ; puis l'écran de l'étape, et `rafraichir()` ;
  - `afficherEtapeTexte(id, r)`, `afficherEtapeMince(id, r)`, `afficherEtapeEchec(id, r, options)`, `afficherDossierPret(id, r)`, chacune dans `#fenetre` ;
  - `blocDestinataire(o, libelle = 'Enregistrer')` et `brancherDestinataire(id, apres)` : `apres`, facultatif, est appelé après l'enregistrement ; la vue détaillée les appelle toujours comme avant ;
  - `ERREURS_API.etat_incompatible` et `ERREURS_API.preparation_en_cours`, chacun une phrase.
- Les gestes : `data-action="postuler"` (la carte « À voir » et la fiche) et `data-action="preparer"` (la fiche « Je postule ») appellent `preparerCandidature`. La fiche « Je postule » sans dossier porte « Préparer ma candidature » ; avec, « Je l'ai envoyée » et « Dossier prêt › » (décision 12). Les anciens écrans gardent `data-action="dossier"`.
- Les écrans. Chacun montre d'abord les `avertissements` de l'étape, l'alerte éliminatoire en tête (décision 5).
  - `texte` : le titre « Il manque le texte de l'annonce », le message, « Ouvrir l'annonce › » (`target="_blank" rel="noopener noreferrer"`, absent sans `url`), une zone de texte, « Préparer avec ce texte », qui ne part pas sur une zone vide, et « Générer avec l'extrait » (`forcer`, décision 4) ;
  - `mince` : le score et le seuil, les manques et leur `quoi_faire`, « Générer quand même » (`forcer`) et « Coller le texte de l'annonce », qui ouvre l'écran `texte` ;
  - `echec` : la cause, et « Réessayer », avec les mêmes options ;
  - `pret` : « Dossier prêt » ; l'avertissement du kit provisoire, s'il y a lieu ; « Adressée à » et le destinataire, ou une phrase qui dit qu'aucun n'est enregistré et qu'il apparaîtra en rouge dans le PDF ; chaque pièce, un lien `download` vers `?pour_envoi=true`, ou une phrase quand il n'y en a aucune ; « Tout en un zip », si le paquet existe, sinon « Régénérer le dossier » (`regenerer`, décision 12) ; « Voir l'annonce › », absent sans `url` ; puis « Je l'ai envoyée » (`demanderCanal`), « Ajouter un destinataire » (« Modifier le destinataire » s'il y en a un), qui montre `blocDestinataire(r.dossier.destinataire, 'Enregistrer et régénérer')`, puis `preparerCandidature(id, bouton, {regenerer: true})`, et « Affiner la lettre », qui montre `blocAffinement` sans rien régénérer (point reporté 4).

- [ ] **Étape 1 : écrire les tests qui échouent**, dans `tests_navigateur/test_parcours_candidature.py`. Une aide, `_simuler_preparation(page, offre_id, reponses) -> list[dict]`, route `**/api/offres/{offre_id}/preparer`, sert les réponses dans l'ordre, rend la liste des corps reçus, et écrit en base ce que la route écrirait : `interessante` pour un statut de `STATUTS_A_PRENDRE`, `dossier_chemin` sur `pret` (décision 11). `FICHES` reçoit une offre par test qui change un statut. Les tests :
  - `test_je_postule_lance_la_preparation_et_montre_le_temps` : la requête retenue, le bouton est désactivé et son texte répond à `\d+ s` ; servie (`texte`), l'écran `texte` s'ouvre ;
  - `test_le_texte_colle_mene_au_dossier_pret_puis_a_l_envoi` (ADR-0003, § 7) : la carte « À voir », « Je postule », l'écran `texte` (le message, le lien de l'annonce), un texte collé, « Préparer avec ce texte » → le second corps porte ce `texte` ; « Dossier prêt » montre deux pièces dont les liens finissent par `?pour_envoi=true` et portent `download`, le zip, « Adressée à » et le lien de l'annonce ; « Je l'ai envoyée », « LinkedIn » → statut `candidature_envoyee` ;
  - `test_l_etape_texte_propose_de_generer_avec_l_extrait` : le corps envoyé est `{"forcer": true}` ;
  - `test_un_texte_vide_ne_part_pas` : après le message qui le dit, une seule requête ;
  - `test_mince_propose_de_coller_le_texte_ou_de_generer` : « Générer quand même » envoie `{"forcer": true}` ; « Coller le texte de l'annonce » montre la zone de texte ;
  - `test_un_echec_propose_de_reessayer` : la cause affichée ; « Réessayer » renvoie les mêmes options ; la fiche dit toujours « Je postule » ;
  - `test_l_alerte_eliminatoire_se_voit` : une réponse `pret` dont `avertissements[0]` est une alerte inventée → elle est le premier texte de l'écran ;
  - `test_ajouter_un_destinataire_enregistre_puis_regenere` : une offre qui a déjà les quatre champs ; « Modifier le destinataire », le nom seul changé, « Enregistrer et régénérer » → le `POST /api/offres/{id}` porte le nouveau nom et les trois autres valeurs inchangées, puis `/preparer` part avec `{"regenerer": true}`, dans cet ordre ;
  - `test_sans_paquet_dossier_pret_propose_de_regenerer` : `archive` faux → « Régénérer le dossier » envoie `{"regenerer": true}`, et aucun lien de zip ;
  - `test_affiner_la_lettre_ne_regenere_pas` : « Affiner la lettre », puis, une fois « Proposer une version affinée » ou « Affinement indisponible » visible, aucune requête `/preparer` de plus ;
  - `test_la_fiche_je_postule_avec_dossier_mene_au_dossier_pret` : la ligne d'actions porte « Je l'ai envoyée » et « Dossier prêt › », ni lien de paquet ni « Régénérer » ;
  - `test_dossier_pret_se_touche_du_doigt_et_tient_dans_l_ecran` : avec une pièce simulée au nom de 80 caractères sans espace, chaque lien et bouton fait au moins `DOIGT`, et `scrollWidth` reste dans les 390 px.
  - Les tests du lot 1 qui passaient par l'ancien geste suivent : `test_le_parcours_de_la_file_a_l_entretien` simule `/preparer`, `test_generer_le_dossier_recharge_a_finir` devient `test_preparer_recharge_a_finir`, et `test_chaque_etat_a_sa_ligne_d_actions` attend les lignes de la décision 12, l'assertion du lien du paquet (lignes 562-564) retournée en son absence.
  - Point reporté 1 : dans `test_non_nomme_l_offre_et_ecarte_la_bonne`, `fenetre.get_by_role("button", name="motif inventé de la première")` devient `fenetre.locator('[data-motif="motif inventé de la première"]')`. L'éprouver par un mutant du code : `remplirMotifs` qui remplit toute zone `.motifs`, sans la garde `data-pour` ; l'ancienne ligne passe, la nouvelle échoue.
- [ ] **Étape 2 : les lancer.** `.venv\Scripts\python -m pytest -q -p no:cacheprovider tests_navigateur`. Attendu : les tests neufs échouent ; les autres passent.
- [ ] **Étape 3 : écrire l'interface.** Le minuteur reprend la forme de `brancherAffinement`.
- [ ] **Étape 4 : relancer** les tests du navigateur, `node --check src/veille/static/app.js`, et `tests/test_javascript.py`. Attendu : tous verts. `app.js` et `style.css` restent en CRLF.
- [ ] **Étape 5 : commit et envoi.** `git add src/veille/static/app.js tests_navigateur/test_parcours_candidature.py` (et `src/veille/static/style.css` s'il a changé), puis `git commit -F <fichier>` : `feat(console): « Je postule » prépare la candidature, et l'écran « Dossier prêt »`, puis `git push origin feat/parcours-lot2`.
- [ ] **Étape 6 : la revue de la tâche**, par un relecteur neuf, avec l'ADR-0003, §§ 4 et 5. Ses corrections sont relues avant la tâche 5.

### Tâche 5 : la documentation et les points reportés

**Fichiers :**
- Modifier : `docs/CANDIDATURE.md` (CRLF), `README.md` (CRLF), `docs/FONCTIONNEMENT.md`, `docs/pistes.md`, `CLAUDE.md`, et `src/veille/completude.py` si l'un de ses textes nomme un bouton absent des nouveaux écrans

- [ ] **Étape 1 : chercher chaque mention de l'ancien geste.** L'outil Grep sur `docs/`, `README.md`, `CLAUDE.md` et `src/veille/completude.py`, motif `Générer le dossier|Generer le dossier|Régénérer|Lire l'annonce|lot 2`.
- [ ] **Étape 2 : réécrire.**
  - `docs/CANDIDATURE.md` : le titre, la ligne 73, le seuil de la ligne 241 et la section « Ce que « Générer le dossier » produit » parlent de « Préparer ma candidature » : ses étapes (le texte, « Générer avec l'extrait », l'information trop mince, le dossier prêt), l'alerte éliminatoire, « Dossier prêt » (les pièces une à une sous leur nom d'envoi, le zip), le destinataire jamais demandé avant, et la régénération qui historise la lettre remplacée.
  - `README.md` : la ligne de `docs/CANDIDATURE.md` nomme « Préparer ma candidature ».
  - `docs/FONCTIONNEMENT.md` : le paragraphe de la fiche dit ce que fait « Je postule » depuis ce lot ; et les trois retouches reportées (point 3) : « Autres actions » sans guillemets imbriqués ; « jusqu'au lot 3 de l'ADR-0003 » dit en clair (ces écrans attendent leur refonte) ; la cellule « À faire » ramenée à une phrase courte, le détail passant dans le paragraphe qui suit le tableau.
  - `docs/pistes.md` : une ligne qui dit que l'ancien « Générer le dossier » des anciens écrans réécrit la lettre du jour sans l'historiser, jusqu'à son retrait au lot 3.
  - `src/veille/completude.py` : un `quoi_faire` ou un commentaire qui nomme un bouton absent des nouveaux écrans est reformulé, son test (`tests/test_completude.py`) avec.
  - `CLAUDE.md`, section « État » : une phrase sur `preparation.py`, la route et l'écran « Dossier prêt ».
- [ ] **Étape 3 : vérifier.** `python -X utf8 -B scripts/modele/documentation.py` rend 0 ; la suite du poste reste verte si `completude.py` a changé ; les fins de ligne sont inchangées.
- [ ] **Étape 4 : commit et envoi.** `git add` des fichiers changés, par chemins, puis `git commit -F <fichier>` : `docs: « Préparer ma candidature » (lot 2 de l'ADR-0003)`, puis `git push origin feat/parcours-lot2`.
- [ ] **Étape 5 : la revue de la tâche**, par un relecteur neuf, qui cherche aussi les mots retirés (« Générer le dossier », « Régénérer ») dans tout le dépôt. Ses corrections sont relues avant la PR prête.

### Tâche 6 : la PR prête, la revue finale et le staging

- [ ] **Étape 1 : la PR prête.** `gh pr ready <n>`. Attendre tous les contrôles verts, `mutation` et `navigateur` compris ; le journal du job `mutation` ne liste que des mutants `killed`.
- [ ] **Étape 2 : la revue finale**, par un relecteur neuf sur le modèle le plus capable, sur tout le diff du lot, avec l'ADR-0003, ce plan et le journal du job `mutation`.
- [ ] **Étape 3 : les corrections**, en une vague, puis leur relecture par un relecteur neuf, sur le diff des corrections. La session fusionne ensuite la PR : `gh pr merge <n> --squash --match-head-commit <sha>`, depuis le clone, sans `cd`.
- [ ] **Étape 4 : 👤 le staging, au téléphone.** Le staging se redéploie seul depuis `principal`. Ses offres factices ont toutes des descriptions de moins de 400 caractères : ce sont des extraits, et la préparation s'y arrête à l'étape `texte`. Le dossier prêt en un seul toucher se vérifie en Python et au navigateur. Edouard vérifie :
  - sur une offre « À voir » : « Je postule » montre le temps qui passe, puis « Il manque le texte de l'annonce » ;
  - un texte inventé de 400 caractères au moins, « Préparer avec ce texte » ; puis, s'il le faut, « Générer quand même » ;
  - sur une autre offre : « Générer avec l'extrait » mène au dossier ;
  - « Dossier prêt » : une pièce téléchargée seule porte le nom qu'elle a dans le zip ; le zip se télécharge ;
  - « Ajouter un destinataire », un nom inventé, « Enregistrer et régénérer » : la lettre le porte ; puis « Modifier le destinataire », la formule d'appel seule changée : le nom reste ;
  - « Affiner la lettre » montre son bloc, ou dit pourquoi il est indisponible, sans régénérer ;
  - « Je l'ai envoyée » mène à « Envoyée » ;
  - la fiche « Je postule » d'une offre dont le dossier est prêt porte « Je l'ai envoyée » et « Dossier prêt › ».

### Tâche 7 : la clôture

- [ ] **Étape 1 : la PR de clôture.** Elle supprime ce plan, reporte dans `CLAUDE.md` ce qui doit survivre (l'état du lot 2, la ligne « Prochain »), relit le README d'après `docs/modele/documentation.md`, coche les critères de `veille-emploi#14`, porte « Closes #14 », la section « Écarts à la spec » (les décisions 3, 4 et 11), et la ligne `Tête relue : <SHA>` de la tête qu'a lue sa dernière relecture. Elle dit aussi que l'écart du lot 1 (la fiche « Je postule » avec dossier, § 4) est soldé par l'écran « Dossier prêt ».
- [ ] **Étape 2 : 👤 l'étiquette `v0.3.0`**, sur le commit de la clôture, posée par Edouard. Puis, depuis le poste, `/sante` de la prod rend `"version":"0.3.0"`, et `modele-version` a publié l'image `0.3.0`.

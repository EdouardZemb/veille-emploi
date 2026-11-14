# Lot 3 du parcours (ADR-0003) : l'écran « Plus » et le ménage des filtres — plan

> **Pour les agents :** compétence requise, *superpowers* `subagent-driven-development` (recommandée) ou `executing-plans`, tâche par tâche. Les étapes se cochent (`- [ ]`). Les étapes 👤 sont des gestes d'Edouard : la session les prépare et ne les lance pas.

**Objectif :** « Plus » devient une liste de six lignes ; Toutes les offres n'a plus que trois filtres ; Mes critères et le Bilan reprennent À classer, Archive et Pilotage ; Réglages reçoit « Notifications » et « Quitter » ; le retour d'Android suit les vues et les fenêtres ; la perte d'un abonnement push se voit et se répare (issue `veille-emploi#15`, AM-3).

**Architecture :** deux fonctions pures neuves de `src/veille/etats.py` portent le filtre d'état et la traduction des liens d'entrée, côté serveur et sous la mutation. Le reste est l'interface (`app.js`, `index.html`, `style.css`, `sw.js`), refaite écran par écran : chaque tâche retire l'écran qu'elle remplace, puis une tâche retire ce qui ne sert plus, paramètres et routes de l'API compris, avec leurs tests. Le retour d'Android vient après, sur les écrans définitifs.

**Pile :** Python 3.13, FastAPI, SQLite ; JavaScript sans framework ; pytest ; Playwright (`tests_navigateur/`) ; Node (`node --check`, harnais de `sw.js`) ; mutmut 3.8.1 (CI Linux seulement).

**Spec :** `docs/decisions/0003-le-parcours-jusqu-a-la-candidature.md`, §§ 1, 2, 6, 7 et 8 ; les critères de `veille-emploi#15` et ses deux commentaires (le retour d'Android, AM-3) ; les treize décisions d'Edouard du 14/11/2026, reprises ci-dessous (« Le cadrage ») ; les pistes de `docs/pistes.md` dont le déclencheur est ce lot.

**Préalables :** le plan fusionné, dans le worktree `veille-emploi.worktrees\parcours-lot3` : `git fetch origin`, puis `git switch --no-track -c feat/parcours-lot3 origin/principal` ; `python -m venv .venv`, `.venv\Scripts\python -m pip install -e .[dev,navigateur]`, `.venv\Scripts\python -m playwright install chromium`. `git rev-parse --git-path hooks` y rend `.githooks`, et `node --version` répond.

## Mécanismes annoncés

- `src/veille/etats.py:16` — `_ETAT_DU_STATUT` — la seule traduction des onze statuts en états ; les deux fonctions neuves la lisent sans la recopier
- `src/veille/etats.py:12-13` — `MISE_DE_COTE = "mise_de_cote"` — les cinq états, puis la mise de côté, hors d'eux
- `src/veille/db.py:522` — `def lister_offres` — lit `verification` et `tri`, et aucun ensemble de statuts
- `src/veille/db.py:539` — `archivee_le IS NULL` — une offre archivée reste hors de la liste, quel que soit le filtre
- `src/veille/db.py:546` — `statut NOT IN ('ecartee','differee')` — sans `statut` ni `inclure_ecartees`, la liste écarte les écartées et les différées, mais garde les refus et les acceptées
- `src/veille/app.py:471` — `def api_offres` — lit `statut`, `zone`, `famille`, `atout`, `source`, `recherche`, `inclure_ecartees`, `verification`, `tri`, `a_documenter` et `limite`, et rend l'état de chaque offre
- `src/veille/app.py:517` — `if a_documenter:` — le filtre et le compte « À documenter », que seule l'ancienne vue lit
- `src/veille/app.py:442-462` — `"statuts": STATUTS` — la page reçoit les statuts, les zones et les atouts des anciens filtres, et rien d'un lien d'entrée
- `src/veille/app.py:808` — `def api_dossier` — l'ancien « Générer le dossier », qu'appelle seul `genererDossier`
- `src/veille/app.py:1309` — `@app.get("/api/relances"` — la liste des relances, qu'appellent seuls `chargerRelances` et `chargerPlus`
- `src/veille/app.py:911` — `Barriere anti-traversee` — la route de téléchargement d'une pièce refuse un fichier hors de son dossier
- `src/veille/app.py:1115` — `def api_classement` — les propositions à classer : leur nombre est celui de `propositions`
- `src/veille/app.py:653` — `"nouvelles": db.compter_archivees_depuis(depuis)` — `/api/archive` compte les archivées depuis la dernière visite, et toutes sans `depuis`
- `src/veille/db.py:1312` — `archive_protegee = 1` — une offre remise dans le flux n'est plus jamais archivée seule
- `src/veille/app.py:1339` — `def api_rescorer` — recalcule toutes les offres, et refuse sans configuration désignée (409 `configuration_non_designee`)
- `src/veille/db.py:763` — `ON CONFLICT(endpoint)` — enregistrer deux fois le même abonnement n'en fait qu'un : le renvoi à l'ouverture est sans danger
- `src/veille/app.py:1371` — `def api_desabonnement` — retire l'abonnement dont l'adresse arrive en paramètre `endpoint`
- `src/veille/app.py:172` — `request.headers.get("origin") != attendue` — toute écriture sans l'en-tête `Origin` de la console est refusée, celles du service worker comprises
- `src/veille/notifications.py:114` — `aucun appareil abonne` — sans abonné, le push ne tente rien, et l'écrit en INFO
- `src/veille/notifications.py:148-153` — `db.supprimer_abonnement(ab["endpoint"])` — un 404 ou un 410 du service push retire l'abonnement, en INFO
- `src/veille/notifications.py:265` — `if ok:` — le mail de repli ne part que si aucun push n'est passé
- `src/veille/notifications.py:279` — `repli mail (aucun appareil joignable)` — ce que dit la ligne `notification` de `veille etat` après un repli remis
- `src/veille/collecte.py:89` — `prevenir_nouvelles_offres(fraiches, base_url=base_url)` — la collecte donne au mail l'adresse de la console
- `src/veille/static/sw.js:14` — `addEventListener('push'` — le service worker n'écoute que `push` et `notificationclick`
- `src/veille/static/app.js:2321` — `async function activerPush` — demande la permission, s'abonne, enregistre l'abonnement, puis envoie un essai ; seul le bouton de l'en-tête l'appelle
- `src/veille/static/app.js:2348` — `window.isSecureContext` — le service worker ne s'enregistre qu'en contexte sûr, et rien ne relit l'abonnement à l'ouverture
- `src/veille/templates/index.html:17-25` — `id="btn-push"` — l'en-tête porte « Notifications » et le formulaire « Quitter » (`POST /deconnexion`)
- `src/veille/templates/index.html:63-69` — `class="lien-plus"` — les sept lignes de « Plus », dont quatre mènent aux anciens écrans
- `src/veille/static/app.js:914` — `async function chargerPlus` — les pastilles des lignes de « Plus », lues à son ouverture seulement, celle des relances par `/api/relances`
- `src/veille/static/app.js:1691` — `const CLE_VISITE_ARCHIVE` — la dernière visite de l'archive, dans le stockage local du navigateur
- `src/veille/static/app.js:302` — `async function chargerPilotage` — l'entonnoir, les tableaux par canal, par famille et par source, et les motifs d'écartement
- `src/veille/static/app.js:2034` — `async function chargerClasser` — les propositions à classer, chacune avec ses preuves et sa coche
- `src/veille/static/app.js:88` — `function carteOffre` — la carte à neuf boutons des anciens écrans
- `src/veille/static/app.js:1652` — `genererDossier(id, bouton)` — le geste de la carte qui appelle l'ancienne route
- `src/veille/static/app.js:2291` — `setTimeout(chargerOffres, 280)` — la recherche attend 280 ms de calme, et rien n'écarte une réponse arrivée après une plus récente
- `src/veille/static/app.js:805` — `function liensVersToutes` — les liens « au-dessus » et « sous le seuil » mènent à Toutes les offres, filtrée par `#f-statut`
- `src/veille/static/app.js:2356-2365` — `const versOffres` — `?filtre=` autre que `nouveau`, ou `?atout=`, ouvrent Toutes les offres sur `#f-statut` ou `#f-atout`
- `src/veille/static/app.js:2173` — `function afficherVue` — change de vue sans toucher à l'historique
- `src/veille/static/app.js:1019` — `if (!fenetre.open) fenetre.showModal();` — la fiche ouvre la fenêtre unique, ou y remplace ce qu'elle montre
- `src/veille/static/app.js:1561` — `$('#fenetre').showModal();` — `ouvrirEntretien` ouvre la fenêtre sans regarder si elle l'est déjà
- `src/veille/templates/index.html:182-185` — `<form method="dialog">` — la fenêtre se ferme par son bouton « Fermer », ou par Échap
- `src/veille/static/app.js:1226` — `const provisoire = r.kit_provisoire` — « Dossier prêt » dit le kit provisoire dans son propre bloc
- `src/veille/dossier.py:725` — `Kit de candidature provisoire` — `generer` le dit aussi, en tête de ses avertissements
- `src/veille/preparation.py:162` — `*resultat.avertissements` — l'étape `pret` reprend tels quels les avertissements de la génération
- `tests/test_javascript.py:253` — `"'fetch'" not in source` — `sw.js` ne porte ni le littéral `'fetch'` ni `"fetch"`, même en commentaire
- `tests/test_javascript.py:217` — `def test_toute_route_appelee_par_le_js_existe` — une route que `app.js` nomme encore ne peut pas partir
- `tests/test_javascript.py:274` — `source.index("const ERREURS_API"):source.index("const niveau")` — `ERREURS_API` et `api()` restent avant `const niveau`
- `tests/test_javascript.py:322` — `def test_le_javascript_ne_nomme_aucun_atout` — aucun fichier `.js` de `static/`, `sw.js` compris, ne nomme un atout
- `tests/test_verification.py:453` — `data-vue="archive"` — la page doit porter le lien de l'archive
- `tests/test_instance.py:364` — `/api/offres/{id}/dossier?forcer=true` — la liste des gestes refusés sans configuration nomme l'ancienne route
- `tests/test_app.py:228-232` — `..%2F..%2F..%2Fetc%2Fpasswd` — la barrière se teste sur un dossier fait par l'ancienne route
- `tests_navigateur/conftest.py:27` — `URL = f"http://localhost:{PORT}"` — `localhost` est un contexte sûr : service worker et push y sont permis sans HTTPS
- `tests_navigateur/test_cibles_tactiles.py:60` — `page.click('.lien-plus[data-vue="offres"]')` — les mesures se font sur l'ancienne liste des offres
- `src/veille/static/style.css:40` — `.pastille:empty{display:none}` — une pastille vide ne se voit pas
- `pyproject.toml:54` — `only_mutate` — mutmut ne mute que `etats.py` et `preparation.py`, sous `tests/test_etats.py` et `tests/test_preparation.py`

## Outils et cas limites

- mutmut 3.8.1 — il remplace aussi un littéral de chaîne et inverse chaque comparaison, ne mute pas les constantes du module, et une fonction que la sélection n'appelle pas donne des mutants « no tests » ; le job exige zéro mutant d'un autre statut que `killed` — le job `mutation` de la PR, lu dès la tâche 1 (PR en brouillon) ; `test_un_etat_inconnu_leve` lit le message par `match`, et les listes attendues sont écrites en clair (tâches 1 et 6)
- FastAPI, paramètres de requête — un paramètre inconnu est ignoré en silence, sans 422 : un test qui passe encore `a_documenter=true` lit une liste entière et peut passer — `test_les_parametres_retires_ne_sont_plus_lus`, sur la signature de `api_offres` et de `db.lister_offres`, et la suppression des tests de ces paramètres (tâche 6)
- Playwright, `page.go_back()` — il rend `None` pour une entrée posée par `pushState`, comme quand rien ne précède : sa valeur ne prouve rien — chaque test de `tests_navigateur/test_retour.py` lit la vue montrée par `expect`, et `test_le_retour_depuis_a_faire_quitte_la_console` part d'un autre document, `/sante` (tâche 7)
- `<dialog>`, l'événement `close` — il part dans une tâche à lui, après le `popstate` qui a fermé la fenêtre : `history.state` y est déjà celui de la vue — `test_le_retour_ferme_la_fiche`, dont le second retour quitte la vue au lieu de toucher dans le vide (tâche 7)
- `<dialog>` modal fermé sans son bouton — par Échap, et sur Android par le retour lui-même : Chrome ferme une fenêtre modale par `cancel` puis `close`, sans traverser l'historique — `test_echap_ferme_la_fenetre_et_retire_son_entree` : l'entrée se retire sur `close`, quel que soit le chemin (tâche 7)
- `history.back()` — asynchrone : une fenêtre rouverte avant la fin du retour lancé par `close` serait refermée par son `popstate` — `test_une_fiche_rouverte_aussitot_se_ferme_au_retour` (tâche 7)
- `pushManager.getSubscription()` — il rend `null`, sans erreur, quand l'abonnement est perdu — `test_sans_abonnement_l_ouverture_se_reabonne` (tâche 5)
- `Notification.permission` — un accesseur statique, dont la valeur par défaut dépend du navigateur et du mode ; `requestPermission` sans geste est refusée ou ignorée — chaque test du push le pose par `add_init_script` avant `app.js`, et `test_sans_permission_l_ouverture_ne_demande_rien` compte les appels à `requestPermission` (tâche 5)
- un service worker dans Chromium sans HTTPS — permis sur `http://localhost`, absent en clair ailleurs (`navigator.serviceWorker` indéfini) ; sans tête, `pushManager.subscribe` échoue faute de service push — les tests remplacent `getSubscription` et `subscribe` sur `PushManager.prototype`, et `test_sans_push_reglages_dit_indisponible` retire `PushManager` (tâche 5)
- `pushsubscriptionchange` — Chrome ne le déclenche pas, ou rarement, et quand il part, `newSubscription` comme `oldSubscription` peuvent manquer ; le renvoi à l'ouverture reste donc le remède principal — les quatre tests de `tests/test_service_worker.py`, sous Node (tâche 5)
- Node, harnais de `sw.js` — absent, le test se saute, comme `tests/test_javascript.py` — le journal du job `verifier` (`-rs`) montre les tests de `tests/test_service_worker.py` passés, pas sautés (tâche 5)
- le délai de la recherche — 280 ms de calme : une frappe rapide n'envoie qu'une requête, et une assertion lue avant le délai ne voit rien — `test_la_recherche_n_envoie_qu_une_requete_par_pause`, qui attend la requête par `expect_request` (tâche 4)
- `fetch`, réponses hors d'ordre — deux recherches en vol rendent leurs réponses dans n'importe quel ordre — `test_une_reponse_perimee_ne_remplace_pas_la_liste`, la première requête retenue par `page.route` (tâche 4)
- Playwright, `get_by_role` avec `exact=True` — le nom d'un bouton comprend le texte de sa pastille : « Plus » devient « Plus 2 » — les tests visent l'onglet par `.onglet[data-vue="plus"]`, et `test_la_pastille_de_plus_ne_compte_que_les_offres_a_classer` le fait avec une pastille pleine (tâche 3)
- Playwright, `page.route` sur un motif glob — le sens de `?` y a changé selon les versions : une adresse à requête se route par une expression régulière — `test_le_bilan_montre_l_entonnoir_puis_trois_listes_repliees`, ses routes en `re.compile` (tâche 3)
- `<details>`, l'événement `toggle` — il part aussi, après coup, pour un `<details>` rendu déjà ouvert — `test_un_bilan_ouvert_sans_deplier_les_archivees_garde_la_pastille` et `test_deplier_les_archivees_eteint_la_pastille_du_bilan` (tâche 3)

## Revues

- la revue de la tâche 1, par un relecteur neuf, avec le journal du job `mutation`, avant la tâche 2 : Tâche 1
- la revue de la tâche 2, par un relecteur neuf, avant la tâche 3 : Tâche 2
- la revue de la tâche 3, par un relecteur neuf, avant la tâche 4 : Tâche 3
- la revue de la tâche 4, par un relecteur neuf, avant la tâche 5 : Tâche 4
- la revue de la tâche 5, par un relecteur neuf, avant la tâche 6 : Tâche 5
- la revue de la tâche 6, par un relecteur neuf, qui cherche les mots retirés dans tout le dépôt, avant la tâche 7 : Tâche 6
- la revue de la tâche 7, par un relecteur neuf, avant la tâche 8 : Tâche 7
- la revue de la tâche 8, par un relecteur neuf, avant la PR prête : Tâche 8
- la revue finale, sur tout le diff du lot, par un relecteur neuf sur le modèle le plus capable, avec la lecture des mutants survivants (ADR-0003, § 7) : Tâche 9
- la relecture des corrections de la revue finale, par un relecteur neuf : Tâche 9

## Le cadrage : les décisions d'Edouard du 14/11/2026

Elles font foi. Edouard a répondu « Ok pour les défauts » aux treize questions.

- **E1.** Un lot, un plan, une PR d'implémentation, puis l'étiquette `v0.4.0`. Pas de tranches.
- **E2.** La carte à neuf boutons (`carteOffre`) part : chaque offre de Toutes les offres devient une ligne (titre, employeur, score, état) qui ouvre la fiche par état.
- **E3.** Trois filtres : la recherche, l'état (les cinq, plus « mises de côté ») et la famille ; la bascule de l'atout mis en avant reste. L'état se filtre côté serveur, par un paramètre `etat` calculé dans `etats.py`, sous la mutation. La zone et la liste des atouts quittent l'écran.
- **E4.** Partent `a_documenter`, `verification` et `tri`, avec leurs tests, puis `POST /api/offres/{id}/dossier` et `GET /api/relances`. Les tests de la barrière de chemin passent sur la route de téléchargement. `zone`, `atout` et `statut` restent.
- **E5.** `?filtre=…` et `?atout=…` restent valides ; `?filtre=` se traduit vers le filtre d'état.
- **E6.** La liste des relances part ; les relances dues restent en tête d'« À finir », et la ligne « Envoyée » de « Candidatures » garde « relance le <date> ».
- **E7.** Mes critères : l'actuel « À classer », « Recalculer tous les scores », et le rappel que les critères se changent dans la configuration de l'instance.
- **E8.** Le Bilan : l'entonnoir, le rendement des sources et les motifs d'écartement, puis trois listes repliées, les archivées (« Remettre dans le flux »), les closes (leur motif) et les mises de côté. Les nouvelles archivées font une pastille sur la ligne « Bilan ».
- **E9.** La pastille de l'onglet « Plus » est créée, et ne compte que les offres à classer.
- **E10.** Chaque vue et chaque fenêtre (la fiche, le panneau « Non », les étapes de la préparation) entrent dans l'historique. Le retour ferme la fenêtre ouverte ; sans fenêtre, il revient à la vue d'avant ; depuis « À faire », il quitte l'application. Un test de navigateur le garde.
- **E11.** Le push (AM-3) : à l'ouverture, renvoyer l'abonnement, ou se réabonner, quand la permission est accordée ; `pushsubscriptionchange` dans `sw.js` ; le retrait journalisé en avertissement ; un mail de repli qui dit qu'aucun appareil n'est abonné, avec le geste qui répare. Réglages dit si cet appareil reçoit les notifications, à côté du bouton « Notifications », qui y arrive avec « Quitter » ; l'en-tête ne garde que le titre.
- **E12.** Entrent l'ancien « Générer le dossier », le kit provisoire annoncé deux fois et le doublon d'`afficherEtapeMince` avec `afficherCompletudeInsuffisante`. Restent des pistes les avertissements recalculés au retour sur « Dossier prêt » et un « Régénérer » toujours visible. Les pistes traitées sortent de `docs/pistes.md`, et « La conséquence pratique » de `docs/CANDIDATURE.md` se met à jour.
- **E13.** La méthode des lots 1 et 2 : ce plan relu par un relecteur neuf, l'exécution par sous-agents, la revue finale sur le modèle le plus capable, le staging vérifié au téléphone, la clôture, puis `v0.4.0`, posée par Edouard.

## Les décisions du plan

Ce que le cadrage laisse ouvert, tranché ici. Les décisions 2 (`inclure_ecartees`) et 7 sont des écarts à la lettre de l'ADR, que la PR déclare avec l'accord d'Edouard.

1. **L'ordre.** Rien ne disparaît avant d'avoir sa place (ADR, § 2). Les tâches 3 à 5 refont un écran à la fois, et retirent l'écran qu'elles remplacent : Archive, À classer, Pilotage et Relances à la tâche 3, les anciens filtres à la tâche 4, l'en-tête à la tâche 5. La tâche 6 retire le code mort, les paramètres et les routes de l'API, et leurs tests. Le retour d'Android vient ensuite : moins d'ouvertures de fenêtre à convertir, et ses tests courent sur les écrans définitifs.
2. **Le filtre d'état et la liste par défaut.** `etat` vaut l'un des cinq états ou `mise_de_cote` ; `etats.statuts_du_filtre` le traduit en statuts, que `db.lister_offres` reçoit (`statut IN`). Sans état, la liste montre les offres « En cours » : À voir, Je postule, Envoyée, Entretien. Les closes (écartées, refus, acceptées) et les mises de côté ne se voient que par leur filtre ; jusqu'ici, la liste par défaut gardait les refus et les acceptées. `etat` et `statut` se combinent ; un `etat` vide vaut aucun état ; un état inconnu rend 400. Une archivée reste hors de la liste sous tout filtre : elle est au Bilan. `inclure_ecartees` reste dans l'API : E4 ne le nomme pas, et des tests s'en servent pour trouver une offre ; sans `etat`, il rend toujours tout.
3. **Les liens d'entrée se traduisent côté serveur.** `etats.etat_du_lien(filtre)` rend l'état d'un statut, et `None` pour `nouveau`, un filtre absent ou inconnu ; la page le reçoit en `data-etat-demande`. Le JavaScript ne traduit jamais un statut en état : `etats.py` reste le seul pont (ADR, § 1). `?atout=` filtre Toutes les offres sur cet atout, nommé dans le résumé.
4. **Trois filtres toujours visibles**, puis la bascule de l'atout : ni bouton « Filtres », ni panneau replié, ni puces. Le résumé nomme les filtres actifs, et « Effacer les filtres » les retire, liste vide ou non. Une réponse plus ancienne que la dernière demande est écartée.
5. **« Chercher une offre »** est la première ligne de « Plus » : elle ouvre Toutes les offres, le curseur dans la recherche. Pas de second champ de recherche.
6. **Une seule ligne d'offre**, `ligneOffre(o, precision)`, pour Toutes les offres et le Bilan : un bouton qui ouvre la fiche, avec l'intitulé, l'employeur, le score, l'état (« Plus tard » pour `a_traiter`, comme la fiche) et, au Bilan, le motif.
7. **Le Bilan garde les tableaux par canal et par famille**, sous l'entonnoir : le canal demandé à « Je l'ai envoyée » ne servirait plus à rien sans eux. Le § 6 ne nomme que l'entonnoir, les sources et les motifs.
8. **Les listes du Bilan se chargent à son ouverture**, repliées, leur nombre dans leur titre. Les archivées comptent comme vues quand on déplie leur liste, pas à l'ouverture du Bilan. La même clé, `veille:archive-vue-le`, garde la dernière visite : la pastille d'un téléphone ne repart pas de zéro.
9. **Les pastilles.** `#pastille-plus` (l'onglet) et `#pastille-criteres` (la ligne « Mes critères ») comptent les propositions à classer ; `#pastille-bilan`, les archivées nouvelles. `compterPastilles()` les recalcule à chaque `rafraichir()`, comme l'archive aujourd'hui : l'onglet dit juste depuis tout écran.
10. **Mes critères** : les offres à classer d'abord (le seul geste qui y attend), puis « Recalculer tous les scores », puis le rappel : les critères se changent dans le `criteres.yaml` de la configuration de l'instance (`VEILLE_CONFIG`), et le recalcul les applique.
11. **Réglages** : le bloc « Notifications » en tête (ce que reçoit cet appareil, et le bouton), « Quitter » au pied, dans son bloc. Les deux sont écrits dans `index.html`, hors de ce que `chargerReglages` réécrit : « Quitter » marche même si `/api/reglages` échoue. Le bouton dit « Activer les notifications », ou « Envoyer une notification d'essai » quand cet appareil les reçoit ; le titre du bloc garde le nom « Notifications ».
12. **Le renvoi à l'ouverture ne demande jamais la permission** : sans geste, Chrome la refuse ou l'ignore. Permission accordée, il renvoie l'abonnement, ou se réabonne s'il n'y en a plus. Il ne dit rien par un message : son résultat se lit dans Réglages, en cinq cas (indisponible, bloquées, inactives, actives, en erreur).
13. **`pushsubscriptionchange`** renvoie le nouvel abonnement, en s'abonnant de nouveau avec la clé de l'ancien s'il n'en porte pas, puis retire l'ancien s'il diffère ; sans l'un ni l'autre, il ne fait rien, et l'ouverture suivante répare.
14. **Le journal et le mail.** Le retrait d'un abonnement et l'absence de tout abonné s'écrivent en avertissement. Quand aucun appareil n'est plus abonné après le push, le dernier retiré à l'instant compris, le mail de repli le dit avec le geste qui répare (`notifications.AUCUN_APPAREIL`), et la ligne `notification` de `veille etat` dit `repli mail (aucun appareil abonné)`.
15. **Le retour d'Android.** Une entrée d'historique par changement de vue, une par ouverture de la fenêtre. Ce que la fenêtre montre ensuite (la fiche, puis « Non », une étape, « Dossier prêt ») n'en ajoute pas : le retour ferme la fenêtre, quoi qu'elle montre (E10). Une vue ouverte juste avant se rejoint par `history.back()` ; l'onglet « À faire » revient à la première entrée (`history.go`), si bien que le retour depuis « À faire » quitte toujours l'application. Un lien d'entrée vers Toutes les offres la pose au-dessus d'« À faire », et l'adresse redevient `/`. Revenue par le retour, une vue se recharge et s'ouvre en haut, comme par son onglet ; la vue sous une fenêtre fermée ne se recharge pas.
16. **Le kit provisoire ne se dit qu'une fois** : quand `kit_provisoire` est vrai, l'étape `pret` ne reprend pas la phrase de `dossier.generer` (`dossier.AVERTISSEMENT_KIT_PROVISOIRE`, texte inchangé) ; le bloc de « Dossier prêt » reste, plus clair.
17. **Le jeu factice ne change pas.** Le staging garde sa base, et ne charge le jeu que dans une base vide : une offre ajoutée à `factice/` n'y paraîtrait pas. Les tests du navigateur inventent leurs offres ; au staging, Edouard fait lui-même une archivée et une close. Toutes les offres du jeu ont une famille : Mes critères y dit « Aucune proposition », et la pastille de « Plus » reste vide, ce que le navigateur vérifie dans les deux sens.
18. **Deux fichiers neufs de tests du navigateur**, `tests_navigateur/test_plus.py` (tâches 3 à 5) et `tests_navigateur/test_retour.py` (tâche 7), chacun avec sa fixture `telephone`, comme les deux fichiers existants, et ses offres inventées par `_inventer` (`test_parcours_candidature.py`), sur un chemin à lui.
19. **Une PR d'implémentation**, `feat/parcours-lot3`, ouverte en brouillon après la tâche 1 pour lire le job `mutation` à chaque envoi, et qui dit « Partie de #15 ». La session la passe prête après la tâche 8, et la fusionne une fois tout vert (mode `session`).

**Hors périmètre :** la base, et les statuts ramenés à cinq (ADR-0003, « Révision ») ; Documents, et Réglages hors de ses deux blocs ; les pistes que garde E12 ; la barrière de chemin par `startswith` (`docs/pistes.md`), dont seuls les tests changent de chemin ; la complétude que `/api/offres` joint encore à chaque offre ; le push réel en CI ; un historique propre à chaque écran de la fenêtre.

## Contraintes globales

- Aucune migration, aucune colonne, aucune variable `VEILLE_*` nouvelle (invariant 6). L'image `0.3.0` lit la base que ce lot laisse ; le retour arrière reste le déploiement de l'étiquette d'avant.
- La traduction statut → état ne vit que dans `etats.py` (ADR, § 1) ; toute logique neuve de domaine y va, gardée par des tests qui tuent ses mutants. mutmut reste limité à `etats.py` et `preparation.py`.
- Le dépôt est public : toute donnée de test est inventée, avec des liens en `exemple.invalid` (M-0001).
- **Les fins de ligne ne se normalisent pas (invariant 7).** Restent en CRLF : `src/veille/static/app.js`, `src/veille/static/style.css`, `src/veille/templates/index.html`, `src/veille/db.py`, `src/veille/dossier.py`, `src/veille/cli.py`, `tests/test_completude.py`, `tests/test_verification.py`, `docs/CANDIDATURE.md`, `docs/CRITERES.md`, `docs/DEMARRAGE.md`, `README.md`. Restent en LF : `src/veille/app.py`, `src/veille/etats.py`, `src/veille/notifications.py`, `src/veille/preparation.py`, `src/veille/completude.py`, `src/veille/static/sw.js`, `tests/test_etats.py`, `tests/test_parcours_api.py`, `tests/test_app.py`, `tests/test_instance.py`, `tests/test_preparation.py`, `tests/test_preparation_api.py`, `tests/test_push_plomberie.py`, `tests/test_notifications.py`, `tests_navigateur/test_cibles_tactiles.py`, `tests_navigateur/test_parcours_candidature.py`, `docs/FONCTIONNEMENT.md`, `docs/exploitation.md`, `docs/pistes.md`, `docs/registre.md`, `CLAUDE.md`. Un fichier neuf est en LF. `tests/test_javascript.py` mêle les deux : on ne le modifie pas. Sous Git Bash, jamais `sed -i` sur un fichier CRLF : l'outil Edit, ou Python en binaire. Avant chaque commit, pour chaque fichier touché, `python -I -c "import sys;b=open(sys.argv[1],'rb').read();print(b.count(b'\r\n'), b.count(b'\n'))" <fichier>` rend deux nombres égaux (CRLF) ou un zéro en premier (LF), comme avant.
- Le JavaScript : toute donnée passe par `echapper()`, un nom dans une adresse par `encodeURIComponent` ; toute route que nomme `app.js` existe ; `node --check` passe sur `app.js` et `sw.js` ; `sw.js` ne porte ni `'fetch'`, ni `"fetch"`, ni `caches.` ; aucun fichier ne nomme un atout ; aucun code du push n'écrit dans la console du navigateur (les tests du navigateur la veulent vide).
- Au téléphone (390 × 844) : toute cible fait au moins 44 px (`DOIGT`), et aucune vue ne défile de côté.
- Le test s'écrit d'abord, et il échoue ; un test qui garde une valeur est éprouvé par un mutant, à la main hors de `etats.py` et de `preparation.py`. La suite du poste : `.venv\Scripts\python -m pytest -q -p no:cacheprovider` ; celle du navigateur : `.venv\Scripts\python -m pytest -q -p no:cacheprovider tests_navigateur`. Une suite lourde à la fois, au premier plan.
- Les fichiers gérés par le modèle ne se modifient pas : `docs/modele/`, `scripts/modele/`, `.githooks/`, `.github/modele/`, `.github/workflows/modele-*.yml`, `tests/deploiement/`.
- Les commits : Conventional Commits, en français, en-tête de 100 caractères au plus, `git add` par chemins, message par fichier (`git commit -F`), les deux lignes d'attribution en pied. Jamais `--no-verify`.

## Points d'attention de la revue

Ce que l'ADR implique sans qu'un critère le nomme, du plus probable au moins probable. Chacun a son test dans la tâche qui possède le code.

1. **Le retour d'Android sur une fenêtre ouverte** : Chrome ferme lui-même la fenêtre modale, sans traverser l'historique ; le retour suivant doit mener à la vue d'avant, jamais toucher dans le vide (tâche 7, `test_echap_ferme_la_fenetre_et_retire_son_entree`, `test_fermer_la_fenetre_retire_son_entree`).
2. **Un téléphone qui a gardé sa permission et perdu son abonnement** (AM-3) : ouvrir l'application le réabonne, et Réglages le dit (tâche 5, `test_sans_abonnement_l_ouverture_se_reabonne`, `test_a_l_ouverture_l_abonnement_existant_est_renvoye`).
3. **Une recherche tapée vite, sur un réseau lent** : la liste montre la dernière demande, jamais une réponse en retard (tâche 4, `test_une_reponse_perimee_ne_remplace_pas_la_liste`).
4. **Un lien d'entrée ancien**, `?filtre=a_traiter` ou `?atout=…`, venu d'un favori ou d'un mail : Toutes les offres filtrée, le filtre nommé et effaçable, et le retour mène à « À faire » (tâche 1, `test_le_lien_d_entree_porte_l_etat_demande` ; tâche 4, `test_un_lien_d_atout_reste_valide` ; tâche 7, `test_un_lien_d_entree_vers_toutes_les_offres_revient_a_a_faire`).
5. **Une offre archivée à tort, remise dans le flux depuis le Bilan** : elle quitte la liste et ne repart jamais seule à l'archive (tâche 3, `test_remettre_dans_le_flux_desarchive_pour_de_bon`).

---

### Tâche 1 : le filtre d'état, côté serveur

**Fichiers :**
- Modifier : `src/veille/etats.py`, `tests/test_etats.py`, `src/veille/db.py` (CRLF), `src/veille/app.py`, `src/veille/templates/index.html` (CRLF), `tests/test_parcours_api.py`

**Interfaces :**
- Produit, dans `etats.py` : `ETATS_FILTRABLES: tuple[str, ...] = ETATS + (MISE_DE_COTE,)` ; `EN_COURS: tuple[str, ...] = ("a_voir", "je_postule", "envoyee", "entretien")` ; `statuts_du_filtre(etat: str | None) -> tuple[str, ...]`, les statuts dans l'ordre de `_ETAT_DU_STATUT`, ceux d'`EN_COURS` pour `None`, et `ValueError(f"état inconnu : {etat!r}")` hors d'`ETATS_FILTRABLES` ; `etat_du_lien(filtre: str | None) -> str | None` (décision 3).
- Produit : `db.lister_offres(..., statuts: Sequence[str] | None = None, ...)` : non nul, `statut IN (…)`, et la clause par défaut tombe ; `GET /api/offres?etat=<filtre>` (décision 2) : un `etat` vide vaut `None`, puis `statuts_du_filtre(etat)` s'applique quand `etat` n'est pas `None`, ou que ni `statut` ni `inclure_ecartees` ne sont donnés ; un `ValueError` rend 400 `état inconnu` ; le `<body>` de la console porte `data-etat-demande="{{ etat_demande or '' }}"`, `etat_demande = etats.etat_du_lien(request.query_params.get("filtre"))`.

- [ ] **Étape 1 : écrire les tests qui échouent.** Dans `tests/test_etats.py` :
  - `test_les_statuts_de_chaque_etat`, paramétré sur la liste écrite en clair : `a_voir` → `("nouveau", "a_traiter")`, `je_postule` → `("interessante",)`, `envoyee` → `("candidature_envoyee", "relance_envoyee", "reponse_recue")`, `entretien` → `("entretien",)`, `close` → `("ecartee", "refus", "accepte")`, `mise_de_cote` → `("differee",)` : `statuts_du_filtre(etat) == statuts`, ordre compris ;
  - `test_sans_etat_le_filtre_rend_les_offres_en_cours` : `statuts_du_filtre(None) == ("nouveau", "a_traiter", "interessante", "candidature_envoyee", "relance_envoyee", "reponse_recue", "entretien")` ;
  - `test_un_etat_inconnu_leve`, paramétré sur `("ecartee", "Close", "", "plus_tard")` : `pytest.raises(ValueError, match="état inconnu")` ;
  - `test_les_filtres_font_le_tour_des_statuts` : les statuts des six filtres, mis bout à bout, donnent chacun des onze `STATUTS` exactement une fois ;
  - `test_un_lien_d_entree_se_traduit_en_etat`, paramétré : `a_traiter` → `a_voir`, `interessante` → `je_postule`, `candidature_envoyee`, `relance_envoyee` et `reponse_recue` → `envoyee`, `entretien` → `entretien`, `ecartee`, `refus` et `accepte` → `close`, `differee` → `mise_de_cote` ;
  - `test_un_lien_vers_la_file_ne_demande_aucun_etat`, paramétré sur `(None, "", "nouveau", "inconnu", "close")` : `None`.
  Dans `tests/test_parcours_api.py`, une offre par statut, faite par `_offre` (le motif des écartées inventé) :
  - `test_le_filtre_d_etat_rend_les_offres_de_cet_etat`, paramétré sur les six filtres et leurs statuts écrits en clair : les ids de `?etat=<filtre>&limite=500` sont exactement ceux des offres de ces statuts, chacune avec son `etat` ;
  - `test_sans_etat_la_liste_rend_les_offres_en_cours` : ni écartée, ni refus, ni acceptée, ni différée ; les sept autres y sont ;
  - `test_un_etat_vide_vaut_aucun_etat` : `?etat=` rend les ids de la liste sans paramètre ;
  - `test_inclure_ecartees_rend_toujours_tout` : les onze ;
  - `test_etat_et_statut_se_combinent` : `?etat=envoyee&statut=reponse_recue` rend la seule `reponse_recue`, `?etat=close&statut=interessante` aucune ;
  - `test_un_etat_inconnu_rend_400` ;
  - `test_une_archivee_reste_hors_du_filtre` : une écartée archivée (`db.archiver`) n'est pas dans `?etat=close` ;
  - `test_le_lien_d_entree_porte_l_etat_demande` : avec une session, `/?filtre=a_traiter` porte `data-etat-demande="a_voir"`, `/?filtre=differee` `data-etat-demande="mise_de_cote"`, et `/`, `/?filtre=nouveau` et `/?filtre=inconnu` `data-etat-demande=""`.
- [ ] **Étape 2 : les lancer.** `.venv\Scripts\python -m pytest -q -p no:cacheprovider tests/test_etats.py tests/test_parcours_api.py`. Attendu : `AttributeError` sur les fonctions absentes, et des listes trop larges.
- [ ] **Étape 3 : écrire le code.** `statuts_du_filtre` filtre `_ETAT_DU_STATUT` sur les états voulus, après le refus d'un état inconnu ; `etat_du_lien` rend `None` pour un filtre vide, `nouveau` ou absent de `_ETAT_DU_STATUT`, sinon son état. Dans `db.lister_offres`, la clause par défaut devient `elif statuts is None and not inclure_ecartees`.
- [ ] **Étape 4 : relancer** ces deux fichiers, puis la suite du poste. Attendu : tous verts, les sauts attendus sous Windows.
- [ ] **Étape 5 : commit.** `git add src/veille/etats.py tests/test_etats.py src/veille/db.py src/veille/app.py src/veille/templates/index.html tests/test_parcours_api.py`, puis `git commit -F <fichier>` : `feat(api): le filtre d'état de Toutes les offres, et les liens d'entrée traduits`.
- [ ] **Étape 6 : la PR en brouillon.** `git push -u origin feat/parcours-lot3`, puis `gh pr create --draft --base principal --body-file <fichier>` : un titre de 93 caractères au plus, « Partie de #15 », la section « Écarts à la spec » avec les décisions 2 (`inclure_ecartees`, promesse : ADR-0003, § 6) et 7 (promesse : ADR-0003, § 6, le Bilan), et la date de l'accord d'Edouard sur ce plan, le corps fini avant la fin de la CI. Lire le job `mutation` (`gh run view <id> --log`) : chaque mutant d'un autre statut que `killed` appelle un test de plus.
- [ ] **Étape 7 : la revue de la tâche**, par un relecteur neuf, avec ce plan, l'ADR-0003 (§§ 1 et 6) et le journal du job `mutation`. Ses corrections sont relues avant la tâche 2.

### Tâche 2 : le push côté serveur (AM-3)

**Fichiers :**
- Modifier : `src/veille/notifications.py`, `tests/test_push_plomberie.py`, `tests/test_notifications.py`

**Interfaces :**
- Produit : `notifications.AUCUN_APPAREIL: str`, mot pour mot : « Aucun appareil n'est abonné aux notifications : elles ne partent plus que par ce mail. Pour les rétablir, ouvre la console sur ton téléphone : si Plus › Réglages › Notifications ne dit pas « Cet appareil reçoit les notifications », touche « Activer les notifications ». » La tâche 5 reprend les deux libellés cités.
- Produit : `envoyer_push` écrit en `WARNING` le retrait d'un abonnement (`abonnement push retire (HTTP %s) : %s | %s`) et l'absence de tout abonné ; `prevenir_nouvelles_offres` relit `db.lister_abonnements()` après un push sans réussite (décision 14).

- [ ] **Étape 1 : écrire les tests qui échouent.** Dans `tests/test_push_plomberie.py`, avec `caplog` sur le journal `veille.notifications` :
  - `test_le_retrait_d_un_abonnement_s_ecrit_en_avertissement`, paramétré sur 404 et 410 : un enregistrement `WARNING` dont le message contient `retire` et le code, et aucun `INFO` sur l'abonnement ;
  - `test_sans_abonne_le_journal_avertit` : `envoyer_push` rend `(0, 0)` et écrit un `WARNING` qui contient `aucun appareil abonne`.
  Dans `tests/test_notifications.py`, les abonnements vidés avant chaque test, `envoyer_push` et `envoyer_mail` remplacés, le corps du mail capté :
  - `test_sans_appareil_abonne_le_mail_le_dit_avec_le_geste` : `(0, 0)`, `base_url="https://console.exemple.invalid"` → `AUCUN_APPAREIL` est dans le corps, après la liste des offres et avant `Console : https://console.exemple.invalid` ; la ligne `notification` de `etat_collecte` vaut `repli mail (aucun appareil abonné)` ;
  - `test_un_appareil_injoignable_ne_dit_pas_qu_aucun_n_est_abonne` : un abonnement inventé (`https://push.exemple.invalid/a`), `(0, 1)` → `AUCUN_APPAREIL` absent, et `repli mail (aucun appareil joignable)` ;
  - `test_le_dernier_abonnement_retire_se_dit_dans_le_mail` : le faux `envoyer_push` retire l'unique abonnement, puis rend `(0, 1)` → `AUCUN_APPAREIL` est dans le corps ;
  - `test_le_geste_nomme_ce_que_reglages_affiche` : `Plus › Réglages › Notifications`, `« Cet appareil reçoit les notifications »` et `« Activer les notifications »` sont dans `AUCUN_APPAREIL`.
- [ ] **Étape 2 : les lancer.** Attendu : les niveaux sont `INFO`, `AUCUN_APPAREIL` n'existe pas.
- [ ] **Étape 3 : écrire le code.** Éprouver les deux tests du journal à la main : remis en `log.info`, chacun échoue.
- [ ] **Étape 4 : relancer** les deux fichiers, puis la suite du poste. Attendu : tous verts.
- [ ] **Étape 5 : commit et envoi.** `git add src/veille/notifications.py tests/test_push_plomberie.py tests/test_notifications.py`, puis `git commit -F <fichier>` : `feat(notifications): la perte d'un abonnement se journalise, et le mail de repli la dit`, puis `git push origin feat/parcours-lot3`.
- [ ] **Étape 6 : la revue de la tâche**, par un relecteur neuf, avec AM-3 (`docs/registre.md`) et le second commentaire de `veille-emploi#15`. Ses corrections sont relues avant la tâche 3.

### Tâche 3 : « Plus », Mes critères, le Bilan et les pastilles

**Fichiers :**
- Modifier : `src/veille/templates/index.html` (CRLF), `src/veille/static/app.js` (CRLF), `src/veille/static/style.css` (CRLF), `tests/test_verification.py` (CRLF), `tests_navigateur/test_parcours_candidature.py`, `tests_navigateur/test_cibles_tactiles.py`
- Créer : `tests_navigateur/test_plus.py`

**Interfaces :**
- Consomme : `GET /api/offres?etat=` (tâche 1) ; `/api/classement`, `/api/classement/valider`, `/api/rescorer`, `/api/entonnoir`, `/api/archive`, `/api/offres/{id}/desarchiver`.
- Produit, dans `index.html` : `<span id="pastille-plus" class="pastille">` dans l'onglet « Plus » ; les lignes Toutes les offres, Mes critères (`data-vue="criteres"`, `#pastille-criteres`), Bilan (`data-vue="bilan"`, `#pastille-bilan`), Documents, Réglages ; `#vue-criteres` (`#contenu-criteres`) et `#vue-bilan` (`#contenu-bilan`), chacune avec « ‹ Plus ».
- Produit, dans `app.js` : `libelleEtat(o) -> string`, que `contenuFiche` reprend ; `ligneOffre(o, precision = '') -> string`, un `<button class="offre ligne-offre" data-action="fiche" data-id>` (décision 6) ; `chargerCriteres()`, `chargerBilan()`, `compterPastilles()` (décisions 8 à 10) ; le geste `data-action="desarchiver"` ; dans le Bilan, `<details class="repli" data-liste="archivees|closes|mises-de-cote">`.
- Part dans cette tâche : les vues et les lignes `relances`, `archive`, `classer` et `pilotage` ; `chargerRelances`, `chargerArchive`, `chargerClasser`, `chargerPilotage`, `chargerPlus` et `compterArchiveNouvelles`, leur code repris par les fonctions neuves ; leurs entrées de `CHARGEURS` et d'`ONGLET_DE_VUE`. Le message de `constater` dit « annulable dans Plus › Bilan ».

- [ ] **Étape 1 : écrire les tests qui échouent.** `tests_navigateur/test_plus.py` : la forme de `test_parcours_candidature.py` (Chromium au téléphone, une session par `auth.ouvrir_session`, aucune erreur dans la console sauf `console_attendue`) ; ses offres inventées par `_inventer(…, "plus", …)` ; toute route à requête simulée par `re.compile`. Les tests :
  - `test_plus_liste_ses_ecrans` : les `.lien-plus`, dans l'ordre, Toutes les offres, Mes critères, Bilan, Documents, Réglages ;
  - `test_la_pastille_de_plus_ne_compte_que_les_offres_a_classer` : `/api/classement` simulé avec deux propositions inventées, `/api/archive` avec `nouvelles: 3` → `#pastille-plus` et `#pastille-criteres` disent « 2 », `#pastille-bilan` « 3 » ; puis zéro proposition → `#pastille-plus` vide et cachée ;
  - `test_mes_criteres_rassemble_le_classement_le_recalcul_et_le_rappel` : la proposition simulée paraît, sa coche et ses preuves ; « Recalculer tous les scores » envoie `POST /api/rescorer` (simulé, `offres_recalculees: 12`), et un message dit « 12 offre(s) recalculée(s) » ; le texte nomme `criteres.yaml` et `VEILLE_CONFIG` ; les trois blocs dans l'ordre de la décision 10 ;
  - `test_valider_un_classement_recalcule_les_pastilles` : « Valider les cochées et rescorer » (simulé), puis `/api/classement` relu à zéro → les deux pastilles vides ;
  - `test_le_bilan_montre_l_entonnoir_puis_trois_listes_repliees` : les titres de bloc, dans l'ordre, Entonnoir, Par canal de candidature, Par famille de métier, Rendement des sources, Motifs d'écartement ; puis trois `details` fermés, chacun avec son nombre dans son résumé ;
  - `test_une_close_montre_son_motif` : une écartée inventée montre son motif, un refus « Refus », une acceptée « Acceptée » ; une mise de côté, son motif ;
  - `test_une_ligne_du_bilan_ouvre_la_fiche` ;
  - `test_remettre_dans_le_flux_desarchive_pour_de_bon` (point d'attention 5) : une offre inventée archivée par `db.archiver` ; « Archivées », « Remettre dans le flux » → `POST …/desarchiver` ; elle quitte la liste ; en base, `archivee_le` est nul et `archive_protegee` vaut 1 ;
  - `test_un_bilan_ouvert_sans_deplier_les_archivees_garde_la_pastille` : stockage local vide, `/api/archive` simulé (`nouvelles: 2`) → Bilan ouvert, la clé `veille:archive-vue-le` absente, `#pastille-bilan` « 2 » ;
  - `test_deplier_les_archivees_eteint_la_pastille_du_bilan` : déplier → la clé est posée, et `/api/archive`, simulé à zéro dès qu'il reçoit `depuis`, vide la pastille ;
  - `test_mes_criteres_et_le_bilan_se_touchent_du_doigt_et_tiennent_dans_l_ecran` : chaque `button`, `summary`, `a` et `label` visible des deux écrans fait au moins `DOIGT` ; avec une close à l'intitulé `LONG`, `scrollWidth` reste dans les 390 px.
  Les tests existants suivent : `test_plus_mene_aux_anciens_ecrans` devient `test_plus_mene_a_ses_ecrans` (le Bilan, puis « ‹ Plus ») ; `test_plus_se_touche_du_doigt_et_tient_dans_l_ecran` compte cinq lignes ; tout `get_by_role("button", name="Plus", exact=True)` vise `.onglet[data-vue="plus"]` ; `test_les_compteurs_et_les_titres_ont_leurs_finitions` lit `#pastille-plus` au lieu de `#pastille-relances` ; `test_la_page_principale_repond` (`tests/test_verification.py`) attend `data-vue="bilan"`.
- [ ] **Étape 2 : les lancer.** `.venv\Scripts\python -m pytest -q -p no:cacheprovider tests_navigateur`. Attendu : les tests neufs et adaptés échouent ; les autres passent.
- [ ] **Étape 3 : écrire l'interface.** Le Bilan charge ensemble `/api/entonnoir`, `/api/archive`, `?etat=close` et `?etat=mise_de_cote` ; une archivée est un `<article class="offre archivee" data-id>` avec son titre (`data-action="fiche"`), « disparue vers le », « Pourquoi elle est ici », « Remettre dans le flux » et « Ouvrir l'annonce › ». Le `toggle` de la liste des archivées, ouverte, appelle `marquerArchiveVue()` puis `compterPastilles()`. Une remise dans le flux recharge le Bilan, la liste des archivées gardée ouverte. `rafraichir()` appelle `compterPastilles()` à la place de `compterArchiveNouvelles()`, et `CHARGEURS.plus` devient une fonction vide : sans elle, `rafraichir()` retomberait sur `chargerOffres`.
- [ ] **Étape 4 : relancer** les tests du navigateur, `node --check src/veille/static/app.js`, `tests/test_javascript.py` et `tests/test_verification.py`. Attendu : tous verts.
- [ ] **Étape 5 : commit et envoi.** `git add` des fichiers de la tâche, par chemins, puis `git commit -F <fichier>` : `feat(console): « Plus » devient une liste, avec Mes critères et le Bilan`, puis `git push origin feat/parcours-lot3`.
- [ ] **Étape 6 : la revue de la tâche**, par un relecteur neuf, avec l'ADR-0003, § 6, et E7 à E9. Ses corrections sont relues avant la tâche 4.

### Tâche 4 : Toutes les offres et ses trois filtres

**Fichiers :**
- Modifier : `src/veille/templates/index.html` (CRLF), `src/veille/static/app.js` (CRLF), `src/veille/static/style.css` (CRLF), `tests_navigateur/test_plus.py`, `tests_navigateur/test_parcours_candidature.py`, `tests_navigateur/test_cibles_tactiles.py`

**Interfaces :**
- Consomme : `GET /api/offres?etat=` et `data-etat-demande` (tâche 1) ; `ligneOffre`, `libelleEtat` (tâche 3).
- Produit, dans `#vue-offres` : `#f-recherche` (`type="search"`, `aria-label="Chercher une offre"`), `#f-etat` (`""` « En cours », puis `a_voir`, `je_postule`, `envoyee`, `entretien`, `close`, `mise_de_cote` « Mises de côté »), `#f-famille`, `#btn-atout`, `#resume-offres`, `#liste-offres` ; dans « Plus », en tête, `<button class="lien-plus" data-vue="offres" data-chercher>Chercher une offre</button>`.
- Produit, dans `app.js` : `let atoutFiltre = ''` ; `filtresActifs() -> {cle, libelle, valeur}[]` ; `parametresOffres() -> URLSearchParams` ; `effacerFiltres()` ; `chargerOffres()`, qui écarte une réponse plus ancienne que la dernière demande (`numeroOffres`).
- Part dans cette tâche : `#btn-filtres`, `#compte-filtres`, `#btn-documenter`, `#puces-filtres` et `#panneau-filtres` (`#f-statut`, `#f-zone`, `#f-atout`, `#f-verification`, `#f-tri`, `#f-ecartees`, `#btn-rescorer`) ; `CHAMPS_FILTRES`, `libelleValeur`, `synchroniserFiltres`, `effacerFiltre`, `surTelephone`, `aDocumenter` et leurs écouteurs. `chargerOffres` n'envoie plus ni `statut`, ni `zone`, ni `inclure_ecartees`, ni `a_documenter`, ni `verification`, ni `tri`.

- [ ] **Étape 1 : écrire les tests qui échouent**, dans `tests_navigateur/test_plus.py` :
  - `test_toutes_les_offres_n_a_que_trois_filtres_et_la_bascule` : `#vue-offres` a trois champs, `#f-recherche`, `#f-etat` et `#f-famille`, et `#btn-atout` visible (l'exemple a un atout mis en avant) ; aucun des identifiants retirés n'est dans la page ;
  - `test_les_options_d_etat_sont_les_cinq_et_les_mises_de_cote` : les valeurs de `#f-etat` sont `["", *etats.ETATS_FILTRABLES]` ;
  - `test_le_filtre_d_etat_part_au_serveur` : « Close » → la requête porte `etat=close`, et aucun des paramètres qui ne partent plus ; les lignes disent « Close » ;
  - `test_une_ligne_porte_titre_employeur_score_et_etat_et_ouvre_la_fiche` ;
  - `test_la_recherche_n_envoie_qu_une_requete_par_pause` : `press_sequentially("abc", delay=40)` → `expect_request` voit `recherche=abc` ; 600 ms plus tard, aucune requête n'a porté `recherche=a` ni `recherche=ab` ;
  - `test_une_reponse_perimee_ne_remplace_pas_la_liste` (point d'attention 3) : la requête `recherche=ab` retenue par `page.route`, puis `recherche=abc` servie (une offre inventée B) ; la première, libérée ensuite (une offre A), ne remplace pas la liste : B seule ;
  - `test_les_filtres_actifs_se_disent_et_s_effacent` : recherche, état et famille → le résumé les nomme ; « Effacer les filtres » vide les trois, et la requête suivante n'en porte aucun ;
  - `test_la_bascule_de_l_atout_filtre_sur_l_atout_mis_en_avant` : `aria-pressed="true"` et `atout=<cle>`, la clé lue dans `data-atout` ; un second toucher retire le filtre ;
  - `test_un_lien_d_atout_reste_valide` (point d'attention 4) : `/?atout=<cle>` ouvre Toutes les offres, la requête porte `atout=<cle>`, le résumé le nomme, et « Effacer les filtres » le retire ;
  - `test_un_lien_d_etat_ouvre_toutes_les_offres_filtree` : `/?filtre=differee` → `#f-etat` vaut `mise_de_cote` ;
  - `test_sans_filtre_une_liste_vide_dit_ou_sont_les_closes` : `/api/offres` simulé vide → « Aucune offre en cours. Les closes et les mises de côté se voient par le filtre d'état. » ;
  - `test_chercher_une_offre_ouvre_la_recherche` : « Chercher une offre » → `#vue-offres` visible, `document.activeElement.id == "f-recherche"` ; et `test_plus_liste_ses_ecrans` attend six lignes, « Chercher une offre » en tête ;
  - `test_toutes_les_offres_se_touche_du_doigt_et_tient_dans_l_ecran` : lignes, champs, bascule et « ‹ Plus » d'au moins `DOIGT` ; avec un intitulé `LONG`, `scrollWidth` dans les 390 px.
  Les tests existants suivent : `test_un_autre_filtre_mene_a_toutes_les_offres` attend `#f-etat` à `je_postule` ; `test_les_offres_sous_le_seuil_menent_a_toutes_les_offres`, `#f-etat` à `a_voir`. Dans `test_cibles_tactiles.py`, la fixture attend `#liste-offres .ligne-offre` ; `test_les_boutons_d_une_offre_se_touchent_du_doigt` devient `test_les_lignes_des_offres_se_touchent_du_doigt` ; `test_les_filtres_se_touchent_du_doigt` mesure les trois champs et la bascule ; `test_le_panneau_des_filtres_tient_dans_l_ecran` devient `test_les_filtres_tiennent_dans_l_ecran`, la famille au libellé le plus long choisie ; `test_pourquoi_ce_score_s_ouvre_du_doigt_sans_deplacer_la_carte` part avec la carte (la fiche porte ce volet, mesuré par `test_les_boutons_de_la_fiche_se_touchent_du_doigt`) ; `#btn-filtres` et `#compte-filtres` quittent leurs tests.
- [ ] **Étape 2 : les lancer.** Attendu : les tests neufs et adaptés échouent.
- [ ] **Étape 3 : écrire l'interface.** Le résumé : « N offre(s), dont M au-dessus du seuil de S. », puis les filtres actifs et « Effacer les filtres ». `liensVersToutes` pose `#f-etat` à `a_voir` et vide les autres filtres. À l'entrée, `data-etat-demande` pose `#f-etat`, `?atout=` pose `atoutFiltre`, et l'un ou l'autre ouvre Toutes les offres.
- [ ] **Étape 4 : relancer** les tests du navigateur, `node --check`, `tests/test_javascript.py`. Attendu : tous verts.
- [ ] **Étape 5 : commit et envoi.** `git add` des fichiers de la tâche, puis `git commit -F <fichier>` : `feat(console): Toutes les offres, en lignes, avec trois filtres`, puis `git push origin feat/parcours-lot3`.
- [ ] **Étape 6 : la revue de la tâche**, par un relecteur neuf, avec E2, E3 et E5. Ses corrections sont relues avant la tâche 5.

### Tâche 5 : Réglages, l'en-tête et le push côté client

**Fichiers :**
- Modifier : `src/veille/templates/index.html` (CRLF), `src/veille/static/app.js` (CRLF), `src/veille/static/style.css` (CRLF), `src/veille/static/sw.js`, `tests/test_notifications.py`, `tests_navigateur/test_plus.py`, `tests_navigateur/test_cibles_tactiles.py`
- Créer : `tests/test_service_worker.py`

**Interfaces :**
- Consomme : `POST` et `DELETE /api/push/abonnement`, `POST /api/push/test` ; `notifications.AUCUN_APPAREIL` (tâche 2).
- Produit, dans `index.html` : `.barre` ne porte que `<h1>Veille emploi</h1>` ; `#vue-reglages` : « ‹ Plus », `#bloc-notifications` (`<h2>Notifications</h2>`, `#etat-push`, `#btn-push`), `#contenu-reglages`, puis un bloc « Quitter » avec `<form action="/deconnexion" method="post">` et son bouton.
- Produit, dans `app.js` : `const ETATS_PUSH`, les cinq phrases de la décision 12, dont « Cet appareil reçoit les notifications. » et « Cet appareil ne reçoit pas les notifications. » ; `let etatPush = {cle, detail}` ; `enregistrerServiceWorker() -> Promise<ServiceWorkerRegistration | null>` ; `synchroniserPush() -> Promise<string>`, lancée une fois au démarrage ; `afficherEtatPush()`, appelée par `chargerReglages`, `synchroniserPush` et `activerPush`. Indisponible : pas de contexte sûr, ni `navigator.serviceWorker`, ni `PushManager`, ni `Notification`, ni clé VAPID.
- Produit, dans `sw.js` : un écouteur `pushsubscriptionchange`, qui appelle `renouvelerAbonnement(evenement) -> Promise<void>` sous `waitUntil` (décision 13), ses écritures `credentials: 'same-origin'`.

- [ ] **Étape 1 : écrire les tests qui échouent.** Dans `tests_navigateur/test_plus.py`, une fixture `cles_push` (`notifications.generer_vapid("mailto:camille@exemple.invalid")` si `CHEMIN_VAPID` manque) et une aide `simuler_push(page, permission, abonnement)`, par `add_init_script` : `Object.defineProperty(Notification, 'permission', …)`, `Notification.requestPermission` qui compte ses appels, `PushManager.prototype.getSubscription` et `.subscribe`, qui notent leurs options et rendent des abonnements inventés (`https://push.exemple.invalid/…`, avec `toJSON()`). Les tests :
  - `test_l_en_tete_ne_garde_que_le_titre` : `.barre` porte « Veille emploi », aucun `button`, aucun `form` ;
  - `test_reglages_porte_notifications_en_tete_et_quitter_au_pied` ;
  - `test_quitter_ferme_la_session` : « Quitter » mène à `/connexion`, et `/` y renvoie ensuite ;
  - `test_a_l_ouverture_l_abonnement_existant_est_renvoye` (point d'attention 2) : permission `granted`, un abonnement → un seul `POST /api/push/abonnement`, son corps égal à `toJSON()` ; `subscribe` jamais appelé ; Réglages dit « Cet appareil reçoit les notifications. », et le bouton « Envoyer une notification d'essai » ;
  - `test_sans_abonnement_l_ouverture_se_reabonne` (point d'attention 2) : `getSubscription` rend `null` → `subscribe` appelé une fois, `userVisibleOnly` vrai, une clé de 65 octets ; le `POST` porte le nouvel abonnement ;
  - `test_sans_permission_l_ouverture_ne_demande_rien` : `default` → aucun `POST`, `requestPermission` jamais appelée ; Réglages dit « Cet appareil ne reçoit pas les notifications. » ;
  - `test_des_notifications_bloquees_se_disent` : `denied` → la phrase qui dit comment les débloquer ;
  - `test_sans_push_reglages_dit_indisponible` : `delete window.PushManager` → la phrase d'indisponibilité, aucun `POST`, aucune erreur ;
  - `test_un_renvoi_en_echec_se_dit_dans_reglages` : le `POST` simulé en 500 → la phrase d'erreur (`console_attendue` : « 500 ») ;
  - `test_activer_les_notifications_abonne_puis_envoie_un_essai` : `default`, puis `requestPermission` rend `granted` → `subscribe`, `POST /api/push/abonnement`, puis `POST /api/push/test` (simulé), dans cet ordre ; Réglages dit qu'il les reçoit ;
  - `test_reglages_se_touche_du_doigt_et_tient_dans_l_ecran`.
  Dans `tests/test_service_worker.py`, un harnais Node charge `sw.js` avec un faux `self` (ses écouteurs notés, `registration.pushManager.subscribe` simulé) et un faux `fetch` qui note ses appels ; sans Node, le test se saute :
  - `test_un_nouvel_abonnement_est_renvoye_puis_l_ancien_retire` : `POST /api/push/abonnement` avec le JSON du nouveau, puis `DELETE /api/push/abonnement?endpoint=<ancien, encodé>`, dans cet ordre ;
  - `test_sans_nouvel_abonnement_le_service_worker_se_reabonne_avec_la_cle_d_avant` : `subscribe` reçoit `userVisibleOnly: true` et l'`applicationServerKey` de l'ancien ;
  - `test_le_meme_abonnement_n_est_pas_retire` ;
  - `test_sans_rien_a_renvoyer_le_service_worker_ne_fait_rien`.
  Dans `tests/test_notifications.py`, `test_le_geste_du_mail_nomme_ce_que_reglages_affiche` : « Cet appareil reçoit les notifications » et « Activer les notifications » sont dans `app.js` ou `index.html`. Dans `test_cibles_tactiles.py`, `test_les_boutons_de_la_barre_se_touchent_du_doigt` devient `test_les_boutons_de_reglages_se_touchent_du_doigt` (`#btn-push`, le bouton de `form[action='/deconnexion']`).
- [ ] **Étape 2 : les lancer.** Attendu : les tests neufs échouent.
- [ ] **Étape 3 : écrire le code.** `activerPush` garde son ordre (permission, abonnement, enregistrement, essai) et dit ses refus en phrases accentuées, sans la console du tailnet ; le bloc de démarrage qui enregistrait le service worker cède la place à `synchroniserPush()`. `sw.js` reste sans `'fetch'`, `"fetch"` ni `caches.`.
- [ ] **Étape 4 : relancer** les tests du navigateur, puis la suite du poste (`tests/test_javascript.py` compris), `node --check` sur `app.js` et `sw.js`. Attendu : tous verts.
- [ ] **Étape 5 : commit et envoi.** `git add` des fichiers de la tâche, puis `git commit -F <fichier>` : `feat(console): les notifications et « Quitter » dans Réglages, l'abonnement renvoyé à l'ouverture`, puis `git push origin feat/parcours-lot3`.
- [ ] **Étape 6 : la revue de la tâche**, par un relecteur neuf, avec E11 et le second commentaire de `veille-emploi#15`. Ses corrections sont relues avant la tâche 6.

### Tâche 6 : le retrait de ce qui ne sert plus

**Fichiers :**
- Modifier : `src/veille/static/app.js` (CRLF), `src/veille/templates/index.html` (CRLF), `src/veille/static/style.css` (CRLF), `src/veille/app.py`, `src/veille/db.py` (CRLF), `src/veille/dossier.py` (CRLF), `src/veille/preparation.py`, `src/veille/completude.py`, `tests/test_app.py`, `tests/test_completude.py` (CRLF), `tests/test_verification.py` (CRLF), `tests/test_instance.py`, `tests/test_preparation.py`, `tests/test_preparation_api.py`, `tests/test_parcours_api.py`

**Interfaces :**
- Produit : `dossier.AVERTISSEMENT_KIT_PROVISOIRE: str`, la phrase actuelle, telle quelle, que `generer` emploie ; l'étape `pret` sans elle quand `kit_provisoire` est vrai (décision 16).
- Part : `carteOffre`, `pastilleVerification`, `etatVerification`, `ageEnJours`, `pastilleCompletude`, `afficherDossier`, `afficherCompletudeInsuffisante`, `genererDossier`, `demanderMotif`, `offresCourantes`, et les gestes `dossier`, `statut`, `ecarter` et `obsolete` du gestionnaire de clics ; dans `api_offres`, `verification`, `tri`, `a_documenter`, `a_travailler` et la clé `a_documenter` ; `api_dossier` ; `api_relances` ; `statuts`, `zones` et `atouts` du contexte de la page ; dans `db.lister_offres`, `verification`, `tri` et leurs clauses (l'ordre devient `score DESC, date_collecte DESC`) ; les règles de `style.css` qui ne servent plus.

- [ ] **Étape 1 : écrire les tests qui échouent, et déplacer ceux qui passaient par ce qui part.**
  - `test_les_routes_retirees_n_existent_plus` (`tests/test_parcours_api.py`) : ni `POST /api/offres/{offre_id}/dossier` ni `GET /api/relances` dans `app.routes` ; avec une session, `POST /api/offres/1/dossier` et `GET /api/relances` ne rendent pas 200 ;
  - `test_les_parametres_retires_ne_sont_plus_lus` : `inspect.signature` de `api_offres` sans `verification`, `tri` ni `a_documenter`, celle de `db.lister_offres` sans `verification` ni `tri` ;
  - `test_la_liste_ne_porte_plus_le_compte_a_documenter` : la clé `a_documenter` absente de `/api/offres` ;
  - `test_le_kit_provisoire_ne_se_dit_qu_une_fois` (`tests/test_preparation.py`) : le faux `generer` rend `kit_provisoire=True` et `avertissements=[dossier.AVERTISSEMENT_KIT_PROVISOIRE, "avertissement inventé"]` → l'étape porte `["avertissement inventé"]` et `kit_provisoire` vrai ; et `test_sans_kit_provisoire_les_avertissements_restent_entiers` : `["a inventé", "b inventé"]`, rendus tels quels ;
  - `tests/test_app.py` : `test_generation_du_dossier` devient `test_la_preparation_rend_un_dossier_provisoire_et_son_paquet` (l'offre remise en `nouveau`, `POST …/preparer {"forcer": true}` → `pret`, `kit_provisoire` vrai, aucun avertissement égal à la phrase du kit, le paquet commence par `PK`) ; `test_dossier_refuse_de_sortir_de_son_repertoire` et `test_un_dossier_d_une_autre_arborescence_s_ouvre_par_son_nom` font leur dossier de même, leurs assertions inchangées ;
  - `tests/test_preparation_api.py` : `test_l_ancien_generer_le_dossier_note_aussi_le_destinataire` devient `test_un_destinataire_enregistre_sans_regenerer_se_dit_sur_dossier_pret`, le dossier fait par `/preparer` avec `forcer`, ses assertions gardées dès le destinataire changé ;
  - `tests/test_instance.py` : l'ancienne route quitte `GESTES_SUR_UNE_OFFRE` (`test_preparer_refuse_sans_configuration_designee` garde la nouvelle) ;
  - supprimés : `test_le_filtre_isole_le_bon_couple` et `test_le_compte_est_rendu_avec_la_liste` (`tests/test_completude.py`, avec `client_completude` s'il ne sert plus), `test_on_peut_isoler_ce_qui_na_jamais_ete_verifie` et `test_le_tri_par_verification_met_les_jamais_vues_en_tete` (`tests/test_verification.py`).
- [ ] **Étape 2 : les lancer.** Attendu : les quatre tests neufs échouent ; les tests déplacés passent déjà.
- [ ] **Étape 3 : retirer.** Une règle de `style.css` ne part qu'après un Grep de sa classe ou de son identifiant sur `app.js` et `index.html` qui ne trouve rien (`.barre-actions`, `.puces`, `.puce`, `.filtres`, `.case`, `.verif`, `.completude`… ; `button.bascule` reste). L'import de `STATUTS` reste s'il sert encore (`api_statut`). La docstring de `completude.py` ne nomme plus l'ancien geste.
- [ ] **Étape 4 : vérifier.** L'outil Grep, motif `genererDossier|carteOffre|afficherDossier|afficherCompletudeInsuffisante|demanderMotif|a_documenter|/api/relances|data-action="(dossier|statut|ecarter|obsolete)"|anciens écrans|jusqu'au lot 3`, sur `src/`, `tests/` et `tests_navigateur/` : rien. Puis la suite du poste, celle du navigateur, `node --check`. Attendu : tous verts.
- [ ] **Étape 5 : commit et envoi.** `git add` des fichiers de la tâche, puis `git commit -F <fichier>` : `refactor(console): retirer les anciennes vues, leurs paramètres et leurs routes`, puis `git push origin feat/parcours-lot3`, et le job `mutation` lu.
- [ ] **Étape 6 : la revue de la tâche**, par un relecteur neuf, qui cherche aussi les mots retirés dans tout le dépôt. Ses corrections sont relues avant la tâche 7.

### Tâche 7 : le retour d'Android

**Fichiers :**
- Modifier : `src/veille/static/app.js` (CRLF), `tests_navigateur/test_parcours_candidature.py` si un test y suppose une vue sans historique
- Créer : `tests_navigateur/test_retour.py`

**Interfaces :**
- Produit, dans `app.js` : `afficherVue(nom, { historique = true } = {})`, qui pose `{vue, precedente, profondeur}` par `history.pushState` quand la vue change ; `allerA(nom)`, le gestionnaire de tout `[data-vue]` (décision 15), qui garde le curseur que `data-chercher` pose dans la recherche ; `ouvrirFenetre()`, seule à appeler `showModal()`, qui ajoute `fenetre: true` à une entrée neuve ; un écouteur `close` de `#fenetre`, qui lance `history.back()` quand l'entrée courante porte `fenetre`, et `retourDeFermeture` ; un écouteur `popstate`, qui ignore le retour lancé par `close`, ferme la fenêtre ouverte, et montre la vue de l'entrée si elle diffère, sans la pousser.
- À l'entrée : une entrée qui porte déjà `vue` (un rechargement) la montre, sans `fenetre` ; sinon `history.replaceState({vue: 'a-faire', precedente: null, profondeur: 0}, '', '/')`, puis, pour un lien d'entrée, Toutes les offres poussée au-dessus.

- [ ] **Étape 1 : écrire les tests qui échouent**, dans `tests_navigateur/test_retour.py` (même forme que `test_plus.py`, ses offres inventées sur le chemin `retour`, `/preparer` simulé comme `_simuler_preparation`) :
  - `test_le_retour_ferme_la_fiche` : une fiche ouverte depuis « À faire » ; `go_back` → la fenêtre fermée, « À faire » visible ; un second `go_back` mène à `/sante` ;
  - `test_le_retour_ferme_le_panneau_non` et `test_le_retour_ferme_une_etape_de_la_preparation` (l'étape `texte`) ;
  - `test_le_retour_revient_a_la_vue_d_avant` : « Plus », Bilan ; `go_back` → « Plus » ; `go_back` → « À faire » ; `go_back` → `/sante` ;
  - `test_le_retour_depuis_a_faire_quitte_la_console` : `/sante`, puis `/` ; `go_back` → `/sante` ;
  - `test_l_onglet_a_faire_revient_a_la_racine` : « Candidatures », « Plus », Toutes les offres, puis l'onglet « À faire » ; `go_back` → `/sante` ;
  - `test_fermer_la_fenetre_retire_son_entree` (point d'attention 1) : « Candidatures », une fiche, « Fermer » ; `go_back` → « À faire » ;
  - `test_echap_ferme_la_fenetre_et_retire_son_entree` (point d'attention 1) : une fiche, Échap ; `go_back` → la vue d'avant ;
  - `test_une_fiche_rouverte_aussitot_se_ferme_au_retour` : « Fermer » puis une autre ligne touchée dans le même `evaluate` ; la seconde fiche ouverte ; `go_back` la ferme, sur la même vue ;
  - `test_un_lien_d_entree_vers_toutes_les_offres_revient_a_a_faire` (point d'attention 4) : `/?filtre=interessante` → Toutes les offres, l'adresse `/` ; `go_back` → « À faire » ;
  - `test_un_rechargement_garde_la_vue` : « Plus », Bilan, `reload` → Bilan ; `go_back` → « Plus » ;
  - `test_la_vue_sous_une_fenetre_fermee_ne_se_recharge_pas` : une fiche, `go_back` → aucune requête `/api/a-faire` entre le retour et la fenêtre fermée.
- [ ] **Étape 2 : les lancer.** Attendu : les tests neufs échouent ; un retour quitte la console.
- [ ] **Étape 3 : écrire le code.** Chaque `showModal()` passe par `ouvrirFenetre()` (`ouvrirFiche`, `demanderNon`, `montrerEtape`, `demanderCanal`, `ouvrirDetail`, `ouvrirEntretien`, `ouvrirRelance`).
- [ ] **Étape 4 : relancer** les tests du navigateur, tous, et `node --check`. L'outil Grep, motif `showModal\(` sur `app.js` : une seule ligne. Attendu : tous verts.
- [ ] **Étape 5 : commit et envoi.** `git add src/veille/static/app.js tests_navigateur/test_retour.py` (et `test_parcours_candidature.py` s'il a changé), puis `git commit -F <fichier>` : `feat(console): le retour d'Android ferme la fenêtre, puis revient à la vue d'avant`, puis `git push origin feat/parcours-lot3`.
- [ ] **Étape 6 : la revue de la tâche**, par un relecteur neuf, avec E10 et le premier commentaire de `veille-emploi#15`. Ses corrections sont relues avant la tâche 8.

### Tâche 8 : la documentation et les messages

**Fichiers :**
- Modifier : `docs/FONCTIONNEMENT.md`, `docs/CANDIDATURE.md` (CRLF), `docs/CRITERES.md` (CRLF), `docs/DEMARRAGE.md` (CRLF), `docs/exploitation.md`, `docs/pistes.md`, `CLAUDE.md`, `src/veille/cli.py` (CRLF), et `README.md` (CRLF) si le Grep y trouve un écran retiré

- [ ] **Étape 1 : chercher.** L'outil Grep sur `docs/` (hors `docs/decisions/` et `docs/modele/`), `README.md`, `CLAUDE.md` et `src/`, motif `Pilotage|À classer|Archive|Relances|documenter|Toutes les offres|Recalculer|Notifications|Quitter|écartées|Filtres|anciens écrans|lot 3|retour d'Android`.
- [ ] **Étape 2 : réécrire.**
  - `docs/FONCTIONNEMENT.md` : la ligne « Plus » du tableau nomme les six lignes ; un paragraphe dit Toutes les offres (les trois filtres, « En cours » par défaut), Mes critères, le Bilan et sa pastille, Réglages, et le retour d'Android ; « Les notifications » dit l'état de l'appareil dans Réglages, le renvoi à l'ouverture et le mail qui dit qu'aucun appareil n'est abonné.
  - `docs/CANDIDATURE.md` : la relance « dans *Plus › Relances* » devient « en tête d'« À finir », et sur la ligne « Envoyée » de « Candidatures » » ; le paragraphe des anciens écrans et de leur « Générer le dossier » part ; « La conséquence pratique » ne parle plus d'un filtre : « Je postule » demande le texte d'une offre mal documentée.
  - `docs/CRITERES.md` : le bouton **Recalculer** devient « Recalculer tous les scores », dans *Plus › Mes critères* ; *Plus › Pilotage* devient *Plus › Bilan*.
  - `docs/DEMARRAGE.md` : le bouton **Notifications** devient *Plus › Réglages*, « Activer les notifications ».
  - `docs/exploitation.md` : le bouton « Recalculer » devient « Recalculer tous les scores » (*Plus › Mes critères*).
  - `docs/pistes.md` : les pistes de l'ancien « Générer le dossier » et du kit provisoire annoncé deux fois sortent ; celles des avertissements recalculés et du « Régénérer » visible perdent « ou le lot 3 » de leur déclencheur.
  - `src/veille/cli.py` : « Plus › Archive » devient « Plus › Bilan », et « appuyer sur 'Notifications' » devient « Plus › Réglages, « Activer les notifications » ».
  - `CLAUDE.md`, « État » : une phrase par écran neuf, le push et le retour ; « Jusqu'au lot 3, le retour d'Android quitte l'application » et l'ancien « Générer le dossier » des anciens écrans partent. « Commandes » : la ligne de `tests_navigateur/` nomme `test_plus.py` et `test_retour.py`.
- [ ] **Étape 3 : vérifier.** `python -X utf8 -B scripts/modele/documentation.py` rend 0 ; la suite du poste reste verte (`cli.py` a changé) ; les fins de ligne sont inchangées.
- [ ] **Étape 4 : commit et envoi.** `git add` des fichiers changés, par chemins, puis `git commit -F <fichier>` : `docs: l'écran « Plus », les filtres, le retour et les notifications (lot 3 de l'ADR-0003)`, puis `git push origin feat/parcours-lot3`.
- [ ] **Étape 5 : la revue de la tâche**, par un relecteur neuf, qui cherche les mots retirés dans tout le dépôt. Ses corrections sont relues avant la PR prête.

### Tâche 9 : la PR prête, la revue finale et le staging

- [ ] **Étape 1 : la PR prête.** `gh pr ready <n>`. Attendre tous les contrôles verts, `mutation`, `navigateur` et `texte-pr` compris ; le journal du job `mutation` ne liste que des mutants `killed`, et celui du job `verifier` montre `tests/test_service_worker.py` passé.
- [ ] **Étape 2 : la revue finale**, par un relecteur neuf sur le modèle le plus capable, sur tout le diff du lot, avec l'ADR-0003, ce plan, `veille-emploi#15` et le journal du job `mutation`.
- [ ] **Étape 3 : les corrections**, en une vague, puis leur relecture par un relecteur neuf, sur le diff des corrections. La session fusionne ensuite : `gh pr merge <n> --squash --match-head-commit <sha>`, depuis le clone, sans `cd`.
- [ ] **Étape 4 : 👤 le staging, au téléphone.** Il se redéploie seul depuis `principal`. Edouard vérifie :
  - l'en-tête ne porte que « Veille emploi » ; « Plus » a six lignes, sans pastille (le jeu n'a rien à classer) ;
  - « Chercher une offre » ouvre le clavier dans la recherche, et deux lettres filtrent la liste ;
  - Toutes les offres : trois filtres et la bascule de l'atout ; « Close » montre les écartées du jeu ; une ligne ouvre sa fiche ; « Effacer les filtres » ;
  - sur une offre « À voir », « Non », puis « N'est plus en ligne » : la ligne « Bilan » porte une pastille ; le Bilan montre l'entonnoir, les sources, les motifs, puis trois listes repliées ; « Archivées », dépliée, montre l'offre et éteint la pastille ; « Remettre dans le flux » la renvoie dans « À faire » ;
  - sur l'offre « Envoyée » du jeu, « Réponse : Refus » : *Bilan › Closes* la montre, « Refus » ;
  - Mes critères : « Aucune proposition », « Recalculer tous les scores » dit le nombre d'offres recalculées, et le rappel nomme `criteres.yaml` ;
  - Réglages : « Notifications » en tête ; l'état dit si le téléphone les reçoit ; sinon, « Activer les notifications », l'autorisation, la notification d'essai arrive et l'état le dit ; l'application fermée puis rouverte, il le dit encore ; « Quitter », au pied, mène à la connexion ;
  - le retour d'Android : il ferme une fiche, le panneau « Non » et l'étape « Il manque le texte de l'annonce » ; depuis le Bilan, il revient à « Plus », puis à « À faire », puis quitte l'application ; après « Fermer » sur une fiche, un seul retour mène à la vue d'avant ;
  - une notification d'essai touchée ouvre « À faire ».

### Tâche 10 : la clôture

- [ ] **Étape 1 : la PR de clôture.** Elle supprime ce plan ; reporte dans `CLAUDE.md` ce qui doit survivre (l'état du lot 3, la ligne « Prochain » : 👤 `v0.4.0`, puis la fin du mode systemd) ; relit le README d'après `docs/modele/documentation.md` ; clôt AM-3 dans `docs/registre.md` (la PR, et le test qui garde le renvoi à l'ouverture) ; coche les critères de `veille-emploi#15` ; porte « Closes #15 », la section « Écarts à la spec » (les décisions 2 et 7, avec leur accord) et la ligne `Tête relue : <SHA>` de la tête qu'a lue sa dernière relecture.
- [ ] **Étape 2 : 👤 l'étiquette `v0.4.0`**, sur le commit de la clôture, posée par Edouard. Puis, depuis le poste, `/sante` de la prod rend `"version":"0.4.0"`, et `modele-version` a publié l'image `0.4.0`.

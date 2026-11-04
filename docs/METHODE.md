# Pourquoi ce projet se teste sur de vraies annonces, tôt

Ce document existe pour que la méthode survive aux sessions suivantes. Ce n'est
pas une préférence de style : quatre défauts de scoring, qu'aucune relecture
n'aurait attrapés, ont été trouvés en faisant tourner la chaîne sur un corpus
réel dès le premier jour.

Les faits de la recherche réelle que ces leçons racontaient (le domaine métier
en cause, les mots exacts) sont dans
le `docs/METHODE.md` du dépôt de données.

**Un scoring écrit sans corpus réel se trompe silencieusement.** Il ne plante
pas, ne lève aucune exception, ne fait échouer aucun test unitaire. Il classe
mal, et personne ne le voit — surtout pas l'utilisateur, qui ne sait pas ce
qu'il ne voit pas.

---

## Les quatre cas, dans l'ordre où ils sont apparus

### 1. La zone déduite de la prose de l'employeur

Un poste à **Coire, Grisons** était crédité de la zone « Bâle et sa région »,
parce que l'employeur citait Bâle dans sa présentation d'entreprise.

**Correction** : les zones se jugent sur le champ `lieu`, pas sur la
description. Avec une exception assumée pour le télétravail, qui n'est presque
jamais dans le champ lieu mais toujours dans le texte.

### 2. Le télétravail sous-pondéré

« full remote » ne rapportait qu'un poids réduit, parce qu'un motif
trouvé dans la description valait 40 % du poids. Or le télétravail complet
pèse lourd dans une recherche, et il est **toujours** écrit là.

**Correction** : option `chercher_dans_description` à poids plein, réservée aux
cas où la mention dans le texte est une affirmation ferme.

### 3. Le poste republié sous un nouvel identifiant

La même offre d'un employeur arrivait trois fois : `…-100001`, `…-100002`,
`…-100003`. Aucune normalisation d'URL ne pouvait les rapprocher — ce sont
de vraies URL distinctes.

**Correction** : une seconde empreinte sur intitulé + employeur.

### 4. Un atout de domaine, presque toujours faux

Le pire des quatre, et le plus instructif. L'atout du secteur métier de la
personne se cherchait par un mot seul, dans tout le texte.

| Ce qui déclenchait | Pourquoi c'est faux |
|---|---|
| le mot du secteur, pris dans l'intitulé d'un autre métier | le mot anglais n'a rien à voir avec le secteur |
| le même mot dans les avantages sociaux | paragraphe présent dans presque toutes les annonces anglophones |

Plusieurs offres d'un même employeur créditées du domaine métier de la personne à
cause du paragraphe de leurs avantages sociaux.

**Correction** : option `champs` pour restreindre où un atout se cherche, et
abandon des motifs d'un seul mot générique.

---

---

## Un résumé ne vaut rien quand une règle est en jeu

Le 28/09/2026, avant de construire la lecture automatique des annonces, il
fallait savoir ce que chaque site autorise.

Un premier outil a récupéré le `robots.txt` de LinkedIn et l'a **résumé** :

> *« **No global block exists.** The document does not contain a
> `User-agent: *` section with `Disallow: /`. »*

C'était **faux**. Le fichier brut, 4861 lignes, contient bien :

```
User-agent: *
Disallow: /
```

Si le résumé avait été cru, on construisait un dispositif qui enfreignait
explicitement une interdiction — **sur son propre compte LinkedIn**, et pour
une part notable des offres de sa liste.

L'erreur n'a été vue qu'en allant chercher le fichier et en l'analysant
directive par directive, règle la plus spécifique d'abord.

### La règle

**Sur une décision qui engage une règle, un risque ou un compte, un résumé ne
vaut rien. Il faut la source.**

Concrètement, dans ce projet :

- `robots.txt` : on récupère le fichier et on l'analyse, jamais on ne demande à
  quelqu'un ce qu'il contient. `enrichissement.politique()` le fait en direct
  avant chaque requête.
- Conditions d'utilisation, plafonds d'API, statuts fiscaux : on cite la source
  ou on dit qu'on ne sait pas.
- Les chiffres qu'on donne à Édouard : mesurés sur ses données, pas estimés.
  Quand ce sont des ordres de grandeur, on l'écrit.

Le coût d'aller vérifier est de quelques minutes. Le coût de se tromper, ici,
aurait été son compte LinkedIn.

---

## Ce qu'il faut en retenir

**Un motif générique cherché dans tout le texte produit du bruit.** Les quatre
cas sont des variantes de cette seule erreur. Avant d'ajouter un motif,
demande-toi où il apparaît *ailleurs* que dans le sens voulu :

- dans la présentation de l'entreprise (« nos bureaux à Bâle, Zurich… ») ;
- dans les avantages sociaux (« pension », « mutuelle », « prise en charge des
  transports ») ;
- dans un mot composé d'un autre domaine (« data warehouse » pour un atout de
  logistique) ;
- dans les mentions légales et le pied de page.

**Préfère toujours** : des expressions de plusieurs mots, une restriction de
`champs`, et un bonus raté plutôt qu'un bonus distribué au hasard. C'est le
classement qui est en jeu, et un classement faux est pire qu'un classement
incomplet — il donne confiance.

---

## Comment tester avant que la collecte réelle existe

La plupart des canaux dépendent d'identifiants qu'Édouard doit créer. Ce n'est
pas une raison pour attendre : tout ce qui ne dépend pas d'eux est déjà
éprouvé, pour que le jour où il les pose, tout s'allume d'un coup plutôt que de
révéler une nouvelle série de blocages.

| Commande | Ce qu'elle prouve, dès maintenant |
|---|---|
| `veille tester-sources` | chaque source : joignable, identifiants présents ou non, ce qui manque |
| `veille tester-notification` | état des deux canaux, push et repli mail |
| `veille tester-mail --fichier x.eml` | analyse une alerte enregistrée, sans toucher à la boîte |
| `veille kit` | ce qui partirait pour une offre française et pour une offre suisse |
| `pytest tests/test_integration_mail.py` | la chaîne mail complète, de l'octet brut à la base |
| `pytest tests/test_push_plomberie.py` | signature VAPID et chiffrement, contre un service de push factice |

Les tests d'intégration mail construisent de vraies alertes multipart, avec
en-têtes MIME, accents, tableaux imbriqués et liens de suivi. Ils font tourner
le parsing, la résolution des liens, le scoring, la déduplication et
l'écriture en base — sans aucun accès réseau.

**Quand un vrai mail arrivera, il ne devra rien rester à découvrir.**

---

## Et quand une alerte n'est pas reconnue

Enregistre le mail depuis Gmail (**Afficher l'original** → *Télécharger*) puis :

```bash
./.venv/bin/veille tester-mail --fichier alerte.eml
```

Tu vois quel parseur a été choisi, ce qu'il a extrait, les liens résolus et le
score. Si rien ne sort, la marche à suivre est affichée : copier
`parsers/generique.py`, adapter deux méthodes, l'inscrire dans le registre.

---

## Un test vert ne dit pas que ça marche

Le champ de collage est parti avec 394 tests au vert, une réponse HTTP 200 sur
la page, et le fichier `app.js` servi correctement. Ouvert dans un navigateur,
il était **entièrement mort** : deux apostrophes non échappées — `'Lire
l'annonce'`, `'Revenir a l'extrait'` — une `SyntaxError` au chargement, aucune
offre affichée, aucun filtre repliable.

Aucun test ne pouvait le voir. Ils vérifiaient que le serveur *sert* le
fichier, jamais que le navigateur sait le *lire*.

Trois conséquences, tenues dans le dépôt :

1. `tests/test_javascript.py` passe chaque `.js` au `node --check`. Le français
   rend le piège permanent — « l'annonce », « l'extrait », « aujourd'hui » — donc
   le garde-fou doit être automatique, pas une vigilance.
2. **On regarde l'écran.** Deux autres défauts ne sont sortis que là, et aucun
   n'aurait été trouvé en relisant le code :
   - une offre écartée pour astreinte affichait « Score : 55 → 99 ▲ +44 » en
     vert. Le chiffre montait — le texte complet apportait des points — mais
     l'offre était morte. Lu vite, sur un téléphone, c'est l'inverse du message.
   - la citation censée prouver la détection était une fenêtre de 130 caractères
     autour du mot, pas la phrase. Le critère « Astreinte » citait la phrase sur
     la migration de données. **Une citation fausse est pire que pas de citation :
     il croit avoir vérifié.**
3. Ce qui a été vu à l'écran redescend en test, dans le même passage, pour que
   le défaut ne puisse pas revenir.

C'est la même règle que pour le `robots.txt` de LinkedIn, un cran plus loin :
**le substitut ne vaut pas la chose.** Un résumé ne vaut pas la source ; un
test HTTP ne vaut pas le navigateur ; un code relu ne vaut pas l'écran.

---

## Le piège récurrent : le général avant le spécifique

Quatre fois, sous quatre formes différentes, le même mécanisme a produit un
défaut :

| # | Où | Ce qui se passait |
|---|----|-------------------|
| 1 | Télétravail | « 2 jours sur site » lu comme présence totale : le motif général examiné avant le spécifique |
| 2 | Employeur / lieu | « Bâle-Ville » coupée sur son trait d'union, lieu inventé |
| 3 | Lieu imprécis | le bruit (« france ») retiré **avant** les motifs : « france entiere » coupé en deux |
| 4 | Lieu imprécis | « franche comte » consommé avant « bourgogne franche comte », résidu ingérable |

Deux mécanismes, un seul effet :

- **(A) ordre des motifs** — le général examiné avant le spécifique ;
- **(B) réécriture du texte** — une étape de nettoyage détruit le motif avant
  qu'on le cherche.

La règle générale, à appliquer partout où on cherche des motifs dans du texte :

> **Le plus spécifique d'abord, le nettoyage ensuite.** Trier les motifs par
> longueur décroissante ; ne retirer du bruit qu'après avoir cherché.

`tests/test_pretraitement.py` verrouille la classe entière, pas seulement les
quatre cas : **chaque motif déclaré dans `criteres.yaml`** est rejoué à travers
le prétraitement qui le concerne. C'est ce test qui a trouvé le cas n° 4 — dans
du code écrit une heure plus tôt pour corriger le cas n° 3.

---

## Ce que le collage d'une page entière rapporte avec lui

Le geste réel n'est pas « sélectionner la description » : c'est Ctrl+A sur
l'onglet. Arrivent donc aussi la colonne *Offres similaires*, les *Personnes
également consultées* et le pied de page — **d'autres annonces**.

Le risque est asymétrique, et c'est ce qui le rend grave : une astreinte
mentionnée dans l'offre voisine disqualifierait la bonne offre, **en citant une
phrase qui ne la concerne pas**. Le rapport aurait l'air d'une preuve.

`couper_sections_annexes()` coupe au premier repère de fin d'annonce, et la
console **dit** ce qu'elle a coupé : *« 526 caractères de rubriques annexes
écartés à partir de "Offres similaires" »*. Une troncature silencieuse serait
pire que le bruit qu'elle enlève.

---

## Les secrets ne vont pas dans les tests

En ajoutant un test de masquage, j'y ai recopié le **vrai** mot de passe
d'application Gmail et la moitié de la clé France Travail, comme valeurs de
fixture. Un fichier de test est versionné, lu, copié, envoyé : c'est exactement
l'endroit où un secret ne doit pas être.

`tests/test_javascript.py` cherche désormais dans tout le dépôt les **formes**
de secret — `PAR_*_<hex>`, 64 hexadécimaux, clé VAPID — en excluant les seuls
fichiers dont c'est le rôle d'en contenir (`config/.env`, `config/auth.json`,
non versionnés). Il a attrapé sa première prise immédiatement : son propre test
d'auto-vérification, où j'avais remis la vraie clé.

---

## Cinquième fois : le rejeu à blanc trouve ce que les tests ne voient pas

La vérification « l'annonce est-elle encore en ligne ? » a été écrite test en
premier, avec les quatre pièges connus verrouillés : page d'expiration en 200,
429, redirection vers l'accueil, site non sondable. **42 tests au vert.**

Puis le rejeu à blanc sur toutes les offres réelles de la base a trouvé un
défaut qu'aucun test n'avait vu : **des annonces vivantes accusées d'être retirées.**

Deux causes systématiques, toutes deux dans la même fonction :

1. **Titre court.** `« QA Lead »` — après normalisation il ne restait que
   `lead`, parce que le filtre écartait les mots de deux lettres et que `qa` en
   fait deux. Le contrôle exigeait trois mots consécutifs, n'en trouvait pas
   assez, et répondait *« titre absent »* là où la réponse honnête était
   **« je ne peux pas savoir »**.
2. **Page traduite.** Le titre est stocké en allemand depuis l'alerte, la page
   sondée est la version anglaise du même site. `Fachspezialist
   Testautomatisierung (Lagerverwaltungssoftware)` contre `Test Automation
   Specialist (Warehouse Management Software)` : même annonce, bien vivante.

Deux corrections, et la seconde est la vraie :

- le contrôle du titre rend désormais **trois** réponses — oui, non, et *je ne
  sais pas* — et filtre les **mots vides**, pas les mots courts ;
- surtout, **« le titre n'est plus sur la page » ne fait plus accuser du tout.**
  Ce verdict est retombé à `injoignable`. `indice_retrait` est réservé à la
  redirection vers une page générique, qui est **structurelle** et non
  textuelle.

Après correction, sur le même corpus : **plus aucun indice**, et une partie de
ces annonces est correctement rendue `vivante`.

**La leçon.** Écrire le test avant la règle protège des pièges qu'on connaît.
Le rejeu sur les données réelles, avant d'activer, trouve ceux qu'on ne connaît
pas encore. Les deux sont nécessaires, et le second n'est pas optionnel quand la
règle peut faire disparaître quelque chose de sa vue.

---

## Ne pas prendre les décisions d'Édouard pour ses propres traces

En nettoyant mes drapeaux de test, j'ai lancé une remise à zéro sur toutes les
lignes portant `verifiee_par`, `archive_protegee` ou un compteur d'échecs — en
supposant qu'elles venaient toutes de moi.

**Une seule de ces lignes était la mienne.** Toutes les autres étaient ses
décisions : il avait ouvert la console entre-temps, utilisé le bouton
« Obsolète » que je venais de livrer, et trié plusieurs annonces. Le script a
effacé `verifiee_par`, `verdict_verification` et **leurs lignes d'événements**.

L'information était sous mes yeux : le script imprimait les horodatages *avant*
d'effacer, et les miens étaient tous antérieurs aux siens. Je ne les ai pas lus
— j'ai enchaîné l'affichage et la suppression dans le même passage.

Réparable, et réparé à l'identique : `archivee_le` et `archive_motif` n'étaient
pas dans mon `UPDATE`, donc la date et le motif exacts de chacune de ses
décisions ont survécu. Ils ont suffi à tout reconstituer.

**Trois règles qui en découlent :**

1. **Un nettoyage n'est jamais « mes traces » par défaut.** Il faut un critère
   qui distingue — ici l'horodatage, ou mieux un marqueur d'origine explicite.
2. **Lire avant d'effacer, pas en même temps.** Un script qui affiche puis
   supprime dans le même passage n'affiche pour personne.
3. **Ne jamais mettre dans le même `UPDATE` ce qu'on veut nettoyer et ce qui
   fait preuve.** C'est ce qui a rendu la réparation possible, par chance et
   non par conception.

---

## Une variable d'environnement inconnue doit échouer

`VEILLE_BASE=/tmp/x.sqlite` avait été posé pour isoler un script de la vraie
base. Le nom exact est `VEILLE_DB`. Personne ne lit `VEILLE_BASE` : le script a
tourné sur la base réelle et y a écrit une offre de test.

La faute de frappe rejouera — c'est certain. Ce qui ne doit plus se produire,
c'est qu'un nom inconnu **ne fasse rien**. Poser une variable exprime une
intention ; l'ignorer en silence trahit cette intention exactement au moment où
l'on se croit protégé.

`config.verifier_environnement()` arrête désormais le programme sur toute
variable `VEILLE_*` ou `FT_*` non reconnue, en nommant la variable et en
proposant le nom le plus proche :

```
veille.config.VariableInconnue: Variable(s) non reconnue(s) :
  VEILLE_BASE — voulais-tu dire VEILLE_DB ?

Une variable qui n'est lue par personne ne fait RIEN : le programme
aurait tourné sur la configuration par défaut, donc sur la VRAIE base.
```

`tests/test_environnement.py` verrouille les deux sens : le nom fautif est
refusé avec sa suggestion, **et** toute variable lue quelque part dans le code
doit figurer dans la liste — sinon le garde-fou bloquerait un jour un démarrage
légitime.

---

## Un `fetch` qui échoue en silence : le bug le plus coûteux du projet

Édouard, à l'écran : *« je clique sur "elle n'y est plus, archiver" et quand je
reviens sur la page principale l'offre est toujours présente. »*

**Cause.** La route `POST /api/offres/{id}/retiree` avait été renommée
`/constat` côté serveur. Le JavaScript appelait toujours l'ancienne.
`fetch()` **ne lève rien sur un 404** : le code fermait la fenêtre, rechargeait
la liste, n'affichait aucune erreur. Tout avait l'air normal.

**Ampleur, mesurée dans le journal du serveur** : plusieurs offres concernées,
presque toutes rattrapées par lui-même en recliquant sur « Obsolète » dans les
secondes qui suivaient. **Une action définitivement perdue** — une annonce qu'il
croyait archivée et qui ne l'était pas.

Aucun test ne pouvait le voir : les tests Python appelaient la bonne route, le
garde-fou JS vérifiait la syntaxe. **Personne ne confrontait les deux.**

Trois corrections, de la plus superficielle à la plus structurelle :

1. la route appelée est corrigée, et les deux chemins vers l'archivage passent
   désormais par **la même fonction** — ils ne peuvent plus diverger ;
2. tous les appels réseau passent par le helper `api()`, qui **lève** sur un
   échec, au lieu de `fetch()` brut. C'était la cause profonde, pas le renommage ;
3. `test_javascript.py` confronte les deux mondes : **toute route appelée par le
   JS doit exister dans FastAPI.** Le test a trouvé exactement une dérive — celle-ci —
   et aucune autre.

**La leçon générale.** Une API qui échoue silencieusement est pire qu'une API
qui plante : l'utilisateur construit une confiance fausse. Chaque fois qu'un
appel peut échouer sans bruit, il faut soit le rendre bruyant, soit un test qui
prouve qu'il ne peut pas échouer.

---

## Dire pourquoi un résultat est vide

*« La génération du dossier ne fonctionne pas. »* Elle fonctionnait : elle
produisait exactement ce qu'elle doit produire quand le kit n'est pas branché —
un squelette de lettre et aucun CV.

Mais `_kit_est_provisoire()` rendait `False` dès que `VEILLE_KIT` était
**définie**, sans regarder si le dossier contenait quoi que ce soit. La variable
pointait vers un dossier vide : aucun avertissement n'était affiché.

Un résultat creux sans explication se lit comme une panne. La fonction regarde
désormais le **contenu** et non la configuration, et la console l'écrit en
premier, en rouge : *« Ton kit de candidature n'est pas branché. Ce n'est pas
une panne : la console n'a rien à joindre. »*

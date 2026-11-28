# Documenter un projet né du modèle

Ce fichier est **géré par le modèle** : il est réécrit par chaque `copier update`, et on ne le
modifie pas dans le projet. Aucun `CLAUDE.md` ne le charge : il sert au moment d'écrire un texte, le
README surtout, et à la clôture d'un lot, qui relit le README d'après lui (`methode.md`, « Le cycle
d'un lot »).

## Le README

Le README accueille un visiteur, Edouard compris, souvent sur un téléphone. Il dit ce qu'est le
projet, puis il aiguille : il ne raconte pas. Le modèle le sème en deux variantes, selon la cible ;
le projet le remplit, puis le tient.

### La variante « code »

Pour les cibles `aucune` et `serveur`, quelle que soit la nature :

```markdown
# <nom>

<description>

<!-- Pour une application : une capture d'écran, à fond opaque. -->

## Pourquoi

<!-- Trois à sept lignes : le besoin, ce que le projet fait, ce qu'il ne fait pas. -->

L'état du projet est dans [CLAUDE.md](CLAUDE.md#état).

## Démarrer

<!-- La commande qui lance le projet. -->

Les autres commandes sont dans [CLAUDE.md](CLAUDE.md#commandes).

## Où lire quoi

| Document | À lire quand |
|---|---|
| [CLAUDE.md](CLAUDE.md) | avant de travailler ici |
| [La méthode](docs/modele/methode.md) | pour la façon de travailler, commune aux projets nés de `modele-projet` |
| [Les pistes](docs/pistes.md) | pour ce qui est noté sans être engagé |
| [Le registre](docs/registre.md) | pour ce que les lots ont appris |
| [L'exploitation](docs/exploitation.md) | pour mettre en service, déployer, restaurer |

## Contribuer

Projet personnel : aucune contribution n'est attendue.

## Licence

[MIT](LICENSE)
```

Ce que dit chaque partie :

- **La première phrase**, la réponse `description` : ce qu'est le projet, et pour qui. Elle peut
  servir aussi de description du dépôt sur GitHub.
- **La capture d'écran**, pour une application, à fond opaque.
- **« Pourquoi »** : trois à sept lignes, le besoin, ce que le projet fait, ce qu'il ne fait pas.
  L'état vit dans `CLAUDE.md` : le README y renvoie, sans le recopier.
- **« Démarrer »** : la commande qui lance le projet. Les autres sont dans `CLAUDE.md`.
- **« Où lire quoi »** : un tableau qui aiguille, avec une colonne « À lire quand ». La ligne de
  l'exploitation ne paraît qu'en cible `serveur`. Deux textes du même nom s'y distinguent par ce
  qu'ils portent : « Le registre de la machine », à côté du registre des constats.
- **« Contribuer »** : une ligne, sans fichier `CONTRIBUTING`.
- **« Licence »**, en nature `code` seulement, en dernier.

Les commentaires HTML ne se voient pas sur GitHub : ils disent quoi écrire, et le texte les
remplace. Le brief et le cadrage ne sont pas dans le README : ils disent le départ du projet, et
n'aiguillent pas un visiteur ; « Ce qui fait foi », dans `CLAUDE.md`, les lie.

**Un renvoi mène à un document qui existe**, jamais à un gabarit resté vide : le démarrage d'une
session le signale (voir « Les contrôles »). C'est pourquoi le README naît sans ligne vers
`docs/decisions/`, qui ne porte alors que son `README.md`. Au premier ADR, le projet ajoute au
tableau « Où lire quoi », après la ligne du registre :

```markdown
| [Les décisions](docs/decisions/) | pour ce qui a été décidé, et pourquoi |
```

Pour la même raison, le README naît sans le lien des publications, qui mènerait à une page vide. À
sa première étiquette, le projet complète la ligne de l'état de « Pourquoi » :

```markdown
L'état du projet est dans [CLAUDE.md](CLAUDE.md#état), les versions dans [les publications](https://github.com/<compte>/<nom>/releases).
```

### La variante « données »

Pour la cible `donnees`, où `<nom du code>` est le nom du dépôt sans son suffixe `-donnees` :

```markdown
# <nom>

Les données de l'instance de [<nom du code>](https://github.com/<compte>/<nom du code>). Dépôt privé, sans code.

Avant d'y travailler : [CLAUDE.md](CLAUDE.md).

## Carte

| Dossier | Ce qu'il porte | Qui le lit |
|---|---|---|
| `config/` | la configuration de l'instance | l'application |
| `contenu/` | le contenu de l'instance | l'application |
| `env/` | l'environnement de la prod et du staging | le déploiement |
| `cles/` | les clés publiques `age` | `secrets.ps1` |
| `secrets/` | les secrets chiffrés, créés par le premier `secrets.ps1 refaire` | le déploiement |

## Ce qui n'y va jamais

Le code, un secret en clair, une clé privée.
```

Les lignes `env/`, `cles/` et `secrets/` ne paraissent qu'avec `cible_code: serveur`. Les dossiers
ne portent pas de lien : à la naissance, `config/` et `contenu/` n'ont que leur `README.md`, et
`secrets/` n'existe pas encore. Un dossier ne se lie qu'une fois qu'il porte autre chose que son
`README.md`.

### Réécrire un README

Avant de réécrire un README, chercher dans tout le dépôt `README.md#` et tout renvoi au README,
ceux d'un texte figé compris. Une ancre suit son titre, et aucun des contrôles ne lit l'ancre
d'un lien. Ce que seul le README porte se déplace ailleurs avant d'en être retiré. Il va dans le
texte qui en tient la source (« Un fait une fois ») ; quand aucun ne peut l'accueillir, dans un
texte d'explication du projet, sous `docs/` (par exemple `docs/fonctionnement.md`), lié depuis
« Où lire quoi » et tenu à la même règle, « Ce qui n'y va jamais », qu'aucun avertissement n'y lit.
Un projet de code né avant la `v0.9.0` met la section « Licence » dans la PR de mise à jour, qui
apporte `LICENSE`. Dans une PR à part, le lien `[MIT](LICENSE)` mènerait à un fichier absent.

## Ce qui n'y va jamais

Un README ne porte pas ce qui se périme sans que personne le voie, parce que sa source est
ailleurs :

- **une heure** (`7h15`) : elle vit dans la configuration ou dans le code ;
- **une version** (`v1.2.3`) : les publications la disent toujours juste ;
- **un lot au futur** (« le prochain lot ajoutera… »), ou un mot qui date un état
  (« actuellement », « bientôt ») : l'état est dans `CLAUDE.md`, la feuille de route dans les
  issues et les pistes ;
- **un arbre de fichiers** (`├──`) : le dépôt le montre, et le tableau « Où lire quoi » aiguille ;
- **une issue ou une PR citée** (`#12`) : la feuille de route est dans les issues et les pistes,
  l'histoire dans les publications ;
- **un nombre recopié** (de tests, de fichiers, de lignes) : il change à chaque PR.

Le démarrage d'une session signale une version, une heure, un arbre de fichiers, un mot qui date
l'état, un lot au futur et une issue ou une PR citée, par une recherche dans le texte qui ne voit
pas tout (voir « La copie dans le README » et « L'issue ou la PR citée », sous « Les contrôles »).
Il ne signale pas un nombre recopié.

Aucun contrôle n'attrape une phrase de prose devenue fausse : c'est le rôle de la relecture du
README, à la clôture de chaque lot.

## Sur un téléphone

Un README se lit souvent sur un téléphone, dans l'application de GitHub ou dans un navigateur
étroit :

- **des cellules de tableau d'une ligne**, au mieux ;
- **chaque schéma Mermaid doublé d'une phrase** qui dit la même chose : d'après des utilisateurs,
  l'application mobile de GitHub ne le rend pas ;
- **un ou deux encadrés au plus** (`> [!NOTE]`), réservés au crucial.

## Un fait une fois

Un fait a un seul endroit ; ailleurs, un lien y mène. Une copie diverge sans bruit, et un texte faux
est pire qu'un texte absent.

| Le fait | Son endroit |
|---|---|
| ce qu'est le projet, et pour qui | la première phrase du README |
| où en est le projet | `CLAUDE.md`, « État », au présent |
| les commandes | `CLAUDE.md`, « Commandes » |
| l'histoire et les versions | les publications de GitHub, ou le journal des versions |
| le comportement | le code et les tests |
| la façon de travailler | `docs/modele/methode.md` |
| les décisions | les ADR, dans `docs/decisions/` et `docs/modele/decisions/` |
| la feuille de route | les issues et `docs/pistes.md` |
| ce que les lots ont appris | `docs/registre.md` |
| la mise en service et les secours | `docs/exploitation.md`, en cible `serveur` |

Dans un dépôt de la cible `donnees`, `CLAUDE.md` dit ce que le dépôt porte, et ses leçons vont au
registre du dépôt de code.

## L'« État » et le journal

- l'« État » de `CLAUDE.md` dit le présent : l'étape en cours, la dernière chose faite, la
  prochaine, ce qui est en service ; 40 lignes non vides au plus, que le démarrage d'une session
  vérifie (voir « L'« État » trop long », sous « Les contrôles ») ;
- le passé va aux publications, que GitHub tient à chaque étiquette ; un projet sans étiquette, ou
  qui veut garder son histoire lisible, tient un journal, `CHANGELOG.md` à la racine, lié depuis
  « Ce qui fait foi », comme l'exige la carte de la racine ;
- le journal : une entrée par version, ou par lot dans un projet sans étiquette
  (`## Lot 3 — AAAA-MM-JJ`), la plus récente d'abord ; le texte qui sort de l'« État » y va tel
  quel.

## Les textes d'un projet

| Texte | Forme | Qui le lit | Qui le tient | Quand on le relit |
|---|---|---|---|---|
| README | accueil | un visiteur, Edouard | la session | à la clôture de chaque lot |
| `CLAUDE.md` | référence | une session | la session | à la PR qui change une règle |
| journal des versions (`CHANGELOG.md`) | référence | une session, Edouard | la session | à chaque étiquette ou clôture |
| `docs/modele/methode.md` | guide et référence | une session | le modèle | à chaque lot du modèle |
| ADR | explication | une session, Edouard | le lot qui décide | à leur révision |
| registre, pistes | conduite | une session, Edouard | la session | au 3e constat, à la clôture |
| `docs/exploitation.md` | guide pratique (runbook) | Edouard | le projet | à chaque `copier update` qui le touche |
| plans | conduite | une session | la session | supprimés à la clôture |
| brief, cadrage | explication | Edouard, une session | figés | jamais |

Les fichiers de `docs/modele/`, ce texte compris, sont tenus par le modèle. Un dépôt de la cible
`donnees` n'a ni registre, ni pistes, ni ADR à lui ; un lot qu'il conduit suit la méthode, et ses
leçons vont au registre du dépôt de code.

## Les ADR

Un ADR est un fichier de `docs/decisions/`, nommé `NNNN-titre.md` et numéroté à partir de `0001`.
Les décisions héritées du modèle sont à part, dans `docs/modele/decisions/` (préfixe `M-`), pour que
leurs numéros ne se heurtent pas à ceux du projet.

Le titre : `# ADR-NNNN — <Sujet> : <décision en une phrase>`.

L'en-tête :

- le statut, daté : proposé, accepté, remplacé par ADR-NNNN ;
- le contexte amont : l'ADR, l'issue ou le document dont celui-ci découle ;
- les amendements, une ligne chacun (voir la règle plus bas).

Les sections, dans cet ordre :

1. **Contexte** : ce qui force à décider ;
2. **Options** : les choix envisagés, avec leurs mérites et leurs défauts ;
3. **Décision** : ce qui est retenu, et pourquoi ;
4. **Conséquences** : ce qui change, dont une rubrique « Difficile à changer » ;
5. **Confirmation** : le test, le contrôle ou la mesure qui tient la décision, nommé par son chemin,
   ou « Aucun », avec sa raison ;
6. **Révision** : quand et sur quel signe on reconsidérera la décision.

**Un ADR ne se supprime pas.** Il s'amende en place : une ligne
`- **Amendé** le AAAA-MM-JJ : <ce qui change>` dans son en-tête, et son corps dit ce qui est en
vigueur. Ou un nouvel ADR l'amende, et le dit en tête de son contexte : l'ancien garde son texte, et
son en-tête le nomme (« amendé par ADR-NNNN le AAAA-MM-JJ »). Quand la décision change de
direction, un nouvel ADR la remplace : l'ancien ne change que de statut, « remplacé par ADR-NNNN ».

Un ADR écrit avant la `v0.15.0` n'a pas à recevoir sa section « Confirmation » : elle vient à son
prochain amendement.

## Retirer un texte

Un semé se vide ou se réécrit, il ne se supprime pas : Copier recrée à chaque mise à jour un semé
absent du projet. C'est le cas du README, du brief, du cadrage, des pistes, du registre,
d'`exploitation.md` et de `LICENSE`.

- **Le README et `CLAUDE.md`** se réécrivent. La carte de la racine refuse leur absence.
- **Le brief et le cadrage** sont figés. Sans objet, ils se vident, ou se réécrivent en une phrase
  qui le dit ; le README ne lie pas un document vide.
- **Les pistes et le registre** se vident de leurs lignes. Le registre garde son en-tête : la
  compétence `/consigner` y écrit.
- **`docs/exploitation.md`** se réécrit.
- **`LICENSE`** : changer de licence, c'est réécrire `LICENSE`, jamais le supprimer ni le renommer.
  Un `LICENSE.md` ferait deux licences à la mise à jour suivante. En nature `code`, la CI refuse un
  `LICENSE` absent ou vide.
- **Un plan** se supprime à la clôture du lot, après le report dans `CLAUDE.md` ou dans un ADR de ce
  qui doit survivre.
- **Un ADR** ne se supprime pas : il s'amende ou se remplace, d'après la règle de « Les ADR ».
- **Un fichier géré**, sous `docs/modele/`, ne se retire pas du projet : un défaut se corrige dans
  `modele-projet`.
- **Un texte propre au projet**, ni semé ni géré, se supprime, avec les liens qui y menaient.

## Les contrôles

`scripts/modele/documentation.py` porte deux contrôles qui refusent en CI, la licence et la carte
de la racine, à la dernière étape du job `confidentialite` du socle, « La documentation de la
racine (licence, carte) », et quatre avertissements, au démarrage d'une session. Chacun dit ce
qu'il a vu. Les sorties citent des chemins, jamais le contenu d'un fichier.

### La licence (refuse en CI)

En nature `code`, `LICENSE` doit être à la racine, sous ce nom exact, non vide, et suivi par git :
la CI lit le commit. La nature se lit comme la lit la porte de confidentialité : en CI, un dépôt
public est de code, et un dépôt privé prend la nature de sa branche par défaut, jamais celle de la
PR ; hors CI, celle de `scripts/modele/reglages.py`.

Ses lignes, chacune après `documentation : ` :

- `licence : LICENSE présent (nature code)` ;
- `licence : non exigée (nature donnees)` ;
- `licence : LICENSE absent ou vide, exigé en nature code` : le refus ;
- `licence : LICENSE présent mais non suivi par git, exigé en nature code` : le refus d'un
  `LICENSE` que git ne suit pas, à la racine d'un dépôt git.

Y répondre en rendant son texte à `LICENSE`. Un `copier update` recrée un `LICENSE` absent, pas un
`LICENSE` vide. Un `LICENSE` qu'un `copier update` vient de créer n'est pas suivi : il s'indexe
(`git add LICENSE`).

### La carte de la racine (refuse en CI)

Chaque fichier `.md` de la racine, sauf `README.md`, est lié : `CLAUDE.md` depuis le README ; un
autre depuis le README, ou depuis la section « Ce qui fait foi » de `CLAUDE.md`. Un fichier de la
racine se cite par un lien, `` [la notice](NOTICE.md) ``, et non par son nom entre accents graves :
un nom qu'on ne peut pas suivre ne mène nulle part. `README.md` et `CLAUDE.md` doivent exister. Un
fichier que git ignore n'est pas compté : `CLAUDE.local.md`, que le `.gitignore` semé exclut ; un
projet né plus tôt l'y ajoute.

Ses lignes, chacune après `documentation : ` :

- `carte : 0 fichier .md à la racine` : la première ligne, quand la racine n'a pas d'autre `.md`
  que `README.md` ;
- `carte : 1 fichier .md à la racine, lié` : la première ligne, quand le seul fichier vu est lié ;
- `carte : <n> fichiers .md à la racine, tous liés` : la première ligne, quand tous le sont ;
- `carte : <n> fichiers .md à la racine, <k> non lié` : la première ligne, quand un fichier n'est
  pas lié ; elle dit aussi combien ne le sont pas, au pluriel quand il le faut (`1 fichier`,
  `2 non liés`) ;
- `carte : README.md absent`, ou `carte : CLAUDE.md absent` : ces deux lignes refusent quelle que
  soit la première ligne ;
- `carte : CLAUDE.md n'est pas lié par README.md` ;
- `carte : <nom> n'est lié ni par README.md ni par « Ce qui fait foi » de CLAUDE.md` ;
- `refus`, en dernière ligne, quand la licence ou la carte refuse.

Y répondre en ajoutant le lien : dans le tableau « Où lire quoi » du README, ou dans « Ce qui fait
foi ». À `carte : README.md absent` ou `carte : CLAUDE.md absent`, rendre le fichier : un semé
retiré revient au `copier update` suivant (« Retirer un texte »).

`python -B scripts/modele/documentation.py`, lancé depuis la racine, donne les lignes de la CI, à
trois écarts près : un `.md` de la racine non suivi compte en local, et la CI ne le voit pas ; le
README et `CLAUDE.md` se lisent tels qu'ils sont dans la copie, validés ou non ; la nature se lit
dans la copie, alors qu'en CI un dépôt privé prend celle de sa branche par défaut. La PR qui pose
ou change la nature d'un dépôt privé y est donc jugée sous l'ancienne : en régime `code` si la
branche par défaut ne porte pas encore `NATURE`, et la licence y est exigée. La licence, elle, ne
compte en local qu'un `LICENSE` suivi, comme la CI.

### Les avertissements au démarrage d'une session

Quatre contrôles avertissent : le gabarit resté vide, l'« État » trop long, la copie dans le README
et l'issue ou la PR citée. Le hook `SessionStart` les lance et les montre à la session. Ce qu'ils
ont de commun :

- le hook les lit sans sous-processus ni réseau, dans les fichiers de la copie, pendant les
  lectures de `gh` ; seul son délai de 30 s les borne ;
- aucun ne refuse, et la CI n'en lance aucun : un avertissement se lit, il ne bloque rien ;
- chacun tourne sous sa garde, et son erreur donne son constat, sans arrêter les autres :
  `gabarit resté vide : non lu (erreur)`, `« État » : non lu (erreur)`,
  `copie dans le README : non lue (erreur)`, `issue citée : non lue (erreur)` ;
- `README.md` et `CLAUDE.md` se lisent sous ce nom exact, à la racine ;
- les constats citent des chemins et des numéros de ligne, jamais le contenu d'un fichier.

Un constat donne la ligne `documentation : <constat>` ; plusieurs, le titre `documentation :` puis
une ligne `- <constat>` chacun, 20 au plus. Quand le script ne s'importe pas, la ligne est
`documentation : non lue (erreur)` ; les signaux de la CI restent. C'est un défaut du modèle, qui se
corrige dans `modele-projet`. Pour relancer les avertissements, depuis la racine :
`python -B scripts/modele/documentation.py --avertissements`, qui imprime chaque constat sur sa
ligne, après `documentation : `, et rend toujours 0, hors d'une erreur d'usage (64).
`--gabarits-vides` en reste le synonyme, pour les commandes déjà écrites. Un constat de trop se lève
en réécrivant la ligne, ou se laisse : un avertissement ne bloque rien. Un `README.md` ou un
`CLAUDE.md` absent ou illisible ne donne aucun constat de l'« État », de la copie ni de l'issue
citée ; seul le gabarit resté vide dit `pas de README.md`.

#### Le gabarit resté vide

Le hook `SessionStart` lit chaque fichier `.md` et chaque dossier que le README lie, et qui
existent dans le dépôt. Le reste est ignoré : une image, un script, un lien externe, une cible
absente ou hors du dépôt. Trois règles ; la première qui touche donne le constat d'un chemin, dans
l'ordre des liens :

- un fichier qui garde le marqueur du gabarit, hors du code :
  `<chemin> : garde le marqueur *AAAA-MM-JJ* du gabarit` ;
- un fichier dont le corps est vide, une fois retirés les titres, les lignes vides, les commentaires
  HTML et les lignes tout en italique, qui sont les consignes des gabarits :
  `<chemin> : corps vide (titres et consignes seulement)` ;
- un dossier qui n'a pas d'autre enfant que `README.md` et `.gitkeep` :
  `<chemin>/ : dossier sans autre fichier que README.md`.

Le registre (tout `registre.md`) et les plans (sous `.claude/plans/`) échappent aux trois règles ;
les fichiers d'ADR (sous `docs/decisions/` ou `docs/adr/`, sauf leur `README.md`), aux deux
premières, et leur dossier relève de la troisième. Deux constats viennent sans règle :
`le README ne lie aucun document du dépôt`, et `pas de README.md`. Rien à signaler ne donne rien.

Y répondre en remplissant le document, ou en retirant son lien du README tant qu'il est vide ; pour
un dossier, en y posant son premier fichier ; pour le marqueur, en écrivant la date qu'il réserve.
À un README qui ne lie aucun document du dépôt, ajouter au moins le lien de `CLAUDE.md`. À
`pas de README.md`, de même que pour la carte : rendre le fichier, que le `copier update` suivant
sème à neuf.

#### L'« État » trop long

Le hook lit `CLAUDE.md`, à la racine : ses sections de niveau 2 dont le titre est « État » (comparé
en NFC, sans égard à la casse), chacune jusqu'au titre suivant de niveau 1 ou 2. Plusieurs sections
« État » s'additionnent. Il compte les lignes non vides, telles qu'elles sont : le code, les
commentaires et les sous-titres comptent, puisque `CLAUDE.md` se charge en entier ; une ligne
d'espaces est vide. Le seuil est de 40 lignes : 40 ne donnent rien, 41 donnent le constat. Un
`CLAUDE.md` absent, ou sans section « État », ne donne rien : celui de la cible `donnees` n'en a
pas.

Son constat :

- `CLAUDE.md : « État » de <n> lignes, au-delà de 40 (le passé va au journal des versions ou
  aux publications)`.

Y répondre en déplaçant le passé vers le journal des versions, ou vers les notes de la publication,
qu'écrit Edouard, et en réécrivant l'« État » au présent (voir « L'« État » et le journal »).

Ses limites : un titre « Etat », sans accent, ou « L'état du projet » n'est pas lu, ni un « État »
de niveau 3.

#### La copie dans le README

Le hook lit `README.md`, à la racine, ligne par ligne, en NFC et sans égard à la casse. Le code, en
bloc ou en ligne, est lu : un arbre de fichiers vit dans un bloc de code, une version dans une
commande. Les commentaires HTML hors du code ne sont pas lus, mais leurs lignes comptent pour les
numéros : ils ne se voient pas sur GitHub. Un `<!--` jamais fermé qui ouvre une ligne, hors du
code, cache la suite, comme sur GitHub ; au milieu d'une ligne, il reste du texte, et la suite est
lue. Quatre sortes de copie, chacune une recherche dans le texte :

- une version : trois nombres séparés par des points, précédés ou non de `v` (`v1.2.3`, `1.2.3`,
  `Node 20.11.1`, `1.2.3-rc.1`) ; `127.0.0.1`, `2026.11.21.1` et `3.12` n'en sont pas, une date en
  points (`2026.11.21`) en est une ;
- une heure : `7h15`, `7 h 15`, `19h00`, `07:15`, `12:30:45` ; `127.0.0.1:8000`, `localhost:3000`
  et `16:9` n'en sont pas, une durée (`1h30`) en est une ;
- un arbre de fichiers : une ligne qui porte `├`, `└` ou `│` ;
- un mot qui date l'état, ou un lot au futur : `actuellement`, `bientôt`, `prochainement`,
  `pour l'instant`, `pour le moment`, `à venir`, `à terme`, `prochain lot`, `lot suivant`,
  `prochaine version` ; ou une ligne qui nomme un lot par son numéro (`lot 3`, `lot #11`) et porte
  un mot de quatre lettres ou plus fini par `ra` ou `ront` (« ajoutera », « seront »).

Ses constats, un par sorte, dans cet ordre, au plus quatre :

- `README.md, l. <n> : une version recopiée` ;
- `README.md, l. <n> : une heure recopiée` ;
- `README.md, l. <n> : un arbre de fichiers` ;
- `README.md, l. <n> : un mot qui date l'état, ou un lot au futur`.

Chacun nomme la première ligne touchée, un numéro du fichier à partir de 1. Quand d'autres lignes
ont la même sorte, il finit par `(et 1 autre ligne)` ou `(et <k> autres lignes)`.

Y répondre en retirant la copie, ou en renvoyant à la source qui la tient : les publications pour
une version, `CLAUDE.md` pour l'état.

Ses limites, dont la liste n'est pas close : un futur dit autrement (« va ajouter », « est
prévu ») ; un mot qui date absent de la liste ; une version à deux nombres (`v1.2`) ; un arbre
dessiné en ASCII (`|--`) ; un nombre recopié (de tests, de lignes), qu'aucune recherche ne sépare
d'un nombre utile ; une phrase de prose devenue fausse. Une recherche peut aussi donner un constat
de trop : un mot fini par « ra » ou « ront » près d'un lot (« Sahara » près d'un « lot 3 », « le
front du lot 3 »), une correspondance de ports (`80:80`) ou un rapport (`16:10`) lus comme une
heure, un numéro de section à trois nombres (`4.3.1`) lu comme une version, un dessin en traits
(`│ boîte │`) lu comme un arbre. Un commentaire fermé qui enjambe un bloc de code laisse lire le
bloc, que GitHub cache ; un `<!--` en tête de ligne, fermé seulement dans un bloc de code, cache la
suite, que GitHub montre. Un code en ligne qui porte le dernier `-->` du texte cache ce qu'il porte
entre `<!--` et `-->`, que GitHub montre ; un `<!--` en tête de ligne qu'un accent grave ouvert
plus haut paraît mettre en code laisse lire ce qu'il ouvre, que GitHub cache ; un `<!--` ouvert au
milieu d'une ligne et fermé plus bas, au-delà de son paragraphe, cache ce qui le sépare de sa
fermeture, que GitHub montre. Seul le README est lu : un texte vers lequel il aiguille ne l'est
pas.

#### L'issue ou la PR citée

Le hook lit `README.md`, à la racine, hors des blocs de code, du code en ligne et des commentaires
HTML, leurs lignes gardées pour les numéros : GitHub n'y lie aucune référence, et une couleur
en code (`` `#000000` ``) n'est pas une issue. Un `<!--` jamais fermé qui ouvre une ligne, hors du
code, cache aussi la suite. Est une référence :

- `#N`, N fait de chiffres, sans lettre, chiffre, `_`, `&`, `#`, `/` ni `.` juste avant, et sans
  lettre, chiffre, `_` ni `-` juste après, hors de la cible d'un lien : `#12`, `(#12)`,
  `voir #12.` ;
- `<compte>/<dépôt>#N`, comme GitHub le lie ;
- un lien dont la cible porte `/issues/N` ou `/pull/N`, absolue ou relative (`../../issues/12`).

`CLAUDE.md#12-intro`, l'ancre d'un sommaire (`[1. Intro](#1-intro)`), `&#123;`, `C#7`, `#12a` et
`# 12` n'en sont pas. La cible d'un lien ne se lit que pour `/issues/N` et `/pull/N`.

Son constat :

- `README.md, l. <n> : une issue ou une PR citée`, suivi de `(et 1 autre ligne)` ou
  `(et <k> autres lignes)` quand d'autres lignes en citent.

Y répondre en retirant la référence : la feuille de route est dans les issues et les pistes,
l'histoire dans les publications.

Ses limites, dont la liste n'est pas close : `GH-12`, que GitHub lie aussi ; une référence dans un
bloc HTML que le texte ne retire pas ; une couleur en chiffres seuls (`#000000`) hors du code ; un
chemin suivi d'une ancre en chiffres hors d'un lien (`docs/a.md#12`), lu comme `<compte>/<dépôt>#N`
; un chemin `…/issues/12` en prose ; une référence dans un bloc de code indenté, ou dans une cible
de lien qui porte une parenthèse ; une référence après un `<!--` en tête de ligne qu'un accent grave
ouvert plus haut paraît mettre en code ; un `<!--` ouvert au milieu d'une ligne et fermé plus bas,
au-delà de son paragraphe, cache ce qui le sépare de sa fermeture, que GitHub montre.

### Ce qui compte comme un lien

Pour la carte comme pour le gabarit resté vide :

- un lien en ligne, `[texte](cible)` ou `![image](cible)`, avec un titre ou des chevrons, son texte
  sur plusieurs lignes au besoin ;
- un lien de référence, `[texte][x]`, `[x][]` ou `[x]`, quand la définition `[x]: cible` de son
  étiquette est dans le même fichier. Une définition ne compte que par son emploi : seule, elle ne
  lie rien, puisque GitHub ne l'affiche pas, et une définition qui coupe un paragraphe n'en est pas
  une. Pour « Ce qui fait foi », l'emploi est dans la section, la définition dans tout `CLAUDE.md`.

Un lien HTML (`<a href="…">`) ne compte pas : la carte demande un lien Markdown, et le remède est la
forme `[texte](cible)`.

Rien ne compte dans un bloc de code, dans un code en ligne ni dans un commentaire HTML : GitHub n'y
rend aucun lien. La cible perd son ancre et sa requête, puis elle est décodée (`%20`) ; un `/` en
tête part de la racine. Une cible n'est pas locale quand elle a un schéma (`https:`, `mailto:`) ou
commence par `//`, n'est qu'une ancre, garde une barre oblique inverse, porte un deux-points sous
Windows, qui y nomme un lecteur (`Z:`, en tête comme plus loin : `docs/Z:x.md`), ou sort du dépôt,
par `..` ou par un lien symbolique. La casse compte, comme sur GitHub : `[x](claude.md)` ne lie pas
`CLAUDE.md`. Un document est un fichier dont le suffixe est `.md`, sans égard à la casse.

### Les écarts connus au rendu de GitHub

Ils sont rares. Certains laissent passer à tort un lien que GitHub ne rend pas :

- dans un bloc de code indenté, que GitHub rend en code ;
- dans un bloc clôturé à l'intérieur d'une citation, ou d'un élément de liste indenté de quatre
  colonnes ou plus, s'il s'ouvre par des tildes ou qu'une ligne vide le coupe ;
- dans un bloc HTML sans ligne vide (`<details>` collé à son contenu) ;
- dans un bloc `<pre>`, `<script>`, `<style>` ou `<textarea>`, lignes vides comprises, jusqu'à la
  fin de la ligne qui porte sa balise fermante ;
- dans un bloc ouvert en tête de ligne par `<!--` (ou par `<?`, `<!DOCTYPE`, `<![CDATA[`), jusqu'à
  la fin de la ligne qui le ferme, ou jusqu'à la fin du fichier s'il ne se ferme jamais ;
- dans une citation ou un élément de liste, dans un bloc ouvert par `<!--`, de même ;
- un lien dont le texte porte un `|` dans une cellule de tableau (`| [a|b](CLAUDE.md) |`), que
  GitHub coupe.

D'autres font refuser à tort :

- un titre souligné (`Ce qui fait foi` sur une ligne de `---`) n'est pas lu ;
- un accent grave échappé (`` \` ``) ouvre quand même un code en ligne ;
- une entité dans la cible (`&#46;`) n'est pas décodée ;
- un fichier dont le nom porte une barre oblique inverse, que Windows refuse, n'est jamais lié ;
- un commentaire HTML ouvert dans un paragraphe cache les liens jusqu'à sa fermeture, plus
  loin (pour la clôture d'un plan, il laisse passer : voir plus bas) ;
- une définition n'est pas lue quand elle suit une ligne de commentaire (`<!-- liens -->`, puis les
  définitions), quand elle est dans un élément de liste ou dans une citation, quand elle suit une
  ligne de séparation (`***`), ou quand son titre tient sur deux lignes ;
- et d'autres formes rares des conteneurs et des commentaires (un bloc clôturé non fermé dans un
  élément de liste, un code en ligne qui franchit une ligne `>` vide, un texte de lien à plus de
  trois niveaux de crochets, une définition après un titre souligné, un commentaire fermé par
  `--->` dans un paragraphe).

D'autres laissent passer à tort ce que GitHub cache, et touchent aussi `texte_pr.py` et `plan.py`,
qui s'appuient sur `documentation.py` ; deux sont connus : un `<!--` jamais fermé, ouvert dans un
élément de liste après quatre espaces ou plus (une puce imbriquée, ou une ligne qui continue la
puce), cache sur GitHub tout ce qui le suit, mais les contrôles lisent encore la suite : un titre,
et donc la section « Ce qui fait foi », la section des écarts à la spec, les sections d'un plan,
ses titres de tâche ou de tranche, le texte de son unité de clôture et ses lignes
« Plan maître : » et « Hors lot : », et la ligne « Tête relue », qui doit toujours nommer la tête
de la PR ; un bloc ouvert en tête de ligne par `<?`, par `<!` suivi d'une majuscule (`<!DOCTYPE`)
ou par `<![CDATA[` cache de même sur GitHub tout ce qui le suit jusqu'au premier `>`, même
plusieurs lignes plus bas, ou jusqu'à la fin sans lui, mais `texte_pr.py` et `plan.py`, qui ne
cherchent que `<!--`, lisent encore la ligne « Tête relue », la section des écarts, les sections
d'un plan, ses titres de tâche ou de tranche, le texte de son unité de clôture et ses lignes
« Plan maître : » et « Hors lot : ». D'autres formes HTML cachent aussi sur GitHub ce que les
contrôles lisent : un `<?` ou un `<!DOCTYPE` après une puce, ou en ligne et fermé plus bas ; un
`<!--` jamais fermé dans une ligne de bloc HTML, comme `<div><!-- note</div>` ; un attribut ou un
titre de lien sur plusieurs lignes.

La clôture d'un plan en a quatre de plus, qui ne touchent que `plan.py` et laissent passer une
clôture que GitHub rend autrement : un titre souligné (une ligne de `===` ou de `---` sous une
ligne) après l'unité de clôture ne la borne pas, et un geste nommé après lui compte ; une
définition `[//]: # (…)`, que GitHub n'affiche pas, compte ; un `-->` suivi de `###` en tête de
ligne, qui ferme un commentaire ouvert dans un paragraphe, fait un titre d'unité, alors que GitHub
rend la ligne en paragraphe ; un `<!--` ouvert dans un paragraphe et fermé plus bas cache à
`plan.py` un titre de clôture que GitHub montre, et `plan.py` vérifie l'unité de clôture suivante.
Ces deux derniers, des commentaires ouverts dans un paragraphe, laissent passer la clôture, alors
qu'un tel commentaire fait refuser à tort un lien.

Un autre tient à Windows, où l'existence d'un chemin se lit sans égard à la casse. Sous Windows, le
contrôle du gabarit resté vide trouve le fichier `docs/cadrage.md` derrière un lien
`docs/Cadrage.md` du README, et peut avertir si ce fichier n'a que son gabarit, alors que GitHub
casse ce lien ; sous Linux, il ne trouve pas ce fichier, et ne dit rien. C'est un avertissement de
trop, jamais un refus. Dans `plan.py`, lancé sous Windows, un lieu de « Mécanismes annoncés » ou la
cible d'une ligne « Plan maître : » écrits dans une autre casse que le fichier passent, alors que la
CI, sous Linux, les refuse (« fichier absent », « plan maître absent ») : la vérification locale
passe là où la CI refuse.

Le remède, chaque fois : écrire le lien sous une forme ordinaire, hors de ces blocs ; dans un plan,
écrire de même les gestes de la clôture et les titres du plan sous la forme que GitHub rend, hors
d'un commentaire et d'une définition, chaque titre en `#`, seul sur sa ligne ; écrire un chemin dans
la casse du fichier. La liste des écarts connus n'est pas close : d'autres formes rares peuvent
encore séparer ce que lisent les contrôles de ce que rend GitHub.

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

L'état du projet est dans [CLAUDE.md](CLAUDE.md#état), les versions dans [les publications](https://github.com/<compte>/<nom>/releases).

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
  L'état vit dans `CLAUDE.md`, les versions dans les publications : le README y renvoie, sans les
  recopier.
- **« Démarrer »** : la commande qui lance le projet. Les autres sont dans `CLAUDE.md`.
- **« Où lire quoi »** : un tableau qui aiguille, avec une colonne « À lire quand ». La ligne de
  l'exploitation ne paraît qu'en cible `serveur`.
- **« Contribuer »** : une ligne, sans fichier `CONTRIBUTING`.
- **« Licence »**, en nature `code` seulement, en dernier.

Les commentaires HTML ne se voient pas sur GitHub : ils disent quoi écrire, et le texte les
remplace. Le brief et le cadrage ne sont pas dans le README : figés depuis la phase 0, ils
n'aiguillent pas un visiteur, et « Ce qui fait foi », dans `CLAUDE.md`, les lie.

**Un renvoi mène à un document qui existe**, jamais à un gabarit resté vide : le démarrage d'une
session le signale (voir « Les trois contrôles »). C'est pourquoi le README naît sans ligne vers
`docs/decisions/`, qui ne porte alors que son `README.md`. Au premier ADR, le projet ajoute au
tableau « Où lire quoi », après la ligne du registre :

```markdown
| [Les décisions](docs/decisions/) | pour ce qui a été décidé, et pourquoi |
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
ceux d'un texte figé compris. Une ancre suit son titre, et aucun des trois contrôles ne lit l'ancre
d'un lien. Ce que seul le README porte se déplace ailleurs avant d'en être retiré. Un projet de
code né avant la `v0.9.0` met la section « Licence » dans la PR de mise à jour, qui apporte
`LICENSE`. Dans une PR à part, le lien `[MIT](LICENSE)` mènerait à un fichier absent.

## Ce qui n'y va jamais

Un README ne porte pas ce qui se périme sans que personne le voie, parce que sa source est
ailleurs :

- **une heure** (`7h15`) : elle vit dans la configuration ou dans le code ;
- **une version** (`v1.2.3`) : le lien vers les publications la dit toujours juste ;
- **un lot au futur** (« le prochain lot ajoutera… »), ou un mot qui date un état
  (« actuellement », « bientôt ») : l'état est dans `CLAUDE.md`, la feuille de route dans les
  issues et les pistes ;
- **un arbre de fichiers** (`├──`) : le dépôt le montre, et le tableau « Où lire quoi » aiguille ;
- **un nombre recopié** (de tests, de fichiers, de lignes) : il change à chaque PR.

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
| où en est le projet | `CLAUDE.md`, « État » |
| les commandes | `CLAUDE.md`, « Commandes » |
| les versions | les publications de GitHub |
| le comportement | le code et les tests |
| la façon de travailler | `docs/modele/methode.md` |
| les décisions | les ADR, dans `docs/decisions/` et `docs/modele/decisions/` |
| la feuille de route | les issues et `docs/pistes.md` |
| ce que les lots ont appris | `docs/registre.md` |
| la mise en service et les secours | `docs/exploitation.md`, en cible `serveur` |

Dans un dépôt de données, `CLAUDE.md` dit ce que le dépôt porte, et ses leçons vont au registre du
dépôt de code.

## Les textes d'un projet

| Texte | Forme | Qui le lit | Qui le tient | Quand on le relit |
|---|---|---|---|---|
| README | accueil | un visiteur, Edouard | la session | à la clôture de chaque lot |
| `CLAUDE.md` | référence | une session | la session | à la PR qui change une règle |
| `docs/modele/methode.md` | guide et référence | une session | le modèle | à chaque lot du modèle |
| ADR | explication | une session, Edouard | le lot qui décide | à leur révision |
| registre, pistes | conduite | une session, Edouard | la session | au 3e constat, à la clôture |
| `docs/exploitation.md` | guide pratique (runbook) | Edouard | le projet | à chaque `copier update` qui le touche |
| plans | conduite | une session | la session | supprimés à la clôture |
| brief, cadrage | explication | Edouard, une session | figés | jamais |

Les fichiers de `docs/modele/`, ce texte compris, sont tenus par le modèle. Un dépôt de données n'a
ni registre, ni pistes, ni plans, ni ADR à lui.

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
- **Un ADR** ne se supprime ni ne se réécrit : un nouvel ADR le remplace, et l'ancien ne change que
  de statut.
- **Un fichier géré**, sous `docs/modele/`, ne se retire pas du projet : un défaut se corrige dans
  `modele-projet`.
- **Un texte propre au projet**, ni semé ni géré, se supprime, avec les liens qui y menaient.

## Les trois contrôles

`scripts/modele/documentation.py` porte trois contrôles. Les deux premiers refusent, en CI, à la
dernière étape du job `confidentialite` du socle, « La documentation de la racine (licence,
carte) ». Le troisième avertit, au démarrage d'une session. Chacun dit ce qu'il a vu. Les sorties
citent des chemins, jamais le contenu d'un fichier.

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

### Le gabarit resté vide (avertit au démarrage d'une session)

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

Un constat donne la ligne `documentation : <constat>` ; plusieurs, le titre `documentation :` puis
une ligne `- <constat>` chacun. Une erreur du contrôle donne `documentation : non lue (erreur)`, et
laisse les signaux de la CI : c'est un défaut du modèle, qui se corrige dans `modele-projet`. Ce
contrôle ne refuse jamais, et la CI ne le lance pas. Pour le relancer, depuis la racine :
`python -B scripts/modele/documentation.py --gabarits-vides`, qui imprime un constat par ligne et
rend toujours 0.

Y répondre en remplissant le document, ou en retirant son lien du README tant qu'il est vide ; pour
un dossier, en y posant son premier fichier ; pour le marqueur, en écrivant la date qu'il réserve.
À un README qui ne lie aucun document du dépôt, ajouter au moins le lien de `CLAUDE.md`. À
`pas de README.md`, de même que pour la carte : rendre le fichier, que le `copier update` suivant
sème à neuf.

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
  loin ;
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
et donc la section « Ce qui fait foi », la section des écarts à la spec, les trois sections d'un
plan et ses titres de tâche ou de tranche, et la ligne « Tête relue », qui doit toujours nommer la
tête de la PR ; un bloc ouvert en tête de ligne par `<?`, par `<!` suivi d'une majuscule
(`<!DOCTYPE`) ou par `<![CDATA[` cache de même sur GitHub tout ce qui le suit jusqu'au premier `>`,
même plusieurs lignes plus bas, ou jusqu'à la fin sans lui, mais `texte_pr.py` et `plan.py`, qui ne
cherchent que `<!--`, lisent encore la ligne « Tête relue », la section des écarts, les trois
sections d'un plan et ses titres de tâche ou de tranche. D'autres formes HTML cachent aussi sur
GitHub ce que les contrôles lisent : un `<?` ou un `<!DOCTYPE` après une puce, ou en ligne et fermé
plus bas ; un `<!--` jamais fermé dans une ligne de bloc HTML, comme `<div><!-- note</div>` ; un
attribut ou un titre de lien sur plusieurs lignes.

Un dernier ne touche que le gabarit resté vide. Sous Windows, l'existence d'un chemin lié s'y lit
sans égard à la casse : un lien `docs/Cadrage.md` vers `docs/cadrage.md` y est lu, et peut avertir,
alors que GitHub casse ce lien ; sous Linux, il est ignoré. C'est un avertissement de trop, jamais
un refus.

Le remède, chaque fois : écrire le lien sous une forme ordinaire, hors de ces blocs.

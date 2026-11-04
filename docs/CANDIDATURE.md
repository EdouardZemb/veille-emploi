# Le bouton « Générer le dossier »

Un clic par offre. La console crée un dossier daté, y met la lettre
préremplie, les pièces de ton kit et une fiche de l'offre, puis te rend le tout
en `.zip` téléchargeable.

**Rien n'est rédigé à ta place.** Le programme remplace des marqueurs dans un
gabarit que tu as écrit, et copie des fichiers. C'est tout.

Les exemples ci-dessous sont ceux de l'exemple livré avec le code (Camille
Exemple, `exemple/`). Le kit de l'instance réelle, ses lettres, les constats
sur sa base et ce que l'affinement y réutilise sont dans
le `docs/CANDIDATURE.md` du dépôt de données.

---

## Ce que contient le dossier généré

```
2026-09-27_fret-digital-ag_testeur-logiciel/
├── lettre-de-motivation.md      ← ton gabarit, marqueurs remplis
├── cv.pdf                       ← copié du kit
├── annexe-technique.pdf         ← copié du kit
├── fiche-offre.md               ← l'offre + pourquoi elle est sortie
└── 2026-09-27_fret-digital-ag_….zip       ← l'ensemble
```

La **fiche-offre** sert à préparer l'entretien : elle reprend l'annonce telle
que collectée, et le détail du score ligne par ligne.

---

## Copier ton kit sur le serveur

L'emplacement est `donnees/kit` dans le clone de la console, en droits **700**,
dans le même dossier protégé que la base (en conteneur, `/donnees/kit`).

**Une seule commande, depuis PowerShell sur ton PC** — remplace le chemin
source par le tien :

```powershell
scp -r "C:\chemin\vers\ton-kit\*" <utilisateur>@<le serveur>:<le clone>/donnees/kit/
```

Puis vérifie ce qui a été reconnu :

```bash
ssh <utilisateur>@<le serveur> "cd <le clone> && ./.venv/bin/veille kit"
```

Rien d'autre à faire : **le dossier est relu à chaque ouverture de la console**.
Tu peux y ajouter des pièces quand tu veux, elles apparaîtront sans
redémarrage et sans modification du code.

Tant que le kit n'a pas de lettre, la console retombe sur les gabarits
provisoires de la configuration (`gabarits/`) et **l'écrit à chaque génération** :

> *Kit de candidature provisoire : les pièces viennent de gabarits/ et non de
> ton CV maître.*

---

## Consulter tes documents depuis ton téléphone

Onglet **Documents** de la console. Deux sections :

**Ton kit**, rangé par catégorie — CV, dossier de candidature, lettres,
préparation d'entretien, stratégie, annexes et certifications. Chaque pièce
affiche son contexte (*français*, *Suisse, anglais*), sa taille et sa date.

**Les dossiers générés**, un par candidature, rattachés à leur offre avec son
statut. Les fichiers de chaque dossier sont aussi téléchargeables directement
depuis la fiche de l'offre, via le bouton **Générer le dossier**.

Tout est derrière ta connexion par passkey, comme le reste de la console. Aucun chemin
n'est servi sans vérification : un fichier demandé doit être *contenu* dans le
dossier autorisé, liens symboliques résolus.

> Les liens **téléchargent** plutôt qu'ils n'affichent : un PDF de CV se lit
> mal dans un onglet de téléphone. Pour un aperçu, ajoute `?apercu=true` à
> l'adresse — utile pour les fichiers `.md`, comme ta préparation d'entretien.

### Fichiers reconnus dans le kit

| Fichier | Rôle |
|---------|------|
| `lettre_atout_<atout>.md` | Lettre spécifique à un atout — ex. `lettre_atout_domaine_logistique.md` |
| `lettre_<famille>.md` | Lettre spécifique à une famille — ex. `lettre_automatisation_tests.md` |
| `lettre_fr.md` / `lettre_en.md` | Lettre par langue de l'annonce |
| `lettre.md` | Lettre par défaut |
| `*.pdf` `*.docx` `*.odt` `*.png` `*.jpg` | Pièces jointes (voir ci-dessous) |

**Choix de la lettre**, dans l'ordre : atout → famille → langue → défaut. La
langue est détectée sur le texte de l'annonce. Les clés de famille et d'atout
sont celles du `criteres.yaml` de ta configuration ; dans l'exemple, les
familles `automatisation_tests`, `test_fonctionnel`, `test_performance`,
`qualification_logicielle`, `pilotage_tests`, `recette_donnees` et
`developpement_outillage`.

### Pièces : les étiquettes de contexte

Un kit peut contenir un **CV français** et un **dossier suisse en anglais**. Les
deux ne doivent jamais partir ensemble.

Le mécanisme : des **étiquettes séparées par des points**, avant l'extension.
Une pièce n'est jointe que si **toutes** ses étiquettes conviennent à l'offre.

| Nom de fichier | Part avec |
|----------------|-----------|
| `annexe-technique.pdf` | **toutes** les offres — aucune étiquette |
| `cv.fr.pdf` | les offres en français |
| `cv.ch.en.pdf` | les offres **suisses** rédigées en **anglais** |
| `dossier-complet.ch.en.pdf` | idem |

Étiquettes reconnues : `fr` `en` `de` pour la langue, `ch` `suisse` `france`
pour le pays. Plus deux étiquettes spéciales :

- **`manuel`** — la pièce n'est **jamais** jointe automatiquement, mais reste
  téléchargeable depuis l'onglet *Documents*.
- aucune étiquette — pièce **universelle**, jointe partout.

Les pièces écartées sont **annoncées** à la génération :

> *Offre détectée : en/ch. Pièces non jointes car destinées à un autre
> contexte : cv.fr.pdf*

### Trois CV, et lequel part

Un kit peut porter trois CV, par exemple :

| Fichier | Part avec | Photo |
|---|---|---|
| `cv.fr.pdf` | les offres en français | non |
| **`cv.en.pdf`** | les offres en anglais, **tous pays** | **non** |
| `cv.ch.en.pdf` | les offres en anglais **en Suisse** | oui |

Un CV **sans** photo n'est jamais un faux pas ; un CV **avec** photo peut en
être un — politiques anti-discrimination, analyse automatisée des
candidatures — et la photo n'est attendue qu'en Suisse et en Allemagne. D'où un
CV anglais sans photo par défaut, et la version avec photo pour la Suisse.

Attention à l'étiquette `manuel` dans ce cas : un nom sans étiquette reconnue
vaut « pièce universelle », et partirait **en plus** du bon CV.

### Quand deux pièces conviennent : la plus spécifique gagne

Pour une offre **suisse en anglais**, `cv.en.pdf` et `cv.ch.en.pdf` conviennent
tous les deux. Les joindre ensemble remettrait **deux CV dans la même
enveloppe**. La console ne garde donc qu'**une pièce par famille** — la famille
étant le nom avant la première étiquette, ici `cv` — et c'est celle qui porte
**le plus d'étiquettes** qui l'emporte :

> *Version moins spécifique non jointe : cv.en.pdf (au profit de cv.ch.en.pdf).
> Si tu préfères l'autre, télécharge-la depuis l'onglet Documents.*

C'est le même principe que partout ailleurs dans ce projet — le plus spécifique
d'abord — et c'est celui qui a corrigé le choix de la lettre.

**Les trois CV restent dans le kit et téléchargeables**, quelle que soit la
règle : si un recruteur demande explicitement un CV sans photo sur une offre
suisse, ou l'inverse, tu prends l'autre dans l'onglet *Documents*.

### Vérifier avant la première candidature

```bash
./.venv/bin/veille kit
```

Liste ce que contient le kit, les étiquettes détectées, et ce qui partirait
pour une offre française puis pour une offre suisse anglophone.

---

## Les marqueurs disponibles

| Marqueur | Contenu |
|----------|---------|
| `{{titre}}` | Intitulé du poste |
| `{{employeur}}` | Employeur |
| `{{lieu}}` | Lieu annoncé |
| `{{url}}` | Lien vers l'annonce |
| `{{contrat}}` | Type de contrat |
| `{{salaire}}` | Salaire publié, ou `non publie` |
| `{{famille}}` / `{{zone}}` | Clés attribuées par le scoring |
| `{{source}}` | Canal de collecte |
| `{{date}}` / `{{date_iso}}` | Date du jour |
| `{{score}}` | Score de l'offre |

Un marqueur inconnu ou vide **reste visible** dans le fichier généré :

```
[[nom_du_marqueur - A COMPLETER]]
```

C'est délibéré. Une case vide se voit à la relecture ; une valeur inventée,
non.

---

## Après l'envoi

Clique **« Candidature envoyée »** et choisis le canal. La console :

- horodate l'envoi ;
- programme la **relance à 10 jours**, qui apparaît dans l'onglet *Relances* ;
- compte ce canal dans l'entonnoir, pour que tu voies lesquels répondent.

Le délai de relance se règle dans `db.changer_statut(delai_relance_jours=…)`.

---

## Le score de complétude — et pourquoi il n'est pas le score de correspondance

Deux chiffres, deux questions, **jamais mélangés** :

| | Question | Où le voir |
|---|---|---|
| **Score** | ce poste me va-t-il ? | pastille pleine, en haut à droite de la carte |
| **Dossier** *(complétude)* | en sait-on assez pour écrire une candidature qui tienne ? | pastille **encadrée**, sous l'employeur |

Une offre à **110 / dossier 28** est excellente et indocumentée : elle mérite dix
minutes de recherche. Une offre à **25 / dossier 90** est parfaitement documentée
et ne t'intéresse pas. Fusionner les deux ferait disparaître exactement
l'information qui te dit **où passer ton temps**, donc aucune moyenne n'existe
nulle part — et un test le vérifie.

### Ce que la complétude mesure

| Élément | Points | Pourquoi |
|---|---:|---|
| Description complète | 35 | sans elle, une lettre ne peut être que générique |
| Fourchette de salaire | 12 | sinon tu négocies à l'aveugle |
| Ville exacte | 10 | décide si le poste est tenable au quotidien |
| Nom de l'employeur | 10 | impossible d'écrire sur eux sans lui |
| Source primaire | 10 | la version d'origine est plus complète, et donne le process |
| Télétravail / présence | 8 | le critère qui tranche le plus souvent |
| Taille et secteur | 5 | situer l'entreprise vaut mieux que parler de soi |
| Langue attendue | 5 | déterminant sur le bassin bâlois |
| Interlocuteur nommé | 5 | une lettre adressée passe mieux |

**Seuil : 55/100.** En dessous, « Générer le dossier » s'arrête et te dit **ce qui
manque, dans l'ordre, avec le geste qui le comble**. Tu peux passer outre —
*Générer quand même* — mais plus sans le savoir.

**La conséquence pratique.** Le collage du texte complet vaut 35 points à lui
seul, et c'est le seul geste qui débloque à peu près toutes les offres venues
des alertes mail, qui n'en portent qu'un extrait. Filtre sur *dossier
insuffisant* + *score au-dessus du seuil* : score élevé, information trop
mince. Ce sont elles qui méritent tes dix minutes.

---

## Les gabarits de lettre

Un gabarit est **ta** lettre : seuls les passages qui varient deviennent des
marqueurs.

| Marqueur | Rempli par |
|---|---|
| `{{employeur}}` `{{titre}}` `{{date}}` | la console, depuis l'offre |
| `{{source_lisible}}` | le nom du site (LinkedIn, jobs.ch, l'Apec…) |
| `{{contact}}` `{{contact_civilite}}` | **toi**, pour chaque offre — la console les signale |
| `[[…]]` (ton adresse, ton téléphone) | **toi, une seule fois**, dans le gabarit |

Les `[[…]]` du gabarit ne changent pas d'une candidature à l'autre : corrige-les
une fois dans les fichiers du kit et ils ne reviendront plus. Les deux
premiers marqueurs sont de la recherche par offre — trouver le nom d'un
interlocuteur vaut mieux que de le contourner.

### Quelle lettre est choisie

Du plus spécifique au plus général : **atout**, puis **famille**, puis langue,
puis défaut. Dans l'exemple, une offre de test *dans la logistique* prend la
lettre de l'atout logistique, pas la lettre générique.

---

## Ce que « Générer le dossier » produit maintenant

### Deux paquets, et c'est le point important

| Paquet | Contenu | Pour qui |
|---|---|---|
| `<nom_fichier>-candidature.zip` | `<nom_fichier>-Lettre-de-motivation.pdf`, `<nom_fichier>-CV.pdf`, `<nom_fichier>-Dossier-technique.pdf` | **le recruteur** |
| `…-DOSSIER-COMPLET.zip` | tout, dont `fiche-offre.md` | **toi** |

`<nom_fichier>` est `profil.nom_fichier` du fichier de critères (dans l'exemple,
`Camille-Exemple`), et `Candidature` sans lui ([CRITERES.md](CRITERES.md)).

`fiche-offre.md` contient ton score, l'explication ligne à ligne et le texte
brut de l'annonce : c'est ta note de préparation d'entretien. **Elle ne part
jamais.** Le bouton de téléchargement sert le paquet d'envoi ; le dossier
complet se demande explicitement.

Les paquets d'une génération précédente sont **supprimés** à chaque
régénération : un paquet périmé qui traîne est un paquet qui peut partir.

### La lettre est assemblée à partir de l'annonce

Le scoring relève, dans l'annonce, les termes exacts qui comptent. La lettre les
reprend **mot pour mot**, juste après le paragraphe qui nomme le poste :

> *Your advertisement mentions wcag, warehouse management and appium. That
> is precisely the ground I work on today, and what the paragraph above
> describes.*

**Rien n'est inventé.** Chaque phrase vient soit de ton gabarit, soit de
l'annonce ; les seules formulations produites sont des charnières, qui ne disent
rien de toi. Deux exigences au maximum — une lettre qui récite l'annonce se voit
autant qu'une lettre générique.

**C'est déterministe** : deux fois la même offre donne deux fois le même texte.

Si l'annonce n'a qu'un extrait, le paragraphe n'est pas écrit et la console le
dit : *« colle le texte complet, le paragraphe se construira tout seul. »* Elle
ne fabrique rien à partir de rien.

### Le PDF

Rendu par WeasyPrint, installé **dans le venv du projet** — aucun paquet
système, la règle d'isolation tient. Les marqueurs non remplis sont
**surlignés en rouge** dans le PDF : impossible d'envoyer un
`[[contact - A COMPLETER]]` sans le voir.

### La phrase du CV

Pour `[[tailor per application]]`, la console **propose** une phrase construite
à partir de la famille et des atouts déjà attribués : `familles.<f>.formule_cv`
et `atouts.<a>.formule` du fichier de critères. Avec l'exemple, pour une offre
d'automatisation qui demande de l'accessibilité :

> *with a particular interest in test automation for web and mobile
> applications and APIs and digital accessibility testing (WCAG)*

Elle est proposée, **jamais appliquée**, et jamais dans le CV maître. Un CV qui
se réécrit tout seul est un CV que tu ne peux plus défendre en entretien.

---

## Quelle règle choisit les termes cités

Le paragraphe assemblé cite **au plus trois termes**, et seulement ceux qui
figurent dans le **corps** de l'annonce — pas dans son intitulé. Citer un mot du
titre montre qu'on a lu le titre ; citer une exigence enfouie dans la
description montre qu'on a lu l'annonce.

Parmi ceux-là, on garde **les plus rares**, et la rareté se **mesure** sur les
descriptions complètes de ta propre base : le terme cité par le moins
d'annonces passe en premier, et un terme présent dans une annonce sur cinq
n'est jamais retenu.

Un terme rare prouve la lecture ; un terme courant ne prouve rien. Si la base
est indisponible, on retombe sur la longueur du terme — « warehouse
management » est plus spécifique que « wms ».

---

## Le destinataire — mémorisé, jamais obligatoire

Trois champs dans la fiche de l'offre : **nom du recruteur**, **formule
d'appel**, **adresse de l'entreprise**. Ils sont **enregistrés sur l'offre** :
chercher un nom de recruteur prend cinq minutes, ça ne se perd pas à la
régénération suivante.

Ils ne sont **jamais obligatoires**. Il existe des offres où le nom n'est nulle
part, et imposer la saisie transformerait une aide en obstacle. Laissés vides,
ils apparaissent **en rouge dans le PDF**.

---

## L'affinement — un bouton, jamais une étape

### Ce qu'il réutilise

L'affinement **n'utilise aucune clé d'API** : il s'authentifie par le jeton de
Claude Code (`CLAUDE_CODE_OAUTH_TOKEN`, rendu par `claude setup-token`, dans
`config/.env`), et réutilise une installation existante du SDK Agent, que
désigne `VEILLE_SDK_AGENT`. Sans identifiants, son bouton ne s'affiche pas.

**Conséquence : aucune clé à créer, aucune ligne de facturation nouvelle.**

### Ce qu'il a le droit de toucher

Les **transitions**, le **ton**, la **longueur**. Rien d'autre.

### Ce qu'un contrôle refuse

| Refus | Pourquoi |
|---|---|
| chiffre inventé | « 40 scénarios » ne devient pas « 400 » |
| date inventée | |
| sigle, outil ou certification ajouté | le cas le plus dangereux |
| survente (`expert`, `extensive experience`, `proven track record`) | « je n'ai encore mené aucune équipe » ne devient jamais une affirmation |
| marqueur `[[…]]` supprimé | ils signalent ce qu'il doit compléter |
| texte amputé de plus de moitié | |

Un résultat hors bornes **n'est jamais appliqué** : la version assemblée reste
en place et les refus sont affichés nommément.

### La réversibilité

`lettre-de-motivation.md` reste la version assemblée tant qu'il n'a pas validé.
S'il garde la proposition, l'assemblée est conservée sous
`lettre-assemblee.md` : le retour arrière reste possible **après coup**.

> Une lettre qu'il ne reconnaît pas est une lettre qu'il ne défendra pas en
> entretien. C'est le critère qui prime sur la qualité du texte.

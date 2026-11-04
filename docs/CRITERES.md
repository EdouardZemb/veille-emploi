# Modifier les critères

Tout est dans le **`criteres.yaml` de ta configuration** : le dossier que
désigne `VEILLE_CONFIG` (en conteneur, `/config`). Tu es développeur : ce
fichier est fait pour que tu l'ajustes sans repasser par moi.

Sans configuration désignée, la console sert l'exemple livré avec le code,
`exemple/criteres.yaml` : Camille Exemple, une personne inventée, testeuse
logiciel autour de Mulhouse et de Bâle. C'est de lui que viennent les exemples
de ce document, et c'est lui qu'on copie pour commencer une configuration.
Sans configuration désignée, la collecte et le rescorage refusent : ils
noteraient les offres avec les critères de Camille.

Les réglages de l'instance réelle, ses arbitrages et ce que ses rejeux ont
donné sont dans le `docs/CRITERES.md` du dépôt de données.

Après toute modification :

```bash
cd <le clone>
./.venv/bin/veille config verifier <dossier>   # 0 : sain ; 2 : un problème par ligne
./.venv/bin/veille rescorer      # recalcule l'existant
systemctl --user restart veille-web
```

Le bouton **Recalculer** de la console fait exactement la même chose. En
conteneur, la configuration est montée en lecture seule : elle change par une
PR, et arrive par le déploiement.

### Ce que le rescorage a le droit de faire

Le moteur peut revenir sur **ses** décisions, jamais sur les tiennes :

| Situation | Ce qui se passe |
|---|---|
| Offre encore intacte, que les nouveaux critères rejettent | part au rebut, avec son motif |
| Offre écartée **automatiquement**, que les nouveaux critères acceptent | revient dans le flux |
| Offre que **tu** as triée — intéressante, candidature envoyée, écartée avec ton motif | **jamais touchée** |

Le rescorage t'annonce les deux mouvements :

```
120 offre(s) recalculee(s) avec les criteres actuels.
  87 offre(s) partie(s) au rebut : les nouveaux criteres les rejettent.
  (tes propres decisions de tri n'ont pas ete touchees)
```

> Sans la première ligne de ce tableau, une nouvelle règle éliminatoire ne
> nettoyait pas l'historique : les offres étaient bien marquées rejetées, mais
> gardaient leur statut et restaient sous tes yeux. C'est exactement ce qui
> s'est produit en ajoutant la règle géographique.

---

## Le dossier de configuration

| Fichier | |
|---|---|
| `criteres.yaml` | obligatoire, avec `version: 1` à la racine |
| `sources.yaml` | facultatif : les recherches France Travail, les mots-clés d'Arbeitnow, les expéditeurs d'alertes, les flux RSS |
| `gabarits/` | au moins `lettre.md` et `relance.md`, puis les variantes (`lettre_en.md`, `relance_en.md`, `lettre_<famille>[_<langue>].md`, `lettre_atout_<atout>[_<langue>].md`) |
| `empreintes-kit.json` | facultatif : la référence de `veille empreintes-kit` |

`veille config verifier <dossier>` contrôle le tout sans rien modifier, et
rend 0 (`sain`), 2 (un problème par ligne, sur la sortie d'erreur) ou 64
(usage).

### `version`

```yaml
version: 1
```

Obligatoire. Une version absente ou inconnue refuse le chargement, avec un
message qui nomme le fichier et la version lue : la console ne se rabat jamais
sur l'exemple.

### `profil`

```yaml
profil:
  nom: "Camille Exemple"
  nom_fichier: "Camille-Exemple"
```

- `nom` : le nom de la personne.
- `nom_fichier` : le préfixe des noms de fichier qui partent chez un recruteur
  (`Camille-Exemple-Lettre-de-motivation.pdf`,
  `Camille-Exemple-candidature.zip`). Absent : `Candidature`. Une chaîne non
  vide, sans barre oblique, sans barre inversée et sans `..`.

Le reste du bloc (poste, langues, certifications, stack) se lit par toi : il
documente d'où viennent les motifs des atouts.

---

## Les motifs, d'abord

Un `motif` est une expression cherchée dans le texte. La comparaison se fait
**sans accents et sans casse** : écris `bale` ou `Bâle`, c'est pareil.

Un motif ne matche **jamais au milieu d'un mot** : `sre` trouve « Ingénieur
SRE » mais pas « Desree ». C'est ce qui permet d'avoir des motifs courts.

---

## Ajouter un intitulé de poste

Dans `familles`, section correspondante :

```yaml
familles:
  automatisation_tests:
    libelle: "Automatisation des tests (web, mobile, API)"
    poids: 32
    motifs:
      - "test automation"
      - "ton nouvel intitule ici"     # <-- ajoute ta ligne
```

Un motif trouvé dans **l'intitulé** rapporte le poids plein. Trouvé dans la
**description**, il rapporte 40 % (réglable par `scoring.poids_description`).

### Créer une famille entière

Copie n'importe quel bloc. La clé (`automatisation_tests`) sert de filtre dans
la console et de nom de lettre (`lettre_automatisation_tests.md`), le `libelle`
est ce qui s'affiche. Chaque famille a un `poids` numérique et des `motifs` en
liste.

### `formule_cv`

```yaml
  automatisation_tests:
    formule_cv:
      en: "test automation for web and mobile applications and APIs"
      fr: "l'automatisation des tests d'applications web, mobiles et d'API"
```

La fin de la phrase que la console propose pour le CV, « with a particular
interest in … » (« avec un intérêt particulier pour … »), quand l'offre reçoit
cette famille ([CANDIDATURE.md](CANDIDATURE.md)). Sans elle, aucune phrase
n'est proposée.

### La hiérarchie des familles

Les poids disent où tu veux être placée. Dans l'exemple, l'automatisation des
tests (32), sa première porte, passe devant le test fonctionnel et la
performance ; le pilotage, qui l'attire sans qu'elle ait encore mené d'équipe,
reste en retrait. Le commentaire en tête du bloc `familles` dit pourquoi :
écris-y les raisons des tiens, c'est ce qui permet de les revoir plus tard.

Une famille qu'on ne veut plus voir en tête ne s'écarte pas : on baisse son
poids. Le jour où l'on veut y revenir, on le remonte, puis un `veille
rescorer` suffit.

---

## L'allemand : recevable plus tard, pas refusé

```yaml
langues:
  allemand_exige:
    poids: -10
    eliminatoire: false
    mise_en_attente: false     # <-- le réglage
```

`mise_en_attente: true` sort les offres germanophones du flux courant et les
range dans le statut **différée**, consultable par le filtre *Statut* de la
console. **Aucune n'est perdue.**

Le jour où ton allemand suffit, repasse à `false`, lance `veille rescorer`, et
elles reviennent toutes d'un coup dans ta liste.

Entre-temps, tu peux aussi simplement remonter `poids` vers `-5` puis `0` au
fur et à mesure de ta progression.

---

## La langue de l'annonce — à ne pas confondre avec l'exigence

**Deux choses différentes, deux réglages différents.** La section ci-dessus,
`langues:`, traite de ce que le poste **exige** : « sehr gute
Deutschkenntnisse », « allemand courant ». La section `langue_annonce:` traite
de la langue dans laquelle l'annonce est **rédigée**.

Une annonce peut être écrite en allemand sans exiger l'allemand, et une annonce
écrite en anglais peut exiger un allemand courant. Les deux règles coexistent.

```yaml
langue_annonce:
  de:
    libelle: "Annonce en allemand"
    mise_en_attente: true      # <-- LE RÉGLAGE
    motif: "annonce en allemand : langue non maîtrisée à ce jour"
```

Avec `mise_en_attente: true`, les annonces allemandes passent en statut
**différée** — consultables par le filtre *Statut* de la console, avec leur
motif écrit. Aucune n'est perdue, aucune n'est supprimée.

### Pour les faire revenir

```yaml
    mise_en_attente: false
```

puis `veille rescorer`. **Elles reviennent toutes d'un coup, score intact.**
Rien d'autre à toucher, aucun code à reprendre.

### ⚠️ L'exception qui compte : la langue de travail

À Bâle, une annonce rédigée en allemand peut décrire un poste dont la langue
de travail est l'anglais : plusieurs grands employeurs de la région travaillent
en anglais. **Quand l'annonce le dit, la console ne met pas l'offre de côté** :
elle la laisse dans le flux avec une contribution
`A VÉRIFIER - Langue de travail anglaise annoncée`, et c'est toi qui tranches.

```yaml
    exception_langue_de_travail:
      motifs:
        - "arbeitssprache ist englisch"
        - "english is our working language"
        - ...
```

Mieux vaut quelques fausses alertes qu'une bonne offre perdue. Ajoute une
formulation à cette liste dès que tu en croises une qui aurait dû compter.

**Ces motifs sont cherchés dans le texte débarrassé du bruit de l'agrégateur.**
Sans ce nettoyage, le pied de page d'Arbeitnow — *« Find more English Speaking
Jobs in Germany »* — ferait passer toutes les annonces allemandes pour des
postes anglophones.

Une annonce qui demande *« Deutsch und Englisch »* demande les deux : elle ne
dit pas que l'anglais est la langue de travail, et n'est pas une exception.

---

## Les atouts — ce que tu apportes, et qui s'additionne

Différence avec les familles : une offre ne reçoit **qu'une** famille, la mieux
placée. Les atouts, eux, **se cumulent** par-dessus.

```yaml
atouts:
  accessibilite:
    libelle: "Accessibilité numérique (RGAA, WCAG)"
    poids: 25
    plafond: 25        # un seul déclenchement suffit
    motifs: ["accessibilite numerique", "rgaa", "wcag", ...]
```

`plafond` borne le total du groupe : une annonce qui énumère quinze
technologies ne doit pas gonfler son score plus qu'une qui en cite trois.
Quand le plafond mord, l'explication affiche « plafonné ».

### `poids_par_pays` — quand la même compétence ne vaut pas pareil

```yaml
  domaine_logistique:
    poids: 8                   # défaut si le pays est inconnu
    poids_par_pays:
      france: 6
      suisse: 12
```

Dans l'exemple, Bâle est une plaque tournante de la logistique : ses éditeurs
de logiciels logistiques paient l'expérience du métier plus qu'en France. Même
compétence, deux valeurs. Un atout peut aussi être monnayable d'un côté de la
frontière et bloqué de l'autre, derrière une exigence de langue.

### `champs` — la clé pour éviter le bruit

Par défaut un atout est cherché dans tout le texte. `champs` restreint :

```yaml
  domaine_logistique:
    champs: ["titre", "employeur"]
```

**Pourquoi ça existe.** Un mot de secteur cherché dans tout le texte se
déclenche sur ses sens voisins. Dans l'exemple, la description parle souvent
des transports en commun ou de leur prise en charge, sans rapport avec le
poste ; et un entrepôt de données (« data warehouse ») n'a rien de logistique.
Un atout de domaine qui cherche son mot dans tout le texte se
déclenche presque toujours à tort ([METHODE.md](METHODE.md)).

Retenir la règle : **si un motif est un mot courant ailleurs, restreins les
champs et préfère des expressions de plusieurs mots.** Mieux vaut rater un
bonus que le distribuer au hasard — c'est le classement qui est en jeu.

### `ignorer_contextes`

```yaml
  accessibilite:
    ignorer_contextes: [recrutement]
```

Les phrases d'un contexte déclaré dans `contextes_ignores` (ici, celles qui
parlent du processus de recrutement : « notre processus de recrutement est
accessible ») ne déclenchent pas l'atout.

### `mis_en_avant` — l'atout que la console met en avant

```yaml
  accessibilite:
    mis_en_avant:
      libelle: "Accessibilité"
      titre: "Offres qui demandent des tests d'accessibilité numérique"
      bouton: "Accessibilité"          # facultatif
      bouton_titre: "…"                # facultatif
```

Un seul atout au plus. Les offres qui le portent reçoivent une étiquette
(`libelle`, et `titre` au survol), et un bouton dans la barre de la console les
isole d'un clic. `bouton` et `bouton_titre` sont le texte du bouton et son
survol ; absents, ils reprennent `libelle` et `titre`. Sans atout mis en avant,
le bouton ne s'affiche pas.

### `formule`

```yaml
  accessibilite:
    formule:
      en: "digital accessibility testing (WCAG)"
      fr: "les tests d'accessibilité numérique (RGAA, WCAG)"
```

Le complément de la phrase du CV : « … and digital accessibility testing
(WCAG) », quand l'offre porte cet atout. La première formule des atouts de
l'offre s'ajoute à celle de sa famille.

### Ajuster un atout

Si un atout fait remonter trop de bruit, baisse-le plutôt que de le supprimer —
et regarde d'abord quels motifs se déclenchent : souvent un seul, trop large.

Le bouton de l'atout mis en avant isole d'un coup les offres qui le portent,
chacune avec l'explication de ce qui l'a déclenché.

---

## Changer un plancher de salaire

```yaml
salaire:
  france:
    plancher: 38000        # sous ce seuil : ÉLIMINATOIRE
    cible_basse: 42000
    cible_haute: 55000
```

Le jugement porte sur la **borne haute** annoncée — c'est ce qui est
négociable. Une offre sans salaire publié n'est **jamais** écartée : elle est
signalée dans l'explication, et c'est tout.

---

## Assouplir ou durcir l'allemand

C'est le réglage qui bouge le plus, quand on progresse.

```yaml
langues:
  allemand_exige:
    poids: -10             # la pénalité actuelle
    eliminatoire: false    # mets true pour les faire disparaître
```

- **Tu progresses** → remonte `poids` vers `-5`, puis `0`.
- **Tu veux arrêter de les voir** → `eliminatoire: true`.

---

## Ajouter un critère éliminatoire

```yaml
eliminatoires:
  mon_critere:
    libelle: "Ce qui s'affichera comme motif"
    motifs:
      - "expression a detecter"
```

Une offre qui déclenche un éliminatoire part directement au rebut, **avec son
motif**, et ne remonte jamais dans le flux.

---

## Géographie — la règle la plus stricte du dispositif

C'est le seul endroit où **une offre parfaite peut être refusée** : une annonce
qui n'est pas en télétravail et qui est trop loin de chez toi n'a rien à faire
dans ta liste.

### Trois cas, un seul passe

| Situation | Décision |
|---|---|
| **Télétravail complet** | recevable, où que soit l'employeur |
| **Présence attendue, zone atteignable** | recevable, selon le rayon |
| **Présence attendue, hors zone** | **ÉLIMINATOIRE**, quel que soit le score |

### Des rayons, des listes

```yaml
zones:
  zone_proche:          # ~15 km — présentiel 5j/5 accepté
    acces: quotidien
    motifs: [saint-louis, huningue, basel, ...]

  zone_occasionnelle:   # ~80 km — 2 jours par semaine au plus
    acces: hybride
    motifs: [colmar, belfort, olten, ...]
```

**Pour élargir ou resserrer ta géographie** : coupe une ville d'une liste,
colle-la dans l'autre. C'est le seul geste.

La distinction sert vraiment : dans l'exemple, un poste à Colmar **tous les
jours** est refusé, le **même poste deux jours par semaine** passe.

### Quatre niveaux de télétravail

Le bloc `geographie` les détecte, dans cet ordre :

| Niveau | Déclenché par | Effet |
|---|---|---|
| `presentiel` | `presence_totale_motifs` — « présentiel », « 5 days a week » | zone quotidienne seulement |
| `partiel` | `presence_partielle_motifs` — « hybrid », « 2 jours par semaine » | zone quotidienne ou hybride |
| `complet` | `teletravail_complet_motifs` — « fully remote », « 100 % remote » | recevable partout |
| `inconnu` | rien de tout cela | zone quotidienne ou hybride, et signalé |

**Le niveau `inconnu` est le plus important à comprendre.** La plupart des
annonces ne disent pas un mot du télétravail, surtout côté France Travail.
Assimiler ce silence à une exigence de présence écarterait la moitié des
offres d'une région. L'offre passe donc si le lieu est atteignable, et
l'explication affiche « Télétravail non précisé — à demander au premier
contact ».

### Pourquoi la détection est si prudente

Trois pièges, tous rencontrés sur de vraies annonces :

1. **« remote-first » n'est pas un engagement.** Une offre à Zurich disait
   *« remote-first culture with hybrid options (office in Zürich) »* et se
   retrouvait **en tête de liste**. Une formulation de culture ne vaut pas un
   contrat : seuls les engagements fermes comptent.
2. **Un avantage n'est pas une exigence.** Ma première correction écartait à
   tort les postes réellement distants, parce que « home office budget »
   apparaissait dans leurs avantages. `presence_partielle_motifs` ne contient
   donc que des formulations de **fréquence de présence**.
3. **L'agrégateur ajoute son propre texte.** Arbeitnow colle
   *« Find Jobs in Switzerland on Arbeitnow Full remote possible. »* en fin de
   description. Des offres présentielles passaient pour distantes.
   `bruit_agregateur` le retire avant toute analyse.

### Deux signalements, sans écartement

- **Employeur suisse en télétravail complet** : au-delà de 40 % de télétravail
  depuis la France, le statut de frontalier est remis en cause. Réglable par
  `suisse_teletravail_complet` : `signaler` (défaut), `ecarter` ou `ignorer`.
- **Employeur lointain en télétravail complet** : « fully remote » à Londres ou
  à New York veut presque toujours dire « fully remote dans ce pays ». Il faut
  une entité qui puisse t'employer depuis la France (`employeur_lointain_motifs`).

### Et les autres zones

Elles se jugent sur le **champ lieu**, jamais sur la description — sans quoi un
poste à Coire se retrouvait crédité de « Bâle » parce que l'employeur
citait Bâle dans sa présentation.

### `indices_lieu` — reconnaître un lieu dans un courriel

```yaml
geographie:
  indices_lieu:
    - "haut-rhin"
    - "sundgau"
    - "mulhouse"
```

Dans une ligne de courriel d'alerte « Entreprise · Lieu », ce qui désigne un
lieu. Le lecteur de courriels a ses indices génériques (pays, cantons…) ; cette
liste les complète avec ceux de ta région, pour qu'un nom de lieu ne soit pas
pris pour un employeur.

---

### Quand l'annonce ne donne qu'une région

« Grand Est, France (Sur site) » couvre, pour Camille, Huningue (son
agglomération) et Sedan (à l'autre bout de la région). Le moteur ne peut ni
l'écarter sur la distance, ni lui donner les points d'une zone atteignable.

Il l'écartait, et des offres de la famille la mieux notée se perdaient ainsi.
France Travail rendra beaucoup de lieux de ce grain, donc la règle compte.

Des grains, parce qu'ils ne valent pas la même chose (l'exemple en a trois) :

```yaml
geographie:
  lieux_imprecis:
    proches:            # ta région : imprécis, mais l'information reste positive
      poids: 0
      motifs: ["sundgau", "haut rhin", "nordwestschweiz", …]
    larges:             # une région large qui te contient à peine
      poids: -5
      motifs: ["grand est", "baden wurttemberg", …]
    lointains:          # ne dit rien de la ville
      poids: -12
      motifs: ["france entiere", "plusieurs sites", "romandie", …]
```

Dans tous les cas l'offre **reste dans le flux**, avec la ligne
*« Lieu imprécis — à vérifier »* et le conseil de demander la ville au premier
contact. Elle ne reçoit aucun point de zone : on ne crédite pas ce qu'on ne
sait pas.

Un lieu n'est imprécis que s'il ne reste **rien** après avoir retiré le motif
et les mots vides (`lieu_imprecis_bruit`) : `Mulhouse, Grand Est` reste précis
et garde sa zone.

Si tu trouves qu'une région traîne trop d'offres inutiles, déplace-la vers un
grain plus lointain : elle perd des points et redescend au fond de la liste,
sans disparaître.

---

## Un éliminatoire à deux étages : `toujours_motifs` et `sauf_si`

Une offre à laquelle on ne peut pas prétendre n'a pas sa place dans le flux,
même en bas — c'est pour ça qu'un autre métier est un **critère éliminatoire**
et pas un malus.

### Le piège, et comment la règle l'évite

Dans l'exemple, l'automatisme industriel (automates, robots, convoyeurs, mise
en service) est un autre métier que celui de Camille, mais il emploie les mêmes
mots que son premier métier, l'automatisation des tests : « automatisation »,
« automation », « automaticien ». Et les entrepôts de son domaine recrutent les
deux. Une exclusion sur le mot seul lui coûterait **sa famille la mieux
notée**.

L'ordre, du plus spécifique au plus général :

1. l'**intitulé** porte-t-il un des `motifs` ? sinon la règle ne s'applique pas ;
2. un signal industriel **sans ambiguïté** — `automate programmable`, `plc`,
   `robotique`, `mise en service` (`toujours_motifs`) ? alors on écarte, même
   si le reste plaide pour ;
3. l'offre a-t-elle reçu une **famille** de son métier
   (`sauf_si.famille_attribuee`) ? alors on garde ;
4. l'annonce porte-t-elle un **signal de son terrain** — test, recette,
   logiciel, ses outils (`sauf_si.motifs`) — dans l'intitulé, l'employeur ou le
   corps ? on garde ;
5. sinon seulement, on écarte.

L'asymétrie est voulue : **un faux maintien te coûte un coup d'œil, un faux
écartement te coûte un poste.**

### Le régler

```yaml
eliminatoires:
  automatisme_industriel:
    champs: ["titre"]           # le métier est nommé dans l'intitulé
    motifs: ["automatisme", "automatisation", "automation", …]
    toujours_motifs: […]        # écartent même si une famille est reconnue
    sauf_si:
      famille_attribuee: true
      champs: ["titre", "employeur", "description"]
      motifs: ["test", "recette", "logiciel", "software", "wms", …]
```

- **Une offre écartée à tort ?** ajoute son signal dans `sauf_si.motifs`.
- **Une offre d'un autre métier qui passe encore ?** si le mot ne peut rien
  vouloir dire d'autre, mets-le dans `toujours_motifs` ; sinon laisse-la, elle
  est bas classée.

`tests/test_automatisme_industriel.py` verrouille le mécanisme sur 37 cas
inventés, avec leur employeur. Pour ta propre configuration, garde de même un
corpus pris dans ta base : modifie la configuration, rejoue-le, et il te dira
immédiatement si tu viens de perdre un poste.

---

## Régler le seuil de notification

```yaml
scoring:
  seuil_interessant: 40    # au-dessus : mis en avant ET notifié
```

C'est le seul curseur qui pilote les notifications : en dessous, ton téléphone
ne sonne pas. Monte-le si tu es dérangé pour rien, descends-le si tu rates des
choses.

Le seuil **vit dans la base** (table `reglages`, clé `seuil`) et se règle dans
Réglages, depuis le téléphone. La valeur de `seuil_interessant` dans
`criteres.yaml` n'est que la graine : elle est importée une seule fois, au
premier démarrage, puis ne sert plus. Changer ce fichier ensuite ne change pas
le seuil.

---

## Ce qu'aucune lettre ne doit affirmer : `affirmations_refusees`

```yaml
affirmations_refusees:
  - libelle: "Allemand courant"
    valeur: "Ne jamais écrire qu'elle parle allemand couramment : elle est au niveau A2."
    provenance: "exemple inventé — profil, langues"
    motifs:
      - "allemand courant"
      - "fluent in german"
```

Facultatif. Une liste de règles, chacune une affirmation fausse qui survit à sa
correction, et qu'un motif rattrape mieux qu'une relecture. La porte de
validation cherche les motifs mot pour mot dans chaque paragraphe de la lettre,
et bloque l'envoi.

- `libelle`, `valeur` et `provenance` : des chaînes non vides. `provenance` dit
  d'où vient la règle, pour remonter à la décision.
- `motifs` : une liste de chaînes, comparées sans accents ni casse.

**Tout ou rien** : une entrée mal formée rend la liste vide, et le contrôle se
déclare `indisponible` plutôt que de vérifier une partie des règles en disant
`ok`. `veille config verifier` nomme l'entrée fautive. Clé absente : aucune
règle.

---

## La préparation d'entretien : `entretien`

```yaml
entretien:
  declencheurs:
    - cle_section: "votre allemand suffira t il"
      categorie: "attaque"
      pourquoi: "l'annonce demande l'allemand : elle en est au niveau A2"
      motifs: ["deutschkenntnisse", "german", "allemand"]
    - cle_section: "pourquoi la suisse"
      categorie: "attaque"
      pays: "ch"
  intitules_a_risque:
    motifs: ["test manager", "head of qa"]
    avertissement: "ton fichier 17 dit que ces postes demandent d'avoir déjà mené une équipe…"
```

Facultatif. La préparation d'entretien lit le fichier de questions du kit et
retient les sections qui concernent l'annonce.

- **`declencheurs`** : les questions que le parcours de la personne appelle.
  Celles qui se posent à tout candidat (« avez-vous écrit ce code », le
  préavis, « pourquoi vous partez », le salaire, les questions à poser, la
  liste d'avant chaque entretien) sont dans le code ; celles de la
  configuration passent devant, et une clé redéclarée remplace la question
  générique de même clé.
  - `cle_section` (obligatoire) : un fragment du titre de la section, sans
    accents ni ponctuation ;
  - `categorie` (obligatoire) : `attaque`, `appui` ou `rituel` ;
  - `pourquoi` : la raison affichée ;
  - `motifs` : sans eux, le point sort toujours ; avec eux, la phrase de
    l'annonce qui porte le premier motif trouvé devient l'ancrage — du plus
    spécifique au plus général ;
  - `pays: ch` réserve le point aux postes en Suisse.
- **`intitules_a_risque`** : des `motifs` d'intitulé et l'`avertissement`
  (non vide) qu'ils déclenchent. Absent : aucun avertissement.

Une entrée mal formée est écartée, et la préparation le signale (« lance
`veille config verifier` ») : sans clé de section, elle trouverait la première
section venue.

---

## La boucle de correction, au bout de trente offres

L'onglet **Pilotage** agrège tes motifs d'écartement. C'est la donnée la plus
utile du dispositif : elle dit ce que le scoring rate.

Lis la colonne **score moyen** de ce tableau :

- Motif fréquent **avec un score élevé** → le scoring fait remonter quelque
  chose qu'il devrait pénaliser. Ajoute un motif éliminatoire, ou un poids
  négatif.
- Motif fréquent **avec un score faible** → le scoring a déjà raison, tu
  confirmes seulement son classement. Rien à faire.

C'est pour ça que le motif est obligatoire quand tu écartes une offre.

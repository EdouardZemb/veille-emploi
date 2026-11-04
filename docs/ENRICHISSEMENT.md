# Lire le texte complet d'une annonce — étude préalable

> **Statut : proposition, rien n'est implémenté.** Ce document rend compte des
> vérifications faites le 28/09/2026 et propose un dispositif. À valider avant
> de coder. Les relevés faits ce jour-là sur la base de l'instance réelle sont
> dans le `docs/ENRICHISSEMENT.md` du dépôt de données.

## Le problème, mesuré

**La plupart des offres au-dessus du seuil sont marquées « données
partielles »** : celles qui viennent des alertes mail. Le scoring ne travaille
alors que sur l'intitulé, le lieu et un extrait de quelques dizaines de
caractères.

Conséquence : les critères éliminatoires **ne peuvent pas s'appliquer**. Le
travail en soirée, l'astreinte, le week-end, l'allemand exigé sont dans le corps
de l'annonce, qu'on ne lit jamais. On écarte sur des indices, et on laisse
passer des offres qu'on aurait dû éliminer.

## La distinction retenue

| | |
|---|---|
| **Interdit, et le reste** | ouvrir toutes les annonces à chaque collecte, sur une tâche planifiée, sans lui. C'est du moissonnage. |
| **D'une autre nature** | aller chercher **une** page, **au moment où il marque une offre intéressante**. Une requête, déclenchée par une action humaine, sur une annonce qu'il vient de décider de lire. |

C'est le rôle déjà prévu pour le navigateur dans le cadrage initial :
« accompagner une candidature précise, avec lui présent ».

---

## Ce que disent les sources — vérifié, pas supposé

`robots.txt` récupéré et analysé le 28/09/2026, bloc `User-agent: *`, règle la
plus spécifique l'emportant.

| Source | Directive pour `*` | Page visée | Verdict |
|---|---|---|---|
| **LinkedIn** | **`Disallow: /`** | `/jobs/view/…` | ⛔ **INTERDIT** |
| **Indeed** | `Disallow: /viewjob` | `/viewjob?jk=…` | ⛔ **INTERDIT** |
| **jobs.ch** | aucune règle applicable | `/en/vacancies/detail/<id>` | ✅ autorisé |
| **arbeitnow** | `Disallow:` (vide) | `/jobs/companies/…` | ✅ autorisé |
| **apec.fr** | aucune règle | pages d'offres | ✅ autorisé |

> ⚠️ **Piège rencontré.** Un premier résumé automatique du `robots.txt` de
> LinkedIn affirmait qu'il n'y avait *pas* de `Disallow: /` global. C'est faux :
> le fichier brut, 4861 lignes, contient bien `User-agent: *` suivi de
> `Disallow: /`. **Toujours lire le fichier, jamais un résumé.**

### Essai réel sur les sources autorisées

Une requête par domaine, espacées de cinq secondes :

| Source | Résultat |
|---|---|
| **jobs.ch** | HTTP 200, **4095 caractères** extraits contre 53 aujourd'hui. Le texte contient *« Fliessende Deutsch- und gute Englischkenntnisse »* — précisément un critère qu'on ne sait pas appliquer. |
| **arbeitnow** | HTTP 410 *Gone* : l'offre a expiré. Sans objet de toute façon — l'API fournit déjà la description complète. |
| **apec.fr** | HTTP 404 : le lien est un redirecteur à jeton, déjà périmé. |

### Sur les liens de suivi

Ils ne sont **pas** résolus par le réseau dans la plupart des cas : les liens
LinkedIn et Indeed portent l'identifiant de l'offre, et `collectors/liens.py`
reconstruit l'URL canonique **hors ligne**, par expression régulière. Aucune
requête n'est émise, donc aucun clic n'est comptabilisé par l'émetteur.

**Défaut séparé constaté** : les liens Apec (`neomarket.diffusion.apec.fr/r?e=…`)
ne sont pas reconnus comme redirecteurs, ne sont donc pas résolus, **et
répondent 404**. Les offres Apec du flux n'ont pas de lien ouvrable — ni pour
le programme, ni pour lui. À corriger indépendamment de cette étude.

---

## Le verdict qui dérange

**Le dispositif, appliqué proprement, ne couvrirait qu'une petite part des
offres au-dessus du seuil.**

| Source | Enrichissable ? |
|---|---|
| LinkedIn | non, interdit |
| arbeitnow | inutile, déjà complet |
| jobs.ch | **oui** |

Sur la base de l'instance réelle, la plupart des offres au-dessus du seuil
venaient de LinkedIn. Le gain se concentre là où c'est interdit. Ce n'est pas une raison d'abandonner
— jobs.ch et les pages carrières monteront en volume dès que les alertes
employeurs produiront — mais il faut le dire avant de construire.

---

## Le dispositif proposé

### 1. Enrichissement à la demande, sources autorisées

Déclenché par **une action humaine** : passage au statut « intéressante », ou
bouton *Lire l'annonce complète*. Jamais en lot, jamais planifié.

- **Liste blanche par domaine** dans `sources.yaml`, avec un verdict explicite
  `autorise` / `interdit` et la raison.
- **`robots.txt` revérifié en direct** avant chaque requête, mis en cache 24 h.
  La liste blanche ne suffit pas : une politique peut changer.
- **Un seul appel**, en-tête `User-Agent` identifiant l'outil et l'usage
  personnel.
- **Délai minimal de 20 secondes entre deux récupérations**, tous domaines
  confondus, et **file d'attente** s'il marque dix offres d'affilée. Jamais de
  rafale.
- **Plafond quotidien** (30 pages) comme garde-fou.

### 2. Refus explicite et visible

Sur LinkedIn et Indeed, le bouton ne tente rien. Il affiche :

> *Lecture automatique impossible : le robots.txt de ce site l'interdit.
> Ouvre l'annonce dans ton navigateur — tu y es connecté — puis colle le texte
> ci-dessous.*

### 3. Le collage manuel — la vraie réponse pour LinkedIn

Un champ de texte dans la fiche de l'offre. Il ouvre l'annonce dans **son**
navigateur, où il est connecté et voit tout, sélectionne, colle. Le texte est
enregistré, l'offre **rescorée**, l'explication mise à jour.

**Couverture : 100 %, LinkedIn compris. Requêtes automatisées : zéro.** C'est
lui qui lit, le programme ne fait que scorer. Deux gestes, et aucune règle
franchie.

### 4. Ce que produit l'enrichissement, quel que soit le canal

- **Rescorage** avec les critères qui ne pouvaient pas s'appliquer : horaires,
  astreinte, week-end, langue, salaire.
- **Alerte visible** si un critère éliminatoire apparaît dans le texte complet
  alors que l'offre était au-dessus du seuil. *« Cette offre semblait parfaite
  et demande des astreintes le week-end »* — c'est le cas le plus utile.
- **Marquage honnête de l'échec** : si la récupération échoue ou revient vide,
  la fiche affiche *« texte complet non récupéré »* plutôt que de laisser croire
  que l'annonce est pauvre. Une page rendue en JavaScript donne peu ou rien : il
  faut le dire.
- **Dossier de candidature enrichi** : les gabarits disposent du vrai texte.

### 5. Limites à ne pas laisser dériver

À reporter dans `LIMITES.md` si le dispositif est retenu :

- déclenchement **humain uniquement**, jamais depuis `veille-collecte.timer` ;
- **une page à la fois**, 20 secondes minimum entre deux ;
- **liste blanche + robots.txt**, les deux, pas l'un ou l'autre ;
- **jamais de contournement** : pas de navigateur sans tête, pas de cookie de
  session, pas d'en-tête falsifié pour passer pour un humain.

---

## Ce qui rapporterait davantage, et tout de suite

**France Travail, tant qu'il n'est pas branché.** Son API fournit la
description complète, gratuitement, de plein droit, sans la moindre question de
robots.txt — et couvre le marché français, un gros gisement en télétravail.

Il ne lui faut que ses recherches, dans le `sources.yaml` de la configuration,
et `FT_CLIENT_ID` et `FT_CLIENT_SECRET`.

**Recommandation : brancher France Travail d'abord.** Le problème des données
partielles s'y règle à la racine, pour un coût nul et sans aucune zone grise.
L'enrichissement à la demande vient ensuite, pour jobs.ch et les pages
carrières.

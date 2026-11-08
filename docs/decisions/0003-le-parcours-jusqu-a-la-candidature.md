# ADR-0003 — Le parcours jusqu'à la candidature : une file, une fiche par état, un bouton

- **Statut** : proposé le 2026-11-08
- **Contexte amont** : la demande d'Edouard du 2026-11-08, « simplifier le système et le rendre plus
  direct sur les fonctionnalités, jusqu'à une candidature », cadrée le même jour (13 questions, les
  réponses par défaut retenues) ; `docs/CANDIDATURE.md` ; `docs/FONCTIONNEMENT.md` ; ADR-0002 (la
  console en conteneur, dont l'invariant « on ajoute avant d'enlever » vaut ici pour la base)

## Contexte

La console a grandi lot après lot, et chaque lot a ajouté son écran, son statut ou son bouton. Le
2026-11-08, elle compte :

- **sept onglets** : Offres, Relances, Archive, À classer, Pilotage, Documents, Réglages ;
- **onze statuts** : `nouveau`, `a_traiter`, `interessante`, `differee`, `candidature_envoyee`,
  `relance_envoyee`, `reponse_recue`, `entretien`, `refus`, `accepte`, `ecartee`. Trois d'entre eux,
  `a_traiter`, `interessante` et `differee`, disent presque la même chose à l'écran ;
- **neuf boutons sur chaque carte d'offre** : Générer le dossier, Intéressante, À traiter,
  Candidature envoyée, Mot de relance, Écarter, Préparer l'entretien, Détail, Obsolète ;
- **une fiche d'une douzaine de blocs** : pourquoi ce score, le texte complet (le récupérer ou le
  coller), les exigences (relever, valider, oublier, puis recalculer), « encore en ligne ? », le
  destinataire, les notes, la complétude, le dossier, l'affinement de la lettre, l'entretien, la
  relance, l'historique. Rien n'y dit quelle est la prochaine chose à faire ;
- **sept filtres** au-dessus de la liste, plus le recalcul, l'atout mis en avant et « À
  documenter ».

La mise au point du score (« À classer », les exigences, le recalcul) se mêle au travail
quotidien, qui est de décider d'une offre puis d'y candidater. Aller d'une offre à une candidature
envoyée demande une dizaine de gestes : lire, compléter le texte, relever les exigences, marquer
l'offre, générer le dossier, l'affiner peut-être, télécharger, envoyer hors de l'application, puis
le dire à la console.

Le vrai frein du dossier est mesurable dans `completude.py` : la description complète de l'annonce
y pèse 35 points sur 100, et le seuil d'un dossier est 55. Une annonce reçue en extrait (moins de
400 caractères, ou marquée données partielles) passe donc presque toujours sous le seuil. Les
autres manques, le salaire, le contact, la taille de l'entreprise, sont rarement bloquants.

## Options

- **A. Une file, une fiche par état, un bouton.** Trois écrans : « À faire », « Candidatures »,
  « Plus ». Cinq états à l'écran au lieu de onze statuts. La fiche ne montre que ce que l'état
  demande, avec une action principale. Un bouton « Préparer ma candidature » enchaîne ce qui se
  fait seul et ne s'arrête que sur ce qui manque. Il retire vraiment des choix à chaque écran, sans
  toucher à la collecte, au score ni à la base.
- **B. Un parcours guidé posé sur l'existant.** Les onglets et la fiche restent ; un bandeau
  « prochaine étape » s'ajoute à chaque offre, et les blocs secondaires se replient. Moins cher,
  sans risque, mais la complexité reste visible dès qu'on sort du bandeau : la demande n'est servie
  qu'à moitié.
- **C. Deux applications.** La candidature au téléphone (la file, les candidatures), un « atelier »
  sur le poste (les critères, le classement, le pilotage, les réglages), à deux adresses. Le
  partage est net, mais il fait deux interfaces à tenir pour un seul utilisateur ; l'écran « Plus »
  de A en obtient presque autant.

## Décision

**L'option A**, livrée en trois lots, après la clôture du #12. Ce qui suit est la spécification
commune aux trois ; chaque lot a son issue, son plan et son étiquette.

### 1. Cinq états, lus sur les onze statuts

Les cinq états ne sont qu'une **lecture** des statuts enregistrés. La base ne change pas : aucune
migration, aucune colonne, et l'image précédente lit toujours la base, ce qui garde le retour
arrière par simple déploiement de l'étiquette d'avant.

| État affiché | Statuts lus | Statut écrit par la nouvelle interface |
|---|---|---|
| À voir | `nouveau` ; `a_traiter`, affiché « Plus tard » | `a_traiter` (« Plus tard ») |
| Je postule | `interessante` | `interessante` |
| Envoyée | `candidature_envoyee`, `relance_envoyee`, `reponse_recue` | `candidature_envoyee`, `relance_envoyee` |
| Entretien | `entretien` | `entretien` |
| Close | `ecartee`, `refus`, `accepte`, avec leur motif | `ecartee` (motif obligatoire), `refus`, `accepte` |

- `differee`, la mise de côté automatique du score, n'est dans aucun des cinq : elle reste hors de
  la file, et se retrouve dans le Bilan, sous « mises de côté ».
- `reponse_recue` n'est plus écrit : « Entretien », « Refus » et « Acceptée » suffisent. Les offres
  qui le portent déjà s'affichent « Envoyée ».
- « Plus tard » écrit `a_traiter`, qui fait partie des statuts protégés d'un archivage automatique
  (`verification.STATUTS_PROTEGES`) : une offre remise à plus tard n'est pas archivée sans preuve.
- Une fonction pure, `etat_de(offre) -> str`, fait la traduction. Elle est la seule à la faire,
  côté serveur, et l'API rend l'état avec l'offre.

### 2. Trois onglets

**À faire**, **Candidatures**, **Plus**. L'en-tête ne garde que le titre : « Notifications » et
« Quitter » vont dans Réglages (lot 3). Jusqu'au lot 3, « Plus » donne accès aux anciens écrans,
inchangés : rien ne disparaît avant d'avoir sa place.

### 3. La file « À faire » (lot 1)

Une route, `GET /api/a-faire`, compose la file, dans cet ordre :

1. **À finir** : ce qui attend un geste, avec sa raison.
   - `relance_due` : une candidature dont la relance est due (`db.relances_dues`, l'actuel onglet
     Relances) ;
   - `a_envoyer` : « Je postule » avec un dossier généré ;
   - `a_preparer` : « Je postule » sans dossier, laissé en cours de route.
2. **À voir** : les offres `nouveau` dont le score atteint le seuil de notification, par score
   décroissant, et le nombre de celles qui sont sous le seuil, avec un lien vers elles.
3. **Plus tard** : les offres `a_traiter`, repliées.

La carte d'une offre à voir porte l'intitulé, l'employeur, le lieu, le salaire, les deux
contributions positives les plus fortes de l'explication du score, et **trois boutons** : « Je
postule », « Plus tard », « Non ».

« Non » ouvre un petit panneau. Le motif reste obligatoire (les motifs disent ce que le score
rate) : les motifs les plus fréquents s'y choisissent en un toucher, un champ libre reste, et
« N'est plus en ligne » archive l'offre comme l'actuel « Obsolète » (`/constat`).

### 4. La fiche par état (lot 1)

La fiche ne montre qu'une ligne d'actions, celle de l'état de l'offre :

| État | Action principale | Actions secondaires |
|---|---|---|
| À voir | Je postule | Plus tard, Non |
| Je postule, sans dossier | Préparer ma candidature | — |
| Je postule, dossier prêt | Je l'ai envoyée | les pièces, l'annonce, le destinataire, affiner la lettre |
| Envoyée | Mot de relance, puis Relancée | Réponse : Entretien, Refus, Acceptée |
| Entretien | Préparer l'entretien | Réponse : Refus, Acceptée |

En dessous, repliés : « Pourquoi ce score », « Notes », et « Autres actions » (le texte complet,
« encore en ligne ? », les exigences, l'historique, le retour à « À voir », qui écrit `nouveau`).
Chaque bouton écrit un statut existant par les routes actuelles.

L'onglet **Candidatures** groupe les offres Je postule (avec « dossier prêt » ou « à préparer »),
Envoyée (avec la date de relance) et Entretien. Les candidatures closes vont au Bilan.

### 5. « Préparer ma candidature » (lot 2)

« Je postule » met l'offre en `interessante` **et lance aussitôt la préparation** : un toucher
sépare la file du dossier quand rien ne manque.

Un module, `preparation.py`, porte une fonction, `preparer(offre_id, texte=None, forcer=False,
regenerer=False)`, qui rend l'étape suivante. La route `POST /api/offres/{id}/preparer` la sert.
Elle n'appelle que l'existant, sans le changer :

1. une offre `nouveau` ou `a_traiter` passe en `interessante`, journalisé ;
2. un `texte` fourni est enregistré d'abord (`enrichissement.appliquer_texte`) : un échec ensuite
   ne le perd pas (invariant 2 du projet) ;
3. si la description reste un extrait : lecture automatique quand la source l'autorise et que la
   cadence le permet (`enrichissement.politique`, `verifier_cadence`, `recuperer`) ; sinon, ou si
   la lecture échoue, l'étape **`texte`**, avec la raison en une ligne et l'adresse de l'annonce ;
4. si la complétude reste sous 55 et que `forcer` est faux : l'étape **`mince`**, avec les deux ou
   trois manques les plus lourds ; « Générer quand même » relance avec `forcer` ;
5. sinon, la génération (`dossier.generer`) : l'étape **`pret`**, avec les pièces d'envoi.

Une génération en échec rend sa cause, l'offre reste « Je postule », et la fiche propose
« Réessayer ». Le bouton se désactive pendant le travail, avec le temps écoulé : un double toucher
ne lance rien deux fois.

**L'écran « Dossier prêt »** liste les pièces d'envoi, chacune téléchargeable (un formulaire en
ligne, au téléphone, les demande une à une), et le paquet d'envoi en zip, sans la note de
préparation. Il dit à qui la lettre est adressée. **Le destinataire n'est jamais demandé avant** :
« Ajouter un destinataire » enregistre ses champs (route existante), avec la référence de
l'annonce proposée, puis régénère par `preparer(regenerer=True)`. Une régénération suit
l'invariant 4 du projet : ce qu'elle remplace, la lettre affinée comprise, entre d'abord dans
l'historique.

Les exigences ne font pas partie du parcours : elles affinent le score et envoient le texte à un
tiers. Elles restent dans « Autres actions ».

### 6. L'écran « Plus » (lot 3)

Une liste : « Chercher une offre », puis :

- **Toutes les offres** : l'actuel onglet Offres, avec trois filtres au lieu de sept, la recherche,
  l'état (les cinq, plus « mises de côté ») et la famille. La bascule de l'atout mis en avant reste,
  en puce. Partent : la liste des atouts, le filtre et le tri par vérification (la fraîcheur se lit
  dans la fiche), « voir les écartées » (l'état Close le remplace) et « À documenter » (le parcours
  du lot 2 demande le texte d'une offre mal documentée dès « Je postule ») ;
- **Mes critères** : l'actuel « À classer », le recalcul de tous les scores, et le rappel que les
  critères se changent dans la configuration de l'instance ;
- **Bilan** : l'entonnoir, le rendement des sources et les motifs d'écartement de l'actuel
  Pilotage, puis trois listes repliées, les archivées (avec « Remettre dans le flux »), les closes
  (avec leur motif) et les mises de côté ;
- **Documents** et **Réglages**, inchangés, sauf « Notifications » et « Quitter », qui arrivent
  dans Réglages.

La pastille de l'onglet « Plus » ne compte que les offres à classer, le seul geste qui y attend.
Les nouvelles archivées s'annoncent sur la ligne du Bilan. Les anciennes vues sortent d'`app.js`,
et les paramètres d'API qu'elles seules utilisaient (`a_documenter`, `verification`, `tri`) sont
retirés avec leurs tests : l'interface et l'API sortent de la même image.

### 7. Les tests, écrits d'abord

- `etat_de` : un cas par statut, `differee` compris.
- `/api/a-faire` : l'ordre des groupes, le seuil, les trois raisons d'« À finir ».
- `preparer`, avec de faux voisins : texte complet → `pret` ; extrait et source autorisée → lecture
  puis `pret` ; source interdite ou cadence dépassée → `texte` ; texte fourni puis génération en
  échec → texte enregistré, offre « Je postule » ; complétude sous 55 → `mince`, puis `forcer` →
  `pret` ; `regenerer` → la version remplacée est dans l'historique.
- Dans un vrai navigateur (`tests_navigateur/`, le job `navigateur` de la CI) : le parcours sur le
  jeu factice, de la file à « Je l'ai envoyée », en passant par le texte collé et « Dossier prêt ».
  Le test des cibles tactiles passe sur les nouveaux écrans.
- Le jeu factice reçoit au besoin une offre par état. Il reste écrit à la main (M-0001).
- **La mutation**, obligation du projet qui n'y existait pas encore, commence ici : un job de CI
  limité à `etat_de` et à `preparation.py`. Ses survivants se lisent dans la revue finale de chaque
  lot.

### 8. La livraison

| Lot | Contenu | Étiquette |
|---|---|---|
| 1 | les cinq états, la file « À faire », la fiche par état, l'onglet Candidatures | `v0.2.0` |
| 2 | « Préparer ma candidature » | `v0.3.0` |
| 3 | l'écran « Plus » et le ménage des filtres | `v0.4.0` |

Chaque lot suit le cycle du modèle (`docs/modele/methode.md`), passe par le staging et se vérifie
au téléphone avant son étiquette, qu'Edouard pose. La documentation suit lot par lot :
`docs/FONCTIONNEMENT.md` (le tableau des onglets), `docs/CANDIDATURE.md` (« Générer le dossier »
devient « Préparer ma candidature »), le README et `CLAUDE.md`.

### Hors périmètre

La collecte, le score et les notifications ; la base (ramener vraiment les statuts à cinq serait un
lot à part, une fois les cinq états éprouvés) ; l'envoi d'une candidature par l'application ; la
suite de l'éditeur de lettre (E2 et après), qui rejoindra plus tard l'écran « Dossier prêt » ; la
fin du mode systemd ; tout changement de langage.

## Conséquences

- La console se lit en trois écrans, et chaque écran propose une action principale. Le chemin
  d'une offre bien documentée à son dossier tient en un toucher, et celui d'un extrait en un
  collage de plus.
- La mise au point du score quitte le travail quotidien sans disparaître : elle vit dans « Mes
  critères ».
- Deux vocabulaires coexistent : les cinq états à l'écran, les onze statuts en base et dans
  l'entonnoir. `etat_de` est le seul pont, et ses tests le gardent.
- Les écrans qui partent (Relances, Archive, À classer, Pilotage, l'ancien onglet Offres) ne
  partent qu'au lot 3, une fois leur contenu replacé.

### Difficile à changer

- La table des états : une interface, un test et une habitude s'y appuient. La changer, c'est un
  nouvel ADR.
- « Je postule » qui lance la préparation : si l'on revient à deux gestes séparés, le compte des
  « à préparer » d'« À finir » change de sens.

## Révision

- Après un mois d'usage du lot 2 : si « À finir » accumule des « à préparer » jamais repris, le
  geste « Je postule » est trop engageant, et la préparation redevient un bouton à part.
- Si les cinq états tiennent trois mois sans exception, un lot peut ramener les statuts de la base
  à cinq, par une migration qui garde l'image précédente lisible.
- Si une étape demande souvent le destinataire avant la génération, il remonte avant le dossier.

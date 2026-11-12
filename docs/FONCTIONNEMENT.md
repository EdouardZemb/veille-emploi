# Comment marche la console : la collecte, le score, les notifications

Une seule page pour **voir** les offres qui te correspondent, les **trier**,
**déclencher** le dossier de candidature, **piloter** l'avancement, consulter
tes **documents** et ajuster tes **réglages**. Elle a trois onglets.

| Onglet | Ce qu'on y fait |
|--------|-----------------|
| **À faire** | d'abord « À finir » (relance due, dossier prêt à envoyer, dossier à préparer), puis « À voir » (au plus 50 offres au-dessus du seuil, avec des liens vers les autres et vers celles sous le seuil), puis « Plus tard », replié. Chaque carte a trois boutons : *Je postule*, *Plus tard*, *Non* (un motif, les fréquents en un toucher, ou « N'est plus en ligne ») |
| **Candidatures** | trois groupes : *Je postule* (« dossier prêt » ou « à préparer »), *Envoyée* (avec la date de relance) et *Entretien* |
| **Plus** | les anciens écrans, jusqu'au lot 3 de l'ADR-0003 : *Toutes les offres*, *Relances*, *Archive*, *À classer*, *Pilotage*, *Documents* et *Réglages* (appareils connectés, seuil de notification, fréquence de collecte, état des sources) |

Toucher une notification ouvre « À faire ».

### Les cinq états d'une offre

L'état n'est qu'une lecture des onze statuts enregistrés : la base ne change
pas (`src/veille/etats.py`, [ADR-0003](decisions/0003-le-parcours-jusqu-a-la-candidature.md), § 1).

| État affiché | Statuts lus |
|---|---|
| À voir | `nouveau` ; `a_traiter`, affiché « Plus tard » |
| Je postule | `interessante` |
| Envoyée | `candidature_envoyee`, `relance_envoyee`, `reponse_recue` |
| Entretien | `entretien` |
| Close | `ecartee`, `refus`, `accepte`, avec leur motif |

`differee`, la mise de côté automatique du score, est hors des cinq états et
hors de la file. La fiche d'une offre n'a qu'une ligne d'actions, celle de son
état. Au lot 1, une offre « Je postule » sans dossier propose « Générer le
dossier » ; « Préparer ma candidature » viendra au lot 2. Trois volets restent
repliés : « Pourquoi ce score », « Notes » et « Autres actions » (le détail
complet, et « Revenir à « À voir »»).

La configuration (critères, sources, gabarits) est un dossier que désigne
`VEILLE_CONFIG`. Sans lui, la console sert l'exemple livré avec le code,
[`exemple/`](../exemple/) — Camille Exemple, une personne inventée — et refuse
de collecter. `veille config verifier <dossier>` dit si un dossier est sain.

## Le principe de collecte

**On ne va pas chercher les annonces : on ingère ce que les sites envoient.**

Trois canaux, par ordre de fiabilité :

1. **API officielles** — France Travail (publique, gratuite), Arbeitnow.
2. **Flux RSS** publiés par les sites.
3. **Alertes mail** sur recherches enregistrées — c'est ce qui débloque tout le
   reste : LinkedIn, Indeed, jobs.ch, et les employeurs sans API ni flux, dont
   la page carrières envoie des alertes.

Deux avantages au canal mail : les filtres de LinkedIn sont meilleurs que ce
qu'on reconstituerait de l'extérieur, donc on hérite de ton ciblage et le
scoring affine par-dessus ; et les employeurs sans API entrent enfin dans le
dispositif.

> ⛔ **Aucun parcours automatisé de LinkedIn**, ni d'un site qui l'interdit.
> Ton compte est l'infrastructure de ta recherche. Voir
> [LIMITES.md](LIMITES.md).

La collecte tourne plusieurs fois par jour, après les envois d'alertes. Sa
fréquence se change dans Réglages, parmi celles que la console propose ; les
heures par défaut sont dans `src/veille/reglages.py`.

Chaque soir, la passe de vérification relit les annonces déjà collectées. Une
offre dont l'annonce a quitté son site, constaté par deux vérifications
espacées, part dans l'archive. La passe ne sonde jamais un site qui l'interdit,
et n'archive jamais une offre que tu as triée, ni une offre dont tu as généré
le dossier. En prod, le planificateur la lance à l'heure que fixe
`src/veille/planificateur.py`, jamais pendant une collecte ; `veille verifier`
la lance à la main.

## Le score

Chaque règle produit une ligne : un libellé, des points, une raison. **Le score
est exactement leur somme** — l'explication affichée dans la console *est* le
calcul, il n'y a rien derrière. Avec les critères de l'exemple :

```
+32  Famille : Automatisation des tests (web, mobile, API)   "test automation" dans l'intitule
+18  Zone : Télétravail intégral                              "full remote" dans le texte de l'annonce
+12  Salaire publié                                           48 000 EUR - dans ta cible
────
 62
```

Une règle **éliminatoire** ne met pas le score à zéro : elle range l'offre au
rebut avec son motif, et le score reste calculé pour que tu puisses vérifier
que le rejet est justifié.

### Les atouts

Une offre ne reçoit qu'**une** famille de métier, mais les **atouts se
cumulent** par-dessus : ce que tu apportes et que d'autres n'apportent pas.

Dans l'exemple, le plus lourd est **l'accessibilité numérique** (`+25`), l'atout
rare de Camille. Viennent ensuite les applications mobiles (`+8`), les outils
de test qu'elle pratique (pytest, Postman, Appium… `+5` chacun, plafonné), sa
stack et le domaine de la logistique, qui ne vaut pas pareil en France et en
Suisse (`poids_par_pays`, [CRITERES.md](CRITERES.md)).

Un atout peut être **mis en avant** (`mis_en_avant`, un seul au plus) : son
bouton, dans la barre de la console, isole d'un clic les offres qui le portent.

Quand une alerte mail ne contient qu'un extrait, l'offre est marquée **données
partielles** : le score ne porte alors que sur l'intitulé et le lieu, et
l'explication le dit — plutôt que de faire semblant.

## Les notifications

Le **push web** est le canal principal : téléphone Android, PWA installable sur
l'écran d'accueil ([DEMARRAGE.md](DEMARRAGE.md), § 5), notification dès qu'une
offre dépasse le seuil de notification, réglé dans Réglages. Son prérequis est
le HTTPS — c'est la première brique à valider, tout le volet mobile en dépend.

Le **mail** est le repli, et ne part que si aucun push n'a pu être remis. Il
sort par `smtp.gmail.com:587` avec le même mot de passe d'application que
l'IMAP — *pas* par un serveur de messagerie local, qui souvent n'achemine rien
vers l'extérieur.

Si les deux canaux échouent, `veille etat` l'affiche sur la ligne
`notification`.

## Le code

Un module par responsabilité, sous `src/veille/` ; la docstring de chacun dit
ce qu'il fait. Les collecteurs sont sous `src/veille/collectors/`, et chaque
format d'alerte mail y a son parseur, sous `collectors/parsers/`.

### Ajouter un site d'alerte mail

1. copie `collectors/parsers/generique.py` en `mon_site.py` ;
2. adapte `reconnait()` (expéditeur/sujet) et `extraire()` (structure HTML) ;
3. inscris la classe dans `parsers/__init__.py`, **avant** `ParseurGenerique`
   qui accepte tout et doit rester en dernier.

Rien d'autre à toucher.

### Ce que les tests gardent

En priorité, les règles dont l'erreur coûterait cher : les critères
éliminatoires, les planchers salariaux, la durée minimale d'intérim suisse — et
les régressions déjà rencontrées sur de vraies données (zone déduite de la
prose, poste republié sous un nouvel identifiant, page principale en erreur
500). La commande qui les lance est dans [CLAUDE.md](../CLAUDE.md#commandes).

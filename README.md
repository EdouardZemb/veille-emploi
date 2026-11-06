# Console de recherche d'emploi

Une seule page pour **voir** les offres qui te correspondent, les **trier**,
**déclencher** le dossier de candidature, **piloter** l'avancement, consulter
tes **documents** et ajuster tes **réglages**.

## 🔗 L'adresse de la console

Servie en HTTPS : sur ton tailnet uniquement pour la console du tailnet, à
l'adresse publique pour la console en conteneur
([exploitation.md](docs/exploitation.md)). L'adresse de l'instance réelle est
dans le `README.md` du dépôt de données.
Sur Android : ouvre l'adresse dans Chrome → menu **⋮** → *Ajouter à l'écran
d'accueil*, puis **Notifications** dans la console.

| Onglet | Ce qu'on y fait |
|--------|-----------------|
| **Offres** | lire, trier, écarter avec motif, générer un dossier |
| **Relances** | les candidatures dont la relance est due |
| **Pilotage** | l'entonnoir, le rendement des sources, les motifs d'écartement |
| **Documents** | ton kit et tes dossiers générés, téléchargeables depuis le téléphone |
| **Réglages** | appareils connectés, seuil de notification, fréquence de collecte, état des sources |

---

## Démarrer

👉 **[docs/DEMARRAGE.md](docs/DEMARRAGE.md) — ce que tu dois faire, toi.**
Rien ne peut être collecté avant.

| Document | Pour quoi |
|----------|-----------|
| [DEMARRAGE.md](docs/DEMARRAGE.md) | Ce que tu dois faire toi : mot de passe Gmail, France Travail, HTTPS, passkeys, PWA |
| [ALERTES.md](docs/ALERTES.md) | Ce que la console filtre déjà — pour ne pas filtrer deux fois dans tes alertes |
| [CRITERES.md](docs/CRITERES.md) | Le fichier de critères : un intitulé, un plancher, l'exigence d'allemand, chaque clé |
| [CANDIDATURE.md](docs/CANDIDATURE.md) | Le bouton « Générer le dossier », brancher ton kit |
| [DONNEES.md](docs/DONNEES.md) | Où vivent tes données, sauvegarde, effacement |
| [ENRICHISSEMENT.md](docs/ENRICHISSEMENT.md) | Lire le texte complet d'une annonce : l'étude et ses mesures |
| [exploitation.md](docs/exploitation.md) | La console en conteneur : le staging, le journal, la sauvegarde, la restauration |
| [LIMITES.md](docs/LIMITES.md) | Ce que ce dispositif ne fait pas, et pourquoi |
| [METHODE.md](docs/METHODE.md) | Pourquoi le scoring se teste sur de vraies annonces, tôt |

Ces documents valent pour toute instance. Ce qui ne vaut que pour l'instance
réelle (son serveur, ses chemins et ses adresses, ses arbitrages, les constats
sur sa base) est dans le `docs/` du dépôt de données, sous le nom du
document d'origine.

La configuration (critères, sources, gabarits) est un dossier que désigne
`VEILLE_CONFIG`. Sans lui, la console sert l'exemple livré avec le code,
[`exemple/`](exemple/) — Camille Exemple, une personne inventée — et refuse de
collecter. `veille config verifier <dossier>` dit si un dossier est sain.

### Vérifier où on en est

```bash
./.venv/bin/veille tester-sources        # chaque source : joignable ? identifiants ?
./.venv/bin/veille tester-notification   # push et repli mail
./.venv/bin/veille kit                   # ce qui partirait dans un dossier
```

Ces trois commandes disent ce qui marche déjà et ce qui attend encore une
action de ta part.

---

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
> [LIMITES.md](docs/LIMITES.md).

---

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
Suisse (`poids_par_pays`, [CRITERES.md](docs/CRITERES.md)).

Un atout peut être **mis en avant** (`mis_en_avant`, un seul au plus) : son
bouton, dans la barre de la console, isole d'un clic les offres qui le portent.

Quand une alerte mail ne contient qu'un extrait, l'offre est marquée **données
partielles** : le score ne porte alors que sur l'intitulé et le lieu, et
l'explication le dit — plutôt que de faire semblant.

---

## Commandes

Depuis le clone de la console (le chemin de l'instance réelle est dans
le `README.md` du dépôt de données) :

```bash
cd <le clone>

./.venv/bin/veille collecter          # tous les collecteurs (c'est ce que fait le timer)
./.venv/bin/veille collecter --source courriel --jours 3
./.venv/bin/veille rescorer           # après modification des critères
./.venv/bin/veille etat               # résumé en console
./.venv/bin/veille config verifier <dossier>   # la configuration est-elle saine ? (0, 2 ou 64)
./.venv/bin/veille tester-mail        # diagnostic IMAP étape par étape
./.venv/bin/veille tester-notification --envoyer   # éprouve push + repli mail
./.venv/bin/veille lien               # lien à usage unique (24 h) pour enregistrer une passkey
./.venv/bin/veille passkeys           # les passkeys ; --retirer <n°> révoque celle d'un appareil perdu
```

`collecter` et `rescorer` refusent sans configuration désignée : ils
noteraient les offres avec l'exemple.

## Notifications

Le **push web** est le canal principal : téléphone Android, PWA installable sur
l'écran d'accueil, notification dès qu'une offre dépasse `seuil_interessant`.
Son prérequis est le HTTPS — c'est la première brique à valider, tout le volet
mobile en dépend.

Le **mail** est le repli, et ne part que si aucun push n'a pu être remis. Il
sort par `smtp.gmail.com:587` avec le même mot de passe d'application que
l'IMAP — *pas* par un serveur de messagerie local, qui souvent n'achemine rien
vers l'extérieur.

Si les deux canaux échouent, `veille etat` l'affiche sur la ligne
`notification`.

### Services

Ce qui suit est la console du tailnet (systemd), jusqu'à la fin du lot #12. La console en
conteneur, depuis le lot #11 : le staging, les journaux et les sauvegardes sont dans
[docs/exploitation.md](docs/exploitation.md).

```bash
systemctl --user status veille-web.service
systemctl --user list-timers veille-collecte.timer
journalctl --user -u veille-web.service -f
journalctl --user -u veille-collecte.service -n 50
```

Par défaut, la collecte tourne **à 7h15, 12h15 et 18h15**, après les envois d'alertes.
La fréquence se change dans Réglages, depuis la console, parmi celles qu'elle propose :
sur la console du tailnet, elle vit dans `veille-collecte.timer` ; en conteneur, en base,
où le planificateur la lit (`src/veille/reglages.py`).

---

## Architecture

Un module par responsabilité ; la docstring de chacun dit ce qu'il fait.

```
src/veille/
├── app.py             FastAPI — la console et son API JSON
├── cli.py             la ligne de commande `veille`
├── config.py          chargement de la configuration (YAML) + normalisation de texte
├── models.py          Offre, canonisation d'URL, empreintes de déduplication
├── db.py              SQLite, sans ORM
├── reglages.py        le seuil et la fréquence de collecte, réglés depuis la console
├── collecte.py        la collecte : chaque source, puis les notifications
├── planificateur.py   la collecte et la purge en conteneur, sans minuteur systemd
├── scoring.py         le moteur de score, une fonction par règle
├── classement.py      une famille proposée aux offres qui n'en ont aucune
├── completude.py      ce qu'on sait d'un poste : le score de complétude
├── enrichissement.py  le texte complet d'une annonce, et le rescore avec lui
├── verification.py    l'annonce est-elle encore en ligne ?
├── exigences.py       les exigences d'une annonce collée, que le modèle propose
├── auth.py            sessions (180 jours), liens à usage unique, cookie
├── passkeys.py        cérémonies WebAuthn (enregistrement, connexion)
├── debit.py           limite de débit, par clé, en fenêtre glissante
├── dossier.py         génération du dossier de candidature
├── documents.py       ses documents, depuis la console
├── empreintes.py      le kit a-t-il bougé sans qu'on le dise ?
├── lettre.py          la lettre comme objet rédigé, et non comme artefact dérivé
├── assemblage.py      une lettre assemblée de ses phrases et des mots de l'annonce
├── affinement.py      affiner une lettre assemblée, sur demande seulement
├── porte.py           la porte de validation, rejouée sur le texte qui part
├── preferences.py     la lecture du magasin de préférences
├── rendu.py           la lettre en PDF, sous un nom qu'un recruteur peut recevoir
├── relance.py         le mot de relance
├── entretien.py       préparer l'entretien d'une offre, à partir de ses réponses
├── notifications.py   push web (VAPID) + repli mail
├── instantane.py      les instantanés que la sauvegarde du modèle appelle
├── factice.py         le jeu de données factice du staging
├── static/            la PWA : app.js, connexion.js, sw.js, style.css, icônes
├── templates/         connexion.html, index.html, lien.html
└── collectors/
    ├── base.py             socle commun aux collecteurs
    ├── france_travail.py   API officielle (OAuth2 client_credentials)
    ├── arbeitnow.py        API publique, sans identifiants
    ├── rss.py              flux déclarés dans sources.yaml
    ├── courriel.py         IMAP — lit UNIQUEMENT le libellé configuré
    ├── liens.py            résolution des redirecteurs de suivi
    └── parsers/            un parseur par format d'alerte : generique, indeed, jobs_ch, linkedin
```

### Ajouter un site d'alerte mail

1. copie `collectors/parsers/generique.py` en `mon_site.py` ;
2. adapte `reconnait()` (expéditeur/sujet) et `extraire()` (structure HTML) ;
3. inscris la classe dans `parsers/__init__.py`, **avant** `ParseurGenerique`
   qui accepte tout et doit rester en dernier.

Rien d'autre à toucher.

---

## Tests

```bash
cd <le clone> && ./.venv/bin/python -m pytest tests/ -q
```

Environ deux mille tests. Ils couvrent en priorité les règles dont l'erreur
coûterait cher : les critères éliminatoires, les planchers salariaux, la durée
minimale d'intérim suisse — et les régressions déjà rencontrées sur de vraies
données (zone déduite de la prose, poste republié sous un nouvel identifiant,
page principale en erreur 500).

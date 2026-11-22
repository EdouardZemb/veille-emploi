# Ce que tu dois faire, toi

Rien ne peut être collecté avant ces étapes. Elles sont dans l'ordre : la 1 et
la 2 débloquent le plus gros volume, la 4 et la 5 ouvrent la console sur ton
téléphone, avec ses notifications. La numérotation garde la place de l'ancienne
étape 3, les certificats HTTPS d'une console servie hors conteneur, qui n'a plus
lieu d'être : la console en conteneur est servie en HTTPS à son adresse
publique ([`exploitation.md`](exploitation.md)).

Les commandes `veille` visent la console de la prod, dans son conteneur : sur
le serveur, `docker exec veille-emploi-app-1 veille …`, ou, depuis le poste,
`ssh <le serveur> "docker exec veille-emploi-app-1 veille …"`. Celles qui
préparent un fichier, comme une configuration, se lancent sur le poste, dans le
clone, en mode local (`.venv\Scripts\veille …`). Les valeurs de l'instance
réelle (le serveur, l'adresse de la console, l'emplacement de la liste de ses
alertes) et sa bascule vers les passkeys sont dans le `docs/DEMARRAGE.md` du
dépôt de données.

---

## 0. Désigner la configuration

La console lit ses critères, ses sources et ses gabarits dans le dossier que
désigne `VEILLE_CONFIG` (en conteneur, `/config`). Sans configuration désignée,
elle sert l'exemple livré avec le code, `exemple/`, et **refuse de collecter** :
elle noterait les offres avec les critères d'une personne inventée. En mode
local (sans `VEILLE_EMPLOI_ENV`), un bandeau le dit, et les gestes sur une offre
(dossier, relance, recalcul, affinement) sont refusés aussi. Pour essayer la
console sur l'exemple, désigne-le, depuis le clone : `VEILLE_CONFIG=exemple`.

Pour commencer : copie `exemple/`, remplis-le, puis, sur le poste,
`.venv\Scripts\veille config verifier <dossier>`, qui rend `sain` (code 0). En
prod, la configuration vit au dépôt de données, que la chaîne monte sur
`/config` ([`exploitation.md`](exploitation.md)) ; sur le poste, pose
`VEILLE_CONFIG=<dossier>` dans l'environnement ou dans le fichier que désigne
`VEILLE_ENV`. La structure du fichier de critères est dans
[`CRITERES.md`](CRITERES.md).

---

## 1. Créer tes alertes mail, site par site

C'est le principe de collecte du dispositif : **on ne va pas chercher les
annonces, on ingère les alertes que les sites envoient**. Tu crées la recherche
une fois, chez eux, avec leurs filtres — qui sont meilleurs que ce qu'on
reconstituerait de l'extérieur. Notre scoring affine par-dessus.

### 1.a — Aucun filtre Gmail à créer

**Cette étape a disparu.** Le collecteur demande directement au serveur Gmail
les messages venant des adresses d'alerte connues, et ne reçoit que ceux-là.
La liste est dans le `sources.yaml` de ta configuration, bloc `courriel`. Celle
de l'exemple couvre déjà LinkedIn, Indeed, jobs.ch, jobup.ch, France Travail,
l'APEC et les principales plateformes de recrutement ; ajoute-y les employeurs
que tu vises.

Tu peux donc passer directement au mot de passe d'application.

> **Sur la confidentialité, pour que ce soit clair.** Un mot de passe
> d'application Gmail donne accès à **toute** ta boîte — il n'existe aucun
> moyen de le limiter à un libellé. C'était déjà vrai avec la méthode du
> filtre. Ce qui délimite la lecture, c'est ce programme, pas Gmail.
>
> Concrètement, en mode `expediteurs` : la recherche est exécutée **par le
> serveur Gmail**, et seuls les messages correspondants sont transférés ici.
> Le reste de ta correspondance n'est jamais téléchargé.
>
> Si tu préfères malgré tout la barrière du libellé, mets `mode: libelle` dans
> le `sources.yaml` de ta configuration et crée le filtre — le code le gère
> toujours.

Le mode par défaut est **`union`** : recherche par expéditeur **et** lecture du
libellé `veille-emploi` s'il existe. Le libellé devient un *filet* — si un
filtre que tu crées attrape une source absente de ma liste, elle rentre quand
même. Sans filtre, il ne coûte rien.

### 1.b — Le mot de passe d'application Gmail

Le collecteur tourne sur le serveur, sans session Claude : il lui faut un accès
IMAP autonome.

1. <https://myaccount.google.com/security> → active la **validation en deux
   étapes** si ce n'est pas fait
2. <https://myaccount.google.com/apppasswords> → crée un mot de passe
   d'application nommé `veille-emploi`
3. Range les 16 caractères dans KeePassXC, puis refais les secrets de la prod
   avec eux, sans leurs espaces, sous `VEILLE_IMAP_MOTDEPASSE` (« Secrets »
   dans [`exploitation.md`](exploitation.md)) ; sur le poste, mets-les dans le
   fichier que désigne `VEILLE_ENV`

Ce n'est **pas** ton mot de passe Gmail, et il est révocable seul, à tout
moment, sans toucher à ton compte.

**C'est la seule étape que personne ne peut faire à ta place.** Une fois
posée et entrée en service, en prod par l'étiquette de données suivante
(« Secrets » dans [`exploitation.md`](exploitation.md)), sur le serveur :

```bash
docker exec veille-emploi-app-1 veille tester-mail              # ce que le collecteur voit
docker exec veille-emploi-app-1 veille decouvrir-expediteurs    # les alertes déjà dans ta boîte
```

`decouvrir-expediteurs` cherche des **sujets** typiques d'alerte et ne lit que
les en-têtes `De:` et `Objet:` — jamais le corps des messages. Il te rend la
liste des expéditeurs trouvés, en marquant ceux qui manquent à la
configuration, prêts à coller.

### 1.c — Les recherches à enregistrer

👉 **Elles vivent dans un seul document**, celui que tu tiens à jour pour ta
recherche (pour l'instance réelle, une fiche de son kit de candidature). Il
fait foi, et lui seul.

[`ALERTES.md`](ALERTES.md) dit ce que la console filtre **déjà** — à lire une
fois, pour ne pas filtrer deux fois et perdre les cas limites.

Une liste tenue en double — ici et ailleurs — finit par diverger, sans que
personne s'en aperçoive. **Un seul document fait foi.**

Pour chaque ligne, il donne : le site, la requête exacte à coller, la zone et
les filtres — LinkedIn, jobs.ch, Apec, France Travail, Indeed — et dit ce
qu'il faut **supprimer**.

> ⚠️ Tant que France Travail n'est pas branché, les alertes mail sont le seul
> canal qui couvre ton marché réel. C'est la seule étape que personne ne peut
> faire à ta place.

---


## 2. France Travail

API officielle, publique et gratuite — le canal le plus fiable côté français,
et le **seul** qui livre le texte intégral des annonces. Les recherches sont
dans le `sources.yaml` de ta configuration, bloc `france_travail` : une par
zone et par famille de métiers que tu vises.

Les identifiants (`FT_CLIENT_ID`, `FT_CLIENT_SECRET`) vont dans les secrets
de la prod (« Secrets » dans [`exploitation.md`](exploitation.md)) ; sur le
poste, dans le fichier que désigne `VEILLE_ENV`, lisible par toi seul.

### Si l'authentification est refusée

Le service répond alors :

```
HTTP 400  {"error":"invalid_client","error_description":"Client authentication failed"}
```

Ce message veut dire **une seule chose** : le serveur d'authentification de
France Travail ne reconnaît pas ce couple identifiant / clé. Ce n'est ni un
problème de format de requête, ni de périmètre, ni de délai — une application
dont l'abonnement n'est pas encore effectif obtient un jeton, et c'est l'appel
à l'API qui échouerait ensuite.

Trois causes possibles, dans l'ordre de fréquence :

1. **La clé secrète a été régénérée.** francetravail.io ne l'affiche qu'une
   fois. Si tu as cliqué à nouveau sur *Générer*, l'ancienne est morte, même si
   elle est encore affichée dans ton presse-papiers ou ton gestionnaire.
2. **L'identifiant et la clé viennent de deux applications différentes** — c'est
   vite arrivé avec deux onglets ouverts.
3. **L'application a été supprimée puis recréée** sous le même nom.

Dans les trois cas la réparation est la même : sur <https://francetravail.io>
→ **Mes applications**, ouvrir l'application, régénérer la clé secrète,
**ranger les deux valeurs ensemble** dans KeePassXC (l'identifiant *et* la
nouvelle clé, recopiés du même écran), puis refaire les secrets (plus haut).

### Vérifier

Sur le serveur, une fois les secrets en service :

```bash
docker exec veille-emploi-app-1 veille etat      # dit si le jeton s'obtient
docker exec veille-emploi-app-1 veille collecter --source france_travail --jours 3
```

`veille collecter`, lancée ainsi, tourne à côté du planificateur de la console,
sans son verrou : pas aux heures de la fréquence.

`veille etat` n'affiche jamais la valeur d'un secret, et masque tout secret que
le service distant renverrait dans son message d'erreur.

### Révoquer ces identifiants

Comme pour le mot de passe d'application Gmail, c'est révocable seul, sans
toucher au reste.

1. <https://francetravail.io> → **Mes applications** → ton application
2. Soit **régénérer la clé secrète** — l'ancienne cesse immédiatement de
   fonctionner, la console s'arrête sur cette source et continue sur les
   autres ; soit **supprimer l'application**, ce qui coupe définitivement.
3. Des identifiants révoqués ne servent plus : la console s'arrête sur cette
   source à chaque collecte. Les retirer des secrets de la prod, c'est retirer
   une clé (« Secrets » dans [`exploitation.md`](exploitation.md), « Une clé
   ajoutée ou retirée »). Sur le poste, efface les deux lignes du fichier que
   désigne `VEILLE_ENV`.

Sans identifiants, le collecteur France Travail **se met en pause proprement** :
il ne fait pas échouer la collecte, les alertes mail et Arbeitnow continuent.

Ces identifiants ne donnent accès qu'aux **offres d'emploi publiques**. Ils ne
touchent ni à ton dossier de demandeur d'emploi, ni à tes données personnelles
France Travail, ni à ton espace personnel.

---

## 4. Se connecter : les passkeys

La console n'a pas de mot de passe. Tu t'y connectes avec une **passkey** : tu
déverrouilles ton téléphone, et c'est tout. Le serveur ne garde que la clé
publique. La session dure 180 jours, et chaque usage la prolonge.

Un appareil sans passkey entre par un **lien à usage unique**, valable 24
heures, de la forme `<origine>/lien#<jeton>`. Le jeton est dans le fragment :
il ne part jamais au serveur ni dans un journal.

### Le premier appareil

👤 Sur le serveur, pour le conteneur de la prod :

1. 👤 **L'origine doit être exacte.** En conteneur, c'est
   `VEILLE_EMPLOI_URL_PUBLIQUE`, que la chaîne pose d'après l'`env/` du dépôt
   de données : l'adresse publique de la console. Sur le poste, c'est
   `VEILLE_URL`, dans le fichier que désigne `VEILLE_ENV`.
   `docker exec veille-emploi-app-1 veille etat` : sa ligne
   `Connexion : 0 passkey, origine …` donne **exactement** l'adresse de la
   barre d'adresse du téléphone. Si elle dit la connexion indisponible,
   l'origine manque.

   > ⚠️ Ce n'est pas qu'une affaire de connexion. La passkey se lie au nom
   > d'hôte de cette origine, et **toute requête qui écrit** dans la console
   > (`POST`, `PUT`, `PATCH`, `DELETE`, la déconnexion comprise) est refusée en 403 si son
   > en-tête `Origin` n'est pas cette origine. Si l'adresse est
   > fausse (autre nom d'hôte, port oublié, `http` au lieu de `https`), **toute
   > la console passe en lecture seule**, pas seulement la connexion. Seuls le
   > schéma, l'hôte et le port comptent : une barre oblique finale ou un chemin
   > dans l'adresse ne gênent pas.

   Une variable `VEILLE_*` inconnue arrête la console et la commande `veille`
   au démarrage : une ligne `VEILLE_AUTH` restée d'une ancienne version
   s'efface.
2. 👤 `docker exec veille-emploi-app-1 veille lien` affiche un lien valable
   24 heures. Ouvre-le sur ton téléphone, puis touche **Enregistrer une
   passkey sur cet appareil**. Pour faire passer le lien du terminal au
   téléphone, voir plus bas.
3. 👤 La console s'ouvre.

La bascule du serveur réel, du mot de passe unique aux passkeys, a été faite
le 27/10/2026 : le § 4 du `docs/DEMARRAGE.md` du dépôt de données n'en garde
qu'un paragraphe daté, et le geste entier, avec son retour arrière, se relit
dans ce dépôt-là par `git show aaf5d76:docs/DEMARRAGE.md`.

### Faire passer un lien du terminal au téléphone

`veille lien` affiche le lien dans le terminal du serveur ; il doit s'ouvrir
sur le téléphone. Pas de QR code pour l'instant, deux façons :

- **SSH depuis le téléphone** (Termux, JuiceSSH…) : lance
  `docker exec veille-emploi-app-1 veille lien` sur le serveur depuis le
  téléphone lui-même, et touche le lien affiché.
- **Une note à toi-même** : copie le lien depuis le terminal du PC dans une
  note ou un message que toi seul lis, ouvre-le sur le téléphone, puis efface
  la note. Le lien ne sert qu'une fois et meurt en 24 heures, mais jusque-là il
  enregistre une passkey pour qui le tient : jamais dans un canal partagé.

### Ajouter un appareil, ou en reprendre la main

- **Ajouter un appareil** : depuis la console, **Plus › Réglages** → bloc
  **Appareils** → **Ajouter un appareil**. Tu obtiens un lien à usage unique
  (24 heures) à ouvrir sur l'autre appareil.
- **Session perdue** (cookie effacé, application réinstallée, déconnexion) :
  ouvre `/connexion` et touche **Se connecter avec une passkey**. La passkey
  de l'appareil rouvre une session.
- **Passkey perdue** (téléphone changé ou réinitialisé, passkey effacée) : sur
  le serveur, `docker exec veille-emploi-app-1 veille lien`, et on recommence à
  l'étape 2. Ou, depuis un autre appareil encore connecté, **Ajouter un
  appareil**.
- **Perdre un appareil** : **Déconnecter** sur sa ligne ferme sa session,
  mais **ne retire pas sa passkey** : qui tient l'appareil en rouvre une. Pour
  la révoquer, sur le serveur :

  ```bash
  docker exec veille-emploi-app-1 veille passkeys                 # les passkeys, avec leur n°
  docker exec veille-emploi-app-1 veille passkeys --retirer <n°>  # retire celle de l'appareil perdu
  ```

  `--retirer` ferme aussi **toutes** les sessions, la tienne comprise :
  reconnecte-toi avec ta passkey. Une passkey que tu ne reconnais pas, dans le
  bloc **Passkeys** des Réglages, se retire de la même façon.

Une passkey est liée au nom d'hôte de l'origine (étape 1) : si l'adresse de la
console change un jour, il faudra en enregistrer une nouvelle.

### Ce que Plus › Réglages permet aussi

- **Le seuil de notification** — au-dessus de quel score ton téléphone sonne.
- **La fréquence de collecte** — de une fois par jour à toutes les deux heures,
  gardée en base. Plus un bouton **Collecter maintenant**, qui ne collecte
  qu'en prod : ailleurs, il dit que la collecte est coupée.
- **Les appareils** — ceux qui sont connectés, un bouton **Déconnecter** par
  ligne, et **Ajouter un appareil** (voir plus haut).
- **Les passkeys** — en lecture seule : l'appareil, la création, le dernier
  usage et le n° à donner à `veille passkeys --retirer`.
- **L'état des sources** — ce qui est prêt, ce qui attend encore une action de
  ta part, et le résultat du dernier passage de chacune.

---

## 5. Installer la PWA sur ton Android

Le service worker des notifications exige une origine sécurisée : la console
en conteneur est servie en HTTPS à son adresse publique. Une fois la passkey
enregistrée (étape 4) :

1. Ouvre l'adresse de la console dans Chrome
2. Connecte-toi
3. Menu ⋮ → **Ajouter à l'écran d'accueil**
4. Dans la console, *Plus › Réglages*, « Activer les notifications » → autorise

Une notification de test part immédiatement. Sur Android le push est fiable,
y compris sans que la PWA soit installée — mais installée, elle démarre plus
vite et s'ouvre en plein écran.

Vérifie les deux canaux quand tu veux, sur le serveur :

```bash
docker exec veille-emploi-app-1 veille tester-notification            # diagnostic
docker exec veille-emploi-app-1 veille tester-notification --envoyer  # expédie vraiment le mail d'essai
```

### Le repli mail

Il ne part **que** si aucun push n'a pu être remis : téléphone hors ligne,
permissions de notification révoquées sans y penser, ou téléphone laissé de
côté. Si le push passe, pas de doublon.

> ⚠️ **Ne repointe pas le SMTP vers un relais local** (`127.0.0.1:25`) sans
> avoir vérifié qu'il achemine vers l'extérieur. Un relais configuré pour la
> seule machine accepte tous les messages et n'en fait sortir aucun : le repli
> échouerait en silence, exactement quand il doit servir.
>
> Le repli sort donc par `smtp.gmail.com:587`, avec le **même mot de passe
> d'application** que l'IMAP — rien de plus à renseigner qu'à l'étape 1.b, et
> une seule chose à révoquer le jour venu.

Si les deux canaux tombent, ça apparaît en clair dans `veille etat`, ligne
`notification`, avec la mention `ECHEC TOTAL`.

---

## 6. Copier ton kit de candidature

En prod, le kit vit dans `/donnees/kit`, dans le dossier des données de la
prod. Sa copie est un geste depuis PowerShell sur ton PC, une commande `scp`,
puis `veille kit`, qui dit ce qui est reconnu : « Copier le kit en prod », dans
[`exploitation.md`](exploitation.md) (« Ce qui est propre à la console »). Sur
le poste, en mode local, le kit est le dossier que désigne `VEILLE_KIT`, sinon
les gabarits de la configuration.

Tes documents apparaîtront dans **Plus › Documents** de la console,
consultables et téléchargeables depuis ton téléphone. Le dossier est relu à
chaque ouverture : tu pourras y ajouter des pièces plus tard sans rien
reconfigurer.

### ⚠️ Renomme les pièces avant

Si ton kit contient un **CV français** et un **dossier suisse en anglais**, sans
étiquette dans le nom de fichier, les deux partiraient ensemble dans chaque
candidature — un dossier suisse anglophone joint à une candidature française
fait mauvais effet.

La convention : des étiquettes séparées par des points, avant l'extension.

| Renomme en | Part avec |
|------------|-----------|
| `cv.fr.pdf` | les offres en français |
| `cv.ch.en.pdf` | les offres suisses en anglais |
| `dossier-complet.ch.en.pdf` | les offres suisses en anglais |
| `annexe-technique.pdf` | **toutes** les offres (aucune étiquette) |
| `lettre.md`, `lettre_en.md` | choisies selon la langue de l'annonce |

`veille kit` te montre exactement ce qui partirait pour une offre française et
pour une offre suisse anglophone. Vérifie avec ça avant la première
candidature.

En attendant, la console fonctionne avec les gabarits provisoires de la
configuration (`gabarits/`) et **le signale à chaque génération**.

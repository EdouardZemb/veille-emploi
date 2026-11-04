# ADR-0002 — La console en conteneur sur l'adresse publique : staging, puis production

- **Statut** : accepté le 2026-10-27
- **Amendée le 2026-11-04** (lot V2, la scission, M-0006 § 7) : l'instance ne vit plus dans ce
  dépôt. Sa configuration, ses secrets chiffrés, ses fichiers d'environnement et les scripts de la
  console du tailnet sont au dépôt de données, `veille-emploi-donnees` : `config/`, `secrets/`,
  `env/` et `scripts/tailnet/`. Le texte qui suit garde les chemins du 2026-10-27, sauf la dernière
  ligne de « Révision ».
- **Contexte amont** : issues #11 (le conteneur et le staging) et #12 (la production et la
  bascule) ; cible `serveur` de `modele-projet` v0.3.0 (M-0001, M-0003, M-0004, M-0005) ; `ancrage`,
  premier projet passé sur cette cible ; ADR-0001 (les passkeys)

## Contexte

La console tourne aujourd'hui sur le serveur, dans son clone du tailnet, par deux
unités systemd utilisateur : `veille-web.service` (uvicorn sur `127.0.0.1:8460`) et
`veille-collecte.timer` (7 h 15, 12 h 15, 18 h 15). Elle n'est vue que du tailnet, par
`tailscale serve`. Ses données sont dispersées : la base et les dossiers dans `donnees/`, le kit
dans `donnees/kit`, les clés des notifications dans `config/vapid.json`, le seuil des
notifications dans `config/criteres.yaml`, que la console réécrit, et la fréquence de collecte
dans le minuteur systemd, qu'elle réécrit aussi.

La cible `serveur` du modèle sert une application en conteneur, derrière le tunnel commun du
serveur. Le staging suit `principal`, la production suit l'étiquette `vX.Y.Z` d'Edouard, et la
sonde du serveur tire l'image toutes les cinq minutes : aucune session n'écrit sur le serveur.
Elle exige une image conforme à M-0003 : tout l'état dans `/donnees`, une racine en lecture seule,
l'uid 1000, 384 Mo, une route de santé au contrat du modèle, et les commandes `SAUVEGARDER` et
`VERIFIER`. `ancrage` y tourne en production depuis le 27/10.

Le staging, à l'adresse publique du staging, sera sur Internet dès le #11 : ce que l'issue #11
liste « avant l'exposition » doit donc précéder son ouverture.

## Options

La seule question ouverte par le modèle est celle de la **collecte** : elle tourne trois fois par
jour, et un conteneur n'a pas de minuteur systemd.

- **A. Un planificateur dans le processus de la console**, comme la purge d'`ancrage`
  (`setInterval`, toutes les 6 heures). Rien à ajouter au déploiement. La fréquence choisie dans
  Réglages s'applique sans redémarrer quoi que ce soit.
- **B. Un second conteneur, tiré de la même image**, qui ne fait que collecter. La collecte ne
  pèse pas sur la console. Mais le modèle ne déploie qu'un service, `app` : santé, sauvegarde et
  test de restauration ne connaissent que lui.
- **C. Un minuteur sur l'hôte**, qui lancerait `docker exec`. Il sort du modèle : l'état voulu du
  serveur vient du dépôt `serveur`, et rien n'y décrit les tâches d'un projet.

## Décision

**Option A pour la collecte**, et le passage en cible `serveur` du modèle v0.3.0, en deux lots :
le **#11** construit l'image, ouvre le staging sur un jeu de données factice et ferme ce qui doit
l'être avant Internet ; le **#12** migre les vraies données en production et retire l'accès par le
tailnet. Le plan du #12 s'écrit une fois le staging vérifié sur le téléphone.

Réponses de copier : `cible=serveur`, le bloc de ports de `.copier-answers.yml` (un port pour la
prod, un pour le staging, un pour le test de restauration, dans un bloc qu'aucun autre projet du
parc n'occupe), `port_app=8460`, `chemin_sante=/sante`, `sauvegardes=true`. Les sous-domaines sont
ceux que le modèle tire du nom du projet, l'un pour la prod, l'autre pour le staging, sous le
domaine de l'adresse publique.

### 1. Deux modes de marche, jusqu'à la fin du #12

La console du tailnet continue de tourner, et de suivre `principal`, jusqu'au retrait de l'ancien
service. Le code marche donc dans deux modes, que **`VEILLE_EMPLOI_ENV`** distingue :

- **posée** (`prod`, `staging`, `ci`) : le mode conteneur. Ses chemins viennent de l'image ; la
  fréquence de collecte vit en base ; la collecte ne tourne qu'en `prod` ;
- **absente** : le mode d'aujourd'hui, avec systemd. C'est aussi celui du test de restauration du
  modèle, qui lance l'image sans variable et attend une santé `ok`.

Le mode systemd est retiré après le #12 (une piste).

### 2. L'image

- `python:3.13-slim`, épinglée par empreinte. Les bibliothèques de WeasyPrint (Pango, HarfBuzz,
  dont `libharfbuzz-subset0`), `fonts-dejavu-core` (les PDF sont en DejaVu Serif), et `tzdata` avec
  `TZ=Europe/Paris` (les heures de collecte sont des heures de Paris).
- L'utilisateur 1000 ; `/donnees` créé à son nom. Les chemins pointent dedans : `VEILLE_DB`,
  `VEILLE_DOSSIERS`, `VEILLE_KIT` et `VEILLE_VAPID`. `/tmp` sert de `HOME` et de cache (WeasyPrint,
  fontconfig) : la racine est en lecture seule.
- `veille servir --hote 0.0.0.0 --port 8460` : le même uvicorn, en un seul processus (le verrou
  du planificateur ne couvre que le sien), et la journalisation INFO de `veille.*`, sans laquelle
  `docker logs` ne montrerait que les échecs. Sans `ENTRYPOINT` : `docker run <image> veille
  instantane verifier /donnees` lance la commande telle quelle, comme le modèle l'exige.
- `ARG REVISION` devient le label `org.opencontainers.image.revision` et la variable `REVISION`,
  que la santé rend. Un `HEALTHCHECK` sur `/sante`.
- La CLI Claude n'est pas dans l'image : le bouton d'affinement ne s'affiche pas (`affinement.py`,
  « sans identifiants, le bouton ne s'affiche pas »). Un test le fixe.

### 3. La configuration

- **`VARIABLES_CONNUES`** reçoit `VEILLE_EMPLOI_ENV`, `VEILLE_EMPLOI_VERSION` et
  `VEILLE_EMPLOI_URL_PUBLIQUE`, que passe le `compose.yml` du modèle. Un test rend ce `compose.yml`
  et vérifie que chaque variable qu'il passe est connue de `config.py` (invariant 6).
- **L'origine** des passkeys et du contrôle d'`Origin` est lue dans `VEILLE_EMPLOI_URL_PUBLIQUE` si
  elle est posée, sinon dans `VEILLE_URL`. Elle est normalisée : schéma `http` ou `https` seulement,
  hôte en minuscules, port par défaut retiré, chemin ignoré. Une adresse illisible rend le contrôle
  `indisponible`, jamais `ok` (invariant 3).
- **Le seuil et la fréquence** vivent en base, dans une table `reglages`. Au premier démarrage, le
  seuil absent de la base est repris de `config/criteres.yaml` : la console du tailnet garde la
  valeur réglée au téléphone. La console n'écrit plus jamais `criteres.yaml`, qui devient du code,
  modifié par PR.
- **La fréquence en mode systemd** : là où `systemctl` manque, elle est rendue `indisponible`, et
  l'onglet Réglages s'affiche (aujourd'hui, une erreur 500).

### 4. La santé

`GET /sante` rend `{statut, environnement, version, revision}` : `statut` vaut `ok` si la base
s'ouvre, sinon la réponse est un 503 `{"statut": "ko"}`. `environnement` vient de
`VEILLE_EMPLOI_ENV`, ou vaut `local` ; `version` vient de `VEILLE_EMPLOI_VERSION`, ou vaut `dev`,
et n'est jamais figée dans l'image ; `revision` vient de `REVISION`.

### 5. Le planificateur

Un fil lancé au démarrage de la console, dans tous les modes. Il purge les sessions et les liens
expirés, au démarrage puis toutes les 6 heures.

En `prod` seulement, il lance aussi la collecte de `veille collecter --jours 7`, notifications
comprises, aux heures de la fréquence lue en base. Une seule collecte à la fois ; une erreur est
journalisée et n'arrête ni le fil ni la console. Réglages écrit la fréquence en base, et le fil la
relit avant chaque attente.

### 6. Avant Internet

Ce que l'issue #11 liste, et les pistes d'authentification du #10, arrivent avant l'ouverture du
staging :

- **la limite de débit par client** : la clé est `CF-Connecting-IP`, sinon l'adresse du client ;
  20 requêtes par minute et par client sur les quatre routes anonymes, et un plafond global de
  secours, à 200 par minute ;
- **le cookie `__Host-veille_session`** sous HTTPS (il exige `Secure`, `Path=/` et aucun
  `Domain`) ; `veille_session` sans HTTPS, comme sous le client de test. Le changement de nom
  ferme les sessions ouvertes : on se reconnecte une fois, par la passkey ;
- **une politique de sécurité du contenu** sur chaque réponse, celle d'`ancrage` : `default-src
  'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src
  'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'`, et
  `Referrer-Policy: same-origin`. `'unsafe-inline'` vient des styles qu'`app.js` pose dans ses
  gabarits. `same-origin` plutôt que `no-referrer` : sous `no-referrer`, le navigateur envoie
  `Origin: null` avec le formulaire de déconnexion, que le contrôle de l'origine refuse ;
  l'adresse ne part pas davantage vers un autre site. Le parcours dans Chromium vérifie
  qu'aucune violation n'est levée ;
- **une nouvelle touche de passkey avant d'ajouter un appareil** : `POST /api/auth/lien/creer`
  exige une assertion WebAuthn de moins de cinq minutes. Un cookie volé ne suffit plus à
  enregistrer une passkey de plus ;
- **les pistes du #10** : `retirer_passkey` en une seule transaction ; `consommer_lien` revérifie
  l'expiration ; le compteur de signature s'écrit de façon atomique (`UPDATE … WHERE compteur =
  <lu>`) ; les tests des trois états de `/connexion` et du 503 de `lien/creer`.

### 7. Les sauvegardes

Les deux commandes vivent sous `veille instantane`, car `veille verifier` existe déjà (il vérifie
une offre).

- **`veille instantane creer <dossier>`** crée le dossier, à la forme de `/donnees` : la base, copiée
  par l'API de sauvegarde de SQLite (cohérente, console en marche), les dossiers, le kit, les clés
  des notifications, et un marqueur `instantane.json` (version, date). Il ne rend 0 que si tout y
  est.
- **`veille instantane verifier <dossier>`** rend 0 si l'instantané est sain, 2 s'il ne l'est pas (marqueur
  absent, `PRAGMA integrity_check` en échec), 64 sur une erreur d'usage. Il ouvre la base en
  lecture seule et ne modifie rien.
- `deploiement/projet.env` : `SAUVEGARDER=veille instantane creer`, `VERIFIER=veille instantane
  verifier`. Pas de
  `REPORTER` : rien ne doit survivre à une restauration.
- Heures, dans `serveur/projets/veille-emploi.env` : `SAUVEGARDE=03:30`, `TEST_RESTAURATION=Sun
  05:30` (posées au #12 ; d'ici là `non`). `ancrage` a 02:45 et le dimanche 04:15 ; le modèle exige 30 et 60 minutes d'écart.

### 8. Le staging

- **Un jeu de données factice écrit à la main** (M-0001), versionné dans `factice/` : une personne
  fictive, une vingtaine d'offres, une ou deux candidatures, et un kit (un CV, les gabarits).
  `veille factice` le charge dans une base vide. La console le lance au démarrage du staging si la
  base est vide.
- **Pas de collecte** (le planificateur ne tourne qu'en `prod`), **pas de mail** : aucun secret de
  Gmail ni de France Travail en staging. **Les notifications push restent actives**, avec des clés
  propres au staging, nées dans son `/donnees`, pour qu'on les vérifie.
- Le premier appareil s'enregistre par `veille lien`, que 👤 Edouard lance dans le conteneur du
  staging.

### 9. Les secrets et la déclaration dans `serveur`

- **Staging** : `HC_SONDE` seulement. **Prod** : `HC_SONDE`, `HC_SAUVEGARDE`,
  `HC_TEST_RESTAURATION`, et les secrets de l'application que la console lit : l'IMAP et le SMTP de
  Gmail, le destinataire des mails, les identifiants de France Travail. La liste finale est celle
  des noms présents aujourd'hui dans `config/.env`, que 👤 Edouard relève (les noms, jamais les
  valeurs). `compose.projet.yml` les passe au conteneur.
- `secrets.ps1` refuse les blancs : le mot de passe d'application de Gmail se saisit sans ses
  espaces, que Google ignore.
- **Ordre** :
  1. 👤 les `.enc` par `secrets.ps1`, puis la PR qui les ajoute, fusionnée ;
  2. la PR de `serveur` (`projets/veille-emploi.env`, les réseaux du tunnel, `REGISTRE.md`), que
     fusionne Edouard, puisque `serveur` est en mode `edouard` ;
  3. 👤 la clé de déploiement (le dépôt est privé), les routes Cloudflare et les contrôles
     Healthchecks.

### 10. La production et la bascule (#12, à planifier après le staging)

1. 👤 L'étiquette `vX.Y.Z` déploie une production vide.
2. 👤 L'ancien service arrête de collecter (`veille-collecte.timer` arrêté), pour que deux
   collectes ne lisent pas la même boîte Gmail. Sa console reste consultable.
3. 👤 `veille instantane creer` lancé dans l'ancien clone produit un instantané de ses vraies données,
   à la forme de `/donnees`. `restaurer.sh prod <instantané>` du modèle le pose en production.
4. 👤 Les passkeys, sessions et abonnements push de l'adresse du tailnet sont effacés de la base
   migrée : une passkey est liée au nom d'hôte, et un abonnement à l'origine.
5. 👤 `veille lien` dans le conteneur de prod. L'application est réinstallée depuis la nouvelle
   adresse, une passkey est créée, les notifications sont réactivées.
6. 👤 La première sauvegarde et le test de restauration.
7. 👤 Le retrait de l'ancien service : `tailscale serve --https=<le port du tailnet> off`, les
   unités arrêtées et désactivées.

**Retour arrière**, jusqu'à l'étape 7 : relancer le minuteur de l'ancien service, qui reprend avec
ses données, intactes. La prod est abandonnée.

## Conséquences

- Pendant le #11 et le #12, une même branche sert deux modes. Les tests couvrent les deux, et le
  mode systemd disparaît ensuite.
- Le renommage du cookie déconnecte une fois chaque appareil, y compris sur le tailnet.
- Modifier `config/criteres.yaml` passe par une PR, et arrive par le déploiement. Le seuil et la
  fréquence restent réglables au téléphone.
- Le staging est public : seules les passkeys le gardent. Ses données sont factices, et il n'a
  aucun secret réel.
- La collecte partage le processus et les 384 Mo de la console. Le staging, qui ne collecte pas,
  ne le mesure pas : c'est la première semaine de prod qui le dira.
- La CI gagne deux jobs, `deploiement` et `image`, et le bloc `concurrency` du modèle ; Dependabot
  suit les images Docker.

## Révision

- Si la collecte dépasse la mémoire ou ralentit la console : l'option B, un second conteneur.
- Si `CF-Connecting-IP` manque derrière le tunnel : la limite redevient globale, et on le dit.
- Après le #12 : retirer le mode systemd, et, au dépôt de données, `scripts/tailnet/installer.sh`
  et `scripts/tailnet/exposer-tailnet.sh`.

# M-0003 — Contrat de l'image : ce que le projet fournit pour que la mécanique le déploie sans le connaître

- **Statut** : accepté le 2026-10-18
- **Amendé** le 2026-10-29, avec le lot 12 : l'application peut lire son instance, sa
  configuration dans `/config` et son contenu dans `/contenu` ; deux commandes la vérifient, et la
  santé dit quelle configuration sert (§ 2 et § 6, M-0006 § 5)
- **Contexte amont** : la chaîne de livraison d'`ancrage`, d'où vient la mécanique de la cible
  `serveur` ; M-0004 (la chaîne de livraison) ; M-0005 (les sauvegardes) ;
  M-0006 (le code et les données)

## Contexte

La mécanique de la cible `serveur` (`deploiement/`, ses unités, la CI) est gérée par le modèle :
elle est la même pour tous les projets, et se corrige une fois pour tous. Elle ne sait rien de
l'application, ni de sa pile, ni de sa base. Il lui faut un contrat, ce que l'image doit faire et
rien de plus, pour la construire, la vérifier, la déployer, la sauvegarder et la restaurer.

## Décision

### 1. L'image

Un `Dockerfile` à la racine du dépôt. L'image :

- écoute sur `0.0.0.0`, au port `8460` (la réponse `port_app`) : `deploiement/compose.yml` le
  publie sur la boucle locale du serveur, et le tunnel commun l'atteint par le réseau du projet. La
  mécanique ne pose pas `PORT` : une app qui le lit lui donne ce port par défaut ;
- tourne en `1000:1000`, sur un système de fichiers en lecture seule, avec `/tmp` en mémoire, sans
  capacité (`cap_drop: ALL`, `no-new-privileges`), dans 384 Mo. `compose.yml` le lui impose ;
  `deploiement/compose.projet.yml` peut changer la mémoire ;
- porte le label `org.opencontainers.image.revision`, rempli par l'argument de construction
  `REVISION` (`docker build --build-arg REVISION=<sha>`) ;
- **crée `/donnees`, à l'uid 1000.** En CI, `modele-image-construire` lance l'image avec
  `--read-only --tmpfs /tmp --user 1000:1000 -v /donnees` : ce volume anonyme hérite du contenu et
  du propriétaire du `/donnees` de l'image, et sans lui l'app n'y écrit pas. En production,
  `/donnees` est un montage du dossier de l'hôte, `~/.local/share/veille-emploi/<env>/donnees` ; vide
  au premier déploiement, il cache le `/donnees` de l'image : l'app crée au démarrage ce qu'il lui
  faut ;
- lit dans son environnement `VEILLE_EMPLOI_ENV`, `VEILLE_EMPLOI_VERSION` et `VEILLE_EMPLOI_URL_PUBLIQUE`, que `compose.yml`
  lui passe. En CI, la mécanique ne pose que `VEILLE_EMPLOI_ENV=ci` et `VEILLE_EMPLOI_URL_PUBLIQUE` ; le projet
  peut y ajouter les siennes, par l'entrée `variables` de `modele-image-construire` ;
- **démarre aussi sans son environnement** : le test de restauration la lance nue
  (`tester-restauration.sh`, `docker run` sans `-e`), sans `VEILLE_EMPLOI_ENV`, `VEILLE_EMPLOI_VERSION` ni
  `VEILLE_EMPLOI_URL_PUBLIQUE`, et sans les secrets ni les variables de `compose.projet.yml`. Sa route de
  santé doit alors répondre `statut` `ok` ;
- démarre par sa commande par défaut. Un `HEALTHCHECK` est conseillé : `docker compose up --wait`
  attend alors que l'app soit saine.

### 2. La route de santé

À `/sante` (la réponse `chemin_sante`), elle rend au moins `{statut, environnement, version,
revision}`, ou un 503 avec `{statut: "ko"}`.

- `statut` vaut `ok` quand l'app peut servir.
- `environnement` est `VEILLE_EMPLOI_ENV` : `dev`, `ci`, `staging` ou `prod`.
- `version` est `VEILLE_EMPLOI_VERSION`, **jamais une valeur figée dans l'image** : la même image sert `main`
  en staging, puis `X.Y.Z` en prod, et une étiquette de retour la redéploie sous un autre numéro
  (M-0004). Absente, en CI, elle a une valeur par défaut.
- `revision` est le SHA du commit construit, celui du label.
- `configuration`, pour un projet qui lit son instance (amendement du 2026-10-29) : `exemple` ou
  `montee` (§ 6).

Trois contrôles la lisent : la CI (`deploiement/ci/verifier-image.sh` : statut `ok`, la révision du
commit, l'environnement `ci`) ; le déploiement, sur le port local (statut `ok`, la version et la
révision attendues) ; la sonde, sur l'adresse publique (HTTP 200 sans redirection, statut `ok`,
l'environnement servi). Quand le projet déclare `VERIFIER_CONFIG`, le déploiement et la sonde
lisent aussi `configuration` (§ 6).

### 3. Les données

Toutes dans `/donnees`. Rien d'autre ne survit à un redémarrage : le système de fichiers est en
lecture seule et `/tmp` est en mémoire.

### 4. Le contrat de l'instantané

Deux commandes de l'image, déclarées dans `deploiement/projet.env` (`SAUVEGARDER=…`,
`VERIFIER=…`), et une troisième, facultative (`REPORTER=…`). Ce fichier est au projet ; il est lu
par un analyseur strict et **jamais sourcé** : une ligne `CLE=mots`, des mots séparés par des
espaces, sans caractère que le shell interpréterait.

- **`SAUVEGARDER <dossier>`** crée ce dossier, qui n'existe pas encore, avec **la forme de
  `/donnees`** : ce que `/donnees` doit contenir pour que l'app reparte. Son parent existe : la
  mécanique le crée avant de lancer la commande. L'instantané est cohérent, pris l'app en marche, dans le conteneur en service
  (`docker compose exec`) ; en CI, dans le conteneur lancé, vers `/tmp/instantane`. Il ne contient
  que des fichiers et des dossiers ; un lien physique y est accepté, il entre dans l'archive comme
  un fichier ordinaire. La commande rend 0 seulement si l'instantané est complet.
- **Le nom est à la mécanique.** Elle passe un nom provisoire, `….partiel`, et le renomme par
  `mv -T` une fois l'instantané contrôlé. Un `.partiel` n'est jamais pris pour le dernier
  instantané ; une destination déjà présente est un échec, rien n'est écrasé.
- **`VERIFIER <dossier>`** répond 0 si l'instantané est conforme, 2 s'il ne l'est pas, 64 en cas
  d'erreur d'usage. Seul le code fait foi ; la sortie va au journal. Sur le serveur, elle tourne
  dans un conteneur jetable (`docker run <image> <mots> /donnees`) qui ne voit que l'instantané,
  monté sur `/donnees` : une image dont l'`ENTRYPOINT` ne lance pas ses arguments la fait échouer,
  et la CI ne le voit pas (« Conséquences »).
- **`VERIFIER` ne modifie jamais son argument.** Le dossier est monté en écriture dans le conteneur
  de vérification, et c'est son contenu que le test de restauration et la restauration mettent
  ensuite en service.
- **Restaurer, c'est remettre le contenu de l'instantané dans `/donnees`.** C'est ce qui rend
  `restaurer.sh` et `tester-restauration.sh` génériques : la mécanique ne sait rien de la base.
- **`REPORTER /actuel /donnees`, facultative**, pour un projet qui garde dans ses données un état
  qu'une restauration ne doit pas défaire (un registre de suppressions, par exemple). Déclarée,
  elle tourne à chaque restauration, application arrêtée, avant la mise en place, dans un
  conteneur jetable de l'image déployée :
  - `/actuel` est une copie jetable des données en service, montée en écriture : une base qui tient
    un journal à côté d'elle ne s'ouvre pas en lecture seule. La commande la lit ; ce qu'elle y
    écrit est jeté ;
  - `/donnees` est la copie de l'instantané qui sera mise en place : la commande y écrit ce qui doit
    survivre ;
  - elle rend 0 quand le report est fait, sa sortie standard étant alors un seul objet JSON, le
    rapport, que la mécanique journalise ; 64 en cas d'erreur d'usage, ce que rend une image qui ne
    connaît pas la commande ; tout autre code est un échec, et une sortie qui n'est pas un seul
    objet JSON aussi ;
  - sur un code 0, seule sa sortie standard, le rapport, va au journal ; sur un échec, ses deux
    sorties y vont, aplaties. Elles ne portent aucune donnée personnelle : des nombres plutôt que
    des noms.

  `REPORTER_SECTION`, facultative aussi, est le titre de la section de `docs/exploitation.md` qui
  dit comment reporter à la main, quand le report n'a pas pu avoir lieu (M-0005).
- **Un instantané vide est refusé.** Un `/donnees` vide, même légitimement, fait donc alerter la
  sauvegarde chaque nuit. Une app qui peut n'avoir aucune donnée y garde au moins un fichier (une
  marque, la version de son schéma).
- **La commande de la version qui arrive tourne dans l'image de celle qui part.** Avant un
  déploiement, l'instantané lance la commande `SAUVEGARDER` du `projet.env` de la version qui
  arrive (la sonde a déjà placé le clone sur elle) dans le conteneur de la version en service. Une
  version qui change `SAUVEGARDER` reste donc compatible avec l'image en service, ou se livre en
  deux temps : d'abord une image qui connaît la nouvelle commande, `projet.env` inchangé, puis,
  une version plus tard, le `projet.env` qui l'utilise. Dans l'autre sens, une image garde la
  commande de la précédente : un retour par étiquette prend son instantané avec la commande de la
  version visée, dans l'image qu'il quitte (invariant 4). `VERIFIER` suit la même règle : elle
  tourne dans l'image déployée, avec le `projet.env` du clone. `REPORTER` aussi : une image qui ne
  la connaît pas, après un retour à une version plus ancienne par exemple, rend 64, et la
  restauration s'arrête sans rien changer.

La mécanique fait le reste : l'archive, le chiffrement, l'envoi, la rétention, le test de
restauration et la restauration (M-0005).

### 5. Ce qui reste au projet

- `deploiement/compose.projet.yml` : ce qu'il ajoute au service `app` (volumes, variables, mémoire).
- Les secrets de son app, nommés dans `deploiement/secrets/<env>.cles` (M-0004).
- Ses vérifications dans le job `verifier` de `ci.yml`, et ses tests de bout en bout contre l'image,
  entre `modele-image-construire` et `modele-image-publier`.
- S'il lit une instance : ses deux commandes de vérification, `exemple/` et `exemple-contenu/`, et
  le champ `configuration` de sa santé (§ 6).

### 6. L'instance : `/config` et `/contenu`

Amendement du 2026-10-29 (M-0006, § 5). Une application peut lire une instance : sa configuration
dans `/config`, son contenu dans `/contenu`. Ce sont deux montages en lecture seule d'un instantané
du commit de données, jamais le clone des données (M-0004, § 8). Les dossiers vivent, selon le
mode, dans `config/` et `contenu/` du dépôt de données, à deux dépôts, ou dans `instance/config/`
et `instance/contenu/` du dépôt lui-même, à un dépôt.

- **Les deux commandes**, facultatives, se déclarent dans `deploiement/projet.env`, en mots séparés
  par des espaces, comme `VERIFIER` :
  - `VERIFIER_CONFIG=<mots>` : lancée en `<mots> /config` ;
  - `VERIFIER_CONTENU=<mots>` : lancée en `<mots> /contenu`, ou en `<mots> /contenu /en-service`
    quand un contenu est en service. `/en-service` est le contenu du couple en service : il permet
    de refuser un changement qui défait un identifiant définitif.

  Codes : 0 conforme, 2 non conforme, 64 usage ; tout autre code refuse. Seul le code fait foi ; la
  sortie va au journal. Elles ne modifient jamais leur argument. Elles tournent dans un conteneur
  jetable de l'image visée (`docker run --rm`), sans réseau (`--network none`), avec les options
  des conteneurs jetables (l'uid 1000, un système de fichiers en lecture seule, aucune capacité,
  384 Mo), et ne voient que leurs dossiers, en lecture seule. Comme pour `VERIFIER`, une image dont
  l'`ENTRYPOINT` ne lance pas ses arguments les fait échouer.
- **La configuration et le contenu portent leur version de schéma** (M-0006, § 5) : une image qui
  ne connaît pas celle du couple les dit non conformes (code 2).
- **Ils vont par paires** : la configuration avec `VERIFIER_CONFIG`, le contenu avec
  `VERIFIER_CONTENU`. Dès que le projet déclare une commande, un dossier présent sans sa commande,
  ou une commande sans son dossier, refuse le déploiement. Un projet qui n'en déclare aucune a un
  couple sans commit de données : le déploiement ne lit pas ses dossiers. À deux dépôts, la CI du
  dépôt de données vérifie la règle dans tous les cas, et refuse aussi. À un dépôt, la CI du code
  vérifie `instance/` comme le fera le déploiement, dès qu'une commande est déclarée : la règle,
  puis chaque commande sur son dossier, dans un conteneur jetable de l'image construite
  (`deploiement/ci/verifier-image.sh`), et le déploiement revérifie. Un dossier est présent quand
  il porte, dans le commit de données, au moins un fichier autre que le `README.md` de sa racine ;
  un `README.md` plus bas compte comme un fichier.
- **La santé dit quelle configuration sert** : le champ `configuration` vaut `exemple` ou `montee`.
  Quand le projet déclare `VERIFIER_CONFIG`, le déploiement exige `exemple` en staging et `montee`
  en prod, et la sonde le contrôle à chaque passage, sur l'adresse publique. Sinon, le champ n'est
  pas lu.
- **Le staging ne monte jamais `/config`** et n'y lance jamais `VERIFIER_CONFIG`, quoi que porte le
  commit de données : il sert l'exemple. Il monte `/contenu`, et y lance `VERIFIER_CONTENU`.
- **La prod ne se replie pas sur l'exemple** : c'est l'application qui refuse de démarrer sans
  `/config` (M-0006, § 5). La chaîne, elle, garantit que la prod d'un projet qui déclare
  `VERIFIER_CONFIG` reçoit le montage, et que sa santé dit `montee`. Deux exceptions, où la prod
  sert sans `/config`, toutes deux vers une version d'avant ses données, qui ne monte rien et dont
  le champ n'est pas lu :
  - un retour arrière par `--retour` vers un couple précédent sans commit de données ;
  - le retour automatique qui suit l'échec de la première version qui déclare `VERIFIER_CONFIG` :
    la version d'avant revient, telle qu'elle était (M-0004, § 8).
- **L'exemple.** Le dépôt de code porte sa configuration d'exemple dans `exemple/` et son contenu
  d'exemple dans `exemple-contenu/`, à sa racine ; l'image les embarque. La CI lance chaque commande
  déclarée sur son exemple, par `docker run` sur l'image construite, comme le serveur la lance
  (`deploiement/ci/verifier-image.sh`) : elle prouve à la fois l'exemple et la clause de
  l'`ENTRYPOINT`. Avant tout conteneur, une commande déclarée sans son dossier d'exemple refuse ;
  un dossier d'exemple sans sa commande n'est pas vérifié, et le journal le dit. La règle du
  `README.md` vaut aussi pour l'exemple. Un projet à un dépôt porte lui aussi son exemple, à côté
  d'`instance/` : la CI l'exige dès qu'une commande est déclarée, et le staging sert `exemple/`.
- **Un projet qui ne déclare ni l'une ni l'autre ne voit aucun changement** : rien n'est monté, rien
  n'est vérifié, le champ `configuration` n'est pas lu, et le commit de données de son couple vaut
  `-` (M-0004, § 8).

## Conséquences

- Toute pile convient, tant que son image tient le contrat.
- À chaque PR, la CI lance l'image comme en production et contrôle sa santé, sa révision et son
  environnement, puis lance `SAUVEGARDER` et `VERIFIER` dans le conteneur, par `docker exec`.
  Une image qui échoue n'est jamais publiée.
- **La CI prouve la clause de l'`ENTRYPOINT` pour `VERIFIER_CONFIG` et `VERIFIER_CONTENU`**
  (amendement du 2026-10-29) : `deploiement/ci/verifier-image.sh` les lance par `docker run` sur
  l'exemple, comme le serveur les lance (§ 6).
- **La CI ne prouve pas la clause de l'`ENTRYPOINT`** : `docker exec` le contourne, alors que le
  serveur lance `VERIFIER` par `docker run`. C'est le test de restauration qui la prouve : la mise
  en service le lance une fois après le premier déploiement en prod (`docs/exploitation.md`), puis
  il tourne chaque semaine, au jour et à l'heure `TEST_RESTAURATION` que déclare `serveur`. Une
  image qui la viole passe la CI, puis fait échouer ce test et toute restauration. Faire passer la
  vérification de la CI par `verifier_copie` est une piste de `modele-projet`.
- Les deux commandes sont du code de l'app, que le projet teste. Leur compatibilité d'une version à
  l'autre s'ajoute à l'invariant 4.
- **Rien ne lance `REPORTER` avant une vraie restauration** : ni la CI, ni le test de restauration
  de la semaine, qui n'a pas de données en service à reporter. Le projet la teste dans ses propres
  tests, contre son image.
- **Difficile à changer** : la forme de l'instantané. Les archives gardées 90 jours la portent.

## Révision

Cet ADR doit être rouvert si :

- une app doit écrire hors de `/donnees`, ou a besoin d'un second service (une base à part) que
  `compose.projet.yml` ne suffit pas à décrire ;
- une app doit écrire dans `/config` ou `/contenu`, ou lire une instance qui change plus vite
  qu'une étiquette ;
- l'instantané complet de chaque nuit devient trop gros ou trop long à prendre ;
- le parc passe à un second serveur.

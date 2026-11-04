# M-0004 — Chaîne de livraison : la CI publie l'image, le serveur va la chercher, une étiquette la met en production

- **Statut** : accepté le 2026-10-18
- **Amendé** le 2026-10-27, avec le lot 9 : après chaque déploiement ou retour arrière réussi, le
  déploiement retire du serveur les images du projet qui ne servent plus (§ 3)
- **Amendé** le 2026-10-29, avec le lot 12 : l'état déployé est un couple, une image et un commit
  de données ; la chaîne lit l'instance dans un second dépôt, ou, pour un projet d'avant M-0006,
  dans le sien, et la prod suit aussi une série d'étiquettes de données (§ 8)
- **Contexte amont** : la chaîne de livraison d'`ancrage` (son ADR-0006), généralisée par le
  modèle ; M-0002 (les étiquettes sont à Edouard) ; M-0003 (le contrat de l'image) ; M-0006 (le
  code et les données)

## Contexte

Plusieurs projets partagent un serveur, qui n'a aucun port entrant et ne doit rien recevoir à la
main : un fichier posé sur l'hôte finit par diverger du dépôt, en silence. Personne n'écrit sur le
serveur après son amorçage (invariant 3). Il faut pourtant qu'une fusion arrive en préproduction
sans geste, qu'une version arrive en production sur un seul geste d'Edouard, et qu'une version qui
échoue s'en aille d'elle-même.

## Décision

### 1. Le chemin d'une version

1. **Une fusion sur la branche principale.** La CI (`ci.yml` : `socle`, `verifier`,
   `deploiement`, puis `image`) construit l'image, la lance comme en production, contrôle sa route
   de santé et sa révision, passe les tests de bout en bout du projet contre elle, puis la publie
   sous `:sha-<sha>` et `:main` (actions `modele-image-construire` et `modele-image-publier`).
   Aucune image n'est publiée pour un commit dont la CI échoue. La sonde de staging la déploie dans
   les 5 minutes.
2. **Une étiquette `vX.Y.Z`, posée par Edouard** (M-0002). `modele-version.yml` vérifie que le
   commit est un ancêtre de la branche principale et que `:sha-<sha>` existe, puis il
   **réétiquette sans reconstruire** : la prod reçoit les octets testés en staging. Il refuse de
   réécrire une version existante dont l'empreinte diffère, et crée la Release. La sonde de prod,
   qui vise la plus haute étiquette `vX.Y.Z`, suit dans les 5 minutes.
3. **Le serveur va chercher.** `sonder.sh <env>`, toutes les 5 minutes : un verrou, un clone
   propre (sinon une alerte), la cible (en staging, la branche principale et l'image `:main` ; en
   prod, la plus haute étiquette), `docker pull`, puis `deployer.sh` si le couple visé, l'image et
   le commit de données, diffère du couple en service (§ 8). Le déploiement vérifie d'abord les
   données du couple, s'il en a (§ 8), prend un instantané de `/donnees` (M-0003, M-0005), lance
   `docker compose up --wait` et contrôle la santé sur le port local : statut, version et révision.
4. **Un déploiement qui échoue** : le couple est marqué `echec` et **jamais retenté**, le
   précédent revient de lui-même, et Healthchecks reçoit `/fail`. Sans version précédente,
   l'application est arrêtée.

### 2. Revenir en arrière : par une étiquette

Un retour voulu passe par git. 👤 Edouard pose une nouvelle étiquette, plus haute que celle en
service, sur le commit de la version visée. `modele-version.yml` la réétiquette sans reconstruire,
et la sonde de prod la déploie comme une autre version ; le clone de prod suit l'étiquette.
L'invariant 4 garantit que l'image précédente fonctionne encore avec les données, `compose.yml` et
les `env/*.env` actuels. C'est pourquoi la version vient de l'environnement, jamais de l'image
(M-0003). À deux dépôts, cette étiquette forme un couple nouveau, l'ancienne image et le commit de
données en service, que les vérifications jugent comme tout couple (§ 8).

`deployer.sh <env> --retour` reste l'outil de secours, lancé à la main sur le serveur quand le
chemin par étiquette ne passe pas. Il revient au couple précédent, son image et son commit de
données (§ 8), marque le couple quitté en échec pour que la sonde ne le redéploie pas, refuse un
second retour, et laisse le clone sur l'étiquette quittée. À deux dépôts, seul ce couple attend :
un geste qui ne change qu'une moitié de la cible, une étiquette de données ou une `vX.Y.Z`, peut
ramener l'autre moitié du couple quitté (M-0006, § 6).

### 3. Les environnements et les images

- Un seul `compose.yml` pour les deux environnements ; seuls `env/<env>.env` et le nom du projet
  Compose changent. Le staging suit `:main`, avec des données factices (M-0001) ; la prod suit la
  plus haute étiquette.
- Les adresses : `<sous_domaine>.<domaine>` et `<sous_domaine>-staging.<domaine>`, un seul niveau
  de sous-domaine, celui que couvre le certificat gratuit de Cloudflare.
- Les images vont sur GHCR, `ghcr.io/edouardzemb/<nom>`. **Un paquet GHCR est privé par
  défaut** : à la mise en service d'un dépôt public, 👤 Edouard le passe en public
  (`docs/exploitation.md`). Le serveur tire avec un seul jeton `read:packages` pour tout le parc,
  rangé dans `~/.config/serveur/docker` par la sonde de `serveur`.
- **Le serveur ne garde que les images utiles.** Après chaque déploiement ou retour arrière réussi,
  `deployer.sh` lance `deploiement/nettoyer-images.sh`, qui retire les images du projet que ni
  l'état des deux environnements, ni un conteneur, ni la marge des 3 plus récentes ne gardent. Son
  échec ne change pas le résultat du déploiement. GHCR garde tout : une image retirée revient par
  un `docker pull`, et un retour arrière par une étiquette n'en dépend pas. La sonde de `serveur`,
  elle, ne supprime toujours rien. Une image qui porte au plus une étiquette se retire par son
  identifiant ; une image qui en porte deux ou plus, par ses étiquettes, un appel chacune, car
  Docker refuse sans `-f` le retrait par identifiant d'une telle image. Le script ne passe jamais
  `-f`. Le même appel fait ensuite le ménage des instantanés des données (§ 8).

### 4. Les secrets : refaits sur le poste

- `<env>.env.enc`, dans le clone des données, chiffrés par `sops` et `age` vers les deux clés
  publiques du parc, `serveur.pub` et `hors-ligne.pub` (`.sops.yaml`), rangées dans le même clone.
  Selon le mode (§ 8, amendement du 2026-10-29) : les secrets dans `secrets/` à deux dépôts,
  `deploiement/secrets/` à un dépôt ; les clés dans `cles/` à deux dépôts, `deploiement/cles/` à un
  dépôt. Les clés attendues sont nommées, sans valeur, dans `deploiement/secrets/<env>.cles`, du
  dépôt de code.
- Sur le serveur, chaque script les déchiffre dans un fichier de mode 600 sous `/dev/shm`, détruit
  par `shred -u` avant qu'une seule ligne soit interprétée, et ne les source jamais. Sans fichier
  chiffré, il rend le code 3.
- **Changer une valeur, c'est refaire le fichier, sur le poste.** 👤 Edouard lance
  `scripts/modele/secrets.ps1 refaire <fichier .env.enc>` dans son propre terminal et colle chaque
  valeur depuis KeePassXC, en saisie masquée ; le script chiffre vers les destinataires de
  `.sops.yaml` et n'affiche aucune valeur. 🤖 La session commite le fichier dans une PR. La valeur
  entre en service à la fusion en staging, à l'étiquette suivante en prod. À deux dépôts, Edouard
  lance le script dans le clone du dépôt de données, le dépôt de code cloné à côté : le script y
  prend le `.cles` du dépôt de code. La PR est celle du dépôt de données, et l'étiquette suivante,
  une étiquette de données ; un projet sans commande attend en plus le déploiement suivant du code
  (§ 8).
- La CI contrôle sans rien déchiffrer (`scripts/modele/verifier_secrets.py`) : chaque `.enc` porte
  exactement les clés de son `.cles`, chiffrées pour les deux clés du parc. À deux dépôts, c'est la
  CI du dépôt de données (`modele-donnees.yml`) : chaque `secrets/<env>.env.enc` contre le `.cles`
  du dépôt de code, lu sur sa branche par défaut, et les destinataires de `.sops.yaml` contre les
  clés de `cles/*.pub`. Le dépôt de code garde gitleaks et le contrôle de ses `.cles`.
- **KeePassXC est la source de chaque valeur.** Une valeur perdue se régénère : une adresse se
  relit dans Healthchecks, un jeton se refait.
- **Écartés** : changer une valeur sur le serveur puis rapatrier le fichier, qui est une écriture
  sur le serveur ; déchiffrer sur le poste avec la clé hors ligne, faite pour la perte du serveur
  et non pour chaque changement.

### 5. Le tunnel commun

Un seul tunnel Cloudflare pour tout le parc, décrit dans le dépôt `serveur` ; le projet n'a pas de
jeton de tunnel. Chaque environnement a son réseau Docker, `tunnel-<nom>-<env>`, déclaré `external`
dans `compose.yml` ; l'app y porte l'alias `<nom>-<env>`, et les routes de Cloudflare visent
`http://<nom>-prod:<port_app>` et `http://<nom>-staging:<port_app>`. Un réseau par environnement, et
non le réseau de l'hôte : le tunnel n'atteint que les apps, jamais les autres ports locaux de la
machine.

### 6. Qui crée quoi

**La sonde de `serveur` crée ce qui manque, la sonde du projet fait vivre ses versions.** Depuis la
déclaration `projets/<nom>.env` du dépôt `serveur`, la première crée les clones, les dossiers, les
réseaux et la première installation des unités ; elle ne supprime jamais rien. La seconde
déploie, et tient les unités à jour : à chaque nouvelle version elle les réinstalle, à chaque
passage elle les compare à leur rendu (`installer-unites.sh --verifier`) et alerte au moindre écart.
Aucune étape de la mise en service ne se passe sur la machine.

À deux dépôts (amendement du 2026-10-29), les clones des données, `~/<nom>-donnees` et
`~/<nom>-donnees-staging`, reviennent aussi à la sonde de `serveur`, avec la clé de déploiement du
dépôt de données, qui est privé. La sonde du projet les attend : un clone absent l'arrête (§ 8).

### 7. La supervision

Un contrôle Healthchecks par sonde (et par sauvegarde, M-0005), dont l'adresse est un secret
(`HC_*`). Une unité en échec déclenche `<nom>-alerte@.service` par `OnFailure=`. Une adresse de
ping passe à `curl` par `-K -`, jamais en argument, et n'est jamais journalisée.

### 8. Le couple et les deux modes

Amendement du 2026-10-29 (M-0006, §§ 5 et 6). L'état déployé est un couple : une image et un
commit de données. Le commit de données dit quelle configuration et quel contenu l'application lit
(M-0003, § 6).

**Les deux modes.** Le mode suit la nature du dépôt, sans réponse de plus. Il est rendu dans
`deploiement/lib.sh` (`MODE_DONNEES`), le seul endroit qui le dit.

| | À deux dépôts | À un dépôt |
|---|---|---|
| Qui | un dépôt de nature `code`, né après M-0006 | un dépôt de nature `donnees`, d'avant M-0006, jusqu'à sa scission (M-0006, § 7) |
| Le code, `compose.yml`, les scripts, `projet.env` | le clone du code | le clone unique |
| `env/`, les secrets, `.sops.yaml`, les clés du parc | à la racine du clone des données, le dépôt `<nom>-donnees` | sous `deploiement/` du clone unique, `.sops.yaml` à sa racine |
| La configuration et le contenu | `config/` et `contenu/` du clone des données | `instance/config/` et `instance/contenu/` du clone unique |
| Les clones du serveur | `~/<nom>` et `~/<nom>-staging`, puis `~/<nom>-donnees` et `~/<nom>-donnees-staging` | `~/<nom>` et `~/<nom>-staging` |
| Le commit de données, en staging | la tête de la branche des données que nomme `VEILLE_EMPLOI_BRANCHE_DONNEES`, la principale à la création | la révision de l'image `:main` |
| Le commit de données, en prod | la plus haute étiquette de données | la révision de l'image de la plus haute `vX.Y.Z` |

Ce projet est à deux dépôts : sa nature est `code`, et son instance vit dans `veille-emploi-donnees`.

**Le commit de données du couple.**

- Un projet qui ne déclare ni `VERIFIER_CONFIG` ni `VERIFIER_CONTENU` a le commit `-` : rien n'est
  monté ni vérifié, et le champ `configuration` n'est pas lu, comme avant le couple.
- Sinon, à deux dépôts, c'est un commit du clone des données de l'environnement. En staging, la
  tête de la branche que nomme `VEILLE_EMPLOI_BRANCHE_DONNEES` dans `env/staging.env` : la variable
  n'a pas de défaut, et le gabarit du dépôt de données y écrit sa branche principale à la création.
  La sonde ne change jamais la branche du clone : elle l'avance par `git merge --ff-only`, sur la
  branche du clonage. Une autre branche ne se suit donc que si elle descend de la tête du clone, et
  changer de branche n'est pas pris en charge à ce jour. En prod, la plus haute étiquette de
  données.
- À un dépôt, c'est la révision de l'image visée, son label `org.opencontainers.image.revision`,
  qui doit exister dans le clone. En prod, c'est le commit que la `vX.Y.Z` désigne : la CI construit
  l'image de ce commit, et l'étiquette la réétiquette sans la reconstruire (§ 1). L'instance va
  donc en prod avec l'étiquette du code : il n'y a pas de série de données.
- **Le commit se fixe d'après la déclaration de la version du code visée, jamais celle qu'on
  quitte.** En prod, la sonde lit le `deploiement/projet.env` de l'étiquette visée sans y passer le
  clone (`git show`). Une version qui commence ou cesse de déclarer une commande se déploie donc
  dès son premier passage.

**L'état.** `deploye` et `precedent` portent `<image@sha256:…> <version> <commit>`, et `echec`
porte `<image@sha256:…> <commit>`. `<commit>` est le commit de données, 40 caractères
hexadécimaux, ou `-`. Chaque fichier s'écrit d'un seul coup. Les scripts d'avant la `v0.7.0` ne
lisent que les premiers champs de ces fichiers (`read -r image version _`) : un retour par une
étiquette du code vers une telle version relit l'état sans se tromper. Un fichier d'avant la
`v0.7.0`, sans le commit, se lit comme un couple en `-`.

**Ce qui déclenche un déploiement** : un couple visé différent du couple déployé, donc une nouvelle
image, un nouveau commit de données, ou les deux. Un commit de données seul redéploie l'image
visée, la même hors d'un `--retour` qui l'a quittée (§ 2), avec les mêmes vérifications et le même
retour arrière. **L'échec se note sur le couple** : un couple en échec ne se rejoue jamais ; tout
autre couple se tente, et un même commit de données peut échouer avec une image et passer avec la
suivante.

**L'instantané des données.** Pour un couple qui a un commit, la chaîne extrait du commit, par
`git archive`, jamais de la copie de travail du clone, les dossiers déclarés, sous
`~/.local/state/veille-emploi/<env>/instantanes/<commit>/config` et `…/contenu`, quel que soit le mode.
Elle travaille sous `<commit>.partiel`, qu'elle retire d'abord s'il reste d'un essai coupé, fige
les droits en lecture seule, puis renomme. Un instantané complet se réutilise tel quel. En staging,
`config/` n'est jamais extrait.

**Le montage de l'instantané.** Le `compose.env` du couple porte `VEILLE_EMPLOI_CONFIG` et
`VEILLE_EMPLOI_CONTENU`, les chemins de l'instantané, et `dc` (`lib.sh`) ajoute `compose.config.yml`
et `compose.contenu.yml`, gérés, qui les montent en lecture seule. Le conteneur ne voit jamais le
clone. Le chemin nomme le commit : un nouveau commit change le montage et recrée le conteneur.
Après le `up`, le déploiement vérifie, par `docker container inspect`, que le conteneur monte
l'instantané visé, en lecture seule. Une variable `VEILLE_EMPLOI_CONFIG` ou `VEILLE_EMPLOI_CONTENU`
posée dans l'environnement est refusée : elle l'emporterait sur `compose.env`.

**La vérification précède tout changement.** Sous le verrou, avant l'instantané de `/donnees` et le
`up`, la chaîne contrôle la règle des paires sur le commit visé, prépare son instantané, puis lance
chaque commande déclarée, avec l'image visée, sur cet instantané (M-0003, § 6). `VERIFIER_CONTENU`
reçoit sur `/en-service` le contenu de l'instantané du couple en service, s'il en a un ; cet
instantané se refait d'abord s'il manque. Le conteneur en service n'est jamais touché :

- des données non conformes (code 2) : le couple est marqué en échec, la sonde alerte, et elle ne
  le retentera pas ;
- une vérification qui n'a pas eu lieu (une règle des paires en défaut, un instantané impossible,
  un code 64 ou tout autre code) : rien n'est marqué, la sonde alerte, et elle réessaie à chaque
  passage.

**Les étiquettes de données.** À deux dépôts, la prod suit la plus haute étiquette de la série
`donnees-AAAA.MM.JJ.n`, par exemple `donnees-2026.11.03.1`, `n` partant de 1 chaque jour, sans
zéro en tête. La plus haute se trie par date, puis par `n` (`git tag --sort=-v:refname`) :
`donnees-2026.11.03.10` passe devant `donnees-2026.11.03.9`. Les autres formes sont ignorées,
`vX.Y.Z` comprises : un dépôt renommé à la scission garde ses anciennes étiquettes du code, que la
chaîne ne lit pas. Une étiquette retirée de l'origine disparaît du clone
(`git fetch --prune --prune-tags`). **Elles sont à Edouard** (M-0002) : le garde de Claude refuse
leur envoi comme celui des `vX.Y.Z`. Aucun workflow ne tourne sur elles : la sonde de prod les lit
dans le clone des données. À un dépôt, il n'y a pas de série de données.

**L'attente d'une étiquette de données.** En prod, quand la version visée du code déclare une
commande et que le dépôt de données n'a encore aucune étiquette, rien n'est tiré ni déployé. Si un
couple est en service, la sonde le contrôle comme à l'ordinaire (l'état, les unités, l'adresse
publique, avec le champ `configuration` de ce couple), puis son signal ok dit « <version> attend
une version des données ». Sans couple en service, son signal ok dit « aucune version des
données ».

**Les deux clones propres et à jour, ou rien.** À deux dépôts, la sonde contrôle aussi le clone des
données de l'environnement, qu'une commande soit déclarée ou non, puisqu'il porte l'env et les
secrets. Trois anomalies l'arrêtent avant tout déploiement :

- « clone des données absent » : sans lui, ni env ni secrets. `HC_SONDE` et l'env que lit
  `alerter.sh` vivent dans ce clone : aucun signal ne peut partir, et seule l'absence du signal ok
  avertit, au bout du délai de grâce ;
- « clone des données modifié » : `git status --porcelain` n'y est pas vide ;
- « mise à jour du clone des données impossible » : en staging, `git fetch` puis
  `git merge --ff-only` de la branche des données ; en prod, `git fetch --prune --prune-tags
  --tags`, puis, juste avant le déploiement, le passage sur l'étiquette de données.

**La limite d'un projet sans commande.** À deux dépôts, son couple a le commit `-` : un changement
de son `env/` ou d'un secret dans le dépôt de données ne déclenche rien, et n'entre en service
qu'au déploiement suivant du code. En prod, le clone des données ne passe sur la plus haute
étiquette de données qu'avant l'appel de `deployer.sh`. Il y passe même sans commande : l'env et
les secrets de la prod suivent la série. Sans aucune étiquette de données, il reste où il est.

**Ajouter ou retirer une commande.** Chaque image se vérifie avec la déclaration de sa propre
version : la sonde avec celle de la version visée, la CI du dépôt de données avec celle de `:main`
(la branche principale du code) et celle de la plus haute `vX.Y.Z`. Une commande ajoutée ou
retirée dans le code se publie avant que les données changent. Dans l'intervalle, la CI des données
refuse : ses deux images ne déclarent pas la même chose, et la règle des paires refuse l'une des
deux. Un couple dont la déclaration et le commit de données ne vont pas par paires ne se déploie
pas non plus : la sonde alerte et réessaie, jusqu'à ce que les données suivent.

**Le retour arrière revient à un couple entier.** `deployer.sh <env> --retour` remet l'image, la
version et le commit de données de `precedent`, avec les vérifications et le contrôle de santé d'un
déploiement ; le ménage garde toujours l'instantané de `precedent`. Deux cas de transition :

- un `precedent` dont le commit est `-`, celui d'une version d'avant ses données, ne monte ni ne
  vérifie rien, même si `projet.env` déclare une commande. C'est le filet de la première version
  qui en déclare une (M-0003, § 6) ;
- à l'inverse, un `precedent` qui a un commit est refusé (code 64) quand `projet.env` ne déclare
  plus rien : pas de retour arrière après une version qui retire ses commandes.

Plus généralement, `--retour` vérifie le couple de `precedent` avec la déclaration de la version
qu'il quitte, le `projet.env` du clone en service. Après une version qui ajoute ou retire une
commande, le retour peut donc être refusé : par la règle des paires, ou par le code 64 de l'ancienne
image, qui ne connaît pas la commande. Le refus ne change rien. Le remède est une étiquette (§ 2),
qui remet en service un couple vérifié.

Un retour par une étiquette du code (§ 2) forme un couple nouveau : l'ancienne image et le commit de
données en service. Les commandes de l'ancienne image le vérifient comme tout couple ; si elles le
refusent, une version de schéma qu'elle ne connaît pas par exemple, le retour demande aussi une
étiquette de données sur l'ancien commit de données (M-0006, § 6). À un dépôt, l'étiquette posée
sur l'ancien commit ramène ensemble l'image et l'instance de ce commit.

**Le ménage des instantanés.** Après chaque déploiement ou retour arrière réussi,
`nettoyer-images.sh` fait, après le ménage des images, celui des instantanés de l'environnement. Il
garde ceux que nomment `deploye` et `precedent` de cet environnement, plus les 3 plus récents des
autres, et retire les autres, ainsi que tout `.partiel` de plus d'un jour. Une surprise l'annule
sans rien retirer ; son échec ne change pas le résultat du déploiement. Un instantané retiré se
refait du clone des données.

## Conséquences

- Ce qu'Edouard seul fait : les étiquettes, les routes Cloudflare, les contrôles Healthchecks,
  chaque saisie de secret, le passage du paquet en public, la clé de déploiement d'un dépôt privé.
- Une version met au plus 5 minutes à arriver après sa publication.
- Un retour arrière ne restaure pas les données : une migration, une variable ou un service
  s'ajoutent avant de s'enlever (invariant 4). Une version qui ne peut pas le respecter le
  déclare, et son retour passe par une restauration (M-0005).
- Une valeur de secret absente de KeePassXC empêche de refaire le fichier : on la régénère d'abord.
- À deux dépôts, la prod a deux étiquettes : une version du code et une version des données y
  entrent chacune par la sienne, et chacune attend Edouard (§ 8). Un projet sans commande n'y fait
  entrer un env ou un secret changé qu'avec une version du code.
- **Difficile à changer** : peu de chose. Le modèle par tirage, GHCR et la convention « étiquette =
  prod » se remplacent sans toucher l'application. La forme de l'état en couple, elle, est lue par
  les versions précédentes des scripts lors d'un retour arrière (§ 8).

## Révision

Cet ADR doit être rouvert si :

- le parc passe à un second serveur ;
- un projet doit être mis en production sans GitHub, ou plus vite que la sonde ;
- un projet ne peut plus tenir l'invariant 4, et son retour arrière demande davantage qu'une
  étiquette ;
- un retour arrière a besoin d'une image que le ménage des images (amendement du 2026-10-27, § 3) a
  retirée du serveur, et que GHCR ne rend pas ;
- un projet doit faire entrer un env ou un secret en service sans version du code, sans déclarer
  de commande de l'instance (§ 8) ;
- un instantané des données devient trop gros pour être extrait à chaque commit de données.

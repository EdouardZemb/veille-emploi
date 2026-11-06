# M-0006 — Le code et les données : un dépôt de code toujours publiable, un dépôt de données privé

- **Statut** : accepté le 2026-10-29
- **Amende** M-0002 (la porte de confidentialité), M-0003 (le contrat de l'image) et M-0004 (la
  chaîne de livraison)
- **Amendé** le 2026-10-29, avec le lot 11 : la liste des constats acceptés nomme un constat par son commit et son chemin, le motif en commentaire ; le numéro d'un motif change quand la liste privée se réordonne.
- **Amendé** le 2026-10-29, avec le lot 12 : la seconde étape est faite. La porte d'un dépôt de
  code suit le premier segment du chemin (§ 3), et la chaîne garde les deux modes, à deux dépôts et
  à un dépôt (§ 6).
- **Amendé** le 2026-11-03, avec le lot 13 : le script de création du poste vit dans
  `modele-projet`, sous `poste/` (§ 7) ; après un retour arrière par `--retour`, un geste qui ne
  change qu'une moitié de la cible ramène l'autre moitié du couple quitté (§ 6) ; en cible
  `serveur`, le dépôt de code est public (§ 1).
- **Amendé** le 2026-11-04, avec le correctif #94 : à la scission, `env/` et `cles/` sont rendus à
  neuf, et `.sops.yaml` se refait pour le nouveau chemin des secrets (§ 6).
- **S'applique en deux temps.** D'abord la porte par nature et le gabarit de données (§ 1 à 4).
  Ensuite la chaîne à deux dépôts et les règles de chemins (§ 3, dernier point, § 5 à 7). Entre les
  deux, la chaîne lit encore tout dans le clone du code, comme avant.
- **Contexte amont** : M-0001 (aucune donnée réelle dans le dépôt, le jeu factice) ; la règle
  posée par Edouard le 2026-10-29 : « il faut repenser les projets pour que la partie code soit
  indépendante de la partie données […] et ça doit être un impératif pour les projets futurs »

## Contexte

M-0001 et l'invariant commun n° 2 interdisent toute donnée personnelle réelle dans le dépôt. Rien
ne le fait respecter, et le modèle lui-même range des données dans le dépôt de code :

- les secrets chiffrés y sont lus à un chemin fixe, et la CI exige leur présence ;
- `deploiement/env/<env>.env`, géré, y porte l'adresse publique et le bloc de ports ;
- `.copier-answers.yml` y porte le domaine, le sous-domaine et le bloc de ports ;
- des scripts et des tests gérés sont rendus avec le domaine et le bloc de ports écrits en dur.

Le modèle public porte en dur un domaine par défaut et les deux clés publiques du parc.

Une application peut aussi porter dans son code ce qui ne peut pas être public sans être une donnée
personnelle : un contenu protégé par le droit d'auteur, ou réservé à des personnes autorisées.

Dans un dépôt privé, la porte de confidentialité n'avertit que sur ce qui identifie (M-0002). Son
historique n'est donc jamais prêt à être publié. Le réécrire ne suffit pas sur GitHub : les
références des PR (`refs/pull/*`) gardent les anciens commits, et seul le support de GitHub peut
les purger.

Le prix se paie en CI : le quota de minutes des dépôts privés ne suffit plus, alors qu'un dépôt
public ne le consomme pas sur les runners standard.

Les données d'exécution, elles, sont déjà hors du dépôt : `/donnees` est monté depuis l'hôte, et
seule cette partie est sauvegardée (M-0003, M-0005). C'est la prise sur laquelle bâtir.

## Options

Où vivent les données :

| Option | Verdict | Raison |
|---|---|---|
| A. Un dépôt de données privé par projet | **Retenue** | Versionné et relu par PR ; chaque application reste propriétaire de ses données (M-0001) ; la session du projet y fusionne. Le dépôt privé d'aujourd'hui devient le dépôt de données sans rien réécrire |
| B. Un seul dépôt de données pour tous, `serveur` | Écartée | Mêle les projets, et met la configuration de chaque application sous le mode `edouard` de `serveur`. Elle ne vaut que pour ce qui relève du parc, qui y est déjà |
| C. La base de l'application, réglée dans l'app | **Retenue en complément** | Pour ce qui se règle au téléphone. Elle est sauvegardée avec `/donnees`, mais pas versionnée |
| D. Les données chiffrées dans le dépôt de code | Écartée | Aucun secret, même chiffré, ne va dans un dépôt de code. Un fichier chiffré public l'est pour toujours : une clé perdue un jour ouvre tout l'historique |
| E. Un dossier posé à la main sur le serveur, monté en lecture seule | Écartée | Viole l'invariant commun n° 3, et perd le versionnement et la relecture |
| F. Un seul dépôt privé, dont un miroir public ne reçoit que le code | Écartée | Garde des commits qui changent le code et les données d'un coup. Mais la CI tourne toujours dans le dépôt privé, donc sur le quota, et une erreur du filtre publie des données |
| G. Le dépôt de données en sous-module privé du dépôt de code | Écartée | Chaque changement de configuration demande un commit du code, et la CI publique ne peut pas lire le sous-module : le couplage revient |
| H. Un dépôt de données commun au parc, autre que `serveur` | Écartée | Sur un seul serveur, sous un seul utilisateur et une seule clé, il n'isole pas mieux qu'un dépôt par projet. Il perd la propriété par projet et le renommage du dépôt existant |

Comment la chaîne combine le code et les données :

| Option | Verdict | Raison |
|---|---|---|
| Le couple : la sonde combine la cible du code et celle des données | **Retenue** | Le staging suit les deux branches principales sans geste ; une version du code va en prod sur une étiquette, une configuration sur une autre |
| I. Le dépôt de données fixe l'image : l'état déployé n'est qu'un commit | Écartée | L'état serait plus simple, mais chaque version du code demanderait une PR dans le dépôt de données puis une étiquette : deux gestes au lieu d'un. Le staging, qui suit `:main`, garderait de toute façon une référence mobile |

## Décision

### 1. Deux natures de dépôt

- Un **dépôt de code** porte l'application, ses tests, son jeu factice, sa configuration
  d'exemple (`exemple/`), son contenu d'exemple et sa documentation générique. Il est public par
  défaut. S'il reste privé, la porte le traite comme public : sa visibilité n'est plus qu'un choix,
  sans travail préalable. En cible `serveur`, ce choix est fait : il est public, puisque la chaîne à
  deux dépôts le suppose. La CI du dépôt de données le clone sans jeton et tire ses images en
  anonyme (§ 6).
- Un **dépôt de données** porte ce qui fait d'une instance celle d'Edouard :
  - la configuration personnelle de l'application (`config/`) ;
  - le contenu de l'instance (`contenu/`, § 2) ;
  - les valeurs d'instance (`env/`) ;
  - les secrets chiffrés et leurs destinataires ;
  - la documentation qui porte un récit personnel ou des noms du parc.

  Il est toujours privé et se nomme `<nom>-donnees`. Les sessions du projet y fusionnent (mode
  `session`) ; le contenu d'un secret reste un geste 👤 d'Edouard (M-0004).
- La réponse `nature` (`code` ou `donnees`) remplace la réponse `visibilite`. Le même modèle produit
  les deux natures, comme il produit les cibles. Chaque nature a ses réponses : un dépôt de code
  n'a ni domaine, ni sous-domaine, ni bloc de ports dans son `.copier-answers.yml`. Ces réponses
  sont celles du dépôt de données, qui en rend son `env/`.
- Un projet en cible `serveur` a toujours un dépôt de données, puisqu'il a des valeurs d'instance
  et des secrets. Un autre projet en crée un le jour où il a une donnée à porter.
- Ce qui se règle au téléphone vit en base (option C) ; le dépôt de données n'en porte que la
  graine.
- `serveur` garde la machine et le parc. Il déclare les deux dépôts de chaque projet.

### 2. Ce qui est une donnée

Ne vont jamais dans un dépôt de code :

- les données d'exécution ;
- la configuration personnelle : identité, employeur, lieu, salaire, choix de recherche ;
- les noms des personnes du foyer, même comme noms factices : le jeu factice invente les siens ;
- les noms d'infrastructure : nom d'hôte, réseau privé, adresses, cibles SSH, domaine et
  sous-domaines, bloc de ports, chemin qui nomme l'hôte ou l'utilisateur. Une convention de chemin
  du modèle, comme `~/.local/share/<nom>`, est du code ;
- les secrets, même chiffrés, et leurs destinataires.

**Le contenu de l'instance** est une troisième catégorie : ni une donnée personnelle, ni du code. Il
regroupe ce que l'application montre et qui ne peut pas être public :

- un contenu protégé par le droit d'auteur, ou réservé à des personnes autorisées ;
- les mentions que la loi oblige l'instance à afficher : le contact du responsable du traitement,
  son lieu, les durées de conservation.

Il va au dépôt de données, dans `contenu/`. À la différence de la configuration personnelle, le
staging le monte aussi (§ 5).

**Sont des données, même publiques ailleurs** : le domaine et les sous-domaines, les clés publiques
`age` du parc, les destinataires de `.sops.yaml`, les métadonnées en clair d'un fichier chiffré. Ils
décrivent l'instance et le parc, pas l'auteur.

**Ne sont pas des données**, et restent dans le code :

- le compte GitHub et le nom qu'il affiche, partout où ils désignent le propriétaire du dépôt (les
  chemins `ghcr.io/<compte>/…`, l'origine du modèle, les labels d'image). Un dépôt public les
  montre par construction. Le compte devient une réponse du modèle plutôt qu'une valeur en dur ;
- le prénom du propriétaire comme rôle dans la méthode : le mode de fusion `edouard`, les gestes 👤 ;
- le contrat des noms de secrets, les fichiers `.cles` : les noms des variables qu'attend
  l'application, sans valeur.

### 3. La porte suit la nature (amende M-0002)

- **Dans un dépôt de code, tout constat refuse**, quelle que soit la visibilité, au hook comme en
  CI. La CI exige la liste privée, comme aujourd'hui.
- **Dans un dépôt de données, la porte avertit sur ce qui identifie et refuse les secrets**, comme
  aujourd'hui dans un dépôt privé.
- **En CI, la nature ne se lit pas dans la PR.** Un dépôt public est toujours un dépôt de code : la
  visibilité réelle l'emporte, comme aujourd'hui `DEPOT_PRIVE`. Un dépôt privé prend la nature écrite
  sur sa branche principale. Une nature absente ou illisible vaut `code`, la plus stricte. Changer la
  nature d'un dépôt est une décision d'Edouard, écrite dans un plan de lot.
- **La liste privée porte ce qu'aucun motif générique ne peut connaître** :
  - le domaine ;
  - les noms des personnes du foyer ;
  - les employeurs et les lieux ;
  - les courriels et les numéros de téléphone.

  Elle ne porte ni le compte GitHub ni le nom qu'il affiche (§ 2). Un motif s'y écrit de façon à ne
  pas prendre un mot pour un autre : `re:` et des bornes de mot quand le texte est court.
- **L'historique d'un dépôt de code est relu chaque semaine par la porte**, dans
  `modele-historique.yml`, et plus seulement par gitleaks :
  `--exiger-prives --historique --acceptes .github/constats-acceptes.txt`, qui relit tout
  l'historique (`git log --all -p`), messages des commits compris. Dans un dépôt de données, la
  porte ne relit rien, et gitleaks seul lit l'historique. Un constat ancien se reconnaît, il ne
  s'efface pas. Une liste versionnée nomme chaque constat accepté par son commit et son chemin, le
  motif en commentaire, jamais par sa valeur, et Edouard la relit. Rien d'autre n'est toléré. Un
  dépôt de code né après M-0006 part d'un commit propre et n'a pas de liste.
- **Avec la chaîne à deux dépôts**, la porte refuse dans un dépôt de code tout fichier `*.enc`, tout
  `.sops.yaml` et tout `cles/*.pub`, à n'importe quelle profondeur, et tout fichier sous un dossier
  de premier niveau `instance/`, `config/` ou `contenu/` : un `src/…/config/` reste du code
  (amendement du 2026-10-29 ; M-0002). Un gabarit `….jinja` n'est pas le fichier qu'il rend. Une
  clé publique `age` y devient un constat, où qu'elle soit écrite. Avant, ces règles refuseraient le
  premier commit de tout projet `serveur`, dont la chaîne lit encore ces fichiers dans le clone du
  code.

### 4. Les tests et le jeu factice

- Les tests d'un dépôt de code ne lisent que des fixtures, le jeu factice, `exemple/` et le contenu
  d'exemple. Chaque chemin de données y est redirigé vers eux, et un test garde-fou le vérifie.
- Ce test est une obligation du projet, écrite avec l'outil de sa pile, comme la mutation testing
  (M-0001) : le modèle ne peut pas l'écrire pour toutes les piles.
- Les tests et les scripts gérés par le modèle, dans un dépôt de code, sont rendus avec des valeurs
  factices : un domaine d'exemple, un bloc de ports d'exemple. Les scripts lisent les vraies
  valeurs dans `env/`, au moment où ils tournent.

### 5. Le contrat de l'application (amende M-0003), en cible `serveur`

- **L'image ne contient aucune donnée personnelle, aucun contenu de l'instance, aucune valeur
  d'instance.** Elle embarque `exemple/`, le contenu d'exemple et le jeu factice, qui sont du code
  (M-0001).
- **Elle lit sa configuration réelle dans `/config`** et son contenu dans `/contenu`, deux montages
  en lecture seule.
- **Le repli sur l'exemple n'existe pas en prod.** En `dev`, en `ci`, en staging, et sans
  environnement (le test de restauration), un `/config` ou un `/contenu` absent ou vide fait
  démarrer l'application sur son exemple. En prod, un projet qui a une configuration ou un contenu
  refuse de démarrer sans eux : sa santé n'est jamais `ok`, et le retour arrière prend la main.
  Servir l'exemple en prod tromperait les utilisateurs, et leurs appareils pourraient effacer ce
  qu'ils gardent du vrai contenu.
- **La route de santé dit quelle configuration sert** : un champ `configuration`, qui vaut
  `exemple` ou `montee`. Le déploiement exige `exemple` en staging, et `montee` en prod quand le
  projet a une configuration. Sinon il échoue, et le couple est marqué en échec. La sonde le
  contrôle aussi à chaque passage, sur l'adresse publique.
- **`VERIFIER_CONFIG <dossier>`**, déclarée dans `deploiement/projet.env`, valide une configuration.
  Comme `VERIFIER`, elle rend 0 si la configuration est conforme, 2 si elle ne l'est pas, 64 en cas
  d'erreur d'usage, et ne modifie jamais son argument. Sur le serveur, elle tourne dans un
  conteneur jetable, sans réseau, qui ne voit que le dossier, monté en lecture seule sur `/config`.
  La CI la lance par `docker run` sur `exemple/` : elle prouve à la fois l'exemple et la clause de
  l'`ENTRYPOINT`.
- **`VERIFIER_CONTENU <dossier> [<en service>]`** fait de même pour un contenu, monté sur
  `/contenu`, avec les mêmes codes. Le second argument, facultatif, est le contenu en service, monté
  à part : il permet de refuser un changement qui défait un identifiant définitif.
- **La configuration et le contenu portent leur version de schéma.** L'application la lit et refuse
  une version qu'elle ne connaît pas : la commande de vérification rend alors 2. Une nouvelle
  version de schéma suit l'invariant commun n° 4 : l'image qui la lit arrive avant les données qui
  la portent, et lit encore l'ancienne.
- **Ils vont par paires** : `config/` avec `VERIFIER_CONFIG`, `contenu/` avec `VERIFIER_CONTENU`. La
  chaîne refuse un dossier sans sa commande, et une commande sans son dossier.
- **Le staging ne monte jamais `/config`.** Il tourne sur `exemple/` et le jeu factice, avec ses
  propres valeurs d'instance et ses propres secrets. Il monte `/contenu`, puisque le contenu de
  l'instance n'est pas une donnée personnelle. La chaîne refuse un montage de `/config` en staging.

### 6. La chaîne de livraison (amende M-0004), en cible `serveur`

- **Deux clones par environnement**, le code et les données. La sonde lit `compose.yml`, ses
  scripts et `projet.env` dans le clone du code ; `env/`, les secrets, les clés du parc, `config/` et
  `contenu/` dans le clone des données. Le code public se clone sans clé ; le dépôt de données
  reçoit la clé de déploiement : leur nombre ne change pas.
- **Le conteneur ne voit jamais le clone.** À chaque commit de données, la chaîne en extrait
  `config/` et `contenu/` dans un instantané immuable, sous l'état du déploiement, et c'est lui qu'elle
  monte. Le chemin de l'instantané nomme le commit. Un nouveau commit change donc le montage et
  recrée le conteneur. Le déploiement vérifie que le conteneur en service monte l'instantané visé.
  Chaque environnement a ses instantanés : le ménage retire ceux que ni son état ni la marge ne
  gardent, comme pour les images (amendement du 2026-10-29 ; M-0004, § 8).
- **Le contrôle des secrets passe au dépôt de données.** Sa CI compare chaque fichier chiffré aux
  `.cles` du dépôt de code, qui est public, et aux destinataires de son `.sops.yaml`. Le dépôt de
  code garde gitleaks.
- **Le dépôt de données suit la règle du code** : le staging suit sa branche principale, la prod
  sa plus haute étiquette, posée par Edouard (M-0002). C'est déjà le sort d'un secret refait, qui
  entre en prod à l'étiquette suivante. Ses étiquettes forment leur propre série, distincte de celle
  du code, et le garde refuse de les envoyer comme les autres.
- **L'état déployé est un couple** : l'image et le commit de données, écrits d'un seul coup. Le
  couple précédent est le dernier couple sain. Un retour arrière revient à un couple entier,
  jamais à une moitié. Un retour par une étiquette du code (M-0004, § 2) forme, lui, un couple
  nouveau : l'ancienne image et le commit de données en service. La commande de vérification le
  refuse si cette image ne connaît pas la version de schéma en service ; le retour demande alors
  aussi une étiquette sur l'ancien commit de données.
- **Ce qui déclenche un déploiement** : une nouvelle image, un nouveau commit de données, ou les
  deux à la fois. Un nouveau commit de données forme un couple avec l'image visée, la plus haute
  `vX.Y.Z` en prod : c'est l'image en service, sauf après un retour arrière par `--retour` qui l'a
  quittée. Le couple se déploie après ses vérifications, avec le même retour arrière qu'une image.
  Après un tel retour, seul le couple quitté est en échec, et un geste qui ne change qu'une moitié
  de la cible ramène l'autre moitié de ce couple. Quand le retour a quitté l'image, une étiquette
  de données remettrait donc en service la version quittée : il faut d'abord une `vX.Y.Z` plus
  haute sur le commit de la version gardée. Quand il a quitté le commit de données, une `vX.Y.Z`
  sur un nouveau commit remettrait en service les données quittées : il faut d'abord une étiquette
  de données sur un commit corrigé. Quand il a quitté les deux, le premier geste remplace la moitié
  en cause.
- **Les deux clones propres et à jour, ou rien.** Un clone modifié, ou dont la mise à jour échoue,
  arrête la sonde avant tout déploiement, avec une alerte, comme aujourd'hui un clone modifié.
- **L'échec se note sur le couple.** Une vérification qui refuse, ou un déploiement qui échoue,
  marque le couple en échec. Un couple en échec ne se rejoue jamais ; tout nouveau couple se tente :
  un même commit de données peut échouer avec une image et passer avec la suivante.
- **L'instantané des données note le couple en service.** Une restauration remet les données sous
  le couple déployé, que l'invariant commun n° 4 rend capable de les lire, et dit le couple de
  l'instantané quand il diffère. Une configuration changée depuis n'est pas défaite : c'est une
  décision, pas une perte.
- **Un projet né avant M-0006 garde la chaîne à un dépôt jusqu'à sa scission.** Le lot de la chaîne
  décide si elle garde les deux modes, ou si ce projet attend sa scission pour monter de version.
  **Le lot de la chaîne a gardé les deux modes** (amendement du 2026-10-29). Le mode suit la nature,
  sans réponse de plus : un dépôt de nature `donnees` en cible `serveur` déploie à un dépôt. Il
  passe aux versions suivantes du modèle sans attendre sa scission et garde ses réponses. Il monte
  déjà sa configuration et son contenu depuis `instance/config/` et `instance/contenu/`, à côté de
  son code. La prod y prend le commit de la plus haute `vX.Y.Z`, sans série d'étiquettes de données.
  La scission déplace ensuite ces dossiers et les secrets chiffrés vers le dépôt de données. Le
  modèle y rend `env/` et `cles/` à la place de `deploiement/env/` et de `deploiement/cles/`, et
  `.sops.yaml` s'y refait pour le nouveau chemin des secrets (amendement du 2026-11-04). Le
  contrat de l'application ne change pas (M-0004, § 8).

### 7. La naissance et la scission

- **Un projet naît en deux dépôts** : le modèle produit le dépôt de code (`nature` à `code`), puis
  le dépôt de données (`nature` à `donnees`). Le script de création du poste,
  `poste/Nouveau-Projet.ps1` dans `modele-projet`, crée les deux.
- **Un dépôt né avant M-0006 ne se réécrit pas.** Il est renommé `<nom>-donnees` et devient le
  dépôt de données : son historique, ses PR, ses issues, ses étiquettes et ses publications restent
  privés. Jusque-là, il a la nature `donnees`. Une PR y retire ensuite le code, qui ne vit plus
  qu'au dépôt public.
- **Un nouveau dépôt public prend le nom du projet, à partir d'un seul commit.** Son arbre se
  construit par la liste de ce qui entre, et non de ce qui sort. La porte en mode public le relit en
  entier avant le premier envoi. Ses versions continuent la numérotation du projet, au-dessus de
  la dernière étiquette d'avant la scission.
- **La scission d'un projet en service est un aller simple**, écrite comme une migration dans le
  plan de son lot :
  - la chaîne ne lit, dans le dépôt renommé, que la série des étiquettes de données ; les
    anciennes étiquettes du code y sont ignorées ;
  - les clones du serveur sont recréés, sonde arrêtée, et non re-pointés : un historique neuf ne
    s'avance pas par `--ff-only`. C'est un geste 👤 écrit d'avance ;
  - les versions d'avant la scission n'ont ni dépôt de code public ni `VERIFIER_CONFIG` : l'horizon
    du retour arrière repart de la première version scindée. La dernière image d'avant reste
    gardée jusqu'à la version suivante ;
  - le paquet d'images ne passe en public qu'une fois supprimées toutes les images qui embarquent
    une donnée ou un contenu de l'instance. D'ici là, il reste privé, et le serveur tire avec le
    jeton du parc.
- Une issue ne se transfère qu'après relecture de son texte, puisque le transfert la rend publique.
  L'inventaire à faire avant le renommage (les remotes, la clé de déploiement, le paquet, les
  secrets de la CI, la règle de protection) est écrit dans le plan du lot de chaque projet.

## Conséquences

- Tout dépôt de code peut passer en public sans rien retirer. Sa CI ne consomme plus le quota, et
  l'application se montre (M-0001).
- Deux dépôts par projet : deux clones, un état déployé en couple, des instantanés de données
  montés, deux étiquettes pour la prod. Une mise en production d'une configuration ou d'un contenu
  attend Edouard, comme celle d'une image.
- Une application lit sa configuration et son contenu au démarrage, dans un montage qui ne change
  pas sous elle. Une vérification qui refuse ne touche jamais le conteneur en service.
- La famille « aucune donnée réelle dans le dépôt » n'est outillée que pour ce que la liste privée
  connaît. Un nom ou un lieu qu'elle ne porte pas passe la porte. La séparation rend la fuite
  improbable, puisque la configuration et le contenu ne sont plus dans le dépôt de code ; elle ne la
  rend pas impossible. La méthode, qui la comptait parmi les familles outillées, le dit désormais.
  Un binaire n'est examiné ni au commit ni dans l'historique : la limite de M-0002 demeure.
- L'historique du modèle garde son ancien domaine par défaut et les clés publiques du parc. Il ne
  se réécrit pas : ce sont des valeurs publiques, inscrites dans la liste des constats acceptés.
- La scission d'un projet déjà en service coûte un lot entier : la réécriture de ce qui mêle le
  code et l'instance, un exemple à écrire, des clones recréés, un horizon de retour arrière remis à
  zéro. C'est un aller simple, qu'Edouard décide projet par projet. Un projet non scindé reste un
  dépôt privé de nature `donnees`, qui fonctionne comme avant.
- La CI d'un dépôt de données reste petite : la porte, les hooks, le contrôle des secrets et les
  commandes de vérification contre l'image publiée. Elle seule consomme encore le quota.
- Un réglage fait au téléphone vit en base. Il est sauvegardé avec `/donnees` (M-0005), mais n'est
  ni versionné ni relu.
- **Difficile à changer** : la séparation elle-même, une fois les projets scindés ; le contrat de
  `/config` et de `/contenu`, et l'état déployé en couple.

## Révision

Cet ADR doit être rouvert si :

- une donnée personnelle ou un contenu de l'instance est trouvé dans un dépôt de code : la porte
  gagne le motif ou le contrôle qui manquait ;
- un réglage fait au téléphone doit être versionné ou relu ;
- un contenu de l'instance est écrit par d'autres que les sessions du projet, ou doit changer plus
  vite qu'une étiquette ;
- les dépôts de données consomment à leur tour plus que le quota ;
- GitHub permet de purger les références des PR sans son support : la réécriture de l'historique
  redevient une option.

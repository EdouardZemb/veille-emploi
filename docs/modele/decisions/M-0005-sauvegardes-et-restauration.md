# M-0005 — Sauvegardes et restauration : un instantané chaque nuit, une copie que le serveur ne sait pas relire, une restauration rejouée

- **Statut** : accepté le 2026-10-18
- **Amendé** le 2026-10-28, avec le lot 10 : avant un déploiement ou un retour arrière, la garde
  du dossier de données refuse un dossier vide ou changé (§ 3)
- **Amendé** le 2026-10-29, avec le lot 12 : chaque instantané de `/donnees` note le couple en
  service dans un fichier voisin, chiffré et envoyé avec l'archive, et la restauration le dit
  (§ 2, § 3 et § 6, M-0004 § 8)
- **Amendé** le 2026-11-01, avec la v0.7.1 : tant que la prod n'a rien déployé, `serveur` peut
  dire « non » aux heures des sauvegardes (§ 2)
- **Contexte amont** : les sauvegardes d'`ancrage` (son ADR-0007, §4 et §5), dont la mécanique
  est extraite ; M-0003 (le contrat de l'instantané) ; M-0004 (la chaîne de livraison)

## Contexte

Une sauvegarde qu'on n'a jamais relue ne prouve rien, et une sauvegarde qui échoue sans alerte peut
rester en échec des semaines. Le serveur peut être perdu ; s'il est compromis, ses copies distantes
ne doivent pas l'être avec lui. La mécanique doit tout faire sans rien savoir de la base de l'app :
elle ne connaît que les commandes du contrat, `SAUVEGARDER`, `VERIFIER` et, facultative,
`REPORTER` (M-0003).

## Décision

### 1. La prod seulement

Le staging n'a que des données factices (M-0001). `sauvegarder.sh`, `tester-restauration.sh` et
`restaurer.sh` refusent tout autre environnement (code 64).

### 2. Chaque nuit, `sauvegarder.sh prod`

- Une prod qui n'a encore rien déployé n'a rien à sauvegarder. Jusque-là, et seulement jusque-là,
  `serveur` peut déclarer `SAUVEGARDE=non` et `TEST_RESTAURATION=non` : ni la sauvegarde ni son
  test ne s'installent. `installer-unites.sh` refuse « non » dès que la prod a un état déployé, et
  quand la sonde de prod va y déployer une version (amendement du 2026-11-01).
- Lancé par `<nom>-sauvegarde.timer`, à l'heure que le dépôt `serveur` donne au projet
  (`projets/<nom>.env`) : deux sauvegardes du parc ne se chevauchent pas.
- Sous le verrou que partagent la sonde, le déploiement et la restauration, `SAUVEGARDER` écrit
  dans le conteneur en service `quotidiennes/<nom>-<horodatage>.partiel`. Le dossier est contrôlé
  (code 0, un dossier non vide, rien que des fichiers et des dossiers), puis renommé par `mv -T`.
  Cette copie en clair reste 30 jours dans `~/backups/<nom>/`, sur le disque des données.
- **La copie distante** est `tar --hard-dereference … | age -R …/hors-ligne.pub`, pour la clé
  publique hors ligne, lue dans les clés du parc du clone des données (M-0004, § 4 ; amendement du
  2026-10-29) : un lien physique y entre comme un fichier ordinaire, et tous les membres sont sous
  un seul dossier, `<nom>-<horodatage>/`. Elle part par `rclone copy` vers
  `sauvegardes:<nom>-sauvegardes` (`sauvegardes:` est l'alias que le serveur fait pointer vers son
  stockage), contrôlée par `rclone lsf`, et reste 90 jours.
- **Le couple de l'instantané.** Amendement du 2026-10-29 (M-0004, § 8). Juste après l'instantané,
  toujours sous le verrou, la mécanique écrit à côté de lui, jamais dedans,
  `<nom>-<horodatage>.couple` : une ligne `<image> <version> <commit>`, le couple en service, celui
  de `deploye` à cet instant. Le contenu de l'instantané et les membres de son archive ne changent
  pas. Sans `deploye`, ou s'il ne se lit pas, il n'y a pas de `.couple`, et la sauvegarde continue.
  Le `.couple` est chiffré pour la même clé, `<nom>-<horodatage>.couple.age`, à la date de
  l'archive, puis envoyé après elle ; `rclone lsf` doit voir les deux. Les données passent avant
  leur couple : si le couple ne se chiffre pas ou ne part pas, l'archive part quand même, et la nuit
  est en échec.
- **La rétention**, après un envoi contrôlé seulement. En local, l'âge se lit dans le nom de
  l'instantané, jamais dans la date du dossier : 30 jours pour `quotidiennes/`, `pre-deploiement/`
  et `avant-restauration-*`, `.partiel` compris ; un nom d'une autre forme n'est jamais retiré. Le
  `.couple` d'un instantané part avec lui. À distance, seules les archives `<nom>-*.tar.age` de plus
  de 90 jours, et leurs couples `<nom>-*.couple.age`, qui ont leur date : le même appel les retire
  ensemble, sans corbeille.
- Le signal `HC_SAUVEGARDE` porte un résumé, jamais la sortie de la commande : Healthchecks est un
  tiers, et la sortie peut décrire les données.

### 3. Avant chaque déploiement

En prod comme en staging, `deployer.sh` prend un instantané, de même forme, dans le
`pre-deploiement/<horodatage>` de l'environnement, si l'app tourne. Il crée d'abord
`pre-deploiement/` s'il manque, et le ramène à 700 avec le dossier des sauvegardes. S'il échoue,
le déploiement n'a pas lieu et rien ne change ; la sonde réessaie, et alerte, à chaque passage.
Après un instantané réussi, il note à côté de lui son couple, comme la sauvegarde de la nuit
(§ 2) : pour `pre-deploiement/`, le couple que le déploiement quitte (amendement du 2026-10-29).
Puis il purge `pre-deploiement/` de ce qui a plus de 30 jours, d'après le nom, chaque instantané
avec son `.couple` : la sauvegarde de la nuit ne tourne qu'en prod, et le staging n'aurait sinon
aucune purge.

**La garde du dossier de données.** Quand une version est déployée (`deploye` existe), un
déploiement comme un retour arrière refuse, avant l'instantané et sans rien changer, un dossier de
données qui n'est plus celui de la version déployée, ou qui est vide. La référence est le chemin
canonique (`realpath`) que chaque succès écrit dans le fichier `donnees` de l'état : le chemin
canonique du jour doit être exactement celui-là, et un lien repointé sur place est donc vu. Un état
d'avant la `v0.5.0` du modèle, sans ce fichier, se rabat sur le dossier que décrit le `compose.env`
de la version déployée ; sans l'un ni l'autre, seul le vide est contrôlé. Le refus rend 1 : le
journal porte les chemins, le signal d'échec n'en porte aucun, et la sonde réessaie et alerte.
L'option `--donnees-neuves`, après l'image et la version, à la main, lève les deux contrôles pour
un déploiement ; elle est refusée avec `--retour` (code 64). Un couple qui a des données la prend
avec `--commit-donnees <sha>`, dans l'ordre qu'on veut (M-0004, § 8 ; amendement du 2026-10-29).
**La limite** : une racine de l'état déplacée elle aussi emporte `deploye` et `donnees`, et le
déploiement passe pour un premier, sans contrôle.

### 4. La clé hors ligne n'est jamais sur le serveur

Les archives distantes sont chiffrées pour `hors-ligne.pub`. La clé privée est rangée hors ligne
(KeePassXC, papier) : une compromission du serveur ne permet pas de les relire. En contrepartie, la
perdre les rend inutilisables.

### 5. Chaque semaine, `tester-restauration.sh prod`

Lancé par `<nom>-test-restauration.timer`, chaque semaine, au jour et à l'heure `TEST_RESTAURATION`
que déclare `serveur` (`projets/<nom>.env`). Le dernier `quotidiennes/<nom>-<horodatage>` (jamais
un `.partiel`) est copié, contrôlé par `VERIFIER` dans un conteneur jetable de l'image en service,
puis l'app démarre sur la copie, au port `bloc_ports + 9` : sa santé doit dire `ok`. Le test ne
touche ni aux données de la prod ni à ses sauvegardes. Signal `HC_TEST_RESTAURATION`.

### 6. Restaurer, à la main : `restaurer.sh prod <dossier|archive .tar.age> [--oui] [--cle <identité age>] [--sans-report]`

- Sans `--oui`, le script dit ce qu'il ferait, report compris, et ne touche à rien.
- Avec `--oui` : le verrou ; `VERIFIER` sur une copie de l'instantané avant tout changement ;
  l'arrêt de l'app ; le report, si le projet en déclare un ; l'ancien contenu de `/donnees` déplacé
  dans `avant-restauration-<horodatage>/`, jamais supprimé ; l'instantané à sa place ; le
  redémarrage et la santé. Si quelque chose échoue en chemin, l'ancien contenu revient, ou le
  message dit où est chaque chose.
- **Le couple de l'instantané** (amendement du 2026-10-29). Avec la source, la restauration lit le
  couple dans le fichier voisin : `<dossier>.couple`, ou, à côté d'une archive,
  `<nom>-<horodatage>.couple.age`, déchiffré avec la même clé, juste après l'archive. Après
  `VERIFIER`, elle le dit quand il diffère du couple déployé, et ne dit rien quand c'est le même.
  Sans fichier voisin (un instantané d'avant la `v0.7.0` du modèle, ou pris sans couple en
  service), elle dit « couple de l'instantané inconnu » ; un fichier qui ne se lit pas (un lien,
  jamais suivi, une autre clé, une autre forme) est dit illisible, sur la même ligne. **Le couple ne
  décide de rien** : les données reviennent sous le couple déployé, que l'invariant 4 rend capable
  de les lire, et une configuration changée depuis n'est pas défaite (M-0006, § 6). Une identité age
  chiffrée par une phrase de passe, dans un fichier, demande la phrase deux fois, pour l'archive
  puis pour son couple : age relit le fichier à chaque fois. C'est accepté ; une clé passée par
  l'entrée standard, elle, n'est lue qu'une fois.
- **Le report.** Restaurer une sauvegarde défait tout ce qui a changé depuis, y compris ce qui ne
  devait pas l'être : un compte supprimé avant la restauration reviendrait. Un projet qui garde un
  tel état (un registre de suppressions, par exemple) déclare `REPORTER` dans
  `deploiement/projet.env` (M-0003), et `REPORTER_SECTION`, la section de son
  `docs/exploitation.md` qui dit comment le reporter à la main. Sans `REPORTER`, rien ne change.
  - Application arrêtée, données encore en place, après `VERIFIER` (le report change l'instantané) :
    les données en service sont copiées dans `~/backups/<nom>/report-<horodatage>/`, en 700, puis
    `<REPORTER…> /actuel /donnees` tourne dans un conteneur jetable de l'image déployée, cette copie
    sur `/actuel` et la copie de l'instantané sur `/donnees`. Les données en service ne sont jamais
    montées.
  - **La copie jetable contient des données personnelles.** Elle n'est jamais dans `/tmp`, ni à un
    endroit qu'une sauvegarde ou un envoi ramasserait, et elle est retirée sur toutes les sorties ;
    celle qu'un arrêt brutal laisse, la sauvegarde de la nuit la retire, sous le même verrou, avec
    la copie de travail des données. Il faut, le temps du report, la place d'une copie de plus des
    données.
  - **Le contrat des sorties** : sur un code 0, la sortie standard est un seul objet JSON, le
    rapport, journalisé sur une ligne ; sur un échec, les deux sorties vont au journal. Le projet
    garantit qu'elles ne portent aucune donnée personnelle.
  - **Tout échec abandonne la restauration, rien n'a changé** : un code 64 (l'image déployée ne
    connaît pas la commande, après un retour par exemple), tout autre code, une sortie qui n'est
    pas un seul objet JSON, ou une copie de l'instantané qui n'a plus, après le report, la forme exigée de
    l'instantané (non vide, rien que des fichiers et des dossiers). `VERIFIER` ne tourne pas une
    seconde fois : le report change légitimement le contenu. L'app repart sur les données en
    service, et le message propose `--sans-report`, puis la section du runbook. C'est le côté sûr :
    un report impossible ne se saute jamais en silence. Sans `jq`, qui contrôle le rapport, une
    restauration où le report doit jouer est refusée avant tout effet.
  - **`--sans-report`** est le choix explicite de l'opérateur. Comme des données en service vides
    (un serveur reconstruit), il ne reporte rien, et la fin de la restauration le rappelle, avec la
    raison et la section, qu'elle réussisse ou échoue après la mise en place de l'instantané.
  - `tester-restauration.sh` ne le lance pas : il n'a pas de données en service à reporter.
- **Une archive vient d'un stockage tiers**, et n'importe qui peut en chiffrer une pour la clé
  publique : ses membres sont contrôlés avant toute extraction (un seul dossier, ni chemin absolu,
  ni `..`, rien que des fichiers et des dossiers).
- **La clé arrive par l'entrée standard** (`--cle /dev/stdin`, depuis le poste) et n'est jamais
  écrite sur le serveur. Une clé privée collée dans un argument, quel qu'il soit, est refusée sans
  être répétée (code 64).

### 7. Chaque trimestre, l'exercice sur le poste

Comme si le serveur était perdu : la dernière archive distante, déchiffrée sur le poste avec la clé
hors ligne passée par l'entrée standard, puis contrôlée par `VERIFIER`. Sa date et sa durée vont
au registre du dépôt `serveur`. **Un seul exercice pour tout le parc** est la cible ; tant qu'un
seul projet a des sauvegardes, c'est la procédure à la main de `docs/exploitation.md`, et l'outil
commun s'écrira au deuxième.

## Conséquences

- On accepte de perdre au plus une journée de données : le rythme des sauvegardes.
- Un `/donnees` vide, même légitimement, fait alerter la sauvegarde chaque nuit (M-0003).
- Une donnée supprimée survit jusqu'à 90 jours dans les archives distantes. Un projet qui a des
  données personnelles le dit dans sa notice, et décide si ses suppressions doivent être rejouées
  après une restauration : c'est à quoi sert `REPORTER` (§6).
- Le coût : deux minuteries, 30 jours d'instantanés sur le disque du serveur, un exercice par
  trimestre.
- **Difficile à changer** : la clé hors ligne, pour laquelle toutes les archives distantes sont
  chiffrées, et la forme de l'instantané (M-0003).

## Révision

Cet ADR doit être rouvert si :

- un deuxième projet a des sauvegardes : l'exercice trimestriel commun au parc s'outille ;
- l'instantané complet de chaque nuit devient trop gros ou trop long ;
- la garde du dossier de données refuse à tort : une application avec sauvegardes dont le dossier
  de données est légitimement vide en service ;
- la clé hors ligne est perdue ou compromise ;
- le stockage distant change.

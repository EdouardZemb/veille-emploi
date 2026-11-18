# Tes données — où elles vivent, comment les sauvegarder, comment les effacer

Cette base contient des données sensibles : **candidatures, prétentions
salariales, notes sur des employeurs, motifs d'écartement**. Un employeur
actuel qui les lirait apprendrait que tu cherches, où, et pour combien.

---

## Dans le conteneur : `/donnees`

Depuis le lot #11, la console tourne en conteneur (`docs/exploitation.md`). **Tout son état est
dans `/donnees`**, un dossier de l'hôte monté à l'uid 1000 ; la racine de l'image est en lecture
seule.

| Quoi | Chemin dans le conteneur |
|------|--------------------------|
| **La base** | `/donnees/veille.sqlite3` |
| Dossiers de candidature générés | `/donnees/dossiers/` |
| Le kit (CV, pièces) | `/donnees/kit/` |
| Clés VAPID (notifications push) | `/donnees/vapid.json`, née au démarrage si elle manque |

- **La base porte aussi les réglages**, dans la table `reglages` (une clé, une valeur, une date) :
  le seuil des notifications et la fréquence de collecte. La configuration (critères, sources,
  gabarits) n'est ni dans `/donnees` ni dans l'image : le conteneur la lit sur `/config`, monté en
  lecture seule, et la console ne la réécrit jamais. Sans `/config`, il sert l'exemple (le staging) ;
  en prod, il refuse de démarrer.
- **La connexion est dans la base.** Les sessions (leur empreinte SHA-256, jamais le jeton), les
  liens à usage unique (leur empreinte) et les passkeys (leurs clés publiques) y sont : la
  sauvegarde de la base les couvre. **Déconnecter** (**Plus › Réglages**, bloc **Appareils**)
  ferme une session ; la passkey d'un appareil perdu se retire sur le serveur, par
  `docker exec veille-emploi-app-1 veille passkeys --retirer <n°>` (`DEMARRAGE.md`, § 4).
- **Les secrets de la collecte ne sont pas dans `/donnees`** : le serveur les déchiffre à chaque
  déploiement (`deploiement/secrets/`) et les passe en variables d'environnement. Le mot de passe
  d'application Gmail y est donc en clair, dans l'environnement du conteneur : c'est inévitable,
  IMAP l'exige. Il est révocable seul depuis <https://myaccount.google.com/apppasswords>, sans
  toucher à ton compte.
- **La sauvegarde** est `veille instantane creer <dossier>` : un dossier à la forme de `/donnees`
  (base copiée par l'API de SQLite, console en marche, `dossiers/`, `kit/`, `vapid.json`) et un
  marqueur `instantane.json`, écrit en dernier. `veille instantane verifier <dossier>` rend 0 si
  l'instantané est sain, 2 sinon. Le serveur les lance chaque nuit (prod) et avant chaque
  déploiement ; la restauration passe par `restaurer.sh` (`docs/exploitation.md`).
- **La base ne sort du serveur que chiffrée**, dans la copie distante de la sauvegarde de la nuit
  (`docs/exploitation.md`, « Ce qui tourne ») ; aucun service tiers ne la lit.
- **Le staging ne tient que le jeu factice** de `factice/`, écrit à la main : aucune donnée réelle.

---

## Sur le poste, en mode local

Sans `VEILLE_EMPLOI_ENV`, une console du poste garde son état dans `donnees/` du clone, que git et
l'image ignorent : la base (`donnees/veille.sqlite3`), les dossiers générés (`donnees/dossiers/`)
et les clés des notifications (`donnees/vapid.json`, nées au démarrage). `VEILLE_DB`,
`VEILLE_DOSSIERS` et `VEILLE_VAPID` les mettent ailleurs. Ses secrets vivent dans le fichier que
désigne `VEILLE_ENV`, hors du dépôt. Aucune sauvegarde ne copie la base du poste : la recherche
réelle vit en prod.

---

## Effacer

### Une offre et sa trace

Écarter une offre dans la console la garde en base (c'est voulu : elle ne doit
jamais remonter, et son motif nourrit le pilotage). Pour l'effacer vraiment, sur
le serveur, dans le conteneur de la prod :

```bash
docker exec veille-emploi-app-1 python -c "
from veille import db
with db.connexion() as cx:
    cx.execute('DELETE FROM offres WHERE id = ?', (123,))
"
```

Les événements liés partent avec (`ON DELETE CASCADE`). Les sauvegardes la
gardent encore : 30 jours sur le serveur, jusqu'à 90 jours dans les archives
distantes (M-0005).

### Repartir de zéro, sur le poste

Arrête la console, puis efface `donnees/veille.sqlite3` et ses fichiers
`-wal` et `-shm` : la base renaît vide au démarrage suivant, et la
configuration n'y est pour rien. En prod, ne repars pas d'une base vide :
chaque nuit, la sauvegarde la copierait, et la rétention finirait par évincer
les bonnes (`docs/exploitation.md`, « Débloquer un déploiement »).

### Tout effacer, définitivement

- **En prod**, sur le serveur : « Tout arrêter », puis le retrait définitif
  qu'elle décrit, d'après la notice du dépôt `serveur` (`docs/exploitation.md`).
  Il retire les unités, les clones, les réseaux, les clés et les données ; les
  sauvegardes, locales et distantes (« Ce qui tourne »), se vérifient à part.
- **Sur le poste** : `donnees/` du clone, et le fichier que désigne
  `VEILLE_ENV`.

Pense aussi à révoquer le mot de passe d'application Gmail et à supprimer
l'application France Travail.

> Sur un SSD, `rm` ne garantit pas l'effacement physique. Si ça compte pour
> toi, chiffre le support plutôt que de compter sur la suppression.

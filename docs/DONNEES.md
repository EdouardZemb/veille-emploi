# Tes données — où elles vivent, comment les sauvegarder, comment les effacer

Cette base contient des données sensibles : **candidatures, prétentions
salariales, notes sur des employeurs, motifs d'écartement**. Un employeur
actuel qui les lirait apprendrait que tu cherches, où, et pour combien.

---

## Dans le conteneur : `/donnees`

Depuis le lot #11, la console peut tourner en conteneur (`docs/exploitation.md`). **Tout son état est
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
- **Les sessions, les liens et les passkeys** sont dans la base, comme ci-dessous.
- **Les secrets de la collecte ne sont pas dans `/donnees`** : le serveur les déchiffre à chaque
  déploiement (`deploiement/secrets/`) et les passe en variables d'environnement.
- **La sauvegarde** est `veille instantane creer <dossier>` : un dossier à la forme de `/donnees`
  (base copiée par l'API de SQLite, console en marche, `dossiers/`, `kit/`, `vapid.json`) et un
  marqueur `instantane.json`, écrit en dernier. `veille instantane verifier <dossier>` rend 0 si
  l'instantané est sain, 2 sinon. Le serveur les lance chaque nuit (prod) et avant chaque
  déploiement ; la restauration passe par `restaurer.sh` (`docs/exploitation.md`).
- **Le staging ne tient que le jeu factice** de `factice/`, écrit à la main : aucune donnée réelle.

Les sections suivantes décrivent la console du tailnet, qui tourne jusqu'à la fin du lot #12,
depuis son clone sur le serveur, `<le clone>`. Les chemins de l'instance réelle sont dans
le `docs/DONNEES.md` du dépôt de données.

---

## Où c'est

| Quoi | Chemin, dans le clone |
|------|-----------------------|
| **La base** | `donnees/veille.sqlite3` |
| Dossiers de candidature générés | `donnees/dossiers/` |
| Identifiants France Travail et IMAP | `config/.env` |
| Clés VAPID (notifications push) | `config/vapid.json` |
| La configuration (critères, sources, gabarits) | le dossier que désigne `VEILLE_CONFIG` |

**La connexion est dans la base.** Les sessions (leur empreinte SHA-256, jamais
le jeton), les liens à usage unique (leur empreinte) et les passkeys (leurs
clés publiques) y sont : la sauvegarde de la base les couvre, et aucun fichier
de `config/` ne sert plus à se connecter. **Déconnecter** (**Plus › Réglages**,
bloc **Appareils**) ferme une session ; la passkey d'un appareil perdu se retire
sur le serveur, par `veille passkeys --retirer <n°>` (`DEMARRAGE.md`, §4).

Le dossier `donnees/` est en **700**, les deux fichiers de `config/` en
**600** : lisibles par toi seul, y compris vis-à-vis des autres comptes de la
machine.

**Rien ne sort du serveur.** La base n'est répliquée nulle part, aucun service
tiers ne la lit. Les seules sorties réseau sont : les appels à l'API France
Travail, la lecture IMAP de ton libellé Gmail, la résolution des liens de
suivi, et l'envoi des notifications push vers le service de Google.

> ⚠️ Ton mot de passe d'application Gmail est en clair dans `config/.env` —
> c'est inévitable, IMAP l'exige. Il est révocable seul depuis
> <https://myaccount.google.com/apppasswords> sans toucher à ton compte.

---

## Sauvegarder

SQLite est en mode WAL : **ne copie pas le fichier à chaud**, tu obtiendrais
une base incohérente. Utilise la commande de sauvegarde intégrée :

```bash
cd <le clone>
./.venv/bin/python -c "
import sqlite3, pathlib, datetime
cible = pathlib.Path.home()/f'sauvegardes/veille-{datetime.date.today()}.sqlite3'
cible.parent.mkdir(exist_ok=True)
src = sqlite3.connect('donnees/veille.sqlite3')
dst = sqlite3.connect(cible)
src.backup(dst); dst.close(); src.close()
print('sauvegarde :', cible)
"
```

Une sauvegarde hebdomadaire, en unité utilisateur :

```bash
cat > ~/.config/systemd/user/veille-sauvegarde.service <<'EOF'
[Unit]
Description=Sauvegarde de la base de veille emploi
[Service]
Type=oneshot
WorkingDirectory=<le clone>
ExecStart=<le clone>/.venv/bin/python -c "import sqlite3,pathlib,datetime; c=pathlib.Path.home()/f'sauvegardes/veille-{datetime.date.today()}.sqlite3'; c.parent.mkdir(exist_ok=True); s=sqlite3.connect('donnees/veille.sqlite3'); d=sqlite3.connect(c); s.backup(d); d.close(); s.close()"
EOF

cat > ~/.config/systemd/user/veille-sauvegarde.timer <<'EOF'
[Unit]
Description=Sauvegarde hebdomadaire de la veille emploi
[Timer]
OnCalendar=Sun 03:00
Persistent=true
[Install]
WantedBy=timers.target
EOF

systemctl --user daemon-reload && systemctl --user enable --now veille-sauvegarde.timer
```

N'oublie pas `config/.env` — il n'est pas dans la base, et sans lui une
restauration te laisse sans collecte.

---

## Effacer

### Une offre et sa trace

Écarter une offre dans la console la garde en base (c'est voulu : elle ne doit
jamais remonter, et son motif nourrit le pilotage). Pour l'effacer vraiment :

```bash
cd <le clone>
./.venv/bin/python -c "
import sys; sys.path.insert(0,'src')
from veille import db
with db.connexion() as cx:
    cx.execute('DELETE FROM offres WHERE id = ?', (123,))
"
```

Les événements liés partent avec (`ON DELETE CASCADE`).

### Repartir de zéro, en gardant la configuration

```bash
cd <le clone>
systemctl --user stop veille-web
rm -f donnees/veille.sqlite3 donnees/veille.sqlite3-wal donnees/veille.sqlite3-shm
./.venv/bin/veille init
systemctl --user start veille-web
```

### Tout effacer, définitivement

```bash
systemctl --user disable --now veille-web.service veille-collecte.timer
rm -rf <le clone> ~/sauvegardes
rm -f ~/.config/systemd/user/veille-*.{service,timer}
rm -f ~/.config/systemd/user/default.target.wants/veille-web.service
rm -f ~/.config/systemd/user/timers.target.wants/veille-collecte.timer
systemctl --user daemon-reload
sudo tailscale serve --https=<le port du tailnet> off
```

Pense aussi à révoquer le mot de passe d'application Gmail et à supprimer
l'application France Travail.

> Sur un SSD, `rm` ne garantit pas l'effacement physique. Si ça compte pour
> toi, chiffre le support plutôt que de compter sur la suppression.

# ADR-0001 — Connexion : des passkeys et des liens à usage unique, alignés sur ancrage

- **Statut** : accepté le 2026-10-27
- **Contexte amont** : issue #10 ; ADR-0002 d'`ancrage` (connexion et invitations) ; étape « La
  console sur l'adresse publique » (milestone des issues #10, #11 et #12)

## Contexte

La console se protège aujourd'hui par un mot de passe unique (`src/veille/auth.py`, lu dans
`config/auth.json`). Ce mot de passe a été pensé contre les autres appareils du tailnet : un
intrus y est improbable, et la console n'est vue que de là. Rien n'y limite les essais.

Cela change avec l'étape « La console sur l'adresse publique » : la console va être exposée sur
Internet. Un mot de passe sans limite d'essais n'y tient pas. Edouard est le seul utilisateur, et
il se sert de la console surtout au téléphone, en application web installée.

## Options

- **A. Garder le mot de passe et limiter les essais.** Le moins de changement. Mais le mot de
  passe reste devinable et se saisit mal au téléphone, et il faudrait en plus un compteur par
  client, que l'architecture ne permet pas (voir la décision).
- **B. Cloudflare Access.** Il envoie lui-même les codes. Mais, d'après creche-planner, une
  session expirée casse l'application installée (le service worker reçoit une redirection), et
  sa configuration vit hors du dépôt.
- **C. Les passkeys d'`ancrage`.** Edouard déverrouille son téléphone, et c'est tout. Le serveur
  ne garde que des clés publiques. Le projet frère a déjà tranché, écrit et testé ce choix
  (ADR-0002) : le suivre évite de décider deux fois, et donne deux cas réels à comparer.

## Décision

**Option C**, avec des liens à usage unique comme seul canal de secours : mêmes passkeys, mêmes
sessions de 180 jours, mêmes liens de 24 heures qu'`ancrage`. Pas de mot de passe.

Les écarts à `ancrage`, chacun avec sa raison :

- **Un seul utilisateur.** Ni invitation, ni nom affiché : il n'y a personne à inviter, et la
  console connaît Edouard d'office (`user_name="edouard"`).
- **Le premier lien vient de `veille lien`, lancé sur le serveur.** Il n'y a pas de compte à
  créer par invitation. Celui qui a la main sur le serveur est le propriétaire : c'est la même
  preuve que `ancrage` demande pour son premier compte. Ensuite, un appareil connecté peut créer
  le lien d'un autre appareil.
- **Un compteur de débit global, sur les quatre routes anonymes.** Les `POST` sur
  `/api/auth/lien/options`, `/api/auth/lien`, `/api/auth/connexion/options` et
  `/api/auth/connexion` partagent un seul compteur, 20 requêtes par minute. Derrière
  `tailscale serve`, et demain derrière le tunnel Cloudflare, toute requête arrive de
  `127.0.0.1` : un compteur par client ne compterait rien. Les routes qui demandent une session
  ne comptent pas. Le coût réel : quiconque joint la console peut bloquer la connexion par
  passkey et l'ajout d'un appareil, aussi longtemps qu'il entretient le compteur. Les sessions
  ouvertes restent utilisables, et elles durent 180 jours : c'est ce qui rend ce coût
  supportable sur le tailnet, pas sur Internet (voir la révision).
- **L'origine vient de `VEILLE_URL`.** L'origine attendue et l'identifiant de la partie de
  confiance (le nom d'hôte) se lisent dans cette variable, qui existe déjà. Absente ou
  illisible, les passkeys sont indisponibles (503 `origine_inconnue`), jamais remplacées par un
  repli silencieux : un contrôle qui n'a pas pu tourner n'est pas un feu vert.
- **On ne retire pas une passkey depuis la console : on la retire sur le serveur.** La console
  déconnecte des sessions, et montre les passkeys en lecture seule (appareil, création, dernier
  usage), pour qu'une passkey inconnue se remarque. Retirer sa seule passkey depuis l'écran
  qu'elle protège enfermerait Edouard dehors. Mais la déconnexion d'une session **ne révoque
  pas** la passkey de l'appareil : qui tient l'appareil en rouvre une. La révocation se fait sur
  le serveur, par `veille passkeys --retirer <id>`, qui ferme aussi **toutes** les sessions :
  celui qui a ajouté sa passkey avec un cookie volé a aussi une session, et rien ne dit
  laquelle. Si c'était la dernière passkey, `veille lien` fait rentrer.

## Conséquences

- **Une dépendance de plus** : `webauthn`, en version majeure épinglée.
- **Trois tables dans la base**, sauvegardées avec elle : les passkeys, les sessions, les liens.
  Elles ne gardent que des empreintes de jetons et des clés publiques.
- **`config/auth.json` disparaît**, et avec lui la variable `VEILLE_AUTH`. Pendant la bascule
  du serveur, il ne sert plus qu'à revenir à l'ancienne version (`docs/DEMARRAGE.md`, §4).
- **Des passkeys distinctes par nom d'hôte** : une passkey se lie à l'identifiant de la partie de
  confiance. Il faut donc en créer une à chaque bascule (tailnet, staging, production).
- **Un navigateur dans la CI** : le parcours complet tourne dans Chromium, avec un
  authentificateur WebAuthn virtuel.
- **Difficile à changer** : peu de chose. L'identité ne dépend pas de la méthode de connexion :
  ajouter un mot de passe ou des codes par e-mail serait un ajout, pas une refonte.

## Révision

À rouvrir dans ces cas :

- **avant l'exposition sur Internet** (étape « La console sur l'adresse publique ») : compter par
  client derrière le tunnel, d'après l'en-tête `CF-Connecting-IP`, uvicorn lancé avec
  `--proxy-headers`. Sur Internet, le compteur global laisserait n'importe qui bloquer la
  connexion ;
- le compteur global bloque Edouard, ou retarde un appareil nouveau plus d'une fois ;
- un second utilisateur arrive : les invitations et le nom affiché reviendraient alors ;
- à la clôture de l'étape « La console sur l'adresse publique », proposer à `modele-projet` un ADR
  commun, tiré d'`ancrage` et de ce projet : deux cas réels.

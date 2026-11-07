# Limites du dispositif — à ne pas faire dériver

Ce document existe pour que les règles ci-dessous survivent aux sessions
suivantes. Elles ne sont pas des préférences de style : ce sont des garde-fous.

---

## 1. Aucun parcours automatisé de LinkedIn

**Interdiction ferme.** Aucun script de ce projet ne doit parcourir LinkedIn,
ni un site qui l'interdit dans ses conditions d'utilisation.

**Pourquoi** : le compte LinkedIn d'Édouard est l'infrastructure de sa
recherche d'emploi. Le faire restreindre serait un dommage sans commune mesure
avec le gain. Cette règle tient **même si un scraper serait plus simple à
écrire**.

**Ce qui est fait à la place** : LinkedIn envoie lui-même les annonces par
alerte mail, sur recherche enregistrée. C'est le canal que le site a prévu. On
l'ingère. Aucune condition d'utilisation n'est franchie, aucun compte n'est
exposé.

### La seule requête réseau vers un site d'annonces

`collectors/liens.py` peut émettre une requête HTTP vers un lien **que le site
a lui-même envoyé dans un mail**, pour résoudre le redirecteur de suivi et
retrouver l'URL réelle — sans quoi la déduplication ne marche pas.

C'est une requête par lien reçu, au rythme des mails. Ce n'est pas du parcours
de catalogue : aucune page de résultats n'est explorée, aucune pagination
suivie. Et deux stratégies hors ligne sont tentées avant (extraction du
paramètre, reconstruction par identifiant) : le réseau n'est le recours que
quand elles échouent.

---

## 1 bis. La lecture du texte complet d'une annonce

Le scoring ne voit souvent qu'un intitulé et un extrait : les critères
éliminatoires — astreinte, week-end, soirée, allemand exigé — sont dans le corps
de l'annonce. `enrichissement.py` permet d'aller le chercher, **sous
conditions strictes**.

### Ce qui est interdit, et qui le reste

Ouvrir les annonces **en lot**, à chaque collecte, sans lui, depuis une tâche
planifiée. C'est du moissonnage. **Rien dans `veille-collecte.timer` ne doit
appeler `enrichissement.recuperer()`.**

### Les cinq règles

1. **Déclenchement humain uniquement.** Un clic sur sa fiche d'offre. Jamais un
   minuteur, jamais une boucle, jamais un lot.
2. **Liste blanche ET `robots.txt`**, les deux, pas l'un ou l'autre. La liste
   blanche dit ce qu'on a étudié ; le `robots.txt`, revérifié en direct et mis
   en cache 24 h, dit ce que le site autorise **aujourd'hui**. Une politique
   change.
3. **Une page à la fois**, 20 secondes minimum entre deux, plafond de 30 pages
   par jour. S'il marque dix offres d'affilée, il attend.
4. **`robots.txt` illisible = abstention.** Dans le doute, on ne va pas voir.
5. **Jamais de contournement.** Pas de navigateur sans tête, pas de cookie de
   session, pas d'en-tête falsifié pour passer pour un humain. Si un site
   refuse, on le respecte et on propose le collage manuel.

### Les verdicts, vérifiés le 28/09/2026

| Source | `User-agent: *` | Décision |
|---|---|---|
| **LinkedIn** | `Disallow: /` | ⛔ jamais — la plupart des offres au-dessus du seuil en viennent, et c'est le compte dont dépend sa recherche |
| **Indeed** | `Disallow: /viewjob` | ⛔ jamais |
| jobs.ch, jobup.ch, arbeitnow, apec.fr | rien d'applicable | ✅ autorisé |

### La voie principale reste le collage manuel

Il ouvre l'annonce dans **son** navigateur, où il est connecté, sélectionne,
colle. **Couverture totale, LinkedIn compris, zéro requête automatisée.** C'est
lui qui lit, le programme ne fait que scorer.

Cette voie respecte la règle **par construction** et non par précaution, ce qui
vaut mieux. Si un arbitrage se présente un jour, c'est elle qu'il faut
privilégier, jamais la récupération automatique.

---

## 2. Le navigateur n'agit jamais sans Édouard

Le rôle du navigateur est d'**accompagner une candidature précise, avec lui
présent** :

- consulter une annonce complète que la collecte n'a pas su rapatrier
- remplir un formulaire de candidature avec lui
- vérifier ponctuellement une page carrière

**Jamais de tâche planifiée qui navigue sans lui.** Aucune unité systemd,
aucun cron, aucun déclencheur de ce projet ne doit piloter un navigateur.

Les seules tâches automatiques du dispositif sont `veille-collecte.timer`
(API, RSS, IMAP) et `veille-web.service` (la console). Ni l'une ni l'autre
n'ouvre de navigateur.

---

## 3. Sur l'adresse publique, les passkeys seules gardent la console

La console contient sa recherche d'emploi : candidatures, prétentions
salariales, notes sur des employeurs.

**La console en conteneur est servie sur l'adresse publique**, par le tunnel du
serveur (ADR-0002), en prod comme en staging. Seules les passkeys la gardent
(ADR-0001) : aucun réseau ne trie qui l'atteint (§ 4). Ce qui a précédé
l'ouverture, la limite de débit, le cookie `__Host-` et la politique de sécurité
du contenu, est dans l'ADR-0002, § 6.

- Dans le conteneur, `uvicorn` écoute sur toutes ses interfaces, au port 8460 :
  le tunnel l'atteint par son réseau. L'hôte ne publie ce port que sur
  `127.0.0.1`, pour la santé locale (`deploiement/compose.yml`).

**La console sans conteneur, jusqu'à son retrait** (ADR-0002, § 10), reste sur
le tailnet seul :

- `uvicorn` écoute **uniquement sur `127.0.0.1`**. Ne change pas ce `--host`.
- L'accès passe par **`tailscale serve`**, qui publie sur le tailnet seul.
- **`tailscale funnel` est proscrit** : il publierait sur Internet.
  `scripts/tailnet/exposer-tailnet.sh` du dépôt de données refuse de démarrer s'il en détecte un,
  et revérifie après coup.
- La console écoute sur le tailnet sur un port choisi pour ne gêner aucun autre
  service de la machine (celui de l'instance réelle, et pourquoi :
  `docs/LIMITES.md` du dépôt de données). N'y touche pas.

---

## 4. Aucun réseau n'est une authentification

L'adresse publique est ouverte à tout Internet. Le tailnet a d'autres appareils,
et d'autres personnes peuvent le rejoindre pour d'autres projets. **La connexion
de la console n'est pas décorative** : c'est ce qui empêche que sa recherche
d'emploi soit lisible par quiconque atteint son adresse, publique ou du tailnet.
Ne retire `Depends(auth.exiger_session)` d'aucune route, et une route nouvelle
qui lit ou écrit des données la porte aussi.

---

## 5. Aucune prose inventée dans les candidatures

`dossier.py` ne rédige rien. Il prend un gabarit **écrit par Édouard**,
remplace des marqueurs par les éléments de l'offre, et copie les pièces
jointes. Un marqueur non résolu reste **visible** dans le fichier généré, sous
la forme `[[nom - A COMPLETER]]`, pour qu'il le voie à la relecture.

Ne fais pas générer de lettre de motivation par un modèle de langage sans qu'il
l'ait demandé explicitement.

---

## 6. Ne pas toucher au reste du serveur

Le serveur héberge d'autres services (ceux de l'instance réelle :
`docs/LIMITES.md` du dépôt de données).

Ce projet vit **entièrement** dans son clone, avec son propre
venv et des unités systemd **utilisateur**. Aucun paquet système, aucun service
système, jamais `pip` en root.

---

## Ce que la vérification « encore en ligne ? » ne peut pas couvrir

### Les annonces de LinkedIn et d'Indeed ne seront jamais vérifiées automatiquement

LinkedIn déclare `Disallow: /`, Indeed interdit `/viewjob`. **Aucune requête ne
part vers ces domaines**, jamais — c'est une règle par construction, pas une
précaution. Conséquence directe : pour ces annonces, la console **ne peut rien
prouver**, donc elle **n'archive rien**.

Ce n'est pas un défaut qu'on corrigera : c'est le prix du compte LinkedIn
d'Édouard, qui est l'infrastructure de sa recherche.

Ce qui est proposé à la place, dans la fiche de l'offre :

- l'état est écrit noir sur blanc — *« non vérifiable »*, avec la raison ;
- un lien pour ouvrir l'annonce lui-même ;
- un bouton **« Elle n'y est plus → archiver »** qui enregistre **son constat**.
  Le motif d'archive dit alors explicitement *« constaté retirée par Édouard »*,
  pour qu'on ne confonde jamais sa décision avec celle du moteur.

### Ce que la sonde ne sait pas distinguer

| Situation | Verdict rendu | Pourquoi on n'en fait pas plus |
|---|---|---|
| Site en panne, 429, 503, coupure réseau | `injoignable` | ne fait ni avancer ni reculer le compteur |
| Page rendue en JavaScript (arrive vide) | `injoignable` | on ne sait pas lire, donc on ne conclut pas |
| Redirection vers l'accueil | `indice_retrait` | beaucoup de sites redirigent aussi pour d'autres raisons — trois confirmations exigées, pas deux |
| Annonce republiée sous une nouvelle URL | non détecté ici | la déduplication par empreinte titre+employeur la rattrape à la collecte |
| Annonce toujours en ligne mais déjà pourvue | `vivante` | rien sur la page ne le dit |

### L'asymétrie assumée

Garder une annonce morte coûte un clic. Archiver une annonce vivante la fait
disparaître de sa vue sans qu'il sache pourquoi — surtout quand les alertes
mail sont **le flux principal**. Toutes les règles penchent donc du même côté :

- **deux** preuves franches (404, 410, page d'expiration) espacées de 20 h, ou
  **trois** indices ;
- une page vivante **remet le compteur à zéro** ;
- une offre triée à la main ou avec un dossier généré n'est **jamais** archivée,
  seulement signalée ;
- « Remettre dans le flux » est **définitif** : la vérification ne réarchivera
  jamais ce qu'il vient de ressortir ;
- **l'archive ne supprime rien** — score, explication, notes et historique sont
  conservés.

---

## Une pièce du kit n'est copiée sur le serveur que prête à partir

Copier une pièce dans le kit, c'est la rendre joignable automatiquement à chaque
candidature : le seul chemin par lequel son texte pourrait atteindre un
recruteur. Un brouillon — une note de rédaction restée visible, des marqueurs
`[[…]]` non remplis — reste donc sur le PC jusqu'à ce qu'il soit fini, et le
contrôle se rejoue avant chaque copie. Le cas qui a fixé cette règle est dans
le `docs/LIMITES.md` du dépôt de données.

---

## Deux régimes d'archivage, et pourquoi ils diffèrent

**Remarque d'Édouard, techniquement juste :** *« les annonces où la vérification
donne un 410, tu peux les archiver sans attendre. Peut-être pas les 404, parce
que ça peut être une autre raison, mais les 410, oui. »*

La distinction est celle du protocole lui-même :

| | **410 Gone** | **404 Not Found** |
|---|---|---|
| Ce que dit le serveur | la ressource **a existé** et elle est **définitivement supprimée** | la ressource est introuvable, **sans dire pourquoi** |
| Nature | une **déclaration** | un **constat** |
| Causes possibles | une seule : l'annonce a été retirée | route cassée, ressource déplacée, erreur passagère, blocage |

D'où deux régimes :

### Régime immédiat — 410 seulement

Une seule vérification suffit. Motif enregistré :

> *Retirée — le site déclare l'annonce définitivement supprimée (HTTP 410), le JJ/MM/AAAA*

### Régime des deux passes — tout le reste

404, page d'expiration en 200, redirection vers l'accueil, et tout autre code.
**Deux preuves espacées d'au moins 20 h**, trois pour un simple indice. Motif :

> *Constatée absente à N vérifications espacées, la dernière le JJ/MM/AAAA : …*

Les deux motifs sont différents **exprès** : l'archive doit dire non seulement
pourquoi une offre y est, mais **avec quel degré de certitude**.

### Le garde-fou : un 410 peut mentir

Rarement, mais ça existe — pare-feu applicatif, serveur mal configuré, réponse
générique sur tout un domaine. Si un domaine **entier** bascule en 410 d'un
coup, c'est plus probablement une panne qu'une purge simultanée.

La règle : **un 410 n'est cru immédiatement que si le domaine a rendu au moins
une annonce vivante dans les 7 derniers jours.** Sinon on retombe sur les deux
passes, en gardant la preuve. Un domaine qui sert encore des annonces vivantes
dit la vérité quand il en déclare une supprimée ; un domaine devenu muet, non.

C'est ce qui distingue le cas réel — Arbeitnow rendait, dans la même passe,
plus d'une centaine de 410 **et** autant de pages vivantes — d'une panne
générale.

### Ce qui ne change pas

- **Les protections sont absolues.** Une offre marquée intéressante, avec un
  dossier généré ou une candidature n'est **jamais** archivée automatiquement,
  410 ou pas. Elle est signalée, elle reste.
- **La réversibilité est intacte.** « Remettre dans le flux » fonctionne à
  l'identique, et pose `archive_protegee` : le système ne réarchivera jamais ce
  qu'il vient de ressortir.
- **429, 503, 500, 403, délai dépassé, coupure réseau** ne comptent toujours
  pour rien : ni preuve, ni remise à zéro.
- **L'archive ne supprime rien.**

---

## L'affinement : pourquoi se reconnecter ne suffit pas

Le fichier d'identifiants de Claude Code (`~/.claude/.credentials.json`) peut
exister, être lu, annoncer un abonnement — et ne contenir **aucun jeton** : une
session interactive rafraîchit visiblement ses jetons en mémoire et les perd en
se fermant, sans jamais réécrire le fichier. D'où le piège : `claude -p` répond
dans son terminal et échoue partout ailleurs. Le relevé qui l'a montré est dans
le `docs/LIMITES.md` du dépôt de données.

**Ce qui marche** : `claude setup-token`, puis le jeton dans `config/.env` sous
`CLAUDE_CODE_OAUTH_TOKEN`, droits `600` — la convention déjà appliquée au mot
de passe Gmail et aux identifiants France Travail. Le service systemd charge ce
fichier via `EnvironmentFile`, donc il le verra sans autre réglage.

### Deux conséquences qu'il faut connaître

**Un conteneur qui monte ce fichier est dans le même cas.** Monter
`~/.claude/.credentials.json` en lecture seule *et* laisser
`ANTHROPIC_API_KEY` vide ne donne aucun moyen de s'authentifier. Le montage
doit être remplacé par le jeton, sinon il continue de donner l'illusion d'une
configuration valide.

**Le `PATH` d'un service systemd ne contient pas `~/.local/bin`.** Mesure :

```
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin
```

Or le binaire `claude`, que le SDK lance, vit précisément là. Corrigé : le
sous-processus Node reçoit un `PATH` complété. Ce n'était pas la cause de
l'échec actuel — vérifié, l'erreur est identique avec et sans — mais ça
l'aurait été dès le jeton posé.

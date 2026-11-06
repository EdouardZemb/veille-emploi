# La méthode des projets nés du modèle

Ce fichier est **géré par le modèle** : il est réécrit par chaque `copier update`, et on ne le
modifie pas dans le projet. Un défaut se corrige dans `modele-projet`, pour tous les projets.

## Le cycle d'un lot

1. Une issue, avec une mini-spec : objectif, critères d'acceptation, hors périmètre. Le formulaire
   « Lot » la pose. Une milestone par étape.
2. Une PR de plan, qui ajoute le plan dans `.claude/plans/`.
3. Une ou plusieurs PR d'implémentation.
4. Une PR de revue finale.
5. Une PR de clôture : elle **supprime le plan** et reporte dans `CLAUDE.md` ou dans un ADR ce qui
   doit survivre.
6. L'étiquette `vX.Y.Z`, **avec l'accord d'Edouard**.

## Les outils

Les plans s'écrivent avec la compétence *superpowers* `writing-plans` et s'exécutent avec
`subagent-driven-development`.

Ces compétences **ne sont pas déclarées dans `.claude/settings.json`**. D'après la documentation de
Claude Code, un plugin déclaré par le projet ne s'installe ni dans une session à distance ni sur un
autre poste, et la déclaration doublerait l'installation du poste.

**Si *superpowers* manque** (c'est le cas dans une session à distance), la méthode ne change pas, seul
l'outillage disparaît :

- le plan s'écrit à la main dans `.claude/plans/`, avec les mêmes sections qu'un plan ordinaire :
  objectif, tâches, vérification de chaque tâche ;
- une seule tâche à la fois ;
- le test d'abord : il est écrit, il échoue, puis le code le fait passer ;
- une revue avant la fusion, par une autre session ou par Edouard.

## Les worktrees

Un sujet = un worktree, dans `<nom>.worktrees\<sujet>`, jamais à côté du dépôt.

## « Fini »

Tests verts, CI verte, `CLAUDE.md` et ADR à jour, déployé, vérifié là où l'application sert (sur un
téléphone Android pour une application mobile).

## Les commits

Conventional Commits, en français, avec un en-tête de 100 caractères au plus. Fusion par squash.
`git add` par chemins explicites, jamais `git add .` ni `git add -A`.

## Les questions groupées

Quand une session a plusieurs questions, elle les pose **en un seul bloc**, numérotées, chacune avec
sa réponse par défaut. « OK pour les défauts, sauf n » suffit comme réponse.

## Les invariants communs

Ils s'ajoutent à ceux du projet.

1. Aucun secret ne passe par la conversation. Les étapes 👤 le disent.
2. Aucune donnée personnelle réelle dans le dépôt, les tests ou le staging. Le jeu de données
   factice est **écrit**, pas dérivé de données réelles (M-0001).
3. Personne n'écrit sur le serveur après son amorçage : tout y arrive par git. Une session y lit,
   elle n'y écrit jamais. Seule exception : les gestes 👤 écrits à l'avance, qu'Edouard lance
   lui-même. Ce sont les gestes 👤 de `docs/exploitation.md` (la mise en service, et les secours :
   restaurer, revenir en arrière, arrêter), et ceux qu'un plan de lot écrit pour une migration.
4. Cible `serveur` : une migration, `compose.yml` et les `env/*.env` doivent laisser fonctionner
   l'image précédente. On ajoute avant d'enlever, et une variable nouvelle ne devient obligatoire
   qu'une version plus tard.
5. Un fichier géré par le modèle ne se modifie pas dans le projet : on corrige le modèle.

## Les garde-fous

Ils sont tous écrits en Python, le seul langage présent à la fois sur le poste, en CI et dans les
sessions à distance.

| Où | Quoi |
|---|---|
| hook git `pre-commit` | confidentialité du contenu indexé, fichiers UTF-16 compris ; un autre binaire est signalé « non examiné ». La porte suit la nature du dépôt : elle refuse tout constat dans un dépôt de code ; dans un dépôt de données, elle avertit sur ce qui identifie et refuse toujours les secrets (voir plus bas), au hook comme en CI. Dans un dépôt de code, elle refuse aussi les fichiers de l'instance, lus sur leur chemin, et toute clé publique `age` (voir plus bas). Au commit d'un alignement ou d'une mise à jour (celui qui modifie `.copier-answers.yml`), refus d'un fichier du modèle, ou d'un secret chiffré que la chaîne lit (en cible `donnees`, sauf `cible_code: aucune`, `secrets/*.env.enc` ; en cible `serveur` à un dépôt, de nature `donnees`, `deploiement/secrets/*.env.enc`), que le `.gitignore` du projet masque. Le remède n'admet que ce que la porte examine, toujours par des lignes ancrées : un dossier du modèle exclu se lève par `!/<dossier>/` ; un dossier mixte, où un fichier local peut vivre à côté d'un fichier examiné, se lève, en exclut le contenu, puis n'admet que ce qu'elle y examine (`!/cles/`, `/cles/*` puis `!/cles/*.pub`), et un ancêtre exclu, de même, suivi des lignes de ses dossiers ; sous un `.gitignore` imbriqué, ces lignes partent de son dossier. Ce que la porte n'examine pas reste masqué, sans refus : dans un dossier mixte, un secret en clair, une clé privée ou un fichier local ; sous un ancêtre levé, un semé du projet (`docs/cadrage.md` sous `docs/`). Sous un dossier du modèle, tout fichier est du modèle, sauf un dossier de secrets ou de clés imbriqué, ou un cache Python : un autre fichier local posé là, même un `.env`, est refusé comme fichier du modèle |
| hook git `commit-msg` | format Conventional Commits, confidentialité du message |
| hook git `pre-push` | refus d'envoyer sur la branche principale |
| hook Claude `PreToolUse` (outils `Bash`, `PowerShell`, `Monitor`, et tout outil MCP qui porte une commande) | bloque `git push` vers la branche principale, tout force-push vers elle, `--no-verify`, toute modification de `core.hooksPath` sauf la réparation `git config core.hooksPath .githooks` (variables `GIT_CONFIG_*` comprises), `gh pr merge` tant que les contrôles ne sont pas tous verts (et toute fusion en mode `edouard`), `gh pr merge --admin`, l'envoi d'une étiquette (`git push --tags`, `--follow-tags`, un refspec `refs/tags/…`, `v1.2.3` ou `donnees-…`) et toute écriture de publication (`gh release` hors `view`, `list`, `download` ; l'API `…/releases`), les alias et extensions de `gh`, ce qui affiche le jeton de `gh` ou les identifiants de git (`gh auth token`, `gh auth status --show-token`, `gh auth git-credential`, `git credential fill`, `git credential-manager get`), et l'effacement, le déplacement ou le renommage de `.githooks` et de `scripts/modele` (`rm`, `mv`, `Remove-Item`, `git rm`…). Il lit aussi les substitutions `$(…)`, même entre guillemets, les blocs PowerShell (`try { … }`, `& { … }`, `% { … }`) et ses affectations (`$x = …`), le texte d'une here-string (`bash <<< '…'`) passée à un interprète, et les enveloppes (`timeout`, `nice -n`, `env -C`, `env -S`, `exec -a`, `Start-Process`, `Start-Process -WorkingDirectory`, `Invoke-Expression`…). Après un retour de dossier qu'il ne suit pas (`cd -`, `cd ~`, `popd`, `Pop-Location`), la branche courante est illisible : un `git push` doit alors nommer sa branche |
| hook Claude `SessionStart` (au démarrage et à la reprise) | affiche ce qui est rouge sur GitHub : les exécutions de la branche principale, les PR ouvertes et les workflows désactivés. Il ne bloque jamais. Ce que n'importe qui écrit depuis un fork n'entre pas dans le contexte de Claude : les exécutions de PR (`pull_request…`) sont écartées, et une PR ou un workflow venus d'ailleurs que le dépôt s'affichent sans le texte qu'ils portent. Une PR d'un fork paraît ainsi sans titre ni nom de contrôle, un workflow absent de la copie, sans son nom |
| CI de base | gitleaks examine les commits de chaque PR et de chaque envoi, et tout l'historique chaque semaine et à la demande (`modele-historique.yml`) ; la porte relit aussi l'historique d'un dépôt de code chaque semaine (`modele-historique.yml`), à côté de gitleaks, et refuse tout constat absent de `.github/constats-acceptes.txt` ; confidentialité du diff, des messages de commit et du texte de la PR ; format des commits ; le garde de Claude **et les signaux** toujours branchés dans `.claude/settings.json` ; actions épinglées par SHA |
| Dependabot | chaque lundi, les versions des actions épinglées (`.github/dependabot.yml`), après trois jours de recul |
| règle de protection GitHub | tout commit qui arrive sur la branche principale est la tête d'une PR dont les contrôles requis sont verts ; un envoi direct de cette tête est accepté et marque la PR fusionnée, sans squash. Côté agent, c'est le refus de pousser vers la branche principale par le garde qui ferme ce chemin. Ni force-push ni suppression de la branche principale. Posée sur les dépôts publics |

**Qui fusionne : la réponse `fusion`.** Deux modes, choisis à la création du projet et enregistrés
dans `.copier-answers.yml` :

- `session` : la session fusionne sa PR une fois tous les contrôles verts ;
- `edouard` : la session ouvre la PR, attend que tout soit vert, le dit, et s'arrête. Le garde
  refuse toute fusion : `gh pr merge` (y compris `--auto` et `--admin`), l'API (`…/merge`) et les
  mutations GraphQL de fusion. Le refus dit `mode fusion : edouard`.

Le mode lui-même se lit sur GitHub, par l'API (`gh api`) : le `.copier-answers.yml` de la branche
principale, et non celui de la copie locale ni `origin/<branche>`, qu'une session peut réécrire.
Tout ce qui est illisible (`gh` absent, erreur, délai dépassé, ligne absente) vaut `edouard`. Deux
entrées restent locales :

- le nom de la branche passée en `ref=` vient des réglages de la copie : `BRANCHE_PRINCIPALE`,
  dans `scripts/modele/reglages.py`, ou l'option `--branche` du garde ;
- l'option `--fusion session|edouard` du garde l'emporte sur la lecture, y compris posée sur la
  commande du hook dans un `settings.json` de la copie. C'est ce que passe le dépôt modèle, qui n'a
  pas de `.copier-answers.yml`.

**Le garde ne fusionne que dans le dépôt de la session.** Il ne lit le mode et les contrôles que du
dossier de la session (le `cwd` du hook). Il refuse donc toute fusion qui nomme un dépôt (`-R`,
`--repo`, `GH_REPO`, `GIT_DIR`, une adresse de PR), même celui de la session, ou qui suit, dans la
même commande, un changement de dossier (`cd`, `pushd`, `popd`, `chdir`, `Set-Location`,
`Push-Location`, `Pop-Location`, `env -C`, `Start-Process -WorkingDirectory`…), même vers le sien.
En mode `session`, le refus dit « fusion dans un autre dépôt : contrôles invérifiables ici », ou
« fusion après un changement de dossier » ; en mode `edouard`, toute fusion est refusée de toute
façon. On fusionne par `gh pr merge <n>`, depuis le clone, sans `cd`. Un plan qui touche plusieurs
dépôts dit, pour chaque PR, qui la fusionne : une session ouverte dans son dépôt, ou Edouard.

**Les étiquettes et les publications sont à Edouard**, dans les deux modes : une étiquette peut
mettre un projet en production. Les étiquettes de données `donnees-AAAA.MM.JJ.n` sont à Edouard,
comme les `vX.Y.Z` : elles mettent en production une configuration ou un contenu. La session les
prépare (`git tag` en local est permis), mais ne les envoie pas et n'écrit aucune publication.

**La PR qui apporte l'option `fusion` à un projet se fusionne à la main**, puisque la branche
principale n'a pas encore la réponse : le garde la lit comme `edouard` tant qu'elle n'y est pas.

**Dépôt de code, dépôt de données.** La nature est une réponse du modèle (`nature` dans
`.copier-answers.yml`, `NATURE` dans `scripts/modele/reglages.py`). Elle vaut `code` par défaut, ou `donnees`
(M-0006). Un dépôt de code porte l'application ; un dépôt de données porte ce qui fait d'une instance
celle d'Edouard, et reste privé. Dans un dépôt de code, tout constat refuse, quelle que soit sa
visibilité. Il refuse au hook comme en CI. Dans un dépôt de données, qui peut nommer son propre serveur, **la
porte avertit sur ce qui identifie et refuse toujours les secrets**. Ce qui identifie (adresses
privées et Tailscale, cibles SSH et scp, noms MagicDNS, motifs de la liste privée) s'affiche, avec
son emplacement et le nom du motif, jamais la valeur, et ne refuse pas. Un secret (clé privée age ou
PEM, jeton GitHub, JWT, jeton de tunnel, adresse de ping) refuse partout, au `pre-commit` comme en
CI ; gitleaks les cherche aussi, en CI. Les erreurs d'usage et l'absence de la liste privée exigée
refusent toujours.

**La porte d'un dépôt de code suit aussi les chemins.** Un dépôt de code ne porte rien de
l'instance (M-0006, § 3). La porte y refuse, au hook comme en CI : tout fichier nommé `*.enc` ou
`.sops.yaml`, et tout `*.pub` dans un dossier `cles/`, à toute profondeur, sauf un gabarit
`….jinja`, qui n'est pas le fichier qu'il rend ; tout fichier dont le premier segment du chemin est
`instance/`, `config/` ou `contenu/`, gabarit compris (un `src/config/` reste du code) ; et une clé
publique `age`, où qu'elle soit écrite. Dans un dépôt de données, ces fichiers sont chez eux : ces
règles n'y donnent aucun constat.

**En CI, la nature ne se lit pas dans la PR.** En CI, un dépôt public est toujours un dépôt de code,
et un dépôt privé prend la nature écrite sur sa branche par défaut, jamais celle de la PR. La porte
la lit par `git show origin/<branche par défaut>:scripts/modele/reglages.py` (la branche arrive par
`BRANCHE_DEFAUT`, la visibilité réelle par `DEPOT_PRIVE`). Une nature illisible vaut `code`, la plus
stricte. Hors CI, aux hooks, la porte lit le `reglages.py` de la copie ; sans lui (le dépôt modèle),
c'est `code`. Un dépôt privé n'a pas de règle de protection : le garde de Claude y est la seule
serrure côté agent, et la CI du socle le seul filet.

**L'historique d'un dépôt de code.** `modele-historique.yml` relit tout l'historique chaque semaine
et à la demande, après gitleaks. Chaque constat se nomme `<commit>:<chemin>:<ligne>` ; le message
d'un commit compte comme un chemin, `message`. Le projet peut en accepter, dans
`.github/constats-acceptes.txt` (un fichier qui lui appartient ; absent, il est vide) : une ligne
par couple (commit, chemin), `<commit> <chemin>`, suivie au besoin de `# <motif>`, jamais la valeur.
Elle écarte tous les constats de ce couple. Edouard relit cette liste, et rien d'autre n'est
toléré. Dans un dépôt de données, la porte dit que gitleaks seul relit l'historique.

**Passer un dépôt en public.** Deux cas.

- **Un dépôt de code né après M-0006 passe en public sans travail préalable** : il ne lui faut que
  sa règle de protection. L'ordre compte : d'abord, 👤, Edouard change la visibilité ; ensuite
  seulement, la règle de protection, que GitHub refuse sur un dépôt privé d'un compte gratuit. Son
  historique est relu chaque semaine.
- **Un dépôt d'avant M-0006 ne passe pas en public** : il se scinde (M-0006, § 7). Il devient le
  dépôt de données, et un nouveau dépôt de code naît d'un seul commit propre. Jusque-là, sa nature
  est `donnees`.

**Les deux modes de la chaîne.** En cible `serveur`, le mode suit la nature, sans réponse de plus
(M-0004, § 8).

- **À deux dépôts**, pour un dépôt de code né après M-0006. L'instance vit à la racine du dépôt de
  données `<nom>-donnees` : `env/`, `secrets/`, `.sops.yaml`, `cles/`, `config/` et `contenu/`. Le
  staging suit la branche principale du code et la branche des données que nomme `env/staging.env`
  (`…_BRANCHE_DONNEES`), la principale à la création ; la prod suit la plus haute `vX.Y.Z` du code
  et la plus haute étiquette de données. Les secrets du dépôt de données sont contrôlés par
  `modele-donnees.yml`, contre le `.cles` du dépôt de code, et ses destinataires contre
  `cles/*.pub`. `secrets.ps1 refaire` y prend le `.cles` du clone voisin du dépôt de code : le dépôt
  de code se clone à côté. Le dépôt de code garde gitleaks et le contrôle de ses `.cles`.
- **À un dépôt**, pour un dépôt de nature `donnees`, d'avant M-0006, jusqu'à sa scission. Tout est
  dans le même dépôt : `deploiement/env/`, `deploiement/secrets/`, `deploiement/cles/`,
  `.sops.yaml`, puis `instance/config/` et `instance/contenu/`. Le staging suit la branche
  principale ; la prod prend le commit de la plus haute `vX.Y.Z`, sans étiquette de données.

Dans les deux modes, un projet qui ne déclare ni `VERIFIER_CONFIG` ni `VERIFIER_CONTENU` ne monte
rien et se déploie comme avant (M-0003, § 6).

Le secret `MOTIFS_INTERDITS` (la liste privée) est posé **deux fois** par dépôt : comme secret
Actions et comme secret Dependabot (`gh secret set MOTIFS_INTERDITS --app dependabot`). Les
exécutions lancées par Dependabot ne reçoivent pas les secrets Actions : sans le second, la
confidentialité échouerait sur chacune de ses PR. Une PR venue d'un fork ne peut pas passer ce
contrôle, faute de secret ; aucun fork n'est attendu, et une telle PR se rouvre depuis une branche
du dépôt.

`core.hooksPath` n'est pas versionné : il doit valoir `.githooks`, chemin **relatif**, dans chaque
clone et chaque worktree.

**Un refus se corrige, il ne se contourne jamais** : pas de `--no-verify`, pas de `core.hooksPath`
modifié.

**Un texte qui cite une commande refusée se passe par fichier.** Le garde lit un message de commit
ou un corps de PR donné en ligne de commande comme il lit une commande, substitutions et
apostrophes inversées comprises : un message qui cite `git push origin main` est refusé comme le
serait la commande. Écrire le texte dans un fichier, puis `git commit -F <fichier>` ou
`gh pr create --body-file <fichier>`.

## Les fichiers gérés par le modèle

- Les fichiers **gérés** sont réécrits par chaque `copier update`. On ne les modifie jamais dans le
  projet : une modification locale ressort en conflit à la mise à jour suivante, et c'est voulu.
- Les fichiers **semés** sont créés une fois, puis appartiennent au projet. `copier update` ne les
  touche plus.
- Un cas mixte, `.claude/settings.json` : le modèle y pose ses hooks, le projet y ajoute ses
  réglages. Un conflit s'y résout à la main, dans la PR de mise à jour.
- **Les chemins gérés sont exclus des formateurs et des linters du projet** (Prettier, biome,
  ruff…) : `.githooks/`, `scripts/modele/`, `docs/modele/`, `.github/modele/`,
  `.github/workflows/modele-*.yml`, `.claude/skills/consigner/`. Un formateur qui les réécrirait
  ferait d'une modification locale un conflit à chaque `copier update`.
- Changer de cible, c'est changer une réponse puis lancer `copier update`. Les fichiers gérés de
  l'ancienne cible disparaissent, ceux de la nouvelle arrivent. Les fichiers semés de l'ancienne
  cible que la nouvelle ne rend pas disparaissent aussi, même retouchés, sans conflit ni `.rej` : ce
  que le projet y a écrit se reprend dans le commit d'avant (`git show <commit>:<chemin>`). Les
  semés que les deux cibles rendent gardent leur contenu d'avant, même si la nouvelle cible les rend
  autrement : le projet les refait à la main, ou les retire par `git rm` dans un commit d'avant la
  mise à jour, car Copier sème à neuf un semé absent du projet. Quand un projet `serveur` à un dépôt
  devient un dépôt de données, ce sont `.gitignore`, `CLAUDE.md`, `README.md`, `.sops.yaml`,
  `.github/workflows/ci.yml` et `.github/dependabot.yml`. Sauf `.gitignore`, qui ne se retire
  jamais : il porte les règles du projet, qui gardent ses fichiers locaux et ses secrets hors du
  dépôt, et sans lui ces fichiers paraissent en non suivis, ce que Copier refuse comme un arbre
  sale. Il se corrige à la main : pour un dépôt de données, `!/secrets/`, `/secrets/*` puis
  `!/secrets/*.env.enc`, à la fin du fichier : les lignes que la porte des masqués donne pour ce
  dossier mixte, et qu'elle ne demande pas, puisqu'elle ne voit pas un secret chiffré déjà suivi ;
  puis celles qu'elle demande. Ce que le modèle ne connaît pas reste où il est : les secrets
  chiffrés de `deploiement/secrets/`, puis `instance/config/` et `instance/contenu/`, se déplacent
  par `git mv` vers `secrets/`, `config/` et `contenu/`, dans le commit d'avant. Une question
  nouvelle prend son défaut sous `--defaults` : dans ce passage, `--data cible_code=serveur` est
  obligatoire. Sans lui, `cible_code` prend `aucune` sans un mot : ni `.sops.yaml`, ni `env/`, ni
  `cles/`, ni `modele-donnees.yml`, et le domaine, le sous-domaine, le bloc de ports et les clés
  sortent des réponses.

Dans un fichier géré, un conflit de `copier update` se résout toujours en faveur du modèle. Les PR
Dependabot qui y montent une version d'action se fusionnent normalement.

## Le registre

`docs/registre.md` porte une ligne par constat :

| N° | Famille | Date | Constat | Motif | Prévention | Critère de sortie | État |
|---|---|---|---|---|---|---|---|

- **AM** : une piste d'amélioration, « il faudrait ».
- **LE** : une leçon, « on a cru que ».
- **EM** : un empêchement, « on n'a pas pu ».

Les numéros ne se réutilisent jamais. **Au 3e constat portant le même motif, on écrit une porte** (un
test, un hook, une vérification de CI), et la ligne le dit. La compétence `/consigner`
(`.claude/skills/consigner/SKILL.md`) écrit la ligne.

Un dépôt de données n'a pas de registre à lui : ses leçons vont au registre de son dépôt de code.

## Les familles de garde-fous de l'écosystème

Toute application de l'écosystème est tenue à cinq familles de garde-fous (M-0001, d'après
l'ADR-0010 de `creche-planner`, §4) :

1. les décisions écrites en ADR ;
2. une CI qui refuse de passer ;
3. le mutation testing des tests du domaine ;
4. la recherche de secrets ;
5. aucune donnée réelle dans le dépôt.

Arbitrage du 16/10 : le modèle outille **quatre** familles (ADR, CI qui refuse, recherche de
secrets, aucune donnée réelle). **La mutation reste une obligation du projet**, avec l'outil de sa
stack, dès que le projet a une logique de domaine. Un site sans logique de domaine n'est pas
concerné.

Même arbitrage pour la cinquième : le modèle outille en partie seulement « aucune donnée réelle dans
le dépôt », par la séparation du code et des données (M-0006) et par la porte de confidentialité.
**Le test d'isolation des chemins de données reste une obligation du projet**, écrit avec l'outil de
sa stack, comme la mutation : chaque chemin de données d'un dépôt de code est redirigé vers des
fixtures, et un test garde-fou le vérifie.

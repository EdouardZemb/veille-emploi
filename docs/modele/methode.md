# La méthode des projets nés du modèle

Ce fichier est **géré par le modèle** : il est réécrit par chaque `copier update`, et on ne le
modifie pas dans le projet. Un défaut se corrige dans `modele-projet`, pour tous les projets.

## Le cycle d'un lot

1. Une issue, avec une mini-spec : objectif, critères d'acceptation, hors périmètre. Le formulaire
   « Lot » la pose. Une milestone par étape.
2. Une PR de plan, qui ajoute le plan dans `.claude/plans/`, avec ses trois sections ; la revue du
   plan le relit avant l'exécution (voir « Les outils »).
3. Une ou plusieurs PR d'implémentation.
4. Une PR de revue finale.
5. Une PR de clôture : elle **supprime le plan**, reporte dans `CLAUDE.md` ou dans un ADR ce qui
   doit survivre, et relit le README d'après `docs/modele/documentation.md`. Elle seule porte
   « Closes #N », les autres PR du lot disant « Partie de #N », et elle nomme la tête relue
   (voir « Le texte de la PR »).
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
  objectif, tâches, vérification de chaque tâche, et les trois sections dites plus bas ;
- une seule tâche à la fois ;
- le test d'abord : il est écrit, il échoue, puis le code le fait passer ;
- une revue avant la fusion, par une autre session ou par Edouard.

**Les trois sections d'un plan.** Qu'il soit écrit par *superpowers* ou à la main, un plan porte
trois sections de niveau 2, que `scripts/modele/plan.py` vérifie. On les écrit avant ses tâches ;
le script n'en vérifie pas la place. Chacune s'arrête au titre suivant, quel que soit son niveau,
ou à la première ligne de séparation (`---`), et n'admet que des puces `-` ou `*`, leurs lignes de
continuation indentées, des lignes vides et « Aucun. ». Une ligne indentée qui commence par une
puce ou un numéro (`-`, `*`, `+`, `1.`) est une sous-liste, et refuse : elle ne continue pas la
puce d'avant. Une ligne qui commence par un commentaire, après au plus trois espaces, et porte un
texte après lui refuse aussi : GitHub la rend en bloc HTML, jamais en puce. Chaque section est
unique : deux sections du même titre refusent, et aucune des deux n'est lue. Un séparateur est un
tiret cadratin (`—`) ou demi-cadratin (`–`), entouré d'espaces.

- `## Mécanismes annoncés` : une ligne par comportement que le plan prête à un mécanisme qui
  existe, `` - `<chemin>:<ligne>` — `<extrait>` — <comportement annoncé> ``. L'extrait, un texte
  de la ligne citée (un nom de fonction, un message), se cherche sur elle, ou dans une plage
  `<chemin>:<ligne>-<fin>` de 40 lignes au plus : un numéro faux ou une fonction mal nommée
  refuse. Un chemin sans préfixe part de la racine du dépôt, et un fichier absent refuse ; `..`,
  un chemin absolu, une barre oblique inverse ou un deux-points dans le chemin refusent, avant
  toute lecture. Un chemin d'un autre dépôt porte son préfixe, `<dépôt>:<chemin>:<ligne>` : il se
  vérifie quand `--depot <dépôt>=<clone>` est donné, et s'écrit sinon « non vérifié », sans refus.
  « Aucun. » est admis ;
- `## Outils et cas limites` : une ligne par outil qu'appelle un contrôle livré par le plan,
  `- <outil> — <cas limite que l'outil traite autrement> — <test qui l'exerce>`, trois morceaux
  non vides. « Aucun. » est admis ;
- `## Revues` : une ligne par temps de revue, `- <revue> : Tâche N`, qui cite au moins une tâche du
  plan, `Tâche N` ou `Task N`, d'après ses titres de niveau 3 (`### Tâche N : …`). Il en faut au
  moins une, et deux titres ne portent jamais le même numéro. La clôture est la première tâche dont
  le titre dit « clôture » ou « closure » : chaque tâche citée la précède.

**La revue du plan** se fait avant l'exécution, par une autre session ou par Edouard :

- elle relit dans le code chaque ligne de « Mécanismes annoncés », et juge un « Aucun. » contre ce
  que le plan décrit ;
- elle cherche, pour chaque outil qu'appelle un contrôle, le cas limite que cet outil traite
  autrement ;
- une correction cherche aussi la même croyance dans le reste du plan et dans la spec.

Les revues et les tests, dans tout le lot :

- chaque temps d'une revue est une tâche du plan, avant la clôture : la revue de chaque tâche, la
  revue finale, la relecture des corrections ; une revue se juge sur la tête qui part. La
  relecture de la tête qui part, dans la PR de clôture, ne s'écrit pas dans « Revues » : c'est la
  ligne `Tête relue` de cette PR qui la porte ;
- la PR de clôture nomme la tête qu'a lue sa dernière relecture, et un écart à la spec se déclare
  dans la PR, chacun avec ses limites (voir « Le texte de la PR ») ;
- un contrôle qui dépend du comportement d'un outil a un test sur le cas limite que cet outil
  traite autrement ; la règle vaut aussi pour un correctif écrit hors du plan ;
- un test qui garde une valeur est éprouvé par un mutant : la valeur changée fait échouer le test.

**En CI**, l'étape « Les plans (.claude/plans) » du socle lance `plan.py` sur chaque plan de
`.claude/plans/` que la PR ajoute ou modifie. Un plan ajouté se vérifie en entier, chaque fichier du
dépôt qu'il cite ouvert, mais un lieu préfixé par un autre dépôt y reste « non vérifié », sans
refus : l'étape ne passe pas `--depot`, et une session vérifie ce lieu en lançant `plan.py` avec
`--depot <dépôt>=<clone>`, puis la revue du plan le relit ; un plan modifié se vérifie sans ouvrir
les fichiers cités (`--sans-lieux`) : ses sections, la forme de chaque ligne et ses revues. Une PR
d'implémentation modifie souvent son plan avec le code qu'il cite, et les numéros de ligne
dérivent : les mécanismes se vérifient à l'entrée du plan, quand la revue du plan les relit, et un
mécanisme ajouté plus tard se relit à la revue. Le socle tourne aussi au push sur la branche
principale, sur les plans que ce push ajoute ou modifie : un plan ajouté s'y vérifie aussi sans
ouvrir les fichiers cités, puisque ses lieux l'ont été à la PR, et qu'une autre PR, fusionnée
entre-temps, a pu décaler une ligne citée.
Sur une base nulle, l'étape ne contrôle rien ; une PR qui ne touche aucun plan passe, comme la PR
de clôture, qui le supprime. La session lance aussi `python scripts/modele/plan.py <plan>` avant
de soumettre son plan à Edouard, et après chaque correction.

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
| hook Claude `SessionStart` (au démarrage et à la reprise) | affiche ce qui est rouge sur GitHub : les exécutions de la branche principale, les PR ouvertes et les workflows désactivés. Il ne bloque jamais. Il signale aussi un gabarit resté vide que le README lie, et un README qui ne lie aucun document du dépôt. Ce que n'importe qui écrit depuis un fork n'entre pas dans le contexte de Claude : les exécutions de PR (`pull_request…`) sont écartées, et une PR ou un workflow venus d'ailleurs que le dépôt s'affichent sans le texte qu'ils portent. Une PR d'un fork paraît ainsi sans titre ni nom de contrôle, un workflow absent de la copie, sans son nom |
| CI de base | gitleaks examine les commits de chaque PR et de chaque envoi, et tout l'historique chaque semaine et à la demande (`modele-historique.yml`) ; la porte relit aussi l'historique d'un dépôt de code chaque semaine (`modele-historique.yml`), à côté de gitleaks, et refuse tout constat absent de `.github/constats-acceptes.txt` ; confidentialité du diff et des messages de commit ; format des commits ; le garde de Claude **et les signaux** toujours branchés dans `.claude/settings.json` ; la licence et la carte de la racine (`scripts/modele/documentation.py`) ; actions épinglées par SHA |
| workflow `texte-pr` | `modele-texte-pr.yml`, seul à écouter `edited` : il relit le texte de chaque PR à son ouverture, à chaque envoi et à chaque retouche de son titre ou de son corps. La confidentialité et le format du titre et du corps, puis la section des écarts à la spec et la tête relue d'une PR qui ferme une issue (`scripts/modele/texte_pr.py`, voir plus bas). Son job, `texte-pr`, est un contrôle requis par la règle de protection d'un dépôt public ; dans un dépôt privé, qui n'a pas de règle, le garde le lit avant une fusion en mode `session` |
| CI de base, étape « Les plans (.claude/plans) » | sur chaque plan de `.claude/plans/` que la PR ajoute ou modifie, `scripts/modele/plan.py` vérifie les trois sections (voir « Les outils ») : un plan ajouté en entier, chaque fichier du dépôt cité ouvert, un lieu d'un autre dépôt restant « non vérifié », sans refus ; un plan modifié sans ouvrir les fichiers cités, ses numéros de ligne dérivant avec le code. Au push sur la branche principale, un plan ajouté se vérifie aussi sans ouvrir les fichiers cités, ses lieux vérifiés à la PR. Sur une base nulle, rien n'est contrôlé. L'étape précède la dernière, celle de la licence et de la carte de la racine |
| Dependabot | chaque lundi, les versions des actions épinglées (`.github/dependabot.yml`), après trois jours de recul |
| règle de protection GitHub | tout commit qui arrive sur la branche principale est la tête d'une PR dont les contrôles requis sont verts ; un envoi direct de cette tête est accepté et marque la PR fusionnée, sans squash. Côté agent, c'est le refus de pousser vers la branche principale par le garde qui ferme ce chemin. Ni force-push ni suppression de la branche principale. Posée sur les dépôts publics |

**Le texte de la PR.** Le workflow géré `texte-pr` (`modele-texte-pr.yml`) est seul à écouter
`edited` : une retouche du titre ou du corps d'une PR ne relance que lui, jamais toute la CI, dès
que le `ci.yml` du projet n'écoute plus `edited`. Le `ci.yml` d'un projet est semé : à sa mise à
jour, un projet déjà né en retire `edited` lui-même. Le workflow porte la confidentialité et le
format du titre et du corps, puis lance `scripts/modele/texte_pr.py`, qui lit le corps dans son
environnement, jamais dans ses arguments, et contrôle deux choses.

- **Les écarts à la spec.** Le corps de toute PR porte une section `## Écarts à la spec`, une
  seule, sauf quand l'auteur de la PR est `dependabot[bot]` : cette liste est fermée, et toute
  autre application y est soumise. La section s'arrête au premier titre, quel que soit son niveau,
  ou à la première ligne de séparation (`---`) : un écart écrit après n'est pas lu. Elle contient
  « Aucun. » seul, ou une ligne par écart,
  `- <écart> — promesse : <§ de la spec, ou de l'issue> — accord d'Edouard : JJ/MM/AAAA`, au
  besoin continuée par des lignes indentées, dans cet ordre : l'écart, qui peut contenir un
  séparateur, puis la promesse, qui n'en contient pas, puis l'accord, dont la date termine la
  ligne. Une ligne indentée qui commence par une puce ou un numéro (`-`, `*`, `+`, `1.`) est une
  sous-liste, et ne continue pas l'écart. Le contrôle refuse, sans nommer de ligne : une section
  absente, vide ou en double ; « Aucun. » à côté d'un écart ; un commentaire HTML jamais fermé,
  qui cacherait la suite. Il refuse, en nommant la ligne par son rang dans la section : une ligne
  qui n'est ni « Aucun. » ni un écart, une sous-liste comprise ; un écart vide, sans « promesse : »
  suivi d'un texte, sans « accord d'Edouard : » suivi d'une date valide `JJ/MM/AAAA`, avec un
  texte après la date, ou hors de cet ordre. Un commentaire fermé ou un bloc clôturé ne compte
  pas : la forme d'une ligne, que le gabarit de PR met en commentaire, n'est pas un écart. Une
  ligne qui commence par un commentaire, après au plus trois espaces, et porte un texte après lui
  refuse, comme une ligne qui n'est ni « Aucun. » ni un écart : GitHub la rend en bloc HTML, son
  texte tel quel, sans Markdown, jamais en puce ; sous une puce, il ne la montre dans la puce que
  si elle est indentée au moins autant que le texte de la puce. Un bloc indenté de quatre espaces
  n'est pas écarté : après une puce, il continue l'écart ; sans puce avant lui, il refuse. Le
  contrôle ne vérifie ni que l'accord est réel, ni qu'un écart n'a pas été tu : il force à écrire
  l'écart, la promesse qu'il touche et la date de l'accord. Un écart se pèse contre la promesse de
  la spec, jamais contre l'ancien comportement, ni contre le seul mécanisme principal : l'accord
  d'Edouard porte sur cette promesse, citée.
- **La tête relue.** Une PR qui ferme une issue porte la ligne `Tête relue : <SHA>`, le SHA
  complet de la tête qu'a lue la dernière relecture. Dans un lot, c'est la PR de clôture, et elle
  seule ; hors des lots, un correctif qui ferme une issue par `Fixes #N` nomme aussi la tête
  relue. Les issues que la PR ferme se lisent par l'API (`closingIssuesReferences`), l'analyse de
  GitHub lui-même, jamais dans le corps ; une réponse absente, en erreur ou mal formée fait
  refuser. Le contrôle refuse aussi une ligne absente, ou un SHA autre que la tête de la PR, en
  nommant les deux SHA. Un commit poussé après la dernière relecture fait donc refuser la PR,
  jusqu'à ce que le corps nomme la nouvelle tête, relue ; cette retouche ne relance que `texte-pr`.
  La ligne se cherche telle que GitHub la montre : un commentaire jamais fermé, ouvert en tête de
  ligne ou après une puce, cache tout ce qui le suit, et une ligne cachée est absente.
- **Les limites de la tête relue.** Le contrôle force à nommer une tête, pas à la relire : la
  relecture reste une tâche du plan. Dans un lot, la PR de revue finale n'est pas visée : sa
  relecture est une tâche du plan, et la PR de clôture relit ensuite la tête qui part. GitHub ne
  lit un mot-clé de fermeture que dans une PR qui vise la branche par défaut : une PR empilée sur
  une autre branche ne ferme rien, et sa tête relue n'est pas exigée. Une issue liée depuis la
  barre latérale de la PR compte aussi, mais aucun type d'événement documenté ne suit ce lien : le
  contrôle repart au commit ou à la modification du corps suivants. La ligne se cherche telle que
  GitHub la montre, à des écarts près, dont deux connus : un `<!--` jamais fermé, ouvert dans un
  élément de liste après quatre espaces ou plus (une puce imbriquée, ou une ligne qui continue la
  puce), cache sur GitHub tout ce qui le suit, et un `<?`, un `<!` suivi d'une majuscule
  (`<!DOCTYPE`) ou un `<![CDATA[` ouvert en tête de ligne, tout ce qui le suit jusqu'au premier
  `>`, même plusieurs lignes plus bas, ou jusqu'à la fin sans lui ; le contrôle lit encore ces
  lignes, la ligne `Tête relue` comme la section des écarts. D'autres formes HTML cachent aussi sur
  GitHub ce que le contrôle lit : un `<?` ou un `<!DOCTYPE` après une puce, ou en ligne et fermé
  plus bas ; un `<!--` jamais fermé dans une ligne de bloc HTML, comme `<div><!-- note</div>` ; un
  attribut ou un titre de lien sur plusieurs lignes. Tous sont bornés : le SHA de cette ligne doit
  toujours égaler la tête de la PR.
- **Ne jamais relancer `texte-pr`.** Une relance, par `gh run rerun` ou depuis l'interface de
  GitHub, rejoue l'événement d'origine : elle relit le titre et le corps de ce moment-là, pas ceux
  de la PR telle qu'elle est. Éprouvé dans le dépôt modèle le 07/11/2026 : après une retouche qui
  retirait la section des écarts, la relance de la première exécution par `gh run rerun` a relu
  le corps d'avant et est passée, et `gh pr checks` a montré `texte-pr` vert sur un corps qui
  refusait. Pour relire le texte, on retouche le titre ou le corps : la retouche relance
  `texte-pr` sur le texte en cours.

**Qui fusionne : la réponse `fusion`.** Deux modes, choisis à la création du projet et enregistrés
dans `.copier-answers.yml` :

- `session` : la session fusionne sa PR une fois tous les contrôles verts ;
- `edouard` : la session ouvre la PR, attend que tout soit vert, le dit, et s'arrête. Le garde
  refuse toute fusion : `gh pr merge` (y compris `--auto` et `--admin`), l'API (`…/merge`) et les
  mutations GraphQL de fusion. Le refus dit `mode fusion : edouard`.

Le mode lui-même se lit sur GitHub, par l'API (`gh api`) : le `.copier-answers.yml` de la branche
principale, et non celui de la copie locale ni `origin/<branche>`, qu'une session peut réécrire.
Tout ce qui est illisible (`gh` absent, erreur, ligne absente) vaut `edouard` ; à court de temps, le
garde refuse en disant « budget de 20 s épuisé : mode non lu, relancer », et « budget de 20 s
épuisé : contrôles non lus, relancer » quand ce sont les contrôles de la PR qu'il n'a pas pu lire.
Deux entrées restent locales :

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
serrure côté agent, et la CI (le socle et `texte-pr`) le seul filet ; avant une fusion en mode
`session`, le garde lit tous les contrôles, `texte-pr` compris (`gh pr checks`). En mode `edouard`,
le garde refuse toute fusion de la session : Edouard fusionne, et rien ne lit les contrôles à sa
place.

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
- Les fichiers **semés** sont créés une fois, puis appartiennent au projet : `copier update` ne
  touche plus un semé présent, mais sème à neuf un semé absent, qu'il ait été retiré ou qu'il soit
  nouveau dans le modèle, comme `LICENSE`. Un fichier non suivi (`??`) après la mise à jour
  s'indexe, ou se retire.
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

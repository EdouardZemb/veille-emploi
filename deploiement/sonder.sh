#!/usr/bin/env bash
# Sonde d'un environnement d'veille-emploi, lancée toutes les 5 minutes par veille-emploi-sonde-<env>.timer.
# Elle suit la cible de l'environnement, un couple : une image et un commit de données (M-0004 et
# M-0006 § 5, amendés). Elle déploie tout nouveau couple par deployer.sh, et sinon contrôle celui
# qui est en service.
#
#   bash deploiement/sonder.sh <prod|staging>
#
# Le commit de données. Un projet dont deploiement/projet.env ne déclare ni VERIFIER_CONFIG ni
# VERIFIER_CONTENU a le commit « - » : rien n'est monté, comme avant le couple. Sinon, selon le mode
# des données (MODE_DONNEES, lib.sh) :
#   - deux dépôts : un commit du clone des données de l'environnement ($VEILLE_EMPLOI_CLONE_DONNEES,
#     lib.sh), la tête de sa branche en staging, la plus haute étiquette de données en prod ;
#   - un dépôt : la révision de l'image visée (son label org.opencontainers.image.revision), qui doit
#     exister dans le clone du projet, qui porte aussi l'instance.
#
# Déroulé :
#   0. à deux dépôts, le clone des données doit exister, avant charger_env, qui y lit l'env :
#      sinon, alerte « clone des données absent ». Sans lui, ni env ni secrets : le signal ne peut
#      pas partir, et seuls le code de sortie (OnFailure=) et l'absence de signal ok le disent.
#      Puis, avant toute action, le refus d'une image, d'une version ou d'un montage posés dans
#      l'environnement (refuser_image_heritee, lib.sh) ;
#   1. verrou $VEILLE_EMPLOI_ETAT/verrou, sans attente. S'il est pris (déploiement manuel, sauvegarde,
#      autre sonde) : « occupé », code 0 ;
#   2. clone propre (`git status --porcelain` vide), sinon alerte « clone modifié » ;
#   3. cible du code, selon le canal de l'environnement (VEILLE_EMPLOI_CANAL, dans son env) :
#      - main (staging) : `git fetch origin principal`, `git merge --ff-only origin/principal` (la
#        branche principale) ; image :main, version main ;
#      - etiquette (prod) : `git fetch --prune --prune-tags --tags origin` (une étiquette retirée
#        de l'origine disparaît aussi du clone : `--tags` seul ne supprime jamais une étiquette
#        locale, et la sonde viserait encore une version retirée) ; plus haute étiquette vX.Y.Z (tri
#        -v:refname, les autres formes comme v1.0.0-rc1 sont ignorées) ; image :X.Y.Z, version
#        X.Y.Z. Sans étiquette : « aucune version », signal ok ;
#   4. les commandes de l'instance que déclare deploiement/projet.env (donnees_declarees, lib.sh),
#      celui de la version visée du code, jamais celui de la version qu'on quitte : en staging, la
#      copie de travail, qui vient de fusionner ; en prod, celui de l'étiquette, lu sans checkout
#      (declaration_visee) : `git ls-tree` dit s'il y est (absent, il ne déclare rien ; une erreur
#      de git alerte), puis `git show <étiquette>:deploiement/projet.env` le copie dans un fichier
#      temporaire, retiré à toute sortie, signal compris ;
#      puis, à deux dépôts, le clone des données, qu'un projet déclare une commande ou non (il porte
#      l'env et les secrets) : propre, sinon alerte « clone des données modifié » ; à jour, selon le
#      même canal, sinon alerte « mise à jour du clone des données impossible » :
#      - main (staging) : `git fetch origin <branche>`, `git merge --ff-only origin/<branche>`, la
#        branche des données étant VEILLE_EMPLOI_BRANCHE_DONNEES, dans l'env, sans défaut (absente :
#        alerte) ; le commit est la tête du clone ;
#      - etiquette (prod) : `git fetch --prune --prune-tags --tags origin` ; plus haute étiquette de
#        données donnees-AAAA.MM.JJ.n (n sans zéro en tête ; tri -v:refname ; les autres formes,
#        vX.Y.Z comprises, sont ignorées), dont le commit se lit sans checkout. Sans elle, une
#        version qui déclare une commande attend, et rien n'est tiré ni déployé
#        (attendre_les_donnees) : le couple en service, s'il y en a un, se contrôle comme à
#        l'étape 7 quand il est déjà déployé ou en échec (rien_de_nouveau), le champ configuration
#        exigé suivant ce couple (montee si son compose.env monte /config, rien sinon), puis le
#        signal ok dit « <version> attend une version des données » ; sans couple en service :
#        « aucune version des données », signal ok ;
#   5. `docker pull -q` de la cible. Sur le canal etiquette, une étiquette que le registre ne
#      connaît pas (« manifest unknown », « manifest for <cible> not found », « <cible>: not
#      found ») n'est pas encore publiée : on attend, sans signal. Tout autre échec alerte ;
#   6. sa référence image@sha256:… ; à un dépôt, avec une commande déclarée, le commit est la
#      révision de cette image, qui doit exister dans le clone, sinon alerte ;
#   7. le couple « <référence> <commit> », comparé à l'état, où un fichier d'avant la v0.7.0, sans
#      commit, vaut « - » :
#      - en échec (les deux champs d'`echec`, contrôlés en premier) : on attend un nouveau couple,
#        sans signal, si l'état laissé par le retour arrière est cohérent (voir etat_apres_echec) ;
#        sinon, alerte « retour arrière incomplet » à chaque passage, sans relance automatique :
#        `deployer.sh` à la main. C'est l'état d'un retour arrière manuel (`deployer.sh <env>
#        --retour`), qui écrit le couple quitté dans `echec` et le garde : la sonde ne le redéploie
#        pas. Si ce retour a échoué, le couple quitté est à la fois déployé et en échec : même
#        attente silencieuse (pas de signal ok), ou même alerte s'il ne répond pas non plus ;
#      - déjà déployé (premier et troisième champs de `deploye`) : en prod, contrôle de dérive des
#        unités ; puis l'adresse publique doit répondre HTTP 200 (une redirection est un échec),
#        avec un corps statut ok pour cet environnement et, si VERIFIER_CONFIG est déclarée,
#        configuration montee en prod, exemple en staging ; signal ok ;
#      - sinon : le clone passe sur l'étiquette (canal etiquette), le clone des données sur
#        l'étiquette de données s'il y en a une (même sans commande déclarée : l'env et les secrets
#        de la prod suivent la série) et, en prod, les unités sont réinstallées
#        (VEILLE_EMPLOI_AVANT_DEPLOIEMENT=1 : « non » aux heures des sauvegardes y refuse) ; puis
#        `deployer.sh <env> <référence> <version> --commit-donnees <commit>` (sans l'option pour
#        « - »), qui envoie ses propres signaux, et dont le code est renvoyé.
#
# Les unités systemd ne concernent que la prod : elles sont toutes rendues depuis son clone (voir
# installer-unites.sh). Le staging ne les installe ni ne les contrôle.
#
# Pas de signal quand le verrou est pris, quand l'image de prod n'est pas encore publiée ou quand
# le couple est en échec et que son retour arrière a abouti : si cela dure, c'est l'absence de
# signal ok qui alerte.
#
# Codes de sortie : 0 ; 1 anomalie (signalée, sauf un clone des données absent), ou image, version
# ou montage hérités (non signalé) ; 3 secrets absents ; 64 usage ; sinon, celui de deployer.sh.
# Tout code non nul déclenche aussi l'alerte de l'unité (OnFailure=).
set -euo pipefail
# shellcheck source=deploiement/lib.sh
. "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

# signaler_sonde ok|echec <message> : le signal n'est qu'un plus (signaler journalise son échec) ;
# le code de la sonde n'en dépend pas.
signaler_sonde() {
  signaler HC_SONDE "$@" || true
}

# anomalie <message> : journal et signal d'échec. L'appelant renvoie ensuite le code 1.
anomalie() {
  journal "anomalie : $1"
  signaler_sonde echec "$1"
}

# etat_apres_echec <référence déployée> <version déployée> : vérifie que le dernier déploiement en
# échec a bien laissé la place. deployer.sh écrit `echec` avant le retour arrière ; s'il est coupé
# pendant ce retour, la version en échec peut tourner encore, sans que rien l'ait signalé.
#   - Une version déployée : compose.env la décrit, et la santé locale annonce sa version et la
#     révision de son image.
#   - Aucune (premier déploiement en échec) : rien du projet ne doit tourner. Sans compose.env,
#     aucun `up` n'a eu lieu ; avec, `dc ps -q app` doit être vide (un conteneur qui redémarre en
#     boucle y figure). La santé locale ne suffirait pas : une version en échec répond souvent mal.
# Succès si l'état est cohérent ; sinon, la raison sur stdout.
etat_apres_echec() {
  local deployee="$1" version_deployee="$2" etat="$VEILLE_EMPLOI_ETAT" conteneurs revision reponse
  if [ -z "$deployee" ]; then
    [ -f "$etat/compose.env" ] || return 0
    if ! conteneurs="$(dc ps -q app)"; then
      echo "état de l'application illisible"
      return 1
    fi
    if [ -n "$conteneurs" ]; then
      echo "la version en échec tourne encore (aucune version déployée avant elle)"
      return 1
    fi
    return 0
  fi
  if [ "$(valeur_de VEILLE_EMPLOI_IMAGE "$etat/compose.env")" != "$deployee" ]; then
    echo "compose.env ne décrit pas la version déployée ($version_deployee)"
    return 1
  fi
  if ! revision="$(revision_de "$deployee")"; then
    echo "révision de la version déployée illisible"
    return 1
  fi
  if ! reponse="$(sante_locale "$version_deployee" "$revision")"; then
    journal "santé locale : ${reponse//$'\n'/ } (attendu : version $version_deployee, révision $revision)"
    echo "la santé locale n'annonce pas la version déployée ($version_deployee)"
    return 1
  fi
}

# controler_adresse_publique <env> [<configuration>] : l'adresse publique (VEILLE_EMPLOI_URL_PUBLIQUE, par
# le tunnel) doit répondre HTTP 200, et son corps doit dire statut ok pour CET environnement, et,
# avec un deuxième argument, ce champ configuration (exemple ou montee, M-0003 amendé). Le corps
# compte : des routes du tunnel inversées (staging et prod) donneraient deux adresses « ok », et
# celle du staging servirait les données réelles de la prod. Une redirection (Cloudflare Access…)
# n'est pas une santé, et `curl -f` la laisse passer : le code HTTP est lu avec -w, sans suivre les
# redirections. En cas d'échec : journal, signal d'échec, code 1.
controler_adresse_publique() {
  local nom_env="$1" configuration="${2:-}" sortie corps http code=0 attendu filtre
  sortie="$(curl -sS -m 10 -w '\n%{http_code}' "$VEILLE_EMPLOI_URL_PUBLIQUE/sante")" || code=$?
  if [ "$code" -ne 0 ]; then
    anomalie "adresse publique injoignable"
    return 1
  fi
  http="${sortie##*$'\n'}"
  corps="${sortie%$'\n'*}"
  if [ "$http" != 200 ]; then
    journal "adresse publique : réponse HTTP $http au lieu de 200 (une redirection n'est pas une santé) : ${corps:0:300}"
    anomalie "adresse publique : réponse HTTP $http au lieu de 200"
    return 1
  fi
  attendu="statut ok, environnement $nom_env${configuration:+, configuration $configuration}"
  # shellcheck disable=SC2016  # $env et $configuration sont des variables de jq (--arg)
  filtre='.statut == "ok" and .environnement == $env'
  # shellcheck disable=SC2016
  [ -z "$configuration" ] || filtre="$filtre"' and .configuration == $configuration'
  if ! jq_vaut true "$corps" "$filtre" --arg env "$nom_env" --arg configuration "$configuration"; then
    journal "adresse publique : corps inattendu (attendu : $attendu) : ${corps:0:300}"
    anomalie "adresse publique : réponse inattendue (attendu : $attendu)"
    return 1
  fi
}

# rien_de_nouveau <env> <version> <référence> <commit> <configuration> <message> : le couple
# « <référence> <commit> », de la version <version>, n'est pas à déployer ; il se contrôle.
#   - En échec (les deux champs d'`echec`, contrôlés en premier) : `deployer.sh <env> --retour` qui
#     n'a pas pu quitter le couple en service le laisse à la fois déployé et en échec. Il n'est pas
#     « en service » : pas de signal ok, le silence tient l'incident ouvert. L'état laissé par le
#     retour arrière doit être cohérent (etat_apres_echec), sinon alerte, sans relance automatique.
#   - Sinon, en service : en prod, contrôle de dérive des unités ; puis l'adresse publique, avec ce
#     champ configuration s'il n'est pas vide (controler_adresse_publique) ; puis le signal ok
#     <message>.
# Lit DEPLOYE_IMAGE, DEPLOYE_VERSION, ECHEC_IMAGE et ECHEC_COMMIT (lire_deploye, lire_echec).
# Échec : anomalie signalée, code 1.
rien_de_nouveau() {
  local nom_env="$1" version="$2" reference="$3" commit="$4" configuration="$5" message="$6" raison
  if [ "$reference" = "$ECHEC_IMAGE" ] && [ "$commit" = "$ECHEC_COMMIT" ]; then
    # Pas de relance automatique : elle reprendrait un instantané à chaque passage.
    if ! raison="$(etat_apres_echec "$DEPLOYE_IMAGE" "$DEPLOYE_VERSION")"; then
      journal "couple en échec ($version, $reference, données $commit), mais le retour arrière n'a pas abouti : $raison. Relancer deployer.sh à la main"
      anomalie "retour arrière incomplet : $raison"
      return 1
    fi
    journal "couple en échec, attente d'un nouveau : $version ($reference, données $commit)"
    return 0
  fi
  if [ "$nom_env" = prod ] && ! bash "$VEILLE_EMPLOI_CLONE/deploiement/installer-unites.sh" --verifier; then
    anomalie "unités divergentes"
    return 1
  fi
  if ! controler_adresse_publique "$nom_env" "$configuration"; then
    return 1
  fi
  journal "$version en service : $reference, données $commit"
  signaler_sonde ok "$message"
  return 0
}

# Le fichier temporaire de declaration_visee, vide hors de sa lecture.
PROJET_ENV_VISE=""

# _retirer_projet_env_vise : retire le fichier temporaire de declaration_visee, s'il y en a un.
_retirer_projet_env_vise() {
  [ -z "$PROJET_ENV_VISE" ] || rm -f -- "$PROJET_ENV_VISE"
  PROJET_ENV_VISE=""
}

# declaration_visee <étiquette> : DECLARE_CONFIG et DECLARE_CONTENU (donnees_declarees, lib.sh)
# d'après le deploiement/projet.env de la version visée du code, jamais celui de la version qu'on
# quitte : deployer.sh, lancé depuis la version visée, refuserait sinon le couple (64).
#   - Sans étiquette (staging) : la copie de travail du clone, qui vient de fusionner la branche
#     principale : c'est la version visée.
#   - Avec une étiquette (prod) : le clone n'y passe qu'avant deployer.sh, son projet.env se lit
#     sans checkout. `git ls-tree` dit s'il y est : une sortie vide, code 0, s'il en est absent, et
#     il ne déclare rien, comme un clone sans projet.env ; une erreur de git n'est pas une absence.
#     Présent, `git show` le copie dans un fichier temporaire, le temps de le lire : il est retiré à
#     la fin, et par un signal (INT, TERM, HUP) reçu pendant ce temps. Les gestionnaires de
#     l'appelant sont rétablis ensuite.
# Échec : anomalie signalée (le stderr de git va au journal), code 1.
declaration_visee() {
  local etiquette="$1" clone="$VEILLE_EMPLOI_CLONE" chemin=deploiement/projet.env present pieges lisible=1
  if [ -z "$etiquette" ]; then
    if ! donnees_declarees; then
      anomalie "$chemin illisible"
      return 1
    fi
    return 0
  fi
  if ! present="$(git -C "$clone" ls-tree --name-only "$etiquette" -- "$chemin")"; then
    journal "git ls-tree --name-only $etiquette -- $chemin impossible"
    anomalie "$chemin de $etiquette illisible"
    return 1
  fi
  if [ -z "$present" ]; then
    DECLARE_CONFIG=0 DECLARE_CONTENU=0
    return 0
  fi
  pieges="$(trap -p INT TERM HUP)"
  trap '_retirer_projet_env_vise; exit 130' INT
  trap '_retirer_projet_env_vise; exit 143' TERM
  trap '_retirer_projet_env_vise; exit 129' HUP
  if ! PROJET_ENV_VISE="$(mktemp "${TMPDIR:-/tmp}/veille-emploi-projet-env.XXXXXX")"; then
    PROJET_ENV_VISE=""
    journal "fichier temporaire impossible pour $chemin de $etiquette"
    lisible=0
  elif ! git -C "$clone" show "$etiquette:$chemin" >"$PROJET_ENV_VISE"; then
    journal "git show $etiquette:$chemin impossible"
    lisible=0
  elif ! donnees_declarees_dans "$PROJET_ENV_VISE"; then
    lisible=0
  fi
  _retirer_projet_env_vise
  trap - INT TERM HUP
  [ -z "$pieges" ] || eval "$pieges"
  if [ "$lisible" -eq 0 ]; then
    anomalie "$chemin de $etiquette illisible"
    return 1
  fi
  return 0
}

# donnees_visees <env> <étiquette> : l'étape 4, les données du couple visé ; <étiquette> est celle
# du code, vide en staging. La déclaration de la version visée (declaration_visee), puis, à deux
# dépôts, le clone des données de l'environnement, qu'une commande soit déclarée ou non (l'env et
# les secrets y vivent ; le canal a été contrôlé à l'étape 3) : propre, puis à jour. Pose :
#   DECLAREE           1 si la version visée déclare une commande de l'instance, 0 sinon ;
#   COMMIT_VISE        le commit de données du couple visé, « - » sans commande déclarée ; à un
#                      dépôt, « - » ici aussi, l'étape 6 le lit dans l'image visée ;
#   ETIQUETTE_DONNEES  l'étiquette de données visée (canal etiquette, à deux dépôts), vide sinon ;
#   ATTENTE_DONNEES    1 si une commande est déclarée mais qu'aucune étiquette de données n'existe
#                      encore : la version visée attend (attendre_les_donnees) ; 0 sinon.
# Échec : anomalie signalée, code 1.
donnees_visees() {
  local nom_env="$1" etiquette="$2" donnees="$VEILLE_EMPLOI_CLONE_DONNEES" modifications etiquettes ligne
  local branche_donnees commit=-
  DECLAREE=0 COMMIT_VISE=- ETIQUETTE_DONNEES="" ATTENTE_DONNEES=0
  declaration_visee "$etiquette" || return 1
  if [ "$DECLARE_CONFIG" -eq 1 ] || [ "$DECLARE_CONTENU" -eq 1 ]; then
    DECLAREE=1
  fi
  [ "$MODE_DONNEES" = deux ] || return 0

  if ! modifications="$(git -C "$donnees" status --porcelain)"; then
    anomalie "git status du clone des données impossible"
    return 1
  fi
  if [ -n "$modifications" ]; then
    journal "clone des données modifié ($donnees) : ${modifications//$'\n'/ ; }"
    anomalie "clone des données modifié"
    return 1
  fi
  case "$VEILLE_EMPLOI_CANAL" in
    main)
      # Sans défaut : une branche devinée suivrait peut-être les données d'un autre environnement.
      # Une valeur qui commencerait par « - » serait une option de git.
      branche_donnees="${VEILLE_EMPLOI_BRANCHE_DONNEES:-}"
      if ! [[ "$branche_donnees" =~ ^[A-Za-z0-9][A-Za-z0-9._/-]*$ ]]; then
        journal "VEILLE_EMPLOI_BRANCHE_DONNEES absente ou invalide dans $donnees/$SOUS_DOSSIER_ENV/$nom_env.env : '$branche_donnees' (attendu : le nom de la branche des données, sans défaut)"
        anomalie "VEILLE_EMPLOI_BRANCHE_DONNEES absente ou invalide"
        return 1
      fi
      if ! git -C "$donnees" fetch origin "$branche_donnees" 9>&- \
        || ! git -C "$donnees" merge --ff-only "origin/$branche_donnees"; then
        journal "clone des données ($donnees) : git fetch origin $branche_donnees, puis git merge --ff-only origin/$branche_donnees, impossible"
        anomalie "mise à jour du clone des données impossible"
        return 1
      fi
      [ "$DECLAREE" -eq 1 ] || return 0
      if ! commit="$(git -C "$donnees" rev-parse HEAD)" || ! [[ "$commit" =~ $MOTIF_SHA ]]; then
        anomalie "commit du clone des données illisible"
        return 1
      fi
      ;;
    etiquette)
      if ! git -C "$donnees" fetch --prune --prune-tags --tags origin 9>&-; then
        journal "clone des données ($donnees) : git fetch --prune --prune-tags --tags origin impossible"
        anomalie "mise à jour du clone des données impossible"
        return 1
      fi
      # Les étiquettes de données seulement : jamais les vX.Y.Z que porterait ce clone.
      if ! etiquettes="$(git -C "$donnees" tag --list 'donnees-*' --sort=-v:refname)"; then
        anomalie "liste des étiquettes de données illisible"
        return 1
      fi
      while IFS= read -r ligne; do
        if [[ "$ligne" =~ ^donnees-[0-9]{4}\.[0-9]{2}\.[0-9]{2}\.[1-9][0-9]*$ ]]; then
          ETIQUETTE_DONNEES="$ligne"
          break
        fi
      done <<<"$etiquettes"
      [ "$DECLAREE" -eq 1 ] || return 0
      if [ -z "$ETIQUETTE_DONNEES" ]; then
        journal "aucune version des données : pas d'étiquette donnees-AAAA.MM.JJ.n dans $donnees"
        ATTENTE_DONNEES=1
        return 0
      fi
      # Le commit de l'étiquette, sans checkout : le clone n'y passe qu'avant deployer.sh.
      if ! commit="$(git -C "$donnees" rev-parse "$ETIQUETTE_DONNEES^{commit}")" \
        || ! [[ "$commit" =~ $MOTIF_SHA ]]; then
        anomalie "commit de $ETIQUETTE_DONNEES illisible"
        return 1
      fi
      ;;
  esac
  COMMIT_VISE="$commit"
  return 0
}

# attendre_les_donnees <env> <version> : la version visée déclare une commande, mais aucune version
# des données n'existe encore (donnees_visees). Sans couple en service (deploye absent), le signal
# ok « aucune version des données ». Un deploye présent mais illisible est une anomalie : rien ne
# dirait plus ce qui sert la prod (hors de l'attente, deployer.sh s'en
# charge). Avec un couple en service, il se contrôle comme quand rien n'est nouveau
# (rien_de_nouveau), et le signal ok dit l'attente. Le champ configuration exigé suit ce couple, pas
# la déclaration visée : montee si son compose.env monte /config, rien sinon.
# L'attente n'arrive qu'en prod : le staging prend la tête de la branche des données.
# Échec : anomalie signalée, code 1.
attendre_les_donnees() {
  local nom_env="$1" version="$2" etat="$VEILLE_EMPLOI_ETAT" configuration=""
  if [ ! -e "$etat/deploye" ] && [ ! -L "$etat/deploye" ]; then
    journal "$version attend une version des données, aucun couple en service"
    signaler_sonde ok "aucune version des données"
    return 0
  fi
  # lire_deploye journalise les champs qu'il n'a pas pu lire.
  if ! lire_deploye; then
    anomalie "$etat/deploye illisible"
    return 1
  fi
  lire_echec || journal "$etat/echec illisible : aucun couple n'est tenu pour en échec"
  if valeur_de VEILLE_EMPLOI_CONFIG "$etat/compose.env" >/dev/null; then
    configuration=montee
  fi
  journal "$version attend une version des données ; le couple en service se contrôle : $DEPLOYE_VERSION ($DEPLOYE_IMAGE, données $DEPLOYE_COMMIT)"
  rien_de_nouveau "$nom_env" "$DEPLOYE_VERSION" "$DEPLOYE_IMAGE" "$DEPLOYE_COMMIT" "$configuration" \
    "$version attend une version des données"
}

main() {
  [ "$#" -eq 1 ] || arreter 64 "usage : bash deploiement/sonder.sh <prod|staging>"
  local nom_env="$1"
  valider_env "$nom_env"

  # 0. À deux dépôts, le clone des données, avant charger_env : il y lit l'env, et s'arrêterait
  # sans rien signaler. Le signal ne part pas davantage ici, HC_SONDE étant un secret de ce clone :
  # le journal et le code de sortie le disent.
  poser_clone_donnees "$nom_env"
  if [ "$MODE_DONNEES" = deux ] && [ ! -d "$VEILLE_EMPLOI_CLONE_DONNEES" ]; then
    journal "clone des données absent : $VEILLE_EMPLOI_CLONE_DONNEES (ni env ni secrets : aucun signal ne peut partir)"
    anomalie "clone des données absent"
    return 1
  fi
  charger_env "$nom_env"
  charger_secrets "$nom_env"
  # L'image, la version et les montages ne viennent que de compose.env : avant tout `dc`.
  refuser_image_heritee
  local etat="$VEILLE_EMPLOI_ETAT" clone="$VEILLE_EMPLOI_CLONE" donnees="$VEILLE_EMPLOI_CLONE_DONNEES"
  local modifications etiquettes etiquette="" ligne version cible sortie code=0 reference message
  local etiquette_donnees commit configuration=""
  local -a option_commit=()

  # 1. Verrou, gardé jusqu'à la fin de la sonde (deployer.sh compris).
  exec 9>"$etat/verrou"
  if ! flock -n 9; then
    journal "occupé : le verrou $etat/verrou est tenu (déploiement, sauvegarde ou autre sonde)"
    return 0
  fi

  # 2. Clone propre.
  if ! modifications="$(git -C "$clone" status --porcelain)"; then
    anomalie "git status impossible"
    return 1
  fi
  if [ -n "$modifications" ]; then
    journal "clone modifié ($clone) : ${modifications//$'\n'/ ; }"
    anomalie "clone modifié"
    return 1
  fi

  # 3. Cible du code. `9>&-` : un processus que git laisserait derrière lui (maître ssh
  # persistant…) ne garde pas le verrou après la sonde.
  case "$VEILLE_EMPLOI_CANAL" in
    main)
      if ! git -C "$clone" fetch origin principal 9>&-; then
        anomalie "git fetch origin principal impossible"
        return 1
      fi
      if ! git -C "$clone" merge --ff-only origin/principal; then
        anomalie "git merge --ff-only origin/principal impossible"
        return 1
      fi
      version=main
      ;;
    etiquette)
      if ! git -C "$clone" fetch --prune --prune-tags --tags origin 9>&-; then
        anomalie "git fetch --prune --prune-tags --tags origin impossible"
        return 1
      fi
      if ! etiquettes="$(git -C "$clone" tag --list --sort=-v:refname)"; then
        anomalie "liste des étiquettes illisible"
        return 1
      fi
      while IFS= read -r ligne; do
        if [[ "$ligne" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
          etiquette="$ligne"
          break
        fi
      done <<<"$etiquettes"
      if [ -z "$etiquette" ]; then
        journal "aucune version : pas d'étiquette vX.Y.Z"
        signaler_sonde ok "aucune version"
        return 0
      fi
      version="${etiquette#v}"
      ;;
    *)
      anomalie "canal inconnu : '$VEILLE_EMPLOI_CANAL' (attendu : main ou etiquette)"
      return 1
      ;;
  esac
  cible="$DEPOT_IMAGE:$version"

  # 4. Les données du couple visé. Sans version des données, la version visée attend, et le couple
  # en service se contrôle (M-0004, § 8).
  donnees_visees "$nom_env" "$etiquette" || return 1
  if [ "$ATTENTE_DONNEES" -eq 1 ]; then
    if ! attendre_les_donnees "$nom_env" "$version"; then
      return 1
    fi
    return 0
  fi
  commit="$COMMIT_VISE" etiquette_donnees="$ETIQUETTE_DONNEES"

  # 5. Image. Seules les réponses du registre « cette étiquette n'existe pas » valent attente ; un
  # « not found » quelconque (docker absent, assistant d'identifiants introuvable, dépôt inconnu)
  # est une panne.
  sortie="$(docker pull -q "$cible" 2>&1)" || code=$?
  if [ "$code" -ne 0 ]; then
    if [ "$VEILLE_EMPLOI_CANAL" = etiquette ] && {
      [[ "$sortie" == *"manifest unknown"* ]] \
        || [[ "$sortie" == *"manifest for $cible not found"* ]] \
        || [[ "$sortie" == *"$cible: not found"* ]]
    }; then
      journal "image pas encore publiée : $cible (${sortie//$'\n'/ })"
      return 0
    fi
    journal "docker pull $cible : code $code : ${sortie//$'\n'/ }"
    anomalie "docker pull $cible impossible"
    return 1
  fi

  # 6. Référence ; à un dépôt, le commit de données est sa révision, celle du clone du projet.
  if ! reference="$(docker image inspect -f '{{index .RepoDigests 0}}' "$cible")" \
    || [[ "$reference" != "$DEPOT_IMAGE@sha256:"* ]] \
    || ! [[ "${reference#"$DEPOT_IMAGE@sha256:"}" =~ ^[0-9a-f]{64}$ ]]; then
    journal "référence de $cible inattendue : '${reference:-}'"
    anomalie "référence de $cible illisible"
    return 1
  fi
  if [ "$MODE_DONNEES" = un ] && [ "$DECLAREE" -eq 1 ]; then
    if ! commit="$(revision_de "$reference")"; then
      anomalie "révision de $cible illisible"
      return 1
    fi
    if ! git -C "$donnees" cat-file -e "$commit^{commit}" 2>/dev/null; then
      journal "révision $commit de $cible absente du clone ($donnees) : ses données ne s'y lisent pas"
      anomalie "révision de l'image absente du clone"
      return 1
    fi
  fi

  # 7. Le couple visé et l'état (lib.sh : « - » pour un commit absent, état d'avant la v0.7.0).
  DEPLOYE_IMAGE="" DEPLOYE_VERSION="" DEPLOYE_COMMIT=-
  [ ! -f "$etat/deploye" ] || lire_deploye || true
  lire_echec || journal "$etat/echec illisible : aucun couple n'est tenu pour en échec"

  # Rien de nouveau : le couple visé est en échec ou en service (rien_de_nouveau, qui contrôle
  # l'échec en premier).
  if { [ "$reference" = "$ECHEC_IMAGE" ] && [ "$commit" = "$ECHEC_COMMIT" ]; } \
    || { [ "$reference" = "$DEPLOYE_IMAGE" ] && [ "$commit" = "$DEPLOYE_COMMIT" ]; }; then
    # Le champ configuration, comme deployer.sh l'exige (M-0003, amendé) : un couple en service a un
    # commit dès qu'une commande est déclarée, et le staging ne monte jamais /config.
    if [ "$DECLARE_CONFIG" -eq 1 ]; then
      configuration=montee
      [ "$nom_env" = prod ] || configuration=exemple
    fi
    message="$version en service"
    [ "$commit" = - ] || message="$message, données ${commit:0:12}"
    if ! rien_de_nouveau "$nom_env" "$version" "$reference" "$commit" "$configuration" "$message"; then
      return 1
    fi
    return 0
  fi

  journal "nouveau couple pour $version : $reference, données $commit (en service : ${DEPLOYE_IMAGE:-aucun}, données $DEPLOYE_COMMIT)"
  if [ -n "$etiquette" ] && ! git -C "$clone" checkout --quiet "$etiquette"; then
    anomalie "git checkout $etiquette impossible"
    return 1
  fi
  if [ -n "$etiquette_donnees" ] && ! git -C "$donnees" checkout --quiet "$etiquette_donnees"; then
    journal "clone des données ($donnees) : git checkout $etiquette_donnees impossible"
    anomalie "mise à jour du clone des données impossible"
    return 1
  fi
  if [ "$nom_env" = prod ]; then
    if ! VEILLE_EMPLOI_AVANT_DEPLOIEMENT=1 bash "$clone/deploiement/installer-unites.sh"; then
      anomalie "installation des unités impossible avant $version"
      return 1
    fi
  fi
  [ "$commit" = - ] || option_commit=(--commit-donnees "$commit")
  code=0
  VEILLE_EMPLOI_VERROU_TENU=1 bash "$clone/deploiement/deployer.sh" "$nom_env" "$reference" "$version" \
    "${option_commit[@]}" || code=$?
  return "$code"
}

# Tout le corps est dans main, appelée sur la dernière ligne : bash a lu tout le fichier avant
# que `git merge` ou `git checkout` ne le remplace.
main "$@"; exit $?

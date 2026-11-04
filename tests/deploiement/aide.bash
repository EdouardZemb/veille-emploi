# Aide commune des tests bats du déploiement. Chaque fichier .bats commence par :
#
#   load aide
#   setup() { preparer_environnement; }
#
# Rien n'est écrit hors de $BATS_TEST_TMPDIR : HOME, TMPDIR, états, données et sauvegardes y sont
# redirigés, et les scripts testés tournent sur une copie de `deploiement/` (le « clone
# temporaire »). Les tests des unités, de la sonde, du déploiement et de la sauvegarde réutilisent
# ces aides.
#
# Variables disponibles après `preparer_environnement` :
#   DEPOT    racine du dépôt réel        CLONE    clone temporaire (copie de deploiement/)
#   DOUBLES  dossier des doubles (en tête du PATH)
#   APPELS   journal des appels des doubles
#   CLONE_DONNEES  le clone des données du test : un dépôt git factice, à côté du clone
#                  temporaire (deux dépôts)
#   SOUS_ENV, SOUS_SECRETS, SOUS_CLES, SOUS_CONFIG, SOUS_CONTENU  les chemins de l'instance dans
#                  CLONE_DONNEES, ceux de lib.sh (env, secrets, cles, config, contenu)
#   GIT_REEL la vraie commande git, qu'un double de git en tête du PATH ne masque pas

DEPOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

preparer_environnement() {
  export CLONE="$BATS_TEST_TMPDIR/clone"
  export HOME="$BATS_TEST_TMPDIR/home"
  export TMPDIR="$BATS_TEST_TMPDIR/tmp"
  export VEILLE_EMPLOI_RACINE_ETAT="$BATS_TEST_TMPDIR/etat"
  export VEILLE_EMPLOI_RACINE_DONNEES="$BATS_TEST_TMPDIR/donnees"
  export VEILLE_EMPLOI_RACINE_SAUVEGARDES="$BATS_TEST_TMPDIR/sauvegardes"
  export VEILLE_EMPLOI_DOCKER_CONFIG="$BATS_TEST_TMPDIR/docker"
  unset SOPS_AGE_KEY_FILE VEILLE_EMPLOI_SHM DOCKER_CONFIG VEILLE_EMPLOI_PROJET_SERVEUR

  DOUBLES="$BATS_TEST_TMPDIR/doubles"
  APPELS="$BATS_TEST_TMPDIR/appels.log"
  mkdir -p "$HOME" "$TMPDIR" "$DOUBLES" "$CLONE"
  : >"$APPELS"
  PATH="$DOUBLES:$PATH"
  # Lue maintenant, quand aucun double n'est encore posé.
  GIT_REEL="$(command -v git)"

  # Les secrets et les clés du dépôt réel n'entrent jamais dans un test : chaque test fabrique les
  # siens (preparer_cles_de_test, preparer_secrets_de_test).
  cp -R "$DEPOT/deploiement" "$CLONE/deploiement"
  rm -rf "$CLONE/deploiement/secrets" "$CLONE/deploiement/cles"

  # Deux dépôts (M-0006, § 6) : l'instance vit dans un clone des données factice, un dépôt git de
  # test que charger_env trouve par la surcharge VEILLE_EMPLOI_CLONE_DONNEES. Ses env portent les
  # valeurs d'exemple du rendu ; ni secret ni clé : chaque test fabrique les siens.
  CLONE_DONNEES="$BATS_TEST_TMPDIR/clone-donnees"
  export VEILLE_EMPLOI_CLONE_DONNEES="$CLONE_DONNEES"
  # shellcheck disable=SC2034  # SOUS_ENV est lue par les fichiers .bats
  SOUS_ENV="env" SOUS_SECRETS="secrets" SOUS_CLES="cles" SOUS_CONFIG="config" SOUS_CONTENU="contenu"
  mkdir -p "$CLONE_DONNEES/env"
  printf '%s\n' "VEILLE_EMPLOI_ENV=prod" "VEILLE_EMPLOI_PROJET=veille-emploi" "VEILLE_EMPLOI_PORT=4310" \
    "VEILLE_EMPLOI_URL_PUBLIQUE=https://veille-emploi.exemple.org" "VEILLE_EMPLOI_CANAL=etiquette" \
    >"$CLONE_DONNEES/env/prod.env"
  printf '%s\n' "VEILLE_EMPLOI_ENV=staging" "VEILLE_EMPLOI_PROJET=veille-emploi-staging" "VEILLE_EMPLOI_PORT=4311" \
    "VEILLE_EMPLOI_URL_PUBLIQUE=https://veille-emploi-staging.exemple.org" "VEILLE_EMPLOI_CANAL=main" \
    "VEILLE_EMPLOI_BRANCHE_DONNEES=principal" >"$CLONE_DONNEES/env/staging.env"
  git_donnees init -q -b principal
  git_donnees add -A
  git_donnees commit -q -m "les env d'exemple"
}

# git_donnees <args…> : la vraie commande git dans le clone des données du test, avec une identité
# de test (HOME est celui du test : aucune configuration globale).
git_donnees() {
  "$GIT_REEL" -C "$CLONE_DONNEES" -c user.name=Essai -c user.email=essai@exemple.org "$@"
}

# commit_de_donnees <chemin…> : un commit du clone des données du test, dont la configuration et le
# contenu (SOUS_CONFIG, SOUS_CONTENU) sont exactement un fichier d'exemple à chacun de ces chemins
# (relatifs à la racine du clone) ; tout le reste du clone y est aussi. Son sha dans COMMIT. Le
# clone devient un dépôt git s'il ne l'est pas encore (un dépôt).
commit_de_donnees() {
  local chemin
  [ -d "$CLONE_DONNEES/.git" ] || git_donnees init -q -b principal
  rm -rf "${CLONE_DONNEES:?}/$SOUS_CONFIG" "${CLONE_DONNEES:?}/$SOUS_CONTENU"
  for chemin in "$@"; do
    mkdir -p "$(dirname "$CLONE_DONNEES/$chemin")"
    echo "fichier d'exemple $chemin" >"$CLONE_DONNEES/$chemin"
  done
  git_donnees add -A
  git_donnees commit -q --allow-empty -m "données de test"
  # shellcheck disable=SC2034  # lue par les fichiers .bats
  COMMIT="$(git_donnees rev-parse HEAD)"
}

# --- age et sops -----------------------------------------------------------------------------

# Saute le test si age ou sops manque ; l'image de test pose VEILLE_EMPLOI_TESTS_SANS_SAUT=1, et le test
# échoue alors, pour qu'une image mal construite ne passe pas pour un succès.
exiger_sops_age() {
  local manquants=""
  local outil
  for outil in sops age age-keygen; do
    command -v "$outil" >/dev/null 2>&1 || manquants="$manquants $outil"
  done
  [ -z "$manquants" ] && return 0
  sauter "outils absents :$manquants"
}

# sauter <raison> : saute le test, faute d'un outil ou d'un dossier du système. Dans l'image de test
# (VEILLE_EMPLOI_TESTS_SANS_SAUT=1), le test échoue à la place : rien n'y manque si l'image est bien construite.
sauter() {
  if [ "${VEILLE_EMPLOI_TESTS_SANS_SAUT:-}" = 1 ]; then
    echo "$1 (VEILLE_EMPLOI_TESTS_SANS_SAUT=1 : échec au lieu d'un saut)" >&2
    return 1
  fi
  skip "$1"
}

# Deux identités age de test (serveur et hors ligne), `.sops.yaml` à la racine du clone des données
# avec les deux destinataires, clés publiques dans son dossier des clés (SOUS_CLES) comme dans le
# dépôt, et SOPS_AGE_KEY_FILE sur l'identité du serveur. Sans effet si c'est déjà fait dans ce test.
preparer_cles_de_test() {
  exiger_sops_age
  [ -f "$BATS_TEST_TMPDIR/cles/serveur.txt" ] && return 0
  mkdir -p "$BATS_TEST_TMPDIR/cles" "$CLONE_DONNEES/$SOUS_CLES" "$CLONE_DONNEES/$SOUS_SECRETS"
  export AGE_IDENTITE_SERVEUR="$BATS_TEST_TMPDIR/cles/serveur.txt"
  export AGE_IDENTITE_HORS_LIGNE="$BATS_TEST_TMPDIR/cles/hors-ligne.txt"
  age-keygen -o "$AGE_IDENTITE_SERVEUR" 2>/dev/null
  age-keygen -o "$AGE_IDENTITE_HORS_LIGNE" 2>/dev/null
  export AGE_PUB_SERVEUR AGE_PUB_HORS_LIGNE
  AGE_PUB_SERVEUR="$(age-keygen -y "$AGE_IDENTITE_SERVEUR")"
  AGE_PUB_HORS_LIGNE="$(age-keygen -y "$AGE_IDENTITE_HORS_LIGNE")"
  printf '%s\n' "$AGE_PUB_SERVEUR" >"$CLONE_DONNEES/$SOUS_CLES/serveur.pub"
  printf '%s\n' "$AGE_PUB_HORS_LIGNE" >"$CLONE_DONNEES/$SOUS_CLES/hors-ligne.pub"
  {
    printf 'creation_rules:\n'
    printf '  - path_regex: %s/.*\\.env\\.enc$\n' "$SOUS_SECRETS"
    printf '    age: >-\n      %s,%s\n' "$AGE_PUB_SERVEUR" "$AGE_PUB_HORS_LIGNE"
  } >"$CLONE_DONNEES/.sops.yaml"
  export SOPS_AGE_KEY_FILE="$AGE_IDENTITE_SERVEUR"
}

# preparer_secrets_de_test <env> CLE=valeur… : chiffre ces variables dans
# $CLONE_DONNEES/$SOUS_SECRETS/<env>.env.enc, pour les deux destinataires.
preparer_secrets_de_test() {
  local nom_env="${1:?environnement}"
  shift
  preparer_cles_de_test
  local clair="$BATS_TEST_TMPDIR/clair-$nom_env.env"
  printf '%s\n' "$@" >"$clair"
  (
    cd "$CLONE_DONNEES" || return 1
    # shellcheck disable=SC2094  # le chemin n'est qu'un nom pour la règle sops, pas un fichier lu
    sops encrypt --filename-override "$SOUS_SECRETS/$nom_env.env.enc" \
      --input-type dotenv --output-type dotenv "$clair" >"$SOUS_SECRETS/$nom_env.env.enc"
  )
  rm -f "$clair"
}

# --- lib.sh ----------------------------------------------------------------------------------

# avec_lib '<code bash>' : exécute ce code, sous `set -euo pipefail` comme les vrais scripts, après
# avoir sourcé lib.sh du clone temporaire. Résultat dans $status et $output (voir `run`).
avec_lib() {
  run bash -c 'set -euo pipefail; . "$CLONE/deploiement/lib.sh"; '"$1"
}

# --- Doubles : commandes factices placées en tête du PATH -------------------------------------

# creer_double <nom> [corps] : crée $DOUBLES/<nom>, qui note son appel dans $APPELS (une ligne :
# le nom puis les arguments séparés par des espaces) puis exécute le corps, du code bash
# (par défaut : `exit 0`). Les arguments y sont dans "$@".
#
# Un appel `-K -` (configuration lue sur l'entrée standard, comme le fait `signaler`) est lu avant
# le corps : l'adresse `url = "…"` n'est pas dans les arguments notés, elle l'est à part, dans
# $APPELS.urls (une ligne par appel `-K -`). envois_supervision recolle les deux.
creer_double() {
  local nom="${1:?nom}"
  local corps="${2:-exit 0}"
  cat >"$DOUBLES/$nom" <<EOF
#!/usr/bin/env bash
{ printf '%s' '$nom'; for argument in "\$@"; do printf ' %s' "\$argument"; done; printf '\n'; } >> '$APPELS'
precedent=''
for argument in "\$@"; do
  if [ "\$precedent" = -K ] && [ "\$argument" = - ]; then
    adresse="\$(sed -n 's/^url = "\\(.*\\)"\$/\\1/p')"
    printf '%s\n' "\$adresse" >> '$APPELS.urls'
  fi
  precedent="\$argument"
done
$corps
EOF
  chmod +x "$DOUBLES/$nom"
}

# creer_double_transparent <nom> : note l'appel, puis lance la vraie commande.
creer_double_transparent() {
  local nom="${1:?nom}"
  local reel
  reel="$(PATH="${PATH//"$DOUBLES":/}" command -v "$nom")" || {
    echo "commande réelle introuvable : $nom" >&2
    return 1
  }
  creer_double "$nom" "exec '$reel' \"\$@\""
}

# installer_doubles <nom…> : place en tête du PATH les doubles écrits d'avance dans
# tests/deploiement/doubles/ (docker, git, curl, rclone). Comme ceux de creer_double, ils notent leurs
# appels dans $APPELS ; ils se pilotent par des variables DOUBLE_* (voir l'en-tête de chacun).
installer_doubles() {
  export APPELS
  local nom
  for nom in "$@"; do
    cp "$DEPOT/tests/deploiement/doubles/$nom" "$DOUBLES/$nom"
    chmod +x "$DOUBLES/$nom"
  done
}

# --- État de déploiement (sonde, déploiement) -------------------------------------------------

# contenu_compose_env <env> <image> <version> : le compose.env que deployer.sh écrit pour cette
# version.
contenu_compose_env() {
  local nom_env="$1" sauvegardes="$VEILLE_EMPLOI_RACINE_SAUVEGARDES" port=4310 url=https://veille-emploi.exemple.org
  if [ "$nom_env" = staging ]; then
    sauvegardes="$VEILLE_EMPLOI_RACINE_DONNEES/staging/sauvegardes"
    port=4311
    url=https://veille-emploi-staging.exemple.org
  fi
  printf '%s\n' "VEILLE_EMPLOI_IMAGE=$2" "VEILLE_EMPLOI_VERSION=$3" "VEILLE_EMPLOI_ENV=$nom_env" \
    "VEILLE_EMPLOI_PORT=$port" "VEILLE_EMPLOI_DONNEES=$VEILLE_EMPLOI_RACINE_DONNEES/$nom_env/donnees" \
    "VEILLE_EMPLOI_SAUVEGARDES=$sauvegardes" "VEILLE_EMPLOI_URL_PUBLIQUE=$url"
}

# en_service <env> <image> <version> : l'état laissé par un déploiement réussi de cette version
# (deploye, compose.env), et l'application qui tourne pour les doubles de docker et de curl.
en_service() {
  local etat="$VEILLE_EMPLOI_RACINE_ETAT/$1"
  mkdir -p "$etat"
  contenu_compose_env "$1" "$2" "$3" >"$etat/compose.env"
  cp "$etat/compose.env" "$BATS_TEST_TMPDIR/en-service.env"
  echo "$2 $3" >"$etat/deploye"
}

# poser_donnees <env> : un fichier dans le dossier de données de cet environnement, comme celui d'une
# application qui a déjà servi. Avec les sauvegardes, deployer.sh refuse un dossier vide quand une
# version est déployée : un test qui part de en_service, sans déploiement réel, doit donc le poser.
poser_donnees() {
  local dossier="$VEILLE_EMPLOI_RACINE_DONNEES/$1/donnees"
  mkdir -p "$dossier"
  echo "données de test" >"$dossier/base"
}

# --- Stock d'images et de conteneurs du double de docker (ménage des images) -----------------

# image_de <c> : l'identifiant d'une image de test, « sha256: » puis 64 fois le caractère <c> (un
# chiffre hexadécimal).
image_de() {
  local suite
  printf -v suite '%64s' ''
  printf 'sha256:%s\n' "${suite// /$1}"
}

# empreinte_de <c> [dépôt] : une empreinte de test, <dépôt>@sha256: puis 32 fois <c> et 32 fois 0
# (défaut : le dépôt du projet). Une empreinte n'est jamais l'identifiant d'une image : le ménage
# ne doit pas confondre les deux.
empreinte_de() {
  local depot="${2:-}" moitie
  [ -n "$depot" ] || depot=ghcr.io/edouardzemb/veille-emploi
  printf -v moitie '%32s' ''
  printf '%s@sha256:%s%s\n' "$depot" "${moitie// /$1}" "${moitie// /0}"
}

# poser_image <c> <créée> <noms> <empreintes> : ajoute au stock du double de docker l'image
# image_de <c>, créée à cette date (RFC 3339, la forme de .Created), avec ces noms et ces
# empreintes, séparés par des espaces (une chaîne vide : aucun).
poser_image() {
  printf '%s|%s|%s|%s\n' "$(image_de "$1")" "$2" "$3" "$4" >>"$(dirname "$APPELS")/images"
}

# poser_conteneur <id> <c> : ajoute au stock du double un conteneur, arrêté ou non, de l'image
# image_de <c>.
poser_conteneur() {
  printf '%s %s\n' "$1" "$(image_de "$2")" >>"$(dirname "$APPELS")/conteneurs"
}

# envois_supervision : les appels de curl vers un service de supervision (`signaler`), un par ligne,
# dans la forme « curl … --data-raw <message> <adresse> ». L'adresse n'est jamais dans les arguments
# notés dans $APPELS (`signaler` la donne à curl sur l'entrée standard, `-K -`) : elle vient de
# $APPELS.urls, que les doubles de curl remplissent. Un test qui remet $APPELS à zéro ne vide pas ce
# fichier : on prend les dernières adresses, une par appel `-K -` encore dans $APPELS.
envois_supervision() {
  local lignes=() urls=() ligne i=0
  mapfile -t lignes < <(appels_de curl | grep -E ' -K -$' || true)
  [ "${#lignes[@]}" -gt 0 ] || return 0
  mapfile -t urls < <(tail -n "${#lignes[@]}" "$APPELS.urls")
  for ligne in "${lignes[@]}"; do
    printf '%s %s\n' "${ligne% -K -}" "${urls[i]}"
    i=$((i + 1))
  done
}

# appels_de <nom> : les lignes du journal pour cette commande.
appels_de() {
  grep -E "^$1( |\$)" "$APPELS" || true
}

# nombre_d_appels <nom>
nombre_d_appels() {
  appels_de "$1" | grep -c . || true
}

# ligne_de <motif> : numéro de la première ligne du journal des appels qui contient ce texte.
ligne_de() {
  grep -nF -- "$1" "$APPELS" | head -n 1 | cut -d: -f1
}

# aucune_ligne <regex> <fichier…> : échoue si la regex (étendue) apparaît dans un des fichiers. Un
# `! grep` seul ne ferait pas échouer le test s'il n'est pas la dernière commande.
aucune_ligne() {
  if grep -qE -- "$1" "${@:2}"; then
    echo "motif présent : $1" >&2
    return 1
  fi
}

# --- Horloge des instantanés (déploiement, sauvegarde) ----------------------------------------

# horloge_qui_avance : l'horodatage d'un instantané (à la seconde) avance à chaque appel. Des
# déploiements ou des sauvegardes qui se suivent en moins d'une seconde, comme ici avec des doubles,
# viseraient sinon le même dossier, que la commande de l'image refuse d'écraser. Les autres appels de
# `date` sont ceux de la vraie.
horloge_qui_avance() {
  local reel
  reel="$(command -v date)"
  cat >"$DOUBLES/date" <<EOF
#!/usr/bin/env bash
if [ "\$*" = '-u +%Y%m%dT%H%M%SZ' ]; then
  n=\$(( \$(cat '$BATS_TEST_TMPDIR/horloge' 2>/dev/null || echo 0) + 1 ))
  echo "\$n" >'$BATS_TEST_TMPDIR/horloge'
  printf '20261015T%06dZ\n' "\$n"
else
  exec '$reel' "\$@"
fi
EOF
  chmod +x "$DOUBLES/date"
}

# --- Verrou tenu par un autre processus (sauvegarde, restauration, lib) -------------------------

# tenir_le_verrou <fichier> : un autre script tient ce verrou jusqu'à relacher_le_verrou.
tenir_le_verrou() {
  rm -f "$BATS_TEST_TMPDIR/verrou-tenu" "$BATS_TEST_TMPDIR/relacher"
  mkdir -p "$(dirname "$1")"
  (
    exec 9>"$1"
    flock 9
    : >"$BATS_TEST_TMPDIR/verrou-tenu"
    # au plus 60 s : un test qui échoue ne laisse pas ce processus derrière lui
    for _ in {1..600}; do
      [ -e "$BATS_TEST_TMPDIR/relacher" ] && break
      sleep 0.1
    done
  ) >/dev/null 2>&1 3>&- &
  TENANT=$!
  while [ ! -e "$BATS_TEST_TMPDIR/verrou-tenu" ]; do sleep 0.1; done
}

relacher_le_verrou() {
  : >"$BATS_TEST_TMPDIR/relacher"
  wait "$TENANT"
}

# abandonner_le_verrou : à appeler dans teardown() : un test qui échoue avant relacher_le_verrou ne
# laisse pas le processus qui tient le verrou derrière lui.
abandonner_le_verrou() {
  [ -z "${TENANT:-}" ] || kill "$TENANT" 2>/dev/null || true
}

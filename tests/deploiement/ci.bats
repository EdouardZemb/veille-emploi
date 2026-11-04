#!/usr/bin/env bats
# deploiement/ci/verifier-image.sh : la vérification de l'image que la CI vient de lancer (action
# modele-image-construire) : santé, révision, environnement, puis un instantané dans le conteneur
# et sa vérification, puis l'exemple du dépôt.
#
# curl et docker sont des doubles : curl répond SANTE_CORPS (connexion refusée s'il est vide)
# et docker simule les commandes de l'image : `docker exec <conteneur> <commande…> <dossier>`, avec
# les codes de DOUBLE_SAUVEGARDER_CODE et DOUBLE_VERIFIER_CODE, et `docker run … veille-emploi:ci
# <commande…> <point de montage>`, avec ceux de DOUBLE_CONFIG_CODE et DOUBLE_CONTENU_CODE.

# Chaque test tourne dans son propre processus : ses `export` ne fuient pas (SC2030, SC2031). Le
# corps d'un double est entre apostrophes : il se développe quand le double tourne (SC2016).
# shellcheck disable=SC2016,SC2030,SC2031

bats_require_minimum_version 1.5.0

load aide

REVISION=0123456789abcdef0123456789abcdef01234567
AUTRE_REVISION=fedcba9876543210fedcba9876543210fedcba98
# Les options des conteneurs jetables de lib.sh.
JETABLES="--user 1000:1000 --read-only --tmpfs /tmp --cap-drop ALL --security-opt no-new-privileges:true --memory 384m"

# corps <environnement> <révision> [statut] : un corps de santé.
corps() {
  printf '{"statut":"%s","environnement":"%s","version":"dev","revision":"%s"}' "${3:-ok}" "$1" "$2"
}

setup() {
  preparer_environnement
  export VEILLE_EMPLOI_SANTE_DELAI=0
  SANTE_CORPS="$(corps ci "$REVISION")"
  export SANTE_CORPS
  creer_double curl '[ -n "${SANTE_CORPS:-}" ] || { echo "curl: (7) Failed to connect to 127.0.0.1" >&2; exit 7; }
printf "%s\n" "$SANTE_CORPS"'
  # Les commandes de l'image sont celles d'un projet.env de test, pas celles que le modèle sème
  # (R11) : verifier-image.sh les lit, il ne les connaît pas.
  printf '%s\n' 'SAUVEGARDER=outil sauvegarder --forme dossier' 'VERIFIER=outil verifier' \
    >"$CLONE/deploiement/projet.env"
  creer_double docker 'case "${1:-}" in
  exec)
    case "${3:-} ${4:-}" in
      "outil sauvegarder") exit "${DOUBLE_SAUVEGARDER_CODE:-0}" ;;
      "outil verifier")
        [ -z "${DOUBLE_VERIFIER_SORTIE:-}" ] || printf "%s\n" "$DOUBLE_VERIFIER_SORTIE"
        exit "${DOUBLE_VERIFIER_CODE:-0}"
        ;;
    esac
    ;;
  run)
    case "$*" in
      *" veille-emploi:ci outil verifier_config /config")
        [ -z "${DOUBLE_CONFIG_SORTIE:-}" ] || printf "%s\n" "$DOUBLE_CONFIG_SORTIE"
        exit "${DOUBLE_CONFIG_CODE:-0}"
        ;;
      *" veille-emploi:ci outil verifier_contenu /contenu") exit "${DOUBLE_CONTENU_CODE:-0}" ;;
    esac
    ;;
esac
echo "double docker : commande inattendue $*" >&2
exit 125'
}

verifier_image() {
  run bash "$CLONE/deploiement/ci/verifier-image.sh" "$@"
}

# declarer_commandes <commande…> : deploiement/projet.env ne déclare que ces commandes de l'instance,
# chacune avec des mots d'exemple (VERIFIER_CONFIG=outil verifier_config…), à côté
# des commandes de sauvegarde du test.
declarer_commandes() {
  local commande
  local -a lignes=('SAUVEGARDER=outil sauvegarder --forme dossier' 'VERIFIER=outil verifier')
  for commande in "$@"; do
    lignes+=("$commande=outil ${commande,,}")
  done
  printf '%s\n' "# Réglages du test" "${lignes[@]}" >"$CLONE/deploiement/projet.env"
}

# exemple_de <chemin…> : les dossiers d'exemple du dépôt (exemple/, exemple-contenu/) ne portent que
# ces fichiers, relatifs à la racine du dépôt.
exemple_de() {
  local chemin
  rm -rf "$CLONE/exemple" "$CLONE/exemple-contenu"
  for chemin in "$@"; do
    mkdir -p "$(dirname "$CLONE/$chemin")"
    echo "fichier d'exemple $chemin" >"$CLONE/$chemin"
  done
}

# lances_par_docker : les appels `docker run` du double, un par ligne (l'exemple ;
# l'instantané passe par `docker exec`).
lances_par_docker() {
  appels_de docker | grep '^docker run ' || true
}

# sur_l_instance <commande…> : ce que l'étape 5 lance après l'exemple quand ces commandes sont
# déclarées et que l'instance suit la règle des paires, une ligne par commande, chacune précédée
# d'un saut de ligne, pour suivre les lancements de l'exemple : à un dépôt, chaque commande sur son
# dossier de l'instance ; à deux dépôts, rien.
sur_l_instance() {
  :
}

@test "verifier_image_conforme" {
  verifier_image veille-emploi "$REVISION"
  [ "$status" -eq 0 ]
  [ "$(appels_de curl)" = "curl -fsS -m 5 http://127.0.0.1:8460/sante" ]
  # l'instantané puis sa vérification, dans le conteneur, mot à mot
  [ "$(appels_de docker)" = "docker exec veille-emploi outil sauvegarder --forme dossier /tmp/instantane
docker exec veille-emploi outil verifier /tmp/instantane" ]
  [[ "$output" == *"instantané conforme"* ]]
}

@test "verifier_image_attend_la_sante" {
  # deux refus de connexion, une santé « ko », puis ok
  local essais="$BATS_TEST_TMPDIR/essais"
  creer_double curl 'n="$(cat "'"$essais"'" 2>/dev/null || echo 0)"
n=$((n + 1))
echo "$n" >"'"$essais"'"
if [ "$n" -le 2 ]; then echo "curl: (7) Failed to connect" >&2; exit 7; fi
if [ "$n" -eq 3 ]; then printf "%s\n" "{\"statut\":\"ko\"}"; exit 0; fi
printf "%s\n" "$SANTE_CORPS"'
  verifier_image veille-emploi "$REVISION"
  [ "$status" -eq 0 ]
  [ "$(nombre_d_appels curl)" -eq 4 ]
}

@test "verifier_image_sante_jamais_conforme_echoue" {
  # SECONDS compte en secondes entières : avec une limite de 1 s, la frontière d'une seconde peut
  # tomber pendant le premier essai et n'en laisser qu'un. Avec 2 s, l'écart lu après un essai de
  # moins d'une seconde vaut au plus 1 : deux essais au moins, où que tombe la frontière (R19).
  export VEILLE_EMPLOI_SANTE_ATTENTE=2 VEILLE_EMPLOI_SANTE_DELAI=0.1
  for cas in refus ko; do
    : >"$APPELS"
    if [ "$cas" = refus ]; then
      export SANTE_CORPS=""
    else
      SANTE_CORPS="$(corps ci "$REVISION" ko)"
      export SANTE_CORPS
    fi
    verifier_image veille-emploi "$REVISION"
    [ "$status" -eq 1 ]
    [[ "$output" == *"santé non conforme après"* ]]
    [ "$(nombre_d_appels curl)" -ge 2 ]
    [ "$(nombre_d_appels docker)" -eq 0 ]
  done
}

@test "verifier_image_revision_differente_echoue" {
  for revision in "$AUTRE_REVISION" local ""; do
    : >"$APPELS"
    SANTE_CORPS="$(corps ci "$revision")"
    export SANTE_CORPS
    verifier_image veille-emploi "$REVISION"
    [ "$status" -eq 1 ]
    [[ "$output" == *"révision servie non conforme : attendue $REVISION"* ]]
    # la santé était ok : pas d'attente, et pas d'instantané
    [ "$(nombre_d_appels curl)" -eq 1 ]
    [ "$(nombre_d_appels docker)" -eq 0 ]
  done
  # sans révision du tout
  export SANTE_CORPS='{"statut":"ok","environnement":"ci","version":"dev"}'
  verifier_image veille-emploi "$REVISION"
  [ "$status" -eq 1 ]
  [[ "$output" == *"révision servie non conforme"* ]]
}

@test "verifier_image_environnement_autre_que_ci_echoue" {
  for environnement in prod staging dev CI ""; do
    : >"$APPELS"
    SANTE_CORPS="$(corps "$environnement" "$REVISION")"
    export SANTE_CORPS
    verifier_image veille-emploi "$REVISION"
    [ "$status" -eq 1 ]
    [[ "$output" == *"environnement servi non conforme : attendu ci"* ]]
    [ "$(nombre_d_appels docker)" -eq 0 ]
  done
}

@test "verifier_image_sauvegarde_non_conforme_echoue" {
  # verifier rend 2 : non conforme, sa sortie au journal
  export DOUBLE_VERIFIER_CODE=2 DOUBLE_VERIFIER_SORTIE="MARQUE absente"
  verifier_image veille-emploi "$REVISION"
  [ "$status" -eq 1 ]
  [[ "$output" == *"instantané non conforme (verifier : code 2) : MARQUE absente"* ]]
  [ "$(nombre_d_appels docker)" -eq 2 ]

  # verifier rend autre chose : la vérification n'a pas eu lieu
  for code in 64 1 125; do
    : >"$APPELS"
    export DOUBLE_VERIFIER_CODE="$code"
    verifier_image veille-emploi "$REVISION"
    [ "$status" -eq 1 ]
    [[ "$output" == *"vérification impossible (verifier : code $code)"* ]]
  done

  # sauvegarder échoue : rien à vérifier
  : >"$APPELS"
  export DOUBLE_VERIFIER_CODE=0 DOUBLE_SAUVEGARDER_CODE=1
  verifier_image veille-emploi "$REVISION"
  [ "$status" -eq 1 ]
  [[ "$output" == *"instantané impossible (sauvegarder : code 1)"* ]]
  [ "$(appels_de docker)" = "docker exec veille-emploi outil sauvegarder --forme dossier /tmp/instantane" ]
}

@test "verifier_image_sans_commande_de_projet_env_echoue" {
  for absente in SAUVEGARDER VERIFIER; do
    : >"$APPELS"
    printf '%s\n' 'SAUVEGARDER=outil sauvegarder' 'VERIFIER=outil verifier' \
      | grep -v "^$absente=" >"$CLONE/deploiement/projet.env"
    verifier_image veille-emploi "$REVISION"
    [ "$status" -eq 1 ]
    [[ "$output" == *"réglage $absente absent"* ]]
    [[ "$output" == *"pas de commande $absente lisible"* ]]
    # les deux commandes sont lues avant de lancer quoi que ce soit
    [ "$(nombre_d_appels docker)" -eq 0 ]
  done
}

@test "verifier_image_refuse_un_usage_invalide" {
  for arguments in "" "veille-emploi" "veille-emploi $REVISION en-trop" "veille-emploi local" "veille-emploi ${REVISION^^}" "-x $REVISION"; do
    : >"$APPELS"
    # shellcheck disable=SC2086  # les arguments sont découpés exprès
    verifier_image $arguments
    [ "$status" -eq 64 ]
    [ "$(nombre_d_appels curl)" -eq 0 ]
    [ "$(nombre_d_appels docker)" -eq 0 ]
  done
}

# L'exemple du dépôt (M-0003) : chaque commande de l'instance que déclare projet.env tourne sur son
# dossier d'exemple, dans un conteneur jetable de l'image construite, sans réseau, le dossier en
# lecture seule, comme le serveur la lance sur un instantané. 0 exigé.
@test "ci : VERIFIER_CONFIG sur exemple/" {
  local code
  local config="docker run --rm --network none $JETABLES -v $CLONE/exemple:/config:ro veille-emploi:ci outil verifier_config /config"
  local contenu="docker run --rm --network none $JETABLES -v $CLONE/exemple-contenu:/contenu:ro veille-emploi:ci outil verifier_contenu /contenu"
  declarer_commandes VERIFIER_CONFIG
  exemple_de exemple/profil.yml
  verifier_image veille-emploi "$REVISION"
  [ "$status" -eq 0 ]
  [ "$(lances_par_docker)" = "$config$(sur_l_instance VERIFIER_CONFIG)" ]
  [[ "$output" == *"exemple de configuration conforme (VERIFIER_CONFIG : code 0)"* ]]
  [[ "$output" == *"image conforme"* ]]
  # après l'instantané et sa vérification, dans le conteneur
  [ "$(appels_de docker | head -n 2)" = "docker exec veille-emploi outil sauvegarder --forme dossier /tmp/instantane
docker exec veille-emploi outil verifier /tmp/instantane" ]

  # les deux commandes, chacune sur son dossier ; un README.md plus bas compte comme un fichier
  : >"$APPELS"
  declarer_commandes VERIFIER_CONFIG VERIFIER_CONTENU
  exemple_de exemple/profil.yml exemple-contenu/pages/README.md
  verifier_image veille-emploi "$REVISION"
  [ "$status" -eq 0 ]
  [ "$(lances_par_docker)" = "$config
$contenu$(sur_l_instance VERIFIER_CONFIG VERIFIER_CONTENU)" ]
  [[ "$output" == *"exemple de contenu conforme (VERIFIER_CONTENU : code 0)"* ]]

  # 2 : l'exemple n'est pas conforme, et la sortie de la commande le dit
  : >"$APPELS"
  export DOUBLE_CONFIG_CODE=2 DOUBLE_CONFIG_SORTIE="version de schéma inconnue"
  verifier_image veille-emploi "$REVISION"
  [ "$status" -eq 1 ]
  [[ "$output" == *"exemple de configuration non conforme (VERIFIER_CONFIG : code 2) : version de schéma inconnue"* ]]
  [[ "$output" == *"image non conforme : exemple/ non conforme (VERIFIER_CONFIG : code 2)"* ]]
  [ "$(lances_par_docker)" = "$config" ]
  # 64 (l'image ne connaît pas la commande) ou tout autre code : la vérification n'a pas eu lieu
  for code in 64 1 125; do
    export DOUBLE_CONFIG_CODE="$code"
    verifier_image veille-emploi "$REVISION"
    [ "$status" -eq 1 ]
    [[ "$output" == *"vérification impossible (VERIFIER_CONFIG : code $code)"* ]]
    [[ "$output" == *"image non conforme : vérification de exemple/ impossible (VERIFIER_CONFIG)"* ]]
  done
  # le contenu, de même
  : >"$APPELS"
  export DOUBLE_CONFIG_CODE=0 DOUBLE_CONTENU_CODE=2
  verifier_image veille-emploi "$REVISION"
  [ "$status" -eq 1 ]
  [[ "$output" == *"image non conforme : exemple-contenu/ non conforme (VERIFIER_CONTENU : code 2)"* ]]
  [ "$(lances_par_docker)" = "$config
$contenu" ]

  # rien de déclaré, aucun dossier d'exemple : rien à lancer, comme avant les commandes de l'instance
  : >"$APPELS"
  declarer_commandes
  exemple_de
  verifier_image veille-emploi "$REVISION"
  [ "$status" -eq 0 ]
  [ -z "$(lances_par_docker)" ]
}

# Une commande déclarée sans son dossier d'exemple refuse, avant tout conteneur : la CI ne peut pas
# la prouver. Un dossier qui ne porte que son README.md compte comme absent.
@test "ci : une commande sans son exemple refuse" {
  local cas fichiers commandes attendus message
  local -a messages
  # <fichiers des exemples>|<commandes déclarées>|<messages attendus, séparés par des points-virgules>
  for cas in \
    "|VERIFIER_CONFIG|VERIFIER_CONFIG sans exemple/" \
    "|VERIFIER_CONTENU|VERIFIER_CONTENU sans exemple-contenu/" \
    "|VERIFIER_CONFIG VERIFIER_CONTENU|VERIFIER_CONFIG sans exemple/;VERIFIER_CONTENU sans exemple-contenu/" \
    "exemple/README.md|VERIFIER_CONFIG|VERIFIER_CONFIG sans exemple/" \
    "exemple-contenu/page.md|VERIFIER_CONFIG VERIFIER_CONTENU|VERIFIER_CONFIG sans exemple/" \
    "exemple/profil.yml|VERIFIER_CONTENU|VERIFIER_CONTENU sans exemple-contenu/;exemple/ présent, sans VERIFIER_CONFIG : non vérifié"; do
    IFS='|' read -r fichiers commandes attendus <<<"$cas"
    # shellcheck disable=SC2086  # listes séparées par des espaces, voulues
    exemple_de $fichiers
    # shellcheck disable=SC2086
    declarer_commandes $commandes
    : >"$APPELS"
    verifier_image veille-emploi "$REVISION"
    [ "$status" -eq 1 ]
    IFS=';' read -r -a messages <<<"$attendus"
    for message in "${messages[@]}"; do
      [[ "$output" == *"$message"* ]]
    done
    [[ "$output" == *"exemple non conforme : chaque commande déclarée dans deploiement/projet.env va avec son dossier d'exemple"* ]]
    # aucune commande de l'instance n'est lancée tant qu'une commande n'a pas son dossier
    [ -z "$(lances_par_docker)" ]
  done
}

# Un dossier d'exemple sans sa commande ne refuse pas : rien ne le vérifie, et le journal le dit. Un
# projet qui ne déclare encore aucune commande de l'instance garde sa CI. Un dossier qui ne porte que
# son README.md compte comme absent ; un README.md plus bas compte.
@test "ci : un exemple sans sa commande n'est pas vérifié" {
  local cas fichiers commandes attendus lance message
  local -a messages
  local config="docker run --rm --network none $JETABLES -v $CLONE/exemple:/config:ro veille-emploi:ci outil verifier_config /config"
  # <fichiers>|<commandes déclarées>|<messages attendus, séparés par des points-virgules>|<lancé>
  for cas in \
    "exemple/profil.yml||exemple/ présent, sans VERIFIER_CONFIG : non vérifié|" \
    "exemple-contenu/page.md||exemple-contenu/ présent, sans VERIFIER_CONTENU : non vérifié|" \
    "exemple/sous/README.md||exemple/ présent, sans VERIFIER_CONFIG : non vérifié|" \
    "exemple/profil.yml exemple-contenu/page.md||exemple/ présent, sans VERIFIER_CONFIG : non vérifié;exemple-contenu/ présent, sans VERIFIER_CONTENU : non vérifié|" \
    "exemple/profil.yml exemple-contenu/page.md|VERIFIER_CONFIG|exemple-contenu/ présent, sans VERIFIER_CONTENU : non vérifié|config"; do
    IFS='|' read -r fichiers commandes attendus lance <<<"$cas"
    # shellcheck disable=SC2086  # listes séparées par des espaces, voulues
    exemple_de $fichiers
    # shellcheck disable=SC2086
    declarer_commandes $commandes
    : >"$APPELS"
    verifier_image veille-emploi "$REVISION"
    [ "$status" -eq 0 ]
    IFS=';' read -r -a messages <<<"$attendus"
    for message in "${messages[@]}"; do
      [[ "$output" == *"$message"* ]]
    done
    [[ "$output" == *"image conforme"* ]]
    # seule une commande déclarée, sur son dossier, lance un conteneur
    if [ "$lance" = config ]; then
      [ "$(lances_par_docker)" = "$config$(sur_l_instance VERIFIER_CONFIG)" ]
    else
      [ -z "$(lances_par_docker)" ]
    fi
  done
  # un dossier qui ne porte que son README.md, sans commande : rien à dire
  exemple_de exemple/README.md exemple-contenu/README.md
  declarer_commandes
  : >"$APPELS"
  verifier_image veille-emploi "$REVISION"
  [ "$status" -eq 0 ]
  [[ "$output" != *"non vérifié"* ]]
  [ -z "$(lances_par_docker)" ]
}

# À deux dépôts, l'instance est dans le dépôt de données, dont la CI la vérifie : l'étape 5 ne tourne
# pas, même quand un dossier du même nom traîne dans le dépôt de code.
@test "ci : à deux dépôts, l'instance n'est pas lue" {
  local config="docker run --rm --network none $JETABLES -v $CLONE/exemple:/config:ro veille-emploi:ci outil verifier_config /config"
  local contenu="docker run --rm --network none $JETABLES -v $CLONE/exemple-contenu:/contenu:ro veille-emploi:ci outil verifier_contenu /contenu"
  declarer_commandes VERIFIER_CONFIG VERIFIER_CONTENU
  exemple_de exemple/profil.yml exemple-contenu/page.md
  mkdir -p "$CLONE/$SOUS_CONFIG" "$CLONE/instance/config"
  echo "fichier hors du dépôt de données" >"$CLONE/$SOUS_CONFIG/profil.yml"
  echo "fichier hors du dépôt de données" >"$CLONE/instance/config/profil.yml"
  verifier_image veille-emploi "$REVISION"
  [ "$status" -eq 0 ]
  [ "$(lances_par_docker)" = "$config
$contenu" ]
  [[ "$output" != *"de l'instance"* ]]
  [[ "$output" == *"image conforme"* ]]
}

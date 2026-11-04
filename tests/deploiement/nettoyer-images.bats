#!/usr/bin/env bats
# nettoyer-images.sh : ce qui est une image du projet, ce qui est gardé (l'état des deux
# environnements, les conteneurs, la marge), les verrous, les retraits, les abstentions ; puis le
# ménage des instantanés des données de l'environnement (M-0004, § 8).
#
# docker est un double (tests/deploiement/doubles/docker) : son stock d'images et de conteneurs est
# posé par poser_image et poser_conteneur (aide.bash). Il refuse, et le note dans refus-images, tout
# retrait que le ménage ne doit jamais demander : une image hors du dépôt ou sans référence, une
# image qu'un conteneur utilise, une option, un `prune`, un `rmi`.

# Chaque test tourne dans son propre processus : les `export` d'un test ne fuient pas dans les
# autres, comme le veut le pilotage des doubles.
# shellcheck disable=SC2030,SC2031

bats_require_minimum_version 1.5.0

load aide

setup() {
  preparer_environnement
  installer_doubles docker
  DEPOT_DU_PROJET=ghcr.io/edouardzemb/veille-emploi
  STOCK="$BATS_TEST_TMPDIR/images"
  REFUS="$BATS_TEST_TMPDIR/refus-images"
}

teardown() {
  abandonner_le_verrou
  # les instantanés des données sont en lecture seule : bats doit pouvoir retirer le dossier du test
  chmod -R u+rwX "$BATS_TEST_TMPDIR" 2>/dev/null || true
}

nettoyer() {
  run bash "$CLONE/deploiement/nettoyer-images.sh" "$@"
}

# etat <env> <fichier> <contenu> : un fichier d'état de cet environnement (vide, sans contenu).
etat() {
  local dossier="$VEILLE_EMPLOI_RACINE_ETAT/$1"
  mkdir -p "$dossier"
  if [ -n "$3" ]; then
    printf '%s\n' "$3" >"$dossier/$2"
  else
    : >"$dossier/$2"
  fi
}

# vider : un stock, un état et un journal des appels neufs, pour le cas suivant d'une boucle. Les
# instantanés des données de l'état sont en lecture seule : les droits d'abord.
vider() {
  chmod -R u+rwX "$VEILLE_EMPLOI_RACINE_ETAT" 2>/dev/null || true
  rm -rf "$VEILLE_EMPLOI_RACINE_ETAT" "$STOCK" "$BATS_TEST_TMPDIR/conteneurs" "$REFUS"
  : >"$APPELS"
}

# cinq_images : cinq images du dépôt, de 1 (la plus ancienne) à 5 (la plus récente, :main), que rien
# ne protège. Sans autre protection, 1 et 2 partent, et 3, 4 et 5 restent en marge.
cinq_images() {
  local c
  for c in 1 2 3 4; do
    poser_image "$c" "2026-10-0${c}T10:00:00Z" "" "$(empreinte_de "$c")"
  done
  poser_image 5 2026-10-05T10:00:00Z "$DEPOT_DU_PROJET:main" "$(empreinte_de 5)"
}

# restent <c…> : ces images sont encore dans le stock.
restent() {
  local c
  for c in "$@"; do
    grep -q "^$(image_de "$c")|" "$STOCK" || {
      echo "image $c retirée" >&2
      return 1
    }
  done
}

# parties <c…> : ces images ont quitté le stock.
parties() {
  local c
  for c in "$@"; do
    if grep -q "^$(image_de "$c")|" "$STOCK"; then
      echo "image $c encore là" >&2
      return 1
    fi
  done
}

# retraits : les appels `docker image rm`, un par ligne.
retraits() {
  appels_de docker | grep -E '^docker image rm( |$)' || true
}

# retrait_de <c…> : les lignes de `retraits` qui retirent ces images, dans cet ordre.
retrait_de() {
  local c
  for c in "$@"; do
    printf 'docker image rm %s\n' "$(image_de "$c")"
  done
}

# journal_dit <ligne> : le journal du dernier `run` a cette ligne, à l'heure près.
journal_dit() {
  printf '%s\n' "$output" | sed -E 's/^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9:]{8}Z //' | grep -Fxq -- "$1" || {
    echo "ligne absente du journal : $1" >&2
    return 1
  }
}

# annule : le dernier `run` a annulé le ménage, sans rien retirer.
annule() {
  [ "$status" -eq 1 ]
  [ -z "$(retraits)" ]
  [[ "$output" == *"ménage des images annulé, rien n'est retiré : "* ]]
}

# bilan <texte> : la ligne de bilan du ménage.
bilan() {
  journal_dit "ménage des images : $1"
}

# --- ce qui est une image du projet ----------------------------------------------------------

@test "retire_seulement_les_images_du_depot" {
  # quatre images du dépôt que rien ne protège : la plus ancienne part, les trois autres sont la
  # marge
  poser_image 1 2026-10-01T10:00:00Z "$DEPOT_DU_PROJET:0.1.0" "$(empreinte_de 1)"
  poser_image 2 2026-10-02T10:00:00Z "" "$(empreinte_de 2)"
  poser_image 3 2026-10-03T10:00:00Z "$DEPOT_DU_PROJET:0.2.0" "$(empreinte_de 3)"
  poser_image 4 2026-10-04T10:00:00Z "$DEPOT_DU_PROJET:main" "$(empreinte_de 4)"
  # plus anciennes encore, mais à laisser : une image étrangère, une qui a aussi un nom ailleurs,
  # une sans référence, et deux aux noms voisins du dépôt
  poser_image 5 2026-09-01T10:00:00Z docker.io/library/busybox:1.36 \
    "$(empreinte_de 5 docker.io/library/busybox)"
  poser_image 6 2026-09-02T10:00:00Z ghcr.io/autre/projet:1 "$(empreinte_de 6)"
  poser_image 7 2026-09-03T10:00:00Z "" ""
  poser_image 8 2026-09-04T10:00:00Z "$DEPOT_DU_PROJET-autre:1" "$(empreinte_de 8 "$DEPOT_DU_PROJET-autre")"
  poser_image 9 2026-09-05T10:00:00Z "$DEPOT_DU_PROJET/sous:1" "$(empreinte_de 9 "$DEPOT_DU_PROJET/sous")"
  nettoyer prod
  [ "$status" -eq 0 ]
  [ "$(retraits)" = "$(retrait_de 1)" ]
  parties 1
  restent 2 3 4 5 6 7 8 9
  [ ! -e "$REFUS" ]
  journal_dit "image retirée : 111111111111 ($DEPOT_DU_PROJET:0.1.0 $(empreinte_de 1))"
  bilan "1 retirée, 3 gardées (0 par l'état, 0 par un conteneur, 3 en marge)"
}

@test "depot_de_test_refuse_tout_sauf_un_registre_local" {
  cinq_images
  local valeur
  for valeur in ghcr.io/edouardzemb/autre docker.io/x/y localhost/x '' $'localhost:5000/x\nghcr.io/y'; do
    echo "cas : '$valeur'"
    : >"$APPELS"
    VEILLE_EMPLOI_DEPOT_IMAGE="$valeur" nettoyer prod
    [ "$status" -eq 64 ]
    [ ! -s "$APPELS" ]
    journal_dit "VEILLE_EMPLOI_DEPOT_IMAGE refusée : seul un registre de la machine (localhost:<port>/…) est accepté"
  done
  restent 1 2 3 4 5
}

@test "depot_de_test_avec_un_port" {
  local depot=localhost:5000/edouardzemb/veille-emploi
  poser_image 1 2026-10-01T10:00:00Z "" "$(empreinte_de 1 "$depot")"
  poser_image 2 2026-10-02T10:00:00Z "" "$(empreinte_de 2 "$depot")"
  poser_image 3 2026-10-03T10:00:00Z "" "$(empreinte_de 3 "$depot")"
  poser_image 4 2026-10-04T10:00:00Z "$depot:main" "$(empreinte_de 4 "$depot")"
  # plus anciennes, hors du dépôt de test : un nom voisin, et le dépôt GHCR du projet
  poser_image 5 2026-09-01T10:00:00Z "$depot-autre:1" "$(empreinte_de 5 "$depot-autre")"
  poser_image 6 2026-09-02T10:00:00Z "$DEPOT_DU_PROJET:0.1.0" "$(empreinte_de 6)"
  VEILLE_EMPLOI_DEPOT_IMAGE="$depot" nettoyer prod
  [ "$status" -eq 0 ]
  # le nom de localhost:5000/…:main s'arrête au dernier « : », pas à celui du port
  [ "$(retraits)" = "$(retrait_de 1)" ]
  restent 2 3 4 5 6
  [ ! -e "$REFUS" ]
  bilan "1 retirée, 3 gardées (0 par l'état, 0 par un conteneur, 3 en marge)"
}

@test "une_image_listee_deux_fois_se_retire_une_fois" {
  poser_image 1 2026-10-01T10:00:00Z "$DEPOT_DU_PROJET:0.1.0 $DEPOT_DU_PROJET:0.1.1" "$(empreinte_de 1)"
  poser_image 2 2026-10-02T10:00:00Z "" "$(empreinte_de 2)"
  poser_image 3 2026-10-03T10:00:00Z "" "$(empreinte_de 3)"
  poser_image 4 2026-10-04T10:00:00Z "$DEPOT_DU_PROJET:0.2.0 $DEPOT_DU_PROJET:main" "$(empreinte_de 4)"
  # le double, comme docker, liste une image une fois par nom, et une fois une image sans nom (hors
  # du journal des appels)
  local liste
  liste="$(APPELS="$BATS_TEST_TMPDIR/hors-journal.log" DOCKER_CONFIG="$BATS_TEST_TMPDIR/docker" \
    docker image ls --all --no-trunc --quiet)"
  [ "$(grep -cx "$(image_de 1)" <<<"$liste")" -eq 2 ]
  [ "$(grep -cx "$(image_de 2)" <<<"$liste")" -eq 1 ]
  [ "$(grep -cx "$(image_de 4)" <<<"$liste")" -eq 2 ]
  nettoyer prod
  [ "$status" -eq 0 ]
  # chaque identifiant n'est inspecté qu'une fois, retiré une fois, compté une fois
  local inspection
  inspection="$(appels_de docker | grep '^docker image inspect --format ')"
  [ "$(grep -o "$(image_de 1)" <<<"$inspection" | wc -l)" -eq 1 ]
  [ "$(grep -o "$(image_de 4)" <<<"$inspection" | wc -l)" -eq 1 ]
  # deux étiquettes : docker refuse sans -f le retrait par l'identifiant, elle part par ses
  # étiquettes, une par appel, et la dernière emporte l'image
  [ "$(retraits)" = "$(printf 'docker image rm %s\n' "$DEPOT_DU_PROJET:0.1.0" "$DEPOT_DU_PROJET:0.1.1")" ]
  parties 1
  restent 2 3 4
  [ ! -e "$REFUS" ]
  [ "$(grep -c 'image retirée : ' <<<"$output")" -eq 1 ]
  journal_dit "image retirée : 111111111111 ($DEPOT_DU_PROJET:0.1.0 $DEPOT_DU_PROJET:0.1.1 $(empreinte_de 1))"
  bilan "1 retirée, 3 gardées (0 par l'état, 0 par un conteneur, 3 en marge)"
}

@test "les_images_sans_etiquette_se_voient_meme_quand_docker_les_cache" {
  # Sans --all, un Docker 29 récent (constaté en 29.5.3) cache les images sans étiquette : les
  # anciennes :main que la sonde de staging a tirées par empreinte. Le double fait de même. Le cas
  # d'un projet en service : le precedent du staging, sans nom, et des images sans nom au-delà de
  # la marge.
  local c
  for c in 1 2 3 4 5; do
    poser_image "$c" "2026-10-0${c}T10:00:00Z" "" "$(empreinte_de "$c")"
  done
  poser_image 6 2026-10-06T10:00:00Z "$DEPOT_DU_PROJET:main" "$(empreinte_de 6)"
  etat staging deploye "$(empreinte_de 6) main -"
  etat staging precedent "$(empreinte_de 5) main -"
  # sans --all, le double ne liste que 6, la seule qui a un nom (hors du journal des appels)
  local liste
  liste="$(APPELS="$BATS_TEST_TMPDIR/hors-journal.log" DOCKER_CONFIG="$BATS_TEST_TMPDIR/docker" \
    docker image ls --no-trunc --quiet)"
  [ "$liste" = "$(image_de 6)" ]
  nettoyer staging
  [ "$status" -eq 0 ]
  # 5 et 6 gardées par l'état, 2 à 4 en marge ; 1, la plus ancienne, part par son identifiant
  [ "$(retraits)" = "$(retrait_de 1)" ]
  parties 1
  restent 2 3 4 5 6
  [ ! -e "$REFUS" ]
  bilan "1 retirée, 5 gardées (2 par l'état, 0 par un conteneur, 3 en marge)"
}

@test "un_retrait_par_etiquette_en_echec_passe_a_l_image_suivante" {
  # 1 et 2 partent ; 1 a deux étiquettes, et le retrait de la seconde échoue
  poser_image 1 2026-10-01T10:00:00Z "$DEPOT_DU_PROJET:0.1.0 $DEPOT_DU_PROJET:0.1.1" "$(empreinte_de 1)"
  local c
  for c in 2 3 4; do
    poser_image "$c" "2026-10-0${c}T10:00:00Z" "" "$(empreinte_de "$c")"
  done
  poser_image 5 2026-10-05T10:00:00Z "$DEPOT_DU_PROJET:main" "$(empreinte_de 5)"
  export DOUBLE_DOCKER_IMAGE_RM_ECHEC="$DEPOT_DU_PROJET:0.1.1"
  nettoyer prod
  [ "$status" -eq 1 ]
  [ "$(retraits)" = "$(printf 'docker image rm %s\n' "$DEPOT_DU_PROJET:0.1.0" "$DEPOT_DU_PROJET:0.1.1" \
    "$(image_de 2)")" ]
  # 1 reste, avec la seule étiquette que docker n'a pas pu retirer ; 2 part quand même
  grep -Fx "$(image_de 1)|2026-10-01T10:00:00Z|$DEPOT_DU_PROJET:0.1.1|$(empreinte_de 1)" "$STOCK"
  parties 2
  restent 3 4 5
  [ ! -e "$REFUS" ]
  journal_dit "retrait impossible : 111111111111 (Error response from daemon: conflict: unable to delete 111111111111 (cannot be forced) - image has dependent child images)"
  [[ "$output" != *"image retirée : 111111111111"* ]]
  journal_dit "image retirée : 222222222222 ($(empreinte_de 2))"
  bilan "1 retirée, 3 gardées (0 par l'état, 0 par un conteneur, 3 en marge)"
}

# --- ce qui est gardé ------------------------------------------------------------------------

@test "chaque_fichier_d_etat_protege_son_image" {
  local env_etat env_lance fichier version contenu
  for env_etat in prod staging; do
    version=0.1.0
    [ "$env_etat" = prod ] || version=main
    for fichier in deploye precedent echec compose.env compose.env.precedent; do
      case "$fichier" in
        deploye | precedent) contenu="$(empreinte_de 1) $version" ;;
        echec) contenu="$(empreinte_de 1)" ;;
        *) contenu="$(contenu_compose_env "$env_etat" "$(empreinte_de 1)" "$version")" ;;
      esac
      # son propre état, puis celui de l'autre environnement
      for env_lance in prod staging; do
        echo "cas : $env_etat/$fichier, ménage lancé en $env_lance"
        vider
        cinq_images
        etat "$env_etat" "$fichier" "$contenu"
        nettoyer "$env_lance"
        [ "$status" -eq 0 ]
        # 1, la plus ancienne, reste : son fichier d'état la nomme ; 2 part à sa place
        [ "$(retraits)" = "$(retrait_de 2)" ]
        restent 1 3 4 5
        bilan "1 retirée, 4 gardées (1 par l'état, 0 par un conteneur, 3 en marge)"
        [ ! -e "$REFUS" ]
      done
    done
  done
}

@test "un_etat_illisible_annule_tout" {
  local env cas fichier contenu
  for env in prod staging; do
    # deploye sans version, echec vide, compose.env sans image ; compose.env.precedent qui nomme
    # une image par étiquette, et precedent dont la version n'a pas la forme qu'écrit deployer.sh
    for cas in "deploye|$(empreinte_de 1)" "echec|" \
      "compose.env|$(contenu_compose_env "$env" "$(empreinte_de 1)" main | grep -v '^VEILLE_EMPLOI_IMAGE=')" \
      "compose.env.precedent|$(contenu_compose_env "$env" "$DEPOT_DU_PROJET:0.1.0" 0.1.0)" \
      "precedent|$(empreinte_de 1) v0.1.0"; do
      fichier="${cas%%|*}"
      contenu="${cas#*|}"
      echo "cas : $env/$fichier"
      vider
      cinq_images
      etat "$env" "$fichier" "$contenu"
      nettoyer prod
      annule
      restent 1 2 3 4 5
    done
  done
}

@test "une_image_utilisee_par_un_conteneur_reste" {
  cinq_images
  poser_conteneur arrete 1
  nettoyer prod
  [ "$status" -eq 0 ]
  [ "$(retraits)" = "$(retrait_de 2)" ]
  restent 1 3 4 5
  [ ! -e "$REFUS" ]
  bilan "1 retirée, 4 gardées (0 par l'état, 1 par un conteneur, 3 en marge)"
  # nommée par l'état et utilisée par un conteneur, elle compte une fois, pour l'état
  vider
  cinq_images
  poser_conteneur arrete 1
  etat prod deploye "$(empreinte_de 1) 0.1.0"
  nettoyer prod
  [ "$status" -eq 0 ]
  bilan "1 retirée, 4 gardées (1 par l'état, 0 par un conteneur, 3 en marge)"
}

@test "la_marge_garde_les_plus_recentes_quelle_que_soit_la_precision" {
  # Docker retire les zéros de fin de la fraction : un tri brut mettrait 00.5Z avant 00Z
  poser_image 1 2026-10-27T10:00:00Z "" "$(empreinte_de 1)"
  poser_image 2 2026-10-27T10:00:00.5Z "" "$(empreinte_de 2)"
  poser_image 3 2026-10-27T10:00:01.25Z "" "$(empreinte_de 3)"
  poser_image 4 2026-10-27T09:59:59.999999999Z "" "$(empreinte_de 4)"
  poser_image 5 2026-10-27T10:00:02Z "" "$(empreinte_de 5)"
  nettoyer prod
  [ "$status" -eq 0 ]
  restent 2 3 5
  parties 1 4
  bilan "2 retirées, 3 gardées (0 par l'état, 0 par un conteneur, 3 en marge)"
}

# --- les verrous -----------------------------------------------------------------------------

@test "verrou_de_l_autre_environnement_pris_rien_ne_part" {
  local env autre
  for env in prod staging; do
    autre=staging
    [ "$env" = prod ] || autre=prod
    echo "cas : ménage en $env, verrou de $autre pris"
    vider
    cinq_images
    tenir_le_verrou "$VEILLE_EMPLOI_RACINE_ETAT/$autre/verrou"
    nettoyer "$env"
    relacher_le_verrou
    [ "$status" -eq 0 ]
    [ ! -s "$APPELS" ]
    restent 1 2 3 4 5
    journal_dit "ménage des images sauté : le verrou $VEILLE_EMPLOI_RACINE_ETAT/$autre/verrou est pris ; le prochain déploiement le fera"
  done
}

@test "autre_etat_absent_le_menage_a_lieu" {
  cinq_images
  nettoyer prod
  [ "$status" -eq 0 ]
  parties 1 2
  restent 3 4 5
  journal_dit "staging : aucun état ($VEILLE_EMPLOI_RACINE_ETAT/staging absent), rien à y protéger"
  # le ménage ne crée pas le dossier de l'autre environnement
  [ ! -e "$VEILLE_EMPLOI_RACINE_ETAT/staging" ]
}

@test "verrou_de_l_autre_qui_ne_s_ouvre_pas_annule_tout" {
  cinq_images
  mkdir -p "$VEILLE_EMPLOI_RACINE_ETAT/staging/verrou"
  nettoyer prod
  annule
  [ ! -s "$APPELS" ]
  restent 1 2 3 4 5
}

@test "verrou_propre" {
  cinq_images
  tenir_le_verrou "$VEILLE_EMPLOI_RACINE_ETAT/prod/verrou"
  # à la main : il attend son verrou, puis abandonne sans rien lire
  VEILLE_EMPLOI_VERROU_ATTENTE=1 nettoyer prod
  [ "$status" -eq 1 ]
  [ ! -s "$APPELS" ]
  journal_dit "verrou $VEILLE_EMPLOI_RACINE_ETAT/prod/verrou toujours pris après 1 s : ménage abandonné, rien n'est retiré"
  # tenu par celui qui le lance (le déploiement) : il ne l'attend pas
  VEILLE_EMPLOI_VERROU_TENU=1 VEILLE_EMPLOI_VERROU_ATTENTE=1 nettoyer prod
  relacher_le_verrou
  [ "$status" -eq 0 ]
  parties 1 2
  bilan "2 retirées, 3 gardées (0 par l'état, 0 par un conteneur, 3 en marge)"
}

# --- les retraits et les abstentions ---------------------------------------------------------

@test "un_retrait_en_echec_n_arrete_pas_les_suivants" {
  cinq_images
  DOUBLE_DOCKER_IMAGE_RM_ECHEC="$(image_de 1)"
  export DOUBLE_DOCKER_IMAGE_RM_ECHEC
  nettoyer prod
  [ "$status" -eq 1 ]
  # de la plus ancienne à la plus récente : 1, en échec, puis 2
  [ "$(retraits)" = "$(retrait_de 1 2)" ]
  restent 1 3 4 5
  parties 2
  [ ! -e "$REFUS" ]
  journal_dit "retrait impossible : 111111111111 (Error response from daemon: conflict: unable to delete 111111111111 (cannot be forced) - image has dependent child images)"
  bilan "1 retirée, 3 gardées (0 par l'état, 0 par un conteneur, 3 en marge)"
}

@test "liste_ou_inspection_en_echec_annule_tout" {
  local cas variable raison
  for cas in "DOUBLE_DOCKER_IMAGE_LS_ECHEC|liste des images impossible (docker image ls : code 1)" \
    "DOUBLE_DOCKER_IMAGE_INSPECT_ECHEC|inspection des images impossible (docker image inspect : code 1)" \
    "DOUBLE_DOCKER_PS_ECHEC|liste des conteneurs impossible (docker ps : code 1)" \
    "DOUBLE_DOCKER_CONTAINER_INSPECT_ECHEC|inspection des conteneurs impossible (docker container inspect : code 1)"; do
    variable="${cas%%|*}"
    raison="${cas#*|}"
    echo "cas : $variable"
    vider
    cinq_images
    poser_conteneur arrete 5
    export "$variable=1"
    nettoyer prod
    unset "$variable"
    annule
    journal_dit "ménage des images annulé, rien n'est retiré : $raison"
    restent 1 2 3 4 5
  done
}

# Une date de création que le ménage ne sait pas ranger, avec un décalage horaire ou vide : la
# marge serait fausse, et le ménage s'annule plutôt que de deviner.
@test "une_date_illisible_annule_tout" {
  local date c
  for date in 2026-10-01T12:00:00+02:00 ''; do
    echo "cas : date '$date'"
    vider
    poser_image 1 "$date" "" "$(empreinte_de 1)"
    for c in 2 3 4; do
      poser_image "$c" "2026-10-0${c}T10:00:00Z" "" "$(empreinte_de "$c")"
    done
    poser_image 5 2026-10-05T10:00:00Z "$DEPOT_DU_PROJET:main" "$(empreinte_de 5)"
    nettoyer prod
    annule
    journal_dit "ménage des images annulé, rien n'est retiré : date de création illisible pour 111111111111 : '$date'"
    restent 1 2 3 4 5
  done
}

@test "deux_menages_de_suite_le_second_ne_retire_rien" {
  cinq_images
  nettoyer prod
  [ "$status" -eq 0 ]
  parties 1 2
  : >"$APPELS"
  nettoyer prod
  [ "$status" -eq 0 ]
  [ -z "$(retraits)" ]
  restent 3 4 5
  bilan "0 retirée, 3 gardées (0 par l'état, 0 par un conteneur, 3 en marge)"
}

@test "usage" {
  cinq_images
  nettoyer
  [ "$status" -eq 64 ]
  nettoyer prod staging
  [ "$status" -eq 64 ]
  nettoyer recette
  [ "$status" -eq 64 ]
  [ ! -s "$APPELS" ]
  restent 1 2 3 4 5
}

@test "jamais_de_force_ni_de_prune" {
  # 1 et 2 partent, 1 par ses deux étiquettes, 2 par son identifiant
  poser_image 1 2026-10-01T10:00:00Z "$DEPOT_DU_PROJET:0.1.0 $DEPOT_DU_PROJET:0.1.1" "$(empreinte_de 1)"
  local c
  for c in 2 3 4 5; do
    poser_image "$c" "2026-10-0${c}T10:00:00Z" "" "$(empreinte_de "$c")"
  done
  nettoyer prod
  [ "$status" -eq 0 ]
  # trois retraits, chacun d'une seule cible, un identifiant ou une étiquette du dépôt, sans option
  [ "$(retraits | wc -l)" -eq 3 ]
  local ligne
  while IFS= read -r ligne; do
    [[ "$ligne" =~ ^docker\ image\ rm\ (sha256:[0-9a-f]{64}|ghcr\.io/edouardzemb/veille-emploi:[^\ ]+)$ ]]
  done < <(retraits)
  aucune_ligne 'prune|rmi' "$APPELS"
  [ ! -e "$REFUS" ]
}

# Le garde-fou des tests précédents : sans ces refus, « refus-images absent » ne prouverait rien.
@test "le_double_refuse_les_retraits_interdits" {
  export DOCKER_CONFIG="$BATS_TEST_TMPDIR/docker"
  poser_image 1 2026-10-01T10:00:00Z "$DEPOT_DU_PROJET:0.1.0" "$(empreinte_de 1)"
  poser_image 2 2026-10-02T10:00:00Z ghcr.io/autre/projet:1 "$(empreinte_de 2)"
  poser_image 3 2026-10-03T10:00:00Z "" ""
  poser_image 4 2026-10-04T10:00:00Z "" "$(empreinte_de 4)"
  poser_conteneur arrete 4
  poser_image 5 2026-10-05T10:00:00Z "$DEPOT_DU_PROJET:0.5.0 $DEPOT_DU_PROJET:0.5.1" "$(empreinte_de 5)"
  local -a cas=(
    "125 image rm -f $(image_de 1)"
    "125 image rm --force $(image_de 1)"
    "125 image rm $(image_de 1) $(image_de 4)"
    "125 rmi $(image_de 1)"
    "125 image prune -a"
    "125 system prune"
    "1 image rm $(image_de 2)"
    "1 image rm ghcr.io/autre/projet:1"
    "1 image rm $(image_de 3)"
    "1 image rm $(image_de 4)"
    "1 image rm $(image_de 5)"
  )
  local ligne refus=0
  for ligne in "${cas[@]}"; do
    echo "cas : docker ${ligne#* }"
    # shellcheck disable=SC2086  # découpage voulu
    run docker ${ligne#* }
    [ "$status" -eq "${ligne%% *}" ]
    refus=$((refus + 1))
    [ "$(wc -l <"$REFUS")" -eq "$refus" ]
  done
  restent 1 2 3 4 5
  # par son identifiant, une image à deux étiquettes est refusée avec le message de docker
  run docker image rm "$(image_de 5)"
  [ "$status" -eq 1 ]
  [[ "$output" == *"(must be forced) - image is referenced in multiple repositories"* ]]
  refus=$((refus + 1))
  # un nom inconnu : l'erreur de docker, sans refus noté
  run docker image rm "$DEPOT_DU_PROJET:inconnue"
  [ "$status" -eq 1 ]
  [ "$(wc -l <"$REFUS")" -eq "$refus" ]
  # les retraits permis, et rien n'est noté : par l'identifiant, l'image quitte le stock…
  run docker image rm "$(image_de 1)"
  [ "$status" -eq 0 ]
  [ "$output" = "Deleted: $(image_de 1)" ]
  parties 1
  # …par une étiquette, ce nom seul part, et la dernière emporte l'image et ses empreintes
  run docker image rm "$DEPOT_DU_PROJET:0.5.0"
  [ "$status" -eq 0 ]
  [ "$output" = "Untagged: $DEPOT_DU_PROJET:0.5.0" ]
  grep -Fx "$(image_de 5)|2026-10-05T10:00:00Z|$DEPOT_DU_PROJET:0.5.1|$(empreinte_de 5)" "$STOCK"
  run docker image rm "$DEPOT_DU_PROJET:0.5.1"
  [ "$status" -eq 0 ]
  [ "$output" = "$(printf '%s\n' "Untagged: $DEPOT_DU_PROJET:0.5.1" "Deleted: $(image_de 5)")" ]
  parties 5
  [ "$(wc -l <"$REFUS")" -eq "$refus" ]
}

# --- les instantanés des données -------------------------------------------------------------
#
# Après celui des images, sous le même verrou, le ménage des instantanés des données de
# l'environnement, dans son seul $VEILLE_EMPLOI_ETAT/instantanes/ (M-0004, § 8) : il garde ceux que
# nomment son deploye et son precedent, plus les 3 plus récents des autres par leur date de
# modification, et retire le reste, ainsi que tout .partiel de plus d'un jour. Les instantanés sont
# figés en lecture seule, comme ceux que fait preparer_instantane (lib.sh).

# commit_de <c> : un commit de données de test, 40 fois le caractère <c>.
commit_de() {
  local suite
  printf -v suite '%40s' ''
  printf '%s\n' "${suite// /$1}"
}

# poser_instantane <env> <nom> <date> : un instantané des données de cet environnement, ou un
# .partiel selon son nom : un dossier contenu/, daté de <date> (touch -d), puis figé en lecture
# seule.
poser_instantane() {
  local dossier="$VEILLE_EMPLOI_RACINE_ETAT/$1/instantanes/$2"
  mkdir -p "$dossier/contenu"
  echo "contenu de $2" >"$dossier/contenu/fichier"
  touch -d "$3" "$dossier/contenu" "$dossier"
  chmod -R a-w "$dossier"
}

# instantanes_de <env> : les entrées du dossier des instantanés de cet environnement, une par ligne,
# dans l'ordre des noms.
instantanes_de() {
  find "$VEILLE_EMPLOI_RACINE_ETAT/$1/instantanes" -mindepth 1 -maxdepth 1 -printf '%f\n' | LC_ALL=C sort
}

@test "ménage : les instantanés gardés et retirés" {
  local a b c d e f z neuf huit x staging_avant
  a="$(commit_de a)"
  b="$(commit_de b)"
  c="$(commit_de c)"
  d="$(commit_de d)"
  e="$(commit_de e)"
  f="$(commit_de f)"
  z="$(commit_de 0)"
  neuf="$(commit_de 9).partiel"
  huit="$(commit_de 8).partiel"
  # l'état de la prod nomme a (deploye) et b (precedent), plus anciens que tous les autres
  etat prod deploye "$(empreinte_de 1) 0.2.0 $a"
  etat prod precedent "$(empreinte_de 2) 0.1.0 $b"
  poser_instantane prod "$a" '10 days ago'
  poser_instantane prod "$b" '9 days ago'
  # les autres : l'ordre de leurs dates n'est pas celui de leurs noms ; c, e et f sont les 3 plus
  # récents, z et d partent
  poser_instantane prod "$c" '1 day ago'
  poser_instantane prod "$e" '2 days ago'
  poser_instantane prod "$f" '3 days ago'
  poser_instantane prod "$z" '4 days ago'
  poser_instantane prod "$d" '8 days ago'
  # un .partiel de plus d'un jour, laissé par un essai coupé ; un de moins d'un jour, qu'un
  # déploiement peut être en train de construire
  poser_instantane prod "$neuf" '25 hours ago'
  poser_instantane prod "$huit" '23 hours ago'
  # le staging a les siens, et son état nomme d : ni l'un ni l'autre ne compte pour la prod
  etat staging deploye "$(empreinte_de 3) main $d"
  for x in 1 2 3 4 5; do
    poser_instantane staging "$(commit_de "$x")" "$((x + 20)) days ago"
  done
  staging_avant="$(instantanes_de staging)"
  # sous le verrou de l'environnement : pris par un autre, rien ne part
  tenir_le_verrou "$VEILLE_EMPLOI_RACINE_ETAT/prod/verrou"
  VEILLE_EMPLOI_VERROU_ATTENTE=1 nettoyer prod
  relacher_le_verrou
  [ "$status" -eq 1 ]
  [ "$(instantanes_de prod | wc -l)" -eq 9 ]
  [[ "$output" != *"instantané"* ]]
  nettoyer prod
  [ "$status" -eq 0 ]
  [ "$(instantanes_de prod)" = "$(printf '%s\n' "$huit" "$a" "$b" "$c" "$e" "$f")" ]
  [ "$(instantanes_de staging)" = "$staging_avant" ]
  journal_dit "instantané retiré : $d"
  journal_dit "instantané retiré : $z"
  journal_dit "instantané retiré : $neuf"
  journal_dit "ménage des instantanés : 3 retirés, 6 gardés (2 par l'état, 3 en marge, 1 partiel de moins d'un jour)"
  # après celui des images
  [[ "$output" == *"ménage des images : "*"ménage des instantanés : "* ]]
  [ ! -e "$REFUS" ]
  # un second passage ne retire rien de plus
  nettoyer prod
  [ "$status" -eq 0 ]
  [ "$(instantanes_de prod)" = "$(printf '%s\n' "$huit" "$a" "$b" "$c" "$e" "$f")" ]
  journal_dit "ménage des instantanés : 0 retiré, 6 gardés (2 par l'état, 3 en marge, 1 partiel de moins d'un jour)"
}

# Un couple sans données montées (« - »), ou un état d'avant la v0.7.0, à deux champs, ne nomme
# aucun instantané : il n'en garde aucun, et ce n'est pas une surprise. Sans dossier d'instantanés
# (un projet qui ne déclare aucune commande), le ménage des instantanés ne dit rien.
@test "ménage : un couple en - ne garde aucun instantané" {
  local x
  etat prod deploye "$(empreinte_de 1) 0.2.0 -"
  etat prod precedent "$(empreinte_de 2) 0.1.0"
  nettoyer prod
  [ "$status" -eq 0 ]
  [[ "$output" != *"instantané"* ]]
  [ ! -e "$VEILLE_EMPLOI_RACINE_ETAT/prod/instantanes" ]
  for x in 1 2 3 4; do
    poser_instantane prod "$(commit_de "$x")" "$x days ago"
  done
  nettoyer prod
  [ "$status" -eq 0 ]
  [ "$(instantanes_de prod)" = "$(printf '%s\n' "$(commit_de 1)" "$(commit_de 2)" "$(commit_de 3)")" ]
  journal_dit "instantané retiré : $(commit_de 4)"
  journal_dit "ménage des instantanés : 1 retiré, 3 gardés (0 par l'état, 3 en marge, 0 partiel de moins d'un jour)"
  [[ "$output" != *"annulé"* ]]
}

# Ce qui arrive aux images ne décide pas des instantanés : un ménage des images sauté (le verrou du
# staging pris) ou en échec (un retrait impossible) laisse les instantanés de la prod se ranger, et le
# code de sortie reste celui des images.
@test "ménage : celui des images ne décide pas de celui des instantanés" {
  local I="$VEILLE_EMPLOI_RACINE_ETAT/prod/instantanes" x
  cinq_images
  for x in 1 2 3 4; do
    poser_instantane prod "$(commit_de "$x")" "$x days ago"
  done
  tenir_le_verrou "$VEILLE_EMPLOI_RACINE_ETAT/staging/verrou"
  nettoyer prod
  relacher_le_verrou
  [ "$status" -eq 0 ]
  [ -z "$(retraits)" ]
  journal_dit "ménage des images sauté : le verrou $VEILLE_EMPLOI_RACINE_ETAT/staging/verrou est pris ; le prochain déploiement le fera"
  [ ! -e "$I/$(commit_de 4)" ]
  journal_dit "ménage des instantanés : 1 retiré, 3 gardés (0 par l'état, 3 en marge, 0 partiel de moins d'un jour)"
  poser_instantane prod "$(commit_de 5)" '5 days ago'
  DOUBLE_DOCKER_IMAGE_RM_ECHEC="$(image_de 1)"
  export DOUBLE_DOCKER_IMAGE_RM_ECHEC
  nettoyer prod
  [ "$status" -eq 1 ]
  journal_dit "retrait impossible : 111111111111 (Error response from daemon: conflict: unable to delete 111111111111 (cannot be forced) - image has dependent child images)"
  [ ! -e "$I/$(commit_de 5)" ]
  journal_dit "ménage des instantanés : 1 retiré, 3 gardés (0 par l'état, 3 en marge, 0 partiel de moins d'un jour)"
}

# Le ménage des images annulé (arreter, dans son sous-shell) n'annule pas celui des instantanés :
# un echec illisible de l'environnement, un état illisible de l'autre, ou son verrou qui ne s'ouvre
# pas. Le code de sortie reste celui des images, 1. L'autre environnement ne décide de rien pour
# les instantanés de celui-ci.
@test "ménage : des images annulées laissent faire celui des instantanés" {
  local I="$VEILLE_EMPLOI_RACINE_ETAT/prod/instantanes" cas x
  for cas in echec-illisible autre-illisible autre-verrou; do
    echo "cas : $cas"
    vider
    cinq_images
    for x in 1 2 3 4; do
      poser_instantane prod "$(commit_de "$x")" "$x days ago"
    done
    case "$cas" in
      echec-illisible) etat prod echec "" ;;
      autre-illisible) etat staging deploye "$(empreinte_de 1)" ;;
      autre-verrou) mkdir -p "$VEILLE_EMPLOI_RACINE_ETAT/staging/verrou" ;;
    esac
    nettoyer prod
    annule
    restent 1 2 3 4 5
    [ ! -e "$I/$(commit_de 4)" ]
    [ "$(instantanes_de prod)" = "$(printf '%s\n' "$(commit_de 1)" "$(commit_de 2)" "$(commit_de 3)")" ]
    journal_dit "instantané retiré : $(commit_de 4)"
    journal_dit "ménage des instantanés : 1 retiré, 3 gardés (0 par l'état, 3 en marge, 0 partiel de moins d'un jour)"
  done
}

# Une erreur inattendue dans le ménage des instantanés (ici, une heure qui n'est pas un nombre, que
# l'arithmétique de bash refuse sous set -u) l'interrompt dans son sous-shell : rien n'est retiré,
# le journal le dit, et le code de sortie reste celui des images, 0 ou 1.
@test "ménage : celui des instantanés interrompu ne change pas le code des images" {
  local I="$VEILLE_EMPLOI_RACINE_ETAT/prod/instantanes" reel x attendu
  reel="$(command -v date)"
  creer_double date 'if [ "$*" = +%s ]; then echo pas-une-heure; exit 0; fi; exec '"$reel"' "$@"'
  for attendu in 0 1; do
    echo "cas : code $attendu"
    vider
    cinq_images
    for x in 1 2 3 4; do
      poser_instantane prod "$(commit_de "$x")" "$x days ago"
    done
    poser_instantane prod "$(commit_de 9).partiel" '2 days ago'
    if [ "$attendu" -eq 1 ]; then
      DOUBLE_DOCKER_IMAGE_RM_ECHEC="$(image_de 1)"
      export DOUBLE_DOCKER_IMAGE_RM_ECHEC
    fi
    nettoyer prod
    [ "$status" -eq "$attendu" ]
    parties 2
    restent 3 4 5
    journal_dit "ménage des instantanés interrompu (code 1) : le code de sortie reste celui des images"
    [ "$(instantanes_de prod | wc -l)" -eq 5 ]
    [[ "$output" != *"instantané retiré"* ]]
    [[ "$output" != *"ménage des instantanés : "* ]]
  done
}

# Une surprise annule le ménage des instantanés, avant tout retrait, et le journal le dit : un nom
# qui n'est ni un commit de 40 caractères hexadécimaux ni <commit>.partiel, une entrée qui n'est pas
# un dossier, un lien (jamais suivi), un état illisible, un dossier des instantanés qui n'en est pas
# un. Le ménage des images, lui, garde ses retraits et son code : 0, ou 1 quand l'état illisible
# l'annule aussi.
@test "ménage : une surprise n'en retire aucun" {
  local I="$VEILLE_EMPLOI_RACINE_ETAT/prod/instantanes" ETAT="$VEILLE_EMPLOI_RACINE_ETAT/prod"
  local ailleurs="$BATS_TEST_TMPDIR/ailleurs" a cas raison attendu x
  local attendu_nom="(attendu : un commit de 40 caractères hexadécimaux, ou <commit>.partiel)"
  a="$(commit_de a)"
  for cas in nom-fichier nom-dossier cache court majuscules fichier lien lien-partiel deploye \
    precedent dossier-lien dossier-fichier; do
    echo "cas : $cas"
    vider
    chmod -R u+rwX "$ailleurs" 2>/dev/null || true
    rm -rf "$ailleurs"
    mkdir -p "$ailleurs"
    echo "à garder" >"$ailleurs/garder.txt"
    cinq_images
    for x in 1 2 3 4 5; do
      poser_instantane prod "$(commit_de "$x")" "$x days ago"
    done
    poser_instantane prod "$(commit_de 9).partiel" '2 days ago'
    attendu=0
    case "$cas" in
      nom-fichier)
        echo "notes" >"$I/notes"
        raison="nom inattendu : $I/notes $attendu_nom"
        ;;
      nom-dossier)
        mkdir "$I/$a-copie"
        raison="nom inattendu : $I/$a-copie $attendu_nom"
        ;;
      cache)
        mkdir "$I/.cache"
        raison="nom inattendu : $I/.cache $attendu_nom"
        ;;
      court)
        mkdir "$I/${a:1}"
        raison="nom inattendu : $I/${a:1} $attendu_nom"
        ;;
      majuscules)
        mkdir "$I/$(commit_de A)"
        raison="nom inattendu : $I/$(commit_de A) $attendu_nom"
        ;;
      fichier)
        echo "pas un dossier" >"$I/$a"
        raison="$I/$a n'est pas un dossier"
        ;;
      lien)
        ln -s "$ailleurs" "$I/$a"
        raison="$I/$a est un lien, qui n'est jamais suivi"
        ;;
      lien-partiel)
        ln -s "$ailleurs" "$I/$a.partiel"
        touch -h -d '3 days ago' "$I/$a.partiel"
        raison="$I/$a.partiel est un lien, qui n'est jamais suivi"
        ;;
      deploye)
        etat prod deploye "$(empreinte_de 1) 0.1.0 pas-un-commit"
        raison="$ETAT/deploye illisible (attendu : la forme qu'écrit deployer.sh)"
        attendu=1
        ;;
      precedent)
        etat prod precedent "$(empreinte_de 1) v0.1.0"
        raison="$ETAT/precedent illisible (attendu : la forme qu'écrit deployer.sh)"
        attendu=1
        ;;
      dossier-lien)
        mv "$I" "$ailleurs/instantanes"
        ln -s "$ailleurs/instantanes" "$I"
        raison="$I est un lien, qui n'est jamais suivi"
        ;;
      dossier-fichier)
        chmod -R u+rwX "$I"
        rm -rf "$I"
        echo "pas un dossier" >"$I"
        raison="$I n'est pas un dossier"
        ;;
    esac
    nettoyer prod
    [ "$status" -eq "$attendu" ]
    journal_dit "ménage des instantanés annulé, rien n'est retiré : $raison"
    [[ "$output" != *"instantané retiré"* ]]
    # rien n'est retiré, ni les instantanés hors de la marge, ni le .partiel de plus d'un jour, ni ce
    # que désigne un lien
    if [ "$cas" = dossier-fichier ]; then
      [ "$(cat "$I")" = "pas un dossier" ]
    else
      for x in 1 2 3 4 5; do
        [ -d "$I/$(commit_de "$x")" ]
      done
      [ -d "$I/$(commit_de 9).partiel" ]
    fi
    [ "$(cat "$ailleurs/garder.txt")" = "à garder" ]
    # les images : leurs retraits et leur code ne changent pas
    if [ "$attendu" -eq 0 ]; then
      parties 1 2
      restent 3 4 5
      bilan "2 retirées, 3 gardées (0 par l'état, 0 par un conteneur, 3 en marge)"
    else
      annule
      restent 1 2 3 4 5
    fi
  done
}

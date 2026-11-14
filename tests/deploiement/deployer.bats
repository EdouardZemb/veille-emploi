#!/usr/bin/env bats
# deployer.sh : verrou, instantané, compose.env, lancement, santé, état, retour arrière.
#
# docker et curl sont des doubles (tests/deploiement/doubles/) : l'« application en service » est
# le fichier en-service.env, que `compose up` remplit à partir du compose.env reçu et que le double
# de curl lit pour répondre à /sante. Les tests tournent surtout en prod, où les versions
# (0.1.0, 0.2.0) se distinguent dans les messages. L'état retient un couple, l'image et le commit de
# données (« - » sans données montées) : voir « le couple », plus bas.

# Chaque test tourne dans son propre processus : les `export DOUBLE_*` d'un test ne fuient pas
# dans les autres, comme le veut le pilotage des doubles.
# shellcheck disable=SC2030,SC2031

bats_require_minimum_version 1.5.0

load aide

setup() {
  preparer_environnement
  installer_doubles docker curl
  export VEILLE_EMPLOI_SANTE_DELAI=0
  ETAT="$VEILLE_EMPLOI_RACINE_ETAT/prod"
  EN_SERVICE="$BATS_TEST_TMPDIR/en-service.env"
  ANCIENNE="ghcr.io/edouardzemb/veille-emploi@sha256:$(printf '1%.0s' {1..64})"
  NOUVELLE="ghcr.io/edouardzemb/veille-emploi@sha256:$(printf '2%.0s' {1..64})"
  SUIVANTE="ghcr.io/edouardzemb/veille-emploi@sha256:$(printf '3%.0s' {1..64})"
  HC=https://hc.example/ping/sonde-prod
  preparer_secrets_de_test prod JETON=jeton-prod-7 "HC_SONDE=$HC"
  projet_env_du_test
}

teardown() {
  # les instantanés des données sont en lecture seule : bats doit pouvoir retirer le dossier du test
  chmod -R u+rwX "$BATS_TEST_TMPDIR" 2>/dev/null || true
}

# projet_env_du_test : le deploiement/projet.env des tests, sans commande de l'instance. Celui du
# projet n'est jamais lu : il déclare peut-être ses propres commandes, et celles de l'image sont
# ici celles du test, en plusieurs mots.
projet_env_du_test() {
  printf '%s\n' 'SAUVEGARDER=outil sauvegarder --forme dossier' 'VERIFIER=outil verifier' \
    >"$CLONE/deploiement/projet.env"
}

deployer() {
  run bash "$CLONE/deploiement/deployer.sh" "$@"
}

# deja_en_service <image> <version> : l'état laissé par un déploiement réussi de cette version, en
# prod (en_service, aide.bash).
deja_en_service() {
  en_service prod "$1" "$2"
  poser_donnees prod
}

# dc_de <env> [<montage>…] : le début de chaque appel de compose du déploiement, celui de `dc`
# (lib.sh) : le projet de l'environnement, ses deux fichiers compose dans l'ordre, puis les fichiers
# de ces montages (config, contenu : compose.<montage>.yml), et son compose.env.
dc_de() {
  local nom_env="$1" projet=veille-emploi montages="" montage
  shift
  [ "$nom_env" = prod ] || projet="veille-emploi-$nom_env"
  for montage in "$@"; do
    montages="$montages -f $CLONE/deploiement/compose.$montage.yml"
  done
  printf 'docker compose -p %s -f %s -f %s%s --env-file %s' "$projet" "$CLONE/deploiement/compose.yml" \
    "$CLONE/deploiement/compose.projet.yml" "$montages" "$VEILLE_EMPLOI_RACINE_ETAT/$nom_env/compose.env"
}

# signaux : les appels de curl vers la supervision.
signaux() {
  envois_supervision
}

signal() {
  printf 'curl -fsS -m 10 --retry 3 --data-raw %s' "$1"
}

nombre_de_lancements() {
  appels_de docker | grep -c ' up -d --wait --wait-timeout 120 --remove-orphans$' || true
}

# --- déploiement réussi ----------------------------------------------------------------------

@test "deploiement_reussi_ecrit_l_etat" {
  deja_en_service "$ANCIENNE" 0.1.0
  echo "ghcr.io/edouardzemb/veille-emploi@sha256:$(printf '9%.0s' {1..64})" >"$ETAT/echec"
  deployer prod "$NOUVELLE" 0.2.0
  [ "$status" -eq 0 ]
  # état : la nouvelle version déployée, l'ancienne gardée comme précédente, plus d'échec
  [ "$(cat "$ETAT/deploye")" = "$NOUVELLE 0.2.0 -" ]
  [ "$(cat "$ETAT/precedent")" = "$ANCIENNE 0.1.0" ]
  [ ! -e "$ETAT/echec" ]
  [ "$(cat "$ETAT/compose.env")" = "$(contenu_compose_env prod "$NOUVELLE" 0.2.0)" ]
  [ "$(cat "$ETAT/compose.env.precedent")" = "$(contenu_compose_env prod "$ANCIENNE" 0.1.0)" ]
  [ "$(signaux)" = "$(signal 'déployé 0.2.0') $HC" ]
  # l'adresse du signal n'est dans aucun argument : curl la reçoit sur son entrée standard
  aucune_ligne 'hc.example' "$APPELS"
  # l'instantané précède le lancement ; tout passe par le projet et le compose.env de la prod
  local dc
  dc="$(dc_de prod)"
  appels_de docker | grep -E "^$dc exec -T app outil sauvegarder --forme dossier /sauvegardes/pre-deploiement/[0-9]{8}T[0-9]{6}Z\.partiel$"
  appels_de docker | grep -Fx "$dc up -d --wait --wait-timeout 120 --remove-orphans"
  [ "$(ligne_de ' exec -T app ')" -lt "$(ligne_de ' up -d ')" ]
  # santé sur la boucle locale, au port de la prod
  appels_de curl | grep -Fx 'curl -fsS -m 5 http://127.0.0.1:4310/sante'
  grep -Fx "VEILLE_EMPLOI_IMAGE=$NOUVELLE" "$EN_SERVICE"
}

@test "deploiement_staging_utilise_son_projet_son_port_et_main" {
  preparer_secrets_de_test staging JETON=jeton-staging-7 HC_SONDE=https://hc.example/ping/sonde-staging
  deployer staging "$NOUVELLE" main
  [ "$status" -eq 0 ]
  local etat="$VEILLE_EMPLOI_RACINE_ETAT/staging"
  [ "$(cat "$etat/deploye")" = "$NOUVELLE main -" ]
  [ "$(cat "$etat/compose.env")" = "$(contenu_compose_env staging "$NOUVELLE" main)" ]
  appels_de docker | grep -F "docker compose -p veille-emploi-staging -f $CLONE/deploiement/compose.yml -f $CLONE/deploiement/compose.projet.yml --env-file $etat/compose.env up"
  appels_de curl | grep -Fx 'curl -fsS -m 5 http://127.0.0.1:4311/sante'
  [ "$(signaux)" = "$(signal 'déployé main') https://hc.example/ping/sonde-staging" ]
}

# Le compose exige VEILLE_EMPLOI_URL_PUBLIQUE, et compose.env la porte (la valeur de
# deploiement/env/<env>.env), pour que `docker compose --env-file compose.env …` lancé à la main ne
# dépende pas du shell.
@test "compose_env_contient_l_url_publique" {
  deployer prod "$NOUVELLE" 0.2.0
  [ "$status" -eq 0 ]
  grep -Fx 'VEILLE_EMPLOI_URL_PUBLIQUE=https://veille-emploi.exemple.org' "$ETAT/compose.env"
  # et c'est cette valeur que reçoit l'application
  grep -Fx 'VEILLE_EMPLOI_URL_PUBLIQUE=https://veille-emploi.exemple.org' "$EN_SERVICE"
  # le staging a la sienne
  preparer_secrets_de_test staging JETON=jeton-staging-7 HC_SONDE=https://hc.example/ping/sonde-staging
  deployer staging "$NOUVELLE" main
  [ "$status" -eq 0 ]
  grep -Fx 'VEILLE_EMPLOI_URL_PUBLIQUE=https://veille-emploi-staging.exemple.org' "$VEILLE_EMPLOI_RACINE_ETAT/staging/compose.env"
}

@test "pas_d_instantane_au_premier_deploiement" {
  # aucun compose.env : `dc` échouerait, on ne demande même pas si l'application tourne
  deployer prod "$NOUVELLE" 0.2.0
  [ "$status" -eq 0 ]
  # le `ps` de compose (l'application tourne-t-elle ?), pas le `docker ps --all` du ménage des images
  [ "$(appels_de docker | grep -c ' compose .* ps ')" -eq 0 ]
  [ "$(appels_de docker | grep -c ' exec ')" -eq 0 ]
  [ "$(cat "$ETAT/deploye")" = "$NOUVELLE 0.2.0 -" ]
  [ ! -e "$ETAT/precedent" ]
  [ ! -e "$ETAT/compose.env.precedent" ]
  [ "$(signaux)" = "$(signal 'déployé 0.2.0') $HC" ]
}

@test "pas_d_instantane_si_l_application_est_arretee" {
  deja_en_service "$ANCIENNE" 0.1.0
  rm "$EN_SERVICE"
  deployer prod "$NOUVELLE" 0.2.0
  [ "$status" -eq 0 ]
  [ "$(appels_de docker | grep -c ' ps -q app$')" -eq 1 ]
  [ "$(appels_de docker | grep -c ' exec ')" -eq 0 ]
  [ "$(cat "$ETAT/deploye")" = "$NOUVELLE 0.2.0 -" ]
}

# `sauvegardes` passe de non à oui sur un projet en service. La version en service a été
# lancée sans le montage /sauvegardes, et son compose.env n'a pas VEILLE_EMPLOI_SAUVEGARDES (ou l'a
# vide) : la commande SAUVEGARDER, lancée dans son conteneur, échouerait à chaque passage de la
# sonde, et plus rien ne se déploierait. Pas d'instantané, et le journal le dit ; la version qui
# arrive monte /sauvegardes, et le déploiement suivant prend le sien.
@test "pas_d_instantane_si_la_version_en_service_ne_monte_pas_les_sauvegardes" {
  local cas suivante pre="$VEILLE_EMPLOI_RACINE_SAUVEGARDES/pre-deploiement"
  suivante="ghcr.io/edouardzemb/veille-emploi@sha256:$(printf '3%.0s' {1..64})"
  for cas in absente vide; do
    rm -rf "$ETAT" "$pre"
    : >"$APPELS"
    deja_en_service "$ANCIENNE" 0.1.0
    if [ "$cas" = absente ]; then
      sed -i '/^VEILLE_EMPLOI_SAUVEGARDES=/d' "$ETAT/compose.env"
    else
      sed -i 's/^VEILLE_EMPLOI_SAUVEGARDES=.*/VEILLE_EMPLOI_SAUVEGARDES=/' "$ETAT/compose.env"
    fi
    deployer prod "$NOUVELLE" 0.2.0
    [ "$status" -eq 0 ]
    [[ "$output" == *"la version en service ne monte pas /sauvegardes : pas d'instantané"* ]]
    [ "$(appels_de docker | grep -c ' exec ')" -eq 0 ]
    [ ! -e "$pre" ]
    [ "$(cat "$ETAT/deploye")" = "$NOUVELLE 0.2.0 -" ]
    [ "$(cat "$ETAT/compose.env")" = "$(contenu_compose_env prod "$NOUVELLE" 0.2.0)" ]
    [ "$(signaux)" = "$(signal 'déployé 0.2.0') $HC" ]
  done
  # la version déployée monte /sauvegardes : le déploiement suivant prend son instantané
  : >"$APPELS"
  deployer prod "$suivante" 0.3.0
  [ "$status" -eq 0 ]
  [ "$(appels_de docker | grep -c ' exec -T app ')" -eq 1 ]
  [ -n "$(find "$pre" -mindepth 1 -maxdepth 1 -type d -regextype posix-extended -regex '.*/[0-9]{8}T[0-9]{6}Z')" ]
}

# --- instantané ------------------------------------------------------------------------------

# Migration 4 : l'instantané d'avant déploiement est un dossier qui a la forme de /donnees, sous
# /sauvegardes/pre-deploiement/<AAAAMMJJTHHMMSSZ>. Il est écrit dans le conteneur en service par la
# commande SAUVEGARDER de deploiement/projet.env, passée mot à mot. Seul son code compte : une
# sortie que le script ne comprend pas ne l'arrête pas. La commande écrit sous un nom provisoire,
# <AAAAMMJJTHHMMSSZ>.partiel, que le script renomme après le code 0 (R13).
@test "deployer_instantane_dans_un_dossier" {
  deja_en_service "$ANCIENNE" 0.1.0
  export DOUBLE_DOCKER_SAUVEGARDE_SORTIE='{"integrite":"inconnue"}'
  deployer prod "$NOUVELLE" 0.2.0
  [ "$status" -eq 0 ]
  local dc ligne destination
  dc="$(dc_de prod)"
  ligne="$(appels_de docker | grep -F "$dc exec ")"
  destination="${ligne##* }"
  [[ "$destination" =~ ^/sauvegardes/pre-deploiement/[0-9]{8}T[0-9]{6}Z\.partiel$ ]]
  [ "$ligne" = "$dc exec -T app outil sauvegarder --forme dossier $destination" ]
  destination="${destination%.partiel}"
  # sur l'hôte, dans les sauvegardes de la prod : un dossier, au contenu de /donnees, sous son nom
  # définitif ; le nom provisoire ne reste pas
  [ -d "$VEILLE_EMPLOI_RACINE_SAUVEGARDES${destination#/sauvegardes}" ]
  [ -f "$VEILLE_EMPLOI_RACINE_SAUVEGARDES${destination#/sauvegardes}/donnees.txt" ]
  [ ! -e "$VEILLE_EMPLOI_RACINE_SAUVEGARDES${destination#/sauvegardes}.partiel" ]
  [[ "$output" == *"instantané : $destination"* ]]
  [ "$(cat "$ETAT/deploye")" = "$NOUVELLE 0.2.0 -" ]
}

# R22 : la commande SAUVEGARDER crée son dossier, pas ses parents. pre-deploiement/ n'existe pas
# avant le premier instantané d'avant déploiement (la sauvegarde de la nuit ne crée que
# quotidiennes/, et le staging n'en a pas) : le script le crée sur l'hôte, comme sauvegarder.sh
# crée quotidiennes/. Le double de docker refuse un parent absent, comme le ferait la commande.
@test "deployer_cree_pre_deploiement_avant_l_instantane" {
  deja_en_service "$ANCIENNE" 0.1.0
  local pre="$VEILLE_EMPLOI_RACINE_SAUVEGARDES/pre-deploiement" instantane
  rm -rf "$pre"
  deployer prod "$NOUVELLE" 0.2.0
  [ "$status" -eq 0 ]
  [ -d "$pre" ]
  # un seul instantané, un dossier sous son nom définitif, et son couple à côté (M-0005, § 3)
  [ "$(find "$pre" -mindepth 1 -maxdepth 1 | wc -l)" -eq 2 ]
  instantane="$(find "$pre" -mindepth 1 -maxdepth 1 -type d)"
  [[ "$(basename "$instantane")" =~ ^[0-9]{8}T[0-9]{6}Z$ ]]
  [ -d "$instantane" ]
  [ -f "$instantane.couple" ]
  [ -f "$instantane/donnees.txt" ]
  [ "$(cat "$ETAT/deploye")" = "$NOUVELLE 0.2.0 -" ]
}

# L'instantané d'avant déploiement est une copie en clair des données. Comme sauvegarder.sh
# pour quotidiennes/, le script ramène le dossier des sauvegardes et pre-deploiement/ à 700, même
# s'ils existaient déjà avec des droits plus larges.
@test "deployer_protege_pre_deploiement" {
  deja_en_service "$ANCIENNE" 0.1.0
  local sauvegardes="$VEILLE_EMPLOI_RACINE_SAUVEGARDES" pre="$VEILLE_EMPLOI_RACINE_SAUVEGARDES/pre-deploiement"
  mkdir -p "$pre"
  chmod 755 "$sauvegardes" "$pre"
  deployer prod "$NOUVELLE" 0.2.0
  [ "$status" -eq 0 ]
  [ "$(stat -c %a "$sauvegardes")" = 700 ]
  [ "$(stat -c %a "$pre")" = 700 ]
}

# La sauvegarde de la nuit, qui purge pre-deploiement/, ne tourne qu'en prod, alors que le
# staging se déploie à chaque fusion. Le déploiement purge donc son propre pre-deploiement/ après un
# instantané réussi : 30 jours, d'après le nom (la regex de sauvegarder.sh), jamais un autre nom.
@test "deployer_purge_ses_instantanes_de_plus_de_30_jours" {
  preparer_secrets_de_test staging JETON=jeton-staging-7 HC_SONDE=https://hc.example/ping/sonde-staging
  en_service staging "$ANCIENNE" main
  poser_donnees staging
  local pre="$VEILLE_EMPLOI_RACINE_DONNEES/staging/sauvegardes/pre-deploiement" vieux recent nom
  vieux="$(date -u -d '31 days ago' +%Y%m%dT%H%M%SZ)"
  recent="$(date -u -d '1 hour ago' +%Y%m%dT%H%M%SZ)"
  for nom in "$vieux" "$vieux.partiel" "$recent" "$vieux.copie" garder; do
    mkdir -p "$pre/$nom/sous"
    echo "$nom" >"$pre/$nom/sous/donnees.txt"
  done
  deployer staging "$NOUVELLE" main
  [ "$status" -eq 0 ]
  # plus de 30 jours, par le nom : partent en entier, .partiel compris
  [ ! -e "$pre/$vieux" ]
  [ ! -e "$pre/$vieux.partiel" ]
  # le récent, les noms d'une autre forme et l'instantané du jour restent
  [ -f "$pre/$recent/sous/donnees.txt" ]
  [ -f "$pre/$vieux.copie/sous/donnees.txt" ]
  [ -f "$pre/garder/sous/donnees.txt" ]
  # avec le couple de l'instantané du jour
  [ "$(find "$pre" -mindepth 1 -maxdepth 1 | wc -l)" -eq 5 ]
  [ "$(cat "$VEILLE_EMPLOI_RACINE_ETAT/staging/deploye")" = "$NOUVELLE main -" ]
}

# Une purge en échec est journalisée, et le déploiement continue : elle ne change rien à la version.
@test "deployer_continue_si_la_purge_echoue" {
  deja_en_service "$ANCIENNE" 0.1.0
  local pre="$VEILLE_EMPLOI_RACINE_SAUVEGARDES/pre-deploiement" vieux
  vieux="$(date -u -d '31 days ago' +%Y%m%dT%H%M%SZ)"
  mkdir -p "$pre/$vieux/verrouille"
  echo "reste" >"$pre/$vieux/verrouille/donnees.txt"
  # un sous-dossier sans droit d'écriture : rm -rf ne peut pas le vider
  chmod 500 "$pre/$vieux/verrouille"
  deployer prod "$NOUVELLE" 0.2.0
  chmod 700 "$pre/$vieux/verrouille"
  [ "$status" -eq 0 ]
  [[ "$output" == *"purge de $pre en échec"* ]]
  [ "$(cat "$ETAT/deploye")" = "$NOUVELLE 0.2.0 -" ]
  [ "$(signaux)" = "$(signal 'déployé 0.2.0') $HC" ]
}

# M-0005, § 3 : l'instantané d'avant le déploiement note, à côté de lui et jamais
# dedans, <horodatage>.couple, le couple de deploye au moment de l'instantané : celui que le
# déploiement quitte. Un état d'avant la v0.7.0 donne le commit « - ». La purge de pre-deploiement/
# retire le couple avec son instantané, et un couple seul de plus de 30 jours.
@test "deployer : l'instantané d'avant le déploiement note le couple qu'il quitte" {
  deja_en_service "$ANCIENNE" 0.1.0
  local pre="$VEILLE_EMPLOI_RACINE_SAUVEGARDES/pre-deploiement" vieux ancien instantane
  vieux="$(date -u -d '31 days ago' +%Y%m%dT%H%M%SZ)"
  ancien="$(date -u -d '40 days ago' +%Y%m%dT%H%M%SZ)"
  mkdir -p "$pre/$vieux"
  echo "vieux" >"$pre/$vieux/donnees.txt"
  echo "$ANCIENNE 0.0.9 -" >"$pre/$vieux.couple"
  echo "$ANCIENNE 0.0.8 -" >"$pre/$ancien.couple"
  deployer prod "$NOUVELLE" 0.2.0
  [ "$status" -eq 0 ]
  instantane="$(find "$pre" -mindepth 1 -maxdepth 1 -type d)"
  [[ "$(basename "$instantane")" =~ ^[0-9]{8}T[0-9]{6}Z$ ]]
  [ "$(cat "$instantane.couple")" = "$ANCIENNE 0.1.0 -" ]
  [[ "$output" == *"couple noté : $instantane.couple ($ANCIENNE 0.1.0 -)"* ]]
  # à côté de l'instantané, jamais dedans : il a la forme de /donnees
  [ "$(cd "$instantane" && find . -mindepth 1 | LC_ALL=C sort)" = "$(printf '%s\n' ./.cachee ./donnees.txt ./sous ./sous/profond.txt)" ]
  # la purge : le vieil instantané et son couple, le couple seul
  [ ! -e "$pre/$vieux" ]
  [ ! -e "$pre/$vieux.couple" ]
  [ ! -e "$pre/$ancien.couple" ]
  [ "$(find "$pre" -mindepth 1 -maxdepth 1 | wc -l)" -eq 2 ]
  # au déploiement suivant, le couple quitté est celui que ce déploiement a écrit
  rm -rf "$pre"
  deployer prod "$SUIVANTE" 0.3.0
  [ "$status" -eq 0 ]
  instantane="$(find "$pre" -mindepth 1 -maxdepth 1 -type d)"
  [ "$(cat "$instantane.couple")" = "$NOUVELLE 0.2.0 -" ]
}

# L'horloge des instantanés ne vieillit pas (modele-projet#136) : ses horodatages tombent la veille
# de la vraie date, avant la vraie heure et après la limite de la purge de 30 jours, qui lit la
# vraie horloge.
# Un jour figé, le 15/10/2026, est passé sous cette limite le 14/11/2026 : la purge retirait alors
# les instantanés des tests.
@test "aide : l'horloge des instantanés reste dans la fenêtre de la purge" {
  local premier second maintenant limite jour
  # le jour de l'horloge, relevé à neuf : la veille de la vraie date, après la limite de la purge
  [[ "$(jour_de_l_horloge)" < "$(date -u +%Y%m%d)" ]]
  [[ "$(date -u -d '30 days ago' +%Y%m%d)" < "$(jour_de_l_horloge)" ]]
  # un jour déjà relevé dans le test reste le sien : un test qui passe minuit garde son jour. Le
  # double ne s'installe qu'une fois par test : installé de nouveau, il prendrait pour la vraie
  # `date` le double déjà en place, et s'appellerait sans fin.
  jour="$(date -u -d '2 days ago' +%Y%m%d)"
  echo "$jour" >"$BATS_TEST_TMPDIR/horloge-jour"
  horloge_qui_avance
  premier="$(date -u +%Y%m%dT%H%M%SZ)"
  second="$(date -u +%Y%m%dT%H%M%SZ)"
  maintenant="$(date -u -d now +%Y%m%dT%H%M%SZ)"
  limite="$(date -u -d '30 days ago' +%Y%m%dT%H%M%SZ)"
  [ "$premier" = "${jour}T000001Z" ]
  [[ "$premier" < "$second" ]]
  [[ "$limite" < "$premier" ]]
  [[ "$second" < "$maintenant" ]]
}

# Le retour arrière manuel prend son instantané comme un déploiement : son .couple nomme le couple
# qu'il quitte, celui de deploye avant le retour, et non celui vers lequel il revient (M-0005, § 3).
@test "deployer : le retour arrière note le couple qu'il quitte" {
  local pre="$VEILLE_EMPLOI_RACINE_SAUVEGARDES/pre-deploiement" instantanes
  deux_versions
  deployer prod --retour
  [ "$status" -eq 0 ]
  [ "$(cat "$ETAT/deploye")" = "$ANCIENNE 0.1.0 -" ]
  # deux instantanés : celui du déploiement de la nouvelle, puis celui du retour
  mapfile -t instantanes < <(find "$pre" -mindepth 1 -maxdepth 1 -type d | LC_ALL=C sort)
  [ "${#instantanes[@]}" -eq 2 ]
  [ "$(cat "${instantanes[0]}.couple")" = "$ANCIENNE 0.1.0 -" ]
  [ "$(cat "${instantanes[1]}.couple")" = "$NOUVELLE 0.2.0 -" ]
  [[ "$output" == *"couple noté : ${instantanes[1]}.couple ($NOUVELLE 0.2.0 -)"* ]]
  [ "$(cd "${instantanes[1]}" && find . -mindepth 1 | LC_ALL=C sort)" = "$(printf '%s\n' ./.cachee ./donnees.txt ./sous ./sous/profond.txt)" ]
}

# Un instantané en échec garde son nom provisoire, pour le diagnostic, mais la sonde
# retente le déploiement toutes les 5 minutes, et chaque tentative laisserait le sien : 12 copies
# en clair par heure. Avant chaque instantané, les .partiel de pre-deploiement/ sont retirés ; seul
# reste celui de la dernière tentative. Un instantané complet, ou un nom d'une autre forme, ne part
# jamais, et un lien n'est pas suivi.
@test "deployer_ne_garde_que_le_dernier_instantane_partiel" {
  deja_en_service "$ANCIENNE" 0.1.0
  local pre="$VEILLE_EMPLOI_RACINE_SAUVEGARDES/pre-deploiement" complet ailleurs nom partiels _
  local autres=()
  complet="$(date -u -d '1 hour ago' +%Y%m%dT%H%M%SZ)"
  autres=("$complet.partiel.copie" autre.partiel "x$complet.partiel" "${complet%Z}.partiel")
  for nom in "$complet" "${autres[@]}"; do
    mkdir -p "$pre/$nom/sous"
    echo "$nom" >"$pre/$nom/sous/donnees.txt"
  done
  # un ancien .partiel qui est un fichier part aussi ; un lien au nom d'un .partiel reste, et ce
  # qu'il désigne n'est pas touché
  echo "fichier" >"$pre/$(date -u -d '2 hours ago' +%Y%m%dT%H%M%SZ).partiel"
  ailleurs="$BATS_TEST_TMPDIR/ailleurs"
  mkdir -p "$ailleurs"
  echo "à garder" >"$ailleurs/donnees.txt"
  ln -s "$ailleurs" "$pre/$(date -u -d '3 hours ago' +%Y%m%dT%H%M%SZ).partiel"
  horloge_qui_avance
  export DOUBLE_DOCKER_SAUVEGARDE_FORME=partielle
  for _ in 1 2; do
    deployer prod "$NOUVELLE" 0.2.0
    [ "$status" -eq 1 ]
    [[ "$output" == *"instantané impossible (code 1)"* ]]
  done
  # un seul .partiel qui ne soit pas un lien : celui de la seconde tentative, intact
  partiels="$(find "$pre" -mindepth 1 -maxdepth 1 ! -type l -regextype posix-extended \
    -regex '.*/[0-9]{8}T[0-9]{6}Z\.partiel')"
  [ "$partiels" = "$pre/$(jour_de_l_horloge)T000002Z.partiel" ]
  [ -f "$pre/$(jour_de_l_horloge)T000002Z.partiel/donnees.txt" ]
  # l'instantané complet et les autres noms restent, en entier ; le lien et sa cible aussi
  for nom in "$complet" "${autres[@]}"; do
    [ "$(cat "$pre/$nom/sous/donnees.txt")" = "$nom" ]
  done
  [ "$(find "$pre" -mindepth 1 -maxdepth 1 -type l | wc -l)" -eq 1 ]
  [ "$(cat "$ailleurs/donnees.txt")" = "à garder" ]
  [ "$(find "$pre" -mindepth 1 -maxdepth 1 | wc -l)" -eq 7 ]
  # rien n'a changé : la version en service y reste
  [ "$(cat "$ETAT/deploye")" = "$ANCIENNE 0.1.0" ]
  # la tentative suivante réussit : le .partiel d'avant part, l'instantané complet reste
  unset DOUBLE_DOCKER_SAUVEGARDE_FORME
  deployer prod "$NOUVELLE" 0.2.0
  [ "$status" -eq 0 ]
  [ -z "$(find "$pre" -mindepth 1 -maxdepth 1 ! -type l -regextype posix-extended \
    -regex '.*/[0-9]{8}T[0-9]{6}Z\.partiel')" ]
  [ "$(cat "$pre/$complet/sous/donnees.txt")" = "$complet" ]
  [ "$(cat "$ETAT/deploye")" = "$NOUVELLE 0.2.0 -" ]
}

# Un .partiel qui ne peut pas être retiré est journalisé, et l'instantané se fait quand même : le
# retrait ne sert qu'à borner la place prise, il ne change rien à la version.
@test "deployer_instantane_meme_si_un_ancien_partiel_ne_part_pas" {
  deja_en_service "$ANCIENNE" 0.1.0
  local pre="$VEILLE_EMPLOI_RACINE_SAUVEGARDES/pre-deploiement" ancien
  ancien="$(date -u -d '1 hour ago' +%Y%m%dT%H%M%SZ).partiel"
  mkdir -p "$pre/$ancien/verrouille"
  echo "reste" >"$pre/$ancien/verrouille/donnees.txt"
  # un sous-dossier sans droit d'écriture : rm -rf ne peut pas le vider
  chmod 500 "$pre/$ancien/verrouille"
  deployer prod "$NOUVELLE" 0.2.0
  chmod 700 "$pre/$ancien/verrouille"
  [ "$status" -eq 0 ]
  [[ "$output" == *"instantanés en échec de $pre : retrait impossible"* ]]
  [ -f "$pre/$ancien/verrouille/donnees.txt" ]
  [ -n "$(find "$pre" -mindepth 1 -maxdepth 1 -type d -regextype posix-extended -regex '.*/[0-9]{8}T[0-9]{6}Z')" ]
  [ "$(cat "$ETAT/deploye")" = "$NOUVELLE 0.2.0 -" ]
  [ "$(signaux)" = "$(signal 'déployé 0.2.0') $HC" ]
}

# Un instantané en échec annule le déploiement avant tout changement : rien n'est arrêté ni lancé,
# l'application en service y reste, et rien n'est marqué en échec. La sonde réessaiera au prochain
# passage. Les cas :
#   - un code non nul ;
#   - une commande qui écrit une partie puis échoue : le dossier garde son nom provisoire (R13) ;
#   - une commande qui rend 0 sans écrire son dossier : rien à renommer ;
#   - une destination déjà présente : rien n'est lancé ni écrasé ;
#   - un dossier vide apparu au nom définitif pendant l'écriture : `mv -T` le remplacerait sans
#     bruit, il ne doit pas ;
#   - pre-deploiement/ impossible à créer (un fichier à sa place) : la commande n'est pas lancée ;
#   - aucune commande SAUVEGARDER dans projet.env.
@test "deployer_instantane_en_echec_n_arrete_rien" {
  deja_en_service "$ANCIENNE" 0.1.0
  cp "$ETAT/compose.env" "$BATS_TEST_TMPDIR/compose.env.avant"
  local cas vrai pre="$VEILLE_EMPLOI_RACINE_SAUVEGARDES/pre-deploiement"
  vrai="$(command -v date)"
  for cas in code-1 code-2 partiel sans-fichier deja-present apparu pre-impossible sans-commande; do
    : >"$APPELS"
    # chaque cas part de pre-deploiement/ vide : deux cas dans la même seconde viseraient le même nom
    rm -rf "$pre" "$DOUBLES/date"
    unset DOUBLE_DOCKER_SAUVEGARDE_CODE DOUBLE_DOCKER_SAUVEGARDE_SORTIE DOUBLE_DOCKER_SAUVEGARDE_FORME \
      DOUBLE_DOCKER_SAUVEGARDE_SANS_FICHIER
    case "$cas" in
      code-*)
        export DOUBLE_DOCKER_SAUVEGARDE_CODE="${cas#code-}"
        export DOUBLE_DOCKER_SAUVEGARDE_SORTIE='données illisibles : /donnees'
        ;;
      partiel) export DOUBLE_DOCKER_SAUVEGARDE_FORME=partielle ;;
      sans-fichier) export DOUBLE_DOCKER_SAUVEGARDE_SANS_FICHIER=1 ;;
      deja-present)
        # shellcheck disable=SC2016  # le corps du double se développe quand il s'exécute, pas ici
        creer_double date 'if [ "$*" = "-u +%Y%m%dT%H%M%SZ" ]; then echo 20261018T024500Z; else exec '"$vrai"' "$@"; fi'
        mkdir -p "$pre/20261018T024500Z"
        echo "déjà là" >"$pre/20261018T024500Z/donnees.txt"
        ;;
      apparu) export DOUBLE_DOCKER_SAUVEGARDE_FORME=apparue ;;
      pre-impossible) echo "pas un dossier" >"$pre" ;;
      sans-commande) printf '%s\n' 'VERIFIER=outil verifier' >"$CLONE/deploiement/projet.env" ;;
    esac
    deployer prod "$NOUVELLE" 0.2.0
    [ "$status" -eq 1 ]
    # rien n'est arrêté ni lancé : l'application en service y reste
    [ "$(appels_de docker | grep -cE ' (up|stop|down) ')" -eq 0 ]
    grep -Fx "VEILLE_EMPLOI_IMAGE=$ANCIENNE" "$EN_SERVICE"
    # rien n'a changé : la sonde réessaiera au prochain passage
    diff "$ETAT/compose.env" "$BATS_TEST_TMPDIR/compose.env.avant"
    [ ! -e "$ETAT/compose.env.precedent" ]
    [ ! -e "$ETAT/echec" ]
    [ "$(cat "$ETAT/deploye")" = "$ANCIENNE 0.1.0" ]
    [ "$(signaux)" = "$(signal 'instantané impossible avant 0.2.0, rien n'"'"'a changé') $HC/fail" ]
    case "$cas" in
      sans-commande)
        [ "$(appels_de docker | grep -c ' exec ')" -eq 0 ]
        [[ "$output" == *"réglage SAUVEGARDER absent"* ]]
        ;;
      partiel)
        [[ "$output" == *"instantané impossible (code 1)"* ]]
        # le dossier écrit en partie garde son nom provisoire ; aucun nom définitif
        [ -n "$(find "$pre" -mindepth 1 -maxdepth 1 -name '*.partiel')" ]
        [ -z "$(find "$pre" -mindepth 1 -maxdepth 1 ! -name '*.partiel')" ]
        ;;
      sans-fichier)
        [[ "$output" == *"la commande a rendu 0, mais"*"ne peut pas prendre le nom"* ]]
        [ -z "$(find "$pre" -mindepth 1 -maxdepth 1 2>/dev/null)" ]
        ;;
      deja-present)
        [[ "$output" == *"$pre/20261018T024500Z existe déjà"* ]]
        [ "$(appels_de docker | grep -c ' exec ')" -eq 0 ]
        [ "$(cat "$pre/20261018T024500Z/donnees.txt")" = "déjà là" ]
        [ "$(find "$pre" -mindepth 1 -maxdepth 1 | wc -l)" -eq 1 ]
        ;;
      apparu)
        [[ "$output" == *"ne peut pas prendre le nom"* ]]
        # le dossier apparu n'est pas remplacé ; l'instantané garde son nom provisoire
        [ -n "$(find "$pre" -mindepth 1 -maxdepth 1 -type d -name '*Z' -empty)" ]
        [ -n "$(find "$pre" -mindepth 2 -maxdepth 2 -path '*.partiel/donnees.txt')" ]
        ;;
      pre-impossible)
        [[ "$output" == *"instantané impossible : le dossier $pre ne peut pas être créé"* ]]
        [ "$(appels_de docker | grep -c ' exec ')" -eq 0 ]
        [ "$(cat "$pre")" = "pas un dossier" ]
        ;;
      *) [[ "$output" == *"instantané impossible (code ${cas#code-}) : données illisibles"* ]] ;;
    esac
  done
}

# Docker injoignable avant tout changement : on s'arrête, sans marquer la version en échec.
@test "refuse_de_deployer_si_l_etat_de_l_application_est_illisible" {
  deja_en_service "$ANCIENNE" 0.1.0
  mv "$DOUBLES/docker" "$DOUBLES/docker-double"
  creer_double docker "[[ \" \$* \" != *' ps '* ]] || exit 1
exec '$DOUBLES/docker-double' \"\$@\""
  deployer prod "$NOUVELLE" 0.2.0
  [ "$status" -eq 1 ]
  [ "$(nombre_de_lancements)" -eq 0 ]
  [ ! -e "$ETAT/echec" ]
  [ ! -e "$ETAT/compose.env.precedent" ]
  [ "$(signaux)" = "$(signal 'état de l'"'"'application illisible avant 0.2.0, rien n'"'"'a changé') $HC/fail" ]
}

# --- échecs et retour arrière ----------------------------------------------------------------

# Une image sans label de révision (« <no value> ») ne peut pas être vérifiée : échec.
@test "image_sans_revision_compte_comme_echec" {
  deja_en_service "$ANCIENNE" 0.1.0
  mv "$DOUBLES/docker" "$DOUBLES/docker-double"
  creer_double docker "if [[ \" \$* \" == *'image.revision'*' $NOUVELLE '* ]]; then echo '<no value>'; exit 0; fi
exec '$DOUBLES/docker-double' \"\$@\""
  deployer prod "$NOUVELLE" 0.2.0
  [ "$status" -eq 1 ]
  [ "$(cat "$ETAT/echec")" = "$NOUVELLE -" ]
  [ "$(cat "$ETAT/compose.env")" = "$(contenu_compose_env prod "$ANCIENNE" 0.1.0)" ]
  [ "$(signaux)" = "$(signal 'échec 0.2.0, retour à 0.1.0') $HC/fail" ]
  [[ "$output" == *"révision illisible"* ]]
}

@test "retour_arriere_si_la_sante_echoue" {
  deja_en_service "$ANCIENNE" 0.1.0
  export DOUBLE_CURL_SANTE_KO="$NOUVELLE"
  deployer prod "$NOUVELLE" 0.2.0
  [ "$status" -eq 1 ]
  # la version est marquée en échec, l'ancienne est restaurée et de nouveau en service
  [ "$(cat "$ETAT/echec")" = "$NOUVELLE -" ]
  [ "$(cat "$ETAT/compose.env")" = "$(contenu_compose_env prod "$ANCIENNE" 0.1.0)" ]
  [ "$(cat "$ETAT/deploye")" = "$ANCIENNE 0.1.0" ]
  [ ! -e "$ETAT/precedent" ]
  grep -Fx "VEILLE_EMPLOI_IMAGE=$ANCIENNE" "$EN_SERVICE"
  [ "$(nombre_de_lancements)" -eq 2 ]
  # dix essais pour la nouvelle version, puis un contrôle réussi de l'ancienne
  [ "$(appels_de curl | grep -c '127\.0\.0\.1')" -eq 11 ]
  [ "$(signaux)" = "$(signal 'échec 0.2.0, retour à 0.1.0') $HC/fail" ]
}

@test "revision_inattendue_compte_comme_echec" {
  deja_en_service "$ANCIENNE" 0.1.0
  export DOUBLE_CURL_REVISION_FAUSSE="$NOUVELLE"
  deployer prod "$NOUVELLE" 0.2.0
  [ "$status" -eq 1 ]
  [ "$(cat "$ETAT/echec")" = "$NOUVELLE -" ]
  [ "$(cat "$ETAT/compose.env")" = "$(contenu_compose_env prod "$ANCIENNE" 0.1.0)" ]
  [ "$(cat "$ETAT/deploye")" = "$ANCIENNE 0.1.0" ]
  [ "$(signaux)" = "$(signal 'échec 0.2.0, retour à 0.1.0') $HC/fail" ]
  # la révision attendue est celle du label de l'image
  appels_de docker | grep -Fx "docker image inspect -f {{index .Config.Labels \"org.opencontainers.image.revision\"}} $NOUVELLE"
}

# Un 200 sans corps n'est pas une santé conforme (jq 1.6 rendrait 0 avec `-e` sur une entrée vide).
@test "sante_sans_corps_compte_comme_echec" {
  deja_en_service "$ANCIENNE" 0.1.0
  export DOUBLE_CURL_SANTE_VIDE="$NOUVELLE"
  deployer prod "$NOUVELLE" 0.2.0
  [ "$status" -eq 1 ]
  [ "$(cat "$ETAT/echec")" = "$NOUVELLE -" ]
  [ "$(cat "$ETAT/deploye")" = "$ANCIENNE 0.1.0" ]
  [ "$(signaux)" = "$(signal 'échec 0.2.0, retour à 0.1.0') $HC/fail" ]
}

@test "echec_du_lancement_declenche_le_retour_arriere" {
  deja_en_service "$ANCIENNE" 0.1.0
  export DOUBLE_DOCKER_UP_ECHEC="$NOUVELLE"
  deployer prod "$NOUVELLE" 0.2.0
  [ "$status" -eq 1 ]
  [ "$(cat "$ETAT/echec")" = "$NOUVELLE -" ]
  [ "$(cat "$ETAT/compose.env")" = "$(contenu_compose_env prod "$ANCIENNE" 0.1.0)" ]
  grep -Fx "VEILLE_EMPLOI_IMAGE=$ANCIENNE" "$EN_SERVICE"
  # pas de contrôle de santé d'une version qui n'a pas démarré : seul l'ancien est contrôlé
  [ "$(appels_de curl | grep -c '127\.0\.0\.1')" -eq 1 ]
  [ "$(signaux)" = "$(signal 'échec 0.2.0, retour à 0.1.0') $HC/fail" ]
}

@test "retour_arriere_en_echec_le_signale" {
  deja_en_service "$ANCIENNE" 0.1.0
  export DOUBLE_CURL_SANTE_KO="$NOUVELLE $ANCIENNE"
  deployer prod "$NOUVELLE" 0.2.0
  [ "$status" -eq 1 ]
  [ "$(cat "$ETAT/echec")" = "$NOUVELLE -" ]
  [ "$(cat "$ETAT/compose.env")" = "$(contenu_compose_env prod "$ANCIENNE" 0.1.0)" ]
  [ "$(cat "$ETAT/deploye")" = "$ANCIENNE 0.1.0" ]
  [ "$(signaux)" = "$(signal 'échec 0.2.0, retour à 0.1.0 en échec') $HC/fail" ]
}

# echec est écrit avant le retour arrière : si celui-ci est coupé net, la sonde ne retentera pas la
# version à chaque passage. Ici, le `up` du retour arrière tue deployer.sh (kill -9). La version
# en échec tourne encore, sans qu'aucun signal soit parti : la sonde suivante doit le voir.
@test "retour_arriere_coupe_net_est_signale_par_la_sonde_suivante" {
  deja_en_service "$ANCIENNE" 0.1.0
  export DOUBLE_CURL_SANTE_KO="$NOUVELLE"
  mv "$DOUBLES/docker" "$DOUBLES/docker-double"
  creer_double docker "
if [[ \" \$* \" == *' up '* ]] && grep -qFx 'VEILLE_EMPLOI_IMAGE=$ANCIENNE' '$ETAT/compose.env'; then
  kill -9 \"\$PPID\"
  exit 1
fi
exec '$DOUBLES/docker-double' \"\$@\""
  deployer prod "$NOUVELLE" 0.2.0
  [ "$status" -eq 137 ]
  # l'état figé par la coupure : echec écrit, compose.env déjà restauré, mais la nouvelle version
  # toujours en service, et aucun signal
  [ "$(cat "$ETAT/echec")" = "$NOUVELLE -" ]
  [ "$(cat "$ETAT/deploye")" = "$ANCIENNE 0.1.0" ]
  [ "$(cat "$ETAT/compose.env")" = "$(contenu_compose_env prod "$ANCIENNE" 0.1.0)" ]
  grep -Fx "VEILLE_EMPLOI_IMAGE=$NOUVELLE" "$EN_SERVICE"
  [ -z "$(signaux)" ]

  # passage suivant de la sonde : alerte, et aucune relance automatique
  mv -f "$DOUBLES/docker-double" "$DOUBLES/docker"
  installer_doubles git
  : >"$APPELS"
  export DOUBLE_GIT_ETIQUETTES=v0.2.0 DOUBLE_DOCKER_EMPREINTE="$NOUVELLE"
  run bash "$CLONE/deploiement/sonder.sh" prod
  [ "$status" -eq 1 ]
  [ "$(signaux)" = "$(signal 'retour arrière incomplet : la santé locale n'"'"'annonce pas la version déployée (0.1.0)') $HC/fail" ]
  [ "$(nombre_de_lancements)" -eq 0 ]
  [ "$(appels_de docker | grep -c ' exec ')" -eq 0 ]
  # et de même à chaque passage, tant que personne n'est intervenu
  : >"$APPELS"
  run bash "$CLONE/deploiement/sonder.sh" prod
  [ "$status" -eq 1 ]
  [[ "$(signaux)" == *"retour arrière incomplet"*"$HC/fail" ]]
}

@test "premier_deploiement_en_echec_alerte_sans_retour" {
  export DOUBLE_CURL_SANTE_KO="$NOUVELLE"
  deployer prod "$NOUVELLE" 0.2.0
  [ "$status" -eq 1 ]
  [ "$(cat "$ETAT/echec")" = "$NOUVELLE -" ]
  [ ! -e "$ETAT/deploye" ]
  [ ! -e "$ETAT/compose.env.precedent" ]
  [ "$(nombre_de_lancements)" -eq 1 ]
  # rien à restaurer : la version en échec est arrêtée plutôt que laissée en service
  appels_de docker | grep -Fx "$(dc_de prod) stop"
  [ ! -e "$EN_SERVICE" ]
  [ "$(signaux)" = "$(signal 'échec 0.2.0, retour à aucun') $HC/fail" ]
}

# Après un premier déploiement en échec, compose.env est celui du couple en échec, et aucun couple
# n'est déployé : le premier succès ne parle ni d'interruption, ni d'un compose.env.precedent qui
# n'existe pas.
@test "deployer : le succès qui suit un premier déploiement en échec ne parle pas d'interruption" {
  export DOUBLE_CURL_SANTE_KO="$NOUVELLE"
  deployer prod "$NOUVELLE" 0.2.0
  [ "$status" -eq 1 ]
  [ ! -e "$ETAT/deploye" ]
  unset DOUBLE_CURL_SANTE_KO
  : >"$APPELS"
  deployer prod "$SUIVANTE" 0.3.0
  [ "$status" -eq 0 ]
  [[ "$output" != *"interrompu"* ]]
  [[ "$output" == *"aucun couple déployé : le compose.env d'un déploiement en échec n'est pas gardé"* ]]
  [ "$(cat "$ETAT/deploye")" = "$SUIVANTE 0.3.0 -" ]
  [ ! -e "$ETAT/precedent" ]
  [ ! -e "$ETAT/compose.env.precedent" ]
  [ ! -e "$ETAT/echec" ]
  [ "$(signaux)" = "$(signal 'déployé 0.3.0') $HC" ]
}

# Un déploiement coupé (Ctrl-C, arrêt de l'unité) laisse un compose.env qui n'est pas celui de la
# version déployée. Il ne doit pas devenir la cible du retour arrière suivant.
@test "un_deploiement_interrompu_ne_devient_pas_la_cible_du_retour_arriere" {
  local interrompue
  interrompue="ghcr.io/edouardzemb/veille-emploi@sha256:$(printf '3%.0s' {1..64})"
  deja_en_service "$ANCIENNE" 0.1.0
  cp "$ETAT/compose.env" "$ETAT/compose.env.precedent"
  contenu_compose_env prod "$interrompue" 0.1.5 >"$ETAT/compose.env"
  export DOUBLE_CURL_SANTE_KO="$NOUVELLE"
  deployer prod "$NOUVELLE" 0.2.0
  [ "$status" -eq 1 ]
  [ "$(cat "$ETAT/compose.env")" = "$(contenu_compose_env prod "$ANCIENNE" 0.1.0)" ]
  [ "$(cat "$ETAT/compose.env.precedent")" = "$(contenu_compose_env prod "$ANCIENNE" 0.1.0)" ]
  [ "$(signaux)" = "$(signal 'échec 0.2.0, retour à 0.1.0') $HC/fail" ]
}

# --- retour arrière manuel : deployer.sh <env> --retour ---------------------------------------
#
# Revenir à la version de `precedent`. La version quittée est écrite dans `echec` avant tout
# changement, et gardée : sans cela, la sonde (qui vise la plus haute étiquette) la redéploierait au
# passage suivant.

# deux_versions : 0.1.0 (ANCIENNE) puis 0.2.0 (NOUVELLE) déployées pour de bon, comme sur une prod où
# 0.2.0 pose problème. Les appels sont remis à zéro.
deux_versions() {
  horloge_qui_avance
  deployer prod "$ANCIENNE" 0.1.0
  [ "$status" -eq 0 ]
  poser_donnees prod
  deployer prod "$NOUVELLE" 0.2.0
  [ "$status" -eq 0 ]
  [ "$(cat "$ETAT/precedent")" = "$ANCIENNE 0.1.0 -" ]
  : >"$APPELS"
}

# passage_de_la_sonde : un passage de la vraie sonde de prod, dont la plus haute étiquette est
# v0.2.0 (image NOUVELLE).
passage_de_la_sonde() {
  installer_doubles git
  export DOUBLE_GIT_ETIQUETTES=v0.2.0 DOUBLE_DOCKER_EMPREINTE="$NOUVELLE"
  : >"$APPELS"
  run bash "$CLONE/deploiement/sonder.sh" prod
}

# etat_fige : une copie de l'état, pour vérifier qu'un refus n'a rien touché. Une copie d'avant
# peut porter des instantanés en lecture seule : ses droits sont rendus avant de la retirer.
etat_fige() {
  chmod -R u+rwX "$BATS_TEST_TMPDIR/etat-avant" 2>/dev/null || true
  rm -rf "$BATS_TEST_TMPDIR/etat-avant"
  cp -a "$ETAT" "$BATS_TEST_TMPDIR/etat-avant"
  : >"$APPELS"
}

@test "retour_manuel_revient_a_la_version_precedente_et_garde_la_version_quittee_en_echec" {
  deux_versions
  # echec doit déjà valoir NOUVELLE quand la précédente est relancée : une coupure à ce moment ne
  # laisse pas la sonde redéployer la version quittée
  mv "$DOUBLES/docker" "$DOUBLES/docker-double"
  cat >"$DOUBLES/docker" <<EOF
#!/usr/bin/env bash
if [[ " \$* " == *' up '* ]]; then
  { cat '$ETAT/echec' 2>/dev/null || echo ABSENT; } >'$BATS_TEST_TMPDIR/echec-au-lancement'
fi
exec '$DOUBLES/docker-double' "\$@"
EOF
  chmod +x "$DOUBLES/docker"
  deployer prod --retour
  [ "$status" -eq 0 ]
  [ "$(cat "$ETAT/deploye")" = "$ANCIENNE 0.1.0 -" ]
  [ "$(cat "$BATS_TEST_TMPDIR/echec-au-lancement")" = "$NOUVELLE -" ]
  # gardée, pas effacée : c'est ce qui empêche la sonde de redéployer la version quittée
  [ "$(cat "$ETAT/echec")" = "$NOUVELLE -" ]
  # plus de version précédente : un second --retour ne rebascule pas vers la version en échec
  [ ! -e "$ETAT/precedent" ]
  [ "$(cat "$ETAT/compose.env")" = "$(contenu_compose_env prod "$ANCIENNE" 0.1.0)" ]
  grep -Fx "VEILLE_EMPLOI_IMAGE=$ANCIENNE" "$EN_SERVICE"
  # comme un déploiement : instantané des données en service, un lancement, santé de la précédente
  [ "$(ligne_de ' exec -T app ')" -lt "$(ligne_de ' up -d ')" ]
  [ "$(nombre_de_lancements)" -eq 1 ]
  appels_de curl | grep -Fx 'curl -fsS -m 5 http://127.0.0.1:4310/sante'
  [ "$(signaux)" = "$(signal 'retour à 0.1.0 effectué (depuis 0.2.0)') $HC" ]

  # le passage suivant de la sonde, dont la plus haute étiquette est encore v0.2.0, attend une
  # nouvelle version : ni relance, ni instantané, ni alerte, ni signal (le silence tient l'incident
  # ouvert) — à chaque passage
  local _
  for _ in 1 2; do
    passage_de_la_sonde
    [ "$status" -eq 0 ]
    [[ "$output" == *"couple en échec, attente d'un nouveau"* ]]
    [ "$(nombre_de_lancements)" -eq 0 ]
    [ "$(appels_de docker | grep -c ' exec ')" -eq 0 ]
    [ "$(nombre_d_appels deployer.sh)" -eq 0 ]
    [ -z "$(signaux)" ]
  done
  [ "$(cat "$ETAT/deploye")" = "$ANCIENNE 0.1.0 -" ]
}

@test "apres_un_retour_manuel_la_version_suivante_se_deploie_normalement" {
  local suivante
  suivante="ghcr.io/edouardzemb/veille-emploi@sha256:$(printf '3%.0s' {1..64})"
  deux_versions
  deployer prod --retour
  [ "$status" -eq 0 ]
  deployer prod "$suivante" 0.3.0
  [ "$status" -eq 0 ]
  [ "$(cat "$ETAT/deploye")" = "$suivante 0.3.0 -" ]
  [ "$(cat "$ETAT/precedent")" = "$ANCIENNE 0.1.0 -" ]
  [ ! -e "$ETAT/echec" ]
  [ "$(cat "$ETAT/compose.env.precedent")" = "$(contenu_compose_env prod "$ANCIENNE" 0.1.0)" ]
}

# Le retour nomme le couple qu'il marque en échec, son image et son commit : seul ce couple attend.
# Sans commande de l'instance, le commit est « - », et une étiquette de données ne déploie rien.
@test "deployer : --retour nomme le couple qu'il marque en échec" {
  deux_versions
  deployer prod --retour
  [ "$status" -eq 0 ]
  [[ "$output" == *"couple $NOUVELLE - (0.2.0) marqué en échec : la sonde ne redéploiera pas ce couple"* ]]
  [[ "$output" != *"redéploierait"* ]]
}

# Avec une commande de l'instance, à deux dépôts, la sonde déploie tout couple neuf : en prod, la
# plus haute `vX.Y.Z` avec la plus haute étiquette de données ; en staging, `:main` avec la tête de
# la branche des données. Après un retour, changer une moitié de la cible ramène donc l'autre moitié
# du couple quitté. Le retour dit laquelle, selon ce qu'il change, et ce qui passe d'abord.

# retour_entre <env> <image> <version> <commit> <image quittée> <version quittée> <commit quitté> :
# les deux couples déployés pour de bon dans cet environnement, puis le retour du second au premier,
# qui réussit. La sortie du retour dans output.
retour_entre() {
  deployer "$1" "$2" "$3" --commit-donnees "$4"
  [ "$status" -eq 0 ]
  poser_donnees "$1"
  deployer "$1" "$5" "$6" --commit-donnees "$7"
  [ "$status" -eq 0 ]
  deployer "$1" --retour
  [ "$status" -eq 0 ]
}

@test "deployer : --retour qui change l'image et les données dit ce que chacune ramènerait" {
  local etat_staging="$VEILLE_EMPLOI_RACINE_ETAT/staging" premier
  horloge_qui_avance
  avec_donnees VERIFIER_CONTENU
  commit_de_donnees "$SOUS_CONTENU/page.md"
  premier="$COMMIT"
  commit_de_donnees "$SOUS_CONTENU/page.md" "$SOUS_CONTENU/autre.md"
  retour_entre prod "$ANCIENNE" 0.1.0 "$premier" "$NOUVELLE" 0.2.0 "$COMMIT"
  [ "$(cat "$ETAT/echec")" = "$NOUVELLE $COMMIT" ]
  [[ "$output" == *"couple $NOUVELLE $COMMIT (0.2.0) marqué en échec : la sonde ne redéploiera pas ce couple"* ]]
  [[ "$output" == *"une nouvelle étiquette de données redéploierait 0.2.0 avec elle, une nouvelle vX.Y.Z les données quittées ($COMMIT) : poser d'abord celle qui remplace la moitié en cause"* ]]
  # La ligne de fin nomme le couple marqué en échec, comme le marquage.
  [[ "$output" == *"retour effectué : 0.1.0 ($ANCIENNE, données $premier) ; le couple $NOUVELLE $COMMIT (0.2.0) reste marqué en échec"* ]]

  # Le staging : la sonde vise `:main` et la tête de la branche des données.
  preparer_secrets_de_test staging JETON=jeton-staging-7 HC_SONDE=https://hc.example/ping/sonde-staging
  retour_entre staging "$ANCIENNE" main "$premier" "$NOUVELLE" main "$COMMIT"
  [ "$(cat "$etat_staging/echec")" = "$NOUVELLE $COMMIT" ]
  [[ "$output" == *"couple $NOUVELLE $COMMIT (main) marqué en échec : la sonde ne redéploiera pas ce couple"* ]]
  [[ "$output" == *"un nouveau commit de la branche des données redéploierait l'image quittée avec lui, une fusion dans le code les données quittées ($COMMIT) : corriger d'abord la moitié en cause"* ]]
}

# Un retour qui ne change que l'image : une étiquette de données ramènerait l'image quittée, et une
# `vX.Y.Z` plus haute que la version quittée, sur le commit de la version gardée, passe d'abord.
@test "deployer : --retour qui ne change que l'image dit qu'une étiquette de données la ramènerait" {
  local etat_staging="$VEILLE_EMPLOI_RACINE_ETAT/staging"
  horloge_qui_avance
  avec_donnees VERIFIER_CONTENU
  commit_de_donnees "$SOUS_CONTENU/page.md"
  retour_entre prod "$ANCIENNE" 0.1.0 "$COMMIT" "$NOUVELLE" 0.2.0 "$COMMIT"
  [ "$(cat "$ETAT/echec")" = "$NOUVELLE $COMMIT" ]
  [[ "$output" == *"une nouvelle étiquette de données redéploierait 0.2.0 avec elle : poser d'abord, sur le commit de 0.1.0, une vX.Y.Z plus haute que 0.2.0"* ]]
  [[ "$output" != *"les données quittées"* ]]
  [[ "$output" == *"retour effectué : 0.1.0 ($ANCIENNE, données $COMMIT) ; le couple $NOUVELLE $COMMIT (0.2.0) reste marqué en échec"* ]]

  preparer_secrets_de_test staging JETON=jeton-staging-7 HC_SONDE=https://hc.example/ping/sonde-staging
  retour_entre staging "$ANCIENNE" main "$COMMIT" "$NOUVELLE" main "$COMMIT"
  [ "$(cat "$etat_staging/echec")" = "$NOUVELLE $COMMIT" ]
  [[ "$output" == *"un nouveau commit de la branche des données redéploierait l'image quittée avec lui : fusionner d'abord le correctif du code"* ]]
  [[ "$output" != *"les données quittées"* ]]
}

# Un retour qui ne change que le commit de données, sous la même image : une nouvelle `vX.Y.Z` (en
# staging, une fusion dans le code) ramènerait les données quittées, et la version gardée, elle,
# peut revenir. Les données corrigées passent d'abord.
@test "deployer : --retour qui ne change que les données dit qu'une version du code les ramènerait" {
  local etat_staging="$VEILLE_EMPLOI_RACINE_ETAT/staging" premier
  horloge_qui_avance
  avec_donnees VERIFIER_CONTENU
  commit_de_donnees "$SOUS_CONTENU/page.md"
  premier="$COMMIT"
  commit_de_donnees "$SOUS_CONTENU/page.md" "$SOUS_CONTENU/autre.md"
  retour_entre prod "$ANCIENNE" 0.1.0 "$premier" "$ANCIENNE" 0.1.0 "$COMMIT"
  [ "$(cat "$ETAT/echec")" = "$ANCIENNE $COMMIT" ]
  [[ "$output" == *"couple $ANCIENNE $COMMIT (0.1.0) marqué en échec : la sonde ne redéploiera pas ce couple"* ]]
  [[ "$output" == *"une vX.Y.Z sur un nouveau commit redéploierait les données quittées ($COMMIT) avec elle : poser d'abord une étiquette de données sur un commit corrigé"* ]]
  [[ "$output" != *"redéploierait 0.1.0"* ]]
  [[ "$output" != *"une vX.Y.Z plus haute"* ]]
  # 0.1.0 est en service : c'est le couple, et non la version, qui reste marqué en échec.
  [[ "$output" == *"retour effectué : 0.1.0 ($ANCIENNE, données $premier) ; le couple $ANCIENNE $COMMIT (0.1.0) reste marqué en échec"* ]]
  [[ "$output" != *"0.1.0 reste marquée en échec"* ]]

  preparer_secrets_de_test staging JETON=jeton-staging-7 HC_SONDE=https://hc.example/ping/sonde-staging
  retour_entre staging "$ANCIENNE" main "$premier" "$ANCIENNE" main "$COMMIT"
  [ "$(cat "$etat_staging/echec")" = "$ANCIENNE $COMMIT" ]
  [[ "$output" == *"une fusion dans le code redéploierait les données quittées ($COMMIT) avec elle : corriger d'abord la branche des données"* ]]
  [[ "$output" != *"fusionner d'abord le correctif du code"* ]]
  [[ "$output" != *"l'image quittée"* ]]
}

@test "retour_manuel_refuse_sans_version_precedente_et_ne_touche_a_rien" {
  # rien n'a jamais été déployé
  deployer prod --retour
  [ "$status" -eq 64 ]
  [[ "$output" == *"aucune version en service"* ]]
  [ ! -s "$APPELS" ]
  [ ! -e "$ETAT/compose.env" ]
  # une seule version déployée : pas de précédente
  deployer prod "$ANCIENNE" 0.1.0
  [ "$status" -eq 0 ]
  etat_fige
  deployer prod --retour
  [ "$status" -eq 64 ]
  [[ "$output" == *"aucune version précédente"* ]]
  diff -r "$ETAT" "$BATS_TEST_TMPDIR/etat-avant"
  [ ! -s "$APPELS" ]
  # une précédente illisible, ou qui est la version en service : refus aussi
  local contenu
  for contenu in 'pas une image' "$ANCIENNE v0.1.0" "$ANCIENNE 0.1.0"; do
    echo "$contenu" >"$ETAT/precedent"
    etat_fige
    deployer prod --retour
    [ "$status" -eq 64 ]
    diff -r "$ETAT" "$BATS_TEST_TMPDIR/etat-avant"
    [ ! -s "$APPELS" ]
  done
}

@test "un_second_retour_manuel_ne_revient_pas_sur_la_version_en_echec" {
  deux_versions
  deployer prod --retour
  [ "$status" -eq 0 ]
  etat_fige
  deployer prod --retour
  [ "$status" -eq 64 ]
  diff -r "$ETAT" "$BATS_TEST_TMPDIR/etat-avant"
  [ ! -s "$APPELS" ]
}

# Rien n'est marqué en échec avant le premier changement d'état : un retour qui n'a pas pu
# commencer ne laisse aucune trace, et la sonde reste aussi sûre qu'avant.
@test "retour_manuel_qui_ne_peut_pas_commencer_ne_change_rien" {
  deux_versions
  etat_fige
  export DOUBLE_DOCKER_SAUVEGARDE_CODE=1
  deployer prod --retour
  [ "$status" -eq 1 ]
  [ "$(nombre_de_lancements)" -eq 0 ]
  diff -r "$ETAT" "$BATS_TEST_TMPDIR/etat-avant"
  [ "$(signaux)" = "$(signal 'instantané impossible avant le retour à 0.1.0, rien n'"'"'a changé') $HC/fail" ]
}

# Santé de la précédente en échec : comme tout déploiement raté, la version en service avant le
# retour est remise en service, le résultat est signalé /fail, et l'état reste cohérent. `precedent`
# est gardé, pour une nouvelle tentative une fois la cause réglée. La version quittée reste dans
# `echec`, donc la sonde ne la redéploie pas et, comme elle est encore en service, n'envoie pas de
# signal ok : le silence tient l'incident ouvert.
@test "retour_manuel_dont_la_sante_echoue_remet_la_version_quittee_en_service" {
  deux_versions
  export DOUBLE_CURL_SANTE_KO="$ANCIENNE"
  deployer prod --retour
  [ "$status" -eq 1 ]
  [ "$(cat "$ETAT/deploye")" = "$NOUVELLE 0.2.0 -" ]
  [ "$(cat "$ETAT/precedent")" = "$ANCIENNE 0.1.0 -" ]
  [ "$(cat "$ETAT/echec")" = "$NOUVELLE -" ]
  [ "$(cat "$ETAT/compose.env")" = "$(contenu_compose_env prod "$NOUVELLE" 0.2.0)" ]
  grep -Fx "VEILLE_EMPLOI_IMAGE=$NOUVELLE" "$EN_SERVICE"
  # dix essais pour la précédente, puis un contrôle réussi de la version remise en service
  [ "$(nombre_de_lancements)" -eq 2 ]
  [ "$(appels_de curl | grep -c '127\.0\.0\.1')" -eq 11 ]
  [ "$(signaux)" = "$(signal 'échec du retour à 0.1.0, 0.2.0 remise en service') $HC/fail" ]

  passage_de_la_sonde
  [ "$status" -eq 0 ]
  [ "$(nombre_de_lancements)" -eq 0 ]
  [ "$(nombre_d_appels deployer.sh)" -eq 0 ]
  [ -z "$(signaux)" ]

  # la cause réglée, une nouvelle tentative aboutit
  unset DOUBLE_CURL_SANTE_KO
  deployer prod --retour
  [ "$status" -eq 0 ]
  [ "$(cat "$ETAT/deploye")" = "$ANCIENNE 0.1.0 -" ]
  [ "$(cat "$ETAT/echec")" = "$NOUVELLE -" ]
}

# Et si la version quittée ne revient pas non plus : le signal le dit, et la sonde alerte à chaque
# passage (elle ne relance rien).
@test "retour_manuel_dont_la_version_quittee_ne_revient_pas_est_signale_par_la_sonde" {
  deux_versions
  export DOUBLE_CURL_SANTE_KO="$ANCIENNE $NOUVELLE"
  deployer prod --retour
  [ "$status" -eq 1 ]
  [ "$(signaux)" = "$(signal 'échec du retour à 0.1.0, 0.2.0 remise en service en échec') $HC/fail" ]
  [ "$(cat "$ETAT/echec")" = "$NOUVELLE -" ]
  [ "$(cat "$ETAT/precedent")" = "$ANCIENNE 0.1.0 -" ]

  passage_de_la_sonde
  [ "$status" -eq 1 ]
  [[ "$(signaux)" == "$(signal 'retour arrière incomplet : ')"*" $HC/fail" ]]
  [ "$(nombre_de_lancements)" -eq 0 ]
}

# Retour coupé net (kill -9) au lancement de la précédente : echec vaut déjà la version quittée,
# compose.env décrit la précédente, la version quittée tourne encore. La sonde le voit.
@test "retour_manuel_coupe_net_est_signale_par_la_sonde_suivante" {
  deux_versions
  mv "$DOUBLES/docker" "$DOUBLES/docker-double"
  creer_double docker "
if [[ \" \$* \" == *' up '* ]] && grep -qFx 'VEILLE_EMPLOI_IMAGE=$ANCIENNE' '$ETAT/compose.env'; then
  kill -9 \"\$PPID\"
  exit 1
fi
exec '$DOUBLES/docker-double' \"\$@\""
  deployer prod --retour
  [ "$status" -eq 137 ]
  [ "$(cat "$ETAT/echec")" = "$NOUVELLE -" ]
  [ "$(cat "$ETAT/deploye")" = "$NOUVELLE 0.2.0 -" ]
  [ -z "$(signaux)" ]

  mv -f "$DOUBLES/docker-double" "$DOUBLES/docker"
  passage_de_la_sonde
  [ "$status" -eq 1 ]
  [ "$(signaux)" = "$(signal 'retour arrière incomplet : compose.env ne décrit pas la version déployée (0.2.0)') $HC/fail" ]
  [ "$(nombre_de_lancements)" -eq 0 ]
}

# --- la garde du dossier de données ----------------------------------------------------------
#
# Une version est déployée, et le dossier de données est vide ou n'est plus celui de cette version
# (un disque ou une racine mal montés) : un déploiement ou un retour arrière repartirait de zéro, et
# l'instantané suivant copierait du vide. deployer.sh le refuse, code 1 signalé, avant tout
# changement. Le dossier de référence est le chemin canonique que le dernier succès a écrit dans
# $ETAT/donnees ; sans ce fichier (un état d'avant la v0.5.0 du modèle, celui que pose en_service),
# celui du compose.env de la version déployée. `--donnees-neuves` lève la garde pour un déploiement
# voulu.

# vider_donnees <env> : le dossier de données reste, sans une seule entrée (fichiers cachés compris).
vider_donnees() {
  find "$VEILLE_EMPLOI_RACINE_DONNEES/$1/donnees" -mindepth 1 -delete
}

# figer_etat <env> : comme etat_fige, pour cet environnement, après avoir créé le verrou que prend
# tout déploiement, pour que `diff -r` ne voie que ce qu'un refus changerait.
figer_etat() {
  local etat="$VEILLE_EMPLOI_RACINE_ETAT/$1"
  : >"$etat/verrou"
  chmod -R u+rwX "$BATS_TEST_TMPDIR/etat-avant" 2>/dev/null || true
  rm -rf "$BATS_TEST_TMPDIR/etat-avant"
  cp -a "$etat" "$BATS_TEST_TMPDIR/etat-avant"
  : >"$APPELS"
}

# refus_sans_trace : ce qu'un refus de la garde garantit, après figer_etat : rien n'a changé dans
# l'état (deploye, donnees, compose.env, compose.env.precedent, pas d'echec), rien n'a été lancé,
# arrêté ni copié.
refus_sans_trace() {
  diff -r "$BATS_TEST_TMPDIR/etat-avant" "$ETAT"
  [ ! -e "$ETAT/echec" ]
  [ "$(nombre_de_lancements)" -eq 0 ]
  [ "$(appels_de docker | grep -cE ' (up|stop|down) ')" -eq 0 ]
  [ "$(appels_de docker | grep -c ' exec ')" -eq 0 ]
}

@test "un_deploiement_suivant_sur_un_dossier_vide_est_refuse" {
  deja_en_service "$ANCIENNE" 0.1.0
  local donnees="$VEILLE_EMPLOI_RACINE_DONNEES/prod/donnees"
  vider_donnees prod
  figer_etat prod
  deployer prod "$NOUVELLE" 0.2.0
  [ "$status" -eq 1 ]
  [[ "$output" == *"dossier de données vide : $donnees, alors qu'une version est déployée : déploiement de 0.2.0 refusé, rien n'a changé."* ]]
  [[ "$output" == *"--donnees-neuves"* ]]
  refus_sans_trace
  # le signal ne porte aucun chemin
  [ "$(signaux)" = "$(signal 'dossier de données vide avant 0.2.0, rien n'"'"'a changé (voir le journal)') $HC/fail" ]
}

# Sans version déployée, un dossier vide est normal : c'est le premier déploiement.
@test "un_premier_deploiement_sur_un_dossier_vide_passe" {
  deployer prod "$NOUVELLE" 0.2.0
  [ "$status" -eq 0 ]
  [ "$(cat "$ETAT/deploye")" = "$NOUVELLE 0.2.0 -" ]
}

# C'est aussi le cas d'un état d'avant la garde : son compose.env porte déjà le chemin des données.
@test "un_deploiement_suivant_sur_le_meme_dossier_plein_passe" {
  deja_en_service "$ANCIENNE" 0.1.0
  deployer prod "$NOUVELLE" 0.2.0
  [ "$status" -eq 0 ]
  [[ "$output" != *"dossier de données"* ]]
  [ "$(cat "$ETAT/deploye")" = "$NOUVELLE 0.2.0 -" ]
}

# Plein ne suffit pas : une autre racine, elle aussi pleine, n'est pas le dossier de la version
# déployée. Le journal cite le nouveau chemin et l'ancien.
@test "un_dossier_change_est_refuse_meme_plein" {
  deja_en_service "$ANCIENNE" 0.1.0
  local ancien="$VEILLE_EMPLOI_RACINE_DONNEES/prod/donnees" autre="$BATS_TEST_TMPDIR/autre"
  export VEILLE_EMPLOI_RACINE_DONNEES="$autre"
  poser_donnees prod
  figer_etat prod
  deployer prod "$NOUVELLE" 0.2.0
  [ "$status" -eq 1 ]
  [[ "$output" == *"dossier de données changé : $autre/prod/donnees au lieu de $ancien, celui de la version déployée : déploiement de 0.2.0 refusé, rien n'a changé."* ]]
  [[ "$output" == *"--donnees-neuves"* ]]
  refus_sans_trace
  [ "$(signaux)" = "$(signal 'dossier de données changé avant 0.2.0, rien n'"'"'a changé (voir le journal)') $HC/fail" ]
}

@test "un_ancien_chemin_disparu_compte_comme_change" {
  deja_en_service "$ANCIENNE" 0.1.0
  local ancien="$VEILLE_EMPLOI_RACINE_DONNEES/prod/donnees" autre="$BATS_TEST_TMPDIR/autre"
  rm -rf "$VEILLE_EMPLOI_RACINE_DONNEES"
  export VEILLE_EMPLOI_RACINE_DONNEES="$autre"
  poser_donnees prod
  figer_etat prod
  deployer prod "$NOUVELLE" 0.2.0
  [ "$status" -eq 1 ]
  [[ "$output" == *"dossier de données changé : $autre/prod/donnees au lieu de $ancien,"* ]]
  refus_sans_trace
  [ "$(signaux)" = "$(signal 'dossier de données changé avant 0.2.0, rien n'"'"'a changé (voir le journal)') $HC/fail" ]
}

@test "un_retour_sur_un_dossier_vide_est_refuse" {
  deux_versions
  vider_donnees prod
  figer_etat prod
  deployer prod --retour
  [ "$status" -eq 1 ]
  [[ "$output" == *"dossier de données vide : $VEILLE_EMPLOI_RACINE_DONNEES/prod/donnees, alors qu'une version est déployée : retour à 0.1.0 refusé, rien n'a changé."* ]]
  # la version quittée n'est même pas marquée en échec
  refus_sans_trace
  [ "$(signaux)" = "$(signal 'dossier de données vide avant le retour à 0.1.0, rien n'"'"'a changé (voir le journal)') $HC/fail" ]
}

# --donnees-neuves : le déploiement voulu sur des données neuves. L'instantané est pris sur l'ancien
# conteneur, avec ses propres données, comme à l'ordinaire.
@test "donnees_neuves_passe_sur_un_dossier_vide" {
  deja_en_service "$ANCIENNE" 0.1.0
  local donnees="$VEILLE_EMPLOI_RACINE_DONNEES/prod/donnees"
  vider_donnees prod
  deployer prod "$NOUVELLE" 0.2.0 --donnees-neuves
  [ "$status" -eq 0 ]
  [[ "$output" == *"données neuves voulues : $donnees (contrôles du dossier de données levés pour ce déploiement)"* ]]
  [ "$(cat "$ETAT/deploye")" = "$NOUVELLE 0.2.0 -" ]
  [ "$(cat "$ETAT/compose.env")" = "$(contenu_compose_env prod "$NOUVELLE" 0.2.0)" ]
  [ "$(appels_de docker | grep -c ' exec -T app ')" -eq 1 ]
}

@test "donnees_neuves_passe_sur_un_dossier_change" {
  deja_en_service "$ANCIENNE" 0.1.0
  local autre="$BATS_TEST_TMPDIR/autre"
  export VEILLE_EMPLOI_RACINE_DONNEES="$autre"
  poser_donnees prod
  deployer prod "$NOUVELLE" 0.2.0 --donnees-neuves
  [ "$status" -eq 0 ]
  [[ "$output" == *"données neuves voulues : $autre/prod/donnees (contrôles du dossier de données levés pour ce déploiement)"* ]]
  [ "$(cat "$ETAT/deploye")" = "$NOUVELLE 0.2.0 -" ]
  # le succès enregistre le nouveau chemin : le déploiement suivant le prend pour référence
  grep -Fx "VEILLE_EMPLOI_DONNEES=$autre/prod/donnees" "$ETAT/compose.env"
  [ "$(cat "$ETAT/donnees")" = "$(realpath "$autre/prod/donnees")" ]
  [ "$(appels_de docker | grep -c ' exec -T app ')" -eq 1 ]
}

# L'option n'est pas un moyen de contourner la garde d'un retour : c'est une erreur d'usage.
@test "donnees_neuves_avec_retour_rend_64" {
  deux_versions
  vider_donnees prod
  figer_etat prod
  deployer prod --retour --donnees-neuves
  [ "$status" -eq 64 ]
  [[ "$output" == *"usage :"* ]]
  diff -r "$BATS_TEST_TMPDIR/etat-avant" "$ETAT"
  [ ! -s "$APPELS" ]
}

# Ce qui compte comme vide, comme le même dossier, et ce qu'on compare.

@test "un_fichier_cache_suffit" {
  deja_en_service "$ANCIENNE" 0.1.0
  vider_donnees prod
  : >"$VEILLE_EMPLOI_RACINE_DONNEES/prod/donnees/.cache"
  deployer prod "$NOUVELLE" 0.2.0
  [ "$status" -eq 0 ]
  [ "$(cat "$ETAT/deploye")" = "$NOUVELLE 0.2.0 -" ]
}

# Un lien symbolique vers la même racine donne une autre chaîne que celle de compose.env, mais le
# même dossier : le déploiement passe. Un lien vers une autre racine, pleine, est un autre dossier.
@test "un_lien_vers_le_meme_dossier_passe_un_lien_ailleurs_non" {
  deja_en_service "$ANCIENNE" 0.1.0
  local racine="$VEILLE_EMPLOI_RACINE_DONNEES" ailleurs="$BATS_TEST_TMPDIR/ailleurs"
  mkdir -p "$ailleurs"
  ln -s "$racine" "$BATS_TEST_TMPDIR/lien-ici"
  ln -s "$ailleurs" "$BATS_TEST_TMPDIR/lien-ailleurs"
  # ailleurs : refus
  export VEILLE_EMPLOI_RACINE_DONNEES="$BATS_TEST_TMPDIR/lien-ailleurs"
  poser_donnees prod
  figer_etat prod
  deployer prod "$NOUVELLE" 0.2.0
  [ "$status" -eq 1 ]
  [[ "$output" == *"dossier de données changé : $BATS_TEST_TMPDIR/lien-ailleurs/prod/donnees au lieu de $racine/prod/donnees,"* ]]
  refus_sans_trace
  # le même dossier sous un autre nom : passe
  export VEILLE_EMPLOI_RACINE_DONNEES="$BATS_TEST_TMPDIR/lien-ici"
  deployer prod "$NOUVELLE" 0.2.0
  [ "$status" -eq 0 ]
  [[ "$output" != *"dossier de données"* ]]
  [ "$(cat "$ETAT/deploye")" = "$NOUVELLE 0.2.0 -" ]
}

# Sans $ETAT/donnees, le compose.env ne sert de référence que s'il existe et décrit la version
# déployée (un déploiement interrompu ne l'a pas laissé tel quel). Sans référence, seul le vide est
# contrôlé, et le journal le dit : un autre dossier, plein, passe ; un dossier vide, non.
@test "sans_reference_seul_le_vide_est_controle" {
  local cas autre="$BATS_TEST_TMPDIR/autre" racine="$VEILLE_EMPLOI_RACINE_DONNEES" suivante
  suivante="ghcr.io/edouardzemb/veille-emploi@sha256:$(printf '3%.0s' {1..64})"
  for cas in absent autre-version; do
    rm -rf "$ETAT" "$racine" "$autre"
    export VEILLE_EMPLOI_RACINE_DONNEES="$racine"
    deja_en_service "$ANCIENNE" 0.1.0
    if [ "$cas" = absent ]; then
      rm "$ETAT/compose.env"
    else
      contenu_compose_env prod "$suivante" 0.3.0 >"$ETAT/compose.env"
    fi
    # vide : refus, quoi qu'il en soit de la référence
    vider_donnees prod
    deployer prod "$NOUVELLE" 0.2.0
    [ "$status" -eq 1 ]
    [[ "$output" == *"dossier de données vide : $racine/prod/donnees,"* ]]
    [ "$(cat "$ETAT/deploye")" = "$ANCIENNE 0.1.0" ]
    # un autre dossier, plein : passe, et le journal dit qu'il n'est pas comparé
    export VEILLE_EMPLOI_RACINE_DONNEES="$autre"
    poser_donnees prod
    deployer prod "$NOUVELLE" 0.2.0
    [ "$status" -eq 0 ]
    [[ "$output" == *"ni l'état ni compose.env ne disent le dossier de la version déployée : le chemin des données n'est pas comparé, seul le vide est contrôlé"* ]]
    [ "$(cat "$ETAT/deploye")" = "$NOUVELLE 0.2.0 -" ]
  done
}

# La sonde rend le code du déploiement. Le refus n'écrit pas `echec` : elle réessaie au passage
# suivant, et déploie dès que le dossier est rétabli. L'installation des unités systemd, que la sonde
# de prod lance avant de déployer, n'est pas ce que ce test examine : un double qui réussit.
@test "la_sonde_rend_le_refus_de_la_garde_et_reessaie" {
  deja_en_service "$ANCIENNE" 0.1.0
  printf '#!/usr/bin/env bash
exit 0
' >"$CLONE/deploiement/installer-unites.sh"
  vider_donnees prod
  passage_de_la_sonde
  [ "$status" -eq 1 ]
  [[ "$output" == *"dossier de données vide :"* ]]
  [ ! -e "$ETAT/echec" ]
  [ "$(cat "$ETAT/deploye")" = "$ANCIENNE 0.1.0" ]
  [ "$(nombre_de_lancements)" -eq 0 ]
  [ "$(signaux)" = "$(signal 'dossier de données vide avant 0.2.0, rien n'"'"'a changé (voir le journal)') $HC/fail" ]
  # le dossier est rétabli : le passage suivant déploie
  poser_donnees prod
  passage_de_la_sonde
  [ "$status" -eq 0 ]
  [ "$(cat "$ETAT/deploye")" = "$NOUVELLE 0.2.0 -" ]
}

@test "la_garde_vaut_aussi_en_staging" {
  preparer_secrets_de_test staging JETON=jeton-staging-7 HC_SONDE=https://hc.example/ping/sonde-staging
  en_service staging "$ANCIENNE" main
  local etat="$VEILLE_EMPLOI_RACINE_ETAT/staging"
  mkdir -p "$VEILLE_EMPLOI_RACINE_DONNEES/staging/donnees"
  figer_etat staging
  deployer staging "$NOUVELLE" main
  [ "$status" -eq 1 ]
  [[ "$output" == *"dossier de données vide : $VEILLE_EMPLOI_RACINE_DONNEES/staging/donnees,"* ]]
  diff -r "$BATS_TEST_TMPDIR/etat-avant" "$etat"
  [ "$(nombre_de_lancements)" -eq 0 ]
  [ "$(signaux)" = "$(signal 'dossier de données vide avant main, rien n'"'"'a changé (voir le journal)') https://hc.example/ping/sonde-staging/fail" ]
}

# Une autre racine, que charger_env vient de créer vide : le refus dit « changé », pas « vide », et
# le journal donne les deux chemins. C'est le cas premier de l'issue modele-projet#49, une racine
# mal réglée.
@test "une_autre_racine_vide_est_dite_changee" {
  local racine="$VEILLE_EMPLOI_RACINE_DONNEES" autre="$BATS_TEST_TMPDIR/autre" ancien
  deployer prod "$ANCIENNE" 0.1.0
  [ "$status" -eq 0 ]
  poser_donnees prod
  ancien="$(realpath "$racine/prod/donnees")"
  export VEILLE_EMPLOI_RACINE_DONNEES="$autre"
  figer_etat prod
  deployer prod "$NOUVELLE" 0.2.0
  [ "$status" -eq 1 ]
  [[ "$output" == *"dossier de données changé : $autre/prod/donnees au lieu de $ancien, celui de la version déployée : déploiement de 0.2.0 refusé, rien n'a changé."* ]]
  [[ "$output" != *"dossier de données vide"* ]]
  # le dossier du jour existe bien, vide
  [ -d "$autre/prod/donnees" ]
  [ -z "$(ls -A "$autre/prod/donnees")" ]
  refus_sans_trace
  [ "$(signaux)" = "$(signal 'dossier de données changé avant 0.2.0, rien n'"'"'a changé (voir le journal)') $HC/fail" ]
}

# L'option est journalisée même au premier déploiement, où il n'y a rien à contrôler.
@test "donnees_neuves_au_premier_deploiement_est_journalisee" {
  deployer prod "$NOUVELLE" 0.2.0 --donnees-neuves
  [ "$status" -eq 0 ]
  [[ "$output" == *"données neuves voulues : $VEILLE_EMPLOI_RACINE_DONNEES/prod/donnees (contrôles du dossier de données levés pour ce déploiement)"* ]]
  [ "$(cat "$ETAT/deploye")" = "$NOUVELLE 0.2.0 -" ]
}

# --- la référence : le chemin canonique du dernier succès ------------------------------------
#
# Chaque succès, déploiement comme retour arrière, écrit dans $ETAT/donnees le chemin canonique
# (`realpath`) du dossier de données. Le déploiement suivant compare le chemin canonique du jour à
# cette chaîne, sans la résoudre de nouveau : un lien repointé sur place est vu. Ces tests partent
# d'un vrai déploiement, qui écrit le fichier.

# lier_donnees <env> <cible> : le dossier de données de cet environnement devient un lien
# symbolique vers <cible>, un dossier qui existe (un autre disque, par exemple).
lier_donnees() {
  local dossier="$VEILLE_EMPLOI_RACINE_DONNEES/$1/donnees"
  mkdir -p "$(dirname "$dossier")"
  rm -rf "$dossier"
  ln -s "$2" "$dossier"
}

# La racine des données passe par un lien : c'est le chemin réel qui est enregistré, pas celui du
# lien. Le retour arrière réussi l'écrit aussi : retiré juste avant, le fichier revient.
@test "le_succes_enregistre_le_chemin_canonique" {
  local vraie="$BATS_TEST_TMPDIR/vraie-racine" canonique
  horloge_qui_avance
  mkdir -p "$vraie"
  ln -s "$vraie" "$BATS_TEST_TMPDIR/racine-en-lien"
  export VEILLE_EMPLOI_RACINE_DONNEES="$BATS_TEST_TMPDIR/racine-en-lien"
  canonique="$(realpath "$vraie")/prod/donnees"
  deployer prod "$ANCIENNE" 0.1.0
  [ "$status" -eq 0 ]
  [ "$(cat "$ETAT/donnees")" = "$canonique" ]
  poser_donnees prod
  deployer prod "$NOUVELLE" 0.2.0
  [ "$status" -eq 0 ]
  [ "$(cat "$ETAT/donnees")" = "$canonique" ]
  rm "$ETAT/donnees"
  deployer prod --retour
  [ "$status" -eq 0 ]
  [ "$(cat "$ETAT/deploye")" = "$ANCIENNE 0.1.0 -" ]
  [ "$(cat "$ETAT/donnees")" = "$canonique" ]
}

# Un dossier de données qui est lui-même un lien vers un dossier plein n'est pas vide : Docker suit
# le lien au montage, la garde aussi.
@test "un_dossier_de_donnees_en_lien_vers_un_dossier_plein_passe" {
  local disque="$BATS_TEST_TMPDIR/disque/donnees"
  mkdir -p "$disque"
  echo "données de test" >"$disque/base"
  lier_donnees prod "$disque"
  deployer prod "$ANCIENNE" 0.1.0
  [ "$status" -eq 0 ]
  deployer prod "$NOUVELLE" 0.2.0
  [ "$status" -eq 0 ]
  [[ "$output" != *"dossier de données"* ]]
  [ "$(cat "$ETAT/deploye")" = "$NOUVELLE 0.2.0 -" ]
}

# Le même lien, vers un dossier vidé : le vide se voit à travers le lien.
@test "un_dossier_de_donnees_en_lien_vers_un_dossier_vide_est_refuse" {
  local disque="$BATS_TEST_TMPDIR/disque/donnees" donnees="$VEILLE_EMPLOI_RACINE_DONNEES/prod/donnees"
  mkdir -p "$disque"
  echo "données de test" >"$disque/base"
  lier_donnees prod "$disque"
  deployer prod "$ANCIENNE" 0.1.0
  [ "$status" -eq 0 ]
  find "$disque" -mindepth 1 -delete
  figer_etat prod
  deployer prod "$NOUVELLE" 0.2.0
  [ "$status" -eq 1 ]
  [[ "$output" == *"dossier de données vide : $donnees, alors qu'une version est déployée : déploiement de 0.2.0 refusé, rien n'a changé."* ]]
  refus_sans_trace
  [ "$(signaux)" = "$(signal 'dossier de données vide avant 0.2.0, rien n'"'"'a changé (voir le journal)') $HC/fail" ]
}

# Le lien est repointé sur place, vers un autre dossier plein : la chaîne de compose.env n'a pas
# changé, le dossier si. Le journal donne le chemin du jour et le chemin réel enregistré, celui de A.
@test "un_lien_repointe_sur_place_est_refuse" {
  local a="$BATS_TEST_TMPDIR/disque-a" b="$BATS_TEST_TMPDIR/disque-b"
  local donnees="$VEILLE_EMPLOI_RACINE_DONNEES/prod/donnees"
  mkdir -p "$a" "$b"
  echo "données de A" >"$a/base"
  echo "données de B" >"$b/base"
  lier_donnees prod "$a"
  deployer prod "$ANCIENNE" 0.1.0
  [ "$status" -eq 0 ]
  lier_donnees prod "$b"
  figer_etat prod
  deployer prod "$NOUVELLE" 0.2.0
  [ "$status" -eq 1 ]
  [[ "$output" == *"dossier de données changé : $donnees au lieu de $(realpath "$a"), celui de la version déployée : déploiement de 0.2.0 refusé, rien n'a changé."* ]]
  refus_sans_trace
  [ "$(signaux)" = "$(signal 'dossier de données changé avant 0.2.0, rien n'"'"'a changé (voir le journal)') $HC/fail" ]
}

# Le cas que la garde prend pour pire que le vide : le dossier du staging devient un lien vers celui
# de la prod, plein.
@test "un_staging_lie_au_dossier_de_la_prod_est_refuse" {
  local racine="$VEILLE_EMPLOI_RACINE_DONNEES" suivante ancien
  suivante="ghcr.io/edouardzemb/veille-emploi@sha256:$(printf '3%.0s' {1..64})"
  preparer_secrets_de_test staging JETON=jeton-staging-7 HC_SONDE=https://hc.example/ping/sonde-staging
  ETAT="$VEILLE_EMPLOI_RACINE_ETAT/staging"
  deployer staging "$NOUVELLE" main
  [ "$status" -eq 0 ]
  ancien="$(realpath "$racine/staging/donnees")"
  poser_donnees prod
  lier_donnees staging "$racine/prod/donnees"
  figer_etat staging
  deployer staging "$suivante" main
  [ "$status" -eq 1 ]
  [[ "$output" == *"dossier de données changé : $racine/staging/donnees au lieu de $ancien, celui de la version déployée : déploiement de main refusé, rien n'a changé."* ]]
  refus_sans_trace
  [ "$(signaux)" = "$(signal 'dossier de données changé avant main, rien n'"'"'a changé (voir le journal)') https://hc.example/ping/sonde-staging/fail" ]
}

# $ETAT/donnees et compose.env disent deux dossiers, pleins tous les deux : le chemin du dernier
# succès fait foi, compose.env n'est que le repli d'un état d'avant la v0.5.0 du modèle.
@test "l_etat_prime_sur_compose_env" {
  deja_en_service "$ANCIENNE" 0.1.0
  local racine="$VEILLE_EMPLOI_RACINE_DONNEES" autre="$BATS_TEST_TMPDIR/autre" enregistre
  export VEILLE_EMPLOI_RACINE_DONNEES="$autre"
  poser_donnees prod
  enregistre="$(realpath "$autre/prod/donnees")"
  echo "$enregistre" >"$ETAT/donnees"
  # le dossier de compose.env : refus
  export VEILLE_EMPLOI_RACINE_DONNEES="$racine"
  figer_etat prod
  deployer prod "$NOUVELLE" 0.2.0
  [ "$status" -eq 1 ]
  [[ "$output" == *"dossier de données changé : $racine/prod/donnees au lieu de $enregistre,"* ]]
  refus_sans_trace
  # celui de $ETAT/donnees : passe
  export VEILLE_EMPLOI_RACINE_DONNEES="$autre"
  deployer prod "$NOUVELLE" 0.2.0
  [ "$status" -eq 0 ]
  [[ "$output" != *"dossier de données"* ]]
  [ "$(cat "$ETAT/deploye")" = "$NOUVELLE 0.2.0 -" ]
}

# Un --donnees-neuves en échec : la version d'avant revient, sur le nouveau dossier (la valeur
# exportée par charger_env l'emporte sur compose.env), mais l'échec n'écrit pas $ETAT/donnees. Le
# déploiement suivant refuse donc « changé » (exploitation.md, « Un geste qui échoue »).
@test "donnees_neuves_en_echec_garde_le_chemin_d_avant" {
  local autre="$BATS_TEST_TMPDIR/autre" ancien suivante
  suivante="ghcr.io/edouardzemb/veille-emploi@sha256:$(printf '3%.0s' {1..64})"
  deployer prod "$ANCIENNE" 0.1.0
  [ "$status" -eq 0 ]
  poser_donnees prod
  ancien="$(cat "$ETAT/donnees")"
  export VEILLE_EMPLOI_RACINE_DONNEES="$autre"
  poser_donnees prod
  export DOUBLE_CURL_SANTE_KO="$NOUVELLE"
  deployer prod "$NOUVELLE" 0.2.0 --donnees-neuves
  [ "$status" -eq 1 ]
  [ "$(cat "$ETAT/deploye")" = "$ANCIENNE 0.1.0 -" ]
  [ "$(cat "$ETAT/donnees")" = "$ancien" ]
  grep -Fx "VEILLE_EMPLOI_IMAGE=$ANCIENNE" "$EN_SERVICE"
  grep -Fx "VEILLE_EMPLOI_DONNEES=$autre/prod/donnees" "$EN_SERVICE"
  unset DOUBLE_CURL_SANTE_KO
  deployer prod "$suivante" 0.3.0
  [ "$status" -eq 1 ]
  [[ "$output" == *"dossier de données changé : $autre/prod/donnees au lieu de $ancien,"* ]]
}

# --- le couple : l'image et le commit de données (M-0004 et M-0006 § 5, amendés) --------------
#
# Un projet qui déclare VERIFIER_CONFIG ou VERIFIER_CONTENU déploie un couple : une image et un
# commit du clone des données, que donne --commit-donnees. Avant tout changement : la règle des
# paires, l'instantané du commit, et les commandes déclarées dans un conteneur jetable de l'image
# visée. Après le `up` : les montages du conteneur, et le champ configuration de la santé. deploye
# et precedent retiennent « <image> <version> <commit> », echec « <image> <commit> » ; le commit
# vaut « - » sans données montées.

JETABLES="--user 1000:1000 --read-only --tmpfs /tmp --cap-drop ALL --security-opt no-new-privileges:true --memory 384m"
FORMAT_MONTAGES='{{json .Mounts}}'

# avec_donnees <commande…> : deploiement/projet.env déclare aussi ces commandes de l'instance
# (VERIFIER_CONFIG=outil verifier_config…), et l'application suit le contrat de /config (M-0003,
# amendé) : sa santé dit configuration, montee si /config est monté, exemple sinon.
avec_donnees() {
  local commande
  for commande in "$@"; do
    printf '%s=outil %s\n' "$commande" "${commande,,}" >>"$CLONE/deploiement/projet.env"
  done
  export DOUBLE_CURL_CONFIGURATION=auto
}

# instantane_de <env> <commit> : l'instantané des données de ce commit, sous l'état de l'environnement.
instantane_de() {
  printf '%s/%s/instantanes/%s\n' "$VEILLE_EMPLOI_RACINE_ETAT" "$1" "$2"
}

# verifications : les vérifications de l'instance, les conteneurs jetables sans réseau, dans l'ordre.
verifications() {
  appels_de docker | grep -F ' run --rm --network none ' || true
}

# verification <config|contenu> <image> <instantané> [<instantané en service>] : l'appel de docker
# qui vérifie ce dossier de l'instantané dans un conteneur jetable de l'image (lib.sh), avec, pour le
# contenu, celui de l'instantané en service sur /en-service.
verification() {
  local montages="-v $3/$1:/$1:ro" arguments="/$1"
  if [ -n "${4:-}" ]; then
    montages="$montages -v $4/contenu:/en-service:ro"
    arguments="$arguments /en-service"
  fi
  printf 'docker run --rm --network none %s %s %s outil verifier_%s %s\n' "$JETABLES" "$montages" \
    "$2" "$1" "$arguments"
}

# montage_de <point> : ce que le conteneur de l'application en service monte sur ce point, que le
# double de docker note dans en-service.env : « false <source> » en lecture seule, vide sans montage.
montage_de() {
  sed -n "s|^MONTAGE=$1 ||p" "$EN_SERVICE"
}

# rien_n_a_change <signal> : après etat_fige, ce que garantit une vérification du couple qui n'a pas
# abouti : l'état n'a pas changé (instantanés des données mis à part), rien n'a été lancé, arrêté ni
# copié, l'application en service est la même, et le signal /fail le dit.
rien_n_a_change() {
  diff -r -x instantanes "$BATS_TEST_TMPDIR/etat-avant" "$ETAT"
  [ "$(nombre_de_lancements)" -eq 0 ]
  [ "$(appels_de docker | grep -cE ' (up|stop|down|exec) ')" -eq 0 ]
  grep -Fx "VEILLE_EMPLOI_IMAGE=$NOUVELLE" "$EN_SERVICE"
  [ "$(signaux)" = "$(signal "$1") $HC/fail" ]
}

@test "deployer : un couple se vérifie avant tout changement" {
  local premier service vise code
  horloge_qui_avance
  avec_donnees VERIFIER_CONFIG VERIFIER_CONTENU
  commit_de_donnees "$SOUS_CONFIG/profil.yml" "$SOUS_CONTENU/page.md"
  premier="$COMMIT"
  service="$(instantane_de prod "$premier")"
  deployer prod "$ANCIENNE" 0.1.0 --commit-donnees "$premier"
  [ "$status" -eq 0 ]
  # sans couple en service, VERIFIER_CONTENU ne reçoit pas /en-service
  [ "$(verifications)" = "$(verification config "$ANCIENNE" "$service")
$(verification contenu "$ANCIENNE" "$service")" ]
  poser_donnees prod
  commit_de_donnees "$SOUS_CONFIG/profil.yml" "$SOUS_CONTENU/page.md" "$SOUS_CONTENU/autre.md"
  vise="$(instantane_de prod "$COMMIT")"
  : >"$APPELS"
  deployer prod "$NOUVELLE" 0.2.0 --commit-donnees "$COMMIT"
  [ "$status" -eq 0 ]
  # l'image visée, sur l'instantané visé ; le contenu, avec celui du couple en service
  [ "$(verifications)" = "$(verification config "$NOUVELLE" "$vise")
$(verification contenu "$NOUVELLE" "$vise" "$service")" ]
  # avant tout changement : l'instantané de /donnees, puis le lancement
  [ "$(ligne_de ' --network none ')" -lt "$(ligne_de ' exec -T app ')" ]
  [ "$(ligne_de ' --network none ')" -lt "$(ligne_de ' up -d ')" ]
  # compose.env monte l'instantané que nomme le commit, et dc ajoute les deux fichiers de montage
  [ "$(cat "$vise/contenu/autre.md")" = "fichier d'exemple $SOUS_CONTENU/autre.md" ]
  grep -Fx "VEILLE_EMPLOI_CONFIG=$vise/config" "$ETAT/compose.env"
  grep -Fx "VEILLE_EMPLOI_CONTENU=$vise/contenu" "$ETAT/compose.env"
  appels_de docker | grep -Fx "$(dc_de prod config contenu) up -d --wait --wait-timeout 120 --remove-orphans"
  # le couple retenu, l'ancien dans precedent
  [ "$(cat "$ETAT/deploye")" = "$NOUVELLE 0.2.0 $COMMIT" ]
  [ "$(cat "$ETAT/precedent")" = "$ANCIENNE 0.1.0 $premier" ]
  [ ! -e "$ETAT/echec" ]
  [ "$(signaux)" = "$(signal "déployé 0.2.0, données ${COMMIT:0:12}") $HC" ]

  # Un commit hors de la règle des paires (VERIFIER_CONTENU sans contenu) : rien n'est lancé, rien
  # n'a changé, et rien n'est marqué en échec : la sonde réessaiera.
  commit_de_donnees "$SOUS_CONFIG/profil.yml"
  etat_fige
  deployer prod "$SUIVANTE" 0.3.0 --commit-donnees "$COMMIT"
  [ "$status" -eq 1 ]
  [[ "$output" == *"VERIFIER_CONTENU sans $SOUS_CONTENU (commit de données $COMMIT)"* ]]
  [ -z "$(verifications)" ]
  rien_n_a_change "données hors de la règle des paires avant 0.3.0, rien n'a changé (voir le journal)"
  # Une vérification qui n'a pas eu lieu (l'image ne connaît pas la commande, ou une autre erreur) :
  # de même.
  commit_de_donnees "$SOUS_CONFIG/profil.yml" "$SOUS_CONTENU/page.md"
  for code in 64 1; do
    export DOUBLE_DOCKER_VERIFIER_INSTANCE_CODE="$code"
    etat_fige
    deployer prod "$SUIVANTE" 0.3.0 --commit-donnees "$COMMIT"
    [ "$status" -eq 1 ]
    [[ "$output" == *"vérification impossible (VERIFIER_CONFIG : code $code)"* ]]
    rien_n_a_change "vérification des données impossible avant 0.3.0, rien n'a changé (voir le journal)"
  done
}

@test "deployer : un refus de VERIFIER_CONFIG marque le couple en échec" {
  local premier
  horloge_qui_avance
  avec_donnees VERIFIER_CONFIG
  commit_de_donnees "$SOUS_CONFIG/profil.yml"
  premier="$COMMIT"
  deployer prod "$ANCIENNE" 0.1.0 --commit-donnees "$premier"
  [ "$status" -eq 0 ]
  poser_donnees prod
  commit_de_donnees "$SOUS_CONFIG/profil.yml" "$SOUS_CONFIG/regles.yml"
  # L'image visée dit les données non conformes : le couple est marqué en échec, rien d'autre ne
  # change, et le conteneur en service n'est pas touché.
  export DOUBLE_DOCKER_VERIFIER_REFUSE="$NOUVELLE"
  etat_fige
  deployer prod "$NOUVELLE" 0.2.0 --commit-donnees "$COMMIT"
  [ "$status" -eq 1 ]
  [[ "$output" == *"configuration non conforme (VERIFIER_CONFIG : code 2)"* ]]
  [ "$(cat "$ETAT/echec")" = "$NOUVELLE $COMMIT" ]
  diff -r -x instantanes -x echec "$BATS_TEST_TMPDIR/etat-avant" "$ETAT"
  [ "$(nombre_de_lancements)" -eq 0 ]
  [ "$(appels_de docker | grep -cE ' (up|stop|down|exec) ')" -eq 0 ]
  grep -Fx "VEILLE_EMPLOI_IMAGE=$ANCIENNE" "$EN_SERVICE"
  [ "$(signaux)" = "$(signal 'données non conformes avant 0.2.0, couple marqué en échec (voir le journal)') $HC/fail" ]
  # Le même commit avec une autre image est un autre couple : il se tente, et passe.
  : >"$APPELS"
  deployer prod "$SUIVANTE" 0.3.0 --commit-donnees "$COMMIT"
  [ "$status" -eq 0 ]
  [ "$(cat "$ETAT/deploye")" = "$SUIVANTE 0.3.0 $COMMIT" ]
  [ "$(cat "$ETAT/precedent")" = "$ANCIENNE 0.1.0 $premier" ]
  [ ! -e "$ETAT/echec" ]
  # Un retour vers un couple que son image dit non conforme : refusé de même, ce couple marqué.
  export DOUBLE_DOCKER_VERIFIER_REFUSE="$ANCIENNE"
  etat_fige
  deployer prod --retour
  [ "$status" -eq 1 ]
  [ "$(cat "$ETAT/echec")" = "$ANCIENNE $premier" ]
  diff -r -x instantanes -x echec "$BATS_TEST_TMPDIR/etat-avant" "$ETAT"
  [ "$(nombre_de_lancements)" -eq 0 ]
  grep -Fx "VEILLE_EMPLOI_IMAGE=$SUIVANTE" "$EN_SERVICE"
  [ "$(signaux)" = "$(signal 'données non conformes avant le retour à 0.1.0, couple marqué en échec (voir le journal)') $HC/fail" ]
}

@test "deployer : un commit de données seul redéploie la même image" {
  local premier service vise
  horloge_qui_avance
  avec_donnees VERIFIER_CONTENU
  commit_de_donnees "$SOUS_CONTENU/page.md"
  premier="$COMMIT"
  service="$(instantane_de prod "$premier")"
  deployer prod "$NOUVELLE" 0.2.0 --commit-donnees "$premier"
  [ "$status" -eq 0 ]
  poser_donnees prod
  commit_de_donnees "$SOUS_CONTENU/page.md" "$SOUS_CONTENU/autre.md"
  vise="$(instantane_de prod "$COMMIT")"
  : >"$APPELS"
  deployer prod "$NOUVELLE" 0.2.0 --commit-donnees "$COMMIT"
  [ "$status" -eq 0 ]
  # le parcours d'une image nouvelle : vérification, instantané de /donnees, lancement, montages
  [ "$(verifications)" = "$(verification contenu "$NOUVELLE" "$vise" "$service")" ]
  [ "$(appels_de docker | grep -c ' exec -T app ')" -eq 1 ]
  [ "$(nombre_de_lancements)" -eq 1 ]
  appels_de docker | grep -Fx "docker container inspect --format $FORMAT_MONTAGES c0ffee"
  # le conteneur monte le nouvel instantané ; /config, que le projet ne déclare pas, ne l'est pas
  [ "$(montage_de /contenu)" = "false $vise/contenu" ]
  [ -z "$(montage_de /config)" ]
  aucune_ligne '^VEILLE_EMPLOI_CONFIG=' "$ETAT/compose.env"
  [ "$(cat "$ETAT/deploye")" = "$NOUVELLE 0.2.0 $COMMIT" ]
  [ "$(cat "$ETAT/precedent")" = "$NOUVELLE 0.2.0 $premier" ]
  grep -Fx "VEILLE_EMPLOI_CONTENU=$service/contenu" "$ETAT/compose.env.precedent"
  [ "$(signaux)" = "$(signal "déployé 0.2.0, données ${COMMIT:0:12}") $HC" ]
  # Le même retour arrière qu'une image nouvelle. Un déploiement interrompu a laissé un compose.env
  # de la même image et d'un autre commit : il ne décrit pas le couple déployé, et ne devient pas la
  # cible du retour, qui reste celle d'avant.
  sed -i "s|^VEILLE_EMPLOI_CONTENU=.*|VEILLE_EMPLOI_CONTENU=$(instantane_de prod "$(printf 'e%.0s' {1..40})")/contenu|" \
    "$ETAT/compose.env"
  commit_de_donnees "$SOUS_CONTENU/page.md" "$SOUS_CONTENU/quatre.md"
  # seul le `up` de l'aller garde ses montages ; celui du retour remonte le précédent
  export DOUBLE_DOCKER_MONTAGES_GARDES_AU_UP=1
  : >"$APPELS"
  deployer prod "$NOUVELLE" 0.2.0 --commit-donnees "$COMMIT"
  [ "$status" -eq 1 ]
  [[ "$output" == *"compose.env ne décrit pas le couple déployé (déploiement interrompu ?)"* ]]
  [ "$(cat "$ETAT/echec")" = "$NOUVELLE $COMMIT" ]
  grep -Fx "VEILLE_EMPLOI_CONTENU=$service/contenu" "$ETAT/compose.env"
  [ "$(signaux)" = "$(signal 'échec 0.2.0, retour à 0.2.0') $HC/fail" ]
}

@test "deployer : le montage visé se vérifie après le up" {
  local premier service vise cas raison retour
  horloge_qui_avance
  avec_donnees VERIFIER_CONFIG VERIFIER_CONTENU
  commit_de_donnees "$SOUS_CONFIG/profil.yml" "$SOUS_CONTENU/page.md"
  premier="$COMMIT"
  service="$(instantane_de prod "$premier")"
  deployer prod "$NOUVELLE" 0.2.0 --commit-donnees "$premier"
  [ "$status" -eq 0 ]
  # après le `up`, les montages du conteneur de l'application : chaque instantané visé, en lecture
  # seule, sur son point de montage ; et, en prod, une santé qui dit montee
  [ "$(ligne_de ' up -d ')" -lt "$(ligne_de " container inspect --format $FORMAT_MONTAGES c0ffee")" ]
  [ "$(montage_de /config)" = "false $service/config" ]
  [ "$(montage_de /contenu)" = "false $service/contenu" ]
  poser_donnees prod
  commit_de_donnees "$SOUS_CONFIG/profil.yml" "$SOUS_CONTENU/autre.md"
  vise="$(instantane_de prod "$COMMIT")"
  # Un conteneur que compose n'a pas recréé (il monte encore l'ancien instantané), un montage en
  # écriture, des montages illisibles, ou une santé qui ne dit pas montee : échec, et retour au
  # couple précédent, comme pour toute santé non conforme. Le pilote vaut aussi pour le `up` du
  # retour, qui se contrôle de même : sauf le conteneur gardé, qui monte encore le couple précédent,
  # le retour est en échec.
  for cas in DOUBLE_DOCKER_MONTAGES_GARDES=1 DOUBLE_DOCKER_MONTAGES_EN_ECRITURE=1 \
    DOUBLE_DOCKER_CONTAINER_INSPECT_ECHEC=1 DOUBLE_CURL_CONFIGURATION=exemple; do
    rm -f "$ETAT/echec"
    : >"$APPELS"
    export "${cas?}"
    deployer prod "$NOUVELLE" 0.2.0 --commit-donnees "$COMMIT"
    [ "$status" -eq 1 ]
    raison="montage des données non conforme"
    [ "$cas" != DOUBLE_CURL_CONFIGURATION=exemple ] || raison="santé non conforme"
    retour="retour à 0.2.0 en échec"
    [ "$cas" != DOUBLE_DOCKER_MONTAGES_GARDES=1 ] || retour="retour à 0.2.0"
    [[ "$output" == *"échec du déploiement de 0.2.0 ($raison)"* ]]
    [ "$cas" != DOUBLE_DOCKER_MONTAGES_GARDES=1 ] \
      || [[ "$output" == *"/config : attendu $vise/config en lecture seule, monté : false $service/config"* ]]
    [ "$(cat "$ETAT/echec")" = "$NOUVELLE $COMMIT" ]
    [ "$(cat "$ETAT/deploye")" = "$NOUVELLE 0.2.0 $premier" ]
    grep -Fx "VEILLE_EMPLOI_CONFIG=$service/config" "$ETAT/compose.env"
    [[ "$(montage_de /config)" == *" $service/config" ]]
    [ "$(signaux)" = "$(signal "échec 0.2.0, $retour") $HC/fail" ]
    unset "${cas%%=*}"
    export DOUBLE_CURL_CONFIGURATION=auto
  done
}

@test "deployer : --retour revient au couple entier" {
  local premier deuxieme troisieme vise service
  horloge_qui_avance
  # Un couple sans données, d'avant la déclaration des commandes, puis un couple avec données.
  deployer prod "$ANCIENNE" 0.1.0
  [ "$status" -eq 0 ]
  poser_donnees prod
  avec_donnees VERIFIER_CONFIG VERIFIER_CONTENU
  commit_de_donnees "$SOUS_CONFIG/profil.yml" "$SOUS_CONTENU/page.md"
  premier="$COMMIT"
  deployer prod "$NOUVELLE" 0.2.0 --commit-donnees "$premier"
  [ "$status" -eq 0 ]
  [ "$(cat "$ETAT/precedent")" = "$ANCIENNE 0.1.0 -" ]
  # Le retour au couple sans données : rien n'est vérifié ni monté, le champ configuration n'est
  # pas lu, et la version quittée est marquée en échec avec son commit.
  : >"$APPELS"
  deployer prod --retour
  [ "$status" -eq 0 ]
  [ -z "$(verifications)" ]
  aucune_ligne ' container inspect ' "$APPELS"
  [ "$(cat "$ETAT/compose.env")" = "$(contenu_compose_env prod "$ANCIENNE" 0.1.0)" ]
  [ -z "$(montage_de /config)" ]
  [ -z "$(montage_de /contenu)" ]
  [ "$(cat "$ETAT/deploye")" = "$ANCIENNE 0.1.0 -" ]
  [ "$(cat "$ETAT/echec")" = "$NOUVELLE $premier" ]

  # Deux couples de la même image, puis le retour au premier des deux : l'image, la version et le
  # commit de precedent, après la même vérification qu'un déploiement.
  commit_de_donnees "$SOUS_CONFIG/profil.yml" "$SOUS_CONTENU/page.md" "$SOUS_CONTENU/deux.md"
  deuxieme="$COMMIT"
  deployer prod "$NOUVELLE" 0.2.0 --commit-donnees "$deuxieme"
  [ "$status" -eq 0 ]
  commit_de_donnees "$SOUS_CONFIG/profil.yml" "$SOUS_CONTENU/page.md" "$SOUS_CONTENU/trois.md"
  troisieme="$COMMIT"
  deployer prod "$NOUVELLE" 0.2.0 --commit-donnees "$troisieme"
  [ "$status" -eq 0 ]
  vise="$(instantane_de prod "$deuxieme")"
  service="$(instantane_de prod "$troisieme")"
  : >"$APPELS"
  deployer prod --retour
  [ "$status" -eq 0 ]
  [ "$(verifications)" = "$(verification config "$NOUVELLE" "$vise")
$(verification contenu "$NOUVELLE" "$vise" "$service")" ]
  grep -Fx "VEILLE_EMPLOI_CONFIG=$vise/config" "$ETAT/compose.env"
  grep -Fx "VEILLE_EMPLOI_CONTENU=$vise/contenu" "$ETAT/compose.env"
  [ "$(montage_de /config)" = "false $vise/config" ]
  [ "$(montage_de /contenu)" = "false $vise/contenu" ]
  [ "$(cat "$ETAT/deploye")" = "$NOUVELLE 0.2.0 $deuxieme" ]
  [ "$(cat "$ETAT/echec")" = "$NOUVELLE $troisieme" ]
  [ ! -e "$ETAT/precedent" ]
  [ "$(signaux)" = "$(signal 'retour à 0.2.0 effectué (depuis 0.2.0)') $HC" ]
}

# Le retour d'un couple en échec : le couple remis en service
# se contrôle comme à l'aller, ses montages après son `up` (ceux de compose.env.precedent) et, aux
# conditions de l'aller, le champ configuration de sa santé. Un conteneur que compose ne recrée pas
# monterait encore l'instantané en échec, et le signal dirait le retour réussi.
@test "deployer : le retour d'un couple en échec remonte l'instantané du précédent" {
  local premier service vise
  horloge_qui_avance
  avec_donnees VERIFIER_CONFIG VERIFIER_CONTENU
  commit_de_donnees "$SOUS_CONFIG/profil.yml" "$SOUS_CONTENU/page.md"
  premier="$COMMIT"
  service="$(instantane_de prod "$premier")"
  deployer prod "$NOUVELLE" 0.2.0 --commit-donnees "$premier"
  [ "$status" -eq 0 ]
  poser_donnees prod
  commit_de_donnees "$SOUS_CONFIG/profil.yml" "$SOUS_CONTENU/autre.md"
  vise="$(instantane_de prod "$COMMIT")"
  # Les données seules en échec (la santé de leur `up` répond 503) : le retour remonte l'instantané
  # du précédent, ses montages se contrôlent après son `up`, et sa santé dit montee.
  export DOUBLE_CURL_SANTE_KO_AU_UP=1
  : >"$APPELS"
  deployer prod "$NOUVELLE" 0.2.0 --commit-donnees "$COMMIT"
  [ "$status" -eq 1 ]
  [[ "$output" == *"échec du déploiement de 0.2.0 (santé non conforme)"* ]]
  [ "$(appels_de docker | sed -nE 's/.* (up -d|container inspect) .*/\1/p')" = "up -d
container inspect
up -d
container inspect" ]
  [[ "$output" == *"montages conformes (/config : $service/config, /contenu : $service/contenu)"* ]]
  [[ "$output" == *"santé conforme (essai "*", configuration montee"* ]]
  [ "$(montage_de /config)" = "false $service/config" ]
  [ "$(montage_de /contenu)" = "false $service/contenu" ]
  [ "$(cat "$ETAT/echec")" = "$NOUVELLE $COMMIT" ]
  [ "$(cat "$ETAT/deploye")" = "$NOUVELLE 0.2.0 $premier" ]
  [ "$(signaux)" = "$(signal 'échec 0.2.0, retour à 0.2.0') $HC/fail" ]
  # Un retour dont le `up` ne recrée pas le conteneur : il monte encore l'instantané en échec, et le
  # retour est en échec, même si sa santé répond.
  export DOUBLE_DOCKER_MONTAGES_GARDES_AU_UP=2
  rm -f "$ETAT/echec"
  : >"$APPELS"
  deployer prod "$NOUVELLE" 0.2.0 --commit-donnees "$COMMIT"
  [ "$status" -eq 1 ]
  [[ "$output" == *"/config : attendu $service/config en lecture seule, monté : false $vise/config"* ]]
  [[ "$output" == *"retour à 0.2.0 en échec : intervention nécessaire"* ]]
  [ "$(montage_de /config)" = "false $vise/config" ]
  [ "$(signaux)" = "$(signal 'échec 0.2.0, retour à 0.2.0 en échec') $HC/fail" ]
  # Un retour recréé, mais dont la santé ne dit pas montee : en échec aussi.
  unset DOUBLE_DOCKER_MONTAGES_GARDES_AU_UP
  export DOUBLE_CURL_CONFIGURATION=exemple
  rm -f "$ETAT/echec"
  : >"$APPELS"
  deployer prod "$NOUVELLE" 0.2.0 --commit-donnees "$COMMIT"
  [ "$status" -eq 1 ]
  [ "$(montage_de /config)" = "false $service/config" ]
  # l'aller, puis le retour, attendaient montee
  [ "$(grep -c 'santé non conforme après 10 essais (attendu : statut ok, version 0.2.0, révision .*, configuration montee)' <<<"$output")" -eq 2 ]
  [ "$(signaux)" = "$(signal 'échec 0.2.0, retour à 0.2.0 en échec') $HC/fail" ]
}

# Docker rend la source d'un montage nettoyée. Un $ETAT qui
# porte « // » (une racine de l'état avec un « / » final) se compare sous sa forme canonique, sans
# résoudre les liens.
@test "deployer : les montages se comparent sous leur forme canonique" {
  local racine="$VEILLE_EMPLOI_RACINE_ETAT" vise propre
  horloge_qui_avance
  export VEILLE_EMPLOI_RACINE_ETAT="$racine/"
  avec_donnees VERIFIER_CONFIG VERIFIER_CONTENU
  commit_de_donnees "$SOUS_CONFIG/profil.yml" "$SOUS_CONTENU/page.md"
  vise="$(instantane_de prod "$COMMIT")"
  propre="$racine/prod/instantanes/$COMMIT"
  [ "$vise" = "$racine//prod/instantanes/$COMMIT" ]
  deployer prod "$NOUVELLE" 0.2.0 --commit-donnees "$COMMIT"
  [ "$status" -eq 0 ]
  grep -Fx "VEILLE_EMPLOI_CONFIG=$vise/config" "$ETAT/compose.env"
  [ "$(montage_de /config)" = "false $propre/config" ]
  [ "$(montage_de /contenu)" = "false $propre/contenu" ]
  [ "$(cat "$ETAT/deploye")" = "$NOUVELLE 0.2.0 $COMMIT" ]
  [ "$(signaux)" = "$(signal "déployé 0.2.0, données ${COMMIT:0:12}") $HC" ]
}

# L'instantané du couple en service, que VERIFIER_CONTENU
# reçoit sur /en-service, se refait s'il manque. S'il ne se refait pas (son commit n'est plus dans
# le clone des données), le refus reste : la vérification n'a pas lieu, et rien ne change.
@test "deployer : l'instantané du couple en service se refait s'il manque" {
  local premier service vise absent
  horloge_qui_avance
  avec_donnees VERIFIER_CONTENU
  commit_de_donnees "$SOUS_CONTENU/page.md"
  premier="$COMMIT"
  service="$(instantane_de prod "$premier")"
  deployer prod "$ANCIENNE" 0.1.0 --commit-donnees "$premier"
  [ "$status" -eq 0 ]
  poser_donnees prod
  chmod -R u+w "$service"
  rm -rf "$service"
  commit_de_donnees "$SOUS_CONTENU/page.md" "$SOUS_CONTENU/autre.md"
  vise="$(instantane_de prod "$COMMIT")"
  : >"$APPELS"
  deployer prod "$NOUVELLE" 0.2.0 --commit-donnees "$COMMIT"
  [ "$status" -eq 0 ]
  [[ "$output" == *"instantané des données prêt : $service"* ]]
  [ "$(cat "$service/contenu/page.md")" = "fichier d'exemple $SOUS_CONTENU/page.md" ]
  [ "$(verifications)" = "$(verification contenu "$NOUVELLE" "$vise" "$service")" ]
  [ "$(cat "$ETAT/deploye")" = "$NOUVELLE 0.2.0 $COMMIT" ]
  # Un couple en service dont le commit n'est plus dans le clone : son instantané ne se refait pas.
  absent="$(printf 'e%.0s' {1..40})"
  printf '%s 0.2.0 %s\n' "$NOUVELLE" "$absent" >"$ETAT/deploye"
  commit_de_donnees "$SOUS_CONTENU/page.md" "$SOUS_CONTENU/trois.md"
  etat_fige
  deployer prod "$SUIVANTE" 0.3.0 --commit-donnees "$COMMIT"
  [ "$status" -eq 1 ]
  [[ "$output" == *"instantané en service introuvable : $(instantane_de prod "$absent")"* ]]
  [ -z "$(verifications)" ]
  rien_n_a_change "vérification des données impossible avant 0.3.0, rien n'a changé (voir le journal)"
}

# --retour refuse (64), sans rien toucher, le commit de données
# de precedent que projet.env (plus aucune commande déclarée) ou le clone des données (commit absent)
# refusent.
@test "deployer : --retour refuse un commit que projet.env ou le clone refusent" {
  local absent
  horloge_qui_avance
  avec_donnees VERIFIER_CONTENU
  commit_de_donnees "$SOUS_CONTENU/page.md"
  deployer prod "$ANCIENNE" 0.1.0 --commit-donnees "$COMMIT"
  [ "$status" -eq 0 ]
  poser_donnees prod
  deployer prod "$NOUVELLE" 0.2.0 --commit-donnees "$COMMIT"
  [ "$status" -eq 0 ]
  [ "$(cat "$ETAT/precedent")" = "$ANCIENNE 0.1.0 $COMMIT" ]
  projet_env_du_test
  etat_fige
  deployer prod --retour
  [ "$status" -eq 64 ]
  [[ "$output" == *"retour arrière impossible : commit de données $COMMIT, mais deploiement/projet.env ne déclare ni VERIFIER_CONFIG ni VERIFIER_CONTENU"* ]]
  [ ! -s "$APPELS" ]
  diff -r "$BATS_TEST_TMPDIR/etat-avant" "$ETAT"
  avec_donnees VERIFIER_CONTENU
  absent="$(printf 'f%.0s' {1..40})"
  printf '%s 0.1.0 %s\n' "$ANCIENNE" "$absent" >"$ETAT/precedent"
  etat_fige
  deployer prod --retour
  [ "$status" -eq 64 ]
  [[ "$output" == *"retour arrière impossible : commit de données $absent introuvable dans $CLONE_DONNEES. Rien n'a changé"* ]]
  [ ! -s "$APPELS" ]
  diff -r "$BATS_TEST_TMPDIR/etat-avant" "$ETAT"
}

# Sans --commit-donnees, un projet qui déclare une commande de l'instance refuse (64),
# et un projet qui n'en déclare aucune prend « - ».
@test "deployer : sans --commit-donnees" {
  local commande
  deja_en_service "$ANCIENNE" 0.1.0
  for commande in VERIFIER_CONFIG VERIFIER_CONTENU; do
    projet_env_du_test
    avec_donnees "$commande"
    etat_fige
    deployer prod "$NOUVELLE" 0.2.0
    [ "$status" -eq 64 ]
    [[ "$output" == *"commit de données absent : deploiement/projet.env déclare $commande ; relancer avec --commit-donnees <sha>. Rien n'a changé"* ]]
    [ ! -s "$APPELS" ]
    diff -r "$BATS_TEST_TMPDIR/etat-avant" "$ETAT"
  done
  projet_env_du_test
  deployer prod "$NOUVELLE" 0.2.0
  [ "$status" -eq 0 ]
  [ "$(cat "$ETAT/deploye")" = "$NOUVELLE 0.2.0 -" ]
  # Sans commande, un commit n'a pas de sens : le couple d'un projet sans données a le commit « - ».
  commit_de_donnees "$SOUS_CONFIG/profil.yml"
  etat_fige
  deployer prod "$SUIVANTE" 0.3.0 --commit-donnees "$COMMIT"
  [ "$status" -eq 64 ]
  [[ "$output" == *"commit de données $COMMIT, mais deploiement/projet.env ne déclare ni VERIFIER_CONFIG ni VERIFIER_CONTENU"* ]]
  [ ! -s "$APPELS" ]
  diff -r "$BATS_TEST_TMPDIR/etat-avant" "$ETAT"
  # Un commit que le clone des données n'a pas : refus aussi.
  avec_donnees VERIFIER_CONFIG
  deployer prod "$SUIVANTE" 0.3.0 --commit-donnees "$(printf 'f%.0s' {1..40})"
  [ "$status" -eq 64 ]
  [[ "$output" == *"commit de données $(printf 'f%.0s' {1..40}) introuvable dans $CLONE_DONNEES. Rien n'a changé"* ]]
  [ ! -s "$APPELS" ]
  diff -r "$BATS_TEST_TMPDIR/etat-avant" "$ETAT"
}

# Le staging d'un projet qui déclare VERIFIER_CONFIG, dont les données
# portent une configuration, ne monte jamais /config : ni dans compose.env, ni dans la vérification,
# ni dans le contrôle des montages après le `up` ; sa santé doit dire exemple.
@test "deployer : le staging ne monte jamais /config" {
  local etat="$VEILLE_EMPLOI_RACINE_ETAT/staging" vise cas raison
  horloge_qui_avance
  preparer_secrets_de_test staging JETON=jeton-staging-7 HC_SONDE=https://hc.example/ping/sonde-staging
  avec_donnees VERIFIER_CONFIG VERIFIER_CONTENU
  commit_de_donnees "$SOUS_CONFIG/profil.yml" "$SOUS_CONTENU/page.md"
  vise="$(instantane_de staging "$COMMIT")"
  deployer staging "$NOUVELLE" main --commit-donnees "$COMMIT"
  [ "$status" -eq 0 ]
  [[ "$output" == *"staging : VERIFIER_CONFIG n'est pas lancée, /config n'y est jamais monté"* ]]
  [ "$(verifications)" = "$(verification contenu "$NOUVELLE" "$vise")" ]
  [ ! -e "$vise/config" ]
  aucune_ligne '^VEILLE_EMPLOI_CONFIG=' "$etat/compose.env"
  grep -Fx "VEILLE_EMPLOI_CONTENU=$vise/contenu" "$etat/compose.env"
  appels_de docker | grep -Fx "$(dc_de staging contenu) up -d --wait --wait-timeout 120 --remove-orphans"
  [ -z "$(montage_de /config)" ]
  [ "$(montage_de /contenu)" = "false $vise/contenu" ]
  # la santé a dit exemple
  [ "$(cat "$etat/deploye")" = "$NOUVELLE main $COMMIT" ]
  # Une santé qui dit montee, ou un /config monté d'ailleurs (par compose.projet.yml) : échec.
  poser_donnees staging
  for cas in DOUBLE_CURL_CONFIGURATION=montee "DOUBLE_DOCKER_MONTAGES_EN_PLUS=/config:$CLONE_DONNEES/$SOUS_CONFIG"; do
    : >"$APPELS"
    export "${cas?}"
    deployer staging "$SUIVANTE" main --commit-donnees "$COMMIT"
    [ "$status" -eq 1 ]
    raison="santé non conforme"
    [[ "$cas" != DOUBLE_DOCKER_MONTAGES_EN_PLUS=* ]] || raison="montage des données non conforme"
    [[ "$output" == *"échec du déploiement de main ($raison)"* ]]
    [ "$(cat "$etat/echec")" = "$SUIVANTE $COMMIT" ]
    [ "$(cat "$etat/deploye")" = "$NOUVELLE main $COMMIT" ]
    unset "${cas%%=*}"
    export DOUBLE_CURL_CONFIGURATION=auto
  done
  [[ "$output" == *"/config monté alors que le couple ne le monte pas : false $CLONE_DONNEES/$SOUS_CONFIG"* ]]
}

# Un projet qui ne déclare aucune commande de l'instance ne change pas de comportement : rien n'est
# lu, vérifié, extrait ni monté, le champ configuration n'est pas lu, et son couple a le commit « - ».
@test "deployer : un projet sans données écrit un couple en -" {
  horloge_qui_avance
  deja_en_service "$ANCIENNE" 0.1.0
  # des données dans le clone, une santé qui dit son champ configuration : rien n'y change
  commit_de_donnees "$SOUS_CONFIG/profil.yml" "$SOUS_CONTENU/page.md"
  export DOUBLE_CURL_CONFIGURATION=exemple
  deployer prod "$NOUVELLE" 0.2.0
  [ "$status" -eq 0 ]
  [ "$(cat "$ETAT/deploye")" = "$NOUVELLE 0.2.0 -" ]
  # precedent garde tel quel l'état d'avant la v0.7.0, qui se lit comme un couple en « - »
  [ "$(cat "$ETAT/precedent")" = "$ANCIENNE 0.1.0" ]
  [ "$(cat "$ETAT/compose.env")" = "$(contenu_compose_env prod "$NOUVELLE" 0.2.0)" ]
  [ -z "$(verifications)" ]
  aucune_ligne ' container inspect ' "$APPELS"
  [ ! -e "$ETAT/instantanes" ]
  [ "$(signaux)" = "$(signal 'déployé 0.2.0') $HC" ]
  # un échec marque « <image> - »
  export DOUBLE_CURL_SANTE_KO="$SUIVANTE"
  deployer prod "$SUIVANTE" 0.3.0
  [ "$status" -eq 1 ]
  [ "$(cat "$ETAT/echec")" = "$SUIVANTE -" ]
  # le retour arrière aussi, vers l'état d'avant la v0.7.0
  unset DOUBLE_CURL_SANTE_KO
  deployer prod --retour
  [ "$status" -eq 0 ]
  [ "$(cat "$ETAT/deploye")" = "$ANCIENNE 0.1.0 -" ]
  [ "$(cat "$ETAT/echec")" = "$NOUVELLE -" ]
}

# --- compose : deux fichiers, orphelins ------------------------------------------------------

# dc compose les deux fichiers, dans l'ordre : compose.yml, géré par le modèle, puis
# compose.projet.yml, les ajouts du projet, que compose fusionne au premier. Tous les appels de
# compose du déploiement, retour arrière compris, passent par eux.
@test "deployer_deux_fichiers_compose" {
  deja_en_service "$ANCIENNE" 0.1.0
  export DOUBLE_CURL_SANTE_KO="$NOUVELLE"
  deployer prod "$NOUVELLE" 0.2.0
  [ "$status" -eq 1 ]
  local dc ligne n=0
  dc="$(dc_de prod)"
  while IFS= read -r ligne; do
    [[ "$ligne" == "$dc "* ]] || {
      echo "appel de compose hors de dc : $ligne" >&2
      return 1
    }
    n=$((n + 1))
  done < <(appels_de docker | grep '^docker compose ')
  # ps et instantané, lancement de la nouvelle, puis retour à l'ancienne
  [ "$n" -eq 4 ]
}

# Migration 1 : chaque `up`, celui du déploiement comme celui du retour arrière, porte
# --remove-orphans. Un conteneur dont aucun des deux fichiers compose ne déclare plus le service (un
# service retiré de compose.projet.yml) ne reste pas en service.
@test "deployer_supprime_les_orphelins" {
  deja_en_service "$ANCIENNE" 0.1.0
  export DOUBLE_CURL_SANTE_KO="$NOUVELLE"
  deployer prod "$NOUVELLE" 0.2.0
  [ "$status" -eq 1 ]
  [ "$(appels_de docker | grep -c ' up ')" -eq 2 ]
  [ "$(nombre_de_lancements)" -eq 2 ]
}

# --- secrets et environnement ----------------------------------------------------------------

# Migration 1 : le tunnel est commun au serveur. Le projet n'a plus de jeton de tunnel dans ses
# secrets, ni de profil de compose pour le lever : des secrets sans jeton se déploient.
@test "deployer_sans_jeton_de_tunnel_deploie" {
  preparer_secrets_de_test prod "HC_SONDE=$HC"
  deja_en_service "$ANCIENNE" 0.1.0
  deployer prod "$NOUVELLE" 0.2.0
  [ "$status" -eq 0 ]
  [ "$(cat "$ETAT/deploye")" = "$NOUVELLE 0.2.0 -" ]
  [ ! -e "$ETAT/echec" ]
  [ "$(nombre_de_lancements)" -eq 1 ]
  aucune_ligne ' --profile' "$APPELS"
  grep -Fx "VEILLE_EMPLOI_IMAGE=$NOUVELLE" "$EN_SERVICE"
  [ "$(signaux)" = "$(signal 'déployé 0.2.0') $HC" ]
}

# Compose donne la priorité au shell sur --env-file (le double de docker aussi) : une image
# exportée ferait relancer la nouvelle version par le retour arrière, et un montage exporté
# monterait autre chose que l'instantané vérifié (la copie de travail du clone des données…).
# deployer.sh refuse de partir, que la variable vienne du shell ou d'une ligne de l'env de
# l'environnement (refuser_image_heritee, après charger_env et charger_secrets).
@test "refuse_une_image_ou_une_version_posees_dans_l_environnement" {
  deja_en_service "$ANCIENNE" 0.1.0
  cp "$ETAT/compose.env" "$BATS_TEST_TMPDIR/compose.env.avant"
  cp "$CLONE_DONNEES/$SOUS_ENV/prod.env" "$BATS_TEST_TMPDIR/prod.env.avant"
  export DOUBLE_CURL_SANTE_KO="$NOUVELLE"
  local variable origine
  for variable in VEILLE_EMPLOI_IMAGE VEILLE_EMPLOI_VERSION VEILLE_EMPLOI_CONFIG VEILLE_EMPLOI_CONTENU; do
    for origine in shell env; do
      : >"$APPELS"
      unset VEILLE_EMPLOI_IMAGE VEILLE_EMPLOI_VERSION VEILLE_EMPLOI_CONFIG VEILLE_EMPLOI_CONTENU
      cp "$BATS_TEST_TMPDIR/prod.env.avant" "$CLONE_DONNEES/$SOUS_ENV/prod.env"
      if [ "$origine" = shell ]; then
        export "$variable=$CLONE_DONNEES/valeur-heritee"
      else
        echo "$variable=$CLONE_DONNEES/valeur-heritee" >>"$CLONE_DONNEES/$SOUS_ENV/prod.env"
      fi
      deployer prod "$NOUVELLE" 0.2.0
      [ "$status" -eq 1 ]
      [[ "$output" == *"$variable est posée dans l'environnement"* ]]
      # rien n'a été tenté : ni instantané, ni lancement, ni état, ni signal
      [ ! -s "$APPELS" ]
      diff "$ETAT/compose.env" "$BATS_TEST_TMPDIR/compose.env.avant"
      [ ! -e "$ETAT/echec" ]
      grep -Fx "VEILLE_EMPLOI_IMAGE=$ANCIENNE" "$EN_SERVICE"
    done
  done
}

# poser_url_publique <valeur> : l'env de la prod du clone des données du test avec cette
# VEILLE_EMPLOI_URL_PUBLIQUE (sans valeur : la ligne est retirée). %q l'écrit sur une seule ligne.
poser_url_publique() {
  sed -i '/^VEILLE_EMPLOI_URL_PUBLIQUE=/d' "$CLONE_DONNEES/$SOUS_ENV/prod.env"
  [ "$#" -eq 0 ] || printf 'VEILLE_EMPLOI_URL_PUBLIQUE=%q
' "$1" >>"$CLONE_DONNEES/$SOUS_ENV/prod.env"
}

# Une adresse qui n'est pas http(s)://hôte[:port] ne s'écrit pas dans compose.env (une valeur sur
# deux lignes y injecterait une variable), et ne fait pas lancer une application qui refuserait de
# démarrer : refus net, avant tout.
@test "deploiement_refuse_une_url_publique_invalide" {
  deja_en_service "$ANCIENNE" 0.1.0
  etat_fige
  local url
  for url in '' 'veille-emploi.exemple.org' 'ftp://veille-emploi.exemple.org' 'https://'     'https://veille-emploi.exemple.org/' 'https://veille-emploi.exemple.org/chemin'     'https://veille-emploi.exemple.org?x=1' 'https://veille-emploi.exemple.org:'     'https://veille-emploi.exemple.org:44a' 'https://moi@veille-emploi.exemple.org'     'https://Majuscules.exemple.org' 'https://veille-emploi.exemple.org '     $'https://veille-emploi.exemple.org
VEILLE_EMPLOI_PORT=80'; do
    poser_url_publique "$url"
    : >"$APPELS"
    deployer prod "$NOUVELLE" 0.2.0
    [ "$status" -eq 1 ]
    [[ "$output" == *"VEILLE_EMPLOI_URL_PUBLIQUE invalide ou absente de $CLONE_DONNEES/$SOUS_ENV/prod.env "* ]]
    [[ "$output" == *"Rien n'a changé"* ]]
    # rien n'a été tenté : ni instantané, ni lancement, ni état, ni signal
    [ ! -s "$APPELS" ]
    diff -r "$ETAT" "$BATS_TEST_TMPDIR/etat-avant"
    grep -Fx "VEILLE_EMPLOI_IMAGE=$ANCIENNE" "$EN_SERVICE"
  done
  # absente du fichier d'environnement : même refus
  poser_url_publique
  deployer prod "$NOUVELLE" 0.2.0
  [ "$status" -eq 1 ]
  [[ "$output" == *"VEILLE_EMPLOI_URL_PUBLIQUE invalide"* ]]
  [ ! -s "$APPELS" ]
  diff -r "$ETAT" "$BATS_TEST_TMPDIR/etat-avant"
  # et un retour arrière, qui réécrit aussi compose.env, la refuse de la même façon
  poser_url_publique 'https://veille-emploi.exemple.org/'
  deployer prod --retour
  [ "$status" -eq 1 ]
  [[ "$output" == *"VEILLE_EMPLOI_URL_PUBLIQUE invalide"* ]]
  [ ! -s "$APPELS" ]
  diff -r "$ETAT" "$BATS_TEST_TMPDIR/etat-avant"
}

# Les secrets de la version (charger_secrets) atteignent compose par son environnement, où
# compose.projet.yml peut les lire ; jamais par un argument ni par un fichier d'état.
@test "deployer_les_secrets_atteignent_compose" {
  deja_en_service "$ANCIENNE" 0.1.0
  export DOUBLE_DOCKER_SECRETS='JETON AUTRE_SECRET'
  deployer prod "$NOUVELLE" 0.2.0
  [ "$status" -eq 0 ]
  # compose a reçu JETON dans son environnement (le double n'en note que le nom), et pas une
  # variable que les secrets ne déclarent pas…
  [ "$(cat "$BATS_TEST_TMPDIR/secrets-recus")" = JETON ]
  # …et jamais en argument ni dans un fichier d'état
  aucune_ligne jeton-prod-7 "$APPELS" "$ETAT"/*
}

@test "deployer_ne_laisse_aucun_secret_dans_une_trace" {
  deja_en_service "$ANCIENNE" 0.1.0
  run bash -x "$CLONE/deploiement/deployer.sh" prod "$NOUVELLE" 0.2.0
  [ "$status" -eq 0 ]
  [ "$(signaux)" = "$(signal 'déployé 0.2.0') $HC" ]
  [[ "$output" != *jeton-prod-7* ]]
  [[ "$output" != *hc.example* ]]
}

# --- verrou ----------------------------------------------------------------------------------

# attendre_le_verrou <fichier> : attend (5 s au plus) qu'un autre processus tienne le verrou.
attendre_le_verrou() {
  local _
  for _ in $(seq 1 100); do
    flock -n "$1" true || return 0
    sleep 0.05
  done
  echo "le verrou n'a jamais été pris" >&2
  return 1
}

@test "deployer_attend_le_verrou_qu_il_ne_tient_pas" {
  mkdir -p "$ETAT"
  # 3>&- : le processus d'arrière-plan ne garde pas la sortie de bats ouverte
  # shellcheck disable=SC2016  # $APPELS est développé par le bash d'arrière-plan
  flock "$ETAT/verrou" bash -c 'sleep 1; echo "verrou libéré" >>"$APPELS"' 3>&- &
  attendre_le_verrou "$ETAT/verrou"
  deployer prod "$NOUVELLE" 0.2.0
  wait
  [ "$status" -eq 0 ]
  # rien n'a été lancé avant que le verrou soit rendu
  [ "$(head -n 1 "$APPELS")" = "verrou libéré" ]
}

@test "deployer_n_attend_pas_le_verrou_que_la_sonde_tient" {
  mkdir -p "$ETAT"
  exec 8>"$ETAT/verrou"
  flock -n 8
  export VEILLE_EMPLOI_VERROU_TENU=1
  run timeout 60 bash "$CLONE/deploiement/deployer.sh" prod "$NOUVELLE" 0.2.0
  exec 8>&-
  [ "$status" -eq 0 ]
  [ "$(cat "$ETAT/deploye")" = "$NOUVELLE 0.2.0 -" ]
}

# --- ménage des images -----------------------------------------------------------------------
#
# Après un succès (déploiement ou retour arrière), deployer.sh lance nettoyer-images.sh sous son
# verrou. Le double de docker tient un stock (poser_image) : le ménage y retire ce que ni l'état, ni
# un conteneur, ni la marge des 3 plus récentes ne gardent.

# stock_a_nettoyer : une image du dépôt, la plus ancienne et sans protection (9), et trois plus
# récentes (6, 7 et 8) qui remplissent la marge.
stock_a_nettoyer() {
  poser_image 9 2026-01-01T10:00:00Z "" "$(empreinte_de 9)"
  poser_image 6 2026-10-06T10:00:00Z "" "$(empreinte_de 6)"
  poser_image 7 2026-10-07T10:00:00Z "" "$(empreinte_de 7)"
  poser_image 8 2026-10-08T10:00:00Z "" "$(empreinte_de 8)"
}

@test "deploiement_reussi_lance_le_menage" {
  deja_en_service "$ANCIENNE" 0.1.0
  stock_a_nettoyer
  deployer prod "$NOUVELLE" 0.2.0
  [ "$status" -eq 0 ]
  appels_de docker | grep -Fx 'docker image ls --all --no-trunc --quiet'
  aucune_ligne "^$(image_de 9)\|" "$BATS_TEST_TMPDIR/images"
  grep -q "^$(image_de 8)|" "$BATS_TEST_TMPDIR/images"
}

@test "retour_reussi_lance_le_menage" {
  deux_versions
  stock_a_nettoyer
  deployer prod --retour
  [ "$status" -eq 0 ]
  appels_de docker | grep -Fx 'docker image ls --all --no-trunc --quiet'
  aucune_ligne "^$(image_de 9)\|" "$BATS_TEST_TMPDIR/images"
  grep -q "^$(image_de 8)|" "$BATS_TEST_TMPDIR/images"
}

@test "deploiement_en_echec_ne_lance_pas_le_menage" {
  deja_en_service "$ANCIENNE" 0.1.0
  stock_a_nettoyer
  export DOUBLE_DOCKER_UP_ECHEC="$NOUVELLE"
  deployer prod "$NOUVELLE" 0.2.0
  [ "$status" -eq 1 ]
  [ "$(nombre_d_appels docker)" -gt 0 ]
  aucune_ligne ' image ls' "$APPELS"
  grep -q "^$(image_de 9)|" "$BATS_TEST_TMPDIR/images"
}

@test "menage_en_echec_le_deploiement_reste_reussi" {
  deja_en_service "$ANCIENNE" 0.1.0
  stock_a_nettoyer
  export DOUBLE_DOCKER_IMAGE_LS_ECHEC=1
  deployer prod "$NOUVELLE" 0.2.0
  [ "$status" -eq 0 ]
  [ "$(cat "$ETAT/deploye")" = "$NOUVELLE 0.2.0 -" ]
  [[ "$output" == *"ménage des images en échec (code 1) : le déploiement reste réussi"* ]]
  [ "$(signaux)" = "$(signal 'déployé 0.2.0') $HC" ]
  aucune_ligne '/fail' "$APPELS.urls"
}

@test "le_menage_passe_apres_le_signal_ok" {
  deja_en_service "$ANCIENNE" 0.1.0
  stock_a_nettoyer
  deployer prod "$NOUVELLE" 0.2.0
  [ "$status" -eq 0 ]
  [ -n "$(ligne_de ' -K -')" ]
  [ "$(ligne_de ' -K -')" -lt "$(ligne_de ' image ls')" ]
}

# De bout en bout : ce que deployer.sh vient d'écrire dans l'état (deploye, precedent, compose.env,
# compose.env.precedent), le ménage le lit. Les images de la version déployée (d) et de la
# précédente (c) sont plus anciennes que les trois de la marge : seul l'état les garde, et sans
# lui elles partiraient avec la quatrième image, plus ancienne encore (9).
@test "le_menage_garde_ce_que_le_deploiement_vient_d_ecrire" {
  deja_en_service "$ANCIENNE" 0.1.0
  poser_image c 2026-01-02T10:00:00Z "" "$ANCIENNE"
  poser_image d 2026-01-03T10:00:00Z "" "$NOUVELLE"
  stock_a_nettoyer
  deployer prod "$NOUVELLE" 0.2.0
  [ "$status" -eq 0 ]
  grep -q "^$(image_de c)|" "$BATS_TEST_TMPDIR/images"
  grep -q "^$(image_de d)|" "$BATS_TEST_TMPDIR/images"
  aucune_ligne "^$(image_de 9)\|" "$BATS_TEST_TMPDIR/images"
  [[ "$output" == *"ménage des images : 1 retirée, 5 gardées (2 par l'état, 0 par un conteneur, 3 en marge)"* ]]
}

# Le ménage des instantanés des données suit celui des images, sous le même verrou (M-0004, § 8).
# Une surprise l'annule sans rien retirer, et le déploiement reste réussi, son signal compris.
@test "deployer : une surprise du ménage des instantanés ne change pas le résultat" {
  deja_en_service "$ANCIENNE" 0.1.0
  stock_a_nettoyer
  mkdir -p "$ETAT/instantanes"
  echo "pas un instantané" >"$ETAT/instantanes/notes"
  deployer prod "$NOUVELLE" 0.2.0
  [ "$status" -eq 0 ]
  [ "$(cat "$ETAT/deploye")" = "$NOUVELLE 0.2.0 -" ]
  [ "$(signaux)" = "$(signal 'déployé 0.2.0') $HC" ]
  [[ "$output" == *"ménage des instantanés annulé, rien n'est retiré : nom inattendu : $ETAT/instantanes/notes"* ]]
  [[ "$output" != *"ménage des images en échec"* ]]
  # les images, elles, sont rangées
  aucune_ligne "^$(image_de 9)\|" "$BATS_TEST_TMPDIR/images"
  [ -f "$ETAT/instantanes/notes" ]
}

# --- divers ----------------------------------------------------------------------------------

# Le signal est un plus : un service de supervision injoignable ne change pas le résultat (son
# silence finit par alerter de lui-même).
@test "un_signal_impossible_ne_change_pas_le_resultat" {
  export DOUBLE_CURL_SIGNAL_CODE=6
  deployer prod "$NOUVELLE" 0.2.0
  [ "$status" -eq 0 ]
  [ "$(cat "$ETAT/deploye")" = "$NOUVELLE 0.2.0 -" ]
  [ "$(signaux)" = "$(signal 'déployé 0.2.0') $HC" ]
}

@test "deployer_refuse_des_arguments_invalides" {
  local -a cas=(
    "prod"
    "prod $NOUVELLE"
    "prod $NOUVELLE 0.2.0 en-trop"
    "essai $NOUVELLE 0.2.0"
    "prod ghcr.io/edouardzemb/veille-emploi:main main"
    "prod ghcr.io/edouardzemb/veille-emploi@sha256:1234 main"
    "prod $NOUVELLE v0.2.0"
    "prod $NOUVELLE 0.2"
    "prod --retour en-trop"
    "prod --retourner"
    "--retour prod"
    "essai --retour"
    "prod --retour --commit-donnees $(printf 'a%.0s' {1..40})"
    "prod $NOUVELLE 0.2.0 --commit-donnees"
    "prod $NOUVELLE 0.2.0 --commit-donnees -"
    "prod $NOUVELLE 0.2.0 --commit-donnees $(printf 'a%.0s' {1..39})"
    "prod $NOUVELLE 0.2.0 --commit-donnees $(printf 'A%.0s' {1..40})"
    "prod $NOUVELLE 0.2.0 --commit-donnees $(printf 'a%.0s' {1..40}) --commit-donnees $(printf 'a%.0s' {1..40})"
    "prod $NOUVELLE 0.2.0 --donnees-neuves --donnees-neuves"
  )
  local arguments
  for arguments in "${cas[@]}"; do
    # shellcheck disable=SC2086  # découpage voulu
    deployer $arguments
    [ "$status" -eq 64 ]
  done
  # une version sur deux lignes injecterait une variable dans compose.env
  deployer prod "$NOUVELLE" $'0.2.0\nVEILLE_EMPLOI_PORT=80'
  [ "$status" -eq 64 ]
  [ ! -s "$APPELS" ]
  [ ! -e "$ETAT/compose.env" ]
}

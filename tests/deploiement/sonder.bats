#!/usr/bin/env bats
# sonder.sh : verrou, clones, cible (main ou plus haute étiquette), image, couple visé (l'image et
# le commit de données), état, déploiement.
#
# git, docker et curl sont des doubles (tests/deploiement/doubles/). deployer.sh et
# installer-unites.sh sont remplacés, dans le clone temporaire, par des doubles qui notent leur
# appel ; un test de bout en bout garde le vrai deployer.sh.
# Deux dépôts : le clone des données est un vrai dépôt git, clone d'une origine du test (un dépôt nu)
# où un autre clone, le « poste », pousse des commits et des étiquettes. Le double de git y passe
# la main au vrai git (DOUBLE_GIT_REEL_DANS) : ses appels sont notés comme les autres.

# Chaque test tourne dans son propre processus : les `export DOUBLE_*` d'un test ne fuient pas
# dans les autres, comme le veut le pilotage des doubles.
# shellcheck disable=SC2030,SC2031

bats_require_minimum_version 1.5.0

load aide

setup() {
  preparer_environnement
  installer_doubles docker git curl
  # Les commandes de l'instance que déclarerait le projet.env du projet ne sont pas celles du test :
  # il part d'un projet qui n'en déclare aucune, et avec_donnees les ajoute.
  sed -i '/^VERIFIER_CONFIG=/d; /^VERIFIER_CONTENU=/d' "$CLONE/deploiement/projet.env"
  # Le clone des données du test (aide.bash) devient le clone d'une origine. Les secrets et les clés
  # que le test y fabrique n'y sont pas versionnés : ils ne le rendent pas modifié.
  ORIGINE_DONNEES="$BATS_TEST_TMPDIR/origine-donnees.git"
  "$GIT_REEL" clone -q --bare "$CLONE_DONNEES" "$ORIGINE_DONNEES"
  git_donnees remote add origin "$ORIGINE_DONNEES"
  git_donnees fetch -q origin
  printf '%s\n' /secrets/ /cles/ /.sops.yaml >>"$CLONE_DONNEES/.git/info/exclude"
  export DOUBLE_GIT_REEL_DANS="$CLONE_DONNEES"
  # La référence que le double de docker donne par défaut à la cible, et une autre.
  EMPREINTE="ghcr.io/edouardzemb/veille-emploi@sha256:$(printf 'a%.0s' {1..64})"
  AUTRE="ghcr.io/edouardzemb/veille-emploi@sha256:$(printf 'b%.0s' {1..64})"
  # Le double de deployer.sh note aussi si le verrou de la sonde est tenu pendant son exécution.
  # shellcheck disable=SC2016  # corps des doubles : développé quand ils tournent, pas ici
  remplacer_par_un_double deployer.sh '
tenu=non
flock -n "$VEILLE_EMPLOI_RACINE_ETAT/$1/verrou" true || tenu=oui
echo "pendant le déploiement : verrou tenu=$tenu VEILLE_EMPLOI_VERROU_TENU=${VEILLE_EMPLOI_VERROU_TENU:-}" >>"$APPELS"
exit "${DOUBLE_DEPLOYER_CODE:-0}"'
  # Celui d'installer-unites.sh note, à l'installation, si la sonde dit qu'elle va déployer.
  # shellcheck disable=SC2016
  remplacer_par_un_double installer-unites.sh '
[ "${1:-}" != --verifier ] || exit "${DOUBLE_UNITES_ECART:-0}"
echo "installation des unités : VEILLE_EMPLOI_AVANT_DEPLOIEMENT=${VEILLE_EMPLOI_AVANT_DEPLOIEMENT:-}" >>"$APPELS"
exit "${DOUBLE_UNITES_INSTALLATION_CODE:-0}"'
}

# remplacer_par_un_double <script> <corps> : remplace deploiement/<script> du clone temporaire par
# un double qui note son appel dans $APPELS, puis exécute le corps.
remplacer_par_un_double() {
  cat >"$CLONE/deploiement/$1" <<EOF
#!/usr/bin/env bash
{ printf '%s' '$1'; for argument in "\$@"; do printf ' %s' "\$argument"; done; printf '\n'; } >> '$APPELS'
$2
EOF
}

# preparer <env> : secrets de test et dossier d'état de cet environnement.
preparer() {
  ETAT="$VEILLE_EMPLOI_RACINE_ETAT/$1"
  HC="https://hc.example/ping/sonde-$1"
  preparer_secrets_de_test "$1" "JETON=jeton-$1-7" "HC_SONDE=$HC"
  mkdir -p "$ETAT"
}

sonder() {
  run bash "$CLONE/deploiement/sonder.sh" "$@"
}

# signaux : les appels de curl vers la supervision.
signaux() {
  envois_supervision
}

signal() {
  printf 'curl -fsS -m 10 --retry 3 --data-raw %s' "$1"
}

# avec_donnees <commande…> : deploiement/projet.env déclare aussi ces commandes de l'instance
# (VERIFIER_CONFIG, VERIFIER_CONTENU) : le couple visé a un commit de données.
avec_donnees() {
  local commande
  for commande in "$@"; do
    printf '%s=outil %s\n' "$commande" "${commande,,}" >>"$CLONE/deploiement/projet.env"
  done
}

# appels_git_dans <clone> : les appels de git qui visent ce clone (`git -C <clone> …`).
appels_git_dans() {
  appels_de git | grep -F "git -C $1 " || true
}

# arbre_vise [<commande…>] : l'arbre de l'étiquette visée du code, que le double de git sert à
# `ls-tree` et à `show` (DOUBLE_GIT_ARBRE) : son deploiement/projet.env est celui de la copie
# de travail, sans commande de l'instance, avec ces commandes.
arbre_vise() {
  local arbre="$BATS_TEST_TMPDIR/arbre-vise" commande
  mkdir -p "$arbre/deploiement"
  sed '/^VERIFIER_CONFIG=/d; /^VERIFIER_CONTENU=/d' "$CLONE/deploiement/projet.env" \
    >"$arbre/deploiement/projet.env"
  for commande in "$@"; do
    printf '%s=outil %s\n' "$commande" "${commande,,}" >>"$arbre/deploiement/projet.env"
  done
  export DOUBLE_GIT_ARBRE="$arbre"
}

# git_poste <args…> : le vrai git dans le poste, un autre clone de l'origine des données.
git_poste() {
  "$GIT_REEL" -C "$BATS_TEST_TMPDIR/poste-donnees" -c user.name=Essai -c user.email=essai@exemple.org "$@"
}

# pousser_des_donnees <chemin…> : un commit sur la branche des données de l'origine, fait depuis le
# poste, avec un fichier d'exemple à chacun de ces chemins ; son sha dans COMMIT. Le clone des
# données du test est alors en retard sur l'origine.
pousser_des_donnees() {
  local poste="$BATS_TEST_TMPDIR/poste-donnees" chemin
  [ -d "$poste" ] || "$GIT_REEL" clone -q "$ORIGINE_DONNEES" "$poste"
  for chemin in "$@"; do
    mkdir -p "$(dirname "$poste/$chemin")"
    echo "fichier d'exemple $chemin" >"$poste/$chemin"
  done
  git_poste add -A
  git_poste commit -q --allow-empty -m "des données du poste"
  git_poste push -q origin HEAD:principal
  COMMIT="$(git_poste rev-parse HEAD)"
}

# etiqueter_les_donnees <étiquette…> : ces étiquettes sur le dernier commit du poste, envoyées à
# l'origine.
etiqueter_les_donnees() {
  local etiquette
  for etiquette in "$@"; do
    git_poste tag "$etiquette"
    git_poste push -q origin "refs/tags/$etiquette"
  done
}

# --- staging ---------------------------------------------------------------------------------

@test "ne_fait_rien_si_deja_deploye" {
  preparer staging
  echo "$EMPREINTE main" >"$ETAT/deploye"
  sonder staging
  [ "$status" -eq 0 ]
  # la sonde a suivi la branche principale (R22) et tiré :main…
  [ "$(appels_git_dans "$CLONE")" = "$(printf '%s\n' "git -C $CLONE status --porcelain" \
    "git -C $CLONE fetch origin principal" \
    "git -C $CLONE merge --ff-only origin/principal")" ]
  # …et la branche des données, même sans commande déclarée : l'env et les secrets y vivent…
  [ "$(appels_git_dans "$CLONE_DONNEES")" = "$(printf '%s\n' "git -C $CLONE_DONNEES status --porcelain" \
    "git -C $CLONE_DONNEES fetch origin principal" \
    "git -C $CLONE_DONNEES merge --ff-only origin/principal")" ]
  appels_de docker | grep -Fx 'docker pull -q ghcr.io/edouardzemb/veille-emploi:main'
  # …puis, rien à déployer : l'adresse publique répond (corps lu, code HTTP vérifié), signal ok
  [ "$(nombre_d_appels deployer.sh)" -eq 0 ]
  appels_de curl | grep -Fx 'curl -sS -m 10 -w \n%{http_code} https://veille-emploi-staging.exemple.org/sante'
  [ "$(signaux)" = "$(signal 'main en service') $HC" ]
  aucune_ligne 'hc.example' "$APPELS"
  # le staging ne contrôle pas les unités
  [ "$(nombre_d_appels installer-unites.sh)" -eq 0 ]
}

@test "deploie_quand_l_empreinte_change" {
  preparer staging
  echo "$AUTRE main" >"$ETAT/deploye"
  sonder staging
  [ "$status" -eq 0 ]
  [ "$(appels_de deployer.sh)" = "deployer.sh staging $EMPREINTE main" ]
  # le déploiement tourne sous le verrou de la sonde, qu'il ne reprend pas
  grep -Fx 'pendant le déploiement : verrou tenu=oui VEILLE_EMPLOI_VERROU_TENU=1' "$APPELS"
  # le signal est l'affaire de deployer.sh, pas de la sonde
  [ -z "$(signaux)" ]
  [ "$(nombre_d_appels installer-unites.sh)" -eq 0 ]
}

# Le ménage des images, lancé par le vrai deployer.sh sous le verrou que la sonde tient : il hérite de
# VEILLE_EMPLOI_VERROU_TENU=1 et ne l'attend pas. Sans cela il attendrait son propre verrou
# (VEILLE_EMPLOI_VERROU_ATTENTE secondes, 600 par défaut) et abandonnerait.
@test "la_sonde_deploie_puis_fait_le_menage_sans_attendre" {
  cp "$DEPOT/deploiement/deployer.sh" "$CLONE/deploiement/deployer.sh"
  installer_doubles curl
  preparer staging
  echo "$AUTRE main" >"$ETAT/deploye"
  poser_donnees staging
  poser_image 9 2026-01-01T10:00:00Z "" "$(empreinte_de 9)"
  poser_image 6 2026-10-06T10:00:00Z "" "$(empreinte_de 6)"
  poser_image 7 2026-10-07T10:00:00Z "" "$(empreinte_de 7)"
  poser_image 8 2026-10-08T10:00:00Z "" "$(empreinte_de 8)"
  export VEILLE_EMPLOI_VERROU_ATTENTE=1 VEILLE_EMPLOI_SANTE_DELAI=0
  sonder staging
  [ "$status" -eq 0 ]
  [ "$(cat "$ETAT/deploye")" = "$EMPREINTE main -" ]
  appels_de docker | grep -Fx 'docker image ls --all --no-trunc --quiet'
  [[ "$output" != *"toujours pris"* ]]
  aucune_ligne "^$(image_de 9)\|" "$BATS_TEST_TMPDIR/images"
}

@test "renvoie_le_code_du_deploiement" {
  preparer staging
  export DOUBLE_DEPLOYER_CODE=1
  sonder staging
  [ "$status" -eq 1 ]
  [ "$(appels_de deployer.sh)" = "deployer.sh staging $EMPREINTE main" ]
}

@test "refuse_un_clone_modifie" {
  preparer staging
  export DOUBLE_GIT_STATUS=' M deploiement/compose.yml'
  sonder staging
  [ "$status" -eq 1 ]
  [ "$(signaux)" = "$(signal 'clone modifié') $HC/fail" ]
  [[ "$output" == *"deploiement/compose.yml"* ]]
  [ "$(appels_de git)" = "git -C $CLONE status --porcelain" ]
  [ "$(nombre_d_appels docker)" -eq 0 ]
  [ "$(nombre_d_appels deployer.sh)" -eq 0 ]
}

@test "alerte_si_l_etat_du_clone_est_illisible" {
  preparer staging
  export DOUBLE_GIT_ECHEC=status
  sonder staging
  [ "$status" -eq 1 ]
  [ "$(signaux)" = "$(signal 'git status impossible') $HC/fail" ]
  [ "$(nombre_d_appels docker)" -eq 0 ]
}

@test "alerte_si_main_ne_peut_pas_avancer" {
  preparer staging
  local sous_commande
  for sous_commande in fetch merge; do
    : >"$APPELS"
    export DOUBLE_GIT_ECHEC="$sous_commande"
    sonder staging
    [ "$status" -eq 1 ]
    [[ "$(signaux)" == "$(signal "git $sous_commande")"*" $HC/fail" ]]
    [ "$(nombre_d_appels docker)" -eq 0 ]
    [ "$(nombre_d_appels deployer.sh)" -eq 0 ]
  done
}

# En staging, :main doit toujours exister : une image introuvable est une panne, pas une attente.
@test "staging_alerte_si_l_image_est_introuvable" {
  preparer staging
  export DOUBLE_DOCKER_PULL_ERREUR='manifest for ghcr.io/edouardzemb/veille-emploi:main not found: manifest unknown: manifest unknown'
  sonder staging
  [ "$status" -eq 1 ]
  [[ "$(signaux)" == *" $HC/fail" ]]
  [ "$(nombre_d_appels deployer.sh)" -eq 0 ]
}

@test "alerte_si_l_adresse_publique_ne_repond_pas" {
  preparer staging
  echo "$EMPREINTE main" >"$ETAT/deploye"
  export DOUBLE_CURL_PUBLIC_CODE=28
  sonder staging
  [ "$status" -eq 1 ]
  [ "$(signaux)" = "$(signal 'adresse publique injoignable') $HC/fail" ]
  [ "$(nombre_d_appels deployer.sh)" -eq 0 ]
}

# Le corps de l'adresse publique doit être celui de CET environnement : des routes du tunnel
# inversées (staging et prod) donneraient deux adresses « ok », et celle du staging servirait les
# données réelles de la prod.
@test "alerte_si_l_adresse_publique_repond_pour_un_autre_environnement" {
  export DOUBLE_GIT_ETIQUETTES=v0.2.0
  local cas nom_env annonce version
  for cas in 'staging prod' 'prod staging'; do
    nom_env="${cas% *}"
    annonce="${cas#* }"
    version=main
    [ "$nom_env" = staging ] || version=0.2.0
    : >"$APPELS"
    preparer "$nom_env"
    echo "$EMPREINTE $version" >"$ETAT/deploye"
    export DOUBLE_CURL_PUBLIC_ENV="$annonce"
    sonder "$nom_env"
    [ "$status" -eq 1 ]
    [[ "$(signaux)" == "$(signal 'adresse publique')"*" $HC/fail" ]]
    [[ "$output" == *"environnement"*"$annonce"* ]]
    [ "$(nombre_d_appels deployer.sh)" -eq 0 ]
  done
}

# Une redirection (Cloudflare Access, par exemple) n'est pas une santé : `curl -f` la laisserait
# passer. Pas plus qu'une erreur HTTP, une page HTML, un corps vide ou un statut qui n'est pas ok.
@test "alerte_si_l_adresse_publique_redirige_ou_ne_repond_pas_une_sante_ok" {
  preparer staging
  echo "$EMPREINTE main" >"$ETAT/deploye"
  local cas
  for cas in 'DOUBLE_CURL_PUBLIC_HTTP=302' 'DOUBLE_CURL_PUBLIC_HTTP=503' \
    'DOUBLE_CURL_PUBLIC_CORPS=<html>Connexion requise</html>' 'DOUBLE_CURL_PUBLIC_CORPS=' \
    'DOUBLE_CURL_PUBLIC_CORPS={"statut":"degrade","environnement":"staging"}'; do
    unset DOUBLE_CURL_PUBLIC_HTTP DOUBLE_CURL_PUBLIC_CORPS
    export "${cas?}"
    : >"$APPELS"
    sonder staging
    [ "$status" -eq 1 ]
    [[ "$(signaux)" == "$(signal 'adresse publique')"*" $HC/fail" ]]
    [ "$(nombre_d_appels deployer.sh)" -eq 0 ]
  done
  # un 3xx dit son code, même avec le corps d'une santé ok
  unset DOUBLE_CURL_PUBLIC_CORPS
  export DOUBLE_CURL_PUBLIC_HTTP=302
  sonder staging
  [[ "$output" == *"302"* ]]
}

# Retour arrière abouti : la version déployée (AUTRE) est décrite par compose.env et répond.
@test "ne_reessaie_pas_une_version_en_echec" {
  preparer staging
  en_service staging "$AUTRE" main
  echo "$EMPREINTE" >"$ETAT/echec"
  sonder staging
  [ "$status" -eq 0 ]
  [[ "$output" == *"couple en échec, attente d'un nouveau"* ]]
  [ "$(nombre_d_appels deployer.sh)" -eq 0 ]
  # l'état laissé par le retour arrière est contrôlé sur place : santé locale de la version déployée
  appels_de docker | grep -Fx "docker image inspect -f {{index .Config.Labels \"org.opencontainers.image.revision\"}} $AUTRE"
  appels_de curl | grep -Fx 'curl -fsS -m 5 http://127.0.0.1:4311/sante'
  # aucun signal : ni ok (le silence alertera), ni échec (déjà signalé)
  [ -z "$(signaux)" ]
  # aucune relance
  [ "$(appels_de docker | grep -c ' up ')" -eq 0 ]
}

# Retour arrière manuel (deployer.sh <env> --retour) qui n'a pas pu quitter la version en service :
# elle est marquée en échec ET déployée. Elle n'est pas « en service » au sens du signal ok : le
# silence tient l'incident ouvert, comme pour toute version en échec.
@test "une_version_en_service_marquee_en_echec_n_envoie_pas_de_signal_ok" {
  preparer staging
  en_service staging "$EMPREINTE" main
  echo "$EMPREINTE" >"$ETAT/echec"
  sonder staging
  [ "$status" -eq 0 ]
  [[ "$output" == *"couple en échec, attente d'un nouveau"* ]]
  [ -z "$(signaux)" ]
  [ "$(nombre_d_appels deployer.sh)" -eq 0 ]
  # l'adresse publique n'est pas contrôlée : l'état local seul compte tant que la version est en échec
  [ -z "$(appels_de curl | grep -F 'exemple.org' || true)" ]
}

# Retour arrière coupé avant la fin : la version en échec (EMPREINTE) tourne encore. La sonde
# alerte à chaque passage, sans rien relancer elle-même.
@test "alerte_si_le_retour_arriere_n_a_pas_abouti" {
  preparer staging
  local cas
  for cas in compose_env_et_service_encore_nouveaux compose_env_encore_nouveau \
    la_nouvelle_repond_encore rien_ne_repond; do
    : >"$APPELS"
    en_service staging "$AUTRE" main
    echo "$EMPREINTE" >"$ETAT/echec"
    case "$cas" in
      compose_env_et_service_encore_nouveaux)
        # coupure avant la restauration de compose.env, la nouvelle version en service
        contenu_compose_env staging "$EMPREINTE" main >"$ETAT/compose.env"
        cp "$ETAT/compose.env" "$BATS_TEST_TMPDIR/en-service.env"
        ;;
      compose_env_encore_nouveau)
        # le `up` de la nouvelle a échoué sans toucher à l'ancienne, qui répond ; coupure avant la
        # restauration : `dc` viserait la nouvelle
        contenu_compose_env staging "$EMPREINTE" main >"$ETAT/compose.env"
        ;;
      la_nouvelle_repond_encore)
        # compose.env restauré, mais la nouvelle version répond toujours (même version « main » :
        # seule la révision la trahit)
        contenu_compose_env staging "$EMPREINTE" main >"$BATS_TEST_TMPDIR/en-service.env"
        ;;
      rien_ne_repond) rm "$BATS_TEST_TMPDIR/en-service.env" ;;
    esac
    sonder staging
    [ "$status" -eq 1 ]
    [[ "$(signaux)" == "$(signal 'retour arrière incomplet : ')"*" $HC/fail" ]]
    [[ "$output" == *"Relancer deployer.sh à la main"* ]]
    [ "$(nombre_d_appels deployer.sh)" -eq 0 ]
    [ "$(appels_de docker | grep -c -E ' (up|exec|stop) ')" -eq 0 ]
  done
}

# Premier déploiement en échec : rien ne doit tourner. Sans compose.env, aucun `up` n'a eu lieu ;
# avec, `dc ps -q app` doit être vide.
@test "premier_deploiement_en_echec_attend_en_silence_si_rien_ne_tourne" {
  preparer staging
  echo "$EMPREINTE" >"$ETAT/echec"
  sonder staging
  [ "$status" -eq 0 ]
  [[ "$output" == *"couple en échec, attente d'un nouveau"* ]]
  [ "$(appels_de docker | grep -c ' ps ')" -eq 0 ]
  [ -z "$(signaux)" ]

  : >"$APPELS"
  contenu_compose_env staging "$EMPREINTE" main >"$ETAT/compose.env"
  sonder staging
  [ "$status" -eq 0 ]
  appels_de docker | grep -E ' ps -q app$'
  [ -z "$(signaux)" ]
}

@test "premier_deploiement_en_echec_alerte_si_la_version_tourne_encore" {
  preparer staging
  echo "$EMPREINTE" >"$ETAT/echec"
  contenu_compose_env staging "$EMPREINTE" main >"$ETAT/compose.env"
  cp "$ETAT/compose.env" "$BATS_TEST_TMPDIR/en-service.env"
  sonder staging
  [ "$status" -eq 1 ]
  [ "$(signaux)" = "$(signal 'retour arrière incomplet : la version en échec tourne encore (aucune version déployée avant elle)') $HC/fail" ]
  [ "$(appels_de docker | grep -c -E ' (up|exec|stop) ')" -eq 0 ]
}

@test "alerte_si_l_empreinte_est_illisible" {
  preparer staging
  local empreinte
  for empreinte in '<no value>' 'ghcr.io/autre/image@sha256:'"$(printf 'a%.0s' {1..64})"; do
    : >"$APPELS"
    export DOUBLE_DOCKER_EMPREINTE="$empreinte"
    sonder staging
    [ "$status" -eq 1 ]
    [[ "$(signaux)" == *" $HC/fail" ]]
    [ "$(nombre_d_appels deployer.sh)" -eq 0 ]
  done
}

# --- prod ------------------------------------------------------------------------------------

@test "prod_choisit_la_plus_haute_version_semver" {
  preparer prod
  export DOUBLE_GIT_ETIQUETTES='v0.9.0 v0.10.0 v0.2.1 v1.0.0-rc1'
  sonder prod
  [ "$status" -eq 0 ]
  appels_de git | grep -Fx "git -C $CLONE fetch --prune --prune-tags --tags origin"
  appels_de docker | grep -Fx 'docker pull -q ghcr.io/edouardzemb/veille-emploi:0.10.0'
  [ "$(appels_de deployer.sh)" = "deployer.sh prod $EMPREINTE 0.10.0" ]
  # le clone passe sur l'étiquette, les unités sont réinstallées (la variable y refuse « non » aux
  # heures des sauvegardes), puis on déploie
  [ "$(appels_de installer-unites.sh)" = installer-unites.sh ]
  grep -Fx 'installation des unités : VEILLE_EMPLOI_AVANT_DEPLOIEMENT=1' "$APPELS"
  [ "$(ligne_de "git -C $CLONE checkout --quiet v0.10.0")" -lt "$(ligne_de installer-unites.sh)" ]
  [ "$(ligne_de installer-unites.sh)" -lt "$(ligne_de 'deployer.sh prod')" ]
  # la prod ne suit pas main
  [ "$(appels_de git | grep -c merge)" -eq 0 ]
}

# Le double trie les étiquettes avec `sort -rV` : on vérifie ici que c'est l'ordre du vrai git.
@test "le_double_de_git_trie_les_etiquettes_comme_git" {
  local vrai_git origine etiquette
  vrai_git="$(PATH="${PATH//"$DOUBLES":/}" command -v git)"
  origine="$BATS_TEST_TMPDIR/depot-reel"
  "$vrai_git" init -q "$origine"
  "$vrai_git" -C "$origine" -c user.name=t -c user.email=t@example.invalid commit -q --allow-empty -m t
  for etiquette in v0.9.0 v0.10.0 v0.2.1 v1.0.0-rc1 v1.0.0; do
    "$vrai_git" -C "$origine" tag "$etiquette"
  done
  export DOUBLE_GIT_ETIQUETTES='v0.9.0 v0.10.0 v0.2.1 v1.0.0-rc1 v1.0.0'
  [ "$(git tag --list --sort=-v:refname)" = "$("$vrai_git" -C "$origine" tag --list --sort=-v:refname)" ]
}

# Une étiquette posée à tort puis supprimée sur GitHub doit disparaître du clone de prod : `git
# fetch --tags` seul ne retire jamais une étiquette locale, et la sonde, qui vise la plus haute,
# redéploierait la version fautive après un retour arrière.
@test "prod_ne_vise_plus_une_etiquette_supprimee_sur_l_origine" {
  preparer prod
  export DOUBLE_GIT_ETIQUETTES='v0.1.0 v0.2.0' DOUBLE_GIT_ORIGINE='v0.1.0 v0.2.0'
  sonder prod
  [ "$status" -eq 0 ]
  appels_de docker | grep -Fx 'docker pull -q ghcr.io/edouardzemb/veille-emploi:0.2.0'
  [ "$(appels_de deployer.sh)" = "deployer.sh prod $EMPREINTE 0.2.0" ]

  # v0.2.0 est supprimée sur l'origine : la sonde suivante vise v0.1.0
  : >"$APPELS"
  export DOUBLE_GIT_ORIGINE='v0.1.0'
  sonder prod
  [ "$status" -eq 0 ]
  appels_de docker | grep -Fx 'docker pull -q ghcr.io/edouardzemb/veille-emploi:0.1.0'
  [ "$(appels_de docker | grep -c ':0.2.0')" -eq 0 ]
  [ "$(appels_de deployer.sh)" = "deployer.sh prod $EMPREINTE 0.1.0" ]
  appels_de git | grep -Fx "git -C $CLONE checkout --quiet v0.1.0"
}

# Le double de git ne prouve rien sur git : on rejoue ici, avec le vrai git, les arguments que la
# sonde lui passe pour `fetch`.
@test "le_fetch_de_la_sonde_retire_d_un_vrai_clone_une_etiquette_supprimee_sur_l_origine" {
  local vrai_git origine copie arguments
  vrai_git="$(PATH="${PATH//"$DOUBLES":/}" command -v git)"
  origine="$BATS_TEST_TMPDIR/origine"
  copie="$BATS_TEST_TMPDIR/copie"
  "$vrai_git" init -q "$origine"
  "$vrai_git" -C "$origine" -c user.name=t -c user.email=t@example.invalid commit -q --allow-empty -m t
  "$vrai_git" -C "$origine" tag v0.1.0
  "$vrai_git" -C "$origine" tag v0.2.0
  "$vrai_git" clone -q "$origine" "$copie"
  "$vrai_git" -C "$copie" tag --list | grep -Fx v0.2.0
  "$vrai_git" -C "$origine" tag -d v0.2.0 >/dev/null

  # la forme d'avant, `fetch --tags origin`, laisse l'étiquette supprimée dans le clone…
  "$vrai_git" -C "$copie" fetch -q --tags origin
  "$vrai_git" -C "$copie" tag --list | grep -Fx v0.2.0

  # …les arguments que la sonde passe aujourd'hui à fetch la retirent
  preparer prod
  export DOUBLE_GIT_ETIQUETTES='v0.1.0'
  sonder prod
  arguments="$(appels_de git | sed -n 's/^git -C [^ ]* fetch //p' | head -n 1)"
  [ -n "$arguments" ]
  # shellcheck disable=SC2086  # les arguments notés par le double, séparés par des espaces
  "$vrai_git" -C "$copie" fetch -q $arguments
  [ "$("$vrai_git" -C "$copie" tag --list)" = v0.1.0 ]
}

@test "prod_sans_etiquette_n_a_rien_a_deployer" {
  preparer prod
  export DOUBLE_GIT_ETIQUETTES='v1.0.0-rc1 essai'
  sonder prod
  [ "$status" -eq 0 ]
  [[ "$output" == *"aucune version"* ]]
  [ "$(signaux)" = "$(signal 'aucune version') $HC" ]
  [ "$(nombre_d_appels docker)" -eq 0 ]
  [ "$(nombre_d_appels deployer.sh)" -eq 0 ]
}

@test "prod_attend_une_image_pas_encore_publiee" {
  preparer prod
  export DOUBLE_GIT_ETIQUETTES='v0.1.0 v0.2.0'
  echo "ghcr.io/edouardzemb/veille-emploi@sha256:$(printf 'c%.0s' {1..64}) 0.1.0" >"$ETAT/deploye"
  local erreur
  # un cas par forme acceptée, puis le message complet de docker
  for erreur in 'manifest unknown' \
    'manifest for ghcr.io/edouardzemb/veille-emploi:0.2.0 not found' \
    'ghcr.io/edouardzemb/veille-emploi:0.2.0: not found' \
    'manifest for ghcr.io/edouardzemb/veille-emploi:0.2.0 not found: manifest unknown: manifest unknown'; do
    : >"$APPELS"
    export DOUBLE_DOCKER_PULL_ERREUR="$erreur"
    sonder prod
    [ "$status" -eq 0 ]
    [[ "$output" == *"image pas encore publiée"* ]]
    [ "$(nombre_d_appels deployer.sh)" -eq 0 ]
    [ "$(appels_de git | grep -c checkout)" -eq 0 ]
    # aucun signal : c'est son absence qui alertera si l'attente dure
    [ "$(nombre_d_appels curl)" -eq 0 ]
  done
}

# Un « not found » qui ne vient pas du registre est une panne, pas une attente.
@test "prod_alerte_sur_un_not_found_qui_n_est_pas_une_etiquette_absente" {
  preparer prod
  export DOUBLE_GIT_ETIQUETTES=v0.2.0
  local erreur
  # shellcheck disable=SC2016  # « $PATH » littéral : c'est le message de docker
  for erreur in \
    'error getting credentials - err: exec: "docker-credential-desktop": executable file not found in $PATH, out: ``' \
    'repository ghcr.io/edouardzemb/veille-emploi not found: name unknown: repository name not known to registry' \
    'manifest for ghcr.io/edouardzemb/veille-emploi:0.1.0 not found'; do
    : >"$APPELS"
    export DOUBLE_DOCKER_PULL_ERREUR="$erreur"
    sonder prod
    [ "$status" -eq 1 ]
    [ "$(signaux)" = "$(signal 'docker pull ghcr.io/edouardzemb/veille-emploi:0.2.0 impossible') $HC/fail" ]
    [ "$(nombre_d_appels deployer.sh)" -eq 0 ]
  done
}

# Sans docker du tout (« docker: command not found ») : alerte.
@test "prod_alerte_si_docker_est_introuvable" {
  preparer prod
  export DOUBLE_GIT_ETIQUETTES=v0.2.0
  rm "$DOUBLES/docker"
  sonder prod
  [ "$status" -eq 1 ]
  [[ "$output" == *"docker: command not found"* ]]
  [ "$(signaux)" = "$(signal 'docker pull ghcr.io/edouardzemb/veille-emploi:0.2.0 impossible') $HC/fail" ]
  [ "$(nombre_d_appels deployer.sh)" -eq 0 ]
}

@test "alerte_si_ghcr_refuse_l_acces" {
  preparer prod
  export DOUBLE_GIT_ETIQUETTES=v0.2.0
  export DOUBLE_DOCKER_PULL_ERREUR='Head "https://ghcr.io/v2/edouardzemb/veille-emploi/manifests/0.2.0": unauthorized'
  sonder prod
  [ "$status" -eq 1 ]
  [[ "$(signaux)" == "$(signal 'docker pull ghcr.io/edouardzemb/veille-emploi:0.2.0 impossible')"*" $HC/fail" ]]
  [[ "$output" == *unauthorized* ]]
  [ "$(nombre_d_appels deployer.sh)" -eq 0 ]
}

@test "prod_en_regime_stable_controle_les_unites_et_l_adresse_publique" {
  preparer prod
  export DOUBLE_GIT_ETIQUETTES='v0.1.0 v0.2.0'
  echo "$EMPREINTE 0.2.0" >"$ETAT/deploye"
  sonder prod
  [ "$status" -eq 0 ]
  [ "$(appels_de installer-unites.sh)" = 'installer-unites.sh --verifier' ]
  appels_de curl | grep -Fx 'curl -sS -m 10 -w \n%{http_code} https://veille-emploi.exemple.org/sante'
  [ "$(signaux)" = "$(signal '0.2.0 en service') $HC" ]
  [ "$(appels_de git | grep -c checkout)" -eq 0 ]
  [ "$(nombre_d_appels deployer.sh)" -eq 0 ]
}

@test "prod_signale_des_unites_divergentes" {
  preparer prod
  export DOUBLE_GIT_ETIQUETTES=v0.2.0
  echo "$EMPREINTE 0.2.0" >"$ETAT/deploye"
  export DOUBLE_UNITES_ECART=1
  sonder prod
  [ "$status" -eq 1 ]
  [ "$(appels_de installer-unites.sh)" = 'installer-unites.sh --verifier' ]
  [ "$(signaux)" = "$(signal 'unités divergentes') $HC/fail" ]
  [ "$(nombre_d_appels deployer.sh)" -eq 0 ]
}

@test "prod_alerte_si_le_passage_a_l_etiquette_echoue" {
  preparer prod
  export DOUBLE_GIT_ETIQUETTES=v0.2.0
  local cas
  for cas in checkout installation; do
    : >"$APPELS"
    if [ "$cas" = checkout ]; then
      export DOUBLE_GIT_ECHEC=checkout
    else
      unset DOUBLE_GIT_ECHEC
      export DOUBLE_UNITES_INSTALLATION_CODE=1
    fi
    sonder prod
    [ "$status" -eq 1 ]
    [[ "$(signaux)" == *" $HC/fail" ]]
    [ "$(nombre_d_appels deployer.sh)" -eq 0 ]
  done
}

@test "prod_alerte_si_les_etiquettes_sont_illisibles" {
  preparer prod
  local sous_commande
  for sous_commande in fetch tag; do
    : >"$APPELS"
    export DOUBLE_GIT_ECHEC="$sous_commande"
    sonder prod
    [ "$status" -eq 1 ]
    [[ "$(signaux)" == *" $HC/fail" ]]
    [ "$(nombre_d_appels docker)" -eq 0 ]
  done
}

# --- le couple visé : l'image et le commit de données -----------------------------------------
#
# Un projet qui déclare VERIFIER_CONFIG ou VERIFIER_CONTENU déploie un couple, une image et un
# commit de données ; un projet qui n'en déclare aucune, l'image et « - ». L'état compare des
# couples : deploye (premier et troisième champs), echec (premier et deuxième), « - » quand le
# commit manque.

# Au premier passage après la mise à jour, un état d'avant la v0.7.0
# (deploye à deux champs, echec à un champ) se lit comme un couple sans données : un projet sans
# données ne se redéploie pas, et rien n'est signalé en échec.
@test "sonder : un état d'avant la v0.7.0 ne redéploie pas un projet sans données" {
  local nom_env version
  export DOUBLE_GIT_ETIQUETTES=v0.2.0
  # une version des données existe : sans commande déclarée, elle ne fait pas un nouveau couple
  pousser_des_donnees contenu/page.md
  etiqueter_les_donnees donnees-2026.11.03.1
  for nom_env in staging prod; do
    version=main
    [ "$nom_env" = staging ] || version=0.2.0
    preparer "$nom_env"
    # en service, avec un état d'avant la v0.7.0 ; une autre image en échec
    : >"$APPELS"
    en_service "$nom_env" "$EMPREINTE" "$version"
    [ "$(cat "$ETAT/deploye")" = "$EMPREINTE $version" ]
    echo "$AUTRE" >"$ETAT/echec"
    sonder "$nom_env"
    [ "$status" -eq 0 ]
    [ "$(signaux)" = "$(signal "$version en service") $HC" ]
    [ "$(nombre_d_appels deployer.sh)" -eq 0 ]
    [ "$(appels_de git | grep -c checkout)" -eq 0 ]

    # l'image visée marquée en échec avant la v0.7.0 : attente en silence, sans relance
    : >"$APPELS"
    en_service "$nom_env" "$AUTRE" "$version"
    echo "$EMPREINTE" >"$ETAT/echec"
    sonder "$nom_env"
    [ "$status" -eq 0 ]
    [[ "$output" == *"couple en échec, attente d'un nouveau : $version ($EMPREINTE, données -)"* ]]
    [ -z "$(signaux)" ]
    [ "$(nombre_d_appels deployer.sh)" -eq 0 ]
  done
}

# M-0003, amendé : la santé d'une application qui déclare VERIFIER_CONFIG dit d'où vient sa
# configuration, par l'adresse publique aussi : montee en prod, exemple en staging, qui ne monte
# jamais /config. Sans VERIFIER_CONFIG, le champ n'est pas lu.
@test "sonder : l'adresse publique doit dire montee en prod" {
  local commit corps
  export DOUBLE_GIT_ETIQUETTES=v0.2.0
  avec_donnees VERIFIER_CONFIG
  pousser_des_donnees config/profil.yml
  etiqueter_les_donnees donnees-2026.11.03.1
  # la même tête pour la branche des données (staging) et pour l'étiquette (prod)
  commit="$COMMIT"
  preparer prod
  echo "$EMPREINTE 0.2.0 $commit" >"$ETAT/deploye"
  for corps in '{"statut":"ok","environnement":"prod"}' \
    '{"statut":"ok","environnement":"prod","configuration":"exemple"}'; do
    : >"$APPELS"
    export DOUBLE_CURL_PUBLIC_CORPS="$corps"
    sonder prod
    [ "$status" -eq 1 ]
    [ "$(signaux)" = "$(signal 'adresse publique : réponse inattendue (attendu : statut ok, environnement prod, configuration montee)') $HC/fail" ]
    [ "$(nombre_d_appels deployer.sh)" -eq 0 ]
  done
  : >"$APPELS"
  export DOUBLE_CURL_PUBLIC_CORPS='{"statut":"ok","environnement":"prod","configuration":"montee"}'
  sonder prod
  [ "$status" -eq 0 ]
  [ "$(signaux)" = "$(signal "0.2.0 en service, données ${commit:0:12}") $HC" ]

  # staging : exemple
  preparer staging
  echo "$EMPREINTE main $commit" >"$ETAT/deploye"
  : >"$APPELS"
  export DOUBLE_CURL_PUBLIC_CORPS='{"statut":"ok","environnement":"staging","configuration":"montee"}'
  sonder staging
  [ "$status" -eq 1 ]
  [ "$(signaux)" = "$(signal 'adresse publique : réponse inattendue (attendu : statut ok, environnement staging, configuration exemple)') $HC/fail" ]
  : >"$APPELS"
  export DOUBLE_CURL_PUBLIC_CORPS='{"statut":"ok","environnement":"staging","configuration":"exemple"}'
  sonder staging
  [ "$status" -eq 0 ]
  [ "$(signaux)" = "$(signal "main en service, données ${commit:0:12}") $HC" ]

  # VERIFIER_CONTENU seule : le champ configuration n'est pas lu
  sed -i 's/^VERIFIER_CONFIG=/VERIFIER_CONTENU=/' "$CLONE/deploiement/projet.env"
  unset DOUBLE_CURL_PUBLIC_CORPS
  : >"$APPELS"
  sonder staging
  [ "$status" -eq 0 ]
  [ "$(signaux)" = "$(signal "main en service, données ${commit:0:12}") $HC" ]
}

# La prod vise la plus haute étiquette de données de la forme
# donnees-AAAA.MM.JJ.n (n sans zéro en tête), en ordre de version : .10 passe devant .9. Toute autre
# forme est ignorée, même plus haute dans ce tri, et une étiquette retirée de l'origine disparaît du
# clone (--prune-tags), comme pour le code. Le vrai git, sur un vrai clone.
@test "sonder : la plus haute étiquette de données, et elle seule" {
  local neuf dix
  preparer prod
  export DOUBLE_GIT_ETIQUETTES=v0.2.0
  avec_donnees VERIFIER_CONTENU

  # 1. des formes refusées seulement : aucune version des données, on attend, sans tirer l'image
  pousser_des_donnees contenu/page.md
  etiqueter_les_donnees donnees-2026.11.3.1 donnees-2026.11.03.0 v1.2.3
  sonder prod
  [ "$status" -eq 0 ]
  [[ "$output" == *"aucune version des données"* ]]
  [ "$(signaux)" = "$(signal 'aucune version des données') $HC" ]
  appels_de git | grep -Fx "git -C $CLONE_DONNEES fetch --prune --prune-tags --tags origin"
  [ "$(nombre_d_appels docker)" -eq 0 ]
  [ "$(nombre_d_appels deployer.sh)" -eq 0 ]

  # 2. .9 puis .10, chacune sur son commit : .10 passe devant .9, et devant donnees-2026.11.3.1, que
  # git range plus haut
  pousser_des_donnees contenu/page.md contenu/neuf.md
  neuf="$COMMIT"
  etiqueter_les_donnees donnees-2026.11.03.9
  pousser_des_donnees contenu/page.md contenu/dix.md
  dix="$COMMIT"
  etiqueter_les_donnees donnees-2026.11.03.10
  : >"$APPELS"
  sonder prod
  [ "$status" -eq 0 ]
  [ "$(git_donnees tag --list 'donnees-*' --sort=-v:refname | head -n 1)" = donnees-2026.11.3.1 ]
  [ "$(appels_de deployer.sh)" = "deployer.sh prod $EMPREINTE 0.2.0 --commit-donnees $dix" ]
  # le clone des données passe sur l'étiquette avant les unités et le déploiement, pas avant
  [ "$(ligne_de "git -C $CLONE_DONNEES checkout --quiet donnees-2026.11.03.10")" -lt "$(ligne_de installer-unites.sh)" ]
  [ "$(ligne_de installer-unites.sh)" -lt "$(ligne_de 'deployer.sh prod')" ]
  [ "$(git_donnees rev-parse HEAD)" = "$dix" ]

  # 3. .10 retirée de l'origine : elle disparaît du clone, et la sonde vise .9
  "$GIT_REEL" -C "$ORIGINE_DONNEES" tag -d donnees-2026.11.03.10 >/dev/null
  : >"$APPELS"
  sonder prod
  [ "$status" -eq 0 ]
  [ -z "$(git_donnees tag --list donnees-2026.11.03.10)" ]
  [ "$(appels_de deployer.sh)" = "deployer.sh prod $EMPREINTE 0.2.0 --commit-donnees $neuf" ]
}

# Le couple change quand seules les données changent : la même image se redéploie avec le nouveau
# commit, la tête de la branche des données en staging, la nouvelle étiquette en prod.
@test "sonder : un nouveau commit de données redéploie la même image" {
  local premier
  avec_donnees VERIFIER_CONTENU

  # staging : le couple en service, puis la branche des données avance
  preparer staging
  premier="$(git_donnees rev-parse HEAD)"
  echo "$EMPREINTE main $premier" >"$ETAT/deploye"
  sonder staging
  [ "$status" -eq 0 ]
  [ "$(signaux)" = "$(signal "main en service, données ${premier:0:12}") $HC" ]
  [ "$(nombre_d_appels deployer.sh)" -eq 0 ]
  pousser_des_donnees contenu/page.md
  : >"$APPELS"
  sonder staging
  [ "$status" -eq 0 ]
  [ "$(appels_git_dans "$CLONE_DONNEES")" = "$(printf '%s\n' "git -C $CLONE_DONNEES status --porcelain" \
    "git -C $CLONE_DONNEES fetch origin principal" \
    "git -C $CLONE_DONNEES merge --ff-only origin/principal" \
    "git -C $CLONE_DONNEES rev-parse HEAD")" ]
  [ "$(appels_de deployer.sh)" = "deployer.sh staging $EMPREINTE main --commit-donnees $COMMIT" ]

  # prod : le couple en service, puis une nouvelle étiquette des données
  preparer prod
  export DOUBLE_GIT_ETIQUETTES=v0.2.0
  etiqueter_les_donnees donnees-2026.11.03.1
  premier="$COMMIT"
  echo "$EMPREINTE 0.2.0 $premier" >"$ETAT/deploye"
  : >"$APPELS"
  sonder prod
  [ "$status" -eq 0 ]
  [ "$(signaux)" = "$(signal "0.2.0 en service, données ${premier:0:12}") $HC" ]
  [ "$(appels_de git | grep -c checkout)" -eq 0 ]
  pousser_des_donnees contenu/page.md contenu/autre.md
  etiqueter_les_donnees donnees-2026.11.04.1
  : >"$APPELS"
  sonder prod
  [ "$status" -eq 0 ]
  [ "$(appels_de deployer.sh)" = "deployer.sh prod $EMPREINTE 0.2.0 --commit-donnees $COMMIT" ]
  # le code reste sur son étiquette, les données passent sur la leur, puis les unités et le déploiement
  [ "$(ligne_de "git -C $CLONE checkout --quiet v0.2.0")" -lt "$(ligne_de installer-unites.sh)" ]
  [ "$(ligne_de "git -C $CLONE_DONNEES checkout --quiet donnees-2026.11.04.1")" -lt "$(ligne_de installer-unites.sh)" ]
  [ "$(ligne_de installer-unites.sh)" -lt "$(ligne_de 'deployer.sh prod')" ]
}

# Un couple en échec attend un autre couple : d'autres données pour la même image, une autre image
# pour les mêmes données, ou la même image avec des données là où son échec n'en avait pas.
@test "sonder : un couple en échec ne se rejoue pas, un autre se tente" {
  local premier
  avec_donnees VERIFIER_CONTENU
  preparer staging
  premier="$(git_donnees rev-parse HEAD)"
  en_service staging "$AUTRE" main
  echo "$AUTRE main $premier" >"$ETAT/deploye"
  echo "$EMPREINTE $premier" >"$ETAT/echec"
  sonder staging
  [ "$status" -eq 0 ]
  [[ "$output" == *"couple en échec, attente d'un nouveau : main ($EMPREINTE, données $premier)"* ]]
  [ -z "$(signaux)" ]
  [ "$(nombre_d_appels deployer.sh)" -eq 0 ]

  # la même image, d'autres données
  pousser_des_donnees contenu/page.md
  : >"$APPELS"
  sonder staging
  [ "$status" -eq 0 ]
  [ "$(appels_de deployer.sh)" = "deployer.sh staging $EMPREINTE main --commit-donnees $COMMIT" ]

  # les mêmes données, une autre image en échec ; puis l'image visée en échec sans données
  local echec
  for echec in "$AUTRE $COMMIT" "$EMPREINTE -" "$EMPREINTE"; do
    echo "$echec" >"$ETAT/echec"
    : >"$APPELS"
    sonder staging
    [ "$status" -eq 0 ]
    [ "$(appels_de deployer.sh)" = "deployer.sh staging $EMPREINTE main --commit-donnees $COMMIT" ]
  done
}

# Deux dépôts : l'env et les secrets vivent dans le clone des données de l'environnement. Avant tout
# déploiement, qu'un projet déclare une commande ou non, il doit exister, être propre et se mettre à
# jour (staging : sa branche, VEILLE_EMPLOI_BRANCHE_DONNEES, sans défaut ; prod : ses étiquettes) ;
# sinon, anomalie. Absent, il n'a ni env ni secrets : le signal ne peut pas partir, le code le dit.
@test "sonder : clone des données absent, modifié, ou en retard" {
  local nom_env cas valeur
  export DOUBLE_GIT_ETIQUETTES=v0.2.0
  for nom_env in staging prod; do
    preparer "$nom_env"
  done

  # absent : rien n'est tenté
  mv "$CLONE_DONNEES" "$BATS_TEST_TMPDIR/donnees-ailleurs"
  for nom_env in staging prod; do
    : >"$APPELS"
    sonder "$nom_env"
    [ "$status" -eq 1 ]
    [[ "$output" == *"clone des données absent : $CLONE_DONNEES"* ]]
    [[ "$output" == *"anomalie : clone des données absent"* ]]
    [ ! -s "$APPELS" ]
  done
  mv "$BATS_TEST_TMPDIR/donnees-ailleurs" "$CLONE_DONNEES"

  # modifié : un fichier suivi changé, ou un fichier de trop ; ni mise à jour, ni image
  for cas in 'staging env/staging.env' 'prod de-trop'; do
    nom_env="${cas% *}"
    preparer "$nom_env"
    : >"$APPELS"
    echo '# modifié' >>"$CLONE_DONNEES/${cas#* }"
    sonder "$nom_env"
    [ "$status" -eq 1 ]
    [ "$(signaux)" = "$(signal 'clone des données modifié') $HC/fail" ]
    [[ "$output" == *"${cas#* }"* ]]
    [ "$(appels_git_dans "$CLONE_DONNEES")" = "git -C $CLONE_DONNEES status --porcelain" ]
    [ "$(nombre_d_appels docker)" -eq 0 ]
    [ "$(nombre_d_appels deployer.sh)" -eq 0 ]
    git_donnees checkout -q -- .
    rm -f "$CLONE_DONNEES/de-trop"
  done

  # en retard : il se met à jour avant le déploiement, sans commande déclarée aussi
  pousser_des_donnees contenu/page.md
  preparer staging
  : >"$APPELS"
  sonder staging
  [ "$status" -eq 0 ]
  [ "$(git_donnees rev-parse HEAD)" = "$COMMIT" ]
  [ "$(appels_de deployer.sh)" = "deployer.sh staging $EMPREINTE main" ]
  # en prod, le commit « - », mais le clone passe sur l'étiquette avant le déploiement : l'env et
  # les secrets suivent la série
  etiqueter_les_donnees donnees-2026.11.03.1
  preparer prod
  : >"$APPELS"
  sonder prod
  [ "$status" -eq 0 ]
  [ "$(appels_de deployer.sh)" = "deployer.sh prod $EMPREINTE 0.2.0" ]
  [ "$(ligne_de "git -C $CLONE_DONNEES checkout --quiet donnees-2026.11.03.1")" -lt "$(ligne_de 'deployer.sh prod')" ]

  # mise à jour impossible : l'origine injoignable
  git_donnees remote set-url origin "$BATS_TEST_TMPDIR/origine-absente.git"
  for nom_env in staging prod; do
    preparer "$nom_env"
    : >"$APPELS"
    sonder "$nom_env"
    [ "$status" -eq 1 ]
    [ "$(signaux)" = "$(signal 'mise à jour du clone des données impossible') $HC/fail" ]
    [ "$(nombre_d_appels docker)" -eq 0 ]
    [ "$(nombre_d_appels deployer.sh)" -eq 0 ]
  done
  git_donnees remote set-url origin "$ORIGINE_DONNEES"

  # mise à jour impossible : une histoire qui a divergé de l'origine
  git_donnees checkout -q principal
  git_donnees commit -q --allow-empty -m "un commit local, absent de l'origine"
  pousser_des_donnees contenu/autre.md
  preparer staging
  : >"$APPELS"
  sonder staging
  [ "$status" -eq 1 ]
  [ "$(signaux)" = "$(signal 'mise à jour du clone des données impossible') $HC/fail" ]
  [ "$(nombre_d_appels deployer.sh)" -eq 0 ]

  # staging sans VEILLE_EMPLOI_BRANCHE_DONNEES, ou avec une valeur qui serait une option : aucune
  # branche par défaut, rien n'est tiré
  for valeur in '' '--upload-pack=touch'; do
    git_donnees reset -q --hard origin/principal
    sed -i "s/^VEILLE_EMPLOI_BRANCHE_DONNEES=.*/VEILLE_EMPLOI_BRANCHE_DONNEES=$valeur/" "$CLONE_DONNEES/env/staging.env"
    git_donnees commit -q -am "une branche des données à essayer"
    : >"$APPELS"
    sonder staging
    [ "$status" -eq 1 ]
    [ "$(signaux)" = "$(signal 'VEILLE_EMPLOI_BRANCHE_DONNEES absente ou invalide') $HC/fail" ]
    [ "$(appels_git_dans "$CLONE_DONNEES")" = "git -C $CLONE_DONNEES status --porcelain" ]
  done
}

# En prod, une version du code qui déclare une commande attend sa première
# étiquette de données. Pendant l'attente, la sonde contrôle le couple en service comme quand rien
# n'est nouveau (l'état après échec, les unités, l'adresse publique), puis dit l'attente par un
# signal ok. Le champ configuration exigé suit le couple en service, pas la déclaration visée :
# montee si son compose.env monte /config, rien sinon. Sans couple en service : « aucune version des
# données », comme avant.
@test "sonder : en prod, la version qui attend ses données contrôle le couple en service" {
  local commit
  commit="$(printf 'c%.0s' {1..40})"
  preparer prod
  export DOUBLE_GIT_ETIQUETTES='v0.1.0 v0.2.0'
  arbre_vise VERIFIER_CONFIG

  # aucun couple en service : l'attente seule
  sonder prod
  [ "$status" -eq 0 ]
  [ "$(signaux)" = "$(signal 'aucune version des données') $HC" ]
  [ "$(nombre_d_appels installer-unites.sh)" -eq 0 ]
  [ -z "$(appels_de curl | grep -F 'exemple.org' || true)" ]
  [ "$(nombre_d_appels docker)" -eq 0 ]

  # 0.1.0 en service, sans /config : ses unités et son adresse publique, sans le champ
  # configuration, que la version visée exigerait
  en_service prod "$AUTRE" 0.1.0
  : >"$APPELS"
  sonder prod
  [ "$status" -eq 0 ]
  [ "$(signaux)" = "$(signal '0.2.0 attend une version des données') $HC" ]
  [ "$(appels_de installer-unites.sh)" = 'installer-unites.sh --verifier' ]
  appels_de curl | grep -Fx 'curl -sS -m 10 -w \n%{http_code} https://veille-emploi.exemple.org/sante'
  [ "$(nombre_d_appels docker)" -eq 0 ]
  [ "$(appels_de git | grep -c checkout)" -eq 0 ]
  [ "$(nombre_d_appels deployer.sh)" -eq 0 ]

  # une panne du couple en service fait échouer la sonde : sa santé publique, ses unités
  export DOUBLE_CURL_PUBLIC_HTTP=503
  : >"$APPELS"
  sonder prod
  [ "$status" -eq 1 ]
  [ "$(signaux)" = "$(signal 'adresse publique : réponse HTTP 503 au lieu de 200') $HC/fail" ]
  [ "$(nombre_d_appels deployer.sh)" -eq 0 ]
  unset DOUBLE_CURL_PUBLIC_HTTP
  export DOUBLE_UNITES_ECART=1
  : >"$APPELS"
  sonder prod
  [ "$status" -eq 1 ]
  [ "$(signaux)" = "$(signal 'unités divergentes') $HC/fail" ]
  unset DOUBLE_UNITES_ECART

  # le couple en service monte /config : montee est exigé
  echo "$AUTRE 0.1.0 $commit" >"$ETAT/deploye"
  echo "VEILLE_EMPLOI_CONFIG=$ETAT/instantanes/$commit/config" >>"$ETAT/compose.env"
  : >"$APPELS"
  sonder prod
  [ "$status" -eq 1 ]
  [ "$(signaux)" = "$(signal 'adresse publique : réponse inattendue (attendu : statut ok, environnement prod, configuration montee)') $HC/fail" ]
  export DOUBLE_CURL_PUBLIC_CORPS='{"statut":"ok","environnement":"prod","configuration":"montee"}'
  : >"$APPELS"
  sonder prod
  [ "$status" -eq 0 ]
  [ "$(signaux)" = "$(signal '0.2.0 attend une version des données') $HC" ]

  # le couple en service est aussi en échec (un retour arrière manuel qui n'a pas pu le quitter) :
  # l'état après échec, contrôlé sur place, et le silence, comme quand rien n'est nouveau
  echo "$AUTRE $commit" >"$ETAT/echec"
  : >"$APPELS"
  sonder prod
  [ "$status" -eq 0 ]
  [[ "$output" == *"couple en échec, attente d'un nouveau : 0.1.0 ($AUTRE, données $commit)"* ]]
  appels_de curl | grep -Fx 'curl -fsS -m 5 http://127.0.0.1:4310/sante'
  [ -z "$(signaux)" ]
  [ "$(nombre_d_appels deployer.sh)" -eq 0 ]
}

# Pendant l'attente des données, un deploye présent mais illisible n'est pas
# « aucune version des données » : rien ne dirait plus ce qui sert la prod. Anomalie, code 1, sans
# signal ok, et rien n'est contrôlé ni déployé. Hors de l'attente, deployer.sh s'en charge.
@test "sonder : pendant l'attente des données, un deploye illisible est une anomalie" {
  local contenu
  preparer prod
  export DOUBLE_GIT_ETIQUETTES='v0.1.0 v0.2.0'
  arbre_vise VERIFIER_CONFIG
  en_service prod "$AUTRE" 0.1.0
  # une image d'une autre forme, un commit invalide, un fichier vide
  for contenu in 'pas-une-image 0.1.0' "$AUTRE 0.1.0 pas-un-commit" ''; do
    printf '%s\n' "$contenu" >"$ETAT/deploye"
    : >"$APPELS"
    sonder prod
    [ "$status" -eq 1 ]
    [[ "$output" == *"$ETAT/deploye illisible : "* ]]
    [ "$(signaux)" = "$(signal "$ETAT/deploye illisible") $HC/fail" ]
    [ "$(nombre_d_appels installer-unites.sh)" -eq 0 ]
    [ -z "$(appels_de curl | grep -F 'exemple.org' || true)" ]
    [ "$(nombre_d_appels docker)" -eq 0 ]
    [ "$(nombre_d_appels deployer.sh)" -eq 0 ]
  done
  # présent, mais pas un fichier : illisible aussi, au journal comme au signal, jamais absent
  rm "$ETAT/deploye"
  mkdir "$ETAT/deploye"
  : >"$APPELS"
  sonder prod
  [ "$status" -eq 1 ]
  [[ "$output" == *"$ETAT/deploye illisible : ce n'est pas un fichier"* ]]
  [[ "$output" != *"aucune version déployée"* ]]
  [ "$(signaux)" = "$(signal "$ETAT/deploye illisible") $HC/fail" ]
  [ "$(nombre_d_appels deployer.sh)" -eq 0 ]
}

# La déclaration qui fixe le commit du couple visé est celle de la version du
# code visée, jamais celle qu'on quitte. En prod, le clone du code ne passe sur l'étiquette qu'avant
# deployer.sh : la sonde lit le projet.env de l'étiquette sans checkout (le double de git le sert
# depuis DOUBLE_GIT_ARBRE). Une version qui commence ou cesse de déclarer une commande se déploie
# donc au premier passage, avec ou sans --commit-donnees, au lieu d'un refus de deployer.sh (64).
@test "sonder : en prod, une étiquette qui se met à déclarer VERIFIER_CONFIG se déploie au premier passage" {
  local commit
  preparer prod
  export DOUBLE_GIT_ETIQUETTES='v0.1.0 v0.2.0'
  # 0.1.0 en service, sans commande : la copie de travail du clone est encore la sienne
  en_service prod "$AUTRE" 0.1.0
  arbre_vise VERIFIER_CONFIG
  # sans étiquette de données, la version qui se met à déclarer attend, sans rien tirer ni changer ;
  # 0.1.0, en service, est contrôlée pendant ce temps (voir plus haut)
  sonder prod
  [ "$status" -eq 0 ]
  [ "$(signaux)" = "$(signal '0.2.0 attend une version des données') $HC" ]
  [ "$(nombre_d_appels docker)" -eq 0 ]
  [ "$(appels_de git | grep -c checkout)" -eq 0 ]
  [ "$(nombre_d_appels deployer.sh)" -eq 0 ]
  pousser_des_donnees config/profil.yml
  etiqueter_les_donnees donnees-2026.11.03.1
  commit="$COMMIT"
  : >"$APPELS"
  sonder prod
  [ "$status" -eq 0 ]
  [ "$(appels_de deployer.sh)" = "deployer.sh prod $EMPREINTE 0.2.0 --commit-donnees $commit" ]
  # le projet.env de l'étiquette, lu avant tout checkout
  [ "$(ligne_de "git -C $CLONE show v0.2.0:deploiement/projet.env")" -lt "$(ligne_de "git -C $CLONE checkout --quiet v0.2.0")" ]

  # le couple ainsi visé, en échec : il attend ; déployé : en service, configuration montee
  echo "$EMPREINTE $commit" >"$ETAT/echec"
  : >"$APPELS"
  sonder prod
  [ "$status" -eq 0 ]
  [[ "$output" == *"couple en échec, attente d'un nouveau : 0.2.0 ($EMPREINTE, données $commit)"* ]]
  [ "$(nombre_d_appels deployer.sh)" -eq 0 ]
  rm "$ETAT/echec"
  echo "$EMPREINTE 0.2.0 $commit" >"$ETAT/deploye"
  export DOUBLE_CURL_PUBLIC_CORPS='{"statut":"ok","environnement":"prod","configuration":"montee"}'
  : >"$APPELS"
  sonder prod
  [ "$status" -eq 0 ]
  [ "$(signaux)" = "$(signal "0.2.0 en service, données ${commit:0:12}") $HC" ]
  [ "$(nombre_d_appels deployer.sh)" -eq 0 ]
}

@test "sonder : en prod, une étiquette qui cesse de déclarer se déploie au premier passage, sans l'option" {
  preparer prod
  export DOUBLE_GIT_ETIQUETTES='v0.1.0 v0.2.0'
  # la copie de travail, celle de 0.1.0 en service, déclare VERIFIER_CONTENU ; l'étiquette, rien
  avec_donnees VERIFIER_CONTENU
  pousser_des_donnees contenu/page.md
  etiqueter_les_donnees donnees-2026.11.03.1
  echo "$AUTRE 0.1.0 $COMMIT" >"$ETAT/deploye"
  arbre_vise
  sonder prod
  [ "$status" -eq 0 ]
  [ "$(appels_de deployer.sh)" = "deployer.sh prod $EMPREINTE 0.2.0" ]
  # aucun commit de données cherché
  [ "$(appels_de git | grep -cF '^{commit}')" -eq 0 ]
  # le clone des données passe quand même sur l'étiquette de données : l'env et les secrets
  appels_de git | grep -Fx "git -C $CLONE_DONNEES checkout --quiet donnees-2026.11.03.1"

  # un projet.env absent de l'étiquette ne déclare rien, comme un clone sans projet.env : git ls-tree
  # le dit, par une sortie vide et le code 0
  rm "$DOUBLE_GIT_ARBRE/deploiement/projet.env"
  : >"$APPELS"
  sonder prod
  [ "$status" -eq 0 ]
  [ "$(appels_de deployer.sh)" = "deployer.sh prod $EMPREINTE 0.2.0" ]
  appels_de git | grep -Fx "git -C $CLONE ls-tree --name-only v0.2.0 -- deploiement/projet.env"
  [ "$(appels_de git | grep -c ' show ')" -eq 0 ]

  # illisible (git ls-tree ou git show en échec, ou une ligne invalide) : anomalie, rien n'est
  # tiré. Une erreur de git n'est pas une absence : son stderr va au journal.
  local cas
  for cas in ls-tree show ligne; do
    arbre_vise
    unset DOUBLE_GIT_ECHEC
    if [ "$cas" = ligne ]; then
      echo 'VERIFIER_CONTENU=outil;verifier' >>"$DOUBLE_GIT_ARBRE/deploiement/projet.env"
    else
      export DOUBLE_GIT_ECHEC="$cas"
    fi
    : >"$APPELS"
    sonder prod
    [ "$status" -eq 1 ]
    [ "$(signaux)" = "$(signal 'deploiement/projet.env de v0.2.0 illisible') $HC/fail" ]
    [ "$cas" = ligne ] || [[ "$output" == *"fatal: échec simulé de git $cas"* ]]
    [ "$(nombre_d_appels docker)" -eq 0 ]
    [ "$(nombre_d_appels deployer.sh)" -eq 0 ]
  done
}

# Le projet.env de l'étiquette se lit dans un fichier temporaire : il ne reste pas derrière la sonde,
# ni à la fin d'un passage, ni quand un SIGTERM (systemd qui arrête l'unité) tombe pendant sa lecture.
@test "sonder : le projet.env de l'étiquette ne laisse aucun fichier temporaire" {
  preparer prod
  export DOUBLE_GIT_ETIQUETTES=v0.2.0
  arbre_vise
  export TMPDIR="$BATS_TEST_TMPDIR/temporaires"
  mkdir -p "$TMPDIR"
  sonder prod
  [ "$status" -eq 0 ]
  appels_de git | grep -Fx "git -C $CLONE show v0.2.0:deploiement/projet.env"
  [ -z "$(find "$TMPDIR" -mindepth 1)" ]

  # le double de git envoie SIGTERM à la sonde pendant `git show`
  export DOUBLE_GIT_TERM=show
  : >"$APPELS"
  sonder prod
  [ "$status" -eq 143 ]
  [ "$(nombre_d_appels docker)" -eq 0 ]
  [ -z "$(find "$TMPDIR" -mindepth 1)" ]
}

# --- verrou, réécriture, secrets, usage ------------------------------------------------------

@test "sort_sans_rien_faire_si_le_verrou_est_pris" {
  preparer staging
  exec 8>"$ETAT/verrou"
  flock -n 8
  sonder staging
  exec 8>&-
  [ "$status" -eq 0 ]
  [[ "$output" == *occupé* ]]
  # ni git, ni docker, ni signal
  [ ! -s "$APPELS" ]
}

# Un `git merge` ou un `git checkout` peut réécrire sonder.sh pendant qu'il tourne. Le double le
# réécrit sur place, avec un contenu plus long : un script qui relirait son fichier après coup
# exécuterait ce contenu (`exit 97`).
@test "sonde_termine_meme_si_git_reecrit_sonder_pendant_l_execution" {
  local nom_env version
  for nom_env in staging prod; do
    # shellcheck disable=SC2153  # DEPOT vient d'aide.bash
    cp "$DEPOT/deploiement/sonder.sh" "$CLONE/deploiement/sonder.sh"
    : >"$APPELS"
    preparer "$nom_env"
    export DOUBLE_GIT_ETIQUETTES=v0.3.0
    export DOUBLE_GIT_REECRIRE="$CLONE/deploiement/sonder.sh"
    version=main
    [ "$nom_env" = staging ] || version=0.3.0
    sonder "$nom_env"
    [ "$status" -eq 0 ]
    grep -q 'réécrit pendant la sonde' "$CLONE/deploiement/sonder.sh"
    [ "$(appels_de deployer.sh)" = "deployer.sh $nom_env $EMPREINTE $version" ]
  done
}

@test "sonde_ne_laisse_aucun_secret_dans_une_trace" {
  preparer staging
  echo "$EMPREINTE main" >"$ETAT/deploye"
  run bash -x "$CLONE/deploiement/sonder.sh" staging
  [ "$status" -eq 0 ]
  [ "$(signaux)" = "$(signal 'main en service') $HC" ]
  [[ "$output" != *jeton-staging-7* ]]
  [[ "$output" != *hc.example* ]]
}

@test "alerte_si_le_canal_est_inconnu" {
  preparer staging
  sed -i 's/^VEILLE_EMPLOI_CANAL=.*/VEILLE_EMPLOI_CANAL=branche/' "$CLONE_DONNEES/$SOUS_ENV/staging.env"
  sonder staging
  [ "$status" -eq 1 ]
  [[ "$(signaux)" == "$(signal 'canal inconnu')"*" $HC/fail" ]]
  [ "$(appels_de git)" = "git -C $CLONE status --porcelain" ]
  [ "$(nombre_d_appels docker)" -eq 0 ]
}

# La garde de lib.sh (refuser_image_heritee) : une image, une version ou un montage posés dans
# l'environnement prendraient le pas sur compose.env dans `dc`. La sonde refuse avant d'agir.
@test "sonder : refuse une image ou un montage hérités" {
  local variable
  preparer staging
  for variable in VEILLE_EMPLOI_IMAGE VEILLE_EMPLOI_VERSION VEILLE_EMPLOI_CONFIG VEILLE_EMPLOI_CONTENU; do
    : >"$APPELS"
    run env "$variable=$CLONE_DONNEES/valeur-heritee" bash "$CLONE/deploiement/sonder.sh" staging
    [ "$status" -eq 1 ]
    [[ "$output" == *"$variable est posée dans l'environnement"* ]]
    [ ! -s "$APPELS" ]
  done
}

@test "sonde_refuse_un_usage_invalide" {
  sonder
  [ "$status" -eq 64 ]
  sonder essai
  [ "$status" -eq 64 ]
  sonder prod staging
  [ "$status" -eq 64 ]
  [ ! -s "$APPELS" ]
}

# --- bout en bout, avec le vrai deployer.sh --------------------------------------------------

@test "sonde_et_deploiement_de_bout_en_bout" {
  cp "$DEPOT/deploiement/deployer.sh" "$CLONE/deploiement/deployer.sh"
  export VEILLE_EMPLOI_SANTE_DELAI=0
  preparer staging

  # 1. premier passage : déploiement de :main
  sonder staging
  [ "$status" -eq 0 ]
  [ "$(cat "$ETAT/deploye")" = "$EMPREINTE main -" ]
  [ "$(signaux)" = "$(signal 'déployé main') $HC" ]

  # 2. passage suivant : rien à faire, l'adresse publique répond
  : >"$APPELS"
  sonder staging
  [ "$status" -eq 0 ]
  [ "$(appels_de docker | grep -c ' up ')" -eq 0 ]
  [ "$(signaux)" = "$(signal 'main en service') $HC" ]

  # 3. une nouvelle image de main : instantané, puis déploiement
  poser_donnees staging
  : >"$APPELS"
  export DOUBLE_DOCKER_EMPREINTE="$AUTRE"
  sonder staging
  [ "$status" -eq 0 ]
  [ "$(appels_de docker | grep -c ' exec -T app ')" -eq 1 ]
  [ "$(cat "$ETAT/deploye")" = "$AUTRE main -" ]
  [ "$(cat "$ETAT/precedent")" = "$EMPREINTE main -" ]
}

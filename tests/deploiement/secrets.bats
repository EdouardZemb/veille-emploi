#!/usr/bin/env bats
# Secrets : `charger_secrets` de lib.sh (déchiffrement vers l'environnement, sans fichier restant)
# et `valeur_sure`, la règle des valeurs. Les fichiers chiffrés se refont sur le poste
# (scripts/modele/secrets.ps1) : les tests fabriquent les leurs par preparer_secrets_de_test.
#
# Les valeurs de test sont factices. Aucun test n'écrit une valeur sur sa sortie : une valeur
# n'est lue que pour être comparée, et les échecs bats n'affichent que le texte des commandes.

# Chaque test tourne dans son propre processus : les `export` d'un test ne fuient pas dans les autres
# (SC2030, SC2031). Le code de avec_lib et les valeurs de test sont entre apostrophes pour ne pas
# se développer ici (SC2016).
# shellcheck disable=SC2016,SC2030,SC2031

load aide

setup() {
  preparer_environnement
}

# valeur_sure_de <valeur> : le code de valeur_sure pour cette valeur, passée en argument.
valeur_sure_de() {
  run bash -c 'set -euo pipefail; . "$CLONE/deploiement/lib.sh"; valeur_sure "$1"' valeur_sure "$1"
}

@test "charger_secrets_expose_la_variable" {
  preparer_secrets_de_test prod JETON=jeton-factice-1 "HC_SONDE=https://hc.example/ping/abc?x=1"

  avec_lib 'charger_env prod
    charger_secrets prod
    [ "$JETON" = "jeton-factice-1" ]
    [ "$HC_SONDE" = "https://hc.example/ping/abc?x=1" ]
    # exportées : les processus enfants (docker compose) les voient
    [ "$(env | grep -c "^JETON=")" -eq 1 ]
    echo exposee'
  [ "$status" -eq 0 ]
  [ "$output" = "exposee" ]
}

@test "charger_secrets_ne_laisse_aucun_fichier" {
  preparer_secrets_de_test prod JETON=jeton-factice-3
  creer_double_transparent shred
  # /dev/shm est introuvable pour ce test : repli sur $TMPDIR
  export VEILLE_EMPLOI_SHM="$BATS_TEST_TMPDIR/shm-absent"
  mkdir -p "$TMPDIR/secrets"
  export TMPDIR="$TMPDIR/secrets"

  avec_lib 'charger_env prod; charger_secrets prod; [ -n "$JETON" ]'
  [ "$status" -eq 0 ]
  [ -z "$(ls -A "$TMPDIR")" ]
  # le fichier a bien existé là, et il a été détruit par `shred -u`
  [ "$(nombre_d_appels shred)" -eq 1 ]
  [[ "$(appels_de shred)" == "shred -u $TMPDIR/"* ]]
}

@test "charger_secrets_utilise_dev_shm_par_defaut" {
  [ -d /dev/shm ] && [ -w /dev/shm ] || sauter "pas de /dev/shm"
  preparer_secrets_de_test prod JETON=jeton-factice-4
  creer_double_transparent shred
  avant="$(ls -A /dev/shm)"

  avec_lib 'charger_env prod; charger_secrets prod; [ -n "$JETON" ]'
  [ "$status" -eq 0 ]
  [ "$(ls -A /dev/shm)" = "$avant" ]
  [[ "$(appels_de shred)" == "shred -u /dev/shm/"* ]]
  # le TMPDIR de test, lui, n'a servi à rien
  [ -z "$(ls -A "$TMPDIR")" ]
}

@test "charger_secrets_nettoie_aussi_apres_un_dechiffrement_impossible" {
  preparer_secrets_de_test prod JETON=jeton-factice-5
  # une identité qui n'est pas destinataire du fichier
  age-keygen -o "$BATS_TEST_TMPDIR/etrangere.txt" 2>/dev/null
  export SOPS_AGE_KEY_FILE="$BATS_TEST_TMPDIR/etrangere.txt"
  creer_double_transparent shred
  export VEILLE_EMPLOI_SHM="$BATS_TEST_TMPDIR/shm-absent"

  avec_lib 'charger_env prod; charger_secrets prod'
  [ "$status" -eq 1 ]
  [[ "$output" == *"déchiffrement impossible pour prod"* ]]
  [[ "$output" != *jeton-factice-5* ]]
  [ -z "$(ls -A "$TMPDIR")" ]
}

@test "charger_secrets_echoue_sans_fichier" {
  preparer_cles_de_test
  avec_lib 'charger_env prod; charger_secrets prod'
  [ "$status" -eq 3 ]
  [[ "$output" == *"secrets absents pour prod"* ]]
}

@test "env_inconnu_refuse" {
  preparer_cles_de_test
  avec_lib 'charger_env recette'
  [ "$status" -eq 64 ]
  avec_lib 'charger_env local'
  [ "$status" -eq 64 ]
  avec_lib 'charger_env ""'
  [ "$status" -eq 64 ]
  avec_lib 'charger_secrets recette'
  [ "$status" -eq 64 ]
}

# Une valeur que le shell interpréterait (espace, guillemet, `$`, `;`…) casserait le chargement,
# voire exécuterait du code : valeur_sure la refuse, et secrets.ps1 applique la même règle à
# l'écriture, sur le poste.
@test "valeur_que_le_shell_interpreterait_refusee" {
  local valeur
  for valeur in '' 'a b' 'a"b' "a'b" 'a$b' 'a`b' 'a;b' 'a&b' 'a|b' 'a<b' 'a>b' 'a(b' 'a)b' 'a\b' \
    'a:~/b' $'a\tb' $'a\rb' $'a\nb' $'a\x01b'; do
    valeur_sure_de "$valeur"
    [ "$status" -eq 1 ]
  done
}

# Ce que le shell laisse intact dans une affectation (pas de globbing, pas de développement
# d'accolades) reste accepté : jetons en base64, adresses avec paramètres.
@test "valeur_avec_symboles_inoffensifs_acceptee_puis_rechargee_a_l_identique" {
  valeur='Ab0+/=_-.:,@%#!*?[]{}^'
  valeur_sure_de "$valeur"
  [ "$status" -eq 0 ]
  preparer_secrets_de_test prod "JETON=$valeur"
  avec_lib 'charger_env prod; charger_secrets prod; [ "$JETON" = '"'$valeur'"' ] && echo identique'
  [ "$status" -eq 0 ]
  [ "$output" = "identique" ]
}

# --- Traces et fichier déchiffré --------------------------------------------------------------

# Sous `bash -x` ou `set -x` (diagnostic d'une unité systemd, par exemple), la trace va sur stderr,
# donc dans le journal : aucun secret ni aucune adresse de ping ne doit y passer, et la trace
# reprend ensuite pour le reste du script.
@test "charger_secrets_n_ecrit_aucun_secret_sous_bash_x" {
  preparer_secrets_de_test prod JETON=jeton-trace-1 HC_SONDE=https://hc.example/ping/uuid-trace-2
  creer_double curl
  run bash -x -c 'set -euo pipefail; . "$CLONE/deploiement/lib.sh"
    charger_env prod; charger_secrets prod; signaler HC_SONDE ok bonjour; : marqueur-de-trace'
  [ "$status" -eq 0 ]
  [[ "$output" != *jeton-trace-1* ]]
  [[ "$output" != *uuid-trace-2* ]]
  [[ "$output" == *"+ : marqueur-de-trace"* ]]
  # les secrets ont bien été chargés et l'adresse bien utilisée
  [[ "$(envois_supervision)" == *"/ping/uuid-trace-2" ]]

  run bash -c 'set -euxo pipefail; . "$CLONE/deploiement/lib.sh"
    charger_env prod; charger_secrets prod; : marqueur-de-trace'
  [ "$status" -eq 0 ]
  [[ "$output" != *jeton-trace-1* ]]
  [[ "$output" == *"+ : marqueur-de-trace"* ]]
}

@test "charger_secrets_n_active_pas_la_trace" {
  preparer_secrets_de_test prod JETON=jeton-trace-3
  avec_lib 'charger_env prod; charger_secrets prod; case "$-" in *x*) echo trace-active;; esac'
  [ "$status" -eq 0 ]
  [ -z "$output" ]
}

# Un fichier déchiffré que le shell interpréterait (écrit à la main avec `sops edit`, par exemple)
# ne doit ni s'exécuter, ni tuer le script avec le clair sur le disque : code 1, rien ne reste.
@test "charger_secrets_refuse_un_fichier_dechiffre_que_le_shell_interpreterait" {
  creer_double_transparent shred
  export VEILLE_EMPLOI_SHM="$BATS_TEST_TMPDIR/shm-absent"
  for ligne in 'JETON=ab$cd' "JETON=\$(touch $BATS_TEST_TMPDIR/injecte)" \
    'JETON="entre guillemets"' 'JETON=a b' 'jeton=minuscules'; do
    preparer_secrets_de_test prod "HC_SONDE=https://hc.example/ok" "$ligne"
    : >"$APPELS"
    avec_lib 'charger_env prod; charger_secrets prod; echo chargee'
    [ "$status" -eq 1 ]
    [[ "$output" == *"secrets illisibles pour prod"* ]]
    [[ "$output" == *"ligne 2"* ]]
    [[ "$output" != *chargee* ]]
    # ni la valeur ni la ligne ne sont répétées
    [[ "$output" != *entre* ]]
    [ -z "$(ls -A "$TMPDIR")" ]
    [ "$(nombre_d_appels shred)" -eq 1 ]
    [ ! -e "$BATS_TEST_TMPDIR/injecte" ]
  done
}

# Rien n'est exporté à moitié : la première ligne, valide, ne l'est pas non plus.
@test "charger_secrets_ne_charge_rien_si_une_ligne_est_invalide" {
  preparer_secrets_de_test prod "HC_SONDE=https://hc.example/ok" 'JETON=ab$cd'
  avec_lib 'trap '"'"'printf "%s" "${HC_SONDE:-vide}"'"'"' EXIT; charger_env prod; charger_secrets prod'
  [ "$status" -eq 1 ]
  [[ "$output" == *vide ]]
  [[ "$output" != *hc.example* ]]
}

@test "charger_secrets_ignore_les_commentaires" {
  preparer_secrets_de_test prod "# commentaire" "JETON=jeton-commente"
  avec_lib 'charger_env prod; charger_secrets prod; [ "$JETON" = "jeton-commente" ] && echo ok'
  [ "$status" -eq 0 ]
  [ "$output" = "ok" ]
}

# Un signal pendant le déchiffrement (arrêt par systemd, Ctrl-C) ne doit pas laisser le clair.
@test "charger_secrets_detruit_le_fichier_sur_signal" {
  preparer_secrets_de_test prod JETON=jeton-signal
  # faux sops : écrit un clair partiel puis attend, le temps d'envoyer le signal
  creer_double sops "touch '$BATS_TEST_TMPDIR/sops-demarre'; echo JETON=jeton-signal; exec sleep 30"
  export VEILLE_EMPLOI_SHM="$BATS_TEST_TMPDIR/shm-absent"
  mkdir -p "$TMPDIR/secrets"
  export TMPDIR="$TMPDIR/secrets"

  setsid bash -c '. "$CLONE/deploiement/lib.sh"; charger_env prod; charger_secrets prod' \
    >/dev/null 2>&1 &
  pid=$!
  for _ in $(seq 1 100); do
    [ -e "$BATS_TEST_TMPDIR/sops-demarre" ] && break
    sleep 0.1
  done
  [ -e "$BATS_TEST_TMPDIR/sops-demarre" ]
  [ -n "$(ls -A "$TMPDIR")" ]
  kill -TERM -- "-$pid"
  code=0
  wait "$pid" || code=$?
  [ "$code" -eq 143 ]
  [ -z "$(ls -A "$TMPDIR")" ]
}

@test "charger_secrets_rend_les_pieges_de_l_appelant" {
  preparer_secrets_de_test prod JETON=jeton-pieges
  avec_lib 'trap "echo piege-term" TERM
    charger_env prod; charger_secrets prod
    trap -p TERM
    trap -p INT HUP EXIT'
  [ "$status" -eq 0 ]
  [[ "$output" == *"trap -- 'echo piege-term' SIGTERM"* ]]
  [[ "$output" != *SIGINT* && "$output" != *SIGHUP* && "$output" != *EXIT* ]]
}

@test "charger_secrets_laisse_l_appelant_faire_son_menage_a_la_sortie" {
  preparer_secrets_de_test prod 'JETON=a b'
  avec_lib 'trap "echo menage-appelant" EXIT; charger_env prod; charger_secrets prod'
  [ "$status" -eq 1 ]
  [[ "$output" == *menage-appelant* ]]
}

#!/usr/bin/env bats
# lib.sh : charger_env, dc, projet.env, signaler, journal, santé, verrou, état déployé, vérification
# d'une copie. (charger_secrets : voir secrets.bats.)

# Chaque test tourne dans son propre processus : les `export` d'un test ne fuient pas dans les autres
# (SC2030, SC2031). Le code de avec_lib est entre apostrophes pour se développer dans le sous-shell
# qui l'exécute, pas ici (SC2016).
# shellcheck disable=SC2016,SC2030,SC2031

bats_require_minimum_version 1.5.0

load aide

setup() {
  preparer_environnement
}

teardown() {
  abandonner_le_verrou
  # les instantanés sont en lecture seule : bats doit pouvoir retirer le dossier du test
  chmod -R u+rwX "$BATS_TEST_TMPDIR" 2>/dev/null || true
}

# Le contrat de lib.sh est son en-tête : une fonction publique (sans « _ » devant) qui n'y figure
# pas est une fonction que personne ne sait exister.
@test "l_en_tete_de_lib_liste_toutes_les_fonctions_publiques" {
  local fonction absentes="" en_tete
  en_tete="$(sed -n '1,/^VEILLE_EMPLOI_CLONE=/p' "$CLONE/deploiement/lib.sh")"
  while read -r fonction; do
    grep -qE "^#   $fonction( |\$)" <<<"$en_tete" || absentes="$absentes $fonction"
  done < <(grep -oE '^[a-z][a-z_]*\(\)' "$CLONE/deploiement/lib.sh" | tr -d '()')
  [ -z "$absentes" ] || {
    echo "fonctions publiques absentes de l'en-tête :$absentes" >&2
    return 1
  }
}

@test "charger_env_exporte_les_chemins_de_prod" {
  avec_lib 'charger_env prod
    printf "%s\n" "$VEILLE_EMPLOI_CLONE" "$VEILLE_EMPLOI_ETAT" "$VEILLE_EMPLOI_DONNEES" "${VEILLE_EMPLOI_SAUVEGARDES-absente}" \
      "$DOCKER_CONFIG" "$VEILLE_EMPLOI_PROJET" "$VEILLE_EMPLOI_PORT" "$VEILLE_EMPLOI_URL_PUBLIQUE"
    # exportées, pour docker compose et les scripts enfants
    for v in VEILLE_EMPLOI_CLONE VEILLE_EMPLOI_ETAT VEILLE_EMPLOI_DONNEES VEILLE_EMPLOI_SAUVEGARDES DOCKER_CONFIG \
        VEILLE_EMPLOI_PROJET VEILLE_EMPLOI_PORT; do
      [ -n "$(printenv "$v")" ] || { echo "$v non exportée"; exit 1; }
    done'
  [ "$status" -eq 0 ]
  [ "${lines[0]}" = "$CLONE" ]
  [ "${lines[1]}" = "$VEILLE_EMPLOI_RACINE_ETAT/prod" ]
  [ "${lines[2]}" = "$VEILLE_EMPLOI_RACINE_DONNEES/prod/donnees" ]
  [ "${lines[3]}" = "$VEILLE_EMPLOI_RACINE_SAUVEGARDES" ]
  [ "${lines[4]}" = "$VEILLE_EMPLOI_DOCKER_CONFIG" ]
  [ "${lines[5]}" = "veille-emploi" ]
  [ "${lines[6]}" = "4310" ]
  [ "${lines[7]}" = "https://veille-emploi.exemple.org" ]
}

@test "charger_env_cree_les_dossiers" {
  avec_lib 'charger_env prod; charger_env staging'
  [ "$status" -eq 0 ]
  [ -d "$VEILLE_EMPLOI_RACINE_ETAT/prod" ]
  [ -d "$VEILLE_EMPLOI_RACINE_DONNEES/prod/donnees" ]
  [ -d "$VEILLE_EMPLOI_RACINE_SAUVEGARDES" ]
  [ -d "$VEILLE_EMPLOI_RACINE_ETAT/staging" ]
  [ -d "$VEILLE_EMPLOI_RACINE_DONNEES/staging/donnees" ]
  [ -d "$VEILLE_EMPLOI_RACINE_DONNEES/staging/sauvegardes" ]
}

@test "charger_env_place_les_sauvegardes_de_staging_sous_les_donnees" {
  avec_lib 'charger_env staging
    printf "%s\n" "${VEILLE_EMPLOI_SAUVEGARDES-absente}" "$VEILLE_EMPLOI_PROJET" "$VEILLE_EMPLOI_PORT" "$VEILLE_EMPLOI_ENV"'
  [ "$status" -eq 0 ]
  [ "${lines[0]}" = "$VEILLE_EMPLOI_RACINE_DONNEES/staging/sauvegardes" ]
  [ "${lines[1]}" = "veille-emploi-staging" ]
  [ "${lines[2]}" = "4311" ]
  [ "${lines[3]}" = "staging" ]
}

@test "charger_env_valeurs_par_defaut_du_serveur" {
  unset VEILLE_EMPLOI_RACINE_ETAT VEILLE_EMPLOI_RACINE_DONNEES VEILLE_EMPLOI_RACINE_SAUVEGARDES VEILLE_EMPLOI_DOCKER_CONFIG
  avec_lib 'charger_env prod
    printf "%s\n" "$VEILLE_EMPLOI_ETAT" "$VEILLE_EMPLOI_DONNEES" "${VEILLE_EMPLOI_SAUVEGARDES-absente}" "$DOCKER_CONFIG"
    charger_env staging
    printf "%s\n" "$VEILLE_EMPLOI_ETAT" "$VEILLE_EMPLOI_DONNEES" "${VEILLE_EMPLOI_SAUVEGARDES-absente}"'
  [ "$status" -eq 0 ]
  [ "${lines[0]}" = "$HOME/.local/state/veille-emploi/prod" ]
  [ "${lines[1]}" = "$HOME/.local/share/veille-emploi/prod/donnees" ]
  [ "${lines[2]}" = "$HOME/backups/veille-emploi" ]
  [ "${lines[3]}" = "$HOME/.config/serveur/docker" ]
  [ "${lines[4]}" = "$HOME/.local/state/veille-emploi/staging" ]
  [ "${lines[5]}" = "$HOME/.local/share/veille-emploi/staging/donnees" ]
  [ "${lines[6]}" = "$HOME/.local/share/veille-emploi/staging/sauvegardes" ]
}

# La configuration Docker du serveur est la sienne (identifiants GHCR posés par sa sonde) : un
# DOCKER_CONFIG hérité du shell ne doit pas s'y substituer.
@test "charger_env_ignore_un_docker_config_herite" {
  export DOCKER_CONFIG=/ailleurs
  avec_lib 'charger_env prod; printf "%s" "$DOCKER_CONFIG"'
  [ "$status" -eq 0 ]
  [ "$output" = "$VEILLE_EMPLOI_DOCKER_CONFIG" ]
}

# Migration 3 : la configuration Docker est celle du serveur, commune aux projets, et non plus
# un dossier propre au projet.
@test "docker_config_par_defaut_serveur" {
  unset VEILLE_EMPLOI_DOCKER_CONFIG
  export DOCKER_CONFIG=/ailleurs
  avec_lib 'charger_env prod; printf "%s" "$DOCKER_CONFIG"'
  [ "$status" -eq 0 ]
  [ "$output" = "$HOME/.config/serveur/docker" ]
  # et c'est elle que reçoit docker compose
  creer_double docker 'printf "%s\n" "$DOCKER_CONFIG" >"'"$BATS_TEST_TMPDIR"'/config-recue"'
  avec_lib 'charger_env prod; dc ps -q app'
  [ "$status" -eq 0 ]
  [ "$(cat "$BATS_TEST_TMPDIR/config-recue")" = "$HOME/.config/serveur/docker" ]
}

# Migration 2 : l'identité age est la clé du serveur, commune aux projets ; une identité posée par
# l'appelant (les tests, une restauration à la main) l'emporte.
@test "cle_sops_par_defaut_serveur" {
  avec_lib 'exporter_cle_sops; printf "%s" "$SOPS_AGE_KEY_FILE"'
  [ "$status" -eq 0 ]
  [ "$output" = "$HOME/.config/sops/age/serveur.txt" ]
  SOPS_AGE_KEY_FILE="$BATS_TEST_TMPDIR/autre.txt" avec_lib 'exporter_cle_sops; printf "%s" "$SOPS_AGE_KEY_FILE"'
  [ "$status" -eq 0 ]
  [ "$output" = "$BATS_TEST_TMPDIR/autre.txt" ]
  # le message d'un déchiffrement impossible nomme l'identité par défaut
  mkdir -p "$CLONE_DONNEES/$SOUS_SECRETS"
  echo 'pas du sops' >"$CLONE_DONNEES/$SOUS_SECRETS/prod.env.enc"
  creer_double sops 'exit 1'
  avec_lib 'charger_env prod; charger_secrets prod'
  [ "$status" -eq 1 ]
  [[ "$output" == *"(identité : $HOME/.config/sops/age/serveur.txt)"* ]]
}

@test "charger_env_prefixe_le_path_une_seule_fois" {
  avec_lib 'charger_env prod; charger_env staging; printf "%s" "$PATH"'
  [ "$status" -eq 0 ]
  [[ "$output" == "$HOME/.local/bin:"* ]]
  [[ "$output" != *"$HOME/.local/bin:$HOME/.local/bin"* ]]
}

@test "charger_env_refuse_un_fichier_d_environnement_incoherent" {
  sed -i 's/^VEILLE_EMPLOI_ENV=.*/VEILLE_EMPLOI_ENV=staging/' "$CLONE_DONNEES/$SOUS_ENV/prod.env"
  avec_lib 'charger_env prod'
  [ "$status" -eq 1 ]
  [[ "$output" == *"prod.env"* ]]
}

@test "charger_env_ne_degrade_pas_le_shell_appelant" {
  # le shell appelant n'avait pas `set -a` : il ne l'a toujours pas ensuite
  avec_lib 'charger_env prod; case "$-" in *a*) echo "set -a reste actif"; exit 1;; esac'
  [ "$status" -eq 0 ]
}

# Les chemins de l'instance, que lib.sh seul définit (M-0006, § 6) : charger_env lit l'env, et
# charger_secrets les secrets, dans le clone des données.
lire_les_chemins='charger_env prod; charger_secrets prod
  printf "%s\n" "$VEILLE_EMPLOI_CLONE_DONNEES" "$VEILLE_EMPLOI_PORT" "$JETON" "$SOUS_DOSSIER_ENV" "$SOUS_DOSSIER_SECRETS" \
    "$SOUS_DOSSIER_CLES" "$SOUS_DOSSIER_CONFIG" "$SOUS_DOSSIER_CONTENU"'

# Deux dépôts : le clone des données est ~/veille-emploi-donnees en prod et ~/veille-emploi-donnees-staging
# en staging (la surcharge VEILLE_EMPLOI_CLONE_DONNEES le déplace, pour les tests) ; deploiement/ du
# clone du code n'est jamais lu, même s'il porte un env et des secrets.
@test "chemins : deux dépôts" {
  mkdir -p "$CLONE/deploiement/env" "$CLONE/deploiement/secrets"
  sed 's/^VEILLE_EMPLOI_PORT=.*/VEILLE_EMPLOI_PORT=4399/' "$CLONE_DONNEES/env/prod.env" >"$CLONE/deploiement/env/prod.env"
  echo 'pas du sops' >"$CLONE/deploiement/secrets/prod.env.enc"
  preparer_secrets_de_test prod JETON=jeton-du-clone-des-donnees
  [ -f "$CLONE_DONNEES/secrets/prod.env.enc" ]
  avec_lib "$lire_les_chemins"
  [ "$status" -eq 0 ]
  [ "${lines[0]}" = "$CLONE_DONNEES" ]
  [ "${lines[1]}" = "4310" ]
  [ "${lines[2]}" = jeton-du-clone-des-donnees ]
  [ "${lines[*]:3}" = "env secrets cles config contenu" ]

  # sans la surcharge : le clone de chaque environnement, même appelé l'un après l'autre
  unset VEILLE_EMPLOI_CLONE_DONNEES
  cp -R "$CLONE_DONNEES" "$HOME/veille-emploi-donnees"
  cp -R "$CLONE_DONNEES" "$HOME/veille-emploi-donnees-staging"
  sed -i 's/^VEILLE_EMPLOI_PORT=.*/VEILLE_EMPLOI_PORT=4397/' "$HOME/veille-emploi-donnees/env/prod.env"
  sed -i 's/^VEILLE_EMPLOI_PORT=.*/VEILLE_EMPLOI_PORT=4398/' "$HOME/veille-emploi-donnees-staging/env/staging.env"
  avec_lib 'charger_env prod; printf "%s\n" "$VEILLE_EMPLOI_CLONE_DONNEES" "$VEILLE_EMPLOI_PORT"
    charger_env staging; printf "%s\n" "$VEILLE_EMPLOI_CLONE_DONNEES" "$VEILLE_EMPLOI_PORT"'
  [ "$status" -eq 0 ]
  [ "${lines[0]}" = "$HOME/veille-emploi-donnees" ]
  [ "${lines[1]}" = 4397 ]
  [ "${lines[2]}" = "$HOME/veille-emploi-donnees-staging" ]
  [ "${lines[3]}" = 4398 ]
  # le clone absent : charger_env s'arrête, et nomme le fichier qu'il attendait
  rm -rf "$HOME/veille-emploi-donnees"
  avec_lib 'charger_env prod'
  [ "$status" -eq 1 ]
  [[ "$output" == *"fichier d'environnement absent : $HOME/veille-emploi-donnees/env/prod.env"* ]]
  # poser_clone_donnees, la même règle, sans rien lire : la sonde dit ainsi un clone absent
  avec_lib 'poser_clone_donnees prod; echo "$VEILLE_EMPLOI_CLONE_DONNEES"
    poser_clone_donnees staging; echo "$VEILLE_EMPLOI_CLONE_DONNEES"'
  [ "$status" -eq 0 ]
  [ "${lines[0]}" = "$HOME/veille-emploi-donnees" ]
  [ "${lines[1]}" = "$HOME/veille-emploi-donnees-staging" ]
  avec_lib 'poser_clone_donnees essai'
  [ "$status" -eq 64 ]
}

# Deux fichiers compose : celui du modèle, puis les ajouts du projet, que compose fusionne.
@test "dc_passe_projet_fichier_compose_et_fichier_d_environnement" {
  creer_double docker
  avec_lib 'charger_env prod; dc ps -q app'
  [ "$status" -eq 0 ]
  [ "$(appels_de docker)" = "docker compose -p veille-emploi -f $CLONE/deploiement/compose.yml -f $CLONE/deploiement/compose.projet.yml --env-file $VEILLE_EMPLOI_RACINE_ETAT/prod/compose.env ps -q app" ]
  avec_lib 'charger_env staging; dc ps -q app'
  [ "$status" -eq 0 ]
  [ "$(appels_de docker | tail -n 1)" = "docker compose -p veille-emploi-staging -f $CLONE/deploiement/compose.yml -f $CLONE/deploiement/compose.projet.yml --env-file $VEILLE_EMPLOI_RACINE_ETAT/staging/compose.env ps -q app" ]
}

@test "dc_exige_charger_env" {
  creer_double docker
  run bash -c 'set -euo pipefail; unset VEILLE_EMPLOI_PROJET; . "$CLONE/deploiement/lib.sh"; dc ps'
  [ "$status" -ne 0 ]
  [ "$(nombre_d_appels docker)" -eq 0 ]
}

# Les montages de l'instantané (M-0006, § 5) ne sont décrits que pour ce que compose.env monte :
# compose.config.yml pour VEILLE_EMPLOI_CONFIG, compose.contenu.yml pour VEILLE_EMPLOI_CONTENU, après les
# fichiers du projet.
@test "dc : les fichiers de montage suivent compose.env" {
  creer_double docker
  local etat="$VEILLE_EMPLOI_RACINE_ETAT/prod" fichiers cas lignes attendus
  fichiers="-f $CLONE/deploiement/compose.yml -f $CLONE/deploiement/compose.projet.yml"
  mkdir -p "$etat"
  # <lignes de compose.env, séparées par des virgules>|<fichiers ajoutés>
  for cas in \
    "VEILLE_EMPLOI_IMAGE=x|" \
    "VEILLE_EMPLOI_IMAGE=x,VEILLE_EMPLOI_CONFIG=/i/config|-f $CLONE/deploiement/compose.config.yml" \
    "VEILLE_EMPLOI_CONTENU=/i/contenu,VEILLE_EMPLOI_IMAGE=x|-f $CLONE/deploiement/compose.contenu.yml" \
    "VEILLE_EMPLOI_CONTENU=/i/contenu,VEILLE_EMPLOI_CONFIG=/i/config|-f $CLONE/deploiement/compose.config.yml -f $CLONE/deploiement/compose.contenu.yml" \
    "VEILLE_EMPLOI_CONFIGURATION=x,VEILLE_EMPLOI_CONTENUS=x,#VEILLE_EMPLOI_CONFIG=/i/config|"; do
    IFS=',' read -r -a lignes <<<"${cas%%|*}"
    printf '%s\n' "${lignes[@]}" >"$etat/compose.env"
    attendus="$fichiers"
    [ -z "${cas#*|}" ] || attendus="$fichiers ${cas#*|}"
    avec_lib 'charger_env prod; dc ps -q app'
    [ "$status" -eq 0 ]
    [ "$(appels_de docker | tail -n 1)" = "docker compose -p veille-emploi $attendus --env-file $etat/compose.env ps -q app" ]
  done
  # sans compose.env : un seul appel, sur les fichiers du projet seulement
  rm "$etat/compose.env"
  : >"$APPELS"
  avec_lib 'charger_env prod; dc ps -q app'
  [ "$status" -eq 0 ]
  [ "$(nombre_d_appels docker)" -eq 1 ]
  [ "$(appels_de docker)" = "docker compose -p veille-emploi $fichiers --env-file $etat/compose.env ps -q app" ]
}

# --- deploiement/projet.env : les réglages du projet, lus et jamais sourcés ----------------------

# projet_env <ligne…> : remplace deploiement/projet.env du clone temporaire par ces lignes.
projet_env() {
  printf '%s\n' "$@" >"$CLONE/deploiement/projet.env"
}

@test "projet_env_jamais_source" {
  local valeur ligne
  for valeur in "\$(touch $BATS_TEST_TMPDIR/temoin)" "\`touch $BATS_TEST_TMPDIR/temoin\`" \
    "sauvegarder;touch $BATS_TEST_TMPDIR/temoin" "sauvegarder && touch $BATS_TEST_TMPDIR/temoin" \
    "sauvegarder | tee $BATS_TEST_TMPDIR/temoin" "sauvegarder >$BATS_TEST_TMPDIR/temoin" \
    '"sauvegarder"' "sauvegarder \${HOME}" $'sauvegarder\tdossier' $'sauvegarder\r'; do
    projet_env "# Réglages" "SAUVEGARDER=$valeur" "VERIFIER=verifier"
    avec_lib 'lire_projet_env SAUVEGARDER; printf "%s|" "${PROJET_MOTS[@]}"'
    [ "$status" -eq 1 ]
    [[ "$output" == *"projet.env, ligne 2 invalide"* ]]
    [ ! -e "$BATS_TEST_TMPDIR/temoin" ]
    # une ligne invalide rend tout le fichier illisible, même pour une autre clé
    avec_lib 'lire_projet_env VERIFIER'
    [ "$status" -eq 1 ]
  done
  # une clé qui n'est pas en majuscules, ou une ligne sans « = »
  for ligne in 'sauvegarder=sauvegarder' 'SAUVEGARDER sauvegarder' '1CLE=x' 'CLE-X=x'; do
    projet_env "$ligne" "VERIFIER=verifier"
    avec_lib 'lire_projet_env VERIFIER'
    [ "$status" -eq 1 ]
    [[ "$output" == *"ligne 1 invalide"* ]]
  done
}

@test "projet_env_mots_separes" {
  projet_env "# Commandes de l'image" "" "SAUVEGARDER=node  outils/instantane.js sauvegarder --forme=dossier " \
    "VERIFIER=verifier" "AUTRE=a:b,c@d%e#f!g*h?i[j]k{l}m^n+o/p=q_r-s.t"
  avec_lib 'lire_projet_env SAUVEGARDER; printf "%s\n" "${#PROJET_MOTS[@]}" "${PROJET_MOTS[@]}"'
  [ "$status" -eq 0 ]
  [ "${lines[0]}" = 4 ]
  [ "${lines[1]}" = node ]
  [ "${lines[2]}" = outils/instantane.js ]
  [ "${lines[3]}" = sauvegarder ]
  [ "${lines[4]}" = --forme=dossier ]
  avec_lib 'lire_projet_env VERIFIER; printf "%s\n" "${#PROJET_MOTS[@]}" "${PROJET_MOTS[@]}"'
  [ "$status" -eq 0 ]
  [ "${lines[0]}" = 1 ]
  [ "${lines[1]}" = verifier ]
  # les symboles que valeur_sure accepte passent tels quels
  avec_lib 'lire_projet_env AUTRE; printf "%s\n" "${PROJET_MOTS[@]}"'
  [ "$status" -eq 0 ]
  [ "$output" = 'a:b,c@d%e#f!g*h?i[j]k{l}m^n+o/p=q_r-s.t' ]
}

@test "projet_env_refuse_absente_vide_double_ou_fichier_manquant" {
  projet_env "VERIFIER=verifier"
  avec_lib 'lire_projet_env SAUVEGARDER'
  [ "$status" -eq 1 ]
  [[ "$output" == *"réglage SAUVEGARDER absent"* ]]
  local valeur
  for valeur in '' ' ' '   '; do
    projet_env "SAUVEGARDER=$valeur"
    avec_lib 'lire_projet_env SAUVEGARDER'
    [ "$status" -eq 1 ]
    [[ "$output" == *"ligne 1 invalide"* ]]
  done
  projet_env "SAUVEGARDER=sauvegarder" "SAUVEGARDER=autre"
  avec_lib 'lire_projet_env SAUVEGARDER; echo "mots : ${#PROJET_MOTS[@]}"'
  [ "$status" -eq 1 ]
  [[ "$output" == *"SAUVEGARDER est déclarée deux fois"* ]]
  rm "$CLONE/deploiement/projet.env"
  avec_lib 'lire_projet_env SAUVEGARDER'
  [ "$status" -eq 1 ]
  [[ "$output" == *"réglages du projet absents"* ]]
  # une clé demandée qui n'en est pas une est une faute d'usage
  projet_env "VERIFIER=verifier"
  avec_lib 'lire_projet_env verifier'
  [ "$status" -eq 64 ]
}

# Une clé facultative (REPORTER, REPORTER_SECTION de la restauration) : absente, rien n'est lu ni
# journalisé, pas même une ligne invalide qu'un lire_projet_env signalerait ; déclarée, elle se lit
# comme les autres, le fichier entier contrôlé.
@test "projet_env_cle_facultative" {
  local compte='lire_projet_env_facultatif REPORTER; echo "mots : ${#PROJET_MOTS[@]}"'
  # en commentaire seulement, comme dans le projet.env que le modèle sème : le test écrit son
  # fichier, car celui du projet déclare peut-être REPORTER (la valeur semée est contrôlée côté modèle)
  projet_env "VERIFIER=verifier" "#REPORTER=reporter" "#REPORTER_SECTION=Reporter à la main"
  avec_lib "$compte"
  [ "$status" -eq 0 ]
  [ "$output" = "mots : 0" ]
  # absente : ni une ligne invalide, ni la clé voisine qui commence comme elle, ni l'absence du
  # fichier n'est une erreur, et rien n'est journalisé
  projet_env "VERIFIER=verifier" "AUTRE=a;b" "REPORTER_SECTION=Reporter à la main"
  avec_lib "$compte"
  [ "$status" -eq 0 ]
  [ "$output" = "mots : 0" ]
  rm "$CLONE/deploiement/projet.env"
  avec_lib "$compte"
  [ "$status" -eq 0 ]
  [ "$output" = "mots : 0" ]
  # déclarée : ses mots, comme lire_projet_env
  projet_env "VERIFIER=verifier" "REPORTER=outil  reporter --tout" "REPORTER_SECTION=Reporter à la main"
  avec_lib 'lire_projet_env_facultatif REPORTER; printf "%s\n" "${PROJET_MOTS[@]}"'
  [ "$status" -eq 0 ]
  [ "$output" = $'outil\nreporter\n--tout' ]
  avec_lib 'lire_projet_env_facultatif REPORTER_SECTION; printf "%s|" "${PROJET_MOTS[*]}"'
  [ "$status" -eq 0 ]
  [ "$output" = "Reporter à la main|" ]
  # déclarée, avec une valeur invalide, une autre ligne invalide ou en double : refus, sans mots
  local cas lignes
  for cas in "ligne 1 invalide|REPORTER=outil;reporter" "ligne 1 invalide|REPORTER=" \
    "ligne 2 invalide|REPORTER=outil|VERIFIER=\$(touch x)" "déclarée deux fois|REPORTER=a|REPORTER=b"; do
    IFS='|' read -r -a lignes <<<"${cas#*|}"
    projet_env "${lignes[@]}"
    avec_lib 'lire_projet_env_facultatif REPORTER || echo "refus, mots : ${#PROJET_MOTS[@]}"'
    [ "$status" -eq 0 ]
    [[ "$output" == *"${cas%%|*}"*"refus, mots : 0" ]]
  done
  # une clé demandée qui n'en est pas une est une faute d'usage
  avec_lib 'lire_projet_env_facultatif reporter'
  [ "$status" -eq 64 ]
}

# Le projet.env du dépôt déclare les deux commandes de l'image, lisibles et d'au moins un mot
# chacune. Le banc en contrôle la forme, jamais les valeurs : chaque projet y met les commandes de
# son image (le fichier n'est semé qu'une fois), et la valeur semée par le modèle est contrôlée
# côté modèle.
@test "projet_env_declare_les_commandes_de_sauvegarde" {
  local cas
  for cas in depot propres; do
    # celui d'un projet qui a mis les commandes de son image à la place des valeurs semées
    [ "$cas" = depot ] || projet_env "# Commandes de l'image" \
      "SAUVEGARDER=node dist/cli.js sauvegarder" "VERIFIER=node dist/cli.js verifier"
    avec_lib 'for cle in SAUVEGARDER VERIFIER; do
        lire_projet_env "$cle"
        [ -n "${PROJET_MOTS[0]:-}" ] || { echo "$cle : aucune commande"; exit 1; }
      done'
    [ "$status" -eq 0 ]
  done
}

# --- L'instance : la règle des paires, l'instantané, sa vérification (M-0006, § 5) ---------------
# Chaque test écrit son projet.env : celui du projet déclare peut-être ses propres commandes.

# declarer <commande…> : deploiement/projet.env ne déclare que ces commandes de vérification de
# l'instance, chacune avec des mots d'exemple (VERIFIER_CONFIG=outil verifier_config…).
declarer() {
  local commande
  local -a lignes=("# Réglages du test")
  for commande in "$@"; do
    lignes+=("$commande=outil ${commande,,}")
  done
  projet_env "${lignes[@]}"
}

# L'image que viserait un déploiement, et les options des conteneurs jetables de lib.sh.
IMAGE_VISEE="ghcr.io/edouardzemb/veille-emploi@sha256:$(printf 'b%.0s' {1..64})"
JETABLES="--user 1000:1000 --read-only --tmpfs /tmp --cap-drop ALL --security-opt no-new-privileges:true --memory 384m"

# messages_du_journal : les lignes de $output (le journal), sans leur horodatage.
messages_du_journal() {
  local ligne
  for ligne in "${lines[@]}"; do
    printf '%s\n' "${ligne#* }"
  done
}

# donnees_declarees lit le projet.env du clone ; donnees_declarees_dans, le fichier qu'on lui donne :
# sonder.sh y passe celui de l'étiquette visée du code, lu sans checkout. Un
# fichier absent ne déclare rien ; le fichier donné se contrôle comme celui du clone. Un nom vide ou
# manquant n'est pas le projet.env du clone : il arrête le script, sans rien lire.
@test "donnees_declarees : le projet.env du clone, ou celui qu'on lui donne" {
  local vise="$BATS_TEST_TMPDIR/projet-vise.env" appel
  declarer VERIFIER_CONFIG
  printf '%s\n' '# Réglages visés' 'VERIFIER_CONTENU=outil verifier_contenu' >"$vise"
  avec_lib 'donnees_declarees; echo "$DECLARE_CONFIG $DECLARE_CONTENU"
    donnees_declarees_dans '"$vise"'; echo "$DECLARE_CONFIG $DECLARE_CONTENU"
    donnees_declarees_dans '"$BATS_TEST_TMPDIR/absent.env"'; echo "$DECLARE_CONFIG $DECLARE_CONTENU"'
  [ "$status" -eq 0 ]
  [ "$output" = $'1 0\n0 1\n0 0' ]
  for appel in 'donnees_declarees_dans ""' donnees_declarees_dans; do
    avec_lib "$appel"'; echo "lu : $DECLARE_CONFIG $DECLARE_CONTENU"'
    [ "$status" -ne 0 ]
    [[ "$output" == *"donnees_declarees_dans : fichier manquant"* ]]
    [[ "$output" != *"lu :"* ]]
  done
  printf '%s\n' 'VERIFIER_CONTENU=outil;verifier' >"$vise"
  avec_lib 'donnees_declarees_dans '"$vise"
  [ "$status" -eq 1 ]
  [[ "$output" == *"réglages du projet illisibles : $vise, ligne 1 invalide"* ]]
}

# La règle des paires : un dossier de l'instance présent dans le commit (un fichier au moins, autre
# que son README.md : voir le test suivant) va avec sa commande, et une commande avec son dossier.
# Chaque paire en défaut est dite ; un commit illisible refuse aussi.
@test "paires : un dossier sans sa commande, une commande sans son dossier" {
  local cas fichiers commandes attendus message attendu
  local -a messages
  # <fichiers du commit>|<commandes déclarées>|<messages attendus, séparés par des virgules>
  for cas in \
    "$SOUS_CONFIG/profil.yml||$SOUS_CONFIG sans VERIFIER_CONFIG" \
    "|VERIFIER_CONFIG|VERIFIER_CONFIG sans $SOUS_CONFIG" \
    "$SOUS_CONTENU/page.md||$SOUS_CONTENU sans VERIFIER_CONTENU" \
    "|VERIFIER_CONTENU|VERIFIER_CONTENU sans $SOUS_CONTENU" \
    "$SOUS_CONFIG/profil.yml|VERIFIER_CONTENU|$SOUS_CONFIG sans VERIFIER_CONFIG,VERIFIER_CONTENU sans $SOUS_CONTENU"; do
    IFS='|' read -r fichiers commandes attendus <<<"$cas"
    # shellcheck disable=SC2086  # listes séparées par des espaces, voulues
    commit_de_donnees $fichiers
    # shellcheck disable=SC2086
    declarer $commandes
    avec_lib 'charger_env prod; controler_paires '"$COMMIT"
    [ "$status" -eq 1 ]
    attendu=""
    IFS=',' read -r -a messages <<<"$attendus"
    for message in "${messages[@]}"; do
      attendu+="$message (commit de données $COMMIT)"$'\n'
    done
    [ "$(messages_du_journal)" = "${attendu%$'\n'}" ]
  done
  # chaque dossier avec sa commande, ou ni l'un ni l'autre : rien à dire. Un dossier du même nom
  # ailleurs dans le dépôt n'est pas celui de l'instance.
  for cas in "$SOUS_CONFIG/profil.yml $SOUS_CONTENU/page.md|VERIFIER_CONFIG VERIFIER_CONTENU" \
    "$SOUS_CONTENU/sous/page.md|VERIFIER_CONTENU" "|" "autre/$SOUS_CONFIG/profil.yml|"; do
    IFS='|' read -r fichiers commandes <<<"$cas"
    # shellcheck disable=SC2086
    commit_de_donnees $fichiers
    # shellcheck disable=SC2086
    declarer $commandes
    avec_lib 'charger_env prod; controler_paires '"$COMMIT"
    [ "$status" -eq 0 ]
    [ -z "$output" ]
  done
  # un commit que le clone n'a pas : refus, dit ; un argument qui n'est pas un commit : usage
  avec_lib 'charger_env prod; controler_paires '"$(printf 'd%.0s' {1..40})"
  [ "$status" -eq 1 ]
  [[ "$output" == *"commit de données illisible"* ]]
  avec_lib 'charger_env prod; controler_paires principal'
  [ "$status" -eq 64 ]
}

# Un dossier de l'instance qui ne porte que le README.md de sa racine (celui
# que sème le gabarit du dépôt de données) compte comme absent, dans les deux sens de la règle. Un
# autre fichier à côté, ou un README.md plus bas, le rend présent.
@test "paires : un dossier qui ne porte que son README.md compte comme absent" {
  local cas fichiers commandes attendu
  # <fichiers du commit>|<commandes déclarées>|<message attendu, vide quand il n'y a rien à dire>
  for cas in \
    "$SOUS_CONFIG/README.md||" \
    "$SOUS_CONFIG/README.md $SOUS_CONTENU/README.md||" \
    "$SOUS_CONFIG/README.md $SOUS_CONTENU/page.md|VERIFIER_CONTENU|" \
    "$SOUS_CONFIG/README.md|VERIFIER_CONFIG|VERIFIER_CONFIG sans $SOUS_CONFIG" \
    "$SOUS_CONTENU/README.md|VERIFIER_CONTENU|VERIFIER_CONTENU sans $SOUS_CONTENU" \
    "$SOUS_CONFIG/README.md $SOUS_CONFIG/a.yaml||$SOUS_CONFIG sans VERIFIER_CONFIG" \
    "$SOUS_CONFIG/a/README.md||$SOUS_CONFIG sans VERIFIER_CONFIG" \
    "$SOUS_CONFIG/README.md $SOUS_CONFIG/été.yml||$SOUS_CONFIG sans VERIFIER_CONFIG" \
    "$SOUS_CONFIG/README.md $SOUS_CONFIG/a.yaml|VERIFIER_CONFIG|"; do
    echo "cas : $cas"
    IFS='|' read -r fichiers commandes attendu <<<"$cas"
    # shellcheck disable=SC2086  # listes séparées par des espaces, voulues
    commit_de_donnees $fichiers
    # shellcheck disable=SC2086
    declarer $commandes
    avec_lib 'charger_env prod; controler_paires '"$COMMIT"
    if [ -z "$attendu" ]; then
      [ "$status" -eq 0 ]
      [ -z "$output" ]
    else
      [ "$status" -eq 1 ]
      [ "$(messages_du_journal)" = "$attendu (commit de données $COMMIT)" ]
    fi
  done
}

# Un .partiel laissé par un essai coupé (en lecture seule, s'il a été coupé après
# chmod) se retire et l'instantané se refait ; un instantané complet se réutilise sans git archive.
@test "instantané : un .partiel se refait, un complet se réutilise" {
  local instantanes="$VEILLE_EMPLOI_RACINE_ETAT/prod/instantanes"
  declarer VERIFIER_CONFIG VERIFIER_CONTENU
  commit_de_donnees "$SOUS_CONFIG/profil.yml" "$SOUS_CONTENU/page.md"
  mkdir -p "$instantanes/$COMMIT.partiel/config"
  echo "reste d'un essai coupé" >"$instantanes/$COMMIT.partiel/config/reste"
  chmod -R a-w "$instantanes/$COMMIT.partiel"
  creer_double_transparent git
  avec_lib 'charger_env prod; preparer_instantane '"$COMMIT"'; echo "INSTANTANE=$INSTANTANE"'
  [ "$status" -eq 0 ]
  [ "${lines[-1]}" = "INSTANTANE=$instantanes/$COMMIT" ]
  [ ! -e "$instantanes/$COMMIT.partiel" ]
  [ "$(cat "$instantanes/$COMMIT/config/profil.yml")" = "fichier d'exemple $SOUS_CONFIG/profil.yml" ]
  [ "$(cat "$instantanes/$COMMIT/contenu/page.md")" = "fichier d'exemple $SOUS_CONTENU/page.md" ]
  [ ! -e "$instantanes/$COMMIT/config/reste" ]
  [ "$(appels_de git | grep -c ' archive ')" -eq 2 ]

  # complet : réutilisé tel quel
  : >"$APPELS"
  avec_lib 'charger_env prod; preparer_instantane '"$COMMIT"'; echo "INSTANTANE=$INSTANTANE"'
  [ "$status" -eq 0 ]
  [ "${lines[-1]}" = "INSTANTANE=$instantanes/$COMMIT" ]
  [[ "$output" == *"instantané des données réutilisé : $instantanes/$COMMIT"* ]]
  [ -z "$(appels_de git | grep ' archive ' || true)" ]

  # un essai qui échoue (un dossier déclaré que le commit n'a pas) : dit, et rien de complet ; son
  # .partiel reste, pour le diagnostic, jusqu'à l'essai suivant
  commit_de_donnees "$SOUS_CONFIG/profil.yml"
  avec_lib 'charger_env prod; preparer_instantane '"$COMMIT"
  [ "$status" -eq 1 ]
  [[ "$output" == *"extraction impossible de $SOUS_CONTENU du commit de données $COMMIT"* ]]
  [ ! -e "$instantanes/$COMMIT" ]
  [ -d "$instantanes/$COMMIT.partiel" ]
  # un instantané qui n'a pas un dossier déclaré n'est pas complet : refus, sans rien remplacer
  mkdir -p "$instantanes/$COMMIT/config"
  avec_lib 'charger_env prod; preparer_instantane '"$COMMIT"
  [ "$status" -eq 1 ]
  [[ "$output" == *"instantané des données incomplet : $instantanes/$COMMIT (sans contenu)"* ]]
  [ -d "$instantanes/$COMMIT/config" ]
}

# L'instantané vient du commit, pas de la copie de travail du clone ; il ne porte que les dossiers
# déclarés, chacun sous son nom final et en entier (son README.md compris), et rien n'y est
# inscriptible.
@test "instantané : en lecture seule, et seulement les dossiers déclarés" {
  local instantane
  declarer VERIFIER_CONTENU
  commit_de_donnees "$SOUS_CONFIG/profil.yml" "$SOUS_CONTENU/page.md" "$SOUS_CONTENU/sous/profond.md" \
    "$SOUS_CONTENU/README.md"
  echo "modifié après le commit" >"$CLONE_DONNEES/$SOUS_CONTENU/page.md"
  avec_lib 'charger_env staging; preparer_instantane '"$COMMIT"'; echo "INSTANTANE=$INSTANTANE"'
  [ "$status" -eq 0 ]
  instantane="$VEILLE_EMPLOI_RACINE_ETAT/staging/instantanes/$COMMIT"
  [ "${lines[-1]}" = "INSTANTANE=$instantane" ]
  [ "$(find "$instantane" -mindepth 1 -maxdepth 1 -printf '%f')" = contenu ]
  [ "$(cat "$instantane/contenu/page.md")" = "fichier d'exemple $SOUS_CONTENU/page.md" ]
  [ "$(cat "$instantane/contenu/sous/profond.md")" = "fichier d'exemple $SOUS_CONTENU/sous/profond.md" ]
  [ "$(cat "$instantane/contenu/README.md")" = "fichier d'exemple $SOUS_CONTENU/README.md" ]
  [ -z "$(find "$instantane" -perm /222)" ]
  # chaque environnement a les siens
  [ ! -e "$VEILLE_EMPLOI_RACINE_ETAT/prod/instantanes" ]
  # les deux dossiers déclarés : les deux, sous config/ et contenu/ quel que soit le mode
  declarer VERIFIER_CONFIG VERIFIER_CONTENU
  commit_de_donnees "$SOUS_CONFIG/profil.yml" "$SOUS_CONTENU/page.md"
  avec_lib 'charger_env prod; preparer_instantane '"$COMMIT"
  [ "$status" -eq 0 ]
  instantane="$VEILLE_EMPLOI_RACINE_ETAT/prod/instantanes/$COMMIT"
  [ "$(find "$instantane" -mindepth 1 -maxdepth 1 -printf '%f\n' | sort | tr '\n' ' ')" = "config contenu " ]
  [ -z "$(find "$instantane" -perm /222)" ]
  # le staging ne monte ni ne vérifie jamais /config, et son instantané n'en porte pas
  # de copie, même quand VERIFIER_CONFIG est déclarée ; complet sans lui, il se réutilise
  avec_lib 'charger_env staging; preparer_instantane '"$COMMIT"
  [ "$status" -eq 0 ]
  instantane="$VEILLE_EMPLOI_RACINE_ETAT/staging/instantanes/$COMMIT"
  [ "$(find "$instantane" -mindepth 1 -maxdepth 1 -printf '%f')" = contenu ]
  [[ "$output" == *"instantané des données prêt : $instantane"* ]]
  avec_lib 'charger_env staging; preparer_instantane '"$COMMIT"
  [ "$status" -eq 0 ]
  [[ "$output" == *"instantané des données réutilisé : $instantane"* ]]
  # VERIFIER_CONFIG seule, en staging : rien à extraire
  declarer VERIFIER_CONFIG
  commit_de_donnees "$SOUS_CONFIG/profil.yml"
  avec_lib 'charger_env staging; preparer_instantane '"$COMMIT"
  [ "$status" -eq 0 ]
  instantane="$VEILLE_EMPLOI_RACINE_ETAT/staging/instantanes/$COMMIT"
  [ -d "$instantane" ]
  [ -z "$(find "$instantane" -mindepth 1)" ]
}

# Les commandes de vérification : chacune dans un conteneur jetable de l'image visée, sans réseau,
# avec les options des conteneurs jetables, son seul dossier monté en lecture seule. 0 conforme,
# 2 non conforme ; 64 ou tout autre code : la vérification n'a pas eu lieu (1).
@test "vérifier : codes 0, 2 et autres" {
  local instantane="$BATS_TEST_TMPDIR/instantane" dossier code
  mkdir -p "$instantane/config" "$instantane/contenu"
  declarer VERIFIER_CONFIG VERIFIER_CONTENU
  creer_double docker 'echo "conforme : 2 fichiers"'
  run --separate-stderr bash -c 'set -euo pipefail; . "$CLONE/deploiement/lib.sh"; verifier_instantane prod '"$IMAGE_VISEE $instantane"
  [ "$status" -eq 0 ]
  # rien sur stdout : la sortie des commandes va au journal
  [ -z "$output" ]
  # shellcheck disable=SC2154  # $stderr est posée par run --separate-stderr
  [[ "$stderr" == *"configuration conforme (VERIFIER_CONFIG : code 0) : conforme : 2 fichiers"* ]]
  [[ "$stderr" == *"contenu conforme (VERIFIER_CONTENU : code 0) : conforme : 2 fichiers"* ]]
  [ "$(appels_de docker)" = "$(printf '%s\n' \
    "docker run --rm --network none $JETABLES -v $instantane/config:/config:ro $IMAGE_VISEE outil verifier_config /config" \
    "docker run --rm --network none $JETABLES -v $instantane/contenu:/contenu:ro $IMAGE_VISEE outil verifier_contenu /contenu")" ]
  # 2 : non conforme, dit, et la vérification s'arrête là
  for dossier in config contenu; do
    creer_double docker 'case "$*" in *":/'"$dossier"':ro "*) echo "écart : '"$dossier"'"; exit 2 ;; esac'
    avec_lib 'verifier_instantane prod '"$IMAGE_VISEE $instantane"
    [ "$status" -eq 2 ]
    [[ "$output" == *"non conforme (VERIFIER_${dossier^^} : code 2) : écart : $dossier"* ]]
  done
  : >"$APPELS"
  creer_double docker 'echo "écart"; exit 2'
  avec_lib 'verifier_instantane prod '"$IMAGE_VISEE $instantane"
  [ "$status" -eq 2 ]
  [ "$(nombre_d_appels docker)" -eq 1 ]
  # 64 (usage refusé par l'image) ou tout autre code
  for code in 64 1 125; do
    creer_double docker 'echo "usage : outil <commande>"; exit '"$code"
    avec_lib 'verifier_instantane prod '"$IMAGE_VISEE $instantane"
    [ "$status" -eq 1 ]
    [[ "$output" == *"vérification impossible (VERIFIER_CONFIG : code $code)"*"usage : outil <commande>"* ]]
  done
  # un dossier déclaré qui manque à l'instantané : erreur, et aucun conteneur (docker créerait le
  # dossier à monter)
  rm -rf "$instantane/contenu"
  : >"$APPELS"
  creer_double docker
  avec_lib 'verifier_instantane prod '"$IMAGE_VISEE $instantane"
  [ "$status" -eq 1 ]
  [[ "$output" == *"instantané sans contenu : $instantane/contenu"* ]]
  [ "$(nombre_d_appels docker)" -eq 0 ]
  # rien de déclaré : rien à lancer
  declarer
  avec_lib 'verifier_instantane prod '"$IMAGE_VISEE $instantane"
  [ "$status" -eq 0 ]
  [ "$(nombre_d_appels docker)" -eq 0 ]
}

# Le staging ne monte jamais /config (M-0006, § 5) : VERIFIER_CONFIG n'y tourne pas, quoi que porte
# l'instantané ; VERIFIER_CONTENU, si.
@test "vérifier : le staging ne lance pas VERIFIER_CONFIG" {
  local instantane="$BATS_TEST_TMPDIR/instantane"
  mkdir -p "$instantane/config" "$instantane/contenu"
  declarer VERIFIER_CONFIG VERIFIER_CONTENU
  creer_double docker 'case "$*" in *":/config:ro "*) exit 2 ;; esac; echo conforme'
  avec_lib 'verifier_instantane staging '"$IMAGE_VISEE $instantane"
  [ "$status" -eq 0 ]
  [ "$(appels_de docker)" = "docker run --rm --network none $JETABLES -v $instantane/contenu:/contenu:ro $IMAGE_VISEE outil verifier_contenu /contenu" ]
  [[ "$output" == *"staging : VERIFIER_CONFIG n'est pas lancée, /config n'y est jamais monté"* ]]
  # sans config/ dans l'instantané non plus
  rm -rf "$instantane/config"
  avec_lib 'verifier_instantane staging '"$IMAGE_VISEE $instantane"
  [ "$status" -eq 0 ]
  aucune_ligne ':/config' "$APPELS"
  # un environnement inconnu est une faute d'usage
  avec_lib 'verifier_instantane recette '"$IMAGE_VISEE $instantane"
  [ "$status" -eq 64 ]
}

# VERIFIER_CONTENU reçoit en second argument le contenu du couple en service, monté sur
# /en-service ; VERIFIER_CONFIG, jamais.
@test "vérifier : /en-service pour le contenu en service" {
  local vise="$BATS_TEST_TMPDIR/vise" service="$BATS_TEST_TMPDIR/service"
  mkdir -p "$vise/config" "$vise/contenu" "$service/config" "$service/contenu"
  declarer VERIFIER_CONFIG VERIFIER_CONTENU
  creer_double docker 'echo conforme'
  avec_lib 'verifier_instantane prod '"$IMAGE_VISEE $vise $service"
  [ "$status" -eq 0 ]
  [ "$(appels_de docker)" = "$(printf '%s\n' \
    "docker run --rm --network none $JETABLES -v $vise/config:/config:ro $IMAGE_VISEE outil verifier_config /config" \
    "docker run --rm --network none $JETABLES -v $vise/contenu:/contenu:ro -v $service/contenu:/en-service:ro $IMAGE_VISEE outil verifier_contenu /contenu /en-service")" ]
  # un couple en service sans contenu (il ne montait que la configuration) : pas de /en-service
  rm -rf "$service/contenu"
  : >"$APPELS"
  avec_lib 'verifier_instantane prod '"$IMAGE_VISEE $vise $service"
  [ "$status" -eq 0 ]
  [ "$(appels_de docker | tail -n 1)" = "docker run --rm --network none $JETABLES -v $vise/contenu:/contenu:ro $IMAGE_VISEE outil verifier_contenu /contenu" ]
  # un instantané en service introuvable : erreur, aucun conteneur
  : >"$APPELS"
  avec_lib 'verifier_instantane prod '"$IMAGE_VISEE $vise $BATS_TEST_TMPDIR/absent"
  [ "$status" -eq 1 ]
  [[ "$output" == *"instantané en service introuvable : $BATS_TEST_TMPDIR/absent"* ]]
  [ "$(nombre_d_appels docker)" -eq 0 ]
}

@test "signaler_ok_envoie_le_message_a_l_adresse_de_la_variable" {
  creer_double curl
  export HC_SONDE="https://hc.example/ping/abc"
  avec_lib 'signaler HC_SONDE ok "déployé v1"'
  [ "$status" -eq 0 ]
  [ "$(envois_supervision)" = "curl -fsS -m 10 --retry 3 --data-raw déployé v1 https://hc.example/ping/abc" ]
}

@test "signaler_echec_ajoute_fail" {
  creer_double curl
  export HC_SONDE="https://hc.example/ping/abc"
  avec_lib 'signaler HC_SONDE echec "échec v1"'
  [ "$status" -eq 0 ]
  [ "$(envois_supervision)" = "curl -fsS -m 10 --retry 3 --data-raw échec v1 https://hc.example/ping/abc/fail" ]
}

@test "signaler_sans_message_envoie_un_corps_vide" {
  creer_double curl
  export HC_SONDE="https://hc.example/ping/abc"
  avec_lib 'signaler HC_SONDE ok'
  [ "$status" -eq 0 ]
  [ "$(envois_supervision)" = "curl -fsS -m 10 --retry 3 --data-raw  https://hc.example/ping/abc" ]
}

@test "signaler_variable_vide_journalise_et_renvoie_0" {
  creer_double curl
  unset HC_SONDE
  avec_lib 'signaler HC_SONDE ok "x"'
  [ "$status" -eq 0 ]
  [[ "$output" == *"signal HC_SONDE non configuré"* ]]
  [ "$(nombre_d_appels curl)" -eq 0 ]
  export HC_SONDE=""
  avec_lib 'signaler HC_SONDE echec "x"'
  [ "$status" -eq 0 ]
  [ "$(nombre_d_appels curl)" -eq 0 ]
}

@test "signaler_propage_l_echec_de_curl_sans_afficher_l_adresse" {
  creer_double curl 'exit 22'
  export HC_SONDE="https://hc.example/ping/secret-uuid"
  avec_lib 'signaler HC_SONDE ok "x"'
  [ "$status" -eq 22 ]
  [[ "$output" == *"HC_SONDE"* ]]
  [[ "$output" != *secret-uuid* ]]
}

# Sur un hôte partagé, la ligne de commande d'un processus est lisible par les autres comptes (ps) :
# l'adresse du ping, qui suffit à envoyer de faux signaux, passe à curl par sa configuration
# (`-K -`, `url = "…"`, lue sur l'entrée standard). Le double refuse une adresse en argument.
@test "signaler_donne_l_adresse_a_curl_sur_l_entree_standard_et_jamais_en_argument" {
  installer_doubles curl
  export HC_SONDE="https://hc-ping.com/uuid-argv-8"
  avec_lib 'signaler HC_SONDE ok "déployé v1"; signaler HC_SONDE echec "échec v1"'
  [ "$status" -eq 0 ]
  [ "$(appels_de curl)" = "$(printf '%s\n' \
    'curl -fsS -m 10 --retry 3 --data-raw déployé v1 -K -' \
    'curl -fsS -m 10 --retry 3 --data-raw échec v1 -K -')" ]
  aucune_ligne 'hc-ping|uuid-argv-8|https?://' "$APPELS"
  # l'adresse est bien arrivée par la configuration, /fail compris
  [ "$(envois_supervision)" = "$(printf '%s\n' \
    'curl -fsS -m 10 --retry 3 --data-raw déployé v1 https://hc-ping.com/uuid-argv-8' \
    'curl -fsS -m 10 --retry 3 --data-raw échec v1 https://hc-ping.com/uuid-argv-8/fail')" ]
}

# Un guillemet, une barre oblique inverse ou un saut de ligne sortiraient de la chaîne de la
# configuration (ou y ajouteraient une ligne : `output = …`). charger_secrets les refuse déjà ;
# signaler ne les envoie pas non plus si la variable vient d'ailleurs.
@test "signaler_refuse_une_adresse_qui_sortirait_de_la_configuration_de_curl" {
  installer_doubles curl
  local adresse
  for adresse in 'https://hc.example/a"b' 'https://hc.example/a\b' \
    $'https://hc.example/a\noutput = "/tmp/pris"'; do
    export HC_SONDE="$adresse"
    : >"$APPELS"
    avec_lib 'signaler HC_SONDE ok "x"'
    [ "$status" -eq 1 ]
    [[ "$output" == *"HC_SONDE"* ]]
    [[ "$output" != *hc.example* ]]
    [ "$(nombre_d_appels curl)" -eq 0 ]
  done
}

@test "signaler_refuse_un_etat_inconnu" {
  creer_double curl
  export HC_SONDE="https://hc.example/ping/abc"
  avec_lib 'signaler HC_SONDE peut-etre'
  [ "$status" -eq 64 ]
  [ "$(nombre_d_appels curl)" -eq 0 ]
}

@test "journal_ecrit_sur_stderr_avec_l_heure_iso" {
  avec_lib 'journal bonjour le monde 2>/dev/null'
  [ "$status" -eq 0 ]
  [ -z "$output" ]
  avec_lib 'journal bonjour le monde 2>&1 >/dev/null'
  [ "$status" -eq 0 ]
  [[ "$output" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z\ bonjour\ le\ monde$ ]]
}

# Sous `bash -x` la trace va dans le journal : l'adresse de ping (qui suffit à envoyer de faux
# signaux) ne doit pas y figurer, mais la trace doit reprendre ensuite.
@test "signaler_n_ecrit_pas_l_adresse_sous_bash_x" {
  creer_double curl
  export HC_SONDE="https://hc.example/ping/uuid-trace-6"
  run bash -x -c 'set -euo pipefail; . "$CLONE/deploiement/lib.sh"
    signaler HC_SONDE echec bonjour; : marqueur-de-trace'
  [ "$status" -eq 0 ]
  [[ "$output" != *uuid-trace-6* ]]
  [[ "$output" == *"+ : marqueur-de-trace"* ]]
  [[ "$(envois_supervision)" == *"/ping/uuid-trace-6/fail" ]]

  # même chose quand curl échoue (le message d'erreur ne répète pas l'adresse)
  creer_double curl 'exit 22'
  run bash -x -c 'set -uo pipefail; . "$CLONE/deploiement/lib.sh"; signaler HC_SONDE ok bonjour; echo "code=$?"'
  [[ "$output" != *uuid-trace-6* ]]
  [[ "$output" == *"code=22"* ]]
}

# --- Santé sur un port, verrou, état déployé --------------------------------------------------
# (communs à la sonde, au déploiement, à la sauvegarde, au test de restauration et à la restauration)

@test "sante_sur_controle_le_port_et_le_filtre_demandes" {
  creer_double curl 'echo "{\"statut\":\"ok\",\"environnement\":\"ci\"}"'
  avec_lib 'sante_sur 4319 ".statut == \"ok\" and .environnement == \$environnement" --arg environnement ci'
  [ "$status" -eq 0 ]
  [ "${lines[0]}" = '{"statut":"ok","environnement":"ci"}' ]
  [ "$(appels_de curl)" = "curl -fsS -m 5 http://127.0.0.1:4319/sante" ]
  # un autre environnement : la réponse est imprimée, le contrôle échoue
  avec_lib 'sante_sur 4319 ".statut == \"ok\" and .environnement == \$environnement" --arg environnement prod'
  [ "$status" -eq 1 ]
  [ "${lines[0]}" = '{"statut":"ok","environnement":"ci"}' ]
  # curl échoue : l'erreur de curl est imprimée
  creer_double curl 'echo "curl: (7) refusé" >&2; exit 7'
  avec_lib 'sante_sur 4319 ".statut == \"ok\""'
  [ "$status" -eq 1 ]
  [ "${lines[0]}" = "curl: (7) refusé" ]
}

@test "sante_locale_vise_le_port_de_l_environnement" {
  creer_double curl 'echo "{\"statut\":\"ok\",\"version\":\"1.2.3\",\"revision\":\"abc\"}"'
  avec_lib 'charger_env prod; sante_locale 1.2.3 abc'
  [ "$status" -eq 0 ]
  [ "$(appels_de curl)" = "curl -fsS -m 5 http://127.0.0.1:4310/sante" ]
  avec_lib 'charger_env prod; sante_locale 1.2.3 autre'
  [ "$status" -eq 1 ]
}

# Le champ configuration (exemple ou montee) n'est exigé que si on le demande : un projet qui ne
# déclare pas VERIFIER_CONFIG garde la santé d'avant.
@test "santé : le champ configuration n'est lu que sur demande" {
  creer_double curl 'echo "{\"statut\":\"ok\",\"version\":\"1.2.3\",\"revision\":\"abc\"}"'
  avec_lib 'charger_env prod; sante_locale 1.2.3 abc'
  [ "$status" -eq 0 ]
  avec_lib 'charger_env prod; sante_locale 1.2.3 abc montee'
  [ "$status" -eq 1 ]
  creer_double curl 'echo "{\"statut\":\"ok\",\"version\":\"1.2.3\",\"revision\":\"abc\",\"configuration\":\"montee\"}"'
  avec_lib 'charger_env prod; sante_locale 1.2.3 abc montee'
  [ "$status" -eq 0 ]
  avec_lib 'charger_env prod; sante_locale 1.2.3 abc exemple'
  [ "$status" -eq 1 ]
  avec_lib 'charger_env prod; sante_locale 1.2.3 abc'
  [ "$status" -eq 0 ]
  # la version et la révision comptent toujours
  avec_lib 'charger_env prod; sante_locale 1.2.3 autre montee'
  [ "$status" -eq 1 ]
}

@test "attendre_sante_reessaie_puis_reussit" {
  export VEILLE_EMPLOI_SANTE_DELAI=0
  # les deux premiers essais échouent, le troisième est bon
  creer_double curl 'n=$(wc -l <"'"$APPELS"'"); if [ "$n" -lt 3 ]; then exit 22; fi; echo "{\"statut\":\"ok\"}"'
  avec_lib 'attendre_sante 4319 ".statut == \"ok\""'
  [ "$status" -eq 0 ]
  [ "$(nombre_d_appels curl)" -eq 3 ]
  [[ "$output" == *"santé conforme sur le port 4319 (essai 3)"* ]]
}

@test "attendre_sante_abandonne_apres_dix_essais" {
  export VEILLE_EMPLOI_SANTE_DELAI=0
  creer_double curl 'echo "curl: (22) 503" >&2; exit 22'
  avec_lib 'attendre_sante 4319 ".statut == \"ok\""'
  [ "$status" -eq 1 ]
  [ "$(nombre_d_appels curl)" -eq 10 ]
  [[ "$output" == *"santé non conforme sur le port 4319 après 10 essais"* ]]
}

@test "reserver_a_prod_refuse_le_staging_et_l_inconnu" {
  avec_lib 'reserver_a_prod prod essai.sh; echo ok'
  [ "$status" -eq 0 ]
  [ "$output" = ok ]
  avec_lib 'reserver_a_prod staging essai.sh'
  [ "$status" -eq 64 ]
  [[ "$output" == *"essai.sh est réservé à la prod (reçu : 'staging')"* ]]
  avec_lib 'reserver_a_prod dev essai.sh'
  [ "$status" -eq 64 ]
  [[ "$output" == *"environnement inconnu"* ]]
}

@test "refuser_image_heritee_refuse_image_et_version_du_shell" {
  avec_lib 'refuser_image_heritee; echo ok'
  [ "$status" -eq 0 ]
  VEILLE_EMPLOI_IMAGE=x avec_lib 'refuser_image_heritee'
  [ "$status" -eq 1 ]
  [[ "$output" == *"VEILLE_EMPLOI_IMAGE est posée dans l'environnement"* ]]
  VEILLE_EMPLOI_VERSION="" avec_lib 'refuser_image_heritee'
  [ "$status" -eq 1 ]
  [[ "$output" == *"VEILLE_EMPLOI_VERSION est posée dans l'environnement"* ]]
}

# Les montages de l'instantané aussi : compose prend VEILLE_EMPLOI_CONFIG et VEILLE_EMPLOI_CONTENU du shell avant
# compose.env, et la prod monterait un autre dossier que l'instantané vérifié (M-0006, § 5). Une
# valeur venue de l'env de l'environnement, que charger_env source et exporte, est refusée de même.
@test "refuser_image_heritee : la configuration et le contenu, du shell ou de l'env" {
  local variable env_prod="$CLONE_DONNEES/$SOUS_ENV/prod.env"
  cp "$env_prod" "$BATS_TEST_TMPDIR/prod.env.origine"
  for variable in VEILLE_EMPLOI_CONFIG VEILLE_EMPLOI_CONTENU; do
    echo "cas : $variable du shell"
    export "$variable=$CLONE_DONNEES/$SOUS_CONFIG"
    avec_lib 'charger_env prod; refuser_image_heritee; echo pas de refus'
    unset "$variable"
    [ "$status" -eq 1 ]
    [[ "$output" == *"$variable est posée dans l'environnement : elle prendrait le pas sur compose.env"* ]]
    [[ "$output" != *"pas de refus"* ]]

    echo "cas : $variable de l'env de prod"
    cp "$BATS_TEST_TMPDIR/prod.env.origine" "$env_prod"
    echo "$variable=$CLONE_DONNEES/$SOUS_CONTENU" >>"$env_prod"
    avec_lib 'charger_env prod; refuser_image_heritee; echo pas de refus'
    [ "$status" -eq 1 ]
    [[ "$output" == *"$variable est posée dans l'environnement"* ]]
    [[ "$output" != *"pas de refus"* ]]
    cp "$BATS_TEST_TMPDIR/prod.env.origine" "$env_prod"
  done
  # un nom voisin n'est pas visé
  VEILLE_EMPLOI_CONFIGURATION=x VEILLE_EMPLOI_CONTENUS=x avec_lib 'charger_env prod; refuser_image_heritee; echo pas de refus'
  [ "$status" -eq 0 ]
  [ "${lines[-1]}" = "pas de refus" ]
}

# _retirer_fige : un dossier figé (a-w, comme un instantané) se retire, sous-dossiers figés compris ;
# un lien est retiré sans que sa cible perde rien, ni ses droits ; un chemin absent n'est pas une
# erreur.
@test "_retirer_fige : un dossier en lecture seule, jamais à travers un lien" {
  local fige="$BATS_TEST_TMPDIR/fige" cible="$BATS_TEST_TMPDIR/cible"
  mkdir -p "$fige/sous" "$cible"
  echo garde >"$cible/fichier"
  echo x >"$fige/sous/fichier"
  ln -s "$cible" "$fige/lien"
  chmod -R a-w "$fige" "$cible"
  avec_lib '_retirer_fige "'"$fige"'"'
  [ "$status" -eq 0 ]
  [ ! -e "$fige" ]
  [ "$(cat "$cible/fichier")" = garde ]
  [ -z "$(find "$cible" -perm /222)" ]
  # un lien à la place du dossier : le lien s'en va, la cible reste, en lecture seule
  ln -s "$cible" "$fige"
  avec_lib '_retirer_fige "'"$fige"'"'
  [ "$status" -eq 0 ]
  [ ! -L "$fige" ]
  [ -d "$cible" ]
  [ -z "$(find "$cible" -perm /222)" ]
  # absent : rien à faire
  avec_lib '_retirer_fige "'"$fige"'"'
  [ "$status" -eq 0 ]
  [ -z "$output" ]
  # un dossier qui ne se retire pas (son parent est figé, et _retirer_fige ne remonte pas) : échec,
  # sans rien journaliser, et il reste
  mkdir -p "$BATS_TEST_TMPDIR/parent/fige"
  chmod a-w "$BATS_TEST_TMPDIR/parent"
  avec_lib '_retirer_fige "'"$BATS_TEST_TMPDIR/parent/fige"'"'
  [ "$status" -eq 1 ]
  [ -z "$output" ]
  [ -d "$BATS_TEST_TMPDIR/parent/fige" ]
}

@test "prendre_verrou_est_le_verrou_de_l_etat_et_attend_le_delai" {
  avec_lib 'charger_env prod; prendre_verrou; echo pris'
  [ "$status" -eq 0 ]
  [ "$output" = pris ]
  [ -f "$VEILLE_EMPLOI_RACINE_ETAT/prod/verrou" ]
  # tenu par un autre processus (poignée de main par fichier marqueur : il tient le verrou quand
  # la main revient) : échec, sans journal, après l'attente demandée
  tenir_le_verrou "$VEILLE_EMPLOI_RACINE_ETAT/prod/verrou"
  VEILLE_EMPLOI_VERROU_ATTENTE=1 avec_lib 'charger_env prod; prendre_verrou'
  relacher_le_verrou
  [ "$status" -eq 1 ]
  [ -z "$output" ]
}

@test "lire_deploye_lit_l_image_et_la_version" {
  local image
  image="ghcr.io/edouardzemb/veille-emploi@sha256:$(printf 'a%.0s' {1..64})"
  en_service prod "$image" 0.4.2
  avec_lib 'charger_env prod; lire_deploye; printf "%s\n" "$DEPLOYE_IMAGE" "$DEPLOYE_VERSION"'
  [ "$status" -eq 0 ]
  [ "${lines[0]}" = "$image" ]
  [ "${lines[1]}" = 0.4.2 ]
}

@test "lire_deploye_refuse_un_etat_absent_ou_illisible" {
  avec_lib 'charger_env prod; lire_deploye'
  [ "$status" -eq 1 ]
  [[ "$output" == *"aucune version déployée"* ]]
  local etat="$VEILLE_EMPLOI_RACINE_ETAT/prod" contenu
  for contenu in "-v 0.1.0" "image-sans-condense 0.1.0" "ghcr.io/x/y@sha256:$(printf 'a%.0s' {1..64})"; do
    echo "$contenu" >"$etat/deploye"
    avec_lib 'charger_env prod; lire_deploye'
    [ "$status" -eq 1 ]
    [[ "$output" == *"deploye illisible"* ]]
  done
  # présent sans être un fichier (un dossier, un lien mort) : illisible, comme le dit le signal de
  # la sonde, et non absent
  local present
  for present in dossier lien-mort; do
    rm -rf "$etat/deploye"
    if [ "$present" = dossier ]; then
      mkdir "$etat/deploye"
    else
      ln -s "$etat/nulle-part" "$etat/deploye"
    fi
    avec_lib 'charger_env prod; lire_deploye'
    [ "$status" -eq 1 ]
    [[ "$output" == *"deploye illisible : ce n'est pas un fichier"* ]]
    [[ "$output" != *"aucune version déployée"* ]]
  done
}

# L'état en couple (M-0004, amendé) : deploye et precedent gagnent un troisième champ, le commit de
# données, et echec un second. Un état d'avant la v0.7.0, sans ce champ, se lit comme un couple dont
# le commit vaut « - ».
@test "couple : lire un état à deux, trois champs, et echec à un, deux champs" {
  local image sha etat="$VEILLE_EMPLOI_RACINE_ETAT/prod" cas contenu version commit_lu
  image="ghcr.io/edouardzemb/veille-emploi@sha256:$(printf 'a%.0s' {1..64})"
  sha="$(printf 'c%.0s' {1..40})"
  mkdir -p "$etat"
  local lire='charger_env prod; lire_deploye; printf "%s\n" "$DEPLOYE_IMAGE" "$DEPLOYE_VERSION" "$DEPLOYE_COMMIT"
    lire_version "$VEILLE_EMPLOI_ETAT/deploye"; printf "%s\n" "$IMAGE_LUE" "$VERSION_LUE" "$COMMIT_LU"'
  # <contenu de deploye>|<version lue>|<commit lu> ; un quatrième champ est ignoré, comme avant
  for cas in "$image 1.2.3|1.2.3|-" "$image 1.2.3 $sha|1.2.3|$sha" "$image 1.2.3 -|1.2.3|-" \
    "$image main $sha autre|main|$sha"; do
    IFS='|' read -r contenu version commit_lu <<<"$cas"
    echo "$contenu" >"$etat/deploye"
    avec_lib "$lire"
    [ "$status" -eq 0 ]
    [ "${lines[*]}" = "$image $version $commit_lu $image $version $commit_lu" ]
  done
  # un commit d'une autre forme : l'état est illisible
  for commit_lu in abc "$(printf 'C%.0s' {1..40})" "${sha}0" "--"; do
    echo "$image 1.2.3 $commit_lu" >"$etat/deploye"
    avec_lib 'charger_env prod; lire_deploye'
    [ "$status" -eq 1 ]
    [[ "$output" == *"deploye illisible"* ]]
    avec_lib 'charger_env prod; lire_version "$VEILLE_EMPLOI_ETAT/deploye" || echo "illisible : [$IMAGE_LUE]"'
    [ "$output" = "illisible : []" ]
  done

  # echec : aucun fichier, aucun couple en échec
  local lecture_echec='charger_env prod; lire_echec; printf "[%s] [%s]\n" "$ECHEC_IMAGE" "$ECHEC_COMMIT"'
  avec_lib "$lecture_echec"
  [ "$status" -eq 0 ]
  [ "$output" = "[] []" ]
  # <contenu de echec>|<commit lu>
  for contenu in "$image|-" "$image $sha|$sha" "$image -|-"; do
    echo "${contenu%|*}" >"$etat/echec"
    avec_lib "$lecture_echec"
    [ "$status" -eq 0 ]
    [ "$output" = "[$image] [${contenu#*|}]" ]
  done
  # illisible : vide, une image d'une autre forme, un commit d'une autre forme
  for contenu in "" "image-sans-condense" "image-sans-condense $sha" "$image abc"; do
    echo "$contenu" >"$etat/echec"
    avec_lib 'charger_env prod; lire_echec || printf "illisible : [%s] [%s]\n" "$ECHEC_IMAGE" "$ECHEC_COMMIT"'
    [ "$status" -eq 0 ]
    [ "$output" = "illisible : [] []" ]
  done
}

# --- verifier_copie : la commande VERIFIER de l'image, sur un dossier qui a la forme de /donnees ---
# Le contrat de l'instantané : `<VERIFIER…> <dossier>` rend 0 (conforme), 2 (non conforme) ou 64
# (usage). Seul le code fait foi.

@test "verifier_copie_lance_verifier_dans_un_conteneur_jetable" {
  local image
  image="ghcr.io/edouardzemb/veille-emploi@sha256:$(printf 'a%.0s' {1..64})"
  projet_env "SAUVEGARDER=outil sauvegarder" "VERIFIER=outil verifier --strict"
  creer_double docker 'echo "conforme : 3 fichiers"'
  run --separate-stderr bash -c 'set -euo pipefail; . "$CLONE/deploiement/lib.sh"; verifier_copie '"$image"' /un/dossier'
  [ "$status" -eq 0 ]
  # rien sur stdout : la sortie de la commande va au journal
  [ -z "$output" ]
  # shellcheck disable=SC2154  # $stderr est posée par run --separate-stderr
  [[ "$stderr" == *"copie conforme (verifier : code 0) : conforme : 3 fichiers"* ]]
  # un conteneur jetable, avec les restrictions du service, qui ne voit que ce dossier, sur
  # /donnees ; la commande de projet.env mot à mot, puis /donnees
  [ "$(appels_de docker)" = "docker run --rm --user 1000:1000 --read-only --tmpfs /tmp --cap-drop ALL --security-opt no-new-privileges:true --memory 384m -v /un/dossier:/donnees $image outil verifier --strict /donnees" ]
}

@test "verifier_copie_rend_0_2_ou_1_selon_le_code_de_verifier" {
  local image code
  image="ghcr.io/edouardzemb/veille-emploi@sha256:$(printf 'a%.0s' {1..64})"
  projet_env "VERIFIER=outil verifier"
  # 2 : l'image dit « non conforme » ; la sortie va au journal, rien sur stdout
  creer_double docker 'echo "écart : donnees.txt"; exit 2'
  run --separate-stderr bash -c 'set -euo pipefail; . "$CLONE/deploiement/lib.sh"; verifier_copie '"$image"' /d'
  [ "$status" -eq 2 ]
  [ -z "$output" ]
  [[ "$stderr" == *"copie non conforme (verifier : code 2) : écart : donnees.txt"* ]]
  # 64 (usage refusé par l'image), ou tout autre code : la vérification n'a pas eu lieu
  for code in 64 1 125; do
    creer_double docker 'echo "usage : outil <commande>"; exit '"$code"
    avec_lib 'verifier_copie '"$image"' /d'
    [ "$status" -eq 1 ]
    [[ "$output" == *"vérification impossible (verifier : code $code)"*"usage : outil <commande>"* ]]
  done
  # sans commande VERIFIER dans projet.env, rien n'est lancé
  : >"$APPELS"
  projet_env "SAUVEGARDER=outil sauvegarder"
  avec_lib 'verifier_copie '"$image"' /d'
  [ "$status" -eq 1 ]
  [[ "$output" == *"réglage VERIFIER absent"* ]]
  [ "$(nombre_d_appels docker)" -eq 0 ]
}

# noter_couple écrit <instantané>.couple par un fichier temporaire du même dossier, puis `mv -T` :
# un lien planté à la place du .couple est remplacé, jamais suivi, et ce qu'il désigne ne change
# pas. Rien ne reste du fichier temporaire, ni quand l'écriture échoue (un dossier à la place du
# .couple) ; sans deploye, pas de couple ; deploye illisible, pas de couple, code 1.
@test "noter_couple : à côté de l'instantané, jamais à travers un lien" {
  local image sha etat="$VEILLE_EMPLOI_RACINE_ETAT/prod" i ailleurs="$BATS_TEST_TMPDIR/ailleurs"
  image="ghcr.io/edouardzemb/veille-emploi@sha256:$(printf 'a%.0s' {1..64})"
  sha="$(printf 'c%.0s' {1..40})"
  i="$BATS_TEST_TMPDIR/instantanes/veille-emploi-20261014T024500Z"
  mkdir -p "$etat" "$i"
  echo "$image 1.2.3 $sha" >"$etat/deploye"
  echo "à garder" >"$ailleurs"
  ln -s "$ailleurs" "$i.couple"
  avec_lib 'charger_env prod; noter_couple "'"$i"'"'
  [ "$status" -eq 0 ]
  [[ "$output" == *"couple noté : $i.couple ($image 1.2.3 $sha)"* ]]
  [ ! -L "$i.couple" ]
  [ -f "$i.couple" ]
  [ "$(cat "$i.couple")" = "$image 1.2.3 $sha" ]
  [ "$(cat "$ailleurs")" = "à garder" ]
  [ "$(find "$BATS_TEST_TMPDIR/instantanes" -mindepth 1 -maxdepth 1 -printf '%f\n' | LC_ALL=C sort)" \
    = "$(printf '%s\n' "veille-emploi-20261014T024500Z" "veille-emploi-20261014T024500Z.couple")" ]
  # un dossier à la place du .couple : l'écriture échoue, journalisée, et rien ne reste d'elle
  rm "$i.couple"
  mkdir -p "$i.couple/dedans"
  avec_lib 'charger_env prod; noter_couple "'"$i"'"'
  [ "$status" -eq 1 ]
  [[ "$output" == *"$i.couple ne s'écrit pas : l'instantané reste, sans son couple"* ]]
  [ -d "$i.couple/dedans" ]
  [ "$(find "$BATS_TEST_TMPDIR/instantanes" -mindepth 1 -maxdepth 1 | wc -l)" -eq 2 ]
  rm -r "$i.couple"
  # deploye illisible : code 1, pas de couple ; absent : code 0, pas de couple
  echo "pas un couple" >"$etat/deploye"
  avec_lib 'charger_env prod; noter_couple "'"$i"'"'
  [ "$status" -eq 1 ]
  [[ "$output" == *"$etat/deploye illisible : pas de $i.couple"* ]]
  rm "$etat/deploye"
  avec_lib 'charger_env prod; noter_couple "'"$i"'"'
  [ "$status" -eq 0 ]
  [[ "$output" == *"aucun couple en service ($etat/deploye absent) : pas de $i.couple"* ]]
  [ "$(find "$BATS_TEST_TMPDIR/instantanes" -mindepth 1 -maxdepth 1 | wc -l)" -eq 1 ]
}

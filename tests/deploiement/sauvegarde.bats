#!/usr/bin/env bats
# sauvegarder.sh, tester-restauration.sh, restaurer.sh : les trois scripts qui protègent les données
# du projet. Réservés à la prod.
#
# Le contrat de l'instantané : `<SAUVEGARDER…> <dossier>` crée ce dossier, qui a la forme de
# /donnees ; `<VERIFIER…> <dossier>` rend 0 (conforme), 2 (non conforme) ou 64 (usage). Les
# commandes sont celles de deploiement/projet.env ; le setup écrit celles du test.
#
# docker, curl et rclone sont des doubles (tests/deploiement/doubles/) : le double de docker écrit
# les instantanés que la commande de l'image écrirait, le double de rclone tient un « distant »
# dans un dossier du test, et age (le vrai) chiffre pour la clé hors ligne de test. Les doubles
# refusent ce qu'un de ces scripts ne doit jamais faire (code 125) : toucher aux données de la prod
# depuis le test de restauration, publier le port de la prod ou hors de 127.0.0.1, effacer hors
# du dossier du remote.

# Chaque test tourne dans son propre processus : les `export DOUBLE_*` d'un test ne fuient pas
# dans les autres, comme le veut le pilotage des doubles.
# shellcheck disable=SC2030,SC2031

bats_require_minimum_version 1.5.0

load aide

setup() {
  preparer_environnement
  installer_doubles docker curl rclone
  export VEILLE_EMPLOI_SANTE_DELAI=0
  ETAT="$VEILLE_EMPLOI_RACINE_ETAT/prod"
  SAUVEGARDES="$VEILLE_EMPLOI_RACINE_SAUVEGARDES"
  DONNEES="$VEILLE_EMPLOI_RACINE_DONNEES/prod/donnees"
  EN_SERVICE="$BATS_TEST_TMPDIR/en-service.env"
  DISTANT="$BATS_TEST_TMPDIR/distant/sauvegardes/veille-emploi-sauvegardes"
  IMAGE="ghcr.io/edouardzemb/veille-emploi@sha256:$(printf '1%.0s' {1..64})"
  HC_SAUVEGARDE=https://hc.example/ping/sauvegarde-prod
  HC_TEST=https://hc.example/ping/test-restauration-prod
  SNAPSHOT=veille-emploi-20261014T024500Z
  preparer_secrets_de_test prod JETON=jeton-prod-7 \
    "HC_SAUVEGARDE=$HC_SAUVEGARDE" "HC_TEST_RESTAURATION=$HC_TEST"
  en_service prod "$IMAGE" 0.1.0
  # Les commandes de l'image sont celles du test, en plusieurs mots, et non celles que le projet
  # déclare pour la sienne dans deploiement/projet.env.
  printf '%s\n' 'SAUVEGARDER=outil sauvegarder --forme dossier' 'VERIFIER=outil verifier' \
    >"$CLONE/deploiement/projet.env"
}

# Un test qui retire des droits les rend avant que bats ne supprime son dossier.
teardown() {
  abandonner_le_verrou
  chmod -R u+rwX "$BATS_TEST_TMPDIR" 2>/dev/null || true
}

sauvegarder() {
  run bash "$CLONE/deploiement/sauvegarder.sh" "$@"
}

tester() {
  run bash "$CLONE/deploiement/tester-restauration.sh" "$@"
}

restaurer() {
  run bash "$CLONE/deploiement/restaurer.sh" "$@"
}

# dc_prod : le début de chaque appel de compose de la prod, celui de `dc` (lib.sh).
dc_prod() {
  printf 'docker compose -p veille-emploi -f %s -f %s --env-file %s' "$CLONE/deploiement/compose.yml" \
    "$CLONE/deploiement/compose.projet.yml" "$ETAT/compose.env"
}

# instantane <nom> [jours [dossier]] : un instantané local, un dossier qui a la forme de /donnees
# (un fichier, un fichier caché, un sous-dossier), daté de N jours, par défaut dans quotidiennes/.
instantane() {
  local nom="$1" jours="${2:-0}" dossier="${3:-quotidiennes}"
  local chemin="$SAUVEGARDES/$dossier/$nom"
  mkdir -p "$chemin/sous"
  echo "instantané de test $nom" >"$chemin/donnees.txt"
  echo "fichier caché" >"$chemin/.cachee"
  echo "fichier profond" >"$chemin/sous/profond.txt"
  touch -d "$jours days ago" "$chemin/donnees.txt" "$chemin/.cachee" "$chemin/sous/profond.txt" \
    "$chemin/sous" "$chemin"
}

# il_y_a <jours> : l'horodatage UTC d'il y a tant de jours, sous la forme des noms d'instantanés.
il_y_a() {
  date -u -d "$1 days ago" +%Y%m%dT%H%M%SZ
}

# donnees_courantes : les données de la prod en service : un fichier, un fichier caché, un dossier.
donnees_courantes() {
  mkdir -p "$DONNEES/journal"
  echo "contenu courant" >"$DONNEES/courant.txt"
  echo "caché courant" >"$DONNEES/.courant"
  echo "journal courant" >"$DONNEES/journal/entree.txt"
}

# contenu_courant_intact : les données de la prod sont celles de donnees_courantes, ni plus ni moins.
contenu_courant_intact() {
  [ "$(cat "$DONNEES/courant.txt")" = "contenu courant" ]
  [ "$(cat "$DONNEES/.courant")" = "caché courant" ]
  [ "$(cat "$DONNEES/journal/entree.txt")" = "journal courant" ]
  [ "$(nombre_d_entrees "$DONNEES")" -eq 3 ]
}

# chiffrer <archive> : chiffre l'entrée standard pour la clé hors ligne, comme sauvegarder.sh.
chiffrer() {
  age -R "$CLONE_DONNEES/$SOUS_CLES/hors-ligne.pub" >"$1"
}

# envois_ok <adresse> : les appels de curl qui ont signalé un succès à cette adresse ;
# envois_echec <adresse> : ceux qui ont signalé un échec.
envois_ok() {
  envois_supervision | grep -F -- "$1" | grep -vF -- "$1/fail" || true
}

envois_echec() {
  envois_supervision | grep -F -- "$1/fail" || true
}

# aucun_envoi : aucun signal n'est parti.
aucun_envoi() {
  [ -z "$(envois_supervision)" ]
}

# aucun_temporaire : le dossier des fichiers temporaires est vide.
aucun_temporaire() {
  local restes
  restes="$(ls -A "$TMPDIR")"
  [ -z "$restes" ] || {
    echo "fichiers temporaires restants : $restes" >&2
    return 1
  }
}

# nombre_d_entrees <dossier> : combien d'entrées (cachées comprises) dans ce dossier.
nombre_d_entrees() {
  find "$1" -mindepth 1 -maxdepth 1 | wc -l
}

# aucun_dossier_avant_restauration : restaurer.sh n'a laissé aucun avant-restauration-* (un dossier
# vide ne reste pas).
aucun_dossier_avant_restauration() {
  if compgen -G "$SAUVEGARDES/avant-restauration-*" >/dev/null; then
    echo "dossier avant-restauration-* présent" >&2
    return 1
  fi
}

# derniere_ligne_de <motif> : numéro de la dernière ligne du journal des appels qui contient ce texte.
derniere_ligne_de() {
  grep -nF -- "$1" "$APPELS" | tail -n 1 | cut -d: -f1
}

# attendre_appel <nom> : jusqu'à 10 s, que cette commande ait été appelée.
attendre_appel() {
  for _ in {1..100}; do
    [ -z "$(appels_de "$1")" ] || return 0
    sleep 0.1
  done
  echo "jamais appelé : $1" >&2
  return 1
}

# double_mv_en_echec <motif…> : un `mv` qui échoue quand sa source (le premier argument qui n'est
# pas une option) correspond à l'un des motifs, et qui est le vrai sinon.
double_mv_en_echec() {
  local motifs="" motif vrai
  vrai="$(command -v mv)"
  for motif in "$@"; do
    motifs="${motifs:+$motifs | }$motif"
  done
  # shellcheck disable=SC2016  # le corps du double se développe quand il s'exécute, pas ici
  creer_double mv 'source=""
for argument in "$@"; do
  case "$argument" in -*) ;; *) source="$argument"; break ;; esac
done
case "$source" in '"$motifs"') echo "mv: cannot move: Input/output error" >&2; exit 1 ;; esac
exec '"$vrai"' "$@"'
}

# reporter_declare [section] : deploiement/projet.env déclare la commande REPORTER du test, en deux
# mots, et, si elle est donnée, la section du runbook qui dit comment reporter à la main.
reporter_declare() {
  printf '%s\n' 'REPORTER=outil reporter' >>"$CLONE/deploiement/projet.env"
  [ -z "${1:-}" ] || printf 'REPORTER_SECTION=%s\n' "$1" >>"$CLONE/deploiement/projet.env"
}

# sans_horodatage : la sortie du dernier `run`, sans l'heure du journal en tête de ligne, et les
# horodatages des dossiers datés de la restauration remplacés par <horodatage>.
sans_horodatage() {
  printf '%s\n' "$output" | sed -E -e 's/^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z //' \
    -e 's/(avant-restauration|report)-[0-9]{8}T[0-9]{6}Z/\1-<horodatage>/g'
}

# aucune_copie_jetable : aucune copie jetable des données en service (report-*) ne reste dans le
# dossier des sauvegardes.
aucune_copie_jetable() {
  if compgen -G "$SAUVEGARDES/report-*" >/dev/null; then
    echo "copie jetable restante : $(ls -d "$SAUVEGARDES"/report-*)" >&2
    return 1
  fi
}

# ==============================================================================================
# Les trois scripts : prod seulement
# ==============================================================================================

@test "staging_refuse" {
  instantane "$SNAPSHOT"
  local script
  for script in sauvegarder.sh tester-restauration.sh; do
    run bash "$CLONE/deploiement/$script" staging
    [ "$status" -eq 64 ]
    [[ "$output" == *"$script est réservé à la prod"* ]]
  done
  restaurer staging "$SAUVEGARDES/quotidiennes/$SNAPSHOT" --oui
  [ "$status" -eq 64 ]
  [[ "$output" == *"restaurer.sh est réservé à la prod"* ]]
  # rien n'a été créé, rien n'a été appelé, aucun signal
  [ ! -e "$VEILLE_EMPLOI_RACINE_ETAT/staging" ]
  [ ! -e "$VEILLE_EMPLOI_RACINE_DONNEES/staging" ]
  [ -z "$(appels_de docker)" ]
  [ -z "$(appels_de rclone)" ]
  aucun_envoi
}

@test "les_scripts_refusent_un_usage_incorrect" {
  run bash "$CLONE/deploiement/sauvegarder.sh"
  [ "$status" -eq 64 ]
  run bash "$CLONE/deploiement/sauvegarder.sh" prod en-trop
  [ "$status" -eq 64 ]
  run bash "$CLONE/deploiement/tester-restauration.sh" dev
  [ "$status" -eq 64 ]
  run bash "$CLONE/deploiement/tester-restauration.sh"
  [ "$status" -eq 64 ]
  run bash "$CLONE/deploiement/restaurer.sh"
  [ "$status" -eq 64 ]
  run bash "$CLONE/deploiement/restaurer.sh" prod
  [ "$status" -eq 64 ]
  [ -z "$(appels_de docker)" ]
  aucun_envoi
}

# ==============================================================================================
# sauvegarder.sh
# ==============================================================================================

@test "sauvegarde_chiffre_pour_la_cle_hors_ligne_et_envoie" {
  sauvegarder prod
  [ "$status" -eq 0 ]

  # une seule archive au distant, chiffrée, nommée veille-emploi-<horodatage UTC> (son couple chiffré
  # est à côté : voir « sauvegarde : le couple voisin, local et distant »)
  local envoyes=("$DISTANT"/*.tar.age)
  [ "${#envoyes[@]}" -eq 1 ]
  local nom
  nom="$(basename "${envoyes[0]}" .tar.age)"
  [[ "$nom" =~ ^veille-emploi-[0-9]{8}T[0-9]{6}Z$ ]]
  [ "${envoyes[0]}" = "$DISTANT/$nom.tar.age" ]
  [ "$(head -c 21 "${envoyes[0]}")" = age-encryption.org/v1 ]

  # la clé hors ligne la déchiffre : l'instantané, à l'identique
  age -d -i "$AGE_IDENTITE_HORS_LIGNE" -o "$BATS_TEST_TMPDIR/clair.tar" "${envoyes[0]}"
  mkdir "$BATS_TEST_TMPDIR/extrait"
  tar -xf "$BATS_TEST_TMPDIR/clair.tar" -C "$BATS_TEST_TMPDIR/extrait"
  diff -r "$BATS_TEST_TMPDIR/extrait/$nom" "$SAUVEGARDES/quotidiennes/$nom"

  # la clé du serveur ne la déchiffre pas : elle ne peut pas lire les sauvegardes hors site
  run ! age -d -i "$AGE_IDENTITE_SERVEUR" -o "$BATS_TEST_TMPDIR/interdit.tar" "${envoyes[0]}"
  [ ! -s "$BATS_TEST_TMPDIR/interdit.tar" ]

  # l'instantané se fait dans le conteneur, par le projet et le compose.env de la prod
  appels_de docker | grep -Fx "$(dc_prod) exec -T app outil sauvegarder --forme dossier /sauvegardes/quotidiennes/$nom.partiel"
  # l'archive chiffrée part, puis sa présence est contrôlée
  appels_de rclone | grep -E "^rclone copy $TMPDIR/veille-emploi-sauvegarde\.[A-Za-z0-9]+/$nom\.tar\.age sauvegardes:veille-emploi-sauvegardes$"
  [ "$(ligne_de 'rclone copy')" -lt "$(ligne_de 'rclone lsf')" ]
  appels_de rclone | grep -Fx 'rclone lsf --files-only sauvegardes:veille-emploi-sauvegardes'
  # le clair ne part jamais : seuls l'archive et son couple chiffrés passent à rclone, jamais
  # l'instantané
  [ "$(appels_de rclone | grep -c '^rclone copy ')" -eq 2 ]
  aucune_ligne 'quotidiennes' <(appels_de rclone)

  # signal de succès : nom et nombre de fichiers de l'instantané ; aucun échec
  [ "$(envois_ok "$HC_SAUVEGARDE")" = "curl -fsS -m 10 --retry 3 --data-raw $nom : 3 fichiers $HC_SAUVEGARDE" ]
  [ -z "$(envois_echec "$HC_SAUVEGARDE")" ]
  [ -z "$(envois_ok "$HC_TEST")$(envois_echec "$HC_TEST")" ]
  aucun_temporaire
  # la copie locale reste, lisible par son seul propriétaire (M-0005)
  [ -d "$SAUVEGARDES/quotidiennes/$nom" ]
  [ "$(stat -c %a "$SAUVEGARDES")" = 700 ]
  [ "$(stat -c %a "$SAUVEGARDES/quotidiennes")" = 700 ]
}

# Le contrat de l'instantané : `<SAUVEGARDER…> <dossier>` crée ce dossier, qui a la forme de
# /donnees. La commande est celle de projet.env, passée mot à mot. Le dossier qu'elle reçoit est
# provisoire, /sauvegardes/quotidiennes/<nom>-<horodatage>.partiel (R13) : le script ne lui donne son
# nom qu'une fois l'instantané contrôlé.
@test "sauvegarde_dossier_instantane" {
  sauvegarder prod
  [ "$status" -eq 0 ]
  # l'instantané, et son couple à côté (M-0005, § 2)
  local instantanes=("$SAUVEGARDES"/quotidiennes/*)
  [ "${#instantanes[@]}" -eq 2 ]
  [ "${instantanes[1]}" = "${instantanes[0]}.couple" ]
  local nom="${instantanes[0]##*/}"
  [[ "$nom" =~ ^veille-emploi-[0-9]{8}T[0-9]{6}Z$ ]]
  # un dossier, au contenu de /donnees, fichiers cachés et sous-dossiers compris
  [ -d "${instantanes[0]}" ]
  [ "$(cat "${instantanes[0]}/donnees.txt")" = "instantané de test $nom" ]
  [ -f "${instantanes[0]}/.cachee" ]
  [ -f "${instantanes[0]}/sous/profond.txt" ]
  # la commande de projet.env, mot à mot, puis la destination provisoire, renommée ensuite
  [ "$(cat "$BATS_TEST_TMPDIR/exec-mots")" = "$(printf '%s\n' outil sauvegarder --forme dossier "/sauvegardes/quotidiennes/$nom.partiel")" ]
  [ ! -e "$SAUVEGARDES/quotidiennes/$nom.partiel" ]
  [[ "$output" == *"instantané : $SAUVEGARDES/quotidiennes/$nom (3 fichiers)"* ]]
}

# R13 : une sauvegarde en échec garde son nom provisoire, <nom>-<horodatage>.partiel, pour le
# diagnostic : rien ne la prend jamais pour un instantané complet, et aucun nom définitif n'apparaît.
@test "sauvegarde_en_echec_laisse_un_partiel" {
  local forme entrees
  # la commande écrit une partie, puis échoue ; ou rend 0 sur un dossier vide
  for forme in partielle vide; do
    DOUBLE_DOCKER_SAUVEGARDE_FORME="$forme" sauvegarder prod
    [ "$status" -eq 1 ]
    entrees=("$SAUVEGARDES"/quotidiennes/*)
    [ "${#entrees[@]}" -eq 1 ]
    [[ "${entrees[0]##*/}" =~ ^veille-emploi-[0-9]{8}T[0-9]{6}Z\.partiel$ ]]
    [ -d "${entrees[0]}" ]
    [ "$forme" != partielle ] || [ -f "${entrees[0]}/donnees.txt" ]
    rm -rf "$SAUVEGARDES/quotidiennes"
  done
  [ "$(envois_echec "$HC_SAUVEGARDE" | wc -l)" -eq 2 ]
  [ -z "$(envois_ok "$HC_SAUVEGARDE")" ]
  [ -z "$(appels_de rclone)" ]
}

# Seule la dernière sauvegarde en échec garde son .partiel. Chaque nuit en échec laisserait
# sinon une copie en clair de plus, que la rétention, qui ne tourne qu'après un envoi réussi,
# n'efface jamais. Avant chaque instantané, les .partiel de quotidiennes/ sont retirés. Une
# sauvegarde complète, ou un nom d'une autre forme, ne part jamais, et un lien n'est pas suivi.
@test "sauvegarde_ne_garde_que_le_dernier_partiel" {
  local q="$SAUVEGARDES/quotidiennes" complet ailleurs nom partiels _
  local autres=()
  complet="veille-emploi-$(il_y_a 1)"
  instantane "$complet"
  autres=("$complet.partiel.copie" autre.partiel "x$complet.partiel" "autre-projet-$(il_y_a 2).partiel")
  for nom in "${autres[@]}"; do
    mkdir -p "$q/$nom"
    echo "$nom" >"$q/$nom/donnees.txt"
  done
  # un ancien .partiel qui est un fichier part aussi ; un lien au nom d'un .partiel reste, et ce
  # qu'il désigne n'est pas touché
  echo "fichier" >"$q/veille-emploi-$(il_y_a 3).partiel"
  ailleurs="$BATS_TEST_TMPDIR/ailleurs"
  mkdir -p "$ailleurs"
  echo "à garder" >"$ailleurs/donnees.txt"
  ln -s "$ailleurs" "$q/veille-emploi-$(il_y_a 4).partiel"
  horloge_qui_avance
  for _ in 1 2; do
    DOUBLE_DOCKER_SAUVEGARDE_FORME=partielle sauvegarder prod
    [ "$status" -eq 1 ]
    [[ "$output" == *"instantané impossible (code 1)"* ]]
  done
  # un seul .partiel qui ne soit pas un lien : celui de la seconde nuit, intact
  partiels="$(find "$q" -mindepth 1 -maxdepth 1 ! -type l -regextype posix-extended \
    -regex '.*/veille-emploi-[0-9]{8}T[0-9]{6}Z\.partiel')"
  [ "$partiels" = "$q/veille-emploi-$(jour_de_l_horloge)T000002Z.partiel" ]
  [ -f "$q/veille-emploi-$(jour_de_l_horloge)T000002Z.partiel/donnees.txt" ]
  # la sauvegarde complète et les autres noms restent, en entier ; le lien et sa cible aussi
  [ "$(cat "$q/$complet/donnees.txt")" = "instantané de test $complet" ]
  [ -f "$q/$complet/sous/profond.txt" ]
  for nom in "${autres[@]}"; do
    [ "$(cat "$q/$nom/donnees.txt")" = "$nom" ]
  done
  [ "$(find "$q" -mindepth 1 -maxdepth 1 -type l | wc -l)" -eq 1 ]
  [ "$(cat "$ailleurs/donnees.txt")" = "à garder" ]
  [ "$(nombre_d_entrees "$q")" -eq 7 ]
  [ -z "$(appels_de rclone)" ]
  [ "$(envois_echec "$HC_SAUVEGARDE" | wc -l)" -eq 2 ]
}

# R67 : une restauration tuée de force (SIGKILL, plantage de l'hôte) laisse, hors de portée de son
# piège, la copie jetable du report (les données en service, en clair, sans rétention) et la copie
# de travail des données. La sauvegarde tient le verrou de la restauration : ce qu'elle trouve n'est
# à aucune restauration en cours, et elle le retire avant l'instantané. Rien d'autre : ni un nom
# d'une autre forme, ni un lien, ni ce qu'il désigne.
@test "sauvegarde_retire_les_restes_d_une_restauration_interrompue" {
  local reste="$SAUVEGARDES/report-20261001T000000Z" ailleurs="$BATS_TEST_TMPDIR/ailleurs" nom
  local autres=(report-20261001 report-20261001T000000Z.garde mon-report-20261001T000000Z)
  # la copie jetable, avec un sous-dossier que la commande du report a laissé en lecture seule
  mkdir -p "$reste/sous" "$DONNEES.nouvelle/sous"
  echo "copie oubliée" >"$reste/courant.txt"
  echo "profond" >"$reste/sous/profond.txt"
  chmod 500 "$reste/sous"
  echo "copie de travail" >"$DONNEES.nouvelle/donnees.txt"
  for nom in "${autres[@]}"; do
    mkdir -p "$SAUVEGARDES/$nom"
    echo "$nom" >"$SAUVEGARDES/$nom/donnees.txt"
  done
  mkdir -p "$ailleurs"
  echo "à garder" >"$ailleurs/donnees.txt"
  ln -s "$ailleurs" "$SAUVEGARDES/report-20261002T000000Z"
  horloge_qui_avance
  sauvegarder prod
  [ "$status" -eq 0 ]
  [ ! -e "$reste" ]
  [ ! -e "$DONNEES.nouvelle" ]
  [[ "$output" == *"reste d'une restauration interrompue retiré : $reste"* ]]
  [[ "$output" == *"reste d'une restauration interrompue retiré : $DONNEES.nouvelle"* ]]
  # avant l'instantané, donc sous le verrou
  [[ "$output" == *"reste d'une restauration interrompue retiré"*"instantané : "* ]]
  # les autres noms, le lien et ce qu'il désigne restent
  for nom in "${autres[@]}"; do
    [ "$(cat "$SAUVEGARDES/$nom/donnees.txt")" = "$nom" ]
  done
  [ -L "$SAUVEGARDES/report-20261002T000000Z" ]
  [ "$(cat "$ailleurs/donnees.txt")" = "à garder" ]
  # une copie de travail qui est un lien n'est pas suivie, et reste ; sans reste, rien n'est dit
  ln -s "$ailleurs" "$DONNEES.nouvelle"
  sauvegarder prod
  [ "$status" -eq 0 ]
  [ -L "$DONNEES.nouvelle" ]
  [ "$(cat "$ailleurs/donnees.txt")" = "à garder" ]
  [[ "$output" != *"reste d'une restauration interrompue"* ]]
}

# Un .partiel qui ne peut pas être retiré est journalisé, et la sauvegarde se fait quand même.
@test "sauvegarde_se_fait_meme_si_un_ancien_partiel_ne_part_pas" {
  local q="$SAUVEGARDES/quotidiennes" ancien
  ancien="veille-emploi-$(il_y_a 1).partiel"
  mkdir -p "$q/$ancien/verrouille"
  echo "reste" >"$q/$ancien/verrouille/donnees.txt"
  # un sous-dossier sans droit d'écriture : rm -rf ne peut pas le vider (teardown rend les droits)
  chmod 500 "$q/$ancien/verrouille"
  sauvegarder prod
  [ "$status" -eq 0 ]
  [[ "$output" == *"sauvegardes en échec de $q : retrait impossible"* ]]
  [ -f "$q/$ancien/verrouille/donnees.txt" ]
  # l'archive et son couple
  [ "$(nombre_d_entrees "$DISTANT")" -eq 2 ]
  [ "$(envois_ok "$HC_SAUVEGARDE" | wc -l)" -eq 1 ]
  [ -z "$(envois_echec "$HC_SAUVEGARDE")" ]
}

# Une destination déjà présente, sous son nom définitif ou provisoire, est une erreur : rien n'est
# écrasé, et la commande n'est pas lancée.
@test "sauvegarde_ne_reutilise_jamais_une_destination" {
  local vrai existant
  vrai="$(command -v date)"
  # shellcheck disable=SC2016  # le corps du double se développe quand il s'exécute, pas ici
  creer_double date 'if [ "$*" = "-u +%Y%m%dT%H%M%SZ" ]; then echo 20261018T024500Z; else exec '"$vrai"' "$@"; fi'
  for existant in veille-emploi-20261018T024500Z veille-emploi-20261018T024500Z.partiel; do
    mkdir -p "$SAUVEGARDES/quotidiennes/$existant"
    echo "déjà là" >"$SAUVEGARDES/quotidiennes/$existant/donnees.txt"
    sauvegarder prod
    [ "$status" -eq 1 ]
    [[ "$output" == *"existe déjà"* ]]
    [ "$(cat "$SAUVEGARDES/quotidiennes/$existant/donnees.txt")" = "déjà là" ]
    rm -rf "$SAUVEGARDES/quotidiennes"
  done
  [ -z "$(appels_de docker | grep ' exec ' || true)" ]
  [ "$(envois_echec "$HC_SAUVEGARDE" | wc -l)" -eq 2 ]
}

# I1 : un instantané où deux noms sont un même fichier (un lien physique). tar le stockerait comme un
# lien (type h), que restaurer.sh refuse : l'archive se fait avec --hard-dereference, et la
# restauration rend les deux noms, au même contenu.
@test "sauvegarde_liens_physiques_archive_restaurable" {
  DOUBLE_DOCKER_SAUVEGARDE_FORME=physique sauvegarder prod
  [ "$status" -eq 0 ]
  local envoyes=("$DISTANT"/*.tar.age) nom
  nom="$(basename "${envoyes[0]}" .tar.age)"
  age -d -i "$AGE_IDENTITE_HORS_LIGNE" -o "$BATS_TEST_TMPDIR/clair.tar" "${envoyes[0]}"
  # que des fichiers et des dossiers dans l'archive
  [ -z "$(tar -tvf "$BATS_TEST_TMPDIR/clair.tar" | cut -c1 | grep -v '^[-d]$' || true)" ]
  donnees_courantes
  restaurer prod "${envoyes[0]}" --oui --cle "$AGE_IDENTITE_HORS_LIGNE"
  [ "$status" -eq 0 ]
  diff -r "$SAUVEGARDES/quotidiennes/$nom" "$DONNEES"
  [ "$(cat "$DONNEES/sous/physique.txt")" = "instantané de test $nom" ]
}

# L'archive : `tar -C quotidiennes -cf - <nom> | age -R cles/hors-ligne.pub`. Tous ses membres sont
# sous un seul dossier, <nom>/, et ce sont des fichiers ou des dossiers : la forme que restaurer.sh
# exige.
@test "sauvegarde_archive_un_seul_dossier" {
  sauvegarder prod
  [ "$status" -eq 0 ]
  local envoyes=("$DISTANT"/*.tar.age) nom membre
  nom="$(basename "${envoyes[0]}" .tar.age)"
  age -d -i "$AGE_IDENTITE_HORS_LIGNE" -o "$BATS_TEST_TMPDIR/clair.tar" "${envoyes[0]}"
  # le premier membre est le dossier, et tous les autres sont dessous
  [ "$(tar -tf "$BATS_TEST_TMPDIR/clair.tar" | head -n 1)" = "$nom/" ]
  while IFS= read -r membre; do
    [[ "$membre" == "$nom/"* ]] || {
      echo "membre hors du dossier : $membre" >&2
      return 1
    }
  done < <(tar -tf "$BATS_TEST_TMPDIR/clair.tar")
  [ "$(tar -tf "$BATS_TEST_TMPDIR/clair.tar" | sort)" = "$(printf '%s\n' "$nom/" "$nom/.cachee" "$nom/donnees.txt" "$nom/sous/" "$nom/sous/profond.txt" | sort)" ]
  [ -z "$(tar -tvf "$BATS_TEST_TMPDIR/clair.tar" | cut -c1 | grep -v '^[-d]$' || true)" ]
}

# M-0005, § 2 : l'instantané note le couple en service, celui de deploye au moment de
# l'instantané, dans <nom>.couple, à côté de lui et jamais dedans : son contenu et les membres de son
# archive ne changent pas. La sauvegarde l'envoie chiffré pour la clé hors ligne, <nom>.couple.age,
# à la date de l'archive : la purge distante les voit du même âge. Un état d'avant la v0.7.0 donne
# le commit « - » ; sans deploye, ou s'il ne se lit pas, aucun couple n'est noté, et la sauvegarde
# a lieu.
@test "sauvegarde : le couple voisin, local et distant" {
  local q="$SAUVEGARDES/quotidiennes" commit nom envoyes
  commit="$(printf 'c%.0s' {1..40})"
  echo "$IMAGE 0.1.0 $commit" >"$ETAT/deploye"
  sauvegarder prod
  [ "$status" -eq 0 ]
  envoyes=("$DISTANT"/*.tar.age)
  [ "${#envoyes[@]}" -eq 1 ]
  nom="$(basename "${envoyes[0]}" .tar.age)"
  [[ "$output" == *"couple noté : $q/$nom.couple ($IMAGE 0.1.0 $commit)"* ]]
  # en local : l'instantané et son couple, rien d'autre ; l'instantané a la forme de /donnees
  [ "$(find "$q" -mindepth 1 -maxdepth 1 -printf '%f\n' | LC_ALL=C sort)" = "$(printf '%s\n' "$nom" "$nom.couple")" ]
  [ "$(cat "$q/$nom.couple")" = "$IMAGE 0.1.0 $commit" ]
  [ "$(cd "$q/$nom" && find . -mindepth 1 | LC_ALL=C sort)" = "$(printf '%s\n' ./.cachee ./donnees.txt ./sous ./sous/profond.txt)" ]
  # au distant : l'archive et son couple chiffré, à la même date, et rien d'autre
  [ "$(find "$DISTANT" -mindepth 1 -maxdepth 1 -printf '%f\n' | LC_ALL=C sort)" = "$(printf '%s\n' "$nom.couple.age" "$nom.tar.age")" ]
  [ "$(head -c 21 "$DISTANT/$nom.couple.age")" = age-encryption.org/v1 ]
  [ "$(age -d -i "$AGE_IDENTITE_HORS_LIGNE" "$DISTANT/$nom.couple.age")" = "$IMAGE 0.1.0 $commit" ]
  [ "$(stat -c %y "$DISTANT/$nom.couple.age")" = "$(stat -c %y "$DISTANT/$nom.tar.age")" ]
  # l'archive n'a pas changé : un seul dossier, les mêmes membres, sans le couple
  age -d -i "$AGE_IDENTITE_HORS_LIGNE" -o "$BATS_TEST_TMPDIR/clair.tar" "$DISTANT/$nom.tar.age"
  [ "$(tar -tf "$BATS_TEST_TMPDIR/clair.tar" | LC_ALL=C sort)" = "$(printf '%s\n' "$nom/" "$nom/.cachee" "$nom/donnees.txt" "$nom/sous/" "$nom/sous/profond.txt")" ]
  # le couple part chiffré, du dossier temporaire, après l'archive et avant le contrôle ; le clair
  # ne part jamais
  appels_de rclone | grep -E "^rclone copy $TMPDIR/veille-emploi-sauvegarde\.[A-Za-z0-9]+/$nom\.couple\.age sauvegardes:veille-emploi-sauvegardes$"
  [ "$(ligne_de "/$nom.tar.age sauvegardes:")" -lt "$(ligne_de "/$nom.couple.age sauvegardes:")" ]
  [ "$(ligne_de "/$nom.couple.age sauvegardes:")" -lt "$(ligne_de 'rclone lsf')" ]
  aucune_ligne '\.couple( |$)' <(appels_de rclone)
  aucune_ligne 'quotidiennes' <(appels_de rclone)
  aucun_temporaire
  # la clé du serveur ne lit pas le couple
  run ! age -d -i "$AGE_IDENTITE_SERVEUR" "$DISTANT/$nom.couple.age"

  # un état d'avant la v0.7.0, à deux champs : le commit vaut « - »
  echo "$IMAGE 0.1.0" >"$ETAT/deploye"
  rm -rf "$q" "$DISTANT"
  sauvegarder prod
  [ "$status" -eq 0 ]
  envoyes=("$DISTANT"/*.tar.age)
  nom="$(basename "${envoyes[0]}" .tar.age)"
  [ "$(cat "$q/$nom.couple")" = "$IMAGE 0.1.0 -" ]
  [ "$(age -d -i "$AGE_IDENTITE_HORS_LIGNE" "$DISTANT/$nom.couple.age")" = "$IMAGE 0.1.0 -" ]

  # deploye illisible, puis absent : aucun couple, ni en local ni au distant ; la sauvegarde a lieu
  local cas
  for cas in illisible absent; do
    rm -rf "$q" "$DISTANT"
    if [ "$cas" = illisible ]; then
      echo "pas un couple" >"$ETAT/deploye"
    else
      rm "$ETAT/deploye"
    fi
    sauvegarder prod
    [ "$status" -eq 0 ]
    envoyes=("$DISTANT"/*.tar.age)
    nom="$(basename "${envoyes[0]}" .tar.age)"
    [ "$(ls -A "$q")" = "$nom" ]
    [ "$(ls -A "$DISTANT")" = "$nom.tar.age" ]
    if [ "$cas" = illisible ]; then
      [[ "$output" == *"$ETAT/deploye illisible : pas de $q/$nom.couple"* ]]
    else
      [[ "$output" == *"aucun couple en service ($ETAT/deploye absent) : pas de $q/$nom.couple"* ]]
    fi
  done
  [ "$(envois_ok "$HC_SAUVEGARDE" | wc -l)" -eq 4 ]
  [ -z "$(envois_echec "$HC_SAUVEGARDE")" ]
}

# Les données passent avant leur couple : un couple qui ne se chiffre pas, ou qui ne prend pas la
# date de l'archive, est journalisé ; l'archive part seule, contrôlée, la rétention a lieu, et la
# nuit est signalée en échec à la fin, la raison dite. Le .couple local reste, avec son instantané.
@test "sauvegarde : un couple en échec n'empêche pas l'archive de partir" {
  local q="$SAUVEGARDES/quotidiennes" envoyes nom cas reel
  echo "$IMAGE 0.1.0 -" >"$ETAT/deploye"
  for cas in age touch; do
    echo "cas : $cas"
    rm -rf "$q" "$DISTANT" "${DOUBLES:?}/age" "$DOUBLES/touch"
    # le double du cas précédent est parti : bash ne doit plus le chercher là
    hash -r
    : >"$APPELS"
    : >"$APPELS.urls"
    reel="$(command -v "$cas")"
    # le double refuse ce qui vise le couple, et laisse passer le reste au vrai ; son corps se
    # développe dans le double, pas ici
    # shellcheck disable=SC2016
    creer_double "$cas" 'for a in "$@"; do case "$a" in *.couple | *.couple.age) echo "'"$cas"' : refus du double" >&2; exit 1 ;; esac; done; exec '"$reel"' "$@"'
    sauvegarder prod
    [ "$status" -eq 1 ]
    envoyes=("$DISTANT"/*.tar.age)
    [ "${#envoyes[@]}" -eq 1 ]
    nom="$(basename "${envoyes[0]}" .tar.age)"
    # l'archive seule au distant, contrôlée, et qui se déchiffre
    [ "$(find "$DISTANT" -mindepth 1 -maxdepth 1 -printf '%f\n')" = "$nom.tar.age" ]
    age -d -i "$AGE_IDENTITE_HORS_LIGNE" -o "$BATS_TEST_TMPDIR/clair.tar" "$DISTANT/$nom.tar.age"
    [ "$(appels_de rclone | grep -c '^rclone copy ')" -eq 1 ]
    appels_de rclone | grep -Fx 'rclone lsf --files-only sauvegardes:veille-emploi-sauvegardes'
    # la rétention a eu lieu
    appels_de rclone | grep -q '^rclone delete '
    # en local, l'instantané et son couple
    [ "$(cat "$q/$nom.couple")" = "$IMAGE 0.1.0 -" ]
    [ -d "$q/$nom" ]
    sans_horodatage | sed -E 's/-sauvegarde\.[A-Za-z0-9]+\//-sauvegarde.<tmp>\//' >"$BATS_TEST_TMPDIR/journal"
    if [ "$cas" = age ]; then
      grep -Fx "chiffrement du couple impossible (age -R $CLONE_DONNEES/$SOUS_CLES/hors-ligne.pub) : l'archive part sans son couple" "$BATS_TEST_TMPDIR/journal"
    else
      grep -Fx "le couple $TMPDIR/veille-emploi-sauvegarde.<tmp>/$nom.couple.age ne prend pas la date de l'archive : l'archive part sans son couple" "$BATS_TEST_TMPDIR/journal"
    fi
    grep -Fx "envoyé : $nom.tar.age vers sauvegardes:veille-emploi-sauvegardes" "$BATS_TEST_TMPDIR/journal"
    [[ "$output" == *"sauvegarde $nom faite et envoyée, mais sans son couple"* ]]
    [ -z "$(envois_ok "$HC_SAUVEGARDE")" ]
    [ "$(envois_echec "$HC_SAUVEGARDE" | wc -l)" -eq 1 ]
    aucun_temporaire
  done
}

# Migration 5 : par défaut, les archives vont vers l'alias sauvegardes:, que le serveur fait pointer
# vers le vrai remote, dans le dossier du projet.
@test "sauvegarde_vers_l_alias_sauvegardes" {
  unset VEILLE_EMPLOI_DISTANT
  sauvegarder prod
  [ "$status" -eq 0 ]
  # copie de l'archive et de son couple, contrôle, rétention : tous visent
  # sauvegardes:veille-emploi-sauvegardes, et rien d'autre
  [ "$(appels_de rclone | wc -l)" -eq 4 ]
  [ -z "$(appels_de rclone | grep -v ' sauvegardes:veille-emploi-sauvegardes$' || true)" ]
  local envoyes=("$BATS_TEST_TMPDIR"/distant/sauvegardes/veille-emploi-sauvegardes/veille-emploi-*.tar.age)
  [ "${#envoyes[@]}" -eq 1 ]
  [ -f "${envoyes[0]}" ]
  [ "$(ls -A "$BATS_TEST_TMPDIR/distant")" = sauvegardes ]
}

@test "sauvegarde_envoie_vers_le_distant_configure" {
  export VEILLE_EMPLOI_DISTANT=sauvegardes:veille-emploi-sauvegardes/essai
  sauvegarder prod
  [ "$status" -eq 0 ]
  local envoyes=("$DISTANT"/essai/veille-emploi-*.tar.age)
  [ "${#envoyes[@]}" -eq 1 ]
  [ -f "${envoyes[0]}" ]
  appels_de rclone | grep -E " sauvegardes:veille-emploi-sauvegardes/essai$"
  # rien dans le dossier par défaut : seul le sous-dossier demandé a reçu quelque chose
  [ "$(nombre_d_entrees "$DISTANT")" -eq 1 ]
}

@test "sauvegarde_signale_un_echec_d_envoi" {
  export DOUBLE_RCLONE_COPY_CODE=1
  sauvegarder prod
  [ "$status" -eq 1 ]
  [[ "$output" == *"envoi vers sauvegardes:veille-emploi-sauvegardes impossible"* ]]
  [ -z "$(envois_ok "$HC_SAUVEGARDE")" ]
  [ "$(envois_echec "$HC_SAUVEGARDE" | wc -l)" -eq 1 ]
  envois_echec "$HC_SAUVEGARDE" | grep -F -- '--data-raw'
  envois_echec "$HC_SAUVEGARDE" | grep -F "envoi"
  # rien n'est parti, ni la rétention : on ne supprime pas quand l'envoi a échoué
  [ ! -e "$DISTANT" ]
  [ -z "$(appels_de rclone | grep delete || true)" ]
  aucun_temporaire
}

@test "sauvegarde_signale_un_envoi_introuvable_au_distant" {
  export DOUBLE_RCLONE_COPY_PERDU=1
  sauvegarder prod
  [ "$status" -eq 1 ]
  [[ "$output" == *"absente de sauvegardes:veille-emploi-sauvegardes"* ]]
  [ -z "$(envois_ok "$HC_SAUVEGARDE")" ]
  [ "$(envois_echec "$HC_SAUVEGARDE" | wc -l)" -eq 1 ]
  [ -z "$(appels_de rclone | grep delete || true)" ]
  aucun_temporaire
}

@test "sauvegarde_signale_un_controle_d_envoi_impossible" {
  export DOUBLE_RCLONE_LSF_CODE=1
  sauvegarder prod
  [ "$status" -eq 1 ]
  [ "$(envois_echec "$HC_SAUVEGARDE" | wc -l)" -eq 1 ]
  [ -z "$(envois_ok "$HC_SAUVEGARDE")" ]
}

@test "sauvegarde_refuse_sans_cle_publique_et_n_envoie_rien" {
  rm "$CLONE_DONNEES/$SOUS_CLES/hors-ligne.pub"
  sauvegarder prod
  [ "$status" -eq 1 ]
  [[ "$output" == *"hors-ligne.pub"* ]]
  [ "$(envois_echec "$HC_SAUVEGARDE" | wc -l)" -eq 1 ]
  [ -z "$(envois_ok "$HC_SAUVEGARDE")" ]
  # ni instantané en clair ni envoi : la clé se contrôle avant tout
  [ -z "$(appels_de rclone)" ]
  [ -z "$(appels_de docker | grep ' exec ' || true)" ]
  aucun_temporaire
}

@test "sauvegarde_refuse_une_cle_publique_vide" {
  : >"$CLONE_DONNEES/$SOUS_CLES/hors-ligne.pub"
  sauvegarder prod
  [ "$status" -eq 1 ]
  [ "$(envois_echec "$HC_SAUVEGARDE" | wc -l)" -eq 1 ]
  [ -z "$(appels_de rclone)" ]
}

@test "sauvegarde_refuse_une_cle_privee_a_la_place_de_la_cle_publique" {
  cp "$AGE_IDENTITE_HORS_LIGNE" "$CLONE_DONNEES/$SOUS_CLES/hors-ligne.pub"
  sauvegarder prod
  [ "$status" -eq 1 ]
  [[ "$output" == *"clé privée"* ]]
  [ "$(envois_echec "$HC_SAUVEGARDE" | wc -l)" -eq 1 ]
  [ -z "$(appels_de rclone)" ]
  # la clé privée n'est pas recopiée dans le journal
  aucune_ligne 'AGE-SECRET-KEY' <(printf '%s\n' "$output")
}

# La commande vient de projet.env : sans elle, rien n'est tenté, et l'échec est signalé.
@test "sauvegarde_sans_commande_sauvegarder_ne_fait_rien" {
  printf '%s\n' 'VERIFIER=outil verifier' >"$CLONE/deploiement/projet.env"
  sauvegarder prod
  [ "$status" -eq 1 ]
  [[ "$output" == *"réglage SAUVEGARDER absent"* ]]
  [[ "$output" == *"commande SAUVEGARDER introuvable"* ]]
  [ "$(envois_echec "$HC_SAUVEGARDE" | wc -l)" -eq 1 ]
  [ -z "$(appels_de docker)" ]
  [ -z "$(appels_de rclone)" ]
  [ ! -e "$SAUVEGARDES/quotidiennes" ]
}

@test "sauvegarde_signale_un_instantane_impossible" {
  export DOUBLE_DOCKER_SAUVEGARDE_CODE=1
  export DOUBLE_DOCKER_SAUVEGARDE_SORTIE='données introuvables : /donnees'
  sauvegarder prod
  [ "$status" -eq 1 ]
  [[ "$output" == *"données introuvables"* ]]
  [ "$(envois_echec "$HC_SAUVEGARDE" | wc -l)" -eq 1 ]
  [ -z "$(envois_ok "$HC_SAUVEGARDE")" ]
  [ -z "$(appels_de rclone)" ]
  aucun_temporaire
}

# Code 0, mais ce qui est sur le disque n'est pas un instantané : un dossier vide (il ne prouve
# rien), un fichier à la place du dossier, ou un dossier qui contient un lien (restaurer.sh
# refuserait son archive).
@test "sauvegarde_ne_fait_pas_confiance_au_seul_code_de_sortie" {
  local forme
  for forme in vide fichier lien; do
    DOUBLE_DOCKER_SAUVEGARDE_FORME="$forme" sauvegarder prod
    [ "$status" -eq 1 ]
    case "$forme" in
      vide) [[ "$output" == *"instantané vide"* ]] ;;
      fichier) [[ "$output" == *"instantané absent du disque"* ]] ;;
      lien) [[ "$output" == *"ni des fichiers ni des dossiers"* ]] ;;
    esac
    rm -rf "$SAUVEGARDES/quotidiennes"
  done
  [ "$(envois_echec "$HC_SAUVEGARDE" | wc -l)" -eq 3 ]
  [ -z "$(envois_ok "$HC_SAUVEGARDE")" ]
  [ -z "$(appels_de rclone)" ]
}

# Seul le code compte (migration 4) : une sortie que le script ne comprend pas ne l'arrête pas, et
# va au journal.
@test "sauvegarde_n_interprete_pas_la_sortie" {
  local sortie
  for sortie in 'pas du json' '{"integrite":"inconnue"}'; do
    DOUBLE_DOCKER_SAUVEGARDE_SORTIE="$sortie" sauvegarder prod
    [ "$status" -eq 0 ]
    [[ "$output" == *"$sortie"* ]]
    rm -rf "$SAUVEGARDES/quotidiennes"
  done
  [ "$(envois_ok "$HC_SAUVEGARDE" | wc -l)" -eq 2 ]
}

@test "sauvegarde_refuse_un_instantane_qui_n_existe_pas_sur_le_disque" {
  # code 0, mais le conteneur n'a rien écrit
  DOUBLE_DOCKER_SAUVEGARDE_SANS_FICHIER=1 sauvegarder prod
  [ "$status" -eq 1 ]
  [[ "$output" == *"instantané absent du disque"* ]]
  [ "$(envois_echec "$HC_SAUVEGARDE" | wc -l)" -eq 1 ]
  [ -z "$(appels_de rclone)" ]
}

# Healthchecks est un tiers : la raison qu'on lui envoie est un résumé (le code, la forme de
# l'instantané), jamais la sortie de la commande, qui peut décrire les données. Elle reste dans le
# journal.
@test "sauvegarde_n_envoie_pas_la_sortie_chez_healthchecks" {
  local sortie='données de i-secret-42 : eleves_secrets=42'
  # 1. la commande échoue et dit où elle en est ; 2. code 0 mais un instantané vide ; 3. succès
  DOUBLE_DOCKER_SAUVEGARDE_CODE=1 DOUBLE_DOCKER_SAUVEGARDE_SORTIE="$sortie" sauvegarder prod
  [ "$status" -eq 1 ]
  [[ "$output" == *"i-secret-42"* ]]
  [[ "$(envois_echec "$HC_SAUVEGARDE")" == *"instantané impossible (code 1)"* ]]
  DOUBLE_DOCKER_SAUVEGARDE_FORME=vide DOUBLE_DOCKER_SAUVEGARDE_SORTIE="$sortie" sauvegarder prod
  [ "$status" -eq 1 ]
  [[ "$output" == *"i-secret-42"* ]]
  rm -rf "$SAUVEGARDES/quotidiennes"
  DOUBLE_DOCKER_SAUVEGARDE_SORTIE="$sortie" sauvegarder prod
  [ "$status" -eq 0 ]
  [[ "$output" == *"i-secret-42"* ]]
  # deux échecs et un succès signalés, dont aucun ne contient la sortie
  [ "$(envois_echec "$HC_SAUVEGARDE" | wc -l)" -eq 2 ]
  [ "$(envois_ok "$HC_SAUVEGARDE" | wc -l)" -eq 1 ]
  aucune_ligne 'i-secret-42|eleves_secrets' "$APPELS" "$APPELS.urls"
}

@test "sauvegarde_refuse_sans_deploiement" {
  rm "$ETAT/compose.env" "$ETAT/deploye"
  sauvegarder prod
  [ "$status" -eq 1 ]
  [[ "$output" == *"compose.env"* ]]
  [ "$(envois_echec "$HC_SAUVEGARDE" | wc -l)" -eq 1 ]
  [ -z "$(appels_de rclone)" ]
}

# R14 : la rétention locale lit l'âge dans le nom des dossiers, l'horodatage UTC qu'il porte, et
# jamais dans leur date. Elle vise quotidiennes/veille-emploi-<horodatage>/, pre-deploiement/<horodatage>/
# (le nom que deployer.sh leur donne), leurs .partiel, et les avant-restauration-<horodatage>/ de
# restaurer.sh, copies en clair des données elles aussi. Un nom d'une autre forme n'est jamais
# retiré, même vieux. Les noms se calculent à partir d'aujourd'hui : le test vaut à toute date.
@test "retention_supprime_au_dela_de_30_jours" {
  local vieux recent ancien q="$SAUVEGARDES/quotidiennes" p="$SAUVEGARDES/pre-deploiement"
  vieux="$(il_y_a 31)"
  recent="$(il_y_a 29)"
  ancien="$(il_y_a 40)"
  # vieux par leur nom, mais datés d'aujourd'hui : ils partent
  instantane "veille-emploi-$vieux"
  instantane "veille-emploi-$vieux.partiel"
  instantane "$vieux" 0 pre-deploiement
  instantane "$vieux.partiel" 0 pre-deploiement
  mkdir -p "$SAUVEGARDES/avant-restauration-$vieux"
  echo vieille >"$SAUVEGARDES/avant-restauration-$vieux/courant.txt"
  # récents par leur nom, mais datés de 60 jours : ils restent
  instantane "veille-emploi-$recent" 60
  instantane "$recent" 60 pre-deploiement
  mkdir -p "$SAUVEGARDES/avant-restauration-$recent"
  echo recente >"$SAUVEGARDES/avant-restauration-$recent/courant.txt"
  touch -d '60 days ago' "$SAUVEGARDES/avant-restauration-$recent"
  # d'autres noms, vieux par leur nom comme par leur date : ils restent
  echo autre >"$q/notes.txt"
  echo autre >"$q/veille-emploi-$ancien.tar"
  echo autre >"$p/$ancien"
  mkdir -p "$q/autre-projet-$ancien" "$q/veille-emploi-$ancien-copie" "$p/notes" "$p/$ancien-copie" \
    "$SAUVEGARDES/avant-restauration-$ancien-copie"
  touch -d '60 days ago' "$q/notes.txt" "$q/veille-emploi-$ancien.tar" "$p/$ancien" "$q/autre-projet-$ancien" \
    "$q/veille-emploi-$ancien-copie" "$p/notes" "$p/$ancien-copie" "$SAUVEGARDES/avant-restauration-$ancien-copie"

  sauvegarder prod
  [ "$status" -eq 0 ]

  # les dossiers de plus de 30 jours, par leur nom, partent en entier ; les autres restent en entier
  [ ! -e "$q/veille-emploi-$vieux" ]
  [ ! -e "$q/veille-emploi-$vieux.partiel" ]
  [ ! -e "$p/$vieux" ]
  [ ! -e "$p/$vieux.partiel" ]
  [ ! -e "$SAUVEGARDES/avant-restauration-$vieux" ]
  [ -f "$q/veille-emploi-$recent/sous/profond.txt" ]
  [ -f "$p/$recent/sous/profond.txt" ]
  [ -e "$SAUVEGARDES/avant-restauration-$recent/courant.txt" ]
  # un nom d'une autre forme, ou ce qui n'est pas un dossier, reste
  [ -e "$q/notes.txt" ]
  [ -e "$q/veille-emploi-$ancien.tar" ]
  [ -f "$p/$ancien" ]
  [ -d "$q/autre-projet-$ancien" ]
  [ -d "$q/veille-emploi-$ancien-copie" ]
  [ -d "$p/notes" ]
  [ -d "$p/$ancien-copie" ]
  [ -d "$SAUVEGARDES/avant-restauration-$ancien-copie" ]
  # l'instantané du jour est là, avec le récent
  [ "$(find "$q" -mindepth 1 -maxdepth 1 -type d -regextype posix-extended -regex '.*/veille-emploi-[0-9]{8}T[0-9]{6}Z' | wc -l)" -eq 2 ]
}

# I2 : une commande SAUVEGARDER qui copie /donnees avec ses dates (cp -a, rsync -a) date l'instantané
# du jour comme ses données, 60 jours ici. Il reste, et le test de restauration le trouve. De même
# pour un instantané d'avant déploiement nommé d'aujourd'hui.
@test "retention_ne_regarde_pas_la_date_des_dossiers" {
  local aujourdhui
  aujourdhui="$(il_y_a 0)"
  instantane "$aujourdhui" 60 pre-deploiement
  DOUBLE_DOCKER_SAUVEGARDE_VIEILLI=60 sauvegarder prod
  [ "$status" -eq 0 ]
  local instantanes=("$SAUVEGARDES"/quotidiennes/veille-emploi-*Z)
  [ "${#instantanes[@]}" -eq 1 ]
  [ -d "${instantanes[0]}" ]
  [ -f "$SAUVEGARDES/pre-deploiement/$aujourdhui/sous/profond.txt" ]
  tester prod
  [ "$status" -eq 0 ]
  [[ "$(envois_ok "$HC_TEST")" == *"${instantanes[0]##*/} restaurée"* ]]
}

@test "retention_supprime_au_dela_de_90_jours_au_distant" {
  mkdir -p "$DISTANT"
  echo vieux >"$DISTANT/veille-emploi-20260601T024500Z.tar.age"
  echo recent >"$DISTANT/veille-emploi-20260901T024500Z.tar.age"
  echo autre >"$DISTANT/notes.txt"
  touch -d '91 days ago' "$DISTANT/veille-emploi-20260601T024500Z.tar.age" "$DISTANT/notes.txt"
  touch -d '89 days ago' "$DISTANT/veille-emploi-20260901T024500Z.tar.age"
  # une vieille archive dans un sous-dossier du dossier de destination : rclone delete est récursif
  # par défaut, --max-depth 1 la protège
  mkdir -p "$DISTANT/sous-dossier"
  echo vieux >"$DISTANT/sous-dossier/veille-emploi-20260501T024500Z.tar.age"
  touch -d '120 days ago' "$DISTANT/sous-dossier/veille-emploi-20260501T024500Z.tar.age"

  sauvegarder prod
  [ "$status" -eq 0 ]
  [ ! -e "$DISTANT/veille-emploi-20260601T024500Z.tar.age" ]
  [ -e "$DISTANT/veille-emploi-20260901T024500Z.tar.age" ]
  # même vieux, ce qui n'est pas une de nos archives n'est jamais effacé
  [ -e "$DISTANT/notes.txt" ]
  # ni ce qui n'est pas directement dans le dossier de la destination
  [ -e "$DISTANT/sous-dossier/veille-emploi-20260501T024500Z.tar.age" ]
  # le récent, notes.txt, le sous-dossier, l'archive du jour et son couple
  [ "$(nombre_d_entrees "$DISTANT")" -eq 5 ]
  # la suppression distante est bornée au dossier (--max-depth 1), à l'âge et à nos archives, et
  # définitive (pas de corbeille : elle prolongerait la conservation au-delà des 90 jours de
  # M-0005) ; elle suit l'envoi, et vise aussi les couples (voir « sauvegarde : la purge distante
  # retire le couple avec son archive »)
  appels_de rclone | grep -Fx "rclone delete --min-age 90d --max-depth 1 --drive-use-trash=false --include veille-emploi-*.tar.age --include veille-emploi-*.couple.age sauvegardes:veille-emploi-sauvegardes"
  [ "$(ligne_de 'rclone lsf')" -lt "$(ligne_de 'rclone delete')" ]
}

# La rétention locale retire le .couple avec son instantané : même nom, même âge, lu dans le nom.
# Un couple seul, dont l'instantané est parti, part aussi quand son nom a plus de 30 jours. Ni un
# lien, ni un nom d'une autre forme ; un .couple n'est jamais pris pour un instantané.
@test "sauvegarde : la rétention locale retire le couple avec son instantané" {
  local q="$SAUVEGARDES/quotidiennes" p="$SAUVEGARDES/pre-deploiement" vieux recent ancien lien
  local ailleurs="$BATS_TEST_TMPDIR/ailleurs.txt" chemin
  vieux="$(il_y_a 31)"
  recent="$(il_y_a 29)"
  ancien="$(il_y_a 40)"
  lien="$(il_y_a 41)"
  echo "à garder" >"$ailleurs"
  # vieux par leur nom ; récents par leur nom, mais datés de 60 jours
  instantane "veille-emploi-$vieux"
  instantane "veille-emploi-$recent" 60
  instantane "$vieux" 0 pre-deploiement
  instantane "$recent" 60 pre-deploiement
  for chemin in "$q/veille-emploi-$vieux" "$q/veille-emploi-$recent" "$p/$vieux" "$p/$recent"; do
    echo "$IMAGE 0.0.1 -" >"$chemin.couple"
  done
  touch -d '60 days ago' "$q/veille-emploi-$recent.couple" "$p/$recent.couple"
  # un couple seul, vieux par son nom
  echo "$IMAGE 0.0.1 -" >"$q/veille-emploi-$ancien.couple"
  # un lien au nom d'un couple, d'autres noms : ils restent, et ce que le lien désigne aussi
  ln -s "$ailleurs" "$q/veille-emploi-$lien.couple"
  echo autre >"$q/notes.couple"
  echo autre >"$q/veille-emploi-$ancien.couple.copie"
  echo autre >"$p/$ancien.couple.copie"
  touch -d '60 days ago' "$q/notes.couple" "$q/veille-emploi-$ancien.couple.copie" "$p/$ancien.couple.copie"
  sauvegarder prod
  [ "$status" -eq 0 ]
  # plus de 30 jours, par le nom : l'instantané et son couple partent ensemble, un couple seul aussi
  [ ! -e "$q/veille-emploi-$vieux" ]
  [ ! -e "$q/veille-emploi-$vieux.couple" ]
  [ ! -e "$p/$vieux" ]
  [ ! -e "$p/$vieux.couple" ]
  [ ! -e "$q/veille-emploi-$ancien.couple" ]
  # les récents restent, chacun avec son couple
  [ -f "$q/veille-emploi-$recent/sous/profond.txt" ]
  [ -f "$q/veille-emploi-$recent.couple" ]
  [ -f "$p/$recent/sous/profond.txt" ]
  [ -f "$p/$recent.couple" ]
  # le lien et sa cible, les autres noms
  [ -L "$q/veille-emploi-$lien.couple" ]
  [ "$(cat "$ailleurs")" = "à garder" ]
  [ -f "$q/notes.couple" ]
  [ -f "$q/veille-emploi-$ancien.couple.copie" ]
  [ -f "$p/$ancien.couple.copie" ]
  # deux instantanés, le récent et celui du jour, chacun avec son couple
  [ "$(find "$q" -mindepth 1 -maxdepth 1 -type d -regextype posix-extended -regex '.*/veille-emploi-[0-9]{8}T[0-9]{6}Z' | wc -l)" -eq 2 ]
  [ "$(find "$q" -mindepth 1 -maxdepth 1 -type f -regextype posix-extended -regex '.*/veille-emploi-[0-9]{8}T[0-9]{6}Z\.couple' | wc -l)" -eq 2 ]
}

# La purge distante, 90 jours, retire le .couple.age avec son archive : la sauvegarde leur donne la
# même date, et un seul `rclone delete` les vise tous deux, du même âge. Ensemble ils partent,
# ensemble ils restent ; un couple seul, vieux, part aussi. Ni ce qui n'est pas à nous, ni un
# sous-dossier.
@test "sauvegarde : la purge distante retire le couple avec son archive" {
  local n
  mkdir -p "$DISTANT/sous-dossier"
  for n in 20260601T024500Z 20260901T024500Z; do
    echo archive >"$DISTANT/veille-emploi-$n.tar.age"
    echo couple >"$DISTANT/veille-emploi-$n.couple.age"
  done
  echo couple >"$DISTANT/veille-emploi-20260501T024500Z.couple.age"
  echo couple >"$DISTANT/autre-projet-20260501T024500Z.couple.age"
  echo couple >"$DISTANT/sous-dossier/veille-emploi-20260401T024500Z.couple.age"
  touch -d '91 days ago' "$DISTANT/veille-emploi-20260601T024500Z.tar.age" \
    "$DISTANT/veille-emploi-20260601T024500Z.couple.age" "$DISTANT/veille-emploi-20260501T024500Z.couple.age" \
    "$DISTANT/autre-projet-20260501T024500Z.couple.age"
  touch -d '89 days ago' "$DISTANT/veille-emploi-20260901T024500Z.tar.age" "$DISTANT/veille-emploi-20260901T024500Z.couple.age"
  touch -d '120 days ago' "$DISTANT/sous-dossier/veille-emploi-20260401T024500Z.couple.age"
  sauvegarder prod
  [ "$status" -eq 0 ]
  [ ! -e "$DISTANT/veille-emploi-20260601T024500Z.tar.age" ]
  [ ! -e "$DISTANT/veille-emploi-20260601T024500Z.couple.age" ]
  [ ! -e "$DISTANT/veille-emploi-20260501T024500Z.couple.age" ]
  [ -e "$DISTANT/veille-emploi-20260901T024500Z.tar.age" ]
  [ -e "$DISTANT/veille-emploi-20260901T024500Z.couple.age" ]
  [ -e "$DISTANT/autre-projet-20260501T024500Z.couple.age" ]
  [ -e "$DISTANT/sous-dossier/veille-emploi-20260401T024500Z.couple.age" ]
  # le récent et son couple, l'autre projet, le sous-dossier, l'archive du jour et son couple
  [ "$(nombre_d_entrees "$DISTANT")" -eq 6 ]
  appels_de rclone | grep -Fx "rclone delete --min-age 90d --max-depth 1 --drive-use-trash=false --include veille-emploi-*.tar.age --include veille-emploi-*.couple.age sauvegardes:veille-emploi-sauvegardes"
}

@test "retention_locale_ne_vise_jamais_le_dossier_des_sauvegardes_lui_meme" {
  # un dossier des sauvegardes qui porterait un nom de dossier à purger, vieux par son nom et sa date
  local racine
  racine="$BATS_TEST_TMPDIR/avant-restauration-$(il_y_a 40)"
  export VEILLE_EMPLOI_RACINE_SAUVEGARDES="$racine"
  SAUVEGARDES="$VEILLE_EMPLOI_RACINE_SAUVEGARDES"
  en_service prod "$IMAGE" 0.1.0
  mkdir -p "$SAUVEGARDES/quotidiennes"
  touch -d '40 days ago' "$SAUVEGARDES"
  sauvegarder prod
  [ "$status" -eq 0 ]
  [ -d "$SAUVEGARDES/quotidiennes" ]
  # l'instantané du jour et son couple
  [ "$(nombre_d_entrees "$SAUVEGARDES/quotidiennes")" -eq 2 ]
}

@test "retention_n_efface_rien_de_local_si_l_envoi_echoue" {
  local vieux
  vieux="$(il_y_a 40)"
  instantane "veille-emploi-$vieux" 40
  export DOUBLE_RCLONE_COPY_CODE=1
  sauvegarder prod
  [ "$status" -eq 1 ]
  [ -f "$SAUVEGARDES/quotidiennes/veille-emploi-$vieux/donnees.txt" ]
}

@test "retention_en_echec_est_signalee_apres_l_envoi" {
  export DOUBLE_RCLONE_DELETE_CODE=1
  sauvegarder prod
  [ "$status" -eq 1 ]
  [[ "$output" == *"rétention"* ]]
  [ -z "$(envois_ok "$HC_SAUVEGARDE")" ]
  [ "$(envois_echec "$HC_SAUVEGARDE" | wc -l)" -eq 1 ]
  # la sauvegarde elle-même est partie, avec son couple
  [ "$(nombre_d_entrees "$DISTANT")" -eq 2 ]
}

@test "sauvegarde_refuse_un_distant_qui_viserait_plus_que_son_dossier" {
  local distant
  for distant in 'sauvegardes:' 'sauvegardes' ':veille-emploi' 'sauvegardes:..' 'sauvegardes:veille-emploi/../autre-projet' \
    'sauvegardes:/' 'sauvegardes:veille-emploi sauvegardes' '-v:veille-emploi'; do
    VEILLE_EMPLOI_DISTANT="$distant" sauvegarder prod
    [ "$status" -eq 1 ]
    [[ "$output" == *"destination distante refusée"* ]]
  done
  # rien n'a été envoyé ni supprimé, mais chaque refus a été signalé
  [ -z "$(appels_de rclone)" ]
  [ "$(envois_echec "$HC_SAUVEGARDE" | wc -l)" -eq 8 ]
}

@test "sauvegarde_attend_le_verrou_partage_puis_s_execute" {
  tenir_le_verrou "$ETAT/verrou"
  bash "$CLONE/deploiement/sauvegarder.sh" prod >"$BATS_TEST_TMPDIR/sortie" 2>&1 3>&- &
  local sauvegarde=$!
  sleep 2
  # toujours en attente : ni instantané, ni envoi
  kill -0 "$sauvegarde"
  [ -z "$(appels_de docker)" ]
  [ -z "$(appels_de rclone)" ]
  relacher_le_verrou
  wait "$sauvegarde"
  [ "$(nombre_d_entrees "$DISTANT")" -eq 2 ]
  [ "$(envois_ok "$HC_SAUVEGARDE" | wc -l)" -eq 1 ]
}

@test "sauvegarde_signale_un_verrou_toujours_pris" {
  export VEILLE_EMPLOI_VERROU_ATTENTE=1
  tenir_le_verrou "$ETAT/verrou"
  sauvegarder prod
  relacher_le_verrou
  [ "$status" -eq 1 ]
  [[ "$output" == *"verrou"*"toujours pris après 1 s"* ]]
  [ "$(envois_echec "$HC_SAUVEGARDE" | wc -l)" -eq 1 ]
  [ -z "$(appels_de docker)" ]
  [ -z "$(appels_de rclone)" ]
}

@test "sauvegarde_tient_le_verrou_pendant_l_instantane" {
  export DOUBLE_DOCKER_SAUVEGARDE_ATTENTE=5
  setsid bash "$CLONE/deploiement/sauvegarder.sh" prod >"$BATS_TEST_TMPDIR/sortie" 2>&1 3>&- &
  local pid=$!
  attendre_appel docker
  # en plein instantané, les données sont lues : le verrou de la sonde et du déploiement est pris
  run ! flock -n "$ETAT/verrou" true
  kill -TERM -- "-$pid"
  wait "$pid" || true
  # une fois finie, il est libre
  flock -n "$ETAT/verrou" true
}

@test "sauvegarde_relache_le_verrou_avant_l_envoi" {
  export DOUBLE_RCLONE_COPY_ATTENTE=5
  setsid bash "$CLONE/deploiement/sauvegarder.sh" prod >"$BATS_TEST_TMPDIR/sortie" 2>&1 3>&- &
  local pid=$!
  attendre_appel rclone
  # en plein envoi, l'archive chiffrée est sur le disque et les données ne sont plus lues : un
  # déploiement ou la sonde n'attendent pas le distant
  flock -n "$ETAT/verrou" true
  kill -TERM -- "-$pid"
  wait "$pid" || true
  # l'échec de l'envoi interrompu est quand même signalé
  [ "$(envois_echec "$HC_SAUVEGARDE" | wc -l)" -eq 1 ]
}

@test "sauvegarde_sans_secrets_s_arrete_avec_le_code_3" {
  rm "$CLONE_DONNEES/$SOUS_SECRETS/prod.env.enc"
  sauvegarder prod
  [ "$status" -eq 3 ]
  [ -z "$(appels_de docker)" ]
  [ -z "$(appels_de rclone)" ]
  aucun_envoi
}

@test "sauvegarde_refuse_une_image_heritee_de_l_environnement" {
  VEILLE_EMPLOI_IMAGE=ghcr.io/edouardzemb/veille-emploi@sha256:ffff sauvegarder prod
  [ "$status" -eq 1 ]
  [[ "$output" == *"VEILLE_EMPLOI_IMAGE est posée dans l'environnement"* ]]
  [ -z "$(appels_de docker)" ]
  [ -z "$(appels_de rclone)" ]
}

@test "sauvegarde_interrompue_signale_l_echec_et_nettoie" {
  export DOUBLE_RCLONE_COPY_ATTENTE=30
  setsid bash "$CLONE/deploiement/sauvegarder.sh" prod >"$BATS_TEST_TMPDIR/sortie" 2>&1 3>&- &
  local pid=$! code=0
  attendre_appel rclone
  kill -TERM -- "-$pid"
  wait "$pid" || code=$?
  [ "$code" -eq 143 ]
  [ "$(envois_echec "$HC_SAUVEGARDE" | wc -l)" -eq 1 ]
  [ -z "$(envois_ok "$HC_SAUVEGARDE")" ]
  [ ! -e "$DISTANT" ]
  aucun_temporaire
}

@test "sauvegarde_ne_laisse_aucune_adresse_dans_une_trace" {
  run bash -x "$CLONE/deploiement/sauvegarder.sh" prod
  [ "$status" -eq 0 ]
  aucune_ligne 'hc\.example|jeton-prod-7' <(printf '%s\n' "$output")
  # elle a bien signalé, mais l'adresse n'est que dans l'appel de curl
  [ "$(envois_ok "$HC_SAUVEGARDE" | wc -l)" -eq 1 ]
}

# ==============================================================================================
# tester-restauration.sh
# ==============================================================================================

@test "test_restauration_restaure_la_derniere_sauvegarde_locale" {
  instantane veille-emploi-20261012T024500Z 3
  instantane "$SNAPSHOT" 1
  instantane veille-emploi-20261013T024500Z 2
  cp -R "$SAUVEGARDES/quotidiennes/$SNAPSHOT" "$BATS_TEST_TMPDIR/avant"
  tester prod
  [ "$status" -eq 0 ]

  # 1. contrôle dans un conteneur jetable, sur une copie de la plus récente, par la commande
  # VERIFIER de projet.env ; l'image est celle de `deploye`
  local copie="$TMPDIR/veille-emploi-test-restauration\.[A-Za-z0-9]+"
  appels_de docker | grep -E "^docker run --rm .*-v $copie:/donnees $IMAGE outil verifier /donnees$"
  [ "$(cat "$BATS_TEST_TMPDIR/run-mots")" = "$(printf '%s\n' outil verifier /donnees)" ]
  # la copie a tout le contenu de l'instantané, fichiers cachés et sous-dossiers compris
  diff -r "$BATS_TEST_TMPDIR/avant" "$BATS_TEST_TMPDIR/verifie"
  # 2. conteneur de test sur 127.0.0.1:4319 seulement, avec cette copie seulement
  appels_de docker | grep -E "^docker run -d --name veille-emploi-test-restauration -p 127\.0\.0\.1:4319:8460 .*-v $copie:/donnees $IMAGE$"
  # santé sur 4319 : jamais sur le port de la prod
  appels_de curl | grep -Fx 'curl -fsS -m 5 http://127.0.0.1:4319/sante'
  [ -z "$(appels_de curl | grep ':4310' || true)" ]
  # 3. arrêt, suppression du conteneur, nettoyage
  [ "$(ligne_de 'docker run --rm')" -lt "$(ligne_de 'docker run -d')" ]
  [ "$(ligne_de 'docker run -d')" -lt "$(ligne_de 'docker stop')" ]
  [ "$(ligne_de 'docker stop')" -lt "$(ligne_de 'docker rm veille-emploi-test-restauration')" ]
  appels_de docker | grep -F 'docker stop -t 10 veille-emploi-test-restauration'
  appels_de docker | grep -Fx 'docker rm veille-emploi-test-restauration'
  [ ! -e "$BATS_TEST_TMPDIR/conteneur-veille-emploi-test-restauration.env" ]
  aucun_temporaire
  # la prod n'a pas bougé : pas de compose du tout, l'application en service est restée en service
  [ -z "$(appels_de docker | grep 'docker compose' || true)" ]
  [ -f "$EN_SERVICE" ]
  # l'instantané n'a pas été touché
  diff -r "$BATS_TEST_TMPDIR/avant" "$SAUVEGARDES/quotidiennes/$SNAPSHOT"
  # résultat
  [ "$(envois_ok "$HC_TEST")" = "curl -fsS -m 10 --retry 3 --data-raw $SNAPSHOT restaurée : 3 fichiers $HC_TEST" ]
  [ -z "$(envois_echec "$HC_TEST")" ]
}

# Le port de l'essai est celui de la prod plus 9, lu dans son env au moment de l'essai : un dépôt de
# code rend ce script sans bloc de ports (M-0006, § 4). 5000 est hors des blocs : aucun port rendu.
@test "test_restauration_publie_le_port_de_la_prod_plus_9" {
  sed -i 's/^VEILLE_EMPLOI_PORT=.*$/VEILLE_EMPLOI_PORT=5000/' "$CLONE_DONNEES/$SOUS_ENV/prod.env"
  grep -Fx 'VEILLE_EMPLOI_PORT=5000' "$CLONE_DONNEES/$SOUS_ENV/prod.env"
  instantane "$SNAPSHOT" 1
  tester prod
  [ "$status" -eq 0 ]
  appels_de docker | grep -E "^docker run -d --name veille-emploi-test-restauration -p 127\.0\.0\.1:5009:8460 "
  appels_de curl | grep -Fx 'curl -fsS -m 5 http://127.0.0.1:5009/sante'
  aucune_ligne ':(5000|4319)([^0-9]|$)' "$APPELS"
  [ "$(envois_ok "$HC_TEST" | wc -l)" -eq 1 ]
}

# Un port de la prod illisible : l'essai n'a pas de port, il échoue avant tout conteneur, et le dit.
@test "test_restauration_refuse_un_port_de_la_prod_illisible" {
  instantane "$SNAPSHOT" 1
  local port
  for port in 43x0 0 04310 65527; do
    sed -i "s/^VEILLE_EMPLOI_PORT=.*\$/VEILLE_EMPLOI_PORT=$port/" "$CLONE_DONNEES/$SOUS_ENV/prod.env"
    tester prod
    [ "$status" -eq 1 ]
    [[ "$output" == *"port de la prod illisible : VEILLE_EMPLOI_PORT='$port'"* ]]
  done
  [ -z "$(appels_de docker | grep -F 'docker run' || true)" ]
  [ "$(envois_echec "$HC_TEST" | wc -l)" -eq 4 ]
  [ -z "$(envois_ok "$HC_TEST")" ]
}

# VERIFIER rend 2 : la copie n'est pas conforme. Le test échoue avant de lancer l'application, et la
# sortie de la commande reste au journal.
@test "test_restauration_verifier_non_conforme_echoue" {
  instantane "$SNAPSHOT" 1
  export DOUBLE_DOCKER_VERIFIER_CODE=2
  export DOUBLE_DOCKER_VERIFIER_SORTIE='écart : sous/profond.txt illisible'
  tester prod
  [ "$status" -eq 1 ]
  [[ "$output" == *"copie non conforme (verifier : code 2) : écart : sous/profond.txt illisible"* ]]
  [ -z "$(envois_ok "$HC_TEST")" ]
  [ "$(envois_echec "$HC_TEST" | wc -l)" -eq 1 ]
  [[ "$(envois_echec "$HC_TEST")" == *"$SNAPSHOT non conforme"* ]]
  aucune_ligne 'écart' <(envois_echec "$HC_TEST")
  # le conteneur de test n'a pas été lancé, rien ne traîne
  [ -z "$(appels_de docker | grep 'docker run -d' || true)" ]
  aucun_temporaire
}

# 64 (une commande que l'image ne connaît pas), un autre code, ou pas de commande VERIFIER : la
# vérification n'a pas eu lieu, et le test échoue sans lancer l'application.
@test "test_restauration_verifier_impossible_echoue" {
  instantane "$SNAPSHOT" 1
  local cas
  for cas in 64 1 sans-commande; do
    case "$cas" in
      sans-commande)
        unset DOUBLE_DOCKER_VERIFIER_CODE
        printf '%s\n' 'SAUVEGARDER=outil sauvegarder' >"$CLONE/deploiement/projet.env"
        ;;
      *) export DOUBLE_DOCKER_VERIFIER_CODE="$cas" ;;
    esac
    tester prod
    [ "$status" -eq 1 ]
    [[ "$output" == *"vérification de la copie de $SNAPSHOT impossible"* ]]
  done
  [ "$(envois_echec "$HC_TEST" | wc -l)" -eq 3 ]
  [ -z "$(envois_ok "$HC_TEST")" ]
  [ -z "$(appels_de docker | grep 'docker run -d' || true)" ]
  aucun_temporaire
}

@test "test_restauration_signale_une_sauvegarde_corrompue" {
  instantane "$SNAPSHOT" 1
  echo CORROMPU >"$SAUVEGARDES/quotidiennes/$SNAPSHOT/donnees.txt"
  tester prod
  [ "$status" -eq 1 ]
  [[ "$output" == *"instantané non conforme : donnees.txt"* ]]
  [ "$(envois_echec "$HC_TEST" | wc -l)" -eq 1 ]
  [ -z "$(appels_de docker | grep 'docker run -d' || true)" ]
}

# Écart 4 : la santé du conteneur de test n'a qu'à dire statut ok. L'instance n'est plus comparée,
# elle n'est pas dans le contrat de l'image : qu'elle manque ou qu'elle diffère, le test passe.
@test "test_restauration_sans_instance" {
  instantane "$SNAPSHOT" 1
  local corps
  for corps in '{"statut":"ok"}' '{"statut":"ok","instance":"une-autre-instance"}'; do
    DOUBLE_CURL_TEST_CORPS="$corps" tester prod
    [ "$status" -eq 0 ]
  done
  # un autre statut échoue, et le conteneur est supprimé quand même
  DOUBLE_CURL_TEST_CORPS='{"statut":"degrade"}' tester prod
  [ "$status" -eq 1 ]
  [ ! -e "$BATS_TEST_TMPDIR/conteneur-veille-emploi-test-restauration.env" ]
  [ "$(envois_ok "$HC_TEST" | wc -l)" -eq 2 ]
  [ "$(envois_echec "$HC_TEST" | wc -l)" -eq 1 ]
  aucun_temporaire
}

@test "test_restauration_signale_une_sante_en_echec_et_garde_la_trace_du_conteneur" {
  instantane "$SNAPSHOT" 1
  export DOUBLE_CURL_TEST_KO=1
  tester prod
  [ "$status" -eq 1 ]
  [ "$(envois_echec "$HC_TEST" | wc -l)" -eq 1 ]
  [ -z "$(envois_ok "$HC_TEST")" ]
  # les dernières lignes du conteneur sont dans le journal, avant sa suppression
  [[ "$output" == *"journal du conteneur veille-emploi-test-restauration"* ]]
  [ "$(ligne_de 'docker run -d')" -lt "$(ligne_de 'docker logs')" ]
  [ "$(ligne_de 'docker logs')" -lt "$(derniere_ligne_de 'docker rm -f')" ]
  [ ! -e "$BATS_TEST_TMPDIR/conteneur-veille-emploi-test-restauration.env" ]
  aucun_temporaire
}

@test "test_restauration_nettoie_quand_le_conteneur_ne_demarre_pas" {
  instantane "$SNAPSHOT" 1
  export DOUBLE_DOCKER_RUN_ECHEC='driver failed programming external connectivity: port is already allocated'
  tester prod
  [ "$status" -eq 1 ]
  [ "$(envois_echec "$HC_TEST" | wc -l)" -eq 1 ]
  aucun_temporaire
  [ -z "$(envois_ok "$HC_TEST")" ]
}

@test "test_restauration_retire_un_conteneur_laisse_par_un_essai_precedent" {
  instantane "$SNAPSHOT" 1
  printf 'PORT=4319\nIMAGE=%s\nDONNEES=/tmp/ancien\n' "$IMAGE" >"$BATS_TEST_TMPDIR/conteneur-veille-emploi-test-restauration.env"
  tester prod
  [ "$status" -eq 0 ]
  [ "$(ligne_de 'docker rm -f veille-emploi-test-restauration')" -lt "$(ligne_de 'docker run -d')" ]
  [ "$(envois_ok "$HC_TEST" | wc -l)" -eq 1 ]
}

@test "test_restauration_signale_un_echec_de_suppression_du_conteneur" {
  instantane "$SNAPSHOT" 1
  export DOUBLE_DOCKER_RM_ECHEC=1
  tester prod
  [ "$status" -eq 1 ]
  [ -z "$(envois_ok "$HC_TEST")" ]
  [ "$(envois_echec "$HC_TEST" | wc -l)" -eq 1 ]
  aucun_temporaire
}

@test "test_restauration_signale_l_absence_de_version_deployee" {
  instantane "$SNAPSHOT" 1
  rm "$ETAT/deploye"
  tester prod
  [ "$status" -eq 1 ]
  [[ "$output" == *"aucune version déployée"* ]]
  [ "$(envois_echec "$HC_TEST" | wc -l)" -eq 1 ]
  [ -z "$(appels_de docker)" ]
}

@test "test_restauration_signale_l_absence_de_sauvegarde_locale" {
  tester prod
  [ "$status" -eq 1 ]
  [[ "$output" == *"aucune sauvegarde locale"* ]]
  [ "$(envois_echec "$HC_TEST" | wc -l)" -eq 1 ]
  [ -z "$(appels_de docker)" ]
}

# La source est le dernier dossier veille-emploi-<horodatage> de quotidiennes/, dans l'ordre des noms, qui
# est celui du temps : ni un fichier, même plus récent, ni un lien, ni un nom d'une autre forme, ni
# le dossier le plus récemment modifié.
@test "test_restauration_prend_le_dernier_dossier" {
  instantane "$SNAPSHOT" 2
  instantane veille-emploi-20261013T024500Z 0
  local q="$SAUVEGARDES/quotidiennes"
  echo "un fichier" >"$q/veille-emploi-20261015T024500Z.tar"
  mkdir -p "$q/veille-emploi-zzz" "$q/veille-emploi-20261016T024500Z-copie"
  ln -s "$q/veille-emploi-20261013T024500Z" "$q/veille-emploi-20261017T024500Z"
  tester prod
  [ "$status" -eq 0 ]
  [[ "$output" == *"test de restauration de $SNAPSHOT"* ]]
  [[ "$(envois_ok "$HC_TEST")" == *"$SNAPSHOT restaurée"* ]]
  [ "$(cat "$BATS_TEST_TMPDIR/verifie/donnees.txt")" = "instantané de test $SNAPSHOT" ]
}

# R13 : une sauvegarde en échec laisse son dossier .partiel, plus récent que le dernier instantané
# complet. Le test de restauration ne le prend jamais.
@test "test_restauration_ignore_un_instantane_partiel" {
  instantane "$SNAPSHOT" 2
  DOUBLE_DOCKER_SAUVEGARDE_FORME=partielle sauvegarder prod
  [ "$status" -eq 1 ]
  tester prod
  [ "$status" -eq 0 ]
  [[ "$output" == *"test de restauration de $SNAPSHOT"* ]]
  [[ "$(envois_ok "$HC_TEST")" == *"$SNAPSHOT restaurée"* ]]
  [ "$(cat "$BATS_TEST_TMPDIR/verifie/donnees.txt")" = "instantané de test $SNAPSHOT" ]
}

# Un .couple, ou un .couple.age, n'est jamais pris pour une sauvegarde, même plus
# récent par son nom et par sa date : le test de restauration prend le dernier instantané, le
# retrait des .partiel n'y touche pas, et restaurer.sh refuse de le restaurer.
@test "sauvegarde : un .couple n'est jamais pris pour une sauvegarde" {
  local q="$SAUVEGARDES/quotidiennes"
  instantane "$SNAPSHOT" 2
  echo "$IMAGE 0.1.0 -" >"$q/$SNAPSHOT.couple"
  echo "$IMAGE 0.1.0 -" >"$q/veille-emploi-20261020T024500Z.couple"
  echo "chiffré" >"$q/veille-emploi-20261021T024500Z.couple.age"
  tester prod
  [ "$status" -eq 0 ]
  [[ "$output" == *"test de restauration de $SNAPSHOT"* ]]
  [[ "$(envois_ok "$HC_TEST")" == *"$SNAPSHOT restaurée"* ]]
  [ "$(cat "$BATS_TEST_TMPDIR/verifie/donnees.txt")" = "instantané de test $SNAPSHOT" ]
  DOUBLE_DOCKER_SAUVEGARDE_FORME=partielle sauvegarder prod
  [ "$status" -eq 1 ]
  [ -f "$q/$SNAPSHOT.couple" ]
  [ -f "$q/veille-emploi-20261020T024500Z.couple" ]
  [ -f "$q/veille-emploi-20261021T024500Z.couple.age" ]
  donnees_courantes
  : >"$APPELS"
  restaurer prod "$q/$SNAPSHOT.couple" --oui
  [ "$status" -eq 64 ]
  [[ "$output" == *"forme inconnue"* ]]
  restaurer prod "$q/veille-emploi-20261021T024500Z.couple.age" --oui --cle "$AGE_IDENTITE_HORS_LIGNE"
  [ "$status" -eq 64 ]
  [[ "$output" == *"forme inconnue"* ]]
  [ -z "$(appels_de docker | grep -E ' (stop|start) ' || true)" ]
  contenu_courant_intact
}

@test "test_restauration_ne_prend_pas_le_verrou_partage" {
  instantane "$SNAPSHOT" 1
  tenir_le_verrou "$ETAT/verrou"
  tester prod
  relacher_le_verrou
  [ "$status" -eq 0 ]
  [ "$(envois_ok "$HC_TEST" | wc -l)" -eq 1 ]
}

@test "test_restauration_ne_se_lance_pas_deux_fois_a_la_fois" {
  instantane "$SNAPSHOT" 1
  # la copie de l'autre exécution, qui travaille : elle n'est pas à balayer
  mkdir -m 700 "$TMPDIR/veille-emploi-test-restauration.EN_COURS"
  tenir_le_verrou "$ETAT/verrou-test-restauration"
  tester prod
  relacher_le_verrou
  # l'autre exécution répond de son résultat : celle-ci ne touche à rien (ni port, ni conteneur)
  [ "$status" -eq 0 ]
  [[ "$output" == *"occupé"* ]]
  [ -z "$(appels_de docker)" ]
  aucun_envoi
  [ -d "$TMPDIR/veille-emploi-test-restauration.EN_COURS" ]
}

# Une exécution tuée de force (SIGKILL, OOM) laisse sa copie en clair des données : la suivante,
# sous le verrou privé, balaie ses propres dossiers, et seulement eux.
@test "test_restauration_balaie_les_copies_laissees_par_une_execution_tuee" {
  instantane "$SNAPSHOT" 1
  mkdir -m 700 "$TMPDIR/veille-emploi-test-restauration.RESTE" "$TMPDIR/veille-emploi-test-restauration.AUTRE"
  echo "copie en clair" >"$TMPDIR/veille-emploi-test-restauration.RESTE/donnees.txt"
  # ce qui n'a pas exactement ce motif, ou n'est pas un dossier, ou n'est pas à la racine, reste
  mkdir -m 700 "$TMPDIR/veille-emploi-restauration.XXXXXX" "$TMPDIR/veille-emploi-test-restauration-autre"
  mkdir -m 700 "$TMPDIR/profond" "$TMPDIR/profond/veille-emploi-test-restauration.PROFOND"
  echo "fichier" >"$TMPDIR/veille-emploi-test-restauration.fichier"
  tester prod
  [ "$status" -eq 0 ]
  [ ! -e "$TMPDIR/veille-emploi-test-restauration.RESTE" ]
  [ ! -e "$TMPDIR/veille-emploi-test-restauration.AUTRE" ]
  [ -d "$TMPDIR/veille-emploi-restauration.XXXXXX" ]
  [ -d "$TMPDIR/veille-emploi-test-restauration-autre" ]
  [ -d "$TMPDIR/profond/veille-emploi-test-restauration.PROFOND" ]
  [ -f "$TMPDIR/veille-emploi-test-restauration.fichier" ]
  # et la propre copie de cette exécution a été détruite à la fin
  [ "$(nombre_d_entrees "$TMPDIR")" -eq 4 ]
}

@test "test_restauration_interrompue_supprime_le_conteneur_et_les_copies" {
  instantane "$SNAPSHOT" 1
  export DOUBLE_CURL_TEST_KO=1
  export VEILLE_EMPLOI_SANTE_DELAI=1
  setsid bash "$CLONE/deploiement/tester-restauration.sh" prod >"$BATS_TEST_TMPDIR/sortie" 2>&1 3>&- &
  local pid=$! code=0
  attendre_appel curl
  [ -f "$BATS_TEST_TMPDIR/conteneur-veille-emploi-test-restauration.env" ]
  kill -TERM -- "-$pid"
  wait "$pid" || code=$?
  [ "$code" -eq 143 ]
  [ ! -e "$BATS_TEST_TMPDIR/conteneur-veille-emploi-test-restauration.env" ]
  [ "$(envois_echec "$HC_TEST" | wc -l)" -eq 1 ]
  aucun_temporaire
}

@test "test_restauration_ne_laisse_aucune_adresse_dans_une_trace" {
  instantane "$SNAPSHOT" 1
  run bash -x "$CLONE/deploiement/tester-restauration.sh" prod
  [ "$status" -eq 0 ]
  aucune_ligne 'hc\.example|jeton-prod-7' <(printf '%s\n' "$output")
}

@test "test_restauration_sans_secrets_s_arrete_avec_le_code_3" {
  instantane "$SNAPSHOT" 1
  rm "$CLONE_DONNEES/$SOUS_SECRETS/prod.env.enc"
  tester prod
  [ "$status" -eq 3 ]
  [ -z "$(appels_de docker)" ]
}

# ==============================================================================================
# restaurer.sh
# ==============================================================================================

@test "restaurer_exige_oui" {
  instantane "$SNAPSHOT" 1
  donnees_courantes
  restaurer prod "$SAUVEGARDES/quotidiennes/$SNAPSHOT"
  [ "$status" -eq 64 ]
  # le plan : la source, les données dont tout le contenu est remplacé, où il sera gardé, comment
  # confirmer
  [[ "$output" == *"$SAUVEGARDES/quotidiennes/$SNAPSHOT"* ]]
  [[ "$output" == *"$DONNEES (tout son contenu)"* ]]
  [[ "$output" == *"avant-restauration-"* ]]
  [[ "$output" == *"--oui"* ]]
  # aucun effet : ni conteneur, ni verrou pris, ni déplacement
  [ -z "$(appels_de docker)" ]
  [ -z "$(appels_de curl)" ]
  [ ! -e "$ETAT/verrou" ]
  contenu_courant_intact
  aucun_dossier_avant_restauration
  aucun_temporaire
  [ -f "$EN_SERVICE" ]
}

@test "restaurer_garde_le_contenu_courant" {
  instantane "$SNAPSHOT" 1
  donnees_courantes
  restaurer prod "$SAUVEGARDES/quotidiennes/$SNAPSHOT" --oui
  [ "$status" -eq 0 ]

  # l'instantané est en place, et lui seul
  diff -r "$SAUVEGARDES/quotidiennes/$SNAPSHOT" "$DONNEES"
  # l'ancien contenu est gardé, entier, dans un dossier daté, privé
  local avant=("$SAUVEGARDES"/avant-restauration-*)
  [ "${#avant[@]}" -eq 1 ]
  [[ "${avant[0]}" =~ /avant-restauration-[0-9]{8}T[0-9]{6}Z$ ]]
  [ "$(stat -c %a "${avant[0]}")" = 700 ]
  [ "$(cat "${avant[0]}/courant.txt")" = "contenu courant" ]
  [ "$(cat "${avant[0]}/.courant")" = "caché courant" ]
  [ "$(cat "${avant[0]}/journal/entree.txt")" = "journal courant" ]
  [ "$(nombre_d_entrees "${avant[0]}")" -eq 3 ]
  # l'instantané d'origine n'a pas bougé
  [ -f "$SAUVEGARDES/quotidiennes/$SNAPSHOT/donnees.txt" ]

  # déroulé : contrôle, arrêt, redémarrage, santé ; par le projet et le compose.env de la prod
  local dc
  dc="$(dc_prod)"
  appels_de docker | grep -E "^docker run --rm .*-v $TMPDIR/veille-emploi-restauration\.[A-Za-z0-9]+/donnees:/donnees $IMAGE outil verifier /donnees$"
  appels_de docker | grep -Fx "$dc stop app"
  appels_de docker | grep -Fx "$dc start app"
  [ "$(ligne_de 'docker run --rm')" -lt "$(ligne_de ' stop app')" ]
  [ "$(ligne_de ' stop app')" -lt "$(ligne_de ' start app')" ]
  [ "$(ligne_de ' start app')" -lt "$(ligne_de 'curl -fsS -m 5 http://127.0.0.1:4310/sante')" ]
  [ -f "$EN_SERVICE" ]
  # le conteneur de test (4319) n'a rien à voir avec une restauration
  [ -z "$(appels_de docker | grep 'docker run -d' || true)" ]
  # la copie de travail, à côté des données, a disparu
  [ ! -e "$DONNEES.nouvelle" ]
  aucun_temporaire
}

# Restaurer, c'est remettre dans /donnees le contenu de l'instantané, et lui seul : tout ce que
# donnees/ contenait part dans avant-restauration-*/, fichiers cachés, sous-dossiers et noms
# inhabituels compris, même ce que l'instantané ne connaît pas. Le dossier lui-même reste : c'est
# lui que le conteneur monte.
@test "restaurer_remplace_tout_le_contenu_de_donnees" {
  instantane "$SNAPSHOT" 1
  donnees_courantes
  # des noms que l'instantané a aussi, et d'autres qu'il n'a pas
  echo "ancienne version" >"$DONNEES/donnees.txt"
  mkdir -p "$DONNEES/sous" "$DONNEES/vide" "$DONNEES/-tiret"
  echo "ancien profond" >"$DONNEES/sous/profond.txt"
  echo "en trop" >"$DONNEES/sous/en-trop.txt"
  echo "espace" >"$DONNEES/nom avec espace"
  echo "saut" >"$DONNEES/$(printf 'saut\nde ligne')"
  echo "points" >"$DONNEES/..points"
  cp -R "$DONNEES" "$BATS_TEST_TMPDIR/donnees-avant"
  local inode
  inode="$(stat -c %i "$DONNEES")"
  restaurer prod "$SAUVEGARDES/quotidiennes/$SNAPSHOT" --oui
  [ "$status" -eq 0 ]
  # exactement le contenu de l'instantané
  diff -r "$SAUVEGARDES/quotidiennes/$SNAPSHOT" "$DONNEES"
  # exactement l'ancien contenu, de côté
  local avant=("$SAUVEGARDES"/avant-restauration-*)
  diff -r "$BATS_TEST_TMPDIR/donnees-avant" "${avant[0]}"
  # le même dossier
  [ "$(stat -c %i "$DONNEES")" = "$inode" ]
}

# Si la mise en place de l'instantané échoue en route, le piège retire ce qui en était entré, remet
# l'ancien contenu, entier, et relance l'application : la restauration n'a pas eu lieu.
@test "restaurer_echec_retablit_l_ancien_contenu" {
  instantane "$SNAPSHOT" 1
  donnees_courantes
  cp -R "$DONNEES" "$BATS_TEST_TMPDIR/donnees-avant"
  # .cachee et donnees.txt entrent, puis le déplacement de sous/ échoue
  double_mv_en_echec '*/donnees.nouvelle/sous'
  restaurer prod "$SAUVEGARDES/quotidiennes/$SNAPSHOT" --oui
  [ "$status" -eq 1 ]
  [[ "$output" == *"mise en place de l'instantané impossible"* ]]
  [[ "$output" == *"ancien contenu remis en place"* ]]
  # l'application a été arrêtée, puis relancée sur l'ancien contenu, intact
  [ "$(ligne_de ' stop app')" -lt "$(ligne_de ' start app')" ]
  [ -f "$EN_SERVICE" ]
  diff -r "$BATS_TEST_TMPDIR/donnees-avant" "$DONNEES"
  # rien de l'instantané ne reste, ni à côté des données, ni de dossier de restauration vide
  [ ! -e "$DONNEES.nouvelle" ]
  aucun_dossier_avant_restauration
  aucun_temporaire
}

# Une base qui tient un journal à côté d'elle (un -wal) le rejouerait au démarrage : si la mise en
# place échoue au milieu, le piège ne doit jamais laisser l'ancienne base à côté d'un journal venu
# de l'instantané. Deux échecs : juste après l'entrée de la base de l'instantané, puis après celle
# de son journal. Après le piège, les données sont l'ancien contenu, à l'octet, et rien d'autre.
@test "restaurer_trap_ne_melange_jamais_ancien_et_instantane" {
  instantane "$SNAPSHOT" 1
  donnees_courantes
  echo "ancienne base" >"$DONNEES/base"
  echo "base de l'instantané" >"$SAUVEGARDES/quotidiennes/$SNAPSHOT/base"
  echo "journal de l'instantané" >"$SAUVEGARDES/quotidiennes/$SNAPSHOT/base-wal"
  cp -R "$DONNEES" "$BATS_TEST_TMPDIR/donnees-avant"
  local echec entre nom
  # dans l'ordre des noms, base précède base-wal, qui précède donnees.txt
  for echec in base-wal donnees.txt; do
    : >"$APPELS"
    # le double du tour précédent part d'abord : le nouveau appellerait sinon l'ancien, et non mv
    rm -f "$DOUBLES/mv"
    double_mv_en_echec "*/donnees.nouvelle/$echec"
    restaurer prod "$SAUVEGARDES/quotidiennes/$SNAPSHOT" --oui
    [ "$status" -eq 1 ]
    [[ "$output" == *"mise en place de l'instantané impossible"*"ancien contenu remis en place"* ]]
    # la mise en place avait commencé : la base de l'instantané (et son journal, au second échec)
    # était entrée dans les données
    entre=(base)
    [ "$echec" = base-wal ] || entre+=(base-wal)
    for nom in "${entre[@]}"; do
      appels_de mv | grep -Fx -- "mv -T -- $DONNEES.nouvelle/$nom $DONNEES/$nom"
      appels_de mv | grep -Fx -- "mv -T -- $DONNEES/$nom $DONNEES.nouvelle/$nom"
    done
    # l'ancien contenu, à l'octet, et rien de l'instantané : ni sa base, ni son journal
    diff -r "$BATS_TEST_TMPDIR/donnees-avant" "$DONNEES"
    [ "$(cat "$DONNEES/base")" = "ancienne base" ]
    [ ! -e "$DONNEES/base-wal" ]
    [ ! -e "$DONNEES/donnees.txt" ]
    # rien ne reste à côté, ni dans un dossier de restauration ; l'application est relancée
    [ ! -e "$DONNEES.nouvelle" ]
    aucun_dossier_avant_restauration
    [ -f "$EN_SERVICE" ]
    aucun_temporaire
  done
}

# Un déplacement interrompu (SIGKILL, plantage de l'hôte) laisse la copie de travail à côté des
# données, hors de portée du piège. Elle est retirée avant tout, application encore en service : rien
# d'une tentative précédente n'entre dans les données.
@test "restauration_retire_les_restes_d_une_restauration_interrompue" {
  instantane "$SNAPSHOT" 1
  donnees_courantes
  mkdir -p "$DONNEES.nouvelle/sous"
  echo "copie d'une tentative précédente" >"$DONNEES.nouvelle/donnees.txt"
  echo "étranger" >"$DONNEES.nouvelle/etranger.txt"
  echo "étranger" >"$DONNEES.nouvelle/sous/etranger.txt"
  restaurer prod "$SAUVEGARDES/quotidiennes/$SNAPSHOT" --oui
  [ "$status" -eq 0 ]
  # retirée avant l'arrêt de l'application, donc avant la copie
  [[ "$output" == *"reste d'une restauration interrompue retiré : $DONNEES.nouvelle"*"arrêt de l'application"* ]]
  diff -r "$SAUVEGARDES/quotidiennes/$SNAPSHOT" "$DONNEES"
  [ ! -e "$DONNEES.nouvelle" ]
}

@test "restauration_refuse_de_continuer_si_un_reste_ne_peut_pas_etre_retire" {
  instantane "$SNAPSHOT" 1
  donnees_courantes
  mkdir -p "$DONNEES.nouvelle"
  echo "étranger" >"$DONNEES.nouvelle/etranger.txt"
  creer_double rm "case \"\$*\" in *donnees.nouvelle*) echo 'rm: cannot remove: Operation not permitted' >&2; exit 1 ;; esac
exec $(command -v rm) \"\$@\""
  restaurer prod "$SAUVEGARDES/quotidiennes/$SNAPSHOT" --oui
  [ "$status" -eq 1 ]
  [[ "$output" == *"impossible à retirer"* ]]
  # rien n'a changé : l'application n'a pas été arrêtée
  [ -z "$(appels_de docker | grep -E ' (stop|start) ' || true)" ]
  [ -f "$EN_SERVICE" ]
  contenu_courant_intact
  # le dossier temporaire du clair est détruit malgré le rm qui échoue dans le piège
  aucun_temporaire
}

@test "restaurer_depuis_un_instantane_de_pre_deploiement" {
  instantane 20261014T120000Z 1 pre-deploiement
  donnees_courantes
  restaurer prod "$SAUVEGARDES/pre-deploiement/20261014T120000Z" --oui
  [ "$status" -eq 0 ]
  diff -r "$SAUVEGARDES/pre-deploiement/20261014T120000Z" "$DONNEES"
}

@test "restaurer_refuse_un_instantane_non_conforme_sans_rien_toucher" {
  instantane "$SNAPSHOT" 1
  donnees_courantes
  export DOUBLE_DOCKER_VERIFIER_SORTIE='écart : sous/profond.txt illisible'
  local code
  for code in 2 64; do
    DOUBLE_DOCKER_VERIFIER_CODE="$code" restaurer prod "$SAUVEGARDES/quotidiennes/$SNAPSHOT" --oui
    [ "$status" -eq 1 ]
    [[ "$output" == *"écart : sous/profond.txt illisible"* ]]
    case "$code" in
      2) [[ "$output" == *"$SAUVEGARDES/quotidiennes/$SNAPSHOT non conforme : rien n'a changé"* ]] ;;
      *) [[ "$output" == *"vérification de $SAUVEGARDES/quotidiennes/$SNAPSHOT impossible : rien n'a changé"* ]] ;;
    esac
  done
  # l'application n'a pas été arrêtée, les données n'ont pas bougé
  [ -z "$(appels_de docker | grep -E ' (stop|start) ' || true)" ]
  contenu_courant_intact
  aucun_dossier_avant_restauration
  [ -f "$EN_SERVICE" ]
  aucun_temporaire
}

@test "restaurer_refuse_un_instantane_corrompu" {
  instantane "$SNAPSHOT" 1
  echo CORROMPU >"$SAUVEGARDES/quotidiennes/$SNAPSHOT/donnees.txt"
  donnees_courantes
  restaurer prod "$SAUVEGARDES/quotidiennes/$SNAPSHOT" --oui
  [ "$status" -eq 1 ]
  [[ "$output" == *"instantané non conforme : donnees.txt"* ]]
  [ -z "$(appels_de docker | grep -E ' (stop|start) ' || true)" ]
  contenu_courant_intact
}

# Un dossier vide ne prouve rien (sauvegarder.sh n'en écrit jamais), et un lien n'est pas une donnée :
# refusés avant la vérification, sans rien toucher.
@test "restaurer_refuse_un_dossier_vide_ou_qui_contient_un_lien" {
  donnees_courantes
  local q="$SAUVEGARDES/quotidiennes"
  mkdir -p "$q/veille-emploi-20261015T024500Z"
  instantane "$SNAPSHOT" 1
  ln -s /etc/hostname "$q/$SNAPSHOT/lien"
  restaurer prod "$q/veille-emploi-20261015T024500Z" --oui
  [ "$status" -eq 1 ]
  [[ "$output" == *"instantané vide"* ]]
  restaurer prod "$q/$SNAPSHOT" --oui
  [ "$status" -eq 1 ]
  [[ "$output" == *"contenu inattendu"*"ni des fichiers ni des dossiers"* ]]
  [ -z "$(appels_de docker)" ]
  contenu_courant_intact
  aucun_dossier_avant_restauration
  aucun_temporaire
}

@test "restaurer_refuse_une_source_qui_n_existe_pas_ou_d_une_autre_forme" {
  donnees_courantes
  # l'usage donne l'exemple de la clé sur l'entrée standard
  restaurer prod
  [ "$status" -eq 64 ]
  [[ "$output" == *"--cle /dev/stdin"* ]]
  restaurer prod "$SAUVEGARDES/quotidiennes/absent" --oui
  [ "$status" -eq 64 ]
  echo x >"$BATS_TEST_TMPDIR/donnees.txt"
  restaurer prod "$BATS_TEST_TMPDIR/donnees.txt" --oui
  [ "$status" -eq 64 ]
  [[ "$output" == *"un dossier"*".tar.age"* ]]
  restaurer prod "$BATS_TEST_TMPDIR/absente.tar.age" --oui --cle "$AGE_IDENTITE_HORS_LIGNE"
  [ "$status" -eq 64 ]
  restaurer prod --oui
  [ "$status" -eq 64 ]
  mkdir -p "$BATS_TEST_TMPDIR/a" "$BATS_TEST_TMPDIR/b"
  restaurer prod "$BATS_TEST_TMPDIR/a" "$BATS_TEST_TMPDIR/b" --oui
  [ "$status" -eq 64 ]
  restaurer prod "$BATS_TEST_TMPDIR/a" --pas-une-option
  [ "$status" -eq 64 ]
  # un instantané partiel (R13) ne se restaure pas
  instantane veille-emploi-20261015T024500Z.partiel 0
  restaurer prod "$SAUVEGARDES/quotidiennes/veille-emploi-20261015T024500Z.partiel" --oui
  [ "$status" -eq 64 ]
  [[ "$output" == *".partiel"*"ne se restaure pas"* ]]
  [ -z "$(appels_de docker)" ]
  contenu_courant_intact
}

@test "restaurer_sans_version_deployee_ne_touche_a_rien" {
  instantane "$SNAPSHOT" 1
  donnees_courantes
  rm "$ETAT/deploye"
  restaurer prod "$SAUVEGARDES/quotidiennes/$SNAPSHOT" --oui
  [ "$status" -eq 1 ]
  [[ "$output" == *"aucune version déployée"* ]]
  [ -z "$(appels_de docker)" ]
  contenu_courant_intact
}

# archive_chiffree : une archive chiffrée comme celles du distant (le tar du dossier de l'instantané,
# chiffré pour la clé hors ligne), dans $BATS_TEST_TMPDIR/$SNAPSHOT.tar.age. L'instantané est gardé
# dans $BATS_TEST_TMPDIR/attendu, et retiré de quotidiennes/.
archive_chiffree() {
  instantane "$SNAPSHOT" 1
  cp -R "$SAUVEGARDES/quotidiennes/$SNAPSHOT" "$BATS_TEST_TMPDIR/attendu"
  tar -C "$SAUVEGARDES/quotidiennes" -cf - "$SNAPSHOT" | chiffrer "$BATS_TEST_TMPDIR/$SNAPSHOT.tar.age"
  rm -rf "${SAUVEGARDES:?}/quotidiennes/$SNAPSHOT"
}

@test "restaurer_depuis_une_archive_chiffree" {
  archive_chiffree
  donnees_courantes
  restaurer prod "$BATS_TEST_TMPDIR/$SNAPSHOT.tar.age" --oui --cle "$AGE_IDENTITE_HORS_LIGNE"
  [ "$status" -eq 0 ]
  diff -r "$BATS_TEST_TMPDIR/attendu" "$DONNEES"
  local avant=("$SAUVEGARDES"/avant-restauration-*)
  [ "$(cat "${avant[0]}/courant.txt")" = "contenu courant" ]
  # le contenu de l'archive a été contrôlé par VERIFIER avant d'entrer
  appels_de docker | grep -E "^docker run --rm .*-v $TMPDIR/veille-emploi-restauration\.[A-Za-z0-9]+/donnees:/donnees $IMAGE outil verifier /donnees$"
  diff -r "$BATS_TEST_TMPDIR/attendu" "$BATS_TEST_TMPDIR/verifie"
  # le clair n'a existé que dans un dossier temporaire, détruit ; la clé n'est jamais dans un argument
  aucun_temporaire
  aucune_ligne 'AGE-SECRET-KEY' "$APPELS" <(printf '%s\n' "$output")
}

# M-0005 : la clé hors ligne n'est jamais sur le serveur. `--cle` accepte un chemin lisible qui
# n'est pas un fichier ordinaire : `--cle /dev/stdin`, la clé arrivant par ssh, ne touche jamais le
# disque du serveur.
@test "restaurer_depuis_une_archive_chiffree_avec_la_cle_sur_l_entree_standard" {
  archive_chiffree
  donnees_courantes
  export ARCHIVE="$BATS_TEST_TMPDIR/$SNAPSHOT.tar.age"
  run bash -c 'cat "$AGE_IDENTITE_HORS_LIGNE" | bash "$CLONE/deploiement/restaurer.sh" prod "$ARCHIVE" --oui --cle /dev/stdin'
  [ "$status" -eq 0 ]
  diff -r "$BATS_TEST_TMPDIR/attendu" "$DONNEES"
  aucun_temporaire
  # la clé n'est ni dans un argument, ni dans la sortie, ni dans aucun dossier où le script écrit
  aucune_ligne 'AGE-SECRET-KEY' "$APPELS" <(printf '%s\n' "$output")
  [ -z "$(grep -rl 'AGE-SECRET-KEY' "$HOME" "$TMPDIR" "$ETAT" "$SAUVEGARDES" "$DONNEES" || true)" ]
}

@test "restaurer_depuis_une_archive_chiffree_exige_la_cle" {
  archive_chiffree
  donnees_courantes
  restaurer prod "$BATS_TEST_TMPDIR/$SNAPSHOT.tar.age" --oui
  [ "$status" -eq 64 ]
  [[ "$output" == *"--cle"* ]]
  restaurer prod "$BATS_TEST_TMPDIR/$SNAPSHOT.tar.age" --oui --cle "$BATS_TEST_TMPDIR/cle-absente.txt"
  [ "$status" -eq 64 ]
  # un dossier est lisible, mais ce n'est pas une identité
  restaurer prod "$BATS_TEST_TMPDIR/$SNAPSHOT.tar.age" --oui --cle "$BATS_TEST_TMPDIR"
  [ "$status" -eq 64 ]
  restaurer prod "$BATS_TEST_TMPDIR/$SNAPSHOT.tar.age" --oui --cle
  [ "$status" -eq 64 ]
  [ -z "$(appels_de docker)" ]
  contenu_courant_intact
}

# R15 : une clé collée à la place du chemin de l'identité est refusée, et jamais répétée, ni dans
# le message, ni dans le plan.
@test "restaurer_refuse_une_cle_collee_sans_l_afficher" {
  archive_chiffree
  donnees_courantes
  local cle oui
  cle="$(grep '^AGE-SECRET-KEY-' "$AGE_IDENTITE_HORS_LIGNE")"
  for oui in --oui ""; do
    # shellcheck disable=SC2086  # sans --oui, l'option disparaît : c'est le plan qui est demandé
    restaurer prod "$BATS_TEST_TMPDIR/$SNAPSHOT.tar.age" $oui --cle "$cle"
    [ "$status" -eq 64 ]
    [[ "$output" == *"--cle attend un chemin vers un fichier d'identité, pas la clé elle-même"* ]]
    cle_non_repetee "$cle"
  done
  [ -z "$(appels_de docker)" ]
  contenu_courant_intact
  aucun_temporaire
}

# cle_non_repetee <clé> : la sortie du dernier `run` ne contient ni le préfixe d'une clé age, ni le
# corps de celle-ci. En échec, rien de la clé n'est affiché (aucune_ligne afficherait son motif).
cle_non_repetee() {
  if printf '%s\n' "$output" | grep -qF -e 'AGE-SECRET-KEY' -e "${1#AGE-SECRET-KEY-}"; then
    echo "la clé est répétée dans la sortie" >&2
    return 1
  fi
}

# R16 : la clé collée par d'autres chemins que `--cle <clé>` n'est pas répétée non plus. D'abord le
# contenu entier du fichier d'identité, ses lignes de commentaire en tête : il ne commence pas par la
# clé.
@test "restaurer_refuse_un_fichier_d_identite_colle_sans_l_afficher" {
  archive_chiffree
  donnees_courantes
  local cle
  cle="$(grep '^AGE-SECRET-KEY-' "$AGE_IDENTITE_HORS_LIGNE")"
  restaurer prod "$BATS_TEST_TMPDIR/$SNAPSHOT.tar.age" --oui --cle "$(cat "$AGE_IDENTITE_HORS_LIGNE")"
  [ "$status" -eq 64 ]
  cle_non_repetee "$cle"
  [ -z "$(appels_de docker)" ]
  contenu_courant_intact
}

# R16 : `--cle=<clé>`, que l'analyse des options prendrait pour une option inconnue.
@test "restaurer_refuse_une_option_cle_egale_sans_l_afficher" {
  archive_chiffree
  donnees_courantes
  local cle
  cle="$(grep '^AGE-SECRET-KEY-' "$AGE_IDENTITE_HORS_LIGNE")"
  restaurer prod "$BATS_TEST_TMPDIR/$SNAPSHOT.tar.age" --oui "--cle=$cle"
  [ "$status" -eq 64 ]
  cle_non_repetee "$cle"
  [ -z "$(appels_de docker)" ]
  contenu_courant_intact
}

# R16 : la clé collée à la place de la source, ou de l'environnement.
@test "restaurer_refuse_une_cle_collee_comme_source_sans_l_afficher" {
  archive_chiffree
  donnees_courantes
  local cle
  cle="$(grep '^AGE-SECRET-KEY-' "$AGE_IDENTITE_HORS_LIGNE")"
  restaurer prod "$cle" --oui
  [ "$status" -eq 64 ]
  cle_non_repetee "$cle"
  restaurer "$cle" "$BATS_TEST_TMPDIR/$SNAPSHOT.tar.age" --oui
  [ "$status" -eq 64 ]
  cle_non_repetee "$cle"
  [ -z "$(appels_de docker)" ]
  contenu_courant_intact
}

@test "restaurer_depuis_une_archive_avec_la_mauvaise_cle_ne_touche_a_rien" {
  archive_chiffree
  donnees_courantes
  restaurer prod "$BATS_TEST_TMPDIR/$SNAPSHOT.tar.age" --oui --cle "$AGE_IDENTITE_SERVEUR"
  [ "$status" -eq 1 ]
  [[ "$output" == *"déchiffrement impossible"* ]]
  [ -z "$(appels_de docker)" ]
  contenu_courant_intact
  aucun_temporaire
}

# Une archive se déchiffre et doit contenir un seul dossier, veille-emploi-<horodatage>/, et rien à côté :
# la forme qu'écrit sauvegarder.sh. N'importe qui connaît la clé publique : l'archive du distant
# n'est pas de confiance, et toute autre forme est refusée avant l'extraction, sans rien toucher.
@test "restaurer_archive_a_un_seul_dossier" {
  donnees_courantes
  local q="$SAUVEGARDES/quotidiennes" cas i=0
  instantane "$SNAPSHOT" 1
  instantane veille-emploi-20261013T024500Z 2
  instantane autre-projet-20261014T024500Z 1
  instantane veille-emploi-pas-un-horodatage 1
  mkdir -p "$q/veille-emploi-20261015T024500Z"
  echo "à côté" >"$q/a-cote.txt"
  # deux dossiers ; le dossier et un fichier à côté ; un fichier seul ; le dossier d'un autre
  # projet ; un nom sans horodatage ; une archive vide
  for cas in "$SNAPSHOT veille-emploi-20261013T024500Z" "$SNAPSHOT a-cote.txt" "a-cote.txt" \
    "autre-projet-20261014T024500Z" "veille-emploi-pas-un-horodatage" ""; do
    i=$((i + 1))
    # shellcheck disable=SC2086  # la liste de noms est volontairement découpée
    tar -C "$q" -cf - $cas --files-from /dev/null | chiffrer "$BATS_TEST_TMPDIR/piege-$i.tar.age"
  done
  tar -C "$q" -cf - veille-emploi-20261015T024500Z | chiffrer "$BATS_TEST_TMPDIR/vide.tar.age"
  # tar est noté à partir d'ici : celui du script
  creer_double_transparent tar
  for i in 1 2 3 4 5 6; do
    restaurer prod "$BATS_TEST_TMPDIR/piege-$i.tar.age" --oui --cle "$AGE_IDENTITE_HORS_LIGNE"
    [ "$status" -eq 1 ]
    [[ "$output" == *"contenu inattendu"* ]]
  done
  # refusées sur la liste de leurs membres : jamais extraites
  [ -z "$(appels_de tar | grep -E ' -x' || true)" ]
  # un dossier vide a la bonne forme, mais il ne prouve rien
  restaurer prod "$BATS_TEST_TMPDIR/vide.tar.age" --oui --cle "$AGE_IDENTITE_HORS_LIGNE"
  [ "$status" -eq 1 ]
  [[ "$output" == *"instantané vide"* ]]
  [ -z "$(appels_de docker)" ]
  contenu_courant_intact
  aucun_dossier_avant_restauration
  aucun_temporaire
  # le dossier seul, avec ses fichiers cachés et ses sous-dossiers, passe
  tar -C "$q" -cf - "$SNAPSHOT" | chiffrer "$BATS_TEST_TMPDIR/bonne.tar.age"
  restaurer prod "$BATS_TEST_TMPDIR/bonne.tar.age" --oui --cle "$AGE_IDENTITE_HORS_LIGNE"
  [ "$status" -eq 0 ]
  diff -r "$q/$SNAPSHOT" "$DONNEES"
}

# Les membres sont contrôlés avant toute extraction : ni chemin absolu, ni « .. », ni lien
# (symbolique ou physique), ni rien d'autre qu'un fichier ou un dossier. tar n'extrait rien.
@test "restaurer_refuse_membre_absolu_parent_ou_lien" {
  donnees_courantes
  local piege="$BATS_TEST_TMPDIR/piege" s="$SNAPSHOT" i
  mkdir -p "$piege/$s/sous" "$piege/lien"
  echo "piégé" >"$piege/$s/donnees.txt"
  ln -s /etc/hostname "$piege/$s/symbolique"
  ln "$piege/$s/donnees.txt" "$piege/$s/physique"
  mkfifo "$piege/$s/tube"
  ln -s "$piege/$s" "$piege/lien/$s"
  # 1. un chemin absolu ; 2. le même, sous le nom du dossier attendu ; 3. « .. » ; 4. un lien
  # symbolique ; 5. un lien physique ; 6. un tube ; 7. le dossier attendu est lui-même un lien
  tar -P -cf - "$piege/$s/donnees.txt" | chiffrer "$BATS_TEST_TMPDIR/piege-1.tar.age"
  tar -P -C "$piege" -cf - --transform 's,^,/,' "$s/donnees.txt" | chiffrer "$BATS_TEST_TMPDIR/piege-2.tar.age"
  tar -P -C "$piege" -cf - "$s/sous/../donnees.txt" | chiffrer "$BATS_TEST_TMPDIR/piege-3.tar.age"
  tar -C "$piege" -cf - "$s/donnees.txt" "$s/symbolique" | chiffrer "$BATS_TEST_TMPDIR/piege-4.tar.age"
  tar -C "$piege" -cf - "$s/donnees.txt" "$s/physique" | chiffrer "$BATS_TEST_TMPDIR/piege-5.tar.age"
  tar -C "$piege" -cf - "$s/donnees.txt" "$s/tube" | chiffrer "$BATS_TEST_TMPDIR/piege-6.tar.age"
  tar -C "$piege/lien" -cf - "$s" | chiffrer "$BATS_TEST_TMPDIR/piege-7.tar.age"
  # tar est noté à partir d'ici : celui du script
  creer_double_transparent tar
  for i in 1 2 3 4 5 6 7; do
    restaurer prod "$BATS_TEST_TMPDIR/piege-$i.tar.age" --oui --cle "$AGE_IDENTITE_HORS_LIGNE"
    [ "$status" -eq 1 ]
    [[ "$output" == *"contenu inattendu"* ]]
  done
  # les archives ont été listées, jamais extraites
  [ -n "$(appels_de tar)" ]
  [ -z "$(appels_de tar | grep -E ' -x' || true)" ]
  [ -z "$(appels_de docker)" ]
  contenu_courant_intact
  aucun_dossier_avant_restauration
  aucun_temporaire
}

# M-0005, § 6 : restaurer.sh lit le couple voisin de la source, <dossier>.couple, ou, pour une
# archive, <archive sans .tar.age>.couple.age, déchiffré avec la même clé. Il dit « couple de
# l'instantané : … » quand il diffère du couple déployé, rien quand c'est le même, « couple de
# l'instantané inconnu » quand il ne se lit pas. La restauration a lieu dans tous les cas. La clé
# sur l'entrée standard ne se lit qu'une fois : elle déchiffre l'archive et son couple, sans jamais
# toucher un disque ni la trace.
@test "restaurer : dit le couple de l'instantané" {
  local q="$SAUVEGARDES/quotidiennes" pre="$SAUVEGARDES/pre-deploiement" autre commit d cle
  autre="ghcr.io/edouardzemb/veille-emploi@sha256:$(printf '2%.0s' {1..64})"
  commit="$(printf 'c%.0s' {1..40})"
  d="$(printf 'd%.0s' {1..40})"
  echo "$IMAGE 0.1.0 $commit" >"$ETAT/deploye"
  horloge_qui_avance
  donnees_courantes
  # 1. le couple d'un instantané quotidien est le couple déployé : rien à dire
  instantane "$SNAPSHOT" 1
  echo "$IMAGE 0.1.0 $commit" >"$q/$SNAPSHOT.couple"
  restaurer prod "$q/$SNAPSHOT" --oui
  [ "$status" -eq 0 ]
  diff -r "$q/$SNAPSHOT" "$DONNEES"
  [[ "$output" != *"couple de l'instantané"* ]]
  # 2. un instantané d'avant déploiement, pris sous un autre couple : il le dit, et restaure
  instantane 20261014T120000Z 1 pre-deploiement
  echo "$autre 0.0.9 -" >"$pre/20261014T120000Z.couple"
  restaurer prod "$pre/20261014T120000Z/" --oui
  [ "$status" -eq 0 ]
  diff -r "$pre/20261014T120000Z" "$DONNEES"
  sans_horodatage | grep -Fx "couple de l'instantané : $autre 0.0.9 - (couple déployé : $IMAGE 0.1.0 $commit)"
  # 3. une archive et son couple chiffré, la clé dans un fichier
  archive_chiffree
  printf '%s\n' "$autre 0.0.8 $d" | chiffrer "$BATS_TEST_TMPDIR/$SNAPSHOT.couple.age"
  restaurer prod "$BATS_TEST_TMPDIR/$SNAPSHOT.tar.age" --oui --cle "$AGE_IDENTITE_HORS_LIGNE"
  [ "$status" -eq 0 ]
  diff -r "$BATS_TEST_TMPDIR/attendu" "$DONNEES"
  sans_horodatage | grep -Fx "couple de l'instantané : $autre 0.0.8 $d (couple déployé : $IMAGE 0.1.0 $commit)"
  aucun_temporaire
  # 4. la clé sur l'entrée standard, lue une seule fois : l'archive et son couple se déchiffrent
  export ARCHIVE="$BATS_TEST_TMPDIR/$SNAPSHOT.tar.age"
  run bash -c 'cat "$AGE_IDENTITE_HORS_LIGNE" | bash "$CLONE/deploiement/restaurer.sh" prod "$ARCHIVE" --oui --cle /dev/stdin'
  [ "$status" -eq 0 ]
  diff -r "$BATS_TEST_TMPDIR/attendu" "$DONNEES"
  sans_horodatage | grep -Fx "couple de l'instantané : $autre 0.0.8 $d (couple déployé : $IMAGE 0.1.0 $commit)"
  aucune_ligne 'AGE-SECRET-KEY' "$APPELS" <(printf '%s\n' "$output")
  [ -z "$(grep -rl 'AGE-SECRET-KEY' "$HOME" "$TMPDIR" "$ETAT" "$SAUVEGARDES" "$DONNEES" || true)" ]
  aucun_temporaire
  # sous bash -x non plus, la clé n'est jamais répétée
  cle="$(grep '^AGE-SECRET-KEY-' "$AGE_IDENTITE_HORS_LIGNE")"
  run bash -c 'cat "$AGE_IDENTITE_HORS_LIGNE" | bash -x "$CLONE/deploiement/restaurer.sh" prod "$ARCHIVE" --oui --cle /dev/stdin'
  [ "$status" -eq 0 ]
  cle_non_repetee "$cle"
  # 5. un couple qui ne se lit pas : chiffré pour une autre clé, d'une autre forme, ou un lien ; il
  # est inconnu, la raison est dans la même ligne (l'erreur d'age comprise, qui ne sort nulle part
  # ailleurs), et la restauration a lieu
  printf '%s\n' "$autre 0.0.8 $d" | age -R "$CLONE_DONNEES/$SOUS_CLES/serveur.pub" >"$BATS_TEST_TMPDIR/$SNAPSHOT.couple.age"
  restaurer prod "$ARCHIVE" --oui --cle "$AGE_IDENTITE_HORS_LIGNE"
  [ "$status" -eq 0 ]
  sans_horodatage | grep -Ex "couple de l'instantané inconnu : $BATS_TEST_TMPDIR/$SNAPSHOT\.couple\.age illisible \(déchiffrement impossible : age: error: no identity matched any of the recipients.*\)"
  aucune_ligne '^age:' <(printf '%s\n' "$output")
  diff -r "$BATS_TEST_TMPDIR/attendu" "$DONNEES"
  echo "pas un couple" >"$pre/20261014T120000Z.couple"
  restaurer prod "$pre/20261014T120000Z" --oui
  [ "$status" -eq 0 ]
  sans_horodatage | grep -Fx "couple de l'instantané inconnu : $pre/20261014T120000Z.couple illisible (attendu : « <image> <version> <commit> »)"
  diff -r "$pre/20261014T120000Z" "$DONNEES"
  rm "$pre/20261014T120000Z.couple"
  echo "$autre 0.0.9 -" >"$BATS_TEST_TMPDIR/couple-ailleurs"
  ln -s "$BATS_TEST_TMPDIR/couple-ailleurs" "$pre/20261014T120000Z.couple"
  restaurer prod "$pre/20261014T120000Z" --oui
  [ "$status" -eq 0 ]
  sans_horodatage | grep -Fx "couple de l'instantané inconnu : $pre/20261014T120000Z.couple illisible (un lien, qui n'est jamais suivi)"
  diff -r "$pre/20261014T120000Z" "$DONNEES"
  aucun_temporaire
}

# Une identité chiffrée par phrase de passe, au format binaire (`age -p`, sans -a), dans un fichier :
# age la lit lui-même, octets nuls compris, comme avant le lot 12 ; la phrase se demande au terminal,
# une fois pour l'archive, une fois pour son couple. `script` tient lieu de terminal. La clé sur
# l'entrée standard, elle, ne se lit qu'une fois, en mémoire (« restaurer : dit le couple de
# l'instantané »).
@test "restaurer : une identité chiffrée par phrase de passe, dans un fichier" {
  local autre d cle="$BATS_TEST_TMPDIR/hors-ligne.age" tentative=0
  autre="ghcr.io/edouardzemb/veille-emploi@sha256:$(printf '2%.0s' {1..64})"
  d="$(printf 'd%.0s' {1..40})"
  export PHRASE=phrase-de-test-seulement CLE_CHIFFREE="$cle" ARCHIVE="$BATS_TEST_TMPDIR/$SNAPSHOT.tar.age"
  archive_chiffree
  donnees_courantes
  printf '%s\n' "$autre 0.0.8 $d" | chiffrer "$BATS_TEST_TMPDIR/$SNAPSHOT.couple.age"
  # le format binaire : l'en-tête d'age, et des octets nuls. Le chiffré est aléatoire : un octet nul
  # n'y est pas toujours (une fois sur deux environ, pour une identité de cette taille), et le test
  # rechiffre jusqu'à en avoir un
  until [ -s "$cle" ] && [ "$(tr -dc '\000' <"$cle" | wc -c)" -gt 0 ]; do
    tentative=$((tentative + 1))
    [ "$tentative" -le 40 ]
    rm -f "$cle"
    printf '%s\n%s\n' "$PHRASE" "$PHRASE" | script -qec "age -p -o '$cle' '$AGE_IDENTITE_HORS_LIGNE'" /dev/null >/dev/null
  done
  [ "$(head -c 21 "$cle")" = age-encryption.org/v1 ]
  cat >"$BATS_TEST_TMPDIR/restaurer-au-terminal" <<'SCRIPT'
#!/usr/bin/env bash
exec bash "$CLONE/deploiement/restaurer.sh" prod "$ARCHIVE" --oui --cle "$CLE_CHIFFREE"
SCRIPT
  run bash -c 'printf "%s\n%s\n" "$PHRASE" "$PHRASE" | script -qec "bash '"$BATS_TEST_TMPDIR"'/restaurer-au-terminal" /dev/null'
  output="${output//$'\r'/}"
  [ "$status" -eq 0 ]
  diff -r "$BATS_TEST_TMPDIR/attendu" "$DONNEES"
  sans_horodatage | grep -Fx "couple de l'instantané : $autre 0.0.8 $d (couple déployé : $IMAGE 0.1.0 -)"
  # deux demandes de la phrase : l'archive, puis son couple
  [ "$(printf '%s\n' "$output" | grep -c 'Enter passphrase')" -eq 2 ]
  [ -z "$(grep -rl 'AGE-SECRET-KEY' "$HOME" "$TMPDIR" "$ETAT" "$SAUVEGARDES" "$DONNEES" || true)" ]
  aucun_temporaire
}

# Une archive d'avant la v0.7.0, sans .couple.age, se restaure exactement comme avant, la clé dans
# un fichier comme sur l'entrée standard : le même journal, une ligne de plus, « couple de
# l'instantané inconnu », et les mêmes appels de Docker.
@test "restaurer : une archive sans couple se restaure comme avant" {
  archive_chiffree
  donnees_courantes
  local archive="$BATS_TEST_TMPDIR/$SNAPSHOT.tar.age" revision="${IMAGE##*:}"
  local ancien="$SAUVEGARDES/avant-restauration-<horodatage>"
  revision="${revision:0:40}"
  horloge_qui_avance
  restaurer prod "$archive" --oui --cle "$AGE_IDENTITE_HORS_LIGNE"
  [ "$status" -eq 0 ]
  diff -r "$BATS_TEST_TMPDIR/attendu" "$DONNEES"
  diff - <(sans_horodatage) <<JOURNAL
restauration de prod depuis $archive (image $IMAGE, version 0.1.0)
copie conforme (verifier : code 0)
instantané conforme : $archive (3 fichiers)
couple de l'instantané inconnu
arrêt de l'application
ancien contenu gardé dans $ancien
démarrage de l'application
santé conforme sur le port 4310 (essai 1) : {"statut":"ok","environnement":"prod","version":"0.1.0","revision":"$revision"}
restauration terminée : $archive ; l'ancien contenu est dans $ancien
JOURNAL
  diff - <(appels_de docker | sed -E 's/-restauration\.[A-Za-z0-9]+\//-restauration.<tmp>\//') <<APPELS_DOCKER
docker run --rm $OPTIONS_JETABLES -v $TMPDIR/veille-emploi-restauration.<tmp>/donnees:/donnees $IMAGE outil verifier /donnees
$(dc_prod) stop app
$(dc_prod) start app
docker image inspect -f {{index .Config.Labels "org.opencontainers.image.revision"}} $IMAGE
APPELS_DOCKER
  aucun_temporaire
  # la clé sur l'entrée standard : la même restauration, le même journal
  : >"$APPELS"
  export ARCHIVE="$archive"
  run bash -c 'cat "$AGE_IDENTITE_HORS_LIGNE" | bash "$CLONE/deploiement/restaurer.sh" prod "$ARCHIVE" --oui --cle /dev/stdin'
  [ "$status" -eq 0 ]
  diff -r "$BATS_TEST_TMPDIR/attendu" "$DONNEES"
  [ "$(sans_horodatage | grep -c "couple de l'instantané")" -eq 1 ]
  sans_horodatage | grep -Fx "couple de l'instantané inconnu"
  sans_horodatage | grep -Fx "restauration terminée : $archive ; l'ancien contenu est dans $ancien"
  aucun_temporaire
}

@test "restaurer_signale_une_sante_en_echec_et_dit_ou_est_l_ancien_contenu" {
  instantane "$SNAPSHOT" 1
  donnees_courantes
  export DOUBLE_CURL_SANTE_KO="$IMAGE"
  restaurer prod "$SAUVEGARDES/quotidiennes/$SNAPSHOT" --oui
  [ "$status" -eq 1 ]
  local avant=("$SAUVEGARDES"/avant-restauration-*)
  [[ "$output" == *"santé non conforme"* ]]
  [[ "$output" == *"${avant[0]}"* ]]
  # la restauration est faite et reste en place : l'ancien contenu n'est pas remis en douce
  diff -r "$SAUVEGARDES/quotidiennes/$SNAPSHOT" "$DONNEES"
  [ "$(cat "${avant[0]}/courant.txt")" = "contenu courant" ]
}

@test "restaurer_ne_touche_pas_aux_donnees_si_la_copie_echoue_avant_l_arret" {
  instantane "$SNAPSHOT" 1
  donnees_courantes
  # la copie de travail se prépare à côté des données : là, on ne peut pas écrire
  chmod 555 "$(dirname "$DONNEES")"
  restaurer prod "$SAUVEGARDES/quotidiennes/$SNAPSHOT" --oui
  [ "$status" -eq 1 ]
  # la copie se prépare avant l'arrêt : l'application n'a pas été arrêtée
  [ -z "$(appels_de docker | grep -E ' (stop|start) ' || true)" ]
  [ -f "$EN_SERVICE" ]
  contenu_courant_intact
  aucun_dossier_avant_restauration
  aucun_temporaire
}

@test "restaurer_relance_l_application_si_son_arret_echoue" {
  instantane "$SNAPSHOT" 1
  donnees_courantes
  # `compose stop` échoue : on ne sait pas dans quel état est l'application
  export DOUBLE_DOCKER_STOP_ECHEC=1
  restaurer prod "$SAUVEGARDES/quotidiennes/$SNAPSHOT" --oui
  [ "$status" -eq 1 ]
  [ -n "$(appels_de docker | grep ' start app' || true)" ]
  contenu_courant_intact
  aucun_dossier_avant_restauration
  [ ! -e "$DONNEES.nouvelle" ]
}

@test "restaurer_attend_le_verrou_partage_puis_s_execute" {
  instantane "$SNAPSHOT" 1
  donnees_courantes
  tenir_le_verrou "$ETAT/verrou"
  bash "$CLONE/deploiement/restaurer.sh" prod "$SAUVEGARDES/quotidiennes/$SNAPSHOT" --oui \
    >"$BATS_TEST_TMPDIR/sortie" 2>&1 3>&- &
  local restauration=$!
  sleep 2
  kill -0 "$restauration"
  [ -z "$(appels_de docker)" ]
  contenu_courant_intact
  relacher_le_verrou
  wait "$restauration"
  diff -r "$SAUVEGARDES/quotidiennes/$SNAPSHOT" "$DONNEES"
}

@test "restaurer_abandonne_si_le_verrou_reste_pris" {
  instantane "$SNAPSHOT" 1
  donnees_courantes
  export VEILLE_EMPLOI_VERROU_ATTENTE=1
  tenir_le_verrou "$ETAT/verrou"
  restaurer prod "$SAUVEGARDES/quotidiennes/$SNAPSHOT" --oui
  relacher_le_verrou
  [ "$status" -eq 1 ]
  [[ "$output" == *"toujours pris après 1 s"* ]]
  [ -z "$(appels_de docker)" ]
  contenu_courant_intact
}

@test "restaurer_tient_le_verrou_jusqu_a_la_fin" {
  instantane "$SNAPSHOT" 1
  donnees_courantes
  # la santé ne revient pas : la restauration reste longtemps dans sa dernière étape
  export DOUBLE_CURL_SANTE_KO="$IMAGE"
  export VEILLE_EMPLOI_SANTE_DELAI=1
  setsid bash "$CLONE/deploiement/restaurer.sh" prod "$SAUVEGARDES/quotidiennes/$SNAPSHOT" --oui \
    >"$BATS_TEST_TMPDIR/sortie" 2>&1 3>&- &
  local pid=$!
  attendre_appel curl
  run ! flock -n "$ETAT/verrou" true
  kill -TERM -- "-$pid"
  wait "$pid" || true
  flock -n "$ETAT/verrou" true
}

@test "restaurer_sans_secrets_s_arrete_avec_le_code_3" {
  instantane "$SNAPSHOT" 1
  rm "$CLONE_DONNEES/$SOUS_SECRETS/prod.env.enc"
  restaurer prod "$SAUVEGARDES/quotidiennes/$SNAPSHOT" --oui
  [ "$status" -eq 3 ]
  [ -z "$(appels_de docker)" ]
}

@test "restaurer_refuse_une_image_heritee_de_l_environnement" {
  instantane "$SNAPSHOT" 1
  donnees_courantes
  VEILLE_EMPLOI_VERSION=9.9.9 restaurer prod "$SAUVEGARDES/quotidiennes/$SNAPSHOT" --oui
  [ "$status" -eq 1 ]
  [[ "$output" == *"VEILLE_EMPLOI_VERSION est posée dans l'environnement"* ]]
  [ -z "$(appels_de docker)" ]
  contenu_courant_intact
}

@test "restaurer_exige_la_revision_deployee_apres_le_redemarrage" {
  instantane "$SNAPSHOT" 1
  donnees_courantes
  export DOUBLE_CURL_REVISION_FAUSSE="$IMAGE"
  restaurer prod "$SAUVEGARDES/quotidiennes/$SNAPSHOT" --oui
  [ "$status" -eq 1 ]
  [[ "$output" == *"santé non conforme"* ]]
}

@test "restaurer_ne_relance_pas_l_application_si_l_ancien_contenu_ne_revient_pas" {
  instantane "$SNAPSHOT" 1
  donnees_courantes
  # la mise en place de l'instantané échoue, puis le retour de l'ancien contenu depuis le dossier de
  # restauration échoue aussi : relancer l'application la ferait démarrer sur des données vides
  double_mv_en_echec '*/donnees.nouvelle/*' '*/avant-restauration-*/*'
  restaurer prod "$SAUVEGARDES/quotidiennes/$SNAPSHOT" --oui
  [ "$status" -ne 0 ]
  local avant=("$SAUVEGARDES"/avant-restauration-*)
  [ "${#avant[@]}" -eq 1 ]
  # l'application a été arrêtée et n'a pas été relancée
  [ -n "$(appels_de docker | grep ' stop app' || true)" ]
  [ -z "$(appels_de docker | grep ' start app' || true)" ]
  [ ! -f "$EN_SERVICE" ]
  [[ "$output" == *"intervention nécessaire : l'ancien contenu n'est pas entièrement revenu"*"${avant[0]}"* ]]
  [[ "$output" != *"ancien contenu remis en place"* ]]
  aucune_ligne '[Vv]ider' <(printf '%s\n' "$output")
  # les vraies données ne sont perdues nulle part : elles sont dans le dossier de restauration
  [ "$(cat "${avant[0]}/courant.txt")" = "contenu courant" ]
  [ "$(cat "${avant[0]}/.courant")" = "caché courant" ]
  [ "$(cat "${avant[0]}/journal/entree.txt")" = "journal courant" ]
  [ "$(nombre_d_entrees "$DONNEES")" -eq 0 ]
  aucun_temporaire
}

# L'instantané ne ressort pas des données. L'ancien contenu est alors entier dans
# avant-restauration-*/, et ce qui reste dans les données n'est fait que de copies de l'instantané. La
# consigne le dit, et ne prescrit jamais de vider quoi que ce soit.
@test "restaurer_intervention_si_l_instantane_ne_ressort_pas" {
  instantane "$SNAPSHOT" 1
  donnees_courantes
  # .cachee et donnees.txt entrent, sous/ échoue, puis .cachee ne ressort pas des données
  double_mv_en_echec '*/donnees.nouvelle/sous' '*/prod/donnees/.cachee'
  restaurer prod "$SAUVEGARDES/quotidiennes/$SNAPSHOT" --oui
  [ "$status" -eq 1 ]
  local avant=("$SAUVEGARDES"/avant-restauration-*)
  [[ "$output" == *"intervention nécessaire : l'ancien contenu est entier dans ${avant[0]}"*"des copies"* ]]
  aucune_ligne '[Vv]ider' <(printf '%s\n' "$output")
  # l'application reste arrêtée
  [ -z "$(appels_de docker | grep ' start app' || true)" ]
  [ ! -f "$EN_SERVICE" ]
  # l'ancien contenu, entier, est dans le dossier de restauration ; les données n'ont que des copies
  [ "$(cat "${avant[0]}/courant.txt")" = "contenu courant" ]
  [ "$(cat "${avant[0]}/.courant")" = "caché courant" ]
  [ "$(cat "${avant[0]}/journal/entree.txt")" = "journal courant" ]
  [ "$(nombre_d_entrees "${avant[0]}")" -eq 3 ]
  [ "$(find "$DONNEES" -mindepth 1 -maxdepth 1 -printf '%f\n' | sort | tr '\n' ' ')" = ".cachee donnees.txt " ]
  aucun_temporaire
}

# L'ancien contenu ne revient qu'en partie. Il est réparti entre les données et
# avant-restauration-*/, et rien de l'instantané ne reste dans les données : la consigne dit de ne
# rien supprimer et de remettre ce qui manque.
@test "restaurer_intervention_si_l_ancien_contenu_revient_en_partie" {
  instantane "$SNAPSHOT" 1
  donnees_courantes
  # sous/ n'entre pas, puis journal/ ne revient pas
  double_mv_en_echec '*/donnees.nouvelle/sous' '*/avant-restauration-*/journal'
  restaurer prod "$SAUVEGARDES/quotidiennes/$SNAPSHOT" --oui
  [ "$status" -eq 1 ]
  local avant=("$SAUVEGARDES"/avant-restauration-*)
  [[ "$output" == *"intervention nécessaire : l'ancien contenu n'est pas entièrement revenu"*"${avant[0]}"*"Ne rien supprimer"* ]]
  aucune_ligne '[Vv]ider' <(printf '%s\n' "$output")
  [ -z "$(appels_de docker | grep ' start app' || true)" ]
  [ ! -f "$EN_SERVICE" ]
  # réparti : une part dans les données, le reste de côté, rien de l'instantané
  [ "$(find "$DONNEES" -mindepth 1 -maxdepth 1 -printf '%f\n' | sort | tr '\n' ' ')" = ".courant courant.txt " ]
  [ "$(cat "$DONNEES/courant.txt")" = "contenu courant" ]
  [ "$(ls -A "${avant[0]}")" = journal ]
  [ "$(cat "${avant[0]}/journal/entree.txt")" = "journal courant" ]
  aucun_temporaire
}

@test "restaurer_signale_un_redemarrage_impossible_et_dit_ou_est_l_ancien_contenu" {
  instantane "$SNAPSHOT" 1
  donnees_courantes
  export DOUBLE_DOCKER_START_ECHEC=1
  restaurer prod "$SAUVEGARDES/quotidiennes/$SNAPSHOT" --oui
  [ "$status" -eq 1 ]
  local avant=("$SAUVEGARDES"/avant-restauration-*)
  # le message d'erreur lui-même (pas seulement le journal qui précède) dit où est l'ancien contenu
  echo "$output" | grep "redémarrage de l'application impossible" | grep -F "${avant[0]}"
  # l'instantané est en place, l'ancien contenu est gardé : rien n'est défait en douce
  diff -r "$SAUVEGARDES/quotidiennes/$SNAPSHOT" "$DONNEES"
  [ "$(cat "${avant[0]}/courant.txt")" = "contenu courant" ]
  [ ! -f "$EN_SERVICE" ]
}

@test "restaurer_sans_donnees_courantes_dit_qu_il_n_y_avait_pas_d_ancien_contenu" {
  instantane "$SNAPSHOT" 1
  restaurer prod "$SAUVEGARDES/quotidiennes/$SNAPSHOT" --oui
  [ "$status" -eq 0 ]
  diff -r "$SAUVEGARDES/quotidiennes/$SNAPSHOT" "$DONNEES"
  # pas de dossier annoncé puis supprimé
  [[ "$output" == *"aucun ancien contenu"* ]]
  [[ "$output" != *"avant-restauration-"* ]]
  aucun_dossier_avant_restauration
}

@test "restaurer_sans_donnees_courantes_ne_cite_pas_de_dossier_quand_la_sante_echoue" {
  instantane "$SNAPSHOT" 1
  export DOUBLE_CURL_SANTE_KO="$IMAGE"
  restaurer prod "$SAUVEGARDES/quotidiennes/$SNAPSHOT" --oui
  [ "$status" -eq 1 ]
  [[ "$output" == *"santé non conforme"* ]]
  [[ "$output" == *"aucun ancien contenu"* ]]
  [[ "$output" != *"avant-restauration-"* ]]
}

# ==============================================================================================
# restaurer.sh : le report (REPORTER)
# ==============================================================================================

# Un projet qui garde dans ses données un état qu'une restauration ne doit pas défaire (M-0005)
# déclare REPORTER dans deploiement/projet.env. Application arrêtée, la commande lit une copie
# jetable des données en service (/actuel) et écrit dans la copie de l'instantané (/donnees) ce
# qui doit survivre, avant que celle-ci ne soit mise en place.

SECTION="Reporter à la main"
OPTIONS_JETABLES="--user 1000:1000 --read-only --tmpfs /tmp --cap-drop ALL --security-opt no-new-privileges:true --memory 384m"

# Sans REPORTER, la restauration est celle d'avant le crochet, à l'octet près : le plan, le journal
# et les appels de Docker. Le projet.env du setup ne le déclare pas. Seul ajout au journal depuis,
# le couple de l'instantané, inconnu ici : l'instantané n'a pas de .couple.
@test "restaurer_sans_reporter_ne_change_rien" {
  instantane "$SNAPSHOT" 1
  donnees_courantes
  restaurer prod "$SAUVEGARDES/quotidiennes/$SNAPSHOT"
  [ "$status" -eq 64 ]
  diff - <(printf '%s\n' "$output") <<PLAN
Restauration des données de prod (rien n'est fait sans --oui).

  source        : $SAUVEGARDES/quotidiennes/$SNAPSHOT
  forme         : dossier d'instantané, copié dans un dossier temporaire détruit à la fin
  données       : $DONNEES (tout son contenu)
  gardées dans  : $SAUVEGARDES/avant-restauration-<horodatage UTC>/

Étapes :
  1. verrou partagé avec la sonde et le déploiement (600 s d'attente au plus)
  2. contrôle de l'instantané par la commande VERIFIER de l'image déployée ; rien n'est touché s'il n'est pas conforme
  3. arrêt de l'application
  4. contenu courant des données mis de côté, contenu de l'instantané mis à sa place
  5. redémarrage, puis contrôle de la santé sur 127.0.0.1:4310

Pour l'exécuter, relancer la même commande avec --oui.
PLAN

  : >"$APPELS"
  restaurer prod "$SAUVEGARDES/quotidiennes/$SNAPSHOT" --oui
  [ "$status" -eq 0 ]
  local revision="${IMAGE##*:}" ancien="$SAUVEGARDES/avant-restauration-<horodatage>"
  revision="${revision:0:40}"
  diff - <(sans_horodatage) <<JOURNAL
restauration de prod depuis $SAUVEGARDES/quotidiennes/$SNAPSHOT (image $IMAGE, version 0.1.0)
copie conforme (verifier : code 0)
instantané conforme : $SAUVEGARDES/quotidiennes/$SNAPSHOT (3 fichiers)
couple de l'instantané inconnu
arrêt de l'application
ancien contenu gardé dans $ancien
démarrage de l'application
santé conforme sur le port 4310 (essai 1) : {"statut":"ok","environnement":"prod","version":"0.1.0","revision":"$revision"}
restauration terminée : $SAUVEGARDES/quotidiennes/$SNAPSHOT ; l'ancien contenu est dans $ancien
JOURNAL
  # Docker : la vérification, l'arrêt, le redémarrage, la révision ; aucun autre conteneur
  diff - <(appels_de docker | sed -E 's/-restauration\.[A-Za-z0-9]+\//-restauration.<tmp>\//') <<APPELS_DOCKER
docker run --rm $OPTIONS_JETABLES -v $TMPDIR/veille-emploi-restauration.<tmp>/donnees:/donnees $IMAGE outil verifier /donnees
$(dc_prod) stop app
$(dc_prod) start app
docker image inspect -f {{index .Config.Labels "org.opencontainers.image.revision"}} $IMAGE
APPELS_DOCKER
  aucune_copie_jetable
}

@test "restaurer_reporte_apres_l_arret_et_avant_la_mise_de_cote" {
  instantane "$SNAPSHOT" 1
  donnees_courantes
  cp -R "$DONNEES" "$BATS_TEST_TMPDIR/donnees-avant"
  reporter_declare "$SECTION"
  restaurer prod "$SAUVEGARDES/quotidiennes/$SNAPSHOT" --oui
  [ "$status" -eq 0 ]

  # un seul report : la commande de projet.env, dans un conteneur jetable de l'image déployée, sur
  # une copie des données en service (/actuel) et sur la copie de l'instantané (/donnees), jamais
  # sur les données elles-mêmes
  [ "$(appels_de docker | grep -cF ' /actuel /donnees')" -eq 1 ]
  local report
  report="$(appels_de docker | grep -F ' /actuel /donnees')"
  [[ "$report" == "docker run --rm $OPTIONS_JETABLES -v $SAUVEGARDES/report-"*":/actuel -v $DONNEES.nouvelle:/donnees $IMAGE outil reporter /actuel /donnees" ]]
  [[ "$report" != *" -v $DONNEES:"* ]]
  [ "$(cat "$BATS_TEST_TMPDIR/report-mots")" = "$(printf '%s\n' outil reporter /actuel /donnees)" ]
  # dans l'ordre : la vérification, l'arrêt, le report, puis le redémarrage
  [ "$(ligne_de ' outil verifier /donnees')" -lt "$(ligne_de ' stop app')" ]
  [ "$(ligne_de ' stop app')" -lt "$(ligne_de ' /actuel /donnees')" ]
  [ "$(ligne_de ' /actuel /donnees')" -lt "$(ligne_de ' start app')" ]
  # avant la mise de côté : les données en service étaient encore en place, et /actuel en était
  # la copie
  diff -r "$BATS_TEST_TMPDIR/donnees-avant" "$BATS_TEST_TMPDIR/report-en-service"
  diff -r "$BATS_TEST_TMPDIR/donnees-avant" "$BATS_TEST_TMPDIR/report-actuel"
  # ce que la commande a écrit dans /donnees est dans les données mises en place, avec l'instantané
  [ "$(cat "$DONNEES/reporte.txt")" = "reporté depuis /actuel : contenu courant" ]
  diff -r -x reporte.txt "$SAUVEGARDES/quotidiennes/$SNAPSHOT" "$DONNEES"
  # l'ancien contenu est gardé, entier ; le journal dit le report, et ne rappelle rien
  local avant=("$SAUVEGARDES"/avant-restauration-*)
  diff -r "$BATS_TEST_TMPDIR/donnees-avant" "${avant[0]}"
  [[ "$output" == *"report fait (reporter : code 0) : {\"reportes\":1}"*"restauration terminée"* ]]
  [[ "$output" != *"attention"* ]]
  [ ! -e "$DONNEES.nouvelle" ]
  aucune_copie_jetable
  aucun_temporaire
}

@test "restaurer_report_n_ecrit_jamais_les_donnees_en_service" {
  instantane "$SNAPSHOT" 1
  donnees_courantes
  cp -R "$DONNEES" "$BATS_TEST_TMPDIR/donnees-avant"
  reporter_declare "$SECTION"
  restaurer prod "$SAUVEGARDES/quotidiennes/$SNAPSHOT" --oui
  [ "$status" -eq 0 ]
  # la commande a écrit dans /actuel...
  [ "$(cat "$BATS_TEST_TMPDIR/report-actuel-apres/trace-du-report")" = "écrit par le report" ]
  [ "$(tail -n 1 "$BATS_TEST_TMPDIR/report-actuel-apres/courant.txt")" = "écrit par le report" ]
  # ...qui n'était qu'une copie : ni l'ancien contenu gardé, ni les données mises en place, ni rien
  # dans les sauvegardes n'en porte la trace
  local avant=("$SAUVEGARDES"/avant-restauration-*)
  diff -r "$BATS_TEST_TMPDIR/donnees-avant" "${avant[0]}"
  [ ! -e "$DONNEES/trace-du-report" ]
  [ -z "$(grep -rl 'écrit par le report' "$DONNEES" "$SAUVEGARDES" || true)" ]
}

# R57 : tout échec du report abandonne la restauration, rien n'a changé. Le message dit la cause,
# puis l'issue : --sans-report, et la section du runbook.
@test "restaurer_report_en_echec_abandonne_sans_rien_changer" {
  instantane "$SNAPSHOT" 1
  donnees_courantes
  reporter_declare "$SECTION"
  local code
  for code in 1 64; do
    : >"$APPELS"
    DOUBLE_DOCKER_REPORT_CODE="$code" restaurer prod "$SAUVEGARDES/quotidiennes/$SNAPSHOT" --oui
    [ "$status" -eq 1 ]
    # le message d'erreur lui-même : la cause, l'abandon, puis --sans-report et la section
    echo "$output" | grep -F "la restauration est abandonnée, rien n'a changé" \
      | grep -F -- "relancer avec --sans-report, puis « $SECTION » (docs/exploitation.md)"
    if [ "$code" -eq 64 ]; then
      echo "$output" | grep -F "la restauration est abandonnée" | grep -F "l'image déployée ne connaît pas la commande REPORTER (outil reporter)"
    else
      [[ "$output" == *"report en échec (reporter : code 1)"* ]]
      [[ "$output" != *"ne connaît pas"* ]]
    fi
    # arrêtée pour le report, puis relancée sur les données en service, intactes
    [ "$(ligne_de ' stop app')" -lt "$(ligne_de ' /actuel /donnees')" ]
    [ "$(ligne_de ' /actuel /donnees')" -lt "$(ligne_de ' start app')" ]
    [ -f "$EN_SERVICE" ]
    contenu_courant_intact
    # la copie de l'instantané, et ce que la commande y avait écrit, sont retirées
    [ ! -e "$DONNEES.nouvelle" ]
    aucun_dossier_avant_restauration
    aucune_copie_jetable
    aucun_temporaire
    # rien n'a été restauré : rien à rappeler
    [[ "$output" != *"attention"* ]]
  done
  # sans section déclarée, le message renvoie au runbook
  sed -i '/^REPORTER_SECTION=/d' "$CLONE/deploiement/projet.env"
  DOUBLE_DOCKER_REPORT_CODE=1 restaurer prod "$SAUVEGARDES/quotidiennes/$SNAPSHOT" --oui
  [ "$status" -eq 1 ]
  echo "$output" | grep -F -- "relancer avec --sans-report, puis reporter à la main (docs/exploitation.md)"
  contenu_courant_intact
}

@test "restaurer_sans_report_rappelle_la_section" {
  instantane "$SNAPSHOT" 1
  donnees_courantes
  reporter_declare "$SECTION"
  horloge_qui_avance
  restaurer prod "$SAUVEGARDES/quotidiennes/$SNAPSHOT" --sans-report --oui
  [ "$status" -eq 0 ]
  # pas de report : ni conteneur, ni copie jetable ; la restauration est faite
  [ -z "$(appels_de docker | grep -F '/actuel' || true)" ]
  diff -r "$SAUVEGARDES/quotidiennes/$SNAPSHOT" "$DONNEES"
  aucune_copie_jetable
  # le journal le dit à l'étape, et le rappel, avec la raison et la section, est la dernière ligne
  [[ "$output" == *"--sans-report : pas de report"*"restauration terminée"* ]]
  [[ "$(sans_horodatage | tail -n 1)" == "attention : le report n'a pas eu lieu (--sans-report) : "*" ; voir « $SECTION » (docs/exploitation.md)" ]]
  # sans section déclarée, le rappel renvoie au runbook
  sed -i '/^REPORTER_SECTION=/d' "$CLONE/deploiement/projet.env"
  restaurer prod "$SAUVEGARDES/quotidiennes/$SNAPSHOT" --sans-report --oui
  [ "$status" -eq 0 ]
  [[ "$(sans_horodatage | tail -n 1)" == "attention : le report n'a pas eu lieu (--sans-report) : "*" ; voir docs/exploitation.md" ]]
}

# Un serveur reconstruit, un dossier de données vide : rien à reporter, et ce n'est pas une erreur.
@test "restaurer_sans_donnees_en_service_ne_reporte_pas" {
  instantane "$SNAPSHOT" 1
  reporter_declare "$SECTION"
  restaurer prod "$SAUVEGARDES/quotidiennes/$SNAPSHOT" --oui
  [ "$status" -eq 0 ]
  [ -z "$(appels_de docker | grep -F '/actuel' || true)" ]
  diff -r "$SAUVEGARDES/quotidiennes/$SNAPSHOT" "$DONNEES"
  [[ "$output" == *"aucune donnée en service : pas de report"* ]]
  [[ "$(sans_horodatage | tail -n 1)" == "attention : le report n'a pas eu lieu (aucune donnée en service) : "*" ; voir « $SECTION » (docs/exploitation.md)" ]]
  aucune_copie_jetable
}

# Le rappel suit aussi l'échec d'une restauration dont l'instantané est en place : le redémarrage
# ou la santé. Avant la mise en place, rien n'est restauré, et il n'y a rien à rappeler.
@test "restaurer_rappel_aussi_sur_echec_apres_mise_en_place" {
  instantane "$SNAPSHOT" 1
  donnees_courantes
  reporter_declare "$SECTION"
  horloge_qui_avance
  DOUBLE_CURL_SANTE_KO="$IMAGE" restaurer prod "$SAUVEGARDES/quotidiennes/$SNAPSHOT" --sans-report --oui
  [ "$status" -eq 1 ]
  [[ "$output" == *"santé non conforme"*"attention : le report n'a pas eu lieu (--sans-report)"*"« $SECTION » (docs/exploitation.md)"* ]]
  [[ "$(sans_horodatage | tail -n 1)" == "attention : le report n'a pas eu lieu (--sans-report) : "* ]]
  DOUBLE_DOCKER_START_ECHEC=1 restaurer prod "$SAUVEGARDES/quotidiennes/$SNAPSHOT" --sans-report --oui
  [ "$status" -eq 1 ]
  [[ "$output" == *"redémarrage de l'application impossible"*"attention : le report n'a pas eu lieu (--sans-report)"* ]]
  # avant la mise en place : pas de rappel
  DOUBLE_DOCKER_VERIFIER_CODE=2 restaurer prod "$SAUVEGARDES/quotidiennes/$SNAPSHOT" --sans-report --oui
  [ "$status" -eq 1 ]
  [[ "$output" != *"attention"* ]]
  # un report fait ne se rappelle pas, même quand la santé échoue ensuite
  DOUBLE_CURL_SANTE_KO="$IMAGE" restaurer prod "$SAUVEGARDES/quotidiennes/$SNAPSHOT" --oui
  [ "$status" -eq 1 ]
  [[ "$output" == *"report fait"*"santé non conforme"* ]]
  [[ "$output" != *"attention"* ]]
}

# R58 : sur un code 0, la sortie standard est le rapport, un seul objet JSON, journalisé sur une
# ligne. Une sortie qui n'en est pas un est un échec : le côté sûr.
@test "restaurer_sortie_du_report_journalisee_si_json" {
  instantane "$SNAPSHOT" 1
  donnees_courantes
  reporter_declare "$SECTION"
  horloge_qui_avance
  export DOUBLE_DOCKER_REPORT_SORTIE=$'{\n  "reportes": 2,\n  "detail": "deux entrées"\n}'
  run --separate-stderr bash "$CLONE/deploiement/restaurer.sh" prod "$SAUVEGARDES/quotidiennes/$SNAPSHOT" --oui
  [ "$status" -eq 0 ]
  # rien de la commande sur la sortie standard du script ; au journal, le rapport sur une ligne
  [ -z "$output" ]
  # shellcheck disable=SC2154  # $stderr est posé par run --separate-stderr
  output="$stderr"
  sans_horodatage | grep -Fx 'report fait (reporter : code 0) : {   "reportes": 2,   "detail": "deux entrées" }'
  # code 0, mais pas un rapport : un mot, rien du tout, un document coupé, et null ou false, du
  # JSON valide qui ne rapporte rien (jq -e les refuse ; jq seul les accepterait)
  local sortie
  for sortie in fait '' '{"reportes": 2' null false; do
    rm -rf "$BATS_TEST_TMPDIR/donnees-avant"
    cp -R "$DONNEES" "$BATS_TEST_TMPDIR/donnees-avant"
    DOUBLE_DOCKER_REPORT_SORTIE="$sortie" restaurer prod "$SAUVEGARDES/quotidiennes/$SNAPSHOT" --oui
    [ "$status" -eq 1 ]
    [[ "$output" == *"report en échec (reporter : code 0, mais la sortie n'est pas un rapport)"* ]]
    echo "$output" | grep -F "la restauration est abandonnée, rien n'a changé" | grep -F -- "--sans-report"
    diff -r "$BATS_TEST_TMPDIR/donnees-avant" "$DONNEES"
    [ -f "$EN_SERVICE" ]
    [ ! -e "$DONNEES.nouvelle" ]
    aucune_copie_jetable
  done
}

# Le rapport est un seul objet JSON. Un nombre, une chaîne, true, un tableau ou deux objets à la
# suite sont du JSON que `jq -e .` accepte, mais pas un rapport : le même refus qu'une sortie
# qui n'est pas du JSON.
@test "restaurer_report_exige_un_seul_objet_json" {
  instantane "$SNAPSHOT" 1
  donnees_courantes
  reporter_declare "$SECTION"
  horloge_qui_avance
  local sortie
  for sortie in 42 '"x"' true '[]' '[{"reportes": 2}]' '{"reportes": 1} {"reportes": 2}' \
    $'{"reportes": 1}\n{"reportes": 2}'; do
    rm -rf "$BATS_TEST_TMPDIR/donnees-avant"
    cp -R "$DONNEES" "$BATS_TEST_TMPDIR/donnees-avant"
    DOUBLE_DOCKER_REPORT_SORTIE="$sortie" restaurer prod "$SAUVEGARDES/quotidiennes/$SNAPSHOT" --oui
    [ "$status" -eq 1 ]
    [[ "$output" == *"report en échec (reporter : code 0, mais la sortie n'est pas un rapport)"* ]]
    [[ "$output" != *"report fait"* ]]
    echo "$output" | grep -F "la restauration est abandonnée, rien n'a changé" | grep -F -- "--sans-report"
    diff -r "$BATS_TEST_TMPDIR/donnees-avant" "$DONNEES"
    [ -f "$EN_SERVICE" ]
    [ ! -e "$DONNEES.nouvelle" ]
    aucune_copie_jetable
  done
  # un objet seul passe, sur une ligne
  DOUBLE_DOCKER_REPORT_SORTIE='{"reportes": 0}' restaurer prod "$SAUVEGARDES/quotidiennes/$SNAPSHOT" --oui
  [ "$status" -eq 0 ]
  sans_horodatage | grep -Fx 'report fait (reporter : code 0) : {"reportes": 0}'
}

@test "restaurer_report_en_echec_journalise_sa_sortie" {
  instantane "$SNAPSHOT" 1
  donnees_courantes
  reporter_declare "$SECTION"
  export DOUBLE_DOCKER_REPORT_CODE=3
  export DOUBLE_DOCKER_REPORT_SORTIE=$'sortie une\nsortie deux'
  export DOUBLE_DOCKER_REPORT_ERREUR=$'erreur une\nerreur deux'
  run --separate-stderr bash "$CLONE/deploiement/restaurer.sh" prod "$SAUVEGARDES/quotidiennes/$SNAPSHOT" --oui
  [ "$status" -eq 1 ]
  # rien de la commande sur la sortie standard du script
  [ -z "$output" ]
  # shellcheck disable=SC2154  # $stderr est posé par run --separate-stderr
  output="$stderr"
  # au journal, sur une ligne : le code, puis les deux sorties, aplaties
  sans_horodatage | grep -Fx "report en échec (reporter : code 3) ; sortie standard : sortie une sortie deux ; sortie d'erreur : erreur une erreur deux"
  contenu_courant_intact
}

# La copie jetable des données en service contient des données personnelles : sous le dossier des
# sauvegardes, en 0700, jamais dans le dossier temporaire, et retirée sur tous les chemins de
# sortie (R58). Celle qu'un report tué (SIGKILL) a laissée part à la restauration suivante.
@test "restaurer_copie_jetable_retiree_partout" {
  instantane "$SNAPSHOT" 1
  donnees_courantes
  reporter_declare "$SECTION"
  # après un échec du report
  DOUBLE_DOCKER_REPORT_CODE=1 restaurer prod "$SAUVEGARDES/quotidiennes/$SNAPSHOT" --oui
  [ "$status" -eq 1 ]
  [ "$(cat "$BATS_TEST_TMPDIR/report-mode")" = 700 ]
  aucune_copie_jetable
  # après un échec de la mise en place, que le piège défait
  double_mv_en_echec '*/donnees.nouvelle/sous'
  restaurer prod "$SAUVEGARDES/quotidiennes/$SNAPSHOT" --oui
  [ "$status" -eq 1 ]
  [[ "$output" == *"report fait"*"mise en place de l'instantané impossible"* ]]
  rm -f "$DOUBLES/mv"
  aucune_copie_jetable
  contenu_courant_intact
  # après une interruption pendant le report : le piège la retire, et relance l'application
  rm -f "$BATS_TEST_TMPDIR/report-mots"
  export DOUBLE_DOCKER_REPORT_ATTENTE=30
  setsid bash "$CLONE/deploiement/restaurer.sh" prod "$SAUVEGARDES/quotidiennes/$SNAPSHOT" --oui \
    >"$BATS_TEST_TMPDIR/sortie" 2>&1 3>&- &
  local pid=$!
  for _ in {1..100}; do
    [ ! -e "$BATS_TEST_TMPDIR/report-mots" ] || break
    sleep 0.1
  done
  [ -e "$BATS_TEST_TMPDIR/report-mots" ]
  compgen -G "$SAUVEGARDES/report-*" >/dev/null
  kill -TERM -- "-$pid"
  wait "$pid" || true
  unset DOUBLE_DOCKER_REPORT_ATTENTE
  aucune_copie_jetable
  contenu_courant_intact
  [ -f "$EN_SERVICE" ]
  [ ! -e "$DONNEES.nouvelle" ]
  # le reste d'un report tué de force part au départ de la restauration suivante, qui réussit
  mkdir -m 700 "$SAUVEGARDES/report-20261001T000000Z"
  echo "copie oubliée" >"$SAUVEGARDES/report-20261001T000000Z/courant.txt"
  : >"$APPELS"
  restaurer prod "$SAUVEGARDES/quotidiennes/$SNAPSHOT" --oui
  [ "$status" -eq 0 ]
  [[ "$output" == *"reste d'une restauration interrompue retiré : $SAUVEGARDES/report-20261001T000000Z"*"arrêt de l'application"* ]]
  # la copie jetable de ce report : sous le dossier des sauvegardes, en 0700, hors du dossier
  # temporaire ; puis retirée
  local actuel
  actuel="$(appels_de docker | sed -nE 's/.* -v ([^ ]+):\/actuel .*/\1/p')"
  [[ "$actuel" =~ ^"$SAUVEGARDES"/report-[0-9]{8}T[0-9]{6}Z$ ]]
  [[ "$actuel" != "$TMPDIR"/* ]]
  [ "$(cat "$BATS_TEST_TMPDIR/report-mode")" = 700 ]
  aucune_copie_jetable
  aucun_temporaire
}

@test "restaurer_plan_dit_si_le_report_jouera" {
  instantane "$SNAPSHOT" 1
  donnees_courantes
  reporter_declare "$SECTION"
  restaurer prod "$SAUVEGARDES/quotidiennes/$SNAPSHOT"
  [ "$status" -eq 64 ]
  # le report jouera, avec cette commande, entre l'arrêt et la mise de côté
  [[ "$output" == *"  3. arrêt de l'application"$'\n'"  4. report : outil reporter /actuel /donnees, "*$'\n'"  5. contenu courant des données mis de côté"*$'\n'"  6. redémarrage"* ]]
  [[ "$output" == *"un échec abandonne la restauration, sauf avec --sans-report"* ]]
  # avec --sans-report, il ne jouera pas, et le plan dit où est la procédure
  restaurer prod "$SAUVEGARDES/quotidiennes/$SNAPSHOT" --sans-report
  [ "$status" -eq 64 ]
  [[ "$output" == *"  4. --sans-report : pas de report (REPORTER : outil reporter)"*"« $SECTION » (docs/exploitation.md)"$'\n'"  5. contenu courant"* ]]
  [[ "$output" != *"4. report :"* ]]
  # sans REPORTER, --sans-report est ignorée, et le plan est celui d'avant le crochet
  printf '%s\n' 'SAUVEGARDER=outil sauvegarder --forme dossier' 'VERIFIER=outil verifier' \
    >"$CLONE/deploiement/projet.env"
  restaurer prod "$SAUVEGARDES/quotidiennes/$SNAPSHOT" --sans-report
  [ "$status" -eq 64 ]
  [[ "$output" == *"--sans-report ignorée : deploiement/projet.env ne déclare pas REPORTER"* ]]
  [[ "$output" == *"  4. contenu courant des données mis de côté"* ]]
  [[ "$output" != *"report :"* ]]
  # aucun effet
  [ -z "$(appels_de docker)" ]
  [ ! -e "$ETAT/verrou" ]
  contenu_courant_intact
  aucune_copie_jetable
  aucun_temporaire
}

# Un REPORTER déclaré mais illisible (un caractère du shell, une apostrophe dans la section) est
# refusé avant tout effet, plan compris.
@test "restaurer_refuse_un_reporter_illisible_sans_rien_toucher" {
  instantane "$SNAPSHOT" 1
  donnees_courantes
  local cas oui
  for cas in "REPORTER_SECTION=$SECTION|REPORTER=outil;reporter" \
    "REPORTER=outil reporter|REPORTER_SECTION=Reporter l'état à la main"; do
    printf '%s\n' 'SAUVEGARDER=outil sauvegarder --forme dossier' 'VERIFIER=outil verifier' \
      "${cas%%|*}" "${cas#*|}" >"$CLONE/deploiement/projet.env"
    for oui in --oui ""; do
      # shellcheck disable=SC2086  # sans --oui, l'option disparaît : c'est le plan qui est demandé
      restaurer prod "$SAUVEGARDES/quotidiennes/$SNAPSHOT" $oui
      [ "$status" -eq 1 ]
      [[ "$output" == *"ligne 4 invalide"*"REPORTER est déclaré, mais deploiement/projet.env est illisible : rien n'a changé"* ]]
    done
  done
  [ -z "$(appels_de docker)" ]
  [ ! -e "$ETAT/verrou" ]
  contenu_courant_intact
  aucun_temporaire
}

# R63 : après le report, la copie de l'instantané garde la forme que l'étape 3 exige de
# l'instantané : non vide, rien que des fichiers et des dossiers. Sinon, comme un report en échec,
# rien n'a changé. VERIFIER ne tourne pas une seconde fois : le report change légitimement le
# contenu.
@test "restaurer_recontrole_la_copie_apres_le_report" {
  instantane "$SNAPSHOT" 1
  donnees_courantes
  reporter_declare "$SECTION"
  local forme
  for forme in vide lien; do
    : >"$APPELS"
    DOUBLE_DOCKER_REPORT_FORME="$forme" restaurer prod "$SAUVEGARDES/quotidiennes/$SNAPSHOT" --oui
    [ "$status" -eq 1 ]
    # la commande a répondu 0 et un rapport : c'est la copie qu'elle laisse qui est refusée
    [[ "$output" == *"report fait (reporter : code 0)"* ]]
    if [ "$forme" = vide ]; then
      [[ "$output" == *"la copie de l'instantané est vide après le report"* ]]
    else
      [[ "$output" == *"la copie de l'instantané contient autre chose que des fichiers et des dossiers après le report"* ]]
    fi
    echo "$output" | grep -F "la restauration est abandonnée, rien n'a changé" \
      | grep -F -- "relancer avec --sans-report, puis « $SECTION » (docs/exploitation.md)"
    # une seule vérification, avant l'arrêt ; puis l'application repart sur ses données, intactes
    [ "$(appels_de docker | grep -cF ' outil verifier /donnees')" -eq 1 ]
    [ "$(ligne_de ' /actuel /donnees')" -lt "$(ligne_de ' start app')" ]
    [ -f "$EN_SERVICE" ]
    contenu_courant_intact
    [ ! -e "$DONNEES.nouvelle" ]
    aucun_dossier_avant_restauration
    aucune_copie_jetable
    aucun_temporaire
    [[ "$output" != *"attention"* ]]
  done
}

# Revue C0, M9 : la copie jetable qui ne peut être ni créée ni remplie abandonne la restauration
# avant le report, rien n'a changé : sans elle, la commande lirait des données incomplètes.
@test "restaurer_copie_jetable_impossible_abandonne" {
  instantane "$SNAPSHOT" 1
  donnees_courantes
  reporter_declare "$SECTION"
  local vrai
  vrai="$(command -v cp)"
  # cp échoue vers la copie jetable, comme sur un disque plein
  # shellcheck disable=SC2016  # le corps du double se développe quand il s'exécute, pas ici
  creer_double cp 'case "$*" in *"/report-2"*) echo "cp: No space left on device" >&2; exit 1 ;; esac
exec '"$vrai"' "$@"'
  restaurer prod "$SAUVEGARDES/quotidiennes/$SNAPSHOT" --oui
  rm -f "$DOUBLES/cp"
  [ "$status" -eq 1 ]
  echo "$output" | grep -F "copie des données en service vers $SAUVEGARDES/report-" \
    | grep -F "impossible : la restauration est abandonnée, rien n'a changé" \
    | grep -F -- "relancer avec --sans-report, puis « $SECTION » (docs/exploitation.md)"
  [ -z "$(appels_de docker | grep -F '/actuel' || true)" ]
  [ -f "$EN_SERVICE" ]
  contenu_courant_intact
  [ ! -e "$DONNEES.nouvelle" ]
  aucun_dossier_avant_restauration
  aucune_copie_jetable
  aucun_temporaire
  # mkdir échoue : un lien occupe déjà le nom de la copie ; il n'est pas à elle, et reste
  horloge_qui_avance
  ln -s /nulle-part "$SAUVEGARDES/report-$(jour_de_l_horloge)T000001Z"
  : >"$APPELS"
  restaurer prod "$SAUVEGARDES/quotidiennes/$SNAPSHOT" --oui
  [ "$status" -eq 1 ]
  echo "$output" \
    | grep -F "copie jetable $SAUVEGARDES/report-$(jour_de_l_horloge)T000001Z impossible à créer : la restauration est abandonnée, rien n'a changé" \
    | grep -F -- "relancer avec --sans-report, puis « $SECTION » (docs/exploitation.md)"
  [ -z "$(appels_de docker | grep -F '/actuel' || true)" ]
  [ -L "$SAUVEGARDES/report-$(jour_de_l_horloge)T000001Z" ]
  [ -f "$EN_SERVICE" ]
  contenu_courant_intact
  [ ! -e "$DONNEES.nouvelle" ]
  aucun_dossier_avant_restauration
  aucun_temporaire
}

# R63 : le rapport du crochet se contrôle par jq. Sans jq, refus avant l'arrêt, et rien ne change.
@test "restaurer_sans_jq_refuse_le_report_avant_l_arret" {
  instantane "$SNAPSHOT" 1
  donnees_courantes
  reporter_declare "$SECTION"
  # un PATH qui a tout ce qu'a l'image du banc, sauf jq
  local sans_jq="$BATS_TEST_TMPDIR/sans-jq" outil chemin
  mkdir -p "$sans_jq"
  for outil in /usr/bin/* /bin/*; do
    [ "${outil##*/}" = jq ] || ln -sf "$outil" "$sans_jq/${outil##*/}"
  done
  chemin="$DOUBLES:$sans_jq:/usr/local/bin"
  run ! env PATH="$chemin" sh -c 'command -v jq'
  run env PATH="$chemin" bash "$CLONE/deploiement/restaurer.sh" prod "$SAUVEGARDES/quotidiennes/$SNAPSHOT" --oui
  [ "$status" -eq 1 ]
  # la cause, puis ce qu'il faut faire
  [ "$(sans_horodatage | tail -n 1)" = "jq introuvable : le rapport du crochet ne peut pas être contrôlé. Rien n'a changé : installer jq, qui vient avec les outils du serveur (outils/installer-outils.sh du dépôt serveur), puis relancer" ]
  # ni verrou, ni conteneur, ni copie : l'application n'a pas été arrêtée
  [ -z "$(appels_de docker)" ]
  [ ! -e "$ETAT/verrou" ]
  [ -f "$EN_SERVICE" ]
  contenu_courant_intact
  [ ! -e "$DONNEES.nouvelle" ]
  aucun_dossier_avant_restauration
  aucune_copie_jetable
  aucun_temporaire
}

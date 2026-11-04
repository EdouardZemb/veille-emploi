#!/usr/bin/env bash
# Sauvegarde nocturne des données de prod : un instantané en clair gardé 30 jours sur le serveur, et
# sa copie chiffrée pour la clé hors ligne, envoyée au distant et gardée 90 jours (M-0005).
#
#   bash deploiement/sauvegarder.sh prod
#
# Lancé chaque nuit par veille-emploi-sauvegarde.timer. Réservé à la prod : le staging n'a que des données
# factices (code 64).
#
# Déroulé :
#   0. contrôles qui précèdent tout effet : la destination distante est un dossier précis d'un
#      remote (jamais sa racine), la clé publique hors ligne est là (et n'est pas une clé privée),
#      l'application est déployée, la commande SAUVEGARDER est dans deploiement/projet.env. Sans
#      clé, aucun instantané n'est fait : rien ne part jamais en clair, et l'absence se voit tout
#      de suite ;
#   1. verrou $VEILLE_EMPLOI_ETAT/verrou, partagé avec la sonde, le déploiement et la restauration (600 s
#      d'attente au plus) : pendant un déploiement ou une restauration, les données bougent ;
#   2. nom veille-emploi-<AAAAMMJJTHHMMSSZ> (UTC) ; un dossier déjà présent à ce nom, ou à ce nom suivi
#      de .partiel, est une erreur : rien n'est écrasé. Puis les .partiel des sauvegardes en échec
#      sont retirés de quotidiennes/ : il n'en reste que celui de la dernière. Puis les restes
#      d'une restauration tuée de force (SIGKILL, plantage de l'hôte), hors de portée de son trap :
#      ses copies jetables $VEILLE_EMPLOI_SAUVEGARDES/report-<AAAAMMJJTHHMMSSZ>, des copies en clair des
#      données en service, et sa copie de travail $VEILLE_EMPLOI_DONNEES.nouvelle. La restauration tient
#      ce verrou de bout en bout : ce qui reste n'est à aucune restauration en cours. Ni un lien, ni
#      un nom d'une autre forme. Un retrait impossible est journalisé et n'arrête rien ;
#   3. instantané dans le conteneur : `<SAUVEGARDER…> /sauvegardes/quotidiennes/<nom>.partiel`, qui
#      crée ce dossier, à la forme de /donnees (le contrat de l'image, M-0003). Le code de sortie
#      d'abord (0, sinon échec), puis le dossier lui-même : un dossier, non vide, fait de fichiers et
#      de dossiers seulement (restaurer.sh refuse tout le reste) ; jamais le seul code 0. La sortie
#      de la commande n'est pas interprétée : elle va au journal. Contrôlé, le dossier prend son nom,
#      <nom> (`mv -T`). Une sauvegarde en échec garde le suffixe .partiel, pour le diagnostic,
#      jusqu'à la suivante (étape 2) : le test de restauration et la restauration ne le prennent
#      jamais, et la rétention l'efface comme les autres. Puis, toujours sous le verrou, le couple
#      en service, celui de $VEILLE_EMPLOI_ETAT/deploye, est noté à côté de l'instantané, jamais
#      dedans : <nom>.couple, une ligne « <image> <version> <commit> » (noter_couple, lib.sh).
#      Sans deploye, ou s'il ne se lit pas, pas de .couple, et la sauvegarde continue :
#      restaurer.sh dira le couple inconnu. Le verrou est relâché dès que l'instantané est en
#      place : la suite (chiffrement, envoi, rétention) ne lit plus les données, et un déploiement
#      ou la sonde n'ont pas à attendre les quotas et les reprises du distant ;
#   4. archive tar du dossier (`tar --hard-dereference -C quotidiennes -cf - <nom>` : tous ses
#      membres sont sous <nom>/, et un lien physique y est un fichier ordinaire, que restaurer.sh
#      accepte), chiffrée par `age -R` pour la clé hors ligne du clone des données
#      (<SOUS_DOSSIER_CLES>/hors-ligne.pub, lib.sh), dans un dossier temporaire 0700 ; l'en-tête age
#      est contrôlé. La clé privée n'est pas sur le serveur : personne ici ne peut relire cette
#      archive. Le .couple, s'il y en a un, est chiffré de même, pour la même clé : <nom>.couple.age,
#      à côté de l'archive et à sa date (`touch -r`), que rclone garde au distant. Les données passent
#      avant leur couple : un couple qui ne se chiffre pas, ou ne prend pas cette date, est
#      journalisé, l'archive part seule, et la nuit est signalée en échec à l'étape 7 ;
#   5. `rclone copy` de l'archive, puis de son couple chiffré, vers
#      ${VEILLE_EMPLOI_DISTANT:-sauvegardes:veille-emploi-sauvegardes}, puis `rclone lsf` : l'un et
#      l'autre doivent y figurer. sauvegardes: est l'alias que le serveur fait pointer vers son
#      remote ;
#   6. rétention, seulement après un envoi contrôlé :
#      - en local, les dossiers de plus de 30 jours dans quotidiennes/ (veille-emploi-<horodatage>) et
#        pre-deploiement/ (<horodatage> : le nom que deployer.sh leur donne), .partiel compris,
#        chacun avec son <nom>.couple, et les dossiers avant-restauration-<horodatage> de
#        restaurer.sh, copies en clair des données elles aussi (purger_par_nom, lib.sh). L'âge se
#        lit dans le nom, jamais dans la date du dossier : une commande SAUVEGARDER qui copie
#        /donnees avec ses dates (cp -a, rsync -a) daterait l'instantané du jour comme ses données.
#        Un nom d'une autre forme n'est jamais retiré ;
#      - à distance, `rclone delete --min-age 90d --max-depth 1 --drive-use-trash=false --include
#        'veille-emploi-*.tar.age' --include 'veille-emploi-*.couple.age'` : seules nos archives et leurs
#        couples de plus de 90 jours, directement dans le dossier de la destination (rclone delete
#        est récursif : sans --max-depth 1, un sous-dossier serait vidé aussi). Une archive et son
#        couple ont la même date : le même appel les retire ensemble, ou les garde ensemble. La
#        suppression est définitive : la corbeille d'un Drive garderait ces archives 30 jours de
#        plus, au-delà des 90 jours promis (M-0005). Le distant peut servir à d'autres projets : une
#        destination qui serait la racine du remote est refusée à l'étape 0 ;
#   7. signal HC_SAUVEGARDE ok « <nom> : <N> fichiers » ; un échec si le couple n'est pas parti
#      (étape 4), après l'envoi et la rétention.
#
# Toute erreur, à partir du chargement des secrets, est signalée (HC_SAUVEGARDE /fail) par un trap
# de sortie, qui détruit aussi le dossier temporaire, y compris sur INT, TERM et HUP. Healthchecks
# est un tiers : la raison envoyée est un résumé (le code de la commande, la forme de l'instantané),
# jamais la sortie de la commande, qui peut décrire les données ; la sortie va au journal. Le signal
# d'une erreur n'efface rien : l'instantané local et l'archive envoyée restent. Si la rétention
# échoue, la sauvegarde est faite mais le signal est un échec : il faut libérer de la place avant
# qu'elle manque.
#
# Codes de sortie : 0 ; 1 échec (signalé) ; 3 secrets absents ; 64 usage ou environnement refusé ;
# 129, 130, 143 interruption.
#
# Variables de test : VEILLE_EMPLOI_DISTANT (la destination), VEILLE_EMPLOI_VERROU_ATTENTE (secondes).
set -euo pipefail
# shellcheck source=deploiement/lib.sh
. "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

# Posées par main.
ARME=0 # 1 dès que les secrets sont chargés : une sortie en erreur est alors signalée
RAISON=""
TMP=""

# echouer <raison…> : journalise et quitte avec le code 1 ; le trap de sortie signale l'échec.
echouer() {
  RAISON="$*"
  journal "échec : $RAISON"
  exit 1
}

# echouer_avec_detail <résumé> <détail> : comme echouer, mais seul le résumé part chez Healthchecks
# (un tiers) ; le détail (la sortie de la commande) reste dans le journal.
echouer_avec_detail() {
  RAISON="$1"
  journal "échec : $1${2:+ : $2}"
  exit 1
}

# sortie : trap EXIT. Détruit le dossier temporaire, et signale l'échec d'une sortie en erreur.
# shellcheck disable=SC2317,SC2329  # appelée par trap EXIT
sortie() {
  local code=$?
  trap - EXIT INT TERM HUP
  [ -z "$TMP" ] || rm -rf -- "$TMP"
  if [ "$code" -ne 0 ] && [ "$ARME" -eq 1 ]; then
    [ -n "$RAISON" ] || RAISON="échec inattendu (code $code), voir le journal de l'unité"
    journal "sauvegarde en échec (code $code) : $RAISON"
    signaler HC_SAUVEGARDE echec "$RAISON" || true
    # Une interruption garde son code (128 + signal) ; toute autre erreur vaut 1.
    [ "$code" -ge 128 ] || code=1
  fi
  exit "$code"
}

# valider_distant <remote:dossier> : un dossier précis d'un remote, dans un alphabet sans `..` ni
# espace. `rclone delete` vide ce qu'on lui donne : « sauvegardes: » viserait toute la racine du
# remote, où d'autres projets ont leurs propres sauvegardes.
valider_distant() {
  local motif='^[A-Za-z0-9_][A-Za-z0-9_.-]*:[A-Za-z0-9_][A-Za-z0-9_.-]*(/[A-Za-z0-9_][A-Za-z0-9_.-]*)*$'
  [[ "$1" =~ $motif ]] \
    || echouer "destination distante refusée : '$1' (attendu : <remote>:<dossier>[/<sous-dossier>…], jamais la racine du remote)"
}

# retention_locale : plus de 30 jours d'après leur nom, rien que des dossiers que ce script,
# deployer.sh ou restaurer.sh écrivent, emportés en entier, chacun avec son .couple
# (purger_par_nom, lib.sh).
retention_locale() {
  local limite
  limite="$(date -u -d '30 days ago' +%Y%m%dT%H%M%SZ)" || return 1
  purger_par_nom "$VEILLE_EMPLOI_SAUVEGARDES/quotidiennes" '^veille-emploi-([0-9]{8}T[0-9]{6}Z)(\.partiel)?$' "$limite" \
    || return 1
  purger_par_nom "$VEILLE_EMPLOI_SAUVEGARDES/pre-deploiement" '^([0-9]{8}T[0-9]{6}Z)(\.partiel)?$' "$limite" \
    || return 1
  purger_par_nom "$VEILLE_EMPLOI_SAUVEGARDES" '^avant-restauration-([0-9]{8}T[0-9]{6}Z)$' "$limite"
}

main() {
  [ "$#" -eq 1 ] || arreter 64 "usage : bash deploiement/sauvegarder.sh prod"
  reserver_a_prod "$1" sauvegarder.sh
  # Les secrets de ce déploiement font seuls foi : rien d'hérité du shell.
  unset HC_SAUVEGARDE
  charger_env prod
  charger_secrets prod

  trap sortie EXIT
  trap 'exit 130' INT
  trap 'exit 143' TERM
  trap 'exit 129' HUP
  ARME=1
  refuser_image_heritee

  local etat="$VEILLE_EMPLOI_ETAT" quotidiennes="$VEILLE_EMPLOI_SAUVEGARDES/quotidiennes"
  local distant="${VEILLE_EMPLOI_DISTANT:-sauvegardes:veille-emploi-sauvegardes}"
  local cle="$VEILLE_EMPLOI_CLONE_DONNEES/$SOUS_DOSSIER_CLES/hors-ligne.pub"
  local nom destination instantane partiel sortie code=0 nombre fichiers archive couple="" presents
  local envoyes echec_couple=""

  # 0. Contrôles qui précèdent tout effet.
  valider_distant "$distant"
  [ -s "$cle" ] \
    || echouer "clé publique hors ligne absente ou vide : $cle. Rien n'est sauvegardé : une copie ne part jamais en clair"
  if grep -q 'AGE-SECRET-KEY' "$cle"; then
    echouer "$cle contient une clé privée : la clé privée hors ligne ne doit jamais être sur le serveur"
  fi
  [ -f "$etat/compose.env" ] \
    || echouer "compose.env absent ($etat) : aucune version déployée, rien à sauvegarder"
  lire_projet_env SAUVEGARDER \
    || echouer "commande SAUVEGARDER introuvable dans deploiement/projet.env : rien n'est sauvegardé"

  # 1. Verrou, gardé pendant l'instantané (relâché après l'étape 3).
  prendre_verrou \
    || echouer "verrou $etat/verrou toujours pris après ${VEILLE_EMPLOI_VERROU_ATTENTE:-600} s : sauvegarde abandonnée, rien n'a changé"

  # 2. Nom. Les copies en clair ne sont lisibles que de leur propriétaire (M-0005) ; le conteneur
  # crée l'instantané dans quotidiennes/, sous le même uid. La commande écrit sous un nom
  # provisoire, que l'instantané ne quitte qu'une fois contrôlé.
  nom="veille-emploi-$(date -u +%Y%m%dT%H%M%SZ)"
  instantane="$quotidiennes/$nom"
  partiel="$instantane.partiel"
  destination="/sauvegardes/quotidiennes/$nom.partiel"
  mkdir -p "$quotidiennes"
  chmod 700 "$VEILLE_EMPLOI_SAUVEGARDES" "$quotidiennes" \
    || echouer "droits de $VEILLE_EMPLOI_SAUVEGARDES impossibles à restreindre"
  if [ -e "$instantane" ] || [ -L "$instantane" ] || [ -e "$partiel" ] || [ -L "$partiel" ]; then
    echouer "$instantane existe déjà (ou $partiel) : rien n'est écrasé, rien n'est sauvegardé"
  fi
  # La rétention ne tourne qu'après un envoi réussi ; sans ce retrait, chaque nuit en échec
  # laisserait son .partiel, une copie en clair des données.
  if ! retirer_partiels "$quotidiennes" '^veille-emploi-[0-9]{8}T[0-9]{6}Z\.partiel$'; then
    journal "sauvegardes en échec de $quotidiennes : retrait impossible, plus d'un .partiel y reste ; la sauvegarde se fait quand même"
  fi
  # Les restes d'une restauration tuée de force (SIGKILL, plantage de l'hôte), que son trap
  # n'a pas retirés. La restauration tient ce verrou de bout en bout : ils ne sont à aucune
  # restauration en cours. La copie jetable du report n'a pas d'autre rétention. Un retrait
  # impossible est journalisé, et la sauvegarde se fait quand même.
  retirer_restes_de_restauration || true
  journal "sauvegarde $nom"

  # 3. Instantané. Le code de sortie d'abord (une commande écrit aussi ses erreurs sur stdout), puis
  # le dossier. La sortie ne va qu'au journal : elle peut décrire les données. Un échec garde le nom
  # provisoire.
  sortie="$(dc exec -T app "${PROJET_MOTS[@]}" "$destination")" || code=$?
  sortie="${sortie//$'\n'/ }"
  [ "$code" -eq 0 ] \
    || echouer_avec_detail "instantané impossible (code $code)" "$sortie"
  { [ -d "$partiel" ] && [ ! -L "$partiel" ]; } \
    || echouer_avec_detail "instantané absent du disque : $partiel (la commande a rendu 0 sans écrire le dossier)" "$sortie"
  [ -n "$(find "$partiel" -mindepth 1 -print -quit)" ] \
    || echouer_avec_detail "instantané vide : $partiel (un dossier vide ne prouve rien)" "$sortie"
  [ -z "$(find "$partiel" -mindepth 1 ! -type f ! -type d -print -quit)" ] \
    || echouer_avec_detail "instantané refusé : $partiel contient des entrées qui ne sont ni des fichiers ni des dossiers (liens…), que restaurer.sh refuserait" "$sortie"
  { [ ! -e "$instantane" ] && [ ! -L "$instantane" ] && mv -T -- "$partiel" "$instantane"; } \
    || echouer "instantané contrôlé, mais $partiel ne peut pas prendre le nom $instantane"
  nombre="$(find "$instantane" -type f | wc -l)"
  fichiers="$nombre fichier"
  [ "$nombre" -le 1 ] || fichiers="${fichiers}s"
  journal "instantané : $instantane ($fichiers)${sortie:+ ; sortie : $sortie}"
  # Le couple en service, encore sous le verrou : deploye ne change pas pendant l'instantané. Un
  # couple qui ne se note pas n'arrête pas la sauvegarde des données ; noter_couple le journalise.
  noter_couple "$instantane" || true

  # L'instantané est un dossier fermé : la suite ne lit plus les données. Le verrou est relâché ici,
  # pour que ni un déploiement manuel ni la sonde n'attendent le distant.
  exec 9>&-

  # 4. Archive chiffrée pour la clé hors ligne, dans un dossier que le trap détruit. Un lien
  # physique y est un fichier ordinaire (--hard-dereference) : restaurer.sh refuse les liens.
  TMP="$(umask 077 && mktemp -d "${TMPDIR:-/tmp}/veille-emploi-sauvegarde.XXXXXX")" \
    || echouer "dossier temporaire impossible dans ${TMPDIR:-/tmp}"
  archive="$TMP/$nom.tar.age"
  tar --hard-dereference -C "$quotidiennes" -cf - "$nom" | age -R "$cle" >"$archive" \
    || echouer "chiffrement impossible (tar | age -R $cle)"
  [ "$(head -c 21 "$archive")" = age-encryption.org/v1 ] \
    || echouer "l'archive $archive n'est pas un fichier age : rien n'est envoyé"
  # Le couple, chiffré pour la même clé, à la date de l'archive : la purge distante leur voit le
  # même âge. Les données passent avant leur couple : un couple en échec est journalisé, l'archive
  # part seule, et l'échec est signalé à la fin (étape 7).
  if [ -f "$instantane.couple" ] && [ ! -L "$instantane.couple" ]; then
    couple="$TMP/$nom.couple.age"
    if ! age -R "$cle" -o "$couple" "$instantane.couple"; then
      echec_couple="chiffrement du couple impossible (age -R $cle)"
    elif [ "$(head -c 21 "$couple")" != age-encryption.org/v1 ]; then
      echec_couple="le couple $couple n'est pas un fichier age"
    elif ! touch -r "$archive" -- "$couple"; then
      echec_couple="le couple $couple ne prend pas la date de l'archive"
    fi
    if [ -n "$echec_couple" ]; then
      journal "$echec_couple : l'archive part sans son couple"
      rm -f -- "$couple"
      couple=""
    fi
  fi

  # 5. Envoi, puis contrôle de présence.
  rclone copy "$archive" "$distant" \
    || echouer "envoi vers $distant impossible (rclone copy : code $?)"
  envoyes="$nom.tar.age"
  if [ -n "$couple" ]; then
    rclone copy "$couple" "$distant" \
      || echouer "envoi du couple vers $distant impossible (rclone copy : code $?)"
    envoyes="$envoyes et $nom.couple.age"
  fi
  presents="$(rclone lsf --files-only "$distant")" \
    || echouer "contrôle de l'envoi vers $distant impossible (rclone lsf : code $?)"
  case $'\n'"$presents"$'\n' in
    *$'\n'"$nom.tar.age"$'\n'*) ;;
    *) echouer "archive $nom.tar.age absente de $distant après l'envoi" ;;
  esac
  if [ -n "$couple" ]; then
    case $'\n'"$presents"$'\n' in
      *$'\n'"$nom.couple.age"$'\n'*) ;;
      *) echouer "couple $nom.couple.age absent de $distant après l'envoi" ;;
    esac
  fi
  journal "envoyé : $envoyes vers $distant"

  # 6. Rétention, après un envoi contrôlé.
  retention_locale \
    || echouer "sauvegarde $nom faite et envoyée, mais rétention locale en échec : de la place peut manquer"
  rclone delete --min-age 90d --max-depth 1 --drive-use-trash=false --include 'veille-emploi-*.tar.age' \
    --include 'veille-emploi-*.couple.age' "$distant" \
    || echouer "sauvegarde $nom faite et envoyée, mais rétention distante en échec (rclone delete : code $?)"

  # 7. Signal. Un couple qui n'est pas parti est un échec : la sauvegarde est faite, mais
  # restaurer.sh dirait son couple inconnu.
  [ -z "$echec_couple" ] \
    || echouer "sauvegarde $nom faite et envoyée, mais sans son couple : $echec_couple"
  journal "sauvegarde terminée : $nom ($fichiers)"
  signaler HC_SAUVEGARDE ok "$nom : $fichiers" || true
  return 0
}

# Tout le corps est dans main, appelée sur la dernière ligne : bash a lu tout le fichier avant
# qu'un `git checkout` ne le remplace.
main "$@"; exit $?

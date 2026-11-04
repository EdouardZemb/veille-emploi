#!/usr/bin/env bash
# Test hebdomadaire de restauration : la dernière sauvegarde locale de prod est restaurée dans un
# conteneur jetable, contrôlée, et l'application y démarre (M-0005). Une sauvegarde qu'on n'a
# jamais relue ne prouve rien.
#
#   bash deploiement/tester-restauration.sh prod
#
# Lancé par veille-emploi-test-restauration.timer, chaque semaine, au jour et à l'heure
# `TEST_RESTAURATION` que déclare `serveur` (`projets/veille-emploi.env`). Réservé à la prod (code 64).
#
# Le port de l'essai est celui de la prod plus 9, le dernier du bloc de dix du projet :
# $VEILLE_EMPLOI_PORT, lu dans l'env de la prod par charger_env, et non un port écrit au rendu (un dépôt
# de code n'a pas de bloc de ports, M-0006 § 4). Un port de la prod illisible est un échec.
#
# Déroulé :
#   1. un verrou privé ($VEILLE_EMPLOI_ETAT/verrou-test-restauration, sans attente) : le port de l'essai et le
#      nom du conteneur n'ont qu'un propriétaire à la fois ; si un autre test tourne, « occupé »,
#      code 0. Sous ce verrou, les ${TMPDIR:-/tmp}/veille-emploi-test-restauration.* de l'utilisateur,
#      à la racine seulement, sont des copies en clair des données laissées par une exécution tuée
#      de force : elles sont supprimées ;
#   2. l'image est la première colonne de $VEILLE_EMPLOI_ETAT/deploye : celle qui est en service ; sans
#      elle, échec (rien à tester) ;
#   3. source : le dernier dossier quotidiennes/veille-emploi-<AAAAMMJJTHHMMSSZ> (l'ordre des noms est celui
#      du temps ; ni un fichier, ni un lien, ni un autre nom), copié dans un dossier temporaire
#      0700. Une sauvegarde en cours d'écriture, ou en échec, porte encore le suffixe .partiel
#      (sauvegarder.sh ne la renomme qu'une fois contrôlée) : elle n'est jamais prise ;
#   4. contrôle : `docker run --rm … -v <copie>:/donnees <image> <VERIFIER…> /donnees`, la commande
#      VERIFIER de deploiement/projet.env, doit rendre 0 (conforme ; 2 = non conforme) ;
#   5. `docker run -d --name veille-emploi-test-restauration -p 127.0.0.1:<port de l'essai>:8460 -v <copie>:/donnees` :
#      l'application démarre sur la copie ; /sante doit répondre statut ok ;
#   6. arrêt et suppression du conteneur, destruction du dossier temporaire ;
#   7. signal HC_TEST_RESTAURATION ok « <nom> restaurée : <N> fichiers », ou /fail à la première
#      erreur.
#
# Ce que ce test ne touche jamais : les données et les sauvegardes de la prod (il ne lit qu'un
# instantané fermé, et n'écrit que dans sa copie), le port de la prod, le projet compose. C'est pourquoi il
# n'a pas besoin du verrou partagé avec la sonde, le déploiement, la sauvegarde et la restauration.
# La copie chiffrée du distant n'est pas testée ici : la clé hors ligne ne vient jamais sur le
# serveur (M-0005) ; elle l'est sur le poste, à la main, chaque trimestre. Le report de
# restaurer.sh (REPORTER) n'y joue pas non plus : le test restaure dans un conteneur jetable, où il
# n'y a pas de données en service à reporter.
#
# Un trap détruit le conteneur et le dossier temporaire sur toutes les sorties : succès, erreur,
# INT, TERM, HUP. Un conteneur laissé par une exécution tuée de force est retiré au démarrage.
#
# Codes de sortie : 0 ; 1 échec (signalé) ; 3 secrets absents ; 64 usage ou environnement refusé ;
# 129, 130, 143 interruption.
#
# Variable de test : VEILLE_EMPLOI_SANTE_DELAI, secondes entre deux essais de santé (défaut 3).
set -euo pipefail
# shellcheck source=deploiement/lib.sh
. "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

CONTENEUR="veille-emploi-test-restauration"

# Posées par main.
ARME=0 # 1 dès que les secrets sont chargés : une sortie en erreur est alors signalée
RAISON=""
TMP=""
PORT_TEST="" # le port de la prod plus 9
CONTENEUR_LANCE=0 # 1 dès que `docker run -d` a été tenté : le trap retire le conteneur

# echouer <raison…> : journalise et quitte avec le code 1 ; le trap de sortie signale l'échec.
echouer() {
  RAISON="$*"
  journal "échec : $RAISON"
  exit 1
}

# sortie : trap EXIT. Retire le conteneur et le dossier temporaire, puis signale l'échec d'une
# sortie en erreur.
# shellcheck disable=SC2317,SC2329  # appelée par trap EXIT
sortie() {
  local code=$?
  trap - EXIT INT TERM HUP
  if [ "$CONTENEUR_LANCE" -eq 1 ] && ! docker rm -f "$CONTENEUR" >/dev/null 2>&1; then
    journal "conteneur $CONTENEUR non supprimé : à retirer à la main (docker rm -f $CONTENEUR)"
  fi
  [ -z "$TMP" ] || rm -rf -- "$TMP"
  if [ "$code" -ne 0 ] && [ "$ARME" -eq 1 ]; then
    [ -n "$RAISON" ] || RAISON="échec inattendu (code $code), voir le journal de l'unité"
    journal "test de restauration en échec (code $code) : $RAISON"
    signaler HC_TEST_RESTAURATION echec "$RAISON" || true
    # Une interruption garde son code (128 + signal) ; toute autre erreur vaut 1.
    [ "$code" -ge 128 ] || code=1
  fi
  exit "$code"
}

# dernier_instantane : le chemin du dernier dossier quotidiennes/veille-emploi-<horodatage> (les noms
# portent l'horodatage UTC : l'ordre alphabétique est l'ordre du temps). Ni un fichier, ni un lien,
# ni un nom d'une autre forme, dont un instantané .partiel, en cours d'écriture ou en échec.
dernier_instantane() {
  local dossier="$VEILLE_EMPLOI_SAUVEGARDES/quotidiennes" chemin retenu=""
  local motif='^veille-emploi-[0-9]{8}T[0-9]{6}Z$'
  for chemin in "$dossier"/veille-emploi-*; do
    { [ -d "$chemin" ] && [ ! -L "$chemin" ]; } || continue
    [[ "${chemin##*/}" =~ $motif ]] || continue
    retenu="$chemin"
  done
  [ -n "$retenu" ] || return 1
  printf '%s\n' "$retenu"
}

main() {
  [ "$#" -eq 1 ] || arreter 64 "usage : bash deploiement/tester-restauration.sh prod"
  reserver_a_prod "$1" tester-restauration.sh
  # Les secrets de ce déploiement font seuls foi : rien d'hérité du shell.
  unset HC_TEST_RESTAURATION
  charger_env prod
  charger_secrets prod

  trap sortie EXIT
  trap 'exit 130' INT
  trap 'exit 143' TERM
  trap 'exit 129' HUP
  ARME=1

  local origine nom nombre fichiers code=0 port_prod="${VEILLE_EMPLOI_PORT:-}"

  # Le port de l'essai : celui de la prod plus 9, qui doit rester un port.
  { [[ "$port_prod" =~ ^[1-9][0-9]{0,4}$ ]] && [ "$port_prod" -le 65526 ]; } \
    || echouer "port de la prod illisible : VEILLE_EMPLOI_PORT='$port_prod'"
  PORT_TEST=$((port_prod + 9))

  # 1. Verrou privé : un seul test à la fois.
  exec 8>"$VEILLE_EMPLOI_ETAT/verrou-test-restauration"
  if ! flock -n 8; then
    journal "occupé : un autre test de restauration est en cours (verrou $VEILLE_EMPLOI_ETAT/verrou-test-restauration)"
    return 0
  fi

  # Sous le verrou privé, aucune autre exécution n'a de copie en cours : celles qui restent dans
  # le dossier temporaire viennent d'une exécution tuée de force (SIGKILL, OOM), et sont des copies
  # en clair des données. On ne balaie que nos dossiers, à ce motif exact, à la racine.
  find "${TMPDIR:-/tmp}" -mindepth 1 -maxdepth 1 -type d -user "$(id -u)" -name 'veille-emploi-test-restauration.*' \
    -exec rm -rf -- {} + || journal "copies laissées par une exécution précédente non supprimées dans ${TMPDIR:-/tmp}"

  # 2. Image en service.
  lire_deploye || echouer "aucune version déployée : rien sur quoi tester la restauration"

  # 3. Source et copie.
  origine="$(dernier_instantane)" || echouer "aucune sauvegarde locale dans $VEILLE_EMPLOI_SAUVEGARDES/quotidiennes"
  nom="${origine##*/}"
  journal "test de restauration de $nom (image $DEPLOYE_IMAGE, version $DEPLOYE_VERSION)"
  TMP="$(umask 077 && mktemp -d "${TMPDIR:-/tmp}/veille-emploi-test-restauration.XXXXXX")" \
    || echouer "dossier temporaire impossible dans ${TMPDIR:-/tmp}"
  cp -R -- "$origine/." "$TMP/" || echouer "copie de $origine impossible"
  nombre="$(find "$TMP" -type f | wc -l)"
  fichiers="$nombre fichier"
  [ "$nombre" -le 1 ] || fichiers="${fichiers}s"

  # 4. Contrôle par la commande VERIFIER de l'image.
  verifier_copie "$DEPLOYE_IMAGE" "$TMP" || code=$?
  case "$code" in
    0) ;;
    2) echouer "copie de $nom non conforme (verifier : code 2) : le détail est dans le journal" ;;
    *) echouer "vérification de la copie de $nom impossible (verifier) : le détail est dans le journal" ;;
  esac
  journal "copie conforme : $nom ($fichiers)"

  # 5. L'application démarre sur la copie. Un conteneur laissé par une exécution tuée de force
  # est retiré d'abord (le nom et le port n'ont qu'un propriétaire, le verrou privé).
  docker rm -f "$CONTENEUR" >/dev/null 2>&1 || true
  CONTENEUR_LANCE=1
  docker run -d --name "$CONTENEUR" -p "127.0.0.1:$PORT_TEST:8460" "${VEILLE_EMPLOI_OPTIONS_JETABLES[@]}" \
    -v "$TMP:/donnees" "$DEPLOYE_IMAGE" >/dev/null \
    || echouer "conteneur $CONTENEUR impossible à lancer (docker run : code $?)"
  if ! attendre_sante "$PORT_TEST" '.statut == "ok"'; then
    docker logs --tail 20 "$CONTENEUR" 2>&1 | while IFS= read -r ligne; do
      journal "conteneur : $ligne"
    done || true
    echouer "santé non conforme sur 127.0.0.1:$PORT_TEST : l'application n'a pas démarré sur la copie de $nom"
  fi

  # 6. Arrêt, suppression, nettoyage.
  docker stop -t 10 "$CONTENEUR" >/dev/null \
    || echouer "arrêt du conteneur $CONTENEUR impossible (docker stop : code $?)"
  docker rm "$CONTENEUR" >/dev/null \
    || echouer "suppression du conteneur $CONTENEUR impossible (docker rm : code $?)"
  CONTENEUR_LANCE=0
  rm -rf -- "$TMP"
  TMP=""

  # 7. Signal.
  journal "test de restauration réussi : $nom, $fichiers"
  signaler HC_TEST_RESTAURATION ok "$nom restaurée : $fichiers" || true
  return 0
}

# Tout le corps est dans main, appelée sur la dernière ligne : bash a lu tout le fichier avant
# qu'un `git checkout` ne le remplace.
main "$@"; exit $?

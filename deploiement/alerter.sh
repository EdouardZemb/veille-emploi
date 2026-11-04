#!/usr/bin/env bash
# Alerte d'échec d'une unité systemd : lancé par veille-emploi-alerte@<unité>.service, que l'OnFailure=
# des unités d'veille-emploi déclenche avec le nom de l'unité en échec (%n).
#
#   bash deploiement/alerter.sh <nom d'unité>
#
# Le nom est traduit en environnement et en variable de signal (secrets de l'environnement), puis
# signaler envoie « échec » à l'adresse de cette variable (Healthchecks : adresse + /fail).
# L'adresse n'est jamais journalisée : elle suffit à envoyer de faux signaux.
#
#   veille-emploi-sonde-prod.service          prod     HC_SONDE
#   veille-emploi-sonde-staging.service       staging  HC_SONDE
#   veille-emploi-sauvegarde.service          prod     HC_SAUVEGARDE
#   veille-emploi-test-restauration.service   prod     HC_TEST_RESTAURATION
#
# Codes de sortie : 64 = usage ou unité inconnue ; 3 = secrets absents ; 1 = autre erreur, ou le
# code de curl si l'envoi échoue. Une alerte qui échoue le laisse voir : l'unité d'alerte est en
# échec dans le journal (elle n'a pas d'OnFailure : une alerte ne s'alerte pas elle-même).
set -euo pipefail
# shellcheck source=deploiement/lib.sh
. "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

main() {
  [ "$#" -eq 1 ] || arreter 64 "usage : bash deploiement/alerter.sh <nom d'unité>"
  local unite="$1" nom_env variable
  case "$unite" in
    veille-emploi-sonde-prod.service) nom_env=prod variable=HC_SONDE ;;
    veille-emploi-sonde-staging.service) nom_env=staging variable=HC_SONDE ;;
    veille-emploi-sauvegarde.service) nom_env=prod variable=HC_SAUVEGARDE ;;
    veille-emploi-test-restauration.service) nom_env=prod variable=HC_TEST_RESTAURATION ;;
    *) arreter 64 "unité inconnue : '$unite'" ;;
  esac

  journal "alerte : échec de $unite (environnement $nom_env, signal $variable)"
  charger_env "$nom_env"
  charger_secrets "$nom_env"
  signaler "$variable" echec "échec de $unite"
}

# Tout le corps est dans main : bash a lu tout le fichier avant qu'un `git checkout` ne le remplace.
main "$@"
exit $?

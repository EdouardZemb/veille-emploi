#!/bin/sh
# Lance les tests bats des scripts de déploiement dans leur image Docker de test : le poste de
# développement n'a ni flock, ni age, ni sops, ni bats. Même commande en local et en CI.
#
#   sh tests/deploiement/lancer.sh                                   tous les tests
#   sh tests/deploiement/lancer.sh tests/deploiement/secrets.bats    un fichier (chemin relatif à la
#                                                                    racine du dépôt, avec des « / »)
#
# Les arguments sont transmis tels quels à bats. Le dépôt est monté sur /depot : les tests copient
# ce qu'ils modifient dans leur dossier temporaire, et n'écrivent rien dans le dépôt.
#
# Codes de sortie : celui de docker build s'il échoue, sinon celui de bats (0 = tout est vert).
set -eu

IMAGE=veille-emploi-tests-deploiement

main() {
  racine="$(CDPATH='' cd -- "$(dirname -- "$0")/../.." && pwd)"
  volume="$racine"
  case "$(uname -s)" in
    MINGW* | MSYS* | CYGWIN*)
      # Git Bash : Docker attend le chemin Windows du dépôt (C:/…), que donne `pwd -W`, et MSYS ne
      # doit pas réécrire les arguments qui commencent par « / » (/depot) en chemins Windows.
      MSYS_NO_PATHCONV=1
      export MSYS_NO_PATHCONV
      volume="$(cd "$racine" && pwd -W)"
      ;;
  esac
  cd "$racine"

  docker build -t "$IMAGE" tests/deploiement
  [ "$#" -gt 0 ] || set -- tests/deploiement
  docker run --rm -v "$volume:/depot" -w /depot "$IMAGE" bats "$@"
}

main "$@"
exit $?

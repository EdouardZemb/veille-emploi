#!/bin/sh
# Géré par le modèle. Lance un script avec un Python 3.10+ qui fonctionne vraiment :
# sous Windows, le « python3 » du Microsoft Store n'est qu'un raccourci d'installation.
# Aucun __pycache__ dans le projet : les scripts importent reglages, que Python mettrait en cache.
PYTHONDONTWRITEBYTECODE=1
export PYTHONDONTWRITEBYTECODE
for candidat in python3 python "py -3"; do
  if $candidat -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' >/dev/null 2>&1; then
    exec $candidat "$@"
  fi
done
echo "modele-projet : aucun Python 3.10 ou plus récent (essayés : python3, python, py -3)." >&2
exit 1

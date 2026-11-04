#!/usr/bin/env bash
# Vérifie l'image que la CI vient de lancer (action modele-image-construire), avant les tests de
# bout en bout du projet et la publication.
#
#   bash deploiement/ci/verifier-image.sh <conteneur> <révision>
#
# <révision> est le SHA du commit construit ($GITHUB_SHA), que l'image doit annoncer.
#
# Déroulé :
#   1. santé : jusqu'à 90 s, `curl http://127.0.0.1:8460/sante` doit rendre
#      .statut == "ok" (l'action publie le port de l'app sur la boucle locale) ;
#   2. cette réponse doit annoncer .revision == <révision> et .environnement == "ci" ;
#   3. instantané : `docker exec <conteneur> <SAUVEGARDER…> /tmp/instantane`, puis
#      `docker exec <conteneur> <VERIFIER…> /tmp/instantane`, les commandes de
#      deploiement/projet.env (lu, jamais sourcé), qui doivent rendre 0. Le contrat de l'image :
#      VERIFIER rend 0 si l'instantané est conforme, 2 s'il ne l'est pas, 64 en cas d'usage refusé.
#   4. l'exemple (M-0003) : chaque commande de l'instance que déclare deploiement/projet.env tourne
#      sur son dossier d'exemple, à la racine du dépôt, comme le serveur la lance sur un instantané
#      (_verifier_par de lib.sh) : `docker run --rm --network none <options jetables>
#      -v <dépôt>/exemple:/config:ro veille-emploi:ci <VERIFIER_CONFIG…> /config`, et de même
#      exemple-contenu/ sur /contenu pour VERIFIER_CONTENU ; 0 exigé. D'abord, pour les deux, une
#      commande déclarée sans son dossier d'exemple refuse, avant tout conteneur : la CI ne peut pas
#      la prouver. Un dossier d'exemple sans sa commande ne refuse pas : il n'est pas vérifié, et le
#      journal le dit. Un dossier qui ne porte que le README.md de sa racine compte comme absent. Un
#      projet qui ne déclare aucune des deux commandes ne lance rien ;
#   5. à un dépôt seulement (MODE_DONNEES de lib.sh), l'instance du dépôt, instance/config et
#      instance/contenu de la copie de travail, comme le déploiement les vérifiera (il les
#      revérifie) : la règle des paires de controler_paires (lib.sh), où un dossier présent sans sa
#      commande refuse aussi, avant tout conteneur, puis chaque commande déclarée sur son dossier,
#      dans le même conteneur jetable de l'image construite qu'à l'étape 4 ; 0 exigé. Un refus
#      nomme le dossier et la commande. Un projet qui ne déclare aucune des deux commandes ne lit
#      pas instance/, comme le déploiement. À deux dépôts, l'instance est dans le dépôt de données,
#      dont la CI la vérifie.
#
# Codes de sortie : 0 image conforme ; 1 non conforme ; 64 usage.
#
# Variables de test : VEILLE_EMPLOI_SANTE_ATTENTE, secondes d'attente de la santé (défaut 90) ;
# VEILLE_EMPLOI_SANTE_DELAI, secondes entre deux essais (défaut 2).
set -euo pipefail

# shellcheck source=deploiement/lib.sh
. "$(dirname -- "${BASH_SOURCE[0]}")/../lib.sh"

USAGE="usage : bash deploiement/ci/verifier-image.sh <conteneur> <révision>"
INSTANTANE=/tmp/instantane
# L'image que l'action modele-image-construire vient de construire, et dont <conteneur> tourne.
IMAGE=veille-emploi:ci

# attendre_sante_ok <attente> <délai> : jusqu'à <attente> secondes, toutes les <délai> secondes, une
# santé qui dit .statut == "ok" ; sa réponse dans SANTE. SECONDS compte en secondes entières :
# l'attente réelle est comprise entre <attente> - 1 et <attente> secondes, et la boucle fait au
# moins deux essais dès que <attente> vaut 2 ou plus et qu'un essai dure moins d'une seconde.
attendre_sante_ok() {
  local limite=$((SECONDS + $1)) delai="$2" reponse=""
  while :; do
    if reponse="$(sante_sur 8460 '.statut == "ok"')"; then
      SANTE="$reponse"
      journal "santé ok après $SECONDS s : $SANTE"
      return 0
    fi
    [ "$SECONDS" -lt "$limite" ] || break
    sleep "$delai"
  done
  journal "santé non conforme après $SECONDS s (limite : $1 s) ; dernière réponse : ${reponse//$'\n'/ }"
  return 1
}

# lancer_dans <conteneur> <mots…> : la commande, dans le conteneur, sur l'instantané. Sa sortie,
# sur une ligne, dans SORTIE ; rend son code.
lancer_dans() {
  local conteneur="$1" code=0
  shift
  SORTIE="$(docker exec "$conteneur" "$@" "$INSTANTANE")" || code=$?
  SORTIE="${SORTIE//$'\n'/ }"
  return "$code"
}

# dossier_present <dossier> : succès si <dossier>, un dossier et pas un lien, porte au moins un
# fichier autre que <dossier>/README.md ; un README.md plus bas compte. La règle de controler_paires
# (lib.sh), lue ici sur la copie de travail : la CI vient de la tirer.
dossier_present() {
  local dossier="$1" chemin
  { [ -d "$dossier" ] && [ ! -L "$dossier" ]; } || return 1
  while IFS= read -r -d '' chemin; do
    [ "$chemin" = "$dossier/README.md" ] || return 0
  done < <(find "$dossier" -mindepth 1 ! -type d -print0)
  return 1
}

# verifier_dossier <non conforme> <CLÉ> <libellé> <dossier> <point de montage> : la commande <CLÉ>
# de projet.env sur <dossier>, relatif à la racine du dépôt, en lecture seule, dans un conteneur
# jetable de l'image construite, sans réseau (_verifier_par de lib.sh, qui journalise sa sortie).
# 0 exigé, sinon le script s'arrête, et son message commence par « <non conforme> non conforme ».
verifier_dossier() {
  local quoi="$1" cle="$2" libelle="$3" dossier="$4" point="$5" code=0
  _verifier_par "$cle" "$libelle" "$IMAGE" -v "$VEILLE_EMPLOI_CLONE/$dossier:$point:ro" -- "$point" || code=$?
  case "$code" in
    0) ;;
    2) arreter 1 "$quoi non conforme : $dossier/ non conforme ($cle : code 2)" ;;
    *) arreter 1 "$quoi non conforme : vérification de $dossier/ impossible ($cle)" ;;
  esac
}

# verifier_dossiers <exemple|instance> <dossier de la configuration> <dossier du contenu> : ces deux
# dossiers de la copie de travail, relatifs à la racine du dépôt, avec les commandes de l'instance
# que déclare deploiement/projet.env (DECLARE_CONFIG et DECLARE_CONTENU, de donnees_declarees).
# D'abord la règle des paires, avant tout conteneur : une commande déclarée sans son dossier est en
# défaut. Un dossier présent sans sa commande l'est aussi pour l'instance, comme au déploiement
# (controler_paires, lib.sh) ; pour l'exemple, il n'est que dit non vérifié. Chaque défaut va au
# journal, et toutes les paires lues, un défaut arrête le script (code 1). Puis chaque commande
# déclarée tourne sur son dossier (verifier_dossier) : un refus de l'exemple dit l'image non
# conforme, puisqu'elle l'embarque ; un refus de l'instance dit l'instance non conforme.
verifier_dossiers() {
  local genre="$1" config="$2" contenu="$3" paire dossier commande declaree defaut defauts=""
  local quoi=image de_config="exemple de configuration" de_contenu="exemple de contenu"
  if [ "$genre" = instance ]; then
    quoi=instance de_config="configuration de l'instance" de_contenu="contenu de l'instance"
  fi
  for paire in "$config VERIFIER_CONFIG $DECLARE_CONFIG" "$contenu VERIFIER_CONTENU $DECLARE_CONTENU"; do
    read -r dossier commande declaree <<<"$paire"
    if dossier_present "$VEILLE_EMPLOI_CLONE/$dossier"; then
      [ "$declaree" -eq 0 ] || continue
      if [ "$genre" = exemple ]; then
        journal "$dossier/ présent, sans $commande : non vérifié"
        continue
      fi
      defaut="$dossier/ sans $commande"
    elif [ "$declaree" -eq 1 ]; then
      defaut="$commande sans $dossier/"
    else
      continue
    fi
    journal "$defaut"
    defauts="${defauts:+$defauts ; }$defaut"
  done
  if [ -n "$defauts" ]; then
    if [ "$genre" = exemple ]; then
      arreter 1 "exemple non conforme : chaque commande déclarée dans deploiement/projet.env va avec son dossier d'exemple"
    fi
    arreter 1 "instance non conforme, règle des paires du déploiement : $defauts"
  fi
  [ "$DECLARE_CONFIG" -eq 0 ] || verifier_dossier "$quoi" VERIFIER_CONFIG "$de_config" "$config" /config
  [ "$DECLARE_CONTENU" -eq 0 ] || verifier_dossier "$quoi" VERIFIER_CONTENU "$de_contenu" "$contenu" /contenu
}

main() {
  [ "$#" -eq 2 ] || arreter 64 "$USAGE"
  local conteneur="$1" revision="$2"
  local attente="${VEILLE_EMPLOI_SANTE_ATTENTE:-90}" delai="${VEILLE_EMPLOI_SANTE_DELAI:-2}"
  [[ "$conteneur" =~ ^[a-zA-Z0-9][a-zA-Z0-9_.-]*$ ]] || arreter 64 "conteneur invalide : '$conteneur' ($USAGE)"
  [[ "$revision" =~ $MOTIF_SHA ]] \
    || arreter 64 "révision invalide : '$revision' (attendu : les 40 caractères hexadécimaux du commit)"
  [[ "$attente" =~ ^[0-9]+$ ]] || arreter 64 "VEILLE_EMPLOI_SANTE_ATTENTE invalide : '$attente'"

  # 1. Santé.
  attendre_sante_ok "$attente" "$delai" || arreter 1 "image non conforme : santé non conforme"

  # 2. Révision et environnement.
  # shellcheck disable=SC2016  # $revision est une variable de jq (--arg)
  jq_vaut true "$SANTE" '.revision == $revision' --arg revision "$revision" \
    || arreter 1 "image non conforme : révision servie non conforme : attendue $revision ; santé : $SANTE"
  jq_vaut true "$SANTE" '.environnement == "ci"' \
    || arreter 1 "image non conforme : environnement servi non conforme : attendu ci ; santé : $SANTE"
  journal "révision $revision et environnement ci annoncés"

  # 3. Instantané, puis sa vérification, par les commandes de l'image. Les deux sont lues avant de
  # lancer quoi que ce soit.
  local -a sauvegarder verifier
  local code=0
  lire_projet_env SAUVEGARDER \
    || arreter 1 "image non conforme : pas de commande SAUVEGARDER lisible dans deploiement/projet.env"
  sauvegarder=("${PROJET_MOTS[@]}")
  lire_projet_env VERIFIER \
    || arreter 1 "image non conforme : pas de commande VERIFIER lisible dans deploiement/projet.env"
  verifier=("${PROJET_MOTS[@]}")
  lancer_dans "$conteneur" "${sauvegarder[@]}" || code=$?
  [ "$code" -eq 0 ] \
    || arreter 1 "image non conforme : instantané impossible (sauvegarder : code $code)${SORTIE:+ : $SORTIE}"
  journal "instantané écrit dans $conteneur:$INSTANTANE${SORTIE:+ : $SORTIE}"
  lancer_dans "$conteneur" "${verifier[@]}" || code=$?
  case "$code" in
    0) journal "instantané conforme (verifier : code 0)${SORTIE:+ : $SORTIE}" ;;
    2) arreter 1 "image non conforme : instantané non conforme (verifier : code 2)${SORTIE:+ : $SORTIE}" ;;
    *) arreter 1 "image non conforme : vérification impossible (verifier : code $code)${SORTIE:+ : $SORTIE}" ;;
  esac

  # 4. L'exemple : chaque commande déclarée a son dossier, puis elle tourne dessus. Un dossier sans
  # sa commande n'est pas vérifié : un projet qui n'a pas encore déclaré la sienne garde sa CI.
  donnees_declarees || arreter 1 "image non conforme : deploiement/projet.env illisible (VERIFIER_CONFIG, VERIFIER_CONTENU)"
  verifier_dossiers exemple exemple exemple-contenu

  # 5. À un dépôt, l'instance, à la racine du dépôt comme l'exemple : la règle des paires, puis
  # chaque commande déclarée, comme le déploiement les fera. Sans commande déclarée, le déploiement
  # ne lit pas l'instance, et la CI non plus.
  if [ "$MODE_DONNEES" = un ] && { [ "$DECLARE_CONFIG" -eq 1 ] || [ "$DECLARE_CONTENU" -eq 1 ]; }; then
    verifier_dossiers instance "$SOUS_DOSSIER_CONFIG" "$SOUS_DOSSIER_CONTENU"
  fi
  journal "image conforme"
}

main "$@"; exit $?

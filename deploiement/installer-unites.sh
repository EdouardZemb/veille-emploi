#!/usr/bin/env bash
# Unités systemd utilisateur d'veille-emploi : rendu des gabarits, installation, contrôle de dérive.
#
#   bash deploiement/installer-unites.sh              rend les gabarits, installe les unités,
#                                                     recharge systemd et active les minuteries
#   bash deploiement/installer-unites.sh --verifier   compare les unités installées à leur rendu,
#                                                     sans rien modifier : code 0 si elles sont
#                                                     conformes, 1 sinon (liste des écarts sur
#                                                     stderr). La sonde de prod l'appelle à chaque
#                                                     passage.
#
# Les unités ne s'installent que par ce script, jamais à la main : une copie à la main finit par
# diverger du dépôt sans que personne le voie (incident déjà vécu sur ce serveur).
#
# Gabarits : deploiement/systemd/*.in, lus dans le clone qui contient ce script. Le rendu est une
# substitution pure de cinq marqueurs, sans autre mécanisme, pour que deux rendus identiques le
# soient à l'octet près (le contrôle compare des octets) :
#   @ENV@               prod ou staging
#   @CLONE@             le clone de l'environnement de l'unité
#   @CLONE_PROD@        le clone de prod, quelle que soit l'unité
#   @HEURE_SAUVEGARDE@  l'heure de la sauvegarde quotidienne (OnCalendar=, *-*-* HH:MM:00)
#   @HEURE_TEST@        l'heure du test de restauration hebdomadaire (OnCalendar=, Jjj *-*-* HH:MM:00)
# Les deux heures se lisent dans la déclaration du projet sur le serveur, ~/serveur/projets/veille-emploi.env
# (clés SAUVEGARDE=HH:MM et TEST_RESTAURATION=Jjj HH:MM, de Mon à Sun) : c'est le serveur qui
# répartit les heures des projets. Le fichier est lu, jamais sourcé ; ses autres clés sont ignorées.
# S'il manque, ou si une heure est absente ou mal formée, rien n'est installé ni vérifié (code 1).
# Les deux clés peuvent valoir « non » ensemble tant que la prod n'a rien déployé, c'est-à-dire
# tant que son état n'a pas de fichier deploye : ni la sauvegarde ni son test ne sont alors rendus,
# et une telle unité déjà installée est une orpheline. « non » refuse (code 1), sans rien installer
# ni vérifier, dès que la prod a un fichier deploye, ou quand la sonde de prod installe les unités
# juste avant d'y déployer une version (VEILLE_EMPLOI_AVANT_DEPLOIEMENT=1) : une prod qui sert a des
# données, et ses sauvegardes.
# Le gabarit veille-emploi-sonde.* donne une unité par environnement (veille-emploi-sonde-prod.*, puis
# veille-emploi-sonde-staging.*, chacune sur son clone) ; tous les autres sont rendus pour la prod, sur
# son clone, sous leur nom sans « .in ».
#
# Seules les entrées veille-emploi-* du dossier des unités sont lues, écrites ou retirées. Une entrée
# veille-emploi-* sans gabarit est une orpheline : le contrôle la signale, l'installation la désactive,
# l'arrête et la retire (y compris un dossier de surcharge veille-emploi-*.d, que crée
# `systemctl --user edit`). Une unité attendue mais absente est aussi un écart.
#
# Variables :
#   VEILLE_EMPLOI_CLONE_PROD      clone de prod (défaut ~/veille-emploi)
#   VEILLE_EMPLOI_CLONE_STAGING   clone de staging (défaut ~/veille-emploi-staging)
#   VEILLE_EMPLOI_DOSSIER_UNITES  dossier des unités (défaut ~/.config/systemd/user)
#   VEILLE_EMPLOI_PROJET_SERVEUR  déclaration du projet sur le serveur (défaut ~/serveur/projets/veille-emploi.env)
#   VEILLE_EMPLOI_RACINE_ETAT     racine des états, où se lit prod/deploye (défaut ~/.local/state/veille-emploi)
#   VEILLE_EMPLOI_AVANT_DEPLOIEMENT  1 : la sonde de prod va déployer, « non » refuse. Une variable
#                               plutôt qu'une option : l'installeur d'une version plus ancienne,
#                               que la sonde appelle quand la prod revient en arrière, l'ignore
#
# Codes de sortie : 0 ; 1 = écart (--verifier) ou erreur ; 64 = usage ou chemin invalide.
set -euo pipefail
export LC_COLLATE=C # ordre des listes et des écarts indépendant de la langue du serveur
# shellcheck source=deploiement/lib.sh
. "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

# Posés par main.
CLONE_PROD=""
CLONE_STAGING=""
DOSSIER=""
RENDU="" # dossier temporaire du rendu ; supprimé à la sortie
ECARTS=0 # nombre d'écarts relevés par verifier
HEURE_SAUVEGARDE="" # valeur d'OnCalendar= de la sauvegarde
HEURE_TEST=""       # valeur d'OnCalendar= du test de restauration
SANS_SAUVEGARDE=0   # 1 : serveur déclare « non », ni la sauvegarde ni son test ne sont rendus

# valider_chemin_de_clone <variable> <chemin> : un chemin absolu, sans caractère que systemd
# interpréterait dans ExecStart (espace, guillemet, \, $, ;, %). Le rendu ne met rien entre
# guillemets : un tel chemin couperait la commande ou serait développé.
valider_chemin_de_clone() {
  local variable="$1" chemin="$2"
  case "$chemin" in
    /*) ;;
    *) arreter 64 "$variable : chemin absolu attendu (reçu : '$chemin')" ;;
  esac
  case "$chemin" in
    *[[:space:][:cntrl:]\"\'\\\$\;%]*)
      arreter 64 "$variable : '$chemin' contient un caractère que systemd interpréterait (espace, guillemet, \\, \$, ;, %)"
      ;;
  esac
}

# lire_heures <fichier> : SAUVEGARDE et TEST_RESTAURATION de la déclaration du projet sur le
# serveur, rendues dans HEURE_SAUVEGARDE et HEURE_TEST (valeurs d'OnCalendar=). Lecteur strict : seules
# les lignes qui commencent par l'une des deux clés comptent, chacune une fois, et chaque valeur a sa
# forme exacte (HH:MM ; Jjj HH:MM, de Mon à Sun), ou « non » sur les deux ensemble (sans_sauvegarde).
# Le fichier n'est jamais sourcé.
lire_heures() {
  local fichier="$1" ligne cle valeur sauvegarde="" test="" vues=" "
  { [ -f "$fichier" ] && [ -r "$fichier" ]; } \
    || arreter 1 "déclaration du projet illisible : $fichier (heures des sauvegardes)"
  while IFS= read -r ligne || [ -n "$ligne" ]; do
    case "$ligne" in
      SAUVEGARDE=* | TEST_RESTAURATION=*) ;;
      *) continue ;;
    esac
    cle="${ligne%%=*}"
    valeur="${ligne#*=}"
    case "$vues" in *" $cle "*) arreter 1 "$fichier : $cle est déclarée deux fois" ;; esac
    vues="$vues$cle "
    if [ "$cle" = SAUVEGARDE ]; then sauvegarde="$valeur"; else test="$valeur"; fi
  done <"$fichier"
  if [ "$sauvegarde" = non ] || [ "$test" = non ]; then
    { [ "$sauvegarde" = non ] && [ "$test" = non ]; } \
      || arreter 1 "$fichier : « non » vaut pour SAUVEGARDE et TEST_RESTAURATION ensemble, sinon chacune a son heure"
    sans_sauvegarde "$fichier"
    return 0
  fi
  [[ "$sauvegarde" =~ ^([01][0-9]|2[0-3]):[0-5][0-9]$ ]] \
    || arreter 1 "$fichier : SAUVEGARDE absente ou mal formée (attendu : HH:MM)"
  [[ "$test" =~ ^(Mon|Tue|Wed|Thu|Fri|Sat|Sun)\ ([01][0-9]|2[0-3]):[0-5][0-9]$ ]] \
    || arreter 1 "$fichier : TEST_RESTAURATION absente ou mal formée (attendu : Jjj HH:MM, de Mon à Sun)"
  HEURE_SAUVEGARDE="*-*-* $sauvegarde:00"
  HEURE_TEST="${test%% *} *-*-* ${test#* }:00"
}

# sans_sauvegarde <fichier> : serveur déclare « non » aux deux heures. Accepté tant que la prod n'a
# rien déployé (aucun fichier deploye dans son état, même vide) et ne va pas déployer
# (VEILLE_EMPLOI_AVANT_DEPLOIEMENT=1) : SANS_SAUVEGARDE ← 1. Sinon, refus (code 1) : une prod qui sert
# a des données, et ses sauvegardes. Rien au journal quand c'est accepté : la sonde de serveur lit la
# sortie de --verifier strictement (des lignes « écart : … » et leur résumé), et toute autre ligne lui
# ferait refuser de réparer. C'est l'installation qui le dit.
sans_sauvegarde() {
  local fichier="$1" deploye
  deploye="${VEILLE_EMPLOI_RACINE_ETAT:-$HOME/.local/state/veille-emploi}/prod/deploye"
  [ "${VEILLE_EMPLOI_AVANT_DEPLOIEMENT:-}" != 1 ] \
    || arreter 1 "$fichier : SAUVEGARDE=non, et la prod va déployer : déclarer d'abord les heures des sauvegardes dans serveur"
  ! existe "$deploye" \
    || arreter 1 "$fichier : SAUVEGARDE=non, mais la prod a déployé ($deploye) : déclarer les heures des sauvegardes dans serveur"
  SANS_SAUVEGARDE=1
}

# rendre_gabarit <gabarit> <env> <clone> <sortie> : substitue les cinq marqueurs. Un autre marqueur
# du même genre (@MAJUSCULES@) est une faute du gabarit : on refuse plutôt que de l'installer tel quel.
rendre_gabarit() {
  local gabarit="$1" nom_env="$2" clone="$3" sortie="$4" contenu=""
  { [ -f "$gabarit" ] && [ -r "$gabarit" ]; } || arreter 1 "gabarit illisible : $gabarit"
  # -d '' : tout le fichier, sans perdre le saut de ligne final (une substitution de commande le
  # supprimerait). Remplacements entre guillemets : une « & » du chemin reste une « & ».
  IFS= read -r -d '' contenu <"$gabarit" || true
  contenu="${contenu//@ENV@/"$nom_env"}"
  contenu="${contenu//@CLONE@/"$clone"}"
  contenu="${contenu//@CLONE_PROD@/"$CLONE_PROD"}"
  contenu="${contenu//@HEURE_SAUVEGARDE@/"$HEURE_SAUVEGARDE"}"
  contenu="${contenu//@HEURE_TEST@/"$HEURE_TEST"}"
  if [[ "$contenu" =~ @[A-Z][A-Z_]*@ ]]; then
    arreter 1 "gabarit ${gabarit##*/} : marqueur inconnu ${BASH_REMATCH[0]} (attendus : @ENV@, @CLONE@, @CLONE_PROD@, @HEURE_SAUVEGARDE@, @HEURE_TEST@)"
  fi
  printf '%s' "$contenu" >"$sortie"
}

# rendre_tout <dossier> : rend tous les gabarits dans ce dossier, avant que quoi que ce soit soit
# installé : un gabarit en faute n'installe rien.
rendre_tout() {
  local sortie="$1" gabarits="$VEILLE_EMPLOI_CLONE/deploiement/systemd" gabarit nom trouves=0
  for gabarit in "$gabarits"/*.in; do
    [ -e "$gabarit" ] || break # aucun gabarit : le glob reste littéral
    nom="${gabarit##*/}"
    nom="${nom%.in}"
    case "$nom" in
      veille-emploi-?*) ;;
      *) arreter 1 "gabarit mal nommé : ${gabarit##*/} (préfixe veille-emploi- attendu)" ;;
    esac
    trouves=$((trouves + 1))
    if [ "$SANS_SAUVEGARDE" -eq 1 ]; then
      case "$nom" in
        veille-emploi-sauvegarde.* | veille-emploi-test-restauration.*) continue ;;
      esac
    fi
    case "$nom" in
      veille-emploi-sonde.*)
        rendre_gabarit "$gabarit" prod "$CLONE_PROD" "$sortie/veille-emploi-sonde-prod.${nom#veille-emploi-sonde.}"
        rendre_gabarit "$gabarit" staging "$CLONE_STAGING" "$sortie/veille-emploi-sonde-staging.${nom#veille-emploi-sonde.}"
        ;;
      *) rendre_gabarit "$gabarit" prod "$CLONE_PROD" "$sortie/$nom" ;;
    esac
  done
  [ "$trouves" -gt 0 ] || arreter 1 "aucun gabarit dans $gabarits"
}

# conforme <rendu> <installee> : un fichier ordinaire (pas un lien, pas un dossier) aux mêmes octets.
conforme() {
  [ -f "$2" ] && [ ! -L "$2" ] && cmp -s "$1" "$2"
}

# existe <chemin> : vrai aussi pour un lien symbolique brisé.
existe() {
  [ -e "$1" ] || [ -L "$1" ]
}

# --- contrôle de dérive ----------------------------------------------------------------------

# ecart <unité> <raison> : une ligne sur stderr et le compte des écarts.
ecart() {
  printf 'écart : %s : %s\n' "$1" "$2" >&2
  ECARTS=$((ECARTS + 1))
}

verifier() {
  local chemin nom
  local -a rendues=("$RENDU"/*)
  ECARTS=0

  for chemin in "${rendues[@]}"; do
    nom="${chemin##*/}"
    if ! existe "$DOSSIER/$nom"; then
      ecart "$nom" "absente (le dépôt la prévoit)"
    elif ! conforme "$chemin" "$DOSSIER/$nom"; then
      if [ -L "$DOSSIER/$nom" ] || [ ! -f "$DOSSIER/$nom" ]; then
        ecart "$nom" "n'est pas un fichier ordinaire"
      else
        ecart "$nom" "différente de son rendu"
      fi
    fi
  done
  for chemin in "$DOSSIER"/veille-emploi-*; do
    existe "$chemin" || continue # aucun fichier : le glob reste littéral
    nom="${chemin##*/}"
    [ -e "$RENDU/$nom" ] || ecart "$nom" "orpheline (aucun gabarit ne la produit)"
  done

  if [ "$ECARTS" -gt 0 ]; then
    journal "$ECARTS écart(s) entre les unités installées dans $DOSSIER et deploiement/systemd : corriger par bash $VEILLE_EMPLOI_CLONE/deploiement/installer-unites.sh"
    return 1
  fi
  journal "unités conformes : ${#rendues[@]} vérifiées dans $DOSSIER"
}

# --- installation ----------------------------------------------------------------------------

# retirer <chemin> : supprime une entrée veille-emploi-* du dossier des unités (fichier, lien symbolique
# ou dossier de surcharge ; un lien est retiré, jamais suivi). Refuse tout autre nom.
retirer() {
  case "${1##*/}" in
    veille-emploi-?*) ;;
    *) arreter 1 "refus de supprimer une entrée qui n'est pas veille-emploi-* : $1" ;;
  esac
  rm -rf -- "$1"
}

installer() {
  local chemin nom
  local -a minuteries=()

  mkdir -p "$DOSSIER"
  [ "$SANS_SAUVEGARDE" -eq 0 ] \
    || journal "sans sauvegarde ni test de restauration : serveur déclare SAUVEGARDE=non, tant que la prod n'a rien déployé"

  # 1. Les orphelines : désactivées et arrêtées avant que leur fichier disparaisse (sinon systemd
  # les garderait actives sans fichier), puis retirées. Si la désactivation échoue, on s'arrête.
  for chemin in "$DOSSIER"/veille-emploi-*; do
    existe "$chemin" || continue
    nom="${chemin##*/}"
    [ ! -e "$RENDU/$nom" ] || continue
    case "$nom" in
      *.service | *.timer)
        if [ -f "$chemin" ] || [ -L "$chemin" ]; then
          systemctl --user disable --now "$nom" || arreter 1 "désactivation de $nom impossible"
        fi
        ;;
    esac
    retirer "$chemin"
    journal "retirée : $nom (orpheline)"
  done

  # 2. Les unités du dépôt : seules celles qui diffèrent sont réécrites. Une entrée qui n'est pas
  # un fichier ordinaire (lien, dossier) est retirée d'abord : `install` ne doit pas écrire à
  # travers un lien.
  for chemin in "$RENDU"/*; do
    nom="${chemin##*/}"
    case "$nom" in *.timer) minuteries+=("$nom") ;; esac
    if conforme "$chemin" "$DOSSIER/$nom"; then
      continue
    fi
    if existe "$DOSSIER/$nom"; then
      retirer "$DOSSIER/$nom"
    fi
    install -m 0644 "$chemin" "$DOSSIER/$nom"
    journal "installée : $nom"
  done

  # 3. systemd.
  systemctl --user daemon-reload
  [ "${#minuteries[@]}" -eq 0 ] || systemctl --user enable --now "${minuteries[@]}"
  journal "unités installées dans $DOSSIER : ${#minuteries[@]} minuteries actives"
}

main() {
  local mode=installer
  case "$#" in
    0) ;;
    1)
      [ "$1" = --verifier ] || arreter 64 "usage : bash deploiement/installer-unites.sh [--verifier]"
      mode=verifier
      ;;
    *) arreter 64 "usage : bash deploiement/installer-unites.sh [--verifier]" ;;
  esac

  CLONE_PROD="${VEILLE_EMPLOI_CLONE_PROD:-$HOME/veille-emploi}"
  CLONE_STAGING="${VEILLE_EMPLOI_CLONE_STAGING:-$HOME/veille-emploi-staging}"
  DOSSIER="${VEILLE_EMPLOI_DOSSIER_UNITES:-$HOME/.config/systemd/user}"
  valider_chemin_de_clone VEILLE_EMPLOI_CLONE_PROD "$CLONE_PROD"
  valider_chemin_de_clone VEILLE_EMPLOI_CLONE_STAGING "$CLONE_STAGING"
  [ -n "$DOSSIER" ] || arreter 64 "VEILLE_EMPLOI_DOSSIER_UNITES est vide"
  lire_heures "${VEILLE_EMPLOI_PROJET_SERVEUR:-$HOME/serveur/projets/veille-emploi.env}"

  RENDU="$(mktemp -d "${TMPDIR:-/tmp}/veille-emploi-unites.XXXXXX")" || arreter 1 "dossier temporaire impossible"
  trap '[ -z "$RENDU" ] || rm -rf -- "$RENDU"' EXIT
  rendre_tout "$RENDU"

  if [ "$mode" = verifier ]; then
    verifier
  else
    installer
  fi
}

# Tout le corps est dans main : bash a lu tout le fichier avant qu'un `git checkout` ne le remplace.
main "$@"
exit $?

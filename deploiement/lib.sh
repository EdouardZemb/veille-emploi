#!/usr/bin/env bash
# Bibliothèque commune des scripts de déploiement : à sourcer, jamais à lancer.
#
#   set -euo pipefail
#   . "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
#   charger_env prod        # chemins, variables de l'environnement, PATH, dossiers
#   charger_secrets prod    # secrets déchiffrés dans l'environnement du script et de ses enfants
#
# Tout script qui appelle `signaler` ou `dc` appelle d'abord `charger_secrets` : `signaler` lit les
# adresses de signal dans l'environnement, et `docker compose` peut y lire des variables dont
# compose.projet.yml a besoin.
#
# Fonctions publiques (celles qui commencent par « _ » sont internes) :
#   journal <message…>                 une ligne horodatée (UTC) sur stderr
#   arreter <code> <message…>          journalise et quitte avec ce code
#   valider_env <env>                  prod ou staging, sinon code 64
#   poser_clone_donnees <env>          VEILLE_EMPLOI_CLONE_DONNEES, le clone des données de l'environnement, sans rien y lire
#   charger_env <env>                  chemins (le clone des données compris), variables, PATH et dossiers de l'environnement
#   prefixer_path                      ~/.local/bin en tête du PATH (une fois)
#   charger_secrets <env>              secrets déchiffrés, exportés dans l'environnement
#   exporter_cle_sops                  l'identité age que sops utilise
#   valeur_sure <valeur>               règle commune aux valeurs de secrets (écriture et lecture)
#   signaler <variable> ok|echec [msg] signal de supervision (Healthchecks) ; l'adresse ne sort jamais
#   dc <args…>                         docker compose du projet (compose.yml, compose.projet.yml, et les montages de compose.env)
#   valeur_de <clé> <fichier>          la valeur d'une clé d'un fichier CLE=valeur (lu, jamais sourcé)
#   lire_projet_env <clé> [<fichier>]  PROJET_MOTS : les mots de cette clé dans deploiement/projet.env (ou ce fichier)
#   lire_projet_env_facultatif <clé> [<fichier>]  la même chose pour une clé facultative : absente, PROJET_MOTS vide
#   donnees_declarees                  DECLARE_CONFIG, DECLARE_CONTENU : 1 si projet.env déclare VERIFIER_CONFIG, VERIFIER_CONTENU, sinon 0
#   donnees_declarees_dans <fichier>   la même chose, d'après ce fichier, le projet.env d'une autre version
#   controler_paires <commit>          la règle des paires : chaque dossier de l'instance du commit avec sa commande, et l'inverse (son README.md seul ne compte pas)
#   preparer_instantane <commit>       INSTANTANE : l'instantané en lecture seule des dossiers déclarés du commit de données (sans config/ en staging)
#   _retirer_fige <chemin>             (privée) retire un dossier figé en lecture seule, comme un instantané : les droits d'abord, jamais à travers un lien ; le ménage des instantanés (nettoyer-images.sh) s'en sert aussi
#   verifier_instantane <env> <image> <instantané> [<instantané en service>]  VERIFIER_CONFIG et VERIFIER_CONTENU, en conteneur jetable
#   _verifier_par <CLÉ> <libellé> <image> <-v …> -- <arguments…>  (privée) une commande de projet.env en conteneur jetable, sans réseau ; ci/verifier-image.sh s'en sert aussi, sur l'exemple du dépôt
#   jq_vaut <attendu> <doc> <filtre>   le filtre jq, appliqué au document, imprime exactement <attendu>
#   revision_de <image>                le label de révision (SHA du commit) de l'image
#   sante_sur <port> <filtre> [opts]   un essai sur http://127.0.0.1:<port>/sante
#   sante_locale <version> <révision> [<configuration>]  un essai sur le port de l'environnement : statut, version, révision (et configuration)
#   attendre_sante <port> <filtre> …   jusqu'à 10 essais de sante_sur
#   reserver_a_prod <env> <script>     code 64 hors prod (sauvegardes, restauration)
#   refuser_image_heritee              refus si VEILLE_EMPLOI_IMAGE, VEILLE_EMPLOI_VERSION, VEILLE_EMPLOI_CONFIG ou VEILLE_EMPLOI_CONTENU est dans l'environnement
#   prendre_verrou                     le verrou de l'état, partagé, sur le descripteur 9
#   lire_version <fichier>             IMAGE_LUE, VERSION_LUE et COMMIT_LU, depuis deploye ou precedent
#   lire_deploye                       DEPLOYE_IMAGE, DEPLOYE_VERSION et DEPLOYE_COMMIT, depuis le fichier deploye
#   lire_echec                         ECHEC_IMAGE et ECHEC_COMMIT, depuis le fichier echec
#   verifier_copie <image> <dossier>   contrôle d'un dossier qui a la forme de /donnees, par la commande VERIFIER
#   noter_couple <instantané>          écrit <instantané>.couple, à côté de lui : le couple de deploye
#   purger_par_nom <dossier> <regex> <limite>  retire les dossiers dont le nom date d'avant <limite>, et leur .couple
#   retirer_partiels <dossier> <regex> retire les instantanés en échec (.partiel) avant un nouvel essai
#   retirer_restes_de_restauration     retire, sous le verrou, ce qu'une restauration tuée a laissé
# Variables posées : VEILLE_EMPLOI_CLONE (racine du clone qui lance le script), DEPOT_IMAGE (le dépôt
# GHCR du projet), MODE_DONNEES (« un » ou « deux » dépôts, M-0006 § 6), SOUS_DOSSIER_ENV,
# SOUS_DOSSIER_SECRETS, SOUS_DOSSIER_CLES, SOUS_DOSSIER_CONFIG et SOUS_DOSSIER_CONTENU (les chemins de
# l'instance dans le clone des données), MOTIF_REFERENCE, MOTIF_VERSION et MOTIF_COMMIT (la forme de
# l'image, de la version et du commit de données dans l'état), MOTIF_SHA (un sha de commit, sans
# « - ») et VEILLE_EMPLOI_OPTIONS_JETABLES (options des conteneurs jetables). charger_env pose en plus
# VEILLE_EMPLOI_CLONE_DONNEES, la racine du clone des données de l'environnement.
#
# Codes de sortie : 64 = usage (environnement inconnu, argument invalide), 3 = secrets absents,
# 1 = toute autre erreur.
#
# Variables de surcharge (pour les tests) :
#   VEILLE_EMPLOI_RACINE_ETAT, VEILLE_EMPLOI_RACINE_DONNEES, VEILLE_EMPLOI_RACINE_SAUVEGARDES  racines des dossiers
#   VEILLE_EMPLOI_CLONE_DONNEES   à deux dépôts, le clone des données des deux environnements (défaut
#                           ~/veille-emploi-donnees en prod, ~/veille-emploi-donnees-staging en staging), lue au chargement
#   VEILLE_EMPLOI_DOCKER_CONFIG   configuration Docker du serveur (DOCKER_CONFIG du shell est ignoré)
#   VEILLE_EMPLOI_SHM             dossier préféré des fichiers temporaires de secrets (défaut /dev/shm)
#   SOPS_AGE_KEY_FILE       identité age (défaut ~/.config/sops/age/serveur.txt)
#   VEILLE_EMPLOI_VERROU_ATTENTE  secondes d'attente de prendre_verrou (défaut 600)
#   VEILLE_EMPLOI_SANTE_DELAI     secondes entre deux essais d'attendre_sante (défaut 3)

# Racine du dépôt auquel appartient cette bibliothèque : le clone qui lance le script.
VEILLE_EMPLOI_CLONE="$(CDPATH='' cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"

# Le dépôt GHCR du projet : celui que tire la sonde, et le seul que vise le ménage des images.
# Défini ici seulement.
# shellcheck disable=SC2034  # lue par sonder.sh et nettoyer-images.sh, qui sourcent lib.sh
DEPOT_IMAGE=ghcr.io/edouardzemb/veille-emploi

# Le mode des données (M-0006, § 6), rendu d'après la nature du dépôt : « deux » pour un dépôt de
# code, dont l'instance (env/, secrets, clés du parc, config/, contenu/) vit dans un second dépôt,
# veille-emploi-donnees ; « un » pour un dépôt de nature donnees, d'avant M-0006, qui la porte lui-même
# jusqu'à sa scission. Défini ici seulement : aucun script ne le recalcule.
MODE_DONNEES="deux"

# Les chemins de l'instance, relatifs à la racine du clone des données (VEILLE_EMPLOI_CLONE_DONNEES, que
# pose charger_env) : à deux dépôts, à la racine du dépôt veille-emploi-donnees ; à un dépôt, sous
# deploiement/ et instance/ du clone unique (M-0006, § 6). Définis ici seulement : aucun autre script
# n'écrit ces chemins.
# shellcheck disable=SC2034  # SOUS_DOSSIER_CLES est lu par sauvegarder.sh, qui source lib.sh
if [ "$MODE_DONNEES" = deux ]; then
  SOUS_DOSSIER_ENV="env"
  SOUS_DOSSIER_SECRETS="secrets"
  SOUS_DOSSIER_CLES="cles"
  SOUS_DOSSIER_CONFIG="config"
  SOUS_DOSSIER_CONTENU="contenu"
else
  SOUS_DOSSIER_ENV="deploiement/env"
  SOUS_DOSSIER_SECRETS="deploiement/secrets"
  SOUS_DOSSIER_CLES="deploiement/cles"
  SOUS_DOSSIER_CONFIG="instance/config"
  SOUS_DOSSIER_CONTENU="instance/contenu"
fi

# La surcharge du clone des données (tests), lue une fois, au chargement : poser_clone_donnees pose
# ensuite la variable du même nom, et un second appel (prod puis staging) ne doit pas reprendre la
# valeur du premier.
_VEILLE_EMPLOI_CLONE_DONNEES_SURCHARGE="${VEILLE_EMPLOI_CLONE_DONNEES:-}"

# La forme d'une image, d'une version et d'un commit de données de l'état : ce que deployer.sh
# accepte en argument et écrit dans deploye, precedent, echec et compose.env, et ce qu'exigent ceux
# qui les relisent (lire_version, pour deployer.sh et nettoyer-images.sh ; lire_deploye et
# lire_echec). Définis ici seulement : une forme nouvelle (une version X.Y.Z-rc.1…) vaut à la fois
# pour l'écriture et pour la lecture, et le ménage des images ne s'annule pas, en silence, à chaque
# passage. Le commit de données est un sha de 40 caractères, ou « - » pour un couple sans données
# montées, et pour un état d'avant la v0.7.0, qui n'a pas ce champ (M-0004, amendé). MOTIF_SHA est
# ce sha seul, sans « - » : le commit qui nomme un dossier de l'état (instantanes/<sha>), et la
# révision d'une image.
MOTIF_REFERENCE='^[a-z0-9][a-z0-9._/:-]*@sha256:[0-9a-f]{64}$'
MOTIF_VERSION='^(main|[0-9]+\.[0-9]+\.[0-9]+)$'
MOTIF_COMMIT='^([0-9a-f]{40}|-)$'
MOTIF_SHA='^[0-9a-f]{40}$'

# journal <message…> : une ligne sur stderr, préfixée de l'heure ISO (UTC).
journal() {
  printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" >&2
}

# arreter <code> <message…> : journalise et quitte le script avec ce code.
arreter() {
  local code="$1"
  shift
  journal "$@"
  exit "$code"
}

# valider_env <env> : prod ou staging, sinon code 64.
valider_env() {
  case "${1:-}" in
    prod | staging) ;;
    *) arreter 64 "environnement inconnu : '${1:-}' (attendu : prod ou staging)" ;;
  esac
}

# Source un fichier dotenv public (l'env de l'environnement, dans le clone des données) en exportant
# ses variables, et laisse `set -a` dans l'état où il l'a trouvé. Jamais pour des secrets : un
# fichier sourcé peut exécuter du code et tuer le shell (voir charger_secrets).
_sourcer_en_exportant() {
  local deja_actif=0 code=0
  case $- in *a*) deja_actif=1 ;; esac
  set -a
  # shellcheck disable=SC1090
  . "$1" || code=$?
  [ "$deja_actif" -eq 1 ] || set +a
  return "$code"
}

# poser_clone_donnees <prod|staging> : VEILLE_EMPLOI_CLONE_DONNEES ← le clone des données de
# l'environnement, sans rien y lire : à deux dépôts, ~/veille-emploi-donnees en prod et
# ~/veille-emploi-donnees-staging en staging, sauf la surcharge des tests ; à un dépôt, le clone qui lance
# le script. La seule règle de ce chemin : charger_env l'appelle, et sonder.sh aussi, avant lui, pour
# dire un clone absent, là où charger_env s'arrêterait sans signal.
poser_clone_donnees() {
  valider_env "${1:-}"
  if [ "$MODE_DONNEES" = deux ]; then
    local clone_donnees="$HOME/veille-emploi-donnees"
    [ "$1" = prod ] || clone_donnees="$clone_donnees-staging"
    VEILLE_EMPLOI_CLONE_DONNEES="${_VEILLE_EMPLOI_CLONE_DONNEES_SURCHARGE:-$clone_donnees}"
  else
    VEILLE_EMPLOI_CLONE_DONNEES="$VEILLE_EMPLOI_CLONE"
  fi
}

# charger_env <prod|staging> : pose VEILLE_EMPLOI_CLONE_DONNEES (poser_clone_donnees), charge son
# <SOUS_DOSSIER_ENV>/<env>.env, fixe et exporte les chemins du
# serveur (VEILLE_EMPLOI_CLONE, VEILLE_EMPLOI_ETAT, VEILLE_EMPLOI_DONNEES, VEILLE_EMPLOI_SAUVEGARDES, DOCKER_CONFIG),
# préfixe le PATH par ~/.local/bin et crée les dossiers de données, de sauvegardes et d'état. Créés
# ici, ils appartiennent à l'utilisateur (uid 1000 sur le serveur, comme le conteneur) ; créés par
# Docker au premier `up`, ils appartiendraient à root et l'application n'y écrirait pas.
# VEILLE_EMPLOI_CLONE_DONNEES n'est pas exportée : chaque script la pose par son propre charger_env.
charger_env() {
  local nom_env="${1:-}"
  valider_env "$nom_env"
  poser_clone_donnees "$nom_env"

  local fichier="$VEILLE_EMPLOI_CLONE_DONNEES/$SOUS_DOSSIER_ENV/$nom_env.env"
  [ -f "$fichier" ] || arreter 1 "fichier d'environnement absent : $fichier"
  _sourcer_en_exportant "$fichier" || arreter 1 "fichier d'environnement illisible : $fichier"
  [ "${VEILLE_EMPLOI_ENV:-}" = "$nom_env" ] \
    || arreter 1 "$fichier déclare VEILLE_EMPLOI_ENV='${VEILLE_EMPLOI_ENV:-}', attendu '$nom_env'"

  local racine_donnees="${VEILLE_EMPLOI_RACINE_DONNEES:-$HOME/.local/share/veille-emploi}"
  export VEILLE_EMPLOI_CLONE
  export VEILLE_EMPLOI_ETAT="${VEILLE_EMPLOI_RACINE_ETAT:-$HOME/.local/state/veille-emploi}/$nom_env"
  export VEILLE_EMPLOI_DONNEES="$racine_donnees/$nom_env/donnees"
  # Prod : ~/backups/veille-emploi. Staging : sous les données, hors du dossier de la prod.
  if [ "$nom_env" = prod ]; then
    export VEILLE_EMPLOI_SAUVEGARDES="${VEILLE_EMPLOI_RACINE_SAUVEGARDES:-$HOME/backups/veille-emploi}"
  else
    export VEILLE_EMPLOI_SAUVEGARDES="$racine_donnees/$nom_env/sauvegardes"
  fi
  # Toujours la configuration du serveur (identifiants GHCR, posés par sa sonde), jamais celle du shell.
  export DOCKER_CONFIG="${VEILLE_EMPLOI_DOCKER_CONFIG:-$HOME/.config/serveur/docker}"

  prefixer_path

  mkdir -p "$VEILLE_EMPLOI_ETAT" "$VEILLE_EMPLOI_DONNEES" "$VEILLE_EMPLOI_SAUVEGARDES"
}

# prefixer_path : ~/.local/bin en tête du PATH, une seule fois. C'est là que le serveur installe jq,
# sops, age… et une session SSH sans login ne l'y met pas. charger_env l'appelle.
prefixer_path() {
  case "$PATH" in
    "$HOME/.local/bin:"*) ;;
    *) export PATH="$HOME/.local/bin:$PATH" ;;
  esac
}

# dc <args…> : docker compose pour le projet courant, sur compose.yml (géré par le modèle) et
# compose.projet.yml (les ajouts du projet, que compose fusionne au premier), puis, quand compose.env
# les porte, les montages de l'instantané des données (M-0006, § 5) : compose.config.yml pour
# VEILLE_EMPLOI_CONFIG, compose.contenu.yml pour VEILLE_EMPLOI_CONTENU, gérés, après les ajouts du projet. Le
# fichier compose.env (écrit par le script de déploiement) porte toutes les variables `${…:?}` du
# compose : `dc down`, `dc logs` ou `dc exec` fonctionnent donc aussi, pas seulement `dc up`. Compose
# lit le shell avant --env-file. Les variables de l'env de l'environnement, que charger_env exporte,
# y ont la même valeur. L'image, la version et les montages de l'instantané (VEILLE_EMPLOI_IMAGE,
# VEILLE_EMPLOI_VERSION, VEILLE_EMPLOI_CONFIG, VEILLE_EMPLOI_CONTENU) ne viennent que de compose.env : posés dans le shell, ou par
# une ligne de l'env, ils l'emporteraient, et refuser_image_heritee les refuse.
dc() {
  : "${VEILLE_EMPLOI_PROJET:?dc : charger_env doit précéder dc}"
  local -a fichiers=(-f "$VEILLE_EMPLOI_CLONE/deploiement/compose.yml" -f "$VEILLE_EMPLOI_CLONE/deploiement/compose.projet.yml")
  if valeur_de VEILLE_EMPLOI_CONFIG "$VEILLE_EMPLOI_ETAT/compose.env" >/dev/null; then
    fichiers+=(-f "$VEILLE_EMPLOI_CLONE/deploiement/compose.config.yml")
  fi
  if valeur_de VEILLE_EMPLOI_CONTENU "$VEILLE_EMPLOI_ETAT/compose.env" >/dev/null; then
    fichiers+=(-f "$VEILLE_EMPLOI_CLONE/deploiement/compose.contenu.yml")
  fi
  docker compose -p "$VEILLE_EMPLOI_PROJET" "${fichiers[@]}" --env-file "$VEILLE_EMPLOI_ETAT/compose.env" "$@"
}

# valeur_de <clé> <fichier> : la valeur de cette clé dans un fichier CLE=valeur écrit par les
# scripts (compose.env). Le fichier est lu, jamais sourcé. Échec si le fichier ou la clé manque.
valeur_de() {
  local ligne
  [ -f "$2" ] || return 1
  while IFS= read -r ligne || [ -n "$ligne" ]; do
    if [[ "$ligne" == "$1="* ]]; then
      printf '%s\n' "${ligne#*=}"
      return 0
    fi
  done <"$2"
  return 1
}

# lire_projet_env <CLÉ> [<fichier>] : les mots de la valeur de cette clé dans deploiement/projet.env
# (les réglages du projet, ses commandes de sauvegarde par exemple), ou dans <fichier>, une autre
# version de lui, dans le tableau PROJET_MOTS. Le fichier est lu, jamais sourcé, et il est contrôlé
# en entier : chaque ligne qui n'est ni vide ni un commentaire doit être de la forme CLE=mots, la
# clé en majuscules, les mots séparés par des espaces et soumis à la règle de valeur_sure. Échec,
# journalisé et PROJET_MOTS vide, si le fichier manque, si une ligne est invalide, ou si la clé est
# absente ou déclarée deux fois.
lire_projet_env() {
  local cle="${1:-}" fichier="${2:-$VEILLE_EMPLOI_CLONE/deploiement/projet.env}" ligne nom valeur numero=0 trouvee=0
  PROJET_MOTS=()
  [[ "$cle" =~ ^[A-Z][A-Z0-9_]*$ ]] || arreter 64 "lire_projet_env : clé invalide"
  if [ ! -f "$fichier" ]; then
    journal "réglages du projet absents : $fichier"
    return 1
  fi
  while IFS= read -r ligne || [ -n "$ligne" ]; do
    numero=$((numero + 1))
    case "$ligne" in '' | '#'*) continue ;; esac
    nom="${ligne%%=*}"
    valeur="${ligne#*=}"
    # Les espaces séparent les mots ; tout le reste suit la règle des secrets.
    if [[ "$ligne" != *=* ]] || ! [[ "$nom" =~ ^[A-Z][A-Z0-9_]*$ ]] || ! valeur_sure "${valeur// /}"; then
      journal "réglages du projet illisibles : $fichier, ligne $numero invalide (attendu : CLE=mots, sans caractère spécial du shell)"
      PROJET_MOTS=()
      return 1
    fi
    [ "$nom" = "$cle" ] || continue
    if [ "$trouvee" -eq 1 ]; then
      journal "réglages du projet illisibles : $cle est déclarée deux fois dans $fichier"
      PROJET_MOTS=()
      return 1
    fi
    trouvee=1
    # shellcheck disable=SC2034  # PROJET_MOTS est lu par l'appelant
    IFS=' ' read -r -a PROJET_MOTS <<<"$valeur"
  done <"$fichier"
  if [ "$trouvee" -eq 0 ]; then
    journal "réglage $cle absent de $fichier"
    return 1
  fi
}

# lire_projet_env_facultatif <CLÉ> [<fichier>] : comme lire_projet_env, pour une clé que le projet
# peut ne pas déclarer. Si aucune ligne de deploiement/projet.env (ou de <fichier>) ne commence par
# « CLÉ= » (ou si le fichier manque), succès, PROJET_MOTS vide, et rien n'est lu ni journalisé : le
# script qui l'appelle se comporte comme avant la clé, à l'octet près. Sinon, c'est
# lire_projet_env, avec le contrôle du fichier entier.
lire_projet_env_facultatif() {
  local cle="${1:-}" fichier="${2:-$VEILLE_EMPLOI_CLONE/deploiement/projet.env}" ligne declaree=0
  PROJET_MOTS=()
  [[ "$cle" =~ ^[A-Z][A-Z0-9_]*$ ]] || arreter 64 "lire_projet_env_facultatif : clé invalide"
  [ -f "$fichier" ] || return 0
  while IFS= read -r ligne || [ -n "$ligne" ]; do
    if [[ "$ligne" == "$cle="* ]]; then
      declaree=1
      break
    fi
  done <"$fichier"
  [ "$declaree" -eq 0 ] || lire_projet_env "$cle" "$fichier"
}

# Options des conteneurs jetables (`docker run`), les mêmes restrictions que le service de
# deploiement/compose.yml : utilisateur 1000, système de fichiers en lecture seule, aucune capacité.
VEILLE_EMPLOI_OPTIONS_JETABLES=(--user 1000:1000 --read-only --tmpfs /tmp --cap-drop ALL
  --security-opt no-new-privileges:true --memory 384m)

# --- L'instance : configuration et contenu, dans le clone des données (M-0006, § 5) ------------
# Chaque dossier va avec sa commande de deploiement/projet.env : SOUS_DOSSIER_CONFIG (monté sur
# /config) avec VERIFIER_CONFIG, SOUS_DOSSIER_CONTENU (monté sur /contenu) avec VERIFIER_CONTENU. Un
# projet qui n'en déclare aucune ne monte rien.

# donnees_declarees : DECLARE_CONFIG et DECLARE_CONTENU à 1 si deploiement/projet.env déclare
# VERIFIER_CONFIG, VERIFIER_CONTENU (lire_projet_env_facultatif), à 0 sinon. Échec, journalisé, si
# projet.env ne se lit pas.
donnees_declarees() {
  donnees_declarees_dans "$VEILLE_EMPLOI_CLONE/deploiement/projet.env"
}

# donnees_declarees_dans <fichier> : la même chose, d'après <fichier>, le projet.env d'une autre
# version du code (sonder.sh y passe celui de l'étiquette visée, lu sans checkout). Un fichier
# absent ne déclare rien. Un nom vide ou manquant arrête le script : lire_projet_env_facultatif
# lirait sinon le projet.env du clone, celui d'une autre version.
donnees_declarees_dans() {
  : "${1:?donnees_declarees_dans : fichier manquant}"
  DECLARE_CONFIG=0 DECLARE_CONTENU=0
  lire_projet_env_facultatif VERIFIER_CONFIG "$1" || return 1
  [ -z "${PROJET_MOTS[0]:-}" ] || DECLARE_CONFIG=1
  lire_projet_env_facultatif VERIFIER_CONTENU "$1" || return 1
  [ -z "${PROJET_MOTS[0]:-}" ] || DECLARE_CONTENU=1
}

# _exiger_commit <commit> <fonction> : un commit de données, 40 caractères hexadécimaux, sinon code
# 64 : il nomme un dossier de l'état.
_exiger_commit() {
  [[ "${1:-}" =~ $MOTIF_SHA ]] \
    || arreter 64 "$2 : commit de données invalide : '${1:-}' (attendu : 40 caractères hexadécimaux)"
}

# controler_paires <commit> : la règle des paires sur le commit de données <commit> de
# VEILLE_EMPLOI_CLONE_DONNEES, d'après `git ls-tree -r`. Un dossier de l'instance est présent quand il
# porte, dans ce commit, au moins un fichier autre que le README.md de sa racine
# (<dossier>/README.md, que sème le gabarit du dépôt de données) ; un README.md plus bas compte comme
# un fichier. Un dossier qui ne porte que ce README.md compte comme absent, dans les deux sens de la
# règle. Un dossier présent sans sa commande, ou une commande sans son dossier, refuse : code 1, et
# une ligne « <dossier> sans <commande> » ou « <commande> sans <dossier> » au journal pour chaque
# paire en défaut. Code 1 aussi, journalisé, si projet.env ou le commit ne se lit pas ; 0 sinon.
controler_paires() {
  local commit="${1:-}" paire dossier commande declaree sortie chemin present code=0
  _exiger_commit "$commit" controler_paires
  donnees_declarees || return 1
  for paire in "$SOUS_DOSSIER_CONFIG VERIFIER_CONFIG $DECLARE_CONFIG" \
    "$SOUS_DOSSIER_CONTENU VERIFIER_CONTENU $DECLARE_CONTENU"; do
    read -r dossier commande declaree <<<"$paire"
    if ! sortie="$(git -C "$VEILLE_EMPLOI_CLONE_DONNEES" ls-tree -r --name-only "$commit" -- "$dossier" 2>&1)"; then
      journal "commit de données illisible : $commit dans $VEILLE_EMPLOI_CLONE_DONNEES (${sortie//$'\n'/ })"
      return 1
    fi
    # Un fichier sous <dossier>/, sauf <dossier>/README.md. git cite entre guillemets un nom hors de
    # l'ASCII ordinaire ("<dossier>/été.yml") : il compte aussi. Un fichier qui porterait le nom du
    # dossier lui-même n'est pas un dossier.
    present=0
    while IFS= read -r chemin; do
      case "$chemin" in
        "$dossier/README.md") ;;
        "$dossier"/* | \""$dossier"/*)
          present=1
          break
          ;;
      esac
    done <<<"$sortie"
    if [ "$present" -eq 1 ] && [ "$declaree" -eq 0 ]; then
      journal "$dossier sans $commande (commit de données $commit)"
      code=1
    elif [ "$present" -eq 0 ] && [ "$declaree" -eq 1 ]; then
      journal "$commande sans $dossier (commit de données $commit)"
      code=1
    fi
  done
  return "$code"
}

# preparer_instantane <commit> : INSTANTANE ← $VEILLE_EMPLOI_ETAT/instantanes/<commit>, l'instantané des
# dossiers déclarés du commit de données <commit>, chacun sous son nom final (config/, contenu/, quel
# que soit le mode). En staging, config/ n'est jamais extrait, même quand VERIFIER_CONFIG est
# déclarée : le staging ne monte ni ne vérifie jamais /config (M-0003, § 6). Complet (il a
# chaque dossier à extraire, selon la même règle), il se réutilise tel quel. Sinon, il se fait sous
# <commit>.partiel : le .partiel d'un essai coupé est retiré (_retirer_fige), chaque dossier y est
# extrait du commit (`git archive`, jamais de la copie de travail du clone), les droits passent en
# lecture seule (a-w), puis le .partiel prend son nom. Rend 0, ou 1 journalisé ; un essai qui échoue
# laisse son .partiel, pour le diagnostic, jusqu'au suivant, et un instantané incomplet n'est jamais
# remplacé. À appeler après charger_env, sous le verrou de l'état.
preparer_instantane() {
  local commit="${1:-}" partiel source nom sortie
  local -a dossiers=()
  _exiger_commit "$commit" preparer_instantane
  INSTANTANE="$VEILLE_EMPLOI_ETAT/instantanes/$commit"
  partiel="$INSTANTANE.partiel"
  donnees_declarees || return 1
  if [ "$DECLARE_CONFIG" -eq 1 ] && [ "${VEILLE_EMPLOI_ENV:?preparer_instantane : charger_env doit précéder}" != staging ]; then
    dossiers+=("$SOUS_DOSSIER_CONFIG:config")
  fi
  [ "$DECLARE_CONTENU" -eq 0 ] || dossiers+=("$SOUS_DOSSIER_CONTENU:contenu")

  if [ -e "$INSTANTANE" ] || [ -L "$INSTANTANE" ]; then
    if [ -L "$INSTANTANE" ] || [ ! -d "$INSTANTANE" ]; then
      journal "instantané des données illisible : $INSTANTANE n'est pas un dossier ; rien n'est remplacé"
      return 1
    fi
    for source in "${dossiers[@]}"; do
      nom="${source##*:}"
      if [ ! -d "$INSTANTANE/$nom" ] || [ -L "$INSTANTANE/$nom" ]; then
        journal "instantané des données incomplet : $INSTANTANE (sans $nom) ; rien n'est remplacé"
        return 1
      fi
    done
    journal "instantané des données réutilisé : $INSTANTANE"
    return 0
  fi

  # Le .partiel d'un essai coupé, peut-être déjà en lecture seule.
  if ! _retirer_fige "$partiel"; then
    journal "instantané des données impossible : $partiel, laissé par un essai coupé, ne se retire pas"
    return 1
  fi
  if ! mkdir -p -- "$VEILLE_EMPLOI_ETAT/instantanes" || ! mkdir -- "$partiel"; then
    journal "instantané des données impossible : $partiel ne se crée pas"
    return 1
  fi
  for source in "${dossiers[@]}"; do
    nom="${source##*:}"
    source="${source%:*}"
    if ! sortie="$( (set -o pipefail
      git -C "$VEILLE_EMPLOI_CLONE_DONNEES" archive --format=tar --prefix="$nom/" "$commit:$source" \
        | tar -x -f - -C "$partiel") 2>&1)"; then
      journal "extraction impossible de $source du commit de données $commit : ${sortie//$'\n'/ }"
      return 1
    fi
  done
  if ! chmod -R a-w -- "$partiel" || ! mv -T -- "$partiel" "$INSTANTANE"; then
    journal "instantané des données impossible : $partiel ne se fige pas ou ne prend pas son nom"
    return 1
  fi
  journal "instantané des données prêt : $INSTANTANE"
}

# _retirer_fige <chemin> : retire <chemin>, un dossier peut-être figé en lecture seule (a-w), comme
# un instantané des données ou le .partiel d'un essai coupé après chmod. Les droits d'écriture du
# propriétaire d'abord, jamais à travers un lien : un lien à la place de <chemin> est retiré sans
# toucher à sa cible, et `chmod -R` ne suit pas les liens qu'il rencontre. Puis le retrait. Rend 0 si
# <chemin> n'existe plus (absent dès le départ compris), 1 sinon, sans rien journaliser : à
# l'appelant de le dire. Il ne touche pas aux droits du dossier parent.
_retirer_fige() {
  local chemin="${1:-}"
  [ -n "$chemin" ] || arreter 64 "_retirer_fige : chemin manquant"
  if [ -e "$chemin" ] || [ -L "$chemin" ]; then
    [ -L "$chemin" ] || [ ! -d "$chemin" ] || chmod -R u+w -- "$chemin" 2>/dev/null || true
    rm -rf -- "$chemin" 2>/dev/null || true
  fi
  [ ! -e "$chemin" ] && [ ! -L "$chemin" ]
}

# verifier_instantane <env> <image> <instantané> [<instantané en service>] : lance sur l'instantané
# chaque commande déclarée, dans un conteneur jetable de <image> (--rm), sans réseau, avec les options
# des conteneurs jetables, chaque dossier en lecture seule sur son point de montage :
# `<VERIFIER_CONFIG…> /config` (jamais en staging, qui ne monte jamais /config), puis
# `<VERIFIER_CONTENU…> /contenu`, suivi de /en-service, le contenu de l'instantané en service, s'il
# en a un. Le contrat de l'image : 0 conforme, 2 non conforme, 64 usage. Seul le code fait foi ; la
# sortie va au journal, jamais sur stdout. Rend 0 si tout est conforme, 2 dès qu'une commande dit
# « non conforme », 1 si la vérification n'a pas eu lieu (projet.env illisible, un dossier à monter
# absent, code 64 ou tout autre code). Aucun conteneur ne part si un dossier à monter manque.
verifier_instantane() {
  local nom_env="${1:-}" image="${2:-}" instantane="${3:-}" en_service="${4:-}"
  local -a contenu=(-v "$instantane/contenu:/contenu:ro" -- /contenu)
  valider_env "$nom_env"
  { [[ "$image" =~ $MOTIF_REFERENCE ]] && [ -n "$instantane" ]; } \
    || arreter 64 "usage : verifier_instantane <env> <image@sha256:…> <instantané> [<instantané en service>]"
  donnees_declarees || return 1
  [ "$nom_env" = prod ] || [ "$DECLARE_CONFIG" -eq 0 ] \
    || journal "staging : VERIFIER_CONFIG n'est pas lancée, /config n'y est jamais monté"

  # Tout ce qui sera monté existe, avant le premier conteneur : docker créerait un dossier absent.
  if [ "$nom_env" = prod ] && [ "$DECLARE_CONFIG" -eq 1 ]; then
    _exiger_dossier "$instantane/config" "instantané sans config" || return 1
  fi
  if [ "$DECLARE_CONTENU" -eq 1 ]; then
    _exiger_dossier "$instantane/contenu" "instantané sans contenu" || return 1
    if [ -n "$en_service" ]; then
      _exiger_dossier "$en_service" "instantané en service introuvable" || return 1
      if [ -d "$en_service/contenu" ]; then
        contenu=(-v "$instantane/contenu:/contenu:ro" -v "$en_service/contenu:/en-service:ro" -- /contenu /en-service)
      fi
    fi
  fi

  if [ "$nom_env" = prod ] && [ "$DECLARE_CONFIG" -eq 1 ]; then
    _verifier_par VERIFIER_CONFIG configuration "$image" -v "$instantane/config:/config:ro" -- /config || return
  fi
  if [ "$DECLARE_CONTENU" -eq 1 ]; then
    _verifier_par VERIFIER_CONTENU contenu "$image" "${contenu[@]}" || return
  fi
}

# _exiger_dossier <chemin> <message> : un dossier, et pas un lien ; sinon « <message> : <chemin> »
# au journal, et échec.
_exiger_dossier() {
  { [ -d "$1" ] && [ ! -L "$1" ]; } && return 0
  journal "$2 : $1"
  return 1
}

# _verifier_par <CLÉ> <libellé> <image> <-v source:cible:ro…> -- <arguments…> : la commande <CLÉ> de
# projet.env, dans un conteneur jetable de <image>, sans réseau, avec ces montages, suivie de ces
# arguments. Rend 0, 2 ou 1, comme verifier_instantane.
_verifier_par() {
  local cle="$1" libelle="$2" image="$3" sortie code=0
  local -a montages=()
  shift 3
  while [ "$#" -gt 0 ] && [ "$1" != -- ]; do
    montages+=("$1")
    shift
  done
  shift
  lire_projet_env "$cle" || return 1
  sortie="$(docker run --rm --network none "${VEILLE_EMPLOI_OPTIONS_JETABLES[@]}" "${montages[@]}" "$image" \
    "${PROJET_MOTS[@]}" "$@")" || code=$?
  case "$code" in
    0)
      journal "$libelle conforme ($cle : code 0)${sortie:+ : ${sortie//$'\n'/ }}"
      return 0
      ;;
    2)
      journal "$libelle non conforme ($cle : code 2) : ${sortie//$'\n'/ }"
      return 2
      ;;
    64)
      journal "vérification impossible ($cle : code 64) : usage refusé, l'image ne connaît pas la commande $cle de projet.env : ${sortie//$'\n'/ }"
      return 1
      ;;
    *)
      journal "vérification impossible ($cle : code $code) : ${sortie//$'\n'/ }"
      return 1
      ;;
  esac
}

# jq_vaut <attendu> <document> <filtre> [options jq…] : le filtre, appliqué au document, imprime
# exactement <attendu>. Pas de `jq -e` : jq 1.6 rend 0 sur une entrée vide, et un corps vide
# passerait pour un succès.
jq_vaut() {
  local attendu="$1" document="$2" filtre="$3" resultat
  shift 3
  resultat="$(printf '%s\n' "$document" | jq -r "$@" "$filtre" 2>/dev/null)" || return 1
  [ "$resultat" = "$attendu" ]
}

# revision_de <image> : le label org.opencontainers.image.revision de l'image (SHA du commit,
# 40 caractères hexadécimaux), ou échec.
revision_de() {
  local revision
  revision="$(docker image inspect -f '{{index .Config.Labels "org.opencontainers.image.revision"}}' "$1")" \
    || return 1
  if ! [[ "$revision" =~ $MOTIF_SHA ]]; then
    journal "révision illisible pour $1 : '$revision'"
    return 1
  fi
  printf '%s\n' "$revision"
}

# sante_sur <port> <filtre jq> [options jq…] : un essai sur http://127.0.0.1:<port>/sante.
# Imprime la réponse (ou l'erreur de curl) ; succès si le filtre, appliqué à la réponse, imprime
# true. Les options (--arg…) vont à jq : le filtre y lit ses variables.
sante_sur() {
  local port="$1" filtre="$2" reponse
  shift 2
  if ! reponse="$(curl -fsS -m 5 "http://127.0.0.1:$port/sante" 2>&1)"; then
    printf '%s\n' "$reponse"
    return 1
  fi
  printf '%s\n' "$reponse"
  jq_vaut true "$reponse" "$filtre" "$@"
}

# sante_locale <version> <révision> [<configuration>] : un essai sur
# http://127.0.0.1:$VEILLE_EMPLOI_PORT/sante. Imprime la réponse (ou l'erreur de curl) ; succès si
# elle annonce statut ok, cette version et cette révision, et, avec un troisième argument, ce champ
# configuration (exemple ou montee, M-0003 amendé). Sans lui, le champ n'est pas lu.
sante_locale() {
  # shellcheck disable=SC2016  # $version, $revision et $configuration sont des variables de jq (--arg)
  if [ "$#" -ge 3 ]; then
    sante_sur "$VEILLE_EMPLOI_PORT" \
      '.statut == "ok" and .version == $version and .revision == $revision and .configuration == $configuration' \
      --arg version "$1" --arg revision "$2" --arg configuration "$3"
  else
    sante_sur "$VEILLE_EMPLOI_PORT" '.statut == "ok" and .version == $version and .revision == $revision' \
      --arg version "$1" --arg revision "$2"
  fi
}

# attendre_sante <port> <filtre jq> [options jq…] : jusqu'à 10 essais de sante_sur, à
# VEILLE_EMPLOI_SANTE_DELAI secondes d'écart (défaut 3). Journalise le résultat ; succès dès qu'un essai
# est conforme.
attendre_sante() {
  local port="$1" delai="${VEILLE_EMPLOI_SANTE_DELAI:-3}" essai reponse=""
  for essai in 1 2 3 4 5 6 7 8 9 10; do
    if reponse="$(sante_sur "$@")"; then
      journal "santé conforme sur le port $port (essai $essai) : ${reponse//$'\n'/ }"
      return 0
    fi
    [ "$essai" -eq 10 ] || sleep "$delai"
  done
  journal "santé non conforme sur le port $port après 10 essais ; dernière réponse : ${reponse//$'\n'/ }"
  return 1
}

# reserver_a_prod <env> <script> : les sauvegardes et leur restauration ne concernent que la prod
# (le staging n'a que des données factices, M-0005). Code 64 sinon, avant tout effet de bord.
reserver_a_prod() {
  valider_env "${1:-}"
  [ "$1" = prod ] \
    || arreter 64 "$2 est réservé à la prod (reçu : '$1') : le staging n'a que des données factices (M-0005)"
}

# refuser_image_heritee : VEILLE_EMPLOI_IMAGE, VEILLE_EMPLOI_VERSION, VEILLE_EMPLOI_CONFIG ou VEILLE_EMPLOI_CONTENU posée dans
# l'environnement ferait lire à `dc` autre chose que compose.env (compose donne la priorité au shell
# sur --env-file) : une autre image, ou, pour les deux derniers, un autre dossier monté que
# l'instantané vérifié, la copie de travail du clone des données par exemple (M-0006, § 5). Refus
# net (code 1) plutôt qu'effacement silencieux : l'appelant a une erreur à voir. Une ligne de l'env
# de l'environnement ou des secrets, que charger_env et charger_secrets exportent, compte aussi : à
# appeler après eux, avant toute action. Le nom est resté celui d'avant les montages.
refuser_image_heritee() {
  local variable
  for variable in VEILLE_EMPLOI_IMAGE VEILLE_EMPLOI_VERSION VEILLE_EMPLOI_CONFIG VEILLE_EMPLOI_CONTENU; do
    if [ -n "${!variable+present}" ]; then
      arreter 1 "$variable est posée dans l'environnement : elle prendrait le pas sur compose.env. Rien n'a changé ; relancer sans elle (unset $variable)"
    fi
  done
}

# prendre_verrou : le verrou $VEILLE_EMPLOI_ETAT/verrou, partagé avec la sonde et le déploiement, sur le
# descripteur 9 (gardé jusqu'à la fin du script). Attend VEILLE_EMPLOI_VERROU_ATTENTE secondes (défaut
# 600) ; échec, sans rien journaliser, si le verrou est toujours pris : à l'appelant de le dire.
prendre_verrou() {
  exec 9>"$VEILLE_EMPLOI_ETAT/verrou"
  flock -w "${VEILLE_EMPLOI_VERROU_ATTENTE:-600}" 9
}

# L'état en couple (M-0004, amendé) : deploye et precedent portent "<image@sha256:…> <version>
# <commit>", echec "<image@sha256:…> <commit>", <commit> étant le commit de données ou « - ». Un
# fichier d'avant la v0.7.0 n'a pas ce dernier champ : il se lit « - ». Un champ de plus est ignoré,
# comme le faisaient les scripts d'avant, qui ne lisent que les premiers (`read -r a b _`).

# lire_version <fichier> : l'image, la version et le commit de données d'un fichier deploye ou
# precedent, écrit par deployer.sh, dans IMAGE_LUE, VERSION_LUE et COMMIT_LU. Échec, sans rien
# journaliser et les trois vides, si le fichier manque, ne se lit pas, ou si l'un des champs n'a pas
# la forme que deployer.sh écrit (MOTIF_REFERENCE, MOTIF_VERSION, MOTIF_COMMIT). Utilisée par
# deployer.sh (le retour arrière) et par nettoyer-images.sh (l'état des deux environnements).
lire_version() {
  IMAGE_LUE="" VERSION_LUE="" COMMIT_LU=""
  [ -f "$1" ] || return 1
  { read -r IMAGE_LUE VERSION_LUE COMMIT_LU _ || true; } <"$1" || return 1
  COMMIT_LU="${COMMIT_LU:--}"
  if [[ "$IMAGE_LUE" =~ $MOTIF_REFERENCE ]] && [[ "$VERSION_LUE" =~ $MOTIF_VERSION ]] \
    && [[ "$COMMIT_LU" =~ $MOTIF_COMMIT ]]; then
    return 0
  fi
  IMAGE_LUE="" VERSION_LUE="" COMMIT_LU=""
  return 1
}

# lire_deploye : l'image, la version et le commit de données de $VEILLE_EMPLOI_ETAT/deploye, écrit par
# deployer.sh, dans DEPLOYE_IMAGE, DEPLOYE_VERSION et DEPLOYE_COMMIT (« - » quand le champ manque).
# Échec, journalisé, si le fichier manque (« aucune version déployée »), s'il est là sans être un
# fichier (un dossier, un lien mort : « illisible », comme le signal de la sonde), si l'image n'a pas
# la forme que deployer.sh écrit (MOTIF_REFERENCE) ou le commit non plus (MOTIF_COMMIT) ; la version
# doit seulement ne pas être vide.
lire_deploye() {
  DEPLOYE_IMAGE="" DEPLOYE_VERSION="" DEPLOYE_COMMIT=""
  if [ ! -e "$VEILLE_EMPLOI_ETAT/deploye" ] && [ ! -L "$VEILLE_EMPLOI_ETAT/deploye" ]; then
    journal "aucune version déployée ($VEILLE_EMPLOI_ETAT/deploye absent) : rien sur quoi s'appuyer"
    return 1
  fi
  if [ ! -f "$VEILLE_EMPLOI_ETAT/deploye" ]; then
    journal "$VEILLE_EMPLOI_ETAT/deploye illisible : ce n'est pas un fichier"
    return 1
  fi
  { read -r DEPLOYE_IMAGE DEPLOYE_VERSION DEPLOYE_COMMIT _ || true; } <"$VEILLE_EMPLOI_ETAT/deploye"
  DEPLOYE_COMMIT="${DEPLOYE_COMMIT:--}"
  if ! [[ "$DEPLOYE_IMAGE" =~ $MOTIF_REFERENCE ]] || [ -z "$DEPLOYE_VERSION" ] \
    || ! [[ "$DEPLOYE_COMMIT" =~ $MOTIF_COMMIT ]]; then
    journal "$VEILLE_EMPLOI_ETAT/deploye illisible : '$DEPLOYE_IMAGE' '$DEPLOYE_VERSION' '$DEPLOYE_COMMIT'"
    return 1
  fi
}

# lire_echec : le couple en échec de $VEILLE_EMPLOI_ETAT/echec, écrit par deployer.sh, dans ECHEC_IMAGE et
# ECHEC_COMMIT (« - » quand le champ manque). Sans fichier, succès, les deux vides : aucun couple
# n'est en échec. Échec, sans rien journaliser et les deux vides, si le fichier ne se lit pas ou si
# l'un des champs n'a pas la forme que deployer.sh écrit (MOTIF_REFERENCE, MOTIF_COMMIT).
lire_echec() {
  local fichier="$VEILLE_EMPLOI_ETAT/echec"
  ECHEC_IMAGE="" ECHEC_COMMIT=""
  [ -e "$fichier" ] || [ -L "$fichier" ] || return 0
  [ -f "$fichier" ] || return 1
  { read -r ECHEC_IMAGE ECHEC_COMMIT _ || true; } <"$fichier" || return 1
  ECHEC_COMMIT="${ECHEC_COMMIT:--}"
  if [[ "$ECHEC_IMAGE" =~ $MOTIF_REFERENCE ]] && [[ "$ECHEC_COMMIT" =~ $MOTIF_COMMIT ]]; then
    return 0
  fi
  ECHEC_IMAGE="" ECHEC_COMMIT=""
  return 1
}

# verifier_copie <image> <dossier> : contrôle <dossier>, qui a la forme de /donnees (un instantané,
# ou sa copie), par la commande VERIFIER de deploiement/projet.env (lu, jamais sourcé), dans un
# conteneur jetable (--rm) qui ne voit que ce dossier, monté sur /donnees : `<VERIFIER…> /donnees`.
# Le contrat de l'image : 0 conforme, 2 non conforme, 64 usage. Seul le code fait foi ; la sortie
# de la commande va au journal, jamais sur stdout. Rend 0 si la copie est conforme, 2 si l'image la
# dit non conforme, 1 si la vérification n'a pas eu lieu (commande VERIFIER absente ou illisible,
# code 64, tout autre code).
verifier_copie() {
  local image="$1" dossier="$2" sortie code=0
  lire_projet_env VERIFIER || return 1
  sortie="$(docker run --rm "${VEILLE_EMPLOI_OPTIONS_JETABLES[@]}" -v "$dossier:/donnees" "$image" \
    "${PROJET_MOTS[@]}" /donnees)" || code=$?
  case "$code" in
    0)
      journal "copie conforme (verifier : code 0)${sortie:+ : ${sortie//$'\n'/ }}"
      return 0
      ;;
    2)
      journal "copie non conforme (verifier : code 2) : ${sortie//$'\n'/ }"
      return 2
      ;;
    64)
      journal "vérification impossible (verifier : code 64) : usage refusé, l'image déployée ne connaît pas la commande VERIFIER de projet.env : ${sortie//$'\n'/ }"
      return 1
      ;;
    *)
      journal "vérification impossible (verifier : code $code) : ${sortie//$'\n'/ }"
      return 1
      ;;
  esac
}

# noter_couple <instantané> : écrit <instantané>.couple, à côté de l'instantané de /donnees et jamais
# dedans (son contenu et les membres de son archive ne changent pas, M-0005, § 2), une ligne
# « <image> <version> <commit> » : le couple de $VEILLE_EMPLOI_ETAT/deploye à cet instant, lu par
# lire_version (le commit d'un état d'avant la v0.7.0 vaut « - »). Pour l'instantané d'avant un
# déploiement, c'est le couple que le déploiement quitte (M-0005, § 3). Sans deploye (un premier
# déploiement), aucun .couple, et le journal le dit : restaurer.sh dira « couple de l'instantané
# inconnu ». L'écriture passe par un fichier temporaire du même dossier (mktemp, qui le crée
# lui-même), puis `mv -T` : un lien planté à la place du .couple est remplacé, jamais suivi, et un
# .couple n'est jamais à moitié écrit. Rend 0 si le .couple est écrit ou s'il n'y a pas de couple en
# service ; 1, journalisé, si deploye ne se lit pas ou si l'écriture échoue : l'instantané reste,
# sans .couple, et le fichier temporaire est retiré. Utilisée par sauvegarder.sh et deployer.sh,
# sous le verrou de l'état, juste après l'instantané.
noter_couple() {
  local instantane="${1:?noter_couple : instantané manquant}" deploye="$VEILLE_EMPLOI_ETAT/deploye" provisoire=""
  if [ ! -e "$deploye" ] && [ ! -L "$deploye" ]; then
    journal "aucun couple en service ($deploye absent) : pas de $instantane.couple"
    return 0
  fi
  if ! lire_version "$deploye"; then
    journal "$deploye illisible : pas de $instantane.couple"
    return 1
  fi
  if ! provisoire="$(mktemp -- "$instantane.couple.XXXXXX")" \
    || ! printf '%s %s %s\n' "$IMAGE_LUE" "$VERSION_LUE" "$COMMIT_LU" >"$provisoire" \
    || ! mv -T -- "$provisoire" "$instantane.couple"; then
    [ -z "$provisoire" ] || rm -f -- "$provisoire"
    journal "$instantane.couple ne s'écrit pas : l'instantané reste, sans son couple"
    return 1
  fi
  journal "couple noté : $instantane.couple ($IMAGE_LUE $VERSION_LUE $COMMIT_LU)"
}

# purger_par_nom <dossier> <regex> <limite> : retire, emportés en entier, les dossiers de <dossier>
# dont le nom suit <regex> et dont l'horodatage, le premier groupe de la regex (AAAAMMJJTHHMMSSZ),
# est antérieur à <limite>, de la même forme : l'ordre lexical est celui du temps. Le .couple voisin
# d'un instantané (noter_couple), un fichier <nom>.couple, suit la règle de son instantané : même
# nom, même âge ; il part avec lui, et seul s'il est seul. Ni un autre fichier, ni un lien, ni un
# nom d'une autre forme. La date du dossier n'est jamais lue. Dans l'ordre des noms, un instantané
# passe avant son .couple : un retrait qui échoue s'arrête avant le couple. Utilisée par la
# rétention de sauvegarder.sh et par la purge de pre-deploiement/ de deployer.sh.
purger_par_nom() {
  local dossier="$1" motif="$2" limite="$3" chemin nom
  [ -d "$dossier" ] || return 0
  for chemin in "$dossier"/*; do
    [ ! -L "$chemin" ] || continue
    nom="${chemin##*/}"
    if [ -d "$chemin" ]; then
      [[ "$nom" =~ $motif ]] || continue
    elif [ -f "$chemin" ] && [[ "$nom" == *.couple ]]; then
      [[ "${nom%.couple}" =~ $motif ]] || continue
    else
      continue
    fi
    [[ "${BASH_REMATCH[1]}" < "$limite" ]] || continue
    rm -rf -- "$chemin" || return 1
  done
}

# retirer_partiels <dossier> <regex> : retire de <dossier> les instantanés en échec, les entrées
# dont le nom suit <regex> et finit par .partiel, dossiers emportés en entier. À appeler juste
# avant un nouvel instantané : il ne reste alors que le .partiel de la dernière tentative, pour le
# diagnostic, et non un par tentative. Ni un lien (jamais suivi), ni un nom d'une autre
# forme, ni un instantané complet. Chaque entrée est tentée ; échec si l'une n'a pas pu partir.
# Utilisée par deployer.sh (pre-deploiement/) et sauvegarder.sh (quotidiennes/).
retirer_partiels() {
  local dossier="$1" motif="$2" chemin code=0
  [ -d "$dossier" ] || return 0
  for chemin in "$dossier"/*.partiel; do
    [ ! -L "$chemin" ] || continue
    { [ -d "$chemin" ] || [ -f "$chemin" ]; } || continue
    [[ "${chemin##*/}" =~ $motif ]] || continue
    rm -rf -- "$chemin" || code=1
  done
  return "$code"
}

# retirer_restes_de_restauration : retire ce qu'une restauration tuée de force (SIGKILL, plantage de
# l'hôte) laisse hors de portée de son trap : les copies jetables de son report,
# $VEILLE_EMPLOI_SAUVEGARDES/report-<AAAAMMJJTHHMMSSZ> (des copies en clair des données en service, sans
# autre rétention), et sa copie de travail, $VEILLE_EMPLOI_DONNEES.nouvelle. À n'appeler que sous le
# verrou de l'état, que la restauration tient de bout en bout : ce qui reste alors n'est à aucune
# restauration en cours. Rien que des dossiers, jamais un lien (ni suivi, ni retiré), ni un nom
# d'une autre forme. Les droits sont rendus d'abord : la commande du report a pu laisser des
# sous-dossiers en lecture seule. Chaque retrait est journalisé, chaque échec aussi, et l'entrée
# suivante est tentée ; échec si l'une n'a pas pu partir. Utilisée par sauvegarder.sh et
# restaurer.sh.
retirer_restes_de_restauration() {
  local chemin code=0
  local -a restes=()
  for chemin in "$VEILLE_EMPLOI_SAUVEGARDES"/report-*; do
    if [[ "${chemin##*/}" =~ ^report-[0-9]{8}T[0-9]{6}Z$ ]]; then
      restes+=("$chemin")
    fi
  done
  restes+=("$VEILLE_EMPLOI_DONNEES.nouvelle")
  for chemin in "${restes[@]}"; do
    { [ -d "$chemin" ] && [ ! -L "$chemin" ]; } || continue
    chmod -R u+rwX -- "$chemin" 2>/dev/null || true
    if rm -rf -- "$chemin"; then
      journal "reste d'une restauration interrompue retiré : $chemin"
    else
      journal "reste d'une restauration interrompue non retiré : $chemin (une copie des données en clair, à retirer à la main)"
      code=1
    fi
  done
  return "$code"
}

# _sans_trace <fonction> <args…> : exécute la fonction sans trace (`bash -x`, `set -x`), puis rétablit
# la trace si elle était active. Pour les fonctions qui manipulent des secrets : la trace va sur
# stderr, donc dans le journal de systemd, et y écrirait chaque valeur et chaque adresse de ping.
_sans_trace() {
  local trace=0 code=0
  case $- in *x*) trace=1 ;; esac
  { set +x; } 2>/dev/null
  "$@" || code=$?
  [ "$trace" -eq 0 ] || set -x
  return "$code"
}

# signaler <variable> ok|echec [message] : prévient le service de supervision dont l'adresse est
# dans la variable (HC_SONDE…). « echec » ajoute /fail. Une variable vide n'est pas une erreur.
# L'adresse n'est jamais journalisée, tracée ni passée en argument à curl (voir _signaler) : elle
# suffit à envoyer de faux signaux.
signaler() {
  _sans_trace _signaler "$@"
}

_signaler() {
  local variable="${1:?signaler : variable}" etat="${2:?signaler : ok|echec}" message="${3:-}"
  case "$etat" in
    ok | echec) ;;
    *) arreter 64 "signaler : état inconnu '$etat' (attendu : ok ou echec)" ;;
  esac
  [[ "$variable" =~ ^[A-Z][A-Z0-9_]*$ ]] || arreter 64 "signaler : nom de variable invalide"

  local adresse="${!variable:-}"
  if [ -z "$adresse" ]; then
    journal "signal $variable non configuré"
    return 0
  fi
  [ "$etat" = ok ] || adresse="${adresse%/}/fail"

  # L'adresse va à curl par sa configuration, lue sur l'entrée standard (`-K -`), jamais en
  # argument : sur l'hôte partagé, la ligne de commande d'un processus est lisible par les autres
  # comptes (ps). Un guillemet, une barre oblique inverse ou un caractère de contrôle sortiraient de
  # la chaîne `url = "…"` (ou y ajouteraient une ligne) : refusés ici, comme charger_secrets le fait
  # dans les secrets. Le message, un résumé sans secret, reste en argument (--data-raw).
  if [[ "$adresse" == *[[:cntrl:]\"\\]* ]]; then
    journal "signal $variable : adresse refusée (guillemet, barre oblique inverse ou caractère de contrôle), rien n'est envoyé"
    return 1
  fi
  local code=0
  printf 'url = "%s"\n' "$adresse" \
    | curl -fsS -m 10 --retry 3 --data-raw "$message" -K - >/dev/null || code=$?
  if [ "$code" -ne 0 ]; then
    journal "envoi du signal $variable impossible (curl : code $code)"
    return "$code"
  fi
}

# exporter_cle_sops : l'identité age que sops utilise pour déchiffrer.
exporter_cle_sops() {
  export SOPS_AGE_KEY_FILE="${SOPS_AGE_KEY_FILE:-$HOME/.config/sops/age/serveur.txt}"
}

# valeur_sure <valeur> : succès si la valeur est non vide et sans caractère que le shell
# interpréterait (espace, contrôle, guillemet, \, $, `, ; & | < > ( ) ~). Règle commune à
# `scripts/modele/secrets.ps1` (écriture, sur le poste) et à charger_secrets (lecture).
valeur_sure() {
  case "$1" in
    '' | *[[:space:][:cntrl:]\"\'\\\$\`\;\&\|\<\>\(\)\~]*) return 1 ;;
  esac
  return 0
}

# Détruit un fichier qui a contenu des secrets.
_detruire() {
  shred -u "$1" 2>/dev/null || rm -f "$1"
}

# Fichier temporaire du déchiffrement en cours, pour que les gestionnaires de signaux le trouvent.
_VEILLE_EMPLOI_SECRETS_TMP=""
_detruire_secrets_tmp() {
  [ -z "$_VEILLE_EMPLOI_SECRETS_TMP" ] || _detruire "$_VEILLE_EMPLOI_SECRETS_TMP"
  _VEILLE_EMPLOI_SECRETS_TMP=""
}

# charger_secrets <env> : déchiffre <SOUS_DOSSIER_SECRETS>/<env>.env.enc du clone des données (que
# pose charger_env, à appeler avant) et exporte ses variables.
#
# Le clair passe par un fichier temporaire de mode 600 (/dev/shm, sinon $TMPDIR). Il n'y reste que
# le temps du déchiffrement et de la lecture : le fichier est détruit (`shred -u`) avant que la
# moindre ligne soit interprétée, et le clair ne vit plus que dans une variable du script. Un signal
# (INT, TERM, HUP) reçu pendant cette courte fenêtre détruit aussi le fichier ; les gestionnaires de
# l'appelant sont rétablis ensuite. Le contenu n'est jamais sourcé : chaque ligne doit être de la
# forme CLE=valeur, avec la règle de valeur_sure (CLE en majuscules, valeur sans caractère
# que le shell interpréterait), sinon code 1 sans rien charger. Rien d'un fichier déchiffré ne peut
# donc s'exécuter ni tuer le script, et rien n'est tracé sous `set -x`.
# Les secrets ne vivent ensuite que dans l'environnement du script et de ses enfants (docker
# compose y lit ceux dont compose.projet.yml a besoin). Code 3 si le fichier chiffré est absent.
charger_secrets() {
  _sans_trace _charger_secrets "$@"
}

_charger_secrets() {
  local nom_env="${1:-}"
  valider_env "$nom_env"

  local chiffre="${VEILLE_EMPLOI_CLONE_DONNEES:?charger_secrets : charger_env doit précéder}/$SOUS_DOSSIER_SECRETS/$nom_env.env.enc"
  [ -f "$chiffre" ] || arreter 3 "secrets absents pour $nom_env"
  command -v sops >/dev/null 2>&1 || arreter 1 "sops est introuvable dans le PATH"
  exporter_cle_sops

  local dossier="${VEILLE_EMPLOI_SHM:-/dev/shm}" pieges contenu ligne cle valeur numero
  { [ -d "$dossier" ] && [ -w "$dossier" ]; } || dossier="${TMPDIR:-/tmp}"
  _VEILLE_EMPLOI_SECRETS_TMP="$(umask 077 && mktemp "$dossier/veille-emploi-secrets.XXXXXX")" \
    || arreter 1 "fichier temporaire impossible dans $dossier"

  # Fenêtre où le clair existe sur le disque : déchiffrement puis lecture, sans code du fichier.
  pieges="$(trap -p INT TERM HUP)"
  trap '_detruire_secrets_tmp; exit 130' INT
  trap '_detruire_secrets_tmp; exit 143' TERM
  trap '_detruire_secrets_tmp; exit 129' HUP
  if ! sops decrypt --input-type dotenv --output-type dotenv "$chiffre" >"$_VEILLE_EMPLOI_SECRETS_TMP" \
    || ! contenu="$(<"$_VEILLE_EMPLOI_SECRETS_TMP")"; then
    _detruire_secrets_tmp
    arreter 1 "déchiffrement impossible pour $nom_env (identité : $SOPS_AGE_KEY_FILE)"
  fi
  _detruire_secrets_tmp
  trap - INT TERM HUP
  [ -z "$pieges" ] || eval "$pieges"

  # Tout valider avant d'exporter quoi que ce soit. Les messages ne citent que le numéro de ligne.
  # (Substitution de processus plutôt que <<< : les bash anciens écrivent la chaîne dans un fichier.)
  numero=0
  while IFS= read -r ligne || [ -n "$ligne" ]; do
    numero=$((numero + 1))
    case "$ligne" in '' | '#'*) continue ;; esac
    cle="${ligne%%=*}"
    valeur="${ligne#*=}"
    if [[ "$ligne" != *=* ]] || ! [[ "$cle" =~ ^[A-Z][A-Z0-9_]*$ ]] || ! valeur_sure "$valeur"; then
      arreter 1 "secrets illisibles pour $nom_env : ligne $numero invalide (attendu : CLE=valeur, sans espace ni caractère spécial du shell)"
    fi
  done < <(printf '%s\n' "$contenu")
  while IFS= read -r ligne || [ -n "$ligne" ]; do
    case "$ligne" in '' | '#'*) continue ;; esac
    export "${ligne%%=*}=${ligne#*=}"
  done < <(printf '%s\n' "$contenu")
}

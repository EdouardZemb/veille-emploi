#!/usr/bin/env bash
# Ménage d'veille-emploi : retire du Docker du serveur les images du dépôt du projet qui ne servent plus,
# puis, de l'état de l'environnement, les instantanés des données qui ne servent plus. Les deux
# environnements partagent ce Docker, donc ce stock d'images. GHCR garde tout : une image retirée
# revient par un `docker pull`, et `docker compose up` la tire lui-même. Un instantané retiré se
# refait du clone des données (preparer_instantane, lib.sh).
#
#   bash deploiement/nettoyer-images.sh <prod|staging>
#
# Lancé par deployer.sh après chaque déploiement ou retour arrière réussi, avec
# VEILLE_EMPLOI_VERROU_TENU=1 (deployer.sh tient déjà le verrou de l'environnement), ou à la main : il
# prend alors ce verrou lui-même. Toujours par `bash`, depuis le clone de
# l'environnement.
#
# Déroulé (les étapes 2 à 6, les images, dans un sous-shell : une annulation n'y arrête qu'elles) :
#   1. verrou $VEILLE_EMPLOI_ETAT/verrou, partagé avec la sonde et le déploiement (600 s d'attente au
#      plus, prendre_verrou), sauf si VEILLE_EMPLOI_VERROU_TENU=1 ;
#   2. verrou de l'autre environnement, sans attente. S'il est pris, le ménage est sauté (code 0) :
#      le prochain déploiement le fera. Sans ce verrou, une image que l'autre sonde vient de tirer
#      pourrait partir avant d'être inscrite dans son état. Si le dossier d'état de l'autre
#      environnement est absent, il n'y a rien à y protéger, et le journal le dit ;
#   3. l'état des deux environnements, lu sans être sourcé : deploye, precedent, echec, et l'image
#      de compose.env et de compose.env.precedent, à la forme qu'écrit deployer.sh (MOTIF_REFERENCE
#      et MOTIF_VERSION, lire_version : lib.sh) ;
#   4. les conteneurs, même arrêtés, et l'image de chacun ;
#   5. les images, chacune une fois, et leur tri :
#      - la liste passe par `docker image ls --all`. Sans --all, un Docker 29 récent (constaté en
#        29.5.3, magasin classique) cache les images sans étiquette, dont les anciennes :main que
#        la sonde a tirées par empreinte. --all montre aussi les intermédiaires, sans référence ;
#      - une image est du projet si toutes ses références, noms et empreintes, portent exactement
#        le dépôt (DEPOT_IMAGE, de lib.sh) : ni <dépôt>-autre, ni <dépôt>/sous-image. Une image sans
#        aucune référence, ou qui en a une ailleurs, n'est jamais touchée ;
#      - une image du projet est gardée si l'une de ses empreintes est une référence de l'état (la
#        comparaison porte sur les chaînes <dépôt>@sha256:… : l'image d'une référence n'a pas à
#        être sur le serveur), si un conteneur l'utilise, ou si elle est parmi les 3 plus récentes
#        des autres, d'après leur date de création (la marge, tous environnements confondus) ;
#   6. les autres partent, de la plus ancienne à la plus récente, une à une : par leur identifiant
#      (`docker image rm <id>`) si elles portent une étiquette au plus ; sinon par leurs
#      étiquettes, une par appel (`docker image rm <dépôt>:<étiquette>`), car docker refuse sans -f
#      le retrait par l'identifiant d'une image qui en porte plusieurs, et la dernière emporte
#      l'image et ses empreintes. Un retrait en échec est journalisé, et l'image suivante est tentée ;
#   7. les instantanés des données de cet environnement, et de lui seul (M-0004, § 8) :
#      $VEILLE_EMPLOI_ETAT/instantanes/, toujours, même quand le ménage des images est sauté ou annulé.
#      Voir « Les instantanés », plus bas.
#
# Jamais de `-f`, de `docker image prune`, de `docker system prune` ni de retrait par un filtre : le
# script liste toutes les images et choisit lui-même celles du projet.
#
# Le ménage des images est annulé en entier, avant tout retrait (code 1), si :
#   - le verrou de l'autre environnement ne s'ouvre pas, ou flock y échoue autrement que parce
#     qu'il est pris ;
#   - un fichier d'état existe mais ne se lit pas, ou n'a pas la forme qu'écrit deployer.sh ;
#   - la liste des conteneurs ou leur inspection échoue, ou l'image d'un conteneur est illisible ;
#   - la liste des images ou leur inspection échoue, un identifiant d'image est illisible, ou
#     l'inspection est inattendue (un identifiant que la liste n'a pas donné) ou incomplète (moins
#     d'images inspectées que listées) ;
#   - la date de création d'une image candidate à la marge est illisible (attendu : la forme
#     RFC 3339 en UTC que rend Docker ; un décalage, +02:00, ou une date vide annule) ;
#   - le tri des images est impossible.
# Dans le doute, rien ne part. Ce tout ou rien vaut jusqu'au premier retrait ; les retraits, eux,
# se font image par image (étape 6), et une image retirée par ses étiquettes l'est en plusieurs
# appels : un échec au milieu laisse l'image avec une étiquette de moins, ni retirée ni gardée
# (code 1), et un ménage suivant la reprend avec celles qui lui restent.
#
# Journal : une ligne par image retirée, une fois partie (les 12 premiers chiffres de son
# identifiant, puis ses références), une par image dont un retrait échoue, puis le bilan : les
# retirées, et les gardées, par l'état, par un conteneur ou en marge. Une image compte une fois,
# pour la première de ces trois raisons qui la garde ; une image dont un retrait échoue ne compte ni
# parmi les retirées ni parmi les gardées.
#
# Les instantanés (étape 7). $VEILLE_EMPLOI_ETAT/instantanes/ porte un dossier par commit de données,
# figé en lecture seule, et le <commit>.partiel d'un instantané en cours ou coupé (preparer_instantane,
# lib.sh). Le ménage garde les instantanés que nomment deploye et precedent de l'environnement (le
# commit de leur couple, lu par lire_version ; « - », ou un état d'avant la v0.7.0, n'en nomme
# aucun), plus les 3 plus récents des autres (la marge, comme les images), d'après leur date de
# modification, puis leur nom à date égale. Il retire les autres, et tout .partiel de plus d'un jour ;
# un .partiel plus jeune reste, qu'un déploiement peut être en train de construire. Chaque entrée
# est lue une fois, sans suivre de lien ; un retrait passe par _retirer_fige (lib.sh), les droits
# d'abord. Une surprise annule le ménage des instantanés en entier, avant tout retrait, et le journal
# le dit (« ménage des instantanés annulé, rien n'est retiré : <raison> ») :
#   - $VEILLE_EMPLOI_ETAT/instantanes est un lien, ou n'est pas un dossier ;
#   - deploye ou precedent existe mais ne se lit pas, ou n'a pas la forme qu'écrit deployer.sh ;
#   - une entrée dont le nom n'est ni un commit de 40 caractères hexadécimaux ni <commit>.partiel,
#     une entrée qui est un lien, ou qui n'est pas un dossier ;
#   - une date de modification illisible.
# Sans dossier des instantanés (un projet qui ne monte pas de données), rien n'est dit. Le journal :
# une ligne par instantané retiré, une par retrait impossible, puis le bilan, les retirés et les
# gardés, par l'état, en marge, ou parce que .partiel de moins d'un jour. Le ménage des instantanés
# ne change jamais le code de sortie : il dit tout au journal.
#
# Codes de sortie, ceux du ménage des images : 0 fait, ou sauté (verrou de l'autre environnement
# pris) ; 1 un retrait en échec, un ménage annulé, ou le verrou de l'environnement toujours pris
# après l'attente (rien n'est alors fait, ni images ni instantanés) ; 64 usage, ou
# VEILLE_EMPLOI_DEPOT_IMAGE refusée.
#
# Variables de test :
#   VEILLE_EMPLOI_DEPOT_IMAGE     le dépôt visé, à la place de DEPOT_IMAGE. Seul un registre de la machine
#                          (localhost:<port>/…) est accepté, sinon code 64 avant toute lecture : le
#                          ménage ne vise jamais le dépôt d'un autre projet
#   VEILLE_EMPLOI_VERROU_ATTENTE  secondes d'attente du verrou de l'environnement (défaut 600)
set -euo pipefail
# shellcheck source=deploiement/lib.sh
. "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

# La marge : parmi les images du projet que rien ne protège, les plus récentes, gardées. La même
# pour les instantanés des données.
MARGE=3
# Les noms du dossier des instantanés : un commit de données (MOTIF_SHA, lib.sh), ou l'instantané
# provisoire d'un commit, <commit>.partiel (preparer_instantane, lib.sh). Un .partiel plus vieux que
# AGE_PARTIEL secondes est le reste d'un essai coupé ; plus jeune, un déploiement peut être en train
# de le construire.
AGE_PARTIEL=86400

# Ce qu'écrit deployer.sh dans l'état suit MOTIF_REFERENCE et MOTIF_VERSION, de lib.sh. Ce que
# rend Docker : un identifiant, et une date RFC 3339 en UTC dont la fraction perd ses zéros de fin,
# et disparaît s'il n'en reste rien (…T10:00:00Z, …T10:00:00.5Z, …T10:00:00.123456789Z).
MOTIF_IDENTIFIANT='^sha256:[0-9a-f]{64}$'
MOTIF_DATE='^([0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2})(\.([0-9]{1,9}))?Z$'
# Le seul dépôt que la variable de test peut désigner : un registre de la machine.
MOTIF_DEPOT_DE_TEST='^localhost:[0-9]+/[a-z0-9._/-]+$'
# Le format de `docker image inspect` : identifiant, date de création, noms, empreintes.
FORMAT_IMAGE='{{.Id}}|{{.Created}}|{{range .RepoTags}}{{.}} {{end}}|{{range .RepoDigests}}{{.}} {{end}}'

# Posées par main et ses fonctions.
DEPOT=""                 # le dépôt visé : DEPOT_IMAGE, ou la variable de test
declare -A NOMMEE=()     # référence → 1 : les images que nomme l'état des deux environnements
declare -A UTILISEE=()   # identifiant → 1 : les images d'un conteneur, arrêté ou non
declare -A REFERENCES=() # identifiant → ses références, pour le journal
declare -A ETIQUETTES=() # identifiant → ses noms (RepoTags), ses cibles de retrait s'il y en a 2+
NOM=""                   # posé par nom_de

# annuler <raison> : le ménage s'arrête avant tout retrait, code 1.
annuler() {
  arreter 1 "ménage des images annulé, rien n'est retiré : $1"
}

# accorder <nombre> <mot> : « 0 retirée », « 1 retirée », « 2 retirées ».
accorder() {
  if [ "$1" -ge 2 ]; then
    printf '%s %ss\n' "$1" "$2"
  else
    printf '%s %s\n' "$1" "$2"
  fi
}

# nom_de <référence> : NOM ← le nom de la référence, sans son empreinte (ce qui précède « @ ») ni
# son étiquette (le « :<étiquette> » final, si le dernier « : » suit le dernier « / » ; celui d'un
# port, localhost:5000/…, n'en est pas une).
nom_de() {
  NOM="$1"
  if [[ "$NOM" == *@* ]]; then
    NOM="${NOM%%@*}"
  elif [[ "${NOM##*/}" == *:* ]]; then
    NOM="${NOM%:*}"
  fi
}

# lire_etat <dossier> : NOMMEE ← les images que nomment les fichiers d'état de ce dossier, lus,
# jamais sourcés : deploye et precedent (« <image@sha256:…> <version> <commit|-> », par lire_version
# de lib.sh, comme deployer.sh les lit, qui contrôle la forme des trois champs), echec
# (« <image@sha256:…> <commit|-> », dont seul le premier champ est lu), et la ligne
# VEILLE_EMPLOI_IMAGE= de compose.env et de compose.env.precedent. Seule l'image compte : la version et
# le commit de données ne gardent aucune image. Un fichier absent (ou un dossier absent) ne protège
# rien ; un fichier présent qui ne se lit pas, ou qui n'a pas la forme qu'écrit deployer.sh, annule
# le ménage.
lire_etat() {
  local fichier chemin image
  for fichier in deploye precedent echec compose.env compose.env.precedent; do
    chemin="$1/$fichier"
    [ -e "$chemin" ] || [ -L "$chemin" ] || continue
    image=""
    case "$fichier" in
      deploye | precedent)
        if lire_version "$chemin"; then
          image="$IMAGE_LUE"
        fi
        ;;
      echec)
        if [ -f "$chemin" ]; then
          { read -r image _ || true; } <"$chemin" || image=""
        fi
        ;;
      *)
        image="$(valeur_de VEILLE_EMPLOI_IMAGE "$chemin")" || image=""
        ;;
    esac
    [[ "$image" =~ $MOTIF_REFERENCE ]] \
      || annuler "$chemin illisible (attendu : la forme qu'écrit deployer.sh)"
    NOMMEE["$image"]=1
  done
}

# abandonner_instantanes <raison> : le ménage des instantanés s'arrête avant tout retrait. Le code de
# sortie ne change pas : c'est celui des images.
abandonner_instantanes() {
  journal "ménage des instantanés annulé, rien n'est retiré : $1"
}

# menage_instantanes : l'étape 7, les instantanés des données de $VEILLE_EMPLOI_ETAT/instantanes/, ceux
# de cet environnement seulement (M-0004, § 8) ; voir « Les instantanés », en tête. Rend toujours
# 0 : une surprise ou un retrait impossible ne se disent qu'au journal.
menage_instantanes() {
  local etat="$VEILLE_EMPLOI_ETAT" dossier="$VEILLE_EMPLOI_ETAT/instantanes" fichier chemin nom modifie
  local maintenant tries partiel par_etat=0 en_marge=0 recents=0 retires=0 rang=0
  local -A gardes=()
  local -a candidats=() plus_vieux_d_abord=() a_retirer=()
  [ -e "$dossier" ] || [ -L "$dossier" ] || return 0
  if [ -L "$dossier" ]; then
    abandonner_instantanes "$dossier est un lien, qui n'est jamais suivi"
    return 0
  fi
  if [ ! -d "$dossier" ]; then
    abandonner_instantanes "$dossier n'est pas un dossier"
    return 0
  fi

  # Ce que l'état garde : le commit du couple de deploye et de precedent ; « - » n'en garde aucun.
  for fichier in deploye precedent; do
    chemin="$etat/$fichier"
    [ -e "$chemin" ] || [ -L "$chemin" ] || continue
    if ! lire_version "$chemin"; then
      abandonner_instantanes "$chemin illisible (attendu : la forme qu'écrit deployer.sh)"
      return 0
    fi
    [ "$COMMIT_LU" = - ] || gardes["$COMMIT_LU"]=1
  done

  # Chaque entrée, une fois, sans suivre de lien ; toutes sont lues avant le premier retrait. Les
  # motifs sans correspondance restent tels quels, et ne désignent rien qui existe.
  if ! maintenant="$(date +%s)"; then
    abandonner_instantanes "heure illisible"
    return 0
  fi
  for chemin in "$dossier"/* "$dossier"/.*; do
    nom="${chemin##*/}"
    case "$nom" in . | ..) continue ;; esac
    [ -e "$chemin" ] || [ -L "$chemin" ] || continue
    # Un commit (MOTIF_SHA, lib.sh), ou ce commit suivi de .partiel.
    partiel=0
    if [[ "$nom" == *.partiel ]] && [[ "${nom%.partiel}" =~ $MOTIF_SHA ]]; then
      partiel=1
    elif ! [[ "$nom" =~ $MOTIF_SHA ]]; then
      abandonner_instantanes "nom inattendu : $chemin (attendu : un commit de 40 caractères hexadécimaux, ou <commit>.partiel)"
      return 0
    fi
    if [ -L "$chemin" ]; then
      abandonner_instantanes "$chemin est un lien, qui n'est jamais suivi"
      return 0
    fi
    if [ ! -d "$chemin" ]; then
      abandonner_instantanes "$chemin n'est pas un dossier"
      return 0
    fi
    # La date de modification, en secondes, par stat, qui ne suit pas les liens.
    if ! modifie="$(stat -c %Y -- "$chemin")" || ! [[ "$modifie" =~ ^[0-9]+$ ]]; then
      abandonner_instantanes "date de modification illisible pour $chemin"
      return 0
    fi
    if [ "$partiel" -eq 1 ]; then
      if [ "$modifie" -lt "$((maintenant - AGE_PARTIEL))" ]; then
        a_retirer+=("$nom")
      else
        recents=$((recents + 1))
      fi
    elif [ -n "${gardes[$nom]+present}" ]; then
      par_etat=$((par_etat + 1))
    else
      candidats+=("$modifie $nom")
    fi
  done

  # La marge : les plus récents d'abord, à date égale dans l'ordre des noms ; au-delà, du plus
  # ancien au plus récent.
  if [ -n "${candidats[*]}" ]; then
    if ! tries="$(printf '%s\n' "${candidats[@]}" | LC_ALL=C sort -k1,1nr -k2,2)"; then
      abandonner_instantanes "tri des instantanés impossible"
      return 0
    fi
    while IFS=' ' read -r _ nom; do
      rang=$((rang + 1))
      if [ "$rang" -le "$MARGE" ]; then
        en_marge=$((en_marge + 1))
      else
        plus_vieux_d_abord=("$nom" "${plus_vieux_d_abord[@]}")
      fi
    done <<<"$tries"
    a_retirer+=("${plus_vieux_d_abord[@]}")
  fi

  # Les retraits, un à la fois : un échec est journalisé, et l'instantané suivant est tenté.
  for nom in "${a_retirer[@]}"; do
    if _retirer_fige "$dossier/$nom"; then
      journal "instantané retiré : $nom"
      retires=$((retires + 1))
    else
      journal "retrait impossible : $dossier/$nom"
    fi
  done
  journal "ménage des instantanés : $(accorder "$retires" retiré), $(accorder "$((par_etat + en_marge + recents))" gardé) ($par_etat par l'état, $en_marge en marge, $(accorder "$recents" partiel) de moins d'un jour)"
}

# menage_images <env> : les étapes 2 à 6, les images. Lancée dans un sous-shell (main) : annuler
# (code 1) n'arrête qu'elle.
menage_images() {
  local nom_env="$1" etat="$VEILLE_EMPLOI_ETAT" autre dossier_autre verrou_autre sortie ligne code=0
  local id cree noms empreintes reference du_depot nommee fraction tries rang cible partie
  local par_etat=0 par_conteneur=0 en_marge=0 retirees=0 listees=0 inspectees=0
  local -a conteneurs=() identifiants=() references=() liste_empreintes=() candidats=() a_retirer=()
  local -a etiquettes=() cibles=()
  local -A vue=()

  # 2. Le verrou de l'autre environnement, sans attente, sur le descripteur 8. flock rend 1 quand
  # il est pris ; tout autre code est une erreur.
  case "$nom_env" in
    prod) autre=staging ;;
    *) autre=prod ;;
  esac
  dossier_autre="$(dirname "$etat")/$autre"
  if [ -e "$dossier_autre" ] || [ -L "$dossier_autre" ]; then
    verrou_autre="$dossier_autre/verrou"
    { exec 8>"$verrou_autre"; } 2>/dev/null || annuler "le verrou $verrou_autre ne s'ouvre pas"
    flock -n 8 || code=$?
    case "$code" in
      0) ;;
      1)
        journal "ménage des images sauté : le verrou $verrou_autre est pris ; le prochain déploiement le fera"
        return 0
        ;;
      *) annuler "le verrou $verrou_autre ne se prend pas (flock : code $code)" ;;
    esac
  else
    journal "$autre : aucun état ($dossier_autre absent), rien à y protéger"
  fi

  # 3. L'état des deux environnements.
  lire_etat "$etat"
  lire_etat "$dossier_autre"

  # 4. Les conteneurs, même arrêtés, et leurs images.
  sortie="$(docker ps --all --no-trunc --quiet)" \
    || annuler "liste des conteneurs impossible (docker ps : code $?)"
  while IFS= read -r ligne; do
    [ -z "$ligne" ] || conteneurs+=("$ligne")
  done <<<"$sortie"
  if [ -n "${conteneurs[*]}" ]; then
    sortie="$(docker container inspect --format '{{.Image}}' "${conteneurs[@]}")" \
      || annuler "inspection des conteneurs impossible (docker container inspect : code $?)"
    while IFS= read -r ligne; do
      [[ "$ligne" =~ $MOTIF_IDENTIFIANT ]] || annuler "image d'un conteneur illisible : '$ligne'"
      UTILISEE["$ligne"]=1
    done <<<"$sortie"
  fi

  # 5. Les images : chaque identifiant une fois (une image à deux noms est listée deux fois), puis
  # leur inspection, et le tri. --all, pour les images sans étiquette (étape 5, en tête).
  sortie="$(docker image ls --all --no-trunc --quiet)" \
    || annuler "liste des images impossible (docker image ls : code $?)"
  while IFS= read -r ligne; do
    [ -n "$ligne" ] || continue
    [[ "$ligne" =~ $MOTIF_IDENTIFIANT ]] || annuler "identifiant d'image illisible : '$ligne'"
    [ -z "${vue[$ligne]+present}" ] || continue
    vue["$ligne"]=1
    identifiants+=("$ligne")
    listees=$((listees + 1))
  done <<<"$sortie"
  sortie=""
  if [ "$listees" -gt 0 ]; then
    sortie="$(docker image inspect --format "$FORMAT_IMAGE" "${identifiants[@]}")" \
      || annuler "inspection des images impossible (docker image inspect : code $?)"
  fi
  while IFS='|' read -r id cree noms empreintes; do
    [ -n "$id$cree$noms$empreintes" ] || continue
    [ -n "${vue[$id]+present}" ] || annuler "inspection inattendue : '$id'"
    inspectees=$((inspectees + 1))
    read -r -a references <<<"$noms $empreintes"
    read -r -a liste_empreintes <<<"$empreintes"
    # Sans aucune référence, ou avec une référence hors du dépôt : jamais touchée.
    [ -n "${references[*]}" ] || continue
    du_depot=1
    for reference in "${references[@]}"; do
      nom_de "$reference"
      if [ "$NOM" != "$DEPOT" ]; then
        du_depot=0
        break
      fi
    done
    [ "$du_depot" -eq 1 ] || continue
    # Gardée par l'état, puis par un conteneur ; sinon, candidate à la marge.
    nommee=0
    for reference in "${liste_empreintes[@]}"; do
      [ -z "${NOMMEE[$reference]+present}" ] || nommee=1
    done
    if [ "$nommee" -eq 1 ]; then
      par_etat=$((par_etat + 1))
    elif [ -n "${UTILISEE[$id]+present}" ]; then
      par_conteneur=$((par_conteneur + 1))
    else
      # La fraction complétée à 9 chiffres : l'ordre des chaînes est alors celui du temps.
      [[ "$cree" =~ $MOTIF_DATE ]] || annuler "date de création illisible pour ${id:7:12} : '$cree'"
      fraction="${BASH_REMATCH[3]}000000000"
      candidats+=("${BASH_REMATCH[1]}.${fraction:0:9}Z $id")
      REFERENCES["$id"]="${references[*]}"
      ETIQUETTES["$id"]="$noms"
    fi
  done <<<"$sortie"
  [ "$inspectees" -eq "$listees" ] \
    || annuler "inspection incomplète : $inspectees images inspectées sur $listees listées"

  # La marge : les plus récentes d'abord ; au-delà, de la plus ancienne à la plus récente.
  if [ -n "${candidats[*]}" ]; then
    tries="$(printf '%s\n' "${candidats[@]}" | LC_ALL=C sort -r)" || annuler "tri des images impossible"
    rang=0
    while IFS=' ' read -r _ id; do
      rang=$((rang + 1))
      if [ "$rang" -le "$MARGE" ]; then
        en_marge=$((en_marge + 1))
      else
        a_retirer=("$id" "${a_retirer[@]}")
      fi
    done <<<"$tries"
  fi

  # 6. Les retraits, une image à la fois : par l'identifiant (une étiquette au plus), sinon par ses
  # étiquettes, une par appel, que docker accepte sans -f ; la dernière emporte l'image et ses
  # empreintes. Un échec arrête cette image, pas les suivantes.
  code=0
  for id in "${a_retirer[@]}"; do
    read -r -a etiquettes <<<"${ETIQUETTES[$id]}"
    if [ -n "${etiquettes[1]:-}" ]; then
      cibles=("${etiquettes[@]}")
    else
      cibles=("$id")
    fi
    partie=1
    for cible in "${cibles[@]}"; do
      if ! sortie="$(docker image rm "$cible" 2>&1)"; then
        journal "retrait impossible : ${id:7:12} (${sortie//$'\n'/ })"
        code=1
        partie=0
        break
      fi
    done
    if [ "$partie" -eq 1 ]; then
      journal "image retirée : ${id:7:12} (${REFERENCES[$id]})"
      retirees=$((retirees + 1))
    fi
  done

  journal "ménage des images : $(accorder "$retirees" retirée), $(accorder "$((par_etat + par_conteneur + en_marge))" gardée) ($par_etat par l'état, $par_conteneur par un conteneur, $en_marge en marge)"
  return "$code"
}

main() {
  [ "$#" -eq 1 ] || arreter 64 "usage : bash deploiement/nettoyer-images.sh <prod|staging>"
  local nom_env="$1" code=0 code_instantanes=0
  valider_env "$nom_env"
  charger_env "$nom_env"

  # Le dépôt : celui du projet, ou, pour l'épreuve sur un vrai Docker, un registre de la machine.
  DEPOT="$DEPOT_IMAGE"
  if [ -n "${VEILLE_EMPLOI_DEPOT_IMAGE+present}" ]; then
    [[ "$VEILLE_EMPLOI_DEPOT_IMAGE" =~ $MOTIF_DEPOT_DE_TEST ]] \
      || arreter 64 "VEILLE_EMPLOI_DEPOT_IMAGE refusée : seul un registre de la machine (localhost:<port>/…) est accepté"
    DEPOT="$VEILLE_EMPLOI_DEPOT_IMAGE"
  fi

  # 1. Le verrou de l'environnement : tenu par celui qui lance le ménage, ou pris ici.
  if [ "${VEILLE_EMPLOI_VERROU_TENU:-}" != 1 ] && ! prendre_verrou; then
    arreter 1 "verrou $VEILLE_EMPLOI_ETAT/verrou toujours pris après ${VEILLE_EMPLOI_VERROU_ATTENTE:-600} s : ménage abandonné, rien n'est retiré"
  fi

  # 2 à 6. Les images, dans un sous-shell : annuler (arreter, code 1) n'y arrête qu'elles, et le
  # verrou de l'autre environnement (descripteur 8) se relâche à sa sortie. errexit est rétabli
  # dedans : dans une liste || ou un if, bash l'y ignorerait.
  set +e
  (
    set -e
    menage_images "$nom_env"
  )
  code=$?
  set -e

  # 7. Les instantanés des données de cet environnement, sous le même verrou : ils ne changent pas
  # le code de sortie, celui des images, même sur une erreur inattendue, que le journal dit.
  set +e
  (
    set -e
    menage_instantanes
  )
  code_instantanes=$?
  set -e
  if [ "$code_instantanes" -ne 0 ]; then
    journal "ménage des instantanés interrompu (code $code_instantanes) : le code de sortie reste celui des images"
  fi
  return "$code"
}

# Tout le corps est dans main, appelée sur la dernière ligne : bash a lu tout le fichier avant
# qu'un `git checkout` ne le remplace.
main "$@"; exit $?

#!/usr/bin/env bash
# Restaure les données de prod depuis un instantané (un dossier de quotidiennes/ ou de
# pre-deploiement/, qui a la forme de /donnees) ou depuis une archive chiffrée du distant (.tar.age :
# le dossier de l'instantané, chiffré pour la clé hors ligne). Opération manuelle, réservée à la
# prod (code 64) :
#
#   bash deploiement/restaurer.sh prod <dossier|archive .tar.age> [--oui] [--cle <identité age>] [--sans-report]
#
# Toujours par `bash`, depuis le clone de prod : un projet né sous Windows enregistre les scripts
# sans bit d'exécution.
#
# Archive chiffrée sans écrire la clé hors ligne sur aucun disque, ni celui du serveur ni celui du
# poste (M-0005) : --cle accepte tout chemin lisible qui n'est pas un dossier, donc /dev/stdin, la
# clé arrivant par ssh. Sur le poste, dans Git Bash : `read -rs CLE`, coller la clé hors ligne
# depuis KeePassXC, puis Entrée ; puis
#
#   printf '%s\n' "$CLE" | ssh <le serveur> 'bash ~/veille-emploi/deploiement/restaurer.sh prod <archive>.tar.age --oui --cle /dev/stdin'
#   unset CLE
#
# Sans --oui, le script affiche ce qu'il ferait et rend 64, sans aucun effet (ni verrou, ni
# conteneur, ni déchiffrement ; charger_env crée au plus des dossiers déjà présents en prod). Avec
# --oui :
#   1. verrou $VEILLE_EMPLOI_ETAT/verrou, partagé avec la sonde, le déploiement et la sauvegarde (600 s
#      d'attente au plus) : la sonde ne relancera rien pendant que l'application est arrêtée ;
#   2. l'image est la première colonne de $VEILLE_EMPLOI_ETAT/deploye : sans version déployée, on
#      déploie d'abord (deployer.sh), puis on restaure ;
#   3. l'instantané, dans un dossier temporaire 0700, détruit (shred) à la sortie :
#      - un dossier y est copié ; un dossier .partiel (une sauvegarde en cours ou en échec) est
#        refusé (code 64) ;
#      - une archive .tar.age exige --cle (l'identité hors ligne, apportée pour l'occasion et jamais
#        gardée sur le serveur). Elle déchiffre l'archive, puis son couple. Un fichier ordinaire,
#        age le lit lui-même, à chaque fois, comme avant le lot 12 : une identité chiffrée par phrase
#        de passe demande alors la phrase deux fois. Autre chose, /dev/stdin (voir ci-dessus), ne se
#        lit qu'une fois : en mémoire, en base64 (octets nuls compris), hors de la trace de bash -x,
#        et jamais écrite. La clé elle-même, collée dans un argument quel qu'il soit, est refusée sans
#        être répétée (code 64).
#        L'archive vient d'un distant et la clé publique n'est pas secrète : n'importe qui peut
#        fabriquer une archive qui se déchiffre. Ses membres sont donc contrôlés avant toute
#        extraction : un seul dossier, veille-emploi-<horodatage>/, et rien à côté ; ni chemin absolu, ni
#        « .. », ni lien, rien que des fichiers et des dossiers ;
#      dans les deux cas, un instantané vide, ou qui contient autre chose que des fichiers et des
#      dossiers, est refusé. Le couple de l'instantané, s'il a été noté (M-0005, § 2), est dans le
#      fichier voisin de la source : <dossier>.couple, ou <archive sans .tar.age>.couple.age,
#      déchiffré avec la même clé dans le dossier temporaire ;
#   4. contrôle, comme le test de restauration : la commande VERIFIER de deploiement/projet.env, dans
#      un conteneur jetable, sur la copie. Rien n'est touché si elle ne rend pas 0. Puis le couple de
#      l'instantané : « couple de l'instantané : <image> <version> <commit> (couple déployé : …) »
#      s'il diffère de celui de deploye, rien si c'est le même, « couple de l'instantané inconnu »
#      sans fichier voisin (un instantané d'avant la v0.7.0, ou pris sans couple en service), et
#      « couple de l'instantané inconnu : <fichier> illisible (<raison>) » si ce fichier ne se lit
#      pas : un lien, jamais suivi, une autre clé (l'erreur d'age, dans cette ligne et nulle part
#      ailleurs), une autre forme. Le couple ne décide de rien : la restauration a lieu dans tous les
#      cas, sur l'image déployée ;
#   5. le reste d'une restauration interrompue ($VEILLE_EMPLOI_DONNEES.nouvelle, la copie de travail
#      qu'un SIGKILL ou un plantage de l'hôte laisse, hors de portée du trap) est retiré, puis
#      l'instantané y est copié, à côté des données, et le dossier
#      $VEILLE_EMPLOI_SAUVEGARDES/avant-restauration-<AAAAMMJJTHHMMSSZ>/ (0700) est créé : tout ce qui
#      peut échouer sans toucher à l'application échoue ici. Retirer plutôt que refuser : ce nom
#      n'est celui d'aucune donnée en service, et un refus bloquerait une reprise d'activité sur un
#      reste que l'opérateur ne peut pas évaluer. Si on ne peut pas le retirer, en revanche, on
#      refuse. Les copies jetables $VEILLE_EMPLOI_SAUVEGARDES/report-<horodatage>/ qu'un report tué
#      a laissées (étape 6 bis) sont retirées aussi ; une copie qui ne part pas est signalée, sans
#      arrêter la restauration : elle n'entre jamais dans les données. La sauvegarde de la nuit,
#      sous le même verrou, retire ces deux restes aussi (retirer_restes_de_restauration, lib.sh) ;
#   6. `dc stop app` ;
#   6 bis. le report, si deploiement/projet.env déclare REPORTER (« Le report », plus bas) ;
#   7. tout le contenu de $VEILLE_EMPLOI_DONNEES, fichiers cachés compris, est déplacé dans ce dossier,
#      jamais supprimé ; le dossier lui-même reste : c'est lui que le conteneur monte ;
#   8. le contenu de l'instantané prend sa place (des déplacements, sans copie) ; `dc start app` ;
#      santé sur 127.0.0.1:$VEILLE_EMPLOI_PORT : statut ok, la version et la révision déployées.
#
# Le report. Un projet qui garde dans ses données un état qu'une restauration ne doit pas défaire
# (M-0005, §6) déclare dans deploiement/projet.env la commande REPORTER de son image et, s'il le
# veut, REPORTER_SECTION : le titre de la section de docs/exploitation.md qui dit comment reporter
# à la main. Deux clés facultatives : sans REPORTER, la restauration est celle d'avant le crochet,
# à l'octet près ; déclarées mais illisibles, refus (code 1) avant tout effet. Avec REPORTER, à
# l'étape 6 bis, application arrêtée, données encore en place, et après le contrôle de l'étape 4,
# puisque le report change le contenu de l'instantané :
#   - les données en service sont copiées dans $VEILLE_EMPLOI_SAUVEGARDES/report-<AAAAMMJJTHHMMSSZ>/, en
#     0700 : des données personnelles, jamais dans le dossier temporaire. `<REPORTER…> /actuel
#     /donnees` tourne dans un conteneur jetable de l'image déployée, cette copie montée en
#     écriture sur /actuel (ce que la commande y écrit est jeté), $VEILLE_EMPLOI_DONNEES.nouvelle sur
#     /donnees (ce qu'elle y écrit est mis en place). $VEILLE_EMPLOI_DONNEES n'est jamais monté. La
#     copie jetable est retirée sur toutes les sorties, trap compris ;
#   - code 0 et un seul objet JSON sur la sortie standard, le rapport : il va au journal, sur une
#     ligne. jq le contrôle : sans jq, la restauration est refusée avant tout effet. Puis la copie
#     de l'instantané doit garder la forme que l'étape 3 exige (non vide, rien que des fichiers et
#     des dossiers), sans second VERIFIER : le report change légitimement son contenu. Tout autre
#     résultat, un code 64 (l'image ne connaît pas la commande), un autre code, une sortie qui
#     n'est pas un seul objet JSON ou une copie qui n'a plus cette forme, abandonne la
#     restauration : les deux sorties de la commande vont au journal, aplaties, le trap retire la
#     copie de l'instantané et
#     relance l'application sur les données en service, code 1. Rien n'a changé, et le message
#     propose --sans-report, puis la section ;
#   - avec --sans-report, ou si les données en service sont vides, pas de report. La fin de la
#     restauration le rappelle, avec la raison et la section : en cas de succès, comme en cas
#     d'échec après la mise en place (le redémarrage, la santé).
# Rien de la commande ne va sur la sortie standard du script. Sans REPORTER, --sans-report est
# ignorée.
#
# Si quelque chose échoue entre l'arrêt et la fin de la mise en place, un trap retire ce qui était
# entré de l'instantané, remet l'ancien contenu en place (s'il avait été déplacé) et relance
# l'application : la restauration n'a pas eu lieu. Si le trap n'y arrive pas, l'application reste
# arrêtée (relancée, elle démarrerait sur des données vides ou incomplètes, sous une santé que la
# sonde jugerait verte), code 1, et le message dit où est chaque chose, sans jamais faire supprimer
# l'ancien contenu :
#   - si l'instantané n'a pas pu ressortir des données, l'ancien contenu est entier dans
#     avant-restauration-*/, et ce qui reste dans les données n'est que des copies de l'instantané ;
#   - si l'ancien contenu n'a pu revenir qu'en partie, il est réparti entre les données et
#     avant-restauration-*/, et rien n'est à supprimer.
# Si c'est le redémarrage ou la santé qui échoue après la mise en place, l'instantané reste en place
# (rien n'est défait en douce) ; l'ancien contenu est dans avant-restauration-*/ (s'il y en avait
# un), et le message dit où.
#
# Les dossiers avant-restauration-* sont des copies en clair des données : sauvegarder.sh les efface
# après 30 jours, comme les autres copies locales.
#
# Codes de sortie : 0 ; 1 échec ; 3 secrets absents ; 64 usage, environnement refusé, ou --oui absent ;
# 129, 130, 143 interruption.
#
# Variables de test : VEILLE_EMPLOI_VERROU_ATTENTE, VEILLE_EMPLOI_SANTE_DELAI.
set -euo pipefail
# shellcheck source=deploiement/lib.sh
. "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

# Posées par main.
SOURCE=""
FORME="" # dossier ou archive
CLE=""
OUI=0
TMP=""
SOMMET="" # le dossier unique d'une archive, posé par verifier_membres
AVANT=""
ANCIEN=0 # 1 si les données courantes avaient un contenu, déplacé dans $AVANT
PHASE=rien # rien, arretee, deplacee (l'ancien contenu sort, puis l'instantané entre), installee, demarree
INSTALLATION=0 # 1 dès que le contenu de l'instantané a commencé d'entrer dans les données
NOUVELLE=""
ECHEC_RETABLIR="" # ce que retablir n'a pas pu faire : instantane (le ressortir) ou ancien (le remettre)
SANS_REPORT=0 # 1 avec --sans-report : l'opérateur renonce au report
REPORTER_MOTS=() # la commande REPORTER de deploiement/projet.env ; vide si le projet n'en déclare pas
REPORTER_SECTION="" # le titre de la section du runbook qui dit comment reporter à la main
REPORT="" # la copie jetable des données en service, tant qu'elle existe
REPORT_ABSENT="" # pourquoi le report, déclaré, n'a pas eu lieu : --sans-report, aucune donnée en service
IDENTITE_LUE=0 # 1 quand --cle n'est pas un fichier ordinaire, et que lire_identite l'a mise en mémoire
IDENTITE="" # alors, son contenu en base64 (lire_identite), effacé après l'étape 3
ERREUR_AGE="" # la première ligne de l'erreur d'age, posée par _dechiffrer_en_silence
COUPLE_VOISIN="" # le fichier voisin de la source qui porte son couple ; vide s'il n'y en a pas
COUPLE_LU="" # « <image> <version> <commit> » lu dans ce fichier ; vide s'il ne se lit pas
COUPLE_RAISON="" # pourquoi ce fichier ne se lit pas

USAGE="usage : bash deploiement/restaurer.sh prod <dossier|archive .tar.age> [--oui] [--cle <identité age>]
exemple, la clé hors ligne sur l'entrée standard, jamais écrite sur un disque ; sur le poste, dans
Git Bash, read -rs CLE (coller la clé, puis Entrée), puis :
  printf '%s\n' \"\$CLE\" | ssh <le serveur> 'bash ~/veille-emploi/deploiement/restaurer.sh prod <archive>.tar.age --oui --cle /dev/stdin'
  unset CLE"

ATTENDU="(attendu : un seul dossier veille-emploi-<horodatage>/, fait de fichiers et de dossiers)"

# retirer <dossier> : retire un dossier de travail, droits rendus d'abord (une copie peut avoir des
# sous-dossiers en lecture seule) ; un lien est retiré, jamais suivi.
retirer() {
  if [ -d "$1" ] && [ ! -L "$1" ]; then
    chmod -R u+rwX -- "$1" 2>/dev/null || true
  fi
  rm -rf -- "$1"
}

# detruire_tmp : le dossier temporaire a pu contenir du clair déchiffré.
# shellcheck disable=SC2317,SC2329  # appelée par sortie, elle-même sous trap
detruire_tmp() {
  [ -n "$TMP" ] || return 0
  chmod -R u+rwX -- "$TMP" 2>/dev/null || true
  find "$TMP" -type f -exec shred -u -n 1 -- {} + 2>/dev/null || true
  rm -rf -- "$TMP"
  TMP=""
}

# deplacer_contenu <de> <vers> : déplace chaque entrée de <de> (cachées comprises, dans l'ordre des
# noms) dans <vers>, sans jamais en écraser une : un nom déjà pris dans <vers> est un échec. Échec
# dès la première entrée qui ne passe pas, journalisé ; celles qui sont passées y restent.
deplacer_contenu() {
  local de="$1" vers="$2" entree nom
  { [ -d "$de" ] && [ -d "$vers" ]; } || {
    journal "déplacement de $de vers $vers impossible : dossier absent"
    return 1
  }
  while IFS= read -r -d '' entree; do
    nom="${entree##*/}"
    if [ -e "$vers/$nom" ] || [ -L "$vers/$nom" ]; then
      journal "$entree non déplacé : $vers/$nom existe déjà"
      return 1
    fi
    mv -T -- "$entree" "$vers/$nom" || {
      journal "$entree non déplacé vers $vers"
      return 1
    }
  done < <(find "$de" -mindepth 1 -maxdepth 1 -print0 | sort -z)
}

# retablir : la restauration a échoué après l'arrêt de l'application, l'ancien contenu sorti des
# données ou en train de l'être. Ce qui était entré de l'instantané repart dans la copie de travail
# (les données ne contenaient alors rien d'autre), puis l'ancien contenu revient. Succès si tout est
# revenu, ou s'il n'y avait rien à remettre ; échec dès qu'une entrée n'est pas revenue, ECHEC_RETABLIR
# disant laquelle des deux étapes n'a pas abouti.
# shellcheck disable=SC2317,SC2329  # appelée par sortie, elle-même sous trap
retablir() {
  if [ "$INSTALLATION" -eq 1 ] && ! deplacer_contenu "$VEILLE_EMPLOI_DONNEES" "$NOUVELLE"; then
    journal "instantané : son contenu n'a pas pu être retiré de $VEILLE_EMPLOI_DONNEES"
    ECHEC_RETABLIR=instantane
    return 1
  fi
  if ! deplacer_contenu "$AVANT" "$VEILLE_EMPLOI_DONNEES"; then
    journal "ancien contenu : non remis en place depuis $AVANT"
    ECHEC_RETABLIR=ancien
    return 1
  fi
  if [ "$ANCIEN" -eq 1 ]; then
    journal "ancien contenu remis en place"
  else
    journal "aucun ancien contenu à remettre en place"
  fi
}

# ancien_contenu : où est l'ancien contenu, pour les messages. Sans ancien contenu, le dossier
# avant-restauration-* est vide, et sortie le supprime : on ne l'annonce pas.
ancien_contenu() {
  if [ "$ANCIEN" -eq 1 ]; then
    printf "l'ancien contenu est dans %s" "$AVANT"
  else
    printf "aucun ancien contenu n'existait avant la restauration"
  fi
}

# conseil_de_retour : comment revenir à l'ancien contenu, s'il y en a un.
conseil_de_retour() {
  [ "$ANCIEN" -eq 1 ] || return 0
  printf " (pour revenir en arrière : arrêter l'application, remplacer le contenu de %s par celui de %s, la relancer)" \
    "$VEILLE_EMPLOI_DONNEES" "$AVANT"
}

# lire_reporter : REPORTER_MOTS et REPORTER_SECTION, depuis deploiement/projet.env (lu, jamais
# sourcé). Deux clés facultatives : absentes, rien n'est lu ni journalisé. Déclarées, le fichier
# entier est contrôlé, et un fichier illisible est refusé (code 1) avant tout effet.
lire_reporter() {
  lire_projet_env_facultatif REPORTER \
    || arreter 1 "REPORTER est déclaré, mais deploiement/projet.env est illisible : rien n'a changé"
  REPORTER_MOTS=("${PROJET_MOTS[@]}")
  if [ "${#REPORTER_MOTS[@]}" -eq 0 ]; then
    [ "$SANS_REPORT" -eq 0 ] || journal "--sans-report ignorée : deploiement/projet.env ne déclare pas REPORTER"
    return 0
  fi
  lire_projet_env_facultatif REPORTER_SECTION \
    || arreter 1 "REPORTER est déclaré, mais deploiement/projet.env est illisible : rien n'a changé"
  REPORTER_SECTION="${PROJET_MOTS[*]}"
}

# renvoi_report : où est la procédure du report à la main, dans le runbook du projet.
renvoi_report() {
  if [ -n "$REPORTER_SECTION" ]; then
    printf '« %s » (docs/exploitation.md)' "$REPORTER_SECTION"
  else
    printf 'docs/exploitation.md'
  fi
}

# conseil_report : l'issue quand le report ne peut pas avoir lieu.
conseil_report() {
  if [ -n "$REPORTER_SECTION" ]; then
    printf 'relancer avec --sans-report, puis « %s » (docs/exploitation.md)' "$REPORTER_SECTION"
  else
    printf 'relancer avec --sans-report, puis reporter à la main (docs/exploitation.md)'
  fi
}

# rappel_report : REPORTER déclaré, le report n'a pas eu lieu (--sans-report, ou aucune donnée en
# service) : ce qu'il aurait repris des données en service manque aux données restaurées, et on le
# dit. Appelée à la fin de la restauration, et par sortie quand elle échoue après la mise en place
# de l'instantané (le redémarrage, la santé) : l'erreur est alors au journal, et le rappel la suit.
rappel_report() {
  [ -n "$REPORT_ABSENT" ] || return 0
  journal "attention : le report n'a pas eu lieu ($REPORT_ABSENT) : ce que REPORTER reprend des données en service n'est pas dans les données restaurées ; voir $(renvoi_report)"
}

# lancer_reporter <image> <actuel> <donnees> : la commande REPORTER dans un conteneur jetable (--rm)
# de l'image, avec les options de $VEILLE_EMPLOI_OPTIONS_JETABLES : <actuel>, la copie jetable des
# données en service, monté en écriture sur /actuel ; <donnees>, la copie de l'instantané, sur
# /donnees : `<REPORTER…> /actuel /donnees`. Le contrat de l'image : 0 reporté, la sortie standard
# étant alors un seul objet JSON, le rapport ; 64 usage ; tout autre code est un échec. Rien de la
# commande ne va sur la sortie standard du script : le rapport va au journal, sur une ligne ; en
# échec, ses deux sorties aussi, aplaties (le projet garantit qu'elles ne portent aucune donnée
# personnelle, M-0005). Sa sortie d'erreur passe par un fichier du dossier temporaire du script.
# Rend 0 si le report est fait, 64 si l'image ne connaît pas la commande, 1 sinon, y compris sur
# un code 0 dont la sortie n'est pas un seul objet JSON.
lancer_reporter() {
  local image="$1" actuel="$2" donnees="$3" fichier="$TMP/report-erreurs" sortie="" erreurs="" sorties code=0
  sortie="$(docker run --rm "${VEILLE_EMPLOI_OPTIONS_JETABLES[@]}" -v "$actuel:/actuel" -v "$donnees:/donnees" \
    "$image" "${REPORTER_MOTS[@]}" /actuel /donnees 2>"$fichier")" || code=$?
  erreurs="$(cat -- "$fichier" 2>/dev/null)" || true
  rm -f -- "$fichier"
  erreurs="${erreurs//$'\n'/ }"
  sorties="${sortie//$'\n'/ }"
  sorties="sortie standard : ${sorties:-(vide)} ; sortie d'erreur : ${erreurs:-(vide)}"
  case "$code" in
    0)
      # Pas de `jq -e .` : jq 1.6 rend 0 sur une entrée vide (voir jq_vaut), et `.` admet un
      # nombre, une chaîne ou deux documents à la suite. `-s` les réunit en un tableau : le
      # rapport est un seul document, et c'est un objet.
      if [ -n "${sortie//[[:space:]]/}" ] \
        && printf '%s\n' "$sortie" | jq -e -s 'length == 1 and (.[0] | type == "object")' >/dev/null 2>&1; then
        journal "report fait (reporter : code 0) : ${sortie//$'\n'/ }"
        return 0
      fi
      journal "report en échec (reporter : code 0, mais la sortie n'est pas un rapport) ; $sorties"
      return 1
      ;;
    64)
      journal "report impossible (reporter : code 64) : usage refusé, l'image déployée ne connaît pas la commande REPORTER de projet.env ; $sorties"
      return 64
      ;;
    *)
      journal "report en échec (reporter : code $code) ; $sorties"
      return 1
      ;;
  esac
}

# faire_le_report <horodatage> : l'étape 6 bis, application arrêtée, données encore en place. Sans
# --sans-report, et si les données en service ne sont pas vides : leur copie jetable, puis
# lancer_reporter. Un échec reste en phase « arretee » : rien n'a été déplacé, et le trap retire la
# copie jetable et celle de l'instantané, puis relance l'application sur les données en service.
faire_le_report() {
  local copie="$VEILLE_EMPLOI_SAUVEGARDES/report-$1" code=0
  if [ "$SANS_REPORT" -eq 1 ]; then
    REPORT_ABSENT="--sans-report"
    journal "--sans-report : pas de report ; voir $(renvoi_report)"
    return 0
  fi
  if [ -z "$(find "$VEILLE_EMPLOI_DONNEES" -mindepth 1 -print -quit)" ]; then
    REPORT_ABSENT="aucune donnée en service"
    journal "aucune donnée en service : pas de report"
    return 0
  fi
  # REPORT n'est posé qu'une fois le dossier créé : un dossier qui existait déjà n'est pas le nôtre.
  mkdir -m 700 "$copie" \
    || arreter 1 "copie jetable $copie impossible à créer : la restauration est abandonnée, rien n'a changé. Si le report ne peut pas avoir lieu, $(conseil_report)"
  REPORT="$copie"
  cp -R -- "$VEILLE_EMPLOI_DONNEES/." "$REPORT/" \
    || arreter 1 "copie des données en service vers $REPORT impossible : la restauration est abandonnée, rien n'a changé. Si le report ne peut pas avoir lieu, $(conseil_report)"
  journal "report : ${REPORTER_MOTS[*]} /actuel /donnees, sur une copie jetable des données en service ($REPORT)"
  lancer_reporter "$DEPLOYE_IMAGE" "$REPORT" "$NOUVELLE" || code=$?
  case "$code" in
    0) ;;
    64) arreter 1 "report impossible : l'image déployée ne connaît pas la commande REPORTER (${REPORTER_MOTS[*]}) : la restauration est abandonnée, rien n'a changé : $(conseil_report)" ;;
    *) arreter 1 "report en échec : la restauration est abandonnée, rien n'a changé (le détail est dans le journal). Si le report ne peut pas avoir lieu, $(conseil_report)" ;;
  esac
  # La copie de l'instantané, après le report : la forme que l'étape 3 exige de l'instantané. Pas de
  # second VERIFIER : le report change légitimement son contenu.
  [ -n "$(find "$NOUVELLE" -mindepth 1 -print -quit)" ] \
    || arreter 1 "report : la copie de l'instantané est vide après le report : la restauration est abandonnée, rien n'a changé. Si le report ne peut pas avoir lieu, $(conseil_report)"
  [ -z "$(find "$NOUVELLE" -mindepth 1 ! -type f ! -type d -print -quit)" ] \
    || arreter 1 "report : la copie de l'instantané contient autre chose que des fichiers et des dossiers après le report (liens…) : la restauration est abandonnée, rien n'a changé. Si le report ne peut pas avoir lieu, $(conseil_report)"
  # Retirée dès qu'elle a servi ; sinon, sortie réessaie.
  if retirer "$REPORT"; then
    REPORT=""
  fi
}

# sortie : trap EXIT. Sur une sortie en erreur après l'arrêt de l'application, l'ancien contenu est
# remis en place s'il avait été déplacé, et l'application relancée. S'il n'a pas pu être remis en
# place, l'application reste arrêtée : relancée, elle démarrerait sur des données vides ou
# incomplètes, sous une santé que la sonde jugerait verte. Sur toutes les sorties, la copie jetable
# du report est retirée d'abord.
# shellcheck disable=SC2317,SC2329  # appelée par trap EXIT
sortie() {
  local code=$? relancer=1
  trap - EXIT INT TERM HUP
  # La copie jetable des données en service : des données personnelles. Un rm qui échoue ne doit
  # pas empêcher la suite (set -e).
  if [ -n "$REPORT" ]; then
    retirer "$REPORT" || journal "copie jetable $REPORT non retirée : une copie des données en clair, à retirer à la main"
  fi
  if [ "$code" -ne 0 ]; then
    if [ "$PHASE" = deplacee ] && ! retablir; then
      relancer=0
      # Jamais « vider » : l'ancien contenu peut être en partie revenu dans les données.
      case "$ECHEC_RETABLIR" in
        instantane)
          journal "intervention nécessaire : l'ancien contenu est entier dans $AVANT, mais des entrées de l'instantané sont restées dans $VEILLE_EMPLOI_DONNEES : ce sont des copies, la source ($SOURCE) est intacte. L'application reste arrêtée (relancée, elle démarrerait sur un instantané incomplet). Déplacer ces entrées de l'instantané hors de $VEILLE_EMPLOI_DONNEES, y remettre tout le contenu de $AVANT, puis lancer docker compose start app"
          ;;
        *)
          journal "intervention nécessaire : l'ancien contenu n'est pas entièrement revenu : il est dans $AVANT et, pour ce qui est déjà revenu, dans $VEILLE_EMPLOI_DONNEES, qui ne contient rien de l'instantané. Ne rien supprimer. L'application reste arrêtée (relancée, elle démarrerait sur des données incomplètes). Déplacer dans $VEILLE_EMPLOI_DONNEES ce qui reste dans $AVANT, puis lancer docker compose start app"
          ;;
      esac
    fi
    if [ "$relancer" -eq 1 ]; then
      case "$PHASE" in
        arretee | deplacee | installee)
          journal "relance de l'application"
          dc start app || journal "relance impossible : intervention nécessaire (docker compose start app)"
          ;;
      esac
    fi
    # La copie de travail : laissée, elle serait le reste d'une restauration interrompue. Un rm qui
    # échoue ne doit pas empêcher la destruction du clair, plus bas (set -e).
    if [ -n "$NOUVELLE" ] && { [ -e "$NOUVELLE" ] || [ -L "$NOUVELLE" ]; }; then
      retirer "$NOUVELLE" || journal "$NOUVELLE non retiré : à retirer avant la prochaine restauration"
    fi
    # L'instantané est en place : si le report n'a pas eu lieu, on le rappelle.
    case "$PHASE" in
      installee | demarree) rappel_report ;;
    esac
  fi
  # Un dossier vide ne reste pas (la copie échoue avant le déplacement, ou il n'y avait pas
  # d'ancien contenu) ; un dossier qui garde des entrées reste.
  [ -z "$AVANT" ] || rmdir "$AVANT" 2>/dev/null || true
  detruire_tmp
  exit "$code"
}

# afficher_plan : ce que --oui ferait, sur stdout. Aucun effet. Avec REPORTER, une étape de plus
# dit si le report jouera, et avec quelle commande ; sans, le plan est celui d'avant le crochet.
afficher_plan() {
  local forme="dossier d'instantané, copié dans un dossier temporaire détruit à la fin" report="" n=4
  [ "$FORME" != archive ] || forme="archive chiffrée, déchiffrée avec $CLE dans un dossier temporaire détruit à la fin"
  if [ "${#REPORTER_MOTS[@]}" -gt 0 ] && [ "$SANS_REPORT" -eq 1 ]; then
    report="  4. --sans-report : pas de report (REPORTER : ${REPORTER_MOTS[*]}) ; ce qu'il reprendrait des
     données en service manquera aux données restaurées : voir $(renvoi_report)
"
    n=5
  elif [ "${#REPORTER_MOTS[@]}" -gt 0 ]; then
    report="  4. report : ${REPORTER_MOTS[*]} /actuel /donnees, dans un conteneur jetable de l'image déployée ;
     /actuel est une copie jetable des données en service, /donnees la copie de l'instantané. Sans
     données en service, pas de report ; un échec abandonne la restauration, sauf avec --sans-report
"
    n=5
  fi
  cat <<PLAN
Restauration des données de prod (rien n'est fait sans --oui).

  source        : $SOURCE
  forme         : $forme
  données       : $VEILLE_EMPLOI_DONNEES (tout son contenu)
  gardées dans  : $VEILLE_EMPLOI_SAUVEGARDES/avant-restauration-<horodatage UTC>/

Étapes :
  1. verrou partagé avec la sonde et le déploiement (600 s d'attente au plus)
  2. contrôle de l'instantané par la commande VERIFIER de l'image déployée ; rien n'est touché s'il n'est pas conforme
  3. arrêt de l'application
${report}  $n. contenu courant des données mis de côté, contenu de l'instantané mis à sa place
  $((n + 1)). redémarrage, puis contrôle de la santé sur 127.0.0.1:$VEILLE_EMPLOI_PORT

Pour l'exécuter, relancer la même commande avec --oui.
PLAN
}

# verifier_membres <archive.tar> : les membres de l'archive, avant toute extraction : tous sous un
# seul dossier veille-emploi-<horodatage>/, sans chemin absolu ni « .. », et rien que des fichiers et des
# dossiers (ni lien symbolique ou physique, ni tube, ni périphérique). Pose SOMMET, le nom de ce
# dossier. Refus (code 1) sinon : rien n'a été extrait.
verifier_membres() {
  local archive="$1" noms types nom type premier i
  local motif='^veille-emploi-[0-9]{8}T[0-9]{6}Z$'
  local liste_noms=() liste_types=()
  SOMMET=""
  # tar échappe les caractères de contrôle des noms (\n…) : un membre par ligne, dans les deux listes.
  noms="$(tar -tf "$archive")" || arreter 1 "archive illisible : $SOURCE"
  types="$(tar -tvf "$archive" | cut -c1)" || arreter 1 "archive illisible : $SOURCE"
  [ -n "$noms" ] || arreter 1 "contenu inattendu dans $SOURCE : archive vide $ATTENDU"
  mapfile -t liste_noms <<<"$noms"
  mapfile -t liste_types <<<"$types"
  [ "${#liste_noms[@]}" -eq "${#liste_types[@]}" ] \
    || arreter 1 "archive illisible : $SOURCE (les deux listes de ses membres diffèrent)"
  for i in "${!liste_noms[@]}"; do
    nom="${liste_noms[i]}"
    type="${liste_types[i]}"
    case "$type" in
      - | d) ;;
      *) arreter 1 "contenu inattendu dans $SOURCE : $nom n'est ni un fichier ni un dossier (type $type : un lien, un tube…) $ATTENDU" ;;
    esac
    case "$nom" in
      /*) arreter 1 "contenu inattendu dans $SOURCE : chemin absolu $nom $ATTENDU" ;;
    esac
    case "/$nom/" in
      */../*) arreter 1 "contenu inattendu dans $SOURCE : $nom remonte d'un dossier (..) $ATTENDU" ;;
    esac
    premier="${nom%%/*}"
    [[ "$premier" =~ $motif ]] \
      || arreter 1 "contenu inattendu dans $SOURCE : $nom n'est pas dans un dossier veille-emploi-<horodatage> $ATTENDU"
    [ -z "$SOMMET" ] || [ "$premier" = "$SOMMET" ] \
      || arreter 1 "contenu inattendu dans $SOURCE : deux dossiers, $SOMMET et $premier $ATTENDU"
    SOMMET="$premier"
    if [ "$nom" = "$premier" ] || [ "$nom" = "$premier/" ]; then
      [ "$type" = d ] || arreter 1 "contenu inattendu dans $SOURCE : $premier n'est pas un dossier $ATTENDU"
    fi
  done
}

# lire_identite : un fichier ordinaire reste à age, qui le lit lui-même à chaque déchiffrement, ses
# octets tels quels (une identité chiffrée par phrase de passe, au format binaire, en a de nuls),
# comme avant le lot 12. Autre chose, /dev/stdin (un tube), ne se lit qu'une fois : IDENTITE ← son
# contenu, en base64, pour que ses octets passent intacts, nuls compris, et IDENTITE_LUE ← 1.
# Appelée par _sans_trace : sous bash -x, la clé ne paraît jamais dans la trace. Elle reste en
# mémoire, jamais sur un disque ni dans un argument.
# shellcheck disable=SC2317,SC2329  # appelée par _sans_trace
lire_identite() {
  [ ! -f "$CLE" ] || return 0
  IDENTITE="$(base64 -w0 -- "$CLE")" || return 1
  IDENTITE_LUE=1
}

# dechiffrer <entrée> <sortie> : `age -d`, avec --cle elle-même si c'est un fichier ordinaire, sinon
# avec l'identité que lire_identite a mise en mémoire, qu'age reçoit par un tube (une substitution
# de processus), jamais par un fichier. Appelée par _sans_trace, pour la même raison.
# shellcheck disable=SC2317,SC2329  # appelée par _sans_trace
dechiffrer() {
  if [ "$IDENTITE_LUE" -eq 1 ]; then
    age -d -i <(printf '%s' "$IDENTITE" | base64 -d) -o "$2" "$1"
  else
    age -d -i "$CLE" -o "$2" "$1"
  fi
}

# _dechiffrer_en_silence <entrée> <sortie> : dechiffrer, mais la première ligne de l'erreur d'age
# va dans ERREUR_AGE, jamais sur la sortie d'erreur : restaurer.sh la dit dans la ligne du couple.
# Appelée par _sans_trace : la trace de bash -x ne se mêle pas à l'erreur.
# shellcheck disable=SC2317,SC2329  # appelée par _sans_trace
_dechiffrer_en_silence() {
  local code=0
  ERREUR_AGE="$(dechiffrer "$1" "$2" 2>&1 >/dev/null)" || code=$?
  ERREUR_AGE="${ERREUR_AGE%%$'\n'*}"
  return "$code"
}

# preparer_archive : déchiffre l'archive, contrôle ses membres, puis l'extrait : $TMP/donnees est son
# dossier unique.
preparer_archive() {
  local archive="$TMP/archive.tar"
  mkdir -m 700 "$TMP/extrait"
  _sans_trace lire_identite \
    || arreter 1 "déchiffrement impossible : $SOURCE (identité : $CLE)"
  _sans_trace dechiffrer "$SOURCE" "$archive" \
    || arreter 1 "déchiffrement impossible : $SOURCE (identité : $CLE)"
  verifier_membres "$archive"
  tar -xf "$archive" -C "$TMP/extrait" --no-same-owner --no-same-permissions \
    || arreter 1 "extraction impossible : $SOURCE"
  rm -f -- "$archive"
  # Ce que tar a écrit : le seul dossier annoncé.
  { [ "$(find "$TMP/extrait" -mindepth 1 -maxdepth 1 | wc -l)" -eq 1 ] && [ -d "$TMP/extrait/$SOMMET" ] \
    && [ ! -L "$TMP/extrait/$SOMMET" ]; } \
    || arreter 1 "contenu inattendu dans $SOURCE : l'extraction n'a pas donné le seul dossier $SOMMET $ATTENDU"
  mv -- "$TMP/extrait/$SOMMET" "$TMP/donnees"
}

# preparer_dossier : copie le contenu du dossier dans $TMP/donnees.
preparer_dossier() {
  mkdir -m 700 "$TMP/donnees"
  cp -R -- "$SOURCE/." "$TMP/donnees/" || arreter 1 "copie de $SOURCE impossible : rien n'a changé"
}

# lire_couple_voisin : le couple de l'instantané, dans le fichier voisin de la source, que
# sauvegarder.sh et deployer.sh écrivent (noter_couple, lib.sh) : <dossier>.couple, en clair, ou
# <archive sans .tar.age>.couple.age, déchiffré avec l'identité de l'archive dans le dossier
# temporaire. COUPLE_VOISIN ← ce fichier s'il existe ; COUPLE_LU ← son couple s'il a la forme d'un
# fichier d'état (lire_version). Un lien, jamais suivi, autre chose qu'un fichier, un fichier qui ne
# se déchiffre pas ou qui n'a pas cette forme laissent COUPLE_LU vide, et COUPLE_RAISON dit
# pourquoi (l'erreur d'age comprise, qui ne sort pas ailleurs). Rien ici n'arrête la restauration,
# ni ne journalise : dire_le_couple le dit, après le contrôle.
lire_couple_voisin() {
  local voisin clair
  if [ "$FORME" = archive ]; then
    voisin="${SOURCE%.tar.age}.couple.age"
    clair="$TMP/couple"
  else
    voisin="${SOURCE%/}.couple"
    clair="$voisin"
  fi
  [ -e "$voisin" ] || [ -L "$voisin" ] || return 0
  COUPLE_VOISIN="$voisin"
  if [ -L "$voisin" ]; then
    COUPLE_RAISON="un lien, qui n'est jamais suivi"
    return 0
  fi
  if [ ! -f "$voisin" ]; then
    COUPLE_RAISON="pas un fichier"
    return 0
  fi
  if [ "$FORME" = archive ] && ! _sans_trace _dechiffrer_en_silence "$voisin" "$clair"; then
    COUPLE_RAISON="déchiffrement impossible : ${ERREUR_AGE:-age, sans message}"
    return 0
  fi
  if lire_version "$clair"; then
    COUPLE_LU="$IMAGE_LUE $VERSION_LUE $COMMIT_LU"
  else
    COUPLE_RAISON="attendu : « <image> <version> <commit> »"
  fi
}

# dire_le_couple : le couple de l'instantané, au journal, face au couple déployé (lire_deploye).
# Rien quand c'est le même : la restauration se fait sur l'image qui l'a écrit.
dire_le_couple() {
  local deploye="$DEPLOYE_IMAGE $DEPLOYE_VERSION $DEPLOYE_COMMIT"
  if [ -z "$COUPLE_VOISIN" ]; then
    journal "couple de l'instantané inconnu"
  elif [ -z "$COUPLE_LU" ]; then
    journal "couple de l'instantané inconnu : $COUPLE_VOISIN illisible ($COUPLE_RAISON)"
  elif [ "$COUPLE_LU" != "$deploye" ]; then
    journal "couple de l'instantané : $COUPLE_LU (couple déployé : $deploye)"
  fi
}

main() {
  # Une clé age collée dans un argument (à la place de l'environnement, de la source, du chemin de
  # l'identité, ou dans --cle=…), même après des lignes de commentaire, n'est jamais répétée : refus
  # avant tout message qui pourrait citer un argument, plan compris.
  local argument
  for argument in "$@"; do
    case "$argument" in
      *AGE-SECRET-KEY-*) arreter 64 "un argument contient une clé privée age, qui n'est pas répétée : rien n'a changé. --cle attend un chemin vers un fichier d'identité, pas la clé elle-même (par exemple --cle /dev/stdin, la clé sur l'entrée standard)" ;;
    esac
  done
  [ "$#" -ge 1 ] || arreter 64 "$USAGE"
  reserver_a_prod "$1" restaurer.sh
  shift
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --oui)
        OUI=1
        shift
        ;;
      --cle)
        [ "$#" -ge 2 ] || arreter 64 "--cle demande un fichier (l'identité age). $USAGE"
        CLE="$2"
        shift 2
        ;;
      --sans-report)
        SANS_REPORT=1
        shift
        ;;
      -*) arreter 64 "option inconnue : $1. $USAGE" ;;
      *)
        [ -z "$SOURCE" ] || arreter 64 "une seule source attendue. $USAGE"
        SOURCE="$1"
        shift
        ;;
    esac
  done
  [ -n "$SOURCE" ] || arreter 64 "$USAGE"
  if [ -d "$SOURCE" ]; then
    FORME=dossier
    case "${SOURCE%/}" in
      *.partiel) arreter 64 "$SOURCE est un instantané partiel (.partiel : une sauvegarde en cours ou en échec), qui ne se restaure pas" ;;
    esac
  elif [[ "$SOURCE" == *.tar.age ]]; then
    FORME=archive
    [ -f "$SOURCE" ] || arreter 64 "archive introuvable : $SOURCE"
  elif [ -e "$SOURCE" ]; then
    arreter 64 "forme inconnue : '$SOURCE' (attendu : un dossier d'instantané, ou une archive .tar.age)"
  else
    arreter 64 "source introuvable : '$SOURCE' (attendu : un dossier d'instantané, ou une archive .tar.age)"
  fi
  if [ "$FORME" = archive ]; then
    [ -n "$CLE" ] || arreter 64 "une archive .tar.age exige --cle <identité age> (la clé hors ligne, apportée pour l'occasion)"
    # -r et non -f : /dev/stdin (un tube) ou tout autre chemin lisible, jamais un dossier. Le test ne
    # lit rien : une identité sur l'entrée standard n'est consommée qu'à l'étape 3, une seule fois
    # (lire_identite) ; un fichier ordinaire, age le relit lui-même.
    { [ -r "$CLE" ] && [ ! -d "$CLE" ]; } || arreter 64 "identité age introuvable ou illisible : $CLE"
  elif [ -n "$CLE" ]; then
    journal "--cle ignorée : elle ne sert qu'aux archives .tar.age"
  fi

  charger_env prod
  lire_reporter
  if [ "$OUI" -ne 1 ]; then
    afficher_plan
    return 64
  fi

  charger_secrets prod
  trap sortie EXIT
  trap 'exit 130' INT
  trap 'exit 143' TERM
  trap 'exit 129' HUP
  refuser_image_heritee
  # Le rapport du report se contrôle par jq : sans lui, refus avant tout effet.
  if [ "${#REPORTER_MOTS[@]}" -gt 0 ] && [ "$SANS_REPORT" -eq 0 ] && ! command -v jq >/dev/null 2>&1; then
    arreter 1 "jq introuvable : le rapport du crochet ne peut pas être contrôlé. Rien n'a changé : installer jq, qui vient avec les outils du serveur (outils/installer-outils.sh du dépôt serveur), puis relancer"
  fi

  local etat="$VEILLE_EMPLOI_ETAT" donnees="$VEILLE_EMPLOI_DONNEES" revision nombre fichiers horodatage code=0

  # 1. Verrou, gardé jusqu'à la fin du script.
  prendre_verrou \
    || arreter 1 "verrou $etat/verrou toujours pris après ${VEILLE_EMPLOI_VERROU_ATTENTE:-600} s : restauration abandonnée, rien n'a changé"

  # 2. Image en service.
  lire_deploye \
    || arreter 1 "restauration impossible sans version déployée : déployer d'abord (deployer.sh), puis restaurer"
  [ -f "$etat/compose.env" ] \
    || arreter 1 "compose.env absent ($etat) : déployer d'abord (deployer.sh), puis restaurer"
  journal "restauration de prod depuis $SOURCE (image $DEPLOYE_IMAGE, version $DEPLOYE_VERSION)"

  # 3. L'instantané, dans un dossier temporaire privé.
  TMP="$(umask 077 && mktemp -d "${TMPDIR:-/tmp}/veille-emploi-restauration.XXXXXX")" \
    || arreter 1 "dossier temporaire impossible dans ${TMPDIR:-/tmp}"
  if [ "$FORME" = archive ]; then
    preparer_archive
  else
    preparer_dossier
  fi
  lire_couple_voisin
  IDENTITE="" IDENTITE_LUE=0
  [ -n "$(find "$TMP/donnees" -mindepth 1 -print -quit)" ] \
    || arreter 1 "instantané vide : $SOURCE : rien n'a changé"
  [ -z "$(find "$TMP/donnees" -mindepth 1 ! -type f ! -type d -print -quit)" ] \
    || arreter 1 "contenu inattendu dans $SOURCE : des entrées ne sont ni des fichiers ni des dossiers (liens…) : rien n'a changé"
  nombre="$(find "$TMP/donnees" -type f | wc -l)"
  fichiers="$nombre fichier"
  [ "$nombre" -le 1 ] || fichiers="${fichiers}s"

  # 4. Contrôle par la commande VERIFIER de l'image.
  verifier_copie "$DEPLOYE_IMAGE" "$TMP/donnees" || code=$?
  case "$code" in
    0) ;;
    2) arreter 1 "$SOURCE non conforme : rien n'a changé (le détail est dans le journal)" ;;
    *) arreter 1 "vérification de $SOURCE impossible : rien n'a changé (le détail est dans le journal)" ;;
  esac
  journal "instantané conforme : $SOURCE ($fichiers)"
  dire_le_couple

  # 5. Tout ce qui peut échouer sans toucher à l'application. L'horodatage est aussi celui de la
  # copie jetable du report (6 bis).
  horodatage="$(date -u +%Y%m%dT%H%M%SZ)"
  AVANT="$VEILLE_EMPLOI_SAUVEGARDES/avant-restauration-$horodatage"
  mkdir -m 700 "$AVANT" || arreter 1 "dossier $AVANT impossible à créer : rien n'a changé"
  NOUVELLE="$donnees.nouvelle"
  # Le reste d'une restauration interrompue (un déplacement tué par SIGKILL ou un plantage de
  # l'hôte, hors de portée du trap) : rien de lui ne doit entrer dans les données. On le retire ici,
  # application encore en service, avant la copie de l'instantané : la copie de travail et les
  # copies jetables du report, par lib.sh, puis ce qu'il en resterait (un lien, ou une copie de
  # travail qui n'a pas pu partir), qui est refusé. Une copie jetable qui ne part pas n'entre jamais
  # dans les données : elle est journalisée, sans arrêter la restauration.
  retirer_restes_de_restauration || true
  if [ -e "$NOUVELLE" ] || [ -L "$NOUVELLE" ]; then
    retirer "$NOUVELLE" \
      || arreter 1 "reste d'une restauration interrompue ($NOUVELLE) impossible à retirer : rien n'a changé, l'application n'a pas été arrêtée"
    journal "reste d'une restauration interrompue retiré : $NOUVELLE"
  fi
  cp -R -- "$TMP/donnees" "$NOUVELLE" \
    || arreter 1 "copie vers $NOUVELLE impossible : rien n'a changé, l'application n'a pas été arrêtée"

  # 6. Arrêt. La phase est posée avant : un arrêt à moitié raté doit aussi être suivi d'une relance.
  PHASE=arretee
  journal "arrêt de l'application"
  dc stop app || arreter 1 "arrêt de l'application impossible (docker compose stop : code $?)"

  # 6 bis. Le report, si le projet en déclare un, avant que rien ne soit déplacé.
  if [ "${#REPORTER_MOTS[@]}" -gt 0 ]; then
    faire_le_report "$horodatage"
  fi

  # 7. L'ancien contenu, entier, est gardé.
  if [ -n "$(find "$donnees" -mindepth 1 -print -quit)" ]; then
    ANCIEN=1
  fi
  PHASE=deplacee
  deplacer_contenu "$donnees" "$AVANT" \
    || arreter 1 "mise de côté du contenu courant de $donnees impossible"
  if [ "$ANCIEN" -eq 1 ]; then
    journal "ancien contenu gardé dans $AVANT"
  else
    journal "aucun ancien contenu à garder"
  fi
  [ -z "$(find "$donnees" -mindepth 1 -print -quit)" ] \
    || arreter 1 "$donnees n'est pas vide après la mise de côté : l'instantané n'est pas mis en place"

  # 8. Mise en place, redémarrage, santé.
  INSTALLATION=1
  deplacer_contenu "$NOUVELLE" "$donnees" \
    || arreter 1 "mise en place de l'instantané impossible"
  PHASE=installee
  rmdir -- "$NOUVELLE" || journal "$NOUVELLE non retiré : à retirer avant la prochaine restauration"
  NOUVELLE=""
  journal "démarrage de l'application"
  dc start app \
    || arreter 1 "redémarrage de l'application impossible (docker compose start app : code $?) : l'instantané est en place, $(ancien_contenu)"
  PHASE=demarree
  revision="$(revision_de "$DEPLOYE_IMAGE")" \
    || arreter 1 "révision de l'image $DEPLOYE_IMAGE illisible : l'instantané est en place, $(ancien_contenu)"
  # shellcheck disable=SC2016  # $version et $revision sont des variables de jq (--arg)
  attendre_sante "$VEILLE_EMPLOI_PORT" '.statut == "ok" and .version == $version and .revision == $revision' \
    --arg version "$DEPLOYE_VERSION" --arg revision "$revision" \
    || arreter 1 "santé non conforme après la restauration : l'instantané est en place, $(ancien_contenu)$(conseil_de_retour)"

  journal "restauration terminée : $SOURCE ; $(ancien_contenu)"
  rappel_report
  return 0
}

# Tout le corps est dans main, appelée sur la dernière ligne : bash a lu tout le fichier avant
# qu'un `git checkout` ne le remplace.
main "$@"; exit $?

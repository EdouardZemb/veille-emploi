#!/usr/bin/env bash
# Déploie un couple d'veille-emploi, une image et un commit de données, contrôle sa santé, et revient au
# couple précédent s'il échoue.
#
#   bash deploiement/deployer.sh <prod|staging> <image@sha256:…> <version> [--commit-donnees <sha>] [--donnees-neuves]
#   bash deploiement/deployer.sh <prod|staging> --retour
#
# <version> est celle que /sante doit annoncer : `main` en staging, X.Y.Z (sans « v ») en
# prod. Lancé par sonder.sh avec VEILLE_EMPLOI_VERROU_TENU=1 (la sonde tient déjà le verrou), ou à la
# main pour un déploiement ou un retour arrière : il prend alors le verrou lui-même. Toujours par
# `bash`, depuis le clone de l'environnement : un projet né sous Windows enregistre les scripts sans
# bit d'exécution.
#
# Le couple (M-0004 et M-0006 § 5, amendés). <sha> est le commit de données : un commit du clone des
# données de l'environnement ($VEILLE_EMPLOI_CLONE_DONNEES, lib.sh), 40 caractères hexadécimaux, dont la
# configuration et le contenu se montent sur /config et /contenu. Il va avec les commandes
# VERIFIER_CONFIG et VERIFIER_CONTENU de deploiement/projet.env : un projet qui en déclare une exige
# --commit-donnees, un projet qui n'en déclare aucune la refuse, et le commit de son couple vaut
# « - » : rien n'est vérifié ni monté, et le champ configuration de la santé n'est pas lu, comme
# avant le couple. Un commit que le clone des données n'a pas est refusé. Ces trois refus : code 64,
# rien de touché.
#
# Déroulé :
#   1. verrou $VEILLE_EMPLOI_ETAT/verrou, partagé avec la sonde et la sauvegarde (600 s d'attente au
#      plus), sauf si VEILLE_EMPLOI_VERROU_TENU=1 ;
#   1 bis. la garde du dossier de données, si une version est déployée ($VEILLE_EMPLOI_ETAT/deploye) : un
#      déploiement ou un retour arrière est refusé, code 1 signalé et rien de changé, quand
#      $VEILLE_EMPLOI_DONNEES n'est plus le dossier de la version déployée (« changé »), sinon quand
#      il est vide (fichiers cachés compris ; un dossier de données qui est un lien est suivi, comme
#      Docker le suit au montage). « Changé » passe d'abord : une autre racine, que charger_env
#      vient de créer vide, est dite changée, et le journal donne les deux chemins. La référence est
#      le chemin canonique que le dernier succès a écrit dans $VEILLE_EMPLOI_ETAT/donnees : même
#      dossier si `realpath` donne aujourd'hui exactement ce chemin, qui n'est jamais résolu de
#      nouveau (un lien repointé est vu). Sans ce fichier (un état d'avant la v0.5.0 du modèle),
#      c'est la valeur de VEILLE_EMPLOI_DONNEES dans le compose.env de la version déployée (celui dont
#      VEILLE_EMPLOI_IMAGE est l'image de deploye) : même chaîne, ou même chemin réel quand les deux
#      dossiers existent ; un ancien dossier disparu compte comme changé. Sans l'un ni l'autre, seul
#      le vide est contrôlé, et le journal le dit. `--donnees-neuves` (déploiement seulement, à la
#      main) lève les deux contrôles pour ce déploiement, et le journal le dit, même au premier ;
#   1 ter. les données du couple visé, s'il a un commit de données : la règle des paires
#      (controler_paires, lib.sh), l'instantané en lecture seule du commit,
#      $VEILLE_EMPLOI_ETAT/instantanes/<sha> (preparer_instantane ; jamais config/ en staging), puis les
#      commandes déclarées, dans un conteneur jetable de l'image visée, sur cet instantané :
#      VERIFIER_CONFIG hors staging, et VERIFIER_CONTENU avec, sur /en-service, le contenu de
#      l'instantané du couple en service, s'il en a un, refait d'abord s'il manque
#      (verifier_instantane). Une règle des paires en défaut, un instantané impossible (celui du
#      couple en service compris) ou une vérification qui n'a pas eu lieu : code 1 signalé,
#      rien de changé, rien de marqué en échec, et la sonde réessaiera. Des données non conformes
#      (code 2) : echec ← "<image> <sha>", code 1 signalé, et rien d'autre ne change : le
#      conteneur en service n'est pas touché ;
#   2. si l'application tourne, et si la version en service monte /sauvegardes (son compose.env
#      déclare VEILLE_EMPLOI_SAUVEGARDES ; sinon, les sauvegardes viennent d'être activées : pas
#      d'instantané, et le journal le dit), instantané de ses données dans le dossier
#      /sauvegardes/pre-deploiement/<AAAAMMJJTHHMMSSZ>, qui a la forme de /donnees, par la commande
#      SAUVEGARDER de deploiement/projet.env (pre-deploiement/ est d'abord créé sur l'hôte s'il
#      manque, car la commande crée son dossier, pas ses parents, puis ramené à 700 avec le dossier
#      des sauvegardes) ; elle l'écrit sous un nom provisoire, <AAAAMMJJTHHMMSSZ>.partiel, que le
#      dossier ne quitte qu'après le code 0 ; si elle ne rend pas 0, on s'arrête là, et le dossier
#      garde ce nom, pour le diagnostic, jusqu'à la tentative suivante, qui retire les .partiel
#      avant d'écrire : il n'en reste qu'un, le dernier. Après le renommage, le couple que le
#      déploiement quitte, celui de deploye, est noté à côté de l'instantané, jamais dedans :
#      <AAAAMMJJTHHMMSSZ>.couple (noter_couple, lib.sh ; M-0005, § 3), rien sans deploye.
#      Puis pre-deploiement/ est purgé des instantanés de plus de 30 jours, d'après leur nom, chacun
#      avec son .couple ; un couple qui ne se note pas, une purge ou un retrait en échec n'arrêtent
#      rien ;
#   3. nouveau compose.env ; l'ancien devient compose.env.precedent s'il décrit bien le couple
#      déployé, son image et les montages de son commit (un déploiement interrompu, ou un premier
#      déploiement en échec, ne devient pas la cible du retour arrière). Il porte l'image, la
#      version et les variables de l'env de
#      l'environnement (env/<env>.env du clone des données) que le compose exige, dont
#      VEILLE_EMPLOI_URL_PUBLIQUE ; avec un commit de données, VEILLE_EMPLOI_CONFIG=<instantané>/config
#      (hors staging, si VERIFIER_CONFIG est déclarée) et VEILLE_EMPLOI_CONTENU=<instantané>/contenu (si
#      VERIFIER_CONTENU l'est), que `dc` monte en lecture seule (compose.config.yml,
#      compose.contenu.yml) ;
#   4. `docker compose up -d --wait --remove-orphans` (un conteneur dont aucun des deux fichiers
#      compose ne déclare plus le service est retiré) ; avec un commit de données, les montages du
#      conteneur app (`docker container inspect`) : sur /config et /contenu, l'instantané visé en
#      lecture seule s'il les monte, rien sinon (jamais /config en staging), les chemins sous leur
#      forme canonique, sans résoudre les liens ; puis santé sur
#      127.0.0.1 : statut ok, la version attendue, la révision du label
#      org.opencontainers.image.revision de l'image et, avec un commit de données et
#      VERIFIER_CONFIG déclarée, le champ configuration : exemple en staging, montee en prod ;
#   5. succès : deploye ← "<image> <version> <commit>" (l'ancien dans precedent), donnees ← le chemin
#      canonique du dossier de données, echec effacé, signal ok ;
#   6. échec : echec ← "<image> <commit>" d'abord (la sonde ne retentera pas ce couple, même si la
#      suite est coupée), puis retour à compose.env.precedent, contrôlé comme à l'aller : ses
#      montages (ceux de compose.env.precedent, sauf si ni lui ni le couple en échec n'ont de commit
#      de données), puis sa santé (statut, version, révision et, aux conditions de l'aller, le champ
#      configuration : montee s'il monte /config, exemple en staging s'il a un commit de données et
#      que VERIFIER_CONFIG est déclarée) ; sans version précédente (premier déploiement), la version
#      en échec est arrêtée. Signal /fail ;
#   7. succès seulement (un déploiement ou un retour arrière réussi), après le signal ok :
#      nettoyer-images.sh, sous le même verrou (VEILLE_EMPLOI_VERROU_TENU=1 : il ne l'attend pas), qui
#      fait le ménage des images, puis celui des instantanés de $VEILLE_EMPLOI_ETAT/instantanes/. Son
#      échec, ou une surprise du ménage des instantanés, est journalisé et ne change pas le
#      résultat.
#
# L'étape 2 n'a rien changé quand elle échoue. Un instantané impossible ne marque pas la version en
# échec : la sonde réessaiera, et alertera, à chaque passage.
#
# Retour arrière manuel (`--retour`) : revient au couple de `precedent`, son image, sa version et son
# commit de données, par le même déroulé, vérification des données comprise, et le même contrôle de
# santé qu'un déploiement. Un couple précédent sans commit (« - ») ne monte rien et ne lit pas le
# champ configuration, même si projet.env déclare une commande : c'est celui d'une version d'avant
# ses données. Ce que le retour change :
#   - Refus, code 64 et rien de touché : pas de couple en service (deploye), pas de couple précédent
#     (precedent absent ou illisible), précédent identique au couple en service, ou commit de
#     données de precedent que projet.env ou le clone des données refusent (voir « Le couple »).
#   - Le couple quitté (deploye) est écrit dans `echec` juste avant le premier changement d'état
#     (après l'instantané, avant compose.env), et reste dans `echec` quoi qu'il arrive : jamais
#     effacé. Sans cela la sonde, qui vise la plus haute étiquette (ou :main), le redéploierait au
#     passage suivant. Elle attend alors en silence un nouveau couple.
#     Seul ce couple attend, et la sonde déploie tout couple neuf : avec une commande de l'instance,
#     changer une moitié de sa cible ramène l'autre moitié du couple quitté. Le journal dit
#     laquelle, selon ce que le retour change, et ce qui passe d'abord (avertir_apres_retour) : si
#     seule l'image change, en prod une vX.Y.Z plus haute que la version quittée, sur le commit de
#     la version gardée (en staging, le correctif du code) ; si seul le commit de données change,
#     une étiquette de données sur un commit corrigé (en staging, la branche des données corrigée) ;
#     si les deux changent, la moitié en cause.
#   - Succès : deploye ← le précédent, `precedent` supprimé (un second --retour ne rebascule pas
#     vers le couple en échec ; le prochain déploiement le recrée), signal ok « retour à <v>
#     effectué (depuis <v>) ».
#   - Santé du précédent non conforme : comme pour tout déploiement raté, le couple quitté est remis
#     en service (compose.env.precedent, que l'étape 3 vient de remplir avec lui), signal /fail
#     « échec du retour à <v>, <v quittée> remise en service ». deploye, precedent (pour une
#     nouvelle tentative, la cause réglée) et echec ne changent pas. Le couple quitté, toujours en
#     service et marqué en échec, n'envoie plus de signal ok (voir sonder.sh) ; la sonde alerte s'il
#     ne répond pas non plus.
#
# État, dans $VEILLE_EMPLOI_ETAT (chaque fichier est remplacé d'un coup, jamais écrit à moitié) :
#   compose.env             variables du compose en service, lues par `dc`
#   compose.env.precedent   celui du dernier couple déployé avant celui-ci : cible du retour
#   deploye                 "<image@sha256:…> <version> <commit>" du couple en service ; <commit> est le
#                           commit de données, ou « - » sans données montées
#   precedent               le contenu précédent de deploye
#   echec                   "<image@sha256:…> <commit>" du dernier couple en échec
#   instantanes/<commit>/   l'instantané des données de ce commit, en lecture seule (lib.sh)
#   donnees                 le chemin canonique (`realpath`) du dossier de données, écrit à chaque
#                           succès, déploiement ou retour arrière, jamais par un refus ni un
#                           échec : la référence de la garde (étape 1 bis)
# Un fichier d'avant la v0.7.0, sans le commit, se lit comme un couple en « - », et les scripts
# d'avant la v0.7.0 ne lisent que les premiers champs d'un fichier de la v0.7.0 (`read -r a b _`).
#
# Codes de sortie : 0 déployé ; 1 échec (signalé, y compris le refus de la garde du dossier de
# données et des données du couple en défaut ; non signalé avant toute action :
# VEILLE_EMPLOI_IMAGE, VEILLE_EMPLOI_VERSION, VEILLE_EMPLOI_CONFIG ou VEILLE_EMPLOI_CONTENU posée dans
# l'environnement, VEILLE_EMPLOI_URL_PUBLIQUE invalide ou absente de env/<env>.env du clone des données,
# deploiement/projet.env illisible, verrou toujours pris après 600 s) ; 3 secrets absents ; 64 usage
# (commit de données absent, de trop, invalide ou introuvable compris), ou retour arrière impossible.
#
# Variable de test : VEILLE_EMPLOI_SANTE_DELAI, secondes entre deux essais de santé (défaut 3).
set -euo pipefail
# shellcheck source=deploiement/lib.sh
. "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

# Posées par main.
NOM_ENV=""
REFERENCE=""
VERSION=""
COMMIT_DONNEES="-" # le commit de données du couple visé, ou « - » : aucune donnée montée
OPTION_COMMIT=0    # 1 avec --commit-donnees
RETOUR=0           # 1 pour --retour
COUPLE_EN_ECHEC="" # "<image> <commit>" que echec nomme si le lancement échoue : le couple visé, ou en retour le couple quitté
VERSION_QUITTEE="" # en retour : la version en service avant le retour
DONNEES_NEUVES=0   # 1 avec --donnees-neuves : la garde du dossier de données est levée
# Posées par preparer_couple et verifier_donnees, d'après le couple visé et deploiement/projet.env.
INSTANTANE_VISE=""        # l'instantané des données du couple visé ; vide sans commit de données
MONTER_CONFIG=0           # 1 : compose.env monte la configuration sur /config (jamais en staging)
MONTER_CONTENU=0          # 1 : compose.env monte le contenu sur /contenu
CONFIGURATION_ATTENDUE="" # le champ configuration que la santé doit dire, exemple ou montee ; vide : non lu
COMMIT_PRECEDENT=""       # le commit du couple que l'étape 3 copie dans compose.env.precedent ; vide : inconnu

# Ce qui s'écrit dans compose.env : une seule ligne chacune, sans surprise. L'image et la version
# suivent MOTIF_REFERENCE et MOTIF_VERSION, définis dans lib.sh : ceux que lire_version et le ménage
# des images exigent en relisant l'état. L'origine du site, sans chemin ni requête : la forme que
# l'application accepte, en plus strict (hôte en minuscules, sans identifiants).
MOTIF_URL_PUBLIQUE='^https?://[a-z0-9.-]+(:[0-9]+)?$'

# ecrire_atomique <fichier> <ligne…> : remplace le fichier d'un coup (fichier temporaire, puis mv).
ecrire_atomique() {
  local fichier="$1"
  shift
  printf '%s\n' "$@" >"$fichier.tmp"
  mv -f -- "$fichier.tmp" "$fichier"
}

# copier_atomique <source> <destination>
copier_atomique() {
  cp -- "$1" "$2.tmp"
  mv -f -- "$2.tmp" "$2"
}

# signaler_sonde ok|echec <message> : le signal n'est qu'un plus. S'il ne part pas, signaler l'a
# journalisé, et le silence alertera de lui-même : le résultat du déploiement ne change pas.
signaler_sonde() {
  signaler HC_SONDE "$@" || true
}

# menage_des_images : retire les images du projet qui ne servent plus, puis les instantanés des
# données que rien ne garde (nettoyer-images.sh), sous le verrou que ce script tient déjà. Le
# déploiement est fini et réussi : le ménage ne le remet pas en cause, et ne rend jamais autre chose
# que 0.
menage_des_images() {
  local code=0
  VEILLE_EMPLOI_VERROU_TENU=1 bash "$VEILLE_EMPLOI_CLONE/deploiement/nettoyer-images.sh" "$NOM_ENV" || code=$?
  if [ "$code" -ne 0 ]; then
    journal "ménage des images en échec (code $code) : le déploiement reste réussi"
  fi
  return 0
}

# lancer : `up` du compose.env courant. Les secrets dont compose.projet.yml a besoin viennent de
# l'environnement (charger_secrets), jamais d'un argument ni d'un fichier. --remove-orphans retire
# les conteneurs du projet dont aucun des deux fichiers compose ne déclare plus le service.
lancer() {
  dc up -d --wait --wait-timeout 120 --remove-orphans
}

# sante_conforme <version> <révision> [<configuration>] : sante_locale (lib.sh), 10 essais, à
# VEILLE_EMPLOI_SANTE_DELAI secondes d'écart ; avec un troisième argument, le champ configuration aussi.
sante_conforme() {
  local version="$1" revision="$2" delai="${VEILLE_EMPLOI_SANTE_DELAI:-3}" essai reponse="" attendu
  attendu="statut ok, version $version, révision $revision${3:+, configuration $3}"
  for essai in 1 2 3 4 5 6 7 8 9 10; do
    if reponse="$(sante_locale "$@")"; then
      journal "santé conforme (essai $essai) : version $version, révision $revision${3:+, configuration $3}"
      return 0
    fi
    [ "$essai" -eq 10 ] || sleep "$delai"
  done
  journal "santé non conforme après 10 essais (attendu : $attendu) ; dernière réponse : ${reponse//$'\n'/ }"
  return 1
}

# preparer_couple : d'après le commit du couple visé et deploiement/projet.env (DECLARE_CONFIG et
# DECLARE_CONTENU, de donnees_declarees), ce que compose.env monte et ce que la santé doit dire. Sans
# commit de données (« - »), rien n'est monté et le champ configuration n'est pas lu. Le staging ne
# monte jamais /config : sa santé doit dire exemple.
preparer_couple() {
  MONTER_CONFIG=0 MONTER_CONTENU=0 CONFIGURATION_ATTENDUE=""
  [ "$COMMIT_DONNEES" != - ] || return 0
  if [ "$DECLARE_CONFIG" -eq 1 ]; then
    if [ "$NOM_ENV" = prod ]; then
      MONTER_CONFIG=1
      CONFIGURATION_ATTENDUE=montee
    else
      CONFIGURATION_ATTENDUE=exemple
    fi
  fi
  [ "$DECLARE_CONTENU" -eq 0 ] || MONTER_CONTENU=1
}

# controler_couple <début du message> : le commit de données du couple visé va avec projet.env et le
# clone des données. Sans commande déclarée, pas de commit : le couple a « - ». Avec, le commit doit
# exister dans $VEILLE_EMPLOI_CLONE_DONNEES. Code 64 sinon, rien de touché ; rien à contrôler pour « - ».
controler_couple() {
  local debut="$1"
  [ "$COMMIT_DONNEES" != - ] || return 0
  if [ "$DECLARE_CONFIG" -eq 0 ] && [ "$DECLARE_CONTENU" -eq 0 ]; then
    arreter 64 "$debut : commit de données $COMMIT_DONNEES, mais deploiement/projet.env ne déclare ni VERIFIER_CONFIG ni VERIFIER_CONTENU (le couple d'un projet sans données montées a le commit « - »). Rien n'a changé"
  fi
  git -C "$VEILLE_EMPLOI_CLONE_DONNEES" cat-file -e "$COMMIT_DONNEES^{commit}" 2>/dev/null \
    || arreter 64 "$debut : commit de données $COMMIT_DONNEES introuvable dans $VEILLE_EMPLOI_CLONE_DONNEES. Rien n'a changé"
}

# verifier_donnees <quoi> <avant> <commit en service> : les données du couple visé, sous le verrou
# et avant tout changement : la règle des paires (controler_paires), l'instantané du commit
# (preparer_instantane), puis les commandes déclarées, dans un conteneur jetable de l'image visée,
# sur cet instantané, avec, pour VERIFIER_CONTENU, l'instantané du couple en service, s'il a un
# commit (verifier_instantane), refait d'abord s'il manque. <quoi> et <avant> sont ceux des messages
# de main. Rend 0 si le couple
# peut se déployer. Des données non conformes (code 2) : echec ← "<image> <commit>", signal, code 1 ;
# la sonde ne retentera pas ce couple. Une règle des paires en défaut, un instantané impossible, ou
# une vérification qui n'a pas eu lieu : rien n'est marqué, signal, code 1, et la sonde réessaiera.
# Dans tous les cas, ni compose.env ni le conteneur en service ne sont touchés.
verifier_donnees() {
  local quoi="$1" avant="$2" commit_service="$3" code=0
  local -a en_service=()
  if ! controler_paires "$COMMIT_DONNEES"; then
    journal "$quoi annulé, rien n'a changé : les données du commit $COMMIT_DONNEES ne suivent pas la règle des paires"
    signaler_sonde echec "données hors de la règle des paires avant $avant, rien n'a changé (voir le journal)"
    return 1
  fi
  if ! preparer_instantane "$COMMIT_DONNEES"; then
    journal "$quoi annulé, rien n'a changé"
    signaler_sonde echec "instantané des données impossible avant $avant, rien n'a changé (voir le journal)"
    return 1
  fi
  INSTANTANE_VISE="$INSTANTANE"
  if [ "$commit_service" != - ]; then
    en_service=("$VEILLE_EMPLOI_ETAT/instantanes/$commit_service")
    # L'instantané du couple en service, que VERIFIER_CONTENU reçoit sur /en-service, se refait s'il
    # manque (retiré à la main, disque refait) : sinon la vérification n'aurait jamais lieu. S'il ne
    # se refait pas, verifier_instantane le dit introuvable, et rien ne change.
    if [ "$DECLARE_CONTENU" -eq 1 ] && [ ! -e "${en_service[0]}" ] && [ ! -L "${en_service[0]}" ]; then
      journal "instantané du couple en service absent : ${en_service[0]} ; il se refait"
      preparer_instantane "$commit_service" \
        || journal "l'instantané du couple en service ne se refait pas"
    fi
  fi
  verifier_instantane "$NOM_ENV" "$REFERENCE" "$INSTANTANE_VISE" "${en_service[@]}" || code=$?
  case "$code" in
    0) return 0 ;;
    2)
      ecrire_atomique "$VEILLE_EMPLOI_ETAT/echec" "$REFERENCE $COMMIT_DONNEES"
      journal "$quoi refusé : les données du commit $COMMIT_DONNEES ne sont pas conformes pour $REFERENCE ; ce couple est marqué en échec, rien d'autre n'a changé"
      signaler_sonde echec "données non conformes avant $avant, couple marqué en échec (voir le journal)"
      return 1
      ;;
    *)
      journal "$quoi annulé, rien n'a changé : la vérification des données n'a pas eu lieu"
      signaler_sonde echec "vérification des données impossible avant $avant, rien n'a changé (voir le journal)"
      return 1
      ;;
  esac
}

# decrit_le_couple <compose.env> <image> <commit> : ce compose.env est celui de ce couple : son
# image, et, pour montages, ceux de l'instantané de ce commit, aucun pour « - ».
decrit_le_couple() {
  local fichier="$1" image="$2" commit="$3" cle chemin
  { [ -n "$image" ] && [ "$(valeur_de VEILLE_EMPLOI_IMAGE "$fichier")" = "$image" ]; } || return 1
  for cle in VEILLE_EMPLOI_CONFIG VEILLE_EMPLOI_CONTENU; do
    chemin="$(valeur_de "$cle" "$fichier")" || continue
    if [ "$commit" = - ] || [[ "$chemin" != "$VEILLE_EMPLOI_ETAT/instantanes/$commit/"* ]]; then
      return 1
    fi
  done
}

# canonique <chemin> : la forme canonique d'un chemin absolu, sans « // », « . », « .. » ni « / »
# final, sans résoudre les liens (`realpath -m -s`) : un lien repointé reste vu. Le chemin tel quel
# si realpath échoue.
canonique() {
  realpath -m -s -- "$1" 2>/dev/null || printf '%s\n' "$1"
}

# controler_montages <source de /config> <source de /contenu> : après le `up`, les montages du
# conteneur app, lus par `docker container inspect` (le JSON de .Mounts, une ligne « <point> <RW>
# <source> » par montage, par jq), sont ceux du couple lancé : sur /config et /contenu, cette source
# en lecture seule, ou rien si elle est vide (jamais /config en staging). Les deux sources se
# comparent sous leur forme canonique (canonique) : docker rend la source nettoyée, et $VEILLE_EMPLOI_ETAT
# peut porter un « // ». Rend 0, ou 1 journalisé.
controler_montages() {
  local sortie point attendu vu destination ecriture chemin
  local -a ids=()
  if ! sortie="$(dc ps -q app)" || [ -z "$sortie" ]; then
    journal "montages invérifiables : aucun conteneur app en service (docker compose ps)"
    return 1
  fi
  mapfile -t ids <<<"$sortie"
  if ! sortie="$(docker container inspect --format '{{json .Mounts}}' "${ids[@]}")"; then
    journal "montages invérifiables : docker container inspect ${ids[*]} en échec"
    return 1
  fi
  if ! sortie="$(printf '%s\n' "$sortie" | jq -r '.[] | "\(.Destination) \(.RW) \(.Source)"' 2>&1)"; then
    journal "montages invérifiables : la réponse de docker container inspect ne se lit pas : ${sortie//$'\n'/ }"
    return 1
  fi
  for point in config contenu; do
    attendu="$1"
    [ "$point" = config ] || attendu="$2"
    [ -z "$attendu" ] || attendu="$(canonique "$attendu")"
    vu=""
    while read -r destination ecriture chemin; do
      [ "$destination" != "/$point" ] || vu="${vu:+$vu, }$ecriture $(canonique "$chemin")"
    done <<<"$sortie"
    if [ -z "$attendu" ] && [ -n "$vu" ]; then
      journal "/$point monté alors que le couple ne le monte pas : $vu"
      return 1
    fi
    if [ -n "$attendu" ] && [ "$vu" != "false $attendu" ]; then
      journal "/$point : attendu $attendu en lecture seule, monté : ${vu:-rien}"
      return 1
    fi
  done
  journal "montages conformes (/config : ${1:-rien}, /contenu : ${2:-rien})"
}

# instantane : copie des données en service, dans un dossier qui a la forme de /donnees, par la
# commande SAUVEGARDER de deploiement/projet.env (lu, jamais sourcé), lancée dans le conteneur en
# service. Seul son code de sortie fait foi : sa sortie n'est que journalisée. La commande écrit sous
# un nom provisoire, <horodatage>.partiel, renommé après le code 0 : un instantané en échec garde ce
# nom, et rien ne le prend pour un instantané complet. Une destination déjà présente est un échec.
# La commande crée son dossier, pas ses parents : pre-deploiement/ est créé ici, sur l'hôte, comme
# sauvegarder.sh crée quotidiennes/, et ramené à 700 avec le dossier des sauvegardes, car un
# instantané est une copie en clair des données. Si l'un ou l'autre échoue, rien n'est lancé.
# Pas d'instantané, et un succès journalisé, si le compose.env en service ne déclare pas (ou vide)
# VEILLE_EMPLOI_SAUVEGARDES : la version en service ne monte pas /sauvegardes.
# Juste avant la commande, les .partiel des tentatives précédentes sont retirés : il n'en reste que
# celui de la dernière. Un retrait impossible est journalisé et n'arrête rien.
# Après un instantané réussi, le couple que le déploiement quitte, celui de deploye, est noté à côté
# de lui, <horodatage>.couple (noter_couple, lib.sh ; M-0005, § 3) : sans deploye, ou s'il ne se lit
# pas, l'instantané reste sans couple, et le déploiement continue. Puis pre-deploiement/ est purgé de
# ce qui a plus de 30 jours, chaque instantané avec son .couple : la sauvegarde de la nuit, qui le
# purge aussi, ne tourne qu'en prod.
instantane() {
  local horodatage destination hote sortie code=0 pre="$VEILLE_EMPLOI_SAUVEGARDES/pre-deploiement" monte
  # Le conteneur en service ne monte /sauvegardes que si son compose.env, celui de la version
  # en service, déclare VEILLE_EMPLOI_SAUVEGARDES. Sans lui (le projet vient d'activer les sauvegardes),
  # la commande échouerait à chaque passage de la sonde, et plus rien ne se déploierait.
  monte="$(valeur_de VEILLE_EMPLOI_SAUVEGARDES "$VEILLE_EMPLOI_ETAT/compose.env")" || monte=""
  if [ -z "$monte" ]; then
    journal "la version en service ne monte pas /sauvegardes : pas d'instantané ($VEILLE_EMPLOI_ETAT/compose.env ne déclare pas VEILLE_EMPLOI_SAUVEGARDES : les sauvegardes viennent d'être activées) ; le déploiement continue sans copie des données"
    return 0
  fi
  lire_projet_env SAUVEGARDER || return 1
  if ! mkdir -p -- "$pre"; then
    journal "instantané impossible : le dossier $pre ne peut pas être créé"
    return 1
  fi
  if ! chmod 700 -- "$VEILLE_EMPLOI_SAUVEGARDES" "$pre"; then
    journal "instantané impossible : les droits de $VEILLE_EMPLOI_SAUVEGARDES et de $pre ne peuvent pas être restreints"
    return 1
  fi
  horodatage="$(date -u +%Y%m%dT%H%M%SZ)"
  destination="/sauvegardes/pre-deploiement/$horodatage"
  hote="$pre/$horodatage"
  if [ -e "$hote" ] || [ -L "$hote" ] || [ -e "$hote.partiel" ] || [ -L "$hote.partiel" ]; then
    journal "instantané impossible : $hote existe déjà (ou $hote.partiel), rien n'est écrasé"
    return 1
  fi
  # La sonde retente toutes les 5 minutes ; sans ce retrait, chaque tentative en échec
  # laisserait son .partiel, une copie en clair des données.
  if ! retirer_partiels "$pre" '^[0-9]{8}T[0-9]{6}Z\.partiel$'; then
    journal "instantanés en échec de $pre : retrait impossible, plus d'un .partiel y reste ; l'instantané se fait quand même"
  fi
  sortie="$(dc exec -T app "${PROJET_MOTS[@]}" "$destination.partiel")" || code=$?
  if [ "$code" -ne 0 ]; then
    journal "instantané impossible (code $code) : ${sortie//$'\n'/ }"
    return 1
  fi
  # Le nom définitif est revérifié juste avant : avec -T, un dossier vide apparu entre-temps serait
  # remplacé sans bruit.
  if ! { [ -d "$hote.partiel" ] && [ ! -L "$hote.partiel" ] && [ ! -e "$hote" ] && [ ! -L "$hote" ] \
    && mv -T -- "$hote.partiel" "$hote"; }; then
    journal "instantané impossible : la commande a rendu 0, mais $hote.partiel ne peut pas prendre le nom $hote"
    return 1
  fi
  journal "instantané : $destination"
  noter_couple "$hote" || true
  purger_pre_deploiement "$pre"
}

# purger_pre_deploiement <dossier> : retire de pre-deploiement/ les instantanés de plus de 30 jours,
# d'après leur nom, chacun avec son .couple, avec la regex et la limite de la rétention de
# sauvegarder.sh. Celle-ci ne tourne qu'en prod : le staging, qui se déploie à chaque fusion,
# n'aurait sinon aucune purge. Un nom d'une autre forme n'est jamais retiré. Un échec est journalisé
# et n'arrête pas le déploiement.
purger_pre_deploiement() {
  local limite
  if ! limite="$(date -u -d '30 days ago' +%Y%m%dT%H%M%SZ)" \
    || ! purger_par_nom "$1" '^([0-9]{8}T[0-9]{6}Z)(\.partiel)?$' "$limite"; then
    journal "purge de $1 en échec : des instantanés de plus de 30 jours peuvent rester"
  fi
}

# controler_donnees <image> <quoi> <avant> : la garde du dossier de données, sous le verrou et avant
# tout changement. <image> est celle de deploye (vide si deploye l'est) ; <quoi> et <avant> sont
# ceux des messages de main. Rend 0 si le déploiement peut continuer ; sinon journalise le refus, le
# signale et rend 1, sans rien écrire dans $VEILLE_EMPLOI_ETAT. Avec --donnees-neuves, le journal le
# dit et rien n'est contrôlé ; sans deploye (premier déploiement), il n'y a rien à comparer.
# Un dossier vide, ou qui n'est plus celui de la version déployée, ressemble à un disque ou à une
# racine mal montés : l'application repartirait de zéro et le prochain instantané copierait du vide.
# La référence est le chemin canonique que le dernier succès a écrit dans
# $VEILLE_EMPLOI_ETAT/donnees, jamais résolu de nouveau : un lien repointé sur place la ferait suivre
# sa nouvelle cible. Sans lui (un état d'avant la v0.5.0 du modèle), le compose.env, s'il décrit la
# version déployée.
# « Changé » passe avant « vide » : une autre racine, que charger_env vient de créer vide, est dite
# changée, avec les deux chemins au journal. Le signal ne porte aucun chemin ; le journal les porte.
controler_donnees() {
  local deployee="$1" quoi="$2" avant="$3" reference canonique image_ref change=0 fin
  local etat="$VEILLE_EMPLOI_ETAT" donnees="$VEILLE_EMPLOI_DONNEES"
  if [ "$DONNEES_NEUVES" -eq 1 ]; then
    journal "données neuves voulues : $donnees" \
      "(contrôles du dossier de données levés pour ce déploiement)"
    return 0
  fi
  [ -f "$etat/deploye" ] || return 0
  fin="$quoi refusé, rien n'a changé. Corriger la racine des données, ou, si c'est voulu,"
  fin="$fin relancer à la main avec --donnees-neuves"
  reference="$(cat -- "$etat/donnees" 2>/dev/null)" || reference=""
  if [ -n "$reference" ]; then
    # Le même dossier si et seulement si son chemin canonique est aujourd'hui cette chaîne.
    canonique="$(realpath -- "$donnees" 2>/dev/null)" || canonique=""
    [ "$canonique" = "$reference" ] || change=1
  else
    # Le repli : le compose.env ne sert de référence que s'il décrit la version déployée.
    image_ref="$(valeur_de VEILLE_EMPLOI_IMAGE "$etat/compose.env")" || image_ref=""
    if [ -n "$deployee" ] && [ "$image_ref" = "$deployee" ] \
      && reference="$(valeur_de VEILLE_EMPLOI_DONNEES "$etat/compose.env")" \
      && [ -n "$reference" ]; then
      # Même chaîne, ou même dossier sous deux noms (lien symbolique) ; un ancien dossier disparu
      # est un changement.
      if [ "$reference" != "$donnees" ] && ! { [ -d "$reference" ] && [ -d "$donnees" ] \
        && [ "$(realpath -- "$reference")" = "$(realpath -- "$donnees")" ]; }; then
        change=1
      fi
    else
      journal "ni l'état ni compose.env ne disent le dossier de la version déployée :" \
        "le chemin des données n'est pas comparé, seul le vide est contrôlé"
    fi
  fi
  if [ "$change" -eq 1 ]; then
    journal "dossier de données changé : $donnees au lieu de $reference," \
      "celui de la version déployée : $fin"
    signaler_sonde echec "dossier de données changé avant $avant, rien n'a changé (voir le journal)"
    return 1
  fi
  # Vide : aucune entrée, fichiers cachés compris. -H suit un dossier de données qui est lui-même un
  # lien, comme Docker au montage. Un dossier illisible compte comme vide.
  if [ -z "$(find -H "$donnees" -mindepth 1 -print -quit 2>/dev/null)" ]; then
    journal "dossier de données vide : $donnees, alors qu'une version est déployée : $fin"
    signaler_sonde echec "dossier de données vide avant $avant, rien n'a changé (voir le journal)"
    return 1
  fi
  return 0
}

# preparer_retour : sous le verrou, REFERENCE, VERSION et COMMIT_DONNEES ← le couple de precedent
# (lire_version, lib.sh) ; COUPLE_EN_ECHEC et VERSION_QUITTEE ← le couple en service. Code 64 et
# aucune écriture si le retour est impossible : pas de couple en service ni précédent, le même
# couple, ou un commit de données que projet.env ou le clone des données refusent (controler_couple).
preparer_retour() {
  local etat="$VEILLE_EMPLOI_ETAT" image_quittee commit_quitte
  lire_version "$etat/deploye" \
    || arreter 64 "retour arrière impossible : aucune version en service ($etat/deploye absent ou illisible). Rien n'a changé"
  image_quittee="$IMAGE_LUE"
  commit_quitte="$COMMIT_LU"
  VERSION_QUITTEE="$VERSION_LUE"
  [ -f "$etat/precedent" ] \
    || arreter 64 "retour arrière impossible : aucune version précédente ($etat/precedent absent : un seul déploiement, ou retour déjà fait). Rien n'a changé"
  lire_version "$etat/precedent" \
    || arreter 64 "retour arrière impossible : $etat/precedent illisible. Rien n'a changé"
  { [ "$IMAGE_LUE" != "$image_quittee" ] || [ "$COMMIT_LU" != "$commit_quitte" ]; } \
    || arreter 64 "retour arrière impossible : le couple précédent ($VERSION_LUE, données $COMMIT_LU) est celui en service. Rien n'a changé"
  REFERENCE="$IMAGE_LUE"
  VERSION="$VERSION_LUE"
  COMMIT_DONNEES="$COMMIT_LU"
  COUPLE_EN_ECHEC="$image_quittee $commit_quitte"
  controler_couple "retour arrière impossible"
}

# commit_des_montages <compose.env> : le commit de données que nomment les montages de ce
# compose.env (VEILLE_EMPLOI_CONFIG, VEILLE_EMPLOI_CONTENU, sous $VEILLE_EMPLOI_ETAT/instantanes/<commit>/), ou « - »
# s'il n'en monte aucun.
commit_des_montages() {
  local cle chemin reste
  for cle in VEILLE_EMPLOI_CONFIG VEILLE_EMPLOI_CONTENU; do
    chemin="$(valeur_de "$cle" "$1")" || continue
    reste="${chemin#"$VEILLE_EMPLOI_ETAT/instantanes/"}"
    if [ "$reste" != "$chemin" ] && [[ "${reste%%/*}" =~ $MOTIF_SHA ]]; then
      printf '%s\n' "${reste%%/*}"
      return 0
    fi
  done
  printf '%s\n' -
}

# avertir_apres_retour : après le marquage d'un retour arrière, avec une commande de l'instance, ce
# qui ramènerait une moitié du couple quitté. Seul ce couple attend, et la sonde déploie tout couple
# neuf : en prod, la plus haute vX.Y.Z avec la plus haute étiquette de données ; en staging, :main
# avec la tête de la branche des données. Changer une moitié de cette cible fait donc un couple neuf
# avec l'autre, celle du couple quitté tant qu'elle n'a pas changé. Ce qui passe d'abord dépend de
# ce que le retour change :
#   - l'image seule : une étiquette de données (un commit de la branche des données) ramènerait
#     l'image quittée ; d'abord une vX.Y.Z plus haute que la version quittée, sur le commit de la
#     version gardée (le correctif du code), qui publie l'image gardée ;
#   - le commit de données seul : une vX.Y.Z sur un nouveau commit (une fusion dans le code)
#     ramènerait les données quittées ; d'abord une étiquette de données sur un commit corrigé (la
#     branche des données corrigée). Une vX.Y.Z sur le commit gardé publie la même image : elle
#     refait le couple quitté, qui attend encore ;
#   - les deux : chaque geste ramène une moitié du couple quitté ; d'abord celui qui remplace la
#     moitié en cause.
avertir_apres_retour() {
  local image_quittee="${COUPLE_EN_ECHEC%% *}" commit_quitte="${COUPLE_EN_ECHEC#* }"
  local image=0 donnees=0
  [ "$image_quittee" = "$REFERENCE" ] || image=1
  [ "$commit_quitte" = "$COMMIT_DONNEES" ] || donnees=1
  if [ "$NOM_ENV" = prod ]; then
    if [ "$image" -eq 1 ] && [ "$donnees" -eq 1 ]; then
      journal "une nouvelle étiquette de données redéploierait $VERSION_QUITTEE avec elle, une nouvelle vX.Y.Z les données quittées ($commit_quitte) : poser d'abord celle qui remplace la moitié en cause"
    elif [ "$image" -eq 1 ]; then
      journal "une nouvelle étiquette de données redéploierait $VERSION_QUITTEE avec elle : poser d'abord, sur le commit de $VERSION, une vX.Y.Z plus haute que $VERSION_QUITTEE"
    else
      journal "une vX.Y.Z sur un nouveau commit redéploierait les données quittées ($commit_quitte) avec elle : poser d'abord une étiquette de données sur un commit corrigé"
    fi
  elif [ "$image" -eq 1 ] && [ "$donnees" -eq 1 ]; then
    journal "un nouveau commit de la branche des données redéploierait l'image quittée avec lui, une fusion dans le code les données quittées ($commit_quitte) : corriger d'abord la moitié en cause"
  elif [ "$image" -eq 1 ]; then
    journal "un nouveau commit de la branche des données redéploierait l'image quittée avec lui : fusionner d'abord le correctif du code"
  else
    journal "une fusion dans le code redéploierait les données quittées ($commit_quitte) avec elle : corriger d'abord la branche des données"
  fi
}

# echouer <raison> : le couple est marqué en échec avant tout le reste, puis retour arrière. En
# retour arrière manuel, le « couple en échec » est celui qu'on quittait : echec le nomme déjà, et
# le remettre en service est le comportement d'un déploiement raté. Le couple remis en service se
# contrôle comme à l'aller : ses montages après le `up`, ceux de compose.env.precedent (un conteneur
# que compose ne recrée pas monterait encore l'instantané en échec), sauf si ni lui ni le couple en
# échec n'ont de commit de données ; puis sa santé, avec le champ configuration aux conditions de
# l'aller, lues sur ce couple : montee s'il monte /config, exemple en staging s'il a un commit de
# données (COMMIT_PRECEDENT, sinon celui de ses montages) et que projet.env déclare VERIFIER_CONFIG.
echouer() {
  local raison="$1" etat="$VEILLE_EMPLOI_ETAT" retour=aucun image_prec version_prec revision_prec message
  local config_prec contenu_prec commit_prec configuration_prec=""
  ecrire_atomique "$etat/echec" "$COUPLE_EN_ECHEC"
  if [ "$RETOUR" -eq 1 ]; then
    journal "échec du retour à $VERSION ($raison) : $COUPLE_EN_ECHEC ($VERSION_QUITTEE) reste marqué en échec"
  else
    journal "échec du déploiement de $VERSION ($raison) : $COUPLE_EN_ECHEC marqué en échec"
  fi

  if [ -f "$etat/compose.env.precedent" ]; then
    copier_atomique "$etat/compose.env.precedent" "$etat/compose.env"
    image_prec="$(valeur_de VEILLE_EMPLOI_IMAGE "$etat/compose.env")" || image_prec=""
    version_prec="$(valeur_de VEILLE_EMPLOI_VERSION "$etat/compose.env")" || version_prec=inconnue
    config_prec="$(valeur_de VEILLE_EMPLOI_CONFIG "$etat/compose.env")" || config_prec=""
    contenu_prec="$(valeur_de VEILLE_EMPLOI_CONTENU "$etat/compose.env")" || contenu_prec=""
    commit_prec="${COMMIT_PRECEDENT:-$(commit_des_montages "$etat/compose.env")}"
    if [ -n "$config_prec" ]; then
      configuration_prec=montee
    elif [ "$NOM_ENV" != prod ] && [ "$commit_prec" != - ] && [ "$DECLARE_CONFIG" -eq 1 ]; then
      configuration_prec=exemple
    fi
    retour="$version_prec"
    journal "retour à $version_prec : $image_prec, données $commit_prec"
    if lancer \
      && { { [ "$commit_prec" = - ] && [ "$COMMIT_DONNEES" = - ]; } \
        || controler_montages "$config_prec" "$contenu_prec"; } \
      && revision_prec="$(revision_de "$image_prec")" \
      && sante_conforme "$version_prec" "$revision_prec" ${configuration_prec:+"$configuration_prec"}; then
      journal "retour à $version_prec réussi"
    else
      retour="$version_prec en échec"
      journal "retour à $version_prec en échec : intervention nécessaire"
    fi
    if [ "$RETOUR" -eq 1 ]; then
      message="échec du retour à $VERSION, $version_prec remise en service"
      [ "$retour" = "$version_prec" ] || message="$message en échec"
    else
      message="échec $VERSION, retour à $retour"
    fi
  else
    # Premier déploiement : rien à restaurer. La version en échec ne reste pas en service (elle
    # pourrait redémarrer en boucle et bloquer l'instantané du déploiement suivant).
    journal "aucune version précédente : arrêt de la version en échec"
    dc stop || journal "arrêt de la version en échec impossible"
    if [ "$RETOUR" -eq 1 ]; then
      message="échec du retour à $VERSION, aucune version à remettre en service (arrêt)"
    else
      message="échec $VERSION, retour à $retour"
    fi
  fi

  signaler_sonde echec "$message"
}

main() {
  local usage="usage : bash deploiement/deployer.sh <prod|staging> <image@sha256:…> <version> [--commit-donnees <sha>] [--donnees-neuves] | bash deploiement/deployer.sh <prod|staging> --retour"
  if [ "$#" -ge 2 ] && [ "$2" = --retour ]; then
    # --retour ne prend aucune option : le couple vient de precedent, et --donnees-neuves
    # n'existe que pour un déploiement.
    [ "$#" -eq 2 ] || arreter 64 "$usage"
    RETOUR=1
    NOM_ENV="$1"
  elif [ "$#" -ge 3 ]; then
    NOM_ENV="$1"
    REFERENCE="$2"
    VERSION="$3"
    shift 3
    while [ "$#" -gt 0 ]; do
      case "$1" in
        --commit-donnees)
          { [ "$#" -ge 2 ] && [ "$OPTION_COMMIT" -eq 0 ]; } || arreter 64 "$usage"
          OPTION_COMMIT=1
          COMMIT_DONNEES="$2"
          shift 2
          ;;
        --donnees-neuves)
          [ "$DONNEES_NEUVES" -eq 0 ] || arreter 64 "$usage"
          DONNEES_NEUVES=1
          shift
          ;;
        *) arreter 64 "$usage" ;;
      esac
    done
    # Validés avant d'être écrits dans compose.env et dans l'état. Le commit de données nomme aussi
    # un dossier de l'état : jamais « - », qui s'écrit en omettant l'option.
    [[ "$REFERENCE" =~ $MOTIF_REFERENCE ]] \
      || arreter 64 "référence invalide : '$REFERENCE' (attendu : image@sha256:<64 caractères hexadécimaux>)"
    [[ "$VERSION" =~ $MOTIF_VERSION ]] \
      || arreter 64 "version invalide : '$VERSION' (attendu : main ou X.Y.Z)"
    if [ "$OPTION_COMMIT" -eq 1 ]; then
      { [[ "$COMMIT_DONNEES" =~ $MOTIF_COMMIT ]] && [ "$COMMIT_DONNEES" != - ]; } \
        || arreter 64 "commit de données invalide : '$COMMIT_DONNEES' (attendu : 40 caractères hexadécimaux)"
    fi
    COUPLE_EN_ECHEC="$REFERENCE $COMMIT_DONNEES"
  else
    arreter 64 "$usage"
  fi

  # Les secrets de cette version font foi : charger_secrets remplace ceux qu'hériteraient le shell
  # ou la sonde (qui a chargé les siens avant de passer le clone sur la nouvelle version). L'adresse
  # du signal est retirée d'abord : une version qui ne la déclare plus n'hérite pas de l'ancienne.
  unset HC_SONDE
  charger_env "$NOM_ENV"
  charger_secrets "$NOM_ENV"
  local etat="$VEILLE_EMPLOI_ETAT" deployee="" commit_deploye=- conteneurs="" revision raison="" quoi avant declarees=""
  local config_visee="" contenu_vise=""
  local -a lignes=()

  # L'image, la version et les montages ne viennent que de compose.env (refuser_image_heritee,
  # lib.sh) : posée dans le shell ou par une ligne de l'env, l'une de ces variables l'emporterait,
  # et le retour arrière relancerait la mauvaise version, ou monterait autre chose que l'instantané
  # vérifié. Refus net plutôt qu'effacement silencieux : l'appelant a une erreur à voir.
  refuser_image_heritee

  # L'adresse publique vient de l'env de l'environnement (charger_env) et s'écrit dans compose.env :
  # validée avant tout, comme la référence et la version. Le message ne reprend pas la valeur, qui
  # pourrait porter des identifiants.
  [[ "${VEILLE_EMPLOI_URL_PUBLIQUE:-}" =~ $MOTIF_URL_PUBLIQUE ]] \
    || arreter 1 "VEILLE_EMPLOI_URL_PUBLIQUE invalide ou absente de $VEILLE_EMPLOI_CLONE_DONNEES/$SOUS_DOSSIER_ENV/$NOM_ENV.env (attendu : http(s)://hôte[:port], sans chemin ni requête). Rien n'a changé"

  # Les commandes de l'instance que déclare projet.env, et, pour un déploiement, le commit de données
  # qui doit aller avec : sans --commit-donnees, une commande déclarée refuse (64) ; celui d'un
  # retour arrière se lit sous le verrou.
  donnees_declarees || arreter 1 "deploiement/projet.env illisible : rien n'a changé"
  if [ "$RETOUR" -eq 0 ]; then
    [ "$DECLARE_CONFIG" -eq 0 ] || declarees="VERIFIER_CONFIG"
    [ "$DECLARE_CONTENU" -eq 0 ] || declarees="${declarees:+$declarees et }VERIFIER_CONTENU"
    if [ "$OPTION_COMMIT" -eq 0 ] && [ -n "$declarees" ]; then
      arreter 64 "commit de données absent : deploiement/projet.env déclare $declarees ; relancer avec --commit-donnees <sha>. Rien n'a changé"
    fi
    controler_couple "déploiement de $VERSION impossible"
  fi

  # 1. Verrou.
  if [ "${VEILLE_EMPLOI_VERROU_TENU:-}" != 1 ]; then
    exec 9>"$etat/verrou"
    quoi="déploiement de $VERSION"
    [ "$RETOUR" -eq 0 ] || quoi="retour arrière"
    flock -w 600 9 \
      || arreter 1 "verrou $etat/verrou toujours pris après 600 s : $quoi abandonné, rien n'a changé"
  fi
  # Le couple précédent se lit sous le verrou : une sonde qui déploie en même temps l'aurait changé.
  # `quoi` et `avant` servent aux messages : « déploiement de 0.2.0 » / « avant 0.2.0 », ou
  # « retour à 0.1.0 » / « avant le retour à 0.1.0 ».
  if [ "$RETOUR" -eq 1 ]; then
    preparer_retour
    quoi="retour à $VERSION"
    avant="le retour à $VERSION"
    journal "retour arrière en $NOM_ENV : $VERSION_QUITTEE ($COUPLE_EN_ECHEC) → $VERSION ($REFERENCE $COMMIT_DONNEES)"
  else
    quoi="déploiement de $VERSION"
    avant="$VERSION"
    journal "déploiement de $VERSION en $NOM_ENV : $REFERENCE, données $COMMIT_DONNEES"
  fi
  preparer_couple

  # Le couple en service : son image sert à l'étape 3 et à la garde, son commit à la
  # vérification du contenu (« - » sans commit, ou pour un état d'avant la v0.7.0).
  if [ -f "$etat/deploye" ]; then
    { read -r deployee _ commit_deploye _ || true; } <"$etat/deploye"
    [[ "${commit_deploye:-}" =~ $MOTIF_COMMIT ]] || commit_deploye=-
  fi
  # 1 bis. La garde du dossier de données, avant toute lecture de l'application et tout changement.
  controler_donnees "$deployee" "$quoi" "$avant" || return 1
  # 1 ter. Les données du couple visé, avant toute lecture de l'application et tout changement.
  if [ "$COMMIT_DONNEES" != - ]; then
    verifier_donnees "$quoi" "$avant" "$commit_deploye" || return 1
  fi

  # 2. Instantané, si l'application tourne. Sans compose.env (premier déploiement), `dc` ne peut
  # pas tourner et il n'y a rien à copier.
  if [ -f "$etat/compose.env" ]; then
    if ! conteneurs="$(dc ps -q app)"; then
      journal "état de l'application illisible (docker compose ps) : $quoi annulé, rien n'a changé"
      signaler_sonde echec "état de l'application illisible avant $avant, rien n'a changé"
      return 1
    fi
  fi
  if [ -n "$conteneurs" ]; then
    if ! instantane; then
      journal "$quoi annulé, rien n'a changé"
      signaler_sonde echec "instantané impossible avant $avant, rien n'a changé"
      return 1
    fi
  else
    journal "application arrêtée ou jamais déployée : pas d'instantané"
  fi

  # 3. compose.env. Un retour arrière marque d'abord le couple quitté : c'est le premier changement
  # d'état, et la sonde ne doit jamais voir le précédent en service sans cette marque.
  if [ "$RETOUR" -eq 1 ]; then
    ecrire_atomique "$etat/echec" "$COUPLE_EN_ECHEC"
    journal "couple $COUPLE_EN_ECHEC ($VERSION_QUITTEE) marqué en échec : la sonde ne redéploiera pas ce couple"
    if [ "$DECLARE_CONFIG" -eq 1 ] || [ "$DECLARE_CONTENU" -eq 1 ]; then
      avertir_apres_retour
    fi
  fi
  if [ -f "$etat/compose.env" ]; then
    if [ -z "$deployee" ]; then
      # Un premier déploiement en échec laisse le compose.env de son couple, sans deploye.
      journal "aucun couple déployé : le compose.env d'un déploiement en échec n'est pas gardé"
    elif decrit_le_couple "$etat/compose.env" "$deployee" "$commit_deploye"; then
      copier_atomique "$etat/compose.env" "$etat/compose.env.precedent"
      COMMIT_PRECEDENT="$commit_deploye"
    elif [ -f "$etat/compose.env.precedent" ]; then
      journal "compose.env ne décrit pas le couple déployé (déploiement interrompu ?) : compose.env.precedent reste la cible du retour arrière"
    else
      journal "compose.env ne décrit pas le couple déployé (déploiement interrompu ?) : il n'est pas gardé"
    fi
  fi
  lignes=(
    "VEILLE_EMPLOI_IMAGE=$REFERENCE"
    "VEILLE_EMPLOI_VERSION=$VERSION"
    "VEILLE_EMPLOI_ENV=$NOM_ENV"
    "VEILLE_EMPLOI_PORT=$VEILLE_EMPLOI_PORT"
    "VEILLE_EMPLOI_DONNEES=$VEILLE_EMPLOI_DONNEES"
    "VEILLE_EMPLOI_SAUVEGARDES=$VEILLE_EMPLOI_SAUVEGARDES"
    "VEILLE_EMPLOI_URL_PUBLIQUE=$VEILLE_EMPLOI_URL_PUBLIQUE"
  )
  # Les montages de l'instantané visé, que `dc` lit dans compose.env (jamais /config en staging).
  [ "$MONTER_CONFIG" -eq 0 ] || config_visee="$INSTANTANE_VISE/config"
  [ "$MONTER_CONTENU" -eq 0 ] || contenu_vise="$INSTANTANE_VISE/contenu"
  [ -z "$config_visee" ] || lignes+=("VEILLE_EMPLOI_CONFIG=$config_visee")
  [ -z "$contenu_vise" ] || lignes+=("VEILLE_EMPLOI_CONTENU=$contenu_vise")
  ecrire_atomique "$etat/compose.env" "${lignes[@]}"

  # 4. Lancement, montages (avec un commit de données) et santé.
  if ! lancer; then
    raison="docker compose up en échec"
  elif [ "$COMMIT_DONNEES" != - ] && ! controler_montages "$config_visee" "$contenu_vise"; then
    raison="montage des données non conforme"
  elif ! revision="$(revision_de "$REFERENCE")"; then
    raison="révision de l'image illisible"
  elif ! sante_conforme "$VERSION" "$revision" ${CONFIGURATION_ATTENDUE:+"$CONFIGURATION_ATTENDUE"}; then
    raison="santé non conforme"
  fi
  if [ -n "$raison" ]; then
    echouer "$raison"
    return 1
  fi

  # 5. Succès. Un retour arrière garde `echec` (le couple quitté) et consomme `precedent`.
  # Juste après deploye, donnees : le chemin canonique du dossier de données, la référence de la
  # garde au déploiement suivant. Seul un succès l'écrit.
  if [ "$RETOUR" -eq 1 ]; then
    ecrire_atomique "$etat/deploye" "$REFERENCE $VERSION $COMMIT_DONNEES"
    ecrire_atomique "$etat/donnees" "$(realpath -- "$VEILLE_EMPLOI_DONNEES")"
    rm -f -- "$etat/precedent"
    journal "retour effectué : $VERSION ($REFERENCE, données $COMMIT_DONNEES) ; le couple $COUPLE_EN_ECHEC ($VERSION_QUITTEE) reste marqué en échec"
    signaler_sonde ok "retour à $VERSION effectué (depuis $VERSION_QUITTEE)"
    menage_des_images
    return 0
  fi
  if [ -f "$etat/deploye" ]; then
    copier_atomique "$etat/deploye" "$etat/precedent"
  fi
  ecrire_atomique "$etat/deploye" "$REFERENCE $VERSION $COMMIT_DONNEES"
  ecrire_atomique "$etat/donnees" "$(realpath -- "$VEILLE_EMPLOI_DONNEES")"
  rm -f -- "$etat/echec"
  journal "déployé : $VERSION ($REFERENCE, données $COMMIT_DONNEES)"
  if [ "$COMMIT_DONNEES" = - ]; then
    signaler_sonde ok "déployé $VERSION"
  else
    signaler_sonde ok "déployé $VERSION, données ${COMMIT_DONNEES:0:12}"
  fi
  menage_des_images
  return 0
}

# Tout le corps est dans main, appelée sur la dernière ligne : bash a lu tout le fichier avant
# qu'un `git checkout` ne le remplace.
main "$@"; exit $?

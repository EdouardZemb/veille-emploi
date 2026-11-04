#!/usr/bin/env bats
# Unités systemd utilisateur : rendu des gabarits (deploiement/systemd/*.in), installation,
# contrôle de dérive (`installer-unites.sh --verifier`) et alerte d'échec (`alerter.sh`).
#
# systemctl est un double qui journalise ses appels : aucune unité n'est réellement installée ni
# démarrée. Les unités vont dans un dossier de test ($UNITES), les deux clones sont des chemins de
# test ($CLONE pour la prod, $CLONE_STAGING pour le staging).

bats_require_minimum_version 1.5.0

load aide

setup() {
  preparer_environnement
  creer_double systemctl
  export VEILLE_EMPLOI_CLONE_PROD="$CLONE"
  CLONE_STAGING="$BATS_TEST_TMPDIR/clone-staging"
  export VEILLE_EMPLOI_CLONE_STAGING="$CLONE_STAGING"
  UNITES="$BATS_TEST_TMPDIR/unites"
  export VEILLE_EMPLOI_DOSSIER_UNITES="$UNITES"
  # La déclaration du projet sur le serveur, à son emplacement par défaut, avec les heures
  # d'origine (02:45, et Sun 04:15 pour le test de restauration).
  declarer_projet SAUVEGARDE=02:45 "TEST_RESTAURATION=Sun 04:15"
  # Les neuf unités rendues : quatre services, quatre minuteries, un modèle d'alerte.
  ATTENDUES=(
    veille-emploi-alerte@.service
    veille-emploi-sauvegarde.service veille-emploi-sauvegarde.timer
    veille-emploi-sonde-prod.service veille-emploi-sonde-prod.timer
    veille-emploi-sonde-staging.service veille-emploi-sonde-staging.timer
    veille-emploi-test-restauration.service veille-emploi-test-restauration.timer
  )
  # Les cinq rendues quand serveur déclare « non » : ni la sauvegarde ni son test.
  SANS_SAUVEGARDE=(
    veille-emploi-alerte@.service
    veille-emploi-sonde-prod.service veille-emploi-sonde-prod.timer
    veille-emploi-sonde-staging.service veille-emploi-sonde-staging.timer
  )
}

# installer [option] : lance installer-unites.sh du clone temporaire ; stdout dans $output, stderr
# dans $stderr (voir `run --separate-stderr`).
installer() {
  run --separate-stderr bash "$CLONE/deploiement/installer-unites.sh" "$@"
}

# declarer_projet <ligne…> : la déclaration du projet sur le serveur, ~/serveur/projets/veille-emploi.env,
# avec ces lignes et quelques autres clés, qu'installer-unites.sh ignore.
declarer_projet() {
  mkdir -p "$HOME/serveur/projets"
  printf '%s\n' "# Déclaration de test" NOM=veille-emploi CIBLE=serveur VISIBILITE=prive BRANCHE=main \
    BLOC_PORTS=4310 "$@" >"$HOME/serveur/projets/veille-emploi.env"
}

# --- rendu -----------------------------------------------------------------------------------

@test "rendu_substitue_les_chemins" {
  installer
  [ "$status" -eq 0 ]
  grep -Fx "ExecStart=/bin/bash $CLONE_STAGING/deploiement/sonder.sh staging" \
    "$UNITES/veille-emploi-sonde-staging.service"
  grep -Fx "ExecStart=/bin/bash $CLONE/deploiement/sonder.sh prod" \
    "$UNITES/veille-emploi-sonde-prod.service"
  # la sauvegarde, son test et l'alerte vivent sur le clone de prod
  grep -Fx "ExecStart=/bin/bash $CLONE/deploiement/sauvegarder.sh prod" \
    "$UNITES/veille-emploi-sauvegarde.service"
  grep -Fx "ExecStart=/bin/bash $CLONE/deploiement/tester-restauration.sh prod" \
    "$UNITES/veille-emploi-test-restauration.service"
  grep -Fx "ExecStart=/bin/bash $CLONE/deploiement/alerter.sh %i" "$UNITES/veille-emploi-alerte@.service"
}

@test "rendu_cree_exactement_les_unites_attendues" {
  installer
  [ "$status" -eq 0 ]
  [ "$(find "$UNITES" -mindepth 1 -printf '%f\n' | sort)" = "$(printf '%s\n' "${ATTENDUES[@]}" | sort)" ]
  # aucun marqueur de gabarit ne subsiste
  aucune_ligne '@[A-Z][A-Z_]*@' "$UNITES"/*
}

@test "rendu_des_services_porte_les_options_du_brief" {
  installer
  [ "$status" -eq 0 ]
  local service
  for service in "$UNITES"/veille-emploi-*.service; do
    grep -Fx 'Type=oneshot' "$service"
    grep -Fx 'Environment=PATH=%h/.local/bin:/usr/local/bin:/usr/bin:/bin' "$service"
    grep -Fx 'Nice=10' "$service"
    grep -Fx 'IOSchedulingClass=idle' "$service"
    grep -Fx 'TimeoutStartSec=15min' "$service"
    # démarrés par leurs minuteries (ou par OnFailure) : jamais d'[Install]
    aucune_ligne '^\[Install\]' "$service"
  done
  # OnFailure est une option de [Unit], pas de [Service] (systemd l'ignorerait)
  for service in sonde-prod sonde-staging sauvegarde test-restauration; do
    [ "$(sed -n '/^\[Unit\]/,/^\[Service\]/p' "$UNITES/veille-emploi-$service.service" \
      | grep -Fxc 'OnFailure=veille-emploi-alerte@%n.service')" -eq 1 ]
  done
  # l'alerte n'a pas d'OnFailure : une alerte en échec ne s'alerte pas elle-même
  aucune_ligne '^OnFailure=' "$UNITES/veille-emploi-alerte@.service"
}

@test "rendu_des_minuteries_porte_les_horaires" {
  installer
  [ "$status" -eq 0 ]
  local minuterie
  for minuterie in "$UNITES"/veille-emploi-*.timer; do
    grep -Fx 'WantedBy=timers.target' "$minuterie"
    # l'unité activée est celle du même nom : pas de Unit=
    aucune_ligne '^Unit=' "$minuterie"
  done
  for minuterie in sonde-prod sonde-staging; do
    grep -Fx 'OnBootSec=2min' "$UNITES/veille-emploi-$minuterie.timer"
    grep -Fx 'OnUnitActiveSec=5min' "$UNITES/veille-emploi-$minuterie.timer"
  done
  grep -Fx 'OnCalendar=*-*-* 02:45:00' "$UNITES/veille-emploi-sauvegarde.timer"
  grep -Fx 'Persistent=true' "$UNITES/veille-emploi-sauvegarde.timer"
  grep -Fx 'OnCalendar=Sun *-*-* 04:15:00' "$UNITES/veille-emploi-test-restauration.timer"
  grep -Fx 'Persistent=true' "$UNITES/veille-emploi-test-restauration.timer"
}

# Rendre deux fois (ici vers deux dossiers) donne les mêmes octets : le contrôle de dérive compare
# des octets.
@test "rendu_est_identique_octet_pour_octet" {
  installer
  [ "$status" -eq 0 ]
  VEILLE_EMPLOI_DOSSIER_UNITES="$BATS_TEST_TMPDIR/unites-bis" installer
  [ "$status" -eq 0 ]
  diff -r "$UNITES" "$BATS_TEST_TMPDIR/unites-bis"
}

# Un chemin de clone avec une esperluette ne doit pas être réinterprété par la substitution.
@test "rendu_garde_un_chemin_avec_une_esperluette_tel_quel" {
  export VEILLE_EMPLOI_CLONE_STAGING="$BATS_TEST_TMPDIR/a&b"
  installer
  [ "$status" -eq 0 ]
  grep -Fx "ExecStart=/bin/bash $BATS_TEST_TMPDIR/a&b/deploiement/sonder.sh staging" \
    "$UNITES/veille-emploi-sonde-staging.service"
}

@test "rendu_refuse_un_chemin_que_systemd_interpreterait" {
  local chemin
  # shellcheck disable=SC2016  # les « $ » sont voulus littéraux
  for chemin in "$BATS_TEST_TMPDIR/avec espace" '/a%h' '/a$HOME' '/a;b' '/a"b' "/a'b" 'relatif/clone'; do
    VEILLE_EMPLOI_CLONE_STAGING="$chemin" installer
    [ "$status" -eq 64 ]
    [[ "$stderr" == *"VEILLE_EMPLOI_CLONE_STAGING"* ]]
  done
  VEILLE_EMPLOI_CLONE_PROD='/a b' installer
  [ "$status" -eq 64 ]
  [[ "$stderr" == *"VEILLE_EMPLOI_CLONE_PROD"* ]]
  # rien n'a été installé, rien n'a été demandé à systemd
  [ ! -e "$UNITES" ]
  [ "$(nombre_d_appels systemctl)" -eq 0 ]
}

@test "rendu_refuse_un_gabarit_a_marqueur_inconnu_sans_rien_installer" {
  printf '[Unit]\nDescription=@INCONNU@\n' >"$CLONE/deploiement/systemd/veille-emploi-sauvegarde.service.in"
  installer
  [ "$status" -eq 1 ]
  [[ "$stderr" == *"@INCONNU@"* ]]
  [ ! -e "$UNITES" ] || [ -z "$(ls -A "$UNITES")" ]
  [ "$(nombre_d_appels systemctl)" -eq 0 ]
}

# --- heures des sauvegardes, lues dans la déclaration du projet sur le serveur ----------------

@test "unites_heures_lues_dans_projets_serveur" {
  declarer_projet SAUVEGARDE=03:10 "TEST_RESTAURATION=Wed 05:20"
  installer
  [ "$status" -eq 0 ]
  grep -Fx 'OnCalendar=*-*-* 03:10:00' "$UNITES/veille-emploi-sauvegarde.timer"
  grep -Fx 'OnCalendar=Wed *-*-* 05:20:00' "$UNITES/veille-emploi-test-restauration.timer"
  # le serveur change une heure : les unités installées divergent, et l'installation les remet
  declarer_projet SAUVEGARDE=03:40 "TEST_RESTAURATION=Wed 05:20"
  installer --verifier
  [ "$status" -eq 1 ]
  [[ "$stderr" == *"veille-emploi-sauvegarde.timer"* ]]
  [[ "$stderr" != *"veille-emploi-test-restauration.timer"* ]]
  installer
  [ "$status" -eq 0 ]
  grep -Fx 'OnCalendar=*-*-* 03:40:00' "$UNITES/veille-emploi-sauvegarde.timer"
  # VEILLE_EMPLOI_PROJET_SERVEUR désigne une autre déclaration
  printf '%s\n' SAUVEGARDE=23:59 "TEST_RESTAURATION=Mon 00:00" >"$BATS_TEST_TMPDIR/ailleurs.env"
  VEILLE_EMPLOI_PROJET_SERVEUR="$BATS_TEST_TMPDIR/ailleurs.env" installer
  [ "$status" -eq 0 ]
  grep -Fx 'OnCalendar=*-*-* 23:59:00' "$UNITES/veille-emploi-sauvegarde.timer"
  grep -Fx 'OnCalendar=Mon *-*-* 00:00:00' "$UNITES/veille-emploi-test-restauration.timer"
}

@test "unites_heures_absentes_refusent" {
  local option
  for option in "" --verifier; do
    rm -f "$HOME/serveur/projets/veille-emploi.env"
    # shellcheck disable=SC2086  # sans option, aucun argument
    installer $option
    [ "$status" -eq 1 ]
    [[ "$stderr" == *"$HOME/serveur/projets/veille-emploi.env"* ]]
    [ ! -e "$UNITES" ]
    [ "$(nombre_d_appels systemctl)" -eq 0 ]
  done
  # une clé absente, « non » sur une seule des deux clés, ou une clé déclarée deux fois
  local cas
  for cas in "SAUVEGARDE=02:45" "TEST_RESTAURATION=Sun 04:15" "SAUVEGARDE=non" "TEST_RESTAURATION=non" \
    "SAUVEGARDE=non|TEST_RESTAURATION=Sun 04:15" "SAUVEGARDE=02:45|TEST_RESTAURATION=non" \
    "SAUVEGARDE=non|TEST_RESTAURATION=non|SAUVEGARDE=non" \
    "SAUVEGARDE=02:45|TEST_RESTAURATION=Sun 04:15|SAUVEGARDE=03:00"; do
    local lignes=()
    IFS='|' read -r -a lignes <<<"$cas"
    declarer_projet "${lignes[@]}"
    installer
    [ "$status" -eq 1 ]
    [[ "$stderr" == *"veille-emploi.env"* ]]
    [ ! -e "$UNITES" ]
  done
  [ "$(nombre_d_appels systemctl)" -eq 0 ]
}

@test "unites_heures_mal_formees_refusent" {
  local valeur
  for valeur in 2:45 25:00 02:60 02:45:00 ' 02:45' '02:45 ' 0245 $'02:45\r' '' Non NON 'non ' $'non\r'; do
    declarer_projet "SAUVEGARDE=$valeur" "TEST_RESTAURATION=Sun 04:15"
    installer
    [ "$status" -eq 1 ]
    [[ "$stderr" == *"SAUVEGARDE absente ou mal formée"* ]]
  done
  for valeur in 'Dim 04:15' 'sun 04:15' 'Sunday 04:15' 'Sun 4:15' 'Sun  04:15' 'Sun 24:00' '04:15' \
    'Sun *-*-* 04:15:00' $'Sun 04:15\r'; do
    declarer_projet SAUVEGARDE=02:45 "TEST_RESTAURATION=$valeur"
    installer
    [ "$status" -eq 1 ]
    [[ "$stderr" == *"TEST_RESTAURATION absente ou mal formée"* ]]
  done
  # rien n'a été installé, rien n'a été demandé à systemd
  [ ! -e "$UNITES" ]
  [ "$(nombre_d_appels systemctl)" -eq 0 ]
}

# Les heures d'origine rendent, à l'octet près, les minuteries d'avant le modèle : sinon la sonde de
# prod verrait des unités divergentes au premier passage (revue, point 5).
@test "unites_heures_identiques_a_ancrage" {
  declarer_projet SAUVEGARDE=02:45 "TEST_RESTAURATION=Sun 04:15"
  installer
  [ "$status" -eq 0 ]
  grep -Fx 'OnCalendar=*-*-* 02:45:00' "$UNITES/veille-emploi-sauvegarde.timer"
  grep -Fx 'OnCalendar=Sun *-*-* 04:15:00' "$UNITES/veille-emploi-test-restauration.timer"
  diff "$UNITES/veille-emploi-sauvegarde.timer" - <<'FIN'
# Rendu de deploiement/systemd/veille-emploi-sauvegarde.timer.in par deploiement/installer-unites.sh.
# Ne pas modifier à la main : la sonde de prod alerte au moindre écart avec ce rendu.
[Unit]
Description=veille-emploi : minuterie de la sauvegarde (prod)

[Timer]
OnCalendar=*-*-* 02:45:00
Persistent=true

[Install]
WantedBy=timers.target
FIN
  diff "$UNITES/veille-emploi-test-restauration.timer" - <<'FIN'
# Rendu de deploiement/systemd/veille-emploi-test-restauration.timer.in par deploiement/installer-unites.sh.
# Ne pas modifier à la main : la sonde de prod alerte au moindre écart avec ce rendu.
[Unit]
Description=veille-emploi : minuterie du test de restauration (prod)

[Timer]
OnCalendar=Sun *-*-* 04:15:00
Persistent=true

[Install]
WantedBy=timers.target
FIN
}

# --- « non » : pas de sauvegarde tant que la prod n'a rien déployé ---------------------------

# prod_deployee : l'état d'une prod qui a déjà déployé une version.
prod_deployee() {
  mkdir -p "$VEILLE_EMPLOI_RACINE_ETAT/prod"
  echo "sha256:0 0.1.0 -" >"$VEILLE_EMPLOI_RACINE_ETAT/prod/deploye"
}

# serveur déclare « non » pour un projet dont la prod n'existe pas encore : la sonde et l'alerte
# s'installent, pas la sauvegarde ni son test, qui échoueraient chaque nuit sans conteneur de prod.
@test "unites_non_sans_prod_deployee_installe_sans_les_sauvegardes" {
  declarer_projet SAUVEGARDE=non TEST_RESTAURATION=non
  installer
  [ "$status" -eq 0 ]
  [ "$(find "$UNITES" -mindepth 1 -printf '%f\n' | sort)" = "$(printf '%s\n' "${SANS_SAUVEGARDE[@]}" | sort)" ]
  [[ "$stderr" == *"SAUVEGARDE=non"* ]]
  [ "$(appels_de systemctl | sed -n 2p)" = "systemctl --user enable --now veille-emploi-sonde-prod.timer veille-emploi-sonde-staging.timer" ]
  # le contrôle ne compte pas les unités de la sauvegarde comme absentes
  installer --verifier
  [ "$status" -eq 0 ]
}

# La sonde de serveur lit la sortie de --verifier strictement : des lignes « écart : … » et leur
# résumé, rien d'autre, sans quoi elle refuse de réparer. « non » n'y ajoute aucune ligne.
@test "unites_non_verifier_ne_dit_que_les_ecarts" {
  declarer_projet SAUVEGARDE=non TEST_RESTAURATION=non
  installer
  [ "$status" -eq 0 ]
  rm "$UNITES/veille-emploi-sonde-prod.timer"
  printf '# modifiée\n' >>"$UNITES/veille-emploi-sonde-staging.service"
  installer --verifier
  [ "$status" -eq 1 ]
  local ligne nombre=0
  while IFS= read -r ligne; do
    nombre=$((nombre + 1))
    case "$ligne" in
      "écart : veille-emploi-sonde-prod.timer : absente (le dépôt la prévoit)") ;;
      "écart : veille-emploi-sonde-staging.service : différente de son rendu") ;;
      *" 2 écart(s) entre les unités installées dans $UNITES et deploiement/systemd : "*) ;;
      *)
        echo "ligne inattendue : $ligne" >&2
        return 1
        ;;
    esac
  done <<<"$stderr"
  [ "$nombre" -eq 3 ]
}

# Des heures, puis « non » : les unités de la sauvegarde deviennent des orphelines, que le contrôle
# signale et que l'installation désactive avant de les retirer.
@test "unites_non_retire_les_unites_de_sauvegarde_deja_installees" {
  installer
  [ "$status" -eq 0 ]
  : >"$APPELS"
  declarer_projet SAUVEGARDE=non TEST_RESTAURATION=non
  installer --verifier
  [ "$status" -eq 1 ]
  [[ "$stderr" == *"veille-emploi-sauvegarde.timer : orpheline"* ]]
  [[ "$stderr" == *"veille-emploi-test-restauration.service : orpheline"* ]]
  installer
  [ "$status" -eq 0 ]
  [ "$(find "$UNITES" -mindepth 1 -printf '%f\n' | sort)" = "$(printf '%s\n' "${SANS_SAUVEGARDE[@]}" | sort)" ]
  [ -n "$(ligne_de 'systemctl --user disable --now veille-emploi-sauvegarde.timer')" ]
  [ -n "$(ligne_de 'systemctl --user disable --now veille-emploi-test-restauration.timer')" ]
  installer --verifier
  [ "$status" -eq 0 ]
}

# Une prod qui a déployé a des données : « non » refuse, en installation comme en contrôle, sans
# rien toucher. La sonde de prod, qui contrôle les unités à chaque passage, alerte donc jusqu'à ce
# que serveur déclare les heures. Un fichier deploye vide, ou un lien brisé, n'est pas une prod
# vierge : « non » y refuse aussi.
@test "unites_non_refuse_quand_la_prod_a_deploye" {
  installer
  [ "$status" -eq 0 ]
  local avant
  avant="$(find "$UNITES" -mindepth 1 -printf '%f\n' | sort)"
  : >"$APPELS"
  declarer_projet SAUVEGARDE=non TEST_RESTAURATION=non
  local deploye="$VEILLE_EMPLOI_RACINE_ETAT/prod/deploye" forme option
  for forme in version vide lien; do
    prod_deployee
    case "$forme" in
      vide) : >"$deploye" ;;
      lien) rm "$deploye" && ln -s "$BATS_TEST_TMPDIR/absent" "$deploye" ;;
    esac
    for option in "" --verifier; do
      # shellcheck disable=SC2086  # sans option, aucun argument
      installer $option
      [ "$status" -eq 1 ]
      [[ "$stderr" == *"SAUVEGARDE=non, mais la prod a déployé ($deploye)"* ]]
    done
    rm -f "$deploye"
  done
  [ "$(find "$UNITES" -mindepth 1 -printf '%f\n' | sort)" = "$avant" ]
  [ "$(nombre_d_appels systemctl)" -eq 0 ]
}

# Sur le serveur, rien ne pose VEILLE_EMPLOI_RACINE_ETAT : l'état de la prod se lit à son emplacement
# par défaut, celui de lib.sh.
@test "unites_non_lit_l_etat_de_la_prod_a_son_emplacement_par_defaut" {
  declarer_projet SAUVEGARDE=non TEST_RESTAURATION=non
  mkdir -p "$HOME/.local/state/veille-emploi/prod"
  echo "sha256:0 0.1.0 -" >"$HOME/.local/state/veille-emploi/prod/deploye"
  VEILLE_EMPLOI_RACINE_ETAT='' installer
  [ "$status" -eq 1 ]
  [[ "$stderr" == *"la prod a déployé ($HOME/.local/state/veille-emploi/prod/deploye)"* ]]
  [ ! -e "$UNITES" ]
  # l'état d'ailleurs ne compte pas
  VEILLE_EMPLOI_RACINE_ETAT="$BATS_TEST_TMPDIR/autre-etat" installer
  [ "$status" -eq 0 ]
}

# La sonde de prod installe les unités avec VEILLE_EMPLOI_AVANT_DEPLOIEMENT=1 juste avant de déployer :
# « non » refuse alors, même si la prod n'a encore rien déployé, et la première version de prod
# attend les heures. Avec des heures, la variable ne change rien.
@test "unites_avant_deploiement_refuse_non" {
  declarer_projet SAUVEGARDE=non TEST_RESTAURATION=non
  VEILLE_EMPLOI_AVANT_DEPLOIEMENT=1 installer
  [ "$status" -eq 1 ]
  [[ "$stderr" == *"SAUVEGARDE=non"* ]]
  [ ! -e "$UNITES" ]
  [ "$(nombre_d_appels systemctl)" -eq 0 ]
  declarer_projet SAUVEGARDE=02:45 "TEST_RESTAURATION=Sun 04:15"
  VEILLE_EMPLOI_AVANT_DEPLOIEMENT=1 installer
  [ "$status" -eq 0 ]
  [ "$(find "$UNITES" -mindepth 1 -printf '%f\n' | sort)" = "$(printf '%s\n' "${ATTENDUES[@]}" | sort)" ]
  installer --verifier
  [ "$status" -eq 0 ]
}

# --- installation ----------------------------------------------------------------------------

@test "installer_recharge_systemd_puis_active_les_minuteries" {
  installer
  [ "$status" -eq 0 ]
  [ "$(appels_de systemctl | head -n 1)" = "systemctl --user daemon-reload" ]
  [ "$(appels_de systemctl | sed -n 2p)" = "systemctl --user enable --now veille-emploi-sauvegarde.timer veille-emploi-sonde-prod.timer veille-emploi-sonde-staging.timer veille-emploi-test-restauration.timer" ]
  [ "$(nombre_d_appels systemctl)" -eq 2 ]
}

@test "installer_puis_verifier_est_conforme" {
  installer
  [ "$status" -eq 0 ]
  installer --verifier
  [ "$status" -eq 0 ]
  [ -z "$stderr" ] || [[ "$stderr" == *"conformes"* ]]
}

@test "installer_est_idempotent_et_ne_reecrit_pas_une_unite_conforme" {
  installer
  [ "$status" -eq 0 ]
  # des dates anciennes : une unité réécrite aurait la date du jour
  touch -d '2001-02-03 04:05:06' "$UNITES"/veille-emploi-*
  installer
  [ "$status" -eq 0 ]
  [ "$(stat -c '%Y' "$UNITES"/veille-emploi-* | sort -u)" = "$(date -d '2001-02-03 04:05:06' +%s)" ]
  installer --verifier
  [ "$status" -eq 0 ]
}

@test "installer_remet_une_unite_modifiee_a_son_rendu" {
  installer
  [ "$status" -eq 0 ]
  echo 'ExecStartPre=/bin/true' >>"$UNITES/veille-emploi-sonde-prod.service"
  installer --verifier
  [ "$status" -eq 1 ]
  installer
  [ "$status" -eq 0 ]
  installer --verifier
  [ "$status" -eq 0 ]
}

@test "installer_retire_les_orphelines_apres_les_avoir_desactivees_puis_est_conforme" {
  installer
  [ "$status" -eq 0 ]
  : >"$APPELS"
  printf '[Service]\nExecStart=/bin/true\n' >"$UNITES/veille-emploi-vieux.service"
  printf '[Timer]\nOnBootSec=1min\n' >"$UNITES/veille-emploi-vieux.timer"
  installer
  [ "$status" -eq 0 ]
  [ ! -e "$UNITES/veille-emploi-vieux.service" ]
  [ ! -e "$UNITES/veille-emploi-vieux.timer" ]
  # désactivées (et arrêtées) avant que le fichier disparaisse, puis rechargement
  [ -n "$(ligne_de 'systemctl --user disable --now veille-emploi-vieux.service')" ]
  [ -n "$(ligne_de 'systemctl --user disable --now veille-emploi-vieux.timer')" ]
  [ "$(ligne_de 'disable --now veille-emploi-vieux.timer')" -lt "$(ligne_de 'daemon-reload')" ]
  [ "$(ligne_de 'daemon-reload')" -lt "$(ligne_de 'enable --now')" ]
  installer --verifier
  [ "$status" -eq 0 ]
}

@test "installer_ne_touche_pas_aux_unites_des_autres_projets" {
  mkdir -p "$UNITES"
  printf '[Service]\nExecStart=/bin/true\n' >"$UNITES/autre-projet-sauvegarde.service"
  printf '[Service]\nExecStart=/bin/true\n' >"$UNITES/veille-emploiur.service"
  cp -p "$UNITES/autre-projet-sauvegarde.service" "$BATS_TEST_TMPDIR/ref-autre.service"
  installer
  [ "$status" -eq 0 ]
  diff "$UNITES/autre-projet-sauvegarde.service" "$BATS_TEST_TMPDIR/ref-autre.service"
  [ -f "$UNITES/veille-emploiur.service" ]
  aucune_ligne 'autre-projet|veille-emploiur' "$APPELS"
  installer --verifier
  [ "$status" -eq 0 ]
}

@test "installer_remplace_un_lien_symbolique_sans_ecrire_sa_cible" {
  installer
  [ "$status" -eq 0 ]
  printf 'cible a ne pas toucher\n' >"$BATS_TEST_TMPDIR/cible"
  rm "$UNITES/veille-emploi-sauvegarde.timer"
  ln -s "$BATS_TEST_TMPDIR/cible" "$UNITES/veille-emploi-sauvegarde.timer"
  installer
  [ "$status" -eq 0 ]
  [ ! -L "$UNITES/veille-emploi-sauvegarde.timer" ]
  [ "$(cat "$BATS_TEST_TMPDIR/cible")" = "cible a ne pas toucher" ]
  installer --verifier
  [ "$status" -eq 0 ]
}

@test "installer_remplace_un_dossier_portant_le_nom_d_une_unite" {
  installer
  [ "$status" -eq 0 ]
  rm "$UNITES/veille-emploi-sauvegarde.timer"
  mkdir "$UNITES/veille-emploi-sauvegarde.timer"
  : >"$UNITES/veille-emploi-sauvegarde.timer/intrus"
  installer
  [ "$status" -eq 0 ]
  [ -f "$UNITES/veille-emploi-sauvegarde.timer" ]
  installer --verifier
  [ "$status" -eq 0 ]
}

@test "installer_s_arrete_si_systemd_refuse_le_rechargement" {
  installer
  [ "$status" -eq 0 ]
  creer_double systemctl 'case "$*" in *daemon-reload*) exit 1;; esac'
  installer
  [ "$status" -ne 0 ]
}

# --- contrôle de dérive ----------------------------------------------------------------------

@test "verifier_detecte_une_unite_modifiee" {
  installer
  [ "$status" -eq 0 ]
  : >"$APPELS"
  echo 'ExecStartPre=/bin/true' >>"$UNITES/veille-emploi-sauvegarde.service"
  installer --verifier
  [ "$status" -eq 1 ]
  # la liste des écarts est sur stderr, rien sur stdout
  [[ "$stderr" == *"veille-emploi-sauvegarde.service"* ]]
  [ -z "$output" ]
  # et seule l'unité modifiée est citée
  [[ "$stderr" != *"veille-emploi-sonde-prod.service"* ]]
  # le contrôle ne modifie rien : l'unité reste modifiée, systemd n'est pas sollicité
  tail -n 1 "$UNITES/veille-emploi-sauvegarde.service" | grep -Fx 'ExecStartPre=/bin/true'
  [ "$(nombre_d_appels systemctl)" -eq 0 ]
}

@test "verifier_detecte_une_unite_orpheline" {
  installer
  [ "$status" -eq 0 ]
  : >"$APPELS"
  printf '[Service]\nExecStart=/bin/true\n' >"$UNITES/veille-emploi-vieux.service"
  installer --verifier
  [ "$status" -eq 1 ]
  [[ "$stderr" == *"veille-emploi-vieux.service"* ]]
  [ -z "$output" ]
  # le contrôle ne supprime rien et ne touche pas à systemd
  [ -f "$UNITES/veille-emploi-vieux.service" ]
  [ "$(nombre_d_appels systemctl)" -eq 0 ]
}

@test "verifier_detecte_une_unite_absente" {
  installer
  [ "$status" -eq 0 ]
  rm "$UNITES/veille-emploi-test-restauration.timer"
  installer --verifier
  [ "$status" -eq 1 ]
  [[ "$stderr" == *"veille-emploi-test-restauration.timer"* ]]
  [[ "$stderr" == *"absente"* ]]
}

@test "verifier_sur_un_hote_vierge_signale_toutes_les_unites_absentes" {
  installer --verifier
  [ "$status" -eq 1 ]
  local unite
  for unite in "${ATTENDUES[@]}"; do
    [[ "$stderr" == *"$unite"* ]]
  done
  # le dossier n'a pas été créé par un simple contrôle
  [ ! -e "$UNITES" ]
}

# `systemctl --user edit` ne modifie pas le fichier : il crée un dossier de surcharge.
@test "verifier_detecte_un_dossier_de_surcharge_et_installer_le_retire" {
  installer
  [ "$status" -eq 0 ]
  mkdir "$UNITES/veille-emploi-sonde-prod.service.d"
  printf '[Service]\nExecStart=\nExecStart=/bin/true\n' >"$UNITES/veille-emploi-sonde-prod.service.d/override.conf"
  installer --verifier
  [ "$status" -eq 1 ]
  [[ "$stderr" == *"veille-emploi-sonde-prod.service.d"* ]]
  installer
  [ "$status" -eq 0 ]
  [ ! -e "$UNITES/veille-emploi-sonde-prod.service.d" ]
  installer --verifier
  [ "$status" -eq 0 ]
}

@test "verifier_detecte_un_lien_symbolique_meme_vers_un_contenu_identique" {
  installer
  [ "$status" -eq 0 ]
  cp "$UNITES/veille-emploi-sauvegarde.timer" "$BATS_TEST_TMPDIR/copie.timer"
  ln -sf "$BATS_TEST_TMPDIR/copie.timer" "$UNITES/veille-emploi-sauvegarde.timer"
  installer --verifier
  [ "$status" -eq 1 ]
  [[ "$stderr" == *"veille-emploi-sauvegarde.timer"* ]]
}

@test "verifier_liste_tous_les_ecarts_d_un_coup" {
  installer
  [ "$status" -eq 0 ]
  echo '# main' >>"$UNITES/veille-emploi-sonde-prod.timer"
  rm "$UNITES/veille-emploi-sonde-staging.service"
  : >"$UNITES/veille-emploi-vieux.timer"
  installer --verifier
  [ "$status" -eq 1 ]
  [[ "$stderr" == *"veille-emploi-sonde-prod.timer"* ]]
  [[ "$stderr" == *"veille-emploi-sonde-staging.service"* ]]
  [[ "$stderr" == *"veille-emploi-vieux.timer"* ]]
}

@test "verifier_suit_le_gabarit_du_clone" {
  installer
  [ "$status" -eq 0 ]
  # un commit change un gabarit : les unités installées sont désormais en retard sur le dépôt
  sed -i 's/^Nice=10$/Nice=5/' "$CLONE/deploiement/systemd/veille-emploi-sauvegarde.service.in"
  installer --verifier
  [ "$status" -eq 1 ]
  [[ "$stderr" == *"veille-emploi-sauvegarde.service"* ]]
  installer
  [ "$status" -eq 0 ]
  grep -Fx 'Nice=5' "$UNITES/veille-emploi-sauvegarde.service"
  installer --verifier
  [ "$status" -eq 0 ]
}

@test "installer_unites_refuse_une_option_inconnue" {
  installer --forcer
  [ "$status" -eq 64 ]
  installer --verifier --verifier
  [ "$status" -eq 64 ]
  [ ! -e "$UNITES" ]
  [ "$(nombre_d_appels systemctl)" -eq 0 ]
}

# --- alerte ----------------------------------------------------------------------------------

@test "alerter_traduit_le_nom_d_unite" {
  creer_double curl
  preparer_secrets_de_test prod HC_SAUVEGARDE=https://hc.example/ping/sauvegarde-prod
  run bash "$CLONE/deploiement/alerter.sh" veille-emploi-sauvegarde.service
  [ "$status" -eq 0 ]
  [ "$(envois_supervision)" = "curl -fsS -m 10 --retry 3 --data-raw échec de veille-emploi-sauvegarde.service https://hc.example/ping/sauvegarde-prod/fail" ]
}

# Chaque unité part vers la bonne variable de signal, avec les secrets de son environnement : la
# sonde de staging et celle de prod ont chacune leur HC_SONDE.
@test "alerter_route_chaque_unite_vers_son_environnement_et_son_signal" {
  creer_double curl
  preparer_secrets_de_test prod JETON=jeton-prod HC_SONDE=https://hc.example/prod/sonde \
    HC_SAUVEGARDE=https://hc.example/prod/sauvegarde HC_TEST_RESTAURATION=https://hc.example/prod/test
  preparer_secrets_de_test staging JETON=jeton-staging HC_SONDE=https://hc.example/staging/sonde
  local cas unite adresse
  for cas in \
    'veille-emploi-sonde-prod.service https://hc.example/prod/sonde/fail' \
    'veille-emploi-sonde-staging.service https://hc.example/staging/sonde/fail' \
    'veille-emploi-sauvegarde.service https://hc.example/prod/sauvegarde/fail' \
    'veille-emploi-test-restauration.service https://hc.example/prod/test/fail'; do
    unite="${cas%% *}"
    adresse="${cas#* }"
    : >"$APPELS"
    run bash "$CLONE/deploiement/alerter.sh" "$unite"
    [ "$status" -eq 0 ]
    [ "$(envois_supervision)" = "curl -fsS -m 10 --retry 3 --data-raw échec de $unite $adresse" ]
  done
}

@test "alerter_refuse_une_unite_inconnue_sans_rien_envoyer" {
  creer_double curl
  preparer_secrets_de_test prod HC_SONDE=https://hc.example/prod/sonde
  run bash "$CLONE/deploiement/alerter.sh" veille-emploi-inconnue.service
  [ "$status" -eq 64 ]
  [[ "$output" == *"veille-emploi-inconnue.service"* ]]
  [ "$(nombre_d_appels curl)" -eq 0 ]
  run bash "$CLONE/deploiement/alerter.sh"
  [ "$status" -eq 64 ]
  run bash "$CLONE/deploiement/alerter.sh" veille-emploi-sonde-prod.service veille-emploi-sauvegarde.service
  [ "$status" -eq 64 ]
  [ "$(nombre_d_appels curl)" -eq 0 ]
}

# Le nom de l'unité vient de `%n` ; une unité sans secrets ne doit pas passer pour un succès.
@test "alerter_echoue_si_les_secrets_manquent" {
  creer_double curl
  run bash "$CLONE/deploiement/alerter.sh" veille-emploi-sauvegarde.service
  [ "$status" -eq 3 ]
  [ "$(nombre_d_appels curl)" -eq 0 ]
}

@test "alerter_echoue_si_l_envoi_echoue" {
  creer_double curl 'exit 22'
  preparer_secrets_de_test prod HC_SAUVEGARDE=https://hc.example/ping/sauvegarde-prod
  run bash "$CLONE/deploiement/alerter.sh" veille-emploi-sauvegarde.service
  [ "$status" -eq 22 ]
}

@test "alerter_ne_laisse_pas_l_adresse_dans_une_trace" {
  creer_double curl
  preparer_secrets_de_test prod HC_SAUVEGARDE=https://hc.example/ping/uuid-secret-9 JETON=jeton-secret-9
  run bash -x "$CLONE/deploiement/alerter.sh" veille-emploi-sauvegarde.service
  [ "$status" -eq 0 ]
  [ "$(nombre_d_appels curl)" -eq 1 ]
  [[ "$output" != *uuid-secret-9* ]]
  [[ "$output" != *jeton-secret-9* ]]
}

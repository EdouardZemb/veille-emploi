"""Ligne de commande.

    veille init            prepare la base et les cles
    veille lien            affiche un lien de connexion, valable 24 h
    veille passkeys        liste les passkeys ; --retirer <id> en retire une
    veille collecter       lance tous les collecteurs actifs (c'est le timer)
    veille rescorer        recalcule tous les scores apres edition des criteres
    veille etat            resume l'etat de la base
    veille tester-mail     diagnostic IMAP : liste les dossiers, essaie un parsing
    veille instantane      creer | verifier un instantane de /donnees (sauvegarde)
    veille config          verifier un dossier de configuration
    veille servir          demarre la console (developpement)
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

# Charge config/.env avant tout le reste : les collecteurs lisent os.environ.
#
# ATTENTION A L'ORDRE : `config.py` calcule ses chemins (base, kit, dossiers)
# AU MOMENT DE SON IMPORT. Si on importait config ici pour connaitre la racine,
# les chemins seraient figes avant que .env soit lu, et VEILLE_KIT serait
# ignore. On deduit donc la racine de ce fichier-ci, sans rien importer.
def _charger_env() -> None:
    racine = Path(__file__).resolve().parent.parent.parent
    chemin = Path(os.environ.get("VEILLE_ENV", racine / "config" / ".env"))
    if not chemin.exists():
        return
    for ligne in chemin.read_text(encoding="utf-8").splitlines():
        ligne = ligne.strip()
        if not ligne or ligne.startswith("#") or "=" not in ligne:
            continue
        cle, _, valeur = ligne.partition("=")
        os.environ.setdefault(cle.strip(), valeur.strip().strip('"').strip("'"))


_charger_env()


def _journalisation(verbeux: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbeux else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    # Les etapes de chaque PDF (huit lignes INFO) noieraient le journal de la
    # console sous `veille servir` ; ses avertissements restent.
    logging.getLogger("weasyprint.progress").setLevel(logging.WARNING)


# --------------------------------------------------------------------------


def cmd_init(args: argparse.Namespace) -> int:
    from . import db, notifications

    db.initialiser()
    print(f"Base prete : {db.CHEMIN_DB}")
    if not notifications.CHEMIN_VAPID.exists():
        cles = notifications.generer_vapid()
        print(f"Cles VAPID generees : {notifications.CHEMIN_VAPID}")
        print(f"  cle publique : {cles.publique}")
    else:
        print(f"Cles VAPID deja presentes : {notifications.CHEMIN_VAPID}")
    return 0


def cmd_factice(args: argparse.Namespace) -> int:
    from . import db, factice

    db.initialiser()
    try:
        n = factice.charger()
    except factice.BaseNonVide:
        print("La base contient déjà des offres : le jeu factice ne se charge que dans une base vide.")
        return 1
    print(f"Jeu factice chargé : {n} offres.")
    return 0


def cmd_lien(args: argparse.Namespace) -> int:
    from . import auth, db, passkeys

    try:
        origine, _ = passkeys.origine_attendue()
    except passkeys.OrigineInconnue:
        print("VEILLE_URL n'est pas définie : impossible de fabriquer un lien.", file=sys.stderr)
        return 1
    db.initialiser()
    jeton = auth.creer_lien("serveur")
    print("Lien valable 24 h, à ouvrir sur l'appareil à enregistrer :")
    print(f"{origine}/lien#{jeton}")
    return 0


def cmd_passkeys(args: argparse.Namespace) -> int:
    """Liste les passkeys ; `--retirer` en retire une et ferme toutes les sessions.

    La console montre les passkeys mais n'en retire aucune : retirer la seule
    passkey depuis l'ecran qu'elle protege enfermerait dehors. Ici, `veille lien`
    fait rentrer.
    """
    from . import auth, db

    db.initialiser()
    if args.retirer is not None:
        if not auth.retirer_passkey(args.retirer):
            print(f"Aucune passkey n'a l'id {args.retirer} : `veille passkeys` les liste.",
                  file=sys.stderr)
            return 1
        print(f"Passkey {args.retirer} retirée. Toutes les sessions sont fermées : "
              "reconnecte-toi avec ta passkey.")
        if db.compter_passkeys() == 0:
            print("Plus aucune passkey : `veille lien` en enregistre une.")
        return 0
    passkeys = db.lister_passkeys()
    if not passkeys:
        print("Aucune passkey enregistrée : `veille lien` en enregistre une.")
        return 0
    print(f"{'id':>4}  {'appareil':<10}  {'créée le':<25}  dernier usage")
    for p in passkeys:
        print(f"{p['id']:>4}  {p['appareil']:<10}  {p['cree_le']:<25}  "
              f"{p['utilisee_le'] or 'jamais'}")
    print("Celle d'un appareil perdu se retire par : veille passkeys --retirer <id>")
    return 0


def _sans_configuration() -> int | None:
    """2 (et le message sur la sortie d'erreur) quand aucune configuration n'est designee."""
    from . import config

    try:
        config.exiger_designee()
    except config.ConfigurationInvalide as e:
        print(e, file=sys.stderr)
        return 2
    return None


def cmd_collecter(args: argparse.Namespace) -> int:
    refus = _sans_configuration()
    if refus is not None:
        return refus

    from . import collecte

    collecte.collecter(
        jours=args.jours,
        sources=set(args.source) if args.source else None,
        notifier=not args.sans_notification,
        sortie=print,
        erreur=lambda ligne: print(ligne, file=sys.stderr),
    )
    return 0


def cmd_rescorer(args: argparse.Namespace) -> int:
    refus = _sans_configuration()
    if refus is not None:
        return refus

    from . import db

    recalculees, ecartees, remises, differees = db.rescorer_tout()
    print(f"{recalculees} offre(s) recalculee(s) avec les criteres actuels.")
    if ecartees:
        print(f"  {ecartees} offre(s) partie(s) au rebut : les nouveaux criteres les rejettent.")
    if differees:
        print(f"  {differees} offre(s) mise(s) de cote : recevables plus tard, "
              f"consultables par le filtre Statut.")
    if remises:
        print(f"  {remises} offre(s) revenue(s) dans le flux.")
    if ecartees or remises or differees:
        print("  (tes propres decisions de tri n'ont pas ete touchees)")
    return 0


def cmd_verifier(args: argparse.Namespace) -> int:
    """Les annonces collectees sont-elles encore en ligne ?

    Archive seulement ce qui est PROUVE retire, apres plusieurs verifications
    espacees. Ne sonde jamais un site qui l'interdit, et n'archive jamais une
    offre qu'Edouard a triee ou sur laquelle il a genere un dossier.
    """
    if not args.sans_enrichir:
        # enrichir rescore les offres : comme `rescorer`, jamais avec l'exemple
        refus = _sans_configuration()
        if refus is not None:
            return refus

    from . import verification

    r = verification.passe(limite=args.limite, enrichir=not args.sans_enrichir)
    print(f"{len(r.sondees)} offre(s) examinee(s).")
    for verdict, n in sorted(r.par_verdict.items(), key=lambda kv: -kv[1]):
        print(f"  {verdict:16} {n}")
    if r.non_sondables:
        print()
        print(f"{r.non_sondables} offre(s) sur un site qui interdit la lecture "
              f"automatisee : jamais archivees, a verifier a la main depuis la console.")
    if r.enrichies:
        print(f"  {len(r.enrichies)} offre(s) completees au passage — leur score a change.")
    if r.signalees:
        print(f"  {len(r.signalees)} offre(s) probablement retirees mais CONSERVEES "
              f"(tu les as triees ou tu as genere un dossier).")
    if r.archivees:
        print()
        print(f"{len(r.archivees)} offre(s) archivees. Onglet Archive pour les voir, "
              f"« Remettre dans le flux » si l'une y est a tort.")
    else:
        print()
        print("Aucune archive : rien n'etait prouve.")
    return 0


def cmd_etat(args: argparse.Namespace) -> int:
    from . import db, passkeys

    db.initialiser()
    try:
        origine, _ = passkeys.origine_attendue()
    except passkeys.OrigineInconnue:
        print("Connexion : indisponible, VEILLE_URL n'est pas définie")
    else:
        n = db.compter_passkeys()
        print(f"Connexion : {n} passkey{'s' if n > 1 else ''}, origine {origine}")
    e = db.entonnoir()
    print(f"Offres en base : {e['total']}")
    for statut, n in sorted(e["par_statut"].items(), key=lambda kv: -kv[1]):
        print(f"  {statut:22} {n}")
    print(f"\nCandidatures envoyees : {e['envoyees']}  |  reponses : {e['repondues']}  |  taux : {e['taux_reponse_global']}%")

    if e["par_source"]:
        print("\nRendement par source :")
        print(f"  {'source':22} {'collectees':>10} {'retenues':>9} {'candidatures':>13}")
        for s in e["par_source"]:
            print(f"  {s['source']:22} {s['collectees']:>10} {s['retenues']:>9} {s['candidatures']:>13}")

    if e["motifs_ecartement"]:
        print("\nMotifs d'ecartement (ce que le scoring rate) :")
        for m in e["motifs_ecartement"][:15]:
            print(f"  {m['n']:>3}x  (score moyen {m['score_moyen']:>6})  {m['motif']}")

    with db.connexion() as cx:
        lignes = cx.execute(
            "SELECT source, derniere_execution, dernier_resultat FROM etat_collecte ORDER BY source"
        ).fetchall()
    if lignes:
        print("\nDerniers passages :")
        for l in lignes:
            alerte = "  <-- A REGARDER" if "ECHEC" in (l["dernier_resultat"] or "") else ""
            print(f"  {l['source']:14} {l['derniere_execution'] or '?':20} {l['dernier_resultat'] or ''}{alerte}")

    relances = db.relances_dues()
    if relances:
        print(f"\nRelances dues : {len(relances)}")
        for r in relances[:10]:
            print(f"  {r['date_relance_due']}  {r['titre'][:50]} | {r.get('employeur') or '?'}")
    return 0


def cmd_decouvrir_expediteurs(args: argparse.Namespace) -> int:
    """Propose les expediteurs d'alertes reellement presents dans la boite.

    Ma liste par defaut est une supposition tant que personne n'a regarde ta
    boite. Cette commande cherche des SUJETS typiques d'alerte et ne rapporte
    que les ADRESSES trouvees, avec un exemple de sujet.

    Elle ne telecharge QUE les en-tetes De: et Objet: - jamais le corps des
    messages.
    """
    import collections
    import email as _email
    import email.policy
    import re as _re

    from .collectors.courriel import BoiteIMAP, _decoder

    MOTS = [
        "job alert", "jobs for you", "new jobs", "job recommendations",
        "alerte emploi", "offres d'emploi", "nouvelles offres", "offre d'emploi",
        "job-abo", "jobabo", "neue jobs", "stellenangebote", "job alarm",
        "recrutement", "votre recherche",
    ]

    try:
        boite = BoiteIMAP()
    except RuntimeError as exc:
        print(f"Configuration incomplete : {exc}", file=sys.stderr)
        return 1

    with boite as b:
        dossier = b.dossier_tous_les_messages()
        b._ouvrir(dossier)
        print(f"Recherche dans « {dossier} » sur les {args.jours} derniers jours.")
        print("Seuls les en-tetes De: et Objet: sont lus.\n")

        from datetime import date as _date, timedelta as _td

        depuis = (_date.today() - _td(days=args.jours)).strftime("%d-%b-%Y")
        uids: dict[bytes, None] = {}
        for mot in MOTS:
            code, donnees = b._cx.uid("SEARCH", None, "SUBJECT", f'"{mot}"', "SINCE", depuis)
            if code == "OK" and donnees and donnees[0]:
                for u in donnees[0].split():
                    uids.setdefault(u, None)

        if not uids:
            print("Aucun message d'alerte trouve. Soit les alertes ne sont pas encore")
            print("creees sur les sites, soit leurs sujets ne ressemblent a aucun de")
            print("ceux que je cherche. Dans le doute, ouvre une alerte a la main et")
            print("releve son expediteur.")
            return 0

        compte: collections.Counter = collections.Counter()
        exemples: dict[str, str] = {}
        for uid in list(uids)[: args.plafond]:
            code, charge = b._cx.uid(
                "FETCH", uid, "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT)])"
            )
            if code != "OK" or not charge or not charge[0]:
                continue
            entetes = _email.message_from_bytes(charge[0][1], policy=_email.policy.default)
            brut = _decoder(entetes.get("From"))
            m = _re.search(r"[\w.+-]+@[\w.-]+", brut)
            if not m:
                continue
            adresse = m.group(0).lower()
            compte[adresse] += 1
            exemples.setdefault(adresse, _decoder(entetes.get("Subject"))[:66])

    connus = {e.lower() for e in boite.expediteurs}

    def deja_couvert(adresse: str) -> bool:
        return any(c in adresse for c in connus)

    print(f"{len(compte)} expediteur(s) distinct(s) sur {sum(compte.values())} message(s) :\n")
    print(f"  {'adresse':44} {'nb':>4}  etat")
    print(f"  {'-'*44} {'-'*4}  ----")
    a_ajouter = []
    for adresse, n in compte.most_common():
        etat = "deja dans ta liste" if deja_couvert(adresse) else "A AJOUTER"
        if etat == "A AJOUTER":
            a_ajouter.append(adresse)
        print(f"  {adresse:44} {n:>4}  {etat}")
        print(f"    ex. « {exemples[adresse]} »")

    if a_ajouter:
        print("\nA coller dans le sources.yaml de ta configuration (VEILLE_CONFIG), bloc courriel, "
              "sous `expediteurs:` :")
        for a in a_ajouter:
            print(f'    - "{a}"')
    else:
        print("\nTa liste couvre tout ce qui a ete trouve.")
    return 0


def cmd_tester_sources(args: argparse.Namespace) -> int:
    """Verifie chaque source : joignable ? identifiants ? repond-elle ?

    Pensee pour etre lancee AVANT d'avoir tous les identifiants : ce qui manque
    est dit explicitement, ce qui marche deja est prouve.
    """
    import httpx

    from .collectors import france_travail
    from .config import masquer, charger_sources

    sources = charger_sources()
    souci = 0

    # --- France Travail -------------------------------------------------
    print("=== France Travail (API officielle) ===")
    recherches = (sources.get("france_travail") or {}).get("recherches", [])
    print(f"  recherches configurees : {len(recherches)}")
    identifiants = bool(os.environ.get("FT_CLIENT_ID") and os.environ.get("FT_CLIENT_SECRET"))

    try:
        # Sans identifiants valides, l'API repond 400/401 : c'est deja la preuve
        # que l'URL est bonne et le service joignable.
        rep = httpx.post(
            france_travail.URL_TOKEN,
            params={"realm": "/partenaire"},
            data={
                "grant_type": "client_credentials",
                "client_id": os.environ.get("FT_CLIENT_ID", "verification"),
                "client_secret": os.environ.get("FT_CLIENT_SECRET", "verification"),
                "scope": france_travail.SCOPES,
            },
            timeout=20,
        )
        print(f"  service de jetons      : joignable (HTTP {rep.status_code})")
        if rep.status_code == 200:
            print("  identifiants           : VALIDES")
            client = france_travail.ClientFranceTravail()
            try:
                lot = client.rechercher({"motsCles": "test", "departement": "67"}, plafond=10)
                print(f"  recherche d'essai      : {len(lot)} offre(s) rendues")
                if lot:
                    o = france_travail.convertir(lot[0])
                    print(f"    exemple : {o.titre[:56]} | {o.lieu[:30]}")
            finally:
                client.close()
        elif identifiants:
            print(f"  identifiants           : REFUSES -> {masquer(rep.text)[:160]}")
            souci += 1
        else:
            print("  identifiants           : absents (FT_CLIENT_ID / FT_CLIENT_SECRET)")
            print("    -> a creer sur https://francetravail.io, voir docs/DEMARRAGE.md")
            souci += 1
    except Exception as exc:
        print(f"  service de jetons      : INJOIGNABLE ({masquer(str(exc))})")
        souci += 1

    # --- Arbeitnow ------------------------------------------------------
    print("\n=== Arbeitnow (API publique, sans identifiants) ===")
    try:
        rep = httpx.get(
            "https://www.arbeitnow.com/api/job-board-api",
            timeout=25, headers={"Accept": "application/json"},
        )
        lot = (rep.json() or {}).get("data", [])
        print(f"  joignable              : HTTP {rep.status_code}, {len(lot)} offre(s) sur la page 1")
    except Exception as exc:
        print(f"  INJOIGNABLE ({exc})")
        souci += 1

    # --- Flux RSS -------------------------------------------------------
    flux = [f for f in (sources.get("rss") or []) if f.get("actif", True)]
    print(f"\n=== Flux RSS ({len(flux)} declare(s)) ===")
    if not flux:
        print("  aucun flux configure - normal, a remplir au fur et a mesure")
    for f in flux:
        try:
            import feedparser

            analyse = feedparser.parse(f["url"], agent="veille-emploi/1.0 (usage personnel)")
            n = len(analyse.entries)
            etat = f"{n} entree(s)" if n else "VIDE ou illisible"
            print(f"  {f.get('cle', '?'):22} {etat}")
            if not n:
                souci += 1
        except Exception as exc:
            print(f"  {f.get('cle', '?'):22} ECHEC ({masquer(str(exc))})")
            souci += 1

    # --- Canal mail -----------------------------------------------------
    print("\n=== Alertes mail (IMAP) ===")
    bloc_mail = sources.get("courriel") or {}
    mode = os.environ.get("VEILLE_IMAP_MODE") or bloc_mail.get("mode", "union")
    expediteurs = bloc_mail.get("expediteurs") or []
    utilisateur = os.environ.get("VEILLE_IMAP_UTILISATEUR", "")
    motdepasse = os.environ.get("VEILLE_IMAP_MOTDEPASSE", "")
    libelle = os.environ.get("VEILLE_IMAP_DOSSIER") or bloc_mail.get("libelle", "veille-emploi")

    print(f"  compte                 : {utilisateur or '(absent)'}")
    print(f"  mode                   : {mode}")
    if mode in ("expediteurs", "union"):
        print(f"  expediteurs connus     : {len(expediteurs)}")
    if mode in ("libelle", "union"):
        appoint = " (filet, facultatif)" if mode == "union" else " (obligatoire dans ce mode)"
        print(f"  libelle                : {libelle}{appoint}")
    if mode == "expediteurs" or (mode == "union" and expediteurs):
        print("  -> AUCUNE regle Gmail a creer : le serveur cherche par expediteur")

    if not motdepasse:
        print("  mot de passe           : absent")
        print("    -> mot de passe d'application Gmail, voir docs/DEMARRAGE.md")
        print("    -> c'est la SEULE chose que personne ne peut faire a ta place")
        souci += 1
    else:
        print("  mot de passe           : present -> lance `veille tester-mail`")

    print(f"\n{'Tout est pret.' if not souci else f'{souci} point(s) a regler avant collecte complete.'}")
    return 0


def cmd_kit(args: argparse.Namespace) -> int:
    """Montre ce que contient le kit et ce qui partirait pour chaque contexte."""
    from .config import CHEMIN_KIT
    from .dossier import PIECES, _choisir_lettre, _piece_convient

    print(f"Kit lu depuis : {CHEMIN_KIT}")
    if not CHEMIN_KIT.exists():
        print("  -> ce dossier n'existe pas. Renseigne VEILLE_KIT dans config/.env")
        return 1

    lettres = sorted(p.name for p in CHEMIN_KIT.glob("lettre*.md"))
    pieces = sorted(p for p in CHEMIN_KIT.iterdir() if p.is_file() and p.suffix.lower() in PIECES)

    print(f"\nLettres trouvees ({len(lettres)}) :")
    for l in lettres or ["  (aucune - la generation echouera)"]:
        print(f"  {l}")

    print(f"\nPieces trouvees ({len(pieces)}) :")
    for p in pieces or []:
        etiquettes = [e for e in p.name.split(".")[1:-1]]
        marque = f"  [{', '.join(etiquettes)}]" if etiquettes else "  [toujours jointe]"
        print(f"  {p.name}{marque}")
    if not pieces:
        print("  (aucune)")

    print("\nCe qui partirait, selon l'offre :")
    exemples = [
        ("offre francaise", {"titre": "Ingenieur QA", "lieu": "Strasbourg",
                             "description": "Vous rejoindrez notre equipe et vous serez en charge des tests."}),
        ("offre suisse en anglais", {"titre": "Test Engineer", "lieu": "Basel, Switzerland",
                                     "description": "You will join our team and you will own the test strategy with us."}),
    ]
    for etiquette, offre in exemples:
        from .dossier import detecter_langue, detecter_pays

        langue, pays = detecter_langue(offre), detecter_pays(offre)
        retenues = [p.name for p in pieces if _piece_convient(p, langue, pays)]
        lettre, alerte = _choisir_lettre(offre)
        print(f"\n  {etiquette} (detectee {langue}/{pays})")
        print(f"    lettre : {lettre.name if lettre else 'AUCUNE'}")
        if alerte:
            print(f"    ! {alerte}")
        print(f"    pieces : {', '.join(retenues) or 'aucune'}")

    print(
        "\nConvention de nommage : etiquettes separees par des points avant l'extension.\n"
        "  cv.fr.pdf            -> offres en francais\n"
        "  dossier.ch.en.pdf    -> offres suisses redigees en anglais\n"
        "  annexe-technique.pdf -> toujours jointe"
    )
    return 0


def cmd_empreintes_kit(args: argparse.Namespace) -> int:
    """Fige, ou vérifie, l'état des pièces du kit.

    La référence vit dans le dossier de configuration désigné (`empreintes-kit.json`), pas
    dans le code. Elle n'est JAMAIS recalculée par les tests : la mettre à jour est un geste
    volontaire, et c'est tout l'intérêt.

    Sans configuration désignée, la commande refuse (code 2), comme `collecter` : la
    référence serait celle de l'exemple, chaque pièce du kit réel y sortirait « NOUVEAU », et
    `--mettre-a-jour` écrirait la référence du kit réel dans `exemple/`.
    """
    refus = _sans_configuration()
    if refus is not None:
        return refus

    from . import empreintes

    etat = empreintes.etat()
    if etat["kit"] is None or etat["raison"]:
        print(f"Kit indisponible : {etat['raison']}")
        print("Rien a figer. Ce n'est pas une divergence.")
        return 0

    print(f"Kit        : {etat['kit']}")
    print(f"Reference  : {empreintes.REFERENCE}")
    print(f"            {etat['reference']} piece(s) figee(s), "
          f"{etat['lues']} piece(s) sur le disque")
    print()

    if args.mettre_a_jour:
        lu = empreintes.calculer(empreintes.dossier_kit())
        anciens = empreintes.lire_reference()
        empreintes.ecrire_reference(lu, note=args.note or "")
        print(f"Reference reecrite : {len(lu)} piece(s).")
        for e in empreintes.comparer(anciens, lu):
            print(f"  {e.nature:8} {e.fichier}")
        print()
        print("Dis dans ton message de validation CE QUI a change et POURQUOI.")
        return 0

    if not etat["ecarts"]:
        print("Aucun ecart : le kit est celui qui a ete valide.")
        return 0

    print(f"{len(etat['ecarts'])} ECART(S) :")
    for e in etat["ecarts"]:
        print(f"  - {e}")
        print()
    return 1


def cmd_tester_notification(args: argparse.Namespace) -> int:
    """Eprouve les deux canaux separement et dit lequel marche."""
    from . import db, notifications

    db.initialiser()
    print("--- Canal 1 : push web ---")
    cles = notifications.charger_vapid()
    if not cles:
        print("  cles VAPID absentes : lance `veille init`")
    else:
        print(f"  cles VAPID presentes (sujet {cles.sujet})")
    abonnements = db.lister_abonnements()
    print(f"  appareils abonnes : {len(abonnements)}")
    if not abonnements:
        print("  -> aucun appareil. Il faut d'abord ouvrir la console en HTTPS sur le")
        print("     tailnet, puis appuyer sur 'Notifications'. Voir docs/DEMARRAGE.md.")
    else:
        ok, ko = notifications.envoyer_push(
            "Veille emploi", "Essai du canal push.", url="/"
        )
        print(f"  envoyes : {ok} | echecs : {ko}")

    print("\n--- Canal 2 : repli mail ---")
    hote, port, utilisateur, motdepasse = notifications._reglages_smtp()
    dest = os.environ.get("VEILLE_MAIL_DESTINATAIRE", "")
    print(f"  serveur      : {hote}:{port}")
    print(f"  compte       : {utilisateur or '(aucun)'}")
    print(f"  destinataire : {dest or '(aucun)'}")
    if not (utilisateur and motdepasse and dest):
        print("  -> configuration incomplete, voir config/.env")
        return 1
    if not args.envoyer:
        print("  -> ajoute --envoyer pour expedier reellement un message d'essai")
        return 0
    remis = notifications.envoyer_mail(
        "[Veille emploi] essai de notification",
        "Si tu lis ceci, le repli mail fonctionne.\n\n"
        "Il ne sert que quand aucun push n'a pu partir : appareil hors ligne,\n"
        "permissions de notification revoquees, ou telephone laisse de cote.",
    )
    print(f"  remise : {'OK' if remis else 'ECHEC (voir le message ci-dessus)'}")
    return 0 if remis else 1


def cmd_tester_mail(args: argparse.Namespace) -> int:
    """Diagnostic du canal mail, etape par etape."""
    from .collectors.courriel import BoiteIMAP
    from .collectors.parsers import analyser

    # --- Mode hors ligne : analyser un .eml enregistre -------------------
    # Le jour ou une alerte est mal decoupee, enregistre le mail depuis Gmail
    # ("Afficher l'original" -> Telecharger) et passe-le ici : on voit
    # exactement ce que le parseur en tire, sans toucher a la boite.
    if args.fichier:
        import email as _email
        import email.policy

        from .collectors.courriel import _corps, _decoder, convertir
        from .collectors.liens import resoudre
        from .scoring import scorer

        chemin = Path(args.fichier)
        if not chemin.exists():
            print(f"Fichier introuvable : {chemin}", file=sys.stderr)
            return 1

        msg = _email.message_from_bytes(chemin.read_bytes(), policy=_email.policy.default)
        exp, suj = _decoder(msg.get("From")), _decoder(msg.get("Subject"))
        html, texte = _corps(msg)
        parseur, annonces = analyser(html, texte, exp, suj)

        print(f"Fichier  : {chemin.name}")
        print(f"De       : {exp[:80]}")
        print(f"Sujet    : {suj[:80]}")
        print(f"Parseur  : {parseur}")
        print(f"Annonces : {len(annonces)}\n")

        import httpx

        with httpx.Client(timeout=10.0, follow_redirects=True) as client:
            for i, a in enumerate(annonces, 1):
                offre = convertir(a, parseur, exp, None, client) if args.reseau else None
                print(f"{i:>3}. {a.titre[:66]}")
                print(f"     employeur : {a.employeur or '(non trouve)'}")
                print(f"     lieu      : {a.lieu or '(non trouve)'}")
                print(f"     lien brut : {a.url[:78]}")
                lien = resoudre(a.url, autoriser_reseau=args.reseau)
                print(f"     canonique : {lien[:78] or '(non resolu)'}")
                if offre is not None:
                    scorer(offre)
                    print(f"     score     : {offre.score:g}"
                          f"{'  [donnees partielles]' if offre.donnees_partielles else ''}")
                    for c in offre.explication:
                        print(f"                 {c.points:>+6}  {c.libelle[:52]}")
                print()
        if not annonces:
            print("AUCUNE ANNONCE EXTRAITE.")
            print("Si le mail en contient, c'est que le format n'est pas reconnu :")
            print("  1. copie src/veille/collectors/parsers/generique.py")
            print("  2. adapte reconnait() et extraire()")
            print("  3. inscris la classe dans parsers/__init__.py, avant ParseurGenerique")
        return 0

    try:
        boite = BoiteIMAP()
    except RuntimeError as exc:
        print(f"Configuration incomplete : {exc}", file=sys.stderr)
        return 1

    import email as _email
    import email.policy

    from .collectors.courriel import _corps, _decoder

    print(f"Connexion a {boite.hote} en tant que {boite.utilisateur}...")
    try:
        with boite as b:
            print("Connexion OK.")
            print(f"Serveur Gmail (recherche native) : {'oui' if b.gmail else 'non'}")
            print(f"Mode de collecte : {b.mode}\n")

            print("Dossiers disponibles :")
            for attrs, nom in b.lister_dossiers():
                roles = " ".join(sorted(a for a in attrs if a != "\\HasNoChildren"))
                marque = "  <-- libelle configure" if nom == b.libelle else ""
                print(f"  {nom:44} {roles}{marque}")

            try:
                plan = b.passes()
            except RuntimeError as exc:
                print(f"\nARRET : {exc}", file=sys.stderr)
                return 1

            print(f"\n{len(plan)} recherche(s) prevue(s) :")
            for p in plan:
                print(f"  - {p.description}  (dossier « {p.dossier} »)")

            total = 0
            for p in plan:
                print(f"\n=== {p.description} ===")
                examines = 0
                for uid, msg in b.messages(p, args.jours):
                    exp, suj = _decoder(msg.get("From")), _decoder(msg.get("Subject"))
                    html, texte = _corps(msg)
                    parseur, annonces = analyser(html, texte, exp, suj)
                    examines += 1
                    total += len(annonces)
                    print(f"\n[{uid}] {suj[:68]}")
                    print(f"     de : {exp[:68]}")
                    print(f"     parseur : {parseur} -> {len(annonces)} annonce(s)")
                    for a in annonces[: args.detail]:
                        print(f"       - {a.titre[:58]}")
                        print(f"         employeur={a.employeur[:32] or '?'} | lieu={a.lieu[:28] or '?'}")
                    if examines >= args.nombre:
                        print(f"\n  (arret apres {args.nombre} messages, utilise --nombre pour en voir plus)")
                        break
                if not examines:
                    print("  aucun message sur la periode")
            print(f"\nTotal : {total} annonce(s) extraite(s).")
    except Exception as exc:
        print(f"ECHEC : {exc}", file=sys.stderr)
        return 1
    return 0


class _ParseurUsage64(argparse.ArgumentParser):
    """Une erreur d'usage rend 64, pas le 2 d'argparse (le 2 est le « non sain »)."""

    def error(self, message: str):
        self.print_usage(sys.stderr)
        print(f"{self.prog} : {message}", file=sys.stderr)
        raise SystemExit(64)


def _analyser_usage64(prog: str, reste: list[str], declarer) -> tuple[argparse.Namespace | None, int]:
    """Analyse `reste` ; `declarer(sous_parseurs)` ajoute les actions.

    Rend (arguments, 0), ou (None, 64) pour tout usage invalide, `-h` compris.
    """
    p = _ParseurUsage64(prog=prog, add_help=False)  # -h : usage, donc 64
    declarer(p.add_subparsers(dest="action", required=True))
    try:
        return p.parse_args(reste), 0
    except SystemExit as e:
        return None, int(e.code or 0)


def cmd_instantane(args: argparse.Namespace) -> int:
    """Les commandes de sauvegarde du modele. Usage incorrect : 64, pas 2 d'argparse."""
    def declarer(sp) -> None:
        sp.add_parser("creer", add_help=False, help="prend un instantane de /donnees").add_argument("dossier")
        sp.add_parser("verifier", add_help=False, help="un instantane est-il restaurable ?").add_argument("dossier")

    a, code = _analyser_usage64("veille instantane", args.reste, declarer)
    if a is None:
        return code

    # Ni db.initialiser() ni db.connexion() : voir instantane.py
    from . import instantane

    if a.action == "verifier":
        return instantane.verifier(Path(a.dossier))
    try:
        instantane.creer(Path(a.dossier))
    except instantane.InstantaneIncomplet as e:
        print(f"Instantané impossible : {e}")
        return 1
    print(f"Instantané pris : {a.dossier}")
    return 0


def cmd_config(args: argparse.Namespace) -> int:
    """`veille config verifier <dossier>` : 0 sain, 2 non sain, 64 usage."""
    def declarer(sp) -> None:
        sp.add_parser("verifier", add_help=False,
                      help="un dossier de configuration est-il sain ?").add_argument("dossier")

    a, code = _analyser_usage64("veille config", args.reste, declarer)
    if a is None:
        return code

    from . import config

    # `~` comme pour VEILLE_CONFIG : entre guillemets, le shell ne le développe pas.
    problemes = config.verifier_dossier(Path(a.dossier).expanduser())
    for probleme in problemes:
        print(probleme, file=sys.stderr)
    if problemes:
        return 2
    print("sain")
    return 0


class _SansSondeDeSante(logging.Filter):
    """Tait les `GET /sante` reussis du journal d'acces d'uvicorn : le
    HEALTHCHECK de l'image, le deploiement et la sonde du serveur l'interrogent
    sans cesse, pres de 3 000 lignes par jour dans `docker logs`. Une sante en
    echec et toute autre requete restent au journal."""

    def filter(self, record: logging.LogRecord) -> bool:
        # uvicorn : (client, methode, chemin et requete, version HTTP, statut)
        if not isinstance(record.args, tuple) or len(record.args) != 5:
            return True
        _, methode, chemin, _, statut = record.args
        try:
            reussie = 200 <= int(statut) < 300
        except (TypeError, ValueError):
            return True
        return not (methode == "GET" and str(chemin).split("?", 1)[0] == "/sante" and reussie)


def cmd_servir(args: argparse.Namespace) -> int:
    import uvicorn

    # Pose avant uvicorn.run : sa configuration du journal remplace les
    # gestionnaires de `uvicorn.access`, pas les filtres du journal lui-meme.
    logging.getLogger("uvicorn.access").addFilter(_SansSondeDeSante())
    uvicorn.run("veille.app:app", host=args.hote, port=args.port, reload=args.rechargement)
    return 0


# --------------------------------------------------------------------------


def principal(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="veille", description="Console de recherche d'emploi")
    p.add_argument("-v", "--verbeux", action="store_true")
    sp = p.add_subparsers(dest="commande", required=True)

    sp.add_parser("init", help="prepare la base et les cles").set_defaults(fonction=cmd_init)

    sp.add_parser("factice", help="charge le jeu de données factice (base vide seulement)").set_defaults(
        fonction=cmd_factice
    )

    sp.add_parser("lien", help="affiche un lien de connexion (24 h)").set_defaults(fonction=cmd_lien)

    pk = sp.add_parser("passkeys", help="liste les passkeys, en retire une (--retirer)")
    pk.add_argument("--retirer", type=int, metavar="ID",
                    help="retire cette passkey et ferme toutes les sessions")
    pk.set_defaults(fonction=cmd_passkeys)

    c = sp.add_parser("collecter", help="lance les collecteurs")
    c.add_argument("--source", action="append", choices=["france_travail", "courriel", "rss", "arbeitnow"])
    c.add_argument("--jours", type=int, default=7, help="fenetre de collecte (defaut : 7)")
    c.add_argument("--sans-notification", action="store_true")
    c.set_defaults(fonction=cmd_collecter)

    sp.add_parser("rescorer", help="recalcule les scores").set_defaults(fonction=cmd_rescorer)
    v = sp.add_parser("verifier", help="les annonces sont-elles encore en ligne ?")
    v.add_argument("--limite", type=int, default=60, help="nombre d'offres a sonder")
    v.add_argument("--sans-enrichir", action="store_true",
                   help="ne pas completer les offres a extrait au passage")
    v.set_defaults(fonction=cmd_verifier)
    sp.add_parser("etat", help="resume de la base").set_defaults(fonction=cmd_etat)

    sp.add_parser("kit", help="verifie le kit de candidature").set_defaults(fonction=cmd_kit)
    e = sp.add_parser("empreintes-kit",
                      help="le kit a-t-il bouge depuis la derniere validation ?")
    e.add_argument("--mettre-a-jour", action="store_true",
                   help="fige l'etat actuel : a faire SEULEMENT si le changement est voulu")
    e.add_argument("--note", default="", help="pourquoi ce changement")
    e.set_defaults(fonction=cmd_empreintes_kit)
    sp.add_parser("tester-sources", help="verifie chaque source de collecte").set_defaults(
        fonction=cmd_tester_sources
    )

    n = sp.add_parser("tester-notification", help="diagnostic push + repli mail")
    n.add_argument("--envoyer", action="store_true", help="expedie reellement le mail d'essai")
    n.set_defaults(fonction=cmd_tester_notification)

    d = sp.add_parser("decouvrir-expediteurs",
                      help="cherche les expediteurs d'alertes dans ta boite (en-tetes seuls)")
    d.add_argument("--jours", type=int, default=90)
    d.add_argument("--plafond", type=int, default=300, help="messages examines au plus")
    d.set_defaults(fonction=cmd_decouvrir_expediteurs)

    t = sp.add_parser("tester-mail", help="diagnostic du canal IMAP")
    t.add_argument("--nombre", type=int, default=5, help="messages a examiner par recherche")
    t.add_argument("--jours", type=int, default=30, help="fenetre d'examen")
    t.add_argument("--detail", type=int, default=5, help="annonces a afficher par message")
    t.add_argument("--fichier", help="analyser un .eml enregistre, sans toucher a la boite")
    t.add_argument("--reseau", action="store_true", help="avec --fichier : resoudre les liens de suivi")
    t.set_defaults(fonction=cmd_tester_mail)

    i = sp.add_parser("instantane", help="creer | verifier un instantane de /donnees",
                      add_help=False)
    i.add_argument("reste", nargs=argparse.REMAINDER)
    i.set_defaults(fonction=cmd_instantane)

    c = sp.add_parser("config", help="verifier un dossier de configuration",
                      add_help=False)
    c.add_argument("reste", nargs=argparse.REMAINDER)
    c.set_defaults(fonction=cmd_config)

    s = sp.add_parser("servir", help="demarre la console")
    s.add_argument("--hote", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8460)
    s.add_argument("--rechargement", action="store_true")
    s.set_defaults(fonction=cmd_servir)

    # `instantane` s'analyse seul : toute erreur d'usage y rend 64 (le 2 de
    # argparse est le "malsain" de `verifier`), options comprises (--foo, -h).
    # `config` fait de meme : 0 sain, 2 non sain, 64 usage.
    brut = list(sys.argv[1:] if argv is None else argv)
    for nom, commande in (("instantane", cmd_instantane), ("config", cmd_config)):
        if nom in brut:
            i = brut.index(nom)
            if all(x in ("-v", "--verbeux") for x in brut[:i]):
                _journalisation(bool(brut[:i]))
                return commande(argparse.Namespace(reste=brut[i + 1:]))

    args = p.parse_args(argv)
    _journalisation(args.verbeux)
    return int(args.fonction(args) or 0)


if __name__ == "__main__":
    raise SystemExit(principal())

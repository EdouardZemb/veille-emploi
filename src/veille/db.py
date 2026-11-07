"""Persistance SQLite.

Un seul fichier, chemin donne par VEILLE_DB. Pas d'ORM : le schema est petit
et les requetes de la console sont lisibles telles quelles.

ATTENTION : cette base contient des donnees sensibles (candidatures, pretentions
salariales, notes sur des employeurs). Voir docs/DONNEES.md pour la sauvegarde
et l'effacement.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator

from .config import CHEMIN_DB
from .models import Contribution, Offre

SCHEMA = """
CREATE TABLE IF NOT EXISTS offres (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    empreinte           TEXT NOT NULL UNIQUE,
    empreinte_titre     TEXT,
    url                 TEXT,
    url_canonique       TEXT,
    titre               TEXT NOT NULL,
    employeur           TEXT,
    lieu                TEXT,
    description         TEXT,
    source              TEXT,
    date_publication    TEXT,
    date_collecte       TEXT NOT NULL,

    salaire_min         REAL,
    salaire_max         REAL,
    salaire_devise      TEXT,
    type_contrat        TEXT,
    duree_mois          INTEGER,
    donnees_partielles  INTEGER NOT NULL DEFAULT 0,

    score               REAL NOT NULL DEFAULT 0,
    famille             TEXT,
    zone                TEXT,
    atouts              TEXT,
    explication         TEXT,
    rejete_auto         INTEGER NOT NULL DEFAULT 0,
    motif_rejet_auto    TEXT,

    statut              TEXT NOT NULL DEFAULT 'nouveau',
    motif_ecartement    TEXT,
    notes               TEXT,
    canal_candidature   TEXT,
    date_candidature    TEXT,
    date_relance_due    TEXT,
    dossier_chemin      TEXT,
    extrait_source      TEXT,
    salaire_source      TEXT,
    contact_nom         TEXT,
    contact_civilite    TEXT,
    adresse_entreprise  TEXT,
    verifiee_le         TEXT,
    verifiee_par        TEXT,
    verdict_verification TEXT,
    motif_verification  TEXT,
    echecs_verification INTEGER NOT NULL DEFAULT 0,
    disparue_le         TEXT,
    archivee_le         TEXT,
    archive_motif       TEXT,
    archive_protegee    INTEGER NOT NULL DEFAULT 0,
    probablement_retiree INTEGER NOT NULL DEFAULT 0,
    famille_validee_le  TEXT,
    reference_annonce   TEXT,
    enrichi_le          TEXT,
    enrichi_par         TEXT,
    vue                 INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_offres_statut ON offres(statut);
CREATE INDEX IF NOT EXISTS idx_offres_score  ON offres(score DESC);
CREATE INDEX IF NOT EXISTS idx_offres_url    ON offres(url_canonique);
CREATE INDEX IF NOT EXISTS idx_offres_titre  ON offres(empreinte_titre);

CREATE TABLE IF NOT EXISTS evenements (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    offre_id  INTEGER NOT NULL REFERENCES offres(id) ON DELETE CASCADE,
    type      TEXT NOT NULL,
    detail    TEXT,
    horodatage TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_evt_offre ON evenements(offre_id);

CREATE TABLE IF NOT EXISTS abonnements_push (
    endpoint   TEXT PRIMARY KEY,
    p256dh     TEXT NOT NULL,
    auth       TEXT NOT NULL,
    cree_le    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS exigences (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    offre_id   INTEGER NOT NULL REFERENCES offres(id) ON DELETE CASCADE,
    attribut   TEXT NOT NULL,
    valeur     TEXT NOT NULL,
    citation   TEXT NOT NULL,
    proposee_par TEXT NOT NULL,
    validee_le TEXT,
    UNIQUE(offre_id, attribut)
);
CREATE INDEX IF NOT EXISTS idx_exig_offre ON exigences(offre_id);

CREATE TABLE IF NOT EXISTS etat_collecte (
    source              TEXT PRIMARY KEY,
    derniere_execution  TEXT,
    dernier_marqueur    TEXT,
    dernier_resultat    TEXT
);
CREATE TABLE IF NOT EXISTS reglages (
    cle         TEXT PRIMARY KEY,
    valeur      TEXT NOT NULL,
    modifie_le  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
    id          INTEGER PRIMARY KEY,
    empreinte   TEXT NOT NULL UNIQUE,
    appareil    TEXT NOT NULL,
    cree_le     TEXT NOT NULL,
    vue_le      TEXT NOT NULL,
    expire_le   TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS liens_connexion (
    id          INTEGER PRIMARY KEY,
    empreinte   TEXT NOT NULL UNIQUE,
    origine     TEXT NOT NULL,
    cree_le     TEXT NOT NULL,
    expire_le   TEXT NOT NULL,
    utilise_le  TEXT
);
CREATE TABLE IF NOT EXISTS passkeys (
    id            INTEGER PRIMARY KEY,
    identifiant   TEXT NOT NULL UNIQUE,
    cle_publique  BLOB NOT NULL,
    compteur      INTEGER NOT NULL,
    transports    TEXT NOT NULL DEFAULT '[]',
    appareil      TEXT NOT NULL,
    cree_le       TEXT NOT NULL,
    utilisee_le   TEXT
);
"""


def _connexion() -> sqlite3.Connection:
    CHEMIN_DB.parent.mkdir(parents=True, exist_ok=True)
    cx = sqlite3.connect(CHEMIN_DB, timeout=15)
    cx.row_factory = sqlite3.Row
    cx.execute("PRAGMA journal_mode=WAL")
    cx.execute("PRAGMA foreign_keys=ON")
    return cx


@contextmanager
def connexion() -> Iterator[sqlite3.Connection]:
    cx = _connexion()
    try:
        yield cx
        cx.commit()
    except Exception:
        cx.rollback()
        raise
    finally:
        cx.close()


def base_ouverte() -> bool:
    """La base s'ouvre et repond : sert a la route de sante."""
    try:
        with connexion() as cx:
            cx.execute("SELECT 1").fetchone()
        return True
    except (sqlite3.Error, OSError):
        return False


def lire_reglage(cle: str) -> str | None:
    """La valeur d'un reglage, ou None s'il n'est pas (encore) en base."""
    try:
        with connexion() as cx:
            ligne = cx.execute("SELECT valeur FROM reglages WHERE cle = ?", (cle,)).fetchone()
    except sqlite3.OperationalError:
        # table absente : base jamais initialisee
        return None
    return ligne["valeur"] if ligne else None


def ecrire_reglage(cle: str, valeur: str) -> None:
    with connexion() as cx:
        cx.execute(
            "INSERT INTO reglages (cle, valeur, modifie_le) VALUES (?, ?, ?) "
            "ON CONFLICT(cle) DO UPDATE SET valeur = excluded.valeur, "
            "modifie_le = excluded.modifie_le",
            (cle, valeur, datetime.now(timezone.utc).isoformat()),
        )


def initialiser() -> None:
    with connexion() as cx:
        cx.executescript(SCHEMA)
        _migrer(cx)


def _migrer(cx: sqlite3.Connection) -> None:
    """Ajoute les colonnes apparues apres la premiere mise en service.

    SQLite ne sait pas faire `ADD COLUMN IF NOT EXISTS` : on lit le schema.
    """
    colonnes = {r["name"] for r in cx.execute("PRAGMA table_info(offres)").fetchall()}
    for nom, definition in (("empreinte_titre", "TEXT"), ("atouts", "TEXT"),
                            ("enrichi_le", "TEXT"), ("enrichi_par", "TEXT"),
                            ("extrait_source", "TEXT"),
                            ("salaire_source", "TEXT"),
                            ("contact_nom", "TEXT"),
                            ("contact_civilite", "TEXT"),
                            ("adresse_entreprise", "TEXT"),
                            ("verifiee_le", "TEXT"),
                            ("verifiee_par", "TEXT"),
                            ("verdict_verification", "TEXT"),
                            ("motif_verification", "TEXT"),
                            ("echecs_verification", "INTEGER NOT NULL DEFAULT 0"),
                            ("disparue_le", "TEXT"),
                            ("archivee_le", "TEXT"),
                            ("archive_motif", "TEXT"),
                            ("archive_protegee", "INTEGER NOT NULL DEFAULT 0"),
                            ("probablement_retiree", "INTEGER NOT NULL DEFAULT 0"),
                            ("famille_validee_le", "TEXT"),
                            ("reference_annonce", "TEXT")):
        if nom not in colonnes:
            cx.execute(f"ALTER TABLE offres ADD COLUMN {nom} {definition}")
    cx.execute("CREATE INDEX IF NOT EXISTS idx_offres_titre ON offres(empreinte_titre)")
    cx.execute("CREATE INDEX IF NOT EXISTS idx_offres_archive ON offres(archivee_le)")
    cx.execute("CREATE INDEX IF NOT EXISTS idx_offres_verif ON offres(verifiee_le)")


# --------------------------------------------------------------------------
# Ecriture
# --------------------------------------------------------------------------


def enregistrer_offre(offre: Offre) -> tuple[int | None, bool]:
    """Insere l'offre si elle est nouvelle.

    Retourne (id, nouvelle). Une offre deja connue n'est jamais re-inseree ni
    remise a 'nouveau' : une offre ecartee ne doit jamais remonter.
    """
    with connexion() as cx:
        existante = cx.execute(
            "SELECT id FROM offres WHERE empreinte = ?", (offre.empreinte,)
        ).fetchone()
        if existante:
            return existante["id"], False

        # Deuxieme filet : meme intitule, meme employeur, URL differente.
        # Cas du poste republie avec un nouvel identifiant, et cas de la meme
        # annonce arrivant par deux canaux. On garde la premiere vue et on
        # consigne la nouvelle apparition plutot que de creer un doublon.
        cle_titre = offre.empreinte_titre
        if cle_titre:
            jumelle = cx.execute(
                "SELECT id, source FROM offres WHERE empreinte_titre = ?", (cle_titre,)
            ).fetchone()
            if jumelle:
                cx.execute(
                    "INSERT INTO evenements (offre_id, type, detail, horodatage) VALUES (?,?,?,?)",
                    (
                        jumelle["id"],
                        "revue",
                        f"republiee via {offre.source} : {offre.url_canonique or offre.url}",
                        datetime.now().isoformat(timespec="seconds"),
                    ),
                )
                return jumelle["id"], False

        cur = cx.execute(
            """
            INSERT INTO offres (
                empreinte, empreinte_titre, url, url_canonique, titre, employeur, lieu, description,
                source, date_publication, date_collecte, salaire_min, salaire_max,
                salaire_devise, type_contrat, duree_mois, donnees_partielles,
                score, famille, zone, atouts, explication, rejete_auto, motif_rejet_auto, statut
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                offre.empreinte,
                cle_titre,
                offre.url,
                offre.url_canonique,
                offre.titre,
                offre.employeur,
                offre.lieu,
                offre.description,
                offre.source,
                offre.date_publication.isoformat() if offre.date_publication else None,
                offre.date_collecte.isoformat(timespec="seconds"),
                offre.salaire_min,
                offre.salaire_max,
                offre.salaire_devise,
                offre.type_contrat,
                offre.duree_mois,
                int(offre.donnees_partielles),
                offre.score,
                offre.famille,
                offre.zone,
                ",".join(offre.atouts),
                json.dumps([c.as_dict() for c in offre.explication], ensure_ascii=False),
                int(offre.rejete_auto),
                offre.motif_rejet_auto,
                # Une offre rejetee par une regle eliminatoire arrive directement
                # au rebut, avec son motif : elle ne pollue pas le flux.
                "ecartee" if offre.rejete_auto else ("differee" if offre.differee else "nouveau"),
            ),
        )
        oid = cur.lastrowid
        if offre.rejete_auto:
            cx.execute(
                "UPDATE offres SET motif_ecartement = ? WHERE id = ?",
                (PREFIXE_AUTOMATIQUE + offre.motif_rejet_auto, oid),
            )
        elif offre.differee:
            cx.execute(
                "UPDATE offres SET motif_ecartement = ? WHERE id = ?",
                (PREFIXE_AUTOMATIQUE + offre.motif_differe, oid),
            )
        cx.execute(
            "INSERT INTO evenements (offre_id, type, detail, horodatage) VALUES (?,?,?,?)",
            (oid, "collectee", offre.source, datetime.now().isoformat(timespec="seconds")),
        )
        return oid, True


def journaliser(offre_id: int, type_evt: str, detail: str = "") -> None:
    with connexion() as cx:
        cx.execute(
            "INSERT INTO evenements (offre_id, type, detail, horodatage) VALUES (?,?,?,?)",
            (offre_id, type_evt, detail, datetime.now().isoformat(timespec="seconds")),
        )


def changer_statut(
    offre_id: int,
    statut: str,
    motif: str | None = None,
    canal: str | None = None,
    delai_relance_jours: int = 10,
) -> None:
    champs: dict[str, Any] = {"statut": statut}
    if motif is not None:
        champs["motif_ecartement"] = motif
    if statut == "candidature_envoyee":
        champs["date_candidature"] = date.today().isoformat()
        champs["date_relance_due"] = (date.today() + timedelta(days=delai_relance_jours)).isoformat()
        if canal:
            champs["canal_candidature"] = canal
    if statut == "relance_envoyee":
        champs["date_relance_due"] = (date.today() + timedelta(days=delai_relance_jours)).isoformat()

    sets = ", ".join(f"{k} = ?" for k in champs)
    with connexion() as cx:
        cx.execute(f"UPDATE offres SET {sets} WHERE id = ?", (*champs.values(), offre_id))
    journaliser(offre_id, f"statut:{statut}", motif or canal or "")


def maj_champs(offre_id: int, **champs: Any) -> None:
    autorises = {"notes", "dossier_chemin", "vue", "date_relance_due",
                 "canal_candidature",
                 # Ce qu'il a cherche lui-meme : une recherche de nom de
                 # recruteur, c'est cinq minutes. Ca ne se perd pas a la
                 # regeneration suivante.
                 "contact_nom", "contact_civilite", "adresse_entreprise",
                 # Reference de l'annonce : memorisee comme le contact, et
                 # jamais obligatoire. Le gabarit fait disparaitre le segment
                 # entier quand elle est vide.
                 "reference_annonce"}
    champs = {k: v for k, v in champs.items() if k in autorises}
    if not champs:
        return
    sets = ", ".join(f"{k} = ?" for k in champs)
    with connexion() as cx:
        cx.execute(f"UPDATE offres SET {sets} WHERE id = ?", (*champs.values(), offre_id))


def enregistrer_texte_complet(offre_id: int, texte: str, offre, origine: str) -> None:
    """Remplace la description par le texte complet et applique le rescorage.

    Le STATUT suit la meme regle que le rescorage global : le moteur peut
    revenir sur ses propres decisions, jamais sur celles d'Edouard. Une offre
    qu'il a triee a la main garde son statut, meme si le texte complet la
    disqualifie — l'alerte le lui signale, c'est a lui de trancher.
    """
    with connexion() as cx:
        ligne = cx.execute(
            "SELECT statut, motif_ecartement, description, extrait_source, "
            "salaire_min, salaire_max, salaire_devise "
            "FROM offres WHERE id = ?", (offre_id,)
        ).fetchone()
        if ligne is None:
            return
        # L'extrait vient de la source, le texte complet vient de lui : on garde
        # les deux. Conserve UNE SEULE FOIS, au premier enrichissement, pour
        # qu'un second collage n'ecrase pas l'original.
        if ligne["extrait_source"] is None:
            # Le salaire part avec l'extrait : sans ca, « revenir a l'extrait »
            # laisserait en place une fourchette que SEUL le texte complet
            # donnait, et l'offre afficherait « score sur extrait » avec des
            # points venus d'ailleurs.
            cx.execute(
                "UPDATE offres SET extrait_source = ?, salaire_source = ? WHERE id = ?",
                (ligne["description"],
                 json.dumps([ligne["salaire_min"], ligne["salaire_max"],
                             ligne["salaire_devise"]]),
                 offre_id),
            )
        cx.execute(
            """UPDATE offres SET description=?, donnees_partielles=0,
                      salaire_min=?, salaire_max=?, salaire_devise=?,
                      score=?, famille=?, zone=?, atouts=?, explication=?,
                      rejete_auto=?, motif_rejet_auto=?,
                      enrichi_le=?, enrichi_par=?
               WHERE id=?""",
            (
                texte,
                offre.salaire_min, offre.salaire_max, offre.salaire_devise,
                offre.score, offre.famille, offre.zone, ",".join(offre.atouts),
                json.dumps([c.as_dict() for c in offre.explication], ensure_ascii=False),
                int(offre.rejete_auto), offre.motif_rejet_auto,
                datetime.now().isoformat(timespec="seconds"), origine,
                offre_id,
            ),
        )
        statut, motif = ligne["statut"], ligne["motif_ecartement"] or ""
        automatique = statut == "nouveau" or (
            statut in ("ecartee", "differee") and motif.startswith(PREFIXE_AUTOMATIQUE)
        )
        if not automatique:
            return          # decision manuelle : on n'y touche pas
        if offre.rejete_auto:
            cx.execute("UPDATE offres SET statut='ecartee', motif_ecartement=? WHERE id=?",
                       (PREFIXE_AUTOMATIQUE + offre.motif_rejet_auto, offre_id))
        elif offre.differee:
            cx.execute("UPDATE offres SET statut='differee', motif_ecartement=? WHERE id=?",
                       (PREFIXE_AUTOMATIQUE + offre.motif_differe, offre_id))
        elif statut != "nouveau":
            cx.execute("UPDATE offres SET statut='nouveau', motif_ecartement=NULL WHERE id=?",
                       (offre_id,))


def annuler_texte_complet(offre_id: int) -> bool:
    """Revient a l'extrait d'origine apres un collage rate.

    Le rescorage qui suit est fait par l'appelant : ici on ne touche qu'au
    texte et aux marques d'enrichissement.
    """
    with connexion() as cx:
        ligne = cx.execute(
            "SELECT extrait_source, salaire_source FROM offres WHERE id = ?",
            (offre_id,)
        ).fetchone()
        if ligne is None or ligne["extrait_source"] is None:
            return False
        try:
            smin, smax, devise = json.loads(ligne["salaire_source"] or "[null,null,null]")
        except (ValueError, TypeError):
            smin = smax = devise = None
        cx.execute(
            """UPDATE offres SET description = extrait_source, extrait_source = NULL,
                      salaire_min = ?, salaire_max = ?, salaire_devise = ?,
                      salaire_source = NULL,
                      donnees_partielles = 1, enrichi_le = NULL, enrichi_par = NULL
               WHERE id = ?""",
            (smin, smax, devise, offre_id),
        )
        return True


def marquer_etat_collecte(source: str, marqueur: str = "", resultat: str = "") -> None:
    with connexion() as cx:
        cx.execute(
            """INSERT INTO etat_collecte (source, derniere_execution, dernier_marqueur, dernier_resultat)
               VALUES (?,?,?,?)
               ON CONFLICT(source) DO UPDATE SET
                 derniere_execution = excluded.derniere_execution,
                 dernier_marqueur   = COALESCE(NULLIF(excluded.dernier_marqueur,''), etat_collecte.dernier_marqueur),
                 dernier_resultat   = excluded.dernier_resultat""",
            (source, datetime.now().isoformat(timespec="seconds"), marqueur, resultat),
        )


def lire_marqueur(source: str) -> str:
    with connexion() as cx:
        r = cx.execute("SELECT dernier_marqueur FROM etat_collecte WHERE source = ?", (source,)).fetchone()
        return (r["dernier_marqueur"] or "") if r else ""


# --------------------------------------------------------------------------
# Lecture
# --------------------------------------------------------------------------


def _ligne_en_dict(r: sqlite3.Row) -> dict[str, Any]:
    d = dict(r)
    try:
        d["explication"] = json.loads(d.get("explication") or "[]")
    except json.JSONDecodeError:
        d["explication"] = []
    d["donnees_partielles"] = bool(d.get("donnees_partielles"))
    d["rejete_auto"] = bool(d.get("rejete_auto"))
    d["atouts"] = [a for a in (d.get("atouts") or "").split(",") if a]
    return d


def lister_offres(
    statut: str | None = None,
    zone: str | None = None,
    famille: str | None = None,
    atout: str | None = None,
    source: str | None = None,
    recherche: str | None = None,
    inclure_ecartees: bool = False,
    inclure_archivees: bool = False,
    verification: str | None = None,
    tri: str | None = None,
    limite: int = 200,
) -> list[dict[str, Any]]:
    clauses, params = [], []
    # L'archive est un onglet a part : rien n'est supprime, mais une offre
    # retiree du site ne doit plus occuper la liste active.
    if not inclure_archivees:
        clauses.append("archivee_le IS NULL")
    if statut:
        clauses.append("statut = ?")
        params.append(statut)
    elif not inclure_ecartees:
        # Ni une offre ecartee, ni une offre mise en attente, ne remontent
        # dans le flux courant. Elles restent accessibles par le filtre statut.
        clauses.append("statut NOT IN ('ecartee','differee')")
    if zone:
        clauses.append("zone = ?")
        params.append(zone)
    if famille:
        clauses.append("famille = ?")
        params.append(famille)
    if atout:
        # Les atouts sont stockes en liste separee par des virgules : on encadre
        # des deux cotes pour que "mobile" ne matche pas "contexte_mobile" par accident.
        clauses.append("(',' || COALESCE(atouts,'') || ',') LIKE ?")
        params.append(f"%,{atout},%")
    if source:
        clauses.append("source LIKE ?")
        params.append(f"{source}%")
    if recherche:
        clauses.append("(titre LIKE ? OR employeur LIKE ? OR lieu LIKE ?)")
        params += [f"%{recherche}%"] * 3

    # Filtrer par FRAICHEUR de verification : « jamais vue » et « vue ce matin »
    # ne doivent pas se ressembler, et il doit pouvoir isoler les unes des autres.
    if verification == "jamais":
        clauses.append("verifiee_le IS NULL")
    elif verification == "non_verifiable":
        clauses.append("verdict_verification = 'interdite'")
    elif verification == "par_edouard":
        clauses.append("verifiee_par = 'edouard'")
    elif verification == "ancienne":
        limite_age = (datetime.now() - timedelta(days=7)).isoformat(timespec="seconds")
        clauses.append("(verifiee_le IS NULL OR verifiee_le < ?)")
        params.append(limite_age)
    elif verification == "recente":
        limite_age = (datetime.now() - timedelta(days=2)).isoformat(timespec="seconds")
        clauses.append("verifiee_le >= ?")
        params.append(limite_age)

    ordres = {
        "score": "score DESC, date_collecte DESC",
        # NULLS FIRST : une offre jamais verifiee est la plus urgente a regarder.
        "verification": "verifiee_le IS NOT NULL, verifiee_le ASC, score DESC",
        "recente": "date_collecte DESC, score DESC",
    }
    ordre = ordres.get(tri or "score", ordres["score"])

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with connexion() as cx:
        rows = cx.execute(
            f"SELECT * FROM offres {where} ORDER BY {ordre} LIMIT ?",
            (*params, limite),
        ).fetchall()
    return [_ligne_en_dict(r) for r in rows]


def lire_offre(offre_id: int) -> dict[str, Any] | None:
    with connexion() as cx:
        r = cx.execute("SELECT * FROM offres WHERE id = ?", (offre_id,)).fetchone()
        if not r:
            return None
        d = _ligne_en_dict(r)
        d["evenements"] = [
            dict(e)
            for e in cx.execute(
                "SELECT type, detail, horodatage FROM evenements WHERE offre_id = ? ORDER BY id",
                (offre_id,),
            ).fetchall()
        ]
        return d


def relances_dues() -> list[dict[str, Any]]:
    with connexion() as cx:
        rows = cx.execute(
            """SELECT * FROM offres
               WHERE date_relance_due IS NOT NULL
                 AND date_relance_due <= ?
                 AND statut IN ('candidature_envoyee','relance_envoyee')
               ORDER BY date_relance_due""",
            (date.today().isoformat(),),
        ).fetchall()
    return [_ligne_en_dict(r) for r in rows]


def offres_nouvelles_non_vues() -> list[dict[str, Any]]:
    with connexion() as cx:
        rows = cx.execute(
            "SELECT * FROM offres WHERE statut = 'nouveau' AND vue = 0 ORDER BY score DESC"
        ).fetchall()
    return [_ligne_en_dict(r) for r in rows]


def motifs_ecartement() -> list[dict[str, Any]]:
    """Les motifs d'ecartement agreges - c'est la donnee qui dira ce que le
    scoring rate. A regarder au bout d'une trentaine d'offres."""
    with connexion() as cx:
        rows = cx.execute(
            """SELECT motif_ecartement AS motif, COUNT(*) AS n, ROUND(AVG(score),1) AS score_moyen
               FROM offres
               WHERE statut = 'ecartee' AND motif_ecartement IS NOT NULL AND motif_ecartement != ''
               GROUP BY motif_ecartement ORDER BY n DESC"""
        ).fetchall()
    return [dict(r) for r in rows]


def entonnoir() -> dict[str, Any]:
    """Statistiques de pilotage : volumes, taux de reponse par canal et par
    famille, rendement des sources."""
    with connexion() as cx:
        par_statut = {
            r["statut"]: r["n"]
            for r in cx.execute("SELECT statut, COUNT(*) n FROM offres GROUP BY statut").fetchall()
        }
        envoyees = cx.execute(
            "SELECT COUNT(*) n FROM offres WHERE date_candidature IS NOT NULL"
        ).fetchone()["n"]
        repondues = cx.execute(
            """SELECT COUNT(*) n FROM offres
               WHERE date_candidature IS NOT NULL
                 AND statut IN ('reponse_recue','entretien','refus','accepte')"""
        ).fetchone()["n"]

        par_canal = [
            dict(r)
            for r in cx.execute(
                """SELECT COALESCE(NULLIF(canal_candidature,''),'non précisé') AS canal,
                          COUNT(*) AS envoyees,
                          SUM(CASE WHEN statut IN ('reponse_recue','entretien','refus','accepte')
                                   THEN 1 ELSE 0 END) AS reponses
                   FROM offres WHERE date_candidature IS NOT NULL
                   GROUP BY canal ORDER BY envoyees DESC"""
            ).fetchall()
        ]
        par_famille = [
            dict(r)
            for r in cx.execute(
                """SELECT COALESCE(NULLIF(famille,''),'inconnue') AS famille,
                          COUNT(*) AS envoyees,
                          SUM(CASE WHEN statut IN ('reponse_recue','entretien','refus','accepte')
                                   THEN 1 ELSE 0 END) AS reponses
                   FROM offres WHERE date_candidature IS NOT NULL
                   GROUP BY famille ORDER BY envoyees DESC"""
            ).fetchall()
        ]
        par_source = [
            dict(r)
            for r in cx.execute(
                """SELECT COALESCE(NULLIF(source,''),'inconnue') AS source,
                          COUNT(*) AS collectees,
                          SUM(CASE WHEN statut != 'ecartee' THEN 1 ELSE 0 END) AS retenues,
                          SUM(CASE WHEN date_candidature IS NOT NULL THEN 1 ELSE 0 END) AS candidatures
                   FROM offres GROUP BY source ORDER BY collectees DESC"""
            ).fetchall()
        ]

    for ligne in (*par_canal, *par_famille):
        ligne["taux_reponse"] = (
            round(100 * ligne["reponses"] / ligne["envoyees"]) if ligne["envoyees"] else 0
        )

    return {
        "par_statut": par_statut,
        "total": sum(par_statut.values()),
        "envoyees": envoyees,
        "repondues": repondues,
        "taux_reponse_global": round(100 * repondues / envoyees) if envoyees else 0,
        "par_canal": par_canal,
        "par_famille": par_famille,
        "par_source": par_source,
        "motifs_ecartement": motifs_ecartement(),
    }


# --------------------------------------------------------------------------
# Abonnements push
# --------------------------------------------------------------------------


def enregistrer_abonnement(endpoint: str, p256dh: str, auth: str) -> None:
    with connexion() as cx:
        cx.execute(
            """INSERT INTO abonnements_push (endpoint, p256dh, auth, cree_le) VALUES (?,?,?,?)
               ON CONFLICT(endpoint) DO UPDATE SET p256dh=excluded.p256dh, auth=excluded.auth""",
            (endpoint, p256dh, auth, datetime.now().isoformat(timespec="seconds")),
        )


def lister_abonnements() -> list[dict[str, str]]:
    with connexion() as cx:
        return [dict(r) for r in cx.execute("SELECT * FROM abonnements_push").fetchall()]


def supprimer_abonnement(endpoint: str) -> None:
    with connexion() as cx:
        cx.execute("DELETE FROM abonnements_push WHERE endpoint = ?", (endpoint,))

# --------------------------------------------------------------------------
# Sessions
# La base ne garde que l'empreinte SHA-256 du jeton, jamais le jeton.
# --------------------------------------------------------------------------


def creer_session(empreinte: str, appareil: str, instant: str, expire_le: str) -> int:
    with connexion() as cx:
        cur = cx.execute(
            "INSERT INTO sessions (empreinte, appareil, cree_le, vue_le, expire_le)"
            " VALUES (?,?,?,?,?)",
            (empreinte, appareil, instant, instant, expire_le),
        )
        return int(cur.lastrowid)


def session_par_empreinte(empreinte: str) -> dict | None:
    with connexion() as cx:
        r = cx.execute("SELECT * FROM sessions WHERE empreinte = ?", (empreinte,)).fetchone()
    return dict(r) if r else None


def prolonger_session(session_id: int, vue_le: str, expire_le: str) -> None:
    with connexion() as cx:
        cx.execute(
            "UPDATE sessions SET vue_le = ?, expire_le = ? WHERE id = ?",
            (vue_le, expire_le, session_id),
        )


def supprimer_session(session_id: int) -> None:
    with connexion() as cx:
        cx.execute("DELETE FROM sessions WHERE id = ?", (session_id,))


def lister_sessions(instant: str) -> list[dict]:
    """Les sessions non expirees a cet instant (ISO UTC, comparable en texte).

    Les expirees restent en base jusqu'a la purge (`purger_expires`) : elles ne
    s'affichent plus.
    """
    with connexion() as cx:
        return [dict(r) for r in cx.execute(
            "SELECT * FROM sessions WHERE expire_le > ? ORDER BY vue_le DESC, id DESC",
            (instant,))]


def supprimer_sessions() -> int:
    """Ferme toutes les sessions ; rend leur nombre."""
    with connexion() as cx:
        return cx.execute("DELETE FROM sessions").rowcount

# --------------------------------------------------------------------------
# Liens de connexion : a usage unique, l'empreinte seule est gardee
# --------------------------------------------------------------------------


def creer_lien(empreinte: str, origine: str, instant: str, expire_le: str) -> int:
    with connexion() as cx:
        cur = cx.execute(
            "INSERT INTO liens_connexion (empreinte, origine, cree_le, expire_le)"
            " VALUES (?,?,?,?)",
            (empreinte, origine, instant, expire_le),
        )
        return int(cur.lastrowid)


def liens_ouverts(instant: str) -> list[dict]:
    """Les liens ni utilises ni expires a cet instant (ISO UTC, comparable en texte)."""
    with connexion() as cx:
        return [dict(r) for r in cx.execute(
            "SELECT * FROM liens_connexion WHERE utilise_le IS NULL AND expire_le > ?"
            " ORDER BY id",
            (instant,))]


def consommer_lien(lien_id: int, instant: str) -> bool:
    """Vrai si le lien etait encore ouvert a cet instant : ni utilise ni expire.

    L'expiration se reverifie ici : un lien peut expirer entre l'ouverture de la
    ceremonie et sa reponse."""
    with connexion() as cx:
        cur = cx.execute(
            "UPDATE liens_connexion SET utilise_le = ?"
            " WHERE id = ? AND utilise_le IS NULL AND expire_le > ?",
            (instant, lien_id, instant),
        )
        return cur.rowcount == 1


def purger_expires(instant: str) -> tuple[int, int]:
    """Supprime les sessions et les liens expires a cet instant (ISO UTC, comparable
    en texte) ; rend leurs nombres. Le planificateur l'appelle (planificateur.py)."""
    with connexion() as cx:
        sessions = cx.execute("DELETE FROM sessions WHERE expire_le <= ?", (instant,)).rowcount
        liens = cx.execute(
            "DELETE FROM liens_connexion WHERE expire_le <= ?", (instant,)).rowcount
    return sessions, liens

# --------------------------------------------------------------------------
# Passkeys : l'identifiant en base64url, la cle publique COSE, le compteur
# --------------------------------------------------------------------------


def enregistrer_passkey(identifiant: str, cle_publique: bytes, compteur: int,
                        transports: list[str], appareil: str, instant: str) -> int:
    with connexion() as cx:
        cur = cx.execute(
            "INSERT INTO passkeys (identifiant, cle_publique, compteur, transports, appareil,"
            " cree_le) VALUES (?,?,?,?,?,?)",
            (identifiant, cle_publique, compteur, json.dumps(transports), appareil, instant),
        )
        return int(cur.lastrowid)


def passkey_par_identifiant(identifiant: str) -> dict | None:
    """La passkey de cet identifiant, ses transports en liste ; sinon None."""
    with connexion() as cx:
        r = cx.execute("SELECT * FROM passkeys WHERE identifiant = ?", (identifiant,)).fetchone()
    if r is None:
        return None
    passkey = dict(r)
    passkey["transports"] = json.loads(passkey["transports"])
    return passkey


def maj_passkey_apres_usage(passkey_id: int, nouveau: int, ancien: int, instant: str) -> bool:
    """Ecrit le compteur si personne ne l'a change depuis `ancien` ; faux sinon.

    Une passkey qui annonce toujours 0 reste valable : `ancien` vaut 0 et la
    ligne correspond."""
    with connexion() as cx:
        cur = cx.execute(
            "UPDATE passkeys SET compteur = ?, utilisee_le = ? WHERE id = ? AND compteur = ?",
            (nouveau, instant, passkey_id, ancien),
        )
        return cur.rowcount == 1


def identifiants_passkeys() -> list[str]:
    with connexion() as cx:
        return [r["identifiant"] for r in cx.execute("SELECT identifiant FROM passkeys ORDER BY id")]


def compter_passkeys() -> int:
    with connexion() as cx:
        return int(cx.execute("SELECT COUNT(*) FROM passkeys").fetchone()[0])


TABLES_D_ACCES = ("passkeys", "sessions", "liens_connexion", "abonnements_push")


def compter_acces() -> dict[str, int]:
    """Le nombre de lignes de chaque table liee a une adresse."""
    with connexion() as cx:
        return {t: int(cx.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0])
                for t in TABLES_D_ACCES}


def effacer_acces() -> dict[str, int]:
    """Efface toutes les lignes de ces tables, en une seule transaction, et rend le
    nombre de lignes effacees par table."""
    with connexion() as cx:
        return {t: cx.execute(f"DELETE FROM {t}").rowcount for t in TABLES_D_ACCES}


def lister_passkeys() -> list[dict]:
    """De quoi reconnaitre chaque passkey, sans sa cle publique ni son identifiant."""
    with connexion() as cx:
        return [dict(r) for r in cx.execute(
            "SELECT id, appareil, cree_le, utilisee_le FROM passkeys ORDER BY id")]


def retirer_passkey_et_sessions(passkey_id: int) -> bool:
    """Retire la passkey et ferme toutes les sessions, en une seule transaction ;
    faux (et rien de touche) si l'id est inconnu."""
    with connexion() as cx:
        if cx.execute("DELETE FROM passkeys WHERE id = ?", (passkey_id,)).rowcount != 1:
            return False
        cx.execute("DELETE FROM sessions")
        return True


# Prefixe des motifs poses par le moteur, par opposition a ceux qu'Edouard
# ecrit lui-meme. C'est ce qui distingue une decision revisable d'une decision
# qui lui appartient.
PREFIXE_AUTOMATIQUE = "Automatique : "


def exigences_de(offre_id: int, validees_seulement: bool = True) -> list[dict[str, Any]]:
    """Les exigences relevees sur cette offre.

    `validees_seulement` est le defaut, et c'est la regle : une proposition
    non validee par Edouard n'existe pas pour le scoring.
    """
    clause = " AND validee_le IS NOT NULL" if validees_seulement else ""
    with connexion() as cx:
        return [dict(r) for r in cx.execute(
            f"SELECT * FROM exigences WHERE offre_id = ?{clause} ORDER BY attribut",
            (offre_id,)).fetchall()]


def exigences_validees(offre_id: int) -> dict[str, dict[str, str]]:
    """{attribut: {valeur, citation}} — ce que le scoring a le droit de lire."""
    return {e["attribut"]: {"valeur": e["valeur"], "citation": e["citation"]}
            for e in exigences_de(offre_id)}


def enregistrer_propositions(offre_id: int, propositions: list[dict[str, str]],
                             par: str) -> int:
    """Depose des propositions NON validees. Ne touche a aucune validee.

    Une exigence deja validee par Edouard n'est jamais ecrasee par une
    nouvelle proposition : c'est sa decision, pas celle du modele.
    """
    n = 0
    with connexion() as cx:
        for p in propositions:
            deja = cx.execute(
                "SELECT validee_le FROM exigences WHERE offre_id=? AND attribut=?",
                (offre_id, p["attribut"])).fetchone()
            if deja and deja["validee_le"]:
                continue
            cx.execute(
                """INSERT INTO exigences (offre_id, attribut, valeur, citation,
                                          proposee_par, validee_le)
                   VALUES (?,?,?,?,?,NULL)
                   ON CONFLICT(offre_id, attribut) DO UPDATE SET
                       valeur=excluded.valeur, citation=excluded.citation,
                       proposee_par=excluded.proposee_par, validee_le=NULL""",
                (offre_id, p["attribut"], p["valeur"], p["citation"], par))
            n += 1
    return n


def valider_exigences(offre_id: int, attributs: list[str]) -> int:
    """Valide les attributs nommes, retire les autres propositions.

    C'est le geste d'Edouard, et c'est lui seul qui ouvre l'exigence au
    scoring. Ce qu'il ne coche pas est supprime : une proposition qui traine
    sans decision finirait par ressembler a un fait.
    """
    maintenant = datetime.now().isoformat(timespec="seconds")
    with connexion() as cx:
        if attributs:
            trous = ",".join("?" * len(attributs))
            cx.execute(
                f"""UPDATE exigences SET validee_le=?
                    WHERE offre_id=? AND attribut IN ({trous})""",
                [maintenant, offre_id, *attributs])
        cx.execute(
            "DELETE FROM exigences WHERE offre_id=? AND validee_le IS NULL",
            (offre_id,))
        n = cx.execute(
            "SELECT COUNT(*) n FROM exigences WHERE offre_id=? AND validee_le IS NOT NULL",
            (offre_id,)).fetchone()["n"]
    rescorer_offre(offre_id)
    return n


def oublier_exigences(offre_id: int) -> None:
    """Retire tout, validees comprises, et rescore sans elles."""
    with connexion() as cx:
        cx.execute("DELETE FROM exigences WHERE offre_id = ?", (offre_id,))
    rescorer_offre(offre_id)


def _a_colonne(r, nom: str) -> bool:
    """La ligne porte-t-elle cette colonne ?

    Une base creee avant la migration n'a pas `famille_validee_le`, et un
    acces direct leverait une IndexError au milieu d'un rescorage.
    """
    try:
        return nom in r.keys()
    except Exception:
        return False


def offres_sans_famille(actives_seulement: bool = True) -> list[dict[str, Any]]:
    """Les offres qu'aucun motif n'a su classer."""
    clause = ("AND archivee_le IS NULL AND statut NOT IN ('ecartee','refus','accepte')"
              if actives_seulement else "")
    with connexion() as cx:
        return [_ligne_en_dict(r) for r in cx.execute(
            f"""SELECT * FROM offres
                WHERE (famille IS NULL OR famille = '') {clause}
                ORDER BY score DESC""").fetchall()]


def valider_famille(offre_id: int, famille: str) -> None:
    """SA decision. Elle survit aux rescorages, comme tout ce qui vient de lui."""
    with connexion() as cx:
        cx.execute(
            "UPDATE offres SET famille=?, famille_validee_le=? WHERE id=?",
            (famille, datetime.now().isoformat(timespec="seconds"), offre_id))
    rescorer_offre(offre_id)
    journaliser(offre_id, "famille_validee", famille)


def offre_depuis_ligne(r) -> "Any":
    """Construit l'`Offre` du scoring depuis une ligne de base.

    Un seul endroit : les deux rescorages construisaient chacun le leur, et
    une exigence validee aurait ete prise en compte par l'un et pas par
    l'autre.
    """
    from .models import Offre

    return Offre(
        titre=r["titre"] or "", employeur=r["employeur"] or "", lieu=r["lieu"] or "",
        description=r["description"] or "", url=r["url"] or "", source=r["source"] or "",
        salaire_min=r["salaire_min"], salaire_max=r["salaire_max"],
        salaire_devise=r["salaire_devise"], type_contrat=r["type_contrat"] or "",
        duree_mois=r["duree_mois"], donnees_partielles=bool(r["donnees_partielles"]),
        exigences=exigences_validees(r["id"]),
        # Une famille qu'il a validee lui-meme : le rescorage ne doit pas
        # l'effacer en ne retrouvant pas de motif, ce qui etait precisement
        # le cas qui l'avait laissee vide.
        famille_validee=(r["famille"] or "") if _a_colonne(r, "famille_validee_le")
        and r["famille_validee_le"] else "",
    )


def rescorer_offre(offre_id: int) -> None:
    """Recalcule une seule offre depuis ce qui est en base."""
    from .models import Offre
    from .scoring import scorer

    r = lire_offre(offre_id)
    if not r:
        return
    o = offre_depuis_ligne(r)
    scorer(o)
    with connexion() as cx:
        cx.execute(
            """UPDATE offres SET score=?, famille=?, zone=?, atouts=?, explication=?,
                      rejete_auto=?, motif_rejet_auto=? WHERE id=?""",
            (o.score, o.famille, o.zone, ",".join(o.atouts),
             json.dumps([c.as_dict() for c in o.explication], ensure_ascii=False),
             int(o.rejete_auto), o.motif_rejet_auto, offre_id),
        )


def rescorer_tout() -> tuple[int, int, int]:
    """Recalcule tout apres modification des criteres.

    Rend (recalculees, nouvellement_ecartees, remises_dans_le_flux,
    nouvellement_differees).

    REGLE : le moteur peut revenir sur SES decisions, jamais sur celles
    d'Edouard.

    - une offre encore intacte (`nouveau`) que les nouveaux criteres rejettent
      part au rebut, avec son motif ;
    - une offre ecartee AUTOMATIQUEMENT que les nouveaux criteres acceptent
      revient dans le flux ;
    - une offre qu'il a lui-meme triee - interessante, candidature envoyee,
      ecartee avec son propre motif - n'est jamais touchee.

    Sans le premier point, une nouvelle regle eliminatoire ne nettoyait pas
    l'historique : les offres passaient `rejete_auto` mais gardaient leur
    statut `nouveau` et restaient sous ses yeux. C'est exactement ce qui s'est
    produit en ajoutant la regle geographique.
    """
    from .config import recharger
    from .scoring import scorer

    recharger()
    nouvellement_ecartees = remises = nouvellement_differees = 0
    # Le rescorage ecrit dans des colonnes qui peuvent avoir ete ajoutees apres
    # la mise en service : sans ce passage, `veille rescorer` echouait sur une
    # base creee par une version anterieure.
    initialiser()
    with connexion() as cx:
        rows = cx.execute("SELECT * FROM offres").fetchall()
        for r in rows:
            o = offre_depuis_ligne(r)
            scorer(o)
            cx.execute(
                """UPDATE offres SET score=?, famille=?, zone=?, atouts=?, explication=?,
                          rejete_auto=?, motif_rejet_auto=? WHERE id=?""",
                (
                    o.score,
                    o.famille,
                    o.zone,
                    ",".join(o.atouts),
                    json.dumps([c.as_dict() for c in o.explication], ensure_ascii=False),
                    int(o.rejete_auto),
                    o.motif_rejet_auto,
                    r["id"],
                ),
            )

            statut = r["statut"]
            motif = r["motif_ecartement"] or ""
            ecartee_automatiquement = statut == "ecartee" and motif.startswith(PREFIXE_AUTOMATIQUE)
            differee_automatiquement = statut == "differee" and motif.startswith(PREFIXE_AUTOMATIQUE)

            # LA MISE EN ATTENTE N'ETAIT PAS APPLIQUEE ICI. Defaut trouve le
            # 02/10/2026 en rejouant l'historique : `rescorer_tout` ne faisait
            # circuler les offres qu'entre « nouveau » et « ecartee ». Le
            # reglage `mise_en_attente`, documente depuis le debut comme
            # « repasse a true et lance veille rescorer », ne produisait donc
            # AUCUN effet par cette commande — seulement a la collecte, ou
            # offre par offre. La promesse de la documentation n'etait pas
            # tenue par le code.
            if o.differee and statut == "nouveau":
                cx.execute(
                    "UPDATE offres SET statut='differee', motif_ecartement=? WHERE id=?",
                    (PREFIXE_AUTOMATIQUE + o.motif_differe, r["id"]),
                )
                nouvellement_differees += 1
                continue
            if o.differee and differee_automatiquement:
                cx.execute(
                    "UPDATE offres SET motif_ecartement=? WHERE id=?",
                    (PREFIXE_AUTOMATIQUE + o.motif_differe, r["id"]),
                )
                continue
            if not o.differee and differee_automatiquement:
                # Le reglage a ete leve : elles reviennent toutes d'un coup.
                cx.execute(
                    "UPDATE offres SET statut='nouveau', motif_ecartement=NULL WHERE id=?",
                    (r["id"],),
                )
                remises += 1
                continue

            if o.rejete_auto and statut == "nouveau":
                cx.execute(
                    "UPDATE offres SET statut='ecartee', motif_ecartement=? WHERE id=?",
                    (PREFIXE_AUTOMATIQUE + o.motif_rejet_auto, r["id"]),
                )
                nouvellement_ecartees += 1
            elif o.rejete_auto and ecartee_automatiquement:
                # Deja au rebut, mais le motif a pu changer.
                cx.execute(
                    "UPDATE offres SET motif_ecartement=? WHERE id=?",
                    (PREFIXE_AUTOMATIQUE + o.motif_rejet_auto, r["id"]),
                )
            elif not o.rejete_auto and ecartee_automatiquement:
                cx.execute(
                    "UPDATE offres SET statut='nouveau', motif_ecartement=NULL WHERE id=?",
                    (r["id"],),
                )
                remises += 1

        return (len(rows), nouvellement_ecartees, remises,
                nouvellement_differees)


# --------------------------------------------------------------------------
# Verification et archive
#
# L'archive NE SUPPRIME RIEN : elle sort l'offre de la liste active et la range
# dans un onglet a part, avec le motif. Tout le reste — score, explication,
# notes, evenements — est conserve tel quel.
# --------------------------------------------------------------------------


def enregistrer_verification(offre_id: int, verdict: str, detail: str,
                             maintenant, avance: bool, reinitialise: bool,
                             par: str = "auto") -> None:
    """Note le resultat d'une sonde.

    `avance` incremente le compteur d'echecs, `reinitialise` le remet a zero.
    Les deux a faux : on a sonde, on n'a rien conclu (site injoignable). Ce cas
    ne doit ni condamner l'offre ni effacer les preuves deja reunies.
    """
    quand = maintenant.isoformat(timespec="seconds")
    with connexion() as cx:
        if reinitialise:
            cx.execute(
                """UPDATE offres
                   SET verifiee_le = ?, verifiee_par = ?, verdict_verification = ?,
                       motif_verification = ?,
                       echecs_verification = 0, disparue_le = NULL,
                       probablement_retiree = 0
                   WHERE id = ?""",
                (quand, par, verdict, detail, offre_id),
            )
            return
        if avance:
            cx.execute(
                """UPDATE offres
                   SET verifiee_le = ?, verifiee_par = ?, verdict_verification = ?,
                       motif_verification = ?,
                       echecs_verification = COALESCE(echecs_verification, 0) + 1,
                       disparue_le = COALESCE(disparue_le, ?)
                   WHERE id = ?""",
                (quand, par, verdict, detail, quand, offre_id),
            )
            return
        cx.execute(
            """UPDATE offres
               SET verifiee_le = ?, verifiee_par = ?, verdict_verification = ?,
                   motif_verification = ?
               WHERE id = ?""",
            (quand, par, verdict, detail, offre_id),
        )


def archiver(offre_id: int, motif: str) -> None:
    with connexion() as cx:
        cx.execute(
            "UPDATE offres SET archivee_le = ?, archive_motif = ? WHERE id = ?",
            (datetime.now().isoformat(timespec="seconds"), motif, offre_id),
        )
    journaliser(offre_id, "archivee", motif)


def signaler_probablement_retiree(offre_id: int, motif: str) -> None:
    """Elle fait partie de son historique de candidature : on previent, on garde."""
    with connexion() as cx:
        deja = cx.execute(
            "SELECT probablement_retiree FROM offres WHERE id = ?", (offre_id,)
        ).fetchone()
        cx.execute(
            "UPDATE offres SET probablement_retiree = 1, archive_motif = ? WHERE id = ?",
            (motif, offre_id),
        )
    if not (deja and deja["probablement_retiree"]):
        journaliser(offre_id, "probablement_retiree", motif)


def desarchiver(offre_id: int, motif: str = "") -> None:
    """Il la ressort : on ne doit JAMAIS la rearchiver automatiquement.

    `archive_protegee` est definitif. Une decision de sa part ne se discute pas,
    exactement comme pour le rescorage.
    """
    with connexion() as cx:
        cx.execute(
            """UPDATE offres
               SET archivee_le = NULL, archive_motif = NULL, archive_protegee = 1,
                   echecs_verification = 0, probablement_retiree = 0
               WHERE id = ?""",
            (offre_id,),
        )
    journaliser(offre_id, "desarchivee", motif or "remise dans le flux a la main")


def compter_archivees_depuis(horodatage: str | None) -> int:
    """Combien d'offres sont parties a l'archive depuis sa derniere visite."""
    with connexion() as cx:
        if not horodatage:
            l = cx.execute("SELECT COUNT(*) n FROM offres WHERE archivee_le IS NOT NULL")
        else:
            l = cx.execute(
                "SELECT COUNT(*) n FROM offres WHERE archivee_le > ?", (horodatage,)
            )
        return l.fetchone()["n"]


def lister_archivees(limite: int = 200) -> list[dict]:
    with connexion() as cx:
        lignes = cx.execute(
            """SELECT * FROM offres WHERE archivee_le IS NOT NULL
               ORDER BY archivee_le DESC LIMIT ?""",
            (limite,),
        ).fetchall()
    return [_ligne_en_dict(l) for l in lignes]


def marquer_verifiee_par_edouard(offre_id: int, encore_en_ligne: bool) -> None:
    """Son constat : il a ouvert l'annonce et il a vu.

    C'est le seul moyen honnete de trancher pour les offres qu'on n'a pas le
    droit de sonder. Son verdict vaut preuve immediate — pas besoin de deux
    confirmations espacees, il a regarde.
    """
    quand = datetime.now().isoformat(timespec="seconds")
    verdict = "vivante" if encore_en_ligne else "retiree"
    with connexion() as cx:
        cx.execute(
            """UPDATE offres
               SET verifiee_le = ?, verifiee_par = 'edouard', verdict_verification = ?,
                   motif_verification = ?, echecs_verification = 0,
                   probablement_retiree = 0,
                   disparue_le = CASE WHEN ? THEN NULL ELSE COALESCE(disparue_le, ?) END,
                   archivee_le = CASE WHEN ? THEN NULL ELSE ? END,
                   archive_motif = CASE WHEN ? THEN NULL ELSE ? END,
                   archive_protegee = CASE WHEN ? THEN 1 ELSE archive_protegee END
               WHERE id = ?""",
            (quand, verdict,
             "constate en ligne par Edouard" if encore_en_ligne
             else "constate retiree par Edouard",
             encore_en_ligne, quand,
             encore_en_ligne, quand,
             encore_en_ligne, "constate retiree par Edouard",
             encore_en_ligne,
             offre_id),
        )
    journaliser(offre_id, "verifiee_par_edouard",
                "encore en ligne" if encore_en_ligne else "retiree")


def domaine_sert_encore(domaine: str, depuis_jours: int = 7,
                        maintenant: datetime | None = None) -> bool:
    """Ce domaine a-t-il rendu au moins une annonce VIVANTE recemment ?

    C'est le garde-fou contre une panne generale. Un 410 est une declaration
    du serveur, donc credible — mais si un domaine ENTIER se met a repondre
    410 d'un coup, c'est plus probablement un pare-feu applicatif ou une
    mauvaise configuration qu'une purge simultanee de toutes les annonces.

    Tant qu'aucune annonce vivante n'est connue sur ce domaine, on ne croit
    pas ses 410 sur parole : on retombe sur la regle des deux passes espacees.

    Les jours se comptent depuis `maintenant`, l'instant de la verification :
    comptes depuis l'horloge, ils faisaient echouer les tests a date figee
    une semaine apres leur date (issue #3).
    """
    if not domaine:
        return False
    maintenant = maintenant or datetime.now()
    limite = (maintenant - timedelta(days=depuis_jours)).isoformat(timespec="seconds")
    with connexion() as cx:
        ligne = cx.execute(
            """SELECT 1 FROM offres
               WHERE verdict_verification = 'vivante'
                 AND verifiee_le >= ?
                 AND (COALESCE(url_canonique, url) LIKE ? OR COALESCE(url_canonique, url) LIKE ?)
               LIMIT 1""",
            (limite, f"%://{domaine}/%", f"%://www.{domaine}/%"),
        ).fetchone()
    return ligne is not None

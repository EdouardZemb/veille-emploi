"""« Préparer ma candidature » : les étapes de `preparation.preparer` (ADR-0003, § 5).

Les voisins qui lisent le réseau, jugent la complétude ou écrivent le dossier sont remplacés
par des faux, qui notent ce qu'ils reçoivent ; `enrichissement.appliquer_texte` reste le vrai,
épié pour lire le `Rapport` qu'il rend. Une base neuve par test, les dossiers sous `tmp_path`.
Toutes les données sont inventées (M-0001).

La mutation (job `mutation` de la CI) tourne sur ce fichier : chaque champ de chaque étape se
vérifie (`_verifier_etape`), chaque chaîne écrite en base se lit, et les listes de statuts sont
écrites en clair, sans relire celles du module.
"""

from __future__ import annotations

import dataclasses
import uuid
import zipfile

import pytest

from veille import db, dossier, enrichissement, models, preparation, reglages, rendu
from veille.completude import Bilan, Manque
from veille.enrichissement import Politique
from veille.models import Offre

DOMAINE = "annonces.exemple.invalid"
NOM_DOSSIER = "2026-11-13_societe-inventee_poste-invente"
GABARIT = "lettre_inventee.md"
AVERTISSEMENTS_GENERES = ["Avertissement inventé de la génération."]
RAISON = "raison inventée"

# Écrites en clair : un statut retiré du module doit faire échouer un test.
A_PRENDRE = ("nouveau", "a_traiter", "differee")
AUTRES = (
    "candidature_envoyee", "relance_envoyee", "reponse_recue", "entretien", "refus", "accepte",
    "ecartee",
)

DESTINATAIRE_VIDE = {
    "contact_nom": "", "contact_civilite": "", "adresse_entreprise": "", "reference_annonce": "",
}

DEFAUTS = {
    "message": "", "url": "", "manques": [], "completude": None, "dossier": None,
    "genere": False, "avertissements": [], "kit_provisoire": False,
}


GRAINE = "Mission inventée de test logiciel : recette et suivi des anomalies. "


def _texte(n: int, graine: str = GRAINE) -> str:
    """Un texte d'annonce inventé de `n` caractères exactement, qui ne finit pas par un blanc
    (le nettoyage le retirerait)."""
    return (graine * (n // len(graine) + 1))[: n - 1] + "."


TEXTE_400 = _texte(400)
TEXTE_LU = _texte(400, "Annonce inventée lue sur le site : tests automatisés et qualité logicielle. ")
GRAINE_ASTREINTE = "Poste inventé avec une astreinte une semaine sur quatre, en plus des tests. "
EXTRAIT = "Extrait inventé de l'annonce."

BILAN_SUFFISANT = Bilan(
    score=80, niveau="solide",
    manques=[Manque("Manque inventé léger", 5, "Geste inventé léger.")],
    acquis=["acquis inventé"], suffisant_pour_dossier=True,
)
MANQUES_INVENTES = [
    Manque("Manque inventé A", 35, "Geste inventé A."),
    Manque("Manque inventé B", 20, "Geste inventé B."),
    Manque("Manque inventé C", 10, "Geste inventé C."),
    Manque("Manque inventé D", 5, "Geste inventé D."),
]
BILAN_MINCE = Bilan(
    score=40, niveau="mince", manques=MANQUES_INVENTES, acquis=[], suffisant_pour_dossier=False,
)


class Voisins:
    """Les faux voisins de `preparer`, réglables test par test.

    Chacun note ce qu'il reçoit, dans `appels`, et l'ordre des appels, dans `ordre`. Le faux
    `generer` écrit un dossier sous `dossier.CHEMIN_DOSSIERS` : une lettre, les `pieces`, et le
    paquet d'envoi qui les porte sous leur nom d'envoi. Le dossier s'appelle `nom_dossier`, un
    nom fixe qu'un test peut changer (une génération d'un autre jour)."""

    def __init__(self) -> None:
        self.politique = Politique(True, DOMAINE, "autorisée (inventé)")
        self.cadence = (True, "")
        self.lecture = (TEXTE_LU, "")
        self.bilan = BILAN_SUFFISANT
        self.panne: Exception | None = None
        self.nom_dossier = NOM_DOSSIER
        self.pieces = ["cv.fr.pdf"]
        self.appels: dict[str, list] = {
            "politique": [], "verifier_cadence": [], "recuperer": [], "evaluer": [], "generer": [],
        }
        self.ordre: list[str] = []
        self.rapports: list[enrichissement.Rapport] = []

    def _noter(self, nom: str, recu) -> None:
        self.appels[nom].append(recu)
        self.ordre.append(nom)

    def faux_politique(self, url):
        self._noter("politique", url)
        return self.politique

    def faux_verifier_cadence(self):
        self._noter("verifier_cadence", None)
        return self.cadence

    def faux_recuperer(self, url):
        self._noter("recuperer", url)
        return self.lecture

    def faux_evaluer(self, offre):
        self._noter("evaluer", offre)
        return self.bilan

    def faux_generer(self, offre):
        self._noter("generer", offre)
        if self.panne is not None:
            raise self.panne
        cible = dossier.CHEMIN_DOSSIERS / self.nom_dossier
        cible.mkdir(parents=True, exist_ok=True)
        (cible / "lettre-de-motivation.md").write_text("Lettre générée inventée.", encoding="utf-8")
        for piece in self.pieces:
            (cible / piece).write_bytes(b"%PDF-1.4 piece inventee")
        with zipfile.ZipFile(cible / f"{rendu.prefixe()}-candidature.zip", "w") as paquet:
            for piece in self.pieces:
                paquet.writestr(rendu.nom_pour_envoi(piece), b"%PDF-1.4 piece inventee")
        return dossier.ResultatDossier(
            chemin=cible,
            fichiers=["lettre-de-motivation.md", *self.pieces],
            gabarit_lettre=GABARIT,
            kit_provisoire=True,
            avertissements=list(AVERTISSEMENTS_GENERES),
            pieces_envoi=[rendu.nom_pour_envoi(p) for p in self.pieces],
        )


@pytest.fixture(autouse=True)
def _base_propre(tmp_path, monkeypatch):
    """Une base neuve par test, et les dossiers de candidature sous `tmp_path`."""
    monkeypatch.setattr(db, "CHEMIN_DB", tmp_path / "veille.sqlite3")
    db.initialiser()
    monkeypatch.setattr(dossier, "CHEMIN_DOSSIERS", tmp_path / "dossiers")


@pytest.fixture(autouse=True)
def voisins(monkeypatch) -> Voisins:
    """Les faux voisins, posés pour chaque test : aucun ne touche le réseau ni le kit."""
    v = Voisins()
    vrai = enrichissement.appliquer_texte

    def epier(offre_id, texte, origine):
        rapport = vrai(offre_id, texte, origine)
        v.rapports.append(rapport)
        return rapport

    monkeypatch.setattr(preparation.enrichissement, "politique", v.faux_politique)
    monkeypatch.setattr(preparation.enrichissement, "verifier_cadence", v.faux_verifier_cadence)
    monkeypatch.setattr(preparation.enrichissement, "recuperer", v.faux_recuperer)
    monkeypatch.setattr(preparation.enrichissement, "appliquer_texte", epier)
    monkeypatch.setattr(preparation.completude, "evaluer", v.faux_evaluer)
    monkeypatch.setattr(preparation.dossier, "generer", v.faux_generer)
    return v


def _offre(statut: str = "nouveau", description: str = TEXTE_400, donnees_partielles: bool = False,
           score: float | None = None) -> int:
    """Une offre inventée, dont l'adresse (`url`) et l'adresse canonique diffèrent."""
    jeton = uuid.uuid4().hex
    offre_id, _ = db.enregistrer_offre(Offre(
        titre=f"Poste inventé {jeton[:8]}",
        employeur=f"Société inventée {jeton[:8]}",
        lieu="Exempleville",
        description=description,
        url=f"https://www.{DOMAINE}/offre/{jeton}?utm_source=alerte-inventee",
        source="test",
        donnees_partielles=donnees_partielles,
    ))
    if statut != "nouveau":
        db.changer_statut(offre_id, statut)
    if score is not None:
        with db.connexion() as cx:
            cx.execute("UPDATE offres SET score = ? WHERE id = ?", (score, offre_id))
    return offre_id


def _au_dessus_du_seuil(**champs) -> int:
    return _offre(score=reglages.lire_seuil() + 10, **champs)


def _journal(offre_id: int) -> list[tuple[str, str]]:
    return [(e["type"], e["detail"]) for e in db.lire_offre(offre_id)["evenements"]]


def _verifier_etape(e, **attendu) -> None:
    """Les neuf champs de l'étape : ceux qu'on nomme à leur valeur, les autres à leur défaut."""
    assert isinstance(e, preparation.Etape)
    assert e.etape in preparation.ETAPES
    assert set(attendu) - {"etape"} <= set(DEFAUTS)
    vus = {"etape": e.etape, **{champ: getattr(e, champ) for champ in DEFAUTS}}
    assert vus == {**DEFAUTS, **attendu}


def _dossier_attendu(pieces=("cv.fr.pdf",), avertissements=(), nom=NOM_DOSSIER) -> dict:
    return {
        "nom": nom,
        "pieces": [{"nom": rendu.nom_pour_envoi(f), "fichier": f} for f in pieces],
        "archive": True,
        "destinataire": DESTINATAIRE_VIDE,
        "avertissements": list(avertissements),
    }


# --------------------------------------------------------------------------
# Jusqu'au dossier prêt
# --------------------------------------------------------------------------


def test_un_texte_complet_mene_au_dossier_pret(voisins):
    offre_id = _offre()
    lien = db.lire_offre(offre_id)["url"]
    e = preparation.preparer(offre_id)
    _verifier_etape(
        e, etape="pret", url=lien, completude=BILAN_SUFFISANT.as_dict(),
        dossier=_dossier_attendu(), genere=True, avertissements=AVERTISSEMENTS_GENERES,
        kit_provisoire=True,
    )
    offre = db.lire_offre(offre_id)
    assert offre["dossier_chemin"] == str(dossier.CHEMIN_DOSSIERS / NOM_DOSSIER)
    assert offre["statut"] == "interessante"
    assert voisins.ordre == ["evaluer", "generer"]
    # Le dossier se génère sur l'offre relue après le statut.
    assert voisins.appels["generer"][0]["id"] == offre_id
    assert voisins.appels["generer"][0]["statut"] == "interessante"
    assert voisins.appels["evaluer"][0]["statut"] == "interessante"
    assert _journal(offre_id) == [
        ("collectee", "test"), ("statut:interessante", ""), ("dossier_genere", GABARIT),
    ]


def test_un_extrait_d_une_source_autorisee_est_lu_puis_pret(voisins):
    # Marqué partiel malgré sa longueur : la marque seule en fait un extrait.
    offre_id = _offre(description=_texte(450), donnees_partielles=True)
    avant = db.lire_offre(offre_id)
    e = preparation.preparer(offre_id)
    _verifier_etape(
        e, etape="pret", url=avant["url"], completude=BILAN_SUFFISANT.as_dict(),
        dossier=_dossier_attendu(), genere=True, avertissements=AVERTISSEMENTS_GENERES,
        kit_provisoire=True,
    )
    assert avant["url_canonique"] != avant["url"]
    assert voisins.appels["politique"] == [avant["url_canonique"]]
    assert voisins.appels["recuperer"] == [avant["url_canonique"]]
    assert voisins.ordre == ["politique", "verifier_cadence", "recuperer", "evaluer", "generer"]
    offre = db.lire_offre(offre_id)
    assert offre["description"] == TEXTE_LU
    assert offre["enrichi_par"] == f"recupere sur {DOMAINE}"
    assert offre["donnees_partielles"] is False
    # La complétude juge le texte lu : l'offre est relue après la lecture.
    assert voisins.appels["evaluer"][0]["description"] == TEXTE_LU


def test_une_description_courte_est_un_extrait(voisins):
    courte = _offre(description=_texte(399))
    assert db.lire_offre(courte)["enrichi_le"] is None
    assert db.lire_offre(courte)["donnees_partielles"] is False
    preparation.preparer(courte)
    assert voisins.appels["politique"] == [db.lire_offre(courte)["url_canonique"]]
    pleine = _offre(description=_texte(400))
    assert preparation.preparer(pleine).etape == "pret"
    assert len(voisins.appels["politique"]) == 1


@pytest.mark.parametrize("bilan, etape", [(BILAN_MINCE, "mince"), (BILAN_SUFFISANT, "pret")])
def test_un_texte_colle_court_n_est_plus_un_extrait(voisins, bilan, etape):
    """Un texte complet enregistré n'est plus un extrait, même court : la préparation ne le relit
    pas et ne le redemande pas, et la complétude dit s'il est trop mince (arbitrage R6)."""
    voisins.bilan = bilan
    voisins.politique = Politique(False, DOMAINE, RAISON)
    offre_id = _offre(description=EXTRAIT, donnees_partielles=True)
    court = _texte(300)
    e = preparation.preparer(offre_id, texte=court)
    assert e.etape == etape
    assert "politique" not in voisins.ordre
    assert voisins.ordre[0] == "evaluer"
    assert voisins.appels["evaluer"][0]["description"] == court
    assert db.lire_offre(offre_id)["enrichi_par"] == "colle a la main"


def test_un_texte_colle_un_autre_jour_n_est_pas_relu(voisins):
    """Une description courte, mais collée un autre jour (`enrichi_le` posé) : jamais relue."""
    offre_id = _offre(description=_texte(300))
    with db.connexion() as cx:
        cx.execute(
            "UPDATE offres SET enrichi_le = ?, enrichi_par = ? WHERE id = ?",
            ("2026-11-12T08:30:00", "colle a la main", offre_id),
        )
    assert preparation.preparer(offre_id).etape == "pret"
    assert voisins.ordre == ["evaluer", "generer"]


def test_une_source_interdite_mene_a_l_etape_texte(voisins):
    voisins.politique = Politique(False, DOMAINE, RAISON, "Conseil inventé.")
    offre_id = _offre(description=EXTRAIT, donnees_partielles=True)
    e = preparation.preparer(offre_id)
    _verifier_etape(e, etape="texte", message=RAISON, url=db.lire_offre(offre_id)["url"])
    assert voisins.ordre == ["politique"]
    assert db.lire_offre(offre_id)["statut"] == "interessante"


def test_une_cadence_depassee_mene_a_l_etape_texte(voisins):
    voisins.cadence = (False, "cadence inventée dépassée")
    offre_id = _offre(description=EXTRAIT, donnees_partielles=True)
    e = preparation.preparer(offre_id)
    _verifier_etape(
        e, etape="texte", message="cadence inventée dépassée", url=db.lire_offre(offre_id)["url"],
    )
    assert voisins.ordre == ["politique", "verifier_cadence"]


def test_une_lecture_en_echec_mene_a_l_etape_texte(voisins):
    voisins.lecture = ("", "lecture inventée en échec")
    offre_id = _offre(description=EXTRAIT, donnees_partielles=True)
    e = preparation.preparer(offre_id)
    _verifier_etape(
        e, etape="texte", message="lecture inventée en échec", url=db.lire_offre(offre_id)["url"],
    )
    assert voisins.ordre == ["politique", "verifier_cadence", "recuperer"]
    assert voisins.rapports == []


def test_un_texte_lu_trop_court_mene_a_l_etape_texte(voisins):
    voisins.lecture = ("Lecture inventée bien courte.", "")
    offre_id = _offre(description=EXTRAIT, donnees_partielles=True)
    e = preparation.preparer(offre_id)
    [rapport] = voisins.rapports
    assert rapport.ok is False
    _verifier_etape(e, etape="texte", message=rapport.message, url=db.lire_offre(offre_id)["url"])
    assert db.lire_offre(offre_id)["description"] == EXTRAIT
    assert "generer" not in voisins.ordre


@pytest.mark.parametrize(
    "url, canonique, lue, montree",
    [
        ("U", "C", "C", "U"),
        ("U", None, "U", "U"),
        (None, "C", "C", "C"),
        (None, None, "", ""),
    ],
)
def test_les_adresses_de_l_annonce(voisins, url, canonique, lue, montree):
    """La lecture prend l'adresse canonique, sinon l'adresse ; l'étape montre l'adresse, sinon la
    canonique, et rien sans l'une ni l'autre (décision 13)."""
    adresses = {
        "U": f"https://www.{DOMAINE}/offre/montree?utm_source=alerte-inventee",
        "C": f"https://{DOMAINE}/offre/lue",
        None: None,
        "": "",
    }
    offre_id = _offre(description=EXTRAIT, donnees_partielles=True)
    with db.connexion() as cx:
        cx.execute(
            "UPDATE offres SET url = ?, url_canonique = ? WHERE id = ?",
            (adresses[url], adresses[canonique], offre_id),
        )
    voisins.politique = Politique(False, DOMAINE, RAISON)
    e = preparation.preparer(offre_id)
    assert voisins.appels["politique"] == [adresses[lue]]
    _verifier_etape(e, etape="texte", message=RAISON, url=adresses[montree])


# --------------------------------------------------------------------------
# Le texte fourni
# --------------------------------------------------------------------------


def test_un_texte_fourni_est_enregistre_avant_la_generation(voisins):
    voisins.panne = RuntimeError("panne inventée")
    offre_id = _offre(description=EXTRAIT, donnees_partielles=True)
    e = preparation.preparer(offre_id, texte=TEXTE_400)
    _verifier_etape(e, etape="echec", message="panne inventée", url=db.lire_offre(offre_id)["url"])
    offre = db.lire_offre(offre_id)
    assert offre["description"] == TEXTE_400
    assert offre["enrichi_par"] == "colle a la main"
    assert offre["statut"] == "interessante"
    assert offre["dossier_chemin"] is None
    assert voisins.ordre == ["evaluer", "generer"]
    # La génération reçoit le texte fourni : l'offre est relue après lui.
    assert voisins.appels["generer"][0]["description"] == TEXTE_400


def test_un_echec_sans_message_nomme_l_exception(voisins):
    voisins.panne = RuntimeError()
    offre_id = _offre()
    e = preparation.preparer(offre_id)
    _verifier_etape(e, etape="echec", message="RuntimeError", url=db.lire_offre(offre_id)["url"])


def test_un_texte_fourni_trop_court_mene_a_l_etape_texte(voisins):
    offre_id = _offre(description=EXTRAIT, donnees_partielles=True)
    e = preparation.preparer(offre_id, texte="trop court")
    [rapport] = voisins.rapports
    assert rapport.ok is False
    _verifier_etape(e, etape="texte", message=rapport.message, url=db.lire_offre(offre_id)["url"])
    assert voisins.ordre == []
    assert db.lire_offre(offre_id)["description"] == EXTRAIT


@pytest.mark.parametrize("vide", ["", "   "])
def test_un_texte_vide_vaut_aucun_texte(voisins, vide):
    voisins.politique = Politique(False, DOMAINE, RAISON)
    offre_id = _offre(description=EXTRAIT, donnees_partielles=True)
    e = preparation.preparer(offre_id, texte=vide)
    _verifier_etape(e, etape="texte", message=RAISON, url=db.lire_offre(offre_id)["url"])
    assert voisins.rapports == []
    assert db.lire_offre(offre_id)["description"] == EXTRAIT
    assert voisins.ordre == ["politique"]


# --------------------------------------------------------------------------
# La complétude, et forcer
# --------------------------------------------------------------------------


def test_une_completude_mince_mene_a_l_etape_mince(voisins):
    voisins.bilan = BILAN_MINCE
    offre_id = _offre()
    e = preparation.preparer(offre_id)
    _verifier_etape(
        e, etape="mince", url=db.lire_offre(offre_id)["url"],
        manques=[m.as_dict() for m in MANQUES_INVENTES[:3]], completude=BILAN_MINCE.as_dict(),
    )
    assert e.manques[0]["libelle"] == "Manque inventé A"
    assert e.manques[2]["libelle"] == "Manque inventé C"
    assert "generer" not in voisins.ordre


def test_forcer_genere_malgre_une_completude_mince(voisins):
    voisins.bilan = BILAN_MINCE
    offre_id = _offre()
    e = preparation.preparer(offre_id, forcer=True)
    _verifier_etape(
        e, etape="pret", url=db.lire_offre(offre_id)["url"], completude=BILAN_MINCE.as_dict(),
        dossier=_dossier_attendu(), genere=True, avertissements=AVERTISSEMENTS_GENERES,
        kit_provisoire=True,
    )


def test_forcer_saute_aussi_l_etape_texte(voisins):
    """« Générer avec l'extrait » : une annonce dont le texte ne se copie pas (décision 4)."""
    voisins.politique = Politique(False, DOMAINE, RAISON)
    offre_id = _offre(description=EXTRAIT, donnees_partielles=True)
    e = preparation.preparer(offre_id, forcer=True)
    _verifier_etape(
        e, etape="pret", url=db.lire_offre(offre_id)["url"], completude=BILAN_SUFFISANT.as_dict(),
        dossier=_dossier_attendu(), genere=True, avertissements=AVERTISSEMENTS_GENERES,
        kit_provisoire=True,
    )
    assert voisins.ordre == ["evaluer", "generer"]


# --------------------------------------------------------------------------
# L'alerte éliminatoire (décision 5)
# --------------------------------------------------------------------------


def _alerte(voisins) -> str:
    """L'alerte du seul texte enregistré par le passage, telle que le `Rapport` la dit."""
    [rapport] = voisins.rapports
    assert rapport.alerte_eliminatoire.startswith("Cette offre etait au-dessus de ton seuil")
    return rapport.alerte_eliminatoire


@pytest.mark.filterwarnings("ignore:Duplicate name")
def test_l_alerte_eliminatoire_du_texte_colle_se_dit(voisins):
    # Deux pièces au même nom d'envoi : l'avertissement de `dossier_pret` vient en dernier.
    voisins.pieces = ["cv.fr.pdf", "cv-ancien.fr.pdf"]
    offre_id = _au_dessus_du_seuil()
    e = preparation.preparer(offre_id, texte=_texte(400, GRAINE_ASTREINTE))
    # Le statut s'écrit avant le texte : l'éliminatoire n'écarte pas l'offre.
    assert db.lire_offre(offre_id)["statut"] == "interessante"
    alerte = _alerte(voisins)
    assert e.etape == "pret"
    assert e.avertissements[0] == alerte
    assert e.avertissements == [alerte, *AVERTISSEMENTS_GENERES, *e.dossier["avertissements"]]
    assert len(e.dossier["avertissements"]) == 1


@pytest.mark.parametrize("etape", ["mince", "echec"])
def test_l_alerte_precede_aussi_les_etapes_qui_s_arretent(voisins, etape):
    """Une alerte s'ajoute en tête des avertissements de toute étape qui suit un texte enregistré.
    L'étape `texte` n'en suit jamais : un texte enregistré n'est plus un extrait (arbitrage R6)."""
    if etape == "mince":
        voisins.bilan = BILAN_MINCE
    else:
        voisins.panne = RuntimeError("panne inventée")
    offre_id = _au_dessus_du_seuil()
    e = preparation.preparer(offre_id, texte=_texte(400, GRAINE_ASTREINTE))
    assert e.etape == etape
    assert e.avertissements == [_alerte(voisins)]
    assert db.lire_offre(offre_id)["statut"] == "interessante"


def test_l_alerte_du_texte_lu_se_dit_aussi(voisins):
    voisins.lecture = (_texte(400, GRAINE_ASTREINTE), "")
    offre_id = _au_dessus_du_seuil(description=EXTRAIT, donnees_partielles=True)
    e = preparation.preparer(offre_id)
    assert e.etape == "pret"
    assert e.avertissements == [_alerte(voisins), *AVERTISSEMENTS_GENERES]
    assert db.lire_offre(offre_id)["statut"] == "interessante"


# --------------------------------------------------------------------------
# Les statuts
# --------------------------------------------------------------------------


@pytest.mark.parametrize("statut", A_PRENDRE)
def test_les_statuts_a_prendre_passent_en_interessante(voisins, statut):
    offre_id = _offre(statut)
    assert preparation.preparer(offre_id).etape == "pret"
    assert db.lire_offre(offre_id)["statut"] == "interessante"
    assert _journal(offre_id).count(("statut:interessante", "")) == 1


def test_une_offre_deja_interessante_ne_change_pas_de_statut(voisins):
    offre_id = _offre("interessante")
    avant = [t for t, _ in _journal(offre_id) if t.startswith("statut:")]
    assert preparation.preparer(offre_id).etape == "pret"
    assert [t for t, _ in _journal(offre_id) if t.startswith("statut:")] == avant
    assert db.lire_offre(offre_id)["statut"] == "interessante"


@pytest.mark.parametrize("statut", AUTRES)
def test_les_autres_etats_sont_refuses(voisins, statut):
    offre_id = _offre(statut)
    avant = db.lire_offre(offre_id)
    with pytest.raises(preparation.EtatIncompatible) as refus:
        preparation.preparer(offre_id, texte=TEXTE_400)
    assert refus.value.args == ()
    # Ni statut, ni texte, ni journal : rien n'est écrit.
    assert db.lire_offre(offre_id) == avant
    assert voisins.ordre == []
    assert voisins.rapports == []


def test_les_listes_font_le_tour_des_statuts():
    tous = (*A_PRENDRE, "interessante", *AUTRES)
    assert len(tous) == len(set(tous))
    assert set(tous) == set(models.STATUTS)


def test_une_offre_inconnue_leve(voisins):
    with pytest.raises(preparation.OffreInconnue) as refus:
        preparation.preparer(987654)
    assert refus.value.args == ()
    assert voisins.ordre == []


def test_l_etape_rend_toujours_ses_neuf_cles():
    noms = [
        "etape", "message", "url", "manques", "completude", "dossier", "genere", "avertissements",
        "kit_provisoire",
    ]
    assert [f.name for f in dataclasses.fields(preparation.Etape)] == noms
    vide = preparation.Etape("texte").as_dict()
    assert list(vide) == noms
    assert vide == {"etape": "texte", **DEFAUTS}
    pleine = preparation.Etape(
        "pret", message="m", url="u", manques=[{"libelle": "l"}], completude={"score": 1},
        dossier={"nom": "d"}, genere=True, avertissements=["a"], kit_provisoire=True,
    ).as_dict()
    assert pleine == {
        "etape": "pret", "message": "m", "url": "u", "manques": [{"libelle": "l"}],
        "completude": {"score": 1}, "dossier": {"nom": "d"}, "genere": True,
        "avertissements": ["a"], "kit_provisoire": True,
    }


# --------------------------------------------------------------------------
# Le dossier prêt
# --------------------------------------------------------------------------


def _paquet(repertoire):
    return repertoire / f"{rendu.prefixe()}-candidature.zip"


def _dossier_sur_disque(fichiers, paquet=None, nom=NOM_DOSSIER):
    """Une offre « Je postule » et son dossier : les `fichiers`, et un paquet d'envoi qui porte
    les noms d'envoi `paquet` (aucun paquet si None)."""
    repertoire = dossier.CHEMIN_DOSSIERS / nom
    repertoire.mkdir(parents=True)
    for f in fichiers:
        (repertoire / f).write_bytes(b"piece inventee")
    if paquet is not None:
        with zipfile.ZipFile(_paquet(repertoire), "w") as z:
            for n in paquet:
                z.writestr(n, b"piece inventee")
    offre_id = _offre("interessante")
    db.maj_champs(offre_id, dossier_chemin=str(repertoire))
    return offre_id, repertoire


def test_le_dossier_pret_liste_les_pieces_du_paquet_d_envoi():
    lettre = f"{rendu.prefixe()}-Lettre-de-motivation.pdf"
    offre_id, repertoire = _dossier_sur_disque(
        ["cv.fr.pdf", lettre, "fiche-offre.md", "notes-inventees.pdf"],
        paquet=[rendu.nom_pour_envoi("cv.fr.pdf"), rendu.nom_pour_envoi(lettre)],
    )
    d = preparation.dossier_pret(db.lire_offre(offre_id))
    # Triées par nom d'envoi, qui ne suit pas l'ordre des noms sur le disque.
    assert d == {
        "nom": NOM_DOSSIER,
        "pieces": [
            {"nom": rendu.nom_pour_envoi("cv.fr.pdf"), "fichier": "cv.fr.pdf"},
            {"nom": rendu.nom_pour_envoi(lettre), "fichier": lettre},
        ],
        "archive": True,
        "destinataire": DESTINATAIRE_VIDE,
        "avertissements": [],
    }
    # Le paquet est refermé : `generer` peut le supprimer, ce que Windows refuse à un fichier ouvert.
    _paquet(repertoire).unlink()


def test_sans_paquet_d_envoi_le_dossier_pret_n_a_aucune_piece():
    offre_id, _ = _dossier_sur_disque(["cv.fr.pdf", "lettre-de-motivation.md"])
    assert preparation.dossier_pret(db.lire_offre(offre_id)) == {
        "nom": NOM_DOSSIER, "pieces": [], "archive": False, "destinataire": DESTINATAIRE_VIDE,
        "avertissements": [],
    }


def test_un_paquet_tronque_vaut_un_paquet_absent():
    offre_id, repertoire = _dossier_sur_disque(["cv.fr.pdf"])
    _paquet(repertoire).write_bytes(b"PK\x03\x04 tronque")
    assert preparation.dossier_pret(db.lire_offre(offre_id)) == {
        "nom": NOM_DOSSIER, "pieces": [], "archive": False, "destinataire": DESTINATAIRE_VIDE,
        "avertissements": [],
    }
    _paquet(repertoire).unlink()


def test_deux_pieces_au_meme_nom_d_envoi_sont_signalees():
    nom = rendu.nom_pour_envoi("lettre-de-motivation.pdf")
    assert nom == rendu.nom_pour_envoi("lettre-de-recommandation-inventee.pdf")
    offre_id, _ = _dossier_sur_disque(
        ["lettre-de-motivation.pdf", "lettre-de-recommandation-inventee.pdf", "cv.fr.pdf"],
        paquet=[nom, rendu.nom_pour_envoi("cv.fr.pdf")],
    )
    d = preparation.dossier_pret(db.lire_offre(offre_id))
    assert d["pieces"] == [
        {"nom": rendu.nom_pour_envoi("cv.fr.pdf"), "fichier": "cv.fr.pdf"},
        {"nom": nom, "fichier": "lettre-de-motivation.pdf"},
        {"nom": nom, "fichier": "lettre-de-recommandation-inventee.pdf"},
    ]
    assert d["avertissements"] == [
        f"lettre-de-motivation.pdf, lettre-de-recommandation-inventee.pdf partent sous le même "
        f"nom, {nom} : le recruteur n'en recevra qu'une. Renomme les autres dans le kit."
    ]


def test_le_dossier_pret_dit_a_qui_la_lettre_est_adressee():
    offre_id, _ = _dossier_sur_disque(["cv.fr.pdf"], paquet=[rendu.nom_pour_envoi("cv.fr.pdf")])
    destinataire = {
        "contact_nom": "Alex Inventé",
        "contact_civilite": "Madame",
        "adresse_entreprise": "1 rue Inventée, 68000 Exempleville",
        "reference_annonce": "REF-INVENTEE-42",
    }
    db.maj_champs(offre_id, **destinataire)
    assert preparation.dossier_pret(db.lire_offre(offre_id))["destinataire"] == destinataire
    # Un champ vidé, ou jamais rempli, est une chaîne vide.
    db.maj_champs(offre_id, contact_nom="", contact_civilite=None)
    assert preparation.dossier_pret(db.lire_offre(offre_id))["destinataire"] == {
        **destinataire, "contact_nom": "", "contact_civilite": "",
    }


def test_sans_dossier_sur_le_disque_le_dossier_pret_est_none():
    offre_id = _offre("interessante")
    assert preparation.dossier_pret(db.lire_offre(offre_id)) is None
    db.maj_champs(offre_id, dossier_chemin=str(dossier.CHEMIN_DOSSIERS / "dossier-absent-invente"))
    assert preparation.dossier_pret(db.lire_offre(offre_id)) is None

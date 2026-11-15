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
import json
import uuid
import zipfile

import pytest

from veille import db, dossier, enrichissement, lettre, models, preparation, reglages, rendu
from veille.completude import Bilan, Manque
from veille.enrichissement import Politique
from veille.models import Offre

DOMAINE = "annonces.exemple.invalid"
NOM_DOSSIER = "2026-11-13_societe-inventee_poste-invente"
# Le dossier que la même offre reçoit un autre jour : `generer` le date du jour.
NOM_AUTRE_JOUR = "2026-11-14_societe-inventee_poste-invente"
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
# L'avertissement de « Dossier prêt » quand la base porte un autre destinataire que la lettre.
ECART = (
    "Un autre destinataire est enregistré, que la lettre n'a pas encore. Pour l'y mettre, touche "
    "« Modifier le destinataire », puis « Enregistrer et régénérer »."
)

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
BILAN_30 = Bilan(
    score=30, niveau="mince", manques=MANQUES_INVENTES, acquis=[], suffisant_pour_dossier=False,
)


class Voisins:
    """Les faux voisins de `preparer`, réglables test par test.

    Chacun note ce qu'il reçoit, dans `appels`, et l'ordre des appels, dans `ordre`. Le faux
    `generer` écrit un dossier sous `dossier.CHEMIN_DOSSIERS` : une lettre (`texte_lettre`), les
    `pieces`, le paquet d'envoi qui les porte sous leur nom d'envoi, puis la note du destinataire.
    Le dossier s'appelle `nom_dossier`, un nom fixe qu'un test peut changer (une génération d'un
    autre jour). Comme le vrai, il réécrit la lettre d'un dossier qui existe, sans l'historiser,
    et retire la note avant de la réécrire. `panne` lève avant toute écriture, ou, avec
    `lettre_avant_la_panne`, juste après la lettre réécrite, comme le vrai qui casse plus loin."""

    def __init__(self) -> None:
        self.politique = Politique(True, DOMAINE, "autorisée (inventé)")
        self.cadence = (True, "")
        self.lecture = (TEXTE_LU, "")
        self.bilan = BILAN_SUFFISANT
        self.panne: Exception | None = None
        self.lettre_avant_la_panne = False
        self.nom_dossier = NOM_DOSSIER
        self.texte_lettre = "Lettre générée inventée."
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
        if self.panne is not None and not self.lettre_avant_la_panne:
            raise self.panne
        cible = dossier.CHEMIN_DOSSIERS / self.nom_dossier
        cible.mkdir(parents=True, exist_ok=True)
        (cible / lettre.NOM_DESTINATAIRE).unlink(missing_ok=True)
        (cible / "lettre-de-motivation.md").write_text(self.texte_lettre, encoding="utf-8")
        if self.panne is not None:
            raise self.panne
        for piece in self.pieces:
            (cible / piece).write_bytes(b"%PDF-1.4 piece inventee")
        with zipfile.ZipFile(cible / f"{rendu.prefixe()}-candidature.zip", "w") as paquet:
            for piece in self.pieces:
                paquet.writestr(rendu.nom_pour_envoi(piece), b"%PDF-1.4 piece inventee")
        dossier.ecrire_note_destinataire(cible, offre)
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


def _dossier_attendu(
    pieces=("cv.fr.pdf",), avertissements=(), nom=NOM_DOSSIER, note=DESTINATAIRE_VIDE,
) -> dict:
    """`note` : le destinataire de la note du dossier, celle qu'écrit le faux `generer` ; None
    pour un dossier sans note."""
    return {
        "nom": nom,
        "pieces": [{"nom": rendu.nom_pour_envoi(f), "fichier": f} for f in pieces],
        "archive": True,
        "destinataire": DESTINATAIRE_VIDE,
        "destinataire_lettre": note,
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
    # Le statut s'écrit avant le texte : l'éliminatoire n'écarte pas l'offre. Écrit après, il
    # finirait aussi `interessante`, mais avec le motif d'écartement automatique que le texte
    # aurait posé, et le texte avant lui au journal.
    offre = db.lire_offre(offre_id)
    assert offre["statut"] == "interessante"
    assert offre["motif_ecartement"] is None
    types = [t for t, _ in _journal(offre_id)]
    assert types.index("statut:interessante") < types.index("texte_complet")
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


def _dossier_sur_disque(fichiers, paquet=None, nom=NOM_DOSSIER, **offre):
    """Une offre « Je postule » et son dossier : les `fichiers`, et un paquet d'envoi qui porte
    les noms d'envoi `paquet` (aucun paquet si None). `offre` va à `_offre`."""
    repertoire = dossier.CHEMIN_DOSSIERS / nom
    repertoire.mkdir(parents=True)
    for f in fichiers:
        (repertoire / f).write_bytes(b"piece inventee")
    if paquet is not None:
        with zipfile.ZipFile(_paquet(repertoire), "w") as z:
            for n in paquet:
                z.writestr(n, b"piece inventee")
    offre_id = _offre("interessante", **offre)
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
        "destinataire_lettre": None,
        "avertissements": [],
    }
    # Le paquet est refermé : `generer` peut le supprimer, ce que Windows refuse à un fichier ouvert.
    _paquet(repertoire).unlink()


def test_sans_paquet_d_envoi_le_dossier_pret_n_a_aucune_piece():
    offre_id, _ = _dossier_sur_disque(["cv.fr.pdf", "lettre-de-motivation.md"])
    assert preparation.dossier_pret(db.lire_offre(offre_id)) == {
        "nom": NOM_DOSSIER, "pieces": [], "archive": False, "destinataire": DESTINATAIRE_VIDE,
        "destinataire_lettre": None, "avertissements": [],
    }


def test_un_paquet_tronque_vaut_un_paquet_absent():
    offre_id, repertoire = _dossier_sur_disque(["cv.fr.pdf"])
    _paquet(repertoire).write_bytes(b"PK\x03\x04 tronque")
    assert preparation.dossier_pret(db.lire_offre(offre_id)) == {
        "nom": NOM_DOSSIER, "pieces": [], "archive": False, "destinataire": DESTINATAIRE_VIDE,
        "destinataire_lettre": None, "avertissements": [],
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


# --------------------------------------------------------------------------
# La note du destinataire : « Dossier prêt » dit celui que porte la lettre
# --------------------------------------------------------------------------

ADRESSEE = {
    "contact_nom": "Alex Inventé",
    "contact_civilite": "Madame",
    "adresse_entreprise": "1 rue Inventée\n68000 Exempleville",
    "reference_annonce": "REF-INVENTEE-42",
}
# Écrits en clair : un champ retiré de la note doit faire échouer un test.
CHAMPS = ("contact_nom", "contact_civilite", "adresse_entreprise", "reference_annonce")


def _dossier_note(**base):
    """Un dossier sur le disque, sa note écrite d'après la base `base`, comme `generer` la
    laisse."""
    offre_id, repertoire = _dossier_sur_disque(
        ["cv.fr.pdf"], paquet=[rendu.nom_pour_envoi("cv.fr.pdf")],
    )
    if base:
        db.maj_champs(offre_id, **base)
    dossier.ecrire_note_destinataire(repertoire, db.lire_offre(offre_id))
    return offre_id, repertoire


def test_les_champs_de_la_note_sont_ceux_du_destinataire():
    assert dossier.CHAMPS_DESTINATAIRE == CHAMPS
    assert preparation.CHAMPS_DESTINATAIRE == CHAMPS
    assert lettre.NOM_DESTINATAIRE == "lettre.destinataire.json"
    assert lettre.NOM_DESTINATAIRE in lettre.JAMAIS_AU_RECRUTEUR


def test_une_note_egale_a_la_base_dit_a_qui_la_lettre_est_adressee():
    offre_id, _ = _dossier_note(**ADRESSEE)
    d = preparation.dossier_pret(db.lire_offre(offre_id))
    assert d["destinataire"] == ADRESSEE
    assert d["destinataire_lettre"] == ADRESSEE
    assert d["avertissements"] == []


@pytest.mark.parametrize("champ", CHAMPS)
@pytest.mark.parametrize("enregistre", ["Valeur inventée enregistrée après la lettre", ""])
def test_une_note_differente_montre_la_lettre_et_le_dit(champ, enregistre):
    """La vue détaillée enregistre un destinataire sans régénérer : la lettre garde le sien,
    l'écran le montre, et dit l'écart et le geste qui le corrige."""
    offre_id, _ = _dossier_note(**ADRESSEE)
    db.maj_champs(offre_id, **{champ: enregistre})
    d = preparation.dossier_pret(db.lire_offre(offre_id))
    assert d["destinataire_lettre"] == ADRESSEE
    assert d["destinataire"] == {**ADRESSEE, champ: enregistre}
    assert d["avertissements"] == [ECART]


def test_une_lettre_sans_destinataire_et_une_base_qui_en_a_un():
    offre_id, _ = _dossier_note()
    db.maj_champs(offre_id, **ADRESSEE)
    d = preparation.dossier_pret(db.lire_offre(offre_id))
    assert d["destinataire_lettre"] == DESTINATAIRE_VIDE
    assert d["destinataire"] == ADRESSEE
    assert d["avertissements"] == [ECART]


def test_sans_note_le_dossier_pret_n_affirme_aucun_destinataire():
    """Un dossier d'avant le lot 2, déjà en prod : rien ne dit ce que porte sa lettre."""
    offre_id, _ = _dossier_sur_disque(["cv.fr.pdf"], paquet=[rendu.nom_pour_envoi("cv.fr.pdf")])
    db.maj_champs(offre_id, **ADRESSEE)
    d = preparation.dossier_pret(db.lire_offre(offre_id))
    assert d["destinataire_lettre"] is None
    assert d["destinataire"] == ADRESSEE
    assert d["avertissements"] == []


@pytest.mark.parametrize(
    "contenu",
    [
        b"{ tronque",
        b"[]",
        b'"une chaine"',
        b'{"contact_nom": "", "contact_civilite": "", "adresse_entreprise": ""}',
        b'{"contact_nom": 3, "contact_civilite": "", "adresse_entreprise": "", '
        b'"reference_annonce": ""}',
        b"\xff\xfe\x00",
    ],
)
def test_une_note_illisible_vaut_une_note_absente(contenu):
    offre_id, repertoire = _dossier_note(**ADRESSEE)
    (repertoire / lettre.NOM_DESTINATAIRE).write_bytes(contenu)
    d = preparation.dossier_pret(db.lire_offre(offre_id))
    assert d["destinataire_lettre"] is None
    assert d["avertissements"] == []


def test_une_note_qui_n_est_pas_un_fichier_vaut_une_note_absente():
    offre_id, repertoire = _dossier_sur_disque(["cv.fr.pdf"])
    (repertoire / lettre.NOM_DESTINATAIRE).mkdir()
    assert dossier.lire_note_destinataire(repertoire) is None
    assert preparation.dossier_pret(db.lire_offre(offre_id))["destinataire_lettre"] is None


def test_la_note_porte_les_quatre_champs_et_rien_d_autre(tmp_path):
    dossier.ecrire_note_destinataire(tmp_path, {**ADRESSEE, "titre": "Poste inventé"})
    assert dossier.lire_note_destinataire(tmp_path) == ADRESSEE
    note = json.loads((tmp_path / lettre.NOM_DESTINATAIRE).read_text(encoding="utf-8"))
    assert note == ADRESSEE
    # Un champ absent ou vide de l'offre est une chaîne vide.
    dossier.ecrire_note_destinataire(tmp_path, {"contact_nom": None})
    assert dossier.lire_note_destinataire(tmp_path) == DESTINATAIRE_VIDE


def _generer_avec(monkeypatch, voisins, *, kit_provisoire, avertissements) -> None:
    """Le faux `generer` des voisins, dont le résultat porte ces `avertissements`."""
    def generer(offre):
        resultat = voisins.faux_generer(offre)
        return dataclasses.replace(
            resultat, kit_provisoire=kit_provisoire, avertissements=list(avertissements),
        )

    monkeypatch.setattr(preparation.dossier, "generer", generer)


def test_le_kit_provisoire_ne_se_dit_qu_une_fois(voisins, monkeypatch):
    """Le bloc de « Dossier prêt » dit le kit provisoire : l'étape ne reprend pas la phrase de
    `generer`, mais garde les autres avertissements."""
    _generer_avec(
        monkeypatch, voisins, kit_provisoire=True,
        avertissements=[dossier.AVERTISSEMENT_KIT_PROVISOIRE, "avertissement inventé"],
    )
    e = preparation.preparer(_offre())
    assert e.etape == "pret"
    assert e.avertissements == ["avertissement inventé"]
    assert e.kit_provisoire is True


def test_sans_kit_provisoire_les_avertissements_restent_entiers(voisins, monkeypatch):
    _generer_avec(
        monkeypatch, voisins, kit_provisoire=False, avertissements=["a inventé", "b inventé"],
    )
    e = preparation.preparer(_offre())
    assert e.avertissements == ["a inventé", "b inventé"]
    assert e.kit_provisoire is False


def test_la_phrase_du_kit_n_est_retiree_que_si_le_kit_est_provisoire(voisins, monkeypatch):
    _generer_avec(
        monkeypatch, voisins, kit_provisoire=False,
        avertissements=[dossier.AVERTISSEMENT_KIT_PROVISOIRE, "avertissement inventé"],
    )
    e = preparation.preparer(_offre())
    assert e.avertissements == [dossier.AVERTISSEMENT_KIT_PROVISOIRE, "avertissement inventé"]


@pytest.mark.filterwarnings("ignore:Duplicate name")
def test_l_ecart_du_destinataire_suit_l_alerte_puis_les_doublons(voisins):
    """L'ordre R5 : l'alerte éliminatoire, puis la génération, puis `dossier_pret`, qui dit les
    noms d'envoi en double, puis l'écart du destinataire."""
    nom = rendu.nom_pour_envoi("lettre-de-motivation.pdf")
    offre_id, repertoire = _dossier_sur_disque(
        ["lettre-de-motivation.pdf", "lettre-de-recommandation-inventee.pdf"], paquet=[nom],
        score=reglages.lire_seuil() + 10,
    )
    dossier.ecrire_note_destinataire(repertoire, db.lire_offre(offre_id))
    db.maj_champs(offre_id, contact_nom=ADRESSEE["contact_nom"])
    e = preparation.preparer(offre_id, texte=_texte(400, GRAINE_ASTREINTE))
    doublon = (
        f"lettre-de-motivation.pdf, lettre-de-recommandation-inventee.pdf partent sous le même "
        f"nom, {nom} : le recruteur n'en recevra qu'une. Renomme les autres dans le kit."
    )
    assert e.etape == "pret"
    assert e.dossier["avertissements"] == [doublon, ECART]
    assert e.avertissements == [_alerte(voisins), doublon, ECART]
    assert voisins.ordre == []


def test_regenerer_met_le_destinataire_enregistre_dans_la_lettre(voisins):
    """« Enregistrer et régénérer » : la note suit la lettre refaite, et l'écart disparaît."""
    offre_id, repertoire = _dossier_note()
    db.maj_champs(offre_id, **ADRESSEE)
    assert preparation.preparer(offre_id).avertissements == [ECART]
    e = preparation.preparer(offre_id, regenerer=True)
    assert e.etape == "pret"
    assert e.dossier["destinataire_lettre"] == ADRESSEE
    assert e.dossier["destinataire"] == ADRESSEE
    assert e.avertissements == AVERTISSEMENTS_GENERES
    assert dossier.lire_note_destinataire(repertoire) == ADRESSEE


# --------------------------------------------------------------------------
# Un dossier existant, et la régénération (décisions 6 à 8, invariant 4)
# --------------------------------------------------------------------------

LETTRE_ASSEMBLEE = "Lettre assemblée inventée"
LETTRE_AFFINEE = "Lettre affinée inventée"
LETTRE_REGENEREE = "Lettre régénérée inventée"
ABSENT = "dossier-absent-invente"


def _dossier_existant(lettre_courante=None, **offre):
    """Une offre « Je postule » et son dossier `NOM_DOSSIER`, tel que `generer` l'a laissé :
    `cv.fr.pdf` et son paquet d'envoi, et la lettre `lettre_courante` (aucune si None)."""
    offre_id, repertoire = _dossier_sur_disque(
        ["cv.fr.pdf"], paquet=[rendu.nom_pour_envoi("cv.fr.pdf")], **offre,
    )
    if lettre_courante is not None:
        _ecrire_lettre(repertoire, lettre_courante)
    return offre_id, repertoire


def _ecrire_lettre(repertoire, texte: str) -> None:
    (repertoire / lettre.NOM_LETTRE).write_text(texte, encoding="utf-8")


def _lire_lettre(repertoire) -> str:
    return (repertoire / lettre.NOM_LETTRE).read_text(encoding="utf-8")


def _noms_de_l_historique(repertoire) -> list[str]:
    return sorted(f.name for f in (repertoire / lettre.NOM_HISTORIQUE).iterdir())


def _verifier_generee(e, offre_id, bilan=BILAN_SUFFISANT, nom=NOM_DOSSIER) -> None:
    """L'étape `pret` d'un passage qui génère : ce que disent les faux, et le dossier `nom`."""
    _verifier_etape(
        e, etape="pret", url=db.lire_offre(offre_id)["url"], completude=bilan.as_dict(),
        dossier=_dossier_attendu(nom=nom), genere=True, avertissements=AVERTISSEMENTS_GENERES,
        kit_provisoire=True,
    )


def test_sans_regenerer_un_dossier_existant_est_rendu_sans_generer(voisins):
    offre_id, repertoire = _dossier_existant()
    lien = db.lire_offre(offre_id)["url"]
    e = preparation.preparer(offre_id)
    # Ni avertissements ni kit provisoire : ils ne valent qu'au passage qui génère. Un dossier
    # écrit à la main n'a pas de note.
    _verifier_etape(e, etape="pret", url=lien, dossier=_dossier_attendu(note=None))
    assert voisins.ordre == []
    assert [t for t, _ in _journal(offre_id) if t.startswith("dossier_")] == []
    # Le dossier n'est plus sur le disque : la préparation le génère.
    db.maj_champs(offre_id, dossier_chemin=str(dossier.CHEMIN_DOSSIERS / ABSENT))
    e = preparation.preparer(offre_id)
    _verifier_generee(e, offre_id)
    assert voisins.ordre == ["evaluer", "generer"]
    assert db.lire_offre(offre_id)["dossier_chemin"] == str(repertoire)
    assert _journal(offre_id)[-1] == ("dossier_genere", GABARIT)


def test_un_dossier_existant_dit_l_alerte_puis_les_doublons(voisins):
    """Sans génération, l'étape `pret` porte l'alerte du texte enregistré par ce passage, puis
    ce que dit `dossier_pret`, les noms d'envoi en double (arbitrage R5)."""
    nom = rendu.nom_pour_envoi("lettre-de-motivation.pdf")
    offre_id, _ = _dossier_sur_disque(
        ["lettre-de-motivation.pdf", "lettre-de-recommandation-inventee.pdf"], paquet=[nom],
        score=reglages.lire_seuil() + 10,
    )
    e = preparation.preparer(offre_id, texte=_texte(400, GRAINE_ASTREINTE))
    pret = preparation.dossier_pret(db.lire_offre(offre_id))
    assert len(pret["avertissements"]) == 1
    _verifier_etape(
        e, etape="pret", url=db.lire_offre(offre_id)["url"], dossier=pret,
        avertissements=[_alerte(voisins), *pret["avertissements"]],
    )
    assert voisins.ordre == []


def test_regenerer_le_meme_jour_historise_la_lettre_remplacee(voisins):
    offre_id, repertoire = _dossier_existant(lettre_courante=LETTRE_AFFINEE)
    voisins.texte_lettre = LETTRE_REGENEREE
    e = preparation.preparer(offre_id, regenerer=True)
    _verifier_generee(e, offre_id)
    versions = lettre.versions(repertoire)
    assert [(v.numero, v.etiquette) for v in versions] == [(1, "avant-regeneration")]
    assert lettre.texte_de_version(repertoire, versions[-1].numero) == LETTRE_AFFINEE
    assert _lire_lettre(repertoire) == LETTRE_REGENEREE
    assert db.lire_offre(offre_id)["dossier_chemin"] == str(repertoire)
    assert _journal(offre_id)[-1] == ("dossier_regenere", GABARIT)
    assert ("dossier_genere", GABARIT) not in _journal(offre_id)


def test_regenerer_un_autre_jour_emporte_l_historique(voisins):
    offre_id, ancien = _dossier_existant(lettre_courante=LETTRE_ASSEMBLEE)
    lettre.historiser(ancien, "assemblee")
    _ecrire_lettre(ancien, LETTRE_AFFINEE)
    voisins.nom_dossier = NOM_AUTRE_JOUR
    voisins.texte_lettre = LETTRE_REGENEREE
    e = preparation.preparer(offre_id, regenerer=True)
    nouveau = dossier.CHEMIN_DOSSIERS / NOM_AUTRE_JOUR
    _verifier_generee(e, offre_id, nom=NOM_AUTRE_JOUR)
    assert e.dossier["nom"] == NOM_AUTRE_JOUR
    assert [(v.numero, v.etiquette) for v in lettre.versions(nouveau)] == [
        (1, "assemblee"), (2, "avant-regeneration"),
    ]
    assert _noms_de_l_historique(nouveau) == _noms_de_l_historique(ancien)
    assert lettre.texte_de_version(nouveau, 1) == LETTRE_ASSEMBLEE
    assert lettre.texte_de_version(nouveau, 2) == LETTRE_AFFINEE
    assert _lire_lettre(nouveau) == LETTRE_REGENEREE
    # L'ancien dossier reste sur le disque, sa lettre avec.
    assert _lire_lettre(ancien) == LETTRE_AFFINEE
    assert db.lire_offre(offre_id)["dossier_chemin"] == str(nouveau)
    assert _journal(offre_id)[-1] == ("dossier_regenere", GABARIT)


def test_regenerer_un_autre_jour_sans_historique_dans_l_ancien(voisins):
    offre_id, ancien = _dossier_existant()
    voisins.nom_dossier = NOM_AUTRE_JOUR
    e = preparation.preparer(offre_id, regenerer=True)
    nouveau = dossier.CHEMIN_DOSSIERS / NOM_AUTRE_JOUR
    _verifier_generee(e, offre_id, nom=NOM_AUTRE_JOUR)
    assert db.lire_offre(offre_id)["dossier_chemin"] == str(nouveau)
    assert not (ancien / lettre.NOM_HISTORIQUE).exists()
    assert not (nouveau / lettre.NOM_HISTORIQUE).exists()
    assert _journal(offre_id)[-1] == ("dossier_regenere", GABARIT)


def test_un_historique_deja_present_n_est_pas_ecrase(voisins):
    offre_id, ancien = _dossier_existant(lettre_courante=LETTRE_AFFINEE)
    nouveau = dossier.CHEMIN_DOSSIERS / NOM_AUTRE_JOUR
    (nouveau / lettre.NOM_HISTORIQUE).mkdir(parents=True)
    (nouveau / lettre.NOM_HISTORIQUE / "001-20261114T0900-assemblee.md").write_text(
        "Lettre inventée d'une autre offre", encoding="utf-8",
    )
    avant = {f.name: f.read_bytes() for f in (nouveau / lettre.NOM_HISTORIQUE).iterdir()}
    voisins.nom_dossier = NOM_AUTRE_JOUR
    e = preparation.preparer(offre_id, regenerer=True)
    _verifier_generee(e, offre_id, nom=NOM_AUTRE_JOUR)
    # Ni écrasé ni fusionné : les numéros des deux historiques se heurteraient.
    assert {f.name: f.read_bytes() for f in (nouveau / lettre.NOM_HISTORIQUE).iterdir()} == avant
    [version] = lettre.versions(ancien)
    assert version.etiquette == "avant-regeneration"
    assert lettre.texte_de_version(ancien, version.numero) == LETTRE_AFFINEE
    assert db.lire_offre(offre_id)["dossier_chemin"] == str(nouveau)


def test_regenerer_sans_dossier_genere_quand_meme(voisins):
    offre_id = _offre("interessante")
    genere = dossier.CHEMIN_DOSSIERS / NOM_DOSSIER
    _verifier_generee(preparation.preparer(offre_id, regenerer=True), offre_id)
    assert db.lire_offre(offre_id)["dossier_chemin"] == str(genere)
    assert lettre.versions(genere) == []
    # Un dossier qui n'est plus sur le disque : rien à historiser, rien à emporter.
    db.maj_champs(offre_id, dossier_chemin=str(dossier.CHEMIN_DOSSIERS / ABSENT))
    _verifier_generee(preparation.preparer(offre_id, regenerer=True), offre_id)
    assert db.lire_offre(offre_id)["dossier_chemin"] == str(genere)
    assert lettre.versions(genere) == []
    assert not (dossier.CHEMIN_DOSSIERS / ABSENT).exists()


def test_regenerer_ne_redemande_ni_texte_ni_completude(voisins):
    """Le dossier a déjà été accepté une fois, peut-être par « Générer quand même » (décision 7)."""
    voisins.bilan = BILAN_30
    offre_id, _ = _dossier_existant(description=EXTRAIT, donnees_partielles=True)
    e = preparation.preparer(offre_id, regenerer=True)
    _verifier_generee(e, offre_id, bilan=BILAN_30)
    assert voisins.ordre == ["evaluer", "generer"]
    assert db.lire_offre(offre_id)["description"] == EXTRAIT


def test_une_regeneration_en_echec_peut_laisser_le_dossier_a_moitie_refait(voisins):
    """Le même jour, `generer` réécrit la lettre, puis casse (T2-M2 de la revue finale). Rien
    ne remet l'ancienne : la lettre est la neuve, le paquet d'envoi l'ancien, et la note du
    destinataire est partie. La lettre d'avant est dans l'historique (invariant 4), et l'offre
    garde son dossier, sans rien au journal."""
    offre_id, repertoire = _dossier_existant(lettre_courante=LETTRE_AFFINEE)
    dossier.ecrire_note_destinataire(repertoire, db.lire_offre(offre_id))
    paquet_avant = _paquet(repertoire).read_bytes()
    voisins.panne = RuntimeError("panne inventée")
    voisins.lettre_avant_la_panne = True
    voisins.texte_lettre = LETTRE_REGENEREE
    e = preparation.preparer(offre_id, regenerer=True)
    _verifier_etape(e, etape="echec", message="panne inventée", url=db.lire_offre(offre_id)["url"])
    assert voisins.ordre == ["evaluer", "generer"]
    assert db.lire_offre(offre_id)["dossier_chemin"] == str(repertoire)
    # Ce qui reste sur le disque.
    assert _lire_lettre(repertoire) == LETTRE_REGENEREE
    assert _paquet(repertoire).read_bytes() == paquet_avant
    assert dossier.lire_note_destinataire(repertoire) is None
    [version] = lettre.versions(repertoire)
    assert version.etiquette == "avant-regeneration"
    assert lettre.texte_de_version(repertoire, version.numero) == LETTRE_AFFINEE
    assert [t for t, _ in _journal(offre_id) if t.startswith("dossier_")] == []
    # Revenu sur « Dossier prêt », l'écran n'affirme aucun destinataire.
    assert preparation.dossier_pret(db.lire_offre(offre_id))["destinataire_lettre"] is None

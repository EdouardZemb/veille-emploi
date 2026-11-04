"""Le classement proposé des offres sans famille.

Les cas de ce fichier sont de VRAIS intitulés, relevés le 02/10/2026 dans sa
base parmi les offres sans famille. Les trois premiers sont son métier et
étaient tombés dans le trou entre deux libellés de motif ; les suivants n'ont
rien à y faire et ne doivent recevoir aucune proposition. Les familles
attendues sont celles de l'exemple.
"""

from __future__ import annotations

import pytest

from veille import classement, db, scoring
from veille.config import charger_criteres
from veille.models import Offre


def _offre(titre, id_=1, score=25.0, employeur="X"):
    return {"id": id_, "titre": titre, "employeur": employeur, "score": score}


# --------------------------------------------------------------------------
# Les offres réellement ratées — le gisement
# --------------------------------------------------------------------------


@pytest.mark.parametrize("titre,famille", [
    ("Automation Tester with Level 2 clearance", "automatisation_tests"),
    ("Sr. Automation Tester with on-site badge required", "automatisation_tests"),
    ("Spécialiste de l'automatisation de tests", "automatisation_tests"),
    ("Test Practitioner/Automation", "automatisation_tests"),
])
def test_les_offres_de_son_metier_recoivent_une_proposition(titre, famille):
    p = classement.proposer(_offre(titre))
    assert p is not None, f"aucune proposition pour « {titre} »"
    assert p.famille == famille, f"{titre} -> {p.famille} ({p.preuves})"


def test_la_proposition_montre_les_mots_qui_la_justifient():
    p = classement.proposer(_offre("Automation Tester with Level 2 clearance"))
    assert p.preuves, "une proposition sans preuve ne se valide pas"
    assert any("automation" in x for x in p.preuves)
    assert all("motif" in x for x in p.preuves), (
        "chaque preuve doit nommer le motif de criteres.yaml d'ou elle vient")


def test_le_pluriel_ne_fait_pas_rater_la_famille():
    """« automatisation de tests » contre le motif « automatisation des tests ».

    C'est exactement l'écart qui avait laissé une offre de sa base sans famille.
    """
    assert classement.proposer(_offre("Spécialiste de l'automatisation de tests"))


# --------------------------------------------------------------------------
# Ce qui ne doit RIEN recevoir
# --------------------------------------------------------------------------


@pytest.mark.parametrize("titre", [
    "Sozialpädagog*in FH/HF 70-80% Wohnheim Am Exempelweg",
    "Hauswart / Fachmann Betriebsunterhalt m/w",
    "Senior School Librarian",
    "Senior School Mathematics Teacher",
    "Exempla Bau. Aussendienstmitarbeiter. Baumaschinen.",
])
def test_les_offres_hors_sujet_ne_recoivent_aucune_proposition(titre):
    p = classement.proposer(_offre(titre))
    assert p is None, f"« {titre} » ne devrait pas etre classee : {p and p.famille}"


def test_un_intitule_vide_ne_propose_rien():
    assert classement.proposer(_offre("")) is None


def test_un_mot_present_partout_ne_suffit_pas():
    """« Senior Engineer » n'est pas une famille. Sans ce garde-fou, le module
    proposerait la famille du developpement logiciel pour la moitie de la base."""
    assert classement.proposer(_offre("Senior Engineer (100%)")) is None


# --------------------------------------------------------------------------
# Le tri, et le vocabulaire
# --------------------------------------------------------------------------


def test_les_propositions_les_plus_sures_dabord():
    offres = [_offre("Senior School Librarian", 1),
              _offre("Automation Tester", 2),
              _offre("Data Steward", 3)]
    props = classement.proposer_pour(offres)
    assert props
    confiances = [p.confiance for p in props]
    assert confiances == sorted(confiances, reverse=True)


def test_un_mot_present_dans_une_seule_famille_pese_plus_que_partage():
    _, etendue = classement.vocabulaire()
    assert etendue["automation"] < etendue["test"], (
        "« test » est dans beaucoup plus de motifs que « automation »")


def test_verification_engineering_va_en_ivvq_sans_que_engineering_compte():
    """Cas reel, transpose a l'exemple. « QA Engineering » partait dans une
    autre famille : « engineering » venait d'un de ses motifs et emportait la
    decision. C'est un mot vide : le mot du metier decide seul, ici
    « verification », cinq fois dans les motifs de l'IVVQ."""
    p = classement.proposer(_offre("Verification Engineering"))
    assert p is not None
    assert p.famille == "qualification_logicielle", p.preuves
    assert not any(x.startswith("« engineering »") for x in p.preuves), p.preuves


def test_un_poste_danalyse_chimique_nest_pas_de_lautomatisation_de_test():
    """Cas reel : « Analytical Development » tombait en automatisation de test a
    cause du mot « development », pris dans « software development engineer
    in test »."""
    p = classement.proposer(
        _offre("Analytical Associate in Analytical Development for Paint Coatings"))
    assert p is None or p.famille != "automatisation_tests", p and p.preuves


def test_les_mots_vides_ne_sont_jamais_des_preuves():
    p = classement.proposer(_offre("Consultant Qualité Produit ERP (H/F)"))
    if p:
        for preuve in p.preuves:
            mot = preuve.split("«")[1].split("»")[0].strip()
            assert mot not in classement.VIDES


# --------------------------------------------------------------------------
# La validation — SA décision, et elle tient
# --------------------------------------------------------------------------


@pytest.fixture
def offre_sans_famille():
    import uuid

    db.initialiser()
    marque = uuid.uuid4().hex[:8]
    # Un intitule qu'aucun motif de l'exemple ne reconnait.
    o = Offre(titre=f"Test Practitioner/Automation {marque}", employeur="X",
              lieu="Mulhouse", description="Un poste de test.",
              url=f"https://exemple.test/{marque}")
    scoring.scorer(o)
    offre_id, nouvelle = db.enregistrer_offre(o)
    assert nouvelle
    return offre_id


def test_une_famille_validee_survit_au_rescorage(offre_sans_famille):
    """Le défaut qu'il faut éviter : rescorer efface ce qu'il a décidé."""
    assert not db.lire_offre(offre_sans_famille)["famille"]
    db.valider_famille(offre_sans_famille, "automatisation_tests")
    db.rescorer_offre(offre_sans_famille)
    assert db.lire_offre(offre_sans_famille)["famille"] == "automatisation_tests"


def test_une_famille_validee_rapporte_exactement_le_bareme_du_fichier(offre_sans_famille):
    poids = float(charger_criteres().familles["automatisation_tests"]["poids"])
    db.valider_famille(offre_sans_famille, "automatisation_tests")
    expl = db.lire_offre(offre_sans_famille)["explication"]
    ligne = [c for c in expl if c["libelle"].startswith("Famille")]
    assert len(ligne) == 1
    assert ligne[0]["points"] == poids, "aucun bareme parallele"
    assert "validée" in ligne[0]["detail"]


def test_le_score_reste_la_somme_exacte_des_contributions(offre_sans_famille):
    db.valider_famille(offre_sans_famille, "automatisation_tests")
    o = db.lire_offre(offre_sans_famille)
    assert o["score"] == round(sum(c["points"] for c in o["explication"]), 1)


def test_sans_famille_validee_rien_ne_change(offre_sans_famille):
    avant = db.lire_offre(offre_sans_famille)
    db.rescorer_offre(offre_sans_famille)
    apres = db.lire_offre(offre_sans_famille)
    assert avant["score"] == apres["score"]
    assert apres["famille"] == avant["famille"]

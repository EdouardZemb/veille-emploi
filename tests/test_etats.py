from datetime import date

import pytest

from veille import etats
from veille.models import STATUTS

AUJ = date(2026, 11, 20)


def _o(id, statut, score=50, **champs):
    return {"id": id, "statut": statut, "score": score,
            "date_collecte": "2026-11-01T08:00:00", **champs}


@pytest.mark.parametrize("statut, etat", [
    ("nouveau", "a_voir"), ("a_traiter", "a_voir"), ("interessante", "je_postule"),
    ("candidature_envoyee", "envoyee"), ("relance_envoyee", "envoyee"),
    ("reponse_recue", "envoyee"), ("entretien", "entretien"),
    ("ecartee", "close"), ("refus", "close"), ("accepte", "close"),
    ("differee", "mise_de_cote"),
])
def test_chaque_statut_a_son_etat(statut, etat):
    assert etats.etat_de({"statut": statut}) == etat


def test_aucun_statut_connu_n_est_sans_etat():
    for s in STATUTS:
        assert etats.etat_de({"statut": s}) in (*etats.ETATS, etats.MISE_DE_COTE)


@pytest.mark.parametrize("offre", [{}, {"statut": None}, {"statut": "inconnu"}])
def test_un_statut_inconnu_leve(offre):
    with pytest.raises(ValueError):
        etats.etat_de(offre)


@pytest.mark.parametrize("offre, raison", [
    ({"statut": "candidature_envoyee", "date_relance_due": "2026-11-20"}, "relance_due"),
    ({"statut": "candidature_envoyee", "date_relance_due": "2026-11-19"}, "relance_due"),
    ({"statut": "relance_envoyee", "date_relance_due": "2026-11-01"}, "relance_due"),
    ({"statut": "candidature_envoyee", "date_relance_due": "2026-11-21"}, None),
    ({"statut": "candidature_envoyee", "date_relance_due": None}, None),
    ({"statut": "reponse_recue", "date_relance_due": "2026-11-01"}, None),
    ({"statut": "interessante", "dossier_chemin": "2026-11-20_x_y"}, "a_envoyer"),
    ({"statut": "interessante", "dossier_chemin": ""}, "a_preparer"),
    ({"statut": "interessante", "dossier_chemin": None}, "a_preparer"),
    ({"statut": "nouveau"}, None),
    ({"statut": "entretien"}, None),
])
def test_la_raison_d_a_finir(offre, raison):
    assert etats.raison_a_finir(offre, AUJ) == raison


def _ids(offres):
    return [o["id"] for o in offres]


def test_la_file_compose_ses_trois_groupes():
    offres = [
        _o(1, "nouveau", 80), _o(2, "nouveau", 60), _o(3, "nouveau", 30),
        _o(4, "a_traiter", 70), _o(5, "interessante", 50),
        _o(6, "interessante", 40, dossier_chemin="d"),
        _o(7, "candidature_envoyee", date_relance_due="2026-11-19"),
        _o(8, "candidature_envoyee", date_relance_due="2026-11-30"),
        _o(9, "relance_envoyee", date_relance_due="2026-11-20"),
    ]
    file = etats.composer_a_faire(offres, 45, AUJ)
    assert _ids(file["a_finir"]) == [7, 9, 6, 5]
    assert _ids(file["a_voir"]) == [1, 2]
    assert _ids(file["plus_tard"]) == [4]
    assert file["a_voir_restantes"] == 0
    assert all("etat" in o for g in ("a_finir", "a_voir", "plus_tard") for o in file[g])
    assert [o["raison"] for o in file["a_finir"]] == [
        "relance_due", "relance_due", "a_envoyer", "a_preparer"]


def test_le_seuil_est_inclus():
    file = etats.composer_a_faire([_o(1, "nouveau", 45)], 45, AUJ)
    assert _ids(file["a_voir"]) == [1]


def test_a_voir_s_arrete_a_la_limite():
    offres = [_o(i, "nouveau", 50 + i) for i in range(55)]
    file = etats.composer_a_faire(offres, 45, AUJ, limite_a_voir=50)
    assert len(file["a_voir"]) == 50
    assert _ids(file["a_voir"]) == list(range(54, 4, -1))
    assert file["a_voir_restantes"] == 5


def test_a_score_egal_la_plus_recente_d_abord():
    offres = [
        _o(1, "nouveau", 60, date_collecte="2026-11-01T09:00:00"),
        _o(2, "nouveau", 60, date_collecte="2026-11-02T09:00:00"),
    ]
    file = etats.composer_a_faire(offres, 45, AUJ)
    assert _ids(file["a_voir"]) == [2, 1]


def test_a_date_de_relance_egale_le_meilleur_score_d_abord():
    offres = [
        _o(1, "candidature_envoyee", 40, date_relance_due="2026-11-10"),
        _o(2, "candidature_envoyee", 70, date_relance_due="2026-11-10"),
    ]
    file = etats.composer_a_faire(offres, 45, AUJ)
    assert _ids(file["a_finir"]) == [2, 1]


def test_un_score_absent_compte_pour_zero():
    offres = [_o(1, "a_traiter", None), _o(2, "a_traiter", 10)]
    file = etats.composer_a_faire(offres, 0, AUJ)
    assert _ids(file["plus_tard"]) == [2, 1]


def test_une_offre_nouvelle_archivee_n_est_pas_a_voir():
    offres = [_o(1, "nouveau", 80, archivee_le="2026-11-10"),
              _o(2, "a_traiter", 80, archivee_le="2026-11-10")]
    file = etats.composer_a_faire(offres, 45, AUJ)
    assert file["a_voir"] == [] and file["plus_tard"] == []


def test_une_candidature_archivee_reste_suivie():
    offres = [_o(1, "candidature_envoyee", date_relance_due="2026-11-10",
                 archivee_le="2026-11-12"),
              _o(2, "interessante", archivee_le="2026-11-12")]
    file = etats.composer_a_faire(offres, 45, AUJ)
    assert _ids(file["a_finir"]) == [1, 2]
    groupes = etats.grouper_candidatures(offres)
    assert _ids(groupes["envoyee"]) == [1]
    assert _ids(groupes["je_postule"]) == [2]


def test_la_composition_ne_touche_pas_les_offres_recues():
    offres = [_o(1, "nouveau", 80), _o(2, "interessante"), _o(3, "a_traiter")]
    etats.composer_a_faire(offres, 45, AUJ)
    etats.grouper_candidatures(offres)
    assert all("etat" not in o and "raison" not in o and "dossier" not in o
               for o in offres)


def test_les_candidatures_se_groupent():
    offres = [
        _o(1, "interessante", 50, dossier_chemin="d"),
        _o(2, "interessante", 60, dossier_chemin=""),
        _o(3, "candidature_envoyee", date_relance_due="2026-11-25"),
        _o(4, "relance_envoyee", date_relance_due="2026-11-22"),
        _o(5, "reponse_recue"),
        _o(6, "entretien"),
        _o(7, "nouveau"), _o(8, "ecartee"), _o(9, "differee"),
    ]
    g = etats.grouper_candidatures(offres)
    assert list(g) == ["je_postule", "envoyee", "entretien"]
    assert _ids(g["je_postule"]) == [2, 1]
    assert [o["dossier"] for o in g["je_postule"]] == [False, True]
    assert _ids(g["envoyee"]) == [4, 3, 5]
    assert _ids(g["entretien"]) == [6]
    assert all(o["etat"] for liste in g.values() for o in liste)


def test_les_entretiens_se_trient_par_score_puis_par_collecte():
    offres = [
        _o(1, "entretien", 40),
        _o(2, "entretien", 80),
        _o(3, "entretien", 40, date_collecte="2026-11-05T08:00:00"),
    ]
    assert _ids(etats.grouper_candidatures(offres)["entretien"]) == [2, 3, 1]


def test_les_je_postule_se_trient_par_score_puis_par_collecte():
    offres = [
        _o(1, "interessante", 40),
        _o(2, "interessante", 80),
        _o(3, "interessante", 40, date_collecte="2026-11-05T08:00:00"),
    ]
    assert _ids(etats.grouper_candidatures(offres)["je_postule"]) == [2, 3, 1]


def test_les_envoyees_a_echeance_egale_le_meilleur_score_d_abord():
    offres = [
        _o(1, "candidature_envoyee", 30, date_relance_due="2026-11-25"),
        _o(2, "relance_envoyee", 70, date_relance_due="2026-11-25"),
        _o(3, "reponse_recue", 20),
        _o(4, "reponse_recue", 90),
    ]
    assert _ids(etats.grouper_candidatures(offres)["envoyee"]) == [2, 1, 4, 3]


def test_une_a_traiter_sous_le_seuil_reste_dans_plus_tard():
    file = etats.composer_a_faire([_o(1, "a_traiter", 10)], 45, AUJ)
    assert _ids(file["plus_tard"]) == [1]
    assert file["a_voir"] == []


def test_une_offre_sans_date_de_collecte_se_trie_apres_celle_qui_en_a_une():
    sans = {"id": 1, "statut": "nouveau", "score": 60}
    avec = _o(2, "nouveau", 60)
    file = etats.composer_a_faire([sans, avec], 45, AUJ)
    assert _ids(file["a_voir"]) == [2, 1]
    sans_none = {**sans, "date_collecte": None}
    file = etats.composer_a_faire([sans_none, avec], 45, AUJ)
    assert _ids(file["a_voir"]) == [2, 1]

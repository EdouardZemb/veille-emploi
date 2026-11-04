"""Le mot de relance — petit, et c'est le geste qu'on ne fait jamais."""

from __future__ import annotations

from datetime import date, timedelta

from veille import relance


def _offre(**kw):
    base = {
        "id": 1, "titre": "Testeur logiciel", "employeur": "Exemple Logistik AG",
        "lieu": "Mulhouse", "statut": "candidature_envoyee",
        "canal_candidature": "courriel",
        "date_candidature": (date.today() - timedelta(days=15)).isoformat(),
        # Assez de texte pour que la langue soit tranchee : depuis le
        # 02/10, une langue indeterminee ne produit plus de relance.
        "description": ("Nous recherchons un ingenieur pour la validation "
                        "des systemes, dans une equipe et avec les metiers."),
    }
    base.update(kw)
    return base


def test_le_texte_porte_les_faits_enregistres():
    r = relance.preparer(_offre())
    assert "Exemple Logistik AG" in r.texte or "Testeur logiciel" in r.texte
    assert "15" in r.texte, "le nombre de jours doit figurer"
    assert r.jours == 15


def test_aucune_phrase_nest_ecrite_par_le_programme():
    """Le texte rendu est le gabarit, marqueurs remplaces — rien d'autre.

    Mesure exacte plutot qu'heuristique : on transforme le gabarit en motif
    en remplacant chaque {{marqueur}} par un joker, et le resultat doit
    correspondre d'un bout a l'autre. Si le module ajoutait une phrase, la
    correspondance echouerait.
    """
    import re

    o = _offre()
    r = relance.preparer(o)
    gabarit = relance._corps_du_gabarit(
        relance.gabarit_pour(o).read_text(encoding="utf-8"))
    # L'objet est retire du texte rendu : on le retire aussi du gabarit.
    gabarit = chr(10).join(l for l in gabarit.splitlines()
                           if not l.strip().lower().startswith("objet"))
    motif = "".join(
        ".*?" if morceau.startswith("{{") else re.escape(morceau)
        for morceau in re.split(r"(\{\{[a-z_]+\}\})", gabarit))
    assert re.fullmatch(motif, r.texte, re.DOTALL), (
        "le texte rendu n'est pas le gabarit : une phrase a ete ajoutee")


def test_une_relance_trop_tot_est_signalee_sans_etre_bloquee():
    r = relance.preparer(_offre(
        date_candidature=(date.today() - timedelta(days=3)).isoformat()))
    assert r.texte, "signaler n'est pas bloquer"
    assert any("impatience" in a for a in r.avertissements)


def test_une_relance_tres_tardive_est_signalee():
    r = relance.preparer(_offre(
        date_candidature=(date.today() - timedelta(days=90)).isoformat()))
    assert any("pourvu" in a for a in r.avertissements)


def test_une_seconde_relance_est_signalee():
    r = relance.preparer(_offre(statut="relance_envoyee"))
    assert any("deja relance" in a for a in r.avertissements)


def test_sans_date_denvoi_la_relance_le_dit():
    r = relance.preparer(_offre(date_candidature=None))
    assert any("Aucune date d'envoi" in a for a in r.avertissements)
    assert r.jours == 0


def test_une_annonce_archivee_est_signalee_sans_blocage():
    r = relance.preparer(_offre(archivee_le="2026-09-30"))
    assert r.texte
    assert any("archivee" in a for a in r.avertissements)


def test_la_notice_du_gabarit_ne_part_pas_au_recruteur():
    """Elle partait : « Marqueurs : `Exemple Logistik AG` `Testeur logiciel` `Mulhouse` »."""
    r = relance.preparer(_offre())
    assert "Marqueurs" not in r.texte
    assert "GABARIT" not in r.texte.upper()


def test_un_gabarit_sans_separateur_est_pris_en_entier():
    assert relance._corps_du_gabarit("Bonjour,\n\nUn mot.") == "Bonjour,\n\nUn mot."


def test_un_marqueur_sans_valeur_reste_visible():
    r = relance.preparer(_offre(contact_nom="", contact_civilite=""))
    assert r.marqueurs_restants, "un trou doit se voir, pas disparaitre"


def test_le_contact_connu_remplace_le_marqueur():
    r = relance.preparer(_offre(contact_nom="Dupont", contact_civilite="Madame"))
    assert "Dupont" in r.texte
    assert "[[contact -" not in r.texte


def test_lobjet_est_extrait_du_gabarit():
    r = relance.preparer(_offre())
    assert r.objet
    assert "Testeur logiciel" in r.objet
    assert not any(l.lower().startswith("objet") for l in r.texte.splitlines())


def test_une_offre_en_anglais_prend_le_gabarit_anglais():
    r = relance.preparer(_offre(
        titre="Test Automation Engineer",
        description=("We are looking for a test automation engineer to join "
                     "our quality team in Basel and build the test suite.")))
    assert r.gabarit.endswith("_en.md"), r.gabarit
    assert "follow up" in r.texte.lower()


def test_le_resultat_est_deterministe():
    o = _offre()
    a = relance.preparer(o, aujourdhui=date(2026, 10, 2))
    b = relance.preparer(o, aujourdhui=date(2026, 10, 2))
    assert a.texte == b.texte

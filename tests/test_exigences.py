"""Le relevé d'exigences — et la propriété qu'il ne doit PAS casser.

Le modèle lit « zwei Tage pro Woche vor Ort » mieux qu'une expression
régulière. Soit. Mais la valeur de cet outil tient à une chose : même offre,
même score, chaque point explicable par une ligne. Ces tests existent pour
qu'on ne puisse pas échanger cette propriété contre du confort — y compris
par inadvertance, dans six mois, en « simplifiant ».

Les trois maillons, un par section :
  1. le modèle ne rend qu'un triplet contraint ;
  2. la citation doit être littérale ;
  3. rien n'agit avant validation.
"""

from __future__ import annotations

import pytest

from veille import db, exigences, scoring
from veille.models import Offre

TEXTE = (
    "Wir suchen einen Testingenieur für unseren Standort in Basel.\n"
    "Sie arbeiten zwei Tage pro Woche vor Ort, der Rest ist remote möglich.\n"
    "Verhandlungssicheres Deutsch wird vorausgesetzt, Englisch von Vorteil.\n"
    "Mindestens drei Jahre Berufserfahrung in der Logistikbranche.\n"
    "Reisetätigkeit gelegentlich. Keine Rufbereitschaft."
)


# ==========================================================================
# 1. LE MODELE NE REND QU'UN TRIPLET CONTRAINT
# ==========================================================================


def test_aucun_attribut_ne_porte_de_points():
    """Si un attribut pouvait porter des points, le modèle noterait."""
    for cle, d in exigences.ATTRIBUTS.items():
        assert "points" not in d, cle
        assert "poids" not in d, cle
        assert "malus" not in d, cle


def test_lexigence_rendue_na_que_trois_champs():
    e = exigences.Exigence("allemand", "courant", "Deutsch")
    assert set(e.as_dict()) == {"attribut", "valeur", "citation", "libelle",
                                "agit_sur_le_score"}
    assert "points" not in e.as_dict()


def test_un_attribut_hors_liste_est_jete():
    brut = [{"attribut": "salaire_juste", "valeur": "oui",
             "citation": "zwei Tage pro Woche vor Ort"}]
    gardees, rejetees = exigences.filtrer(brut, TEXTE)
    assert gardees == []
    assert "hors liste" in rejetees[0]


def test_une_valeur_hors_domaine_est_jetee():
    brut = [{"attribut": "allemand", "valeur": "excellent",
             "citation": "Verhandlungssicheres Deutsch wird vorausgesetzt"}]
    gardees, rejetees = exigences.filtrer(brut, TEXTE)
    assert gardees == []
    assert "hors domaine" in rejetees[0]


def test_seuls_trois_attributs_touchent_au_score():
    """Elargir cette liste est une décision, pas un détail d'implémentation."""
    assert set(exigences.ATTRIBUTS_QUI_AGISSENT) == {
        "teletravail", "jours_sur_site", "allemand"}


def test_la_consigne_interdit_la_traduction_et_le_resume():
    c = exigences._consigne().lower()
    assert "mot pour mot" in c
    assert "traduction" in c and "resume" in c
    assert "aucune note, aucun score" in c


# ==========================================================================
# 2. LA CITATION DOIT ETRE LITTERALE
# ==========================================================================


def test_une_citation_litterale_passe():
    brut = [{"attribut": "jours_sur_site", "valeur": "2",
             "citation": "zwei Tage pro Woche vor Ort"}]
    gardees, rejetees = exigences.filtrer(brut, TEXTE)
    assert rejetees == []
    assert gardees[0].valeur == "2"
    assert gardees[0].citation in TEXTE


def test_une_citation_traduite_est_jetee():
    """Le cas qui coûterait cher : une traduction est plausible et fausse."""
    brut = [{"attribut": "jours_sur_site", "valeur": "2",
             "citation": "deux jours par semaine sur site"}]
    gardees, rejetees = exigences.filtrer(brut, TEXTE)
    assert gardees == []
    assert "n'est pas dans le texte" in rejetees[0]


def test_une_citation_reformulee_meme_de_peu_est_jetee():
    brut = [{"attribut": "allemand", "valeur": "courant",
             "citation": "Verhandlungssicheres Deutsch ist erforderlich"}]
    gardees, _ = exigences.filtrer(brut, TEXTE)
    assert gardees == []


def test_les_espaces_et_retours_a_la_ligne_sont_tolerés():
    """Un modèle recolle les lignes. Les MOTS doivent être les siens, pas la
    mise en page — et c'est l'extrait du TEXTE qui est conservé."""
    brut = [{"attribut": "jours_sur_site", "valeur": "2",
             "citation": "Basel.  Sie arbeiten zwei Tage"}]
    gardees, rejetees = exigences.filtrer(brut, TEXTE)
    assert rejetees == [], rejetees
    assert gardees[0].citation in TEXTE, "c'est la tranche du texte qui est gardée"


def test_une_citation_trop_courte_est_jetee():
    brut = [{"attribut": "allemand", "valeur": "courant", "citation": "Deutsch"}]
    gardees, rejetees = exigences.filtrer(brut, TEXTE)
    assert gardees == []
    assert "longueur" in rejetees[0]


def test_un_meme_attribut_propose_deux_fois_ne_compte_quune_fois():
    brut = [
        {"attribut": "jours_sur_site", "valeur": "2",
         "citation": "zwei Tage pro Woche vor Ort"},
        {"attribut": "jours_sur_site", "valeur": "4",
         "citation": "zwei Tage pro Woche vor Ort"},
    ]
    gardees, rejetees = exigences.filtrer(brut, TEXTE)
    assert len(gardees) == 1 and gardees[0].valeur == "2"
    assert "deux fois" in rejetees[0]


def test_une_sortie_illisible_ne_produit_rien():
    for cochonnerie in ("", "je ne sais pas", "null", "{}", "<html>"):
        assert exigences._extraire_json(cochonnerie) == []


def test_un_tableau_dans_un_bloc_markdown_est_lu():
    brut = exigences._extraire_json(
        '```json\n[{"attribut":"anglais","valeur":"courant","citation":"x"}]\n```')
    assert brut and brut[0]["attribut"] == "anglais"


# ==========================================================================
# 3. RIEN N'AGIT AVANT VALIDATION
# ==========================================================================


@pytest.fixture
def offre_en_base():
    """Une offre neuve par test.

    L'URL doit etre REELLEMENT unique : avec `id(object())`, Python reutilise
    l'adresse liberee et deux tests retombaient sur la meme empreinte, donc
    sur la meme offre — l'un heritant des exigences validees par l'autre.
    """
    import uuid

    db.initialiser()
    marque = uuid.uuid4().hex[:8]
    # Titre ET url uniques : la deduplication porte aussi sur
    # `empreinte_titre` (titre + employeur), et deux offres de meme intitule
    # etaient fusionnees — le second test heritait des exigences du premier.
    o = Offre(titre=f"Testingenieur {marque}", employeur="X",
              lieu="Basel", description=TEXTE,
              url=f"https://exemple.test/{marque}")
    scoring.scorer(o)
    offre_id, nouvelle = db.enregistrer_offre(o)
    assert nouvelle, "le test a besoin d'une offre neuve"
    return offre_id


def test_une_proposition_non_validee_ne_change_pas_le_score(offre_en_base):
    avant = db.lire_offre(offre_en_base)["score"]
    db.enregistrer_propositions(offre_en_base, [
        {"attribut": "allemand", "valeur": "courant", "citation": "Deutsch wird"},
    ], par="modele")
    db.rescorer_offre(offre_en_base)
    assert db.lire_offre(offre_en_base)["score"] == avant
    assert db.exigences_validees(offre_en_base) == {}


def test_la_validation_est_ce_qui_agit(offre_en_base):
    avant = db.lire_offre(offre_en_base)["score"]
    db.enregistrer_propositions(offre_en_base, [
        {"attribut": "jours_sur_site", "valeur": "2",
         "citation": "zwei Tage pro Woche vor Ort"},
    ], par="modele")
    db.valider_exigences(offre_en_base, ["jours_sur_site"])
    apres = db.lire_offre(offre_en_base)
    assert db.exigences_validees(offre_en_base)["jours_sur_site"]["valeur"] == "2"
    assert apres["score"] != avant or apres["zone"]


def test_ce_quil_ne_coche_pas_est_supprime(offre_en_base):
    db.enregistrer_propositions(offre_en_base, [
        {"attribut": "allemand", "valeur": "courant", "citation": "a"},
        {"attribut": "anglais", "valeur": "souhaite", "citation": "b"},
    ], par="modele")
    db.valider_exigences(offre_en_base, ["allemand"])
    restantes = {e["attribut"] for e in db.exigences_de(offre_en_base, False)}
    assert restantes == {"allemand"}


def test_une_exigence_validee_nest_pas_ecrasee_par_une_nouvelle_proposition(offre_en_base):
    """Sa décision tient, même si le modèle est relancé et dit autre chose."""
    db.enregistrer_propositions(offre_en_base, [
        {"attribut": "allemand", "valeur": "courant", "citation": "a"}], par="m")
    db.valider_exigences(offre_en_base, ["allemand"])
    db.enregistrer_propositions(offre_en_base, [
        {"attribut": "allemand", "valeur": "aucun", "citation": "b"}], par="m")
    assert db.exigences_validees(offre_en_base)["allemand"]["valeur"] == "courant"


def test_oublier_une_exigence_rend_le_score_dorigine(offre_en_base):
    avant = db.lire_offre(offre_en_base)["score"]
    db.enregistrer_propositions(offre_en_base, [
        {"attribut": "jours_sur_site", "valeur": "2",
         "citation": "zwei Tage pro Woche vor Ort"}], par="m")
    db.valider_exigences(offre_en_base, ["jours_sur_site"])
    db.oublier_exigences(offre_en_base)
    assert db.lire_offre(offre_en_base)["score"] == avant


# ==========================================================================
# LE DETERMINISME, mesuré
# ==========================================================================


def _offre(**kw):
    base = {"titre": "Test Engineer", "employeur": "X", "lieu": "Basel",
            "description": TEXTE}
    base.update(kw)
    return Offre(**base)


def test_meme_offre_memes_exigences_meme_score():
    exig = {"jours_sur_site": {"valeur": "2", "citation": "zwei Tage"}}
    a, b = _offre(exigences=dict(exig)), _offre(exigences=dict(exig))
    scoring.scorer(a)
    scoring.scorer(b)
    assert a.score == b.score
    assert [c.as_dict() for c in a.explication] == [c.as_dict() for c in b.explication]


def test_chaque_point_reste_explique_par_une_ligne():
    o = _offre(exigences={"allemand": {"valeur": "courant",
                                       "citation": "Verhandlungssicheres Deutsch"}})
    scoring.scorer(o)
    assert o.score == round(sum(c.points for c in o.explication), 1)
    allemand = [c for c in o.explication if "Allemand" in c.libelle]
    assert allemand, [c.libelle for c in o.explication]
    assert "Verhandlungssicheres Deutsch" in allemand[0].detail
    assert "validée" in allemand[0].detail, "il doit voir que ça vient de LUI"


def test_une_exigence_validee_neutralise_une_detection_fausse():
    """Le vrai gain : « Deutschkenntnisse von Vorteil » n'est pas une exigence.

    Les motifs la comptaient comme telle et l'offre partait en malus.
    """
    texte = ("Gute Deutschkenntnisse von Vorteil, die Arbeitssprache ist Englisch.")
    sans = _offre(description=texte)
    scoring.scorer(sans)
    avec = _offre(description=texte,
                  exigences={"allemand": {"valeur": "souhaite",
                                          "citation": "von Vorteil"}})
    scoring.scorer(avec)
    assert avec.score > sans.score, (
        "l'exigence validée doit lever le malus que les motifs avaient posé")


def test_sans_exigence_le_scoring_est_exactement_celui_davant():
    """Garde-fou : aucun comportement ne change pour les offres existantes."""
    o1 = _offre()
    o2 = _offre(exigences={})
    scoring.scorer(o1)
    scoring.scorer(o2)
    assert o1.score == o2.score
    assert [c.as_dict() for c in o1.explication] == [c.as_dict() for c in o2.explication]


def test_le_nombre_de_jours_prime_sur_le_mode_annonce():
    o = _offre(exigences={
        "teletravail": {"valeur": "complet", "citation": "remote"},
        "jours_sur_site": {"valeur": "3", "citation": "drei Tage"},
    })
    niveau, preuve = scoring.detecter_teletravail(o, scoring.charger_criteres())
    assert niveau == "partiel"
    assert "3 jour" in preuve


def test_zero_jour_sur_site_vaut_teletravail_complet():
    o = _offre(exigences={"jours_sur_site": {"valeur": "0", "citation": "x"}})
    niveau, _ = scoring.detecter_teletravail(o, scoring.charger_criteres())
    assert niveau == "complet"


def test_la_preuve_dit_que_lexigence_vient_de_lui():
    o = _offre(exigences={"teletravail": {"valeur": "aucun",
                                          "citation": "vollständig vor Ort"}})
    niveau, preuve = scoring.detecter_teletravail(o, scoring.charger_criteres())
    assert niveau == "presentiel"
    assert "validée" in preuve and "vollständig vor Ort" in preuve

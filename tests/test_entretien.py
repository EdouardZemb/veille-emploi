"""La preparation d'entretien — ecrite AVANT le module, et elle le tient.

La propriete qui compte : aucune question n'existe sans ancrage, et aucun
ancrage n'est une reformulation. Une question inventee ne le generait pas :
elle lui ferait preparer la mauvaise chose, et il arriverait desarme devant
celle qu'on lui posera vraiment.
"""

from __future__ import annotations

import pytest

from veille import entretien
from veille.config import charger_criteres, normaliser

# --------------------------------------------------------------------------
# Un faux fichier 17, celui de Camille Exemple, de la meme forme que le vrai.
#
# Ses titres sont ceux que cherchent les declencheurs : les generiques du code,
# et ceux de `entretien.declencheurs` dans l'exemple. Un temoin le verifie
# (`test_le_faux_fichier_17_couvre_tous_les_declencheurs_de_l_exemple`).
# --------------------------------------------------------------------------

KIT_17 = """# Préparation d'entretien

**À relire la veille, pas à apprendre par cœur.**

# 1. Tes atouts

| Fait | Pourquoi ça compte |
|---|---|
| **Trois ans d'automatisation** | La preuve par les suites qui tournent |

# 2. Les objections que tu vas recevoir

## « Vous n'avez jamais encadré d'équipe ? »

**C'est vrai. Ne le maquille pas en management.**

> « Non. J'ai coordonné une campagne de recette à trois, sans la diriger. »

## « Vous n'avez jamais testé de logiciel embarqué ? »

> « Non. Je teste des applications mobiles qui pilotent des terminaux d'entrepôt. »

## « Votre allemand suffira-t-il ? »

> « Pas encore pour une réunion : je suis au niveau A2, et je prends des cours. »

## « Pourquoi vous partez ? »

**Ne dis jamais ce que tu fuis. Dis ce que tu cherches.**

## « Vous travaillez en France : pourquoi la Suisse ? »

> « Pour l'équipe et pour le produit. Le trajet, je le fais déjà. »

## « Quel est votre préavis ? »

> « Deux mois. »

## « Avez-vous écrit ce code ? » — la question à ne pas subir

**Ne laisse pas la question arriver par surprise.**

# 3. Ton point fort : l'audit d'accessibilité

Le récit en trente secondes.

# 4. La logistique, ton terrain

Les trois chiffres de l'entrepôt.

# 5. Le salaire — la question qui vaut le plus

Ne donne jamais le premier chiffre.

# 6. Tes questions à eux

Trois questions, pas plus.

# 7. À faire avant chaque entretien

La liste de la veille.
"""


@pytest.fixture
def kit(tmp_path, monkeypatch):
    (tmp_path / "17-Preparation-entretien.md").write_text(KIT_17, encoding="utf-8")
    monkeypatch.setattr(entretien, "CHEMIN_KIT", tmp_path)
    return tmp_path


def offre(**kw):
    base = {
        "titre": "Testeuse automaticienne",
        "employeur": "Exemple Logistique SA",
        "lieu": "Mulhouse",
        "description": "Poste de test d'une application web.",
    }
    base.update(kw)
    return base


def _poser_criteres(monkeypatch, request, tmp_path, modifier):
    """Des criteres derives de l'exemple, dans un sous-dossier : `tmp_path` porte
    deja le faux kit."""
    from tests.aide_criteres import poser_criteres

    dossier = tmp_path / "criteres"
    dossier.mkdir()
    return poser_criteres(monkeypatch, request, dossier, modifier)


# --------------------------------------------------------------------------
# LA REGLE : tout point porte un ancrage LITTERAL
# --------------------------------------------------------------------------


def test_chaque_point_porte_une_citation_litterale(kit):
    o = offre(description=(
        "Nous recherchons une testeuse pour un logiciel embarque. "
        "Une experience en encadrement d equipe est requise. "
        "Deutsch ist erforderlich. "
        "Entree en fonction des que possible."
    ))
    prep = entretien.preparer(o, pieces=["annexe-technique.pdf"])
    assert prep.points, "aucun point produit sur une annonce qui coche tout"
    manques = entretien.verifier_ancrages(prep, o, KIT_17)
    assert manques == [], manques


def test_une_citation_reformulee_est_refusee(kit):
    """Le controle doit mordre. S'il ne mord pas, il ne prouve rien."""
    o = offre()
    prep = entretien.preparer(o)
    assert prep.points
    prep.points[0].citation = "une phrase que personne n'a ecrite"
    prep.points[0].ancrage = "annonce"
    manques = entretien.verifier_ancrages(prep, o, KIT_17)
    assert len(manques) == 1
    assert "absente de l'annonce" in manques[0]


def test_un_ancrage_vide_est_refuse(kit):
    o = offre()
    prep = entretien.preparer(o)
    prep.points[0].citation = "   "
    assert entretien.verifier_ancrages(prep, o, KIT_17)


def test_la_citation_annonce_est_bien_la_phrase_du_motif(kit):
    o = offre(description=(
        "Le poste est base a Bale. "
        "Gute Deutschkenntnisse sind zwingend erforderlich. "
        "Le salaire est negociable."
    ))
    prep = entretien.preparer(o)
    allemand = [p for p in prep.points if "allemand" in p.question.lower()]
    assert allemand, "le declencheur allemand n'a pas pris"
    assert "Deutschkenntnisse" in allemand[0].citation
    assert "salaire est negociable" not in allemand[0].citation, \
        "c'est le bug de la phrase d'a cote, deja corrige une fois"


# --------------------------------------------------------------------------
# Les declencheurs : ce qui sort, et ce qui ne sort PAS
# --------------------------------------------------------------------------


def test_sans_mention_dallemand_la_question_allemande_ne_sort_pas(kit):
    prep = entretien.preparer(offre(description="Poste en francais, equipe francaise."))
    assert not [p for p in prep.points if "allemand" in p.question.lower()]


def test_sans_dossier_technique_joint_la_question_sur_le_code_ne_sort_pas(kit):
    """Elle n'a de sens que s'il envoie reellement le code."""
    prep = entretien.preparer(offre(), pieces=["cv.fr.pdf"])
    assert not [p for p in prep.points if "ce code" in p.question.lower()]


def test_avec_le_dossier_technique_joint_elle_sort_et_nomme_la_piece(kit):
    prep = entretien.preparer(offre(), pieces=["annexe-technique.pdf"])
    code = [p for p in prep.points if "ce code" in p.question.lower()]
    assert code
    assert "annexe-technique.pdf" in code[0].pourquoi


def test_la_question_frontalier_ne_sort_que_pour_la_suisse(kit):
    """Le declencheur restreint a la Suisse est celui de l'exemple (`pays: ch`)."""
    cle = next(d.cle_section for d in entretien.declencheurs() if d.pays == "ch")

    def frontalier(points):
        return [p for p in points if cle in normaliser(p.question)]

    assert not frontalier(entretien.preparer(offre(lieu="Mulhouse")).points)
    assert frontalier(entretien.preparer(offre(lieu="Basel, Suisse")).points)


def test_les_questions_universelles_sortent_toujours_et_sancrent_sur_le_dossier(kit):
    prep = entretien.preparer(offre(description="x"))
    universelles = [p for p in prep.points
                    if "Pourquoi vous partez" in p.question
                    or "salaire" in p.question.lower()]
    assert len(universelles) == 2
    for p in universelles:
        assert p.ancrage == "dossier"
        assert p.citation in KIT_17


def test_les_attaques_passent_devant(kit):
    prep = entretien.preparer(offre())
    categories = [p.categorie for p in prep.points]
    assert categories == sorted(categories,
                                key=lambda c: {"attaque": 0, "appui": 1}.get(c, 2))


# --------------------------------------------------------------------------
# Le module n'ecrit AUCUNE prose
# --------------------------------------------------------------------------


def test_toute_reponse_vient_mot_pour_mot_du_fichier_17(kit):
    prep = entretien.preparer(
        offre(description="logiciel embarque, encadrement d equipe, accessibilite"),
        pieces=["annexe-technique.pdf"])
    for p in prep.points:
        assert p.reponse, f"section vide : {p.question}"
        assert p.reponse in KIT_17, f"prose inventee dans « {p.question} »"


def test_le_rendu_ne_contient_que_du_texte_du_kit_ou_de_loffre(kit):
    o = offre(description="audit RGAA")
    texte = entretien.rendre_markdown(entretien.preparer(o), o)
    assert "Préparation d'entretien" in texte or "Preparation d'entretien" in texte
    for p in entretien.preparer(o).points:
        assert p.reponse in texte


# --------------------------------------------------------------------------
# Ce qui manque est DIT, jamais tu
# --------------------------------------------------------------------------


def test_une_section_renommee_est_signalee(tmp_path, monkeypatch):
    ampute = KIT_17.replace("## « Quel est votre préavis ? »",
                            "## « Dans combien de temps êtes-vous libre ? »")
    (tmp_path / "17-prep.md").write_text(ampute, encoding="utf-8")
    monkeypatch.setattr(entretien, "CHEMIN_KIT", tmp_path)
    prep = entretien.preparer(offre(description="start date asap"))
    assert "quel est votre preavis" in prep.sections_absentes
    assert any("introuvables" in a for a in prep.avertissements)


def test_sans_fichier_17_la_console_le_dit_et_ninvente_rien(tmp_path, monkeypatch):
    monkeypatch.setattr(entretien, "CHEMIN_KIT", tmp_path)
    prep = entretien.preparer(offre())
    assert not prep.kit_disponible
    assert prep.points == []
    assert any("n'en invente pas" in a for a in prep.avertissements)


def test_un_intitule_a_risque_declenche_l_avertissement_du_kit(kit):
    """Les intitules a risque et l'avertissement sont ceux de l'exemple
    (`entretien.intitules_a_risque`)."""
    risque = charger_criteres().brut["entretien"]["intitules_a_risque"]
    motif = risque["motifs"][0]
    prep = entretien.preparer(offre(titre=f"Senior {motif.title()} (H/F)"))
    assert f"Intitule « {motif} » : {risque['avertissement']}" in prep.avertissements


def test_pas_davertissement_sur_un_intitule_ordinaire(kit):
    prep = entretien.preparer(offre(titre="Testeuse automaticienne"))
    assert not any(a.startswith("Intitule «") for a in prep.avertissements)


def test_le_nombre_de_points_est_plafonne(kit):
    o = offre(
        titre="Senior QA Automation Engineer",
        lieu="Basel, Suisse",
        description=("logiciel embarque, encadrement d equipe, Deutschkenntnisse, "
                     "start date asap, audit RGAA, WMS"),
    )
    prep = entretien.preparer(o, pieces=["annexe-technique.pdf"])
    assert len(prep.points) == entretien.MAX_POINTS
    assert any("non repris" in a for a in prep.avertissements)


# --------------------------------------------------------------------------
# Les declencheurs : les generiques dans le code, les autres dans la configuration
# --------------------------------------------------------------------------


def test_le_faux_fichier_17_couvre_tous_les_declencheurs_de_l_exemple(kit):
    """TEMOIN DE FIXTURE. Chaque declencheur, generique ou de l'exemple, trouve sa
    section : un declencheur renomme dans l'exemple ne fait pas taire ses tests en
    silence."""
    prep = entretien.preparer(offre())
    assert prep.sections_absentes == []
    assert len(entretien.declencheurs()) > len(entretien.DECLENCHEURS_GENERIQUES), (
        "l'exemple doit ajouter ses propres declencheurs")


def test_les_declencheurs_propres_viennent_de_la_configuration(kit, monkeypatch, request,
                                                               tmp_path):
    """Un declencheur qui porte un fait du parcours vit dans `entretien.declencheurs`.
    Remplacer cette liste remplace ces declencheurs-la, et eux seuls : les generiques
    du code restent."""
    def modifier(brut):
        brut["entretien"]["declencheurs"] = [{
            "cle_section": "tes atouts", "categorie": "appui",
            "pourquoi": "raison inventée", "motifs": ["zorglub"]}]

    _poser_criteres(monkeypatch, request, tmp_path, modifier)
    o = offre(description="Le poste demande du zorglub. Deutschkenntnisse erforderlich.")
    prep = entretien.preparer(o)

    atouts = [p for p in prep.points if p.section == "1. Tes atouts"]
    assert len(atouts) == 1
    assert atouts[0].categorie == "appui"
    assert atouts[0].pourquoi == "raison inventée — « zorglub »"
    assert atouts[0].citation == "Le poste demande du zorglub."
    # L'allemand de l'exemple n'est plus declare : il ne sort plus.
    assert not [p for p in prep.points if "allemand" in p.question.lower()]
    assert [p for p in prep.points if "Pourquoi vous partez" in p.question]
    assert entretien.verifier_ancrages(prep, o, KIT_17) == []


def test_sans_cle_entretien_seuls_les_generiques_restent(kit, monkeypatch, request, tmp_path):
    _poser_criteres(monkeypatch, request, tmp_path, lambda brut: brut.pop("entretien"))

    assert entretien.declencheurs() == entretien.DECLENCHEURS_GENERIQUES
    prep = entretien.preparer(offre(description="Deutschkenntnisse erforderlich."))
    assert not [p for p in prep.points if "allemand" in p.question.lower()]
    universelles = [p for p in prep.points
                    if "Pourquoi vous partez" in p.question or "salaire" in p.question.lower()]
    assert len(universelles) == 2
    assert prep.sections_absentes == []


def test_la_configuration_passe_devant_et_une_cle_redeclaree_remplace_le_generique(
        monkeypatch, request, tmp_path):
    """La configuration complete les generiques. Une cle qu'elle redeclare prend la
    place du generique, sans doublon : sinon la section manquante serait signalee
    deux fois."""
    generique = next(d for d in entretien.DECLENCHEURS_GENERIQUES if not d.motifs)

    def modifier(brut):
        brut["entretien"]["declencheurs"] = [
            {"cle_section": "zorglub", "categorie": "attaque", "pourquoi": "propre"},
            {"cle_section": generique.cle_section, "categorie": "attaque",
             "pourquoi": "redéclarée"},
        ]

    _poser_criteres(monkeypatch, request, tmp_path, modifier)
    tous = entretien.declencheurs()
    assert [d.cle_section for d in tous[:2]] == ["zorglub", generique.cle_section]
    assert tous[1].pourquoi == "redéclarée"
    assert [d.cle_section for d in tous].count(generique.cle_section) == 1
    assert tous[2:] == tuple(d for d in entretien.DECLENCHEURS_GENERIQUES if d != generique)


def test_un_declencheur_mal_forme_est_signale_pas_tu(kit, monkeypatch, request, tmp_path):
    """Sans cle de section, il trouverait la premiere section venue. Il est ecarte,
    et l'ecran le dit."""
    _poser_criteres(monkeypatch, request, tmp_path,
                    lambda brut: brut["entretien"]["declencheurs"].insert(
                        0, {"categorie": "attaque", "pourquoi": "sans cle"}))
    prep = entretien.preparer(offre())
    assert any("mal formé" in a and "veille config verifier" in a
               for a in prep.avertissements), prep.avertissements
    assert prep.points
    assert prep.sections_absentes == []
    assert not [p for p in prep.points if p.pourquoi == "sans cle"]


def test_l_intitule_a_risque_vient_de_la_configuration(kit, monkeypatch, request, tmp_path):
    _poser_criteres(monkeypatch, request, tmp_path,
                    lambda brut: brut["entretien"].update(intitules_a_risque={
                        "motifs": ["Zorglub Engineer"], "avertissement": "texte inventé."}))
    prep = entretien.preparer(offre(titre="Senior Zorglub Engineer (H/F)"))
    assert "Intitule « Zorglub Engineer » : texte inventé." in prep.avertissements


def test_preparer_lit_la_table_entretien_une_seule_fois(kit, monkeypatch):
    """Les declencheurs et les intitules a risque viennent de la MEME lecture :
    un fichier modifie entre deux lectures ne melange pas deux configurations."""
    lectures = []
    vraie = entretien._entretien_configure

    def comptee():
        lectures.append(1)
        return vraie()

    monkeypatch.setattr(entretien, "_entretien_configure", comptee)
    prep = entretien.preparer(offre())
    assert prep.points
    assert len(lectures) == 1


def test_sans_intitules_a_risque_aucun_avertissement(kit, monkeypatch, request, tmp_path):
    motif = charger_criteres().brut["entretien"]["intitules_a_risque"]["motifs"][0]
    _poser_criteres(monkeypatch, request, tmp_path,
                    lambda brut: brut["entretien"].pop("intitules_a_risque"))
    prep = entretien.preparer(offre(titre=f"Senior {motif.title()} (H/F)"))
    assert not any(a.startswith("Intitule «") for a in prep.avertissements)


# --------------------------------------------------------------------------
# Le decoupage
# --------------------------------------------------------------------------


def test_le_decoupage_retrouve_toutes_les_sections():
    sections = entretien.decouper(KIT_17)
    titres = [s.titre for s in sections]
    assert "6. Tes questions à eux" in titres
    assert any("embarqué" in t for t in titres)


def test_une_section_ne_deborde_pas_sur_la_suivante():
    sections = {s.titre: s.corps for s in entretien.decouper(KIT_17)}
    corps = sections["6. Tes questions à eux"]
    assert "Trois questions" in corps
    assert "liste de la veille" not in corps


def test_la_premiere_ligne_ignore_les_tableaux_et_les_chevrons():
    s = entretien.Section("t", 2, "> « Deux mois. »\n\nautre chose")
    assert s.premiere_ligne == "« Deux mois. »"


def test_est_suisse_suit_la_detection_du_pays(monkeypatch, request, tmp_path):
    """Les lieux suisses sont ceux de `geographie.pays`, pas une liste du code."""
    from tests.aide_criteres import poser_criteres

    assert not entretien._est_suisse(offre(lieu="Zzvillebourg"))

    def modifier(brut):
        brut["geographie"]["pays"]["suisse"].append("zzvillebourg")

    poser_criteres(monkeypatch, request, tmp_path, modifier)
    assert entretien._est_suisse(offre(lieu="Zzvillebourg"))
    assert not entretien._est_suisse(offre(lieu="Mulhouse"))

"""L'assemblage : ses phrases, les mots de l'annonce, rien d'autre.

La règle qui tient tout : **rien n'est inventé**. Chaque phrase vient soit de
son gabarit, soit de l'annonce. Les seules formulations que ce module produit
sont des charnières, qui ne disent rien de lui.

Et le résultat est **déterministe** : deux fois la même offre, deux fois le
même texte. C'est ce qui permet à l'affinement par modèle d'être un choix et
non une dépendance — si l'affinement échoue, le texte de base existe déjà.
"""

from __future__ import annotations

import pytest

from veille import assemblage


def _offre(**kw):
    base = {
        "titre": "Testeur logiciel WMS H/F",
        "employeur": "Exemple Logistik AG",
        "lieu": "Mulhouse",
        # Le corps doit contenir les termes, sinon ils sont ecartes : c'est
        # precisement la regle que ces tests verrouillent.
        "description": ("Vous pilotez la recette du wms en environnement supply chain. "
                        "Vous garantissez le rapprochement des stocks, la data quality "
                        "et la reprise des flux edi."),
        # La famille et l'atout sont ceux de l'exemple : la phrase du CV les lit.
        "famille": "recette_donnees",
        "atouts": ["domaine_logistique"],
        "explication": [
            {"libelle": "Logistique et transport",
             "points": 30.0, "detail": '"wms" dans l\'intitule'},
            {"libelle": "Famille : Recette des données et du décisionnel",
             "points": 20.0,
             "detail": '"rapprochement des stocks", "data quality", "flux edi" - plafonne'},
            {"libelle": "Zone : Trajet quotidien en train ou en voiture (~40 km)",
             "points": 25.0, "detail": '"mulhouse" dans le lieu annonce'},
            {"libelle": "Salaire publié", "points": 15.0,
             "detail": "44 000 - 48 000 EUR - dans ta cible"},
        ],
    }
    base.update(kw)
    return base


# --------------------------------------------------------------------------
# Ce qui est retenu de l'annonce
# --------------------------------------------------------------------------


def test_seuls_les_termes_releves_par_le_scoring_sont_cites():
    """Pas de recherche a l'aveugle : on reutilise ce qui est deja prouve."""
    ex = assemblage.exigences_de_loffre(_offre())
    termes = [t for e in ex for t in e.termes]
    assert "rapprochement des stocks" in termes
    assert "wms" in termes


def test_ce_qui_parle_de_lui_est_ecarte():
    """La zone et le salaire n'ont rien a faire dans « votre annonce demande »."""
    ex = assemblage.exigences_de_loffre(_offre())
    libelles = " ".join(e.libelle.lower() for e in ex)
    assert "zone" not in libelles
    assert "salaire" not in libelles


def test_au_plus_deux_exigences():
    """Une lettre qui recite l'annonce se voit autant qu'une lettre generique."""
    assert len(assemblage.exigences_de_loffre(_offre())) <= assemblage.MAX_EXIGENCES


def test_les_exigences_sont_triees_par_poids():
    ex = assemblage.exigences_de_loffre(_offre())
    assert [e.points for e in ex] == sorted([e.points for e in ex], reverse=True)


def test_une_contribution_sans_terme_cite_est_ignoree():
    o = _offre(explication=[{"libelle": "Anglais suffisant", "points": 5.0,
                             "detail": "environnement international repere"}])
    assert assemblage.exigences_de_loffre(o) == []


def test_une_contribution_negative_est_ignoree():
    o = _offre(explication=[{"libelle": "Allemand exige", "points": -15.0,
                             "detail": '"deutsch" dans le texte'}])
    assert assemblage.exigences_de_loffre(o) == []


# --------------------------------------------------------------------------
# Le paragraphe produit
# --------------------------------------------------------------------------


def test_le_paragraphe_cite_les_mots_de_lemployeur():
    a = assemblage.assembler(_offre(), langue="en")
    assert "rapprochement des stocks" in a.paragraphe
    assert a.paragraphe.startswith("Your advertisement names")


def test_le_paragraphe_existe_en_francais():
    a = assemblage.assembler(_offre(), langue="fr")
    assert "Votre annonce cite" in a.paragraphe
    assert "rapprochement des stocks" in a.paragraphe


def test_lassemblage_est_deterministe():
    """Deux fois la meme offre, deux fois le meme texte. C'est ce qui permet
    a l'affinement d'etre un choix et non une dependance."""
    a = assemblage.assembler(_offre(), langue="en")
    b = assemblage.assembler(_offre(), langue="en")
    assert a.paragraphe == b.paragraphe
    assert a.phrase_cv == b.phrase_cv


def test_une_offre_sans_matiere_le_dit_au_lieu_dinventer():
    """Le cas le plus important : quand on n'a rien, on ne fabrique rien."""
    a = assemblage.assembler(_offre(explication=[]), langue="en")
    assert a.paragraphe == ""
    assert a.raison_vide
    assert "colle le texte complet" in a.raison_vide.lower()


def test_lenumeration_est_lisible():
    a = assemblage.assembler(_offre(), langue="en")
    assert " and " in a.paragraphe
    assert ", ," not in a.paragraphe


# --------------------------------------------------------------------------
# La phrase du CV — proposée, jamais imposée
# --------------------------------------------------------------------------


def test_la_phrase_cv_vient_de_la_famille_et_des_atouts():
    p = assemblage.phrase_cv(_offre(), langue="en")
    assert "data and business intelligence testing" in p
    assert "warehouse management systems" in p, "l'atout doit completer la famille"


def test_la_phrase_cv_reste_dans_le_vocabulaire_du_referentiel():
    """Aucun superlatif, aucune experience inventee."""
    p = assemblage.phrase_cv(_offre(), langue="en").lower()
    for interdit in ("expert", "passionate", "extensive", "years of", "leading",
                     "excellent", "proven track record"):
        assert interdit not in p, f"formulation inventee : {interdit}"


def test_une_famille_inconnue_ne_propose_rien():
    """Mieux vaut ne rien proposer qu'une phrase a cote."""
    assert assemblage.phrase_cv(_offre(famille="famille_inconnue"), langue="en") == ""
    assert assemblage.phrase_cv(_offre(famille=""), langue="en") == ""


def test_les_atouts_en_chaine_sont_acceptes():
    """Le premier atout n'a pas de formule : la phrase prend celle du suivant."""
    o = _offre(atouts="contexte_mobile,accessibilite")
    assert "digital accessibility testing" in assemblage.phrase_cv(o, langue="en")


def _criteres_sans_formule_en(tmp_path, monkeypatch):
    """Un fichier de critères, écrit dans tmp_path, où une famille n'a de formule qu'en français."""
    import yaml

    from veille import config

    brut = yaml.safe_load((config.RACINE / "exemple" / "criteres.yaml").read_text(encoding="utf-8"))
    famille = next(iter(brut["familles"]))
    brut["familles"][famille]["formule_cv"] = {"fr": "Une formule seulement en francais"}
    chemin = tmp_path / "criteres.yaml"
    chemin.write_text(yaml.safe_dump(brut, allow_unicode=True), encoding="utf-8")
    monkeypatch.setattr(config, "CHEMIN_CRITERES", chemin)
    config.recharger()
    return famille


def test_une_formule_sans_anglais_ne_propose_rien_en_anglais(tmp_path, monkeypatch):
    """Le code ne signale pas la formule incomplète (`verifier_dossier`) : il ne propose rien
    dans la langue qui manque, et la famille n'est pas « couverte »."""
    from veille import config

    famille = _criteres_sans_formule_en(tmp_path, monkeypatch)
    try:
        assert assemblage.phrase_cv(_offre(famille=famille, atouts=[]), langue="en") == ""
        assert "francais" in assemblage.phrase_cv(_offre(famille=famille, atouts=[]), langue="fr")
        assert famille not in assemblage.familles_couvertes()
    finally:
        config.recharger()


def test_chaque_famille_de_l_exemple_a_une_formule_complete_ou_aucune():
    import yaml

    from veille import config

    brut = yaml.safe_load((config.RACINE / "exemple" / "criteres.yaml").read_text(encoding="utf-8"))
    for nom, famille in brut["familles"].items():
        formule = famille.get("formule_cv")
        if formule is None:
            continue
        assert set(formule) == {"en", "fr"}, nom
        assert all(str(v).strip() for v in formule.values()), nom


# --------------------------------------------------------------------------
# Le corps de l'annonce, et les termes les plus rares
#
# Citer un mot du TITRE montre qu'on a lu le titre. Citer une exigence enfouie
# dans la description montre qu'on a lu l'annonce. C'est toute la difference
# entre une lettre qui parait personnalisee et une qui l'est.
#
# Et la specificite se MESURE, sur son corpus : un terme de niche sort dans
# deux ou trois annonces, « test » dans une sur cinq. Un terme rare prouve la
# lecture ; un terme courant non.
# --------------------------------------------------------------------------


def test_un_terme_present_seulement_dans_lintitule_est_ecarte():
    o = _offre(
        titre="Testeur WMS",
        description="Vous assurez la qualite des livraisons du site.",
        explication=[{"libelle": "Logistique et transport",
                      "points": 30.0, "detail": '"wms" dans l\'intitule'}],
    )
    assert assemblage.exigences_de_loffre(o) == []


def test_un_terme_present_dans_le_corps_est_retenu():
    o = _offre(
        description="Vous garantissez le rapprochement des stocks de notre WMS.",
        explication=[{"libelle": "Recette des données et du décisionnel",
                      "points": 20.0, "detail": '"rapprochement des stocks", "wms"'}],
    )
    termes = [t for e in assemblage.exigences_de_loffre(o) for t in e.termes]
    assert "rapprochement des stocks" in termes and "wms" in termes


def test_au_plus_trois_termes_cites():
    """Quatre font une liste, pas une lecture."""
    o = _offre(
        description="rapprochement des stocks, data quality, edi, wms et inventaire.",
        explication=[
            {"libelle": "Logistique et transport", "points": 30.0,
             "detail": '"wms", "inventaire"'},
            {"libelle": "Recette des données et du décisionnel", "points": 20.0,
             "detail": '"rapprochement des stocks", "data quality", "edi"'},
        ],
    )
    a = assemblage.assembler(o, langue="en")
    assert len(assemblage.termes_a_citer(assemblage.exigences_de_loffre(o))) <= 3
    assert a.paragraphe.count(",") <= 2


def test_les_termes_les_plus_rares_sont_preferes(monkeypatch):
    """La selection suit la frequence mesuree sur son corpus."""
    monkeypatch.setattr(assemblage, "_frequences",
                        lambda t: {"test": 50, "wms": 7, "edi": 4, "data quality": 1})
    ex = [assemblage.Exigence(termes=["test", "wms", "edi", "data quality"],
                              libelle="x", points=10.0)]
    assert assemblage.termes_a_citer(ex) == ["data quality", "edi", "wms"]


def test_sans_mesure_le_terme_le_plus_long_fait_foi(monkeypatch):
    """Base indisponible : on retombe sur un critere raisonnable."""
    monkeypatch.setattr(assemblage, "_frequences", lambda t: {})
    ex = [assemblage.Exigence(termes=["wms", "rapprochement des stocks", "ci"],
                              libelle="x", points=10.0)]
    assert assemblage.termes_a_citer(ex)[0] == "rapprochement des stocks"


def test_une_annonce_dont_les_termes_ne_sont_quau_titre_le_dit():
    o = _offre(
        titre="Testeur WMS",
        description="Poste a pourvoir. Equipe dynamique.",
        explication=[{"libelle": "Logistique et transport",
                      "points": 30.0, "detail": '"wms" dans l\'intitule'}],
    )
    a = assemblage.assembler(o, langue="en")
    assert a.paragraphe == ""
    assert "intitulé" in a.raison_vide or "intitule" in a.raison_vide


def test_la_mesure_de_rarete_ne_casse_pas_sans_base(monkeypatch):
    def plante(*a, **k):
        raise RuntimeError("base indisponible")

    import veille.db as db_mod
    monkeypatch.setattr(db_mod, "connexion", plante)
    assert assemblage._frequences(["wms"]) == {}


# --------------------------------------------------------------------------
# LA CHARNIERE NE DOIT RIEN AFFIRMER SUR LUI
#
# 02/10/2026, lu sur un dossier reel. Transpose ici a l'exemple, une lettre
# disait, a trois paragraphes d'intervalle :
#
#   « Your advertisement mentions wms, edi and cross-docking. That is precisely
#     the ground I work on today, and what the paragraph above describes. »
#   « Where I am honest with you: I have no EDI track record. »
#
# Le meme document affirmait travailler sur l'EDI tous les jours et n'y avoir
# jamais touche. Une lettre qui se contredit se remarque immediatement — et
# c'est la charniere qui mentait, pas lui.
# --------------------------------------------------------------------------


def test_la_charniere_naffirme_aucune_experience():
    """Elle est la seule phrase ecrite par le programme : elle doit etre vraie
    pour TOUTE offre, y compris celles dont il ne connait pas le domaine."""
    for langue, phrase in assemblage.CHARNIERES.items():
        bas = phrase.lower()
        for interdit in ("je travaille", "i work", "mon quotidien", "my daily",
                         "terrain sur lequel", "the ground i", "j'ai l'habitude",
                         "i am familiar", "experience"):
            assert interdit not in bas, f"{langue} : « {interdit} » dans la charniere"


def test_la_charniere_ne_commente_pas_le_document():
    """« et ce que decrit le paragraphe ci-dessus » : dans la lettre francaise,
    le paragraphe ci-dessus etait « Madame, Monsieur, »."""
    for langue, phrase in assemblage.CHARNIERES.items():
        bas = phrase.lower()
        for interdit in ("ci-dessus", "ci-dessous", "paragraph above",
                         "paragraph below", "above describes"):
            assert interdit not in bas, f"{langue} : metatexte « {interdit} »"


def test_la_charniere_ne_dit_que_ce_qui_est_verifiable():
    """Elle ne doit porter que les termes, et rien d'autre."""
    for phrase in assemblage.CHARNIERES.values():
        assert "{termes}" in phrase
        assert phrase.count(".") == 1, "une seule phrase, un seul point"


def test_les_termes_sont_cites_avec_la_casse_de_lannonce():
    d = "Migration EDI en environnement eCommerce, avec reprise du rapprochement des stocks."
    assert assemblage._casse_dorigine("edi", d) == "EDI"
    assert assemblage._casse_dorigine("ecommerce", d) == "eCommerce"
    assert assemblage._casse_dorigine("rapprochement des stocks", d) == "rapprochement des stocks"


def test_un_terme_absent_de_lannonce_nest_pas_invente():
    assert assemblage._casse_dorigine("kubernetes", "une annonce") == "kubernetes"
    assert assemblage._casse_dorigine("wms", "") == "wms"


def test_le_paragraphe_assemble_ne_se_contredit_pas_avec_l_aveu():
    """Le cas du 02/10, transpose a l'exemple : la charniere ne doit plus
    revendiquer l'EDI."""
    offre = {
        "titre": "Testeur WMS - Migration EDI en environnement supply chain",
        "description": ("Migration EDI en environnement supply chain. "
                        "Reprise du rapprochement des stocks et des flux de cross-docking."),
        "explication": [
            {"libelle": "Logistique et transport", "points": 30,
             "detail": '"edi" dans l\'intitule'},
            {"libelle": "Recette des données et du décisionnel", "points": 20,
             "detail": '"rapprochement des stocks" dans la description'},
        ],
    }
    a = assemblage.assembler(offre, langue="en")
    if a.paragraphe:
        bas = a.paragraphe.lower()
        assert "i work on today" not in bas
        assert "paragraph above" not in bas


# --------------------------------------------------------------------------
# Les formules viennent de la configuration, jamais du code
# --------------------------------------------------------------------------


def test_formules_lues_de_la_configuration(monkeypatch, request, tmp_path):
    from tests.aide_criteres import poser_criteres

    def modifier(brut):
        brut["familles"]["test_fonctionnel"]["formule_cv"] = {"fr": "le test", "en": "testing"}

    poser_criteres(monkeypatch, request, tmp_path, modifier)
    o = _offre(famille="test_fonctionnel", atouts=[])
    assert assemblage.phrase_cv(o, "fr") == "avec un intérêt particulier pour le test"
    assert assemblage.phrase_cv(o, "en") == "with a particular interest in testing"


def test_une_famille_sans_formule_ne_propose_rien(monkeypatch, request, tmp_path):
    from tests.aide_criteres import poser_criteres

    poser_criteres(
        monkeypatch, request, tmp_path,
        lambda brut: brut["familles"]["test_fonctionnel"].pop("formule_cv", None),
    )
    o = _offre(famille="test_fonctionnel", atouts=[])
    assert assemblage.phrase_cv(o, "fr") == ""
    assert "test_fonctionnel" not in assemblage.familles_couvertes()


def test_la_formule_d_un_atout_vient_de_la_configuration(monkeypatch, request, tmp_path):
    from tests.aide_criteres import poser_criteres

    def modifier(brut):
        brut["atouts"]["outils_test"]["formule"] = {"fr": "un outil", "en": "a tool"}

    poser_criteres(monkeypatch, request, tmp_path, modifier)
    o = _offre(atouts=["outils_test"])
    assert assemblage.phrase_cv(o, "en").endswith(" and a tool")

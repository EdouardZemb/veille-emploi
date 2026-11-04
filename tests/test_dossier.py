"""Tests de la selection des pieces de candidature.

Un kit peut contenir un CV francais ET un dossier suisse en anglais. Les deux ne
doivent jamais partir ensemble : une candidature francaise avec un dossier
suisse anglophone en piece jointe fait mauvais effet.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.sauts import sauter
from veille import dossier


def _weasyprint_utilisable() -> bool:
    """WeasyPrint rend-il un PDF sur cette machine ? Sous Windows sans Pango,
    l'import leve OSError et non ImportError : on attrape tout, comme le fait
    `rendu.lettre_en_pdf`. Sur le serveur, il est installe et ces tests tournent."""
    try:
        from weasyprint import HTML  # noqa: F401
    except Exception:
        return False
    return True


@pytest.fixture
def kit(tmp_path, monkeypatch):
    """Un kit de forme courante."""
    for nom in (
        "cv.fr.pdf",
        "cv.ch.en.pdf",
        "dossier-complet.ch.en.pdf",
        "annexe-technique.pdf",
        "certificat-ctfl.pdf",
    ):
        (tmp_path / nom).write_bytes(b"%PDF-1.4 factice")
    (tmp_path / "lettre.md").write_text("Objet : {{titre}} chez {{employeur}}", encoding="utf-8")
    (tmp_path / "lettre_en.md").write_text("Subject: {{titre}} at {{employeur}}", encoding="utf-8")
    monkeypatch.setattr(dossier, "CHEMIN_KIT", tmp_path)
    monkeypatch.setattr(dossier, "CHEMIN_DOSSIERS", tmp_path / "sortie")
    return tmp_path


OFFRE_FR = {
    "titre": "Ingenieur QA",
    "employeur": "Entreprise Exemple SA",
    "lieu": "Strasbourg",
    "description": "Vous rejoindrez notre equipe et vous serez en charge des tests et des campagnes.",
    "explication": [],
}

OFFRE_CH_EN = {
    "titre": "Test Engineer",
    "employeur": "Exemplia",
    "lieu": "Basel, Switzerland",
    "description": "You will join our team and you will own the test strategy with us and for our users.",
    "salaire_devise": "CHF",
    "explication": [],
}


# --------------------------------------------------------------------------
# Detection
# --------------------------------------------------------------------------


def test_detection_langue():
    assert dossier.detecter_langue(OFFRE_FR) == "fr"
    assert dossier.detecter_langue(OFFRE_CH_EN) == "en"


def test_detection_pays():
    assert dossier.detecter_pays(OFFRE_FR) == "france"
    assert dossier.detecter_pays(OFFRE_CH_EN) == "ch"


# --------------------------------------------------------------------------
# Selection des pieces
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "nom,langue,pays,attendu",
    [
        ("annexe-technique.pdf", "fr", "france", True),   # sans etiquette : toujours
        ("annexe-technique.pdf", "en", "ch", True),
        ("cv.fr.pdf", "fr", "france", True),
        ("cv.fr.pdf", "en", "ch", False),
        ("cv.ch.en.pdf", "en", "ch", True),
        ("cv.ch.en.pdf", "fr", "france", False),
        ("cv.ch.en.pdf", "en", "france", False),          # bonne langue, mauvais pays
        ("cv.ch.en.pdf", "fr", "ch", False),              # bon pays, mauvaise langue
    ],
)
def test_une_piece_ne_part_que_dans_son_contexte(nom, langue, pays, attendu):
    assert dossier._piece_convient(Path(nom), langue, pays) is attendu


def test_le_cv_francais_ne_part_pas_avec_une_offre_suisse_anglophone(kit):
    r = dossier.generer(dict(OFFRE_CH_EN))
    assert "cv.ch.en.pdf" in r.fichiers
    assert "cv.fr.pdf" not in r.fichiers
    assert "annexe-technique.pdf" in r.fichiers, "les pieces sans etiquette partent toujours"


def test_le_dossier_suisse_ne_part_pas_avec_une_offre_francaise(kit):
    r = dossier.generer(dict(OFFRE_FR))
    assert "cv.fr.pdf" in r.fichiers
    assert "cv.ch.en.pdf" not in r.fichiers
    assert "dossier-complet.ch.en.pdf" not in r.fichiers


def test_les_pieces_ecartees_sont_annoncees(kit):
    r = dossier.generer(dict(OFFRE_FR))
    assert any("non jointes" in a for a in r.avertissements)
    assert any("cv.ch.en.pdf" in a for a in r.avertissements)


# --------------------------------------------------------------------------
# Lettre
# --------------------------------------------------------------------------


def test_la_lettre_suit_la_langue_de_loffre(kit):
    assert dossier.generer(dict(OFFRE_CH_EN)).gabarit_lettre == "lettre_en.md"
    assert dossier.generer(dict(OFFRE_FR)).gabarit_lettre == "lettre.md"


def test_les_marqueurs_sont_remplis(kit):
    r = dossier.generer(dict(OFFRE_FR))
    texte = (r.chemin / "lettre-de-motivation.md").read_text(encoding="utf-8")
    assert "Ingenieur QA" in texte
    assert "Entreprise Exemple SA" in texte
    assert "{{" not in texte


def test_un_marqueur_inconnu_reste_visible(kit, monkeypatch):
    """On ne devine jamais : le trou doit se voir a la relecture."""
    (kit / "lettre.md").write_text("Reference : {{inexistant}}", encoding="utf-8")
    r = dossier.generer(dict(OFFRE_FR))
    texte = (r.chemin / "lettre-de-motivation.md").read_text(encoding="utf-8")
    assert "[[inexistant - À COMPLÉTER]]" in texte
    assert any("compléter" in a.lower() for a in r.avertissements)


# --------------------------------------------------------------------------
# Kit absent
# --------------------------------------------------------------------------


def test_un_kit_vide_retombe_sur_les_gabarits_du_depot(tmp_path, monkeypatch):
    """Regression : pointer VEILLE_KIT sur un dossier encore vide cassait la
    generation au lieu de la degrader."""
    vide = tmp_path / "kit-vide"
    vide.mkdir()
    monkeypatch.setattr(dossier, "CHEMIN_KIT", vide)
    monkeypatch.setattr(dossier, "CHEMIN_DOSSIERS", tmp_path / "sortie")
    r = dossier.generer(dict(OFFRE_FR))
    assert r.gabarit_lettre, "une lettre doit quand meme etre produite"
    assert "lettre-de-motivation.md" in r.fichiers
    assert "fiche-offre.md" in r.fichiers


def test_le_kit_prime_sur_les_gabarits_du_depot(kit):
    """Des qu'une lettre est dans le kit, c'est elle qui sert."""
    r = dossier.generer(dict(OFFRE_FR))
    assert r.gabarit_lettre == "lettre.md"
    texte = (r.chemin / "lettre-de-motivation.md").read_text(encoding="utf-8")
    assert "Objet : Ingenieur QA chez Entreprise Exemple SA" in texte, "le gabarit du kit, pas celui du depot"


def test_sans_kit_du_tout_la_fiche_est_produite(tmp_path, monkeypatch):
    monkeypatch.setattr(dossier, "CHEMIN_KIT", tmp_path / "inexistant")
    monkeypatch.setattr(dossier, "CHEMIN_DOSSIERS", tmp_path / "sortie")
    r = dossier.generer(dict(OFFRE_FR))
    assert "fiche-offre.md" in r.fichiers, "la fiche de l'offre doit toujours etre produite"
    assert any("CV PDF" in a for a in r.avertissements)


# --------------------------------------------------------------------------
# « Le kit est-il branche ? » se lit dans le CONTENU, pas dans la configuration
#
# Defaut trouve apres qu'Edouard a dit « la generation du dossier ne
# fonctionne pas ». Elle fonctionnait : elle produisait un squelette de lettre
# sans CV, exactement comme prevu quand le kit n'est pas la. Mais
# `_kit_est_provisoire()` rendait False des que VEILLE_KIT etait DEFINIE —
# meme vers un dossier vide — donc la console n'affichait aucun avertissement.
# Il voyait un resultat creux sans jamais savoir pourquoi.
# --------------------------------------------------------------------------


def test_un_kit_vide_est_provisoire_meme_si_la_variable_est_definie(tmp_path, monkeypatch):
    from veille import dossier

    vide = tmp_path / "kit"
    vide.mkdir()
    monkeypatch.setenv("VEILLE_KIT", str(vide))
    monkeypatch.setattr(dossier, "CHEMIN_KIT", vide)
    assert dossier._kit_est_provisoire(), "un dossier vide n'est pas un kit"
    assert dossier.pieces_du_kit() == []


def test_un_kit_qui_contient_une_vraie_piece_nest_plus_provisoire(tmp_path, monkeypatch):
    from veille import dossier

    plein = tmp_path / "kit"
    plein.mkdir()
    (plein / "cv.fr.pdf").write_bytes(b"%PDF-1.4 fictif")
    monkeypatch.setattr(dossier, "CHEMIN_KIT", plein)
    assert not dossier._kit_est_provisoire()
    assert dossier.pieces_du_kit() == ["cv.fr.pdf"]


def test_un_dossier_absent_est_provisoire(tmp_path, monkeypatch):
    from veille import dossier

    monkeypatch.setattr(dossier, "CHEMIN_KIT", tmp_path / "nexiste-pas")
    assert dossier._kit_est_provisoire()
    assert dossier.pieces_du_kit() == []


def test_le_marqueur_provisoire_prime_sur_le_contenu(tmp_path, monkeypatch):
    """`gabarits/` porte un `.provisoire` : ce sont des modeles, pas des pieces."""
    from veille import dossier

    d = tmp_path / "kit"
    d.mkdir()
    (d / ".provisoire").write_text("modeles de travail")
    (d / "cv.fr.pdf").write_bytes(b"%PDF-1.4 fictif")
    monkeypatch.setattr(dossier, "CHEMIN_KIT", d)
    assert dossier._kit_est_provisoire()


# --------------------------------------------------------------------------
# Trois lettres, choisies par ce que l'offre est
#
# Les lettres d'un kit ne sont pas interchangeables : l'une parle d'une
# famille de metier, une autre d'une autre famille, une troisieme d'un domaine.
# Les joindre indifferemment serait pire que de n'en joindre aucune.
# --------------------------------------------------------------------------


def _kit(tmp_path, *noms):
    d = tmp_path / "kit"
    d.mkdir(exist_ok=True)
    for n in noms:
        (d / n).write_text(f"gabarit {n} pour {{{{employeur}}}}", encoding="utf-8")
    return d


def test_latout_prime_sur_la_famille(tmp_path, monkeypatch):
    """Une offre DANS LE DOMAINE d'un atout merite la lettre de ce domaine."""
    from veille import dossier

    d = _kit(tmp_path, "lettre_atout_domaine_invente.md",
             "lettre_autre_famille_inventee.md", "lettre.md")
    monkeypatch.setattr(dossier, "CHEMIN_KIT", d)
    choisie, _ = dossier._choisir_lettre({
        "titre": "Test Manager", "famille": "autre_famille_inventee",
        "atouts": ["domaine_invente"], "description": "Nous recherchons une personne pour la recette des logiciels, dans une equipe et avec les metiers.",
        "lieu": "Mulhouse",
    })
    assert choisie.name == "lettre_atout_domaine_invente.md"


def test_la_famille_sert_quand_aucun_atout_ne_correspond(tmp_path, monkeypatch):
    from veille import dossier

    d = _kit(tmp_path, "lettre_atout_domaine_invente.md",
             "lettre_famille_inventee.md", "lettre.md")
    monkeypatch.setattr(dossier, "CHEMIN_KIT", d)
    choisie, _ = dossier._choisir_lettre({
        "titre": "Ingenieur IVVQ", "famille": "famille_inventee",
        "atouts": ["stack_pratiquee"], "description": "Nous recherchons une personne pour la recette des logiciels, dans une equipe et avec les metiers.",
        "lieu": "Mulhouse",
    })
    assert choisie.name == "lettre_famille_inventee.md"


def test_les_atouts_en_chaine_sont_acceptes(tmp_path, monkeypatch):
    """La base les stocke separes par des virgules."""
    from veille import dossier

    d = _kit(tmp_path, "lettre_atout_domaine_invente.md", "lettre.md")
    monkeypatch.setattr(dossier, "CHEMIN_KIT", d)
    choisie, _ = dossier._choisir_lettre({
        "titre": "x", "famille": "", "atouts": "outils_test,domaine_invente",
        "description": "Nous recherchons une personne pour la recette des logiciels, dans une equipe et avec les metiers.",
        "lieu": "Mulhouse",
    })
    assert choisie.name == "lettre_atout_domaine_invente.md"


def test_le_repli_tient_quand_aucune_lettre_ne_correspond(tmp_path, monkeypatch):
    from veille import dossier

    d = _kit(tmp_path, "lettre.md")
    monkeypatch.setattr(dossier, "CHEMIN_KIT", d)
    choisie, _ = dossier._choisir_lettre({
        "titre": "x", "famille": "maintenance_applicative", "atouts": [],
        "description": "Nous recherchons une personne pour la recette des logiciels, dans une equipe et avec les metiers.",
        "lieu": "Mulhouse",
    })
    assert choisie.name == "lettre.md"


# --------------------------------------------------------------------------
# Deux paquets, et la fiche de preparation ne part jamais
#
# `fiche-offre.md` contient le score, l'explication ligne a ligne et le texte
# brut de l'annonce. C'est sa note de preparation d'entretien. Elle n'a rien a
# faire dans ce qu'un recruteur recoit.
# --------------------------------------------------------------------------


def _kit_complet(tmp_path, monkeypatch):
    from veille import dossier

    k = tmp_path / "kit"
    k.mkdir()
    (k / "lettre.md").write_text(
        "Camille Exemple\n\nI am applying for the position of {{titre}}.\n\n"
        "Dear Sir,\n\nYours sincerely,\nCamille Exemple\n", encoding="utf-8")
    (k / "annexe-technique.pdf").write_bytes(b"%PDF-1.4 fictif")
    # DEUX CV, un francais et un anglais pour la Suisse : depuis que la langue
    # est detectee pour de bon, un kit qui n'a que le CV francais ne couvre plus
    # une annonce anglaise — et la lettre fictive de ce kit est anglaise.
    (k / "cv.fr.pdf").write_bytes(b"%PDF-1.4 fictif")
    (k / "cv.ch.en.pdf").write_bytes(b"%PDF-1.4 fictif anglais")
    monkeypatch.setattr(dossier, "CHEMIN_KIT", k)
    monkeypatch.setattr(dossier, "CHEMIN_DOSSIERS", tmp_path / "sortie")
    return k


def _offre_test():
    return {
        # Offre anglophone EN SUISSE : c'est le seul contexte que ce kit
        # couvre en anglais, `cv.ch.en.pdf` etant etiquete ch+en. Une
        # annonce anglaise situee en France n'a aucun CV — voir le
        # test ci-dessous, qui fige ce trou plutot que de le cacher.
        "titre": "WMS Test Engineer", "employeur": "Une societe", "lieu": "Basel",
        # Texte anglais : la lettre fictive du kit est anglaise,
        # et la langue de l'annonce doit desormais correspondre.
        "description": ("We are looking for a test engineer and you will work with our teams on the systems in scope."),
        "famille": "famille_inventee",
        "atouts": [], "explication": [], "url": "https://exemple.invalid/1",
        "source": "test", "type_contrat": "CDI",
    }


def test_le_paquet_denvoi_ne_contient_pas_la_fiche(tmp_path, monkeypatch):
    import zipfile

    from veille import dossier

    _kit_complet(tmp_path, monkeypatch)
    r = dossier.generer(_offre_test())
    envoi = next(p for p in r.chemin.glob("*candidature.zip"))
    with zipfile.ZipFile(envoi) as z:
        noms = z.namelist()
    assert not any("fiche" in n.lower() for n in noms), noms
    assert not any(n.endswith(".md") for n in noms), "aucun markdown a un recruteur"


@pytest.mark.skipif(sauter(_weasyprint_utilisable), reason="WeasyPrint indisponible sur cette machine")
def test_le_paquet_denvoi_porte_des_noms_recevables(tmp_path, monkeypatch):
    import zipfile

    from veille import dossier

    _kit_complet(tmp_path, monkeypatch)
    r = dossier.generer(_offre_test())
    with zipfile.ZipFile(next(r.chemin.glob("*candidature.zip"))) as z:
        noms = z.namelist()
    assert all(n.startswith("Camille-Exemple-") for n in noms), noms
    assert any("CV" in n for n in noms)
    assert any("Lettre-de-motivation" in n for n in noms)


def test_le_dossier_complet_garde_la_fiche_pour_lui(tmp_path, monkeypatch):
    import zipfile

    from veille import dossier

    _kit_complet(tmp_path, monkeypatch)
    r = dossier.generer(_offre_test())
    with zipfile.ZipFile(next(r.chemin.glob("*DOSSIER-COMPLET.zip"))) as z:
        assert any("fiche-offre" in n for n in z.namelist())


def test_les_paquets_perimes_sont_supprimes(tmp_path, monkeypatch):
    """Un paquet d'une generation precedente contenait la fiche : il ne doit
    pas survivre a une regeneration."""
    from veille import dossier

    _kit_complet(tmp_path, monkeypatch)
    r = dossier.generer(_offre_test())
    piege = r.chemin / f"{r.chemin.name}.zip"
    piege.write_bytes(b"ancien paquet avec la fiche dedans")
    dossier.generer(_offre_test())
    assert not piege.exists(), "l'ancien paquet doit disparaitre"


@pytest.mark.skipif(sauter(_weasyprint_utilisable), reason="WeasyPrint indisponible sur cette machine")
def test_la_lettre_sort_en_pdf(tmp_path, monkeypatch):
    from veille import dossier

    _kit_complet(tmp_path, monkeypatch)
    r = dossier.generer(_offre_test())
    pdf = r.chemin / "Camille-Exemple-Lettre-de-motivation.pdf"
    assert pdf.exists() and pdf.stat().st_size > 1000
    assert pdf.read_bytes().startswith(b"%PDF")


def test_sans_aucune_piece_pdf_le_paquet_vide_est_signale(tmp_path, monkeypatch):
    from veille import dossier

    k = tmp_path / "kit"
    k.mkdir()
    (k / "lettre.md").write_text("Camille Exemple\n", encoding="utf-8")
    monkeypatch.setattr(dossier, "CHEMIN_KIT", k)
    monkeypatch.setattr(dossier, "CHEMIN_DOSSIERS", tmp_path / "sortie")
    r = dossier.generer(_offre_test())
    # La lettre est rendue en PDF, donc le paquet n'est pas vide — mais le CV
    # manque et ca doit etre dit.
    assert any("CV" in a for a in r.avertissements), r.avertissements


# --------------------------------------------------------------------------
# L'etiquette « manuel »
#
# Une variante du CV, nommee `cv-variante-en.pdf` « sans etiquette reconnue
# pour qu'elle ne parte jamais automatiquement ». Mesure avant copie : la
# regle joint par DEFAUT tout ce qui n'a aucune etiquette — c'est ce qui fait
# partir l'annexe technique partout. Cette variante serait donc partie dans
# chaque candidature, a cote de l'autre CV.
# --------------------------------------------------------------------------


def test_un_nom_sans_point_na_aucune_etiquette_et_part_partout():
    """Le comportement qui piegeait — on le verrouille pour qu'il se voie."""
    from pathlib import Path as _P

    assert dossier._piece_convient(_P("cv-variante-en.pdf"), "fr", "france")
    assert dossier._piece_convient(_P("cv-variante-en.pdf"), "en", "ch")


def test_letiquette_manuel_retire_la_piece_de_tout_envoi():
    from pathlib import Path as _P

    for langue, pays in (("fr", "france"), ("en", "ch"), ("de", "ch")):
        assert not dossier._piece_convient(
            _P("cv-variante.manuel.ch.en.pdf"), langue, pays)


def test_letiquette_manuel_ne_depend_pas_des_autres_etiquettes():
    from pathlib import Path as _P

    assert not dossier._piece_convient(_P("note.manuel.pdf"), "fr", "france")


def test_les_cv_etiquetes_partent_dans_le_bon_contexte():
    from pathlib import Path as _P

    assert dossier._piece_convient(_P("cv.fr.pdf"), "fr", "france")
    assert not dossier._piece_convient(_P("cv.fr.pdf"), "en", "ch")
    assert dossier._piece_convient(_P("cv.ch.en.pdf"), "en", "ch")
    assert not dossier._piece_convient(_P("cv.ch.en.pdf"), "fr", "france")
    assert not dossier._piece_convient(_P("cv.ch.en.pdf"), "en", "france")


# --------------------------------------------------------------------------
# LA LANGUE PASSE AVANT LA SPECIALITE
#
# 02/10/2026, defaut structurel vu sur un dossier reel : l'offre est en
# France, son annonce est en francais, et la console a produit une lettre
# EN ANGLAIS. Les lettres de specialite d'un kit peuvent toutes etre
# anglaises ; la selection choisissait par famille sans jamais comparer les
# langues. Une lettre anglaise chez un recruteur francais est eliminatoire —
# elle coute l'offre, pas des points.
# --------------------------------------------------------------------------

LETTRE_EN = ("<!-- gabarit -->\n\nDear {{contact}},\n\n"
             "I am applying for the position of {{titre}}.\n\n"
             "Yours sincerely,\nCamille Exemple\n")
LETTRE_FR = ("<!-- gabarit -->\n\nMadame, Monsieur,\n\n"
             "Je postule au poste de {{titre}}.\n\n"
             "Je vous prie d'agreer mes salutations distinguees.\nCamille Exemple\n")


def _kit_langues(tmp_path, monkeypatch, **fichiers):
    from veille import dossier

    d = tmp_path / "kit"
    d.mkdir(exist_ok=True)
    for nom, contenu in fichiers.items():
        (d / nom.replace("__", ".")).write_text(contenu, encoding="utf-8")
    monkeypatch.setattr(dossier, "CHEMIN_KIT", d)
    return d


def _offre_fr(**kw):
    base = {"titre": "Ingenieur IVVQ", "famille": "famille_inventee",
            "atouts": [], "lieu": "Mulhouse",
            "description": ("Nous recherchons un ingenieur pour la recette "
                            "des logiciels logistiques. Vous travaillerez avec "
                            "les equipes et nous vous accompagnerons dans le "
                            "cadre des projets de migration.")}
    base.update(kw)
    return base


def _offre_en(**kw):
    base = {"titre": "WMS Test Engineer", "famille": "famille_inventee",
            "atouts": [], "lieu": "Basel",
            "description": ("We are looking for an engineer and you will work "
                            "with our teams for the testing of warehouse management "
                            "systems with the quality department.")}
    base.update(kw)
    return base


def test_une_annonce_francaise_ne_recoit_pas_la_lettre_anglaise(tmp_path, monkeypatch):
    """Le cas du 02/10, exactement."""
    from veille import dossier

    _kit_langues(tmp_path, monkeypatch,
                 lettre_famille_inventee__md=LETTRE_EN,
                 lettre_fr__md=LETTRE_FR)
    o = _offre_fr()
    assert dossier.detecter_langue(o) == "fr"
    choisie, alerte = dossier._choisir_lettre(o)
    assert choisie.name == "lettre_fr.md", (
        "une lettre francaise moins specialisee vaut mieux qu'une lettre "
        "anglaise specialisee")
    assert alerte == ""


def test_la_specialite_reprend_la_main_a_langue_egale(tmp_path, monkeypatch):
    from veille import dossier

    _kit_langues(tmp_path, monkeypatch,
                 lettre_famille_inventee_fr__md=LETTRE_FR,
                 lettre_fr__md=LETTRE_FR)
    choisie, alerte = dossier._choisir_lettre(_offre_fr())
    assert choisie.name == "lettre_famille_inventee_fr.md"
    assert alerte == ""


def test_une_annonce_anglaise_prend_bien_la_lettre_anglaise(tmp_path, monkeypatch):
    from veille import dossier

    _kit_langues(tmp_path, monkeypatch,
                 lettre_famille_inventee__md=LETTRE_EN,
                 lettre_fr__md=LETTRE_FR)
    o = _offre_en()
    assert dossier.detecter_langue(o) == "en"
    choisie, alerte = dossier._choisir_lettre(o)
    assert choisie.name == "lettre_famille_inventee.md"
    assert alerte == ""


def test_sans_gabarit_dans_la_bonne_langue_la_console_ne_sert_RIEN(tmp_path, monkeypatch):
    """DECISION RENVERSEE LE 02/10/2026 AU SOIR.

    Ce test affirmait « une page blanche n'aide personne » et verifiait que
    la console servait quand meme la lettre d'une autre langue, avec un
    avertissement. L'arbitrage d'Edouard est l'inverse : une lettre dans la
    mauvaise langue est eliminatoire, un dossier incomplet ne l'est pas.
    On ne sert plus rien, et on le dit.
    """
    from veille import dossier

    _kit_langues(tmp_path, monkeypatch,
                 lettre_famille_inventee__md=LETTRE_EN)
    monkeypatch.setattr(dossier, "CHEMIN_GABARITS", tmp_path / "vide")
    choisie, alerte = dossier._choisir_lettre(_offre_fr())
    assert choisie is None, "mieux vaut rien qu'une lettre eliminatoire"
    assert "francais" in alerte
    assert "lettre_famille_inventee_fr.md" in alerte


def test_le_suffixe_de_langue_ne_trompe_pas_la_selection(tmp_path, monkeypatch):
    """Un fichier mal nomme ne doit pas passer : c'est le CONTENU qui tranche."""
    from veille import dossier

    _kit_langues(tmp_path, monkeypatch,
                 lettre_famille_inventee_fr__md=LETTRE_EN,
                 lettre_fr__md=LETTRE_FR)
    choisie, alerte = dossier._choisir_lettre(_offre_fr())
    assert choisie.name == "lettre_fr.md"
    assert alerte == ""


def test_le_squelette_du_depot_est_signale_comme_tel(tmp_path, monkeypatch):
    """Bonne langue, mais aucune de ses phrases dedans : il doit le savoir."""
    from veille import dossier

    _kit_langues(tmp_path, monkeypatch,
                 lettre_famille_inventee__md=LETTRE_EN)
    choisie, alerte = dossier._choisir_lettre(_offre_fr())
    assert choisie.name == "lettre.md"
    assert choisie.parent != dossier.CHEMIN_KIT
    assert "squelette" in alerte
    assert "lettre_famille_inventee_fr.md" in alerte


def test_le_paragraphe_assemble_se_pose_dans_une_lettre_francaise():
    """Sans repere francais, le paragraphe n'etait pose nulle part et
    l'annonce n'etait pas citee du tout."""
    from veille import dossier

    sortie = dossier._inserer_paragraphe(LETTRE_FR, "PARAGRAPHE ASSEMBLE")
    assert "PARAGRAPHE ASSEMBLE" in sortie
    lignes = sortie.splitlines()
    i = lignes.index("PARAGRAPHE ASSEMBLE")
    assert any("Madame, Monsieur" in l or "Je postule" in l for l in lignes[:i])


# --------------------------------------------------------------------------
# Les caracteres qui sortent mal
#
# 02/10/2026 : Edouard signale des caracteres etranges dans le .md genere.
# Mesure : AUCUN melange UTF-8 / cp1252, ni dans les gabarits, ni dans le .md,
# ni dans le PDF — l'hypothese de la conversion ratee ne tient pas. Mais deux
# gabarits portaient U+2044 FRACTION SLASH dans leur ligne « Application — »,
# la ou un « / » est attendu. L'artefact vient des .docx eux-memes, ou Word
# l'avait introduit par autocorrection ; la conversion l'a fidelement recopie.
# --------------------------------------------------------------------------

CARACTERES_ADMIS = set(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
    " .,;:!?()[]{}<>/-_" + chr(92) + chr(34) + chr(39) + "@#%&*+=|~^$" + chr(10) + chr(9) + chr(13) +
    "\u00e0\u00e2\u00e4\u00e9\u00e8\u00ea\u00eb\u00ee\u00ef\u00f4\u00f6"
    "\u00f9\u00fb\u00fc\u00e7\u00c0\u00c2\u00c4\u00c9\u00c8\u00ca\u00cb"
    "\u00ce\u00cf\u00d4\u00d6\u00d9\u00db\u00dc\u00c7"
    "\u2019\u2014\u2013\u00ab\u00bb\u201c\u201d\u00b7\u20ac\u00ae\u00a9"
)


SANS_KIT_REEL = ("pas de kit reel : il n'est lu que par VEILLE_ENV, "
                 "que la suite pointe sur un fichier absent")


def _kit_reel():
    """Le dossier de kit de PRODUCTION, pas celui des tests.

    Lu, comme par `empreintes.dossier_kit()`, dans la ligne `VEILLE_KIT=` du fichier
    que designe `VEILLE_ENV`. Mais sans ses deux autres sources : cette aide ne lit
    pas la variable `VEILLE_KIT` (la suite la pose sur les gabarits de l'exemple), et
    elle ne se rabat pas sur `config/.env` quand `VEILLE_ENV` est absente, la ou
    `dossier_kit()` le fait. La suite pointe `VEILLE_ENV` sur un fichier absent
    (`conftest.py`) : elle ne lit que des fixtures, et les tests qui en dependent
    s'y sautent, sur le serveur aussi.
    """
    import os
    from pathlib import Path as _P

    brut = os.environ.get("VEILLE_ENV", "").strip()
    env = _P(brut) if brut else None
    if env is not None and env.is_file():
        for ligne in env.read_text(encoding="utf-8").splitlines():
            if ligne.strip().startswith("VEILLE_KIT="):
                d = _P(os.path.expanduser(ligne.split("=", 1)[1].strip()))
                return d if d.exists() else None
    return None


@pytest.mark.skipif(_kit_reel() is None, reason=SANS_KIT_REEL)
def test_aucun_gabarit_du_kit_ne_porte_de_caractere_douteux():
    """Le filet qui manquait : il attrape l'artefact AVANT l'envoi."""
    import unicodedata

    import re as _re

    fautifs = []
    for f in sorted(_kit_reel().glob("lettre*.md")):
        # On controle CE QUI PART : les notes internes vivent dans des
        # commentaires HTML et peuvent porter ce qu'elles veulent — un ⚠️,
        # un point de suspension. Elles ne sont jamais rendues.
        corps = _re.sub(r"<!--.*?-->", " ", f.read_text(encoding="utf-8"), flags=_re.S)
        for i, c in enumerate(corps):
            if c not in CARACTERES_ADMIS:
                fautifs.append(
                    f"{f.name} : U+{ord(c):04X} "
                    f"{unicodedata.name(c, 'SANS NOM')} en position {i} "
                    f"-> {corps[max(0, i - 30):i + 30]!r}")
                break
    assert fautifs == [], fautifs


@pytest.mark.skipif(_kit_reel() is None, reason=SANS_KIT_REEL)
def test_aucun_gabarit_ne_porte_de_signature_de_mauvais_encodage():
    """Les traces d'un UTF-8 relu en latin-1 ou en cp1252."""
    import re as _re

    for f in sorted(_kit_reel().glob("lettre*.md")):
        t = f.read_text(encoding="utf-8")
        assert not _re.search("\u00c3.", t), f"{f.name} : UTF-8 relu en latin-1"
        assert not _re.search("\u00e2\u20ac.", t), f"{f.name} : UTF-8 relu en cp1252"
        assert "\ufffd" not in t, f"{f.name} : caractere de remplacement"


def test_la_barre_de_fraction_est_detectee_comme_douteuse():
    """Garde-fou du garde-fou : le test ci-dessus doit mordre."""
    assert "\u2044" not in CARACTERES_ADMIS
    assert "/" in CARACTERES_ADMIS


# --------------------------------------------------------------------------
# Ce que le PDF montre REELLEMENT au recruteur
#
# 02/10/2026 : le module de rendu n'interpretait aucun Markdown. Les trois
# lettres du kit n'en utilisent pas, donc rien ne se voyait — jusqu'a ce que
# la premiere lettre FRANCAISE passe par le squelette du depot. Le PDF
# affichait alors « **Objet : candidature au poste de ...** », asterisques
# comprises, et la ligne de provenance « *Offre reperee via mail:generique
# le 02/10 - https://linkedin.com/...* », qui disait au recruteur par quel
# canal l'offre avait ete trouvee.
# --------------------------------------------------------------------------


def test_le_gras_markdown_ne_part_pas_avec_ses_asterisques():
    from veille import rendu

    html, _ = rendu._en_html("**Objet : candidature au poste de X**")
    assert "<strong>Objet : candidature au poste de X</strong>" in html
    assert "**" not in html


def test_litalique_est_rendu():
    from veille import rendu

    html, _ = rendu._en_html("*une mention*")
    assert "<em>une mention</em>" in html
    assert "*" not in html


def test_un_filet_horizontal_ne_sort_pas_dans_la_lettre():
    from veille import rendu

    html, _ = rendu._en_html("Madame,\n\n---\n\nCordialement")
    assert "---" not in html


def test_le_contenu_reste_echappe():
    """La transformation agit APRES l'echappement : rien ne doit pouvoir
    injecter de balise depuis le texte de la lettre."""
    from veille import rendu

    html, _ = rendu._en_html("**<script>alert(1)</script>**")
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_la_ligne_de_provenance_ne_part_pas_au_recruteur():
    """Elle est desormais dans un commentaire : visible dans le .md, absente
    du PDF."""
    from veille import dossier, rendu

    for nom in ("lettre.md", "lettre_en.md"):
        brut = (dossier.CHEMIN_GABARITS / nom).read_text(encoding="utf-8")
        # Meme chaine que la generation : notice retiree, puis commentaires.
        html, _ = rendu._en_html(rendu._corps(dossier.corps_du_gabarit(brut)))
        assert "{{source}}" not in html, nom
        assert "reperee via" not in html and "found via" not in html, nom


def test_la_notice_du_squelette_ne_part_pas_au_recruteur():
    from veille import dossier, rendu

    brut = (dossier.CHEMIN_GABARITS / "lettre.md").read_text(encoding="utf-8")
    corps = dossier.corps_du_gabarit(brut)
    html, _ = rendu._en_html(rendu._corps(corps))
    assert "GABARIT PROVISOIRE" not in html
    assert "Marqueurs disponibles" not in html
    assert "Madame, Monsieur" in html, "le corps de la lettre doit rester"


def test_corps_du_gabarit_ne_coupe_pas_une_lettre_du_kit():
    """Les lettres du kit n'ont pas de `---` : elles doivent traverser
    intactes."""
    from veille import dossier

    sans_separateur = "<!-- notice -->\n\nDear X,\n\nI am applying.\n"
    assert dossier.corps_du_gabarit(sans_separateur) == sans_separateur


def test_corps_du_gabarit_ne_coupe_jamais_plus_de_la_moitie():
    from veille import dossier

    texte = "ligne\n" * 4 + "---\n" + "corps\n"
    assert dossier.corps_du_gabarit(texte) == texte


# --------------------------------------------------------------------------
# Les lettres FRANCAISES du kit, et ce qu'elles ont revele
#
# 02/10/2026. Elles terminaient par une section Markdown ordinaire :
#     ⚠️ À supprimer avant envoi — notes de gabarit
# Les lettres anglaises du kit mettent leurs notes dans un commentaire HTML,
# invisible au rendu. Celles-ci non : la note et ses instructions de redaction
# partaient dans le PDF du recruteur.
# --------------------------------------------------------------------------


def test_un_bloc_qui_se_declare_interne_ne_part_pas():
    from veille import rendu

    html, _ = rendu._en_html(
        "Madame,\n\nLe corps de la lettre.\n\n"
        "\u26a0\ufe0f \u00c0 supprimer avant envoi \u2014 notes de gabarit\n\n"
        "- Completez les crochets.")
    assert "corps de la lettre" in html
    assert "supprimer avant envoi" not in html
    assert "Completez les crochets" not in html, (
        "tout ce qui suit la note interne doit tomber aussi")


@pytest.mark.parametrize("entete", [
    "\u00c0 supprimer avant envoi", "NE PART PAS AU RECRUTEUR",
    "Pour toi, pas pour le recruteur", "Delete before sending",
    "notes de gabarit",
])
def test_les_formulations_internes_connues_sont_reconnues(entete):
    from veille import rendu

    assert rendu.bloc_a_jeter(f"{entete} : ceci est une note")


def test_une_phrase_ordinaire_nest_pas_prise_pour_une_note():
    from veille import rendu

    assert not rendu.bloc_a_jeter(
        "Je serais heureux d'echanger sur les risques qualite.")


def test_les_marqueurs_des_notes_internes_ne_sont_pas_comptes():
    """Sinon la console annonce des marqueurs a completer qui n'existent pas
    dans la lettre envoyee."""
    from veille import rendu

    _, restants = rendu._en_html(
        "Madame,\n\n[[Societe]]\n\n\u00c0 supprimer avant envoi\n\n[[autre]]")
    assert restants == 1


def test_le_code_inline_perd_ses_accents_graves():
    from veille import rendu

    html, _ = rendu._en_html("Mon projet `projet-exemple` est public.")
    assert "projet-exemple" in html
    assert "`" not in html


# --------------------------------------------------------------------------
# Ou se pose la charniere — le plus specifique d'abord
#
# Dans une lettre francaise, « Madame, Monsieur, » precede « Je postule ».
# Les deux familles de reperes etant testees dans le meme test,
# la formule d'appel gagnait, et la charniere se posait AVANT l'annonce du
# poste : on citait l'annonce avant d'avoir dit a quoi on postulait.
# --------------------------------------------------------------------------

LETTRE_COMPLETE = ("Camille Exemple\n\nMadame, Monsieur,\n\n"
                   "Je postule au poste de [[intitule]], reference [[ref]].\n\n"
                   "Ces perimetres sont ceux dont j'ai la charge aujourd'hui.\n")


def test_la_charniere_se_pose_apres_la_phrase_qui_nomme_le_poste():
    from veille import dossier

    sortie = dossier._inserer_paragraphe(LETTRE_COMPLETE, "CHARNIERE")
    lignes = [l for l in sortie.splitlines() if l.strip()]
    i_charniere = lignes.index("CHARNIERE")
    i_postule = next(k for k, l in enumerate(lignes) if l.startswith("Je postule"))
    i_appel = next(k for k, l in enumerate(lignes) if l.startswith("Madame, Monsieur"))
    assert i_appel < i_postule < i_charniere, (
        "la charniere doit suivre « Je postule », pas la formule d'appel")


def test_la_charniere_precede_le_paragraphe_qui_enchaine():
    """Ses lettres enchainent dessus : « Ces perimetres sont ceux dont... »."""
    from veille import dossier

    lignes = [l for l in dossier._inserer_paragraphe(
        LETTRE_COMPLETE, "CHARNIERE").splitlines() if l.strip()]
    i = lignes.index("CHARNIERE")
    assert lignes[i + 1].startswith("Ces perimetres")


def test_sans_phrase_qui_nomme_le_poste_on_se_rabat_sur_la_formule_dappel():
    """Le squelette du depot n'a pas de « Je postule »."""
    from veille import dossier

    squelette = "Camille Exemple\n\nMadame, Monsieur,\n\nCordialement\n"
    lignes = [l for l in dossier._inserer_paragraphe(
        squelette, "CHARNIERE").splitlines() if l.strip()]
    assert lignes.index("CHARNIERE") == lignes.index("Madame, Monsieur,") + 1


def test_la_charniere_nest_posee_quune_seule_fois():
    from veille import dossier

    sortie = dossier._inserer_paragraphe(
        LETTRE_COMPLETE + "\nJe postule encore.\n", "CHARNIERE")
    assert sortie.count("CHARNIERE") == 1


# --------------------------------------------------------------------------
# LE SEGMENT FACULTATIF — la ponctuation orpheline
#
# La phrase est : « Je postule au poste suivant : {{titre}}{{#reference}} —
# référence {{reference}}{{/reference}}, publié sur {{source_lisible}}. »
# Sans référence, « — référence , publié sur LinkedIn » serait bancal. Le
# tiret et le mot sont DANS le segment, la virgule est DEHORS : c'est le
# gabarit qui decide ce qui disparait, pas une reparation de ponctuation
# apres coup — c'est precisement ce qui produit des virgules orphelines.
# --------------------------------------------------------------------------

PHRASE = ("Je postule au poste suivant : {{titre}}{{#reference}} \u2014 r\u00e9f\u00e9rence "
          "{{reference}}{{/reference}}, publi\u00e9 sur {{source_lisible}}.")
BASE = {"titre": "Ing\u00e9nieur IVVQ", "source_lisible": "LinkedIn"}


def test_avec_reference_le_segment_apparait():
    from veille import dossier

    t, manquants = dossier._remplir(PHRASE, {**BASE, "reference": "WMS-2026-114"})
    assert t == ("Je postule au poste suivant : Ing\u00e9nieur IVVQ \u2014 r\u00e9f\u00e9rence "
                 "WMS-2026-114, publi\u00e9 sur LinkedIn.")
    assert manquants == []


def test_sans_reference_le_segment_disparait_en_entier():
    from veille import dossier

    t, manquants = dossier._remplir(PHRASE, {**BASE, "reference": ""})
    assert t == ("Je postule au poste suivant : Ing\u00e9nieur IVVQ, publi\u00e9 sur LinkedIn.")
    assert manquants == [], "un segment facultatif n'est pas un marqueur manquant"


def test_aucune_ponctuation_orpheline_sans_reference():
    from veille import dossier

    t, _ = dossier._remplir(PHRASE, {**BASE, "reference": ""})
    assert " ," not in t and ",," not in t
    assert "\u2014" not in t, "le tiret doit partir avec le segment"
    assert "r\u00e9f\u00e9rence" not in t.lower()
    assert t.count(".") == 1


def test_une_reference_faite_despaces_compte_pour_vide():
    from veille import dossier

    t, _ = dossier._remplir(PHRASE, {**BASE, "reference": "   "})
    assert "r\u00e9f\u00e9rence" not in t.lower()


def test_un_segment_facultatif_ne_mange_pas_le_reste_du_texte():
    """La regex est non-gourmande : deux segments ne se fusionnent pas."""
    from veille import dossier

    g = "A{{#x}} un {{/x}}B{{#y}} deux {{/y}}C"
    assert dossier._remplir(g, {"x": "1", "y": ""})[0] == "A un BC"
    assert dossier._remplir(g, {"x": "", "y": "1"})[0] == "AB deux C"


def test_les_marqueurs_hors_segment_restent_signales():
    from veille import dossier

    t, manquants = dossier._remplir(PHRASE, {"reference": "R-1"})
    assert manquants == ["titre", "source_lisible"]
    assert "[[titre - À COMPLÉTER]]" in t


# --------------------------------------------------------------------------
# La deduction de la reference — PROPOSER, jamais ecrire
#
# Mesure du 02/10/2026 : presque aucune annonce complete ne porte de
# reference explicite. Un premier motif trop large en trouvait de nombreuses —
# toutes fausses : « Refactoring », « reflects », « reference architectures ».
# --------------------------------------------------------------------------


@pytest.mark.parametrize("texte,attendu", [
    ("Poste a pourvoir, reference : WMS-2026-114, merci de la rappeler.", "WMS-2026-114"),
    ("R\u00e9f. n\u00b0 4815-TR dans votre courriel.", "4815-TR"),
    ("R\u00e9f\u00e9rence de l'offre : R2026/0042", "R2026/0042"),
    ("Job ID: 88213 - apply online", "88213"),
    ("Kennziffer 2026-114 bitte angeben", "2026-114"),
])
def test_une_reference_etiquetee_est_proposee(texte, attendu):
    from veille import dossier

    valeur, preuve = dossier.deduire_reference({"titre": "", "description": texte})
    assert valeur == attendu
    assert preuve, "la proposition doit montrer d'ou elle vient"


@pytest.mark.parametrize("texte", [
    "Nous recherchons un ingenieur refactoring de nos pipelines.",
    "a great workplace reflects the world around us",
    "reference architectures and cloud infrastructure",
    "Reviews et refactoring font partie du quotidien.",
    "Une offre sans aucune reference.",
])
def test_aucune_reference_nest_inventee(texte):
    """Les cinq cas qui produisaient de nombreux faux positifs sur sa vraie base."""
    from veille import dossier

    valeur, _ = dossier.deduire_reference({"titre": "", "description": texte})
    assert valeur == "", f"invente : {valeur}"


def test_lidentifiant_linkedin_nest_pas_propose_comme_reference():
    """L'annonce ne le nomme jamais « reference » : le proposer serait faux."""
    from veille import dossier

    valeur, _ = dossier.deduire_reference({
        "titre": "Ingenieur IVVQ", "description": "Un poste interessant.",
        "url": "https://linkedin.com/jobs/view/4000000001"})
    assert valeur == ""


def test_les_commentaires_ne_sont_pas_substitues():
    """Ses notes a lui restent lisibles : la notice qui ENUMERE les marqueurs
    devenait « Marqueurs remplis par la console : Exemple Logistik AG, Testeur
    logiciel... »."""
    from veille import dossier

    g = ("Objet : {{titre}}\n\n"
         "<!-- Marqueurs : {{employeur}}, {{titre}}, {{reference}}. -->")
    t, manquants = dossier._remplir(g, {"titre": "Testeur", "employeur": "Exemple Logistik AG"})
    assert "Objet : Testeur" in t
    assert "<!-- Marqueurs : {{employeur}}, {{titre}}, {{reference}}. -->" in t
    assert manquants == [], "un marqueur cite dans une note n'est pas un trou"


def test_un_marqueur_facultatif_cite_dans_une_note_nest_pas_reclame():
    """Sinon l'ecran reclame une reference pourtant facultative."""
    from veille import dossier

    g = ("Je postule{{#reference}} - ref {{reference}}{{/reference}}.\n\n"
         "<!-- {{reference}} vient du bloc Destinataire. -->")
    _, manquants = dossier._remplir(g, {"reference": ""})
    assert "reference" not in manquants


# --------------------------------------------------------------------------
# L'ALLEMAND — une annonce germanophone recevait une lettre francaise
#
# 02/10/2026. `detecter_langue` comptait des mots outils francais et anglais,
# et rendait « en if marqueurs_en > marqueurs_fr else fr ». Une annonce
# allemande n'a aucun des deux : egalite a zero, donc « fr », EN SILENCE.
#
# Mesure sur la base : les annonces allemandes etaient classees « fr » ou
# « en », aucune correcte. Celles classees « fr » recevaient `lettre_fr.md` ET
# `cv.fr.pdf`, sans le moindre avertissement.
#
# La cause fine : « des » figurait dans la liste francaise. C'est aussi le
# genitif allemand, et il est bien plus frequent en allemand qu'en francais
# dans une annonce. Un mot outil ne vaut que s'il n'appartient qu'a une langue.
# --------------------------------------------------------------------------

ANNONCE_DE = {
    "titre": "Senior Software Engineer (m/w/d)",
    "description": (
        "Wir suchen eine erfahrene Entwicklerin oder einen Entwickler für "
        "unser Team in Basel. Sie arbeiten mit modernen Technologien und "
        "sind für die Qualität der Software verantwortlich. Das Team ist "
        "international, und wir bieten ein attraktives Umfeld. Bei uns wird "
        "Eigenverantwortung grossgeschrieben; Deutschkenntnisse sind "
        "Voraussetzung, Englisch von Vorteil."),
    "lieu": "Basel",
}
ANNONCE_FR = {
    "titre": "Ingenieur recette",
    "description": ("Nous recherchons un ingenieur pour la recette des "
                    "logiciels logistiques. Vous travaillez dans une equipe "
                    "et avec les metiers, pour des projets de migration."),
    "lieu": "Mulhouse",
}
ANNONCE_EN = {
    "titre": "Quality Engineer",
    "description": ("We are looking for a quality engineer and you will work "
                    "with our teams on the systems that are critical for the "
                    "business. This is a role that matters."),
    "lieu": "Basel",
}


def test_une_annonce_allemande_est_reconnue_comme_allemande():
    from veille import dossier

    assert dossier.detecter_langue(ANNONCE_DE) == "de"


def test_le_francais_et_langlais_ne_regressent_pas():
    from veille import dossier

    assert dossier.detecter_langue(ANNONCE_FR) == "fr"
    assert dossier.detecter_langue(ANNONCE_EN) == "en"


def test_des_nest_plus_un_marqueur_francais():
    """C'est le mot precis qui poussait la plupart des annonces allemandes vers « fr »."""
    from veille import dossier

    assert " des " not in dossier.MOTS_OUTILS["fr"]


def test_aucun_mot_outil_nappartient_a_deux_langues():
    """Le garde-fou general derriere le cas « des »."""
    from veille import dossier

    vus = {}
    for langue, mots in dossier.MOTS_OUTILS.items():
        for m in mots:
            assert m not in vus, (
                f"« {m.strip()} » est a la fois {vus.get(m)} et {langue}")
            vus[m] = langue


def test_une_annonce_sans_texte_rend_une_langue_indeterminee():
    """Cas reel, une offre de sa base : la description n'est que le pied de page de
    l'agregateur. La console doit dire qu'elle ne sait pas."""
    from veille import dossier

    assert dossier.detecter_langue(
        {"titre": "Senior Software Engineer", "description": "<p>1</p>"}) == ""


def test_une_egalite_nest_pas_une_decision():
    from veille import dossier

    ambigu = {"titre": "", "description": "le the la and les you"}
    assert dossier.detecter_langue(ambigu) == ""


def test_un_seul_mot_outil_ne_suffit_pas():
    from veille import dossier

    assert dossier.detecter_langue({"titre": "", "description": "und"}) == ""


# --------------------------------------------------------------------------
# Refuser plutot que servir la mauvaise langue
# --------------------------------------------------------------------------


def test_aucune_lettre_nest_generee_pour_une_annonce_allemande(tmp_path, monkeypatch):
    from veille import dossier

    _kit_langues(tmp_path, monkeypatch,
                 lettre_famille_inventee_fr__md=LETTRE_FR,
                 lettre_en__md=LETTRE_EN)
    chemin, alerte = dossier._choisir_lettre({**ANNONCE_DE, "famille": "", "atouts": []})
    assert chemin is None, "mieux vaut rien qu'une lettre eliminatoire"
    assert "ALLEMAND" in alerte
    assert "eliminatoire" in alerte
    assert "a la main" in alerte, "l'avertissement doit dire quoi faire"


def test_aucune_lettre_nest_generee_quand_la_langue_est_indeterminee(tmp_path, monkeypatch):
    from veille import dossier

    _kit_langues(tmp_path, monkeypatch, lettre_fr__md=LETTRE_FR)
    chemin, alerte = dossier._choisir_lettre(
        {"titre": "x", "description": "<p>1</p>", "famille": "", "atouts": []})
    assert chemin is None
    assert "INDETERMINEE" in alerte
    assert "une chance sur trois" in alerte


def test_aucun_cv_etiquete_ne_part_sur_une_annonce_allemande():
    """Le CV francais partait avec les annonces mal classees."""
    from pathlib import Path as _P

    from veille import dossier

    for cv in ("cv.fr.pdf", "cv.ch.en.pdf"):
        assert not dossier._piece_convient(_P(cv), "de", "ch")
        assert not dossier._piece_convient(_P(cv), "", "ch")
    # L'annexe technique, sans etiquette de langue, reste jointe.
    assert dossier._piece_convient(_P("annexe-technique.pdf"), "de", "ch")


def test_lallemand_nest_pas_une_langue_servie():
    """L'allemand n'est pas servi tant qu'aucune piece allemande n'est
    deposee. Le jour ou il y en a une, c'est cette constante qui change, et le
    refus disparait."""
    from veille import dossier

    assert "de" not in dossier.LANGUES_SERVIES
    assert set(dossier.LANGUES_SERVIES) == {"fr", "en"}


def test_aucune_relance_nest_redigee_dans_une_langue_non_servie():
    from veille import relance

    r = relance.preparer({**ANNONCE_DE, "statut": "candidature_envoyee",
                          "date_candidature": "2026-09-01"})
    assert r.texte == ""
    assert any("allemand" in a for a in r.avertissements)


def test_une_annonce_anglaise_situee_en_france_na_aucun_cv():
    """TROU CONNU, fige ici pour qu'il ne se decouvre pas un soir d'envoi.

    Un kit de deux CV etiquetes `fr` et `ch.en` : une annonce redigee en
    anglais mais situee en France ne correspond a aucun des deux. Le CV
    francais est ecarte par la langue, le suisse par le pays. Le paquet
    d'envoi part alors sans CV, et l'avertissement « Aucun CV PDF retenu »
    le dit. Il manquerait un `cv.en.pdf`, ou une etiquette de pays sur le CV
    anglais — c'est une decision, pas un correctif evident.
    """
    from pathlib import Path as _P

    from veille import dossier

    assert not dossier._piece_convient(_P("cv.fr.pdf"), "en", "france")
    assert not dossier._piece_convient(_P("cv.ch.en.pdf"), "en", "france")


# --------------------------------------------------------------------------
# LE CV SANS PHOTO EST LE CV ANGLAIS PAR DEFAUT
#
# Sans etiquette reconnue, une variante du CV part EN PLUS du bon CV, parce
# qu'un nom sans etiquette vaut « piece universelle » : l'etiquette `manuel`
# la retire alors de tout envoi.
#
# Bien etiquete, le CV sans photo est au contraire le bon CV dans un cas
# precis : toute offre anglophone hors de Suisse. Un CV sans photo n'est
# jamais un faux pas ; un CV avec photo peut en etre un (politiques
# anti-discrimination, analyse automatisee). La photo n'est attendue qu'en
# Suisse et en Allemagne.
#
#   cv.fr.pdf       -> offres en francais
#   cv.en.pdf       -> offres en anglais, TOUS pays        (sans photo)
#   cv.ch.en.pdf    -> offres en anglais EN SUISSE          (avec photo)
#
# Les deux derniers conviennent a une offre suisse anglophone : le plus
# SPECIFIQUE gagne, donc celui avec photo. C'est le principe applique partout
# dans ce projet, et celui qui a corrige le choix de la lettre.
# --------------------------------------------------------------------------

from pathlib import Path as _Chemin

PIECES_CV = [_Chemin("cv.fr.pdf"), _Chemin("cv.en.pdf"), _Chemin("cv.ch.en.pdf"),
             _Chemin("annexe-technique.pdf")]


def _retenues(langue, pays):
    from veille import dossier

    return [p.name for p in dossier.pieces_retenues(PIECES_CV, langue, pays)]


def test_une_offre_anglaise_en_france_recoit_le_cv_sans_photo():
    """C'etait le trou : des offres partaient sans aucun CV."""
    assert _retenues("en", "france") == ["annexe-technique.pdf", "cv.en.pdf"]


def test_une_offre_anglaise_en_suisse_recoit_le_cv_avec_photo():
    """Les deux conviennent ; le plus specifique gagne."""
    assert _retenues("en", "ch") == ["annexe-technique.pdf", "cv.ch.en.pdf"]


def test_une_offre_anglaise_en_suisse_ne_recoit_PAS_deux_cv():
    """Le defaut corrige : deux CV dans la meme enveloppe."""
    cv = [n for n in _retenues("en", "ch") if n.startswith("cv")]
    assert len(cv) == 1, cv


def test_une_offre_anglaise_ailleurs_recoit_le_cv_sans_photo():
    for pays in ("allemagne", "autre", ""):
        assert "cv.en.pdf" in _retenues("en", pays), pays
        assert "cv.ch.en.pdf" not in _retenues("en", pays), pays


def test_une_offre_francaise_recoit_toujours_le_cv_francais():
    assert _retenues("fr", "france") == ["annexe-technique.pdf", "cv.fr.pdf"]


def test_une_offre_allemande_ne_recoit_aucun_cv():
    """Pas de piece allemande dans le kit : le refus tient."""
    assert [n for n in _retenues("de", "ch") if n.startswith("cv")] == []
    assert [n for n in _retenues("de", "allemagne") if n.startswith("cv")] == []


def test_lannexe_technique_part_toujours():
    for langue, pays in (("fr", "france"), ("en", "ch"), ("de", "allemagne")):
        assert "annexe-technique.pdf" in _retenues(langue, pays)


def test_le_plus_specifique_gagne_quel_que_soit_lordre_des_fichiers():
    """La regle ne doit pas dependre de l'ordre de lecture du dossier."""
    from veille import dossier

    a_lenvers = list(reversed(PIECES_CV))
    assert ([p.name for p in dossier.pieces_retenues(a_lenvers, "en", "ch")]
            == ["annexe-technique.pdf", "cv.ch.en.pdf"])


def test_letiquette_manuel_prime_toujours_sur_la_specificite():
    """Si une piece est marquee `manuel`, elle ne part pas, meme si elle est
    la plus specifique de sa famille."""
    from veille import dossier

    pieces = [_Chemin("cv.en.pdf"), _Chemin("cv.manuel.ch.en.pdf")]
    assert [p.name for p in dossier.pieces_retenues(pieces, "en", "ch")] == ["cv.en.pdf"]


def test_les_deux_cv_restent_telechargeables():
    """Le renversement ne doit retirer aucune piece du kit : il change
    laquelle part automatiquement, pas ce qui est disponible."""
    kit = _kit_reel()
    if kit is None:
        pytest.skip(SANS_KIT_REEL)
    presents = {f.name for f in kit.iterdir()}
    assert {"cv.fr.pdf", "cv.en.pdf", "cv.ch.en.pdf"} <= presents, sorted(presents)

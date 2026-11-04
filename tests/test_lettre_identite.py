"""L'identite des paragraphes — le point delicat de l'editeur.

Tout le reste en depend : l'historique, la provenance affichee a l'ecran, et
demain l'ancrage des annotations de la relecture. Ces tests verrouillent les
deux proprietes qui comptent :

  1. OUVRIR SANS TOUCHER NE CHANGE RIEN. Ni le fichier, ni les identifiants,
     ni les origines.
  2. L'ECHEC SE DEGRADE DU BON COTE. Un bloc qu'on ne reconnait pas devient
     `edouard`. On peut lui attribuer une phrase du gabarit ; on ne peut pas
     lui retirer une phrase qu'il a ecrite.

CHAQUE COMPTAGE PORTE SON TEMOIN. Un test qui compte des paragraphes sur une
lettre vide passe en annoncant zero, et ne dit rien du tout.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from veille import lettre as L

# --------------------------------------------------------------------------
# Une lettre realiste : quatre blocs, dont une charniere d'assemblage.
# --------------------------------------------------------------------------

ENTETE = "**Camille Exemple**"
APPEL = "Madame, Monsieur,"
CHARNIERE = "Votre annonce cite stock reconciliation, EDI et cross-docking."
CORPS = ("Je suis testeuse logiciel, avec un socle de développeuse. "
         "En recette mobile chez un distributeur d'énergie, je suis "
         "testeuse principale de quatre applications clientes.")
SIGNATURE = "Camille Exemple"

LETTRE = "\n\n".join([ENTETE, APPEL, CHARNIERE, CORPS, SIGNATURE]) + "\n"


def _ecrire(tmp_path: Path, texte: str, meta: dict | None = None) -> Path:
    (tmp_path / L.NOM_LETTRE).write_text(texte, encoding="utf-8")
    if meta is not None:
        (tmp_path / L.NOM_META).write_text(
            json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    return tmp_path


def _meta_initiale(texte: str, origines: list[str]) -> dict:
    blocs = L.decouper(texte)
    assert len(blocs) == len(origines), "TEMOIN : le fixture est incoherent"
    return {
        "schema": "lettre/1",
        "etat": "assemblee",
        "redigee_le": "",
        "filiation": {"gabarit_nom": "lettre_fr.md", "gabarit_empreinte": "abc",
                      "assemblage_paragraphe": CHARNIERE},
        "paragraphes": [
            {"id": f"p{i + 1:02d}", "origine": o,
             "empreinte": L.empreinte(c), "position": i,
             "modifie_le": "", "code_relecture": ""}
            for i, (o, (c, _s)) in enumerate(zip(origines, blocs))
        ],
    }


ORIGINES_DEPART = ["gabarit", "gabarit", "assemblage", "gabarit", "gabarit"]


@pytest.fixture
def dossier(tmp_path):
    return _ecrire(tmp_path, LETTRE, _meta_initiale(LETTRE, ORIGINES_DEPART))


# --------------------------------------------------------------------------
# 1. Le decoupage est reversible au caractere pres
# --------------------------------------------------------------------------


@pytest.mark.parametrize("texte", [
    LETTRE,
    "un seul bloc",
    "a\n\nb",
    "a\n\n\n\nb",
    "a\n   \nb",                      # separateur avec des espaces
    "\n\ndebut vide\n\nfin\n\n",      # separateurs aux deux bords
    "ligne\nsimple\nsans\nbloc",      # aucun saut double
    "accents : éèàçôûî ÄÖÜ ß œ",
])
def test_recoller_rend_le_texte_exact(texte):
    assert L.recoller(L.decouper(texte)) == texte


def test_le_decoupage_suit_celui_du_rendu():
    """Un paragraphe de l'editeur EST un bloc du PDF.

    Sans cet alignement, une annotation ancree sur un paragraphe ne designerait
    pas le meme texte dans l'editeur et dans le document imprime.
    """
    from veille import rendu

    attendus = [b.strip() for b in rendu._SEPARATEUR_BLOC.split(LETTRE) if b.strip()]
    obtenus = [c.strip() for c, _s in L.decouper(LETTRE) if c.strip()]
    assert obtenus == attendus
    assert len(obtenus) == 5, "TEMOIN : la lettre de test doit avoir 5 blocs"


def test_une_lettre_vide_rend_une_liste_vide():
    assert L.decouper("") == []
    # TEMOIN NEGATIF : une lettre non vide ne rend JAMAIS une liste vide.
    assert len(L.decouper(LETTRE)) == 5


# --------------------------------------------------------------------------
# 2. Ouvrir sans toucher ne change rien
# --------------------------------------------------------------------------


def test_ouvrir_sans_rien_changer_ne_change_rien(dossier):
    lu = L.lire(dossier)
    assert len(lu.paragraphes) == 5, "TEMOIN : 5 paragraphes attendus"
    assert [p.id for p in lu.paragraphes] == ["p01", "p02", "p03", "p04", "p05"]
    assert [p.origine for p in lu.paragraphes] == ORIGINES_DEPART
    assert lu.etat == "assemblee"
    assert lu.paragraphes_de_lui == []
    assert lu.texte == LETTRE


def test_la_lecture_nécrit_rien_sur_le_disque(dossier):
    avant = {f.name: f.read_bytes() for f in dossier.iterdir()}
    assert avant, "TEMOIN : le dossier de test n'est pas vide"
    L.lire(dossier)
    apres = {f.name: f.read_bytes() for f in dossier.iterdir()}
    assert apres == avant


def test_un_aller_retour_lecture_ecriture_est_stable(dossier):
    un = L.lire(dossier)
    L.ecrire(un)
    deux = L.lire(dossier)
    assert [p.id for p in deux.paragraphes] == [p.id for p in un.paragraphes]
    assert [p.origine for p in deux.paragraphes] == [p.origine for p in un.paragraphes]
    assert deux.texte == un.texte == LETTRE


# --------------------------------------------------------------------------
# 3. Il modifie un paragraphe
# --------------------------------------------------------------------------


def test_un_paragraphe_modifie_garde_son_id_et_devient_le_sien(dossier):
    modifie = LETTRE.replace(CORPS, CORPS + " J'ai automatisé les parcours de paiement.")
    assert modifie != LETTRE, "TEMOIN : la modification doit changer le texte"
    (dossier / L.NOM_LETTRE).write_text(modifie, encoding="utf-8")

    lu = L.lire(dossier)
    assert [p.id for p in lu.paragraphes] == ["p01", "p02", "p03", "p04", "p05"]
    assert lu.par_id("p04").origine == "edouard"
    # Les autres n'ont pas bouge : c'est la propriete qui compte.
    assert [p.origine for p in lu.paragraphes] == [
        "gabarit", "gabarit", "assemblage", "edouard", "gabarit"]
    assert lu.par_id("p04").modifie_le, "une modification doit etre datee"
    assert lu.etat == "redigee", "un paragraphe de lui fait une lettre redigee"


def test_modifier_un_accent_est_une_modification(dossier):
    """Une empreinte qui ignorerait les accents ne verrait pas qu'un accent a
    ete casse — or c'est un des defauts que la porte doit attraper."""
    casse = LETTRE.replace("développeuse", "developpeuse")
    assert casse != LETTRE
    (dossier / L.NOM_LETTRE).write_text(casse, encoding="utf-8")
    assert L.lire(dossier).par_id("p04").origine == "edouard"


def test_un_blanc_de_bord_nest_pas_une_modification(dossier):
    """Sinon chaque enregistrement ferait basculer toute la lettre en
    « ecrite par lui », et la provenance ne vaudrait plus rien."""
    avec_blancs = LETTRE.replace(CORPS, CORPS + "   ")
    assert avec_blancs != LETTRE
    (dossier / L.NOM_LETTRE).write_text(avec_blancs, encoding="utf-8")
    lu = L.lire(dossier)
    assert lu.par_id("p04").origine == "gabarit"
    assert lu.paragraphes_de_lui == []


# --------------------------------------------------------------------------
# 4. Il insere, supprime, deplace
# --------------------------------------------------------------------------


def test_une_insertion_ne_decale_pas_la_provenance(dossier):
    """LE PIEGE QUE CE MODULE EXISTE POUR EVITER. Avec un `id` fonde sur
    l'indice, inserer un bloc ferait croire que le paragraphe suivant est de
    lui, et celui d'apres aussi, jusqu'a la fin de la lettre."""
    nouveau = "Un paragraphe que j'ajoute moi-même."
    modifie = LETTRE.replace(CORPS, CORPS + "\n\n" + nouveau)
    (dossier / L.NOM_LETTRE).write_text(modifie, encoding="utf-8")

    lu = L.lire(dossier)
    assert len(lu.paragraphes) == 6, "TEMOIN : un bloc de plus"
    textes = [p.texte.strip() for p in lu.paragraphes]
    assert textes.index(nouveau) == 4
    # Les cinq blocs d'origine gardent id ET origine.
    assert lu.par_id("p01").origine == "gabarit"
    assert lu.par_id("p03").origine == "assemblage"
    assert lu.par_id("p04").origine == "gabarit"
    assert lu.par_id("p05").origine == "gabarit"
    assert lu.par_id("p05").texte.strip() == SIGNATURE
    # Le nouveau porte un id neuf et c'est le sien.
    neuf = [p for p in lu.paragraphes if p.texte.strip() == nouveau][0]
    assert neuf.id == "p06"
    assert neuf.origine == "edouard"
    assert len(lu.paragraphes_de_lui) == 1


def test_une_suppression_ne_decale_pas_la_provenance(dossier):
    modifie = LETTRE.replace(CHARNIERE + "\n\n", "")
    assert CHARNIERE not in modifie
    (dossier / L.NOM_LETTRE).write_text(modifie, encoding="utf-8")

    lu = L.lire(dossier)
    assert len(lu.paragraphes) == 4, "TEMOIN : un bloc de moins"
    assert [p.id for p in lu.paragraphes] == ["p01", "p02", "p04", "p05"]
    assert [p.origine for p in lu.paragraphes] == ["gabarit"] * 4
    assert lu.paragraphes_de_lui == []


def test_un_id_supprime_nest_jamais_reattribue(dossier):
    """Sinon l'historique et les annotations de la relecture pointeraient vers
    un paragraphe qui n'a rien a voir."""
    sans = LETTRE.replace(CHARNIERE + "\n\n", "")
    (dossier / L.NOM_LETTRE).write_text(sans, encoding="utf-8")
    L.ecrire(L.lire(dossier))                       # p03 disparait de la meta
    avec = sans.replace(CORPS, "Tout autre chose.\n\n" + CORPS)
    (dossier / L.NOM_LETTRE).write_text(avec, encoding="utf-8")

    lu = L.lire(dossier)
    neuf = [p for p in lu.paragraphes if p.texte.strip() == "Tout autre chose."][0]
    assert neuf.id != "p03", "p03 a existe : son identifiant est brule"
    assert neuf.origine == "edouard"


def test_deplacer_un_paragraphe_conserve_son_identite(dossier):
    """L'empreinte voyage avec le texte : c'est la passe 1 qui le garantit."""
    modifie = "\n\n".join([ENTETE, APPEL, CORPS, CHARNIERE, SIGNATURE]) + "\n"
    (dossier / L.NOM_LETTRE).write_text(modifie, encoding="utf-8")

    lu = L.lire(dossier)
    assert [p.id for p in lu.paragraphes] == ["p01", "p02", "p04", "p03", "p05"]
    assert lu.par_id("p03").origine == "assemblage"
    assert lu.par_id("p04").origine == "gabarit"
    assert lu.paragraphes_de_lui == [], "deplacer n'est pas reecrire"


def test_deux_paragraphes_identiques_sont_consommes_dans_lordre(dossier):
    texte = "\n\n".join([ENTETE, APPEL, APPEL, SIGNATURE]) + "\n"
    meta = _meta_initiale(texte, ["gabarit", "gabarit", "edouard", "gabarit"])
    _ecrire(dossier, texte, meta)
    lu = L.lire(dossier)
    assert len(lu.paragraphes) == 4, "TEMOIN"
    assert [p.id for p in lu.paragraphes] == ["p01", "p02", "p03", "p04"]
    assert [p.origine for p in lu.paragraphes] == [
        "gabarit", "gabarit", "edouard", "gabarit"]


# --------------------------------------------------------------------------
# 5. L'echec se degrade du bon cote
# --------------------------------------------------------------------------


def test_une_lettre_entierement_reecrite_est_entierement_de_lui(dossier):
    reecrite = "\n\n".join([
        "Un en-tête que j'ai refait.",
        "Une formule d'appel à moi.",
        "Un corps entièrement réécrit à la main.",
    ]) + "\n"
    (dossier / L.NOM_LETTRE).write_text(reecrite, encoding="utf-8")

    lu = L.lire(dossier)
    assert len(lu.paragraphes) == 3, "TEMOIN"
    assert all(p.origine == "edouard" for p in lu.paragraphes)
    assert not any(p.origine == "gabarit" for p in lu.paragraphes), (
        "aucun paragraphe reecrit ne doit etre attribue au gabarit")
    assert lu.etat == "redigee"
    assert lu.mots_de_lui > 0, "TEMOIN : le comptage de mots doit etre non nul"


def test_sans_meta_la_provenance_se_reconstruit_sans_mentir(tmp_path):
    """Les quatre dossiers deja generes n'ont pas de `lettre.meta.json`.

    On ne devine pas une provenance qu'on n'a pas enregistree : tout est
    `gabarit`, ce qui est VRAI d'une lettre jamais editee.
    """
    _ecrire(tmp_path, LETTRE)
    assert not (tmp_path / L.NOM_META).exists(), "TEMOIN : pas de meta"
    lu = L.lire(tmp_path)
    assert lu.meta_reconstruite is True
    assert len(lu.paragraphes) == 5, "TEMOIN"
    assert all(p.origine == "gabarit" for p in lu.paragraphes)
    assert lu.etat == "assemblee"


def test_une_meta_corrompue_ne_fait_pas_perdre_la_lettre(tmp_path):
    _ecrire(tmp_path, LETTRE)
    (tmp_path / L.NOM_META).write_text("{ ceci n'est pas du json", encoding="utf-8")
    with pytest.raises(Exception):
        L.lire(tmp_path)
    # Et surtout : la lettre est intacte sur le disque.
    assert (tmp_path / L.NOM_LETTRE).read_text(encoding="utf-8") == LETTRE


def test_une_origine_inconnue_dans_la_meta_devient_la_sienne(dossier):
    """Une valeur que personne ne lit ne doit pas faire n'importe quoi. Un
    `origine` hors de la liste close est traite comme « de lui » : c'est le
    cote prudent."""
    meta = json.loads((dossier / L.NOM_META).read_text(encoding="utf-8"))
    meta["paragraphes"][1]["origine"] = "machin"
    (dossier / L.NOM_META).write_text(json.dumps(meta), encoding="utf-8")
    assert L.lire(dossier).par_id("p02").origine == "edouard"


# --------------------------------------------------------------------------
# 6. Empreintes
# --------------------------------------------------------------------------


def test_un_fichier_absent_rend_une_empreinte_vide(tmp_path):
    assert L.empreinte_fichier(tmp_path / "pas-la.md") == ""
    present = tmp_path / "la.md"
    present.write_text("contenu", encoding="utf-8")
    # TEMOIN NEGATIF : un fichier present rend une empreinte non vide, et
    # differente de celle d'un absent. Sans ce temoin, « empreintes egales »
    # serait vrai de deux fichiers manquants.
    assert L.empreinte_fichier(present) != ""
    assert L.empreinte_fichier(present) != L.empreinte_fichier(tmp_path / "pas-la.md")


def test_deux_contenus_differents_ont_des_empreintes_differentes():
    assert L.empreinte("a") != L.empreinte("b")
    assert L.empreinte("eCommerce") != L.empreinte("ecommerce")
    assert L.empreinte("ingénieur") != L.empreinte("ingenieur")
    # Et la normalisation documentee : fins de ligne et blancs de bord.
    assert L.empreinte("a\r\nb") == L.empreinte("a\nb")
    assert L.empreinte("  a  ") == L.empreinte("a")


# --------------------------------------------------------------------------
# 7. Les invariants cables pour la relecture (E2)
# --------------------------------------------------------------------------


def test_jamais_une_seule_proposition():
    assert L.propositions_recevables([]) is True
    assert L.propositions_recevables(["une"]) is False
    assert L.propositions_recevables(["une", "deux"]) is True
    assert L.propositions_recevables(["une", "deux", "trois"]) is True
    assert L.propositions_recevables(["1", "2", "3", "4"]) is False


def test_le_plafond_dannotations_est_de_trois():
    assert L.MAX_ANNOTATIONS == 3


def test_les_origines_sont_une_liste_close_de_quatre():
    assert L.ORIGINES == ("gabarit", "assemblage", "edouard", "agent_accepte")
    assert set(L.ORIGINES_HUMAINES) <= set(L.ORIGINES)


# --------------------------------------------------------------------------
# 8. Les vraies lettres du kit passent le decoupage
# --------------------------------------------------------------------------


def test_les_lettres_reelles_survivent_a_un_aller_retour():
    """Temoin d'assiette : si le kit est absent, le test le DIT et se saute.
    Il ne passe pas en silence sur zero fichier."""
    from veille.config import CHEMIN_GABARITS, CHEMIN_KIT

    fichiers = []
    for dossier in (CHEMIN_KIT, CHEMIN_GABARITS):
        if dossier.exists():
            fichiers += [f for f in sorted(dossier.iterdir())
                         if f.suffix == ".md" and f.name.startswith("lettre")]
    if not fichiers:
        pytest.skip("aucune lettre sur cette machine : rien a verifier")
    assert len(fichiers) >= 1, "TEMOIN : au moins une lettre"
    for f in fichiers:
        texte = f.read_text(encoding="utf-8")
        blocs = L.decouper(texte)
        assert L.recoller(blocs) == texte, f"{f.name} ne survit pas a l'aller-retour"
        assert len(blocs) >= 2, f"{f.name} : une lettre a plus d'un bloc"

"""La porte de validation, rejouee sur le texte edite.

CHAQUE CONTROLE A SON TEMOIN NEGATIF — un cas qui le fait ECHOUER. C'est la
condition pour qu'il vaille quelque chose : six controles au vert sur un
dossier vide sont six controles qui ne valent rien, et une session a failli
rapporter sept zeros qui valaient zero parce que la liste etait vide.

On verifie donc, pour chaque controle : qu'il passe quand tout va bien, ET
qu'il echoue quand il doit echouer.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from veille import lettre as L
from veille import porte, preferences
from veille.config import ConfigurationInvalide, charger_criteres

# --------------------------------------------------------------------------
# Un dossier complet et valide : lettre, meta avec filiation, copie du gabarit
# --------------------------------------------------------------------------

GABARIT = """**Camille Exemple**

Madame, Monsieur,

{{titre}} chez {{employeur}}.

Je suis testeuse logiciel, avec un socle de développeuse. En recette mobile
chez un distributeur d'énergie, je suis testeuse principale de quatre
applications clientes et de leur portail web.

Préavis de trois mois, négociable. Basée à Altkirch, je suis disponible en
présentiel dans tout le Haut-Rhin.

Camille Exemple
"""

OFFRE = {
    "id": 1,
    "titre": "Senior WMS Test Engineer",
    "employeur": "Lagerhaus Exemple AG",
    "lieu": "Suisse",
    "description": (
        "We are currently offering an opportunity as Senior WMS Test Engineer "
        "at our location in Pratteln. The role covers stock reconciliation, "
        "the EDI landscape and cross-docking relevant warehouse systems."),
    "url": "https://www.jobs.ch/fr/offres-emplois/detail/1",
    "source": "mail:jobs_ch",
    "type_contrat": "",
    "salaire_min": None, "salaire_max": None, "salaire_devise": None,
    "famille": "famille_inventee",
    "zone": "",
    "score": 44.0,
    # Les contributions du scoring, telles que `assemblage` les relit : c'est
    # d'elles que sort la phrase « Votre annonce cite ... ».
    "explication": [
        {"libelle": "Recette des données et du décisionnel",
         "points": 24, "detail": '"stock reconciliation", "edi"'},
        {"libelle": "Logistique et transport",
         "points": 35, "detail": '"cross-docking" dans la description'},
    ],
    "contact_nom": "", "contact_civilite": "", "adresse_entreprise": "",
    "reference_annonce": "",
}


def _charniere(offre: dict) -> str:
    """La phrase que `assemblage` produit REELLEMENT pour cette offre.

    ON NE LA FIGE PAS A LA MAIN. Une charniere ecrite en dur dans le test
    serait comparee a une charniere calculee par le code : le controle
    `assemblage_perime` echouerait sur un dossier sain, et c'est exactement ce
    qui s'est passe au premier passage. Le fixture doit refleter le code, pas
    une idee du code.
    """
    from veille import assemblage

    return assemblage.assembler(offre, langue="fr").paragraphe.strip()


CHARNIERE = _charniere(OFFRE)
# TEMOIN DE FIXTURE. Si la charniere est vide, `assemblage_perime` rend « rien
# a perimer » et tous ses temoins negatifs deviennent creux : le test
# passerait en ne verifiant rien.
assert CHARNIERE, (
    "TEMOIN : l'offre de test doit produire une phrase d'assemblage, "
    "sinon le controle assemblage_perime n'est pas eprouve")

LETTRE = f"""**Camille Exemple**

Madame, Monsieur,

Senior WMS Test Engineer chez Lagerhaus Exemple AG.

{CHARNIERE}

Je suis testeuse logiciel, avec un socle de développeuse. En recette mobile
chez un distributeur d'énergie, je suis testeuse principale de quatre
applications clientes et de leur portail web.

Préavis de trois mois, négociable. Basée à Altkirch, je suis disponible en
présentiel dans tout le Haut-Rhin.

Camille Exemple
"""


def _monter(tmp_path: Path, texte: str = LETTRE, *, gabarit: str = GABARIT,
            filiation: dict | None = None, avec_meta: bool = True,
            meta_depuis: str | None = None) -> Path:
    """Monte un dossier. `meta_depuis` sert a simuler une EDITION : la meta
    decrit le texte d'avant, le `.md` porte le texte d'apres."""
    (tmp_path / L.NOM_LETTRE).write_text(texte, encoding="utf-8")
    if gabarit is not None:
        (tmp_path / L.NOM_GABARIT).write_text(gabarit, encoding="utf-8")
    if not avec_meta:
        return tmp_path
    fil = filiation if filiation is not None else {
        "gabarit_nom": "lettre_famille_inventee_fr.md",
        "gabarit_source": "kit",
        "gabarit_empreinte": L.empreinte_fichier(tmp_path / L.NOM_GABARIT),
        "langue_gabarit": "fr",
        "marqueurs_resolus": {
            "employeur": "Lagerhaus Exemple AG",
            "titre": "Senior WMS Test Engineer",
            "lieu": "Suisse",
            "contact": "", "contact_civilite": "", "adresse_entreprise": "",
            "reference": "",
        },
        "assemblage_paragraphe": CHARNIERE,
        "assemblage_termes": ["stock reconciliation", "EDI", "cross-docking"],
    }
    blocs = L.decouper(meta_depuis if meta_depuis is not None else texte)
    (tmp_path / L.NOM_META).write_text(json.dumps({
        "schema": "lettre/1",
        "etat": "assemblee",
        "redigee_le": "2026-10-10T21:48:00+02:00",
        "dernier_id": len(blocs),
        "filiation": fil,
        "paragraphes": [
            {"id": f"p{i + 1:02d}", "origine": "gabarit",
             "empreinte": L.empreinte(c), "position": i,
             "modifie_le": "", "code_relecture": ""}
            for i, (c, _s) in enumerate(blocs)
        ],
    }, ensure_ascii=False), encoding="utf-8")
    return tmp_path


def _code(v: porte.Verdict, code: str) -> porte.Controle:
    trouve = next((c for c in v.controles if c.code == code), None)
    assert trouve is not None, f"TEMOIN : le controle {code} doit etre rendu"
    return trouve


# --------------------------------------------------------------------------
# Le cas de reference : tout va bien
# --------------------------------------------------------------------------


def test_un_dossier_sain_est_envoyable(tmp_path):
    v = porte.verifier(_monter(tmp_path), OFFRE)
    en_defaut = [c.code for c in v.controles if c.bloquant and c.etat != porte.OK]
    assert en_defaut == [], f"controles en defaut : {en_defaut}"
    assert v.envoyable is True
    assert v.a_regler == 0
    # TEMOIN : la porte a bien rendu SEPT controles, pas un sous-ensemble.
    assert len(v.controles) == 7, [c.code for c in v.controles]


# --------------------------------------------------------------------------
# 0. Le temoin d'assiette
# --------------------------------------------------------------------------


def test_un_dossier_vide_ne_rend_pas_six_controles_au_vert(tmp_path):
    """LE TEST QUI JUSTIFIE LE TEMOIN D'ASSIETTE."""
    v = porte.verifier(tmp_path, OFFRE)
    assert v.envoyable is False
    assert len(v.controles) == 1, "un dossier vide ne rend QU'UN controle"
    assert v.controles[0].code == "assiette"
    assert v.controles[0].etat == porte.ECHEC
    assert not any(c.etat == porte.OK for c in v.controles)


def test_une_lettre_trop_courte_na_rien_a_controler(tmp_path):
    (tmp_path / L.NOM_LETTRE).write_text("Madame, Monsieur,\n", encoding="utf-8")
    v = porte.verifier(tmp_path, OFFRE)
    assert v.envoyable is False
    assert _code(v, "assiette").etat == porte.ECHEC
    assert "caractères" in _code(v, "assiette").constat


def test_lassiette_passe_sur_une_vraie_lettre(tmp_path):
    """TEMOIN NEGATIF du temoin : il ne doit pas echouer sur du vrai."""
    v = porte.verifier(_monter(tmp_path), OFFRE)
    a = _code(v, "assiette")
    assert a.etat == porte.OK
    assert "paragraphes" in a.constat


# --------------------------------------------------------------------------
# 1. Ce qu'il refuse d'affirmer
# --------------------------------------------------------------------------


def test_une_lettre_saine_passe_le_controle_des_affirmations(tmp_path):
    c = _code(porte.verifier(_monter(tmp_path), OFFRE), "affirmations_interdites")
    assert c.etat == porte.OK
    # TEMOIN : le controle doit dire sur COMBIEN de regles il a porte. Un `ok`
    # sur zero regle ne vaut rien.
    assert "règle" in c.constat
    assert not c.constat.startswith("0 règle")


# Les regles de l'exemple, par libelle. Les tests de la porte lisent l'exemple
# (`affirmations_refusees` de `exemple/criteres.yaml`), pas le code : le code n'en
# porte aucune.
_EXEMPLE = {r["libelle"]: r["motifs"]
            for r in charger_criteres().brut["affirmations_refusees"]}

# Le montant inventé du salaire de Camille. Le test ne le recopie pas, et il ne
# peut pas l'inventer, puisqu'un autre montant ne serait attrape par aucun motif :
# il le lit la ou il est.
_MONTANT = next(m for m in _EXEMPLE["Salaire actuel"] if m[:1].isdigit())

# (phrase, libelle de la regle, motif attendu dans le constat)
_CAS = [
    ("Je suis certifiée ISTQB Advanced depuis cette année.",
     "Niveau de certification ISTQB", "istqb advanced"),
    ("J'ai encadré une équipe de trois testeurs.",
     "Encadrement d'équipe", "j ai encadre une equipe"),
    ("I managed a team of four testers.", "Encadrement d'équipe", "managed a team"),
    ("Je parle allemand couramment.", "Allemand courant", "allemand couramment"),
    ("I am fluent in German and English.", "Allemand courant", "fluent in german"),
    (f"Mon salaire actuel est de {_MONTANT}.", "Salaire actuel", "mon salaire actuel est"),
    (f"Aujourd'hui, c'est {_MONTANT} par an.", "Salaire actuel", _MONTANT),
]


def test_les_cas_couvrent_chaque_regle_de_l_exemple():
    """TEMOIN DE FIXTURE : chaque regle de l'exemple a son temoin negatif, et chaque
    motif attendu est bien un motif de sa regle."""
    assert {libelle for _phrase, libelle, _motif in _CAS} == set(_EXEMPLE)
    for _phrase, libelle, motif in _CAS:
        assert motif in _EXEMPLE[libelle], (libelle, motif)


@pytest.mark.parametrize("phrase, libelle, attendu", _CAS)
def test_une_affirmation_refusee_bloque_lenvoi(tmp_path, phrase, libelle, attendu):
    """TEMOIN NEGATIF, pour chaque regle de l'exemple, en francais et en anglais."""
    texte = LETTRE.replace("Camille Exemple\n", phrase + "\n\nCamille Exemple\n")
    v = porte.verifier(_monter(tmp_path, texte), OFFRE)
    c = _code(v, "affirmations_interdites")
    assert c.etat == porte.ECHEC, f"« {phrase} » doit etre attrapee"
    assert c.bloquant is True
    assert attendu in c.constat
    assert libelle in c.constat
    assert c.paragraphes, "le controle doit nommer le paragraphe"
    assert v.envoyable is False


def test_le_controle_ne_se_declenche_pas_sur_un_mot_voisin(tmp_path):
    """Les limites de mots : « ISTQB » seul n'est pas une affirmation refusée, et la
    certification qu'elle détient vraiment passe. Sinon elle apprendrait a ignorer
    le controle."""
    texte = LETTRE.replace(
        "Camille Exemple\n",
        "Je suis certifiée ISTQB, niveau Foundation (CTFL).\n\nCamille Exemple\n")
    c = _code(porte.verifier(_monter(tmp_path, texte), OFFRE),
              "affirmations_interdites")
    assert c.etat == porte.OK, c.constat


def test_le_controle_dit_quil_ne_voit_pas_les_equivalents(tmp_path):
    """Il ne doit pas pretendre couvrir ce qu'il ne couvre pas : les
    formulations equivalentes sont le travail de la relecture (E2)."""
    c = _code(porte.verifier(_monter(tmp_path), OFFRE), "affirmations_interdites")
    assert "équivalentes" in c.constat


def test_sans_aucune_regle_le_controle_est_indisponible_jamais_ok(monkeypatch, tmp_path):
    """UNE LISTE VIDE N'EST PAS UNE AUTORISATION. C'est le defaut qui a produit
    de nombreuses offres dans le mauvais pays : confondre « je ne sais pas » et « tout
    va bien »."""
    monkeypatch.setattr(preferences, "affirmations_refusees",
                        lambda: ([], "repli"))
    v = porte.verifier(_monter(tmp_path), OFFRE)
    c = _code(v, "affirmations_interdites")
    assert c.etat == porte.INDISPONIBLE
    assert c.etat != porte.OK
    assert v.envoyable is False, "un controle bloquant indisponible bloque"


def test_le_magasin_de_preferences_nest_pas_declare_disponible():
    """Le contrat du magasin n'est pas arrete : la veille ne doit PAS pretendre
    le lire, et surtout ne pas en creer un deuxieme."""
    assert preferences.disponible().possible is False
    assert "contrat" in preferences.disponible().raison
    # Et le port ne rend rien pour un domaine connu, sans lever.
    assert preferences.lire(preferences.DOMAINE_STYLE) == []
    # Un domaine inconnu, en revanche, ECHOUE : une valeur que personne ne lit
    # ne doit pas faire semblant de marcher.
    with pytest.raises(ValueError):
        preferences.lire("machin")


def test_le_repli_porte_sa_provenance():
    regles, origine = preferences.affirmations_refusees()
    assert origine == "repli"
    assert len(regles) == len(_EXEMPLE) >= 2, "TEMOIN : les regles de l'exemple"
    for r in regles:
        assert r.provenance, "une regle sans provenance est incontournable"
        assert r.libelle
        assert r.motifs


# --------------------------------------------------------------------------
# Les regles vivent dans la configuration, jamais dans le code
# --------------------------------------------------------------------------


def _poser_criteres(monkeypatch, request, tmp_path, modifier):
    """Des criteres derives de l'exemple, dans un sous-dossier : `tmp_path` porte
    deja le dossier de candidature que monte `_monter`."""
    from tests.aide_criteres import poser_criteres

    dossier = tmp_path / "criteres"
    dossier.mkdir()
    return poser_criteres(monkeypatch, request, dossier, modifier)


def test_les_affirmations_refusees_viennent_de_la_configuration(monkeypatch, request,
                                                                tmp_path):
    """`affirmations_refusees` de `criteres.yaml`, lue telle quelle. L'origine reste
    « repli » : le magasin n'est pas branche, et la configuration n'en est pas un."""
    regle = {"libelle": "Règle inventée", "valeur": "Ne jamais l'écrire.",
             "provenance": "test", "motifs": ["zorglub certifiee"]}
    _poser_criteres(monkeypatch, request, tmp_path,
                    lambda brut: brut.update(affirmations_refusees=[regle]))

    regles, origine = preferences.affirmations_refusees()
    assert origine == "repli"
    assert [(r.domaine, r.libelle, r.valeur, r.provenance, r.motifs) for r in regles] == [
        (preferences.DOMAINE_AFFIRMATIONS, "Règle inventée", "Ne jamais l'écrire.",
         "test", ["zorglub certifiee"])]

    texte = LETTRE.replace("Camille Exemple\n",
                           "Je suis zorglub certifiée.\n\nCamille Exemple\n")
    c = _code(porte.verifier(_monter(tmp_path, texte), OFFRE), "affirmations_interdites")
    assert c.etat == porte.ECHEC
    assert "zorglub certifiee" in c.constat
    assert "Règle inventée" in c.constat


def test_sans_affirmations_dans_la_configuration_la_liste_est_vide(monkeypatch, request,
                                                                   tmp_path):
    """Cle absente : aucune regle. Le controle se declare alors indisponible, jamais
    `ok` — aucune regle de repli ne vit plus dans le code."""
    _poser_criteres(monkeypatch, request, tmp_path,
                    lambda brut: brut.pop("affirmations_refusees", None))

    assert preferences.affirmations_refusees() == ([], "repli")
    c = _code(porte.verifier(_monter(tmp_path), OFFRE), "affirmations_interdites")
    assert c.etat == porte.INDISPONIBLE


_REGLE_VALIDE = {"libelle": "Valide", "valeur": "v", "provenance": "p", "motifs": ["zorglub"]}


@pytest.mark.parametrize("valeur", [
    "une chaine",
    {"libelle": "une table au lieu d'une liste"},
    ["pas une table"],
    [{"libelle": "sans motifs"}],
    [{"libelle": "motifs en chaine", "motifs": "zorglub"}],
    [{"libelle": "un motif nombre", "motifs": ["zorglub", 3]}],
    [_REGLE_VALIDE, {"libelle": "la seconde est mal formee", "motifs": "zorglub"}],
])
def test_des_affirmations_mal_formees_ne_passent_pas_pour_des_regles(valeur, monkeypatch,
                                                                    request, tmp_path):
    """Une entree mal formee rend la liste entiere inutilisable : verifier une partie
    des regles en disant `ok` serait un vert sans verification (invariant 3). Le
    controle se declare indisponible, et `veille config verifier` nomme l'entree."""
    _poser_criteres(monkeypatch, request, tmp_path,
                    lambda brut: brut.update(affirmations_refusees=valeur))

    assert preferences.affirmations_refusees() == ([], "repli")
    c = _code(porte.verifier(_monter(tmp_path), OFFRE), "affirmations_interdites")
    assert c.etat == porte.INDISPONIBLE


@pytest.mark.parametrize("contenu, levee", [
    ("version: 1\nfamilles:\n  zorglub: [non termine\n", yaml.YAMLError),
    ("familles: {}\n", ConfigurationInvalide),
], ids=["yaml_tronque", "version_absente"])
def test_un_fichier_de_criteres_illisible_ne_fait_pas_tomber_la_porte(contenu, levee,
                                                                     monkeypatch, request,
                                                                     tmp_path):
    """Le controle des affirmations n'a pas pu tourner : il se declare indisponible
    (invariant 3), et les autres controles de la porte tournent. Ailleurs, le
    chargement leve toujours."""
    from veille import config

    chemin = tmp_path / "criteres" / "criteres.yaml"
    chemin.parent.mkdir()
    chemin.write_text(contenu, encoding="utf-8")
    monkeypatch.setattr(config, "CHEMIN_CRITERES", chemin)
    config.recharger()
    request.addfinalizer(config.recharger)

    with pytest.raises(levee):
        config.charger_criteres()
    assert preferences.affirmations_refusees() == ([], "repli")
    v = porte.verifier(_monter(tmp_path), OFFRE)
    assert len(v.controles) == 7, [c.code for c in v.controles]
    assert _code(v, "affirmations_interdites").etat == porte.INDISPONIBLE
    assert _code(v, "filiation_gabarit").etat == porte.OK
    assert _code(v, "marqueurs_perimes").etat == porte.OK
    assert v.envoyable is False


# --- Le detecteur des regles ecrites en dur --------------------------------
#
# Il garde le principe, pas une forme : une `Preference` ne se construit qu'a
# partir de ce qui a ete LU (un appel, une variable locale). Du texte ecrit dans
# le code, sous n'importe quelle forme, est une regle en dur.

# Les champs de `Preference`, dans l'ordre de ses arguments positionnels.
_CHAMPS_DE_PREFERENCE = ("domaine", "valeur", "provenance", "revue_le", "motifs", "libelle")
# Les cles d'une regle d'affirmation, ecrite comme une table.
_CLES_DE_REGLE = {"libelle", "valeur", "provenance", "motifs"}
# Les conversions natives : elles transforment, elles ne lisent rien.
_CONVERSIONS = {"list", "tuple", "set", "frozenset", "sorted", "str", "dict"}


def _texte_en_dur(noeud, constantes: set[str]) -> bool:
    """Le noeud porte-t-il du texte ecrit dans le code ? Un appel, un attribut, un
    indice ou une variable locale portent ce qui a ete lu : ils n'en portent pas."""
    import ast

    if isinstance(noeud, ast.Constant):
        return isinstance(noeud.value, str) and bool(noeud.value.strip())
    if isinstance(noeud, ast.Name):
        return noeud.id in constantes
    if isinstance(noeud, ast.JoinedStr):
        return any(_texte_en_dur(v.value if isinstance(v, ast.FormattedValue) else v,
                                 constantes) for v in noeud.values)
    if isinstance(noeud, (ast.List, ast.Tuple, ast.Set)):
        return any(_texte_en_dur(e, constantes) for e in noeud.elts)
    if isinstance(noeud, ast.Dict):
        return any(_texte_en_dur(v, constantes) for v in noeud.values)
    if isinstance(noeud, ast.BinOp):
        return _texte_en_dur(noeud.left, constantes) or _texte_en_dur(noeud.right, constantes)
    if isinstance(noeud, (ast.Starred, ast.Subscript)):
        # `*["a"]`, `CONSTANTE[0]` : ce qui est dedans, ou ce qui est indexe.
        return _texte_en_dur(noeud.value, constantes)
    if isinstance(noeud, ast.Call) and getattr(noeud.func, "id", None) in _CONVERSIONS:
        # `list(("a",))`, `str(CONSTANTE)` : une conversion ne lit rien.
        return (any(_texte_en_dur(a, constantes) for a in noeud.args)
                or any(_texte_en_dur(k.value, constantes) for k in noeud.keywords))
    return False


def _constantes_du_module(arbre) -> set[str]:
    """Les noms que le module lie a du texte ecrit en dur, chaines comprises."""
    import ast

    constantes: set[str] = set()
    for _ in range(3):
        for n in arbre.body:
            cibles = (n.targets if isinstance(n, ast.Assign)
                      else [n.target] if isinstance(n, ast.AnnAssign) and n.value else [])
            for cible in cibles:
                if isinstance(cible, ast.Name) and _texte_en_dur(n.value, constantes):
                    constantes.add(cible.id)
    return constantes


def _est_preference(noeud) -> bool:
    import ast

    return isinstance(noeud, ast.Call) and (
        getattr(noeud.func, "id", None) or getattr(noeud.func, "attr", None)) == "Preference"


def _preferences_en_dur(source: str) -> list[str]:
    """Ce qui, dans `source`, construit une regle a partir de texte ecrit en dur.

    Le domaine (premier argument) n'est pas examine : il dit ou ranger la
    preference, pas ce qu'elle interdit, et c'est une constante du module."""
    import ast

    arbre = ast.parse(source)
    constantes = _constantes_du_module(arbre)
    trouves: list[str] = []
    for n in ast.walk(arbre):
        if not _est_preference(n):
            continue
        for rang, arg in enumerate(n.args):
            champ = _CHAMPS_DE_PREFERENCE[rang] if rang < len(_CHAMPS_DE_PREFERENCE) else "?"
            if (isinstance(arg, ast.Starred) or champ != "domaine") and \
                    _texte_en_dur(arg, constantes):
                trouves.append(f"{n.lineno} : argument positionnel {rang} ({champ})")
        for kw in n.keywords:
            if kw.arg == "domaine":
                continue
            valeur = kw.value
            if kw.arg is None and isinstance(valeur, ast.Dict):
                valeur = ast.Dict(
                    keys=[k for k in valeur.keys
                          if not (isinstance(k, ast.Constant) and k.value == "domaine")],
                    values=[v for k, v in zip(valeur.keys, valeur.values)
                            if not (isinstance(k, ast.Constant) and k.value == "domaine")])
            if _texte_en_dur(valeur, constantes):
                trouves.append(f"{n.lineno} : {kw.arg or '**'}")
    # Une table de regles au niveau du module, de la forme de l'ancien repli : des
    # `Preference`, ou des tables qui en ont les cles.
    for n in arbre.body:
        valeur = n.value if isinstance(n, (ast.Assign, ast.AnnAssign)) else None
        if valeur is None:
            continue
        for sous in ast.walk(valeur):
            if _est_preference(sous):
                trouves.append(f"{n.lineno} : table de Preference au niveau du module")
                break
            cles = ({k.value for k in sous.keys if isinstance(k, ast.Constant)}
                    if isinstance(sous, ast.Dict)
                    else {k.arg for k in sous.keywords}
                    if isinstance(sous, ast.Call) and getattr(sous.func, "id", None) == "dict"
                    else set())
            if len(_CLES_DE_REGLE & cles) >= 2:
                trouves.append(f"{n.lineno} : table de regles au niveau du module")
                break
    return trouves


_D = 'D = "affirmations_refusees"\n'


@pytest.mark.parametrize("source", [
    # positionnel
    _D + 'def f():\n    return Preference(D, "Ne jamais l\'écrire.", "p", "", ["z"], "Règle")\n',
    # nomme, chaine
    _D + 'def f():\n    return Preference(domaine=D, libelle="Règle")\n',
    # nomme, liste
    _D + 'def f():\n    return Preference(domaine=D, motifs=["zorglub"])\n',
    # **dict ecrit dans l'appel
    _D + 'def f():\n    return Preference(**{"domaine": D, "libelle": "Règle"})\n',
    # une constante du module
    _D + 'LIBELLE = "Règle"\ndef f():\n    return Preference(domaine=D, libelle=LIBELLE)\n',
    # **une table du module
    _D + 'R = {"libelle": "Règle"}\ndef f():\n    return Preference(domaine=D, **R)\n',
    # f-chaine
    _D + 'def f(n):\n    return Preference(domaine=D, libelle=f"Règle {n}")\n',
    # concatenation
    _D + 'def f(x):\n    return Preference(domaine=D, valeur=x + " jamais")\n',
    # *liste
    _D + 'def f():\n    return Preference(D, *["v", "p"])\n',
    # constante du module, construite en deux temps
    _D + 'A = "Règle"\nB = (A,)\ndef f():\n    return Preference(domaine=D, motifs=list(B), libelle=B[0])\n',
    # table de Preference au niveau du module, meme calculee
    _D + 'REGLES = (Preference(domaine=D, libelle=lire()),)\n',
    # table de regles en tables, au niveau du module
    'REGLES = [{"libelle": "Règle", "motifs": ["z"]}]\n',
    # table de regles en appels a dict, au niveau du module
    'REGLES = [dict(libelle="Règle", motifs=["z"])]\n',
], ids=["positionnel", "nomme", "liste", "dict", "constante", "dict_du_module", "f_chaine",
        "concatenation", "etoile", "constante_composee", "table_de_preference",
        "table_de_regles", "table_de_regles_dict"])
def test_le_detecteur_attrape_chaque_forme_de_regle_en_dur(source):
    """TEMOIN NEGATIF du detecteur : chaque forme de contournement est attrapee."""
    assert _preferences_en_dur(source), source


def test_le_detecteur_laisse_passer_une_regle_lue():
    """TEMOIN POSITIF : la forme du lecteur de la configuration."""
    source = (_D + "def f(brut):\n"
              "    return [Preference(domaine=D, libelle=r.get('libelle', ''),\n"
              "                       valeur=r.get('valeur', ''), motifs=list(r['motifs']))\n"
              "            for r in brut['affirmations_refusees']]\n")
    assert _preferences_en_dur(source) == []


def test_aucune_regle_d_affirmation_n_est_ecrite_dans_le_code():
    """Une affirmation refusee dit un fait de la vie d'une personne : elle vit dans sa
    configuration. Aucun module de `src/` ne garde de repli, ni ne construit une
    `Preference` a partir de texte ecrit en dur, sous aucune forme (voir les temoins
    du detecteur ci-dessus)."""
    from veille import config

    assert not hasattr(preferences, "REPLI_AFFIRMATIONS")
    en_dur = []
    for fichier in sorted((config.RACINE / "src" / "veille").rglob("*.py")):
        en_dur += [f"{fichier.name}:{t}"
                   for t in _preferences_en_dur(fichier.read_text(encoding="utf-8"))]
    assert en_dur == [], en_dur


# --------------------------------------------------------------------------
# 2. L'empreinte du gabarit
# --------------------------------------------------------------------------


def test_un_gabarit_inchange_passe(tmp_path):
    c = _code(porte.verifier(_monter(tmp_path), OFFRE), "filiation_gabarit")
    assert c.etat == porte.OK
    assert "inchangé" in c.constat


def test_un_gabarit_corrige_depuis_bloque_lenvoi(tmp_path):
    """TEMOIN NEGATIF. C'est l'incident de la lettre corrigee cote kit qui
    partait malgre tout, transpose a une lettre figee."""
    rep = _monter(tmp_path)
    (rep / L.NOM_GABARIT).write_text(
        GABARIT.replace("Préavis de trois mois", "Préavis de trois mois (art. 11)"),
        encoding="utf-8")
    v = porte.verifier(rep, OFFRE)
    c = _code(v, "filiation_gabarit")
    assert c.etat == porte.ECHEC
    assert c.bloquant is True
    assert "corrigé depuis" in c.constat
    assert "J'assume" in c.quoi_faire
    assert v.envoyable is False


def test_une_copie_de_gabarit_absente_est_indisponible_pas_ok(tmp_path):
    rep = _monter(tmp_path)
    (rep / L.NOM_GABARIT).unlink()
    c = _code(porte.verifier(rep, OFFRE), "filiation_gabarit")
    assert c.etat == porte.INDISPONIBLE
    assert c.etat != porte.OK


def test_sans_filiation_le_controle_le_dit(tmp_path):
    """Les quatre dossiers deja generes sont dans ce cas. Ne pas savoir n'est
    pas « tout va bien »."""
    rep = _monter(tmp_path, gabarit=None, avec_meta=False)
    v = porte.verifier(rep, OFFRE)
    c = _code(v, "filiation_gabarit")
    assert c.etat == porte.INDISPONIBLE
    assert "avant l'éditeur" in c.constat
    assert v.envoyable is False


# --------------------------------------------------------------------------
# 3. Les marqueurs perimes
# --------------------------------------------------------------------------


def test_une_offre_inchangee_passe(tmp_path):
    c = _code(porte.verifier(_monter(tmp_path), OFFRE), "marqueurs_perimes")
    assert c.etat == porte.OK


def test_un_employeur_corrige_depuis_bloque_lenvoi(tmp_path):
    """TEMOIN NEGATIF. Les offres aux champs intervertis vont produire
    exactement ce cas quand la collecte sera corrigee."""
    offre = dict(OFFRE, employeur="Lagerhaus Exemple AG, Pratteln")
    v = porte.verifier(_monter(tmp_path), offre)
    c = _code(v, "marqueurs_perimes")
    assert c.etat == porte.ECHEC
    assert "employeur" in c.constat
    assert "Pratteln" in c.constat
    assert "Ne régénère pas" in c.quoi_faire
    assert v.envoyable is False


def test_un_rescorer_ne_met_aucun_dossier_en_alerte(tmp_path):
    """LE TEST QUI COMPTE. `POST /api/rescorer` recalcule toutes les offres :
    si le score ou la famille declenchaient une alerte, TOUS ses dossiers
    passeraient au rouge d'un coup."""
    offre = dict(OFFRE, score=99.0, famille="autre_famille_inventee", zone="zone_inventee",
                 rejete_auto=1, motif_rejet_auto="peu importe")
    v = porte.verifier(_monter(tmp_path), offre)
    assert _code(v, "marqueurs_perimes").etat == porte.OK
    assert v.envoyable is True


def test_sans_marqueurs_figes_le_controle_est_indisponible(tmp_path):
    rep = _monter(tmp_path, filiation={
        "gabarit_nom": "x.md", "gabarit_empreinte": "",
        "marqueurs_resolus": {}, "assemblage_paragraphe": ""})
    c = _code(porte.verifier(rep, OFFRE), "marqueurs_perimes")
    assert c.etat == porte.INDISPONIBLE


# --------------------------------------------------------------------------
# 4. L'assemblage perime
# --------------------------------------------------------------------------


def test_une_charniere_reecrite_nest_pas_une_peremption(tmp_path):
    """S'il a reecrit la phrase, c'est sa decision. Le programme n'a pas a
    reclamer."""
    texte = LETTRE.replace(CHARNIERE, "Votre annonce décrit un contexte WMS.")
    c = _code(porte.verifier(_monter(tmp_path, texte), OFFRE), "assemblage_perime")
    assert c.etat == porte.OK
    assert "ta décision" in c.constat


def test_sans_charniere_il_ny_a_rien_a_perimer(tmp_path):
    rep = _monter(tmp_path, filiation={
        "gabarit_nom": "x.md",
        "gabarit_empreinte": L.empreinte_fichier(tmp_path / L.NOM_GABARIT),
        "marqueurs_resolus": {"employeur": "Lagerhaus Exemple AG",
                              "titre": "Senior WMS Test Engineer",
                              "lieu": "Suisse"},
        "assemblage_paragraphe": ""})
    c = _code(porte.verifier(rep, OFFRE), "assemblage_perime")
    assert c.etat == porte.OK


def test_une_charniere_qui_cite_ce_que_le_scoring_ne_releve_plus_bloque(tmp_path):
    """TEMOIN NEGATIF. C'est un cas vecu : la lettre cite un sigle que le
    scoring ne releve plus."""
    # L'offre ne porte aucune explication : `assembler` ne rend donc aucune
    # charniere, alors que la lettre en contient une.
    v = porte.verifier(_monter(tmp_path), dict(OFFRE, explication=[]))
    c = _code(v, "assemblage_perime")
    assert c.etat == porte.ECHEC
    assert CHARNIERE in c.constat
    assert c.paragraphes, "le paragraphe doit etre nomme"
    assert v.envoyable is False


# --------------------------------------------------------------------------
# 5. La structure — l'amputation silencieuse
# --------------------------------------------------------------------------


def test_une_lettre_entiere_passe(tmp_path):
    c = _code(porte.verifier(_monter(tmp_path), OFFRE), "structure_lettre")
    assert c.etat == porte.OK
    assert "Formule d'appel présente" in c.constat


def test_un_paragraphe_qui_se_declare_interne_ampute_la_lettre(tmp_path):
    """TEMOIN NEGATIF. `rendu._en_html` fait `break` sur `bloc_a_jeter`, lui ET
    tout ce qui suit : la lettre perd sa signature, en silence."""
    texte = LETTRE.replace(
        CHARNIERE,
        "Vous demandez de ne pas envoyer de photo, ce que je respecte.")
    v = porte.verifier(_monter(tmp_path, texte), OFFRE)
    c = _code(v, "structure_lettre")
    assert c.etat == porte.ECHEC
    assert "qu'une partie de la lettre" in c.constat
    assert v.envoyable is False


def test_une_lettre_sans_formule_dappel_est_refusee(tmp_path):
    texte = LETTRE.replace("Madame, Monsieur,\n\n", "")
    v = porte.verifier(_monter(tmp_path, texte), OFFRE)
    c = _code(v, "structure_lettre")
    assert c.etat == porte.ECHEC
    assert "formule d'appel" in c.constat


# --------------------------------------------------------------------------
# 6. La provenance — avertissant, PAS bloquant
# --------------------------------------------------------------------------


def test_la_provenance_nest_pas_bloquante(tmp_path):
    """Une incoherence de comptabilite interne n'atteint jamais ce que le
    recruteur recoit. Bloquer l'envoi pour ca transformerait un defaut de
    confort en dossier qui ne part pas."""
    rep = _monter(tmp_path)
    meta = json.loads((rep / L.NOM_META).read_text(encoding="utf-8"))
    for p in meta["paragraphes"]:
        p["id"] = "p01"                       # doublons partout
    (rep / L.NOM_META).write_text(json.dumps(meta), encoding="utf-8")

    v = porte.verifier(rep, OFFRE)
    c = _code(v, "provenance_coherente")
    assert c.bloquant is False
    assert v.envoyable is True, "la provenance ne doit jamais bloquer l'envoi"


def test_la_provenance_compte_ce_quil_a_ecrit(tmp_path):
    """C'est ce comptage qui alimente l'avertissement chiffre de « Repartir du
    gabarit ». Un avertissement qui se trompe est pire qu'une absence."""
    texte = LETTRE.replace(
        "présentiel dans tout le Haut-Rhin.",
        "présentiel dans tout le Haut-Rhin, et j'ajoute cette phrase moi-même.")
    assert texte != LETTRE, "TEMOIN : la modification doit porter"
    # La meta decrit le texte D'AVANT : c'est ce qui fait de ce cas une
    # edition, et non un dossier genere tel quel.
    v = porte.verifier(_monter(tmp_path, texte, meta_depuis=LETTRE), OFFRE)
    c = _code(v, "provenance_coherente")
    assert c.etat == porte.OK
    assert "1 paragraphe(s) de toi" in c.constat


def test_un_dossier_sans_meta_signale_une_provenance_reconstruite(tmp_path):
    rep = _monter(tmp_path, avec_meta=False)
    c = _code(porte.verifier(rep, OFFRE), "provenance_coherente")
    assert c.etat == porte.INDISPONIBLE
    assert c.bloquant is False


# --------------------------------------------------------------------------
# Le verdict global
# --------------------------------------------------------------------------


def test_un_seul_controle_bloquant_en_defaut_suffit_a_refuser(tmp_path):
    rep = _monter(tmp_path)
    (rep / L.NOM_GABARIT).write_text(GABARIT + "\nune ligne de plus\n",
                                     encoding="utf-8")
    v = porte.verifier(rep, OFFRE)
    assert v.envoyable is False
    assert v.a_regler == 1
    assert [c.code for c in v.echecs] == ["filiation_gabarit"]
    # Et les autres restent au vert : un echec n'en entraine pas d'autres.
    assert _code(v, "affirmations_interdites").etat == porte.OK
    assert _code(v, "structure_lettre").etat == porte.OK


def test_la_porte_necrit_rien(tmp_path):
    rep = _monter(tmp_path)
    avant = {f.name: f.read_bytes() for f in rep.iterdir()}
    assert len(avant) == 3, "TEMOIN : lettre, meta, gabarit"
    porte.verifier(rep, OFFRE)
    porte.verifier(rep, OFFRE)
    assert {f.name: f.read_bytes() for f in rep.iterdir()} == avant


def test_le_verdict_est_serialisable(tmp_path):
    d = porte.verifier(_monter(tmp_path), OFFRE).as_dict()
    assert json.loads(json.dumps(d, ensure_ascii=False))["envoyable"] is True
    assert len(d["controles"]) == 7
    for c in d["controles"]:
        assert set(c) == {"code", "etat", "bloquant", "constat", "quoi_faire",
                          "paragraphes"}

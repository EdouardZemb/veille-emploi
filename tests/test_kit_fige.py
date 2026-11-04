"""Le kit servi par la console est-il celui qu'on a validé ?

CE TEST ÉCHOUE. Il ne journalise pas, il ne prévient pas : il casse la suite.

Ce qui l'a rendu nécessaire : des lettres servies par la console divergeaient
de leurs sources. L'une portait une affirmation corrigée côté kit, et elle
partait malgré tout. Deux arborescences parallèles, aucune synchronisation, aucune alarme. Un avertissement dans un journal n'aurait rien changé : on a établi
deux fois dans la même journée que la prose ne tient pas.

La référence est FIGÉE dans `empreintes-kit.json`, dans le dossier de configuration
(`VEILLE_CONFIG`) — pas recalculée depuis le kit. Un contrôle qui relit le disque
qu'il surveille mesure sa propre copie et passe toujours.

Depuis le lot V1, la suite ne voit plus le kit réel : `conftest.py` pose `VEILLE_KIT`
sur les gabarits de l'exemple, et ces tests se sautent plutôt que de mesurer l'exemple
comme s'il était le kit. Le kit se vérifie donc par `veille empreintes-kit`, lancée à
chaque mise à jour du serveur (`CLAUDE.md`).
"""

from __future__ import annotations

import pytest

from veille import config, empreintes


def _kit():
    """Le kit réel, ou None. Absent n'est PAS synonyme de divergent.

    La suite pose `VEILLE_KIT` sur les gabarits de l'exemple (`conftest.py`) : ce
    ne sont pas les pièces d'un kit réel, et les mesurer ferait passer l'exemple
    pour le kit qu'on surveille. On se saute, en le disant.
    """
    dossier = empreintes.dossier_kit()
    if dossier is None:
        return None, "VEILLE_KIT n'est pas définie, ou son dossier n'existe pas"
    if dossier.resolve().is_relative_to((config.RACINE / "exemple").resolve()):
        return None, f"VEILLE_KIT désigne les gabarits de l'exemple ({dossier}), pas un kit réel"
    if not empreintes.pieces(dossier):
        return None, f"le kit ({dossier}) est vide"
    return dossier, ""


DOSSIER, RAISON = _kit()


@pytest.mark.skipif(DOSSIER is None, reason=f"pas de kit ici : {RAISON}")
def test_le_kit_na_pas_derive_depuis_la_derniere_validation():
    """Le cœur. Il nomme le fichier, les deux empreintes, et quoi faire."""
    reference = empreintes.lire_reference()
    assert reference, (
        "Aucune référence figée : empreintes-kit.json est absent ou vide.\n"
        "Lance `veille empreintes-kit --mettre-a-jour` une première fois, "
        "APRÈS avoir vérifié que le kit est dans l'état que tu veux figer."
    )
    ecarts = empreintes.comparer(reference, empreintes.calculer(DOSSIER))
    if ecarts:
        detail = "\n\n".join(f"  - {e}" for e in ecarts)
        pytest.fail(
            f"\nLE KIT A DIVERGÉ DE LA RÉFÉRENCE — {len(ecarts)} écart(s).\n\n"
            f"{detail}\n\n"
            f"  Kit mesuré   : {DOSSIER}\n"
            f"  Référence    : {empreintes.REFERENCE}\n\n"
            f"  La référence n'est jamais recalculée automatiquement : si ces\n"
            f"  changements sont voulus, c'est à toi de l'écrire.\n",
            pytrace=False,
        )


@pytest.mark.skipif(DOSSIER is None, reason=f"pas de kit ici : {RAISON}")
def test_les_lettres_anglaises_sont_surveillees():
    """Ce sont précisément celles qui ont dérivé. Qu'on ne les oublie pas : chaque
    lettre anglaise du kit est dans la référence figée."""
    reference = empreintes.lire_reference()
    anglaises = sorted(f.name for f in empreintes.pieces(DOSSIER)
                       if f.name.startswith("lettre") and f.name.endswith("_en.md"))
    assert anglaises, f"aucune lettre anglaise dans le kit ({DOSSIER})"
    manquantes = [n for n in anglaises if n not in reference]
    assert not manquantes, (
        f"ces lettres ne sont pas figées : {sorted(manquantes)}. "
        f"Ce sont celles qui ont dérivé sans alarme."
    )


@pytest.mark.skipif(DOSSIER is None, reason=f"pas de kit ici : {RAISON}")
def test_les_cv_sont_surveilles():
    reference = empreintes.lire_reference()
    cv = [n for n in reference if n.lower().startswith("cv")]
    assert len(cv) >= 3, f"seulement {len(cv)} CV figé(s) : {cv}"


# --------------------------------------------------------------------------
# Le contrôle lui-même — il doit mordre, et distinguer les trois natures
# --------------------------------------------------------------------------


def test_un_fichier_modifie_est_detecte():
    ecarts = empreintes.comparer({"a.md": "aaa", "b.md": "bbb"},
                                 {"a.md": "aaa", "b.md": "ZZZ"})
    assert len(ecarts) == 1
    assert ecarts[0].nature == "modifie"
    assert ecarts[0].fichier == "b.md"
    assert ecarts[0].attendu == "bbb" and ecarts[0].lu == "ZZZ"


def test_un_fichier_disparu_est_detecte():
    ecarts = empreintes.comparer({"a.md": "aaa"}, {})
    assert ecarts[0].nature == "absent"


def test_un_fichier_nouveau_est_detecte():
    """Une piece deposee sans etre figee part aussi en candidature."""
    ecarts = empreintes.comparer({}, {"surprise.pdf": "xxx"})
    assert ecarts[0].nature == "nouveau"


def test_un_kit_conforme_ne_produit_aucun_ecart():
    assert empreintes.comparer({"a.md": "aaa"}, {"a.md": "aaa"}) == []


@pytest.mark.parametrize("nature,attendus", [
    ("modifie", ("empreinte attendue", "empreinte lue", "redepose",
                 "empreintes-kit --mettre-a-jour")),
    ("absent", ("DISPARU", "redepose")),
    ("nouveau", ("NOUVEAU", "mettre-a-jour")),
])
def test_le_message_dit_quoi_faire(nature, attendus):
    """Un echec qui ne dit pas quoi faire se contourne au lieu d'etre traite."""
    texte = str(empreintes.Ecart("piece.md", nature, attendu="aaa", lu="bbb"))
    for mot in attendus:
        assert mot in texte, f"« {mot} » absent du message pour « {nature} »"
    assert "piece.md" in texte


def test_la_reference_nest_pas_recalculee_depuis_le_kit(tmp_path, monkeypatch):
    """LE POINT QUI FAIT TOUT. Si la reference se recalculait, le controle
    mesurerait sa propre copie et passerait toujours."""
    kit = tmp_path / "kit"
    kit.mkdir()
    (kit / "lettre_fr.md").write_text("version A", encoding="utf-8")
    monkeypatch.setenv("VEILLE_KIT", str(kit))

    fige = empreintes.calculer(empreintes.dossier_kit())
    (kit / "lettre_fr.md").write_text("version B — modifiee en douce", encoding="utf-8")

    ecarts = empreintes.comparer(fige, empreintes.calculer(empreintes.dossier_kit()))
    assert len(ecarts) == 1 and ecarts[0].nature == "modifie", (
        "le controle doit voir la modification, pas la suivre")


def test_sans_kit_le_controle_ne_crie_pas(tmp_path, monkeypatch):
    """« le kit n'est pas la » n'est pas « le kit a diverge »."""
    monkeypatch.setenv("VEILLE_KIT", str(tmp_path / "nexiste-pas"))
    assert empreintes.dossier_kit() is None
    assert empreintes.etat()["ecarts"] == []
    assert "n'existe pas" in empreintes.etat()["raison"]


def test_un_kit_vide_est_signale_comme_vide_pas_comme_divergent(tmp_path, monkeypatch):
    vide = tmp_path / "kit"
    vide.mkdir()
    monkeypatch.setenv("VEILLE_KIT", str(vide))
    etat = empreintes.etat()
    assert etat["ecarts"] == []
    assert "vide" in etat["raison"]

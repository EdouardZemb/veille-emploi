"""Le dossier de configuration : sa résolution, sa version et `veille config verifier`.

Les chemins de `config` sont calculés à l'import : ce qui dépend de
l'environnement se prouve donc dans un sous-processus, jamais en rechargeant le
module (d'autres modules en gardent des références). Les tests qui posent une
variable la posent eux-mêmes et ne comptent pas sur l'environnement ambiant.
"""

from __future__ import annotations

import os
import shutil
import socket
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from veille import cli, config, scoring

EXEMPLE = config.RACINE / "exemple"
VARIABLES_DE_CONFIG = ("VEILLE_CONFIG", "VEILLE_CRITERES", "VEILLE_SOURCES", "VEILLE_KIT",
                       "VEILLE_EMPLOI_ENV")


def _sous_processus(code: str, **variables: str) -> str:
    """Exécute `code` dans un interpréteur neuf, avec les seules variables données."""
    env = {k: v for k, v in os.environ.items() if k not in VARIABLES_DE_CONFIG}
    env.update(variables)
    resultat = subprocess.run(
        [sys.executable, "-X", "utf8", "-c", code],
        env=env, capture_output=True, text=True, encoding="utf-8", timeout=60,
    )
    assert resultat.returncode == 0, resultat.stderr
    return resultat.stdout.strip()


@pytest.fixture
def copie_exemple(tmp_path) -> Path:
    destination = tmp_path / "copie"
    shutil.copytree(EXEMPLE, destination)
    return destination


@pytest.fixture
def cache_vide(monkeypatch):
    """Les chargeurs sont mis en cache : on les vide avant, et après chaque test."""
    config.recharger()
    yield
    config.recharger()


def _reecrire_criteres(dossier: Path, modifier) -> None:
    chemin = dossier / "criteres.yaml"
    contenu = yaml.safe_load(chemin.read_text(encoding="utf-8"))
    modifier(contenu)
    chemin.write_text(yaml.safe_dump(contenu, allow_unicode=True), encoding="utf-8")


# --- L'exemple -------------------------------------------------------------


def test_l_exemple_est_sain():
    # L'exemple se vérifie ici ; la configuration réelle d'une instance se vérifie
    # par `veille config verifier`, hors de la suite (étape de la CI).
    assert config.verifier_dossier(EXEMPLE) == []


def test_l_exemple_a_sept_familles_et_leurs_formules():
    brut = yaml.safe_load((EXEMPLE / "criteres.yaml").read_text(encoding="utf-8"))
    assert len(brut["familles"]) == 7
    for nom, famille in brut["familles"].items():
        assert set(famille["formule_cv"]) == {"en", "fr"}, nom
        assert all(famille["formule_cv"].values()), nom


def test_cinq_atouts_dont_un_mis_en_avant():
    brut = yaml.safe_load((EXEMPLE / "criteres.yaml").read_text(encoding="utf-8"))
    assert len(brut["atouts"]) == 5
    mis_en_avant = [a for a in brut["atouts"].values() if a.get("mis_en_avant")]
    assert len(mis_en_avant) == 1
    assert set(mis_en_avant[0]["mis_en_avant"]) == {"libelle", "titre"}
    # Une formule est complète ou absente : un atout de contexte ne dit rien de la
    # personne, et la phrase du CV passe au suivant (tests/test_assemblage.py).
    sans_formule = [nom for nom, atout in brut["atouts"].items() if "formule" not in atout]
    assert sans_formule, "l'exemple doit garder un atout sans formule"
    for nom, atout in brut["atouts"].items():
        if "formule" in atout:
            assert set(atout["formule"]) == {"en", "fr"}, nom
            assert all(str(v).strip() for v in atout["formule"].values()), nom


def test_l_exemple_est_inventé_de_bout_en_bout():
    for fichier in (EXEMPLE / "gabarits" / "lettre.md", EXEMPLE / "gabarits" / "relance.md"):
        texte = fichier.read_text(encoding="utf-8")
        assert "Camille Exemple" in texte
        assert "camille@exemple.invalid" in texte
        assert "+33" not in texte


# --- La version ------------------------------------------------------------


@pytest.mark.parametrize("cas", ["absente", "inconnue"])
def test_version_absente_ou_inconnue(cas, copie_exemple, monkeypatch, cache_vide):
    chemin = copie_exemple / "criteres.yaml"
    if cas == "absente":
        _reecrire_criteres(copie_exemple, lambda c: c.pop("version"))
    else:
        _reecrire_criteres(copie_exemple, lambda c: c.update(version=2))

    problemes = config.verifier_dossier(copie_exemple)
    assert any("version" in p for p in problemes), problemes

    monkeypatch.setattr(config, "CHEMIN_CRITERES", chemin)
    with pytest.raises(config.ConfigurationInvalide) as erreur:
        config.charger_criteres()
    assert "criteres.yaml" in str(erreur.value)
    assert "version" in str(erreur.value)
    if cas == "inconnue":
        assert "2" in str(erreur.value)


def test_une_version_booleenne_n_est_pas_la_version_1(copie_exemple):
    _reecrire_criteres(copie_exemple, lambda c: c.update(version=True))
    assert any("version" in p for p in config.verifier_dossier(copie_exemple))


def test_la_configuration_invalide_est_une_erreur_d_execution():
    assert issubclass(config.ConfigurationInvalide, RuntimeError)
    assert config.VERSIONS_CONNUES == frozenset({1})


# --- La résolution ---------------------------------------------------------


def test_dossier_designe_absent(tmp_path):
    absent = tmp_path / "absent"
    sortie = _sous_processus(
        "from veille import config\n"
        "for charger in (config.charger_criteres, config.charger_sources):\n"
        "    try:\n"
        "        charger()\n"
        "    except config.ConfigurationInvalide as e:\n"
        "        print('INVALIDE')\n"
        "    else:\n"
        "        print('CHARGE')\n",
        VEILLE_CONFIG=str(absent),
    )
    assert sortie.splitlines() == ["INVALIDE", "INVALIDE"]


@pytest.mark.parametrize("variable", ["VEILLE_CONFIG", "VEILLE_CRITERES"])
def test_un_dossier_designe_sans_criteres_est_une_configuration_invalide(variable, tmp_path):
    """Un `VEILLE_CRITERES` resté vers un ancien chemin, ou un dossier sans son fichier : un
    message qui nomme le fichier (`ConfigurationInvalide`), pas une trace FileNotFoundError."""
    dossier = tmp_path / "sans-criteres"
    dossier.mkdir()
    (dossier / "sources.yaml").write_text("{}\n", encoding="utf-8")
    valeur = str(dossier) if variable == "VEILLE_CONFIG" else str(dossier / "criteres.yaml")
    sortie = _sous_processus(
        "from veille import config\n"
        "try:\n"
        "    config.charger_criteres()\n"
        "except config.ConfigurationInvalide as e:\n"
        "    print('INVALIDE', e)\n"
        "else:\n"
        "    print('CHARGE')\n",
        **{variable: valeur},
    )
    assert sortie.startswith("INVALIDE "), sortie
    assert str(dossier / "criteres.yaml") in sortie


def test_criteres_seuls_designent_le_dossier(tmp_path):
    a = tmp_path / "a"
    sortie = _sous_processus(
        "from veille import config\n"
        "print(config.DOSSIER_CONFIG)\n"
        "print(config.CHEMIN_SOURCES)\n"
        "print(config.CHEMIN_GABARITS)\n"
        "print(config.CHEMIN_KIT)\n"
        "print(config.config_designee())\n",
        VEILLE_CRITERES=str(a / "criteres.yaml"),
    )
    dossier, sources, gabarits, kit, designee = sortie.splitlines()
    assert Path(dossier) == a
    assert Path(sources) == a / "sources.yaml"
    assert Path(gabarits) == a / "gabarits"
    assert Path(kit) == a / "gabarits"
    assert designee == "True"


def test_config_pose_donne_tout_le_dossier(tmp_path):
    sortie = _sous_processus(
        "from veille import config\n"
        "print(config.CHEMIN_CRITERES)\n"
        "print(config.CHEMIN_SOURCES)\n"
        "print(config.CHEMIN_GABARITS)\n",
        VEILLE_CONFIG=str(tmp_path),
    )
    criteres, sources, gabarits = (Path(x) for x in sortie.splitlines())
    assert criteres == tmp_path / "criteres.yaml"
    assert sources == tmp_path / "sources.yaml"
    assert gabarits == tmp_path / "gabarits"


def test_le_defaut_n_est_pas_designe():
    sortie = _sous_processus("from veille import config\nprint(config.config_designee())\n")
    assert sortie == "False"


def test_config_designee(tmp_path, monkeypatch):
    monkeypatch.delenv("VEILLE_CONFIG", raising=False)
    monkeypatch.delenv("VEILLE_CRITERES", raising=False)
    monkeypatch.delenv("VEILLE_EMPLOI_ENV", raising=False)
    monkeypatch.setattr(config, "CONFIG_MONTEE", tmp_path / "absent")
    assert config.config_designee() is False

    monkeypatch.setenv("VEILLE_CONFIG", str(tmp_path))
    assert config.config_designee() is True
    monkeypatch.delenv("VEILLE_CONFIG")

    monkeypatch.setenv("VEILLE_CRITERES", str(tmp_path / "criteres.yaml"))
    assert config.config_designee() is True
    monkeypatch.delenv("VEILLE_CRITERES")

    assert config.config_designee() is False
    # Une variable posée mais vide ne désigne rien.
    monkeypatch.setenv("VEILLE_CONFIG", "")
    assert config.config_designee() is False


def _monter(tmp_path, contenu: str | None) -> Path:
    montee = tmp_path / "config-montee"
    if contenu == "absent":
        return montee
    montee.mkdir()
    if contenu == "plein":
        (montee / "criteres.yaml").write_text("version: 1\n", encoding="utf-8")
    return montee


@pytest.mark.parametrize(
    "environ, contenu, attendu",
    [
        ({"VEILLE_EMPLOI_ENV": "staging"}, "plein", "montee"),
        ({"VEILLE_EMPLOI_ENV": "prod"}, "plein", "montee"),
        ({"VEILLE_EMPLOI_ENV": "staging"}, "vide", "defaut"),
        ({"VEILLE_EMPLOI_ENV": "staging"}, "absent", "defaut"),
        ({}, "plein", "defaut"),                       # hors conteneur, ignore
        ({"VEILLE_EMPLOI_ENV": ""}, "plein", "defaut"),
        ({"VEILLE_EMPLOI_ENV": "staging", "VEILLE_CONFIG": "{autre}"}, "plein", "autre"),
        ({"VEILLE_EMPLOI_ENV": "staging", "VEILLE_CRITERES": "{autre}/criteres.yaml"}, "plein", "autre"),
    ],
)
def test_config_montee(environ, contenu, attendu, tmp_path):
    montee = _monter(tmp_path, contenu)
    autre = tmp_path / "autre"
    environ = {k: v.replace("{autre}", str(autre)) for k, v in environ.items()}
    dossier, designe = config.resoudre_dossier(environ, montee)
    if attendu == "montee":
        assert (dossier, designe) == (montee, True)
    elif attendu == "defaut":
        assert designe is False
        assert dossier != montee
    else:
        assert (dossier, designe) == (autre, True)


def test_resoudre_dossier_ne_touche_pas_a_l_environnement(tmp_path, monkeypatch):
    monkeypatch.setenv("VEILLE_CONFIG", str(tmp_path / "ailleurs"))
    # La fonction est pure : elle ne lit que ce qu'on lui donne.
    dossier, designe = config.resoudre_dossier({}, tmp_path / "absent")
    assert designe is False
    assert dossier != tmp_path / "ailleurs"


def test_les_nouvelles_variables_sont_connues():
    assert config.variables_inconnues({"VEILLE_CONFIG": "x", "VEILLE_SDK_AGENT": "y"}) == []
    assert "VEILLE_CONFIG" in config.VARIABLES_CONNUES
    assert "VEILLE_SDK_AGENT" in config.VARIABLES_CONNUES


# --- veille config verifier ------------------------------------------------


def _empreinte(dossier: Path) -> dict[str, tuple[bytes, int]]:
    return {
        str(p.relative_to(dossier)): (p.read_bytes(), p.stat().st_mtime_ns)
        for p in sorted(dossier.rglob("*")) if p.is_file()
    }


def test_config_verifier_sain(capsys, copie_exemple):
    avant = _empreinte(copie_exemple)
    assert cli.principal(["config", "verifier", str(copie_exemple)]) == 0
    sortie = capsys.readouterr()
    assert sortie.out.strip() == "sain"
    assert sortie.err == ""
    assert _empreinte(copie_exemple) == avant


def test_config_verifier_non_sain(capsys, copie_exemple):
    (copie_exemple / "gabarits" / "relance.md").unlink()
    avant = _empreinte(copie_exemple)
    assert cli.principal(["config", "verifier", str(copie_exemple)]) == 2
    sortie = capsys.readouterr()
    assert "relance.md" in sortie.err
    assert "sain" not in sortie.out.split()
    assert _empreinte(copie_exemple) == avant


def test_config_verifier_un_probleme_par_ligne(capsys, copie_exemple):
    (copie_exemple / "gabarits" / "relance.md").unlink()
    (copie_exemple / "gabarits" / "lettre.md").unlink()
    assert cli.principal(["config", "verifier", str(copie_exemple)]) == 2
    lignes = [x for x in capsys.readouterr().err.splitlines() if x.strip()]
    assert len(lignes) == 2


def test_config_verifier_dossier_absent(capsys, tmp_path):
    assert cli.principal(["config", "verifier", str(tmp_path / "absent")]) == 2
    assert capsys.readouterr().err.strip()


def test_config_verifier_developpe_le_tilde(capsys, monkeypatch, copie_exemple):
    """Comme `VEILLE_CONFIG` (`resoudre_dossier`) : un `~` entre guillemets, que le shell ne
    développe pas, désigne le dossier personnel."""
    monkeypatch.setenv("HOME", str(copie_exemple.parent))
    monkeypatch.setenv("USERPROFILE", str(copie_exemple.parent))
    assert cli.principal(["config", "verifier", f"~/{copie_exemple.name}"]) == 0
    sortie = capsys.readouterr()
    assert sortie.out.strip() == "sain"
    assert sortie.err == ""


@pytest.mark.parametrize(
    "arguments",
    [
        ["config"],
        ["config", "verifier"],
        ["config", "verifier", "a", "b"],
        ["config", "-h"],
        ["config", "verifier", "-h"],
        ["config", "inconnue", "a"],
    ],
)
def test_config_verifier_usage(arguments, capsys):
    assert cli.principal(arguments) == 64
    assert capsys.readouterr().out == ""


# --- Ce que vérifie la vérification ---------------------------------------


@pytest.mark.parametrize(
    "modification, mot",
    [
        (lambda c: c.pop("familles"), "familles"),
        (lambda c: c.update(familles={}), "familles"),
        (lambda c: c["familles"]["test_fonctionnel"].pop("poids"), "poids"),
        (lambda c: c["familles"]["test_fonctionnel"].update(poids="beaucoup"), "poids"),
        (lambda c: c["familles"]["test_fonctionnel"].update(motifs="un seul"), "motifs"),
        (lambda c: c["scoring"].update(seuil_interessant="haut"), "seuil_interessant"),
        (lambda c: c["geographie"].update(pays=["france"]), "pays"),
    ],
)
def test_criteres_mal_formes(modification, mot, copie_exemple):
    _reecrire_criteres(copie_exemple, modification)
    problemes = config.verifier_dossier(copie_exemple)
    assert any(mot in p for p in problemes), problemes


def test_deux_atouts_mis_en_avant(capsys, copie_exemple):
    def modifier(contenu):
        for atout in contenu["atouts"].values():
            atout["mis_en_avant"] = {"libelle": "x", "titre": "y"}

    _reecrire_criteres(copie_exemple, modifier)
    assert any("mis_en_avant" in p for p in config.verifier_dossier(copie_exemple))
    assert cli.principal(["config", "verifier", str(copie_exemple)]) == 2


def test_sources_illisibles(copie_exemple):
    (copie_exemple / "sources.yaml").write_text("a: [non fermé\n", encoding="utf-8")
    assert any("sources.yaml" in p for p in config.verifier_dossier(copie_exemple))


def test_sources_facultatives(copie_exemple):
    (copie_exemple / "sources.yaml").unlink()
    assert config.verifier_dossier(copie_exemple) == []


def test_criteres_absents(tmp_path):
    (tmp_path / "gabarits").mkdir()
    problemes = config.verifier_dossier(tmp_path)
    assert any("criteres.yaml" in p for p in problemes)


def test_criteres_illisibles(copie_exemple):
    (copie_exemple / "criteres.yaml").write_text("version: [1\n", encoding="utf-8")
    assert any("criteres.yaml" in p for p in config.verifier_dossier(copie_exemple))


def test_gabarits_obligatoires(copie_exemple):
    shutil.rmtree(copie_exemple / "gabarits")
    problemes = config.verifier_dossier(copie_exemple)
    assert any("lettre.md" in p for p in problemes)
    assert any("relance.md" in p for p in problemes)


# --- La géographie, les sources et le score d'essai -------------------------
# Le score parcourt chaque `geographie.pays.<pays>` comme une liste de motifs, et les
# collecteurs lisent `sources.yaml` comme une table : une autre forme fait tomber chaque
# score, ou chaque collecte. Ce que les contrôles de forme ne voient pas, un score d'essai
# sur des offres inventées l'attrape.


@pytest.mark.parametrize(
    "modification, attendu",
    [
        (lambda c: c["geographie"]["pays"].update(france=None),
         "geographie.pays.france doit etre une liste de chaines"),
        (lambda c: c["geographie"]["pays"].update(suisse="une ville"),
         "geographie.pays.suisse doit etre une liste de chaines"),
        (lambda c: c["geographie"]["pays"]["france"].insert(0, 42),
         "geographie.pays.france[0] doit etre une chaine"),
    ],
)
def test_une_liste_de_pays_mal_formee_est_nommee(modification, attendu, copie_exemple):
    _reecrire_criteres(copie_exemple, modification)
    problemes = config.verifier_dossier(copie_exemple)
    assert f"criteres.yaml : {attendu}" in problemes, problemes
    assert cli.principal(["config", "verifier", str(copie_exemple)]) == 2


def test_un_pays_a_null_fait_aussi_tomber_le_score_d_essai(copie_exemple):
    """Le cas de la revue : `null` passait pour `sain`, puis chaque offre levait TypeError."""
    _reecrire_criteres(copie_exemple, lambda c: c["geographie"]["pays"].update(france=None))
    problemes = config.verifier_dossier(copie_exemple)
    assert "criteres.yaml : le score n'a pas pu tourner : TypeError" in problemes, problemes


def test_des_sources_en_liste_sont_un_probleme(copie_exemple):
    (copie_exemple / "sources.yaml").write_text("- france_travail\n- rss\n", encoding="utf-8")
    problemes = config.verifier_dossier(copie_exemple)
    assert any("sources.yaml" in p and "une table est attendue" in p for p in problemes), problemes
    assert cli.principal(["config", "verifier", str(copie_exemple)]) == 2


def test_des_sources_vides_restent_saines(copie_exemple):
    """Un fichier vide se charge comme une table vide (`charger_sources`) : il reste sain."""
    (copie_exemple / "sources.yaml").write_text("", encoding="utf-8")
    assert config.verifier_dossier(copie_exemple) == []


def test_seul_le_score_d_essai_voit_un_poids_de_description_illisible(capsys, copie_exemple):
    """`scoring.poids_description` n'a pas de contrôle de forme : seul le score d'essai voit que
    le score tomberait. Il le dit en une ligne, par le type de l'exception, sans trace Python."""
    _reecrire_criteres(copie_exemple,
                       lambda c: c["scoring"].update(poids_description="beaucoup"))
    assert config.verifier_dossier(copie_exemple) == [
        "criteres.yaml : le score n'a pas pu tourner : ValueError"]
    assert cli.principal(["config", "verifier", str(copie_exemple)]) == 2
    sortie = capsys.readouterr()
    assert sortie.err.strip() == "criteres.yaml : le score n'a pas pu tourner : ValueError"
    assert "Traceback" not in sortie.err
    assert "sain" not in sortie.out.split()


def test_le_score_d_essai_ne_lit_que_le_dossier_verifie(copie_exemple, monkeypatch):
    """Ni réseau, ni base, ni la configuration chargée : les seuls critères du dossier."""
    def interdit(*_args, **_kwargs):
        raise AssertionError("le score d'essai est sorti du dossier vérifié")

    monkeypatch.setattr(socket, "create_connection", interdit)
    monkeypatch.setattr(socket.socket, "connect", interdit)
    monkeypatch.setattr(sqlite3, "connect", interdit)
    monkeypatch.setattr(config, "charger_criteres", interdit)
    monkeypatch.setattr(scoring, "charger_criteres", interdit)
    assert config.verifier_dossier(copie_exemple) == []


# --- Le profil et l'atout mis en avant -------------------------------------


@pytest.mark.parametrize("valeur", ["", "   ", "a/b", "a\\b", "..", "x..y", 3, ["a"]])
def test_un_nom_de_fichier_de_profil_invalide_est_signale(valeur, copie_exemple):
    _reecrire_criteres(copie_exemple, lambda c: c.setdefault("profil", {}).update(nom_fichier=valeur))
    problemes = config.verifier_dossier(copie_exemple)
    assert any("nom_fichier" in p for p in problemes), problemes


def test_un_nom_de_fichier_de_profil_valide_ou_absent_passe(copie_exemple):
    _reecrire_criteres(copie_exemple, lambda c: c.setdefault("profil", {}).update(nom_fichier="Exemple_CV"))
    assert config.verifier_dossier(copie_exemple) == []
    _reecrire_criteres(copie_exemple, lambda c: c.setdefault("profil", {}).pop("nom_fichier", None))
    assert config.verifier_dossier(copie_exemple) == []


@pytest.mark.parametrize("valeur", ["oui", ["libelle"], 3])
def test_un_mis_en_avant_qui_n_est_pas_une_table_est_un_probleme(valeur, copie_exemple):
    def modifier(c):
        for atout in c["atouts"].values():
            atout.pop("mis_en_avant", None)
        next(iter(c["atouts"].values()))["mis_en_avant"] = valeur

    _reecrire_criteres(copie_exemple, modifier)
    problemes = config.verifier_dossier(copie_exemple)
    assert any("mis_en_avant" in p for p in problemes), problemes


def test_un_mis_en_avant_non_table_ne_compte_pas_comme_un_atout_en_avant(copie_exemple):
    """Deux valeurs « vraies » mais pas des tables : un problème de forme chacune, pas un « 2 le sont »."""
    def modifier(c):
        for atout in c["atouts"].values():
            atout["mis_en_avant"] = True

    _reecrire_criteres(copie_exemple, modifier)
    problemes = config.verifier_dossier(copie_exemple)
    assert not any("un seul atout" in p for p in problemes), problemes
    assert any("mis_en_avant" in p for p in problemes), problemes


# --- Les contrôles par motif -----------------------------------------------
# Ceux que `tests/test_pretraitement.py` faisait sur la configuration lue par la
# suite : `veille config verifier` les fait sur toute configuration.


def test_le_parcours_trouve_les_motifs_de_l_exemple():
    """Si la structure de la configuration change, ce garde-fou doit crier :
    sans lui, les contrôles par motif ne vérifieraient plus rien, en silence."""
    brut = yaml.safe_load((EXEMPLE / "criteres.yaml").read_text(encoding="utf-8"))
    motifs = config.motifs_declares(brut)
    assert len(motifs) > 100
    chemins = {chemin for chemin, _ in motifs}
    assert not any(c.endswith("bruit_agregateur") for c in chemins)
    for attendu in ("geographie.lieux_imprecis.proches.motifs",
                    "geographie.presence_partielle_motifs",
                    "geographie.presence_totale_motifs",
                    "geographie.teletravail_complet_motifs"):
        assert attendu in chemins, attendu


def test_un_motif_que_la_normalisation_detruit_est_nomme(copie_exemple):
    _reecrire_criteres(copie_exemple,
                       lambda c: c["familles"]["test_fonctionnel"]["motifs"].append("++"))
    problemes = config.verifier_dossier(copie_exemple)
    assert any("familles.test_fonctionnel.motifs" in p and "'++'" in p
               and "normalisation" in p for p in problemes), problemes


def test_un_lieu_imprecis_classe_dans_un_autre_groupe_est_nomme(copie_exemple):
    """Le même motif dans deux groupes : le premier examiné l'emporte, l'autre
    n'est jamais rendu. Lequel dépend de l'ordre du fichier (la réécriture trie
    les clés) : le test accepte l'un ou l'autre."""
    def modifier(c):
        groupes = c["geographie"]["lieux_imprecis"]
        groupes["lointains"]["motifs"].append(groupes["proches"]["motifs"][0])

    _reecrire_criteres(copie_exemple, modifier)
    motif = yaml.safe_load((copie_exemple / "criteres.yaml").read_text(encoding="utf-8"))[
        "geographie"]["lieux_imprecis"]["proches"]["motifs"][0]
    problemes = config.verifier_dossier(copie_exemple)
    assert any("geographie.lieux_imprecis." in p and repr(motif) in p
               and "est classe en" in p for p in problemes), problemes


def test_un_bruit_de_lieu_qui_manque_rend_le_motif_meconnaissable(copie_exemple):
    """Sans « france » dans le bruit, « <motif>, France » garde un résidu : le
    lieu n'est plus reconnu comme imprécis."""
    _reecrire_criteres(copie_exemple,
                       lambda c: c["geographie"]["lieu_imprecis_bruit"].remove("france"))
    problemes = config.verifier_dossier(copie_exemple)
    assert any("lieux_imprecis.proches" in p and ", France'" in p
               and "n'est pas reconnu" in p for p in problemes), problemes


def test_un_motif_de_teletravail_masque_par_un_plus_general_est_nomme(copie_exemple):
    """Le piège de « 2 jours sur site » à l'envers : un motif de présence totale
    qui contient un motif de présence partielle, examiné avant lui."""
    _reecrire_criteres(copie_exemple, lambda c: c["geographie"]["presence_totale_motifs"]
                       .append("5 jours sur site par semaine"))
    problemes = config.verifier_dossier(copie_exemple)
    assert any("geographie.presence_totale_motifs" in p
               and "'5 jours sur site par semaine'" in p
               and "'partiel'" in p for p in problemes), problemes


def test_un_controle_par_motif_qui_n_a_pas_pu_tourner_est_un_probleme(copie_exemple):
    """Un poids illisible fait échouer la recherche des lieux : c'est un problème
    rapporté, pas un « sain » par défaut."""
    _reecrire_criteres(copie_exemple,
                       lambda c: c["geographie"]["lieux_imprecis"]["proches"].update(poids="beaucoup"))
    problemes = config.verifier_dossier(copie_exemple)
    assert any("n'ont pas pu tourner" in p for p in problemes), problemes
    assert cli.principal(["config", "verifier", str(copie_exemple)]) == 2


# --- La forme des listes de motifs -----------------------------------------
# Au chargement, une chaîne posée à la place d'une liste se parcourt lettre par
# lettre, et chaque lettre devient un motif ; `None` ou un nombre arrêtent le score.
# La vérification le dit, en nommant la clé, au lieu de sauter la liste en silence.


@pytest.mark.parametrize(
    "modification, chemin",
    [
        (lambda c: c["geographie"].update(presence_totale_motifs="100 % sur site"),
         "geographie.presence_totale_motifs"),
        (lambda c: c["contrat"].update(interim_motifs=None), "contrat.interim_motifs"),
        (lambda c: c["geographie"]["lieux_imprecis"]["proches"].update(motifs="une region"),
         "geographie.lieux_imprecis.proches.motifs"),
        (lambda c: c["atouts"]["domaine_logistique"].update(motifs={"un": "logistique"}),
         "atouts.domaine_logistique.motifs"),
    ],
)
def test_une_liste_de_motifs_qui_n_est_pas_une_liste_est_nommee(modification, chemin,
                                                               copie_exemple):
    _reecrire_criteres(copie_exemple, modification)
    problemes = config.verifier_dossier(copie_exemple)
    assert any(f"{chemin} doit etre une liste de chaines" in p for p in problemes), problemes
    assert cli.principal(["config", "verifier", str(copie_exemple)]) == 2


def test_un_motif_qui_n_est_pas_une_chaine_est_nomme(copie_exemple):
    rang = {}

    def modifier(c):
        motifs = c["familles"]["test_fonctionnel"]["motifs"]
        rang["n"] = len(motifs)
        motifs.append(42)

    _reecrire_criteres(copie_exemple, modifier)
    problemes = config.verifier_dossier(copie_exemple)
    attendu = f"familles.test_fonctionnel.motifs[{rang['n']}] doit etre une chaine"
    assert any(attendu in p for p in problemes), problemes


def test_les_motifs_d_une_famille_ne_sont_signales_qu_une_fois(copie_exemple):
    """`familles.<f>.motifs` a déjà son contrôle (`_problemes_de_criteres`) : la
    vérification de forme ne le double pas."""
    _reecrire_criteres(copie_exemple,
                       lambda c: c["familles"]["test_fonctionnel"].update(motifs="un seul"))
    problemes = config.verifier_dossier(copie_exemple)
    assert [p for p in problemes if "familles.test_fonctionnel.motifs" in p] == [
        "criteres.yaml : familles.test_fonctionnel.motifs doit etre une liste"], problemes


@pytest.mark.parametrize(
    "modification, chemin",
    [
        (lambda c: c["geographie"].update(lieux_imprecis=["proches"]),
         "geographie.lieux_imprecis"),
        (lambda c: c["geographie"]["lieux_imprecis"].update(proches="une region"),
         "geographie.lieux_imprecis.proches"),
    ],
)
def test_un_groupe_de_lieux_imprecis_mal_forme_est_nomme(modification, chemin, copie_exemple):
    _reecrire_criteres(copie_exemple, modification)
    problemes = config.verifier_dossier(copie_exemple)
    assert any(p.endswith(f"{chemin} doit etre une table") for p in problemes), problemes
    # Les contrôles des lieux et du télétravail ne tournent pas sur une géographie
    # mal formée, et le disent.
    assert any("n'ont pas pu tourner" in p for p in problemes), problemes
    assert cli.principal(["config", "verifier", str(copie_exemple)]) == 2


def test_une_geographie_mal_formee_coupe_les_controles_par_motif_en_le_disant(copie_exemple):
    """Une liste de télétravail en chaîne : ses lettres deviendraient des motifs, et
    les contrôles du télétravail rendraient des constats faux. Ils ne tournent pas."""
    _reecrire_criteres(copie_exemple,
                       lambda c: c["geographie"].update(presence_partielle_motifs="hybride"))
    problemes = config.verifier_dossier(copie_exemple)
    assert any("n'ont pas pu tourner" in p and "geographie mal formee" in p
               for p in problemes), problemes
    assert not any("un motif plus general l'emporte" in p for p in problemes), problemes


# --- Les affirmations refusées et les déclencheurs d'entretien --------------
# Deux listes de tables : la vérification de forme des motifs ne descend pas dans
# une liste, ces deux clés ont donc leur propre contrôle, qui nomme le chemin.


def test_l_exemple_porte_des_affirmations_refusees_et_des_declencheurs():
    brut = yaml.safe_load((EXEMPLE / "criteres.yaml").read_text(encoding="utf-8"))
    affirmations = brut["affirmations_refusees"]
    assert 2 <= len(affirmations) <= 4
    for regle in affirmations:
        assert set(regle) == {"libelle", "valeur", "provenance", "motifs"}, regle
        assert regle["motifs"] and all(isinstance(m, str) for m in regle["motifs"])
    declencheurs = brut["entretien"]["declencheurs"]
    assert declencheurs
    assert {d["categorie"] for d in declencheurs} <= {"attaque", "appui", "rituel"}
    assert brut["entretien"]["intitules_a_risque"]["motifs"]


def test_les_affirmations_et_l_entretien_sont_facultatifs(copie_exemple):
    def modifier(c):
        c.pop("affirmations_refusees")
        c.pop("entretien")

    _reecrire_criteres(copie_exemple, modifier)
    assert config.verifier_dossier(copie_exemple) == []


@pytest.mark.parametrize(
    "modification, attendu",
    [
        (lambda c: c.update(affirmations_refusees={"une": "table"}),
         "affirmations_refusees doit etre une liste de tables"),
        (lambda c: c.update(affirmations_refusees="une chaine"),
         "affirmations_refusees doit etre une liste de tables"),
        (lambda c: c["affirmations_refusees"].insert(0, "une chaine"),
         "affirmations_refusees[0] doit etre une table"),
        (lambda c: c["affirmations_refusees"][0].update(motifs="un seul"),
         "affirmations_refusees[0].motifs doit etre une liste de chaines"),
        (lambda c: c["affirmations_refusees"][0].pop("motifs"),
         "affirmations_refusees[0].motifs doit etre une liste de chaines"),
        (lambda c: c["affirmations_refusees"][1]["motifs"].insert(0, 42),
         "affirmations_refusees[1].motifs[0] doit etre une chaine"),
        (lambda c: c["affirmations_refusees"][0].update(libelle=["une", "liste"]),
         "affirmations_refusees[0].libelle doit etre une chaine non vide"),
        (lambda c: c["affirmations_refusees"][0].pop("libelle"),
         "affirmations_refusees[0].libelle doit etre une chaine non vide"),
        (lambda c: c["affirmations_refusees"][0].update(libelle="  "),
         "affirmations_refusees[0].libelle doit etre une chaine non vide"),
        (lambda c: c["affirmations_refusees"][0].update(provenance=12),
         "affirmations_refusees[0].provenance doit etre une chaine non vide"),
        (lambda c: c["affirmations_refusees"][0].pop("provenance"),
         "affirmations_refusees[0].provenance doit etre une chaine non vide"),
        (lambda c: c["affirmations_refusees"][0].update(provenance=""),
         "affirmations_refusees[0].provenance doit etre une chaine non vide"),
        (lambda c: c["affirmations_refusees"][0].pop("valeur"),
         "affirmations_refusees[0].valeur doit etre une chaine non vide"),
        (lambda c: c["affirmations_refusees"][0].update(valeur=""),
         "affirmations_refusees[0].valeur doit etre une chaine non vide"),
        (lambda c: c.update(entretien=["une", "liste"]),
         "entretien doit etre une table"),
        (lambda c: c["entretien"].update(declencheurs={"une": "table"}),
         "entretien.declencheurs doit etre une liste de tables"),
        (lambda c: c["entretien"]["declencheurs"].insert(0, "une chaine"),
         "entretien.declencheurs[0] doit etre une table"),
        (lambda c: c["entretien"]["declencheurs"][0].pop("cle_section"),
         "entretien.declencheurs[0].cle_section doit etre une chaine non vide"),
        (lambda c: c["entretien"]["declencheurs"][0].update(cle_section="  "),
         "entretien.declencheurs[0].cle_section doit etre une chaine non vide"),
        (lambda c: c["entretien"]["declencheurs"][0].update(categorie="bof"),
         "entretien.declencheurs[0].categorie doit valoir attaque, appui ou rituel"),
        (lambda c: c["entretien"]["declencheurs"][0].update(pourquoi=3),
         "entretien.declencheurs[0].pourquoi doit etre une chaine"),
        (lambda c: c["entretien"]["declencheurs"][0].update(motifs="un seul"),
         "entretien.declencheurs[0].motifs doit etre une liste de chaines"),
        (lambda c: c["entretien"]["declencheurs"][0]["motifs"].insert(0, 7),
         "entretien.declencheurs[0].motifs[0] doit etre une chaine"),
        (lambda c: c["entretien"]["declencheurs"][0].update(pays="fr"),
         "entretien.declencheurs[0].pays doit valoir ch, ou etre absent"),
        (lambda c: c["entretien"].update(intitules_a_risque=["sdet"]),
         "entretien.intitules_a_risque doit etre une table"),
        (lambda c: c["entretien"]["intitules_a_risque"].pop("motifs"),
         "entretien.intitules_a_risque.motifs doit etre une liste de chaines"),
        (lambda c: c["entretien"]["intitules_a_risque"].pop("avertissement"),
         "entretien.intitules_a_risque.avertissement doit etre une chaine non vide"),
    ],
)
def test_une_affirmation_ou_un_declencheur_mal_forme_est_nomme(modification, attendu,
                                                              copie_exemple):
    _reecrire_criteres(copie_exemple, modification)
    problemes = config.verifier_dossier(copie_exemple)
    assert any(p == f"criteres.yaml : {attendu}" for p in problemes), problemes
    assert cli.principal(["config", "verifier", str(copie_exemple)]) == 2

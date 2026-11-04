"""La suite ne touche jamais les vrais fichiers de la console.

Elle tourne aussi sur le serveur, ou la console sert : une variable `VEILLE_*`
exportee dans le shell ne doit pas l'y envoyer sur la vraie base ou les vraies cles.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from veille import config, notifications

EXEMPLE = config.RACINE / "exemple"
VARIABLES_DE_CONFIGURATION = ("VEILLE_CONFIG", "VEILLE_KIT", "VEILLE_CRITERES", "VEILLE_SOURCES")


def test_la_suite_tourne_dans_un_dossier_temporaire():
    for nom, chemin in (
        ("VEILLE_DB", config.CHEMIN_DB),
        ("VEILLE_DOSSIERS", config.CHEMIN_DOSSIERS),
        ("VEILLE_VAPID", notifications.CHEMIN_VAPID),
    ):
        assert "veille-tests-" in str(chemin), f"{nom} sort du dossier temporaire : {chemin}"


def test_la_suite_ne_lit_pas_le_fichier_d_environnement_de_la_console():
    """Importer `veille.cli` charge un fichier d'environnement, `config/.env` par
    defaut. Sur le serveur, ce sont les vraies valeurs : importe par un test, il
    les versait dans toute la suite, et `VEILLE_KIT` y faisait echouer
    tests/test_cli_env.py. La suite pointe `VEILLE_ENV` sur un fichier absent."""
    chemin = os.environ.get("VEILLE_ENV", "")
    assert "veille-tests-" in chemin, f"VEILLE_ENV sort du dossier temporaire : {chemin!r}"
    assert not Path(chemin).exists()


def test_les_cookies_de_la_suite_n_exigent_pas_https():
    """Un `VEILLE_HTTPS=1` exporte ne passe pas : le client de test parle en http,
    et ne renverrait pas un cookie `Secure`."""
    assert os.environ["VEILLE_HTTPS"] == "0"


def test_la_suite_ne_herite_pas_des_variables_du_conteneur():
    """`VEILLE_EMPLOI_ENV` ferait demarrer chaque test en mode conteneur ;
    l'absence est leur valeur neutre, la suite les retire avant l'import."""
    for nom in ("VEILLE_EMPLOI_ENV", "VEILLE_EMPLOI_URL_PUBLIQUE", "VEILLE_EMPLOI_VERSION"):
        assert nom not in os.environ, f"{nom} est exportee dans la suite"


def test_la_suite_tourne_sur_l_exemple():
    """La suite lit l'exemple, jamais la configuration d'une instance : un test qui
    affirme sur les valeurs d'une instance casse a chaque reglage de celle-ci."""
    assert config.DOSSIER_CONFIG == EXEMPLE
    assert config.CHEMIN_CRITERES == EXEMPLE / "criteres.yaml"
    assert config.CHEMIN_SOURCES == EXEMPLE / "sources.yaml"
    assert config.CHEMIN_GABARITS == EXEMPLE / "gabarits"
    assert config.CHEMIN_KIT.is_relative_to(EXEMPLE), (
        f"le kit sort de l'exemple : {config.CHEMIN_KIT}")


def test_les_variables_de_configuration_sont_affectees_par_la_suite():
    """`VEILLE_CONFIG` et `VEILLE_KIT` sont affectees, `VEILLE_CRITERES` et
    `VEILLE_SOURCES` retirees : aucune ne vient du shell."""
    assert os.environ.get("VEILLE_CONFIG") == str(EXEMPLE)
    assert os.environ.get("VEILLE_KIT") == str(EXEMPLE / "gabarits")
    for nom in ("VEILLE_CRITERES", "VEILLE_SOURCES"):
        assert nom not in os.environ, f"{nom} est exportee dans la suite"


def test_une_configuration_exportee_n_entre_pas_dans_la_suite(tmp_path):
    """Sur le serveur, `VEILLE_CONFIG` et `VEILLE_KIT` designent l'instance. Exportees
    dans le shell qui lance la suite, elles n'y entrent pas : `conftest.py` les
    reaffecte, ou les retire, avant tout import de `veille`."""
    ailleurs = tmp_path / "ailleurs"
    (ailleurs / "gabarits").mkdir(parents=True)
    # `conftest.py` cree son dossier `veille-tests-*` a l'import : il va dans
    # `tmp_path`, pas dans le dossier temporaire du systeme, a chaque passage.
    temporaire = tmp_path / "temporaire"
    temporaire.mkdir()
    env = dict(os.environ)
    env.update({
        "VEILLE_CONFIG": str(ailleurs),
        "VEILLE_KIT": str(ailleurs / "gabarits"),
        "VEILLE_CRITERES": str(ailleurs / "criteres.yaml"),
        "VEILLE_SOURCES": str(ailleurs / "sources.yaml"),
        "PYTHONPATH": os.pathsep.join([str(config.RACINE), str(config.RACINE / "src")]),
        "TMP": str(temporaire),
        "TEMP": str(temporaire),
        "TMPDIR": str(temporaire),
    })
    code = (
        "import os, tests.conftest\n"
        "from veille import config\n"
        "for nom in " + repr(VARIABLES_DE_CONFIGURATION) + ":\n"
        "    print(nom, os.environ.get(nom, '-'))\n"
        "print('DOSSIER', config.DOSSIER_CONFIG)\n"
        "print('CRITERES', config.CHEMIN_CRITERES)\n"
        "print('SOURCES', config.CHEMIN_SOURCES)\n"
        "print('KIT', config.CHEMIN_KIT)\n"
    )
    r = subprocess.run([sys.executable, "-X", "utf8", "-c", code], capture_output=True,
                       text=True, encoding="utf-8", env=env, cwd=str(config.RACINE), timeout=60)
    assert r.returncode == 0, r.stderr
    lu = dict(ligne.split(" ", 1) for ligne in r.stdout.splitlines())
    assert lu["VEILLE_CONFIG"] == str(EXEMPLE)
    assert lu["VEILLE_KIT"] == str(EXEMPLE / "gabarits")
    assert lu["VEILLE_CRITERES"] == "-"
    assert lu["VEILLE_SOURCES"] == "-"
    assert lu["DOSSIER"] == str(EXEMPLE)
    assert lu["CRITERES"] == str(EXEMPLE / "criteres.yaml")
    assert lu["SOURCES"] == str(EXEMPLE / "sources.yaml")
    assert lu["KIT"] == str(EXEMPLE / "gabarits")
    assert str(ailleurs) not in r.stdout
    assert list(temporaire.glob("veille-tests-*")), "le sous-processus a ecrit hors de tmp_path"

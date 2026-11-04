"""L'ordre de chargement de la configuration.

Regression : `_charger_env()` importait `config` pour connaitre la racine. Or
`config` calcule ses chemins au moment de son import — la base, le kit, les
dossiers generes. Les variables de `config/.env` etaient donc lues APRES que
les chemins soient figes, et `VEILLE_KIT` restait sans effet en ligne de
commande. Le service systemd ne le voyait pas, lui recevant ses variables par
`EnvironmentFile`.
"""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent


def test_charger_env_nimporte_pas_config():
    """La garde la plus simple : le mot `config` ne doit pas apparaitre dans
    le corps de `_charger_env`."""
    source = (RACINE / "src" / "veille" / "cli.py").read_text(encoding="utf-8")
    debut = source.index("def _charger_env")
    fin = source.index("_charger_env()", debut)
    corps = source[debut:fin]
    assert "from .config" not in corps, (
        "importer config ici fige ses chemins avant la lecture de .env"
    )


def test_le_env_est_lu_avant_le_calcul_des_chemins(tmp_path):
    """Verification de bout en bout, dans un processus neuf."""
    env_fichier = tmp_path / "mon.env"
    kit = tmp_path / "kit-a-moi"
    kit.mkdir()
    env_fichier.write_text(f"VEILLE_KIT={kit}\n", encoding="utf-8")

    script = textwrap.dedent(f"""
        import os, sys
        os.environ["VEILLE_ENV"] = {str(env_fichier)!r}
        sys.path.insert(0, {str(RACINE / "src")!r})
        from veille import cli          # declenche _charger_env()
        from veille.config import CHEMIN_KIT
        print(CHEMIN_KIT)
    """)
    # Sans le `VEILLE_KIT` que la suite pose : une variable deja posee gagne sur
    # le fichier (test suivant), et le fichier ne serait jamais lu.
    env = {k: v for k, v in os.environ.items() if k != "VEILLE_KIT"}
    resultat = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, timeout=60, env=env
    )
    assert resultat.returncode == 0, resultat.stderr
    assert resultat.stdout.strip() == str(kit), (
        f"VEILLE_KIT ignore : {resultat.stdout.strip()}"
    )


def test_une_variable_deja_posee_gagne_sur_le_fichier(tmp_path):
    """`setdefault` : l'environnement du service prime sur config/.env."""
    env_fichier = tmp_path / "mon.env"
    env_fichier.write_text(f"VEILLE_KIT={tmp_path / 'du-fichier'}\n", encoding="utf-8")
    impose = tmp_path / "impose"

    script = textwrap.dedent(f"""
        import os, sys
        os.environ["VEILLE_ENV"] = {str(env_fichier)!r}
        os.environ["VEILLE_KIT"] = {str(impose)!r}
        sys.path.insert(0, {str(RACINE / "src")!r})
        from veille import cli
        from veille.config import CHEMIN_KIT
        print(CHEMIN_KIT)
    """)
    resultat = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, timeout=60
    )
    assert resultat.returncode == 0, resultat.stderr
    assert resultat.stdout.strip() == str(impose)


# --------------------------------------------------------------------------
# Les secrets ne sortent jamais
#
# Le danger n'est pas le code qu'on relit : c'est le service distant qui
# renvoie dans son corps d'erreur ce qu'on lui a envoye, et qu'on recopie
# tel quel dans un journal.
# --------------------------------------------------------------------------


# Les valeurs ci-dessous sont FICTIVES et doivent le rester : un fichier de
# test est versionne, lu, copie. Aucun secret reel n'a rien a y faire.
def test_un_corps_de_reponse_qui_contient_le_secret_est_masque(monkeypatch):
    from veille.config import masquer

    monkeypatch.setenv("FT_CLIENT_SECRET", "0123456789abcdef0123456789abcdef")
    monkeypatch.setenv("VEILLE_IMAP_MOTDEPASSE", "motdepasseappfictif")
    brut = ('{"error":"invalid_client","envoye":"0123456789abcdef0123456789abcdef",'
            '"imap":"motdepasseappfictif"}')
    propre = masquer(brut)
    assert "0123456789abcdef" not in propre
    assert "motdepasseappfictif" not in propre
    assert "invalid_client" in propre, "le diagnostic utile doit rester lisible"


def test_une_valeur_vide_ou_courte_ne_masque_pas_tout(monkeypatch):
    """Un secret vide ne doit pas transformer chaque caractere en marqueur."""
    from veille.config import masquer

    monkeypatch.setenv("FT_CLIENT_SECRET", "")
    monkeypatch.setenv("FT_CLIENT_ID", "abc")      # trop court pour etre un secret
    assert masquer("texte normal abc") == "texte normal abc"

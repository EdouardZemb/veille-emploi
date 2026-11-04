"""Les bornes de l'affinement — c'est ici que se situe le vrai risque.

Une lettre affinée qui lui prête une expérience qu'il n'a pas se retourne
contre lui en entretien, et il ne saura même pas d'où ça vient. L'affinement a
le droit de retoucher les **transitions, le ton et la longueur**. Il n'a pas le
droit d'inventer un fait.

Ces tests ne font aucun appel réseau : ils vérifient la frontière, qui est la
seule chose qui protège.
"""

from __future__ import annotations

import json
import os

import pytest

from tests.sauts import sauter
from veille import affinement

ORIGINAL = """Camille Exemple

I am applying for the position of WMS Test Engineer, advertised on LinkedIn.

Where I am honest with you: I have no EDI track record. Where I am ahead is the
automation of mobile test suites. I hold the ISTQB Foundation and Mobile
Application Testing certificates, sat in June and October 2025.

On the three mobile apps I test for a client I wrote 640 automated checks
from five sources and traced them back to 95 user stories.

Enclosures: CV [[diplomas]]
"""


# --------------------------------------------------------------------------
# Ce qui est refusé
# --------------------------------------------------------------------------


def test_un_chiffre_invente_est_refuse():
    faux = ORIGINAL.replace("640 automated checks", "1200 automated checks")
    refus = affinement.verifier_bornes(ORIGINAL, faux)
    assert any("chiffre" in r for r in refus), refus


def test_une_date_inventee_est_refusee():
    faux = ORIGINAL.replace("June and October 2025", "June 2023 and October 2025")
    assert any("date" in r for r in affinement.verifier_bornes(ORIGINAL, faux))


def test_une_certification_ajoutee_est_refusee():
    """Le cas le plus dangereux : une competence qu'il n'a pas."""
    faux = ORIGINAL.replace("ISTQB Foundation", "ISTQB Foundation, the APICS CPIM badge")
    refus = affinement.verifier_bornes(ORIGINAL, faux)
    assert any("certification" in r or "outils" in r for r in refus), refus


def test_un_outil_ajoute_est_refuse():
    faux = ORIGINAL + "\nI also work daily with SAP EWM and Manhattan platforms.\n"
    assert affinement.verifier_bornes(ORIGINAL, faux)


@pytest.mark.parametrize("formule", [
    "I am an expert in electronic data interchange",
    "with extensive experience in EDI environments",
    "a proven track record in warehouse automation",
])
def test_la_survente_est_refusee(formule):
    """« Je n'ai pas de vecu EDI » ne doit jamais devenir une affirmation."""
    faux = ORIGINAL.replace("I have no EDI track record", formule)
    refus = affinement.verifier_bornes(ORIGINAL, faux)
    assert any("survente" in r for r in refus), refus


def test_la_suppression_dun_marqueur_est_refusee():
    """Les marqueurs signalent ce qu'il doit completer : les effacer les cache."""
    faux = ORIGINAL.replace("[[diplomas]]", "diplomas")
    assert any("marqueur" in r for r in affinement.verifier_bornes(ORIGINAL, faux))


def test_un_texte_ampute_de_moitie_est_refuse():
    faux = ORIGINAL[: len(ORIGINAL) // 3]
    assert any("ampute" in r for r in affinement.verifier_bornes(ORIGINAL, faux))


# --------------------------------------------------------------------------
# Ce qui est accepté — sinon l'affinement ne sert à rien
# --------------------------------------------------------------------------


def test_une_transition_amelioree_passe():
    mieux = ORIGINAL.replace(
        "On the three mobile apps I test for a client I wrote",
        "That discipline is not theoretical. On the three mobile apps I test "
        "for a client I wrote",
    )
    assert mieux != ORIGINAL, "TEMOIN : la modification doit porter"
    assert affinement.verifier_bornes(ORIGINAL, mieux) == []


def test_un_raccourcissement_raisonnable_passe():
    plus_court = ORIGINAL.replace(
        "Application Testing certificates, sat in June and October 2025.",
        "Application Testing certificates.",
    )
    assert plus_court != ORIGINAL, "TEMOIN : la modification doit porter"
    assert affinement.verifier_bornes(ORIGINAL, plus_court) == []


def test_une_reformulation_sans_fait_nouveau_passe():
    autre = ORIGINAL.replace(
        "Where I am honest with you:", "To be straightforward with you:")
    assert affinement.verifier_bornes(ORIGINAL, autre) == []


# --------------------------------------------------------------------------
# La disponibilité — pas d'erreur obscure
# --------------------------------------------------------------------------


def test_sans_node_le_bouton_se_desactive_proprement(monkeypatch):
    monkeypatch.setattr(affinement.shutil, "which", lambda _: None)
    d = affinement.disponible()
    assert not d.possible
    assert "node" in d.raison.lower()


def test_sans_sdk_la_raison_est_explicite(monkeypatch, tmp_path):
    monkeypatch.setattr(affinement.shutil, "which", lambda _: "/usr/bin/node")
    monkeypatch.setattr(affinement, "RACINE_SDK", tmp_path / "absent")
    d = affinement.disponible()
    assert not d.possible
    assert "installation du sdk" in d.raison.lower()


def test_sans_identifiants_la_raison_est_explicite(monkeypatch, tmp_path):
    sdk = tmp_path / "node_modules" / "@anthropic-ai" / "claude-agent-sdk"
    sdk.mkdir(parents=True)
    monkeypatch.setattr(affinement.shutil, "which", lambda _: "/usr/bin/node")
    monkeypatch.setattr(affinement, "RACINE_SDK", tmp_path)
    monkeypatch.setattr(affinement, "IDENTIFIANTS", tmp_path / "pas-de-cle")
    for v in affinement.VARIABLES_JETON:
        monkeypatch.delenv(v, raising=False)
    d = affinement.disponible()
    assert not d.possible
    assert "jeton" in d.raison.lower()
    assert "setup-token" in d.raison, "il doit savoir quoi faire"


def test_ce_qui_part_est_dit_explicitement(monkeypatch, tmp_path):
    sdk = tmp_path / "node_modules" / "@anthropic-ai" / "claude-agent-sdk"
    sdk.mkdir(parents=True)
    cle = tmp_path / "credentials.json"
    cle.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "jeton-de-test")
    monkeypatch.setattr(affinement.shutil, "which", lambda _: "/usr/bin/node")
    monkeypatch.setattr(affinement, "RACINE_SDK", tmp_path)
    monkeypatch.setattr(affinement, "IDENTIFIANTS", cle)
    d = affinement.disponible()
    assert d.possible
    assert "quittent ton serveur" in d.ce_qui_part
    assert "annonce" in d.ce_qui_part


def test_indisponible_ne_leve_pas_derreur(monkeypatch):
    """Pas d'erreur obscure : un message, et la lettre assemblee suffit."""
    monkeypatch.setattr(affinement.shutil, "which", lambda _: None)
    r = affinement.affiner("texte", "annonce")
    assert not r.ok and r.message and r.texte == ""


def test_un_resultat_hors_bornes_nest_jamais_applique(monkeypatch, tmp_path):
    """Meme quand l'appel reussit, un texte qui invente est refuse."""
    sdk = tmp_path / "node_modules" / "@anthropic-ai" / "claude-agent-sdk"
    sdk.mkdir(parents=True)
    cle = tmp_path / "credentials.json"
    cle.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "jeton-de-test")
    monkeypatch.setattr(affinement.shutil, "which", lambda _: "/usr/bin/node")
    monkeypatch.setattr(affinement, "RACINE_SDK", tmp_path)
    monkeypatch.setattr(affinement, "IDENTIFIANTS", cle)

    import json as _json

    monkeypatch.setattr(affinement.subprocess, "Popen", _faux_popen(
        _json.dumps({"texte": ORIGINAL.replace("640", "9000")})))
    r = affinement.affiner(ORIGINAL, "annonce")
    assert not r.ok
    assert r.refus
    assert "PAS applique" in r.message


# --------------------------------------------------------------------------
# Un echec d'authentification ne doit jamais devenir une lettre
#
# Le SDK rend ses echecs comme du TEXTE d'assistant. Sans controle,
# « Failed to authenticate: OAuth session expired » serait propose comme
# lettre de motivation — et le message affiche serait du JavaScript minifie.
# --------------------------------------------------------------------------


@pytest.mark.parametrize("brut", [
    "Failed to authenticate: OAuth session expired and could not be refreshed",
    "Error: invalid api key",
    "Please run /login",
])
def test_un_echec_dauthentification_est_reconnu(brut):
    assert affinement._est_echec_auth(brut)


def test_le_message_dauthentification_est_lisible():
    m = affinement._message_echec("Failed to authenticate: OAuth session expired")
    assert "aucun jeton exploitable" in m.lower()
    assert "setup-token" in m, "il doit savoir quoi faire"
    assert "lettre assemblee reste complete" in m
    # Ce qu'on interdit, c'est la trace TECHNIQUE, pas la ponctuation.
    for marque in (".mjs", "at Object", "node:internal", "=>", "function(",
                   "ERR_", "Traceback"):
        assert marque not in m, f"trace technique dans le message : {marque}"


def test_un_echec_rendu_comme_texte_nest_jamais_propose(monkeypatch, tmp_path):
    sdk = tmp_path / "node_modules" / "@anthropic-ai" / "claude-agent-sdk"
    sdk.mkdir(parents=True)
    cle = tmp_path / "credentials.json"
    cle.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "jeton-de-test")
    monkeypatch.setattr(affinement.shutil, "which", lambda _: "/usr/bin/node")
    monkeypatch.setattr(affinement, "RACINE_SDK", tmp_path)
    monkeypatch.setattr(affinement, "IDENTIFIANTS", cle)

    import json as _json

    monkeypatch.setattr(affinement.subprocess, "Popen", _faux_popen(
        _json.dumps({"texte": "Failed to authenticate: OAuth session expired"})))
    r = affinement.affiner(ORIGINAL, "annonce")
    assert not r.ok
    assert "setup-token" in r.message
    assert r.texte == "", "un echec ne doit pas etre propose comme texte"


# --------------------------------------------------------------------------
# Un fichier d'identifiants peut être une COQUILLE
#
# Constat sur le serveur : `~/.claude/.credentials.json` peut exister, structure
# intacte, et ses deux jetons être des chaînes VIDES, avec `expiresAt: 0`. Le
# fichier ne bouge pas quand on se reconnecte : une session interactive ne
# réécrit pas ce fichier.
#
# Tester l'EXISTENCE du fichier ne prouvait donc rien, et `disponible()`
# rendait `True` sur un serveur incapable de s'authentifier.
# --------------------------------------------------------------------------


def _coquille(tmp_path):
    """Un fichier coquille : la structure attendue, des jetons vides."""
    f = tmp_path / "credentials.json"
    f.write_text(json.dumps({
        "claudeAiOauth": {"accessToken": "", "refreshToken": "", "expiresAt": 0}
    }), encoding="utf-8")
    return f


def _faux_popen(sortie: str = "", erreur: str = "", code: int = 0, vu=None):
    """Remplace `subprocess.Popen` dans les tests.

    La plomberie est passee de `subprocess.run` a `Popen` pour pouvoir tuer
    la descendance a l'expiration : `run` ne tue que son fils direct, et le
    binaire `claude` survivait a l'abandon.
    """
    class FauxProc:
        pid = 4242
        returncode = code

        def communicate(self, entree=None, timeout=None):
            return sortie, erreur

        def kill(self):
            pass

        def wait(self, timeout=None):
            return code

    def fabriquer(*a, **k):
        if vu is not None:
            vu.update(k)
        return FauxProc()

    return fabriquer


def _sdk(tmp_path):
    d = tmp_path / "node_modules" / "@anthropic-ai" / "claude-agent-sdk"
    d.mkdir(parents=True, exist_ok=True)
    return tmp_path


def test_un_fichier_coquille_ne_compte_pas_pour_un_jeton(monkeypatch, tmp_path):
    monkeypatch.setattr(affinement, "IDENTIFIANTS", _coquille(tmp_path))
    assert not affinement._fichier_porte_un_jeton()


def test_un_fichier_avec_jeton_compte(monkeypatch, tmp_path):
    f = tmp_path / "c.json"
    f.write_text(json.dumps({"claudeAiOauth": {"accessToken": "sk-ant-oat01-abc"}}),
                 encoding="utf-8")
    monkeypatch.setattr(affinement, "IDENTIFIANTS", f)
    assert affinement._fichier_porte_un_jeton()


def test_disponible_refuse_sur_une_coquille(monkeypatch, tmp_path):
    """Le cas reel : SDK present, fichier present, et pourtant rien ne marche."""
    monkeypatch.setattr(affinement.shutil, "which", lambda _: "/usr/bin/node")
    monkeypatch.setattr(affinement, "RACINE_SDK", _sdk(tmp_path))
    monkeypatch.setattr(affinement, "IDENTIFIANTS", _coquille(tmp_path))
    for v in affinement.VARIABLES_JETON:
        monkeypatch.delenv(v, raising=False)
    d = affinement.disponible()
    assert not d.possible
    assert "coquille" in d.raison or "vides" in d.raison
    assert "setup-token" in d.raison, "il doit savoir quoi faire"
    assert "config/.env" in d.raison


@pytest.mark.parametrize("variable", ["CLAUDE_CODE_OAUTH_TOKEN", "ANTHROPIC_API_KEY"])
def test_un_jeton_dans_lenvironnement_suffit(monkeypatch, tmp_path, variable):
    monkeypatch.setattr(affinement.shutil, "which", lambda _: "/usr/bin/node")
    monkeypatch.setattr(affinement, "RACINE_SDK", _sdk(tmp_path))
    monkeypatch.setattr(affinement, "IDENTIFIANTS", _coquille(tmp_path))
    for v in affinement.VARIABLES_JETON:
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setenv(variable, "jeton-de-test")
    assert affinement.jeton_present() == variable
    assert affinement.disponible().possible


def test_un_jeton_vide_ou_blanc_ne_compte_pas(monkeypatch):
    for v in affinement.VARIABLES_JETON:
        monkeypatch.setenv(v, "   ")
    assert affinement.jeton_present() == ""


def test_le_message_dechec_donne_le_vrai_remede():
    """L'ancien message disait de relancer `claude` en SSH. C'est faux : on a
    mesure que ca ne reecrit pas le fichier."""
    m = affinement._message_echec("Failed to authenticate: OAuth session expired")
    assert "setup-token" in m
    assert "config/.env" in m
    assert "ne suffit pas" in m
    assert "lettre assemblee reste complete" in m


def test_le_sous_processus_recoit_un_path_qui_trouve_claude(monkeypatch, tmp_path):
    """Le PATH d'un service systemd ne contient pas ~/.local/bin."""
    monkeypatch.setattr(affinement.shutil, "which", lambda _: "/usr/bin/node")
    monkeypatch.setattr(affinement, "RACINE_SDK", _sdk(tmp_path))
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "jeton-de-test")
    monkeypatch.setenv("PATH", "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin")

    vu = {}
    monkeypatch.setattr(affinement.subprocess, "Popen",
                        _faux_popen(json.dumps({"texte": "texte"}), vu=vu))
    affinement.affiner("Camille Exemple\n\nUn texte.\n", "annonce")
    chemin = vu["env"]["PATH"]
    assert str(affinement.BIN_LOCAL) in chemin, chemin
    assert chemin.startswith(str(affinement.BIN_LOCAL)), "doit primer sur le reste"


def test_le_jeton_est_transmis_au_sous_processus(monkeypatch, tmp_path):
    monkeypatch.setattr(affinement.shutil, "which", lambda _: "/usr/bin/node")
    monkeypatch.setattr(affinement, "RACINE_SDK", _sdk(tmp_path))
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "jeton-de-test")

    vu = {}
    monkeypatch.setattr(affinement.subprocess, "Popen",
                        _faux_popen(json.dumps({"texte": "texte"}), vu=vu))
    affinement.affiner("Camille Exemple\n\nUn texte.\n", "annonce")
    assert vu["env"]["CLAUDE_CODE_OAUTH_TOKEN"] == "jeton-de-test"


# --------------------------------------------------------------------------
# La consigne, durcie apres un echec reel
#
# 02/10/2026, premier affinement reel : sur une lettre dont tout l'argument
# est une reserve d'experience, le modele a ajoute deux references que la
# lettre n'avait jamais ecrites. Les bornes ont refuse l'ensemble — y compris un travail de style reellement
# meilleur. La consigne d'alors se contentait d'interdire « une certification,
# un outil, une technologie » : trop general pour mordre.
#
# Les bornes ne bougent PAS. C'est la consigne qui doit rendre le refus rare.
# --------------------------------------------------------------------------


def test_la_consigne_interdit_nommement_les_categories_inventees():
    c = affinement.consigne().lower()
    for mot in ("norme", "referentiel", "reglementation", "certification",
                "sigle", "outil", "technologie", "employeur"):
        assert mot in c, f"la consigne ne nomme pas la categorie « {mot} »"


def test_la_consigne_cite_un_cas_concret_a_une_seule_place():
    """Un interdit abstrait n'a pas suffi : la consigne nomme un cas concret, de
    la forme de l'incident — une lettre qui dit ne pas avoir un vecu, et des
    references que la version precedente y a ajoutees. Le cas est invente : le
    recit reel n'a rien a faire dans le code. Il tient a une seule place, et les
    bornes le refusent."""
    import re
    c = affinement.consigne()
    origines = re.findall(r"Lettre d'origine : « (.+?) »", c)
    ajouts = re.findall(r"Ta version precedente : elle a ajoute (.+?)\.\n", c)
    assert len(origines) == 1 and len(ajouts) == 1, (origines, ajouts)
    assert re.search(r"\bpas\b", origines[0]), "la lettre d'origine est une reserve"
    references = [r.strip() for r in re.split(r",| et ", ajouts[0])]
    assert len(references) >= 2, references
    for reference in references:
        assert reference not in origines[0], f"« {reference} » est un ajout"
        assert c.count(reference) == 1, f"« {reference} » : une seule place"
    # La version precedente, telle que la consigne la decrit, est refusee.
    refus = affinement.verifier_bornes(origines[0], f"{origines[0]} {ajouts[0]}.")
    assert any("certifications ou outils" in r for r in refus), refus


def test_la_consigne_dit_que_lannonce_nautorise_rien():
    """Le piege suivant : reprendre un sigle de l'annonce. Les bornes
    comparent la lettre a la lettre, pas a l'annonce — un sigle pris dans
    l'annonce serait refuse comme une invention."""
    import re
    plat = re.sub(r"\s+", " ", affinement.consigne().lower())
    assert "seule la lettre fait foi" in plat


def test_la_consigne_interdit_de_recasser_les_sigles():
    """« wms » devenu « WMS » est un sigle NOUVEAU pour les bornes. Le
    modele doit le savoir, sinon il se fait refuser sur une correction juste."""
    assert "casse des sigles" in affinement.consigne().lower()


def test_la_consigne_annonce_le_controle_automatique():
    """Lui dire que le refus est en bloc, et ce qu'il perd en se le prenant."""
    bas = affinement.consigne().lower()
    assert "controle automatique" in bas
    assert "rejet" in bas or "refus" in bas


def test_les_bornes_restent_inchangees():
    """Consigne durcie ne veut pas dire filet relache. Ce test echoue si
    quelqu'un retire une borne pour faire passer une proposition."""
    rendu = ("Je suis EXPERT en EDIFACT depuis 2019, et j'ai 21 ans de WMS.")
    origine = "Je n'ai pas de vecu dans ce domaine."
    refus = affinement.verifier_bornes(origine, rendu)
    categories = " | ".join(refus)
    assert "chiffres" in categories
    assert "dates" in categories
    assert "certifications ou outils" in categories
    assert "survente" in categories


def test_une_borne_mord_sur_la_forme_de_l_incident_du_02_octobre():
    """Ce qui a ete refuse ce jour-la, transpose a l'exemple : une reserve
    d'experience, et deux references du domaine ajoutees, dont un numero."""
    avant = ("Your advertisement mentions wms, edi and cross-docking. "
             "Where I am honest with you: I have no EDI track record.")
    apres = ("Your advertisement centres on wms, edi and cross-docking, and on "
             "message standards such as EDIFACT and GS1 128. "
             "I have no EDI track record.")
    refus = affinement.verifier_bornes(avant, apres)
    assert any("EDIFACT" in r for r in refus), refus
    assert any("128" in r for r in refus), refus


# --------------------------------------------------------------------------
# Le depassement de delai
#
# 02/10/2026, 09:06:26 : la demande d'Edouard a ete coupee a 120 s pile. Le
# delai qui mordait etait `DELAI`, cote Python — aucune autre couche n'en
# impose. Et deux defauts sont apparus en le mesurant :
#
#   1. `subprocess.run(timeout=)` ne tue que son fils direct, `node`. Le
#      binaire `claude`, lance par le SDK, est un PETIT-FILS : il continuait
#      de tourner apres l'abandon. Du temps consomme pour rien.
#   2. Le message de depassement avait perdu, lors d'un refactor, la phrase
#      qui dit que la lettre assemblee reste valable — et l'ecran l'affichait
#      sous « Proposition refusee », alors que rien n'avait ete propose.
# --------------------------------------------------------------------------


def test_le_delai_laisse_de_la_marge_au_pire_temps_mesure():
    """42,7 s avec l'ancienne consigne, 90,8 s avec la durcie, coupe a 120."""
    assert affinement.DELAI >= 150, "trop court : 120 mordait deja"
    assert affinement.DELAI <= 240, "au-dela, ce n'est plus une attente"


def test_un_depassement_nest_pas_un_refus(monkeypatch, tmp_path):
    monkeypatch.setattr(affinement.shutil, "which", lambda _: "/usr/bin/node")
    monkeypatch.setattr(affinement, "RACINE_SDK", _sdk(tmp_path))
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "jeton-de-test")

    class FauxProc:
        pid = 4242
        returncode = None

        def communicate(self, *a, **k):
            raise affinement.subprocess.TimeoutExpired("node", affinement.DELAI)

        def kill(self):
            pass

        def wait(self, timeout=None):
            return 0

    monkeypatch.setattr(affinement.subprocess, "Popen", lambda *a, **k: FauxProc())
    monkeypatch.setattr(affinement, "_tuer_larbre", lambda p: None)

    r = affinement.affiner("Camille Exemple\n\nUn texte.\n", "annonce")
    assert not r.ok
    assert r.depassement is True, "l'ecran doit pouvoir le distinguer d'un refus"
    assert r.refus == [], "rien n'a ete propose, donc rien n'a ete refuse"
    assert "lettre assemblee est intacte" in r.message
    assert "reessayer" in r.message.lower()
    assert "interrompu" in r.message
    assert r.as_dict()["depassement"] is True


def test_le_sous_processus_est_lance_dans_sa_propre_session(monkeypatch, tmp_path):
    """Sans ca, on ne peut pas tuer la descendance : le binaire `claude`
    survivait a l'abandon et terminait son travail dans le vide."""
    monkeypatch.setattr(affinement.shutil, "which", lambda _: "/usr/bin/node")
    monkeypatch.setattr(affinement, "RACINE_SDK", _sdk(tmp_path))
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "jeton-de-test")

    vu = {}
    monkeypatch.setattr(affinement.subprocess, "Popen",
                        _faux_popen(json.dumps({"texte": "texte"}), vu=vu))
    affinement.affiner("Camille Exemple\n\nUn texte.\n", "annonce")
    assert vu.get("start_new_session") is True


@pytest.mark.skipif(sauter(lambda: hasattr(os, "killpg")), reason="groupes de processus POSIX")
def test_tuer_larbre_vise_le_groupe_entier(monkeypatch):
    tues = []

    class FauxProc:
        pid = 777
        def wait(self, timeout=None):
            return 0
        def kill(self):
            tues.append(("kill-direct", self.pid))

    monkeypatch.setattr(affinement.os, "getpgid", lambda pid: pid)
    monkeypatch.setattr(affinement.os, "killpg",
                        lambda pgid, sig: tues.append((sig, pgid)))
    affinement._tuer_larbre(FauxProc())
    assert (affinement.signal.SIGTERM, 777) in tues
    assert ("kill-direct", 777) not in tues, "on tue le GROUPE, pas le seul fils"


@pytest.mark.skipif(sauter(lambda: hasattr(os, "killpg")), reason="groupes de processus POSIX")
def test_un_groupe_deja_disparu_ne_leve_pas():
    class FauxProc:
        pid = 999999999
        def wait(self, timeout=None):
            return 0
        def kill(self):
            pass

    affinement._tuer_larbre(FauxProc())   # ne doit pas lever


def test_deux_appels_nutilisent_pas_le_meme_fichier_de_script(monkeypatch, tmp_path):
    """Nom fixe = deux appels simultanes s'effacent le script l'un l'autre.

    Releve du 02/10 : un appel sur deux a echoue sur une erreur de module
    introuvable pendant qu'un autre tournait.
    """
    monkeypatch.setattr(affinement.shutil, "which", lambda _: "/usr/bin/node")
    monkeypatch.setattr(affinement, "RACINE_SDK", _sdk(tmp_path))
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "jeton-de-test")

    chemins = []

    class FauxProc:
        pid = 1
        returncode = 0

        def communicate(self, entree=None, timeout=None):
            return json.dumps({"texte": "texte"}), ""

    def capture(cmd, *a, **k):
        chemins.append(cmd[1])
        return FauxProc()

    monkeypatch.setattr(affinement.subprocess, "Popen", capture)
    affinement.appeler_modele("p", "c")
    affinement.appeler_modele("p", "c")
    assert len(set(chemins)) == 2, chemins


def test_le_script_temporaire_est_efface_apres_lappel(monkeypatch, tmp_path):
    monkeypatch.setattr(affinement.shutil, "which", lambda _: "/usr/bin/node")
    monkeypatch.setattr(affinement, "RACINE_SDK", _sdk(tmp_path))
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "jeton-de-test")
    monkeypatch.setattr(affinement.subprocess, "Popen",
                        _faux_popen(json.dumps({"texte": "texte"})))
    affinement.appeler_modele("p", "c")
    assert not list(tmp_path.glob(".affinement-veille*"))


def test_le_message_derreur_donne_la_cause_pas_le_chemin_du_fichier():
    """02/10 : Edouard a vu « Affinement indisponible : file:///home/camille/
    sdk-agent/node_modules/.../sdk.mjs:99 ». Node imprime le cadre
    de code AVANT le message, et on prenait la premiere ligne."""
    brut = (
        "file:///home/camille/sdk-agent/node_modules/"
        "@anthropic-ai/claude-agent-sdk/sdk.mjs:99\n"
        "`;k2(n).then(()=>{if(t!==void 0){let s=dNe(n);" + "x" * 2000 + "\n"
        "        ^\n\n"
        "TypeError: Cannot read properties of undefined (reading 'content')\n"
        "    at cC.initialize (sdk.mjs:99:12)\n"
    )
    m = affinement._message_echec(brut)
    assert "TypeError" in m
    assert "sdk.mjs:99\n" not in m
    assert "file:///" not in m
    assert len(m) < 260


def test_sans_ligne_derreur_on_prend_une_ligne_courte_de_la_fin():
    brut = "bruit " * 200 + "\nquelque chose a mal tourne\n"
    assert "quelque chose a mal tourne" in affinement._message_echec(brut)


def test_un_stderr_vide_ne_fait_pas_tomber_le_message():
    assert affinement._message_echec("")
    assert affinement._message_echec(None)


def test_le_motif_derreur_ne_contient_aucun_caractere_de_controle():
    """Garde-fou sur un piege deja rencontre cinq fois ici.

    Ecrit « Error\b » dans une edition qui traverse plusieurs couches de
    citation, le \b devient le caractere BACKSPACE (0x08) : le motif compile
    sans erreur et ne matche plus jamais rien. On le mesure.
    """
    motif = affinement._LIGNE_ERREUR.pattern
    for c in motif:
        assert c == chr(9) or ord(c) >= 32, (
            f"caractere de controle {ord(c)} dans le motif : {motif!r}")
    assert affinement._LIGNE_ERREUR.findall("TypeError: quelque chose")


# --------------------------------------------------------------------------
# Un point final n'est pas un chiffre invente
#
# 02/10/2026 : une proposition a ete refusee pour « chiffres inventes : 5. ».
# L'original disait « norme 5 seconde edition », la proposition « norme 5. ». La
# classe de caracteres de _CHIFFRES inclut le point — pour attraper « 12,5 »
# — et ramassait donc le point de fin de phrase. Soixante secondes jetees.
# --------------------------------------------------------------------------


def test_un_point_final_ne_compte_pas_comme_un_chiffre_nouveau():
    avant = "Norme VDA 5 seconde edition, 64 cas et 350 regles."
    apres = "Norme VDA 5. Il y a 64 cas et 350 regles."
    assert affinement.verifier_bornes(avant, apres) == []


def test_une_virgule_collee_ne_compte_pas_non_plus():
    avant = "Il y a 21 elements et 5 categories."
    apres = "Il y a 21, puis 5, dans l'ordre."
    assert affinement.verifier_bornes(avant, apres) == []


def test_un_vrai_chiffre_nouveau_est_toujours_refuse():
    """Le filet ne doit pas s'etre desserre."""
    refus = affinement.verifier_bornes("J'ai 64 cas.", "J'ai 64 cas et 2000 regles.")
    assert any("chiffres inventes" in r and "2000" in r for r in refus), refus


def test_les_nombres_a_espace_ou_virgule_restent_compares_entiers():
    assert affinement.verifier_bornes("91,25 % au module.", "91,25 % au module !") == []
    refus = affinement.verifier_bornes("91,25 % au module.", "99,99 % au module.")
    assert refus


# --------------------------------------------------------------------------
# Le SDK et le nom viennent de la configuration
# --------------------------------------------------------------------------


def test_affinement_sans_sdk_agent(monkeypatch):
    monkeypatch.setattr(affinement.shutil, "which", lambda _: "/usr/bin/node")
    monkeypatch.setattr(affinement, "RACINE_SDK", None)
    d = affinement.disponible()
    assert not d.possible
    assert "VEILLE_SDK_AGENT n'est pas posée" in d.raison


def test_la_consigne_nomme_la_personne_du_profil(monkeypatch, request, tmp_path):
    from tests.aide_criteres import poser_criteres

    poser_criteres(
        monkeypatch, request, tmp_path,
        lambda brut: brut["profil"].update(nom="Camille Exemple"),
    )
    c = affinement.consigne()
    assert "ECRITE par Camille Exemple." in c
    assert "que Camille n'a jamais" in c


def test_la_consigne_sans_nom_parle_de_la_personne_candidate(monkeypatch, request, tmp_path):
    from tests.aide_criteres import poser_criteres

    poser_criteres(
        monkeypatch, request, tmp_path,
        lambda brut: brut["profil"].pop("nom", None),
    )
    c = affinement.consigne()
    assert "ECRITE par la personne candidate." in c
    assert "que la personne candidate n'a jamais" in c

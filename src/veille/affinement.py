"""Affiner une lettre déjà assemblée — sur demande, jamais automatiquement.

CE MODULE N'EST PAS LE CHEMIN NORMAL. La generation produit toujours une lettre
complete sans lui : assemblee a partir de ses phrases et des mots de l'annonce,
gratuite, reproductible, sans que rien ne sorte de la machine. L'affinement est
un bouton qu'il actionne sur une candidature qui compte.

CE QU'IL A LE DROIT DE TOUCHER — et c'est strictement borne :
  - les transitions entre paragraphes,
  - le ton,
  - la longueur.

CE QU'IL N'A PAS LE DROIT DE FAIRE :
  - inventer un fait, une competence, une experience, un chiffre, une date,
  - ajouter une certification, un outil, un employeur, une technologie,
  - transformer une reserve en affirmation (« je n'ai pas de vecu dans ce
    domaine » ne devient jamais « je connais ce domaine »).

C'est la que se situe le vrai risque. Une lettre affinee qui lui prete une
experience qu'il n'a pas se retourne contre lui en entretien, et il ne saura
meme pas d'ou ca vient. D'ou `verifier_bornes()`, qui compare le texte rendu au
texte d'origine et REFUSE un resultat qui a introduit des elements nouveaux.

IDENTIFIANTS : on suit la convention du SDK Agent (`VEILLE_SDK_AGENT`), qui
n'utilise aucune cle d'API — il lit `~/.claude/.credentials.json` en lecture
seule et laisse `ANTHROPIC_API_KEY` vide. Pas de cle a creer, pas de ligne de
facturation nouvelle. Sans identifiants, le bouton ne s'affiche pas.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import signal
import subprocess
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Le SDK Agent vit dans une arborescence Node deja installee. On ne duplique
# pas une seconde arborescence : on reference celle-la, par `VEILLE_SDK_AGENT`
# (sa racine), et on le dit si elle manque ou si elle bouge.
log = logging.getLogger(__name__)

_RACINE_SDK_POSEE = os.environ.get("VEILLE_SDK_AGENT", "").strip()
RACINE_SDK: Path | None = Path(_RACINE_SDK_POSEE).expanduser() if _RACINE_SDK_POSEE else None
IDENTIFIANTS = Path.home() / ".claude" / ".credentials.json"

# Les deux formes de jeton acceptees, dans l'ordre de preference.
#   CLAUDE_CODE_OAUTH_TOKEN : ce que rend `claude setup-token` (long terme)
#   ANTHROPIC_API_KEY       : une cle d'API classique
# Elles sont lues depuis config/.env, que le service systemd charge deja via
# `EnvironmentFile` — meme convention que le mot de passe Gmail et France
# Travail : droits 600, jamais affichees, jamais journalisees.
VARIABLES_JETON = ("CLAUDE_CODE_OAUTH_TOKEN", "ANTHROPIC_API_KEY")

# Le SDK lance le binaire `claude`, qui vit dans ~/.local/bin. Le PATH d'un
# service systemd ne le contient PAS : sans cet ajout, le SDK ne le trouverait
# pas une fois le jeton en place.
BIN_LOCAL = Path.home() / ".local" / "bin"


def jeton_present() -> str:
    """Le NOM de la variable qui porte un jeton, ou une chaine vide."""
    return next((v for v in VARIABLES_JETON if os.environ.get(v, "").strip()), "")


def _fichier_porte_un_jeton() -> bool:
    """`.credentials.json` contient-il un jeton EXPLOITABLE ?

    Le fichier peut exister et n'etre qu'une coquille : structure intacte,
    jetons vides. C'est l'etat observe sur le serveur le 02/10/2026. Tester
    l'existence du fichier ne prouve donc rien.
    """
    try:
        d = json.loads(IDENTIFIANTS.read_text(encoding="utf-8"))
    except Exception:
        return False
    o = d.get("claudeAiOauth") or {}
    return bool((o.get("accessToken") or "").strip()
                or (o.get("refreshToken") or "").strip())

# 180 s, et c'est mesure.
#
# Le 02/10 a 09:06:26, la demande d'Edouard a ete coupee a 120 s pile. Aucune
# autre couche n'impose de delai : le navigateur n'en pose aucun, tailscale
# serve est un proxy nu, uvicorn n'a qu'un keep-alive de 5 s, et le SDK n'a
# pas de limite. La requete est d'ailleurs rendue en HTTP 200 — c'est donc
# bien l'application qui a abandonne, pas le reseau.
#
# ON A SOUPCONNE LA CONSIGNE DURCIE, ET C'EST FAUX. Mesure sur la meme lettre
# de 5 300 caracteres : consigne courte 60,2 s et 59,2 s, consigne durcie
# 29,0 s. Les 2 432 caracteres de consigne ne pesent rien face a la lettre et
# a l'annonce. Ce qui varie, c'est le service : 29 s a plus de 120 s pour un
# travail identique.
#
# D'ou 180 : une marge franche au-dessus du pire temps observe, sans aller
# au-dela — passe trois minutes, ce n'est plus une attente, c'est une panne
# silencieuse, et mieux vaut rendre la main.
DELAI = 180

# Le SDK rend ses echecs d'authentification comme du TEXTE d'assistant : sans
# ce controle, « Failed to authenticate » deviendrait la lettre.
_ECHECS_AUTH = (
    "failed to authenticate", "oauth session expired", "not authenticated",
    "invalid api key", "authentication_error", "please run /login",
)

_CONSIGNE_MODELE = """Tu retravailles une lettre de motivation DEJA ECRITE par @@NOM@@.

Elle part a un recruteur sous son nom. Il devra defendre en entretien chaque
mot qu'elle contient. Tout ce que tu ajoutes et qu'il ne sait pas, il le
decouvrira devant eux.

TU AS LE DROIT DE :
- ameliorer les transitions entre les paragraphes ;
- ajuster le ton pour qu'il colle a l'annonce ;
- raccourcir ce qui est trop long.

INTERDIT ABSOLU — NOMMER CE QUI N'EST PAS DEJA ECRIT

N'ecris AUCUN nom de norme, de referentiel, de reglementation, de methode, de
certification, de sigle, d'outil, de technologie ou d'employeur qui ne figure
pas DEJA, mot pour mot, dans la lettre qu'on te donne. Pas meme pour illustrer,
pas meme entre parenthese, pas meme precede de « comme » ou « par exemple ».

Le fait que l'annonce cite un nom ne t'autorise pas a l'ecrire : seule la
lettre fait foi.

CE QUI S'EST DEJA PRODUIT, ET QU'IL NE FAUT PAS REFAIRE

Lettre d'origine : « Je n'ai pas de vecu en cybersecurite. »
Ta version precedente : elle a ajoute ISO 27001 et NIS 2.

Deux references @@QUI_N_A@@ jamais ecrites, dans la lettre meme ou
il annonce qu'il n'a pas ce vecu. Un recruteur l'aurait interroge dessus,
et il n'aurait pas su d'ou elles venaient. Une telle proposition est
rejetee en bloc : tout le travail de style est perdu avec elle.

LE RESTE DES INTERDITS

- Aucun chiffre, aucune date, aucun pourcentage, aucune duree qui ne soit deja
  dans la lettre. Pas un numero de norme, pas « dix ans » s'il a ecrit autre
  chose.
- Aucun fait, competence ou experience nouvelle.
- Ne transforme jamais une reserve en affirmation. S'il ecrit qu'il n'a pas de
  vecu dans un domaine, cela doit rester lisible comme tel, au meme endroit et
  aussi net.
- N'ecris pas « expert », « expertise », « maitrise », « solide experience »,
  « track record » la ou il ne les a pas ecrits.
- Ne supprime pas les marqueurs entre doubles crochets : ils signalent ce qu'il
  doit completer lui-meme.
- Ne touche pas a la casse des sigles. S'il a ecrit « sql », laisse « sql ».
  Changer la casse fait passer le mot pour un ajout, et la proposition est
  rejetee.

Un controle automatique compare ton texte au sien, mot a mot. Un seul nom ou
un seul chiffre nouveau fait rejeter l'ensemble, y compris ce que tu as bien
fait. Si une transition te semble demander un exemple, ecris-la sans exemple.

Rends UNIQUEMENT le texte de la lettre, sans commentaire ni preambule.
"""


@dataclass
class Disponibilite:
    possible: bool
    raison: str = ""
    ce_qui_part: str = ""


@dataclass
class Affinement:
    ok: bool
    texte: str = ""
    message: str = ""
    refus: list[str] = field(default_factory=list)
    # Un depassement n'est pas un refus : rien n'a ete propose, donc rien
    # n'a ete rejete. L'ecran ne doit pas dire « Proposition refusee ».
    depassement: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "texte": self.texte, "message": self.message,
                "refus": self.refus, "depassement": self.depassement}


def consigne() -> str:
    """La consigne de l'affinement, au nom de la personne du profil.

    `profil.nom` de `criteres.yaml` ; absent, « la personne candidate ». Le
    prenom (premier mot du nom) sert dans la phrase qui rappelle le cas
    concret.
    """
    from .config import charger_criteres

    nom = str((charger_criteres().brut.get("profil") or {}).get("nom") or "").strip()
    if not nom:
        return (_CONSIGNE_MODELE.replace("@@NOM@@", "la personne candidate")
                .replace("@@QUI_N_A@@", "que la personne candidate n'a"))
    prenom = nom.split()[0]
    que = "qu'" if prenom[:1].lower() in "aeiouyhéèêâîôû" else "que "
    return (_CONSIGNE_MODELE.replace("@@NOM@@", nom)
            .replace("@@QUI_N_A@@", f"{que}{prenom} n'a"))


def disponible() -> Disponibilite:
    """L'affinement est-il utilisable ? Sinon on le dit, sans erreur obscure."""
    if not shutil.which("node"):
        return Disponibilite(False, "Node n'est pas installe sur ce serveur.")
    if RACINE_SDK is None:
        return Disponibilite(
            False,
            "VEILLE_SDK_AGENT n'est pas posée : elle désigne la racine de "
            "l'arborescence Node qui porte le SDK Agent. Sans elle, le bouton "
            "reste inactif et la lettre assemblée suffit.",
        )
    sdk = RACINE_SDK / "node_modules" / "@anthropic-ai" / "claude-agent-sdk"
    if not sdk.exists():
        return Disponibilite(
            False,
            f"Le SDK Agent est introuvable dans {RACINE_SDK}. L'affinement "
            f"reutilise l'installation du SDK : si tu l'as "
            f"deplacee, le bouton reste inactif et la lettre assemblee suffit.",
        )
    if not (jeton_present() or _fichier_porte_un_jeton()):
        return Disponibilite(
            False,
            "Aucun jeton exploitable. Le fichier ~/.claude/.credentials.json "
            "existe mais ses jetons sont vides : une session interactive ne "
            "les y reecrit pas. Pose CLAUDE_CODE_OAUTH_TOKEN (rendu par "
            "`claude setup-token`) dans config/.env — le service le lit deja.",
        )
    return Disponibilite(
        True,
        ce_qui_part=(
            "Le texte de ta lettre et celui de l'annonce sont envoyes a "
            "Anthropic pour etre retravailles. Ils quittent ton serveur. "
            "La version assemblee reste enregistree : tu peux y revenir."
        ),
    )


# --------------------------------------------------------------------------
# Les bornes — c'est le cœur, pas l'appel
# --------------------------------------------------------------------------

# Ce qui, apparaissant dans le resultat sans etre dans l'original, trahit une
# invention. On ne cherche pas a tout attraper : on attrape ce qui coute cher.
_CHIFFRES = re.compile(r"\b\d[\d  .,]{0,12}\b")
# Groupe NON capturant : avec un groupe capturant, `findall` ne rendait que
# le siecle et aucune date n'etait jamais detectee.
_ANNEES = re.compile(r"\b(?:19|20)\d{2}\b")
_SIGLES = re.compile(r"\b[A-Z][A-Z0-9][A-Z0-9-]{1,11}\b")
_MARQUEURS = re.compile(r"\[\[[^\]]+\]\]")

# Mots qui transforment une reserve en affirmation.
_SURVENTE = ("expert", "expertise", "extensive experience", "proven track record",
             "mastery", "fully proficient", "deep experience", "seasoned",
             "specialiste reconnu", "maitrise parfaite", "forte expertise")


# Ponctuation qui colle aux nombres et qui n'en fait pas partie.
_BORDS_NOMBRE = " .,;:)" + chr(0xA0) + chr(0x202F)


def _nombres(texte: str) -> set[str]:
    """Les nombres du texte, debarrasses de la ponctuation qui les borde.

    DEFAUT MESURE LE 02/10/2026. La classe de caracteres de `_CHIFFRES`
    inclut le point et la virgule, pour attraper « 1 000 » et « 12,50 ». Elle
    attrapait donc aussi le point final : une proposition qui ecrivait
    « norme 5. » la ou l'original disait « norme 5 seconde edition » se
    faisait refuser pour « chiffres inventes : 5. ». Soixante secondes d'appel jetees
    pour un point. C'est le meme artefact qui avait produit « 11, » dans le
    refus du matin.

    On ne desserre rien : les chiffres eux-memes sont compares a l'identique.
    On retire seulement ce qui n'est pas un chiffre.
    """
    return {c.strip(_BORDS_NOMBRE) for c in _CHIFFRES.findall(texte)} - {""}


def _normalise(t: str) -> str:
    return re.sub(r"\s+", " ", t.lower())


def verifier_bornes(avant: str, apres: str) -> list[str]:
    """Qu'est-ce que le resultat a introduit qui n'etait pas la ?

    Rend la liste des refus. Vide = le resultat est acceptable.
    """
    refus: list[str] = []
    a, b = _normalise(avant), _normalise(apres)

    nouveaux_chiffres = _nombres(apres) - _nombres(avant)
    nouveaux_chiffres = {c for c in nouveaux_chiffres if len(c) > 1}
    if nouveaux_chiffres:
        refus.append(f"chiffres inventes : {', '.join(sorted(nouveaux_chiffres)[:5])}")

    nouvelles_annees = set(_ANNEES.findall(apres)) - set(_ANNEES.findall(avant))
    if nouvelles_annees:
        refus.append(f"dates inventees : {', '.join(sorted(nouvelles_annees))}")

    nouveaux_sigles = set(_SIGLES.findall(apres)) - set(_SIGLES.findall(avant))
    if nouveaux_sigles:
        refus.append(
            f"certifications ou outils ajoutes : {', '.join(sorted(nouveaux_sigles)[:5])}"
        )

    survente = [m for m in _SURVENTE if m in b and m not in a]
    if survente:
        refus.append(f"survente introduite : {', '.join(survente)}")

    perdus = len(_MARQUEURS.findall(avant)) - len(_MARQUEURS.findall(apres))
    if perdus > 0:
        refus.append(f"{perdus} marqueur(s) a completer supprime(s)")

    if len(apres.strip()) < len(avant.strip()) * 0.5:
        refus.append("texte ampute de plus de la moitie")

    return refus


# --------------------------------------------------------------------------
# L'appel
# --------------------------------------------------------------------------

_SCRIPT = """
import { query } from '@anthropic-ai/claude-agent-sdk';
const entree = JSON.parse(await new Response(process.stdin).text());
let sortie = '';
for await (const m of query({
  prompt: entree.prompt,
  options: { maxTurns: 1, allowedTools: [], systemPrompt: entree.consigne },
})) {
  if (m.type === 'assistant') {
    for (const bloc of m.message.content) if (bloc.type === 'text') sortie += bloc.text;
  }
}
process.stdout.write(JSON.stringify({ texte: sortie }));
"""


def _est_echec_auth(texte: str) -> bool:
    bas = (texte or "").lower()
    return any(m in bas for m in _ECHECS_AUTH)


# Motif ecrit SANS contre-oblique, volontairement. Ecrit « ...Error\b... »,
# le \b est arrive dans le fichier sous la forme du caractere BACKSPACE
# (0x08) et le motif ne matchait plus rien — le piege d'echappement deja
# rencontre quatre fois ici. On le contourne par construction.
_LIGNE_ERREUR = re.compile("^[ " + chr(9) + "]*[A-Za-z_]*Error[: ].*$", re.MULTILINE)


def _ligne_derreur(brut: str) -> str:
    """La ligne qui dit VRAIMENT ce qui ne va pas.

    Quand Node leve une exception non rattrapee, il imprime d'abord le chemin
    du fichier puis une ligne de code — ici 4 000 caracteres de SDK minifie —
    et seulement ENSUITE le message d'erreur. Prendre la premiere ligne non
    vide, comme on le faisait, rendait a Edouard
    « file:///…/node_modules/.../sdk.mjs:99 »,
    c'est-a-dire rien.
    """
    texte = brut or ""
    erreurs = _LIGNE_ERREUR.findall(texte)
    if erreurs:
        return " ".join(erreurs[0].split())
    lignes = [l.strip() for l in texte.splitlines() if l.strip()]
    # A defaut, la DERNIERE ligne courte : le bas d'une trace Node est plus
    # parlant que son haut.
    courtes = [l for l in lignes if len(l) < 300]
    return courtes[-1] if courtes else (lignes[0][:200] if lignes else "cause inconnue")


def _message_echec(brut: str) -> str:
    """Un message qu'il peut lire, pas une trace de pile minifiee."""
    if _est_echec_auth(brut):
        return (
            "Le serveur n'a aucun jeton exploitable. Se reconnecter dans une "
            "session interactive ne suffit pas : les jetons ne sont pas "
            "reecrits dans ~/.claude/.credentials.json, qui reste une coquille "
            "vide. Le remede : `claude setup-token`, puis poser le jeton rendu "
            "dans config/.env sous CLAUDE_CODE_OAUTH_TOKEN. "
            "En attendant, la lettre assemblee reste complete et utilisable."
        )
    return f"Affinement indisponible : {_ligne_derreur(brut)[:200]}"


@dataclass
class Reponse:
    """Ce que rend un appel au modele, avant toute interpretation."""

    ok: bool
    texte: str = ""
    message: str = ""
    # Vrai quand c'est le DELAI qui a mordu, pas un refus ni une panne. Ce
    # n'est pas la meme chose a l'ecran : rien n'a ete propose, donc rien n'a
    # ete refuse, et il peut simplement reessayer.
    depassement: bool = False


def _tuer_larbre(proc: subprocess.Popen) -> None:
    """Tue le sous-processus ET sa descendance.

    MESURE DU 02/10/2026, et c'est le vrai defaut. `subprocess.run(timeout=)`
    ne tue que son fils direct — ici `node`. Or le SDK lance le binaire
    `claude` comme PETIT-FILS. Apres un depassement, ce binaire continuait de
    tourner : douze secondes apres l'abandon, il etait toujours la (PID 3705755,
    `claude --output-format stream-json --max-turns 1`). Le travail se terminait
    donc cote serveur, la reponse etait jetee, et Edouard voyait une erreur.
    Du temps consomme pour rien, exactement le pire cas.

    `start_new_session=True` place node dans son propre groupe de processus ;
    on peut alors tuer le groupe entier d'un seul signal.
    """
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
    except (ProcessLookupError, PermissionError, OSError):
        proc.kill()
        return
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except OSError:
            pass


def appeler_modele(prompt: str, consigne: str) -> Reponse:
    """Un aller-retour avec le SDK. Aucune borne ici : c'est de la plomberie.

    Partage avec le releve d'exigences. Les bornes de l'affinement sont dans
    `affiner`, pas ici — un appelant qui veut autre chose qu'une lettre pose
    SES propres verifications, et `exigences.filtrer()` en est une.
    """
    etat = disponible()
    if not etat.possible:
        return Reponse(False, message=etat.raison)

    # Nom UNIQUE par appel. Avec un nom fixe, deux appels simultanes — un
    # affinement et un releve d'exigences, ou deux onglets — ecrivaient le
    # meme fichier, et le premier a finir l'effacait sous les pieds du second
    # avant que son `node` ne l'ait charge. La fenetre est etroite, mais le
    # releve du 02/10 porte un echec en « ERR_MODULE_NOT_FOUND » qui y
    # ressemble, et le remede ne coute rien.
    script = RACINE_SDK / f".affinement-veille-{os.getpid()}-{uuid.uuid4().hex[:8]}.mjs"
    proc = None
    try:
        script.write_text(_SCRIPT, encoding="utf-8")
        environnement = dict(os.environ)
        # Le PATH d'un service systemd ne contient pas ~/.local/bin, ou vit le
        # binaire `claude` que le SDK lance. Mesure du 02/10 :
        # PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin
        environnement["PATH"] = f"{BIN_LOCAL}:{environnement.get('PATH', '')}"
        proc = subprocess.Popen(
            ["node", str(script)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, cwd=str(RACINE_SDK), env=environnement,
            start_new_session=True,
        )
        try:
            sortie, erreur = proc.communicate(
                json.dumps({"prompt": prompt, "consigne": consigne}), timeout=DELAI)
        except subprocess.TimeoutExpired:
            _tuer_larbre(proc)
            return Reponse(
                False, depassement=True,
                message=f"Pas de reponse en {DELAI} s. L'appel a ete "
                        f"interrompu, rien ne continue a tourner dans le vide. "
                        f"Ta lettre assemblee est intacte : tu peux reessayer, "
                        f"ou la garder telle quelle.")
    except Exception as exc:
        if proc is not None:
            _tuer_larbre(proc)
        return Reponse(False, message=f"Appel impossible : {exc}")
    finally:
        script.unlink(missing_ok=True)

    if proc.returncode != 0 or _est_echec_auth(erreur):
        # Le message rendu a Edouard est volontairement court. La trace
        # part au journal, et on en garde la FIN : Node imprime d'abord le
        # cadre de code — ici 4 000 caracteres de SDK minifie — et le
        # message d'erreur seulement ensuite. Garder le debut, c'etait
        # garder le bruit et jeter la cause.
        log.warning("affinement : code %s, fin du stderr :\n%s",
                    proc.returncode, (erreur or "").strip()[-3000:])
        return Reponse(False, message=_message_echec(erreur))
    try:
        texte = (json.loads(sortie) or {}).get("texte", "").strip()
    except json.JSONDecodeError:
        return Reponse(False, message="Reponse illisible.")
    if not texte:
        return Reponse(False, message="Reponse vide.")
    if _est_echec_auth(texte):
        # Le SDK rend l'echec comme du TEXTE : sans ce controle, « Failed to
        # authenticate » partirait comme proposition de lettre.
        return Reponse(False, message=_message_echec(texte))
    return Reponse(True, texte=texte)


def affiner(lettre: str, annonce: str) -> Affinement:
    """Retravaille la lettre. Refuse un resultat qui a invente quelque chose."""
    prompt = (
        "Voici l'annonce a laquelle cette lettre repond :\n\n"
        f"{annonce[:6000]}\n\n"
        "--- LETTRE A RETRAVAILLER ---\n\n"
        f"{lettre}"
    )
    reponse = appeler_modele(prompt, consigne())
    if not reponse.ok:
        return Affinement(False, message=reponse.message,
                          depassement=reponse.depassement)
    texte = reponse.texte

    refus = verifier_bornes(lettre, texte)
    if refus:
        return Affinement(
            False, texte=texte, refus=refus,
            message="Le texte propose sort des bornes : il a introduit des "
                    "elements qui ne sont pas dans ta lettre. Il n'est PAS "
                    "applique — la version assemblee reste en place.",
        )
    return Affinement(True, texte=texte,
                      message="Proposition. Relis-la : si tu ne la reconnais "
                              "pas, reviens a la version assemblee.")

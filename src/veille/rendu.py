"""Rendre la lettre en PDF, sous un nom qu'un recruteur peut recevoir.

Un recruteur reçoit `<Prenom-Nom>-Lettre-de-motivation.pdf`, pas
`lettre-de-motivation.md`. Le nom du fichier est la premiere chose qu'il voit.

WeasyPrint est installe dans le venv du projet : aucun paquet systeme, la regle
d'isolation tient. Si l'import echoue, on le DIT au lieu de produire un dossier
silencieusement incomplet.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from pathlib import Path

PREFIXE_PAR_DEFAUT = "Candidature"


def prefixe() -> str:
    """Le préfixe des noms de PDF : `profil.nom_fichier`, sinon `Candidature`."""
    from .config import charger_criteres

    profil = charger_criteres().brut.get("profil") or {}
    return str(profil.get("nom_fichier") or "").strip() or PREFIXE_PAR_DEFAUT

# Mise en page sobre, pensee pour l'impression et la lecture a l'ecran. Pas de
# fantaisie : une lettre de motivation se lit, elle ne se regarde pas.
STYLE = """
@page { size: A4; margin: 22mm 20mm 20mm 20mm; }
body { font-family: "DejaVu Serif", Georgia, serif; font-size: 10.5pt;
       line-height: 1.5; color: #111; }
.entete { font-size: 10pt; line-height: 1.45; margin-bottom: 14mm; }
.entete .nom { font-size: 13pt; font-weight: bold; letter-spacing: .3px; }
.destinataire { margin-bottom: 8mm; }
.lieu-date { margin-bottom: 10mm; }
.objet { font-weight: bold; margin-bottom: 7mm; }
p { margin: 0 0 3.5mm 0; text-align: justify; }
.signature { margin-top: 9mm; }
/* Un marqueur non rempli doit SAUTER AUX YEUX sur le PDF relu. */
.acompleter { background: #ffe8e8; color: #a00; font-weight: bold;
              padding: 0 2px; border: 1px solid #e0a0a0; }
"""

_A_COMPLETER = re.compile(r"\[\[([^\]]+)\]\]")
_SEPARATEUR_BLOC = re.compile(r"\n\s*\n")


@dataclass
class Rendu:
    chemin: Path | None
    ok: bool
    message: str = ""
    marqueurs_restants: int = 0


def _corps(markdown: str) -> str:
    """Le texte du gabarit, sans ses commentaires de redaction."""
    sans_commentaires = re.sub(r"<!--.*?-->", "", markdown, flags=re.S)
    return sans_commentaires.strip()


import re as _re_md

import re as _re_md

_GRAS = _re_md.compile(r"\*\*(.+?)\*\*", _re_md.S)
_ITALIQUE = _re_md.compile(r"(?<!\*)\*([^*]+?)\*(?!\*)", _re_md.S)
# Le code inline n'a aucun sens dans une lettre : on garde le mot, on jette
# les accents graves. Des lettres francaises ecrivaient un nom de projet et
# `[...]` entre accents graves, qui partaient tels quels dans le PDF.
_CODE = _re_md.compile(r"`([^`]+)`")

# Un bloc qui se declare lui-meme comme ne devant pas partir. Certaines
# lettres du kit mettent leurs notes dans un commentaire HTML ; d'autres,
# arrivees ensuite, les mettaient dans une section Markdown ordinaire, qui
# s'imprimait donc dans le PDF du recruteur.
_A_JETER = _re_md.compile(
    r"supprimer avant envoi|ne pas envoyer|ne part pas au recruteur"
    r"|pour toi, pas pour le recruteur|delete before sending"
    r"|notes de gabarit",
    _re_md.IGNORECASE,
)


def bloc_a_jeter(bloc: str) -> bool:
    """Ce bloc se declare-t-il comme interne ?

    FILET, PAS CONVENTION. La bonne pratique reste le commentaire HTML, qui
    ne depend d'aucune formulation. Mais une note interne imprimee dans une
    lettre de candidature coute l'offre, et un filet qui lit ce que la note
    dit d'elle-meme ne coute rien.
    """
    return bool(_A_JETER.search(bloc))


def _markdown_minimal(echappe: str) -> str:
    """Le gras, l'italique et le code inline, sur du texte DEJA echappe.

    DEFAUT MESURE LE 02/10/2026. Ce module n'interpretait aucun Markdown : il
    echappait tout et enveloppait dans un <p>. Les premieres lettres du kit
    n'en utilisaient pas, donc rien ne se voyait. Des que des lettres
    FRANCAISES sont arrivees, le PDF destine au recruteur affichait
    « **Objet : candidature...** » et des accents graves autour d'un nom de
    projet.

    On travaille sur du texte deja echappe : aucune balise ne peut etre
    injectee par le contenu de la lettre.
    """
    sortie = _GRAS.sub(r"<strong>\1</strong>", echappe)
    sortie = _ITALIQUE.sub(r"<em>\1</em>", sortie)
    return _CODE.sub(r"\1", sortie)


def _en_html(texte: str) -> tuple[str, int]:
    """Markdown simple -> HTML. Les marqueurs restants sont mis en evidence.

    Les blocs internes sont retires AVANT le comptage : un marqueur qui vit
    dans une note de gabarit n'est pas un marqueur a completer dans la
    lettre, et le compter ferait sonner une alarme pour rien.
    """
    paragraphes = []
    restants = 0
    for bloc in re.split(_SEPARATEUR_BLOC, texte):
        bloc = bloc.strip()
        # Un filet horizontal ne se met pas dans une lettre : dans le
        # fichier source il separe la notice du corps, rien de plus.
        if not bloc or (len(bloc) >= 3 and set(bloc) <= {"-"}):
            continue
        # Des qu un bloc se declare interne, lui et TOUT ce qui suit
        # s arretent la : ces notes vivent en fin de fichier et
        # s etalent sur plusieurs paragraphes.
        if bloc_a_jeter(bloc):
            break
        restants += len(_A_COMPLETER.findall(bloc))
        echappe = _markdown_minimal(html.escape(bloc).replace(chr(10), "<br>"))
        # Apres echappement, les crochets sont intacts : on les repere ici.
        echappe = _A_COMPLETER.sub(
            lambda m: f'<span class="acompleter">[{html.escape(m.group(1))}]</span>',
            echappe,
        )
        paragraphes.append(f"<p>{echappe}</p>")
    return chr(10).join(paragraphes), restants


def lettre_en_pdf(markdown: str, destination: Path) -> Rendu:
    """Ecrit la lettre en PDF. Dit franchement si elle n'a pas pu l'etre."""
    try:
        from weasyprint import HTML
    except Exception as exc:  # pragma: no cover - depend de l'installation
        return Rendu(None, False,
                     f"WeasyPrint indisponible ({exc}) : la lettre reste en "
                     f"Markdown, elle n'est pas envoyable telle quelle.")

    corps, restants = _en_html(_corps(markdown))
    page = (f"<!doctype html><html><head><meta charset='utf-8'>"
            f"<style>{STYLE}</style></head><body>{corps}</body></html>")
    try:
        HTML(string=page).write_pdf(str(destination))
    except Exception as exc:  # pragma: no cover
        return Rendu(None, False, f"Rendu PDF echoue : {exc}")
    return Rendu(destination, True, marqueurs_restants=restants)


def nom_pour_envoi(nom_source: str) -> str:
    """Le nom qu'un recruteur doit voir.

    `cv.ch.en.pdf` -> `<Prefixe>-CV-Suisse.pdf`
    `dossier-technique.pdf` -> `<Prefixe>-Dossier-technique.pdf`
    """
    base = nom_source.lower()
    debut = prefixe()
    if base.startswith("cv") or ".cv." in base:
        etiquettes = ""
        if ".ch." in base or "-ch-" in base:
            etiquettes = "-Suisse"
        elif ".fr." in base or "-fr-" in base:
            etiquettes = "-France"
        return f"{debut}-CV{etiquettes}{Path(nom_source).suffix}"
    if "dossier-technique" in base:
        return f"{debut}-Dossier-technique{Path(nom_source).suffix}"
    if "lettre" in base:
        return f"{debut}-Lettre-de-motivation{Path(nom_source).suffix}"
    # Tout le reste garde son nom, prefixe : rien ne part anonyme.
    return f"{debut}-{nom_source}"

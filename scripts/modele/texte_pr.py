"""Le texte de la PR : la section « Écarts à la spec », et la tête relue d'une PR qui ferme une
issue. Le workflow `texte-pr` le lance, après la confidentialité du titre et du corps.

Les écarts à la spec. Le corps de toute PR porte une section de niveau 2 `## Écarts à la spec`,
une seule, sauf quand l'auteur de la PR est `dependabot[bot]` ; cette liste est fermée. La section
court jusqu'au premier titre, quel que soit son niveau, ou à la première ligne de séparation : ce
qui suit n'est pas lu. Elle contient « Aucun. » seul, ou une ligne par écart :
`- <écart> — promesse : <§ de la spec, ou de l'issue> — accord : JJ/MM/AAAA`, une puce `-` ou `*`,
au besoin continuée par des lignes indentées, jointes à elle. Dans cet ordre : l'écart, non vide,
qui peut contenir un séparateur ; « promesse : » suivi d'un texte, sans séparateur ; « accord : »,
ou l'ancienne forme « accord d'Edouard : », suivi d'une vraie date, à deux chiffres pour le jour et
le mois, qui termine la ligne : rien ne la suit que des espaces. La section n'admet rien d'autre
que des lignes vides, « Aucun. », des puces, et des lignes indentées qui continuent la puce
d'avant ; une ligne indentée qui commence par une puce ou un numéro est une sous-liste, et ne la
continue pas. Le contrôle refuse, sans nommer de ligne : une section absente, vide ou en double ;
« Aucun. » à côté d'un écart ; un `<!--` jamais fermé dans la section, qui cacherait la suite. Il
refuse, en nommant la ligne par son rang dans la section, la ligne 1 étant celle qui suit le
titre : une ligne qui n'est ni « Aucun. » ni un écart, une sous-liste comprise ; un écart vide,
sans « promesse : » suivi d'un texte, sans « accord : » ni « accord d'Edouard : » suivi d'une vraie
date, avec un texte après la date, ou hors de cet ordre. Les commentaires fermés et les blocs de
code clôturés ne comptent pas : la forme d'une ligne, que le gabarit met en commentaire, n'est pas
un écart. Une ligne qui commence par un commentaire, après au plus trois espaces, et porte un
texte après sa fermeture n'est ni une puce ni la suite d'une puce : GitHub la rend en bloc HTML.

La tête relue. Une PR qui ferme une issue porte la ligne `Tête relue : <SHA complet>`, égale à la
tête de la PR. Les issues qu'elle ferme ne se lisent pas dans le corps : l'étape d'avant les
demande à l'API (`closingIssuesReferences`, l'analyse de GitHub lui-même) et écrit la réponse dans
le fichier de `--fermetures`. Une réponse absente, vide, en erreur, sans la PR ou au compte mal
formé fait refuser : le contrôle reste fermé. La ligne se cherche dans le corps tel que GitHub le
rend : hors des commentaires et des blocs de code, et avant tout commentaire jamais fermé ouvert
en tête de ligne ou après une puce, qui cache tout ce qui le suit ; une ligne qu'il cache est
absente. À des écarts près, dont deux connus : un `<!--` jamais fermé, ouvert dans un élément de
liste après quatre espaces ou plus (une puce imbriquée, ou une ligne qui continue la puce), cache
sur GitHub tout ce qui le suit, et un `<?`, un `<!` suivi d'une majuscule (`<!DOCTYPE`) ou un
`<![CDATA[` ouvert en tête de ligne, tout ce qui le suit jusqu'au premier `>`, même plusieurs
lignes plus bas, ou jusqu'à la fin sans lui ; le contrôle lit encore ces lignes, la ligne « Tête
relue » comme la section des écarts. D'autres formes HTML cachent aussi sur GitHub ce que le
contrôle lit : un `<?` ou un `<!DOCTYPE` après une puce, ou en ligne et fermé plus bas ; un `<!--`
jamais fermé dans une ligne de bloc HTML, comme `<div><!-- note</div>` ; un attribut ou un titre
de lien sur plusieurs lignes. Tous sont bornés : le SHA de cette ligne doit toujours égaler la
tête de la PR. Un `<!--` au milieu d'un paragraphe reste du texte, et ne cache rien. Le SHA se lit
aussi entre accents graves ou en majuscules.

Avant toute lecture, hors du code en ligne : le texte en LF et en NFC ; l'apostrophe typographique
et U+02BC deviennent `'`, une espace insécable devient une espace ; un séparateur est `—` ou `–`
entouré d'espaces ; les étiquettes se lisent sans égard à la casse.

La sortie ne cite jamais le corps : un corps de PR est public, et peut porter un motif privé. Elle
nomme une ligne par son rang, et seuls des SHA paraissent : les deux, complets, dans le refus d'une
tête relue différente ; les 12 premiers caractères de la tête, dans un succès.

Bibliothèque standard seule, Python 3.10 ou plus.

Usage : texte_pr.py --fermetures FICHIER
        Le corps, l'auteur et la tête se lisent dans l'environnement, jamais dans les arguments :
        CORPS (absent : vide), AUTEUR (exigé), TETE (exigée, 40 caractères hexadécimaux).
        FICHIER est la réponse de l'API sur les issues que la PR ferme.

Retour : 0 rien à signaler, 1 refus, 64 erreur d'usage.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import sys
import unicodedata
from pathlib import Path

EXIT_USAGE = 64
PREFIXE = "texte de la PR : "
EXEMPTE = "dependabot[bot]"
TITRE_ECARTS = "Écarts à la spec"
ECARTS = "écarts à la spec : "
FERME = "ferme une issue : "

_TRADUCTION = str.maketrans({"\u2019": "'", "\u02bc": "'", "\u00a0": " ", "\u202f": " "})
_PUCE = re.compile(r"[-*](?:[ \t]+|$)")
# Un séparateur : un tiret cadratin ou demi-cadratin, entouré d'espaces.
_SEPARATEUR = re.compile(r"[ \t]+[\u2014\u2013][ \t]+")
_PROMESSE = re.compile(r"promesse[ \t]*:(.*)$", re.IGNORECASE)
_ACCORD = re.compile(r"accord(?: d'edouard)?[ \t]*:[ \t]*(.*)$", re.IGNORECASE)
_DATE = re.compile(r"([0-9]{2})/([0-9]{2})/([0-9]{4})(?![0-9/])")

NI_AUCUN_NI_ECART = "ni « Aucun. » ni un écart"
ECART_VIDE = "écart vide avant « promesse : »"
PROMESSE_ABSENTE = "promesse absente"
ACCORD_INVALIDE = "accord absent ou date invalide (JJ/MM/AAAA)"
APRES_LA_DATE = "texte après la date de l'accord, qui termine la ligne"
ORDRE = "l'écart, puis « promesse : », puis « accord : JJ/MM/AAAA » en fin de ligne"
_TETE_RELUE = re.compile(r"[ \t]*tête relue[ \t]*:[ \t]*(`?)([0-9a-f]{40})\1[ \t]*", re.IGNORECASE)
_SHA = re.compile(r"[0-9a-fA-F]{40}")


def _voisins() -> None:
    """Avant d'importer un voisin : aucun cache écrit, même lancé sans `-B`, et le dossier du
    script dans le chemin d'import, en fin, sans doublon, même sous `python -I`."""
    sys.dont_write_bytecode = True
    dossier = os.path.dirname(os.path.abspath(__file__))
    if dossier not in sys.path:
        sys.path.append(dossier)


def _documentation():
    _voisins()
    import documentation

    return documentation


def _normaliser(texte: str) -> str:
    """Le texte, hors du code en ligne, en NFC, apostrophes droites et espaces ordinaires."""
    morceaux = []
    debut = 0
    for m in _documentation().CODE_EN_LIGNE.finditer(texte):
        morceaux.append(unicodedata.normalize("NFC", texte[debut : m.start()]))
        morceaux.append(m.group(0))
        debut = m.end()
    morceaux.append(unicodedata.normalize("NFC", texte[debut:]))
    return "".join(
        morceau if i % 2 else morceau.translate(_TRADUCTION) for i, morceau in enumerate(morceaux)
    )


def _refus_de_la_date(valeur: str) -> str | None:
    """Le refus de la valeur d'un accord, ou `None` : une vraie date `JJ/MM/AAAA`, deux chiffres au
    jour et au mois (`strptime` seul admettrait `7/1/2026`), que rien ne suit que des espaces."""
    m = _DATE.match(valeur)
    if m is None:
        return ACCORD_INVALIDE
    try:
        datetime.date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    except ValueError:
        return ACCORD_INVALIDE
    return APRES_LA_DATE if valeur[m.end() :].strip() else None


def _verifier_ecart(rang: int, texte: str) -> list[str]:
    """Les refus d'un écart, lu sur sa puce et ses lignes de continuation jointes. La dernière
    partie est l'accord, dont la date termine la ligne ; l'avant-dernière, la promesse ; ce qui les
    précède, non vide, l'écart, qui peut contenir un séparateur."""
    # une espace devant : un séparateur en tête laisse une première partie, l'écart, vide
    parties = [partie.strip() for partie in _SEPARATEUR.split(" " + texte)]
    motifs = []
    desordre = False
    accord = _ACCORD.match(parties[-1])
    fin = len(parties) - 1 if accord else len(parties)
    promesse = _PROMESSE.match(parties[fin - 1]) if fin >= 1 else None
    if promesse is not None:
        if not any(parties[: fin - 1]):
            motifs.append(ECART_VIDE)
        if not promesse.group(1).strip():
            motifs.append(PROMESSE_ABSENTE)
    elif any((m := _PROMESSE.match(p)) and m.group(1).strip() for p in parties):
        desordre = True
    else:
        motifs.append(PROMESSE_ABSENTE)
    if accord is not None:
        if (motif := _refus_de_la_date(accord.group(1))) is not None:
            motifs.append(motif)
    elif any(_ACCORD.match(p) for p in parties):
        desordre = True
    else:
        motifs.append(ACCORD_INVALIDE)
    if desordre:
        motifs.append(ORDRE)
    return [f"{ECARTS}ligne {rang} de la section : {motif}" for motif in motifs]


def ecarts(corps: str) -> tuple[list[str], bool]:
    """La section « Écarts à la spec » : (lignes, refus)."""
    doc = _documentation()
    trouvees = doc.sections(corps, TITRE_ECARTS, niveau=2, bornee=True)
    if not trouvees:
        return [ECARTS + "section absente (titre de niveau 2 « Écarts à la spec »)"], True
    if len(trouvees) > 1:
        return [ECARTS + "section en double (un seul titre de niveau 2 « Écarts à la spec »)"], True
    brute = trouvees[0]
    propre = doc.sans_bloc_ni_commentaire(brute)
    if "<!--" in doc.CODE_EN_LIGNE.sub("", propre):
        return [ECARTS + "commentaire HTML non fermé"], True
    # Une ligne qui commence par un commentaire, puis porte un texte après sa fermeture : GitHub la
    # rend en bloc HTML, son texte tel quel, jamais en puce, et le contrôle n'y lit ni une puce ni
    # la suite d'une puce. Son rang est celui de la ligne qui ferme le commentaire ; dans un bloc
    # clôturé, cette ligne est vide, et ne compte pas.
    en_bloc_html = doc.lignes_en_bloc_html(brute)
    refus: list[tuple[int, str]] = []
    aucun = False
    lus: list[tuple[int, list[str]]] = []
    puce_ouverte = False
    for rang, ligne in enumerate(_normaliser(propre).split("\n"), start=1):
        if not ligne.strip():
            continue
        if rang in en_bloc_html:
            pass
        elif ligne[0] in " \t":  # une ligne indentée continue la puce d'avant, sauf une sous-liste
            if puce_ouverte and doc.SOUS_LISTE.match(ligne) is None:
                lus[-1][1].append(ligne.strip())
                continue
        elif ligne.rstrip() == "Aucun.":
            aucun, puce_ouverte = True, False
            continue
        elif (m := _PUCE.match(ligne)) is not None:
            lus.append((rang, [ligne[m.end() :].strip()]))
            puce_ouverte = True
            continue
        puce_ouverte = False
        refus.append((rang, f"{ECARTS}ligne {rang} de la section : {NI_AUCUN_NI_ECART}"))
    for rang, morceaux in lus:
        refus.extend((rang, r) for r in _verifier_ecart(rang, " ".join(morceaux)))
    refus.sort(key=lambda r: r[0])
    lignes = [r for _, r in refus]
    if aucun and lus:
        lignes.append(ECARTS + "« Aucun. » à côté d'un écart")
    if lignes:
        return lignes, True
    if aucun:
        return [ECARTS + "aucun"], False
    if not lus:
        return [ECARTS + "section vide (« Aucun. » ou une ligne par écart)"], True
    return [f"{ECARTS}{len(lus)} déclaré{'s' if len(lus) > 1 else ''}"], False


def _fermees(fermetures: str | None) -> int | None:
    """Le nombre d'issues que la PR ferme, lu dans la réponse de l'API ; `None` si elle est
    absente, vide, en erreur, sans la PR, ou si le compte n'est pas un entier."""
    if fermetures is None or not fermetures.strip():
        return None
    try:
        reponse = json.loads(fermetures)
    except ValueError:
        return None
    if not isinstance(reponse, dict) or "errors" in reponse:
        return None
    try:
        references = reponse["data"]["repository"]["pullRequest"]["closingIssuesReferences"]
        total = references["totalCount"]
    except (KeyError, TypeError):
        return None
    if isinstance(total, bool) or not isinstance(total, int) or total < 0:
        return None
    return total


def tete_relue(corps: str, tete: str, fermetures: str | None) -> tuple[list[str], bool]:
    """La tête relue : (lignes, refus). `fermetures` est le texte de la réponse de l'API, ou
    `None` si le fichier est absent."""
    total = _fermees(fermetures)
    if total is None:
        return ["fermetures illisibles (réponse de l'API absente, en erreur ou mal formée)"], True
    if not total > 0:
        return ["ne ferme aucune issue : tête relue non exigée"], False
    doc = _documentation()
    visible = doc.sans_bloc_ni_commentaire(corps)
    # un commentaire jamais fermé, ouvert en tête de ligne ou après une puce, cache sur GitHub tout
    # ce qui le suit ; au milieu d'un paragraphe, il reste du texte
    cache = re.search(doc.DEBUT_DE_BLOC + "<!--", visible, re.MULTILINE)
    texte = _normaliser(visible if cache is None else visible[: cache.start()])
    relues = [m.group(2).lower() for m in map(_TETE_RELUE.fullmatch, texte.split("\n")) if m]
    tete = tete.lower()
    if not relues:
        return [FERME + "ligne « Tête relue : <SHA complet> » absente"], True
    autres = [sha for sha in relues if sha != tete]
    if autres:
        return [f"{FERME}tête relue {autres[0]} différente de la tête {tete}"], True
    return [f"{FERME}tête relue égale à la tête {tete[:12]}"], False


def _lire(chemin: str) -> str | None:
    """Le texte du fichier des fermetures, chaque octet qui n'est pas de l'UTF-8 remplacé ; `None`
    s'il ne se lit pas."""
    try:
        return Path(chemin).read_bytes().decode("utf-8", errors="replace")
    except OSError:
        return None


class _Analyseur(argparse.ArgumentParser):
    def error(self, message: str):  # le message reçu pourrait citer l'entrée : on ne l'affiche pas
        self.exit(EXIT_USAGE, "texte de la PR : usage invalide (voir --help)\n")


def main(argv: list[str] | None = None) -> int:
    for flux in (sys.stdout, sys.stderr):
        try:
            flux.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
        except (AttributeError, ValueError):
            pass
    p = _Analyseur(
        prog="texte_pr.py",
        description=(
            "Les écarts à la spec et la tête relue d'une PR. Le corps, l'auteur et la tête se"
            " lisent dans CORPS, AUTEUR et TETE."
        ),
    )
    p.add_argument(
        "--fermetures",
        required=True,
        metavar="FICHIER",
        help="la réponse de l'API sur les issues que la PR ferme (closingIssuesReferences)",
    )
    try:
        args = p.parse_args(argv)
    except SystemExit as sortie:
        return 0 if sortie.code in (0, None) else EXIT_USAGE
    auteur = os.environ.get("AUTEUR", "")
    tete = os.environ.get("TETE", "")
    if not auteur or _SHA.fullmatch(tete) is None:
        print(
            "texte de la PR : usage invalide : AUTEUR et TETE (40 caractères hexadécimaux)"
            " exigés (voir --help)",
            file=sys.stderr,
        )
        return EXIT_USAGE
    if auteur == EXEMPTE:
        print(f"{PREFIXE}PR de {EXEMPTE} : écarts et tête relue non exigés")
        return 0
    corps = os.environ.get("CORPS", "")
    lignes_ecarts, refus_ecarts = ecarts(corps)
    lignes_tete, refus_tete = tete_relue(corps, tete, _lire(args.fermetures))
    for ligne in (*lignes_ecarts, *lignes_tete):
        print(PREFIXE + ligne)
    if refus_ecarts or refus_tete:
        print(PREFIXE + "refus")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

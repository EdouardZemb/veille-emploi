"""Le contrôle d'un plan : ses quatre sections de niveau 2, « Mécanismes annoncés », « Outils et cas
limites », « Effets cherchés » et « Revues ». Le socle le lance sur les plans d'une PR
(`.claude/plans/*.md`) ; une session le lance sur son plan, avant de le soumettre et après chaque
correction.

Les sections. Chacune se lit bornée : de son titre de niveau 2 jusqu'au premier titre, quel que
soit son niveau, ou à la première ligne de séparation (`---`). Sans titre de niveau 2, elle est
absente : un titre de niveau 3 ne la remplace pas. Deux titres de niveau 2 du même nom refusent,
en double, et aucune des deux sections n'est lue. Hors des blocs de code clôturés et des
commentaires fermés, elle n'admet que des lignes vides, « Aucun. », des puces `-` ou `*`, et des
lignes indentées, qui continuent la puce d'avant et se joignent à elle. Toute autre ligne refuse,
une ligne indentée sans puce avant elle comprise, comme un `<!--` jamais fermé, qui cacherait la
suite sur GitHub. Une ligne indentée qui commence par une puce ou un numéro (`-`, `*`, `+`, `1.`)
est une sous-liste, et ne continue pas la puce d'avant : elle refuse. Une ligne qui commence par
un commentaire, après au plus trois espaces, et porte un texte après sa fermeture n'est ni une
puce ni la suite d'une puce : GitHub la rend en bloc HTML, et elle refuse aussi. Une section où il
ne reste rien refuse, vide. « Aucun. » n'est admis que seul, et jamais dans « Revues ». Un refus
nomme la ligne par son rang dans la section, la ligne 1 étant celle qui suit le titre, jamais par
son texte.

Avant toute lecture, hors du code en ligne : le texte en LF et en NFC ; l'apostrophe typographique
et U+02BC deviennent `'`, une espace insécable devient une espace. Un séparateur est `—` ou `–`,
entouré d'espaces.

Mécanismes annoncés. Une ligne par comportement que le plan prête à un mécanisme qui existe :
`` - `<lieu>` — `<extrait>` — <comportement> ``, le comportement non vide. Les deux codes en ligne
se lisent comme CommonMark : une suite de N accents graves s'ouvre et se ferme sur une suite
d'exactement N, et une espace en tête et en queue se retire quand les deux sont là. Le lieu a la
forme `[<dépôt>:]<chemin>:<ligne>[-<fin>]`. Trois morceaux séparés par `:` donnent un préfixe, un
nom `[A-Za-z0-9][A-Za-z0-9._-]*`, et deux n'en donnent pas ; un autre nombre de morceaux, ou un
préfixe qui n'est pas un nom, refuse : un chemin du dépôt n'a jamais de deux-points, que Windows
n'admet pas. Le chemin n'est ni vide ni absolu, et ne porte ni `..` ni barre oblique inverse ; la
plage a 40 lignes au plus. Ces refus viennent avant toute lecture et tout `Path` : sous Windows,
`resolve` ouvrirait un partage réseau ou un lecteur. Un chemin sans préfixe part de la racine ; un
chemin préfixé, du clone que nomme `--depot <dépôt>=<clone>`, et sans lui il est « non vérifié »,
sans refus. Le fichier, une fois résolu, reste sous sa racine et est un fichier, sinon absent.
Ses lignes se comptent par `\\n`, comme git et GitHub les comptent, jamais par `splitlines`, qui
coupe aussi sur U+2028 ou `\\f`. L'extrait se cherche, en NFC des deux côtés, sur la ligne citée ou
sur l'une des lignes de la plage. Avec `--sans-lieux`, chaque lieu se lit sans ouvrir de fichier :
la CI vérifie ainsi un plan modifié, dont les numéros de ligne dérivent avec le code qu'il cite.

Outils et cas limites. Une puce, coupée aux deux premiers séparateurs hors du code en ligne, en
trois morceaux non vides : l'outil, le cas limite qu'il traite autrement, le test qui l'exerce.

Effets cherchés. Une puce par décision du plan qui change une forme, une règle, un geste ou un
défaut que reçoit un autre lieu, coupée comme « Outils et cas limites » en trois morceaux non
vides : la décision, où elle arrive, comment c'est vérifié. « Aucun. » seul est admis. La section
n'est exigée que d'un plan neuf (`--neuf`) ; présente, elle se vérifie dans tous les modes.
`--neuf` ne dit rien de plus que la nouveauté du plan : il est distinct de `--sans-lieux`, qui ne
dit que de ne pas ouvrir les fichiers cités. Sa limite : sans `--neuf`, retirer la section entière
d'un plan qui la portait n'est pas vu.

Revues. Une puce par temps de revue, qui cite au moins une unité du plan, présente dans ses titres
de niveau 3, lus hors des blocs de code clôturés et des blocs de commentaire HTML, fermés ou non.
Une unité est une tâche, `### Tâche N : …` ou `### Task N: …`, citée par `Tâche N` ou `Task N`, ou
une tranche, `### Tranche N`, citée par `Tranche N`, sans égard à la casse. Un plan à tâches,
ou sans unité, ne cite que des tâches ; un plan maître, qui a des tranches et aucune tâche, ne cite
que des tranches : l'autre mot n'est que du texte. Un plan qui a les deux sortes est mêlé : il
refuse (`MELE`), juste avant le résumé, et ses citations se lisent dans les deux sortes, chacune
contre les titres de sa sorte. Un numéro suivi d'un point reste le numéro : `### Tranche 2.1` est
la tranche 2. Deux titres de la même sorte ne portent jamais le même numéro. La clôture est la
première unité dont le titre dit « clôture » ou « closure » : chaque unité citée la précède. Un
titre après elle ne refuse pas, mais une revue qui le cite refuse.

La clôture. Un plan neuf, ou qui porte « Effets cherchés », a une unité de clôture, celle que lit
« Revues » : un titre qui dit « clôture » avant la vraie clôture en devient l'unité. Elle nomme
six gestes, le plan supprimé, `CLAUDE.md` ou un ADR, le README, les leçons du lot, la fermeture de
l'issue, la tête relue (`GESTES`), et chaque mot de `--cloture`, à répéter. Son texte va de son
titre à la ligne qui précède le titre suivant de niveau 1 à 3, lu comme dans `sections()`, ou à la
fin du plan. Il se prend sur les lignes d'origine, les commentaires retirés, les blocs de code
gardés, sauf un bloc pris dans un commentaire retiré, puis se lit en NFC, apostrophes droites,
espaces ordinaires, sans égard à la casse, code compris. Un mot se cherche sans lettre, chiffre ni
`_` juste avant ni juste après lui (`\\w`, qui compte `_` : l'emphase `_README_` cache le mot) ;
`supprim` et `suppress` n'ont cette limite qu'avant eux ; entre deux mots, tout blanc compte,
retour à la ligne compris. Un `<!--` jamais fermé dans l'unité refuse, et cache la suite. Le refus
nomme l'unité et les gestes qui manquent, dans l'ordre de `GESTES` puis des options, un mot de
`--cloture` entre guillemets. Sans unité de clôture, un tel plan refuse (`AUCUNE_CLOTURE`), sauf un
plan de tranche ou un plan hors lot, qui n'est tenu ni à l'unité ni aux gestes. La porte voit un
geste que la clôture ne nomme pas, jamais un geste nommé mais fait à moitié.

Les lignes déclarées. Avant la première unité, hors des blocs de code et des commentaires, jusqu'à
trois espaces en tête, le gras admis autour du nom, deux-points compris ou non :
`` Plan maître : `.claude/plans/<fichier>.md` `` dit un plan de tranche, `Hors lot : <raison>` un
plan hors lot. Le chemin, un code en ligne seul après les deux-points, refuse avant toute lecture
pour les raisons d'un lieu, puis hors de `.claude/plans/` ou sans `.md` ; lieux ouverts, il nomme
un plan maître sous la racine, lu comme un plan. Une raison vide, deux lignes de la même sorte, les
deux sortes ensemble, ou l'une d'elles dans un plan maître refusent. Sans `--neuf` ni « Effets
cherchés », ni la clôture ni ces lignes ne se vérifient.

Les fichiers. Un plan qui commence par un BOM UTF-16 se lit en UTF-16, ce qu'écrivent `>` et
`Out-File` de PowerShell 5.1 ; sinon, le plan et les fichiers cités se lisent en UTF-8, BOM retiré,
chaque octet qui n'est pas de l'UTF-8 remplacé.

La sortie ne cite jamais une ligne du plan : seulement des chemins, des rangs, des numéros de tâche
ou de tranche, les titres des sections, les noms des gestes, les mots de `--cloture` et les formes
fixes des refus (la forme attendue d'une section, le commentaire jamais fermé), chaque caractère de
contrôle ou séparateur de ligne d'un nom remplacé par `?`. Elle finit par un résumé, puis par
`refus` s'il y a refus.

Bibliothèque standard seule, Python 3.10 ou plus.

Usage : plan.py PLAN [--racine DOSSIER] [--depot NOM=CLONE]... [--sans-lieux] [--neuf]
                [--cloture MOT]...
        PLAN se lit où qu'il soit. Un chemin sans préfixe part de DOSSIER (défaut : le dossier
        courant), un chemin préfixé par NOM, de CLONE. --sans-lieux vérifie la forme de chaque
        lieu, sans ouvrir de fichier. --neuf exige « Effets cherchés » : un plan neuf, tenu
        aussi à sa clôture. --cloture MOT ajoute un mot que la clôture doit nommer.

Retour : 0 rien à signaler, 1 refus, 64 erreur d'usage (plan illisible, racine ou clone absents,
         --depot mal formé, valeur vide de --cloture).
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import unicodedata
from pathlib import Path

EXIT_USAGE = 64
PLAGE_MAX = 40
PREFIXE = "plan : "
MECANISMES = "Mécanismes annoncés"
OUTILS = "Outils et cas limites"
EFFETS = "Effets cherchés"
REVUES = "Revues"
AUCUN = "Aucun."
TACHE = "Tâche"
TRANCHE = "Tranche"
MELE = "le plan mêle des tâches et des tranches"
COMMENTAIRE_OUVERT = "commentaire HTML jamais fermé, qui cache la suite"
# Une revue sans citation : un texte fixe par sorte citée.
AUCUNE_CITATION = {
    (TACHE,): "aucune tâche citée",
    (TRANCHE,): "aucune tranche citée",
    (TACHE, TRANCHE): "aucune tâche ni tranche citée",
}
# Chaque refus de forme dit la forme de sa section.
FORMES = {
    MECANISMES: "forme attendue : - `<chemin>:<ligne>` — `<extrait>` — <comportement annoncé>, "
    "ou « Aucun. » seul",
    OUTILS: "forme attendue : - <outil> — <cas limite> — <test>, ou « Aucun. » seul",
    EFFETS: "forme attendue : - <décision> — <où elle arrive> — <comment c'est vérifié>, "
    "ou « Aucun. » seul",
    REVUES: "forme attendue : - <revue> : Tâche N, ou Tranche N dans un plan maître ; "
    "jamais « Aucun. »",
}
# Les gestes de clôture, dans l'ordre où le refus les nomme : du nom du geste à son expression,
# cherchée dans le texte replié de l'unité de clôture (`_texte_de_cloture`).
GESTES: dict[str, str] = {
    "le plan supprimé": r"(?<!\w)suppr(?:im|ess)",
    "CLAUDE.md ou un ADR": r"(?<!\w)claude\.md(?!\w)|(?<!\w)adr(?!\w)",
    "le README": r"(?<!\w)readme(?!\w)",
    "les leçons du lot": r"(?<!\w)(?:leçons?|constats?)(?!\w)",
    "la fermeture de l'issue": r"(?<!\w)(?:closes|fixes)(?!\w)|(?<!\w)ferme\s+l'issue(?!\w)",
    "la tête relue": r"(?<!\w)tête\s+relue(?!\w)",
}
AUCUNE_CLOTURE = (
    "aucune unité de clôture : un titre `### Tâche N : … clôture`, ou `### Tranche N · … clôture` "
    "dans un plan maître ; un plan de tranche porte la ligne `Plan maître :`, un plan hors lot la "
    "ligne `Hors lot :`"
)
MAITRE_SANS_CHEMIN = "ligne « Plan maître : » sans chemin"
MAITRE_EN_DOUBLE = "plan maître en double"
MAITRE_DANS_UN_MAITRE = "un plan maître ne nomme pas de plan maître"
HORS_LOT_SANS_RAISON = "ligne « Hors lot : » sans raison"
HORS_LOT_EN_DOUBLE = "ligne « Hors lot : » en double"
HORS_LOT_DANS_UN_MAITRE = "un plan maître n'est pas hors lot"
LES_DEUX_LIGNES = "un plan ne porte pas à la fois « Plan maître : » et « Hors lot : »"
PLANS = ".claude/plans/"

_TRADUCTION = str.maketrans({"\u2019": "'", "\u02bc": "'", "\u00a0": " ", "\u202f": " "})
_PUCE = re.compile(r"[-*](?:[ \t]+|$)")
# Un séparateur : un tiret cadratin ou demi-cadratin, entouré d'espaces.
_SEPARATEUR = re.compile(r"[ \t]+[\u2014\u2013][ \t]+")
_NOM = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
_LIGNES = re.compile(r"([1-9][0-9]{0,8})(?:-([1-9][0-9]{0,8}))?")
_TITRE = re.compile(r" {0,3}###[ \t]+(tâche|task|tranche)[ \t]+([0-9]{1,9})\b", re.IGNORECASE)
_CITATION = re.compile(r"\b(?:tâche|task)[ \t]+([0-9]{1,9})\b", re.IGNORECASE)
_CITATION_DE_TRANCHE = re.compile(r"\btranche[ \t]+([0-9]{1,9})\b", re.IGNORECASE)
_CLOTURE = ("clôture", "closure")
# Une ligne déclarée : son nom, `Plan maître` ou `Hors lot`, le gras admis autour de lui,
# deux-points compris ou non, une espace ou aucune avant les deux-points ; puis sa valeur.
_DECLARATION = re.compile(
    r" {0,3}(\*\*)?(plan maître|hors lot)(?:(?(1)\*\*) ?:| ?:(?(1)\*\*))[ \t]*(.*?)[ \t]*$",
    re.IGNORECASE,
)
# Ce qui tient la place d'un bloc de code clôturé dans le texte de l'unité de clôture, le temps de
# retirer les commentaires : un caractère d'usage privé, ni accent grave ni `<`.
_JETON = "\ue000"


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


def lire_plan(octets: bytes) -> str:
    """Le texte d'un plan, en LF, sans BOM : en UTF-16 s'il commence par un BOM UTF-16, sinon en
    UTF-8, chaque octet qui n'est pas de l'UTF-8 remplacé."""
    if octets.startswith((b"\xff\xfe", b"\xfe\xff")):
        texte = octets.decode("utf-16", errors="replace")
    else:
        texte = octets.decode("utf-8", errors="replace")
    return _documentation()._en_lf(texte.removeprefix("\ufeff"))


def lieu(texte: str) -> tuple[str | None, str, int, int]:
    """Le lieu d'un mécanisme, `[<dépôt>:]<chemin>:<ligne>[-<fin>]` : (préfixe ou `None`, chemin,
    début, fin). Lève `ValueError`, avec la raison, avant de construire le moindre `Path`."""
    morceaux = texte.split(":")
    if len(morceaux) == 3 and _NOM.fullmatch(morceaux[0]):
        prefixe, chemin, lignes = morceaux
    elif len(morceaux) == 2:
        prefixe, (chemin, lignes) = None, morceaux
    elif len(morceaux) < 2:
        raise ValueError("ligne invalide")
    else:
        raise ValueError("deux-points dans le chemin")
    if not chemin:
        raise ValueError("ligne invalide")
    if chemin.startswith("/"):
        raise ValueError("chemin absolu")
    if "\\" in chemin:
        raise ValueError("barre oblique inverse")
    if ".." in chemin.split("/"):
        raise ValueError("..")
    m = _LIGNES.fullmatch(lignes)
    if m is None:
        raise ValueError("ligne invalide")
    debut = int(m.group(1))
    fin = int(m.group(2) or debut)
    if fin < debut:
        raise ValueError("ligne invalide")
    if fin - debut + 1 > PLAGE_MAX:
        raise ValueError(f"plage de plus de {PLAGE_MAX} lignes")
    return prefixe, chemin, debut, fin


def _chemin_du_plan_maitre(chemin: str) -> str | None:
    """La raison du refus du chemin d'une ligne `Plan maître :`, ou `None`. Les quatre premières
    raisons sont celles de `lieu()`, et viennent avant le moindre `Path`."""
    if ":" in chemin:
        return "deux-points dans le chemin"
    if chemin.startswith("/"):
        return "chemin absolu"
    if "\\" in chemin:
        return "barre oblique inverse"
    if ".." in chemin.split("/"):
        return ".."
    if not chemin.startswith(PLANS):
        return f"hors de {PLANS}"
    if not chemin.endswith(".md"):
        return "sans .md"
    return None


def _replier(texte: str) -> str:
    """Le texte en NFC, apostrophes droites et espaces ordinaires, sans égard à la casse, code en
    ligne compris : `_normaliser` laisse le code tel quel, pas cette fonction."""
    return unicodedata.normalize("NFC", texte).translate(_TRADUCTION).casefold()


def _mot(mot: str) -> re.Pattern:
    """L'expression d'un mot de `--cloture`, déjà replié : ses mots échappés, joints par tout blanc,
    retour à la ligne compris, sans lettre, chiffre ni `_` juste avant ni juste après."""
    return re.compile(r"(?<!\w)" + r"\s+".join(map(re.escape, mot.split())) + r"(?!\w)")


def _normaliser(texte: str, doc) -> str:
    """Le texte, hors du code en ligne, en NFC, apostrophes droites et espaces ordinaires."""
    morceaux = []
    debut = 0
    for m in doc.CODE_EN_LIGNE.finditer(texte):
        morceaux.append(unicodedata.normalize("NFC", texte[debut : m.start()]))
        morceaux.append(m.group(0))
        debut = m.end()
    morceaux.append(unicodedata.normalize("NFC", texte[debut:]))
    return "".join(
        morceau if i % 2 else morceau.translate(_TRADUCTION) for i, morceau in enumerate(morceaux)
    )


def _lire_section(
    brute: str, doc
) -> tuple[list[tuple[int, str]], list[int], list[int], int | None]:
    """Les lignes d'une section : (puces, chacune avec son rang et ses lignes de continuation
    jointes ; rangs des « Aucun. » ; rangs des lignes refusées ; rang d'un `<!--` jamais fermé, ou
    `None`). Ce `<!--` refuse sa ligne, à part des lignes refusées, et cache la suite. Une
    sous-liste, ou une ligne ouverte par un commentaire puis portant un texte, que GitHub rend en
    bloc HTML, ne continue pas la puce d'avant : elle refuse."""
    propre = doc.sans_bloc_ni_commentaire(brute)
    masque = doc.CODE_EN_LIGNE.sub(lambda m: re.sub(r"[^\n]", "x", m.group(0)), propre)
    en_bloc_html = doc.lignes_en_bloc_html(brute)
    puces: list[tuple[int, list[str]]] = []
    aucuns: list[int] = []
    refusees: list[int] = []
    ouvert = None
    ouverte = False
    lignes = zip(_normaliser(propre, doc).split("\n"), masque.split("\n"))
    for rang, (ligne, hors_du_code) in enumerate(lignes, start=1):
        if "<!--" in hors_du_code:
            ouvert = rang
            break
        if not ligne.strip():
            continue
        if rang in en_bloc_html:
            pass
        elif ligne[0] in " \t":  # une ligne indentée continue la puce d'avant, sauf une sous-liste
            if ouverte and doc.SOUS_LISTE.match(ligne) is None:
                puces[-1][1].append(ligne.strip())
                continue
        elif ligne.rstrip() == AUCUN:
            aucuns.append(rang)
            ouverte = False
            continue
        elif (m := _PUCE.match(ligne)) is not None:
            puces.append((rang, [ligne[m.end() :].strip()]))
            ouverte = True
            continue
        ouverte = False
        refusees.append(rang)
    return [(rang, " ".join(morceaux)) for rang, morceaux in puces], aucuns, refusees, ouvert


def _code_en_ligne(texte: str, position: int, doc) -> tuple[str, int] | None:
    """Le code en ligne qui commence à `position` : (contenu, fin), ou `None`."""
    m = doc.CODE_EN_LIGNE.match(texte, position)
    if m is None:
        return None
    n = len(m.group(1))
    contenu = m.group(0)[n:-n]
    if contenu.startswith(" ") and contenu.endswith(" ") and contenu.strip(" "):
        contenu = contenu[1:-1]
    return contenu, m.end()


def _lieu_et_extrait(texte: str, doc) -> tuple[str, str] | None:
    """Le lieu et l'extrait d'une ligne de mécanisme, ou `None` si elle n'a pas sa forme : un code
    en ligne, un séparateur, un code en ligne non blanc, un séparateur, un texte."""
    premier = _code_en_ligne(texte, 0, doc)
    if premier is None:
        return None
    texte_du_lieu, fin = premier
    separateur = _SEPARATEUR.match(texte, fin)
    if separateur is None:
        return None
    second = _code_en_ligne(texte, separateur.end(), doc)
    if second is None:
        return None
    extrait, fin = second
    separateur = _SEPARATEUR.match(texte, fin)
    if separateur is None or not texte[separateur.end() :].strip() or not extrait.strip():
        return None
    return texte_du_lieu, extrait


def _couper(texte: str, n: int, doc) -> list[str]:
    """Le texte coupé à ses `n` premiers séparateurs, hors du code en ligne."""
    masque = doc.CODE_EN_LIGNE.sub(lambda m: "x" * len(m.group(0)), texte)
    morceaux = []
    debut = 0
    for m in _SEPARATEUR.finditer(masque):
        if len(morceaux) == n:
            break
        morceaux.append(texte[debut : m.start()])
        debut = m.end()
    morceaux.append(texte[debut:])
    return morceaux


def _octets_du_fichier(base: Path, chemin: str, resolues: dict[Path, Path]) -> bytes | None:
    """Les octets du fichier `chemin` sous `base` ; `None` s'il n'est pas un fichier, ou s'il sort
    de `base` une fois résolu."""
    try:
        if base not in resolues:
            resolues[base] = base.resolve()
        racine = resolues[base]
        fichier = (racine / chemin).resolve()
        if not fichier.is_relative_to(racine) or not fichier.is_file():
            return None
        return fichier.read_bytes()
    except (OSError, RuntimeError, ValueError):
        return None


def _lignes_du_fichier(base: Path, chemin: str, resolues: dict[Path, Path]) -> list[str] | None:
    """Les lignes du fichier `chemin` sous `base`, comptées par `\\n` ; `None` s'il n'est pas un
    fichier, ou s'il sort de `base` une fois résolu."""
    octets = _octets_du_fichier(base, chemin, resolues)
    if octets is None:
        return None
    texte = octets.decode("utf-8", errors="replace").removeprefix("\ufeff").replace("\r\n", "\n")
    lignes = texte.split("\n")
    if lignes[-1] == "":
        lignes.pop()
    return lignes


def _mecanisme(
    texte: str, racine: Path, depots: dict[str, Path], lieux: bool, doc, resolues: dict[Path, Path]
) -> tuple[str, str | None]:
    """Une ligne de mécanisme : (« vérifié », « non vérifié » ou « refus » ; message)."""
    lu = _lieu_et_extrait(texte, doc)
    if lu is None:
        return "refus", FORMES[MECANISMES]
    texte_du_lieu, extrait = lu
    try:
        prefixe, chemin, debut, fin = lieu(texte_du_lieu)
    except ValueError as raison:
        return "refus", f"chemin refusé ({raison})"
    if not lieux:
        return "vérifié", None
    if prefixe is not None and prefixe not in depots:
        return "non vérifié", f"non vérifié (dépôt {doc._affichable(prefixe)} absent)"
    base = racine if prefixe is None else depots[prefixe]
    lignes = _lignes_du_fichier(base, chemin, resolues)
    if lignes is None:
        return "refus", f"fichier absent : {doc._affichable(texte_du_lieu.rsplit(':', 1)[0])}"
    if fin > len(lignes):
        return "refus", f"ligne {fin} hors du fichier ({len(lignes)} lignes)"
    cherche = unicodedata.normalize("NFC", extrait)
    if any(cherche in unicodedata.normalize("NFC", ligne) for ligne in lignes[debut - 1 : fin]):
        return "vérifié", None
    return "refus", f"extrait absent de {doc._affichable(texte_du_lieu)}"


def _unites(texte: str, doc) -> list[tuple[str, int, str]]:
    """Les unités du plan, dans l'ordre : (sorte, `TACHE` ou `TRANCHE` ; numéro ; titre replié),
    d'après les titres de niveau 3 lus hors des blocs de code clôturés et des blocs de commentaire
    HTML, fermés ou non. Comme dans `sections()`, chaque bloc se retire, ses fins de ligne gardées :
    un `<!--` jamais fermé qui ouvre un bloc cache tout ce qui le suit, comme sur GitHub."""
    return [(sorte, numero, titre) for _, sorte, numero, titre in _titres_d_unites(texte, doc)]


def _visibles(texte: str, doc) -> list[str]:
    """Les lignes du texte en LF, comme `sections()` y lit les titres : chaque ligne d'un bloc de
    code clôturé et d'un bloc de commentaire vidée, leur nombre gardé."""
    visibles = doc._BLOC_DE_COMMENTAIRE.sub(
        lambda m: "\n" * m.group(0).count("\n"), doc._hors_des_blocs(doc._en_lf(texte))
    )
    return visibles.split("\n")


def _titres_d_unites(texte: str, doc) -> list[tuple[int, str, int, str]]:
    """Les unités de `_unites`, chacune précédée du rang de sa ligne dans le texte, la première
    ligne au rang 0."""
    lignes = doc.sans_bloc_ni_commentaire("\n".join(_visibles(texte, doc))).split("\n")
    titres = []
    for i, ligne in enumerate(lignes):
        ligne = unicodedata.normalize("NFC", ligne)
        m = _TITRE.match(ligne)
        if m is not None:
            sorte = TRANCHE if m.group(1).casefold() == "tranche" else TACHE
            titres.append((i, sorte, int(m.group(2)), ligne.casefold()))
    return titres


def _dit_cloture(titre: str) -> bool:
    """Le titre replié d'une unité dit la clôture : « clôture » ou « closure ». `verifier` et
    `_texte_de_cloture` reconnaissent l'unité de clôture par lui seul."""
    return any(mot in titre for mot in _CLOTURE)


def _texte_de_cloture(texte: str, doc) -> tuple[str, int | None] | None:
    """Le texte de l'unité de clôture, replié, et le rang dans le plan, la première ligne au rang 1,
    d'un `<!--` jamais fermé qu'elle porte, ou `None` ; `None` sans unité de clôture.

    Le texte va de la ligne du titre à celle qui précède le titre suivant de niveau 1 à 3, lu comme
    dans `sections()`, ou à la fin du plan. Il se prend sur les lignes d'origine : chaque bloc de
    code clôturé y tient la place d'un jeton, les commentaires fermés se retirent, puis seuls
    reviennent les blocs dont le jeton a survécu. Un `<!--` dans un bloc de code ne retire rien ; un
    bloc pris dans un commentaire retiré ne revient pas. Un `<!--` jamais fermé, hors du code,
    cache la suite : le texte s'arrête à lui."""
    texte = doc._en_lf(texte)
    lignes = texte.split("\n")
    debut = next(
        (i for i, _, _, titre in _titres_d_unites(texte, doc) if _dit_cloture(titre)), None
    )
    if debut is None:
        return None
    visibles = _visibles(texte, doc)
    fin = len(lignes)
    for j in range(debut + 1, len(lignes)):
        m = doc._TITRE.match(visibles[j])
        if m is not None and len(m.group(1)) <= 3:
            fin = j
            break
    # `_hors_des_blocs` ne vide que les lignes des blocs : marquées, les lignes vides le disent
    marquees = doc._hors_des_blocs("\n".join(ligne or _JETON for ligne in lignes)).split("\n")
    morceaux: list[str] = []
    blocs: dict[int, list[str]] = {}
    i = debut
    while i < fin:
        if marquees[i]:
            morceaux.append(lignes[i])
            i += 1
            continue
        j = i
        while j < fin and not marquees[j]:
            j += 1
        blocs[len(morceaux)] = lignes[i:j]
        morceaux += [_JETON] + [""] * (j - i - 1)
        i = j
    propre = doc.sans_bloc_ni_commentaire("\n".join(morceaux))
    masque = doc.CODE_EN_LIGNE.sub(lambda m: re.sub(r"[^\n]", "x", m.group(0)), propre)
    ouvert = None
    position = masque.find("<!--")
    if position >= 0:
        ouvert = debut + masque.count("\n", 0, position) + 1
        propre = propre[:position]
    rendues = propre.split("\n")
    for rang, bloc in blocs.items():
        if rang < len(rendues) and rendues[rang] == _JETON:
            rendues[rang] = "\n".join(bloc)
    return _replier("\n".join(rendues)), ouvert


def _declarations(texte: str, doc) -> tuple[list[str], list[str]]:
    """Les valeurs des lignes `Plan maître :`, le contenu de leur code en ligne, s'il est seul
    après les deux-points, ou `""`, et `Hors lot :`, leur raison, vide ou non. Elles se lisent avant
    la première unité, hors des blocs de code et des commentaires, jusqu'à trois espaces en tête."""
    titres = _titres_d_unites(texte, doc)
    lignes = doc.sans_bloc_ni_commentaire("\n".join(_visibles(texte, doc))).split("\n")
    maitres: list[str] = []
    hors_lot: list[str] = []
    for ligne in lignes[: titres[0][0] if titres else len(lignes)]:
        m = _DECLARATION.match(_normaliser(ligne, doc))
        if m is None:
            continue
        valeur = m.group(3)
        if m.group(2).casefold() == "hors lot":
            hors_lot.append(valeur)
            continue
        code = _code_en_ligne(valeur, 0, doc)
        maitres.append(code[0] if code is not None and not valeur[code[1] :].strip() else "")
    return maitres, hors_lot


def _verifier_declarations(
    maitres: list[str],
    hors_lot: list[str],
    est_maitre: bool,
    racine: Path,
    lieux: bool,
    doc,
    resolues: dict[Path, Path],
) -> tuple[list[str], bool]:
    """Les lignes déclarées : (refus, dispense). Un plan qui en porte une est dispensé d'unité de
    clôture et de gestes, sauf un plan maître, qui ne peut en porter aucune. La cible d'une ligne
    `Plan maître :` ne se lit que lieux ouverts, et son chemin refuse avant toute lecture."""
    if not maitres and not hors_lot:
        return [], False
    if est_maitre:
        refus = []
        if maitres:
            refus.append(MAITRE_DANS_UN_MAITRE)
        if hors_lot:
            refus.append(HORS_LOT_DANS_UN_MAITRE)
        return refus, False
    if maitres and hors_lot:
        return [LES_DEUX_LIGNES], True
    if len(maitres) > 1:
        return [MAITRE_EN_DOUBLE], True
    if len(hors_lot) > 1:
        return [HORS_LOT_EN_DOUBLE], True
    if hors_lot:
        return ([] if hors_lot[0] else [HORS_LOT_SANS_RAISON]), True
    (chemin,) = maitres
    if not chemin:
        return [MAITRE_SANS_CHEMIN], True
    raison = _chemin_du_plan_maitre(chemin)
    if raison is not None:
        return [f"chemin du plan maître refusé ({raison})"], True
    if not lieux:
        return [], True
    octets = _octets_du_fichier(racine, chemin, resolues)
    if octets is None:
        return [f"plan maître absent : {doc._affichable(chemin)}"], True
    sortes = {sorte for sorte, _, _ in _unites(lire_plan(octets), doc)}
    if sortes != {TRANCHE}:
        return [f"{doc._affichable(chemin)} n'est pas un plan maître"], True
    return [], True


def _verifier_cloture(
    texte: str,
    unites: list[tuple[str, int, str]],
    rang_cloture: int | None,
    cloture: tuple[str, ...],
    doc,
) -> list[str]:
    """Les refus de l'unité de clôture : son absence, un `<!--` jamais fermé, puis les gestes et les
    mots de `cloture` qu'elle ne nomme pas, dans l'ordre de `GESTES` puis des mots."""
    if rang_cloture is None:
        return [AUCUNE_CLOTURE]
    # `rang_cloture` et `_texte_de_cloture` ne peuvent viser deux unités : c'est la même recherche,
    # la première unité de `_titres_d_unites` dont `_dit_cloture` accepte le titre, sur le même
    # texte en LF (`_unites` en dérive, et `_en_lf` laisse tel quel un texte déjà en LF)
    texte_de_cloture, ouvert = _texte_de_cloture(texte, doc)
    sorte, numero, _ = unites[rang_cloture]
    refus = []
    if ouvert is not None:
        refus.append(f"clôture ({sorte} {numero}) : {COMMENTAIRE_OUVERT}")
    manquants = [nom for nom, motif in GESTES.items() if not re.search(motif, texte_de_cloture)]
    manquants += [
        f"« {doc._affichable(mot)} »" for mot in cloture if not _mot(mot).search(texte_de_cloture)
    ]
    if manquants:
        refus.append(f"clôture ({sorte} {numero}) : gestes non nommés : {', '.join(manquants)}")
    return refus


def verifier(
    texte: str,
    racine: Path,
    depots: dict[str, Path],
    lieux: bool = True,
    neuf: bool = False,
    cloture: tuple[str, ...] = (),
) -> tuple[list[str], bool]:
    """Les sections d'un plan, puis sa clôture : (lignes, refus). La dernière ligne est le résumé.
    Avec `lieux=False`, la forme de chaque lieu se vérifie par `lieu()`, sans ouvrir de fichier, et
    la cible d'une ligne `Plan maître :` n'est pas lue. Avec `neuf`, « Effets cherchés » est
    exigée. Avec `neuf`, ou la section présente, l'unité de clôture nomme les gestes et chaque mot
    de `cloture`, sauf dans un plan de tranche ou un plan hors lot. `cloture` : des mots déjà
    repliés par `_replier`, sans blanc autour, comme `main` les passe."""
    doc = _documentation()
    texte = doc._en_lf(texte)
    lignes: list[str] = []
    refus = False
    resolues: dict[Path, Path] = {}
    comptes = {"vérifié": 0, "non vérifié": 0, OUTILS: 0, EFFETS: 0, REVUES: 0}
    unites = _unites(texte, doc)
    sortes = {sorte for sorte, _, _ in unites}
    mele = len(sortes) == 2
    # un plan maître a des tranches et aucune tâche ; un plan sans unité est un plan à tâches
    if mele:
        citees = (TACHE, TRANCHE)
    else:
        citees = (TRANCHE,) if sortes == {TRANCHE} else (TACHE,)
    rang_cloture = next((i for i, (_, _, titre) in enumerate(unites) if _dit_cloture(titre)), None)

    def revue(ligne: str) -> list[str]:
        cites = []
        for sorte in citees:
            motif = _CITATION if sorte == TACHE else _CITATION_DE_TRANCHE
            cites += [(sorte, int(m.group(1))) for m in motif.finditer(ligne)]
        cites = list(dict.fromkeys(cites))
        if not cites:
            return [AUCUNE_CITATION[citees]]
        motifs = []
        for sorte, n in cites:
            rang = next((i for i, (s, num, _) in enumerate(unites) if (s, num) == (sorte, n)), None)
            if rang is None:
                motifs.append(f"{sorte} {n} absente des titres")
            elif rang_cloture is not None and rang >= rang_cloture:
                sorte_cloture, numero_cloture, _ = unites[rang_cloture]
                motifs.append(
                    f"{sorte} {n} ne précède pas la clôture ({sorte_cloture} {numero_cloture})"
                )
        return motifs

    effets_presents = False
    for titre in (MECANISMES, OUTILS, EFFETS, REVUES):
        morceaux = doc.sections(texte, titre, niveau=2, bornee=True)
        if titre == EFFETS:
            effets_presents = bool(morceaux)
        if not morceaux:
            if titre == EFFETS and not neuf:
                continue
            lignes.append(f"section « {titre} » absente (titre de niveau 2)")
            refus = True
            continue
        if len(morceaux) > 1:  # jointes, les lignes de la seconde auraient un rang faux
            lignes.append(f"section « {titre} » en double")
            refus = True
            continue
        puces, aucuns, refusees, ouvert = _lire_section(morceaux[0], doc)
        if not (puces or aucuns or refusees or ouvert is not None):
            lignes.append(f"section « {titre} » vide")
            refus = True
            continue
        # « Aucun. » n'est admis que seul, et jamais dans « Revues »
        constats = [(rang, FORMES[titre], True) for rang in refusees]
        if puces or titre == REVUES:
            constats += [(rang, FORMES[titre], True) for rang in aucuns]
        if ouvert is not None:
            constats.append((ouvert, COMMENTAIRE_OUVERT, True))
        for rang, ligne in puces:
            if titre == MECANISMES:
                etat, message = _mecanisme(ligne, racine, depots, lieux, doc, resolues)
                if etat == "refus":
                    constats.append((rang, message, True))
                else:
                    comptes[etat] += 1
                    if message is not None:
                        constats.append((rang, message, False))
            elif titre in (OUTILS, EFFETS):
                # une espace devant : un séparateur en tête laisse un premier morceau vide
                morceaux = _couper(" " + ligne, 2, doc)
                if len(morceaux) == 3 and all(morceau.strip() for morceau in morceaux):
                    comptes[titre] += 1
                else:
                    constats.append((rang, FORMES[titre], True))
            else:
                motifs = revue(ligne)
                constats += [(rang, motif, True) for motif in motifs]
                comptes[REVUES] += not motifs
        for rang, message, refuse in sorted(constats, key=lambda c: c[0]):
            lignes.append(f"{titre}, ligne {rang} : {message}")
            refus = refus or refuse
    # la clôture, la ligne `Hors lot :` et la ligne `Plan maître :` : d'un plan neuf, ou né sous
    # ces règles, que la section dit
    if neuf or effets_presents:
        maitres, hors_lot = _declarations(texte, doc)
        messages, dispense = _verifier_declarations(
            maitres, hors_lot, sortes == {TRANCHE}, racine, lieux, doc, resolues
        )
        if not dispense:
            messages += _verifier_cloture(texte, unites, rang_cloture, cloture, doc)
        lignes += messages
        refus = refus or bool(messages)
    numeros = [(sorte, numero) for sorte, numero, _ in unites]
    for sorte, n in sorted({u for u in numeros if numeros.count(u) > 1}):
        lignes.append(f"{sorte} {n} en double")
        refus = True
    if mele:
        lignes.append(MELE)
        refus = True
    if lieux:
        tete = f"{comptes['vérifié']} mécanismes vérifiés, {comptes['non vérifié']} non vérifiés"
    else:
        tete = f"{comptes['vérifié']} mécanismes, lieux non ouverts"
    lignes.append(
        f"{tete}, {comptes[OUTILS]} outils, {comptes[EFFETS]} effets, {comptes[REVUES]} revues"
    )
    return lignes, refus


class _Analyseur(argparse.ArgumentParser):
    def error(self, message: str):  # le message reçu pourrait citer l'entrée : on ne l'affiche pas
        self.exit(EXIT_USAGE, "plan : usage invalide (voir --help)\n")


def _usage(raison: str) -> int:
    print(f"{PREFIXE}usage invalide : {raison} (voir --help)", file=sys.stderr)
    return EXIT_USAGE


def main(argv: list[str] | None = None) -> int:
    for flux in (sys.stdout, sys.stderr):
        try:
            flux.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
        except (AttributeError, ValueError):
            pass
    p = _Analyseur(
        prog="plan.py",
        description=(
            "Les sections d'un plan : mécanismes annoncés, outils et cas limites, effets cherchés, "
            "revues ; puis sa clôture et ses lignes « Plan maître : » et « Hors lot : »."
        ),
    )
    p.add_argument("plan", metavar="PLAN", help="le plan, lu où qu'il soit")
    p.add_argument(
        "--racine",
        type=Path,
        default=Path("."),
        metavar="DOSSIER",
        help="d'où partent les chemins sans préfixe (défaut : le dossier courant)",
    )
    p.add_argument(
        "--depot",
        action="append",
        default=[],
        metavar="NOM=CLONE",
        help="d'où partent les chemins préfixés par NOM ; à répéter",
    )
    p.add_argument(
        "--sans-lieux",
        action="store_true",
        help="la forme de chaque lieu, sans ouvrir de fichier (un plan modifié)",
    )
    p.add_argument(
        "--neuf",
        action="store_true",
        help="un plan neuf : « Effets cherchés » et la clôture exigées",
    )
    p.add_argument(
        "--cloture",
        action="append",
        default=[],
        metavar="MOT",
        help="un mot, ou une suite de mots, que la clôture doit nommer ; à répéter",
    )
    try:
        args = p.parse_args(argv)
    except SystemExit as sortie:
        return 0 if sortie.code in (0, None) else EXIT_USAGE
    doc = _documentation()
    depots: dict[str, Path] = {}
    for valeur in args.depot:
        nom, egal, clone = valeur.partition("=")
        if not egal or not clone or _NOM.fullmatch(nom) is None:
            return _usage("--depot NOM=CLONE attendu")
        if not Path(clone).is_dir():
            return _usage(f"clone de {nom} introuvable")
        depots[nom] = Path(clone)
    if not args.racine.is_dir():
        return _usage("racine introuvable")
    mots = tuple(_replier(mot).strip() for mot in args.cloture)
    if not all(mots):
        return _usage("--cloture MOT attendu")
    nom_du_plan = doc._affichable(args.plan)
    try:
        octets = Path(args.plan).read_bytes()
    except OSError:
        return _usage(f"plan illisible : {nom_du_plan}")
    lignes, refus = verifier(
        lire_plan(octets), args.racine, depots, not args.sans_lieux, args.neuf, mots
    )
    for ligne in lignes:
        print(f"{PREFIXE}{nom_du_plan} : {ligne}")
    if refus:
        print(PREFIXE + "refus")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

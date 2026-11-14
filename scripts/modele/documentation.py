"""La documentation de la racine : la licence et la carte, deux contrôles qui refusent en CI, et le
gabarit resté vide, qui avertit au démarrage d'une session.

La licence. En nature `code`, `LICENSE` doit être présent à la racine, sous ce nom exact, et non
vide, et, à la racine d'un dépôt git, suivi par git, comme dans le commit que lit la CI : un
`LICENSE` qu'un `copier update` vient de créer refuse tant qu'il n'est pas indexé. En nature
`donnees`, il n'est pas exigé. La nature se lit comme la lit la porte de confidentialité, par
`nature()` de `confidentialite.py` : en CI, un dépôt public est de code, et un dépôt privé prend la
nature de sa branche par défaut, jamais celle de la PR ; hors CI, c'est le `reglages.py` voisin, et
`code` sans lui.

La carte. Chaque fichier `.md` de la racine, sauf `README.md`, doit être lié par un lien Markdown :
`CLAUDE.md` depuis `README.md`, un autre depuis `README.md` ou depuis la section « Ce qui fait foi »
de `CLAUDE.md` (jusqu'au titre suivant de même niveau ou d'un niveau supérieur). Un nom entre
accents graves ne suffit pas : on ne peut pas le suivre. `README.md` et `CLAUDE.md` doivent exister.
La sortie dit le nombre de fichiers vus, puis nomme chaque fichier non lié. À la racine d'un dépôt
git, les fichiers vus sont ceux que git suit ou suivrait : un fichier qu'il ignore n'est pas compté
(`CLAUDE.local.md`, que le `.gitignore` semé exclut ; un projet né plus tôt l'y ajoute). Ailleurs,
c'est tout le dossier.

Lancé sur le poste, depuis la racine, le script donne les lignes de la CI, à trois écarts près : un
`.md` de la racine non suivi compte en local, et la CI ne le voit pas ; le README et `CLAUDE.md` se
lisent tels qu'ils sont dans la copie, validés ou non ; la nature se lit dans la copie, alors qu'en
CI un dépôt privé prend celle de sa branche par défaut (la PR qui pose ou change la nature d'un
dépôt privé y est jugée sous l'ancienne). La licence, elle, ne compte en local qu'un `LICENSE`
suivi, comme la CI.

Le gabarit resté vide. Chaque fichier `.md` et chaque dossier que `README.md` lie, et qui existent
sous la racine, sont lus ; le reste est ignoré : une image, un script, un lien externe, une cible
absente ou hors de la racine. Trois règles, dont la première qui touche donne le constat d'un
chemin : un fichier qui garde le marqueur du gabarit, `*AAAA-MM-JJ*`, hors du code ; un fichier
dont le corps est vide, une fois retirés les titres (de `#` à `######`), les lignes vides, les
commentaires HTML et les lignes tout en italique (`*…*` ou `_…_`), une ligne d'un bloc de code
faisant un corps ; un dossier sans autre enfant que `README.md` et `.gitkeep`. Le registre (tout
`registre.md`, sans égard à la casse) et les plans (sous `.claude/plans/`) échappent aux trois
règles ; les fichiers d'ADR (sous `docs/decisions/` ou `docs/adr/`, sauf leur `README.md`), aux
deux premières, et leur dossier relève de la troisième. Les constats suivent l'ordre des liens, un
par chemin. Rien à signaler ne donne rien, sauf un README qui ne lie aucun document du dépôt, ou
pas de README. Ce contrôle ne refuse jamais et ne lance aucun sous-processus : `signaux.py` le
lance au `SessionStart`, jamais la CI.

Ce qui est un lien : un lien en ligne, `[…](cible)` ou `![…](cible)`, avec un titre ou des
chevrons, son texte sur plusieurs lignes ou entre crochets au besoin, une image cliquable donnant
ses deux cibles ; un lien de référence, `[texte][x]`, `[x][]` ou `[x]`, quand une définition
`[x]: cible` de son étiquette (sans égard à la casse ni aux blancs) est dans le même fichier, hors
d'une liste ou d'une citation, sa cible au besoin sur la ligne suivante. Comme sur GitHub, une
définition ne se rend pas : seule, elle ne lie rien, et une définition qui coupe un paragraphe n'en
est pas une. Pour « Ce qui fait foi », les emplois se lisent dans la section, les définitions dans
tout `CLAUDE.md`. Un lien HTML (`<a href="…">`) ne compte pas : la carte demande un lien Markdown,
et le remède est la forme `[texte](cible)`.
Les blocs de code clôturés, le code en ligne et les commentaires HTML sont retirés avant : GitHub
n'y rend aucun lien. La cible perd son ancre et sa requête, ses échappements (`\\.`), puis elle est
décodée (`%20`) ; un `/` en tête part de la racine ; une cible avec un schéma (`https:`, `mailto:`)
ou sans (`//hôte`), une ancre seule, une cible où reste une barre oblique inverse (GitHub ne la lit
pas comme un séparateur ; sous Windows, deux en tête nommeraient un partage réseau), sous Windows
une cible qui porte un deux-points (il y nomme un lecteur, en tête comme plus loin : `./Z:/x.md`,
`docs/Z:x.md` ; sous Linux, c'est un caractère comme un autre), ou une cible qui sort de la racine,
par `..` ou par un lien symbolique, n'est pas locale. Les chemins se comparent à la casse près,
comme sur GitHub ; un document est un fichier dont le suffixe est `.md`, sans égard à la casse. Un
texte en CRLF se lit comme en LF, un BOM en tête est ignoré, et un octet qui n'est pas de l'UTF-8
est remplacé, sans erreur.

Des écarts connus au rendu de GitHub, rares. Certains laissent passer à tort un lien que GitHub ne
rend pas : dans un bloc de code indenté, que GitHub rend en code ; dans un bloc clôturé à
l'intérieur d'une citation, ou d'un élément de liste indenté de quatre colonnes ou plus, s'il
s'ouvre par des tildes ou qu'une ligne vide le coupe ; dans un bloc HTML sans ligne vide
(`<details>` collé à son contenu) ; dans un bloc `<pre>`, `<script>`, `<style>` ou `<textarea>`,
lignes vides comprises, jusqu'à la fin de la ligne qui porte sa balise fermante ; dans un bloc
ouvert en tête de ligne par `<!--` (ou par `<?`, `<!DOCTYPE`, `<![CDATA[`), jusqu'à la fin de la
ligne qui le ferme (`<!-- liens --> [n](NOTICE.md)` ne lie rien), ou jusqu'à la fin du fichier
s'il ne se ferme jamais ; dans une citation ou un élément de liste, dans un bloc ouvert par
`<!--`, de même. Dans ces blocs, GitHub ne lit pas le Markdown. S'y ajoute un lien dont le texte
porte un `|` dans une cellule de tableau, que GitHub coupe. Les autres font refuser à tort. Un
titre souligné (`Ce qui fait foi` sur une ligne de `---`) n'est pas lu ; un accent grave échappé
(`` \\` ``) ouvre quand même un code en ligne ; une entité dans la cible (`&#46;`) n'est pas
décodée ; un fichier dont le nom porte une barre oblique inverse, que Windows refuse, n'est jamais
lié ; un commentaire HTML ouvert dans un paragraphe cache les liens jusqu'à sa fermeture, plus loin.
Une définition n'est pas lue quand elle suit une ligne de commentaire (`<!-- liens -->`, puis les
définitions), quand elle est dans un élément de liste ou dans une citation, quand elle suit une
ligne de séparation (`***`), ou quand son titre tient sur deux lignes ; et d'autres formes rares des
conteneurs et des commentaires (un bloc clôturé non fermé dans un élément de liste, un code en ligne
qui franchit une ligne `>` vide, un texte de lien à plus de trois niveaux de crochets, une
définition après un titre souligné, un commentaire fermé par `--->` dans un paragraphe) font aussi
refuser à tort.
D'autres laissent passer à tort ce que GitHub cache, et touchent aussi `texte_pr.py` et `plan.py`,
qui s'appuient sur ce script ; deux sont connus : un `<!--` jamais fermé, ouvert dans un élément de
liste après quatre espaces ou plus (une puce imbriquée, ou une ligne qui continue la puce), cache
sur GitHub tout ce qui le suit, mais les contrôles lisent encore la suite : un titre, et donc la
section « Ce qui fait foi », la section des écarts à la spec, les trois sections d'un plan et ses
titres de tâche ou de tranche, et la ligne « Tête relue », qui doit toujours nommer la tête de la
PR ; un bloc ouvert en tête de ligne par `<?`, par `<!` suivi d'une majuscule (`<!DOCTYPE`) ou par
`<![CDATA[` cache de même sur GitHub tout ce qui le suit jusqu'au premier `>`, même plusieurs lignes
plus bas, ou jusqu'à la fin sans lui, mais `texte_pr.py` et `plan.py`, qui ne cherchent que `<!--`,
lisent encore la ligne « Tête relue », la section des écarts, les trois sections d'un plan et ses
titres de tâche ou de tranche. D'autres formes HTML cachent aussi sur GitHub ce que les contrôles
lisent : un `<?` ou un `<!DOCTYPE` après une puce, ou en ligne et fermé plus bas ; un `<!--` jamais
fermé dans une ligne de bloc HTML, comme `<div><!-- note</div>` ; un attribut ou un titre de lien
sur plusieurs lignes.
Un dernier ne touche que le gabarit resté vide. Sous Windows, il lit l'existence d'un chemin lié
sans égard à la casse : un lien `docs/Cadrage.md` vers `docs/cadrage.md` y est lu, et peut
avertir, alors que GitHub casse ce lien ; sous Linux, il est ignoré. C'est un avertissement de
trop, jamais un refus.

La sortie ne cite jamais le contenu d'un fichier, seulement des chemins, chaque caractère de
contrôle, séparateur de ligne ou de paragraphe (U+2028, U+2029) ou non décodable (un nom qui n'est
pas de l'UTF-8) remplacé par `?`.

Bibliothèque standard seule, Python 3.10 ou plus.

Usage : documentation.py [--racine DOSSIER] [--gabarits-vides]  (racine par défaut : le dossier
        courant ; la CI lance la licence et la carte depuis la racine du dépôt. --racine change
        les fichiers lus, pas la nature : hors CI, c'est celle du `reglages.py` voisin du
        script ; en CI, celle de la branche par défaut, lue dans le dossier courant.
        --gabarits-vides lance le seul gabarit resté vide, et imprime un constat par ligne)

Retour : 0 rien à signaler, 1 refus, 64 erreur d'usage ; avec --gabarits-vides, toujours 0, hors
         d'une erreur d'usage.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import unicodedata
from pathlib import Path
from urllib.parse import unquote

EXIT_USAGE = 64
PREFIXE = "documentation : "
CE_QUI_FAIT_FOI = "ce qui fait foi"
NON_LIE = "n'est lié ni par README.md ni par « Ce qui fait foi » de CLAUDE.md"

# --- ce qui est un lien ----------------------------------------------------------------------

_OUVERTURE = re.compile(r" {0,3}(`{3,}|~{3,})(.*)$")
_FERMETURE = re.compile(r" {0,3}(`{3,}|~{3,})[ \t]*$")
# Un commentaire HTML (`<!-->` et `<!--->` en sont deux, complets).
COMMENTAIRE = re.compile(r"<!--(?:-?>|.*?-->)", re.DOTALL)
# Un code en ligne : une suite d'accents graves, refermée par une suite de même longueur, sans
# franchir une ligne vide.
CODE_EN_LIGNE = re.compile(r"(?<!`)(`+)(?!`)(?:(?!\n[ \t]*\n).)*?(?<!`)\1(?!`)", re.DOTALL)
# L'un ou l'autre : le plus à gauche l'emporte, comme sur GitHub. Le groupe 1 n'est pris que par un
# code en ligne.
_CODE_OU_COMMENTAIRE = re.compile(COMMENTAIRE.pattern + "|" + CODE_EN_LIGNE.pattern, re.DOTALL)
_ECHAPPEMENT = re.compile(r"\\(.)", re.DOTALL)
# Un caractère du texte d'un lien : ni crochet, ni barre oblique inverse nue, ni ligne vide.
_CAR = r"(?:[^\[\]\\\n]|\\.|\n(?![ \t]*\n))"


def _crochets(profondeur: int) -> str:
    """Un texte entre crochets, où d'autres crochets s'emboîtent sur `profondeur` niveaux."""
    if profondeur == 0:
        return rf"\[{_CAR}*\]"
    return rf"\[(?:{_CAR}|{_crochets(profondeur - 1)})*\]"


_DESTINATION = (
    r"\(\s*(?:<(?P<chevrons>[^<>\n]*)>"
    r"|(?P<brute>(?!<)(?:[^\s()\\]|\\.|\((?:[^\s()\\]|\\.)*\))+))"
    r"(?:\s+(?:\"(?:[^\"\\]|\\.)*\"|'(?:[^'\\]|\\.)*'|\((?:[^()\\]|\\.)*\)))?\s*\)"
)
# Un texte entre crochets, suivi d'une destination (un lien en ligne), d'une étiquette (`[x]`, une
# référence pleine, ou `[]`, une référence repliée), ou de rien (une référence raccourcie).
_LIEN = re.compile(
    r"(?P<image>!?)(?P<texte>" + _crochets(3) + r")"
    r"(?:" + _DESTINATION + r"|\[(?P<etiquette>" + _CAR + r"*)\])?"
)
# Une définition de référence : son étiquette, sa cible (au besoin sur la ligne suivante), un
# titre facultatif, puis rien d'autre sur la ligne.
_DEFINITION = re.compile(
    r"^ {0,3}\[(?P<etiquette>(?!\^)(?:[^\[\]\\\n]|\\.)+)\]:[ \t]*(?:\n[ \t]*)?"
    r"(?:<(?P<chevrons>[^<>\n]*)>|(?P<brute>(?!<)\S+))"
    r"(?:(?:[ \t]+|[ \t]*\n[ \t]*)"
    r"(?:\"(?:[^\"\\\n]|\\.)*\"|'(?:[^'\\\n]|\\.)*'|\((?:[^()\\\n]|\\.)*\)))?[ \t]*$",
    re.MULTILINE,
)
_SCHEMA = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*:")
_PONCTUATION_ECHAPPEE = re.compile(r"\\([!-/:-@\[-`{-~])")
_TITRE = re.compile(r" {0,3}(#{1,6})(?:[ \t]+(.*?))?[ \t]*$")
_FERMANTE = re.compile(r"(?:^|[ \t]+)#+$")
_COMMENTAIRE = re.compile(COMMENTAIRE.pattern)
# Ce qui peut précéder, sur sa ligne, un `<!--` qui ouvre un bloc de commentaire : au plus trois
# espaces, après une puce, un numéro ou `>`. À composer, en mode MULTILINE. Chaque espace n'a
# qu'une lecture : après `>`, une tabulation et trois espaces au plus, ou quatre espaces au plus ;
# après une puce ou un numéro, toutes les espaces et tabulations. Un motif où l'espace qui suit un
# `>` se prendrait aussi par le tour suivant reculerait de façon exponentielle sur une ligne de `> `
# sans `<!--`, et Python 3.10 n'a pas de groupe atomique.
DEBUT_DE_BLOC = r"^ {0,3}(?:>(?:\t {0,3}| {0,4})|(?:[-*+]|\d{1,9}[.)])[ \t]+)*"
# Un bloc de commentaire HTML : ouvert par `<!--` en tête de ligne, ou après une puce, un numéro ou
# `>`, il court jusqu'à la fin de la ligne qui porte `-->`, la sienne comprise (`<!-->` se ferme
# aussitôt), ou jusqu'à la fin.
_BLOC_DE_COMMENTAIRE = re.compile(
    DEBUT_DE_BLOC + r"<!(?=--).*?(?:-->[^\n]*|\Z)", re.MULTILINE | re.DOTALL
)
# Un commentaire ouvert en tête de ligne, après au plus trois espaces : GitHub rend en bloc HTML la
# ligne qui le ferme, son texte tel quel, jamais en puce ni en suite de puce.
_COMMENTAIRE_EN_TETE = re.compile(
    r"^ {0,3}(?:" + COMMENTAIRE.pattern + ")", re.MULTILINE | re.DOTALL
)
# Une sous-liste : une ligne indentée qui commence par une puce ou par un numéro. `texte_pr.py` et
# `plan.py` la refusent toujours, plus strictement que GitHub, qui joint à la puce d'avant un
# numéro autre que 1 et une ligne indentée de quatre colonnes ou plus au-delà du texte de la puce.
SOUS_LISTE = re.compile(r"[ \t]+(?:[-*+]|[0-9]{1,9}[.)])(?:[ \t]|$)")


def _en_lf(texte: str) -> str:
    return texte.replace("\r\n", "\n").replace("\r", "\n")


def _hors_des_blocs(texte: str) -> str:
    """Le texte, chaque ligne d'un bloc de code clôturé vidée : le nombre de lignes ne change pas.
    Un bloc se ferme par une clôture du même caractère, au moins aussi longue ; sans elle, il court
    jusqu'à la fin. Une suite d'accents graves suivie d'un autre accent grave n'ouvre rien."""
    lignes = texte.split("\n")
    cloture: tuple[str, int] | None = None
    for i, ligne in enumerate(lignes):
        if cloture is None:
            ouverture = _OUVERTURE.match(ligne)
            if ouverture is None:
                continue
            suite = ouverture.group(1)
            if suite[0] == "`" and "`" in ouverture.group(2):
                continue
            cloture = (suite[0], len(suite))
        else:
            fermeture = _FERMETURE.match(ligne)
            suite = fermeture.group(1) if fermeture else ""
            if suite[:1] == cloture[0] and len(suite) >= cloture[1]:
                cloture = None
        lignes[i] = ""
    return "\n".join(lignes)


def _sans_code_ni_commentaire(texte: str) -> str:
    """Chaque code en ligne et chaque commentaire HTML remplacés par des `x`, ses fins de ligne
    gardées ; chaque crochet échappé (`\\[`) remplacé de même, une barre oblique inverse échappée
    comprise."""
    texte = _CODE_OU_COMMENTAIRE.sub(lambda m: re.sub(r"[^\n]", "x", m.group(0)), texte)
    return _ECHAPPEMENT.sub(lambda m: "xx" if m.group(1) in "[]" else m.group(0), texte)


def _preparer(texte: str) -> str:
    return _sans_code_ni_commentaire(_hors_des_blocs(_en_lf(texte)))


def sans_bloc_ni_commentaire(texte: str) -> str:
    """Le texte en LF, chaque ligne d'un bloc de code clôturé vidée et chaque commentaire HTML fermé
    retiré, leurs fins de ligne gardées : le nombre de lignes ne change pas. Un code en ligne reste,
    et protège le `<!--` qu'il contiendrait ; un `<!--` jamais fermé reste du texte."""
    return _CODE_OU_COMMENTAIRE.sub(
        lambda m: m.group(0) if m.group(1) else "\n" * m.group(0).count("\n"),
        _hors_des_blocs(_en_lf(texte)),
    )


def lignes_en_bloc_html(texte: str) -> set[int]:
    """Les rangs, la première ligne du texte au rang 1, des lignes qui ferment un commentaire
    ouvert en tête de ligne, après au plus trois espaces : GitHub rend une telle ligne en bloc HTML,
    et un texte après la fermeture n'y est ni une puce ni la suite d'une puce. Une ligne d'un bloc
    de code clôturé peut y être : au lecteur de l'écarter."""
    texte = _en_lf(texte)
    return {texte.count("\n", 0, m.end()) + 1 for m in _COMMENTAIRE_EN_TETE.finditer(texte)}


def _cle(etiquette: str) -> str | None:
    """L'étiquette d'une référence, normalisée comme sur GitHub (casse et blancs repliés) ; `None`
    si elle ne peut pas en être une : blanche, ou de plus de 999 caractères. Une étiquette à
    crochets, ou une note (`^1`), n'est jamais définie : `_DEFINITION` les écarte."""
    if not etiquette.strip() or len(etiquette) > 999:
        return None
    return " ".join(etiquette.split()).casefold()


def _definitions(texte: str) -> tuple[dict[str, str], str]:
    """Les définitions de référence d'un texte préparé : {étiquette : cible}, la première
    l'emportant, puis le texte où chacune est remplacée par des `x`, ses fins de ligne gardées. Une
    définition n'interrompt pas un paragraphe : elle suit le début du texte, une ligne vide, un
    titre ou une autre définition ; sinon, comme sur GitHub, c'est du texte."""
    cibles: dict[str, str] = {}
    morceaux = []
    debut_libre = 0
    fin_precedente = -1
    for m in _DEFINITION.finditer(texte):
        debut = m.start()
        if debut > 0 and fin_precedente != debut - 1:
            avant = texte[texte.rfind("\n", 0, debut - 1) + 1 : debut - 1]
            if avant.strip() and not _TITRE.match(avant):
                continue
        cle = _cle(m.group("etiquette"))
        if cle is None:
            continue
        cible = m.group("chevrons") if m.group("chevrons") is not None else m.group("brute")
        cibles.setdefault(cle, cible)
        morceaux.append(texte[debut_libre:debut])
        morceaux.append(re.sub(r"[^\n]", "x", m.group(0)))
        debut_libre = fin_precedente = m.end()
    morceaux.append(texte[debut_libre:])
    return cibles, "".join(morceaux)


def _en_ligne(texte: str, definitions: dict[str, str]) -> list[tuple[str, bool]]:
    """Les liens d'un texte préparé, dans l'ordre : (cible, image ?). Une image dans le texte d'un
    lien compte, et le lien aussi ; un lien dans le texte d'un lien l'emporte, et le lien qui le
    contient n'en est pas un. Une référence pleine qui n'est pas un lien, son étiquette non
    définie ou son texte portant un lien, n'est que du texte, et son étiquette peut ouvrir un autre
    lien (`[a][x](cible)`, `[a [b](c) d][x]`)."""
    trouves: list[tuple[str, bool]] = []
    position = 0
    while (m := _LIEN.search(texte, position)) is not None:
        position = m.end()
        image = m.group("image") == "!"
        contenu = m.group("texte")[1:-1]
        interieurs = [] if image else _en_ligne(contenu, definitions)
        trouves.extend(interieurs)
        if any(not est_image for _, est_image in interieurs):
            if m.group("etiquette"):
                position = m.start("etiquette") - 1
            continue
        if m.group("chevrons") is not None or m.group("brute") is not None:
            cible = m.group("chevrons") if m.group("chevrons") is not None else m.group("brute")
            if cible:
                trouves.append((cible, image))
            continue
        etiquette = m.group("etiquette")
        cle = _cle(etiquette or contenu)
        if cle is not None and definitions.get(cle):
            trouves.append((definitions[cle], image))
        elif etiquette:
            position = m.start("etiquette") - 1
    return trouves


def liens(texte: str, document: str | None = None) -> list[str]:
    """Les cibles brutes des liens d'un texte, dans l'ordre où ils paraissent, sans leurs
    chevrons, hors des blocs de code clôturés, du code en ligne et des commentaires HTML. Les
    définitions de référence se lisent dans `document`, le fichier dont le texte est une partie
    (une section), et par défaut dans le texte lui-même."""
    definitions, texte = _definitions(_preparer(texte))
    if document is not None:
        definitions, _ = _definitions(_preparer(document))
    return [cible for cible, _ in _en_ligne(texte, definitions)]


def cible_locale(cible: str, racine: Path) -> str | None:
    """Le chemin, relatif à la racine et en `/`, sans `/` final (`.` pour la racine), que vise une
    cible ; `None` si elle n'est pas locale : un schéma, une ancre seule, une barre oblique inverse
    restée après les échappements, sous Windows un deux-points (un lecteur, `Z:`, en tête ou plus
    loin : `docs/Z:x.md`), ou une sortie de la racine, par `..` ou par un lien symbolique."""
    if _SCHEMA.match(cible) or cible.startswith("//"):
        return None
    chemin = cible.split("#", 1)[0].split("?", 1)[0]
    chemin = unquote(_PONCTUATION_ECHAPPEE.sub(r"\1", chemin), errors="replace")
    if not chemin:
        return None
    segments: list[str] = []
    for segment in chemin.split("/"):
        if segment in ("", "."):
            continue
        if segment == "..":
            if not segments:
                return None
            segments.pop()
        else:
            segments.append(segment)
    relatif = "/".join(segments) or "."
    # GitHub ne lit pas `\` comme un séparateur : une telle cible n'est jamais un chemin du dépôt.
    # Sous Windows, deux en tête nommeraient un partage réseau, que `resolve` ouvrirait. Un
    # deux-points y nomme un lecteur, en tête (`Z:/x.md`, `Q:x.md`, qu'un `./` ou un `%5A` cachent
    # au schéma) comme plus loin (`docs/Z:x.md` : en mode non strict, `resolve` joint `Z:x.md` au
    # dernier dossier qui existe, ce qui repart du lecteur, puis lit l'état de ce chemin), et un nom
    # de fichier Windows n'en porte jamais. Ces cibles sont refusées avant `resolve`. Sous Linux, un
    # deux-points ne nomme aucun lecteur : la cible reste locale.
    if "\\" in relatif or (os.name == "nt" and ":" in relatif):
        return None
    try:
        base = racine.resolve()
        if not (base / relatif).resolve().is_relative_to(base):
            return None
    except (OSError, RuntimeError, ValueError):
        return None
    return relatif


def _affichable(texte: str) -> str:
    """Le texte, chaque caractère de contrôle (catégorie Unicode `Cc`), séparateur de ligne ou de
    paragraphe (`Zl`, `Zp`, que `splitlines` coupe aussi) ou non décodable (`Cs`, ce que donne
    sous Linux un nom qui n'est pas de l'UTF-8) remplacé par `?`."""
    return "".join(
        "?" if unicodedata.category(c) in ("Cc", "Zl", "Zp", "Cs") else c for c in texte
    )


# --- les contrôles ---------------------------------------------------------------------------


def _noms(racine: Path, suivis_seulement: bool = False) -> list[str]:
    """Les noms du premier niveau de la racine. À la racine d'un dépôt git (un `.git` y est), ceux
    que git suit ou suivrait, pour la carte : un fichier qu'il ignore n'en est pas, un fichier non
    suivi en est. Avec `suivis_seulement`, pour la licence, ceux que git suit seulement (l'index) :
    la CI lit le commit, et un fichier non suivi n'y est pas. Ailleurs, ou si git ne répond pas,
    tout le dossier."""
    if (racine / ".git").exists():
        env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
        commande = ["git", "ls-files", "-z", "--cached"]
        if not suivis_seulement:
            commande += ["--others", "--exclude-standard", "--directory"]
        try:
            r = subprocess.run(
                commande,
                cwd=racine,
                env=env,
                capture_output=True,
                check=False,
                timeout=60,
            )
        except (OSError, subprocess.SubprocessError):
            r = None
        if r is not None and r.returncode == 0:
            return sorted({os.fsdecode(c).split("/", 1)[0] for c in r.stdout.split(b"\0") if c})
    return os.listdir(racine)


def _texte(chemin: Path) -> str | None:
    """Le texte d'un fichier, en LF, sans BOM, chaque octet qui n'est pas de l'UTF-8 remplacé ;
    `None` s'il ne se lit pas."""
    try:
        return _en_lf(chemin.read_text("utf-8", errors="replace").removeprefix("\ufeff"))
    except OSError:
        return None


def _lire(racine: Path, nom: str, noms: list[str]) -> str | None:
    """Le texte d'un fichier de la racine, nommé à la casse près, sans BOM ; `None` s'il n'y est
    pas."""
    chemin = racine / nom
    if nom not in noms or not chemin.is_file():
        return None
    return _texte(chemin)


# Une ligne de séparation : trois `-`, `*` ou `_` au moins, du même caractère, des blancs entre eux.
_SEPARATEUR = re.compile(r" {0,3}([-*_])(?:[ \t]*\1){2,}[ \t]*$")


def _replie(titre: str) -> str:
    """Un titre comparable : en NFC, sans égard à la casse."""
    return unicodedata.normalize("NFC", titre).casefold()


def section(
    texte: str, titre: str, niveau: int | None = None, bornee: bool = False
) -> str | None:
    """Les lignes d'origine, en LF, des sections d'un titre donné, ou `None` si aucun titre ne lui
    correspond (voir `sections`). Deux sections sont séparées par une ligne vide : la seconde ne
    prolonge pas un paragraphe de la première."""
    morceaux = sections(texte, titre, niveau, bornee)
    return "\n\n".join(morceaux) if morceaux else None


def sections(
    texte: str, titre: str, niveau: int | None = None, bornee: bool = False
) -> list[str]:
    """Les lignes d'origine, en LF, de chaque section d'un titre donné, dans l'ordre ; une liste
    vide si aucun titre ne lui correspond. Le titre se compare en NFC, sans égard à la casse ; avec
    `niveau`, seul un titre de ce niveau compte. Une section court jusqu'au titre suivant de même
    niveau ou d'un niveau supérieur ; bornée, jusqu'au premier titre, quel que soit son niveau, ou à
    la première ligne de séparation (`---`, `***`, `___`). Les titres et les séparateurs se lisent
    hors des blocs de code clôturés et des blocs de commentaire HTML, où GitHub n'en affiche aucun.
    Un commentaire en ligne est retiré du titre."""
    lignes = _en_lf(texte).split("\n")
    # Seul un bloc de commentaire cache un titre, ses fins de ligne gardées, qu'il s'ouvre en tête
    # de ligne ou après une puce, un numéro ou `>`. La structure des blocs passe avant le code en
    # ligne : un accent grave isolé plus haut n'y change rien. Un `<!--` ouvert dans un paragraphe
    # reste du texte : le titre qui suit coupe le paragraphe.
    visibles = _BLOC_DE_COMMENTAIRE.sub(
        lambda m: re.sub(r"[^\n]", "x", m.group(0)), _hors_des_blocs("\n".join(lignes))
    )
    cherche = _replie(titre)
    titres: list[tuple[int, int, str]] = []
    separateurs: list[int] = []
    for i, ligne in enumerate(visibles.split("\n")):
        m = _TITRE.match(ligne)
        if m:
            contenu = _FERMANTE.sub("", _COMMENTAIRE.sub("", m.group(2) or "")).strip()
            titres.append((i, len(m.group(1)), _replie(contenu)))
        elif _SEPARATEUR.match(ligne):
            separateurs.append(i)
    morceaux = []
    for k, (i, n, contenu) in enumerate(titres):
        if contenu != cherche or (niveau is not None and n != niveau):
            continue
        if bornee:
            suivants = [titres[k + 1][0]] if k + 1 < len(titres) else []
            suivants += [j for j in separateurs if j > i][:1]
            fin = min(suivants, default=len(lignes))
        else:
            fin = next((j for j, autre, _ in titres[k + 1 :] if autre <= n), len(lignes))
        morceaux.append("\n".join(lignes[i + 1 : fin]))
    return morceaux


def _cibles(texte: str, racine: Path, document: str | None = None) -> set[str]:
    trouves = (cible_locale(lien, racine) for lien in liens(texte, document))
    return {c for c in trouves if c is not None}


def licence(racine: Path, nature: str) -> tuple[list[str], bool]:
    """La licence : (lignes, refus). Le texte se lit dans le dossier ; à la racine d'un dépôt git,
    `LICENSE` doit en plus être suivi, comme dans le commit que lit la CI."""
    if nature == "donnees":
        return ["licence : non exigée (nature donnees)"], False
    texte = _lire(racine, "LICENSE", os.listdir(racine))
    if texte is None or not texte.strip():
        return ["licence : LICENSE absent ou vide, exigé en nature code"], True
    if "LICENSE" not in _noms(racine, suivis_seulement=True):
        return ["licence : LICENSE présent mais non suivi par git, exigé en nature code"], True
    return ["licence : LICENSE présent (nature code)"], False


def carte(racine: Path) -> tuple[list[str], bool]:
    """La carte de la racine : (lignes, refus). La première ligne dit le nombre de fichiers vus."""
    noms = _noms(racine)
    vus = sorted(
        nom
        for nom in noms
        if Path(nom).suffix.lower() == ".md" and nom != "README.md" and (racine / nom).is_file()
    )
    readme = _lire(racine, "README.md", noms)
    claude = _lire(racine, "CLAUDE.md", noms)
    absents = [
        f"carte : {nom} absent"
        for nom, texte in (("README.md", readme), ("CLAUDE.md", claude))
        if texte is None
    ]
    par_le_readme = _cibles(readme or "", racine)
    foi = section(claude or "", CE_QUI_FAIT_FOI) or ""
    par_ce_qui_fait_foi = _cibles(foi, racine, claude)
    non_lies = []
    for nom in vus:
        if nom == "CLAUDE.md":
            if nom not in par_le_readme:
                non_lies.append("carte : CLAUDE.md n'est pas lié par README.md")
        elif nom not in par_le_readme and nom not in par_ce_qui_fait_foi:
            non_lies.append(f"carte : {_affichable(nom)} {NON_LIE}")
    tete = f"carte : {len(vus)} fichier{'s' if len(vus) > 1 else ''} .md à la racine"
    if non_lies:
        tete += f", {len(non_lies)} non lié{'s' if len(non_lies) > 1 else ''}"
    elif len(vus) == 1:
        tete += ", lié"
    elif len(vus) > 1:
        tete += ", tous liés"
    return [tete, *absents, *non_lies], bool(absents or non_lies)


MARQUEUR = "*AAAA-MM-JJ*"
# Une ligne tout en italique : une seule emphase, de son premier à son dernier caractère.
_ITALIQUE = re.compile(r"\*[^*\s](?:[^*]*[^*\s])?\*|_[^_\s](?:[^_]*[^_\s])?_")
_PLANS = ".claude/plans"
_ADR = ("docs/decisions/", "docs/adr/")
_SANS_CONTENU = {"README.md", ".gitkeep"}


def _sous_les_plans(chemin: str) -> bool:
    return chemin == _PLANS or chemin.startswith(_PLANS + "/")


def _fichier_mis_de_cote(chemin: str) -> bool:
    """Le registre (tout `registre.md`, sans égard à la casse), un plan, ou un fichier d'ADR (sous
    `docs/decisions/` ou `docs/adr/`, sauf leur `README.md`) : ni le marqueur ni le corps ne s'y
    lisent."""
    if chemin.rsplit("/", 1)[-1].lower() == "registre.md" or _sous_les_plans(chemin):
        return True
    return chemin.startswith(_ADR) and chemin not in {d + "README.md" for d in _ADR}


def _corps_vide(texte: str) -> bool:
    """Vrai si le texte n'a que des titres (de `#` à `######`), des lignes vides, des commentaires
    HTML et des lignes tout en italique. Une ligne d'un bloc de code clôturé, ses clôtures
    comprises, fait un corps ; un code en ligne aussi."""
    hors = _hors_des_blocs(texte)
    for ligne, dehors in zip(texte.split("\n"), hors.split("\n")):
        if ligne.strip() and not dehors:  # une ligne vidée par `_hors_des_blocs` : du code
            return False
    for ligne in sans_bloc_ni_commentaire(texte).split("\n"):
        if ligne.strip() and not _TITRE.match(ligne) and not _ITALIQUE.fullmatch(ligne.strip()):
            return False
    return True


def _dossier_sans_contenu(dossier: Path) -> bool:
    """Vrai si le dossier n'a pas d'autre enfant direct que `README.md` et `.gitkeep`."""
    try:
        return not set(os.listdir(dossier)) - _SANS_CONTENU
    except OSError:
        return False


def gabarits_vides(racine: Path) -> list[str]:
    """Les constats du gabarit resté vide, dans l'ordre des liens de `README.md`, un par chemin.
    Aucun sous-processus : la racine se lit telle quelle, sans git."""
    try:
        noms = os.listdir(racine)
    except OSError:
        noms = []
    readme = _lire(racine, "README.md", noms)
    if readme is None:
        return ["pas de README.md"]
    constats: list[str] = []
    deja: set[str] = set()
    documents = 0
    for lien in liens(readme):
        chemin = cible_locale(lien, racine)
        if chemin is None or chemin in deja:
            continue
        deja.add(chemin)
        cible, nom = racine / chemin, _affichable(chemin)
        if cible.is_dir():
            documents += 1
            if not _sous_les_plans(chemin) and _dossier_sans_contenu(cible):
                constats.append(f"{nom}/ : dossier sans autre fichier que README.md")
        elif cible.is_file() and Path(chemin).suffix.lower() == ".md":
            documents += 1
            texte = None if _fichier_mis_de_cote(chemin) else _texte(cible)
            if texte is None:
                continue
            if MARQUEUR in _preparer(texte):
                constats.append(f"{nom} : garde le marqueur {MARQUEUR} du gabarit")
            elif _corps_vide(texte):
                constats.append(f"{nom} : corps vide (titres et consignes seulement)")
    if not documents:
        return ["le README ne lie aucun document du dépôt"]
    return constats


# --- ligne de commande -----------------------------------------------------------------------


def _voisins() -> None:
    """Avant d'importer un voisin : aucun cache écrit, même lancé sans `-B`, et le dossier du
    script dans le chemin d'import, en fin, sans doublon, même sous `python -I`."""
    sys.dont_write_bytecode = True
    dossier = os.path.dirname(os.path.abspath(__file__))
    if dossier not in sys.path:
        sys.path.append(dossier)


def _nature() -> str:
    """La nature, lue par la porte de confidentialité : importée ici seulement, à l'appel, sans
    écrire de cache, même lancé sans `-B` : aucun `__pycache__` dans le projet."""
    _voisins()
    from confidentialite import nature

    return nature()


class _Analyseur(argparse.ArgumentParser):
    def error(self, message: str):  # le message reçu pourrait citer l'entrée : on ne l'affiche pas
        self.exit(EXIT_USAGE, "documentation : usage invalide (voir --help)\n")


def main(argv: list[str] | None = None) -> int:
    for flux in (sys.stdout, sys.stderr):
        try:
            flux.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
        except (AttributeError, ValueError):
            pass
    p = _Analyseur(
        prog="documentation.py",
        description="La licence et la carte de la racine, ou le gabarit resté vide.",
    )
    p.add_argument(
        "--racine",
        type=Path,
        default=Path("."),
        help=(
            "racine du dépôt (défaut : le dossier courant) ; elle change les fichiers lus, pas la"
            " nature : hors CI, c'est celle du reglages.py voisin du script ; en CI, celle de la"
            " branche par défaut, lue dans le dossier courant"
        ),
    )
    p.add_argument(
        "--gabarits-vides",
        action="store_true",
        help="le seul gabarit resté vide : un constat par ligne, et toujours 0",
    )
    try:
        args = p.parse_args(argv)
    except SystemExit as sortie:
        return 0 if sortie.code in (0, None) else EXIT_USAGE
    if not args.racine.is_dir():
        print("documentation : racine introuvable (voir --help)", file=sys.stderr)
        return EXIT_USAGE
    if args.gabarits_vides:
        try:
            constats = gabarits_vides(args.racine)
        except Exception:  # noqa: BLE001 - un avertissement ne fait jamais échouer
            constats = ["non lue (erreur)"]
        for constat in constats:
            print(PREFIXE + constat)
        return 0
    lignes_licence, refus_licence = licence(args.racine, _nature())
    lignes_carte, refus_carte = carte(args.racine)
    for ligne in (*lignes_licence, *lignes_carte):
        print(PREFIXE + ligne)
    if refus_licence or refus_carte:
        print(PREFIXE + "refus")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

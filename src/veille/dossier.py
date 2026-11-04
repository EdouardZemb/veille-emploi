"""Generation du dossier de candidature.

REGLE DE CONCEPTION : ce module n'ecrit AUCUNE prose. Il prend un gabarit
fourni par toi, remplace des marqueurs par les elements de l'offre, et copie
les pieces jointes. Tout ce qui ressemble a une phrase vient d'un fichier que
tu as ecrit - jamais du programme.

Le kit de candidature (CV maitre, lettres types, annexe technique) est produit
par une autre session. Il est lu depuis VEILLE_KIT ; tant qu'il n'est pas
livre, on se rabat sur le `gabarits/` du dossier de configuration et la console signale que les pieces sont
provisoires.

Choix du gabarit de lettre, par ordre de priorite :
  1. lettre_<famille>.md      (ex. lettre_automatisation_tests.md)
  2. lettre_<langue>.md       (lettre_en.md si l'offre est en anglais)
  3. lettre.md                (defaut)
"""

from __future__ import annotations

import io
import logging
import re
import shutil
import unicodedata
import zipfile
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from .config import CHEMIN_DOSSIERS, CHEMIN_GABARITS, CHEMIN_KIT, normaliser

log = logging.getLogger(__name__)

# Extensions considerees comme des pieces a joindre telles quelles.
PIECES = (".pdf", ".docx", ".odt", ".png", ".jpg")

# Etiquettes reconnues dans un nom de fichier, separees par des points avant
# l'extension. Une piece n'est jointe que si TOUTES ses etiquettes conviennent
# a l'offre.
#
#   cv.fr.pdf              -> uniquement les offres en francais
#   dossier.ch.en.pdf      -> uniquement les offres suisses redigees en anglais
#   annexe-technique.pdf   -> toujours jointe
#
# Sans cette regle, un CV francais et un dossier anglais partaient ensemble
# dans chaque candidature.
ETIQUETTES_LANGUE = {"fr", "en", "de"}
ETIQUETTES_PAYS = {"ch", "suisse", "france", "fr-fr"}

# Etiquette qui retire une piece de TOUT envoi automatique, sans la retirer du
# kit : elle reste telechargeable depuis la console quand un recruteur la
# demande.
#
# POURQUOI ELLE EXISTE. Un nom « sans etiquette reconnue » ne met pas une
# piece de cote : la regle ci-dessous joint par defaut tout ce qui n'a aucune
# etiquette — c'est ce qui fait partir `annexe-technique.pdf` partout. Une
# variante du CV nommee `cv-variante-en.pdf` n'a aucune etiquette au sens de
# cette regle (aucun point dans le nom) : elle serait partie dans CHAQUE
# candidature, a cote de l'autre CV. Deux CV dans la meme enveloppe.
ETIQUETTE_MANUELLE = "manuel"

_RE_MARQUEUR = re.compile(r"\{\{\s*([a-z_]+)\s*\}\}")
# Segment facultatif : {{#cle}}...{{/cle}}. Voir `_remplir`.
# Les commentaires HTML sont preserves tels quels — voir `_remplir`.
_RE_COMMENTAIRE = re.compile(r"(<!--.*?-->)", re.S)
_RE_SECTION = re.compile(r"\{\{#([a-z_]+)\}\}(.*?)\{\{/\1\}\}", re.S)


@dataclass
class ResultatDossier:
    chemin: Path
    fichiers: list[str]
    gabarit_lettre: str
    kit_provisoire: bool
    avertissements: list[str]
    # Ce qui part au recruteur, sous les noms qu'il verra. Distinct de
    # `fichiers`, qui contient aussi sa note de preparation d'entretien.
    pieces_envoi: list[str] = field(default_factory=list)
    # Ce que l'assemblage a repris de l'annonce, pour le montrer a l'ecran.
    assemblage: dict = field(default_factory=dict)
    # Les points d'entretien retenus, pour les montrer sans relire le fichier.
    preparation: dict = field(default_factory=dict)


def _ardoise(texte: str, longueur: int = 60) -> str:
    """Nom de fichier sur : sans accents, sans ponctuation, tirets."""
    decompose = unicodedata.normalize("NFKD", texte or "")
    sans = "".join(c for c in decompose if not unicodedata.combining(c))
    propre = re.sub(r"[^A-Za-z0-9]+", "-", sans).strip("-")
    return (propre[:longueur] or "offre").lower()


def _kit_est_provisoire() -> bool:
    """Vrai tant qu'aucune vraie piece n'est disponible.

    ATTENTION, DEFAUT CORRIGE : cette fonction rendait False des que
    `VEILLE_KIT` etait DEFINIE, sans regarder si le dossier contenait quoi que
    ce soit. Sur le serveur, la variable pointait vers un dossier vide : la
    console generait donc un squelette de lettre sans CV, et n'affichait AUCUN
    avertissement. Edouard a vu « ca ne fonctionne pas » la ou la verite etait
    « le kit n'est pas branche » — il n'avait aucun moyen de le savoir.

    On regarde desormais le CONTENU, pas la configuration.
    """
    if (CHEMIN_KIT / ".provisoire").exists():
        return True
    if not CHEMIN_KIT.exists():
        return True
    # Une vraie piece de candidature : un CV ou une lettre en PDF, DOCX ou ODT.
    return not any(
        f.is_file() and f.suffix.lower() in PIECES for f in CHEMIN_KIT.iterdir()
    )


def pieces_du_kit() -> list[str]:
    """Ce que le kit contient reellement, pour le dire a l'ecran."""
    if not CHEMIN_KIT.exists():
        return []
    return sorted(f.name for f in CHEMIN_KIT.iterdir()
                  if f.is_file() and f.suffix.lower() in PIECES)


_SITES = {
    "linkedin.com": "LinkedIn", "jobs.ch": "jobs.ch", "indeed.com": "Indeed",
    "arbeitnow.com": "Arbeitnow", "apec.fr": "l'Apec", "hellowork.com": "HelloWork",
    "welcometothejungle.com": "Welcome to the Jungle",
    "candidat.francetravail.fr": "France Travail",
    "francetravail.fr": "France Travail", "monster.fr": "Monster",
}


def _source_lisible(offre: dict[str, Any]) -> str:
    """Le nom du site ou l'annonce a ete vue, tel qu'on l'ecrit dans une lettre."""
    from urllib.parse import urlsplit

    hote = (urlsplit(offre.get("url_canonique") or offre.get("url") or "").hostname or "").lower()
    hote = hote[4:] if hote.startswith("www.") else hote
    for domaine, nom in _SITES.items():
        if hote.endswith(domaine):
            return nom
    return hote or "votre site carriere"


def _valeurs(offre: dict[str, Any]) -> dict[str, str]:
    """Les marqueurs remplacables dans un gabarit."""
    salaire = ""
    if offre.get("salaire_min") or offre.get("salaire_max"):
        smin, smax = offre.get("salaire_min"), offre.get("salaire_max")
        dev = offre.get("salaire_devise") or ""
        salaire = f"{smin:,.0f} - {smax:,.0f} {dev}".replace(",", " ") if smin and smax else f"{smin or smax:,.0f} {dev}".replace(",", " ")

    return {
        "titre": offre.get("titre", ""),
        "employeur": offre.get("employeur", "") or "[employeur non identifié dans l'annonce]",
        "lieu": offre.get("lieu", "") or "[lieu non précisé]",
        "url": offre.get("url", ""),
        "source": offre.get("source", ""),
        # « advertised on mail:generique » ne veut rien dire pour un recruteur.
        # On rend le NOM DU SITE, deduit de l'annonce elle-meme.
        "source_lisible": _source_lisible(offre),
        "famille": offre.get("famille", ""),
        "zone": offre.get("zone", ""),
        "contrat": offre.get("type_contrat", ""),
        "salaire": salaire or "non publie",
        "date": date.today().strftime("%d/%m/%Y"),
        # Ce qu'il a cherche lui-meme pour CETTE offre. Jamais obligatoire :
        # une offre sans nom de recruteur existe, et imposer la saisie
        # transformerait une aide en obstacle. Le PDF signale les manques.
        "contact": offre.get("contact_nom") or "",
        "contact_civilite": offre.get("contact_civilite") or "",
        "adresse_entreprise": offre.get("adresse_entreprise") or "",
        # Reference de l'annonce, saisie ou validee par lui. Vide le plus
        # souvent : presque aucune annonce complete n'en porte.
        "reference": offre.get("reference_annonce") or "",
        "date_iso": date.today().isoformat(),
        "score": str(offre.get("score", "")),
    }


def _remplir(gabarit: str, valeurs: dict[str, str]) -> tuple[str, list[str]]:
    """Remplace les marqueurs. Un marqueur inconnu est laisse VISIBLE.

    On ne devine jamais : un marqueur non resolu reste dans le texte pour que
    tu le voies immediatement a la relecture.

    LES SEGMENTS FACULTATIFS. `{{#cle}}...{{/cle}}` encadre un morceau de
    phrase qui n'existe que si `cle` a une valeur. Vide, le segment disparait
    EN ENTIER — ponctuation comprise.

    C'est le gabarit qui decide ce qui disparait, pas le programme. La phrase
    « Je postule au poste suivant : {{titre}}{{#reference}} - reference
    {{reference}}{{/reference}}, publie sur {{source_lisible}}. » rend :

        ... Ingenieur IVVQ - reference R-1234, publie sur LinkedIn.
        ... Ingenieur IVVQ, publie sur LinkedIn.

    Le tiret et le mot « reference » sont DANS le segment, la virgule est
    DEHORS. Aucune reparation de ponctuation apres coup : c'est precisement
    ce qui produit des virgules orphelines, parce qu'il faudrait deviner ce
    que l'auteur voulait. Ici il l'a ecrit.

    Un segment facultatif ne compte JAMAIS comme un marqueur manquant : il
    est facultatif, c'est tout son sens.
    """
    manquants: list[str] = []

    def section(m: re.Match) -> str:
        cle, interieur = m.group(1), m.group(2)
        return interieur if (valeurs.get(cle) or "").strip() else ""

    def remplacer(m: re.Match) -> str:
        cle = m.group(1)
        if cle in valeurs and valeurs[cle]:
            return valeurs[cle]
        manquants.append(cle)
        return f"[[{cle} - À COMPLÉTER]]"

    def traiter(morceau: str) -> str:
        # Les sections d'abord : ce qu'elles retirent ne doit pas etre
        # comptabilise comme un marqueur a completer.
        return _RE_MARQUEUR.sub(remplacer, _RE_SECTION.sub(section, morceau))

    # LES COMMENTAIRES NE SONT PAS TOUCHES. Ce sont ses notes a lui ; elles ne
    # partent jamais au recruteur. Y substituer les marqueurs produisait deux
    # defauts, vus le 02/10/2026 : la notice « Marqueurs remplis par la
    # console : {{employeur}}, {{titre}}... » devenait « ... : Exemple
    # Logistik AG, Testeur logiciel... », donc illisible ; et le `{{reference}}` qu'elle cite
    # etait compte comme un marqueur manquant, ce qui faisait reclamer a
    # l'ecran une reference pourtant facultative.
    morceaux = _RE_COMMENTAIRE.split(gabarit)
    sortie = [m if i % 2 else traiter(m) for i, m in enumerate(morceaux)]
    return "".join(sortie), manquants


# --------------------------------------------------------------------------
# La reference de l'annonce
# --------------------------------------------------------------------------

# Une etiquette ENTIERE, un separateur, et un jeton qui porte au moins un
# chiffre. Sans ces trois conditions, « Refactoring », « reflects » et
# « reference architectures » etaient pris pour des references : de nombreux
# faux positifs lors de la premiere mesure.
_RE_REFERENCE = re.compile(
    r"\b(?:r[ée]f|r[ée]f\.|r[ée]f[ée]rence|reference)\s*"
    r"(?:de l.offre|offre|annonce)?\s*(?:n[°o]|:|#|-)\s*"
    r"([A-Za-z0-9][A-Za-z0-9._/-]{1,23}\d[A-Za-z0-9._/-]{0,10}"
    r"|\d[A-Za-z0-9._/-]{2,20})"
    r"|\b(?:job|requisition|vacancy|posting|position)\s+"
    r"(?:id|number|no\.?|code|ref)\s*(?:n[°o]|:|#|-)?\s*"
    r"([A-Za-z0-9][A-Za-z0-9._/-]*\d[A-Za-z0-9._/-]*)"
    r"|\b(?:Kennziffer|Stellennummer|Referenznummer|Referenz)\s*"
    r"(?:nr\.?|:|#)?\s*([A-Za-z0-9][A-Za-z0-9._/-]*\d[A-Za-z0-9._/-]*)",
    re.IGNORECASE,
)


def deduire_reference(offre: dict[str, Any]) -> tuple[str, str]:
    """(reference proposee, phrase d'ou elle vient) — ou ("", "").

    PROPOSE, n'ECRIT PAS. Le champ est prerempli dans la console avec la
    phrase qui le justifie ; c'est Edouard qui valide, comme pour le reste.

    On exige que l'annonce DISE que c'est une reference : une etiquette, un
    separateur, un jeton contenant un chiffre. L'identifiant numerique d'une
    URL LinkedIn n'est PAS propose : l'annonce ne le nomme jamais ainsi, et
    une reference fausse est pire qu'une reference absente.

    MESURE DU 02/10/2026 : presque aucune annonce complete ne porte de
    reference explicite. Cette fonction rendra donc une chaine vide presque
    toujours — c'est le resultat attendu, pas une panne.
    """
    texte = f"{offre.get('titre') or ''}\n{offre.get('description') or ''}"
    m = _RE_REFERENCE.search(texte)
    if not m:
        return "", ""
    valeur = next((g for g in m.groups() if g), "")
    if not valeur:
        return "", ""
    debut, fin = max(0, m.start() - 60), min(len(texte), m.end() + 40)
    return valeur, " ".join(texte[debut:fin].split())


# Mots outils, par langue. Ce sont les mots les plus frequents d'une langue
# et ceux qu'un texte ne peut pas eviter — bien plus fiables qu'un lexique
# metier, qui est souvent anglais dans les trois langues.
#
# ATTENTION AUX MOTS COMMUNS A DEUX LANGUES. « des » etait dans la liste
# francaise : c'est aussi le genitif allemand, et il est tres frequent. Dans
# la base, c'est lui qui poussait la plupart des annonces allemandes vers le
# francais. Un mot outil ne vaut que s'il n'appartient qu'a une langue.
MOTS_OUTILS = {
    "fr": (" le ", " la ", " les ", " vous ", " nous ", " une ", " dans ",
           " pour ", " est ", " et ", " avec ", " sur "),
    "en": (" the ", " and ", " you ", " we ", " with ", " for ", " our ",
           " are ", " this ", " that "),
    "de": (" und ", " der ", " die ", " das ", " mit ", " fur ", " von ",
           " sie ", " wir ", " ein ", " eine ", " den ", " dem ", " im ",
           " zu ", " auf ", " als ", " bei ", " ist ", " sind ", " nicht ",
           " oder ", " auch ", " werden ", " wird "),
}

# Les langues dans lesquelles le code sert des pièces : une constante du code, pas
# de la configuration. Déposer une pièce allemande dans le kit n'y change rien ;
# servir l'allemand, c'est changer cette constante. Une lettre qu'on ne peut pas
# relire, une version bâchée, est pire que pas de version.
LANGUES_SERVIES = ("fr", "en")

# En-dessous, ce n'est pas un signal : c'est du bruit. Deux mots outils
# distincts suffisent a trancher, zero ou un ne suffisent pas.
SEUIL_LANGUE = 2


def compter_langues(offre: dict[str, Any]) -> dict[str, int]:
    """Combien de mots outils de chaque langue, dans l'annonce."""
    texte = normaliser(f"{offre.get('titre','')} {offre.get('description','')}")
    return {lg: sum(1 for m in mots if m in texte)
            for lg, mots in MOTS_OUTILS.items()}


def detecter_langue(offre: dict[str, Any]) -> str:
    """'fr', 'en', 'de' — ou '' quand l'annonce ne dit rien.

    LA CHAINE VIDE EST UN RESULTAT, PAS UN ECHEC. L'ancienne version rendait
    `"en" if marqueurs_en > marqueurs_fr else "fr"` : a egalite — y compris
    zero partout — elle rendait « fr » en silence. Une annonce allemande n'a
    aucun mot outil francais ni anglais : elle recevait donc une lettre
    francaise, avec le CV francais, et AUCUN avertissement.

    Mesure du 02/10/2026 sur la base : les annonces allemandes etaient
    classees « fr » ou « en ». Aucune correcte.

    Le defaut n'etait pas que le francais soit un mauvais defaut : c'est
    qu'une absence d'indice etait presentee comme une certitude. On rend
    desormais une chaine vide, et l'appelant doit la traiter.
    """
    compte = compter_langues(offre)
    gagnante = max(compte, key=lambda lg: compte[lg])
    meilleur = compte[gagnante]
    if meilleur < SEUIL_LANGUE:
        return ""
    # Une egalite n'est pas une decision.
    if sorted(compte.values())[-2] == meilleur:
        return ""
    return gagnante


def langue_lisible(langue: str) -> str:
    return {"fr": "francais", "en": "anglais", "de": "allemand"}.get(
        langue, "indeterminee")


def detecter_pays(offre: dict[str, Any]) -> str:
    """'ch' | 'france' | 'allemagne' | 'autre' | '' — quelles pieces joindre.

    Rend le pays REEL, pas un repli. Jusqu'au 02/10/2026 cette fonction
    rendait « france » pour tout ce qui n'etait pas suisse : un poste a
    Hambourg recevait donc le CV francais. Mesure du jour : une part notable
    des offres hors France et hors Suisse etaient dans ce cas, plus d'autres
    dont le lieu ne dit rien.
    """
    from .models import Offre
    from .scoring import detecter_pays as _pays

    fictive = Offre(
        titre=offre.get("titre", ""),
        employeur=offre.get("employeur", ""),
        lieu=offre.get("lieu", ""),
        salaire_devise=offre.get("salaire_devise"),
    )
    reel = _pays(fictive)
    return "ch" if reel == "suisse" else reel


def _piece_convient(nom: Path, langue: str, pays: str) -> bool:
    """Une piece est jointe si toutes ses etiquettes conviennent a l'offre."""
    etiquettes = {p.lower() for p in nom.name.split(".")[1:-1]}
    if ETIQUETTE_MANUELLE in etiquettes:
        return False  # jamais automatique, mais toujours dans le kit
    if not etiquettes:
        return True  # aucune etiquette : piece universelle
    for e in etiquettes:
        if e in ETIQUETTES_LANGUE and e != langue:
            return False
        if e in ETIQUETTES_PAYS:
            attendu = {"ch", "suisse"} if pays == "ch" else (
                {"france", "fr-fr"} if pays == "france" else set())
            if e not in attendu:
                return False
    return True


def _specificite(nom: Path) -> int:
    """Combien d'etiquettes porte cette piece."""
    return len([p for p in nom.name.split(".")[1:-1] if p])


def _famille_de_piece(nom: Path) -> str:
    """Le nom avant la premiere etiquette : `cv.ch.en.pdf` -> `cv`.

    Deux fichiers de la meme famille sont deux versions d'une meme piece :
    on n'en envoie qu'UNE.
    """
    return nom.name.split(".")[0].lower()


def pieces_retenues(pieces: list[Path], langue: str, pays: str) -> list[Path]:
    """Les pieces a joindre : filtrees, puis LA PLUS SPECIFIQUE par famille.

    POURQUOI UNE PRIORITE, ET PAS SEULEMENT UN FILTRE. Deux fichiers peuvent
    convenir a une offre suisse anglophone : `cv.en.pdf` (anglais, tous pays)
    et `cv.ch.en.pdf` (anglais, Suisse). Les joindre tous les deux mettrait
    deux CV dans la meme enveloppe.

    LE PLUS SPECIFIQUE GAGNE : `cv.ch.en.pdf` porte deux etiquettes, `cv.en.pdf`
    une seule. C'est le principe applique partout dans ce projet, et c'est
    celui qui a corrige le choix de la lettre.
    """
    convenables = [p for p in pieces if _piece_convient(p, langue, pays)]
    par_famille: dict[str, Path] = {}
    for p in sorted(convenables, key=lambda x: x.name):
        famille = _famille_de_piece(p)
        meilleur = par_famille.get(famille)
        if meilleur is None or _specificite(p) > _specificite(meilleur):
            par_famille[famille] = p
    return sorted(par_famille.values(), key=lambda x: x.name)


def _noms_attendus(offre: dict[str, Any]) -> list[str]:
    """Les gabarits qu'il faudrait ecrire pour la langue de cette annonce.

    Sert a dire QUOI ecrire, plutot que « aucun gabarit trouve ».
    """
    langue = detecter_langue(offre)
    famille = offre.get("famille") or ""
    attendus = [f"lettre_{famille}_{langue}.md"] if famille else []
    attendus.append(f"lettre_{langue}.md")
    return attendus


def _candidats_lettre(offre: dict[str, Any]) -> list[Path]:
    """Les gabarits existants, du plus specifique au plus general.

    Ordre : ATOUT, puis famille, puis langue, puis defaut. L'atout passe en
    premier parce qu'il est plus specifique : sur une offre de test dans le
    domaine d'un de ses atouts, la lettre de ce domaine vaut mieux que sa
    lettre QA generique. C'est le meme principe que partout ailleurs
    dans ce projet — le plus specifique d'abord.

    Chaque nom existe en deux formes : avec suffixe de langue
    (`lettre_test_fonctionnel_fr.md`) et sans (`lettre_test_fonctionnel.md`). La forme
    suffixee passe en premier, mais ce n'est qu'un indice de tri : c'est le
    CONTENU qui tranche, dans `_choisir_lettre`. Un fichier mal suffixe ne
    peut donc pas tromper la selection.

    Le kit passe avant les gabarits du depot : ses lettres a lui d'abord, le
    squelette seulement en dernier recours.
    """
    famille = offre.get("famille") or ""
    langue = detecter_langue(offre)
    atouts = offre.get("atouts") or []
    if isinstance(atouts, str):
        atouts = [a for a in atouts.split(",") if a]

    noms: list[str] = []
    for a in atouts:
        noms += [f"lettre_atout_{a}_{langue}.md", f"lettre_atout_{a}.md"]
    if famille:
        noms += [f"lettre_{famille}_{langue}.md", f"lettre_{famille}.md"]
    noms += [f"lettre_{langue}.md", "lettre.md"]

    candidats: list[Path] = []
    for dossier in (CHEMIN_KIT, CHEMIN_GABARITS):
        for nom in noms:
            chemin = dossier / nom
            if chemin.exists() and chemin not in candidats:
                candidats.append(chemin)
    return candidats


def corps_du_gabarit(brut: str) -> str:
    """Le gabarit sans sa notice d'en-tete.

    Un gabarit commence souvent par sa propre notice — la liste des marqueurs,
    ce qu'il faut en faire — separee du texte par une ligne `---`. Sans cette
    coupe, la notice partait au recruteur AVEC SES MARQUEURS REMPLACES, ce qui
    donnait, le 02/10/2026, dans la lettre francaise :

        Marqueurs disponibles : `Testeur logiciel H/F` `Exemple Logistik AG` `Bale` ...

    Les lettres du kit n'ont pas de `---` : leur notice est un commentaire
    HTML, invisible au rendu. Elles traversent donc cette fonction intactes.

    Garde-fou : on ne coupe jamais plus de la moitie du fichier. Un gabarit
    dont le corps contiendrait un `---` en tete ne doit pas etre ampute.
    """
    lignes = brut.splitlines()
    for i, ligne in enumerate(lignes):
        if ligne.strip() != "---":
            continue
        reste = lignes[i + 1:]
        if len(reste) < len(lignes) / 2:
            break  # on couperait le corps : on ne touche a rien
        return "\n".join(reste).strip("\n")
    return brut


def _choisir_lettre(offre: dict[str, Any]) -> tuple[Path | None, str]:
    """Le gabarit a utiliser, et l'avertissement a afficher — souvent vide.

    LA LANGUE PASSE AVANT LA SPECIALITE, et c'est le defaut corrige le
    02/10/2026. Une offre a Mulhouse, annonce en francais, et la console a
    produit une lettre EN ANGLAIS : la selection choisissait par
    famille — `<famille>` -> `lettre_<famille>.md` —
    sans jamais regarder la langue, et les lettres du kit etaient alors toutes
    anglaises. Mesure du jour : elles rendaient « en », l'offre rendait « fr »,
    et rien ne comparait les deux.

    Une lettre anglaise envoyee a un recruteur francais est eliminatoire. Une
    lettre moins specialisee dans la bonne langue ne l'est pas. Donc : on
    prend le premier candidat QUI PARLE LA BONNE LANGUE, meme moins
    specifique — et s'il n'y en a aucun, on le DIT, fort.
    """
    langue = detecter_langue(offre)
    candidats = _candidats_lettre(offre)
    if not candidats:
        return None, (
            f"Aucun gabarit de lettre nulle part. Attendu dans ton kit : "
            f"{', '.join(_noms_attendus(offre))}.")

    for chemin in candidats:
        if _langue_du_gabarit(chemin.read_text(encoding="utf-8")) != langue:
            continue
        if chemin.parent != CHEMIN_KIT:
            # Bonne langue, mais c'est le squelette du depot : aucune de ses
            # phrases dedans. Il doit le savoir avant de relire.
            return chemin, (
                f"Aucune lettre en {langue.upper()} dans ton kit. La console "
                f"est retombee sur le squelette « {chemin.name} », qui ne "
                f"contient aucune de tes phrases — il est a completer "
                f"entierement. A ecrire cote kit : "
                f"{', '.join(_noms_attendus(offre))}."
            )
        return chemin, ""

    # --- Aucun gabarit ne parle la langue de l'annonce --------------------
    #
    # ON NE SERT RIEN. Jusqu'au 02/10/2026 la console rendait le premier
    # candidat venu « parce qu'une page blanche n'aide personne ». C'etait
    # faux : une lettre francaise chez un recruteur germanophone est
    # eliminatoire, alors qu'un dossier incomplet et signale ne coute que du
    # temps. Mieux vaut rendre rien et le dire fort.
    if not langue:
        return None, (
            "LANGUE INDETERMINEE : l'annonce ne porte pas assez de mots pour "
            "que la console tranche entre le francais, l'anglais et "
            "l'allemand. Aucune lettre n'a ete generee — elle aurait eu une "
            "chance sur trois d'etre dans la mauvaise langue. Colle le texte "
            "complet de l'annonce, ou ecris la lettre a la main."
        )
    if langue not in LANGUES_SERVIES:
        return None, (
            f"LANGUE : cette annonce est en {langue_lisible(langue).upper()}, "
            f"et tu n'as aucune lettre dans cette langue. Aucune lettre n'a "
            f"ete generee : une lettre dans la mauvaise langue est "
            f"eliminatoire, un dossier incomplet ne l'est pas. "
            f"Si tu veux repondre quand meme, ecris-la a la main — ou "
            f"telecharge les pieces depuis l'onglet Documents et compose "
            f"l'envoi toi-meme."
        )
    return None, (
        f"LANGUE : cette annonce est en {langue_lisible(langue)} et aucun "
        f"gabarit n'existe dans cette langue. Aucune lettre n'a ete generee. "
        f"A ecrire cote kit : {', '.join(_noms_attendus(offre))}."
    )


_REPERES_EN = ("Dear ", "Yours sincerely", "I am applying for", "Enclosures:")


def _langue_du_gabarit(texte: str) -> str:
    """La langue dans laquelle CE gabarit est ecrit."""
    return "en" if any(r in texte for r in _REPERES_EN) else "fr"


# Reperes d'ouverture, DU PLUS SPECIFIQUE AU PLUS GENERAL.
#
# « Je postule » nomme le poste ; la formule d'appel ne nomme rien. Il faut
# donc chercher la phrase qui nomme le poste DANS TOUT LE FICHIER avant de se
# rabattre sur la formule d'appel.
#
# DEFAUT MESURE LE 02/10/2026. Les deux familles de reperes etaient testees
# ligne par ligne dans le meme `if` : la premiere rencontree gagnait. Dans des
# lettres francaises arrivees ensuite, « Madame, Monsieur, » precede « Je
# postule », et la charniere se posait AVANT l'annonce du poste :
#
#     Madame, Monsieur,
#     Votre annonce cite Appium, JMeter et RGAA.
#     Je postule au poste de [[intitule exact]]...
#
# On citait l'annonce avant d'avoir dit a quoi on postulait, et le paragraphe
# ecrit pour enchainer sur la charniere se retrouvait trois lignes plus bas.
# C'est le piege recurrent de ce projet — le plus specifique d'abord.
REPERES_POSTE = ("I am applying for", "Je postule")
REPERES_APPEL = ("Madame, Monsieur", "Madame,", "Monsieur,", "Dear ")


def _inserer_paragraphe(gabarit: str, paragraphe: str) -> str:
    """Pose le paragraphe assemble juste apres celui qui nomme le poste.

    C'est sa place naturelle : on vient de dire pour quel poste on postule, on
    montre aussitot qu'on a lu l'annonce. Si le paragraphe est vide — annonce
    sans matiere a citer — on ne touche a rien plutot que d'ouvrir un trou.

    A defaut de phrase qui nomme le poste, on se rabat sur la formule d'appel :
    c'est le cas du squelette du depot, qui n'a pas de « Je postule ».
    """
    if not paragraphe:
        return gabarit
    saut = chr(10)
    lignes = gabarit.split(saut)

    reperes = REPERES_POSTE
    if not any(l.startswith(REPERES_POSTE) for l in lignes):
        reperes = REPERES_APPEL
        if not any(l.startswith(REPERES_APPEL) for l in lignes):
            # Gabarit sans repere connu : on rend l'original, on ne devine pas.
            return gabarit

    sortie: list[str] = []
    pose = False
    for ligne in lignes:
        sortie.append(ligne)
        if not pose and ligne.startswith(reperes):
            sortie.append("")
            sortie.append(paragraphe)
            pose = True
    return saut.join(sortie)


def regenerer_pdf(repertoire) -> dict[str, Any]:
    """Refait le PDF et le paquet d'envoi apres un changement de lettre."""
    import zipfile as _zip
    from pathlib import Path as _P

    from . import rendu

    base = _P(repertoire)
    r = rendu.lettre_en_pdf((base / "lettre-de-motivation.md").read_text(encoding="utf-8"),
                            base / f"{rendu.prefixe()}-Lettre-de-motivation.pdf")
    if not r.ok:
        return {"ok": False, "message": r.message}
    pieces = sorted(f.name for f in base.iterdir()
                    if f.suffix.lower() in (".pdf",) and f.name.startswith(rendu.prefixe()))
    pieces += sorted(f.name for f in base.iterdir()
                     if f.suffix.lower() in PIECES and not f.name.startswith(rendu.prefixe()))
    envoi = base / f"{rendu.prefixe()}-candidature.zip"
    envoi.unlink(missing_ok=True)
    with _zip.ZipFile(envoi, "w", _zip.ZIP_DEFLATED) as z:
        for f in pieces:
            z.write(base / f, arcname=rendu.nom_pour_envoi(f))
    return {"ok": True, "marqueurs_restants": r.marqueurs_restants}


def generer(offre: dict[str, Any]) -> ResultatDossier:
    """Cree le dossier de candidature et rend son emplacement."""
    avertissements: list[str] = []
    provisoire = _kit_est_provisoire()
    if provisoire:
        avertissements.append(
            "Kit de candidature provisoire : les pieces viennent du dossier gabarits/ de ta "
            "configuration (VEILLE_CONFIG) et non "
            "de ton CV maitre. Pointe VEILLE_KIT sur le vrai kit des qu'il est livre."
        )

    nom_dossier = f"{date.today().isoformat()}_{_ardoise(offre.get('employeur') or 'employeur')}_{_ardoise(offre.get('titre'), 40)}"
    cible = CHEMIN_DOSSIERS / nom_dossier
    cible.mkdir(parents=True, exist_ok=True)
    # Ces dossiers contiennent ses lettres et le detail des offres. L'umask par
    # defaut les laissait en 775 : on serre, sur le dossier de sortie comme sur
    # chaque dossier de candidature.
    for repertoire in (CHEMIN_DOSSIERS, cible):
        try:
            repertoire.chmod(0o700)
        except OSError:
            pass  # Windows

    valeurs = _valeurs(offre)
    langue = detecter_langue(offre)
    fichiers: list[str] = []

    # --- 1. Lettre de motivation preremplie -----------------------------
    gabarit_lettre, alerte_langue = _choisir_lettre(offre)
    if alerte_langue:
        avertissements.append(alerte_langue)
    assemble = None
    if gabarit_lettre:
        from . import assemblage

        # La charniere suit la langue de la LETTRE, pas celle de l'annonce :
        # une offre au titre francais peut appeler sa lettre anglaise, et une
        # phrase francaise au milieu d'un texte anglais se verrait aussitot.
        texte_gabarit = corps_du_gabarit(
            gabarit_lettre.read_text(encoding="utf-8"))
        assemble = assemblage.assembler(
            offre, langue=_langue_du_gabarit(texte_gabarit)
        )
        brut = _inserer_paragraphe(texte_gabarit, assemble.paragraphe)
        contenu, manquants = _remplir(brut, valeurs)
        (cible / "lettre-de-motivation.md").write_text(contenu, encoding="utf-8")
        fichiers.append("lettre-de-motivation.md")
        if manquants:
            avertissements.append(
                "Marqueurs à compléter à la main dans la lettre : " + ", ".join(sorted(set(manquants)))
            )
    elif not alerte_langue:
        # `_choisir_lettre` explique deja son refus quand il en a un. On
        # n'ajoute un message generique que s'il n'a rien dit.
        avertissements.append(
            f"Aucun gabarit de lettre trouve dans {CHEMIN_KIT}. Attendu : lettre.md, "
            "lettre_fr.md, lettre_en.md ou lettre_<famille>.md"
        )

    # --- 2. Pieces jointes du kit, filtrees par langue et par pays -------
    langue, pays = detecter_langue(offre), detecter_pays(offre)
    ecartees: list[str] = []
    manuelles: list[str] = []
    supplantees: list[str] = []
    if CHEMIN_KIT.exists():
        candidates = [p for p in sorted(CHEMIN_KIT.iterdir())
                      if p.is_file() and p.suffix.lower() in PIECES]
        retenues = {p.name for p in pieces_retenues(candidates, langue, pays)}
        for piece in candidates:
            etiquettes = {e.lower() for e in piece.name.split(".")[1:-1]}
            if piece.name in retenues:
                shutil.copy2(piece, cible / piece.name)
                fichiers.append(piece.name)
            elif ETIQUETTE_MANUELLE in etiquettes:
                # Pas « destinee a un autre contexte » : mise de cote par
                # choix, et disponible dans le kit quand on la demande.
                manuelles.append(piece.name)
            elif _piece_convient(piece, langue, pays):
                # Elle conviendrait, mais une version PLUS SPECIFIQUE l'a
                # emporte. Le dire autrement serait faux.
                gagnante = next(n for n in retenues
                                if _famille_de_piece(Path(n)) == _famille_de_piece(piece))
                supplantees.append(f"{piece.name} (au profit de {gagnante})")
            else:
                ecartees.append(piece.name)

    if ecartees and langue in LANGUES_SERVIES:
        avertissements.append(
            f"Offre détectée : {langue}/{pays}. Pièces non jointes car destinées à un autre "
            f"contexte : {', '.join(ecartees)}"
        )
    elif ecartees:
        # Langue allemande ou indeterminee : AUCUN CV ne convient, et le dire
        # vaguement laisserait croire a un detail de contexte.
        avertissements.append(
            f"AUCUNE PIECE ETIQUETEE PAR LANGUE N'A ETE JOINTE : l'annonce est "
            f"en {langue_lisible(langue)}, et tes pieces sont etiquetees fr ou "
            f"en. Ecartees : {', '.join(ecartees)}. Tu peux les telecharger "
            f"depuis l'onglet Documents si tu decides de repondre quand meme."
        )
    if supplantees:
        avertissements.append(
            f"Version moins spécifique non jointe : {', '.join(supplantees)}. "
            f"Si tu préfères l'autre, télécharge-la depuis l'onglet Documents."
        )
    if manuelles:
        avertissements.append(
            f"Jamais jointe automatiquement, téléchargeable depuis l'onglet "
            f"Documents si on te la demande : {', '.join(manuelles)}"
        )
    if not any(f.lower().endswith(".pdf") for f in fichiers):
        avertissements.append("Aucun CV PDF retenu pour cette offre : à vérifier avant envoi.")

    # --- 3. Fiche de l'offre, pour preparer l'entretien ------------------
    explication = offre.get("explication") or []
    lignes_expl = "\n".join(
        f"- {c.get('libelle')} : {c.get('points'):+g} pts"
        + (f" ({c.get('detail')})" if c.get("detail") else "")
        for c in explication
    )
    fiche = f"""# {valeurs['titre']}

**Employeur** : {valeurs['employeur']}
**Lieu** : {valeurs['lieu']}
**Contrat** : {valeurs['contrat'] or 'non précisé'}
**Salaire annoncé** : {valeurs['salaire']}
**Source** : {valeurs['source']}
**Annonce** : {valeurs['url'] or 'lien non disponible'}
**Score** : {valeurs['score']}

## Pourquoi cette offre est sortie

{lignes_expl or '(aucune contribution enregistree)'}

## Texte de l'annonce tel que collecte

{offre.get('description') or '(non collecte - le mail ne contenait quun extrait)'}

---
Dossier généré le {valeurs['date']}. Relis la lettre avant envoi.
"""
    (cible / "fiche-offre.md").write_text(fiche, encoding="utf-8")
    fichiers.append("fiche-offre.md")

    # --- 4. La lettre en PDF, sous un nom envoyable -----------------------
    from . import rendu

    pieces_envoi: list[str] = []
    rendu_lettre = None
    if "lettre-de-motivation.md" in fichiers:
        rendu_lettre = rendu.lettre_en_pdf(
            (cible / "lettre-de-motivation.md").read_text(encoding="utf-8"),
            cible / f"{rendu.prefixe()}-Lettre-de-motivation.pdf",
        )
        if rendu_lettre.ok:
            fichiers.append(rendu_lettre.chemin.name)
            pieces_envoi.append(rendu_lettre.chemin.name)
            if rendu_lettre.marqueurs_restants:
                avertissements.append(
                    f"{rendu_lettre.marqueurs_restants} marqueur(s) encore à "
                    f"compléter dans la lettre : ils sont surlignés en rouge "
                    f"dans le PDF."
                )
        else:
            avertissements.append(rendu_lettre.message)

    # --- 5. DEUX paquets, et c'est le point important ---------------------
    #
    # `fiche-offre.md` contient le score, l'explication et le texte brut de
    # l'annonce : c'est sa note de preparation d'entretien. Elle n'a RIEN a
    # faire dans ce qu'il envoie a un recruteur. Les deux paquets sont donc
    # distincts, et celui de l'envoi ne contient que des pieces nommees pour
    # etre recues.
    for f in fichiers:
        if f.lower().endswith((".pdf", ".docx", ".odt")) and f not in pieces_envoi:
            pieces_envoi.append(f)

    # --- 6. La note d'entretien, taillee a CETTE offre -------------------
    #
    # `fiche-offre.md` dit pourquoi l'offre est sortie. Elle ne dit pas ce
    # qu'on va lui demander. C'est ce que fait cette note : les sections de
    # son fichier 17 qui concernent cette annonce, chacune avec l'ancrage qui
    # justifie sa presence. Elle rejoint le paquet complet, JAMAIS l'envoi.
    from . import entretien as _entretien

    preparation = _entretien.preparer(offre, pieces=pieces_envoi)
    (cible / "preparation-entretien.md").write_text(
        _entretien.rendre_markdown(preparation, offre), encoding="utf-8")
    fichiers.append("preparation-entretien.md")
    if not preparation.kit_disponible:
        avertissements.extend(preparation.avertissements)

    # Les paquets d'une generation precedente contenaient la fiche de
    # preparation d'entretien. On les supprime : un paquet perime qui traine
    # est un paquet qui peut partir.
    for vieux in cible.glob("*.zip"):
        vieux.unlink(missing_ok=True)

    archive = cible / f"{nom_dossier}-DOSSIER-COMPLET.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
        for f in fichiers:
            z.write(cible / f, arcname=f)

    envoi = cible / f"{rendu.prefixe()}-candidature.zip"
    with zipfile.ZipFile(envoi, "w", zipfile.ZIP_DEFLATED) as z:
        for f in pieces_envoi:
            z.write(cible / f, arcname=rendu.nom_pour_envoi(f))

    if not pieces_envoi:
        avertissements.append(
            "Le paquet d'envoi est VIDE : aucune piece en PDF. Il manque au "
            "moins ton CV — exporte-le et depose-le dans le kit."
        )

    return ResultatDossier(
        chemin=cible,
        fichiers=fichiers,
        gabarit_lettre=gabarit_lettre.name if gabarit_lettre else "",
        kit_provisoire=provisoire,
        avertissements=avertissements,
        pieces_envoi=[rendu.nom_pour_envoi(f) for f in pieces_envoi],
        assemblage=assemble.as_dict() if assemble else {},
        preparation=preparation.as_dict(),
    )

"""La porte de validation, rejouee sur LE TEXTE QUI PART.

Une porte qui ne validerait que la sortie du gabarit ne vaudrait rien des
qu'il y a un editeur : il peut lui aussi casser un accent, supprimer la ligne
de reference, laisser un crochet ou amputer une phrase.

DEUX NOTIONS QU'ON NE CONFOND JAMAIS :

    ENREGISTRER n'est JAMAIS bloque. Un editeur qui refuse de sauvegarder un
    texte intermediaire est inutilisable, a plus forte raison au telephone.

    ENVOYER l'est. `envoyable` est faux, et chaque controle en echec porte son
    constat et son `quoi_faire`.

TROIS ETATS PAR CONTROLE, et le troisieme compte autant que les autres :

    ok           : verifie, conforme.
    echec        : verifie, non conforme. On dit quoi et ou.
    indisponible : LE CONTROLE N'A PAS PU TOURNER. Ce n'est pas un `ok`.
                   C'est la distinction que `Affinement.depassement` a du
                   apprendre parce que l'ecran annoncait « proposition
                   refusee » quand rien n'avait ete propose.

Un controle bloquant `indisponible` rend `envoyable` faux, avec une raison
distincte d'un echec. Il reste la sortie « J'assume », journalisee — comme
pour l'empreinte de gabarit, et pour la meme raison : faire taire une alarme
oblige a ecrire qu'on l'assume.

PERIMETRE DE CE MODULE (E1). Les six controles propres au TEXTE EDITE, plus le
temoin d'assiette. Les dix controles du paquet d'envoi — pieces annoncees,
absence de score, provenance, accents dans le PDF — relevent de la solution B
et viendront s'ajouter ici, dans la meme liste.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import lettre as L
from . import preferences
from .config import contient, normaliser

# --------------------------------------------------------------------------
# Un controle
# --------------------------------------------------------------------------

OK = "ok"
ECHEC = "echec"
INDISPONIBLE = "indisponible"


@dataclass
class Controle:
    code: str
    etat: str
    bloquant: bool
    constat: str = ""
    quoi_faire: str = ""
    # Les paragraphes concernes, pour que l'ecran surligne la bonne carte.
    paragraphes: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.etat == OK

    def as_dict(self) -> dict[str, Any]:
        return {"code": self.code, "etat": self.etat, "bloquant": self.bloquant,
                "constat": self.constat, "quoi_faire": self.quoi_faire,
                "paragraphes": self.paragraphes}


@dataclass
class Verdict:
    envoyable: bool
    controles: list[Controle]

    @property
    def echecs(self) -> list[Controle]:
        return [c for c in self.controles if c.etat == ECHEC and c.bloquant]

    @property
    def indisponibles(self) -> list[Controle]:
        return [c for c in self.controles if c.etat == INDISPONIBLE and c.bloquant]

    @property
    def a_regler(self) -> int:
        return len(self.echecs) + len(self.indisponibles)

    def as_dict(self) -> dict[str, Any]:
        return {"envoyable": self.envoyable,
                "a_regler": self.a_regler,
                "controles": [c.as_dict() for c in self.controles]}


# --------------------------------------------------------------------------
# 0. Le temoin d'assiette — sans lui, tous les autres ne valent rien
# --------------------------------------------------------------------------


def _assiette(repertoire: Path, lettre: L.Lettre | None) -> Controle:
    """La porte a-t-elle quelque chose a controler ?

    SIX CONTROLES AU VERT SUR UN DOSSIER VIDE SONT SIX CONTROLES QUI NE VALENT
    RIEN. Une session a failli rapporter sept zeros qui valaient zero parce que
    la liste etait vide ; une autre a conclu « fichiers identiques » sur des
    empreintes egales de trois erreurs 404. Ce controle est le temoin, et il est
    bloquant.
    """
    if lettre is None:
        return Controle("assiette", ECHEC, True,
                        f"Aucune lettre dans {repertoire.name}.",
                        "Génère le dossier d'abord.")
    if not lettre.paragraphes:
        return Controle("assiette", ECHEC, True,
                        "La lettre est vide : zéro paragraphe.",
                        "Repars du gabarit, ou colle un texte.")
    corps = lettre.texte.strip()
    if len(corps) < 200:
        return Controle("assiette", ECHEC, True,
                        f"La lettre fait {len(corps)} caractères : il n'y a "
                        f"rien à contrôler.",
                        "Une lettre de candidature fait au moins quelques "
                        "paragraphes. Repars du gabarit.")
    return Controle("assiette", OK, True,
                    f"{len(lettre.paragraphes)} paragraphes, "
                    f"{len(corps)} caractères à contrôler.")


# --------------------------------------------------------------------------
# 1. Ce qu'il refuse d'affirmer — DETERMINISTE, AVANT TOUT APPEL D'AGENT
# --------------------------------------------------------------------------


def _affirmations_interdites(lettre: L.Lettre) -> Controle:
    """Une affirmation qu'il refuse de faire est-elle dans la lettre ?

    C'EST LE CONTROLE LE PLUS RENTABLE DE LA PORTE, et il est deterministe.

    Les regles viennent de `preferences.affirmations_refusees()` : la cle
    `affirmations_refusees` de la configuration, tant que le magasin n'est pas
    branche. Les cas qu'elles couvrent ont tous la meme forme : UNE AFFIRMATION
    FAUSSE QUI SURVIT A SA PROPRE CORRECTION. Corrigee dans le kit, elle
    ressort d'un gabarit du serveur, d'une copie en ligne, d'une proposition de
    l'affinement, et part dans les candidatures pendant qu'on la croit reglee.

    Une affirmation qui survit a sa correction ne se rattrape pas par de la
    relecture attentive : elle se rattrape par une recherche de motif qui ne
    fatigue pas. D'ou : recherche LITTERALE, instantanee, infalsifiable, et
    AVANT tout appel d'agent. Un agent qui met vingt secondes ne doit pas etre
    le filet de securite d'un defaut qu'une milliseconde attrape.

    L'AGENT, LUI, SERVIRA A AUTRE CHOSE (E2) : reperer les formulations
    EQUIVALENTES qu'une recherche litterale manque — une tournure au futur, un
    synonyme, un « bientot ». Ce controle-ci ne les verra pas, et il ne doit
    pas pretendre le contraire : son constat dit sur quoi il a porte.

    BLOQUANT. Meme raison que l'empreinte de gabarit : les incidents connus
    sont tous passes par un avertissement ignore, et un avertissement dans un
    journal est encore de la prose. La sortie est « J'assume », qui est un
    geste, pas un silence.
    """
    regles, origine = preferences.affirmations_refusees()
    dispo = preferences.disponible()

    if not regles:
        # Magasin branche mais vide, ou magasin absent sans repli : on ne
        # conclut RIEN. Une liste vide parce qu'il n'a rien interdit et une
        # liste vide parce que le magasin n'est pas lisible sont deux
        # situations opposees.
        return Controle("affirmations_interdites", INDISPONIBLE, True,
                        dispo.raison or "Aucune règle à vérifier.",
                        "Branche le magasin de préférences, ou assume cette "
                        "version en connaissance de cause.")

    trouves: list[tuple[L.Paragraphe, preferences.Preference, str]] = []
    for p in lettre.paragraphes:
        cible = normaliser(p.texte)
        for regle in regles:
            for motif in regle.motifs:
                if contient(cible, motif):
                    trouves.append((p, regle, motif))
                    break

    if not trouves:
        return Controle(
            "affirmations_interdites", OK, True,
            f"{len(regles)} règle(s) vérifiée(s) sur "
            f"{len(lettre.paragraphes)} paragraphes, par recherche littérale "
            f"({origine}). Les formulations équivalentes ne sont pas couvertes "
            f"par ce contrôle.")

    lignes = []
    for p, regle, motif in trouves:
        lignes.append(f"« {motif} » dans le paragraphe {p.id} — {regle.libelle}")
    return Controle(
        "affirmations_interdites", ECHEC, True,
        "Cette lettre affirme ce que tu as décidé de ne jamais affirmer :\n"
        + "\n".join(f"  · {l}" for l in lignes),
        "Retire la formulation, ou assume cette version — « J'assume » est "
        "journalisé. Origine de la règle : "
        + "; ".join(sorted({r.provenance for _p, r, _m in trouves})),
        paragraphes=sorted({p.id for p, _r, _m in trouves}))


# --------------------------------------------------------------------------
# 2. L'empreinte du gabarit — l'anti-derive
# --------------------------------------------------------------------------


def _filiation_gabarit(lettre: L.Lettre) -> Controle:
    """Le gabarit dont cette lettre est issue a-t-il ete corrige depuis ?

    `empreintes.py` existe parce qu'une lettre portant une affirmation fausse
    partait malgre tout, alors qu'elle avait ete corrigee cote kit. Deux
    arborescences paralleles, aucune synchronisation, aucune alarme.

    Une lettre redigee en octobre et envoyee en decembre est le meme risque,
    avec une difference qui l'aggrave : le kit est surveille, une lettre figee
    dans un dossier de candidature ne l'est par rien.

    L'EMPREINTE DE FILIATION N'EST JAMAIS RAFRAICHIE AUTOMATIQUEMENT. Un
    controle qui relirait l'empreinte du document surveille mesurerait sa
    propre copie et passerait toujours.
    """
    f = lettre.filiation
    if not f.gabarit_empreinte:
        return Controle(
            "filiation_gabarit", INDISPONIBLE, True,
            "Cette lettre ne porte pas l'empreinte du gabarit dont elle est "
            "issue : elle a été générée avant l'éditeur."
            if lettre.meta_reconstruite else
            "Aucune empreinte de gabarit enregistrée pour cette lettre.",
            "Repars du gabarit pour la doter d'une filiation, ou assume cette "
            "version. Tant que la filiation manque, on ne peut pas savoir si "
            "le gabarit a changé — et ne pas savoir n'est pas « tout va bien ».")

    copie = lettre.repertoire / L.NOM_GABARIT
    actuelle = L.empreinte_fichier(copie)
    if not actuelle:
        return Controle(
            "filiation_gabarit", INDISPONIBLE, True,
            f"La copie du gabarit ({L.NOM_GABARIT}) est absente du dossier : "
            f"impossible de comparer.",
            "Repars du gabarit, ce qui redéposera la copie.")

    if actuelle == f.gabarit_empreinte:
        return Controle("filiation_gabarit", OK, True,
                        f"Issue de {f.gabarit_nom} ({f.gabarit_empreinte[:8]}…), "
                        f"inchangé.")

    return Controle(
        "filiation_gabarit", ECHEC, True,
        f"Le gabarit dont cette lettre est issue a été corrigé depuis.\n"
        f"  Lettre rédigée le {lettre.redigee_le or '?'} à partir de "
        f"{f.gabarit_nom}\n"
        f"  empreinte à la rédaction : {f.gabarit_empreinte}\n"
        f"  empreinte du gabarit lu  : {actuelle}\n"
        f"Cette lettre peut contenir une formulation corrigée depuis.",
        "Repars du gabarit corrigé, ou assume cette version — « J'assume » "
        "est journalisé.")


# --------------------------------------------------------------------------
# 3. Les marqueurs perimes
# --------------------------------------------------------------------------

# Les seuls marqueurs qui ARRIVENT DANS LE TEXTE. Le score, la famille et la
# zone n'y arrivent pas : un rescorer, qui recalcule toutes les offres, ne doit
# donc mettre AUCUN dossier en alerte.
MARQUEURS_SURVEILLES = ("employeur", "titre", "lieu", "contact",
                        "contact_civilite", "adresse_entreprise", "reference")


def _marqueurs_perimes(lettre: L.Lettre, offre: dict[str, Any] | None) -> Controle:
    if offre is None:
        return Controle("marqueurs_perimes", INDISPONIBLE, True,
                        "L'offre n'a pas été fournie : rien à comparer.",
                        "Ouvre le dossier depuis la console.")
    figes = lettre.filiation.marqueurs_resolus
    if not figes:
        return Controle(
            "marqueurs_perimes", INDISPONIBLE, True,
            "Cette lettre ne porte pas les valeurs d'offre figées à la "
            "rédaction : impossible de savoir ce qui a vieilli.",
            "Repars du gabarit pour les enregistrer, ou assume cette version.")

    from . import dossier as _dossier

    courants = _dossier._valeurs(offre)
    ecarts = []
    for cle in MARQUEURS_SURVEILLES:
        avant = (figes.get(cle) or "").strip()
        apres = (courants.get(cle) or "").strip()
        if avant != apres:
            ecarts.append((cle, avant, apres))

    if not ecarts:
        return Controle("marqueurs_perimes", OK, True,
                        f"{len(MARQUEURS_SURVEILLES)} marqueurs comparés, "
                        f"aucun n'a changé depuis la rédaction.")

    lignes = [f"{cle} : « {avant or '(vide)'} » → « {apres or '(vide)'} »"
              for cle, avant, apres in ecarts]
    return Controle(
        "marqueurs_perimes", ECHEC, True,
        "L'offre a changé depuis que cette lettre a été rédigée. La lettre "
        "porte l'ancienne valeur :\n" + "\n".join(f"  · {l}" for l in lignes),
        "Remplace la valeur dans le paragraphe concerné — la console te "
        "propose la substitution ciblée. Ne régénère pas : tes paragraphes "
        "disparaîtraient.")


# --------------------------------------------------------------------------
# 4. L'assemblage perime
# --------------------------------------------------------------------------


def _assemblage_perime(lettre: L.Lettre, offre: dict[str, Any] | None) -> Controle:
    """La phrase « Votre annonce cite ... » cite-t-elle encore ce que le
    scoring releve ?

    C'EST UN CAS VECU. L'annonce enumere une liste de technologies en vrac ; le
    scoring en tire une famille sur un seul sigle de la liste ; `assemblage`
    ecrirait « Votre annonce cite <ce sigle> » dans une lettre qui dit ne pas
    avoir ce vecu. Si le scoring est corrige et ne cite plus le sigle, la
    lettre deja redigee le cite encore.
    """
    if not lettre.filiation.assemblage_paragraphe:
        return Controle("assemblage_perime", OK, True,
                        "Cette lettre ne porte aucune phrase d'assemblage : "
                        "rien à périmer.")
    if offre is None:
        return Controle("assemblage_perime", INDISPONIBLE, True,
                        "L'offre n'a pas été fournie : rien à comparer.",
                        "Ouvre le dossier depuis la console.")

    fige = lettre.filiation.assemblage_paragraphe.strip()
    present = any(p.texte.strip() == fige for p in lettre.paragraphes)
    if not present:
        # Il l'a reecrite ou supprimee : c'est sa decision, pas une peremption.
        return Controle("assemblage_perime", OK, True,
                        "La phrase d'assemblage a été réécrite ou retirée : "
                        "c'est ta décision, pas une péremption.")

    from . import assemblage as _assemblage

    try:
        courant = _assemblage.assembler(
            offre, langue=lettre.filiation.langue_gabarit or "fr").paragraphe.strip()
    except Exception as exc:  # pragma: no cover - defensif
        return Controle("assemblage_perime", INDISPONIBLE, True,
                        f"L'assemblage n'a pas pu être recalculé : {exc}",
                        "Réessaie, ou assume cette version.")

    if courant == fige:
        return Controle("assemblage_perime", OK, True,
                        "La phrase d'assemblage cite toujours ce que le "
                        "scoring relève.")
    return Controle(
        "assemblage_perime", ECHEC, True,
        "La phrase qui cite l'annonce ne correspond plus à ce que le scoring "
        "relève :\n"
        f"  dans la lettre : « {fige} »\n"
        f"  aujourd'hui    : « {courant or '(plus rien à citer)'} »",
        "Remplace la phrase, ou retire-la. Citer un terme que l'annonce ne "
        "contient pas est le défaut le plus coûteux de la lettre.",
        paragraphes=[p.id for p in lettre.paragraphes if p.texte.strip() == fige])


# --------------------------------------------------------------------------
# 5. La structure de la lettre — l'amputation silencieuse
# --------------------------------------------------------------------------


def _structure_lettre(lettre: L.Lettre) -> Controle:
    """Ce qui arrivera DANS LE PDF a-t-il encore la forme d'une lettre ?

    DEFAUT STRUCTUREL DE `rendu._en_html` : il fait `break` des qu'un bloc se
    declare interne (`bloc_a_jeter`), lui ET tout ce qui suit. Si un paragraphe
    destine au recruteur contient la formule — en citant l'annonce, par exemple
    « nous vous demandons de ne pas envoyer de photo » — la lettre est coupee
    la et PERD SA SIGNATURE, sans qu'aucun message ne le dise.

    On ne controle donc pas le `.md` : on controle ce que le rendu en fait.
    """
    from . import rendu
    from .dossier import REPERES_APPEL

    corps = rendu._corps(lettre.texte)
    html, _restants = rendu._en_html(corps)
    rendu_texte = html

    if not rendu_texte.strip():
        return Controle("structure_lettre", ECHEC, True,
                        "Le rendu de cette lettre est VIDE : rien n'arriverait "
                        "dans le PDF.",
                        "Le premier bloc se déclare probablement interne "
                        "(« à supprimer avant envoi »). Retire la formule.")

    # L'amputation : le rendu fait-il au moins 60 % du corps source ?
    source = len(corps.strip())
    rendu_utile = len(rendu_texte)
    if source and rendu_utile < source * 0.6:
        coupe = next((p.id for p in lettre.paragraphes
                      if rendu.bloc_a_jeter(p.texte)), "")
        return Controle(
            "structure_lettre", ECHEC, True,
            f"Le PDF ne contiendrait qu'une partie de la lettre : "
            f"{rendu_utile} caractères rendus pour {source} dans le texte.",
            "Un paragraphe se déclare interne (« à supprimer avant envoi », "
            "« ne pas envoyer »…) et le rendu s'arrête là, signature comprise. "
            "Reformule ce paragraphe."
            + (f" Le premier concerné est {coupe}." if coupe else ""),
            paragraphes=[coupe] if coupe else [])

    if not any(r in rendu_texte for r in REPERES_APPEL):
        return Controle(
            "structure_lettre", ECHEC, True,
            "Le PDF ne contiendrait aucune formule d'appel "
            f"({', '.join(REPERES_APPEL[:3])}…).",
            "Une lettre de candidature s'ouvre sur une formule d'appel. "
            "Vérifie que le paragraphe n'a pas été supprimé.")

    return Controle("structure_lettre", OK, True,
                    f"Formule d'appel présente, {rendu_utile} caractères "
                    f"rendus sur {source}.")


# --------------------------------------------------------------------------
# 6. La provenance — AVERTISSANT, et je dis pourquoi j'ai change d'avis
# --------------------------------------------------------------------------


def _provenance_coherente(lettre: L.Lettre) -> Controle:
    """La provenance par paragraphe est-elle exploitable ?

    LA CONCEPTION LE DISAIT BLOQUANT. APRES IMPLEMENTATION, IL NE DOIT PAS
    L'ETRE, et l'argument est simple : une incoherence de provenance
    n'atteint JAMAIS ce que le recruteur recoit. Bloquer un envoi pour une
    erreur de comptabilite interne, c'est transformer un defaut de confort en
    dossier qui ne part pas — exactement ce que cette conception combat.

    Il reste utile : c'est lui qui garantit que l'avertissement chiffre de
    « Repartir du gabarit » — « 3 paragraphes, 412 mots » — dit vrai. Un
    avertissement qui se trompe sur ce qu'il va perdre est pire qu'une absence
    d'avertissement.
    """
    ids = [p.id for p in lettre.paragraphes]
    doublons = sorted({i for i in ids if ids.count(i) > 1})
    inconnues = sorted({p.origine for p in lettre.paragraphes
                        if p.origine not in L.ORIGINES})

    if lettre.meta_reconstruite:
        return Controle(
            "provenance_coherente", INDISPONIBLE, False,
            "Dossier généré avant l'éditeur : la provenance a été "
            "reconstruite, tous les paragraphes sont attribués au gabarit.",
            "Dès que tu modifies un paragraphe, il passera à ton nom. Aucune "
            "action nécessaire.")
    if doublons:
        return Controle("provenance_coherente", ECHEC, False,
                        f"Identifiants de paragraphe en double : "
                        f"{', '.join(doublons)}.",
                        "Signale-le : c'est un défaut du programme, pas de ta "
                        "lettre. L'envoi n'est pas bloqué.")
    if inconnues:
        return Controle("provenance_coherente", ECHEC, False,
                        f"Origines inconnues : {', '.join(inconnues)}.",
                        "Signale-le. L'envoi n'est pas bloqué.")
    return Controle(
        "provenance_coherente", OK, False,
        f"{len(lettre.paragraphes_de_lui)} paragraphe(s) de toi "
        f"({lettre.mots_de_lui} mots), {len(ids)} au total.")


# --------------------------------------------------------------------------
# Entree publique
# --------------------------------------------------------------------------


def verifier(repertoire: Path, offre: dict[str, Any] | None = None) -> Verdict:
    """Le verdict sur le texte TEL QU'IL EST sur le disque.

    N'ECRIT RIEN. Peut etre rejoue autant de fois qu'on veut, y compris apres
    une correction manuelle du `.md`.
    """
    repertoire = Path(repertoire)
    try:
        lue: L.Lettre | None = L.lire(repertoire)
    except FileNotFoundError:
        lue = None

    assiette = _assiette(repertoire, lue)
    if assiette.etat != OK or lue is None:
        # On ne rend PAS six `ok` sur un dossier vide : on rend un seul
        # controle, celui qui dit qu'il n'y a rien a controler.
        return Verdict(False, [assiette])

    controles = [
        assiette,
        _affirmations_interdites(lue),
        _filiation_gabarit(lue),
        _marqueurs_perimes(lue, offre),
        _assemblage_perime(lue, offre),
        _structure_lettre(lue),
        _provenance_coherente(lue),
    ]
    bloquants_en_defaut = [c for c in controles
                           if c.bloquant and c.etat != OK]
    return Verdict(not bloquants_en_defaut, controles)

"""Chargement de la configuration et utilitaires de normalisation de texte.

Toute la comparaison de motifs passe par `normaliser()` : sans accents, en
minuscules, ponctuation reduite a des espaces. Cela permet d'ecrire les motifs
dans le `criteres.yaml` de la configuration sans se soucier des accents ni de la casse.
"""

from __future__ import annotations

import os
import re
import unicodedata
from dataclasses import dataclass
from collections.abc import Mapping
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

# --------------------------------------------------------------------------
# Emplacements. Tout est surchargeable par variable d'environnement pour que
# le meme code tourne en local (Windows) et sur le serveur.
# --------------------------------------------------------------------------

RACINE = Path(__file__).resolve().parent.parent.parent


# Les secrets vivent dans config/.env. Ils ne doivent apparaitre NULLE PART
# ailleurs : ni journal, ni sortie de commande, ni message de diagnostic. Un
# service peut tres bien renvoyer dans son corps d'erreur ce qu'on lui a
# envoye — c'est la que les secrets fuient, pas dans le code qu'on relit.
SECRETS = (
    "FT_CLIENT_SECRET", "FT_CLIENT_ID",
    "VEILLE_IMAP_MOTDEPASSE", "VEILLE_SMTP_MOTDEPASSE",
    "VEILLE_VAPID_PRIVEE",
)


def masquer(texte: str | None) -> str:
    """Remplace toute valeur secrete connue par un marqueur.

    A passer sur tout ce qui vient de l'exterieur avant de l'afficher :
    corps de reponse HTTP, message d'exception, trace.
    """
    resultat = texte or ""
    for nom in SECRETS:
        valeur = os.environ.get(nom, "")
        if valeur and len(valeur) >= 8:
            resultat = resultat.replace(valeur, f"…{nom} masque…")
    return resultat


# --------------------------------------------------------------------------
# Une variable d'environnement inconnue doit ECHOUER, pas etre ignoree
#
# POURQUOI CE CODE EXISTE : en deboguant, `VEILLE_BASE=/tmp/x.sqlite` a ete
# pose pour isoler un script de la vraie base. Le nom exact est `VEILLE_DB`.
# Personne ne lit `VEILLE_BASE`, donc le script a tourne sur la BASE REELLE et
# y a ecrit une offre de test.
#
# Le defaut n'est pas la faute de frappe — elle rejouera — mais le fait qu'un
# nom inconnu ne fasse RIEN. Une variable qu'on prend la peine de poser exprime
# une intention ; l'ignorer en silence trahit cette intention au pire moment,
# celui ou on croit etre isole.
#
# Desormais : toute variable `VEILLE_*` ou `FT_*` non reconnue arrete le
# programme, en nommant la variable et en proposant le nom le plus proche.
VARIABLES_CONNUES = frozenset({
    # Chemins
    "VEILLE_CONFIG", "VEILLE_SDK_AGENT",
    "VEILLE_CRITERES", "VEILLE_SOURCES", "VEILLE_DB", "VEILLE_KIT",
    "VEILLE_DOSSIERS", "VEILLE_VAPID", "VEILLE_ENV",
    # Magasin de preferences PARTAGE avec Pupitre. Son contrat est
    # ecrit ailleurs : la veille ne fait que le LIRE, et n'en cree
    # jamais un second. Non posee aujourd'hui : `preferences.disponible()`
    # rend donc False, et les controles qui en dependent se declarent
    # indisponibles — jamais « au vert ».
    "VEILLE_PREFERENCES",
    # Console
    "VEILLE_HTTPS", "VEILLE_URL", "VEILLE_VAPID_PRIVEE",
    # Courriel
    "VEILLE_IMAP_HOTE", "VEILLE_IMAP_PORT", "VEILLE_IMAP_UTILISATEUR",
    "VEILLE_IMAP_MOTDEPASSE", "VEILLE_IMAP_DOSSIER", "VEILLE_IMAP_MODE",
    "VEILLE_SMTP_HOTE", "VEILLE_SMTP_PORT", "VEILLE_SMTP_UTILISATEUR",
    "VEILLE_SMTP_MOTDEPASSE",
    "VEILLE_MAIL_DESTINATAIRE", "VEILLE_MAIL_EXPEDITEUR",
    # France Travail
    "FT_CLIENT_ID", "FT_CLIENT_SECRET",
    # Deploiement (compose.yml du modele)
    "VEILLE_EMPLOI_ENV", "VEILLE_EMPLOI_VERSION", "VEILLE_EMPLOI_URL_PUBLIQUE",
})

PREFIXES_SURVEILLES = ("VEILLE_", "FT_")


class VariableInconnue(RuntimeError):
    """Une variable d'environnement du projet porte un nom que personne ne lit."""


def variables_inconnues(environnement=None) -> list[tuple[str, str]]:
    """(nom_pose, nom_le_plus_proche) pour chaque variable non reconnue."""
    import difflib

    env = environnement if environnement is not None else os.environ
    trouvees = []
    for nom in sorted(env):
        if not nom.startswith(PREFIXES_SURVEILLES) or nom in VARIABLES_CONNUES:
            continue
        proches = difflib.get_close_matches(nom, VARIABLES_CONNUES, n=1, cutoff=0.6)
        trouvees.append((nom, proches[0] if proches else ""))
    return trouvees


def verifier_environnement(environnement=None) -> None:
    """Arrete tout si une variable du projet n'est pas reconnue."""
    inconnues = variables_inconnues(environnement)
    if not inconnues:
        return
    lignes = []
    for nom, proche in inconnues:
        suggestion = f" — voulais-tu dire {proche} ?" if proche else ""
        lignes.append(f"  {nom}{suggestion}")
    raise VariableInconnue(
        "Variable(s) d'environnement non reconnue(s) par ce projet :\n"
        + "\n".join(lignes)
        + "\n\nUne variable qui n'est lue par personne ne fait RIEN : le programme\n"
          "aurait tourne sur la configuration par defaut, donc sur la VRAIE base.\n"
          "Corrige le nom, ou retire la variable."
    )


verifier_environnement()


def environnement() -> str | None:
    """Le mode de deploiement (`prod`, `staging`, `ci`), ou None hors conteneur."""
    return os.environ.get("VEILLE_EMPLOI_ENV", "").strip() or None


def version() -> str:
    """La version de l'image (`VEILLE_EMPLOI_VERSION`), ou `dev`."""
    return os.environ.get("VEILLE_EMPLOI_VERSION", "").strip() or "dev"


def _chemin(env: str, defaut: Path) -> Path:
    brut = os.environ.get(env)
    return Path(brut).expanduser() if brut else defaut


# --------------------------------------------------------------------------
# Le dossier de configuration
#
# Un dossier porte tout ce qui est propre a une instance : `criteres.yaml`,
# `sources.yaml`, `gabarits/` et `empreintes-kit.json`. Le code ne connait que
# la regle qui le trouve ; `veille config verifier <dossier>` dit s'il est sain.
# --------------------------------------------------------------------------

CONFIG_MONTEE = Path("/config")
"""Le dossier que le conteneur monte, en lecture seule, quand il y en a un."""

# Sans rien de designe, le code sert l'exemple livre avec lui : jamais la
# configuration d'une instance, qui vit hors du code (`VEILLE_CONFIG`).
_DEFAUT = RACINE / "exemple"

VERSIONS_CONNUES = frozenset({1})


class ConfigurationInvalide(RuntimeError):
    """Un dossier de configuration est absent, ou son contenu est inutilisable."""


def _non_vide(dossier: Path) -> bool:
    try:
        return dossier.is_dir() and any(dossier.iterdir())
    except OSError:
        return False


def resoudre_dossier(environ: Mapping[str, str], montee: Path) -> tuple[Path, bool]:
    """Le dossier de configuration, et s'il est DESIGNE (plutot que par defaut).

    1. `VEILLE_CONFIG`, si elle est posee et non vide ;
    2. sinon le dossier de `VEILLE_CRITERES`, si elle est posee ;
    3. sinon, en conteneur (`VEILLE_EMPLOI_ENV` posee), `montee` s'il existe et
       n'est pas vide ;
    4. sinon le defaut.

    Fonction pure : elle ne lit que ses arguments (et le disque pour `montee`).
    Un dossier designe mais absent n'est pas refuse ici : ce sont les
    chargeurs qui refusent, pour que les commandes de sauvegarde tournent.
    """
    pose = (environ.get("VEILLE_CONFIG") or "").strip()
    if pose:
        return Path(pose).expanduser(), True
    criteres = (environ.get("VEILLE_CRITERES") or "").strip()
    if criteres:
        return Path(criteres).expanduser().parent, True
    if (environ.get("VEILLE_EMPLOI_ENV") or "").strip() and _non_vide(montee):
        return montee, True
    return _DEFAUT, False


def config_designee() -> bool:
    """Vrai quand une configuration est designee, faux sur le defaut."""
    return resoudre_dossier(os.environ, CONFIG_MONTEE)[1]


# Un seul refus pour tous les gestes (collecte, rescorage, empreintes du kit, et, dans la
# console, dossier, relance, recalcul, affinement) : le message dit l'état et le remède.
MESSAGE_SANS_CONFIGURATION = (
    "aucune configuration n'est désignée : cette console sert l'exemple. "
    "Pose VEILLE_CONFIG (docs/exploitation.md, « La configuration désignée »)."
)


def exiger_designee() -> None:
    """Refuse de noter des offres avec l'exemple : a appeler avant toute collecte ou tout rescorage."""
    if not config_designee():
        raise ConfigurationInvalide(MESSAGE_SANS_CONFIGURATION)


def exiger_configuration() -> None:
    """En prod, la console refuse de demarrer sans configuration designee.

    Pas de repli sur l'exemple : elle servirait les vraies offres notees par lui.
    La resolution, elle, ne leve pas : les commandes de l'instantane tournent toujours.
    Hors prod (sans environnement, `ci`, `staging`), le repli sur l'exemple demeure.
    """
    if environnement() != "prod":
        return
    if not config_designee():
        raise ConfigurationInvalide(
            "en prod, aucune configuration montée : /config est absent ou vide"
        )
    # Un dossier non vide mais cassé (sans criteres.yaml, version inconnue) arrête aussi
    # le démarrage : sinon /sante dirait « montee » d'une console qui ne sait rien noter.
    try:
        charger_criteres()
    except ConfigurationInvalide as e:
        raise ConfigurationInvalide(f"en prod, la configuration montée est inutilisable : {e}") from e


DOSSIER_CONFIG, _DESIGNEE_A_L_IMPORT = resoudre_dossier(os.environ, CONFIG_MONTEE)
CHEMIN_GABARITS = DOSSIER_CONFIG / "gabarits"

CHEMIN_CRITERES = _chemin("VEILLE_CRITERES", DOSSIER_CONFIG / "criteres.yaml")
CHEMIN_SOURCES = _chemin("VEILLE_SOURCES", DOSSIER_CONFIG / "sources.yaml")
CHEMIN_DB = _chemin("VEILLE_DB", RACINE / "donnees" / "veille.sqlite3")
# Le kit de candidature (CV maitre, lettres types, annexe technique) est produit
# par une autre session et n'est pas encore livre : on le lit depuis un
# emplacement configurable et on se rabat sur les gabarits de la configuration.
CHEMIN_KIT = _chemin("VEILLE_KIT", CHEMIN_GABARITS)
CHEMIN_DOSSIERS = _chemin("VEILLE_DOSSIERS", RACINE / "donnees" / "dossiers")


# --------------------------------------------------------------------------
# Normalisation
# --------------------------------------------------------------------------

_NON_ALNUM = re.compile(r"[^a-z0-9%+#./]+")

# On garde `.` et `/` pour "node.js" ou "ci/cd", et `%+#` pour "80%", "C#",
# "C++". Mais un point de fin de phrase restait alors colle au mot : le texte
# "recette fonctionnelle." ne correspondait plus au motif "recette fonctionnelle".
# On ne garde donc `.` et `/` qu'entre deux caracteres alphanumeriques, et
# `%+#` que precedes d'un alphanumerique.
# La regle s'applique au texte ET aux motifs : seule leur coherence compte.
_PONCTUATION_FLOTTANTE = re.compile(
    r"(?<![a-z0-9])[./]|[./](?![a-z0-9])|(?<![a-z0-9])[%+#]"
)


def normaliser(texte: str | None) -> str:
    """Minuscules, sans accents, ponctuation -> espaces, espaces compactes."""
    if not texte:
        return ""
    decompose = unicodedata.normalize("NFKD", texte)
    sans_accents = "".join(c for c in decompose if not unicodedata.combining(c))
    # oe/ae ligatures et quelques equivalences allemandes
    sans_accents = (
        sans_accents.replace("œ", "oe").replace("æ", "ae").replace("ß", "ss")
    )
    minuscule = sans_accents.lower()
    sans_ponctuation = _NON_ALNUM.sub(" ", minuscule)
    sans_flottante = _PONCTUATION_FLOTTANTE.sub(" ", sans_ponctuation)
    return " " + re.sub(r"\s+", " ", sans_flottante).strip() + " "


def contient(texte_normalise: str, motif: str) -> bool:
    """Vrai si `motif` apparait dans un texte deja normalise.

    On encadre d'espaces pour eviter qu'un motif court ("sre", "tma", "amoa")
    ne matche au milieu d'un mot ("desree", "stma").
    """
    m = normaliser(motif).strip()
    if not m:
        return False
    if f" {m} " in texte_normalise:
        return True
    # La barre oblique est gardee a la normalisation pour « ci/cd » ou « and/or ».
    # Consequence imprevue : « Ingenieur qualification/validation » ne repondait
    # pas au motif « qualification validation ». On reessaie en la traitant
    # comme un separateur. Quatre intitules du corpus etaient dans ce cas.
    if "/" in texte_normalise:
        aplati = re.sub(r"\s+", " ", texte_normalise.replace("/", " "))
        return f" {m} " in aplati
    return False


# --------------------------------------------------------------------------
# Chargement
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Criteres:
    brut: dict[str, Any]

    @property
    def familles(self) -> dict[str, Any]:
        return self.brut.get("familles", {})

    @property
    def atouts(self) -> dict[str, Any]:
        return self.brut.get("atouts", {})

    @property
    def zones(self) -> dict[str, Any]:
        return self.brut.get("zones", {})

    @property
    def langues(self) -> dict[str, Any]:
        return self.brut.get("langues", {})

    @property
    def eliminatoires(self) -> dict[str, Any]:
        return self.brut.get("eliminatoires", {})

    @property
    def salaire(self) -> dict[str, Any]:
        return self.brut.get("salaire", {})

    @property
    def contrat(self) -> dict[str, Any]:
        return self.brut.get("contrat", {})

    @property
    def scoring(self) -> dict[str, Any]:
        return self.brut.get("scoring", {})

    @property
    def zone_inconnue_poids(self) -> float:
        return float(self.brut.get("zone_inconnue_poids", 0))


def _lire_yaml(chemin: Path) -> dict[str, Any]:
    if not chemin.exists():
        raise FileNotFoundError(f"Fichier de configuration introuvable : {chemin}")
    with chemin.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def _exiger_dossier_designe() -> None:
    """Un dossier designe qui n'existe pas refuse : jamais de repli sur l'exemple."""
    if _DESIGNEE_A_L_IMPORT and not DOSSIER_CONFIG.is_dir():
        raise ConfigurationInvalide(
            f"Le dossier de configuration designe n'existe pas : {DOSSIER_CONFIG}"
        )


def _probleme_de_version(brut: Any, chemin: Path) -> str | None:
    """Le message qui nomme le fichier et la version lue, ou None si elle est connue."""
    version = brut.get("version") if isinstance(brut, dict) else None
    # `True == 1` en Python : un booleen n'est pas la version 1.
    if isinstance(version, int) and not isinstance(version, bool) and version in VERSIONS_CONNUES:
        return None
    connues = ", ".join(str(v) for v in sorted(VERSIONS_CONNUES))
    if version is None:
        return f"{chemin} : version absente (versions connues : {connues})"
    return f"{chemin} : version {version!r} inconnue (versions connues : {connues})"


@lru_cache(maxsize=1)
def charger_criteres() -> Criteres:
    _exiger_dossier_designe()
    # Un fichier absent est une configuration inutilisable, dite en clair et qui nomme le
    # fichier : un VEILLE_CRITERES resté vers un ancien chemin levait sinon FileNotFoundError.
    if not CHEMIN_CRITERES.is_file():
        raise ConfigurationInvalide(f"{CHEMIN_CRITERES} : fichier obligatoire absent")
    brut = _lire_yaml(CHEMIN_CRITERES)
    probleme = _probleme_de_version(brut, CHEMIN_CRITERES)
    if probleme:
        raise ConfigurationInvalide(probleme)
    return Criteres(brut)


@lru_cache(maxsize=1)
def charger_sources() -> dict[str, Any]:
    _exiger_dossier_designe()
    if not CHEMIN_SOURCES.exists():
        return {}
    return _lire_yaml(CHEMIN_SOURCES)


def _nombre(valeur: Any) -> bool:
    return isinstance(valeur, (int, float)) and not isinstance(valeur, bool)


def verifier_dossier(dossier: Path) -> list[str]:
    """Les problemes d'un dossier de configuration (liste vide : il est sain).

    Ne modifie rien. Un controle qui n'a pas pu tourner est un probleme, jamais
    un succes : un fichier illisible ne passe pas pour « rien a signaler ».
    """
    dossier = Path(dossier)
    if not dossier.is_dir():
        return [f"{dossier} : dossier absent"]
    problemes: list[str] = []

    chemin = dossier / "criteres.yaml"
    brut: Any = None
    if not chemin.is_file():
        problemes.append(f"{chemin} : fichier obligatoire absent")
    else:
        try:
            brut = yaml.safe_load(chemin.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, yaml.YAMLError) as e:
            problemes.append(f"{chemin} : illisible ({type(e).__name__})")
        else:
            if not isinstance(brut, dict):
                problemes.append(f"{chemin} : une table est attendue a la racine")
                brut = None
    if brut is not None:
        version = _probleme_de_version(brut, chemin)
        if version:
            problemes.append(version)
        problemes += _problemes_de_criteres(brut)
        problemes += _problemes_de_motifs(brut)
        essai = _probleme_du_score_d_essai(brut)
        if essai:
            problemes.append(essai)

    sources = dossier / "sources.yaml"
    if sources.exists():
        try:
            contenu = yaml.safe_load(sources.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, yaml.YAMLError) as e:
            problemes.append(f"{sources} : illisible ({type(e).__name__})")
        else:
            # Les collecteurs le lisent comme une table ; vide, il vaut une table vide.
            if contenu is not None and not isinstance(contenu, dict):
                problemes.append(f"{sources} : une table est attendue à la racine")

    for nom in ("lettre.md", "relance.md"):
        if not (dossier / "gabarits" / nom).is_file():
            problemes.append(f"{dossier / 'gabarits' / nom} : gabarit obligatoire absent")
    return problemes


def _problemes_de_criteres(brut: dict[str, Any]) -> list[str]:
    problemes: list[str] = []
    familles = brut.get("familles")
    if not isinstance(familles, dict) or not familles:
        problemes.append("criteres.yaml : familles doit etre une table non vide")
    else:
        for nom, famille in familles.items():
            if not isinstance(famille, dict) or not _nombre(famille.get("poids")):
                problemes.append(f"criteres.yaml : familles.{nom}.poids doit etre numerique")
            if not isinstance(famille, dict) or not isinstance(famille.get("motifs"), list):
                problemes.append(f"criteres.yaml : familles.{nom}.motifs doit etre une liste")

    scoring = brut.get("scoring")
    if not isinstance(scoring, dict) or not _nombre(scoring.get("seuil_interessant")):
        problemes.append("criteres.yaml : scoring.seuil_interessant doit etre numerique")

    geographie = brut.get("geographie")
    if not isinstance(geographie, dict) or not isinstance(geographie.get("pays"), dict):
        problemes.append("criteres.yaml : geographie.pays doit etre une table")
    else:
        # Le score parcourt chaque pays comme une liste de motifs (`scoring.detecter_pays`) :
        # `null` le fait tomber, et une chaîne s'y lit lettre par lettre.
        for pays, motifs in geographie["pays"].items():
            problemes += _problemes_de_liste_de_chaines(motifs, f"geographie.pays.{pays}")

    profil = brut.get("profil")
    if isinstance(profil, dict) and "nom_fichier" in profil:
        nom = profil["nom_fichier"]
        if not isinstance(nom, str) or not nom.strip() or any(m in nom for m in ("/", "\\", "..")):
            problemes.append(
                "criteres.yaml : profil.nom_fichier doit etre une chaine non vide, "
                "sans barre oblique, sans barre inversee et sans .."
            )

    atouts = brut.get("atouts") or {}
    if isinstance(atouts, dict):
        for nom_atout, atout in atouts.items():
            valeur = atout.get("mis_en_avant") if isinstance(atout, dict) else None
            if valeur is not None and valeur is not False and not isinstance(valeur, dict):
                problemes.append(
                    f"criteres.yaml : atouts.{nom_atout}.mis_en_avant doit etre une table"
                )
        mis_en_avant = [n for n, a in atouts.items()
                        if isinstance(a, dict) and isinstance(a.get("mis_en_avant"), dict)
                        and a["mis_en_avant"]]
        if len(mis_en_avant) > 1:
            problemes.append(
                "criteres.yaml : un seul atout peut etre mis_en_avant, "
                f"{len(mis_en_avant)} le sont ({', '.join(map(str, mis_en_avant))})"
            )
    problemes += problemes_d_affirmations(brut)
    problemes += problemes_d_entretien(brut)
    return problemes


# --------------------------------------------------------------------------
# Le score d'essai
#
# Les contrôles de forme ne couvrent pas toutes les sections que lit le score. Trois offres
# inventées, notées avec les critères du dossier, attrapent le reste : une configuration qui
# fait tomber le score n'est jamais `sain`. Ni réseau ni base : `scorer` ne lit que l'offre
# et les critères qu'on lui passe.
# --------------------------------------------------------------------------


def _offres_d_essai() -> list[Any]:
    """Trois offres inventées, neuves à chaque appel (`scorer` les modifie) : en France, avec un
    salaire et un CDI ; en télétravail complet, payée en francs suisses, en intérim ; sans lieu,
    réduite à un extrait."""
    from .models import Offre

    return [
        Offre(titre="Testeuse logiciel", employeur="Entreprise d'essai", lieu="France",
              description="Poste en CDI. Tests fonctionnels et automatisation des tests.",
              type_contrat="CDI", salaire_min=42000.0, salaire_max=48000.0,
              salaire_devise="EUR"),
        Offre(titre="QA Engineer", employeur="Entreprise d'essai", lieu="Remote",
              description="Mission d'intérim de 6 mois, full remote. Test automation.",
              type_contrat="Intérim", salaire_min=90000.0, salaire_devise="CHF"),
        Offre(titre="Ingénieur qualité", donnees_partielles=True),
    ]


def _probleme_du_score_d_essai(brut: dict[str, Any]) -> str | None:
    """Le problème si le score tombe sur une offre d'essai, sinon None. Le type de l'exception
    seulement : une trace Python n'apprend rien de plus à qui corrige son fichier."""
    from .scoring import scorer

    criteres = Criteres(brut)
    try:
        for offre in _offres_d_essai():
            scorer(offre, criteres)
    except Exception as e:  # noqa: BLE001 — un contrôle qui n'a pas tourné n'est pas un succès
        return f"criteres.yaml : le score n'a pas pu tourner : {type(e).__name__}"
    return None


# --------------------------------------------------------------------------
# Les affirmations refusees et l'entretien : deux listes de tables
#
# La verification de forme des motifs (`_problemes_de_forme_des_motifs`) ne
# descend pas dans une liste : ces deux cles ont donc leur propre controle, qui
# nomme le chemin de la meme facon (`cle[rang].champ`). Le code qui les lit
# (`preferences`, `entretien`) s'appuie sur ces memes fonctions : ce que la
# verification refuse, il ne l'emploie pas.
# --------------------------------------------------------------------------

CATEGORIES_DE_DECLENCHEUR = ("attaque", "appui", "rituel")


def _problemes_de_liste_de_chaines(valeur: Any, chemin: str) -> list[str]:
    if not isinstance(valeur, list):
        return [f"criteres.yaml : {chemin} doit etre une liste de chaines"]
    return [f"criteres.yaml : {chemin}[{i}] doit etre une chaine"
            for i, element in enumerate(valeur) if not isinstance(element, str)]


def _chaine_non_vide(valeur: Any) -> bool:
    return isinstance(valeur, str) and bool(valeur.strip())


def problemes_d_affirmations(brut: dict[str, Any]) -> list[str]:
    """`affirmations_refusees`, quand elle est presente : une liste de tables
    `{libelle, valeur, provenance, motifs}`. Le libelle, la valeur et la
    provenance sont des chaines non vides : une regle qu'on ne peut pas nommer
    ni remonter a sa decision est une regle qu'on contournera. Les motifs sont
    une liste de chaines. Liste vide : elle est bien formee, ou absente."""
    if "affirmations_refusees" not in brut:
        return []
    regles = brut["affirmations_refusees"]
    if not isinstance(regles, list):
        return ["criteres.yaml : affirmations_refusees doit etre une liste de tables"]
    problemes: list[str] = []
    for i, regle in enumerate(regles):
        chemin = f"affirmations_refusees[{i}]"
        if not isinstance(regle, dict):
            problemes.append(f"criteres.yaml : {chemin} doit etre une table")
            continue
        problemes += _problemes_de_liste_de_chaines(regle.get("motifs"), f"{chemin}.motifs")
        problemes += [f"criteres.yaml : {chemin}.{champ} doit etre une chaine non vide"
                      for champ in ("libelle", "valeur", "provenance")
                      if not _chaine_non_vide(regle.get(champ))]
    return problemes


def problemes_de_declencheur(entree: Any, chemin: str) -> list[str]:
    """Une entree de `entretien.declencheurs`, de la forme d'`entretien.Declencheur`.
    Liste vide : elle est bien formee.

    La cle de section est exigee : vide, elle se trouverait dans le titre de la
    premiere section venue."""
    if not isinstance(entree, dict):
        return [f"criteres.yaml : {chemin} doit etre une table"]
    problemes: list[str] = []
    if not _chaine_non_vide(entree.get("cle_section")):
        problemes.append(f"criteres.yaml : {chemin}.cle_section doit etre une chaine non vide")
    if entree.get("categorie") not in CATEGORIES_DE_DECLENCHEUR:
        problemes.append(
            f"criteres.yaml : {chemin}.categorie doit valoir attaque, appui ou rituel")
    if "pourquoi" in entree and not isinstance(entree["pourquoi"], str):
        problemes.append(f"criteres.yaml : {chemin}.pourquoi doit etre une chaine")
    if "motifs" in entree:
        problemes += _problemes_de_liste_de_chaines(entree["motifs"], f"{chemin}.motifs")
    if entree.get("pays", "") not in ("", "ch"):
        problemes.append(f"criteres.yaml : {chemin}.pays doit valoir ch, ou etre absent")
    return problemes


def problemes_d_entretien(brut: dict[str, Any]) -> list[str]:
    """`entretien`, quand elle est presente : une table, avec `declencheurs` (une
    liste de tables, voir `problemes_de_declencheur`) et `intitules_a_risque` (une
    table `{motifs, avertissement}`). Une liste `motifs` presente est controlee,
    comme toutes les autres, par `_problemes_de_forme_des_motifs`."""
    if "entretien" not in brut:
        return []
    entretien = brut["entretien"]
    if not isinstance(entretien, dict):
        return ["criteres.yaml : entretien doit etre une table"]
    problemes: list[str] = []
    if "declencheurs" in entretien:
        declencheurs = entretien["declencheurs"]
        if not isinstance(declencheurs, list):
            problemes.append("criteres.yaml : entretien.declencheurs doit etre une liste de tables")
        else:
            for i, entree in enumerate(declencheurs):
                problemes += problemes_de_declencheur(entree, f"entretien.declencheurs[{i}]")
    if "intitules_a_risque" in entretien:
        risque = entretien["intitules_a_risque"]
        if not isinstance(risque, dict):
            problemes.append("criteres.yaml : entretien.intitules_a_risque doit etre une table")
        else:
            if "motifs" not in risque:
                problemes.append(
                    "criteres.yaml : entretien.intitules_a_risque.motifs doit etre une liste "
                    "de chaines")
            if not _chaine_non_vide(risque.get("avertissement")):
                problemes.append(
                    "criteres.yaml : entretien.intitules_a_risque.avertissement doit etre une "
                    "chaine non vide")
    return problemes


# --------------------------------------------------------------------------
# Les controles par motif
#
# Le meme piege a mordu trois fois : un pretraitement mange un motif avant qu'on
# le cherche (la normalisation, le retrait du bruit d'un lieu), ou un motif general
# masque un motif specifique (le teletravail). `tests/test_pretraitement.py` le
# verifiait sur la configuration lue par la suite ; la suite tourne sur l'exemple,
# et c'est donc ici que toute configuration le retrouve, par `veille config
# verifier` (la CI le lance sur la configuration reelle).
# --------------------------------------------------------------------------

# Le bruit reel qui entoure un lieu imprecis dans les annonces.
HABILLAGES_DE_LIEU = ("{m}", "{m}, France", "{m} (Sur site)", "{m}, France (Sur site)")

# Chaque liste de motifs de teletravail, et le niveau qu'elle doit rendre.
NIVEAUX_DE_TELETRAVAIL = (
    ("teletravail_complet_motifs", "complet"),
    ("presence_partielle_motifs", "partiel"),
    ("presence_totale_motifs", "presentiel"),
)


def motifs_declares(brut: dict[str, Any]) -> list[tuple[str, str]]:
    """(chemin, motif) pour chaque motif textuel declare : toute liste sous une cle
    qui finit par `motifs`. `bruit_agregateur` porte des expressions regulieres,
    pas des motifs : il n'en fait pas partie."""
    trouves: list[tuple[str, str]] = []

    def descendre(noeud: Any, chemin: str) -> None:
        if isinstance(noeud, dict):
            for cle, valeur in noeud.items():
                descendre(valeur, f"{chemin}.{cle}" if chemin else str(cle))
        elif isinstance(noeud, list) and chemin.endswith("motifs"):
            trouves.extend((chemin, m) for m in noeud if isinstance(m, str))

    descendre(brut, "")
    return trouves


# `familles.<f>.motifs` a deja son controle de type (`_problemes_de_criteres`).
_MOTIFS_DE_FAMILLE = re.compile(r"familles\.[^.]+\.motifs")


def _problemes_de_forme_des_motifs(brut: dict[str, Any]) -> list[str]:
    """Toute cle qui finit par `motifs` porte une liste de chaines.

    `motifs_declares` saute le reste en silence, et le chargement s'y trompe : une
    chaine s'y parcourt lettre par lettre (chaque lettre devient un motif), `None`
    ou un nombre arretent le score. On nomme donc la cle.
    """
    problemes: list[str] = []

    def descendre(noeud: Any, chemin: str) -> None:
        if not isinstance(noeud, dict):
            return
        for cle, valeur in noeud.items():
            sous = f"{chemin}.{cle}" if chemin else str(cle)
            if str(cle).endswith("motifs"):
                if not isinstance(valeur, list):
                    if not _MOTIFS_DE_FAMILLE.fullmatch(sous):
                        problemes.append(f"criteres.yaml : {sous} doit etre une liste de chaines")
                else:
                    problemes.extend(
                        f"criteres.yaml : {sous}[{i}] doit etre une chaine"
                        for i, motif in enumerate(valeur) if not isinstance(motif, str))
            descendre(valeur, sous)

    descendre(brut, "")
    return problemes


def _problemes_de_groupes_de_lieux(geo: dict[str, Any]) -> list[str]:
    """`geographie.lieux_imprecis` : une table de groupes, chacun une table."""
    groupes = geo.get("lieux_imprecis")
    if groupes is None:
        return []
    if not isinstance(groupes, dict):
        return ["criteres.yaml : geographie.lieux_imprecis doit etre une table"]
    return [f"criteres.yaml : geographie.lieux_imprecis.{groupe} doit etre une table"
            for groupe, bloc in groupes.items() if not isinstance(bloc, dict)]


def _problemes_de_motifs(brut: dict[str, Any]) -> list[str]:
    """Les motifs que le pretraitement detruirait, ou qu'un motif plus general masque."""
    forme = _problemes_de_forme_des_motifs(brut)
    problemes: list[str] = list(forme)
    for chemin, motif in motifs_declares(brut):
        # Un motif que `normaliser` detruit ne peut jamais etre detecte.
        if not contient(normaliser(f"Avant, {motif}, apres."), motif):
            problemes.append(
                f"criteres.yaml : {chemin} : le motif {motif!r} ne survit pas a la normalisation")

    geo = brut.get("geographie")
    if not isinstance(geo, dict):
        return problemes
    groupes = _problemes_de_groupes_de_lieux(geo)
    problemes += groupes
    # Sur une geographie mal formee, les controles ci-dessous tomberaient, ou
    # liraient les lettres d'une chaine comme des motifs et rendraient des constats
    # faux. Ils ne tournent pas, et on le dit : ce n'est pas un succes.
    if groupes or any(p.startswith("criteres.yaml : geographie.") for p in forme):
        problemes.append(
            "criteres.yaml : les controles des lieux et du teletravail n'ont pas pu tourner "
            "(geographie mal formee, voir plus haut)")
        return problemes
    try:
        problemes += _problemes_de_lieux(brut, geo)
        problemes += _problemes_de_teletravail(brut, geo)
    except Exception as e:  # noqa: BLE001 — un controle qui n'a pas tourne n'est pas un succes
        problemes.append(
            f"criteres.yaml : les controles des lieux et du teletravail n'ont pas pu tourner "
            f"({type(e).__name__})")
    return problemes


def _problemes_de_lieux(brut: dict[str, Any], geo: dict[str, Any]) -> list[str]:
    """Chaque motif de lieu imprecis, entoure du bruit des annonces, reste reconnu,
    et dans son groupe : le bruit ne doit pas le couper (« france entiere »)."""
    from .models import Offre
    from .scoring import lieu_imprecis

    criteres = Criteres(brut)
    problemes: list[str] = []
    groupes = geo.get("lieux_imprecis") or {}
    if not isinstance(groupes, dict):
        return problemes
    for groupe, bloc in groupes.items():
        for motif in (bloc or {}).get("motifs", []) if isinstance(bloc, dict) else []:
            if not isinstance(motif, str):
                continue
            for habillage in HABILLAGES_DE_LIEU:
                lieu = habillage.format(m=motif)
                trouve, _poids, vu = lieu_imprecis(Offre(titre="Poste", lieu=lieu), criteres)
                if not trouve:
                    problemes.append(
                        f"criteres.yaml : geographie.lieux_imprecis.{groupe} : {lieu!r} "
                        "n'est pas reconnu comme imprecis (le bruit coupe le motif)")
                    break
                if vu != groupe:
                    problemes.append(
                        f"criteres.yaml : geographie.lieux_imprecis.{groupe} : {lieu!r} "
                        f"est classe en {vu} au lieu de {groupe}")
                    break
    return problemes


def _problemes_de_teletravail(brut: dict[str, Any], geo: dict[str, Any]) -> list[str]:
    """Chaque motif de teletravail rend le niveau de sa liste : un motif plus general,
    examine avant lui, ne doit pas l'emporter (« 2 jours sur site »)."""
    from .models import Offre
    from .scoring import detecter_teletravail

    criteres = Criteres(brut)
    problemes: list[str] = []
    for cle, attendu in NIVEAUX_DE_TELETRAVAIL:
        motifs = geo.get(cle) or []
        for motif in motifs if isinstance(motifs, list) else []:
            if not isinstance(motif, str):
                continue
            o = Offre(titre="Poste", lieu="",
                      description=f"Description du poste. {motif}. Equipe de dix personnes.")
            niveau, preuve = detecter_teletravail(o, criteres)
            if niveau != attendu:
                problemes.append(
                    f"criteres.yaml : geographie.{cle} : le motif {motif!r} donne {niveau!r} "
                    f"au lieu de {attendu!r} (preuve retenue : {preuve!r}) — "
                    "un motif plus general l'emporte")
    return problemes


def recharger() -> None:
    """A appeler apres modification des fichiers de config."""
    charger_criteres.cache_clear()
    charger_sources.cache_clear()

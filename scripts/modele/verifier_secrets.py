"""Contrôle des secrets chiffrés par sops, sans les déchiffrer.

Bibliothèque standard seule, Python 3.10 ou plus.

Usage :
    verifier_secrets.py [--racine DIR] [--cles DIR]

Pour chaque `*.env.enc` (hors `.git/`), on compare :
  - ses clés à celles de son `.cles` (même nom, suffixe `.env.enc` remplacé par `.cles`) ;
  - ses destinataires age à ceux de `.sops.yaml`.
Un `.cles` sans `.enc` avertit seulement : un projet neuf n'a pas encore ses secrets. Il ne dit
rien dans le dépôt de code d'un projet `serveur` à deux dépôts (`MODE_DONNEES="deux"` dans
`deploiement/lib.sh`) : ses `.enc` vivent dans le dépôt de données, dont la CI les contrôle.
`reglages.SECRETS_EXIGES` (chemin du `.cles` -> clés exigées) ajoute les clés dont la mécanique a besoin.

Le dépôt de données d'un projet `serveur` (M-0006, § 8) porte ses `secrets/<env>.env.enc`, mais la
liste de leurs clés est dans le dépôt de code (`deploiement/secrets/<env>.cles`). Avec `--cles DIR`,
seuls les `secrets/*.env.enc` de la racine sont lus (jamais un `.enc` du clone du code, ni
d'ailleurs), le `.cles` d'un `<env>.env.enc` est `DIR/<env>.cles`, seuls les `.cles` de DIR sont
lus, et les destinataires de `.sops.yaml` doivent en plus être exactement les clés age de
`cles/*.pub`. Sans `--cles`, dans un dépôt dont `reglages.DEPOT_CODE` nomme le dépôt de code et qui
porte `.github/workflows/modele-donnees.yml`, le contrôle passe en le disant : modele-donnees.yml le
fait, le dépôt de code cloné à côté. Sans ce workflow (le dépôt de données d'un projet sans
serveur), le contrôle ordinaire tourne.

Les messages nomment des chemins, des numéros de ligne et des noms de clé, jamais une valeur.

Retour : 0 conforme (avertissements compris), 1 refus, 64 erreur d'usage.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

EXIT_REFUS = 1
EXIT_USAGE = 64

REGEX_CLE = re.compile(r"[A-Z][A-Z0-9_]*")
REGEX_NOM = re.compile(r"([^=\s]+)=")
REGEX_DESTINATAIRE = re.compile(r"sops_age__list_\d+__map_recipient")
REGEX_AGE = re.compile(r"age1[0-9a-z]{58}")

BOM_UTF8 = b"\xef\xbb\xbf"
SUFFIXE_ENC = ".env.enc"
SUFFIXE_CLES = ".cles"
DOSSIER_PUB = "cles"
DOSSIER_SECRETS = "secrets"
WORKFLOW_DONNEES = ".github/workflows/modele-donnees.yml"
MESSAGE_DONNEES = "secrets : contrôlés par modele-donnees.yml, contre le .cles du dépôt de code"
# Le mode des données d'un projet `serveur`, défini dans deploiement/lib.sh seulement : lu, jamais
# recalculé.
LIB_DU_SERVEUR = "deploiement/lib.sh"
MODE_A_DEUX_DEPOTS = re.compile(r'^MODE_DONNEES="deux"\r?$', re.MULTILINE)


class Illisible(Exception):
    """Un fichier qu'on ne peut pas lire : porte le numéro de ligne, jamais son contenu."""

    def __init__(self, ligne: int, raison: str):
        super().__init__(raison)
        self.ligne = ligne
        self.raison = raison


@dataclass(frozen=True)
class Constat:
    niveau: str  # « refus » ou « avertissement »
    chemin: str
    message: str


def lire_texte(chemin: Path) -> str:
    """Le texte UTF-8 du fichier, sans son BOM ; un octet qui n'est pas de l'UTF-8 est Illisible."""
    brut = chemin.read_bytes().removeprefix(BOM_UTF8)
    try:
        return brut.decode("utf-8")
    except UnicodeDecodeError as e:
        # Le numéro de la ligne fautive, jamais l'octet ni son voisinage.
        raise Illisible(brut[: e.start].count(b"\n") + 1, "fichier non UTF-8") from None


def lire_cles(chemin: Path) -> list[str]:
    """Une clé par ligne ; lignes vides et « # » ignorées ; un doublon est une erreur."""
    cles: list[str] = []
    for numero, brut in enumerate(lire_texte(chemin).splitlines(), start=1):
        ligne = brut.strip()
        if not ligne or ligne.startswith("#"):
            continue
        if not REGEX_CLE.fullmatch(ligne):
            raise Illisible(numero, "clé invalide (attendu : MAJUSCULES, chiffres et _)")
        if ligne in cles:
            raise Illisible(numero, f"clé en double : {ligne}")
        cles.append(ligne)
    return cles


def lire_chiffre(chemin: Path) -> tuple[set[str], set[str]]:
    """(clés, destinataires) d'un dotenv chiffré par sops. Aucune valeur n'est conservée."""
    cles: set[str] = set()
    destinataires: set[str] = set()
    for numero, brut in enumerate(lire_texte(chemin).splitlines(), start=1):
        # Un commentaire sops ressort chiffré (#ENC[…, type:comment]) : ni clé, ni citable.
        if not brut.strip() or brut.lstrip().startswith("#"):
            continue
        correspondance = REGEX_NOM.match(brut)
        if not correspondance:
            raise Illisible(numero, "ligne sans « = » : ce n'est pas un dotenv chiffré")
        nom = correspondance.group(1)
        if nom.startswith("sops_"):
            if REGEX_DESTINATAIRE.fullmatch(nom):
                destinataires.add(brut[correspondance.end() :].strip())
        else:
            if not brut[correspondance.end() :].startswith("ENC[AES256_GCM,"):
                raise Illisible(numero, f"valeur non chiffrée : {nom}")
            cles.add(nom)
    return cles, destinataires


def destinataires_sops_yaml(racine: Path) -> set[str]:
    return set(REGEX_AGE.findall(lire_texte(racine / ".sops.yaml")))


def _fichiers(racine: Path, motif: str) -> list[Path]:
    return sorted(p for p in racine.rglob(motif) if ".git" not in p.relative_to(racine).parts and p.is_file())


def _relatif(racine: Path, chemin: Path) -> str:
    # Un .cles de --cles peut être donné autrement que la racine (absolu, ou hors du dépôt).
    for base, cible in ((racine, chemin), (racine.resolve(), chemin.resolve())):
        try:
            return cible.relative_to(base).as_posix()
        except ValueError:
            pass
    return chemin.as_posix()


def _court(destinataire: str) -> str:
    return destinataire[:8] + "…"


def _noms(cles) -> str:
    return ", ".join(sorted(cles))


def _comparer_au_parc(racine: Path, attendus: set[str]) -> list[Constat]:
    """Les destinataires de .sops.yaml sont exactement les clés age de cles/*.pub : une clé du parc
    absente de .sops.yaml, ou un destinataire sans sa clé dans cles/, refuse (en abrégé)."""
    constats: list[Constat] = []
    parc: set[str] = set()
    dossier = racine / DOSSIER_PUB
    for chemin in sorted(dossier.glob("*.pub")) if dossier.is_dir() else []:
        rel = _relatif(racine, chemin)
        try:
            cles = set(REGEX_AGE.findall(lire_texte(chemin)))
        except Illisible as e:
            constats.append(Constat("refus", f"{rel}:{e.ligne}", e.raison))
            continue
        if not cles:
            constats.append(Constat("refus", rel, "aucune clé age"))
        for cle in sorted(cles - attendus):
            constats.append(Constat("refus", rel, f"clé absente de .sops.yaml : {_court(cle)}"))
        parc |= cles
    for cle in sorted(attendus - parc):
        message = f"destinataire sans clé dans {DOSSIER_PUB}/ : {_court(cle)}"
        constats.append(Constat("refus", ".sops.yaml", message))
    return constats


def verifier(racine: Path, exiges: dict[str, list[str]], cles: Path | None = None) -> list[Constat]:
    """Les constats sur les secrets de <racine>. Avec <cles>, le dossier des .cles du dépôt de code :
    seuls les secrets/*.env.enc de <racine> et les .cles de <cles> sont lus, et .sops.yaml se
    compare aussi aux clés de cles/*.pub."""
    racine = Path(racine)
    constats: list[Constat] = []
    if cles is None:
        enc = _fichiers(racine, "*" + SUFFIXE_ENC)
        cles_fichiers = _fichiers(racine, "*" + SUFFIXE_CLES)
    else:
        enc = sorted(p for p in (racine / DOSSIER_SECRETS).glob("*" + SUFFIXE_ENC) if p.is_file())
        cles_fichiers = sorted(p for p in Path(cles).glob("*" + SUFFIXE_CLES) if p.is_file())

    sops_yaml = racine / ".sops.yaml"
    attendus: set[str] | None = None
    if enc or cles is not None:
        if not sops_yaml.is_file():
            message = "absent : les destinataires ne peuvent pas être contrôlés"
            constats.append(Constat("refus", ".sops.yaml", message))
        else:
            try:
                attendus = destinataires_sops_yaml(racine)
            except Illisible as e:
                constats.append(Constat("refus", f".sops.yaml:{e.ligne}", e.raison))
            else:
                if cles is not None:
                    constats += _comparer_au_parc(racine, attendus)
                if not attendus:
                    constats.append(Constat("refus", ".sops.yaml", "aucun destinataire age"))
                    attendus = None

    for chemin in enc:
        rel = _relatif(racine, chemin)
        nom_cles = chemin.name[: -len(SUFFIXE_ENC)] + SUFFIXE_CLES
        voisin = chemin.with_name(nom_cles) if cles is None else Path(cles) / nom_cles
        try:
            cles_chiffrees, destinataires = lire_chiffre(chemin)
        except Illisible as e:
            constats.append(Constat("refus", f"{rel}:{e.ligne}", e.raison))
            continue
        if not voisin.is_file():
            constats.append(Constat("refus", rel, f"pas de {_relatif(racine, voisin)} : la liste des clés attendues manque"))
        else:
            try:
                declarees = set(lire_cles(voisin))
            except Illisible as e:
                constats.append(Constat("refus", f"{_relatif(racine, voisin)}:{e.ligne}", e.raison))
            else:
                if declarees - cles_chiffrees:
                    constats.append(Constat("refus", rel, f"clés manquantes : {_noms(declarees - cles_chiffrees)}"))
                if cles_chiffrees - declarees:
                    constats.append(Constat("refus", rel, f"clés en trop : {_noms(cles_chiffrees - declarees)}"))
        if attendus is not None:
            if attendus - destinataires:
                manquants = ", ".join(sorted(_court(d) for d in attendus - destinataires))
                constats.append(Constat("refus", rel, f"destinataires manquants : {manquants}"))
            if destinataires - attendus:
                en_trop = ", ".join(sorted(_court(d) for d in destinataires - attendus))
                constats.append(Constat("refus", rel, f"destinataires hors .sops.yaml : {en_trop}"))
        elif not destinataires:
            constats.append(Constat("refus", rel, "aucun destinataire age"))

    noms_enc = {p.name for p in enc}
    # Dans le dépôt de code à deux dépôts, un .cles n'a jamais de .enc voisin : rien à en dire.
    enc_ailleurs = cles is None and _a_deux_depots(racine)
    for chemin in cles_fichiers:
        voisin = chemin.with_name(chemin.name[: -len(SUFFIXE_CLES)] + SUFFIXE_ENC)
        if cles is None:
            sans_enc = not voisin.is_file()
        else:  # le .enc est dans le dépôt de données, sous le même nom
            sans_enc = voisin.name not in noms_enc
        if sans_enc and not enc_ailleurs:
            constats.append(
                Constat("avertissement", _relatif(racine, chemin), f"pas de {voisin.name} : secrets pas encore posés")
            )

    for rel_cles, requises in sorted(exiges.items()):
        chemin = racine / rel_cles
        if not chemin.is_file():
            constats.append(Constat("refus", rel_cles, "absent, mais la mécanique du modèle en exige des clés"))
            continue
        try:
            presentes = set(lire_cles(chemin))
        except Illisible as e:
            constats.append(Constat("refus", f"{rel_cles}:{e.ligne}", e.raison))
            continue
        absentes = set(requises) - presentes
        if absentes:
            constats.append(Constat("refus", rel_cles, f"clés exigées par la mécanique du modèle : {_noms(absentes)}"))

    return constats


def _a_deux_depots(racine: Path) -> bool:
    """Vrai si <racine> est le dépôt de code d'un projet `serveur` à deux dépôts, d'après
    MODE_DONNEES de deploiement/lib.sh ; faux sans lib.sh lisible (un projet sans serveur)."""
    try:
        return bool(MODE_A_DEUX_DEPOTS.search((racine / LIB_DU_SERVEUR).read_text(encoding="utf-8")))
    except (OSError, UnicodeDecodeError):
        return False


def _reglages():
    """Le reglages.py voisin du script, celui du projet ; None sans lui (le dépôt modèle)."""
    try:
        import reglages  # type: ignore[import-not-found]
    except ImportError:
        return None
    return reglages


def _exiges_des_reglages() -> dict[str, list[str]]:
    return dict(getattr(_reglages(), "SECRETS_EXIGES", {}))


def main(argv: list[str] | None = None, exiges: dict[str, list[str]] | None = None) -> int:
    analyseur = argparse.ArgumentParser(description="Contrôle des secrets chiffrés par sops, sans déchiffrer.")
    analyseur.add_argument("--racine", default=".", help="racine du dépôt (défaut : le dossier courant)")
    analyseur.add_argument(
        "--cles", help="le dossier des .cles, celui du dépôt de code pour un dépôt de données"
    )
    try:
        args = analyseur.parse_args(argv)
    except SystemExit as e:
        return EXIT_USAGE if e.code else 0
    racine = Path(args.racine)
    if not racine.is_dir():
        print(f"racine introuvable : {racine}", file=sys.stderr)
        return EXIT_USAGE
    cles = None
    if args.cles is not None:
        cles = Path(args.cles)
        if not cles.is_dir():
            print(f"dossier des .cles introuvable : {cles}", file=sys.stderr)
            return EXIT_USAGE
    elif getattr(_reglages(), "DEPOT_CODE", None) and (racine / WORKFLOW_DONNEES).is_file():
        # Le dépôt de données d'un projet serveur : la liste des clés est dans le dépôt de code, et
        # modele-donnees.yml les compare (M-0006, § 8).
        print(MESSAGE_DONNEES)
        return 0
    if exiges is None:
        exiges = _exiges_des_reglages()
    constats = verifier(racine, exiges, cles)
    for c in constats:
        print(f"{c.niveau} : {c.chemin} : {c.message}")
    return EXIT_REFUS if any(c.niveau == "refus" for c in constats) else 0


if __name__ == "__main__":
    # Les messages sont en UTF-8 quelle que soit la page de code de la console ou du tube.
    for flux in (sys.stdout, sys.stderr):
        flux.reconfigure(encoding="utf-8")
    sys.exit(main())

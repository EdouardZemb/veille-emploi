"""Contrôle d'un dépôt de données contre les images de son dépôt de code (M-0006, § 8).

Bibliothèque standard seule, Python 3.10 ou plus.

Usage :
    verifier_donnees.py --code DIR [--compte COMPTE] [--images REF [REF …]]

À lancer à la racine du dépôt de données : son scripts/modele/reglages.py nomme le dépôt de code
(DEPOT_CODE). DIR est un clone de ce dépôt de code, sur sa branche par défaut, avec ses étiquettes.

Les images vérifiées : ghcr.io/<compte en minuscules>/<DEPOT_CODE>:main, avec la déclaration de la
copie de DIR (deploiement/projet.env), et l'image de la plus haute étiquette vX.Y.Z du code, publiée
sous X.Y.Z, avec la déclaration de cette étiquette. Sans vX.Y.Z, seule :main, et la sortie le dit.
Le compte vient de --compte, sinon de GITHUB_REPOSITORY_OWNER. --images remplace cette liste :
chaque image prend alors la déclaration de la copie.

Pour chaque image, comme le serveur vérifie un couple (deploiement/lib.sh) :
  - la règle des paires, sur le commit HEAD du dépôt de données (git ls-tree : un fichier non suivi
    ne compte pas) : config/ va avec VERIFIER_CONFIG, contenu/ avec VERIFIER_CONTENU, et l'inverse ;
    un dossier qui ne porte que le README.md de sa racine compte comme absent ;
  - docker pull : une image qui ne se tire pas refuse ;
  - chaque commande déclarée, dans un conteneur jetable de l'image, sans réseau, les dossiers de
    HEAD (extraits par git archive) en lecture seule : `<VERIFIER_CONFIG…> /config`, puis
    `<VERIFIER_CONTENU…> /contenu`, suivi de /en-service, le contenu/ de la plus haute étiquette de
    données donnees-AAAA.MM.JJ.n, quand elle en porte un. En CI, les deux commandes tournent pour
    chaque image : rien n'y distingue le staging de la prod.
Le contrat de l'image : 0 conforme, 2 non conforme, 64 usage ; tout autre code refuse.

Les déclarations se lisent comme lib.sh les lit (lire_projet_env_facultatif), sans jamais sourcer
projet.env. Tout ce qui refuse est dit, l'image et sa version nommées, puis le code de sortie.

Retour : 0 conforme, 1 refus, 64 erreur d'usage.
"""

from __future__ import annotations

import argparse
import io
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unicodedata
from dataclasses import dataclass
from pathlib import Path

EXIT_REFUS = 1
EXIT_USAGE = 64

# Une copie de <P>OPTIONS_JETABLES de deploiement/lib.sh : un test les lie (test_verifier_donnees).
OPTIONS_JETABLES = (
    "--user", "1000:1000", "--read-only", "--tmpfs", "/tmp", "--cap-drop", "ALL",
    "--security-opt", "no-new-privileges:true", "--memory", "384m",
)  # fmt: skip
# Les dossiers de l'instance d'un dépôt de données, à sa racine (SOUS_DOSSIER_CONFIG et
# SOUS_DOSSIER_CONTENU de lib.sh, à deux dépôts).
DOSSIER_CONFIG = "config"
DOSSIER_CONTENU = "contenu"
PROJET_ENV = "deploiement/projet.env"
# Les droits de ce que lit le conteneur jetable, posés explicitement (l'umask n'y entre pas).
DROITS_DOSSIER = 0o755
DROITS_FICHIER = 0o644
DROITS_EXECUTABLE = 0o755

REGEX_CLE = re.compile(r"[A-Z][A-Z0-9_]*")
REGEX_VERSION = re.compile(r"v([0-9]+)\.([0-9]+)\.([0-9]+)")
REGEX_ETIQUETTE_DONNEES = re.compile(r"donnees-([0-9]{4})\.([0-9]{2})\.([0-9]{2})\.([1-9][0-9]*)")
REGEX_COMPTE = re.compile(r"[A-Za-z0-9](?:-?[A-Za-z0-9])*")
REGEX_DEPOT = re.compile(r"[a-z][a-z0-9-]*")
# Les caractères que valeur_sure (lib.sh) refuse, en plus des blancs et des caractères de contrôle.
INTERDITS = frozenset("\"'\\$`;&|<>()~")


class Illisible(Exception):
    """Une déclaration, un commit ou une étiquette qu'on ne peut pas lire."""


@dataclass(frozen=True)
class Declaration:
    """Les mots de VERIFIER_CONFIG et de VERIFIER_CONTENU ; vides, la commande n'est pas déclarée."""

    config: tuple[str, ...] = ()
    contenu: tuple[str, ...] = ()


@dataclass(frozen=True)
class Cible:
    image: str
    version: str  # « main », « vX.Y.Z » ou « déclaration de la copie »
    declaration: Declaration | None
    erreur: str = ""  # la déclaration illisible, quand declaration vaut None


def valeur_sure(valeur: str) -> bool:
    """La règle de valeur_sure (lib.sh) : non vide, sans blanc, contrôle ni caractère du shell."""
    return bool(valeur) and not any(
        c.isspace() or unicodedata.category(c) == "Cc" or c in INTERDITS for c in valeur
    )


def _mots(texte: str, cle: str, source: str) -> tuple[str, ...]:
    """Les mots de <cle>, comme lire_projet_env_facultatif : sans ligne « <cle>= », rien n'est lu ;
    sinon le fichier entier se contrôle (lire_projet_env)."""
    lignes = texte.split("\n")
    if not any(ligne.startswith(cle + "=") for ligne in lignes):
        return ()
    mots: tuple[str, ...] | None = None
    for numero, ligne in enumerate(lignes, start=1):
        if not ligne or ligne.startswith("#"):
            continue
        nom, egal, valeur = ligne.partition("=")
        if not egal or not REGEX_CLE.fullmatch(nom) or not valeur_sure(valeur.replace(" ", "")):
            raise Illisible(
                f"{source}, ligne {numero} invalide (attendu : CLE=mots, sans caractère spécial "
                "du shell)"
            )
        if nom != cle:
            continue
        if mots is not None:
            raise Illisible(f"{cle} est déclarée deux fois dans {source}")
        mots = tuple(mot for mot in valeur.split(" ") if mot)
    return mots or ()


def lire_declaration(texte: str | None, source: str) -> Declaration:
    """La déclaration d'un projet.env ; None (pas de fichier) ne déclare rien. Illisible sinon."""
    if texte is None:
        return Declaration()
    return Declaration(
        config=_mots(texte, "VERIFIER_CONFIG", source),
        contenu=_mots(texte, "VERIFIER_CONTENU", source),
    )


def plus_haute_version(etiquettes) -> str | None:
    """La plus haute vX.Y.Z, triée par nombres ; les autres formes sont ignorées."""
    versions = [
        (tuple(map(int, m.groups())), e) for e in etiquettes if (m := REGEX_VERSION.fullmatch(e))
    ]
    return max(versions)[1] if versions else None


def plus_haute_etiquette_donnees(etiquettes) -> str | None:
    """La plus haute donnees-AAAA.MM.JJ.n, triée par date puis par n ; les autres formes sont
    ignorées."""
    valides = [
        (tuple(map(int, m.groups())), e)
        for e in etiquettes
        if (m := REGEX_ETIQUETTE_DONNEES.fullmatch(e))
    ]
    return max(valides)[1] if valides else None


def _git(depot: Path, *arguments: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(depot), *arguments], capture_output=True, check=False)


def _une_ligne(octets: bytes) -> str:
    return " ".join(octets.decode("utf-8", errors="replace").split())


def etiquettes(depot: Path, motif: str) -> list[str]:
    r = _git(depot, "tag", "--list", motif)
    if r.returncode != 0:
        raise Illisible(f"étiquettes illisibles dans {depot} : {_une_ligne(r.stderr)}")
    return r.stdout.decode("utf-8", errors="replace").split()


def present(depot: Path, revision: str, dossier: str) -> bool:
    """Le dossier porte, dans <revision>, au moins un fichier autre que <dossier>/README.md."""
    r = _git(depot, "ls-tree", "-r", "-z", "--name-only", revision, "--", dossier)
    if r.returncode != 0:
        raise Illisible(f"{revision} illisible dans le dépôt de données : {_une_ligne(r.stderr)}")
    for chemin in r.stdout.decode("utf-8", errors="surrogateescape").split("\0"):
        if chemin.startswith(dossier + "/") and chemin != dossier + "/README.md":
            return True
    return False


def ouvrir_au_conteneur(racine: Path) -> None:
    """<racine> et tout ce qu'elle porte, lisibles par le conteneur jetable, qui tourne sous
    1000:1000 et non sous l'utilisateur du script, quel que soit l'umask : dossiers 0755, fichiers
    0644 (0755 s'ils sont exécutables). Un lien n'est pas suivi."""
    os.chmod(racine, DROITS_DOSSIER)
    for dossier, sous_dossiers, fichiers in os.walk(racine):
        for nom in sous_dossiers + fichiers:
            chemin = os.path.join(dossier, nom)
            if os.path.islink(chemin):
                continue
            if os.path.isdir(chemin):
                os.chmod(chemin, DROITS_DOSSIER)
            else:
                executable = os.stat(chemin).st_mode & 0o111
                os.chmod(chemin, DROITS_EXECUTABLE if executable else DROITS_FICHIER)


def extraire(depot: Path, revision: str, dossier: str, destination: Path) -> Path:
    """Le <dossier> de <revision>, par git archive, dans <destination> : jamais la copie de travail.
    Ce que l'extraction refuse (un lien qui sort du dossier, avec le filtre `data`) est Illisible."""
    r = _git(depot, "archive", "--format=tar", f"{revision}:{dossier}")
    if r.returncode != 0:
        raise Illisible(f"{dossier}/ de {revision} ne s'extrait pas : {_une_ligne(r.stderr)}")
    destination.mkdir(parents=True)
    try:
        with tarfile.open(fileobj=io.BytesIO(r.stdout)) as archive:
            if hasattr(tarfile, "data_filter"):
                archive.extractall(destination, filter="data")
            else:  # un Python 3.10 ou 3.11 d'avant le filtre : l'archive vient du dépôt lui-même
                archive.extractall(destination)
    except (tarfile.TarError, OSError) as e:
        raise Illisible(
            f"{dossier}/ de {revision} ne s'extrait pas : {' '.join(str(e).split())}"
        ) from None
    ouvrir_au_conteneur(destination)
    return destination


def declaration_de(code: Path, etiquette: str | None) -> Declaration:
    """La déclaration de la copie du code (etiquette None) ou de cette étiquette, lue sans checkout.
    Un projet.env absent ne déclare rien."""
    if etiquette is None:
        chemin = code / PROJET_ENV
        if not chemin.is_file():
            return Declaration()
        try:
            texte = chemin.read_bytes().decode("utf-8")
        except UnicodeDecodeError:
            raise Illisible(f"{PROJET_ENV} n'est pas en UTF-8") from None
        return lire_declaration(texte, PROJET_ENV)
    reference = f"refs/tags/{etiquette}"
    r = _git(code, "ls-tree", "--name-only", reference, "--", PROJET_ENV)
    if r.returncode != 0:
        raise Illisible(f"{PROJET_ENV} de {etiquette} illisible : {_une_ligne(r.stderr)}")
    if not r.stdout.strip():
        return Declaration()
    r = _git(code, "show", f"{reference}:{PROJET_ENV}")
    if r.returncode != 0:
        raise Illisible(f"{PROJET_ENV} de {etiquette} illisible : {_une_ligne(r.stderr)}")
    try:
        texte = r.stdout.decode("utf-8")
    except UnicodeDecodeError:
        raise Illisible(f"{PROJET_ENV} de {etiquette} n'est pas en UTF-8") from None
    return lire_declaration(texte, f"{PROJET_ENV} de {etiquette}")


def _cible(image: str, version: str, code: Path, etiquette: str | None) -> Cible:
    try:
        return Cible(image, version, declaration_de(code, etiquette))
    except Illisible as e:
        return Cible(image, version, None, str(e))


def _depot_code() -> str | None:
    """DEPOT_CODE du reglages.py voisin du script : le dépôt de code de ce dépôt de données."""
    try:
        import reglages  # type: ignore[import-not-found]
    except ImportError:
        return None
    return getattr(reglages, "DEPOT_CODE", None)


class Verification:
    """Les images d'un dépôt de données, vérifiées une à une ; les refus s'accumulent."""

    def __init__(self, depot: Path, docker: str, temporaire: Path, en_service: str | None):
        self.depot = depot
        self.docker = docker
        self.temporaire = temporaire
        self.en_service = en_service
        self.refus: list[str] = []
        self._presents: dict[str, bool] = {}
        self._extraits: dict[tuple[str, str], Path] = {}

    def refuser(self, cible: Cible, message: str) -> None:
        self.refus.append(f"{cible.image} ({cible.version}) : {message}")
        print(f"refus : {cible.image} ({cible.version}) : {message}")

    def dire(self, cible: Cible, message: str) -> None:
        print(f"données : {cible.image} ({cible.version}) : {message}")

    def present(self, dossier: str) -> bool:
        if dossier not in self._presents:
            self._presents[dossier] = present(self.depot, "HEAD", dossier)
        return self._presents[dossier]

    def extrait(self, nom: str, revision: str, dossier: str) -> Path:
        """<dossier> de <revision>, extrait une fois, sous <temporaire>/<nom>/<dossier> : « vise »
        pour HEAD, « en-service » pour l'étiquette du contenu en service."""
        if (nom, dossier) not in self._extraits:
            parent = self.temporaire / nom
            parent.mkdir(exist_ok=True)
            os.chmod(parent, DROITS_DOSSIER)
            self._extraits[nom, dossier] = extraire(self.depot, revision, dossier, parent / dossier)
        return self._extraits[nom, dossier]

    def verifier(self, cible: Cible) -> None:
        if cible.declaration is None:
            self.refuser(cible, f"{PROJET_ENV} illisible : {cible.erreur}")
            return
        declaration = cible.declaration
        paires = True
        for dossier, cle, mots in (
            (DOSSIER_CONFIG, "VERIFIER_CONFIG", declaration.config),
            (DOSSIER_CONTENU, "VERIFIER_CONTENU", declaration.contenu),
        ):
            if self.present(dossier) and not mots:
                self.refuser(cible, f"{dossier}/ sans {cle}")
                paires = False
            elif mots and not self.present(dossier):
                self.refuser(cible, f"{cle} sans {dossier}/")
                paires = False

        r = subprocess.run(
            [self.docker, "pull", "-q", cible.image], capture_output=True, check=False
        )
        if r.returncode != 0:
            self.refuser(
                cible,
                f"image absente du registre, ou illisible (docker pull : code {r.returncode}) : "
                f"{_une_ligne(r.stdout + r.stderr)}",
            )
            return
        if not paires:
            return

        if declaration.config:
            montages = [(self.extrait("vise", "HEAD", DOSSIER_CONFIG), "/config")]
            self.lancer(cible, "VERIFIER_CONFIG", "configuration", declaration.config, montages)
        if declaration.contenu:
            montages = [(self.extrait("vise", "HEAD", DOSSIER_CONTENU), "/contenu")]
            if self.en_service:
                etiquette = f"refs/tags/{self.en_service}"
                en_service = self.extrait("en-service", etiquette, DOSSIER_CONTENU)
                montages.append((en_service, "/en-service"))
            self.lancer(cible, "VERIFIER_CONTENU", "contenu", declaration.contenu, montages)

    def lancer(self, cible: Cible, cle: str, libelle: str, mots, montages) -> None:
        """`docker run --rm --network none <options jetables> -v <source>:<point>:ro… <image>
        <mots> <points de montage…>`, comme _verifier_par de lib.sh : chaque point de montage est
        aussi un argument de la commande, dans l'ordre (/contenu, puis /en-service)."""
        volumes = [
            option for source, point in montages for option in ("-v", f"{source}:{point}:ro")
        ]
        commande = [*mots, *(point for _, point in montages)]
        r = subprocess.run(
            [self.docker, "run", "--rm", "--network", "none", *OPTIONS_JETABLES, *volumes]
            + [cible.image, *commande],
            capture_output=True,
            check=False,
        )
        sortie = _une_ligne(r.stdout + r.stderr)
        quoi = f"{cle} : {' '.join(commande)} : code {r.returncode}"
        if r.returncode == 0:
            self.dire(cible, f"{libelle} conforme ({quoi})")
        elif r.returncode == 2:
            self.refuser(cible, f"{libelle} non conforme ({quoi}) : {sortie}")
        elif r.returncode == EXIT_USAGE:
            self.refuser(
                cible,
                f"vérification impossible ({quoi}) : usage refusé, l'image ne connaît pas la "
                f"commande {cle} de projet.env : {sortie}",
            )
        else:
            self.refuser(cible, f"vérification impossible ({quoi}) : {sortie}")


def _usage(message: str) -> int:
    print(f"données : {message}", file=sys.stderr)
    return EXIT_USAGE


def main(argv: list[str] | None = None) -> int:
    analyseur = argparse.ArgumentParser(
        description="Contrôle d'un dépôt de données contre les images de son dépôt de code."
    )
    analyseur.add_argument("--code", required=True, help="le clone du dépôt de code")
    analyseur.add_argument("--compte", help="le compte GitHub des images (défaut : celui du dépôt)")
    analyseur.add_argument("--images", nargs="+", help="les images à vérifier, à la place")
    try:
        args = analyseur.parse_args(argv)
    except SystemExit as e:
        return EXIT_USAGE if e.code else 0

    code = Path(args.code)
    if not (code / ".git").exists():
        return _usage(f"{code} n'est pas un clone du dépôt de code")
    depot = Path(".")
    prefixe = _git(depot, "rev-parse", "--show-prefix")
    if (
        prefixe.returncode != 0
        or prefixe.stdout.strip()
        or _git(depot, "rev-parse", "--verify", "-q", "HEAD^{commit}").returncode != 0
    ):
        return _usage("à lancer à la racine du dépôt de données, sur un commit")

    if args.images:
        cibles = [_cible(image, "déclaration de la copie", code, None) for image in args.images]
    else:
        depot_code = _depot_code()
        if not isinstance(depot_code, str) or not REGEX_DEPOT.fullmatch(depot_code):
            return _usage(
                "pas de DEPOT_CODE lisible dans scripts/modele/reglages.py : ce dépôt n'est pas "
                "un dépôt de données"
            )
        compte = (
            args.compte if args.compte is not None else os.environ.get("GITHUB_REPOSITORY_OWNER")
        )
        if not compte:
            return _usage("le compte des images manque : --compte, ou GITHUB_REPOSITORY_OWNER")
        if not REGEX_COMPTE.fullmatch(compte):
            return _usage(f"compte invalide : {compte!r}")
        base = f"ghcr.io/{compte.lower()}/{depot_code}"
        try:
            version = plus_haute_version(etiquettes(code, "v*"))
        except Illisible as e:
            print(f"refus : {e}")
            return EXIT_REFUS
        cibles = [_cible(f"{base}:main", "main", code, None)]
        if version:
            cibles.append(_cible(f"{base}:{version[1:]}", version, code, version))
        else:
            print("données : aucune version publiée du code : seule :main est vérifiée")

    docker = shutil.which("docker")
    if not docker:
        print("refus : docker introuvable : les images ne peuvent pas être vérifiées")
        return EXIT_REFUS
    try:
        en_service = plus_haute_etiquette_donnees(etiquettes(depot, "donnees-*"))
        if en_service and not present(depot, f"refs/tags/{en_service}", DOSSIER_CONTENU):
            en_service = None
        if en_service:
            print(f"données : contenu en service : {DOSSIER_CONTENU}/ de {en_service}")
        with tempfile.TemporaryDirectory(prefix="verifier-donnees-") as temporaire:
            # Le conteneur tourne sous l'utilisateur 1000 : il doit pouvoir traverser le dossier.
            os.chmod(temporaire, DROITS_DOSSIER)
            verification = Verification(depot, docker, Path(temporaire), en_service)
            for cible in cibles:
                verification.verifier(cible)
    except Illisible as e:
        print(f"refus : {e}")
        return EXIT_REFUS
    if verification.refus:
        return EXIT_REFUS
    print("données : conformes")
    return 0


if __name__ == "__main__":
    # Les messages sont en UTF-8 quelle que soit la page de code de la console ou du tube.
    for flux in (sys.stdout, sys.stderr):
        flux.reconfigure(encoding="utf-8")
    sys.exit(main())

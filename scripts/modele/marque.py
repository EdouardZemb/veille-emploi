"""Le relais qui marque le staging (bibliothèque standard seule, Python 3.10).

Placé devant l'application en staging, le relais transmet chaque requête et chaque réponse, en
HTTP/1.1 des deux côtés, et pose trois marques sur ce qu'elle sert : un bandeau « TEST » (la
feuille `FEUILLE`), le préfixe « test » du titre et du nom de l'application installée, et une icône
recolorée (une rampe orange sur la luminance de chaque pixel). Il répond lui-même sous `/.marque/`
(`sante`, `marque.css`, `icone`), et ne demande jamais rien qu'à son amont. Une cible est sous
`/.marque/` telle qu'elle arrive, une fois décodée (`%2E`, `%2e`, `%2F` et `%2f`, eux seuls), ou
une fois décodée puis normalisée (ses segments `.` et `..` retirés). Toute autre cible part telle
qu'elle est arrivée.

Son environnement : `MARQUE_ENV`, qui doit valoir `staging` (sinon le code 64) ; `MARQUE_AMONT`,
l'application, `http://<hôte>:<port>` ; `MARQUE_PORT`, son port d'écoute, de 1 à 65535 ;
`MARQUE_HOTE`, son adresse d'écoute, `HOTE_ECOUTE` par défaut. Son journal, sur la sortie d'erreur,
n'écrit jamais un chemin, une requête, un en-tête ni une adresse : une ligne à son démarrage, une à
son refus, et une par incident (l'application injoignable, une page trop grande, un manifeste trop
grand, un manifeste illisible, une icône remplacée par la générique et sa raison, un incident
interne).

Les retouches de la page et du manifeste sont une recherche dans le texte, pas une lecture du HTML.
Les limites connues du relais, que cette liste ne ferme pas :

- une page servie par un service worker ne porte les marques qu'une fois actif un service worker
  installé après l'arrivée du relais ; hors ligne, elle garde le bandeau seulement si
  `/.marque/marque.css` est dans le cache ;
- une copie d'une page ou d'un manifeste mise en cache avant le relais, et encore fraîche dans le
  cache du navigateur (un `max-age`, ou la fraîcheur heuristique d'un `Last-Modified` sans
  `Cache-Control`), se montre sans passer par lui, donc sans marque, jusqu'à son expiration ;
- une politique de sécurité du contenu dont `style-src` n'admet pas `'self'` bloque la feuille, et
  donc le bandeau ;
- un titre changé par un script fait perdre « test » à l'onglet, le bandeau reste ;
- les icônes des notifications, écrites dans le code d'un service worker, restent celles de la prod ;
- une icône d'une autre origine est remplacée par l'icône générique ;
- les icônes de `shortcuts` et de `screenshots`, dans le manifeste, gardent leurs couleurs : seules
  celles d'`icons` sont retouchées ;
- une application de staging déjà installée ne change d'icône et de nom que lorsque Chrome
  rafraîchit son WebAPK : on la réinstalle ;
- un fragment HTML chargé par un script reçoit lui aussi le lien de la feuille ;
- une page en UTF-16 ou en UTF-32 n'est pas reconnue : ni titre ni bandeau, et le lien ajouté à la
  fin s'y lit comme du texte ;
- un `::before` propre à l'application sur une fenêtre modale ou un `popover` ouvert est remplacé
  par la bande ;
- seules quatre formes se cherchent, `</head>`, `<body`, `<title>` et `<link ... rel=...icon...>`,
  et seulement dans l'en-tête : une forme écrite autrement (`</head >`, un `<title>` après
  `<body`) n'est pas vue ;
- un `<link>` ou un `<title>` dont la balise, ou une valeur entre guillemets, ne se ferme jamais
  court jusqu'à la fin, comme pour le tokeniseur HTML, qui n'ouvre une valeur entre guillemets que
  juste après le `=` qui suit un nom : aucune balise de la même sorte qui le suit n'est lue ; les
  deux recherches sont distinctes, et un `<link>` ouvert ne cache pas un `<title>` ;
- les commentaires `<!-- ... -->` se lisent à la lettre : `<!-->` et `<!--->`, que HTML ferme tout de
  suite, ouvrent ici un commentaire qui cache la suite ; un CDATA, un `<script>` ou un `<style>` qui
  contient une de ces formes n'est pas distingué du reste de la page ;
- un attribut `href` d'icône est lu entre guillemets ou sans (jusqu'à un blanc ou `>`, guillemets
  compris, comme pour le tokeniseur HTML), et ses entités HTML sont lues avant la résolution ;
  `<base href>` n'est pas lu : un lien d'icône relatif se résout d'après le chemin de la page ;
- le chemin et la requête d'un lien d'icône sont encodés comme le navigateur les demande (WHATWG) :
  le non ASCII en UTF-8, l'espace, les contrôles et quelques signes (`^` compris dans le chemin, et
  non dans la requête), le reste tel quel, `%` compris ; une apostrophe de la requête, que WHATWG
  encode pour `http` et `https`, passe telle quelle ; une barre oblique inverse, que le navigateur
  lit comme `/`, donne l'icône générique ; un `href` se lit en UTF-8, quel que soit le jeu de
  caractères de la page ;
- une ligne de requête ou un en-tête qu'`http.server` refuse lui-même, dont la ligne qu'une espace
  dans le chemin coupe en quatre mots, reçoit son 400, 414 ou 431, et la connexion se ferme, sans
  lecture du corps ; le relais refuse lui-même par 400, corps lu et connexion gardée (en HTTP/1.1 :
  un client HTTP/1.0 voit la connexion se fermer après chaque réponse), une cible qui ne commence
  pas par une seule `/` (la forme absolue comprise, et `//…`, lue sur la ligne de requête brute,
  qu'`http.server` réécrirait en `/…`) ou qui porte un octet hors de 0x21-0x7E, et une méthode
  qu'`http.client` ne sait pas envoyer (un octet de 0x00 à 0x1F, un caractère non ASCII) ; une
  méthode qui porte 0x7F passe, et l'application en juge ;
- `email.feedparser`, qui lit les en-têtes pour `http.server`, perd tous ceux qui suivent une ligne
  qu'il lit mal (une ligne sans deux-points, un nom suivi d'une espace), `Content-Length` compris,
  prend un CR pour une fin de ligne, et garde dans la valeur un repli ou un octet nul : le corps
  passerait pour une seconde requête, ou un en-tête serait injecté. Le relais refuse par 400, sans
  lire le corps, et ferme la connexion, une requête dont il note un défaut des en-têtes, et une
  requête dont une ligne d'en-tête porte un CR ailleurs qu'avant son LF final, porte un octet nul,
  ou commence par une espace ou une tabulation (un repli) ;
- un corps au cadrage illisible (un `Transfer-Encoding` autre que `chunked`, ou accompagné d'un
  `Content-Length`, des `Content-Length` contradictoires ou qui ne sont pas des nombres, un morceau
  mal formé, plus de 100 champs de fin) reçoit 400, et la connexion se ferme. Un défaut lu avant le
  corps, ou dans ses premières lectures, ne fait rien parvenir à l'application ; plus loin, elle a
  déjà reçu la ligne de requête, les en-têtes et le début du corps, puis la fermeture ;
- une page ou un manifeste que le relais peut retoucher est lu entier, 5 Mio au plus, avant tout
  envoi : une page que l'application diffuse au fil n'arrive au client qu'entière, ou par ses
  5 premiers Mio d'un coup, le reste suivant au fil ;
- le corps d'une requête que le relais transmet est lu en entier avant la réponse : un client qui
  envoie un corps par morceaux et attend la réponse avant de le finir reste bloqué jusqu'au délai
  d'inactivité de 75 s, qui ferme la connexion ;
- une réponse que l'application envoie avant d'avoir lu le corps, puis suivie d'une fermeture (un
  413 précoce, un 401 avant l'envoi), peut se perdre : le client reçoit alors 502, et le journal
  dit l'application injoignable ;
- un manifeste de 5 Mio fait de petits objets peut dépasser, une fois lu, la mémoire du conteneur,
  128 Mio, comme une page de 5 Mio faite de liens d'icône, une fois retouchée : le relais est alors
  tué, puis relancé ;
- WebSocket : le relais répond 501 ; un 101 que l'application envoie sans qu'on le lui demande
  n'est pas transmis : le client reçoit 502, et le journal dit l'application injoignable ;
- si le premier déploiement du staging par un `deployer.sh` de la `v0.14.0` du modèle échoue, le
  retour automatique recopie un `compose.env.precedent` sans `<PREFIXE>RELAIS` : il sert le staging
  sans marque, jusqu'au déploiement suivant ;
- le rendu du bandeau dans un navigateur n'est éprouvé par aucun test : c'est la constatation sur
  l'appareil qui le prouve ;
- un PNG de profondeur 16 ou de palette de 1 à 4 bits, entrelacé, un ICO ou un WebP reçoit l'icône
  générique ; les blocs annexes d'un PNG sont retirés (gamma, profil de couleur, texte) ;
- un PNG se reconnaît à sa signature, un SVG à son type, `image/svg+xml` : un SVG servi sous un
  autre type reçoit l'icône générique.
"""

import base64
import functools
import hashlib
import html
import http.client
import itertools
import json
import os
import re
import socketserver
import struct
import sys
import threading
import zlib
from collections import OrderedDict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import quote, unquote, urljoin, urlsplit

# --- les valeurs fixées par la spec -------------------------------------------------------------

# La rampe : (luminance, (R, V, B)) à 0, 128 et 255.
RAMPE = ((0, (0x5C, 0x1A, 0x00)), (128, (0xE8, 0x59, 0x0C)), (255, (0xFF, 0xE3, 0xC2)))
ORANGE = (0xE8, 0x59, 0x0C)

PREFIXE_TITRE = b"test &middot; "
PREFIXE_NOM = "test · "
PREFIXE_NOM_COURT = "test "

LIEN_FEUILLE = b'<link rel="stylesheet" href="/.marque/marque.css">'
CHEMIN_RESERVE = "/.marque/"

PLAFOND_PAGE = 5 * 1024 * 1024
COTE_MAX = 1024
# Les pixels d'un PNG, octets de filtre exclus, ou les octets d'un SVG.
ICONE_MAX = 4 * 1024 * 1024
# Ce que le relais lit d'une icône de l'application : au-delà, l'icône générique.
LECTURE_ICONE_MAX = 5 * 1024 * 1024

ICONES_GARDEES = 32
CACHE_OCTETS = 16 * 1024 * 1024
LECTURES_ICONE = 2

DELAI_AMONT = 120
DELAI_INACTIF = 75

# L'adresse d'écoute par défaut : le port publié et l'alias du tunnel arrivent sur l'interface du
# conteneur.
HOTE_ECOUTE = "0.0.0.0"

_DECLARATIONS = (
    'content: "TEST"; position: fixed; top: 0; left: 0; right: 0; box-sizing: content-box; '
    "height: 20px; padding-top: env(safe-area-inset-top, 0px); background: #e8590c; "
    "color: #ffffff; font: 700 12px/20px system-ui, sans-serif; letter-spacing: 0.2em; "
    "text-align: center; pointer-events: none; z-index: 2147483647;"
)

# Trois règles séparées : un navigateur qui ne connaît pas `:popover-open` rejetterait toute une
# liste de sélecteurs.
FEUILLE = (
    "/* La marque du staging, posée par le relais du modèle (scripts/modele/marque.py). */\n"
    + "".join(
        selecteur + " { " + _DECLARATIONS + " }\n"
        for selecteur in ("html::before", "dialog[open]::before", ":popover-open::before")
    )
).encode("utf-8")


# --- la rampe -----------------------------------------------------------------------------------


def luminance(r: int, g: int, b: int) -> int:
    return (54 * r + 183 * g + 19 * b) >> 8


def couleur_de(l: int) -> tuple[int, int, int]:
    """La couleur de la rampe pour une luminance de 0 à 255."""
    for (l0, c0), (l1, c1) in itertools.pairwise(RAMPE):
        if l <= l1:
            return tuple(  # type: ignore[return-value]
                round(a + (b - a) * (l - l0) / (l1 - l0)) for a, b in zip(c0, c1)
            )
    return RAMPE[-1][1]


@functools.cache
def _tables() -> tuple[bytes, bytes, bytes]:
    """Les trois tables 256 -> 256 de la rampe, une par canal."""
    couleurs = [couleur_de(i) for i in range(256)]
    return tuple(bytes(c[k] for c in couleurs) for k in range(3))  # type: ignore[return-value]


# --- le PNG -------------------------------------------------------------------------------------

_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_CANAUX = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}


def _bloc(nom: bytes, donnees: bytes) -> bytes:
    crc = zlib.crc32(nom + donnees) & 0xFFFFFFFF
    return struct.pack(">I", len(donnees)) + nom + donnees + struct.pack(">I", crc)


def _lire_blocs(donnees: bytes) -> dict[bytes, list[bytes]] | None:
    """Les blocs d'un PNG par nom, ou `None` s'il est tronqué, mal formé ou sans `IEND`."""
    if not donnees.startswith(_SIGNATURE):
        return None
    blocs: dict[bytes, list[bytes]] = {}
    pos = len(_SIGNATURE)
    fin = len(donnees)
    premier = True
    while pos + 12 <= fin:
        (taille,) = struct.unpack_from(">I", donnees, pos)
        nom = donnees[pos + 4 : pos + 8]
        debut = pos + 8
        if debut + taille + 4 > fin:
            return None
        corps = donnees[debut : debut + taille]
        (crc,) = struct.unpack_from(">I", donnees, debut + taille)
        if zlib.crc32(nom + corps) & 0xFFFFFFFF != crc:
            return None
        if premier and nom != b"IHDR":
            return None
        premier = False
        blocs.setdefault(nom, []).append(corps)
        if nom == b"IEND":
            return blocs
        pos = debut + taille + 4
    return None


def _defiltrer(brut: bytes, largeur: int, hauteur: int, canaux: int) -> bytearray | None:
    """Les pixels d'un PNG non entrelacé de profondeur 8, octets de filtre retirés."""
    long_ligne = largeur * canaux
    pas = long_ligne + 1
    pixels = bytearray(long_ligne * hauteur)
    precedente = bytearray(long_ligne)
    for y in range(hauteur):
        filtre = brut[y * pas]
        ligne = bytearray(brut[y * pas + 1 : (y + 1) * pas])
        if filtre == 0:
            pass
        elif filtre == 1:
            for i in range(canaux, long_ligne):
                ligne[i] = (ligne[i] + ligne[i - canaux]) & 255
        elif filtre == 2:
            for i in range(long_ligne):
                ligne[i] = (ligne[i] + precedente[i]) & 255
        elif filtre == 3:
            for i in range(long_ligne):
                gauche = ligne[i - canaux] if i >= canaux else 0
                ligne[i] = (ligne[i] + ((gauche + precedente[i]) >> 1)) & 255
        elif filtre == 4:
            for i in range(long_ligne):
                a = ligne[i - canaux] if i >= canaux else 0
                b = precedente[i]
                c = precedente[i - canaux] if i >= canaux else 0
                pa = abs(b - c)
                pb = abs(a - c)
                pc = abs(a + b - 2 * c)
                if pa <= pb and pa <= pc:
                    p = a
                elif pb <= pc:
                    p = b
                else:
                    p = c
                ligne[i] = (ligne[i] + p) & 255
        else:
            return None
        pixels[y * long_ligne : (y + 1) * long_ligne] = ligne
        precedente = ligne
    return pixels


def _png(largeur: int, hauteur: int, type_couleur: int, blocs_avant: bytes, image: bytes) -> bytes:
    """Un PNG de profondeur 8 : `image` est l'image sans octets de filtre."""
    long_ligne = len(image) // hauteur
    brut = bytearray(hauteur * (long_ligne + 1))
    for y in range(hauteur):
        debut = y * (long_ligne + 1) + 1
        brut[debut : debut + long_ligne] = image[y * long_ligne : (y + 1) * long_ligne]
    entete = struct.pack(">IIBBBBB", largeur, hauteur, 8, type_couleur, 0, 0, 0)
    return (
        _SIGNATURE
        + _bloc(b"IHDR", entete)
        + blocs_avant
        + _bloc(b"IDAT", zlib.compress(bytes(brut), 6))
        + _bloc(b"IEND", b"")
    )


def recolorer_png(donnees: bytes) -> bytes | None:
    """Le PNG recoloré, ou `None` s'il n'est pas de ceux que le relais admet."""
    try:
        return _recolorer_png(donnees)
    except (zlib.error, struct.error, ValueError, IndexError):
        return None


def _recolorer_png(donnees: bytes) -> bytes | None:
    blocs = _lire_blocs(donnees)
    if blocs is None or len(blocs.get(b"IHDR", [])) != 1 or len(blocs[b"IHDR"][0]) != 13:
        return None
    largeur, hauteur, profondeur, type_couleur, compression, filtrage, entrelace = struct.unpack(
        ">IIBBBBB", blocs[b"IHDR"][0]
    )
    if profondeur != 8 or type_couleur not in _CANAUX or compression or filtrage or entrelace:
        return None
    if not (1 <= largeur <= COTE_MAX and 1 <= hauteur <= COTE_MAX):
        return None
    canaux = _CANAUX[type_couleur]
    if largeur * hauteur * canaux > ICONE_MAX:
        return None
    attendu = hauteur * (largeur * canaux + 1)
    decompresseur = zlib.decompressobj()
    brut = decompresseur.decompress(b"".join(blocs.get(b"IDAT", [])), attendu + 1)
    if len(brut) != attendu or decompresseur.unconsumed_tail or not decompresseur.eof:
        return None
    if decompresseur.unused_data:
        return None
    pixels = _defiltrer(brut, largeur, hauteur, canaux)
    if pixels is None:
        return None
    rouge, vert, bleu = _tables()
    trns = blocs.get(b"tRNS", [b""])[0]
    nombre = largeur * hauteur

    if type_couleur == 3:
        palette = blocs.get(b"PLTE", [b""])[0]
        if not palette or len(palette) % 3 or len(palette) > 768:
            return None
        neuve = bytearray(len(palette))
        for i in range(0, len(palette), 3):
            c = couleur_de(luminance(palette[i], palette[i + 1], palette[i + 2]))
            neuve[i : i + 3] = bytes(c)
        avant = _bloc(b"PLTE", bytes(neuve))
        if trns:
            avant += _bloc(b"tRNS", trns)
        return _png(largeur, hauteur, 3, avant, bytes(pixels))

    if type_couleur in (0, 4):
        gris = bytes(pixels[0::canaux])
        lum = gris
        alpha = bytes(pixels[1::2]) if type_couleur == 4 else None
        if type_couleur == 0 and len(trns) >= 2:
            if trns[0] == 0:
                alpha = bytes(0 if g == trns[1] else 255 for g in gris)
            else:
                alpha = b"\xff" * nombre
    else:
        r, v, b = bytes(pixels[0::canaux]), bytes(pixels[1::canaux]), bytes(pixels[2::canaux])
        lum = bytes(map(luminance, r, v, b))
        alpha = bytes(pixels[3::4]) if type_couleur == 6 else None
        if type_couleur == 2 and len(trns) >= 6:
            if trns[0] == 0 and trns[2] == 0 and trns[4] == 0:
                cle_rvb = (trns[1], trns[3], trns[5])
                alpha = bytes(0 if t == cle_rvb else 255 for t in zip(r, v, b))
            else:
                alpha = b"\xff" * nombre

    sortie_canaux = 3 if alpha is None else 4
    image = bytearray(nombre * sortie_canaux)
    image[0::sortie_canaux] = lum.translate(rouge)
    image[1::sortie_canaux] = lum.translate(vert)
    image[2::sortie_canaux] = lum.translate(bleu)
    if alpha is not None:
        image[3::4] = alpha
    return _png(largeur, hauteur, 2 if alpha is None else 6, b"", bytes(image))


@functools.cache
def icone_generique() -> bytes:
    """Un PNG de 512 x 512, tout orange, calculé une fois."""
    return _png(512, 512, 2, b"", bytes(ORANGE) * (512 * 512))


# --- le SVG -------------------------------------------------------------------------------------

_NOMBRE = r"[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?"
_NOMBRE_SEUL = re.compile(_NOMBRE.encode() + rb"\Z")
_BALISE_SVG = re.compile(rb"""<svg(?![\w:-])(?:[^>"']|"[^"]*"|'[^']*')*>""", re.IGNORECASE)
_ATTRIBUT = re.compile(
    rb"""(?<![\w:.-])(viewBox|width|height)\s*=\s*(?:"([^"]*)"|'([^']*)')""", re.IGNORECASE
)
_COMMENTAIRE = re.compile(rb"<!--.*?(?:-->|\Z)", re.DOTALL)

_ENVELOPPE = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="{v}"><defs>'
    '<filter id="m" color-interpolation-filters="sRGB">'
    '<feColorMatrix type="matrix" values="0.2109 0.7148 0.0742 0 0 0.2109 0.7148 0.0742 0 0 '
    '0.2109 0.7148 0.0742 0 0 0 0 0 1 0"/>'
    '<feComponentTransfer><feFuncR type="table" tableValues="0.3608 0.9098 1"/>'
    '<feFuncG type="table" tableValues="0.1020 0.3490 0.8902"/>'
    '<feFuncB type="table" tableValues="0 0.0471 0.7608"/></feComponentTransfer></filter></defs>'
    '<image href="data:image/svg+xml;base64,{b}" x="{x}" y="{y}" width="{w}" height="{h}" '
    'filter="url(#m)"/></svg>'
)


def _nombres(texte: bytes, combien: int) -> list[str] | None:
    morceaux = [m for m in re.split(rb"[\s,]+", texte.strip()) if m]
    if len(morceaux) != combien or not all(_NOMBRE_SEUL.match(m) for m in morceaux):
        return None
    return [m.decode("ascii") for m in morceaux]


def _cadre(donnees: bytes) -> list[str]:
    """Les quatre nombres du `viewBox` de la balise racine, ou de `width` et `height`."""
    visible = _COMMENTAIRE.sub(lambda m: b" " * len(m.group()), donnees)
    balise = _BALISE_SVG.search(visible)
    valeurs: dict[bytes, bytes] = {}
    if balise:
        for m in _ATTRIBUT.finditer(balise.group()):
            valeurs.setdefault(m.group(1).lower(), m.group(2) if m.group(2) is not None else m.group(3))
    vue = _nombres(valeurs[b"viewbox"], 4) if b"viewbox" in valeurs else None
    if vue:
        return vue
    taille = []
    for nom in (b"width", b"height"):
        brut = valeurs.get(nom, b"").strip()
        if brut.lower().endswith(b"px"):
            brut = brut[:-2]
        nombres = _nombres(brut, 1)
        taille.append(nombres[0] if nombres and float(nombres[0]) > 0 else None)
    if all(taille):
        return ["0", "0", *taille]  # type: ignore[list-item]
    return ["0", "0", "100", "100"]


def envelopper_svg(donnees: bytes) -> bytes | None:
    """L'enveloppe SVG qui embarque l'original sous le filtre de la rampe."""
    if len(donnees) > ICONE_MAX:
        return None
    x, y, w, h = _cadre(donnees)
    sortie = _ENVELOPPE.format(
        v=f"{x} {y} {w} {h}",
        b=base64.b64encode(donnees).decode("ascii"),
        x=x,
        y=y,
        w=w,
        h=h,
    )
    return sortie.encode("ascii")


# --- les liens d'icône --------------------------------------------------------------------------

_ICONE_GENERIQUE = "/.marque/icone"
# Le point et la barre encodés, que l'application décode (uvicorn décode `%2F` dans son chemin).
_POINT_OU_BARRE_ENCODES = re.compile(r"%2([EeFf])")


def _sans_points(chemin: str) -> str:
    """Le chemin absolu `chemin` sans ses segments `.` et `..` (RFC 3986, § 5.2.4)."""
    segments = chemin.split("/")[1:]
    sortie: list[str] = []
    for k, segment in enumerate(segments):
        if segment == "..":
            if sortie:
                sortie.pop()
        elif segment != ".":
            sortie.append(segment)
            continue
        # un `.` ou un `..` final laisse le chemin fini par `/`
        if k == len(segments) - 1:
            sortie.append("")
    return "/" + "/".join(sortie)


def _chemin_decode(cible: str) -> str:
    """Le chemin de la cible absolue `cible`, sans sa requête, `%2E`, `%2e`, `%2F` et `%2f`
    décodés (eux seuls), comme l'application le lit."""
    return _POINT_OU_BARRE_ENCODES.sub(
        lambda m: "." if m.group(1) in "Ee" else "/", cible.partition("?")[0]
    )


def chemin_normal(cible: str) -> str:
    """Le chemin décodé de la cible absolue `cible`, puis ses segments `.` et `..` retirés. Il ne
    sert qu'à reconnaître le chemin réservé : la cible transmise reste telle qu'elle est arrivée."""
    return _sans_points(_chemin_decode(cible))


def sous_le_chemin_reserve(cible: str) -> bool:
    """Si la cible absolue `cible` est sous `/.marque/` : telle qu'elle est, décodée, ou décodée
    puis normalisée."""
    decode = _chemin_decode(cible)
    return any(
        forme.startswith(CHEMIN_RESERVE) for forme in (cible, decode, _sans_points(decode))
    )


def chemin_admis(de: str) -> bool:
    """Un chemin de l'application : une seule `/` de tête, des caractères imprimables sans espace,
    hors du chemin réservé, qui n'est jamais le sien, même normalisé."""
    if not 1 <= len(de) <= 1024 or not de.startswith("/") or de.startswith("//"):
        return False
    if sous_le_chemin_reserve(de):
        return False
    return all("!" <= c <= "~" and c != "\\" for c in de)


def _gardes(encodes: str) -> str:
    """L'ASCII imprimable, sans les caractères `encodes` : ce que le navigateur laisse tel quel."""
    return "".join(chr(c) for c in range(0x21, 0x7F) if chr(c) not in encodes)


# Ce que le navigateur encode, d'après WHATWG : les contrôles C0, DEL, l'espace et le non ASCII (en
# UTF-8), puis, dans le chemin (« path percent-encode set »), `"`, `#`, `<`, `>`, `?`, `^`,
# l'accent grave, `{` et `}`, et, dans la requête (« query percent-encode set »), `"`, `#`, `<` et
# `>`. Tout le reste passe tel quel, `%` compris, qu'il ouvre un `%XX` ou non, et l'apostrophe de la
# requête, que WHATWG encode pour `http` et `https` (« special-query percent-encode set »).
_GARDES_CHEMIN = _gardes('"#<>?^`{}')
_GARDES_REQUETE = _gardes('"#<>')


def lien_icone(cible: str, base: str, hote: str | None) -> str:
    """Le lien de l'icône recolorée pour `cible`, lue sur la page ou le manifeste `base`."""
    try:
        jointe = urlsplit(urljoin(base, cible.strip()))
    except ValueError:
        return _ICONE_GENERIQUE
    if (jointe.scheme or jointe.netloc) and (
        jointe.scheme not in ("", "http", "https")
        or hote is None
        or "@" in jointe.netloc
        or jointe.netloc.lower() != hote.lower()
    ):
        return _ICONE_GENERIQUE
    # L'encodage ne fait que rallonger : au-delà de 1024 caractères, `chemin_admis` refuserait.
    if len(jointe.path) + len(jointe.query) > 1024:
        return _ICONE_GENERIQUE
    # Le chemin et la requête résolus sont encodés comme le navigateur les demanderait :
    # `/icône.png` devient `/ic%C3%B4ne.png`, `?v=é` devient `?v=%C3%A9`, `/a+b.png` reste tel
    # quel. Une barre oblique inverse n'est pas encodée : `chemin_admis` la refuse.
    try:
        chemin = quote(jointe.path, safe=_GARDES_CHEMIN)
        requete = quote(jointe.query, safe=_GARDES_REQUETE)
    except UnicodeEncodeError:
        # un caractère qu'UTF-8 n'encode pas, une demi-paire venue du JSON
        return _ICONE_GENERIQUE
    de = chemin + ("?" + requete if requete else "")
    if not chemin_admis(de):
        return _ICONE_GENERIQUE
    return _ICONE_GENERIQUE + "?de=" + quote(de, safe="/")


# --- la page ------------------------------------------------------------------------------------

# Le début d'un `<link>` ou d'un `<title>`, et non d'un `<linker>` ou d'un `<titles>`.
_DEBUT_LINK = re.compile(rb"<link(?=[\s/>])")
_DEBUT_TITRE = re.compile(rb"<title(?=[\s/>])")
# Les états du tokeniseur HTML dans une balise, chacun sauté d'un coup : avant un nom (les blancs et
# `/`), un nom (son premier caractère peut être `=`, et un guillemet en fait partie), les blancs,
# une valeur sans guillemets (un guillemet en fait partie).
_AVANT_NOM = re.compile(rb"[\s/]*")
_NOM = re.compile(rb"[^\s/>][^\s/>=]*")
_BLANCS = re.compile(rb"\s*")
_SANS_GUILLEMETS = re.compile(rb"[^\s>]*")
_GUILLEMET = re.compile(rb"""["']""")
# Un attribut d'un `<link>` ; une valeur sans guillemets court, comme pour le tokeniseur HTML,
# jusqu'à un blanc ou `>`, guillemets et `<` compris.
_ATTRIBUT_LINK = re.compile(
    rb"""([^\s"'<>/=]+)(?:\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+)))?"""
)
_FAVICON = b'<link rel="icon" href="/.marque/icone?de=/favicon.ico">'


def _fin_de_balise(texte: bytes, pos: int, fin: int) -> int:
    """La place qui suit le `>` d'une balise ouverte avant `pos`, les valeurs entre guillemets
    sautées, ou -1 si la balise, ou l'une de ses valeurs, ne se ferme pas avant `fin`. Comme pour
    le tokeniseur HTML, un guillemet n'ouvre une valeur que juste après le `=` qui suit un nom,
    blancs admis autour. Chaque pas avance d'un nom ou d'une valeur : la recherche est linéaire."""
    # Sans guillemet avant le premier `>`, la balise s'y ferme, dans tout état du tokeniseur ; et
    # sans `>`, elle ne se ferme jamais.
    chevron = texte.find(b">", pos, fin)
    if chevron < 0:
        return -1
    if _GUILLEMET.search(texte, pos, chevron) is None:
        return chevron + 1
    while True:
        pos = _AVANT_NOM.match(texte, pos, fin).end()
        if pos >= fin:
            return -1
        if texte[pos] == 0x3E:  # `>`
            return pos + 1
        pos = _BLANCS.match(texte, _NOM.match(texte, pos, fin).end(), fin).end()
        if pos >= fin:
            return -1
        if texte[pos] != 0x3D:  # pas de `=` : un autre nom, `/` ou `>`
            continue
        pos = _BLANCS.match(texte, pos + 1, fin).end()
        if pos >= fin:
            return -1
        signe = texte[pos]
        if signe in (0x22, 0x27):  # `"` ou `'` : une valeur entre guillemets
            ferme = texte.find(texte[pos : pos + 1], pos + 1, fin)
            if ferme < 0:
                return -1
            pos = ferme + 1
        elif signe != 0x3E:  # une valeur sans guillemets ; `>` ferme la balise au tour suivant
            pos = _SANS_GUILLEMETS.match(texte, pos, fin).end()


def _balises(debut: re.Pattern, texte: bytes, fin: int):
    """Le début et la fin de chaque balise que `debut` ouvre avant `fin`, en un seul passage. Une
    balise ou une valeur jamais fermée court jusqu'à la fin, comme pour le tokeniseur HTML : la
    recherche s'y arrête, sans elle."""
    pos = 0
    while (ouverte := debut.search(texte, pos, fin)) is not None:
        bout = _fin_de_balise(texte, ouverte.end(), fin)
        if bout < 0:
            return
        yield ouverte.start(), bout
        pos = bout


def est_page(type_contenu: str | None) -> bool:
    return (type_contenu or "").split(";")[0].strip().lower() == "text/html"


def est_manifeste(chemin: str, type_contenu: str | None) -> bool:
    sans_requete = chemin.split("?")[0]
    type_seul = (type_contenu or "").split(";")[0].strip().lower()
    return (
        sans_requete.endswith(".webmanifest")
        or sans_requete == "/manifest.json"
        or type_seul == "application/manifest+json"
    )


def _balise_icone(balise: bytes) -> tuple[bool, tuple[int, int, bytes, bool] | None]:
    """Si un `<link>` est une icône, et la place de la valeur de son `href` dans la balise."""
    rel = ""
    href = None
    for m in _ATTRIBUT_LINK.finditer(balise, len(b"<link")):
        nom = m.group(1).lower()
        for k in (2, 3, 4):
            if m.group(k) is not None:
                valeur, debut, fin = m.group(k), m.start(k), m.end(k)
                break
        else:
            continue
        if nom == b"rel" and not rel:
            rel = valeur.decode("latin-1").lower()
        elif nom == b"href" and href is None:
            href = (debut, fin, valeur, m.group(4) is not None)
    mots = rel.split()
    icone = "icon" in mots or any(mot.startswith("apple-touch-icon") for mot in mots)
    return icone, href


def retoucher_page(corps: bytes, chemin: str, hote: str | None) -> bytes:
    """La page avec la feuille, le préfixe du titre et les liens d'icône."""
    # Les formes se cherchent hors des commentaires : leur texte est masqué, de même longueur.
    visible = _COMMENTAIRE.sub(lambda m: b" " * len(m.group()), corps).lower()
    fin = visible.find(b"</head>")
    if fin < 0:
        fin = visible.find(b"<body")
    if fin < 0:
        fin = len(corps)
    modifs: list[tuple[int, int, bytes]] = []
    titre = next(_balises(_DEBUT_TITRE, visible, fin), None)
    if titre:
        modifs.append((titre[1], titre[1], PREFIXE_TITRE))
    liens = 0
    # le lien retouché de chaque valeur déjà lue : un `href` répété n'est résolu qu'une fois
    neufs: dict[bytes, bytes] = {}
    for ouverte, bout in _balises(_DEBUT_LINK, visible, fin):
        balise = corps[ouverte:bout]
        icone, href = _balise_icone(balise)
        if not icone:
            continue
        liens += 1
        if href is None:
            continue
        debut, fin_valeur, valeur, sans_guillemets = href
        neuf = neufs.get(valeur)
        if neuf is None:
            neuf = lien_icone(html.unescape(valeur.decode("utf-8", "replace")), chemin, hote)
            neuf = neufs[valeur] = neuf.encode("ascii")
        if sans_guillemets:
            neuf = b'"' + neuf + b'"'
        modifs.append((ouverte + debut, ouverte + fin_valeur, neuf))
    modifs.append((fin, fin, LIEN_FEUILLE + (b"" if liens else _FAVICON)))
    # La page se construit une seule fois, de ses morceaux dans l'ordre. Deux retouches à la même
    # place se posent la dernière ajoutée d'abord ; une retouche qui chevauche la précédente, un
    # titre lu dans la valeur d'un lien, est laissée.
    morceaux: list[bytes] = []
    place = 0
    ordre = sorted(range(len(modifs)), key=lambda i: (modifs[i][0], -i))
    for debut, bout, texte in (modifs[i] for i in ordre):
        if debut < place:
            continue
        morceaux += (corps[place:debut], texte)
        place = bout
    morceaux.append(corps[place:])
    return b"".join(morceaux)


# --- le manifeste -------------------------------------------------------------------------------


def retoucher_manifeste(corps: bytes, chemin: str, hote: str | None) -> bytes | None:
    """Le manifeste marqué, ou `None` s'il est illisible."""
    try:
        manifeste = json.loads(corps.decode("utf-8-sig"))
    except (UnicodeDecodeError, ValueError, RecursionError):
        return None
    if not isinstance(manifeste, dict):
        return None
    nom, court = manifeste.get("name"), manifeste.get("short_name")
    if isinstance(nom, str):
        manifeste["name"] = PREFIXE_NOM + nom
    if isinstance(court, str):
        manifeste["short_name"] = PREFIXE_NOM_COURT + court
    if not isinstance(nom, str) and not isinstance(court, str):
        manifeste["name"] = "test"
    icones = manifeste.get("icons")
    if isinstance(icones, list):
        for icone in icones:
            if isinstance(icone, dict) and isinstance(icone.get("src"), str):
                icone["src"] = lien_icone(icone["src"], chemin, hote)
    try:
        return json.dumps(manifeste, ensure_ascii=False).encode("utf-8")
    except UnicodeEncodeError:
        return None


# --- le serveur ---------------------------------------------------------------------------------

BLOC = 64 * 1024

# Les en-têtes d'un seul saut, retirés dans les deux sens, avec ceux que nomme `Connection` et tous
# les `Proxy-*`.
_UN_SAUT = frozenset(("connection", "keep-alive", "te", "trailer", "transfer-encoding", "upgrade"))
# Les conditionnels d'un `GET` ou d'un `HEAD` : une copie en cache d'avant le relais reviendrait en
# 304, sans marque.
_CONDITIONNELS = frozenset(("if-none-match", "if-modified-since"))
# Ce que la demande d'une icône ne transmet pas : elle veut l'icône entière, sans compression.
_HORS_ICONE = _CONDITIONNELS | frozenset(
    ("if-match", "if-unmodified-since", "if-range", "range")
    + ("accept-encoding", "expect", "content-length")
)
_ERREURS_AMONT = (OSError, http.client.HTTPException)
_SANS_CACHE = (("Cache-Control", "no-cache"),)
# Les directives de l'application qu'une réponse retouchée garde, à côté de `no-cache`.
_DIRECTIVES_GARDEES = ("no-store", "private")
_ENTRE_GUILLEMETS = re.compile(r'"(?:[^"\\]|\\.)*"')
_LONGUEUR = re.compile(r"[0-9]{1,18}\Z")
_PORT = re.compile(r"[0-9]{1,5}\Z")
_TAILLE_MORCEAU = re.compile(rb"([0-9A-Fa-f]{1,16})[ \t]*(?:;[^\r\n]*)?\r?\n\Z")
_CHAMPS_DE_FIN = 100


class _MalFormee(Exception):
    """Le cadrage du corps de la requête est illisible : on ne sait plus où elle finit."""


class _ClientParti(Exception):
    """Le client est parti pendant qu'une réponse informative lui était écrite. Ce n'est pas une
    `OSError`, que la lecture de l'application prendrait pour une application injoignable."""


class _Reponse(http.client.HTTPResponse):
    """Une réponse de l'application, qui lit sur le même fichier tamponné ses réponses
    informatives (de 102 à 199, sauf 101), jusqu'à la réponse finale, et les passe à `informer`.
    `http.client` saute lui-même le 100, et prendrait toute autre réponse 1xx pour la finale."""

    def __init__(self, sock, *args, informer=None, **kwargs) -> None:
        super().__init__(sock, *args, **kwargs)
        self._informer = informer

    def _read_status(self):
        while True:
            version, statut, raison = super()._read_status()
            if not 102 <= statut < 200:
                return version, statut, raison
            entetes = http.client.parse_headers(self.fp)
            if self._informer is not None:
                self._informer(statut, raison.strip(), entetes.items())


class _Lignes:
    """Le fichier du client, le temps que `http.client.parse_headers` lise les en-têtes, ce qu'il
    fait par `readline` seul : note une ligne d'en-tête refusée, qui porte un CR ailleurs que juste
    avant son LF final ou un octet nul, ou qui commence par une espace ou une tabulation."""

    def __init__(self, fichier) -> None:
        self.fichier = fichier
        self.refusee = False

    def readline(self, taille: int = -1) -> bytes:
        ligne = self.fichier.readline(taille)
        if ligne.endswith(b"\r\n"):
            reste = ligne[:-2]
        elif ligne.endswith(b"\n"):
            reste = ligne[:-1]
        else:
            reste = ligne
        # un CR qu'`email.feedparser` prendrait pour une fin de ligne
        if b"\r" in reste:
            self.refusee = True
        # un octet nul, interdit dans un champ
        if b"\x00" in ligne:
            self.refusee = True
        # un repli, qui continuerait la ligne d'avant ; la ligne vide finale commence par CR ou LF
        if ligne[:1] in (b" ", b"\t"):
            self.refusee = True
        return ligne


def journal(message: str) -> None:
    """Une ligne du journal, sur la sortie d'erreur. Jamais un chemin, une requête, un en-tête ni
    une adresse : un jeton peut passer dans un chemin."""
    sys.stderr.write(f"marque : {message}\n")
    sys.stderr.flush()


def _sauf(entetes: list[tuple[str, str]], *noms: str) -> list[tuple[str, str]]:
    return [(nom, valeur) for nom, valeur in entetes if nom.lower() not in noms]


def _sans_un_saut(entetes: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """Les en-têtes, doublons compris et dans leur ordre, sans ceux d'un seul saut."""
    nommes = {
        jeton.strip().lower()
        for nom, valeur in entetes
        if nom.lower() == "connection"
        for jeton in valeur.split(",")
    }
    # `Host` passe tel qu'il arrive, même nommé par `Connection`.
    nommes.discard("host")
    return [
        (nom, valeur)
        for nom, valeur in entetes
        if nom.lower() not in _UN_SAUT
        and nom.lower() not in nommes
        and not nom.lower().startswith("proxy-")
    ]


def _cible_admise(cible: str) -> bool:
    """Une seule `/` de tête, puis des octets de 0x21 à 0x7E : ni espace, ni caractère de contrôle,
    ni caractère non ASCII, ni forme absolue, qui échapperait au chemin réservé."""
    return (
        cible.startswith("/")
        and not cible.startswith("//")
        and all("!" <= c <= "~" for c in cible)
    )


def _amont(amont: str) -> tuple[str, int]:
    """L'hôte et le port de `http://<hôte>:<port>`, ou `ValueError`."""
    morceaux = urlsplit(amont)
    port = morceaux.port
    if (
        morceaux.scheme != "http"
        or not morceaux.hostname
        or port is None
        or port < 1
        or morceaux.username is not None
        or morceaux.path not in ("", "/")
        or morceaux.query
        or morceaux.fragment
    ):
        raise ValueError("amont : http://<hôte>:<port> attendu")
    return morceaux.hostname, port


def _lire_borne(reponse: http.client.HTTPResponse, n: int) -> bytes:
    """Au plus `n` octets du corps ; `IncompleteRead` si l'application coupe avant sa longueur."""
    corps = reponse.read(n)
    if reponse.length and len(corps) < n:
        raise http.client.IncompleteRead(corps, reponse.length)
    return corps


def _cache_retouche(entetes: list[tuple[str, str]]) -> tuple[str, str]:
    """Le `Cache-Control` d'une réponse retouchée : `no-cache`, puis `no-store` et `private` si
    l'application les pose, sous leur forme simple. `max-age`, `public` et les autres partent."""
    noms = {
        morceau.partition("=")[0].strip().lower()
        for nom, valeur in entetes
        if nom.lower() == "cache-control"
        for morceau in _ENTRE_GUILLEMETS.sub('""', valeur).split(",")
    }
    gardees = [directive for directive in _DIRECTIVES_GARDEES if directive in noms]
    return ("Cache-Control", ", ".join(("no-cache", *gardees)))


def _trop_grande(sorte: str, corps: bytes) -> bool:
    if sorte == "svg":
        return len(corps) > ICONE_MAX
    if corps[12:16] == b"IHDR" and len(corps) >= 24:
        largeur, hauteur = struct.unpack(">II", corps[16:24])
        return largeur > COTE_MAX or hauteur > COTE_MAX
    return False


class _Serveur(ThreadingHTTPServer):
    """Le serveur du relais : son amont, ses délais, et l'état que partagent ses connexions."""

    def __init__(
        self, adresse: tuple[str, int], amont: tuple[str, int], delai_inactif: float,
        delai_amont: float,
    ) -> None:
        self.amont = amont
        self.delai_inactif = delai_inactif
        self.delai_amont = delai_amont
        self.lectures = threading.BoundedSemaphore(LECTURES_ICONE)
        self.recoloration = threading.Lock()
        self._verrou_cache = threading.Lock()
        self._cache: OrderedDict[tuple[bytes, str], bytes] = OrderedDict()
        self._octets = 0
        super().__init__(adresse, Relais)

    def server_bind(self) -> None:
        # Celui d'`HTTPServer` demande le nom de l'adresse d'écoute (`socket.getfqdn`), une
        # résolution inverse : le relais ne demande jamais rien qu'à son amont.
        socketserver.TCPServer.server_bind(self)
        self.server_name = str(self.server_address[0])
        self.server_port = self.server_address[1]

    def handle_error(self, request, client_address) -> None:
        # Celui de `socketserver` écrirait l'adresse du client et la trace de l'exception.
        journal("incident interne, connexion fermée")

    def icone_gardee(self, cle: tuple[bytes, str]) -> bytes | None:
        with self._verrou_cache:
            icone = self._cache.get(cle)
            if icone is not None:
                self._cache.move_to_end(cle)
            return icone

    def garder_icone(self, cle: tuple[bytes, str], icone: bytes) -> None:
        """Garde l'icône ; au-delà des plafonds, la plus ancienne sort d'abord."""
        with self._verrou_cache:
            if cle in self._cache:
                return
            self._cache[cle] = icone
            self._octets += len(icone)
            while len(self._cache) > ICONES_GARDEES or self._octets > CACHE_OCTETS:
                _, sortie = self._cache.popitem(last=False)
                self._octets -= len(sortie)


class Relais(BaseHTTPRequestHandler):
    """Une connexion du client : chaque requête passe à l'application, sauf sous `/.marque/`."""

    protocol_version = "HTTP/1.1"
    # `TCP_NODELAY` : une réponse écrite en plusieurs fois part sans attendre l'accusé du client.
    disable_nagle_algorithm = True

    def setup(self) -> None:
        self.timeout = self.server.delai_inactif
        super().setup()

    def handle(self) -> None:
        try:
            super().handle()
        except (ConnectionError, _ClientParti):
            # Le client est parti, pendant une réponse ou entre deux requêtes : la connexion se
            # ferme, sans ligne. Un délai de lecture du client est pris par `handle_one_request`.
            self.close_connection = True

    def log_message(self, *args) -> None:
        """Rien : le journal de `http.server` porte la ligne de requête et l'adresse du client."""

    def parse_request(self) -> bool:
        # `_Lignes` voit les lignes brutes des en-têtes, puis `self.rfile` redevient le fichier du
        # client, intact : le corps se lit sans lui.
        lignes = _Lignes(self.rfile)
        self.rfile = lignes
        try:
            admise = super().parse_request()
        finally:
            self.rfile = lignes.fichier
            self._ligne_refusee = lignes.refusee
        if admise:
            # `http.server` réécrit une cible qui commence par `//` en `/…` (gh-87389) : le relais
            # reprend la cible brute de la ligne de requête, que `http.server` a coupée de même.
            self.path = self.requestline.split()[1]
            # Un client HTTP/1.0 n'apprendrait pas que la connexion reste ouverte : elle se ferme
            # après la réponse, même s'il demande `keep-alive`.
            if self.request_version < "HTTP/1.1":
                self.close_connection = True
        return admise

    def __getattr__(self, nom: str):
        # Toute méthode passe, et non les seules que `http.server` connaît.
        if nom.startswith("do_"):
            return self._servir
        raise AttributeError(nom)

    # --- la requête ---------------------------------------------------------------------------

    def _servir(self) -> None:
        self._repondu = False
        # La longueur que `_corps` a lue, que `_transmettre` remet seule ; `None` sans longueur.
        self._longueur_lue = None
        if self.headers.defects or self._ligne_refusee:
            # `email.feedparser` a perdu les en-têtes qui suivent une ligne mal formée,
            # `Content-Length` et `Transfer-Encoding` compris, a lu un CR nu comme une fin de
            # ligne, ou garde un repli ou un octet nul : le corps passerait pour une seconde
            # requête, ou un en-tête serait injecté. Il n'est pas lu, et la connexion se ferme.
            self._repondre(400, "en-têtes mal formés\n".encode(), fermer=True)
            return
        try:
            blocs, par_morceaux = self._corps()
            if not _cible_admise(self.path):
                self._vider(blocs)
                self._repondre(400, "cible refusée\n".encode())
            elif self._demande_upgrade():
                self._vider(blocs)
                self._repondre(501, b"upgrade non transmis\n")
            elif sous_le_chemin_reserve(self.path):
                self._vider(blocs)
                self._reserve()
            else:
                self._transmettre(blocs, par_morceaux)
        except _MalFormee:
            self.close_connection = True
            if not self._repondu:
                self._repondre(400, "corps mal cadré\n".encode(), fermer=True)

    def _corps(self):
        """Les blocs du corps de la requête, lus à la demande, et s'il vient par morceaux."""
        codages = self.headers.get_all("Transfer-Encoding")
        if codages:
            if ",".join(codages).strip().lower() != "chunked":
                raise _MalFormee
            if "Content-Length" in self.headers:
                # Un frontal qui lirait `Content-Length` verrait une autre fin de requête.
                raise _MalFormee
            return self._morceaux(), True
        longueurs = {valeur.strip() for valeur in self.headers.get_all("Content-Length") or ()}
        if len(longueurs) > 1 or not all(_LONGUEUR.match(valeur) for valeur in longueurs):
            raise _MalFormee
        self._longueur_lue = int(longueurs.pop()) if longueurs else None
        return self._longueur(self._longueur_lue or 0), False

    def _longueur(self, restant: int):
        while restant:
            bloc = self.rfile.read1(min(restant, BLOC))
            if not bloc:
                raise ConnectionAbortedError("client parti au milieu du corps")
            restant -= len(bloc)
            yield bloc

    def _morceaux(self):
        while True:
            ligne = self.rfile.readline(1024)
            trouvee = _TAILLE_MORCEAU.match(ligne)
            if not trouvee:
                if not ligne:
                    raise ConnectionAbortedError("client parti au milieu du corps")
                raise _MalFormee
            restant = int(trouvee.group(1), 16)
            if restant == 0:
                break
            yield from self._longueur(restant)
            if self.rfile.readline(3) not in (b"\r\n", b"\n"):
                raise _MalFormee
        # au plus `_CHAMPS_DE_FIN` champs de fin, puis la ligne vide
        for _ in range(_CHAMPS_DE_FIN + 1):
            ligne = self.rfile.readline(65537)
            if ligne in (b"\r\n", b"\n"):
                return
            if not ligne:
                raise ConnectionAbortedError("client parti au milieu du corps")
        raise _MalFormee

    @staticmethod
    def _vider(blocs) -> None:
        for _ in blocs:
            pass

    def _demande_upgrade(self) -> bool:
        jetons = {
            jeton.strip().lower()
            for valeur in self.headers.get_all("Connection") or ()
            for jeton in valeur.split(",")
        }
        return "upgrade" in jetons and "Upgrade" in self.headers

    def _repondre(
        self, code: int, corps: bytes, type_contenu: str = "text/plain; charset=utf-8",
        entetes: tuple[tuple[str, str], ...] = (), fermer: bool = False,
    ) -> None:
        """Une réponse du relais lui-même, avec sa longueur : la connexion d'un client HTTP/1.1
        sert encore, sauf `fermer` ; celle d'un client HTTP/1.0 se ferme après chaque réponse."""
        self.send_response(code)
        self.send_header("Content-Type", type_contenu)
        self.send_header("Content-Length", str(len(corps)))
        for nom, valeur in entetes:
            self.send_header(nom, valeur)
        if fermer:
            self.send_header("Connection", "close")
        self.end_headers()
        self._repondu = True
        if self.command != "HEAD":
            self.wfile.write(corps)

    def _injoignable(self) -> None:
        journal("application injoignable")
        self._repondre(502, b"application injoignable\n")

    # --- le chemin réservé --------------------------------------------------------------------

    def _reserve(self) -> None:
        # le chemin normalisé : `/%2Emarque/sante` est la santé ; la requête, telle qu'elle arrive
        chemin, requete = chemin_normal(self.path), self.path.partition("?")[2]
        if chemin == "/.marque/sante":
            self._repondre(200, b'{"statut":"ok"}', "application/json", _SANS_CACHE)
        elif chemin == "/.marque/marque.css":
            self._repondre(200, FEUILLE, "text/css; charset=utf-8", _SANS_CACHE)
        elif chemin == "/.marque/icone":
            self._icone(requete)
        else:
            self._repondre(404, b"inconnu sous /.marque/\n")

    def _generique(self, raison: str) -> None:
        journal(f"icône remplacée par la générique : {raison}")
        self._repondre(200, icone_generique(), "image/png", _SANS_CACHE)

    def _icone(self, requete: str) -> None:
        de = None
        for morceau in requete.split("&"):
            nom, _, valeur = morceau.partition("=")
            if nom == "de":
                de = unquote(valeur)
                break
        if de is None:
            self._generique("autre origine")
            return
        if not chemin_admis(de):
            self._generique("chemin refusé")
            return
        try:
            # Une place de lecture tient de la lecture du corps à la fin de sa recoloration : au
            # plus `LECTURES_ICONE` corps d'icône sont en mémoire à la fois. Le corps ne vit que
            # dans `_icone_lue`, et la réponse part après lui, la place rendue.
            with self.server.lectures:
                issue = self._icone_lue(de)
        except _ERREURS_AMONT:
            self._injoignable()
            return
        if issue is None:
            # L'application a coupé après ses en-têtes : la connexion se ferme, sans 502 ni ligne.
            self.close_connection = True
            return
        icone, type_ou_raison = issue
        if icone is None:
            self._generique(type_ou_raison)
            return
        self._repondre(200, icone, type_ou_raison, _SANS_CACHE)

    def _icone_lue(self, de: str) -> tuple[bytes | None, str] | None:
        """L'icône recolorée de `de` et son type, ou `None` et la raison de l'icône générique ;
        `None` si l'application coupe après ses en-têtes. Une icône déjà gardée rend sa place
        dès la lecture, sans attendre la recoloration d'une autre."""
        statut, type_contenu, codage, corps = self._lire_icone(de)
        if corps is None:
            return None
        if statut != 200:
            return None, f"réponse {statut}"
        if len(corps) > LECTURE_ICONE_MAX:
            return None, "taille"
        if codage != "identity":
            # un corps compressé n'est ni un PNG ni un SVG : enveloppé, il donnerait une icône vide
            return None, "format"
        if corps.startswith(_SIGNATURE):
            sorte = "png"
        elif (type_contenu or "").split(";")[0].strip().lower() == "image/svg+xml":
            sorte = "svg"
        else:
            return None, "format"
        if _trop_grande(sorte, corps):
            return None, "taille"
        cle = (hashlib.sha256(corps).digest(), sorte)
        icone = self.server.icone_gardee(cle)
        if icone is None:
            with self.server.recoloration:
                icone = self.server.icone_gardee(cle)
                if icone is None:
                    icone = recolorer_png(corps) if sorte == "png" else envelopper_svg(corps)
                    if icone is not None:
                        self.server.garder_icone(cle, icone)
        if icone is None:
            return None, "format"
        return icone, "image/png" if sorte == "png" else "image/svg+xml"

    def _lire_icone(self, de: str) -> tuple[int, str | None, str, bytes | None]:
        """Le statut, le type, le codage et au plus `LECTURE_ICONE_MAX + 1` octets de l'icône
        `de`, le corps `None` si l'application coupe après ses en-têtes. Une réponse informative
        de l'application est sautée, sans rien en dire au client."""
        conn = self._vers_l_application()
        try:
            conn.putrequest("GET", de, skip_host=True, skip_accept_encoding=True)
            for nom, valeur in _sans_un_saut(self.headers.items()):
                if nom.lower() not in _HORS_ICONE:
                    conn.putheader(nom, valeur)
            conn.endheaders()
            reponse = conn.getresponse()
            if reponse.status != 200:
                return reponse.status, None, "identity", b""
            try:
                corps = _lire_borne(reponse, LECTURE_ICONE_MAX + 1)
            except _ERREURS_AMONT:
                return 200, None, "identity", None
            codage = (reponse.getheader("Content-Encoding") or "identity").strip().lower()
            return 200, reponse.getheader("Content-Type"), codage, corps
        finally:
            conn.close()

    # --- la transmission ----------------------------------------------------------------------

    def _vers_l_application(self, informer=None) -> http.client.HTTPConnection:
        """Une connexion neuve vers l'application, dont les réponses informatives vont à
        `informer`, ou sont sautées."""
        conn = http.client.HTTPConnection(*self.server.amont, timeout=self.server.delai_amont)
        conn.response_class = functools.partial(_Reponse, informer=informer)
        return conn

    def _informer(self, statut: int, raison: str, entetes) -> None:
        """Une réponse informative de l'application, transmise sans corps au client HTTP/1.1."""
        self.send_response_only(statut, raison)
        for nom, valeur in _sans_un_saut(list(entetes)):
            self.send_header(nom, valeur)
        try:
            self.end_headers()
        except OSError as erreur:
            raise _ClientParti from erreur

    def _vers_l_amont(self) -> list[tuple[str, str]]:
        # `Content-Length` part toujours : `_transmettre` remet seule la longueur que `_corps` a
        # lue, et un `Connection` qui le nomme ne retire jamais le cadrage. Il ne vient jamais
        # avec `Transfer-Encoding` : `_corps` les refuse ensemble.
        retires = {"accept-encoding", "expect", "content-length"}
        if self.command in ("GET", "HEAD"):
            retires |= _CONDITIONNELS
        return [
            (nom, valeur)
            for nom, valeur in _sans_un_saut(self.headers.items())
            if nom.lower() not in retires
        ]

    @staticmethod
    def _amont_suit(fonction, *args) -> bool:
        try:
            fonction(*args)
        except _ERREURS_AMONT:
            return False
        return True

    def _transmettre(self, blocs, par_morceaux: bool) -> None:
        # Une réponse informative passe à un client HTTP/1.1, jamais à un client HTTP/1.0.
        http11 = self.request_version >= "HTTP/1.1"
        conn = self._vers_l_application(self._informer if http11 else None)
        try:
            try:
                conn.putrequest(self.command, self.path, skip_host=True, skip_accept_encoding=True)
                for nom, valeur in self._vers_l_amont():
                    conn.putheader(nom, valeur)
                if par_morceaux:
                    conn.putheader("Transfer-Encoding", "chunked")
                elif self._longueur_lue is not None:
                    conn.putheader("Content-Length", str(self._longueur_lue))
            except ValueError:
                # Une méthode que `http.client` ne sait pas envoyer : un octet de 0x00 à 0x1F, un
                # caractère non ASCII. Pour les en-têtes, la garde n'est que défensive : aucun
                # en-tête lu par `http.server` ne la déclenche, ceux qu'`email.feedparser` lit
                # mal étant refusés plus tôt.
                self._vider(blocs)
                self._repondre(400, "méthode refusée\n".encode())
                return
            # Rien ne part avant deux blocs du corps, ou sa fin : un corps mal cadré qui tient en
            # un bloc ne fait rien parvenir à l'application. La connexion s'ouvre à `endheaders`.
            blocs = iter(blocs)
            lus = list(itertools.islice(blocs, 2))
            # L'amont qui tombe ne coupe pas la lecture du client : le corps est lu en entier.
            suit = self._amont_suit(conn.endheaders)
            for bloc in itertools.chain(lus, blocs):
                if suit:
                    envoi = b"%x\r\n%s\r\n" % (len(bloc), bloc) if par_morceaux else bloc
                    suit = self._amont_suit(conn.send, envoi)
            if suit and par_morceaux:
                suit = self._amont_suit(conn.send, b"0\r\n\r\n")
            if not suit:
                self._injoignable()
                return
            try:
                reponse = conn.getresponse()
            except _ERREURS_AMONT:
                self._injoignable()
                return
            if reponse.status == 101:
                # Jamais sollicité : le relais répond 501 à toute demande d'`Upgrade`, et retire
                # `Upgrade` des autres requêtes. L'application n'a pas rendu de réponse utilisable.
                self._injoignable()
                return
            self._relayer(reponse)
        finally:
            conn.close()

    def _relayer(self, reponse: http.client.HTTPResponse) -> None:
        entetes = _sans_un_saut(reponse.getheaders())
        type_contenu = reponse.getheader("Content-Type")
        codage = (reponse.getheader("Content-Encoding") or "identity").strip().lower()
        page = est_page(type_contenu)
        marquable = (
            reponse.status == 200
            and codage == "identity"
            and (page or est_manifeste(self.path, type_contenu))
        )
        if self.command == "HEAD" or reponse.status in (204, 304) or reponse.status < 200:
            if self.command == "HEAD" and marquable:
                # le `GET` serait retouché : sa longueur ne serait pas celle-ci
                entetes = _sauf(entetes, "content-length")
            self._entetes(reponse, entetes)
        elif self.command == "GET" and marquable:
            self._marquer(reponse, entetes, page)
        else:
            self._flux(reponse, entetes)

    def _entetes(self, reponse, entetes, ajouts=()) -> None:
        # `send_response_only` : `send_response` ajouterait un second `Server` et un second `Date`.
        self.send_response_only(reponse.status, reponse.reason)
        for nom, valeur in (*entetes, *ajouts):
            self.send_header(nom, valeur)
        self.end_headers()
        self._repondu = True

    def _marquer(self, reponse, entetes, page: bool) -> None:
        try:
            corps = _lire_borne(reponse, PLAFOND_PAGE + 1)
        except _ERREURS_AMONT:
            # L'application a coupé après ses en-têtes : la connexion se ferme, sans 502 ni ligne.
            self.close_connection = True
            return
        if len(corps) > PLAFOND_PAGE:
            if page:
                journal("page trop grande, transmise sans marque")
            else:
                journal("manifeste trop grand, transmis sans marque")
            self._flux(reponse, entetes, debut=corps)
            return
        hote = self.headers.get("Host")
        if page:
            neuf = retoucher_page(corps, self.path, hote)
        else:
            neuf = retoucher_manifeste(corps, self.path, hote)
        if neuf is None:
            journal("manifeste illisible, transmis sans marque")
            neuf = corps
        else:
            # `no-cache`, sans perdre le `no-store` ni le `private` de l'application
            cache = _cache_retouche(entetes)
            entetes = [*_sauf(entetes, "etag", "last-modified", "cache-control"), cache]
        longueur = (("Content-Length", str(len(neuf))),)
        self._entetes(reponse, _sauf(entetes, "content-length"), longueur)
        self.wfile.write(neuf)

    def _flux(self, reponse, entetes, debut: bytes = b"") -> None:
        """La réponse au fil de sa lecture, avec sa longueur ou par morceaux vers un client
        HTTP/1.1. Vers un client HTTP/1.0, une réponse sans longueur finit avec la connexion."""
        connue = reponse.length is not None and not reponse.chunked
        morceaux = not connue and self.request_version >= "HTTP/1.1"
        entetes = _sauf(entetes, "content-length")
        if connue:
            ajouts = (("Content-Length", str(len(debut) + reponse.length)),)
        elif morceaux:
            ajouts = (("Transfer-Encoding", "chunked"),)
        else:
            ajouts = ()
            self.close_connection = True
        self._entetes(reponse, entetes, ajouts)
        if debut:
            self._ecrire(debut, morceaux)
        while True:
            try:
                bloc = reponse.read1(BLOC)
            except _ERREURS_AMONT:
                # Les en-têtes sont partis : la connexion se ferme, sans ligne.
                self.close_connection = True
                return
            if not bloc:
                break
            self._ecrire(bloc, morceaux)
        if reponse.length:
            # l'application a coupé avant la longueur annoncée
            self.close_connection = True
        elif morceaux:
            self.wfile.write(b"0\r\n\r\n")

    def _ecrire(self, bloc: bytes, morceaux: bool) -> None:
        self.wfile.write(b"%x\r\n%s\r\n" % (len(bloc), bloc) if morceaux else bloc)


def creer_serveur(
    hote: str, port: int, amont: str, delai_inactif: float = DELAI_INACTIF,
    delai_amont: float = DELAI_AMONT,
) -> ThreadingHTTPServer:
    """Le relais à l'écoute sur `hote`:`port`, devant l'application `amont`, `http://<hôte>:<port>`.

    `delai_inactif` ferme une connexion du client muette ; `delai_amont` borne chaque attente de
    l'application. `ValueError` si `amont` n'a pas cette forme."""
    return _Serveur((hote, port), _amont(amont), delai_inactif, delai_amont)


def main(argv: list[str] | None = None) -> int:
    """Lance le relais d'après son environnement ; `argv` n'est pas lu."""
    # Sous Windows, la sortie d'erreur d'un Python lancé par un tube est en cp1252.
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    env = os.environ.get("MARQUE_ENV")
    if env != "staging":
        etat = "MARQUE_ENV absente" if env is None else f"MARQUE_ENV={env}"
        journal(f"refus hors du staging ({etat})")
        return 64
    port = os.environ.get("MARQUE_PORT", "")
    if not _PORT.match(port) or not 1 <= int(port) <= 65535:
        journal("refus : MARQUE_PORT n'est pas un port de 1 à 65535")
        return 64
    amont = os.environ.get("MARQUE_AMONT", "")
    try:
        _amont(amont)
    except ValueError:
        journal("refus : MARQUE_AMONT n'a pas la forme http://<hôte>:<port>")
        return 64
    try:
        serveur = creer_serveur(os.environ.get("MARQUE_HOTE", HOTE_ECOUTE), int(port), amont)
    except OSError:
        journal(f"écoute impossible sur le port {int(port)}")
        return 1
    journal(f"relais du staging prêt sur le port {int(port)}")
    try:
        serveur.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())


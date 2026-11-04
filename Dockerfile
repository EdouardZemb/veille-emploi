# L'image de la console (contrat : docs/modele/decisions/M-0003 ; choix : ADR-0002, section 2).
# Pas de directive de syntaxe en première ligne : elle ferait tirer de Docker Hub, à chaque
# construction, un frontend BuildKit flottant. Ce Dockerfile n'utilise que la syntaxe intégrée.
#
# Construite par la CI (`docker build --build-arg REVISION=<sha>`, action modele-image-construire)
# et lancée comme en production (deploiement/compose.yml) : l'uid 1000, une racine en lecture
# seule, /tmp en mémoire, tout l'état dans /donnees. La version vient de l'environnement
# (VEILLE_EMPLOI_VERSION), jamais de l'image.

# python:3.13-slim (Python 3.13.18), résolue le 2026-10-28 ; empreinte de l'index
# multi-architecture. Dependabot la fait monter (.github/dependabot.yml).
FROM python:3.13-slim@sha256:2d44738ebf4ce5f63b9d9ea871e9c7cfdc0426f7b0c97cac915fd88ded1d86bb

# Les bibliothèques de WeasyPrint (Pango et HarfBuzz, dont libharfbuzz-subset0, qui découpe les
# polices des PDF), DejaVu (les lettres en PDF sont en DejaVu Serif), et la base des fuseaux : les
# heures de collecte sont celles de Paris.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b libharfbuzz-subset0 \
        fonts-dejavu-core tzdata \
    && rm -rf /var/lib/apt/lists/*

# Le dépôt, moins ce que .dockerignore écarte (les secrets, les données, les outils du poste),
# installé en mode éditable : config.RACINE vaut /app, où la console lit exemple/ (sa configuration
# par défaut) et le jeu factice du staging (factice/). La configuration personnelle vit au dépôt
# de données et n'entre pas dans l'image : la console lit /config quand il est monté et non vide.
# Le code reste à root, en lecture seule pour l'uid 1000.
# compileall : la racine est en lecture seule, Python ne pourrait pas y écrire ses .pyc.
WORKDIR /app
COPY . .
RUN pip install --no-cache-dir -e ".[pdf]" \
    && python -m compileall -q src

# /donnees, à l'uid 1000 : en CI, le volume anonyme (`-v /donnees`) en hérite ; en production,
# c'est le dossier de l'hôte qui y est monté.
RUN mkdir /donnees && chown 1000:1000 /donnees

# Les chemins de la console pointent dans /donnees. /tmp sert de HOME et de cache (WeasyPrint,
# fontconfig) : la racine est en lecture seule.
ENV VEILLE_DB=/donnees/veille.sqlite3 \
    VEILLE_DOSSIERS=/donnees/dossiers \
    VEILLE_KIT=/donnees/kit \
    VEILLE_VAPID=/donnees/vapid.json \
    TZ=Europe/Paris \
    HOME=/tmp \
    XDG_CACHE_HOME=/tmp/cache \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# La révision vient de la CI (SHA du commit) : la santé la rend, le déploiement la compare au
# label. Déclarée en dernier, pour qu'un changement de révision ne rejoue que ces couches.
ARG REVISION
ENV REVISION=$REVISION
LABEL org.opencontainers.image.revision=$REVISION \
      org.opencontainers.image.source=https://github.com/EdouardZemb/veille-emploi

USER 1000:1000
EXPOSE 8460

# `--start-interval` : pendant le démarrage, une sonde toutes les 2 s, pour que
# `docker compose up --wait` rende la main dès que la console répond. Un 503 ou une connexion
# refusée lèvent une exception : le code de sortie est 1.
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --start-interval=2s --retries=3 \
    CMD ["python", "-c", "import sys, urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8460/sante', timeout=4).status == 200 else 1)"]

# Sans ENTRYPOINT : `docker run <image> veille instantane verifier /donnees` lance la commande
# telle quelle (M-0003). `veille servir` lance uvicorn, un seul processus (le verrou du
# planificateur ne couvre que le sien), et règle le journal de `veille.*` au niveau INFO :
# `docker logs` montre les collectes et les purges, pas seulement les échecs.
CMD ["veille", "servir", "--hote", "0.0.0.0", "--port", "8460"]

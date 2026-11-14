# Image de test des scripts de déploiement (bats). Elle porte les mêmes versions d'age et de sops
# que le serveur ; elle est construite et lancée par `tests/deploiement/lancer.sh`, à l'identique
# sur le poste et en CI.

# debian:bookworm-slim, résolue le 2026-10-15 ; empreinte de l'index multi-architecture.
FROM debian:bookworm-slim@sha256:734a72b3d6142a71993b4bc580ca01d8ca687f77a2c422d96a961d3376b179bc

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        bats ca-certificates coreutils curl git jq util-linux \
    && rm -rf /var/lib/apt/lists/*

# age v1.3.2 (linux-amd64). La version ne publie pas de fichier de sommes : cette somme SHA-256 est
# le champ « digest » de l'archive dans l'API des releases de GitHub
# (gh api repos/FiloSottile/age/releases/tags/v1.3.2), la même que dans la CI du modèle.
# Archive : https://github.com/FiloSottile/age/releases/download/v1.3.2/age-v1.3.2-linux-amd64.tar.gz
RUN curl -fsSL -o /tmp/age.tar.gz \
        https://github.com/FiloSottile/age/releases/download/v1.3.2/age-v1.3.2-linux-amd64.tar.gz \
    && echo "cbe24006683f8eb669266162894b9a522a1af52f2665fbc63a4bb032ed26ac10  /tmp/age.tar.gz" \
        | sha256sum -c - \
    && tar -xzf /tmp/age.tar.gz -C /usr/local/bin --strip-components=1 age/age age/age-keygen \
    && rm /tmp/age.tar.gz

# sops v3.13.3 (linux.amd64). Somme tirée du fichier officiel de la version :
# https://github.com/getsops/sops/releases/download/v3.13.3/sops-v3.13.3.checksums.txt
RUN curl -fsSL -o /usr/local/bin/sops \
        https://github.com/getsops/sops/releases/download/v3.13.3/sops-v3.13.3.linux.amd64 \
    && echo "e5bec3346a873ae91d871550f3e698c1aad962aff462a080e40f25fde17fef6b  /usr/local/bin/sops" \
        | sha256sum -c - \
    && chmod 755 /usr/local/bin/sops

# Sans age ni sops, les tests de secrets ne doivent pas être sautés en silence : ils échouent. Il en
# va de même de tout test qui sauterait faute d'un outil ou d'un dossier du système (LE-16).
ENV VEILLE_EMPLOI_TESTS_SANS_SAUT=1

# Comme sur le serveur : un utilisateur ordinaire, uid 1000.
RUN useradd --create-home --uid 1000 --shell /bin/bash testeur
USER testeur

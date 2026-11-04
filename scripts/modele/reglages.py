"""Réglages du projet, posés au rendu du modèle."""

BRANCHE_PRINCIPALE = "principal"
# « code » : la porte de confidentialité refuse tout constat ; « donnees » : elle avertit sur ce qui identifie et refuse les secrets (M-0006).
NATURE = "code"
# Clés que la mécanique du modèle exige dans chaque `.cles`, indexées par le chemin du `.cles`.
SECRETS_EXIGES: dict[str, list[str]] = {
    "deploiement/secrets/prod.cles": ["HC_SONDE", "HC_SAUVEGARDE", "HC_TEST_RESTAURATION"],
    "deploiement/secrets/staging.cles": ["HC_SONDE"],
}

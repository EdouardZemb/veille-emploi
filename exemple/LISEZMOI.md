# L'exemple

Une configuration complète pour une personne inventée, Camille Exemple, testeuse
logiciel autour de Mulhouse (France) et de Bâle (Suisse). Le code tourne sur ce
dossier tant qu'aucune configuration n'est désignée : il sert de défaut, de
modèle et de jeu de référence aux tests.

Rien ici ne décrit une vraie personne. Les adresses sont en `.exemple.invalid`.

## Ce que contient un dossier de configuration

- `criteres.yaml` : obligatoire, avec `version: 1` à la racine ;
- `sources.yaml` : facultatif ;
- `gabarits/` : au moins `lettre.md` et `relance.md`, puis les variantes
  (`lettre_en.md`, `relance_en.md`, `lettre_<famille>[_<langue>].md`,
  `lettre_atout_<atout>[_<langue>].md`) et `.provisoire` ;
- `empreintes-kit.json` : facultatif.

## Faire sa propre configuration

1. Copier ce dossier hors du dépôt, puis le remplir.
2. Le désigner par la variable `VEILLE_CONFIG`.
3. Le contrôler : `veille config verifier <dossier>` rend 0 (sain), 2 (non sain)
   ou 64 (usage).

Sans configuration désignée, la collecte refuse : elle noterait les offres avec
cet exemple. Hors conteneur, la console le dit aussi par un bandeau, et refuse les
gestes sur une offre (dossier, relance, recalcul, affinement). Pour l'essayer sur
cet exemple, désigne-le, depuis le clone : `VEILLE_CONFIG=exemple`.

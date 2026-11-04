---
name: consigner
description: Consigner un constat (piste d'amélioration, leçon ou empêchement) dans docs/registre.md, avec le prochain numéro libre, un motif et, au 3e constat du même motif, la proposition d'une porte.
argument-hint: "[constat en une phrase]"
---

# Consigner un constat

Le constat à consigner : $ARGUMENTS

C'est une écriture dans un fichier Markdown, `docs/registre.md`. Elle ne dépend d'aucun outil du
projet. L'en-tête du tableau est :

```
| N° | Famille | Date | Constat | Motif | Prévention | Critère de sortie | État |
```

1. **Choisir la famille.** `AM` : une piste d'amélioration, « il faudrait ». `LE` : une leçon, « on
   a cru que ». `EM` : un empêchement, « on n'a pas pu ».
2. **Prendre le premier numéro libre** de cette famille (les numéros ne se réutilisent jamais, même
   ceux d'une ligne close) et **remplir toutes les colonnes**. L'origine se déduit de la branche
   courante. La date est celle du jour.
3. **Rattacher la ligne à un motif existant, ou en créer un.** Compter les lignes qui portent ce
   motif. Au 3e constat, proposer la porte qui l'empêchera (un test, un hook, une vérification de
   CI) et l'écrire dans la colonne « Prévention ».
4. **Rendre compte en une ligne** : le numéro attribué, le motif, et la porte proposée s'il y en a
   une.

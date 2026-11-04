# Décisions d'architecture (ADR)

Un fichier par décision : `NNNN-titre.md`, numéroté à partir de `0001`. Les décisions héritées du modèle sont à part, dans `docs/modele/decisions/` (préfixe `M-`), pour que leurs numéros ne se heurtent pas à ceux du projet.

**Un ADR ne se réécrit pas.** Si la décision change, un nouvel ADR remplace l'ancien : on ne modifie dans l'ancien que son statut, qui renvoie au nouveau.

## Format

Titre :

```
# ADR-NNNN — <Sujet> : <décision en une phrase>
```

En-tête :

- statut daté (proposé, accepté, remplacé par ADR-NNNN), avec la date ;
- contexte amont : l'ADR, l'issue ou le document dont celui-ci découle.

Sections, dans cet ordre :

1. **Contexte** : ce qui force à décider.
2. **Options** : les choix envisagés, avec leurs mérites et leurs défauts.
3. **Décision** : ce qui est retenu, et pourquoi.
4. **Conséquences** : ce qui change, dont une rubrique « Difficile à changer ».
5. **Révision** : quand et sur quel signe on reconsidérera la décision.

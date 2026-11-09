# Le jeu de données factice

Ce dossier contient le jeu de données du staging de la console. Tout y est inventé : la personne
(Camille Exemple), les employeurs, les offres, les adresses et les pièces du kit. Aucune donnée
réelle n'y entre, et aucune n'en est dérivée (invariant M-0001 de l'écosystème).

- `offres.yaml` : une vingtaine d'offres, qui couvrent les familles de `exemple/criteres.yaml` (au
  moins deux par famille), ses quatre zones, la Suisse en francs, un lieu absent et un lieu
  imprécis, chacun de ses éliminatoires (une offre écartée par critère) et une annonce en
  allemand, avec des scores variés, sous et au-dessus du seuil. Le staging les note avec l'exemple,
  la configuration par défaut de l'image : le jeu se lit comme l'exemple le note.
- `candidatures.yaml` : les offres auxquelles Camille a déjà répondu, ou qu'elle a retenues : une par état du
  parcours. La clé `statut` (`interessante`, `a_traiter`, `candidature_envoyee` par défaut, `entretien`) en fixe
  l'état, et `relance_due: true` rend sa relance due depuis la veille du chargement ; tout autre statut arrête le chargement.
- `kit/` : les pièces du kit, écrites en HTML. Le chargement les rend en PDF.

Toute adresse mail y finit par `@exemple.invalid`, et tout lien a un hôte en `.exemple.invalid`
(un domaine réservé, qui ne résout jamais). Le chargement ne se fait que sur une base vide :
`veille factice`, ou le démarrage de la console en `staging`.

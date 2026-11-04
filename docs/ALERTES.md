# Les alertes mail — ce que la console attend d'elles

> 👉 **La liste des recherches à créer n'est pas ici.** Elle vit dans un seul
> document, celui que tu tiens à jour pour ta recherche ; celui de l'instance
> réelle est nommé dans
> le `docs/ALERTES.md` du dépôt de données.
>
> **Un seul document fait foi.** Une liste tenue en double — ici et ailleurs —
> finit par diverger sans que personne s'en aperçoive, et c'est la mauvaise
> version qu'on suit.
>
> Ce fichier-ci ne décrit que le **contrat côté console** : ce que le scoring
> fait déjà, pour que tes alertes n'aient pas à le refaire. Les exemples sont
> ceux de la configuration d'exemple (`exemple/criteres.yaml`).

---

## Ne filtre pas deux fois

Tant que France Travail n'est pas branché, les alertes mail sont souvent le
seul canal qui couvre ton marché. Une requête trop serrée coûte des offres que
**rien ne rattrapera**.

### Ce que le scoring écarte tout seul

| Critère | Où il se règle |
|---|---|
| Les autres métiers et les conditions refusées — dans l'exemple : automatisme industriel, astreinte, week-end, horaires décalés, support de premier niveau, déplacements fréquents, relation clientèle en allemand | `eliminatoires` |
| Salaire sous le plancher — dans l'exemple, 38 000 € (France) / 85 000 CHF (Suisse) | `salaire.<pays>.plancher` |
| Poste présentiel hors des zones atteignables | `zones`, `geographie` |

### Ce qu'il signale sans écarter

| Critère | Effet, dans l'exemple |
|---|---|
| Allemand exigé | −10 points, l'offre reste visible |
| Lieu imprécis proche — « Sundgau », « Haut-Rhin » | 0 point, « demande la ville au premier contact » |
| Lieu imprécis large — « Grand Est » | −5 points |
| Lieu imprécis lointain — « France entière », « plusieurs sites » | −12 points |
| Salaire non publié | signalé |
| Employeur suisse en télétravail complet | avertissement sur le statut de frontalier |

---

## Donc : jamais de `NOT` dans une requête d'alerte

`Test automation NOT industrie` supprime aussi l'offre **de test logiciel chez
un industriel** — exactement celle qu'on veut voir. La console fait déjà la
distinction, et elle la fait sur le texte complet, pas sur trois mots
d'intitulé.

**Le tri se fait dans la console, pas dans la boîte mail.**

---

## Les zones, chiffrées

Celles de l'exemple :

| Zone | Points | Portée |
|---|---|---|
| Télétravail intégral | 18 | où que soit l'employeur |
| Proche | 28 | ~15 km — l'agglomération de Bâle, des deux côtés de la frontière |
| Trajet | 16 | ~40 km — un trajet quotidien en train ou en voiture |
| Occasionnelle | 8 | ~80 km — deux jours sur site par semaine au plus |

La liste exacte des communes est dans le `criteres.yaml` de ta configuration,
bloc `zones`.

---

## Vérifier que les alertes rentrent

```bash
cd <le clone>
./.venv/bin/veille decouvrir-expediteurs   # les expéditeurs vus dans la boîte
./.venv/bin/veille collecter               # collecte immédiate
./.venv/bin/veille etat                    # rendement par source
```

`decouvrir-expediteurs` ne lit que les en-têtes `De:` et `Objet:`, jamais le
corps des messages. Il dit quels expéditeurs manquent au `sources.yaml` de ta
configuration, prêts à coller.

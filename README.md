# veille-emploi

Console de recherche d'emploi : collecte, score explicable, candidature, pilotage. Pour une seule personne, qui la consulte au téléphone, en application web installée.

## Pourquoi

Chercher un emploi, c'est lire chaque jour des dizaines d'annonces venues de partout, pour en garder quelques-unes.
La console ingère ce que les sites envoient (API officielles, flux RSS, alertes mail), et donne à chaque offre un score dont l'explication est le calcul.
Elle prépare le dossier de candidature, rappelle les relances, et mesure ce que rapporte chaque source.
Elle ne parcourt jamais LinkedIn, ni un site qui l'interdit, et n'invente aucune prose dans une candidature ([les limites](docs/LIMITES.md)).
Le code tourne par défaut sur [`exemple/`](exemple/), une personne inventée ; une instance réelle vit dans un dépôt de données à part, privé.

L'état du projet est dans [CLAUDE.md](CLAUDE.md#état), les versions dans [les publications](https://github.com/EdouardZemb/veille-emploi/releases).

## Démarrer

```bash
python -m venv .venv
.venv/bin/pip install -e ".[dev]"      # sous Windows : .venv\Scripts\…
.venv/bin/veille servir                # la console, qui sert l'exemple
```

Pour une vraie recherche, [ce que tu dois faire, toi](docs/DEMARRAGE.md) vient d'abord : rien ne peut être collecté avant. Les autres commandes sont dans [CLAUDE.md](CLAUDE.md#commandes).

## Où lire quoi

| Document | À lire quand |
|---|---|
| [CLAUDE.md](CLAUDE.md) | avant de travailler ici |
| [Le démarrage](docs/DEMARRAGE.md) | pour brancher une instance : Gmail, France Travail, HTTPS, passkeys, PWA |
| [Le fonctionnement](docs/FONCTIONNEMENT.md) | pour la collecte, le score et les notifications |
| [Les critères](docs/CRITERES.md) | pour régler le score : intitulés, planchers, allemand, atouts |
| [Les alertes](docs/ALERTES.md) | pour écrire des alertes mail sans filtrer deux fois |
| [La candidature](docs/CANDIDATURE.md) | pour « Préparer ma candidature », du toucher sur « Je postule » au dossier prêt, et le kit |
| [Les données](docs/DONNEES.md) | pour savoir où elles vivent, les sauvegarder, les effacer |
| [L'enrichissement](docs/ENRICHISSEMENT.md) | pour lire le texte complet d'une annonce : l'étude |
| [Les limites](docs/LIMITES.md) | pour ce que la console ne fait pas, et pourquoi |
| [Les vraies annonces](docs/METHODE.md) | pour savoir pourquoi le score se teste sur de vraies annonces, tôt |
| [La méthode](docs/modele/methode.md) | pour la façon de travailler, commune aux projets nés de `modele-projet` |
| [Les pistes](docs/pistes.md) | pour ce qui est noté sans être engagé |
| [Le registre](docs/registre.md) | pour ce que les lots ont appris |
| [Les décisions](docs/decisions/) | pour ce qui a été décidé, et pourquoi |
| [L'exploitation](docs/exploitation.md) | pour mettre en service, déployer, restaurer |

## Contribuer

Projet personnel : aucune contribution n'est attendue.

## Licence

[MIT](LICENSE)

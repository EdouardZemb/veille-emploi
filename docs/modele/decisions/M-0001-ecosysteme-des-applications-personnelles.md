# M-0001 — Écosystème des applications personnelles : identité différée, silos, démonstration factice, garde-fous, partage par événements

- **Statut** : accepté le 2026-10-16
- **Contexte amont** : ADR-0010 de `creche-planner`, dont ce texte reprend les règles 2 à 5. La
  règle 1 (le référentiel de compétences, possédé par la veille emploi) est propre à la veille et
  reste là-bas :
  <https://github.com/EdouardZemb/creche-planner/blob/main/docs/adr/0010-ecosysteme-applications-personnelles.md>

## Contexte

L'ADR-0010 avoue sa propre faiblesse : il vit dans le dépôt d'une application et gouverne des
applications qui n'y sont pas. Son autorité sur elles dépend de ce qu'elles y renvoient. Le modèle
devient la maison de ces règles : chaque projet qui en naît les reçoit, avec la méthode.

Plusieurs applications personnelles coexistent, sur le même serveur, sans rien partager d'autre que
la machine. Aucune n'a besoin aujourd'hui de reconnaître une personne connue d'une autre. En
revanche, chacune doit pouvoir être montrée sans que des données réelles apparaissent, et chacune
doit tenir un niveau de qualité qui se voit.

## Décision

Les règles 1 à 4 ci-dessous reprennent les règles 2 à 5 de l'ADR-0010 ; sa règle 1, propre à la
veille, n'est que renvoyée.

Quatre règles, valables pour toute application de l'écosystème, y compris celles qui n'existent pas
encore.

### 1. L'identité est différée derrière une interface étroite

- Toute donnée appartient dès maintenant à un **identifiant de propriétaire opaque**, un UUID sans
  signification, généré localement.
- La traduction « personne authentifiée → identifiant opaque » se fait **à un seul endroit** par
  application, derrière une interface qui ne fait que cela.
- **L'adresse e-mail n'est jamais une clé.** Elle est un moyen d'authentification. Comme clé, elle
  deviendrait l'annuaire central de fait, sans contrat, et porterait une donnée personnelle dans
  chaque table.
- Le jour où deux applications doivent reconnaître la même personne, on remplace l'implémentation de
  l'interface, sans réécrire aucun schéma.

### 2. Le mode démonstration est une contrainte d'architecture

- Toute application doit pouvoir tourner **entièrement** sur un jeu de données **factice**, versionné
  avec son code.
- La démonstration partage le chemin de livraison de ce qui part en production (mêmes images, mêmes
  portes), mais **pas les données** : elle tourne dans son propre silo, sans accès à aucune base
  réelle. Un filtre posé sur des données réelles n'est qu'à un bug de la fuite ; un silo sans accès
  ne l'est pas.
- Le jeu factice est **écrit**, pas dérivé de données réelles. Aucune anonymisation de données
  réelles ne sert de source.

### 3. Les garde-fous de qualité sont la condition d'entrée

Décisions écrites en ADR, CI qui **refuse** de passer, tests du domaine avec **mutation testing**,
recherche de secrets, aucune donnée réelle dans le dépôt. La norme porte sur les **familles** de
garde-fous, pas sur l'outillage exact. Pour une application existante, elle s'applique au module
qu'on y ajoute, pas rétroactivement.

**Ajout de cet ADR, absent de l'ADR-0010 (arbitrage du 16/10) :** le modèle outille quatre de ces familles. La mutation reste au projet, avec l'outil de sa stack, dès
que le projet a une logique de domaine (voir `docs/modele/methode.md`, « Les familles de garde-fous
de l'écosystème »).

### 4. Le partage se fait par événements et par référentiel commun

Chaque application reste autonome et **propriétaire** de ses données. Elle expose ce qu'elle partage
par des événements versionnés ou des exports, jamais par un accès à sa base. Aucune application
n'écrit chez une autre.

## Conséquences

- Aucune application n'a de dépendance de démarrage vers une autre.
- Les schémas sont prêts pour une identité commune sans qu'aucune soit construite.
- **Rien n'est partagé aujourd'hui** : aucune vue transverse sur une personne. C'est le prix de
  l'identité différée.
- Maintenir un jeu de données factice a un coût permanent : chaque évolution de schéma doit le faire
  évoluer, faute de quoi la démonstration casse, et une démonstration cassée pousse à « juste montrer
  les vraies données une fois ».
- La norme de qualité ralentit le démarrage d'une nouvelle application. Pour un outil personnel,
  c'est un coût réel, accepté parce que c'est aussi ce qui se montre.
- **Difficile à changer** : l'identifiant de propriétaire opaque, une fois porté par toutes les
  données.

## Révision

Cet ADR doit être rouvert si :

- deux applications doivent reconnaître la même personne pour un besoin réel : l'implémentation
  commune de l'interface fait alors l'objet de son propre ADR ;
- une application de l'écosystème sert quelqu'un hors du foyer, ou est proposée à des tiers : la
  question se repose sous l'angle des droits des personnes.

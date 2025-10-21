# l4f-bot

Bot communautaire de LaFourmilière, pensé pour alléger la modération et offrir des outils pratiques aux membres. Ce document résume les fonctionnalités déployées à ce jour et présente les chantiers à venir pour que chacun puisse suivre l’évolution du projet.

## Sommaire

- [Fonctionnalités actuelles](#fonctionnalités-actuelles)
  - [Gestion des salons vocaux](#gestion-des-salons-vocaux)
  - [Panneau de contrôle `/panel`](#panneau-de-contrôle-panel)
  - [Rôles par réactions](#rôles-par-réactions)
  - [Statistiques de jeu](#statistiques-de-jeu)
  - [Sondages `/sondage`](#sondages-sondage)
  - [Accueil automatisé](#accueil-automatisé)
  - [Outils administrateur](#outils-administrateur)
- [Fonctionnalités à venir](#fonctionnalités-à-venir)

## Fonctionnalités actuelles

### Gestion des salons vocaux
- Création automatique d’un salon personnel lorsqu’un membre rejoint le hub vocal.
- Nettoyage des salons vides pour garder la catégorie propre.
- Attribution des permissions de gestion au propriétaire.

### Panneau de contrôle `/panel`
- Permet à l’auteur d’un salon vocal temporaire de le verrouiller/déverrouiller, d’ajuster la limite de places ou de le renommer.
- Les actions sont réalisées via des boutons persistants et sécurisés (réponses éphémères, vérification du propriétaire).

### Rôles par réactions
- Assistant interactif pour publier un message de distribution de rôles basé sur les émojis (avec pré-test des réactions).
- Gestion de la base locale pour ajouter ou retirer automatiquement les rôles lorsque les membres réagissent.

### Statistiques de jeu
- Enregistre le temps passé par jeu grâce aux activités Discord.
- Commandes slash `/top-jeux` (classement serveur) et `/stats-moi` (bilan personnel) avec affichage dans des embeds lisibles.

### Sondages `/sondage`

Le cog `Polls` ajoute une commande slash permettant de créer rapidement un sondage dans le salon de votre choix.

**Syntaxe**

```
/sondage question:"Votre question" choix1:"Option A" choix2:"Option B" [choix3:"…"] … [choix10:"…"] [timeout:Durée en minutes] [
salon:#canal]
```

**Règles et limites**

- la question est obligatoire et est tronquée à 256 caractères ;
- il faut proposer au minimum deux choix distincts et au maximum dix ;
- chaque choix est limité à 100 caractères ;
- les doublons (majuscules/minuscules ignorées) sont refusés ;
- la durée est optionnelle et peut aller jusqu’à 7 jours (10 080 minutes) ; la date de fin est affichée dans le sondage ;
- le paramètre `salon` permet aux modérateurs de publier le sondage dans un autre salon tant que le bot peut y écrire ;
- le bot ajoute automatiquement les réactions numériques 1️⃣…🔟 pour recueillir les votes.

Si aucun salon n’est fourni, la réponse slash affiche directement le sondage afin que tous les membres du salon puissent voter immédiatement. Lorsque le sondage est publié dans un autre salon, un accusé de réception éphémère contenant le lien du message est envoyé à l’auteur de la commande. En cas d’erreur (permissions manquantes, validations, etc.), un message éphémère décrit la cause afin que l’utilisateur puisse corriger la commande.

### Accueil automatisé
- Attribue automatiquement le rôle de bienvenue configuré et envoie un message d’accueil dans le salon dédié.
- Optionnellement, expédie un message privé personnalisé au nouveau membre.

### Outils administrateur
- Commande `/sync` pour resynchroniser rapidement les commandes slash du serveur (administrateurs uniquement).

## Fonctionnalités à venir

- **Sondages enrichis :** options anonymes, résultats différés et possibilité de clore/réouvrir un vote existant.
- **Améliorations du panel vocal :** transfert de propriété, presets de limites et raccourcis pour inviter des membres.
- **Tableau de bord stats :** exports hebdomadaires (CSV/embeds) et classement individuel multi-périodes.
- **Qualité de vie modération :** rappel automatique des règles à l’arrivée et commandes de purge ciblée dans les salons textuels.

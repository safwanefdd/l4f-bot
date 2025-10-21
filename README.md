# l4f-bot

## Commande `/sondage`

Le cog `Polls` ajoute une commande slash permettant de créer rapidement un sondage dans le salon courant.

**Syntaxe**

```
/sondage question:"Votre question" choix1:"Option A" choix2:"Option B" [choix3:"…"] … [choix10:"…"]
```

**Règles et limites**

- la question est obligatoire et est tronquée à 256 caractères ;
- il faut proposer au minimum deux choix distincts et au maximum dix ;
- chaque choix est limité à 100 caractères ;
- les doublons (majuscules/minuscules ignorées) sont refusés ;
- le bot ajoute automatiquement les réactions numériques 1️⃣…🔟 pour recueillir les votes.

Après publication, le bot confirme la création du sondage via un message éphemère. En cas d’erreur (permissions manquantes, validations, etc.), un message éphemère décrit la cause afin que l’utilisateur puisse corriger la commande.

# l4f-bot

## Commande `/sondage`

Le cog `Polls` ajoute une commande slash permettant de créer rapidement un sondage dans le salon de votre choix.

**Syntaxe**

```
/sondage question:"Votre question" choix1:"Option A" choix2:"Option B" [choix3:"…"] … [choix10:"…"] [timeout:Durée en minutes] [salon:#canal]
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

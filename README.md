# l4f-bot

## Commande `/sondage`

Le cog `Polls` ajoute une commande slash permettant de créer rapidement un sondage dans le salon de votre choix.

**Syntaxe**

```
/sondage question:"Votre question" choix1:"Option A" choix2:"Option B" [choix3:"…"] … [choix10:"…"] [setTimeOut:Durée en minutes] [salon:#canal]
```

**Règles et limites**

- la question est obligatoire et est tronquée à 256 caractères ;
- il faut proposer au minimum deux choix distincts et au maximum dix ;
- chaque choix est limité à 100 caractères ;
- les doublons (majuscules/minuscules ignorées) sont refusés ;
- la durée (`setTimeOut`) est optionnelle et peut aller jusqu’à 7 jours (10 080 minutes) ; la date de fin est affichée dans le sondage ;
- le paramètre `salon` permet aux modérateurs de publier le sondage dans un autre salon tant que le bot peut y écrire ;
- le message contient une embed claire listant les choix numérotés et le bot ajoute automatiquement les réactions 1️⃣ à 🔟 pour les votes.

Le sondage est envoyé dans le salon choisi sous la forme d’un embed lisible (« 📊 Nouveau sondage ») qui rappelle la question, détaille chaque choix et affiche la date limite si `setTimeOut` est renseigné. Les participants votent simplement en réagissant avec l’emoji correspondant. L’auteur reçoit systématiquement un accusé de réception éphémère indiquant le salon, la durée configurée (`setTimeOut`) et un lien direct vers le message. En cas d’erreur (permissions manquantes, validations, etc.), un message éphémère décrit la cause afin que l’utilisateur puisse corriger la commande.

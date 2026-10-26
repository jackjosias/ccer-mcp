# CCER — Politique de conservation des médias temporaires

**But :** garantir qu'une succession de centaines de projets longs ne provoque
pas une croissance illimitée des preuves JPEG sur le poste Ubuntu, tout en
préservant les médias de l'utilisateur et la sécurité des gestes Concat.

## Trois catégories, à ne jamais confondre

1. **Médias utilisateur permanents :** vidéo source importée dans Concat,
   fichiers audio originaux, projet Concat, fichier exporté final validé.
   **Jamais supprimés automatiquement.**
2. **Échantillons d'analyse :** `ccer.timecoded_review` utilise
   `ffmpeg -f image2pipe pipe:1`; les JPEG sont des octets en mémoire,
   transmis au MCP puis relâchés, pas des fichiers JPEG créés par image.
   Le résultat envoyé à ChatGPT est hors du contrôle de suppression local ;
   le nettoyage Ubuntu ne garantit donc pas la suppression des données
   potentiellement conservées par le fournisseur.
3. **Preuves de bureau générées par l'ancienne commande visible :**
   `.runtime/ccer-desktop-evidence/before-<12hex>.jpg/json` et
   `after-<12hex>.jpg`. Ces preuves restent locales et sont la seule
   cible du nettoyage ajouté.

## Mécanisme actuellement implémenté

- Fichier `ccer/evidence_retention.py` : répertoire propriétaire uniquement
  (0700), refus de symlinks, contrôle des noms et de l'UID, TTL **30 minutes**,
  quota **32 MiB** et refus de toute croissance non maîtrisée.
- `ccer.visible_desktop._write_image` réserve la place et purge les anciennes
  preuves expirées à chaque nouvelle capture ; image créée en 0600 sans
  phase temporaire publiquement accessible.
- Les reçus d'action sont aussi créés en 0600. Une preuve d'action encore
  active **ne peut pas être nettoyée par simple acquittement**.
- Une revue explicitement confirmée peut effacer **un seul** groupe de
  preuves par identifiant ; sans confirmation, refus :
  ```bash
  python3 -m ccer.visible_desktop cleanup \
    --receipt abcdef012345 --confirmed-reviewed
  ```
  Ne déclencher cette commande qu'**après vérification** du geste, jamais
  si son résultat est UNKNOWN.
- Purger seulement les anciennes preuves expirées :
  ```bash
  python3 -m ccer.visible_desktop cleanup
  ```
- Cette purge n'explore jamais les dossiers `Videos`, `Movies`, les projets
  Concat, ni les autres dossiers de `.runtime`. Tout fichier ne correspondant
  pas strictement à un nom CCER reconnu est ignoré.

## Limitations non résolues

- Le TTL des JPEG est opportuniste lors des captures, mais un timer systemd utilisateur `ccer-scratch-gc.timer` appelle aussi la purge une fois par jour, même sans nouvelles captures. La suppression peut donc survenir après les 30 minutes nominales, selon la prochaine activation du timer. Les anciennes captures ne possèdent pas encore d'identifiant fiable de projet Concat.
- Les gestes via le MCP natif ne créent pas automatiquement ces JPEG locaux :
  ils retournent les images au client MCP, où leur rétention ne peut pas être
  commandée par le fichier local.
- Les clips intermédiaires du rendu `director_render` utilisent maintenant `ccer.temp_lifecycle` : propriétaire et projet identifiés, suppression à la fin du job et récupération après crash. Les caches internes et sauvegardes natives de Concat, ainsi que les vieux fichiers de test `.runtime/ccer-smoke`, restent volontairement exclus de cette purge.
- Une confirmation de fin de projet devra maintenir le **projet, les médias
  sources et les exports finaux** dans des répertoires permanents distincts.
  Ne pas remplacer cette étape par une purge récursive d'un chemin ambigu.

## Contrat de sécurité

Aucune suppression récursive ; suppression strictement limitée à des JPEG
et JSON reconnus, possédés par l'utilisateur, situés dans le dossier
de preuves dédié. Une preuve nécessaire à une décision ou à un geste
non encore confirmé doit être préservée jusqu'à réconciliation explicite.

# CCER — Observation audiovisuelle horodatée (lecture seule)

## Objectif

Le nouveau tool MCP **`ccer_timecoded_review`** transmet à ChatGPT
jusqu'à huit véritables images JPEG extraites d'une vidéo, avec le timecode
de chacune. Il ne lance aucune fenêtre, ne crée aucun montage et ne
manipule ni la souris X11 ni l'interface Concat.

L'objectif est de permettre à un assistant capable d'interpréter les images
de repérer visuellement, par exemple, une erreur de cadrage ou une transition
mal placée à **un instant vérifiable**, avant toute suggestion d'édition.

## Entrées

```json
{
  "file": "/home/your-user/Videos/CCER/exemple.mp4",
  "startSeconds": 0,
  "seconds": 30,
  "frameCount": 6
}
```

- Seuls les fichiers à l'intérieur de **CCER_ROOT** sont acceptés, par
  `Production.path(..., must_exist=True)`.
- `startSeconds` : 0 à 86400 ; `seconds` : 0.5 à 120 ;
  `frameCount` : 1 à 8.
- Le tool transmet des images MCP typées `image/jpeg`, associées à
  `timeSeconds`. Les données JPEG brutes ne sont pas recopiées dans le JSON
  de métadonnées ni dans les journaux.
- Chaque image est limitée à 350 Ko et ramenée à 480 pixels de large,
  sous réserve de la disponibilité de FFmpeg/FFprobe.
- Le calcul réutilise `quality.visual_scan`,
  `shot_intelligence.scene_cuts`, `visual_edit.color_report` et
  `rhythm.silence_map`. Aucune analyse de découpage n'est lancée par une
  seconde implémentation concurrente.
- Les fichiers source ne sont pas modifiés.

## Contrat d'interprétation

Une **détection technique** n'est pas une preuve de mauvais montage :
un noir peut être voulu, un plan fixe peut être artistique et un silence peut
être dramatique. Les intervalles détectés doivent être revus par l'agent ou
l'humain avant toute correction. Aucun score de beauté ou qualité esthétique
« certifiée » n'est fabriqué.

Cette version fournit de vrais échantillons visuels, pas encore le visionnage
continu de toutes les images à la cadence source ; elle ne transcrit pas la
parole et ne prétend pas reconnaître les objets/personnes sans examen
visuel des images retournées.

## Contrôle de fonctionnement hors plugin

Une commande locale **en lecture seule** permet de vérifier le décodage et
le rapport technique, sans déverser les JPEG en base64 dans le terminal :

```bash
cd /home/your-user/WORKSPACE-LOGICIEL/concat/ccer-mcp
python3 -m ccer.timecoded_review \
  --file "$HOME/Videos/CCER/ccer-review-validation-20261026.mp4" \
  --seconds 2.5 --frames 4
```

Les métadonnées affichent les timecodes et tailles JPEG. Les images sont
transmises lors de l'invocation de `ccer_timecoded_review` par le MCP.

## Intégration et certification

- `ccer/production.py` : schéma borné et routage via CCER_ROOT.
- `ccer/server.py` : images MCP séparées des métadonnées.
- `ccer/direct_gateway.py` : outil accessible en mode lecture seule.
- `tests/test_timecoded_review.py` : décodage FFmpeg réel, protection des
  chemins, validation des limites, livraison d'images MIME correctes.
- `tests/test_ccer.py` : catalogue mis à jour.
- La liste des outils exposés par ChatGPT peut nécessiter le rafraîchissement
  de la session/connecteur après un changement du schéma MCP. Vérifier
  l'apparition effective de l'action dans le catalogue avant de prétendre
  qu'elle est directement utilisable dans cette session.

### Itération éditoriale sûre

1. Lire les images et timecodes de l'export ou du média autorisé.
2. Rédiger une hypothèse de problème ancrée dans les images observées.
3. Vérifier les séquences voisines avec une fenêtre `startSeconds` plus étroite.
4. Proposer un geste Concat **avec confirmation**.
5. Contrôler l'image AVANT et APRÈS le geste via `ccer_desktop_capture`.
6. Exporter dans Concat par son interface et vérifier le MP4 final.

Ne jamais utiliser l'analyse hors écran pour appliquer une mutation
invisible au projet : la règle GUI-FIRST reste permanente.

## Parcours paginé des vidéos longues

Le nouvel outil de lecture seule `ccer_long_review_plan` reçoit
`file`, `windowSeconds` (0,5 à 120), `frameCount` (1 à 8),
`cursor` (entier positif, défaut 0) et `pageSize` (1 à 24).
Il lit la durée avec FFprobe et renvoie les fenêtres ordonnées avec
des `reviewArguments` directement utilisables par l'outil existant
`ccer_timecoded_review`.

Exemple : vidéo de 30 minutes et fenêtres de 30 secondes => 60
fenêtres. `pageSize:12` renvoie les douze premières,
`nextCursor:12` permet de reprendre le même parcours plus tard.
Le planificateur n'extrait aucun JPEG. Chaque revue ultérieure
transmet au plus huit JPEG réels décodés en mémoire, avec leurs
timecodes. Une fenêtre planifiée ne signifie pas qu'elle a été visionnée.
Le parcours est borné aux vidéos de 24 heures au maximum.

Aucune transcription ou compréhension sémantique n'est inventée.
Les sources et les exports ne sont jamais effacés. La fonction n'a
aucune capacité d'effacement des images déjà transmises aux services
ChatGPT : une suppression du cloud ne doit jamais être promise.

## Revue de remarques éditoriales horodatées

`ccer_editorial_note_review` accepte `file`, `timeSeconds`,
`note` (1 à 1 200 caractères), `contextSeconds` (0,5 à 60)
et `frameCount` (1 à 8). Exemple :
`{"file":".../source.mp4","timeSeconds":83,"note":"À 01:23, le cadrage est mauvais","contextSeconds":8}`.

L'outil réutilise FFmpeg et `ccer_timecoded_review`. Il extrait en
mémoire des JPEG réels, dont un exactement au timecode donné, et
conserve le contexte avant/après. Il ne crée pas de collection JPEG
locale et ne persiste pas l'annotation. La note porte les marqueurs
`provenance:user_supplied` et `verified:false` : CCER ne prétend
pas comprendre automatiquement le jugement éditorial.

Toute correction reste soumise à une confirmation explicite et
aux captures AVANT/APRÈS des gestes dans Concat Desktop.
Ce module ne peut pas effacer les images déjà transmises côté cloud.

## Sous-titres et preuve audio horodatée

`ccer_timed_caption_context` prend une liste de sous-titres fournis (1 à 2000 cues `start`/`duration`/`text`), un fichier média dans le dossier autorisé, `startSeconds`, `seconds` (0,5 à 120), `maxCues` (1 à 100) et `includeAudioSilence` (booléen). Les timecodes absolus sont conservés et la validation des chevauchements réutilise `captions_check`. Les silences de la plage viennent du `silence_map` FFmpeg existant. Une fenêtre trop dense est refusée sans troncature silencieuse.

L’outil est en lecture seule. Il ne reconnaît pas la parole, n’effectue pas d’alignement forcé mot à mot, n’installe aucun modèle et ne crée aucune image ou cache audio local.

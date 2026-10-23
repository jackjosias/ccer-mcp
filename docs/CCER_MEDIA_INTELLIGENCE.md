# CCER Media Intelligence — catalogues éditoriaux

## Capacités implémentées

CCER indexe des rushes fournis par l'éditeur avec descriptions et mots-clés
rédigés par des humains. Le moteur réutilise FFprobe, la détection de scènes
FFmpeg existante, le storyboard CCER et le rendu déjà certifié.

Quatre outils MCP complémentaires :
- ccer_media_index : génère un catalogue JSON nouveau, avec description,
  tags, note de licence et option de segmentation FFmpeg.
- ccer_media_search : recherche textuelle sans accents dans les annotations,
  classée par pertinence pondérée. Ne déduit pas les objets des pixels.
- ccer_media_match : associe les scènes d'un scénario aux prises annotées ;
  renvoie les scènes sans correspondance, sans inventer de plan.
- ccer_media_match_render : demande confirm=true puis réutilise le moteur
  de rendu dirigé et la validation des exports MP4. Ne modifie pas le projet
  actuellement affiché dans Concat.

Catalogue : les tailles et dates de modification des rushes sont mémorisées.
Si un rush change, CCER exige de reconstruire le catalogue.
Ce contrôle ne constitue ni une empreinte cryptographique ni une authentification
des droits, ni une vérification des annotations fournies.

## Workflow concret

1. Placer les rushes autorisés sous ~/Videos/CCER/media/.
2. Appeler ccer_media_index avec des objets file, description, tags et
   éventuellement licenseNote, plus un output JSON inédit sous CCER_ROOT.
3. Appeler ccer_media_search (catalog, text) pour inspecter les correspondances.
4. Préparer un plan avec ccer_creative_plan (script et scènes fournis).
5. Appeler ccer_media_match (catalog, plan), examiner les clips, mediaStart
   et le score lexical, puis corriger les manques et annotations.
6. Appeler ccer_media_match_render avec confirm=true et un output MP4 neuf.
7. Vérifier ccer_visual_scan, ccer_color_report et effectuer la revue humaine.

La sélection utilise la recherche de tokens exacts normalisés. Aucun modèle
d'embeddings ni de reconnaissance sémantique automatique n'est installé.

## Source timecode

Le rendu existant accepte mediaStart sur chaque scène vidéo : il se positionne
au timecode demandé et vérifie que la durée du plan tient dans le rush.
Les vidéos sans mediaStart conservent leur ancienne boucle si elles sont courtes.
Les images fixes ne nécessitent pas de timecode.

## Tests reproductibles

Depuis le workspace VS Code :

    python3 -m unittest discover -s tests -v
    python3 -m tests.live_gateway_wire
    python3 -m tests.live_media_catalog

Le test réel crée des clips synthétiques rouges et bleus, les annote,
les sélectionne dans un scénario de deux plans, rend le MP4, puis inspecte
les pixels pour vérifier rouge puis bleu. Il vérifie aussi le positionnement
dans la portion bleue d'un rush rouge+bleu. Ce test ne démontre pas une
compréhension visuelle généralisée.

## Hors périmètre actuel

Reconnaissance automatique des objets et actions, embeddings multilingues,
transcription ou diarisation, vérification des licences, esthétique autonome,
multicaméra, continuité sémantique et parité complète avec CapCut/Shotcut.
Ces fonctions requièrent des moteurs et tests dédiés.

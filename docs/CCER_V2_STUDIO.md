# CCER V2 Studio — production créative locale

## État réel validé (Ubuntu, 23 octobre 2026)

- Concat Desktop 0.2.8, mode MCP `window`
- 42 outils natifs + 40 outils CCER = **82 outils MCP**
- FFmpeg / FFprobe présents, FFmpeg `flite` utilisable pour voix **anglaise**
- Pipeline testé : brief → scénario fourni → storyboard → voix anglaise → scènes vidéo → sous-titres → MP4 → FFprobe et visual scan
- 32 tests unitaires et qualification de l'export visuel réel et du catalogue Media Intelligence lors du palier V4
- Aucune modification directe du projet actuellement affiché à l'écran dans Concat 0.2.8

## Les outils principaux

`ccer_creative_plan` : répartit un scénario fourni en scènes minutées.
`ccer_storyboard` : plan des prises, composition, intentions visuelles.
`ccer_shot_inspect`, `ccer_scene_detect`, `ccer_contact_sheet` : exploration technique des rushes.
`ccer_voice_flite` : synthèse WAV anglaise locale sans téléchargement.
`ccer_audio_mix` : atténuation de la musique sous la voix et mesure de loudness.
`ccer_subtitles_write` et `ccer_caption_validate` : préparation et contrôle SRT.
`ccer_directed_render` : assemblage de plans avec durées fixées, audio et sous-titres.
`ccer_studio_produce` : orchestre les modules précédents dans un projet isolé, avec rapport JSON.
`ccer_export_verify`, `ccer_visual_scan` : contrôle technique du fichier réel.
`ccer_silence_map`, `ccer_beat_candidates` : détection des silences et transitoires musicales.
`ccer_cut_plan` : propositions de coupes, sans modification automatique du projet.
`ccer_caption_timing_hint` : estimation temporelle des phrases, sans reconnaissance vocale.
`ccer_color_report` : mesure YUV échantillonnée, sans prétention d'étalonnage automatique.
`ccer_reframe_export` : recadrage cover ou contain, positionnement du point focal.
`ccer_transition_export` : fondu, glissement ou balayage de deux plans, avec bande-son externe facultative.
`ccer_media_index`, `ccer_media_search`, `ccer_media_match`, `ccer_media_match_render` : catalogues annotés et sélection de rushes pour scénarios. Guide : docs/CCER_MEDIA_INTELLIGENCE.md.

## Exemples de cas d'usage professionnels

| Usage | Capacités activables maintenant | À développer pour une autonomie complète |
|---|---|---|
| YouTube Shorts / TikTok / Reels | Format vertical, voix enregistrée, SRT, cuts, export | Sélection visuelle intelligente, sous-titres mot à mot |
| Tutoriels | Storyboard, scènes chronométrées, narration et mixage | Capture d'écran programmée, callouts contextuels |
| Documentaires | Assemblage multi-sources, plan éditorial, son | Recherche documentaire et vérification des faits |
| Podcasts vidéo | Tracks Concat, normalisation audio et MP4 | Détection des intervenants et multicam automatique |
| Publicité / marque | Titres, effets Concat, versions 9:16/16:9/1:1 | Brand kits, motion design avancé automatique |
| Interviews | Coupures Concat, sous-titres, traitement sonore | Diarisation, multicam, suppression intelligente des hésitations |
| Clips musicaux | Timeline, keyframes, détection de pulsations et montage dirigé sur les coupes | Beat tracking robuste en musique réelle, esthétique et transitions synchronisées |
| Vidéos e-commerce | Templates natifs, textes, exports | Détourage/reframing IA et catalogue produit intégré |
| Films créatifs | Keyframes et composition contrôlée | Étalonnage avancé et direction photo automatisée |
| Éditions en lot | Recettes, checkpoints, audits et variantes de ratio | Rendu distribué et reprise transactionnelle multi-machine |

Ces catégories ne signifient pas que chaque option de CapCut ou Shotcut est reproduite.

## Exemple : production studio MCP avec voix anglaise

```json
{
  "name": "Demo-English-01",
  "brief": {
    "topic": "CCER video editing",
    "language": "en",
    "profile": "shorts",
    "durationSeconds": 12,
    "script": "Hello from CCER. Here is an automated studio demonstration.",
    "assets": [
      "/home/your-user/Videos/CCER/media/clip1.mp4",
      "/home/your-user/Videos/CCER/media/clip2.mp4"
    ]
  },
  "generateEnglishVoice": true,
  "burnCaptions": true
}
```

Appeler `ccer_studio_produce` avec ces arguments après avoir placé les deux médias réels dans le dossier autorisé. Le nom du projet doit être inédit.

### Pour une voix française

Utiliser `narrationFile` avec un WAV/M4A/MP3 français déjà enregistré et **désactiver** `generateEnglishVoice`. Le moteur `flite` disponible n'offre pas une voix française naturelle et n'effectue aucun alignement temporel mot à mot.

## Tests reproductibles

Depuis le workspace ouvert dans VS Code :

```bash
python3 -m compileall -q ccer tests
python3 -m unittest discover -s tests -v
python3 -m tests.live_gateway_wire
python3 -m tests.live_studio
python3 -m tests.live_director
python3 -m tests.live_v2_studio
python3 -m tests.live_rhythm
python3 -m tests.live_visual
python3 -m tests.live_media_catalog
```

Tous les tests `live_*` réalisent des opérations réelles : le serveur Concat doit rester ouvert avec l'automatisation activée. Ils créent des fichiers uniques sous `~/Videos/CCER`; ils ne doivent jamais être exécutés sur des projets de production non sauvegardés.

## Contrats de qualité et limites

1. Ne pas inventer de sources vidéo ou de faits : tous les rushes doivent être fournis et autorisés.
2. Ne jamais écraser un livrable existant. Une reprise après erreur doit examiner l'état enregistré.
3. Un MP4 valide techniquement n'est pas nécessairement excellent artistiquement.
4. Les temps des sous-titres sont estimés par le plan, **pas alignés à la waveform**.
5. Les exports en 4K longue durée devront être qualifiés séparément sur le matériel utilisateur.
6. Le contrôle visuel de Concat Desktop en direct demeure une évolution amont.
7. Le disque Ubuntu ne disposait que d'environ 23 Go libres au dernier préflight ; éviter les gros modèles et caches sans analyse préalable.
8. La licence AGPL de Concat continue de s'appliquer selon les utilisations du code amont.

## Prochain palier technique

Transcription et alignement français mot à mot, vraie classification sémantique des plans, synchronisation musicale robuste sur de vraies productions, détection et correction de cadrage, QA colorimétrique, agent autonome avec validation de décisions créatives et support multicam. **Non encore certifiés comme implémentés.**

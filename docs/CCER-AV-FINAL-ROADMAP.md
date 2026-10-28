# CCER — Feuille de route finale audiovisuelle (28 octobre 2026)

## Objectif
Voir, écouter, comprendre, monter sur le véritable Concat Desktop, vérifier chaque export.

## Règles non négociables
- GUI-FIRST : les gestes de montage restent visibles dans Concat sur le bureau humain.
- Les outils FFmpeg en lecture seule peuvent extraire des images en mémoire.
- Jamais de transcription inventée : distinguer un SRT fourni et un ASR exécuté.
- Réutiliser timecoded_review, rhythm, quality, Concat Whisper et l'export SRT.
- Tous fichiers sous la racine autorisée CCER_ROOT, sans destruction des médias.
- Buffers bornés et nettoyage ; aucune capture permanente inutile.

## Phases et critères d'acceptation
1. Fondation native CCER/Concat — PASS précédent : véritable GUI et MP4 1080p.
2. Vidéo horodatée — EXISTANT : fenêtres paginées, JPEG, scènes/noirs/silences.
3. Sous-titres et image/audio — EN RECETTE : lecture SRT fiable, images réelles
   synchronisées avec chaque phrase et métriques audio. Nouveaux outils
   ccer_transcript_read et ccer_av_timeline, lecture seule.
4. Écoute réelle Whisper — À TESTER : ouvrir une vidéo parlée dans Concat,
   exécuter la transcription native, exporter SRT via l'interface,
   comparer les paroles à l'audio, importer le SRT dans CCER.
   Réutiliser le modèle small existant, sans téléchargement en double.
5. Analyse sémantique — À QUALIFIER : VLM local ou OpenVision adapté aux
   limites RAM/CPU ; compréhension des sons non vocaux (Whisper ne suffit pas).
6. Quasi temps réel — À CONSTRUIRE : flux d'événements horodatés, frames
   adaptatives, segments audio, backpressure, latence et reprises mesurées.
7. Réalisation professionnelle — À VALIDER : vrai rush parlé de plusieurs
   minutes, coupes, titres, transitions, mix audio, sous-titres et MP4 décodé.
8. Recette finale — tests Python/Rust, contrôle des deux dépôts, sécurité,
   retention, QA audio/vidéo, aucun montage invisible.

Ne jamais prétendre que les phases 4 à 8 sont validées sur une vidéo muette de 2 s.

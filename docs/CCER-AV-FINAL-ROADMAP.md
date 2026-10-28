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
3. Sous-titres et image/audio — VALIDÉ AU NIVEAU MCP LOCAL : lecture SRT,
   véritables images et courts segments audio PCM/WAV synchronisés, sans création
   de fichiers intermédiaires. Outils ccer_transcript_read, ccer_av_timeline
   (includeAudio explicite) et ccer_audio_window (0,25 à 10 s). La capacité du
   client ChatGPT à percevoir sémantiquement les blocs audio MCP reste à certifier.
4. Écoute réelle Whisper — TRANSCRIPTION NATIVE OBSERVÉE, RECETTE PARTIELLE :
   Concat PID 101086, projet `Untitled project 8`, média parlé de test
   `ccer-whisper-spoken-test-20261028.mp4` (5,705 s). Le modèle existant
   Small Multilingual a généré un titre persistant de 0,900 à 6,500 s,
   visible dans Concat et confirmé dans `concat.json` ; zéro second modèle.
   `ccer.project_caption_audit` valide par FFprobe la couverture temporelle
   sans écrire de média. Avertissement `caption_layout` : phrase trop longue.
   **Export SRT GUI NON CERTIFIÉ** : boîte `xdg-desktop-portal-gtk` ouverte
   `Exporter en SRT…`, nom `Untitled project 8.srt` prérempli, aucun fichier
   SRT encore créé/vérifié. Aucun clic X11 physique ni action aveugle.
   Comparaison parole/audio et ingestion du SRT par CCER encore ouvertes.
5. Analyse sémantique — À QUALIFIER : VLM local ou OpenVision adapté aux
   limites RAM/CPU ; compréhension des sons non vocaux (Whisper ne suffit pas).
6. Quasi temps réel — SOCLE HORODATÉ TESTÉ : ccer_av_events agrège les
   observations vidéo/audio et les sous-titres externes sous forme de pages
   de 1 à 100 événements, avec curseur de reprise et sans cache JPEG local.
   La diffusion en direct, la latence mesurée, les images adaptatives et la
   backpressure entre processus restent À CONSTRUIRE.
7. Réalisation professionnelle — À VALIDER : vrai rush parlé de plusieurs
   minutes, coupes, titres, transitions, mix audio, sous-titres et MP4 décodé.
8. Recette finale — Python 193/193 PASS (28 oct. 2026), git-diff-check
   PASS, zéro erreur IDE. Rust natif, SRT final, montage parlé professionnel,
   sécurité des deux dépôts et QA finale encore à valider.

Ne jamais prétendre que les phases 4 à 8 sont validées sur une vidéo muette de 2 s.

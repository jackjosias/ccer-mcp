# CCER — Relecture audiovisuelle progressive (28 octobre 2026)

La nouvelle commande de lecture seule `ccer_av_replay_poll` réutilise
`ccer.av_event_cursor.inspect_event_window`, `ccer.timecoded_review`,
`ccer.av_timeline` et le garde de chemins `controls.inside`.

## Contrat MCP
Le consommateur appelle `ccer_av_replay_poll` avec `file`, `cursor`
(initialement zéro), `windowSeconds` (0,5 à 10 secondes),
`frameCount` (1 à 4), `maxEvents` (1 à 100) et éventuellement
`transcriptFile`/`timelineOffsetSeconds`. Chaque appel retourne au
maximum une fenêtre, des événements horodatés, `nextCursor`, la durée,
les informations de pression locale et des indicateurs de provenance.

Si `consumerReady=false`, aucun décodeur n'est appelé, `paused=true`,
la liste des événements est vide et le curseur est conservé. Sur pression
CPU/RAM critique, une seule image est décodée au maximum, contre 2
en mode contraint et 4 en mode normal. Si `maxEvents` serait dépassé,
l'opération refuse plutôt que perdre silencieusement des événements.
`observationLatencyMs`, `windowDurationSeconds` et
`processingRealTimeFactor` mesurent désormais chaque analyse de fenêtre
sur une horloge monotone. Ces métriques excluent la latence réseau,
l'attente du consommateur et toute notion de diffusion live.

L'implémentation ne crée pas de fichier JPG, de base de données de frames,
de boucle de traitement persistante ni de second Concat.
`mode=recorded_pull_replay`, `liveStreamActive=false`,
`continuousPlaybackPerformed=false` et
`semanticUnderstandingPerformed=false` sont vérifiés :
**ce n'est ni un flux en direct ni un modèle de compréhension visuelle**.

## Preuves
Les tests couvrent curseur terminal, pression critique, backpressure,
chemins non autorisés, paramètres invalides, absence de troncature et un
véritable MP4 de 3 secondes MPEG-4/AAC interrogé via le DirectGateway.
Exécuter `python3 -m unittest tests.test_av_replay_poll -v`.
Les tests n'écrivent aucune image JPEG permanente.

## Images visuelles dans la même fenêtre
Avec `includeFrames=true`, les JPEG déjà décodés pour les événements sont
transmis en blocs image MCP. Aucun nouveau passage FFmpeg ni fichier JPEG
ne sont créés ; les métadonnées JSON ne contiennent jamais leur base64.
Par défaut `includeFrames=false` conserve le mode événementiel léger.
Les limites de 1 à 4 images et la pause par `consumerReady=false`
continuent de protéger le PC. Un véritable MP4 MPEG-4/AAC a servi de recette
pour vérifier les octets JPEG et la transmission MCP.

## Vision sans modèle supplémentaire
Les images horodatées sont extraites en mémoire avec FFmpeg et transmises
via ccer_timecoded_review. ChatGPT peut inspecter ces images reçues, tandis
que ccer_desktop_capture permet d'observer les changements dans Concat.
Les scènes, couleurs et silences sont des indices techniques, pas des
identifications sémantiques automatiques. Aucun adaptateur Qwen/Ollama
n'est requis ou exposé par CCER.

## Travail restant
Enchaîner ces fenêtres automatiquement avec cadence/latence mesurées
et contrôle d'acquittement interprocessus, inspecter dans ChatGPT les images MCP reçues et utiliser le son/Whisper
existants sans autre modèle local, puis réaliser dans le Concat GUI un montage
parlé de plusieurs minutes avec vérification MP4 et audit Rust.

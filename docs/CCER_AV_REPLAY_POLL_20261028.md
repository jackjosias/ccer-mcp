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

## Choix de backend sémantique
Le dépôt officiel Qwen3-VL (https://github.com/QwenLM/Qwen3-VL)
décrit une entrée vidéo constituée d'images horodatées. Mage-VL MCP
(https://github.com/WeiyePlayer/mage-vl-mcp) utilise un modèle local
mais documente un GPU NVIDIA de 8 Gio. Aucun de ces deux modèles
n'a été installé ou exécuté dans CCER. Sur ce poste Intel, la
qualification sémantique exige d'abord un backend réellement disponible,
une mesure mémoire et un test qualitatif sur des scènes et sons réels.

## Travail restant
Enchaîner ces fenêtres automatiquement avec cadence/latence mesurées
et contrôle d'acquittement interprocessus, raccorder un backend de vision
et d'identification des sons, puis réaliser dans le Concat GUI un montage
parlé de plusieurs minutes avec vérification MP4 et audit Rust.

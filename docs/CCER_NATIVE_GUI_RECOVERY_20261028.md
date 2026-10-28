# CCER — Recette native visuelle du 28 octobre 2026

## Preuves validées

Concat PID 101086, fenêtre X11 0x04400005 en 1400 × 900 sur DISPLAY :1.
La capture native Slint authentifiée a retrouvé son fonctionnement après
un timeout intermittent. Trois clics vrais, envoyés **dans Slint** et
confirmés BEFORE/AFTER, ont réussi : onglet Stickers, déplacement de la
tête de lecture vers 00:00:03:04, retour à l'onglet Texte. Captures de
contrôle indépendantes en lecture seule sur exactement la même fenêtre
via l'outil préexistant `ccer.readonly_window`. Jamais de souris X11
physique ni de deuxième Concat.

Le nouvel état `desktop_gui.status` annonce `inputReady=false` et
`safeForClickReceipt=false` en cas de timeout Slint, après attestation
du secours X11 strictement en lecture seule. Une erreur de credential
refuse toujours ce secours. 28 tests ciblés PASS.

Le moteur Rust `concat-core` a réussi 60 tests et 2 doctests,
`cargo fmt --check` PASS. Rust Concat GUI complet non certifié.

## Anomalie non résolue : preview noir

L'aperçu a affiché des barres colorées avant les gestes, puis est resté
**noir** après changement d'onglet et déplacement de la tête de
lecture dans le clip. Concat montre toujours les pistes, les miniatures
colorées, les poignées de sélection du texte et l'horodatage 00:00:03:04.
La cause de cette défaillance visuelle n'est pas encore établie et un
montage professionnel long ne doit pas être certifié à ce stade.

Le projet enregistré et le SRT n'ont pas changé :
- concat.json SHA256 d20622f62cc694838d0935298ec5a9e21a0c56bf7fdcea8f10237d92feff7291
- Untitled project 8.srt SHA256 9d8d684b21f5f490991ff0258270db11efb6007d750e8568c99f8427b8de9ca7

## Session native après réconciliation

La session précédente PID 101086 a été remplacée par une AppImage standard
PID 10485, au premier écran. La commande idempotente mise en place a
fermé normalement cette AppImage et lancé une unique instance instrumentée
PID 120739, socket Slint attesté, sans headless ni second Concat.
Un deuxième appel a réutilisé le même PID, sans nouveau lancement.
Cela résout le problème d'attachement et de doublons, pas encore
l'anomalie d'aperçu noir constatée dans l'ancienne session.
Voir docs/CCER_NATIVE_IDEMPOTENT_LIFECYCLE_20261028.md.

## Suite

Diagnostiquer et corriger le compositing/rafraîchissement de l'aperçu
dans le vrai Concat sans substituer une modification de projet invisible.
Puis monter un rush parlé réel de plusieurs minutes, contrôler les
titres, transitions, son, SRT et export MP4; terminer tests Rust et
validation du transport MCP distant. La vision reste FFmpeg/captures
Slint/ChatGPT et Whisper Concat ; pas de Qwen/Ollama.

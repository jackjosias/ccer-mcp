# CCER Native Computer Use — Slint (24 octobre 2026)

## Contexte vérifié

Objectif : piloter la véritable interface de Concat sans focaliser sa fenêtre ni déplacer le pointeur physique du propriétaire, qui continue à travailler dans Antigravity ou VLC.

Source de référence : `jub0t/Concat`, tag `v0.2.8`, commit `79116bd0f9a103c633d888603ad27890e929dbdc`, copie locale distincte `.upstream-concat/`, branche `feat/ccer-inapp-slint-20261023`. La production reste l'AppImage officielle non modifiée.

Slint 1.18 offre `Window::dispatch_event_with_result(WindowEvent)` pour les événements d'interface et `Window::take_snapshot()` pour capturer de vrais pixels RGBA. Concat les relie déjà à la fenêtre dans `src/crates/concat/src/lib.rs` et à son `Shell::with`.

## Réalisations

- `ccer/inapp_protocol.py` : client Unix local avec permissions, `SO_PEERCRED`, preuve d'autorisation, fenêtres et frames liées, hash SHA-256 du JPEG et capture AVANT/APRÈS chaque geste. Aucun fallback X11/headless.
- `tests/test_inapp_protocol.py` et `tests/test_native_desktop.py` : **78/78 tests Python réussis**, dont un essai via une vraie socket Unix vers un simulateur Slint (et non une fenêtre Concat réelle).
- Fork Rust : `ccer_input.rs` (événements Slint, JPEG) et `ccer_server.rs` (socket Unix privée, SO_PEERCRED, preuve SHA-256, session, compteur d'image). Déclaré dans `lib.rs` uniquement sous le feature `ccer-inapp` et démarré uniquement avec une configuration explicite. Le premier `cargo check` a réussi (code 0) AVANT l'ajout du drag temporisé. Le drag à étapes Slint est ajouté, mais son typage final et son exécution sur une vraie fenêtre restent à certifier.
- Copie source Git isolée (environ 64 Mo) ignorée par le dépôt CCER.

## Certification encore indispensable

1. Le `cargo check --features ccer-inapp` initial a réussi (**code 0**, 37 min 26 s). Il faut contrôler les nouvelles modifications du drag et construire le binaire indépendant de l'AppImage officielle.
2. Démarrer ce binaire avec une socket `~/.local/state/ccer-inapp/*.sock` et une autorisation aléatoire de 32 caractères minimum ; contrôler les permissions 0700/0600 et l'identité UID/PID.
3. Capturer de **vrais pixels Slint** et tester les clics, le défilement, les touches, la capture avant/après, les images périmées et l'absence de contrôle du pointeur physique X11.
4. Le drag temporisé est ajouté (timer Slint de 50 ms), sans certification réelle. Le curseur fantôme indépendant et les captures de frames intermédiaires restent à implémenter ; aucun repli X11.
5. Certifier import, montage, sauvegarde, export vidéo et reconnexion sur un projet jetable dans une véritable fenêtre.

## Contraintes de compilation

Ubuntu : 17 Go libres au dernier contrôle, disque 96 % utilisé et swap fortement sollicité. Cargo a récupéré ses dépendances. Les fichiers de développement Linux ont été extraits sans sudo dans le répertoire persistant `.upstream-concat/.ccer-build-deps/root` (exclu de Git). Une archive **FFmpeg 7.1.5 partagée** (SHA-256 `df7e15a2d2fe0ee15ae36e0e3b83596dd088ee0a0767874241d9a54380df0add`) est isolée dans `.upstream-concat/.ccer-ffmpeg7`, sélectionnée par le script `.upstream-concat/.ccer-cargo-check.sh`. Le verrou Cargo a été actualisé hors ligne pour les dépendances optionnelles et le contrôle rétablit `--offline --locked`. Le script de téléchargement `.upstream-concat/.ccer-fetch-build-deps.sh` reconstruit cet environnement en cas de besoin. Un `cargo check` a terminé avec **code de sortie 0** en 37 min 26 s, avant les changements du drag. Le script `.upstream-concat/.ccer-cargo-check.sh build` construit l'exécutable avec un seul job.

## Reproductibilité du fork

Le fork Rust est commité sur `feat/ccer-inapp-slint-20261023` : fondation `3a63096`, puis serveur sécurisé et environnement reproductible `6aa3661`. Le dépôt CCER conserve trois patchs à appliquer **dans cet ordre** sur une copie propre du tag officiel Concat `v0.2.8` : `docs/native-patches/0001-feat-concat-stage-opt-in-Slint-computer-use-events-a.patch`, puis `docs/native-patches/0001-feat-ccer-add-opt-in-authenticated-Slint-Unix-bridge.patch`, et enfin `docs/native-patches/0001-feat-ccer-paced-native-Slint-drag-and-controlled-bui.patch`. Les deuxième et troisième patchs passent `git apply --reverse --check` sur le fork (code 0). Le commit `ea7294e` ajoute le drag cadencé et le mode build. Le test réel est `python3 -m tests.native_slint_smoke`, uniquement après compilation de l'exécutable. Le dépôt imbriqué `.upstream-concat/` reste ignoré pour éviter de dupliquer les sources et les binaires.

**État honnête (24 octobre 2026) :** routage Python natif explicite `ccer/native_desktop.py` raccordé à `desktop_gui.py`, 78/78 tests réussis avec mocks et simulateur Unix, socket réelle côté tests Python. Serveur Rust compilé avant le drag ; le code du drag temporisé est ajouté et attend validation Rust et visuelle. La saisie libre reste refusée, sans repli X11. AppImage officielle intacte ; Xvfb/Lavapipe reste un mode GUI distinct.

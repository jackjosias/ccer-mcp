# CCER Native Computer Use — Slint (24 octobre 2026)

## Contexte vérifié

Objectif : piloter la véritable interface de Concat sans focaliser sa fenêtre ni déplacer le pointeur physique du propriétaire, qui continue à travailler dans Antigravity ou VLC.

Source de référence : `jub0t/Concat`, tag `v0.2.8`, commit `79116bd0f9a103c633d888603ad27890e929dbdc`, copie locale distincte `.upstream-concat/`, branche `feat/ccer-inapp-slint-20261023`. La production reste l'AppImage officielle non modifiée.

Slint 1.18 offre `Window::dispatch_event_with_result(WindowEvent)` pour les événements d'interface et `Window::take_snapshot()` pour capturer de vrais pixels RGBA. Concat les relie déjà à la fenêtre dans `src/crates/concat/src/lib.rs` et à son `Shell::with`.

## Réalisations

- `ccer/inapp_protocol.py` : client Unix local avec permissions, `SO_PEERCRED`, preuve d'autorisation, fenêtres et frames liées, hash SHA-256 du JPEG et capture AVANT/APRÈS chaque geste. Aucun fallback X11/headless.
- `tests/test_inapp_protocol.py` et `tests/test_native_desktop.py` : **82/82 tests Python réussis**, dont un essai via une vraie socket Unix vers un simulateur Slint (et non une fenêtre Concat réelle).
- Fork Rust : `ccer_input.rs` (événements Slint, JPEG) et `ccer_server.rs` (socket Unix privée, SO_PEERCRED, preuve SHA-256, session, compteur d'image). Déclaré dans `lib.rs` uniquement sous le feature `ccer-inapp` et démarré uniquement avec une configuration explicite. Le contrôle `cargo check` initial puis le contrôle final **incluant le drag temporisé** ont réussi (codes 0). Le drag à étapes Slint compile ; son exécution sur une vraie fenêtre reste à certifier.
- Copie source Git isolée (environ 64 Mo) ignorée par le dépôt CCER.

## Certification encore indispensable

1. Deux contrôles `cargo check --features ccer-inapp` ont réussi (**code 0** ; le second inclut le drag et a duré 43 min 12 s). Il faut terminer le `cargo build` du binaire indépendant de l'AppImage officielle, puis compiler/certifier les nouveaux gestes `file_drop` et `select_export_folder` (commit Rust `9c5987f`, non couverts par les contrôles antérieurs).
2. Démarrer ce binaire avec une socket `~/.local/state/ccer-inapp/*.sock` et une autorisation aléatoire de 32 caractères minimum ; contrôler les permissions 0700/0600 et l'identité UID/PID.
3. Capturer de **vrais pixels Slint** et tester les clics, le défilement, les touches, la capture avant/après, les images périmées et l'absence de contrôle du pointeur physique X11.
4. Le drag temporisé est ajouté (timer Slint de 50 ms), sans certification réelle. Le curseur fantôme indépendant et les captures de frames intermédiaires restent à implémenter ; aucun repli X11.
5. Certifier import, montage, sauvegarde, export vidéo et reconnexion sur un projet jetable dans une véritable fenêtre. `bash tests/create_native_smoke_fixture.sh` crée un MP4 H.264/AAC de 2 s dans `.runtime/ccer-smoke/source.mp4`; ce média a été vérifié par `ffprobe` (2.000 s, 437676 octets). L'export **par Concat** n'a pas encore été réalisé.

## Contraintes de compilation

Ubuntu : 17 Go libres au dernier contrôle, disque 96 % utilisé et swap fortement sollicité. Cargo a récupéré ses dépendances. Les fichiers de développement Linux ont été extraits sans sudo dans le répertoire persistant `.upstream-concat/.ccer-build-deps/root` (exclu de Git). Une archive **FFmpeg 7.1.5 partagée** (SHA-256 `df7e15a2d2fe0ee15ae36e0e3b83596dd088ee0a0767874241d9a54380df0add`) est isolée dans `.upstream-concat/.ccer-ffmpeg7`, sélectionnée par le script `.upstream-concat/.ccer-cargo-check.sh`. Le verrou Cargo a été actualisé hors ligne pour les dépendances optionnelles et le contrôle rétablit `--offline --locked`. Le script de téléchargement `.upstream-concat/.ccer-fetch-build-deps.sh` reconstruit cet environnement en cas de besoin. Deux `cargo check` ont terminé avec **code de sortie 0** ; le second inclut le drag cadencé et a duré 43 min 12 s. Le script `.upstream-concat/.ccer-cargo-check.sh build` construit l'exécutable avec deux jobs depuis le commit `a6d2a31` ; la construction complète peut dépasser une heure sur le ThinkPad (15 Gio RAM, swap fortement utilisé).

## Reproductibilité du fork

Le fork Rust est commité sur `feat/ccer-inapp-slint-20261023` : fondation `3a63096`, puis serveur sécurisé et environnement reproductible `6aa3661`. Le dépôt CCER conserve cinq patchs à appliquer **dans cet ordre** sur une copie propre du tag officiel Concat `v0.2.8` : `docs/native-patches/0001-feat-concat-stage-opt-in-Slint-computer-use-events-a.patch`, puis `docs/native-patches/0001-feat-ccer-add-opt-in-authenticated-Slint-Unix-bridge.patch`, ensuite `docs/native-patches/0001-feat-ccer-paced-native-Slint-drag-and-controlled-bui.patch`, puis `docs/native-patches/0001-build-ccer-use-two-Cargo-jobs-for-native-desktop-bin.patch`, et enfin `docs/native-patches/0001-feat-ccer-guarded-scene-media-drop-and-export-folder.patch`. Les deuxième et troisième patchs passent `git apply --reverse --check` sur le fork (code 0). Le commit `ea7294e` ajoute le drag cadencé et le mode build. Le test réel est `python3 -m tests.native_slint_smoke`, uniquement après compilation de l'exécutable. Il vérifie permissions 0600, image réelle, frame avant/après, move, drag, clic, scroll et Échap, ainsi que dépôt de média autorisé et dossier d'export via les messages UI de Concat, sur configuration XDG jetable. Le test du résultat visuel, du placement timeline et du vrai MP4 exporté reste requis. Le dépôt imbriqué `.upstream-concat/` reste ignoré pour éviter de dupliquer les sources et les binaires.

**État honnête (24 octobre 2026) :** routage Python natif explicite `ccer/native_desktop.py` raccordé à `desktop_gui.py`, 82/82 tests réussis avec mocks et simulateur Unix, socket réelle côté tests Python. Serveur Rust et drag temporisé compilés avec succès ; les vrais gestes et l'export attendent la construction du binaire et une certification visuelle. La saisie libre reste refusée, sans repli X11. AppImage officielle intacte ; Xvfb/Lavapipe reste un mode GUI distinct.

# CCER Native Computer Use — Slint (23 octobre 2026)

## Contexte vérifié

Objectif : piloter la véritable interface de Concat sans focaliser sa fenêtre ni déplacer le pointeur physique du propriétaire, qui continue à travailler dans Antigravity ou VLC.

Source de référence : `jub0t/Concat`, tag `v0.2.8`, commit `79116bd0f9a103c633d888603ad27890e929dbdc`, copie locale distincte `.upstream-concat/`, branche `feat/ccer-inapp-slint-20261023`. La production reste l'AppImage officielle non modifiée.

Slint 1.18 offre `Window::dispatch_event_with_result(WindowEvent)` pour les événements d'interface et `Window::take_snapshot()` pour capturer de vrais pixels RGBA. Concat les relie déjà à la fenêtre dans `src/crates/concat/src/lib.rs` et à son `Shell::with`.

## Réalisations

- `ccer/inapp_protocol.py` : client Unix local avec permissions, `SO_PEERCRED`, preuve d'autorisation, fenêtres et frames liées, hash SHA-256 du JPEG et capture AVANT/APRÈS chaque geste. Aucun fallback X11/headless.
- `tests/test_inapp_protocol.py` : 9 tests réussis **avec serveur simulé uniquement**.
- Fork Rust : `src/crates/concat/src/ccer_input.rs`, activé uniquement par le feature `ccer-inapp`. Événements Slint réels click/move/scroll/clavier sur le thread UI ; capture JPEG via `Window::take_snapshot()`. Aucun serveur, socket ou entrée physique démarrés automatiquement. Les drags sont refusés jusqu'à leur implémentation temporisée et visible.
- Copie source Git isolée (environ 64 Mo) ignorée par le dépôt CCER.

## À réaliser avant certification native

1. Compiler le feature `ccer-inapp` contre **les dépendances verrouillées** de Concat et tester les événements sur une fenêtre réelle.
2. Ajouter dans Concat un listener UNIX local, désactivé par défaut, avec activation volontaire, permissions 0600, contrôle client UID/PID et secret de session.
3. Relier le listener à `slint::invoke_from_event_loop` et `Shell::with` ; envoyer des captures réelles avec compteur de frame, identité de fenêtre/session et réponses au protocole Python.
4. Ajouter curseur fantôme Slint, glisser-déposer temporisé avec captures intermédiaires, annulation et vérification de l'état du projet.
5. Certifier dix gestes réels, import, montage, sauvegarde et export sur projet jetable, sans événement focus/souris imputable à CCER, puis reconnexion et redémarrage du tunnel.

## Contraintes de compilation

Ubuntu : ~21 Go libres, disque 95 % utilisé, `rustc 1.95.0` et `cargo 1.95.0`. `cargo metadata --offline --no-deps` réussit. `cargo check --offline --locked -p concat --lib --features ccer-inapp` reste bloqué avant compilation car le cache Rust possède `log 0.4.29` mais le lock officiel exige `log 0.4.34`. Ne pas modifier le lockfile ni déclencher un build massif sans mesurer sa taille.

## Reproductibilité du fork

Le fork Rust a été commité localement en `3a63096` sur `feat/ccer-inapp-slint-20261023`. Le patch exporté est versionné avec CCER sous `docs/native-patches/0001-feat-concat-stage-opt-in-Slint-computer-use-events-a.patch` : il peut être appliqué sur une copie propre du tag officiel `v0.2.8` avec `git apply /chemin/vers/ce/patch`. Le dépôt imbriqué `.upstream-concat/` reste volontairement ignoré par Git CCER pour éviter les sources dupliquées.

**État honnête :** transport Python simulé validé et socle Rust préparé ; aucune compilation Rust complète ni Computer Use natif end-to-end certifié à ce stade. Garder Xvfb+Lavapipe comme contrôle GUI de référence.

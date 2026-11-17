# Documentation technique CCER

Ce portail classe les guides existants sans dupliquer leur contenu. [README principal](../README.md) · [CHANGELOG](../CHANGELOG.md) · [Contribuer](../CONTRIBUTING.md) · [Sécurité](../SECURITY.md).

## Vue d'ensemble et installation

| Document | Sujet |
|---|---|
| [Architecture](architecture.svg) · [Source Mermaid](architecture.mmd) | Vue générale versionnée |
| [Installation native](CCER_NATIVE_SETUP.md) | Compiler un Concat instrumenté |
| [Protocole Slint](CCER_NATIVE_SLINT.md) | Session, captures et gestes |
| [Bureau visible](CCER_VISIBLE_DESKTOP.md) | Contrôle de l'interface réelle |
| [Direct Visible Desktop](CCER_DIRECT_VISIBLE_DESKTOP.md) | Modes d'observation |
| [Connexion tunnel](CCER_DIRECT_TUNNEL.md) | Transport ChatGPT Direct |

## Sécurité et interface

| Document | Sujet |
|---|---|
| [GUI-FIRST](CCER_GUI_FIRST_CONTRACT.md) | Capture avant/après et autorisations |
| [Focus et pointeur](CCER_FOCUS_ISOLATION.md) | Non-interférence |
| [Desktop Control](CCER_DESKTOP_CONTROL.md) | Outils et bornes |
| [Cycle idempotent](CCER_NATIVE_IDEMPOTENT_LIFECYCLE_20261028.md) | Une seule session contrôlée |

## Analyse audiovisuelle

| Document | Sujet |
|---|---|
| [Revue timecodée](CCER_TIMECODED_REVIEW.md) | JPEG authentiques et pagination |
| [Replay A/V](CCER_AV_REPLAY_POLL_20261028.md) | Décodage borné et charge |
| [Whisper ASR](CCER_ASR_READINESS.md) | Modèle intégré et preuves |
| [SRT natif](CCER_NATIVE_SRT_ACCEPTANCE_20261028.md) | Contrat de sauvegarde |
| [Intelligence média](CCER_MEDIA_INTELLIGENCE.md) | Métadonnées et recherche |
| [Studio V2](CCER_V2_STUDIO.md) | Narration et montage |

## Médias temporaires et audits

| Document | Sujet |
|---|---|
| [Scratch lifecycle](CCER_SCRATCH_LIFECYCLE.md) | Ressources temporaires |
| [Rétention des médias](CCER_TEMPORARY_MEDIA_RETENTION.md) | Ne pas supprimer les sources |

## Vérifier le schéma

```bash
python3 docs/render_architecture.py --check
```

Le README intègre deux diagrammes de processus Mermaid ; le dépôt ne prétend pas contenir les **onze SVG** de WCER. Les preuves datées sont accessibles dans [CHANGELOG](../CHANGELOG.md).

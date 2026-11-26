# Contribuer à CCER

CCER développe une assistance vidéo **observable, vérifiable et non intrusive**. Les contributions doivent être ciblées, réversibles, testées et compatibles avec le contrat [GUI-FIRST](docs/CCER_GUI_FIRST_CONTRACT.md).

## Avant de modifier le code

Lire le [README](README.md), le [CHANGELOG](CHANGELOG.md), la [politique de sécurité](SECURITY.md) et l'[index technique](docs/README.md).

- Réutiliser les modules existants (DRY) et les tests.
- Préserver **FFmpeg/FFprobe + captures réelles + Whisper intégré** ; ne pas ajouter un VLM local lourd sans accord explicite.
- Ne jamais déplacer la souris physique, voler le focus ou modifier une timeline en headless via ChatGPT Direct.
- Ne pas supprimer des vidéos sources ou exports pour nettoyer des artefacts temporaires.

## Structure

| Emplacement | Contenu |
|---|---|
| `ccer/` | Passerelles, commandes CLI, médias et sécurité |
| `tests/test_*.py` | Tests de contrats et régressions |
| `tests/live_*.py` | Tests sur médias et sessions dédiés |
| `docs/` | Spécifications, guides natifs et preuve A/V |
| `docs/native-patches/` | Patches pour Concat instrumenté |

## Préparer le développement

```bash
git clone https://github.com/jackjosias/ccer-mcp.git
cd ccer-mcp
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m pip install -e .
```

Installer Concat et les outils Rust seulement selon [le guide natif](docs/CCER_NATIVE_SETUP.md).

## Git et travail parallèle

Utiliser une branche ou un **worktree isolé**. Délimiter les fichiers de chaque agent, vérifier `git status` et ne pas écraser les modifications concurrentes. Les préfixes `docs/`, `feat/`, `fix/`, `test/`, `security/` et `refactor/` sont recommandés.

## Tests et qualification

```bash
python3 -m compileall -q ccer
python3 -m unittest discover -s tests -p 'test_*.py' -q
python3 docs/render_architecture.py --check
git diff --check
git status
```

Un mock PASS n'est pas une preuve de geste dans Concat. Documenter séparément la validation Slint, les captures authentiques, l'absence d'interférence et les exports. Ne jamais inventer une qualification LIVE.

## Pull requests

1. Décrire l'objectif, le périmètre et les risques.
2. Justifier la réutilisation de code et les tests pertinents.
3. Inclure les résultats datés, le statut du runtime et les blocages.
4. Ajouter l'évolution dans [CHANGELOG.md](CHANGELOG.md) sans effacer l'historique.
5. Mettre à jour le guide `docs/` existant plutôt que dupliquer des instructions.
6. Ouvrir une PR et solliciter une revue de [@jackjosias](https://github.com/jackjosias).

Aucun `push --force`, merge dangereux, suppression de worktree non fusionné ou contournement d'un refus de sécurité. Les contributions au code original CCER sont soumises à **AGPL-3.0-or-later** ([LICENSE](LICENSE)). Ne soumettre que du contenu que vous êtes autorisé à distribuer ; respecter les licences et mentions des composants tiers, notamment [Concat](https://github.com/jub0t/Concat).

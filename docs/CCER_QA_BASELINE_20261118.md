# CCER — Baseline QA indépendante (18 novembre 2026)

> **Périmètre : audit de code et tests reproductibles, pas certification d'un montage réel.** Ce rapport évite toute intervention dans la fenêtre Concat utilisée par l'autre agent.

## Périmètre et provenance

- Source locale audité : branche `feat/wcer-operator-direct-transaction-20261023031543`, SHA `0220f7a2eeab87fad97d65eef2cd3487721f37e8`.
- Copie de test isolée : `/tmp/ccer-qa-independent-20261118`, créée par `git clone --no-hardlinks`.
- GitHub public `main` : SHA `059a1f1cc79ad898a22d8e313d2442c118399971` au moment du contrôle. **Ce commit public n'est pas identique au snapshot local testé.**
- Les tests `tests/live_*`, la fenêtre Concat, le pointeur physique et les médias utilisateur n'ont pas été manipulés. L'espace de travail original est resté propre, HEAD inchangé.
- DRY/TDD : les tests, protocoles et vérifications existants ont été réutilisés sans duplicata.

## Résultats exécutés

| Vérification | Résultat |
| --- | --- |
| `python3 -m unittest discover -s /tmp/ccer-qa-independent-20261118/tests -t /tmp/ccer-qa-independent-20261118 -p 'test_*.py' -q` | **PASS, 268 tests, 96,235 s, exit 0** |
| `python3 /tmp/ccer-qa-independent-20261118/docs/render_architecture.py --check` | **PASS, SVG matches Mermaid source** |
| `python3 -m ccer.native_setup --check` (lecture seule sur source locale) | **PASS, 6 patchs natifs, base Concat `79116bd0f9a1`** |
| Outils installés | **Python 3.12.3 ; FFmpeg et FFprobe 6.1.1** |
| Intégrité espace de travail de l'agent parallèle | **PASS, clean=true, HEAD `0220f7a`** |
| Workflow GitHub sur `main` `059a1f1` | **PASS**, [exécution 44101179865](https://github.com/jackjosias/ccer-mcp/actions/runs/44101179865) |

Le workflow public couvre les régressions Python, les diagrammes et la reproduction des patchs **source** ; il ne prouve pas la compilation du binaire Rust complet ni une opération UI réelle.

## Matrice de conformité

| Domaine | Verdict de cette campagne | Ce qui n'est pas prouvé |
| --- | --- | --- |
| Régressions Python | **PASS 268/268** | Les scénarios `live_*` |
| Gateway direct et GUI-FIRST | **Contrat dans le code ; tests au vert** | Autorisation d'un geste sur Concat réel |
| Slint : socket, reçus, images | **Tests de protocole couverts** | Vrais pixels, drag et export dans la fenêtre GUI |
| Patchs Rust / Concat | **PASS intégrité de six patchs** | Compilation Rust `cargo build` et exécution native |
| FFmpeg : vidéo, audio, scènes, silences | **Binaires disponibles, régressions vertes** | Compréhension sémantique intégrale d'une vidéo |
| Whisper / SRT | **Intégration et contrats source** | Nouvelle transcription réellement écoutée, offsets vérifiés |
| Rétention des JPEG et médias temporaires | **Contrat/tests couverts** | Inspection exhaustive des fichiers utilisateur |
| Export et qualité créative | **NON TESTÉ en UI réelle** | Import, coupes, titres, mix, sous-titres, vrai MP4 vérifié |
| Client MCP distant / tunnel | **NON TESTÉ en bout en bout** | Activation effective du client et contrôle natif |

Une ligne des tests indique `current.AppImage (missing)` dans un scénario ; cela ne suffit pas pour conclure à l'absence générale de Concat sur la machine.

## Séquence de recette réelle à venir

1. **Rebase méthodique** sur les changements de l'autre agent, puis régressions ciblées ; comparaison du snapshot local et de `main` avant intégration.
2. **Build Concat instrumenté** sur une copie épinglée de la source officielle avec les six patchs ; `cargo check` et `cargo build`, sans démarrer une seconde instance Concat par défaut.
3. **Test GUI Slint coordonné** : permissions socket/UID/PID, `inputReady`, fenêtre attendue, captures AVANT/APRÈS, image fraîche (< 75 s), clic/drag/scroll, refus des reçus périmés ; pas d'entrée physique X11.
4. **Montage jetable vérifiable** : import média autorisé, coupe, titre, audio, sous-titres, sauvegarde, export **nouveau**, inspection FFprobe et décodage intégral FFmpeg.
5. **Rush parlé long** : Whisper/SRT, timecodes/offsets, noirs, gels, silences, loudness, qualité de voix et revue humaine ; la pagination des frames n'est pas un visionnage intégral en continu.
6. **Garde-fous** : rollback sans rejouer une action inconnue, nettoyage borné des seules preuves, préservation des médias sources, des projets et des exports finals.

**Décision :** QA source automatisée **PASS** ; homologation de montage réel **EN ATTENTE**. Préserver l'architecture légère FFmpeg + captures réelles + Whisper intégré à Concat : **ne pas ajouter Qwen/Ollama/VLM**.

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

**Complément natif du 18 novembre 2026 :** sur le commit local `196749f`, 269 tests Python PASS (192,893 s, exit 0) dans un clone indépendant ; les six patchs passent `ccer.native_setup --check` et l'arbre préparé passe `--verify` ; FFprobe confirme un MP4 jetable H.264/AAC 640×360 de 2 s. Build Cargo `--lite --jobs 2` déjà actif auprès de l'agent parallèle ; aucun second build ni Concat lancé. Le diagnostic visible donne `nativeBridge=false`, aucune fenêtre sur `:1`, `launchReady=false` (garde-fou de charge) : certification GUI réelle toujours EN ATTENTE. CI du commit GitHub `aa680e7` : success.

## Certification E2E graphique réelle — 18 novembre 2026 (complément post-baseline)

**Statut de cette recette : PASS pour un montage audiovisuel synthétique de 5 secondes.** Ce complément actualise les états « en attente » du tableau historique ci-dessus ; il ne transforme pas les contrôles non exécutés (Whisper réel, rush long, pilotage du client MCP distant) en succès.

| Jalon contrôlé | Preuve constatée | Verdict |
| --- | --- | --- |
| Concat visible | Instance instrumentée PID `949394`, fenêtre `0x03c00005`, `DISPLAY :1` sur le bureau réel ; aucune session Xvfb ni injection de pointeur X11 | **PASS** |
| Projet / import | `CCER-Visual-QA-20261118`, média synthétique `source.mp4` ajouté par `file_drop` natif autorisé (`1 added, 0 failed`) | **PASS** |
| Montage par l'UI | Titre de 0 à 3,00 s, vidéo `m5` de 3,00 à 5,00 s ; deux clips même timeline, sans trou, avec captures Slint avant/après les gestes | **PASS** |
| Export Concat | Bouton Exporter de la fenêtre réelle ; `export: started` 16:24:03.537 UTC et `export: finished` 16:26:44.704 UTC, soit 161,167 s | **PASS** |
| Sortie vidéo | MP4 H.264 High, 1920×1080, 24 ips, 120 images, exactement 5,000 s | **PASS** |
| Sortie audio | AAC LC, 48 kHz, stéréo, piste de 4,970 s ; `silencedetect` 0–3,00004 s puis signal audible ; volume moyen −24,1 dB / crête −19,2 dB sur le segment 3–5 s | **PASS** |
| Intégrité | FFprobe exit 0, décodage intégral FFmpeg exit 0, images inspectées à 1,0 s (titre) et 3,5 s (source vidéo) | **PASS** |
| Préservation | Ancien export de titre seul conservé ; aucun média ni projet utilisateur tiers modifié ; dépôt de développement local inchangé | **PASS** |

**Source :** `.runtime/ccer-smoke/source.mp4`, H.264 640×360 à 24 ips, AAC mono 48 kHz, 2,000 s, 437 676 octets. Seule cette fixture et le projet jetable dédié ont servi au montage.

**Livrable local :** `.runtime/ccer-smoke/exports/CCER-Visual-QA-Final-20261118.mp4` sous `/home/jack-josias/WORKSPACE-LOGICIEL/concat/ccer-mcp/`. Taille : **4 008 833 octets** ; empreinte SHA-256 : `3e101619287bdd720d9eea283b436d7d5a20ff550fc9618eabc2a26c00b5dc11`.

**Méthode GUI-FIRST :** chaque action mutante a été soumise à une capture Slint fraîche, un reçu et une capture après action ; l'état de la timeline a été recoupé avec le fichier de projet. Un drag court de 0,2 s depuis la carte média a créé le clip (`AddClip` dans le journal), puis des gestes natifs `MoveClips` ont supprimé les blancs. Aucun edit caché de `concat.json` n'a été utilisé.

**Diagnostics sans impact sur ce PASS :** le rendu Intel HD 520 émet un avertissement de détection de l'ICD Vulkan Nvidia absent ; le moteur choisit ensuite l'iGPU Intel. Un seek direct à 3,5 s a émis `mmco: unref short failure`, mais le décodage séquentiel complet est passé avec exit 0 et la frame a été vérifiée visuellement.

**Limites et prochains chantiers :** cette certification porte exclusivement sur ce scénario court et synthétique. La capture Slint de sécurité reste coûteuse (baseline médiane 8,13 s ; prévisualisation X11 en lecture seule 1,14 s, sans pouvoir d'action). La vitesse d'export de 161 s pour 5 s et les rushs longs/parlés avec Whisper, sous-titres, transitions, mixage complexe, et contrôle créatif intégral restent à qualifier ou optimiser. Ne jamais confondre réussite du smoke E2E et certification de l'ensemble du produit CCER.

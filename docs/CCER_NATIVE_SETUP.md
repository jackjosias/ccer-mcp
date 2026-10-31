# CCER Native Setup V1 — Concat Rust/Slint

Cette procédure installe un **pont Slint instrumenté** sur une copie officielle et épinglée de Concat v0.2.8. Les six patchs publics incluent les quatre derniers correctifs natifs. Les neuf fichiers concernés sont comparés à des empreintes SHA-256 vérifiées sur le fork de référence, commit `6c0db85`.

> [!IMPORTANT]
> **Concat officiel et Concat instrumenté ne sont pas interchangeables.** Le programme `ccer-concat` installe l'AppImage officielle, sans pont Slint. Le programme `ccer-native` prépare une version instrumentée distincte et ne remplace aucune fenêtre ou installation existante.

## Prérequis

Linux x86_64 et **X11** pour les gestes visibles ; Python 3.10+, Git, Rust/Cargo, compilateur C/C++, Clang, pkg-config, FFmpeg/FFprobe et les bibliothèques de développement de [Concat](https://github.com/jub0t/Concat). La compilation native peut nécessiter FFmpeg 7 et les bibliothèques de fonts, audio et graphique du système. Elle n'installe aucun paquet système toute seule.

## Installer et préparer

```bash
git clone https://github.com/jackjosias/ccer-mcp.git
cd ccer-mcp
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m pip install -e .

ccer-native --check
ccer-native --prepare --fetch
ccer-native --verify
```

**`--fetch` est explicite :** sans cette option, aucune requête réseau n'a lieu. La source est récupérée uniquement depuis `https://github.com/jub0t/Concat.git` et épinglée au commit `79116bd0f9a103c633d888603ad27890e929dbdc`.

Si un clone officiel propre existe déjà, réutilisez-le :

```bash
ccer-native --prepare --source /CHEMIN/VERS/CONCAT
ccer-native --verify
```

Le nouvel arbre de travail utilise `git worktree` sous `.runtime/concat-native-prepared`. Il partage les objets Git avec la source : **pas de duplication de dépôt Git, aucune mutation du code source initial**. Les patchs sont contrôlés par SHA-256, appliqués dans l'ordre et les neuf fichiers résultants sont vérifiés. Une erreur retire uniquement l'arbre nouvellement créé ; un dossier préexistant est préservé. Relancer `--prepare` est idempotent.

## Compilation à la demande

```bash
ccer-native --build
```

Cette commande utilise Cargo avec `--locked --offline --features ccer-inapp -j 2`. Elle exige que les dépendances de développement et le cache Cargo soient disponibles ; elle ne lance et ne ferme jamais Concat. Si le cache des crates est vide sur un nouveau poste, autorisez **explicitement** leur téléchargement lors de la compilation :

```bash
ccer-native --build --allow-downloads
```

Le réseau reste désactivé par défaut ; cette option peut télécharger les dépendances Rust et leur chaîne de compilation, mais ne lance toujours pas Concat.

Pour réutiliser volontairement un cache Cargo existant au lieu de produire une seconde copie volumineuse :

```bash
export CCER_NATIVE_CARGO_TARGET_DIR=/CHEMIN/CCER/.upstream-concat/src/target
ccer-native --build
```

Le chemin du cache doit correspondre à un dossier réel du dépôt CCER. **Attention : un cache Cargo partagé peut régénérer et remplacer ses artefacts de compilation, y compris son binaire `debug/concat`. N'utilisez ce mode que si aucune instance de ce binaire n'est en cours d'exécution.** Sans cache personnalisé, le binaire attendu est `.runtime/concat-native-prepared/src/target/debug/concat`.

## Utiliser la version instrumentée

```bash
export CCER_NATIVE_BIN=/CHEMIN/ABSOLU/VERS/concat
export CCER_NATIVE_LIB_DIR=/CHEMIN/ABSOLU/VERS/lib   # optionnel
python3 -m ccer.visible_desktop status
```

La commande `launch` existante ne doit être invoquée qu'avec une seule session autorisée et des prérequis validés. Elle n'envoie aucun geste sur le pointeur physique. Voir [GUI-FIRST](CCER_GUI_FIRST_CONTRACT.md), [Native Slint](CCER_NATIVE_SLINT.md) et [Visible Desktop](CCER_DIRECT_VISIBLE_DESKTOP.md).

## Validation

```bash
python3 -m unittest tests.test_native_setup -v
python3 -m unittest discover -s tests -p 'test_*.py' -q
ccer-native --verify
```

**Attention :** préparation vérifiée, compilation réussie et montage vidéo réel sont trois preuves distinctes. Une recette GUI complète exige captures avant/après, timeline et export MP4 contrôlé par FFprobe. Les originaux et montages en cours ne doivent pas être utilisés pour une recette destructive.

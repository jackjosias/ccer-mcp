# CCER — Cycle de vie Concat GUI idempotent (28 octobre 2026)

## Une seule commande, jamais de headless

L'interface existante offre désormais la réconciliation atomique :

```bash
python3 -m ccer.visible_desktop reconcile --replace-unpatched --confirm --allow-high-cpu
```

Sans `--replace-unpatched --confirm`, la commande est **diagnostique**
si une AppImage standard existe et ne la ferme jamais. Sans
`--allow-high-cpu`, le seuil CPU de sécurité standard reste actif ;
l'opt-in ne désactive **pas** le minimum d'un Gio de RAM disponible.

Le résultat est `ATTACHED` quand l'unique Concat instrumenté est
déjà en fonctionnement : le socket Slint authentifié est contrôlé
par `observe`, aucun nouvel éditeur n'est lancé. Il est
`LAUNCHED_AND_ATTACHED` quand une fermeture normale autorisée
précède le lancement du binaire Rust instrumenté. Les deux cas
affirment `headless=false` et `physicalPointerUsed=false`.

## Invariants vérifiés

- Seuls les fenêtres identifiées `.concat`, les PIDs du propriétaire,
  la ligne de commande exacte de l'AppImage Concat installée et le
  binaire depuis son montage AppImage sont admissibles à un remplacement.
- La fermeture passe **uniquement** par WM_DELETE_WINDOW (`wmctrl -ic`),
  jamais SIGKILL, déplacement de curseur ou X11 keyboard injection.
  Un dialogue Enregistrer/Annuler ou un processus non terminé empêche
  immédiatement tout lancement supplémentaire ; un titre de fenêtre
  ne constitue pas une garantie de sauvegarde du projet.
- Les ressources, le binaire instrumenté et ses bibliothèques sont
  contrôlés **avant** la fermeture. Aucun démarrage sous mémoire
  insuffisante ; le dépassement CPU exige l'opt-in.
- Un fichier `lifecycle.lock` propriétaire, régulier, mode 0600, dans le
  répertoire privé CCER 0700, utilise `flock LOCK_EX|LOCK_NB` afin
  d'empêcher deux réconciliations/lancements concurrents.
- Le launcher Rust existant (`visible_desktop._launch_unlocked`) reste
  l'unique constructeur de processus et d'identité socket/proof ;
  `launch` public et `reconcile` partagent le même verrou.
- Les identités obsolètes de `desktop.json` sont remplacées uniquement
  par le lanceur existant après le contrôle des fenêtres et des ressources.
  Aucun relancement silencieux d'un geste incertain.

## Recette exécutée sur le vrai poste

Avant : une seule AppImage non instrumentée, PID **10485**,
fenêtre `0x03a00005`, affichant « Bon retour » ; ancienne identité
Slint pointant vers le PID mort 101086.

Appel confirmé : résultat **LAUNCHED_AND_ATTACHED**, nouvelle instance
Rust PID **120739**, fenêtre `0x03a00005`, `nativeFrame=1`,
`inputReady=true`, `headless=false`, aucune souris X11.
Nouvel appel identique non destructif : **ATTACHED** sur le même PID
120739, `launched=false`, toujours une seule fenêtre `.concat`
dans `wmctrl -lxp`. L'ancienne AppImage n'a pas été forcée/killée.

## Limites encore ouvertes

Le raccord natif et l'absence de doublons sont prouvés ; le rendu noir
observé dans le projet de la session antérieure n'est pas corrigé par
cette fonctionnalité. La recette professionnelle d'un montage long,
la compilation Rust GUI complète et la validation MCP distante restent
des jalons distincts. Vision exclusivement FFmpeg, captures natives,
inspection ChatGPT et Whisper déjà intégré à Concat, sans Qwen.

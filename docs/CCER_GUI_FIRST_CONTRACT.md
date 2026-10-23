# CCER — CONTRAT DE MONTAGE VISUEL OBLIGATOIRE

**Règle permanente du propriétaire, valable dans toute conversation future.**
ChatGPT GPT-6 est le réalisateur. Toutes les modifications de vidéo doivent être
faites **visiblement dans une session Concat isolée** (souris, clavier,
sélection, glisser-déposer, menus, timeline, export). L'utilisateur doit
pouvoir observer cette session dans un visualiseur qu'il choisit, sans
interruption de son travail dans Antigravity, VLC ou une autre application.

## Protection dans le code (pas seulement un prompt)

Le connecteur ChatGPT `ccer_direct_stdio.py` sert `DirectGateway`. Même avec
`--access control`, il n'annonce et n'exécute que les outils de lecture,
de diagnostic, de capture et `ccer_desktop_act`.

Toutes les écritures MCP invisibles (par exemple `project_create`,
`media_import`, `clip_update`, `title_add`, `export_start`,
`ccer_produce`, `ccer_directed_render`) sont **refusées côté serveur**,
même si quelqu'un tente de les appeler directement. L'option
`--mode headless` est refusée pour la connexion ChatGPT.
Les outils natifs existent toujours pour des tests de développement isolés
via `Gateway`, qui n'est PAS exposé par le tunnel ChatGPT.

## Boucle obligatoire, une action à la fois

1. Faire `ccer_preflight` puis `ccer_desktop_status`.
2. Faire `ccer_desktop_capture` **avant chaque geste**. La capture doit
   dater de moins de 75 secondes et correspondre à la fenêtre ciblée.
3. Avant toute action, vérifier `inputReady=true` dans `ccer_desktop_status`.
   Si l'affichage est partagé avec l'utilisateur, refuser tout geste.
   Faire une seule action réelle `ccer_desktop_act`, avec
   `expectedWindowId` exact, `confirm=true` et `withCapture=true` :
   `click`, `drag`, `scroll`, `key`, `type`.
4. Examiner l'image retournée **après chaque geste** ; reconnaître les
   anomalies et les corriger visuellement. Une nouvelle capture explicite
   est exigée pour autoriser le geste suivant.
5. Entre les gestes, l'utilisateur peut donner des corrections. Ne jamais
   enchaîner un script de modifications non observables.
6. Sauvegarder/exporter en cliquant dans Concat ; utiliser ensuite les
   outils de lecture et les diagnostics pour contrôler le vrai MP4.

**Si une action est impossible via Concat UI : s'arrêter et expliquer.**
Ne jamais basculer silencieusement sur le moteur headless.

## Visibilité et limites

- `drag` déplace uniquement le pointeur privé Xvfb, jamais la souris
  physique de l'utilisateur. Les clics ont aussi une courte pause de stabilisation.
- Les images sont des **captures successives**, et non un flux vidéo continu.
  Les sélecteurs « Importer des médias » de GTK sont désormais pris en charge
  **uniquement** après vérification stricte de leur classe, titre, PID et type.
  Les autres dialogues système non vérifiés demeurent interdits.
- `actionSent=true` prouve uniquement l'envoi à la bonne fenêtre ; vérifier
  ensuite l'interface et le projet, sans prétendre à une réussite artistique.
- Le contrat CCER ne dépend pas de WCER ni d'Ollama ; WCER sert uniquement à
  modifier/tester le code de CCER.

## Régression et mise en service

```bash
cd ~/WORKSPACE-LOGICIEL/concat/ccer-mcp
python3 -m unittest discover -s tests -v
python3 -m tests.live_direct_control
```

Le test refuse la création headless, permet les captures et bloque la
touche `Escape` sur le bureau humain. Les gestes réels ne seront certifiés
qu'après fonctionnement de Concat dans une session graphique isolée.
Voir [isolation du focus et de la souris](CCER_FOCUS_ISOLATION.md).

Après mise à jour du code, le propriétaire doit redémarrer uniquement son
`tunnel-client run --profile ccer-direct` dans le même terminal, puis
actualiser le connecteur ChatGPT. Le nombre d'outils **directement visibles
diminue volontairement**, mais les 85 outils du moteur natif demeurent
disponibles au développement. Cette restriction permanente garantit qu'un
futur assistant ne réutilise pas une opération de montage silencieuse.

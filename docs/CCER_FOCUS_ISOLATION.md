# CCER — Isolation du focus et de la souris (contrat durable)

## Invariant non négociable

L'agent CCER ne doit **jamais** activer Concat sur la session X11 de l'utilisateur
ni déplacer le pointeur physique. Antigravity, VLC, Word et les autres logiciels
doivent rester utilisables pendant que GPT-6 prépare/observe ses actions.

## Correctif antérieur étudié : chrome-mcp-source

Référence locale : `/home/your-user/sys/systemd/sysctl/sysstat/config/linux/chrome-mcp-source`.
Dans `mcp/browser-mission-hardening.mjs`, le fix Chrome :
- refuse `bringToFront` lors de `select_page`;
- force `new_page` à l'arrière-plan ;
- transmet `focus:false` à `Target.createTarget`;
- sépare le focus DOM du focus de fenêtre ;
- redimensionne le viewport par CDP, sans redimensionner la fenêtre OS.

**Différence fondamentale** : ces mécanismes CDP ne sont pas disponibles
pour les événements X11 de Concat. Le précédent CCER utilisait
`windowactivate`, `windowfocus`, `mousemove`, ce qui prenait réellement
le contrôle de la souris physique et du bureau.

## Verrou implémenté en priorité

`ccer.focus_isolation.require_private_input` est appelé **avant toute
action xdotool** dans `desktop_gui.interact`. Pour autoriser une action,
CCER exige :
- `DISPLAY` égal à `CCER_PRIVATE_DISPLAY` et différent du
  `CCER_HUMAN_DISPLAY` ;
- un Xvfb identifié par PID réel, commande exacte avec `-auth` et
  `-nolisten tcp` ;
- un fichier Xauthority régulier, privé et appartenant à l'utilisateur ;
- la présence de la socket UNIX de l'affichage isolé.

Sinon, le serveur renvoie `FOCUS_ISOLATION_REQUIRED` et **aucun clic,
clavier, mouvement ou glisser-déposer n'est envoyé**. L'activation
`windowactivate` du bureau humain a été supprimée.

`ccer_desktop_status` expose `inputReady=false` lorsque l'isolation
n'est pas attestée. Les captures et les diagnostics de lecture restent
possibles ; ne pas présenter l'interface comme contrôlable tant que l'accès
virtuel n'est pas opérationnel.

## Validation matérielle

`python3 -m tests.live_isolation_probe` crée temporairement un Xvfb privé,
déplace le pointeur **de cette session isolée**, puis confirme que le pointeur
et le focus de la session humaine ne changent pas. Le test nettoie ses
processus. `python3 -m tests.live_no_intrusion` confirme qu'une action
sur le Concat humain est refusée avant tout input.

**Blocage matériel encore constaté** : l'AppImage Concat 0.2.8 ne rend
pas son interface dans ce Xvfb. Son backend Vulkan exige DRI3 pour la
présentation. `WGPU_BACKEND=gl` n'a pas levé la limitation. Le mode natif
`CONCAT_GPU=software` provoque lui aussi un crash de Concat (SIGSEGV,
code -11) dans Xvfb. Le rendu isolé de Concat n'est donc PAS certifié. Nous ne devons PAS réactiver le contrôle du bureau humain
pour pallier cette incompatibilité.

## Condition pour reprendre un montage autonome en arrière-plan

Mettre à disposition un **affichage secondaire privé qui prend en charge
la présentation graphique requise par Concat**, puis y lancer une instance
Concat indépendante. Un viewer distinct, ouvert volontairement par
l'utilisateur, pourra afficher cette session sans forcer le premier plan.
Cela nécessite des essais GPU/DRI3 et une attestation de la session avant
mise en production. Aucun second rendu Concat n'est encore certifié.

### Non-régression

```bash
python3 -m unittest discover -s tests -v
python3 -m tests.live_isolation_probe
python3 -m tests.live_no_intrusion
python3 -m tests.live_direct_control
```

Après livraison, un redémarrage de **ccer-direct uniquement** est requis
pour que son processus MCP charge le nouveau verrou. Ne pas redémarrer
WCER, Antigravity ou le gestionnaire de fenêtres.

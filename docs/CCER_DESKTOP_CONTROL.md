# CCER Desktop Control — Concat GUI sous ChatGPT GPT-6

## Architecture et rôle

ChatGPT GPT-6 pilote le workflow de production : préparation, observation,
commande du montage, nouvelle capture, vérification des modifications et export.
**Aucun Ollama ni modèle local supplémentaire n'est nécessaire à cette boucle.**

L'outil Concat reste connecté via 42 outils MCP natifs, et CCER expose à présent
43 extensions (total **85 outils MCP** avec Concat Desktop 0.2.8).

### Contrôle visuel Concat : trois nouveaux outils

1. `ccer_desktop_status` identifie la fenêtre X11 Concat **ou son dialogue GTK
   « Importer des médias » vérifié**, puis renvoie l'identifiant, les dimensions
   et le PID de la cible courante.
2. `ccer_desktop_capture` renvoie une image JPEG de cette fenêtre sous forme
   d'un bloc **MCP image**, pas seulement un chemin de fichier. Son paramètre
   `maxWidth` vaut 840 par défaut (320 à 1600).
3. `ccer_desktop_act` envoie uniquement à cette fenêtre un clic, une touche,
   un texte court, un défilement ou un glisser-déposer progressif. Exige `confirm=true` et
   `expectedWindowId` récupéré via status/capture. Une nouvelle image
   MCP est renvoyée après interaction par défaut.

Exemple pour une interaction avec approbation :

```json
{
  "expectedWindowId": "0x03a00005",
  "action": "click",
  "x": 28,
  "y": 16,
  "button": 1,
  "confirm": true,
  "withCapture": true
}
```

**Depuis ChatGPT : une capture explicite AVANT chaque geste et une capture
obligatoire APRÈS. Le serveur bloque toute modification headless.**
Voir [le contrat GUI-FIRST](CCER_GUI_FIRST_CONTRACT.md).

L'identifiant de fenêtre présenté est un **exemple de la séance de test**, non
une valeur stable : il faut toujours le relire. Les coordonnées sont relatives
à la fenêtre **dans ses dimensions réelles** : une image prévisualisée peut
être redimensionnée et ne doit pas être utilisée directement comme système
de coordonnées.

## Sécurité et limites

- L'intégration est **Linux X11 uniquement**. Un bureau Wayland, un poste
  Windows ou macOS ne peut pas l'utiliser dans cet état.
- La classe X11 doit être exactement `.concat`, le processus affiché
  doit être `AppRun` ou `Concat` et il doit y avoir une seule fenêtre.
- Les captures utilisent `ffmpeg -f x11grab -window_id` ciblé sur Concat,
  ou sur son sélecteur de médias GTK dont la classe, le PID, le titre exact et le
  type de fenêtre sont vérifiés. Aucune capture générale du bureau n'est permise.
- Les actions demandent un `windowId` récent et une confirmation explicite.
  Si la cible est absente ou différente, l'interaction est refusée.
- Le clavier autorise seulement une liste bornée de touches/commandes. Le
  texte est limité à 500 caractères imprimables. Aucun shell n'est exécuté
  à partir du texte d'une commande GUI.
- Toute interaction est enregistrée dans le journal CCER, sans recopier le
  texte tapé ni le contenu de la capture.
- Un succès `actionSent=true` confirme l'envoi à Concat, **pas** la
  réussite fonctionnelle de l'opération visée. Il faut lire la capture
  suivante et/ou vérifier l'état du projet via les outils Concat MCP.
- X11 ne garantit pas une isolation du clavier par processus aussi forte qu'une
  machine virtuelle. Éviter de contrôler le bureau si une autre personne y
  travaille en même temps. Utiliser des projets de test avant les productions.

## Tests réels certifiés

```bash
cd ~/WORKSPACE-LOGICIEL/concat/ccer-mcp
python3 -m unittest discover -s tests -v
python3 -m tests.live_gateway_wire
python3 -m tests.live_desktop
```

Le test supplémentaire `python3 -m tests.live_portal_capture` vérifie
le dialogue « Importer des médias » lorsqu'il est ouvert, **sans sélectionner
ni modifier de fichier**. Le pont refuse les autres sélecteurs GTK.

Le test GUI capture la fenêtre Concat, clique le menu `Fichier`, envoie
`Échap`, obtient une seconde capture, et vérifie l'identifiant de la
fenêtre, la présence des blocs MCP image et l'audit.

## Objectif d'orchestration en conversation

1. GPT-6 choisit le montage et les outils Concat/CCER nécessaires.
2. `ccer_desktop_capture` fournit une observation réelle de Concat.
3. GPT-6 choisit un clic ou une touche ; `ccer_desktop_act` vérifie la cible.
4. GPT-6 inspecte la capture suivante et compare avec l'état MCP du projet.
5. Après vérification, GPT-6 poursuit le montage ou demande une clarification
   seulement si les éléments manquent ou que l'action est risquée.

Les captures et clics ne forment pas encore un agent autonome permanent ni une
reconnaissance universelle de tous les contrôles du logiciel. Le connecteur MCP
doit être accessible à la session ChatGPT qui orchestre, ou relayé via les outils
de développement WCER disponibles.

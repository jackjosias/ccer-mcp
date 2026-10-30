# CCER — contrôle natif du Concat visible (sans écran virtuel)

## Contrat utilisateur

La **seule cible acceptable** est la fenêtre Concat que l'utilisateur voit sur son bureau.
CCER n'injecte **aucun événement X11/XTest**, ne déplace pas le pointeur matériel,
n'active pas d'autres fenêtres et ne réutilise pas Chrome comme écran de montage.

La version officielle Concat 0.2.8 possède un MCP, mais son API ne modifie pas
le projet déjà ouvert dans la fenêtre : le mode live est encore à implémenter
en amont (issue #337). Il n'est **pas possible d'injecter rétroactivement**
notre module Rust dans l'AppImage officielle déjà en cours d'exécution.

## Architecture DRY

- Fork Rust compilé : `.upstream-concat/src/target/debug/concat`, avec la
  fonctionnalité opt-in `ccer-inapp`.
- Serveur `ccer_server.rs` démarré au lancement réel de Concat uniquement
  avec `CCER_INAPP_SOCKET` et une autorisation longue et aléatoire.
- `ccer/visible_desktop.py` : lanceur sur le **véritable DISPLAY** et dans le
  **véritable HOME**, détectant/refusant une fenêtre Concat préexistante ;
  reçu d'identité privé `~/.local/state/ccer-inapp/desktop.json` (0600).
- `ccer/native_desktop.py` : reconnecte automatiquement le MCP au reçu
  privé, après validation de l'exécutable/PID, via **le même**
  `InAppComputerUse` authentifié utilisé par les tests.
- Opérations confirmées : capture SHA-256 AVANT, geste Slint interne sur
  l'instance identifiée, capture APRÈS. Aucun repli `xdotool` sur le bureau humain.

## Reprise sûre de la véritable application

1. Lancer la commande de diagnostic (lecture seule) :

   ```bash
   cd /home/your-user/WORKSPACE-LOGICIEL/concat/ccer-mcp
   python3 -m ccer.visible_desktop status
   ```

2. Sauvegarder tout projet en cours **et fermer soi-même l'AppImage officielle**
   quand on souhaite remplacer l'exécutable par le fork compatible.
   **CCER refuse de la fermer** et ne lance pas de deuxième instance en parallèle.
   Ne pas essayer de connecter la version officielle inchangée à cette socket.
3. Sur le bureau local X11, lancer le Concat compatible, **visible à l'écran** :

   ```bash
   python3 -m ccer.visible_desktop launch --media-root "$HOME/Videos" --export-root "$HOME/Videos"
   ```

   Le binaire natif utilisera le véritable bureau et le véritable HOME ; aucun
   Xvfb, aucun navigateur, aucune simulation. Le fichier d'autorisation n'est
   pas transmis dans le journal ni dans le terminal.
4. Observer la **même fenêtre** via son endpoint sécurisé :

   ```bash
   python3 -m ccer.visible_desktop observe
   ```

   Cette commande fournit une image JPEG AVANT et un reçu dans
   `.runtime/ccer-desktop-evidence/`.
5. Pour une action approuvée, reprendre le suffixe hexadécimal du nom
   `before-<suffixe>.json`, et utiliser les coordonnées du **vrai cadre**
   Slint (pas celles d'une capture redimensionnée) :

   ```bash
   python3 -m ccer.visible_desktop act --receipt "<suffixe>" --type click --x 200 --y 250 --confirm
   ```

   Le résultat contient le chemin de l'image APRÈS, à examiner pour certifier
   l'effet métier. Chaque reçu expire après 60 secondes, et une variation de
   l'image ou de PID entraîne un refus sans geste.

## Autorisation propriétaire de la charge système

L'option `python3 -m ccer.visible_desktop launch --ignore-resource-advisory`
permet un lancement malgré les estimations CPU et RAM lorsque le propriétaire
l'autorise explicitement. Elle préserve les contrôles d'identité du PID,
de fenêtre unique, de chemins médias et les preuves Slint avant/après.
Elle ne remplace ni ne ferme une AppImage officielle encore ouverte.

## Critères de certification restant à accomplir

- Vérifier sur la **fenêtre installée visible** la connexion réelle au PID,
  l'absence d'activation de focus et de déplacement du pointeur physique.
- Faire un montage jetable : importer `source.mp4`, voir `Clips : 1`,
  exporter par Concat, attester MP4 final par FFprobe.
- Valider les commandes MCP par le connecteur CCER lorsque celui-ci sera
  accessible (l'erreur 429 actuelle est indépendante du protocole Rust).
- Vérifier que la fenêtre réelle reste réactive sous pression mémoire/disque.

Ne jamais annoncer « intégration Concat Desktop certifiée » sur la seule base
de tests réalisés sous Xvfb ou sur un export vidéo intermédiaire caché.

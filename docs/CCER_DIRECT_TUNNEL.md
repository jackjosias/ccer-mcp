# CCER Direct — GPT-6 → Secure MCP Tunnel → CCER → Concat Desktop

## Objectif

CCER est un serveur MCP autonome : **WCER n'intervient pas dans les missions
vidéo**. WCER peut servir à développer CCER, mais le runtime fonctionne
indépendamment. Le transport réseau officiel `tunnel-client` dirige un tunnel
sortant authentifié vers le lanceur local `ccer_direct_stdio.py`. Aucun port
public entrant et aucune dépendance à Ollama.

## Deux profils

- `observe` (défaut) : lecture, inspection et capture JPEG Concat. Les appels
  d'écriture sont refusés par le serveur, même s'ils ne figurent pas dans
  `tools/list`.
- `control` : **montage GUI-FIRST obligatoire**. Seuls les outils de lecture
  et le contrôle de la fenêtre Concat sont exposés. Les 85 outils du moteur
  existent toujours en interne, mais aucune modification headless n'est
  autorisée via ChatGPT. Voir [le contrat permanent](CCER_GUI_FIRST_CONTRACT.md).

Le contrôle de fenêtre reste borné à Concat et exige identifiant courant de
fenêtre et confirmation explicite. Un clic envoyé n'est pas la preuve de la
réussite du montage ; une nouvelle capture et l'état du projet doivent confirmer.

## Mise en service du profil séparé

1. Créer un **nouveau** tunnel CCER sur
   https://platform.openai.com/settings/organization/tunnels .
   Ne pas réutiliser celui de WCER.
2. Créer une clé API *runtime* dans le compte autorisé et la configurer sur
   l'Ubuntu sous `CONTROL_PLANE_API_KEY` par votre gestionnaire de secrets.
   Ne jamais la placer dans Git, la documentation ou cette conversation.
3. Dans le terminal du projet :

```bash
cd ~/WORKSPACE-LOGICIEL/concat/ccer-mcp
python3 -m ccer.tunnel_setup --tunnel-id "tunnel_VOTRE_ID_REEL" \
  --profile ccer-direct --access observe
tunnel-client doctor --profile ccer-direct
tunnel-client run --profile ccer-direct
```

Le générateur vérifie que l'ID contient `tunnel_` suivi de **32 caractères
minuscules alphanumériques**. Il crée un profil utilisateur uniquement s'il
n'existe pas déjà, via le modèle officiel `sample_mcp_stdio_local`. Il
référence la clé en `env:CONTROL_PLANE_API_KEY` et lie le panneau de santé
à l'interface locale `127.0.0.1`.

## Activation du contrôle sur un tunnel CCER déjà connecté

Quand le plugin `ccer-mcp` existe déjà et expose les 34 outils de lecture,
**ne pas recréer de tunnel**. Sur l'Ubuntu où réside le profil existant :

```bash
cd ~/WORKSPACE-LOGICIEL/concat/ccer-mcp
python3 -m ccer.profile_access --access control
python3 -m ccer.profile_access --access control --apply
```

La première commande est un aperçu sans écriture. La deuxième ne change
que `--access observe` en `--access control` dans
`~/.config/tunnel-client/ccer-direct.yaml`. Elle conserve l'identifiant
de tunnel, la référence de clé et les autres options. Elle refuse les liens
symboliques, profils inattendus, modifications concurrentes et écrasements
non intentionnels. La bascule est réversible avec
`python3 -m ccer.profile_access --access observe --apply`.

IMPORTANT : un `tunnel-client run` déjà actif conserve sa configuration
précédente. Dans **son terminal existant**, effectuer `Ctrl+C`, puis :

```bash
tunnel-client doctor --profile ccer-direct
tunnel-client run --profile ccer-direct
```

Le même terminal doit avoir `CONTROL_PLANE_API_KEY` configuré. Ne jamais
afficher ou transmettre sa valeur.

Après redémarrage, **actualiser ou reconnecter** le plugin CCER dans
ChatGPT afin qu'il redécouvre le catalogue GUI-FIRST restreint. Tester
`ccer_desktop_status`, `ccer_desktop_capture`, puis une action de contrôle
inoffensive avec confirmation explicite. Certaines modifications de permissions
peuvent nécessiter de réautoriser le plugin côté ChatGPT. Une commande distante
ne peut pas augmenter les droits d'un processus qui tourne encore en observe.

4. Dans un espace ChatGPT autorisé : Plugins → Ajouter un serveur MCP
   personnalisé → Tunnel → sélectionner le tunnel CCER → examiner les outils,
   confirmer les autorisations, puis créer/installer le plugin. Mentionner
   ensuite `@CCER` dans le chat. La disponibilité dépend du compte,
   du rôle et des politiques du workspace.

**Ne pas activer** les options de débogage qui exposent les payloads, ni
l'interface d'administration à distance.

## Certifications disponibles sans accès au cloud

```bash
python3 -m unittest discover -s tests -v
python3 -m tests.live_direct_stdio
python3 -m tests.live_direct_control
```

La première certification lance un client MCP externe indépendant depuis
`/tmp`, vérifie une vraie capture Concat et un refus d'action en mode
lecture. La deuxième lance le profil contrôle dans un processus indépendant,
refuse une création invisible, capture Concat avant l'action, envoie
  seulement `Échap`, lit la capture après l'action et refuse un deuxième
  geste sans nouvelle capture.

Le test du **vrai tunnel authentifié** ne peut réussir qu'une fois le nouvel
ID, la clé runtime et les permissions ChatGPT disponibles. Ne jamais
déclarer la connexion directe ChatGPT active sur la seule base des tests
stdio ou d'un profil de démonstration.

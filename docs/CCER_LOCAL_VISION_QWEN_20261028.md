# CCER — Adaptateur visuel local Qwen3.5 0.8B (28 octobre 2026)

## Découverte matériellement vérifiée
Ollama est installé sur le poste Ubuntu ; son registre contient
`qwen3.5:0.8b` et `qwen3.5-0.8b-fast:latest`. Les deux manifestes
référencent le même blob SHA-256 de modèle de 1 036 034 688 octets ;
aucune deuxième copie des poids n'est requise.

`python3 -m ccer.vision_model` est une sonde de lecture seule : son
résultat réel a été `installed=true`, `ollamaLoopbackOnline=false`,
`ready=false`, `inferencePerformed=false`, `modelDownloadPerformed=false`.
Le modèle n'a **pas** été lancé ni téléchargé. Le statut réutilise
la mesure CPU/RAM du moteur audiovisuel, et expose
`heavyInferenceAllowed=false` sous pression critique. Aucun modèle
n'est alors chargé. L'absence de service est
un blocage d'exécution d'inférence réel, non une preuve d'incompatibilité
du modèle. L'état actuel du poste est sous forte pression CPU/RAM.

## Interfaces MCP
- `ccer_vision_model_status` : vérifie le manifeste, le digest, la
  présence et taille exacte du blob, et la disponibilité TCP locale
  sur 127.0.0.1:11434, sans démarrer de processus.
- `ccer_vision_frame` : exige un fichier vidéo dans CCER_ROOT et
  `timeSeconds` valide, décode **une seule** image 480 pixels avec
  le décodeur FFmpeg préexistant `ccer.timecoded_review._frame`, calcule
  SHA-256 des octets JPEG, puis propose ces octets exclusivement au
  serveur Ollama de loopback via `/api/generate`. Pas de transfert cloud,
  pas de proxy HTTP, refus des redirections, `stream=false`,
  `num_ctx=1024`, `num_predict=100`, `num_thread=2`,
  `keep_alive=0s`. Aucune image temporaire sur disque.

La réussite n'est proclamée que si Ollama renvoie un HTTP 200 et une
réponse JSON non vide et bornée. L'output précise
`semanticAccuracyIndependentlyVerified=false` et `audioUnderstood=false`.
Whisper de Concat conserve seul le rôle de transcription de la parole ;
un VLM sur une image ne prétend ni entendre la bande sonore ni confirmer
le sens de toute une vidéo.

## Recette et limites
`python3 -m unittest tests.test_vision_model -v` couvre refus offline
avant tout décodage, manipulation de chemin, horodatage invalide, manifeste
falsifié, image ancrée par SHA, réponse HTTP locale simulée et non-fuite
JPEG. Les simulations certifient le contrat Python et l'intégration MCP,
**pas l'inférence réelle du modèle sur la machine**.

Documentation du modèle : https://ollama.com/library/qwen3.5
Le lancement d'Ollama et la qualification de la qualité des descriptions
sur plusieurs images/sons restent nécessaires pour valider la phase 5.

## Blocage système Ollama diagnostiqué

L'unité `/etc/systemd/system/ollama.service` est activée mais échoue
avec `217/USER`. Elle impose `User=ollama` et `Group=ollama`;
`getent passwd ollama` retourne code 2 (compte absent).
Le service ne peut donc pas ouvrir le port 11434.

Le drop-in système utilise `OLLAMA_ORIGINS=*`, `OLLAMA_KEEP_ALIVE=24h`,
`OLLAMA_CONTEXT_LENGTH=8192`, `MemorySwapMax=0` et
`OOMScoreAdjust=-800`. Un redémarrage immédiat serait inadapté :
le compte de service doit être réparé, les origines restreintes et
les budgets mémoire/CPU et la durée de rétention bornés.
CCER n'a pas modifié `/etc`, ni redémarré le service, ni téléchargé
de poids supplémentaires, ni prétendu effectuer une inférence réelle.

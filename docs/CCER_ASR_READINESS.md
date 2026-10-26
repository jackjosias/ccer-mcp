# CCER — Vérification locale du moteur Whisper de Concat

Concat possède déjà un moteur `whisper.cpp` intégré. Le nouveau contrôle `ccer_asr_status` est **strictement en lecture seule**. Il n'importe aucun média, ne télécharge aucun modèle, ne lance pas de transcription et ne clique pas dans Concat.

- `ccer_asr_status({})` : présence, taille et indication de pression CPU/RAM **sans lire tout le modèle**. La taille seule ne garantit pas son intégrité.
- `ccer_asr_status({verifySha256:true})` : vérifie par SHA-256 le modèle local; cette opération lit ~488 Mo et reste facultative.
- `ccer_preflight` expose le même état sous `asr`, sans calculer de hash complet.

Modèle pris en charge et vérifié : `small` multilingue, `ggml-small.bin`, 487 601 967 octets, empreinte attendue issue de `concat-speech/src/transcribe.rs`. Sous Linux : `<XDG_DATA_HOME ou ~/.local/share>/app.concat.editor/whisper-models/`.

Le champ `resourceAdvisory` signale une charge CPU/RAM potentiellement défavorable. **Il n'atteste pas de la réussite d'une transcription.** La validation complète impose une source de parole autorisée, un test réel dans « Sous-titres/Transcripteur » de Concat, la vérification des mots et des timecodes, et un projet test distinct. Le pilotage direct reste GUI-FIRST et ne peut pas faire d'écritures invisibles.

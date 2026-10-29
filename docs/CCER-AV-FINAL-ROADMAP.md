# CCER — Feuille de route finale audiovisuelle (28 octobre 2026)

## Objectif
Voir, écouter, comprendre, monter sur le véritable Concat Desktop, vérifier chaque export.

## Règles non négociables
- GUI-FIRST : les gestes de montage restent visibles dans Concat sur le bureau humain.
- Les outils FFmpeg en lecture seule peuvent extraire des images en mémoire.
- Jamais de transcription inventée : distinguer un SRT fourni et un ASR exécuté.
- Réutiliser timecoded_review, rhythm, quality, Concat Whisper et l'export SRT.
- Tous fichiers sous la racine autorisée CCER_ROOT, sans destruction des médias.
- Buffers bornés et nettoyage ; aucune capture permanente inutile.

## Phases et critères d'acceptation
1. Fondation native CCER/Concat — PASS précédent : véritable GUI et MP4 1080p.
2. Vidéo horodatée — EXISTANT : fenêtres paginées, JPEG, scènes/noirs/silences.
3. Sous-titres et image/audio — VALIDÉ AU NIVEAU MCP LOCAL : lecture SRT,
   véritables images et courts segments audio PCM/WAV synchronisés, sans création
   de fichiers intermédiaires. Outils ccer_transcript_read, ccer_av_timeline
   (includeAudio explicite) et ccer_audio_window (0,25 à 10 s). La capacité du
   client ChatGPT à percevoir sémantiquement les blocs audio MCP reste à certifier.
4. Écoute réelle Whisper — EXPORT SRT NATIF + SYNCHRO SOURCE VALIDÉS :
   Concat PID 101086, projet `Untitled project 8` et média parlé 5,705 s.
   Modèle Small Multilingual existant : texte transcrit sur la piste Concat.
   Le bouton Save du dialogue GTK externe `Exporter en SRT…` a été actionné
   **une seule fois** avec AT-SPI natif, sans souris X11 ni clavier simulé,
   après contrôle de l'identité du dialogue, du nom et de l'absence d'écrasement.
   Export réellement vérifié : `~/Desktop/Concat/Untitled project 8/Untitled project 8.srt`
   (117 octets), un cue de 00:00:00,900 à 00:00:06,500, phrase anglaise.
   `ccer.native_srt_acceptance` a lu ce SRT et le vrai MP4 ; compensation
   explicite de la position +0,900 s dans `ccer_transcript_read`,
   `ccer_av_timeline` et `ccer_av_events` : cue source de 0,000 à
   5,600 s, deux vraies images décodées associées au cue, audio présent,
   zéro JPEG local persistant. Anciennes requêtes offset=0 inchangées.
   `caption_layout` signale un bloc de texte trop long ; qualité de la
   transcription comparée indépendamment à l'écoute encore à certifier.
   Le contrôle de provenance du parseur reste `external_srt_unverified`
   (le parseur ne prétend pas exécuter lui-même Whisper).
5. Vision légère — OUTILS EXISTANTS CONSERVÉS, AUCUN MODÈLE AJOUTÉ :
   FFmpeg/FFprobe extraient des images JPEG horodatées directement en mémoire ;
   ccer_timecoded_review / ccer_av_timeline les transmettent par blocs image
   MCP pour inspection visuelle par le client. ccer_desktop_capture montre
   la vraie fenêtre Concat ; scène, noir, couleur et silence restent des
   mesures techniques, sans prétendre comprendre automatiquement l'image.
   Whisper intégré à Concat traite les paroles. Sur demande de l'utilisateur,
   tout l'adaptateur Qwen/Ollama ajouté à CCER a été retiré, sans supprimer
   les modèles préexistants ailleurs sur la machine.
   Le pont natif Slint a permis trois gestes confirmés BEFORE/AFTER,
   mais l'aperçu vidéo reste noir même à l'intérieur du clip : anomalie
   de rendu ouverte, voir docs/CCER_NATIVE_GUI_RECOVERY_20261028.md.
   Cycle de vie natif idempotent réconcilié sur la machine réelle :
   unique Concat instrumenté PID 120739, fenêtre 0x03a00005,
   statut Slint inputReady=true ; deuxième appel ATTACHED sans spawn.
   Commande et invariants : docs/CCER_NATIVE_IDEMPOTENT_LIFECYCLE_20261028.md.
   L'inspection intégrale en temps réel reste à qualifier.
6. Quasi temps réel — RELECTURE PROGRESSIVE TESTÉE, LIVE NON ACQUIS :
    ccer_av_events conserve la pagination ; ccer_av_replay_poll relit une
    fenêtre enregistrée par appel avec curseur, pression CPU/RAM mesurée,
    budget adaptatif de 1 à 4 images ; includeFrames=true transmet les JPEG
     MCP issus du même décodage, sans fichier temporaire ni seconde passe.
     Pause par consumerReady=false
    sans décodage. La latence locale par fenêtre est mesurée, sans
    prétendre mesurer une latence live bout-en-bout. Pas de troncature.
    Vidéo réelle MPEG-4/AAC et 22 tests ciblés PASS ; ni caméra/micro
    en continu, ni worker permanent, ni garantie de latence ou de sémantique.
7. Réalisation professionnelle — À VALIDER : vrai rush parlé de plusieurs
   minutes, coupes, titres, transitions, mix audio, sous-titres et MP4 décodé.
8. Recette finale — Base Python 216/216 PASS (28 oct. 2026) ; Rust concat-core 60 tests
   unitaires et 2 doctests PASS, git-diff-check
   PASS, zéro erreur IDE, fork Rust propre, rustfmt --check PASS (fork Concat). Le nettoyage des preuves CCER a
   supprimé les 29 aperçus historiques (393 185 octets), dossier vidé ;
   timer existant actif/activé. Restent à qualifier : Rust natif complet,
   perception sémantique des sons et images, vrai montage parlé de plusieurs
   minutes, streaming véritablement continu avec latence mesurée, connecteur
   MCP distant et QA créative finale.

Ne jamais prétendre que les phases 4 à 8 sont validées sur une vidéo muette de 2 s.

## Actualisation terrain — 29 octobre 2026

- **Aperçu arrêté après seek corrigé (PASS GUI réelle)** : binaire Concat 0.2.8 reconstruit, fork commit `e21c997`. Deux positions vidéo différentes dans la fenêtre Slint ont produit une image non noire avec sous-titres, mesures YAVG 125,59 et 125,47. Contrôle AVANT/APRÈS et aucun clic physique X11.
- **Montage long natif partiellement validé** : scratch `~/Desktop/Concat/Untitled project 9`, source H.264/AAC copiée sans réencodage (180,063 s), glisser-déposer natif et deux `SplitClips` réalisés. Trois segments `c2`, `c3`, `c5` couvrent les 180,063 s. Le projet `Untitled project 8` et son SRT restent intacts.
- **Export GPU réel commencé le 29 octobre** depuis Concat, Intel HD 520, H.264/AAC 1920×1080. Au dernier contrôle à 23 h 08, le rendu était encore en cours, 49 % confirmé visuellement et fichier temporaire `~/Videos/.Untitled project 9.concat-video.mp4` > 100 Mo. **Ce fichier n'est pas un livrable final tant que l'encodeur ne l'a pas finalisé et que FFprobe/FFmpeg ne l'ont pas validé.**
- **Régressions** : 229 tests Python PASS avant le rendu ; relance intégrale pendant l'export expirée, donc sans verdict. `cargo fmt` et contrôles Git PASS. Tests Rust natifs lourds non certifiés.
- **Gestion du stockage** : `preview-before-*` désormais pris en charge par le collecteur borné, tests de non-suppression des médias et de refus des liens symboliques (11/11 PASS), commit principal `5d4f78a`. Le collecteur a retiré 11 preuves expirées (211267 octets).
- **Encore ouverts** : MP4 final certifié avec son et image, titres, transitions, mixage et SRT d'un montage long, qualité audio sémantique contrôlée, streaming AV continu mesuré et tests Rust natifs complets. Ne pas assimiler décodage FFmpeg ou présence d'audio à une écoute sémantique.

## Certification terrain — reprise du 29 octobre 2026 (après finalisation)

- **Export natif Concat terminé et retrouvé sur disque** : `~/Videos/Untitled project 9.mp4`, 194 346 686 octets, SHA-256 `8a2a2228193660753646723afd07758dc3d3679de43a6769e5f6d6c74ffecf45`. La capture native Slint du PID `114239` confirme visuellement « Exporté · 188 MB » et « 3 clips », sans lancement d'un second encodeur.
- **Conteneur et flux PASS** : `ffprobe` exit 0, MP4 H.264 1920×1080 à 24 images/s, AAC 48 kHz stéréo, durée 183,458333 s ; comptage du fichier entier : 4 403 paquets vidéo et 8 599 paquets audio.
- **Décodage intégral PASS** : FFmpeg `-xerror -threads 2 -i <export> -map 0:v:0 -map 0:a:0 -f null -` exécuté du début à la fin, exit 0 et aucune erreur de décodage émise. Une première tentative plafonnée à 180 s avait expiré, sans être comptée comme PASS.
- **Timeline persistante** : trois segments `c2` (11,750 s), `c3` (88,039 s) et `c5` (80,274 s), couvrant le rush source de 180,063 s sur T4. Le décalage initial de 3,4 s donne un export de 183,458 s dans la tolérance d'une image.
- **Non-régression du projet de référence** : `Untitled project 8/concat.json` SHA-256 `d20622f62cc694838d0935298ec5a9e21a0c56bf7fdcea8f10237d92feff7291` et SRT SHA-256 `9d8d684b21f5f490991ff0258270db11efb6007d750e8568c99f8427b8de9ca7` inchangés.
- **Résiduels non certifiés** : montage professionnel de plusieurs minutes avec titres, transitions, mixage et SRT, compréhension sémantique de la voix et des images, vrai flux AV continu à latence mesurée, batterie Rust native complète et essai MCP distant. La validation technique de l'export ne clôt pas ces critères.

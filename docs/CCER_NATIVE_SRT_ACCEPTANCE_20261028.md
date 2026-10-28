# CCER — Recette SRT native du 28 octobre 2026

Chaîne vérifiée sur le seul Concat déjà ouvert, sans deuxième instance :
import autorisé d'un MP4 parlé (5,705 s), insertion en timeline à 0,900 s,
transcription par le modèle Whisper Small Multilingual déjà installé,
titre persistant vérifié dans `concat.json`, ouverture de l'export SRT natif,
acceptation unique du bouton GTK Save par AT-SPI, fichier SRT lu sur disque.

## Fichier de sortie réel
`~/Desktop/Concat/Untitled project 8/Untitled project 8.srt` (117 octets).
Il contient un cue de 00:00:00,900 à 00:00:06,500 avec le texte reconnu :
« Hello friends, welcome to our video editor, this is a real speech recognition test. »

## Justesse des deux bases de temps
La vidéo source dure 5,705 s et son clip sur la timeline commence à 0,900 s.
L'export natif porte les timestamps **de la timeline**, non ceux de la
vidéo source. Le parseur existant `av_timeline.read_srt` accepte désormais
le paramètre explicite `timeline_offset_seconds=0.9`; par défaut il reste 0.
Résultat : 0,000 → 5,600 s en temps source. La revue réelle produit deux
images décodées aux secondes 1,000 et 3,000, toutes deux associées au cue ;
audio AAC effectivement présent. Aucun JPEG permanent de revue n'est créé.

La commande de lecture seule réutilisable est `python3 -m
ccer.native_srt_acceptance --media-root ROOT --project-root PROJET
--video VIDEO.mp4 --srt TITRES.srt --timeline-offset 0.9`. Les racines
sont vérifiées, les symlinks SRT refusés, et les images encodées ne sont
jamais recopiées dans le JSON de sortie.

## Limites non levées
Le cue unique dépasse les recommandations de lisibilité (avertissement
`caption_layout`), la comparaison phonétique des mots à la piste sonore
n'est pas une certification indépendante, aucun VLM n'a identifié le sens
de toutes les scènes/sons. Il manque toujours un flux adaptatif quasi réel,
un véritable montage professionnel parlé de plusieurs minutes, la recette
Rust et la validation du pont MCP distant. Ne pas traiter le fixture synthétique
comme une recette créative finale.

## Sécurité
Le pont AT-SPI est limité au dialogue GTK `Exporter en SRT…` du projet
de test `Untitled project 8`, demande `--confirm`, vérifie avant le geste
que le fichier cible n'existe pas et n'autorise aucune tentative répétée
automatique. Après le succès, son préflight doit refuser une nouvelle
écriture. Le projet, la source et les anciens exports sont préservés.

## Rétention des captures temporaires (28 octobre 2026)
Le gestionnaire existant `ccer.evidence_retention.prune` traite désormais
également les **familles strictement reconnues** de JPEG de diagnostic
historiques, sans changer les protections des reçus natifs avant/après :
âge supérieur ou égal à 30 minutes, fichier régulier possédé par l'utilisateur,
taille au maximum 2 Mio, refus des liens symboliques et des photos non reconnues.
La recette réelle `python3 -m ccer.visible_desktop cleanup` a supprimé
29 aperçus (393 185 octets) et laissé 0 fichier dans le dossier géré.
Le timer périodique `ccer-scratch-gc.timer` est actif et activé.
Les sources, projets, exports MP4 et SRT restent conservés ; aucune copie
stockée par ChatGPT dans le cloud n'est supprimable par ce nettoyage local.

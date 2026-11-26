# CHANGELOG — CCER

Historique chronologique du **Creative Engineering Runtime**, du **plus récent au plus ancien**. Les dates sont des jalons de code vérifiés par l'historique Git du dépôt CCER, pas des numéros de version inventés.

> **Important : SOURCE ≠ LIVE.** Un commit ou une campagne de tests ne garantit pas que le binaire Concat utilisé actuellement, l'extension MCP ou le connecteur ChatGPT ait été activé. Les limites et blocages restent signalés.

## 26 novembre 2026 — confiance et licence

- Ajout du texte AGPL v3 et clarification du régime de licence du code original CCER ; conservation des licences tierces.
- Badge M8ven dans le README ; la note et la vérification de l’éditeur restent indépendantes et ne sont pas garanties par ce badge.

## 17 novembre 2026 — préparation du Concat instrumenté

- `651442a` — tests de réconciliation native et fixtures scratch rendus plus portables.
- `6d495fe` — vérification CI GitHub Actions des patchs Concat épinglés.
- `bfdb647` — mode de build natif Cargo à consommation de ressources réduite.

**État :** commits SOURCE présents. Ni compilation réussie sur tous les systèmes ni activation LIVE ne se déduisent de leurs titres.

## 31 octobre 2026 — installation native reproductible

- `ab0a6a2` — téléchargement des dépendances Cargo soumis à un opt-in explicite.
- `fa7bf89` — préparation de Concat/Slint à partir de sources et patchs vérifiés.

**Limite :** la préparation du build ne constitue pas une preuve d'interaction avec la vraie interface.

## 30 octobre 2026 — installation, interface et exports

**Livraison source :**

- `f8adf7f` — gestion de l'AppImage Concat officielle et documentation d'installation MCP.
- `c0384b4` — vérification d'une frame Slint revue et exécution unique du geste dans la même session.
- `254b35f` — saisie de texte Slint bornée et contrôlée par reçus.
- `db9a623` — lancement visuel autorisé malgré une alerte ressources après décision explicite.

**Rapports de qualification archivés :**

- `c72bfb0` — export final et correction de timeline sans interstice.
- `a7f744b` — titre/dissolve et blocages ASR/export restant à lever.
- `f990af9` — export Concat natif de trois minutes consigné.
- `e914a04` — baseline de timeline `project9`.
- `1d9efc3`, `2033845` — mesures audio et jalon de saisie native.
- `841175d`, `888eeca` — charge machine, recommandations et suivi Rust.

**Preuve :** ces références correspondent à des commits. Les résultats publiés dans leurs guides ont leur propre portée ; aucune garantie LIVE actuelle n'est déduite de ces intitulés.

## 29 octobre 2026 — sécurité des images et suivi des jalons

- `8738c5c` — état documentaire des jalons A/V natifs et QA résiduelle.
- `5d4f78a` — expiration prudente des images `before` déjà revues.

**Règle :** ne jamais rejouer un geste à partir d'une capture périmée.

## 28 octobre 2026 — revue audiovisuelle locale et Whisper

**A/V :**
- `ff55374` — JPEG de replay optionnels produits dans **la même passe FFmpeg**.
- `50e49db` — polling audiovisuel borné avec adaptation à la charge.
- `e3e91f1` — événements A/V paginés disponibles sur MCP.
- `5c25df3` — inspection temporelle de médias autorisés.
- `22e6c38`, `01ee8b6` — audio réel et curseur A/V borné.
- `ba2cde2` — synchronisation vidéo et SRT.

**Parole :**
- `0faa0de` — acceptation du SRT via le portail GTK et alignement des timecodes.
- `e0c06f9` — audit des captions sauvegardées.
- `e605ed4` — cas négatifs SRT dupliqué/ambigu.
- `e344b56` — progression Whisper et blocages documentés.

**Sûreté et architecture :**
- `fa346ba` — nettoyage ciblé de captures possédées par CCER.
- `5ae8851` — réconciliation idempotente d'une instance Concat visible.
- `335ca36` — **suppression de l'intégration expérimentale Qwen/Ollama** afin de conserver la voie légère FFmpeg + captures authentiques.

Les anciens commits `39b535b` et `092c2f6` relatifs à une piste Qwen **ne décrivent pas une fonctionnalité actuelle** : `335ca36` la retire.

**Preuve historique :** des campagnes ciblées du 28 octobre avaient donné 216 tests Python réussis, mais une suite réussie ne certifie pas l'exécution GUI complète. Certains essais natifs ont connu des timeouts sous forte charge ; ne pas extrapoler une homologation globale.

## 26–27 octobre 2026 — isolation et ressources

- `0f26307` — test de refus d'un reçu natif falsifié sur X11.
- `778fe04` — protection face aux sessions Xvfb privées.
- `71cf146` — refus de repli vers le bureau humain si Slint expire.
- `4c44449` — prévention des lancements de GUI supplémentaires sous surcharge.
- `e18d2e6` — mode Direct passif et visuel par défaut.
- `c620aa3` — audit audio Talaxeum en lecture seule.

**Invariant :** une fenêtre Concat privée sous Xvfb ne représente pas automatiquement la fenêtre personnelle de l'utilisateur.

## Sources et règles de maintenance

- [Index documentaire](docs/README.md)
- [Revue par timecode](docs/CCER_TIMECODED_REVIEW.md)
- [Whisper](docs/CCER_ASR_READINESS.md)
- [Pont natif](docs/CCER_NATIVE_SETUP.md)

Chaque ajout doit séparer : **date, problème, modification, commit, tests datés, activation LIVE confirmée ou non et risques restants**. Conserver les anciens jalons ; insérer les nouvelles entrées en haut.

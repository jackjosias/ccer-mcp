# Politique de sécurité — CCER

CCER peut examiner des médias et interagir avec une vraie fenêtre Concat. **La protection du bureau humain, des rushs, des exports et des secrets est prioritaire.**

## Signaler une vulnérabilité

Ne publier ni jeton ni média privé dans une issue. Utiliser **Security → Report a vulnerability** sur [GitHub](https://github.com/jackjosias/ccer-mcp/security) **si activé**, ou contacter [@jackjosias](https://github.com/jackjosias) en privé par un canal convenu. Aucun e-mail de sécurité ni délai garanti n'est supposé.

Un bug ordinaire peut être signalé avec version, reproduction minimale, comportement attendu et logs **expurgés**.

## Garanties et limites

| Risque | Garde attendue |
|---|---|
| Mauvaise fenêtre | Vérification de classe, PID et session Slint |
| Geste non autorisé | Confirmation explicite et capture avant récente |
| Mutation invisible | **GUI-FIRST** côté connecteur Direct |
| Bureau humain perturbé | Pas d'injection X11 physique ou de vol de focus |
| Timeout ambigu | Ne pas rejouer une action sensible aveuglément |
| Chemin arbitraire | Refus des écritures hors racine autorisée |
| Perte de médias | Conservation des sources/exports et GC limité |
| Fuite de secrets | Exclusion Git et expurgation |

**Un refus de sécurité ne doit jamais être contourné via un autre outil ou un shell.** Ces défenses applicatives ne constituent pas une sandbox OS exhaustive.

## Contrat de contrôle natif

1. Identifier la bonne session Concat.
2. Obtenir une capture authentique **AVANT**.
3. Vérifier la fraîcheur et les autorisations.
4. Exécuter une seule action native.
5. Examiner la capture **APRÈS**.
6. Arrêter si l'état est ambigu.

L'envoi d'une action ne prouve ni la réussite du montage ni celle de l'export.

## Confidentialité et rétention

Ne pas committer `.env`, identifiants, jetons, `automation.json`, médias privés, captures personnelles ou chemins sensibles. Ne supprimer **aucun rush ni export utilisateur** pour libérer de l'espace. Les nettoyages portent uniquement sur les artefacts temporaires CCER identifiables.

Les chaînes SHA détectent certaines altérations, mais ne prouvent pas l'identité de l'auteur du journal. Les images éventuellement transmises à un client cloud ne peuvent être déclarées supprimées à distance sans preuve.

## Guides

[GUI-FIRST](docs/CCER_GUI_FIRST_CONTRACT.md) · [Focus](docs/CCER_FOCUS_ISOLATION.md) · [Rétention](docs/CCER_TEMPORARY_MEDIA_RETENTION.md) · [Installation native](docs/CCER_NATIVE_SETUP.md) · [CHANGELOG](CHANGELOG.md) · [CONTRIBUTING](CONTRIBUTING.md).

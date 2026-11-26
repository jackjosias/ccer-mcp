# CCER privacy policy / Politique de confidentialité

Effective: 2026-11-26. Applies to the open-source CCER MCP gateway in this repository, not to Concat Desktop or third-party MCP clients and services.

## Data processed and purpose

CCER is a self-hosted gateway for authorized video editing and media inspection. It may process project paths and metadata, source media, audio samples, video frames, subtitles and transcripts, Concat window screenshots, tool arguments and results, session information, and technical audit records. Processing supports requested editing, analysis, permission checks, verification and troubleshooting. The local operator chooses the permitted media root, client and access profile. Only process media and personal data you are authorized to use.

## Local processing, transmission and third parties

FFmpeg/FFprobe and the documented Concat Whisper workflows run locally. CCER can return image, audio and text evidence to the connected MCP client; results are not necessarily local-only when a remote or cloud client is configured. The optional authenticated tunnel transports MCP requests and responses through its configured provider. That provider and the client may process or retain transmitted content under their own policies. Review their terms and limit sensitive content. CCER cannot delete copies held by a remote client.

Explicit installation and native preparation workflows may contact GitHub or its release infrastructure to obtain software. GitHub independently operates this public repository. Do not submit private media, credentials or unredacted logs in public issues. The project does not offer a hosted media-upload or advertising service through this repository.

## Local storage and retention

- User media, project files and final exports are preserved by CCER temporary-file cleanup; manage them yourself.
- Sampled frames may be held in memory and returned to the MCP client. Local cleanup does not govern copies outside CCER.
- Recognized legacy desktop evidence has a nominal 30-minute retention and a 32 MiB quota. Expiry is opportunistic (or via a configured cleanup timer); active action receipts are protected. Not all Concat caches, backups or native evidence are covered.
- Managed render scratch files are cleaned at job completion and may be recovered after interruption. The local audit journal (`.ccer/audit.jsonl`) and other project records can persist; no universal automatic deletion period is claimed.
- Configuration and authentication credentials are managed locally or by the chosen provider. Never commit credentials or private files.

See [temporary media retention](docs/CCER_TEMPORARY_MEDIA_RETENTION.md) and [direct tunnel setup](docs/CCER_DIRECT_TUNNEL.md).

## Access and safeguards

The Direct observe profile rejects write operations. Direct control requires an authorized, instrumented Concat session and GUI-FIRST checks. Path boundaries, private scratch/evidence directories, explicit confirmation for guarded operations and audit records reduce risk; they are not a complete operating-system sandbox or guarantee of confidentiality. Configure least privilege, keep dependencies current and protect your account and filesystem.

## User choices and contact

The local operator controls the installation and can disconnect the MCP client, revoke credentials through the relevant provider, inspect stored records and manage retained files. Do not remove active action evidence until the operation is reconciled. Requests concerning third-party processing should be directed to that provider. For privacy questions concerning CCER, contact the maintainer [@jackjosias](https://github.com/jackjosias) through a private agreed channel; follow [SECURITY.md](SECURITY.md) for security reports. Share only redacted information.

This policy describes documented software behavior, not a certification of regulatory compliance. Changes are tracked in the repository.

## Résumé en français

CCER est une passerelle MCP auto-hébergée. Elle traite les médias autorisés, métadonnées, captures, extraits audio, sous-titres et traces techniques nécessaires au montage et à sa vérification. Les traitements FFmpeg et Whisper documentés sont locaux, mais les résultats transmis au client MCP ou au tunnel peuvent être traités par des services tiers. Le nettoyage CCER ne supprime pas automatiquement les rushs ni les exports finaux ; les preuves temporaires reconnues ont une rétention nominale de 30 minutes, avec exceptions. Les journaux et autres données de projet peuvent persister. Le propriétaire maîtrise les accès, les fichiers et la révocation des identifiants. Contact : [@jackjosias](https://github.com/jackjosias), via un canal privé convenu.

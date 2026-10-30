# CCER — Scratch propriétaire, rétention et récupération après crash

## Portée réelle

Le gestionnaire `ccer/temp_lifecycle.py` fournit un espace de travail
**strictement temporaire par opération**, étiqueté par projet. Il reprend le
principe éprouvé de `tempfile.TemporaryDirectory` et ajoute une provenance
persistante et une récupération après crash. Le moteur `director_render`
utilise désormais ce mécanisme sans changer son pipeline vidéo FFmpeg.

* L'espace scratch se situe sous le root CCER autorisé :
  `<CCER_ROOT>/.ccer/scratch-jobs/job-<uuid>`.
* Le dossier appartient au compte Ubuntu et est privé (0700).
  Le manifeste `.ccer-scratch.json` porte le contrat, l'UUID, le projet,
  l'opération, le PID, son instant de démarrage noyau et l'heure de création.
* Sortie normale, erreur FFmpeg ou exception Python : suppression des fichiers
  de l'espace scratch **immédiatement à la fin du contexte**.
* Crash machine ou arrêt forcé du processus : le manifeste permet la reprise.
  Après **24 heures**, un dossier est récupérable uniquement si le processus
  propriétaire n'est plus actif. Le vérificateur refuse les symlinks,
  les propriétaires incorrects, les chemins hors espace et les fichiers
  spéciaux. Un processus non inspectable reste **protégé**.
* Un nouveau rendu recherche et élimine opportunément les anciens jobs
  admissibles. Un timer système utilisateur refait cette tâche une fois par
  jour, même après une coupure, via `Persistent=true`.
* Les nouveaux rendus sont refusés s'il reste moins de **2 GiB libres**,
  afin d'éviter une saturation totale du disque. Ce seuil est un garde-fou
  initial, **pas un quota de taille effectif pendant le rendu**.

## Inspection sûre

Par défaut, toutes les actions sont en **simulation sans suppression** :

```bash
cd /home/your-user/WORKSPACE-LOGICIEL/concat/ccer-mcp
python3 -m ccer.temp_lifecycle status --root "$HOME/Videos/CCER"
```

Pour récupérer les jobs admissibles : 

```bash
python3 -m ccer.temp_lifecycle sweep --root "$HOME/Videos/CCER" --confirm
```

Cette commande NE supprime PAS les exports dans `Movies`, les médias sources
dans `Videos`, les dossiers de projet Concat, ni les JPEG de preuve gérés
séparément par `ccer/evidence_retention.py`.

## Automatisation systemd utilisateur

Deux unités sont fournies comme fichiers réutilisables sous `docs/` :

* `ccer-scratch-gc.service` : exécute successivement `sweep --confirm` sur le root approuvé et `ccer.visible_desktop cleanup` pour les JPEG/reçus expirés reconnus ;
* `ccer-scratch-gc.timer` : déclenchement quotidien, `Persistent=true`,
  délai aléatoire maximum de 30 minutes.

État installé sur l'Ubuntu utilisateur le 26 octobre 2026 :

```bash
systemctl --user is-enabled ccer-scratch-gc.timer
systemctl --user list-timers ccer-scratch-gc.timer --all
systemctl --user show ccer-scratch-gc.service -p Result -p ExecMainStatus
```

La configuration est distincte de `ccer-direct.service`, du tunnel WCER,
du tunnel Linux Chrome et du processus Concat Desktop visible.

## Limites et garanties

1. Seuls les dossiers créés par **ce gestionnaire** sont éligibles.
   Les temporaires d'autres applications ne sont pas touchés.
2. Les JPEG d'analyse `ccer_timecoded_review` circulent déjà en mémoire
   et ne sont pas stockés systématiquement comme fichiers. Les données
   envoyées à ChatGPT suivent en revanche la politique du service distant.
3. Le rendu FFmpeg est désormais supervisé toutes les 250 ms par `run_bounded_encoder` : arrêt du groupe de processus si son scratch dépasse 2 Gio, si l'espace libre descend sous 1 Gio ou si le délai autorisé est dépassé. Ces seuils sont des garde-fous contrôlés périodiquement, pas des quotas au niveau du système de fichiers : un léger dépassement est possible entre deux observations. Les productions plus longues exigent un budget dédié et des mesures de consommation.
4. Le cache natif interne de Concat, ses projets et les rendus exportés
   ne sont pas dans le périmètre du nettoyage CCER. Ils ne doivent pas
   être effacés sans contrat de propriété distinct et vérifié.
5. Le timer ne traite que le root `~/Videos/CCER`. Une future prise en
   charge de multiples roots requiert une liste d'autorisations explicite,
   jamais une exploration récursive du dossier personnel.

## Critères de sûreté couverts par les tests

* Réussite normale et exception : aucun fichier scratch résiduel.
* Reprise d'un job mort ancien, dry-run sans suppression.
* Refus de supprimer les jobs actifs et fichiers hors registre.
* Refus de symlink vers un média permanent.
* Refus d'opération quand le disque disponible est insuffisant.
* Arrêt et attente du processus encodeur lors d'un dépassement du budget scratch ; source préservée.
* Véritable rendu FFmpeg court : export préservé et dossier scratch entièrement nettoyé.

La cible durable est **zéro accumulation involontaire de médias temporaires**,
sans aucune promesse trompeuse d'effacement des médias déjà envoyés à un
fournisseur externe.

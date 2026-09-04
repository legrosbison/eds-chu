# EDS CHU

Projet de construction d'un Entrepôt de Données de Santé suivant une architecture médaillon : Lake → Bronze → Silver → Gold → dashboards.

## Démarrage rapide

Prérequis : Docker avec le plugin Compose et Python 3.12 ou supérieur.

```bash
python3 scripts/init_env.py
docker compose up -d --build
docker compose ps --all
```

`init_env.py` crée un fichier `.env` local avec une clé de pseudonymisation
aléatoire. Ce fichier est ignoré par Git et reçoit les permissions `0600`.
Conservez cette clé : la changer casserait la stabilité des pseudonymes.

Services disponibles :

| Service          | Adresse                      | Usage                      |
| ---------------- | ---------------------------- | -------------------------- |
| ClickHouse HTTP  | <http://localhost:8123/play> | Console SQL                |
| ClickHouse natif | `localhost:9000`             | Connexion des clients      |
| Metabase         | <http://localhost:3000>      | Dashboards                 |
| Scheduler        | conteneur Docker             | Pipeline quotidien à 02:00 |

Au premier lancement :

- le scheduler exécute immédiatement le pipeline puis le planifie chaque jour ;
- `metabase-setup` configure la connexion ClickHouse, les deux dashboards et
  les comptes de démonstration ;
- les identifiants locaux sont conservés dans `.env` et ne sont jamais publiés.

Le Compose initialise automatiquement les bases `bronze`, `silver`, `gold` et `audit`. Les volumes Docker conservent les données entre deux redémarrages.

Pour arrêter les services sans supprimer les données :

```bash
docker compose down
```

## Profilage des sources

Le rapport agrégé est disponible dans [docs/profilage-sources.md](docs/profilage-sources.md). Il ne contient aucune identité patient.

Pour le régénérer :

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python scripts/profile_sources.py
```

Résultats produits :

- `docs/profilage-sources.md` : rapport lisible ;
- `reports/source-profile.json` : résultat structuré pour les futurs contrôles automatisés.

## Modèles de données

### Bronze

- [Modèle Bronze et cours pédagogique](docs/data-model-bronze.md)

### Silver

- [Documentation et diagramme Mermaid](docs/data-model-silver.md)
- [Modèle HTML interactif](docs/data-model-silver-interactif.html)

Pour utiliser toutes les interactions, clonez le dépôt puis ouvrez `docs/data-model-silver-interactif.html` dans un navigateur.

Le modèle est une constellation constituée de :

- cinq dimensions : patient, service, date, diagnostic et CCAM ;
- quatre faits : séjour, diagnostic associé, relevé de monitoring et acte médical.

### Gold

- [Modèle Gold, formules et explication des KPI](docs/data-model-gold.md)

Gold contient les six KPI initiaux et les cinq KPI de l'évolution : activité et
DMS par catégorie, actes par service et par type, densité par lit et montant
facturé par service.

## Dashboards et exploitation

- [Description des dashboards et démonstration des droits](docs/dashboards-metabase.md)
- [Guide d'exploitation, journaux et reprise sur incident](docs/exploitation.md)

Les dashboards peuvent être reprovisionnés sans doublons :

```bash
python3 scripts/setup_metabase.py
```

Pour suivre le traitement quotidien :

```bash
docker compose logs -f scheduler
```

Les données sources et les PDF du cours ne sont volontairement pas publiés dans ce dépôt.

## Pipeline Lake → Bronze → Silver → Gold

Le pipeline complet se lance avec une seule commande :

```bash
python3 scripts/run_pipeline.py
```

Il réalise successivement :

1. la détection incrémentale des fichiers et leur copie versionnée dans le Lake ;
2. la pseudonymisation HMAC-SHA256 des patients avant leur entrée dans le Lake ;
3. le chargement typé et traçable des tables Bronze ;
4. les contrôles, rejets et transformations SQL vers les dimensions et faits Silver ;
5. le calcul des tables Gold et des KPI prêts pour Metabase.

Un deuxième lancement ne recharge pas les fichiers déjà réussis. Pour exécuter
une partie seulement :

```bash
python3 scripts/ingest_lake.py --dry-run
python3 scripts/run_pipeline.py --step lake
python3 scripts/run_pipeline.py --step bronze
python3 scripts/run_pipeline.py --step silver
python3 scripts/run_pipeline.py --step gold
```

Pour débuter, retenez seulement `python3 scripts/run_pipeline.py` : les options
par étape servent surtout à comprendre ou à reprendre un traitement.

Le fonctionnement, les règles de reprise et les volumes contrôlés sont détaillés
dans [la documentation du pipeline](docs/pipeline-lake-bronze-silver.md).

## État du projet

- [x] Analyse du sujet
- [x] Modèle Silver et relations
- [x] Exploration et profilage des sources
- [x] Environnement Docker avec ClickHouse et Metabase
- [x] Ingestion incrémentale et pseudonymisation
- [x] Tables Bronze puis transformations SQL Silver
- [x] Tables Gold et KPI
- [x] Dashboards pilotage et recherche
- [x] Orchestration, journalisation et documentation d'exploitation
- [x] Évolution du 29 août : services enrichis, CCAM, actes et nouveaux KPI

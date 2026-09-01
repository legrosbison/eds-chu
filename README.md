# EDS CHU

Projet de construction d'un Entrepôt de Données de Santé suivant une architecture médaillon : Lake → Bronze → Silver → Gold → dashboards.

## Démarrage rapide

Prérequis : Docker avec le plugin Compose et Python 3.12 ou supérieur.

```bash
python3 scripts/init_env.py
docker compose up -d
docker compose ps
python3 scripts/run_pipeline.py
```

`init_env.py` crée un fichier `.env` local avec une clé de pseudonymisation
aléatoire. Ce fichier est ignoré par Git et reçoit les permissions `0600`.
Conservez cette clé : la changer casserait la stabilité des pseudonymes.

Services disponibles :

| Service          | Adresse                      | Usage                 |
| ---------------- | ---------------------------- | --------------------- |
| ClickHouse HTTP  | <http://localhost:8123/play> | Console SQL           |
| ClickHouse natif | `localhost:9000`             | Connexion des clients |
| Metabase         | <http://localhost:3000>      | Dashboards            |

Au premier lancement de Metabase, créez le compte administrateur puis ajoutez une base ClickHouse avec :

- hôte : `clickhouse` ;
- port : `8123` ;
- base par défaut : `gold` ;
- utilisateur et mot de passe : valeurs de `.env`.

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

- quatre dimensions : patient, service, date et diagnostic ;
- trois faits : séjour, diagnostic associé à un séjour et relevé de monitoring.

Les données sources et les PDF du cours ne sont volontairement pas publiés dans ce dépôt.

## Pipeline Lake → Bronze → Silver

Le pipeline complet se lance avec une seule commande :

```bash
python3 scripts/run_pipeline.py
```

Il réalise successivement :

1. la détection incrémentale des fichiers et leur copie versionnée dans le Lake ;
2. la pseudonymisation HMAC-SHA256 des patients avant leur entrée dans le Lake ;
3. le chargement typé et traçable des tables Bronze ;
4. les contrôles, rejets et transformations SQL vers les dimensions et faits Silver.

Un deuxième lancement ne recharge pas les fichiers déjà réussis. Pour exécuter
une partie seulement :

```bash
python3 scripts/ingest_lake.py --dry-run
python3 scripts/run_pipeline.py --skip-lake
python3 scripts/run_pipeline.py --skip-bronze
```

Le fonctionnement, les règles de reprise et les volumes contrôlés sont détaillés
dans [la documentation du pipeline](docs/pipeline-lake-bronze-silver.md).

## État du projet

- [x] Analyse du sujet
- [x] Modèle Silver et relations
- [x] Exploration et profilage des sources
- [x] Environnement Docker avec ClickHouse et Metabase
- [x] Ingestion incrémentale et pseudonymisation
- [x] Tables Bronze puis transformations SQL Silver
- [ ] Tables Gold et KPI
- [ ] Dashboards pilotage et recherche
- [ ] Orchestration, journalisation et documentation d'exploitation

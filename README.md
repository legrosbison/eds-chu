# EDS CHU

Projet de construction d'un Entrepôt de Données de Santé suivant une architecture médaillon : Lake → Bronze → Silver → Gold → dashboards.

## Démarrage rapide

Prérequis : Docker avec le plugin Compose et Python 3.12 ou supérieur.

```bash
cp .env.example .env
docker compose up -d
docker compose ps
```

Services disponibles :

| Service | Adresse | Usage |
|---|---|---|
| ClickHouse HTTP | <http://localhost:8123/play> | Console SQL |
| ClickHouse natif | `localhost:9000` | Connexion des clients |
| Metabase | <http://localhost:3000> | Dashboards |

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

## Modèle de données Silver

- [Documentation et diagramme Mermaid](docs/data-model-silver.md)
- [Modèle HTML interactif](docs/data-model-silver-interactif.html)

Pour utiliser toutes les interactions, clonez le dépôt puis ouvrez `docs/data-model-silver-interactif.html` dans un navigateur.

Le modèle est une constellation constituée de :

- quatre dimensions : patient, service, date et diagnostic ;
- trois faits : séjour, diagnostic associé à un séjour et relevé de monitoring.

Les données sources et les PDF du cours ne sont volontairement pas publiés dans ce dépôt.

## État du projet

- [x] Analyse du sujet
- [x] Modèle Silver et relations
- [x] Exploration et profilage des sources
- [x] Environnement Docker avec ClickHouse et Metabase
- [ ] Ingestion incrémentale et pseudonymisation
- [ ] Tables Bronze puis transformations SQL Silver
- [ ] Tables Gold et KPI
- [ ] Dashboards pilotage et recherche
- [ ] Orchestration, journalisation et documentation d'exploitation

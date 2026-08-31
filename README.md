# EDS CHU

Projet de construction d'un Entrepôt de Données de Santé suivant une architecture médaillon : Lake → Bronze → Silver → Gold → dashboards.

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
- [ ] Exploration et profilage des sources
- [ ] Environnement Docker avec ClickHouse et Metabase
- [ ] Ingestion incrémentale et pseudonymisation
- [ ] Tables Bronze puis transformations SQL Silver
- [ ] Tables Gold et KPI
- [ ] Dashboards pilotage et recherche
- [ ] Orchestration, journalisation et documentation d'exploitation

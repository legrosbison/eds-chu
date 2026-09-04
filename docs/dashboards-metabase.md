# Dashboards Metabase

## Objectif

Le sujet demande deux interfaces pour deux publics différents. Le script
[`setup_metabase.py`](../scripts/setup_metabase.py) crée automatiquement les
collections, les questions, les dashboards, les groupes et deux comptes de
démonstration.

```text
Groupe Pilotage  → collection et dashboard Pilotage uniquement
Groupe Recherche → collection et dashboard Recherche uniquement
Administrateur   → les deux
```

## Dashboard Pilotage hospitalier

Il contient dix cartes : les cinq indicateurs initiaux et les cinq indicateurs
du dépôt d'évolution.

| Carte                             | Visualisation | Source Gold                  |
| --------------------------------- | ------------- | ---------------------------- |
| Séjours valides                   | nombre        | `kpi_readmission_30d`        |
| Taux de réadmission à 30 jours    | nombre        | `kpi_readmission_30d`        |
| DMS par service                   | barres        | `kpi_dms_service`            |
| Activité quotidienne des urgences | courbes       | `kpi_emergency_daily`        |
| Alertes de monitoring par jour    | courbes       | `kpi_monitoring_alert_daily` |
| Activité et DMS par catégorie     | tableau       | `kpi_activity_dms_category`  |
| Actes par service                 | tableau       | `kpi_acts_service`           |
| Actes par type CCAM               | barres        | `kpi_acts_type`              |
| Densité d'actes par lit           | barres        | `kpi_act_density_bed`        |
| Montant facturé par service       | barres        | `kpi_billed_amount_service`  |

Cette séparation répond au besoin de la direction : suivre l'activité et la
qualité des soins sans accéder aux analyses de cohortes de recherche.

Neurologie reste présente dans les cartes d'activité et de facturation. Elle
n'apparaît pas dans la densité par lit, car le nouveau référentiel ne fournit
pas sa capacité et le projet n'invente pas cette valeur.

## Dashboard Recherche clinique

Il contient quatre cartes :

| Carte                     | Visualisation | Règle importante                                      |
| ------------------------- | ------------- | ----------------------------------------------------- |
| Pathologies diffusables   | nombre        | compte les cohortes d'au moins 5 patients             |
| Cohortes masquées         | nombre        | montre que la règle de confidentialité est appliquée  |
| Prévalence par pathologie | barres        | patients distincts, petits effectifs absents          |
| Cohortes par âge et sexe  | tableau       | diagnostic principal et tranches `0-9`, `10-19`, etc. |

Les questions de recherche utilisent uniquement
`publishable_patient_count`. Pour une cellule inférieure à 5, cette valeur est
`NULL` et l'interface affiche `Masqué`. Le compte brut n'est jamais sélectionné
par les cartes diffusées.

## Provisionnement

Le service `metabase-setup` le fait automatiquement au démarrage :

```bash
python3 scripts/init_env.py
docker compose up -d --build
docker compose ps --all
```

Il doit terminer avec le statut `Exited (0)`. Pour le rejouer manuellement :

```bash
python3 scripts/setup_metabase.py
```

Le script est idempotent : il met à jour les objets portant les mêmes noms sans
créer de doublons.

## Démontrer le cloisonnement

Les comptes sont configurés localement dans `.env`. Pour afficher leurs noms :

```bash
grep -E '^METABASE_(PILOTAGE|RECHERCHE)_EMAIL=' .env
```

Pour retrouver leurs mots de passe de démonstration :

```bash
grep -E '^METABASE_(PILOTAGE|RECHERCHE)_PASSWORD=' .env
```

1. Ouvrir <http://localhost:3000> dans une fenêtre privée avec le compte
   Pilotage : seul `Pilotage hospitalier` est visible.
2. Se déconnecter puis utiliser le compte Recherche : seul
   `Recherche clinique` est visible.
3. Vérifier que ces comptes peuvent consulter les cartes mais ne peuvent pas
   créer de nouvelles requêtes.

Metabase Community ne fournit pas toutes les autorisations avancées de l'édition
payante. Le projet utilise donc le cloisonnement disponible gratuitement :
collections séparées, groupes dédiés et création de requêtes interdite. Pour un
usage hospitalier réel, il faudrait compléter cela avec une authentification
centralisée et des comptes ClickHouse distincts par finalité.

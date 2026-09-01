# Profilage des fichiers sources

Rapport généré automatiquement par `scripts/profile_sources.py`. Il ne contient aucune identité ni valeur patient en clair.

## Périmètre

| Domaine     | Dépôt      | Lignes / entrées | Taille (octets) |
| ----------- | ---------- | ---------------- | --------------- |
| patients    | 2026-08-26 | 4 800            | 273456          |
| patients    | 2026-08-27 | 5 400            | 307537          |
| patients    | 2026-08-28 | 6 000            | 341737          |
| stays       | 2026-08-26 | 5 000            | 413300          |
| stays       | 2026-08-27 | 5 000            | 413006          |
| stays       | 2026-08-28 | 5 000            | 413350          |
| diagnostics | 2026-08-26 | 5 000            | 1004550         |
| diagnostics | 2026-08-27 | 5 000            | 1009538         |
| diagnostics | 2026-08-28 | 5 000            | 1008958         |
| monitoring  | 2026-08-26 | 24 631           | 105091          |
| monitoring  | 2026-08-27 | 22 190           | 97754           |
| monitoring  | 2026-08-28 | 19 856           | 101141          |
| cim10       | 2026-08-26 | 10               | 363             |
| services    | 2026-08-26 | 8                | 171             |

Volume total des fichiers : **5,489,952 octets** pour **14 fichiers**.

## Résultats principaux

| Domaine     | Contrôle                                                  | Nombre | Décision              |
| ----------- | --------------------------------------------------------- | ------ | --------------------- |
| Patients    | Lignes reçues                                             | 16200  | Information           |
| Patients    | Patients distincts                                        | 6000   | Information           |
| Patients    | Lignes retirées par déduplication version la plus récente | 10200  | Traitement Silver     |
| Patients    | Sexes invalides                                           | 0      | Rejet                 |
| Patients    | Dates de naissance invalides                              | 0      | Rejet                 |
| Séjours     | Lignes reçues                                             | 15000  | Information           |
| Séjours     | Séjours en cours                                          | 1190   | Conserver             |
| Séjours     | Sortie antérieure à l'admission                           | 136    | Rejet                 |
| Séjours     | Séjour terminé sans mode de sortie                        | 1992   | Rejet                 |
| Séjours     | Lignes rejetées (règles combinées)                        | 2111   | Rejet                 |
| Séjours     | Patients inconnus                                         | 0      | Rejet / investigation |
| Séjours     | Services inconnus                                         | 0      | Rejet / investigation |
| Diagnostics | Associations aplaties                                     | 37380  | Information           |
| Diagnostics | Codes CIM-10 inconnus                                     | 0      | Rejet / investigation |
| Diagnostics | Types invalides                                           | 0      | Rejet                 |
| Diagnostics | Lignes liées à un séjour Silver rejeté                    | 5276   | Rejet en cascade      |
| Monitoring  | Relevés reçus                                             | 66677  | Information           |
| Monitoring  | FC hors 20–250                                            | 1369   | Rejet                 |
| Monitoring  | SpO2 hors 50–100                                          | 1369   | Rejet                 |
| Monitoring  | Température hors 30–45                                    | 0      | Rejet                 |
| Monitoring  | Lignes rejetées par les règles obligatoires               | 1369   | Rejet                 |
| Monitoring  | Relevés hors fenêtre du séjour                            | 520    | Rejet de cohérence    |
| Monitoring  | Lignes liées à un séjour Silver rejeté                    | 9192   | Rejet en cascade      |
| Monitoring  | Lignes rejetées (règles combinées)                        | 10362  | Rejet                 |

## Patients

- **16,200 lignes** reçues pour **6,000 patients distincts**.
- **10,200 lignes** sont des retours quotidiens à retirer en gardant la version la plus récente.
- **0 patients** ont changé sur au moins un attribut Silver (`birth_date`, `sex`, `region_code`) entre deux dépôts.
- Doublons à l'intérieur d'un même fichier : **0**.
- Valeurs manquantes : patient_id **0**, birth_date **0**, sex **0**, region_code **0**.

Décision Silver : pseudonymiser `patient_id`, supprimer nom/prénom/NIR, généraliser `birth_date` en `birth_year`, normaliser le sexe et dédupliquer sur le pseudonyme stable.

## Séjours

- **15,000 lignes** et **15,000 identifiants de séjour distincts**.
- **1,190 séjours en cours** : sortie vide légitime, à conserver.
- **136 séjours** ont une sortie antérieure à l'admission et doivent être rejetés.
- **1,992 séjours terminés** n'ont pas de mode de sortie et doivent être rejetés au titre des valeurs manquantes.
- Après combinaison des règles, **12,889 séjours sont acceptés** et **2,111 rejetés**.
- Intégrité : **0 patients inconnus**, **0 services inconnus**.
- Durée valide en heures : min **2.0**, médiane **147.0**, moyenne **145.92**, max **288.0**.
- Modes d'admission observés : `{"mutation": 4981, "programme": 4945, "urgence": 5074}`.

## Diagnostics

- **15,000 entrées séjour** deviennent **37,380 lignes** après aplatissement du JSON.
- Nombre de diagnostics par séjour : min **1**, médiane **2.0**, moyenne **2.49**, max **4**.
- Codes CIM-10 inconnus : **0** ; séjours inconnus : **0**.
- Doublons sur `(stay_id, code_cim10, type)` : **0**.
- **5,276 diagnostics** sont rejetés en cascade car leur séjour parent est invalide ; **32,104 lignes** restent acceptées.

## Monitoring

- **66,677 relevés** dont **1,369 lignes** rejetées par les règles physiologiques ou de format obligatoires.
- Fréquence cardiaque : min **0**, max **500**, hors plage **1369**.
- SpO2 : min **0**, max **120**, hors plage **1369**.
- Température : min **36.4**, max **40.0**, hors plage **0**.
- Doublons sur `(stay_id, ts)` : **0**.
- Intégrité : **0 séjours inconnus**, **0 relevés avant admission**, **520 après sortie**.
- **9,192 relevés** dépendent d'un séjour Silver rejeté. Après combinaison des règles physiologiques, temporelles et parentales, **56,315 relevés sont acceptés** et **10,362 rejetés**.

Les bornes fournies par le sujet sont des bornes de **validité**, pas des seuils d'alerte clinique. Les seuils d'alerte devront être validés par le métier avant leur calcul en Gold.

## Conséquences pour l'implémentation

1. Charger d'abord les référentiels et patients, puis les séjours, diagnostics et relevés afin de contrôler l'intégrité des clés.
2. Pseudonymiser avant l'entrée dans l'entrepôt et ne jamais tracer de donnée identifiante dans les rejets.
3. Écrire les lignes invalides dans `audit_quality_rejects` avec la règle, le lot et le fichier source.
4. Partitionner `fact_monitoring` par mois de `measurement_date_key` ; ne pas créer une partition par jour.
5. Effectuer Bronze → Silver → Gold en SQL dans ClickHouse. Le script de profilage sert uniquement à l'exploration initiale.

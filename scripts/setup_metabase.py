#!/usr/bin/env python3
"""Provision Metabase with the two EDS dashboards and their access groups."""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from ingest_lake import load_env_file


ROOT = Path(__file__).resolve().parents[1]


class MetabaseClient:
    def __init__(self, url: str) -> None:
        self.url = url.rstrip("/")
        self.session_id: str | None = None

    def request(
        self, method: str, path: str, payload: dict[str, Any] | None = None
    ) -> Any:
        headers = {"Content-Type": "application/json"}
        if self.session_id:
            headers["X-Metabase-Session"] = self.session_id
        request = urllib.request.Request(
            self.url + path,
            data=json.dumps(payload).encode() if payload is not None else None,
            headers=headers,
            method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=180) as response:
                body = response.read()
                return json.loads(body) if body else None
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")
            raise RuntimeError(
                f"Metabase HTTP {error.code} pour {method} {path}: {detail}"
            ) from error

    def login(self, email: str, password: str) -> None:
        response = self.request(
            "POST", "/api/session", {"username": email, "password": password}
        )
        self.session_id = response["id"]


def wait_for_metabase(client: MetabaseClient) -> None:
    for _ in range(60):
        try:
            if client.request("GET", "/api/health").get("status") == "ok":
                return
        except (OSError, RuntimeError):
            pass
        time.sleep(2)
    raise RuntimeError("Metabase n'est pas devenu disponible")


def list_items(response: Any) -> list[dict[str, Any]]:
    if isinstance(response, list):
        return response
    if isinstance(response, dict) and isinstance(response.get("data"), list):
        return response["data"]
    return []


def ensure_initial_setup(
    client: MetabaseClient, email: str, password: str
) -> None:
    properties = client.request("GET", "/api/session/properties")
    if properties.get("has-user-setup"):
        return
    client.request(
        "POST",
        "/api/setup",
        {
            "token": properties["setup-token"],
            "user": {
                "first_name": "Admin",
                "last_name": "EDS CHU",
                "email": email,
                "password": password,
            },
            "prefs": {"site_name": "EDS CHU", "site_locale": "fr"},
        },
    )
    print(f"METABASE_SETUP admin={email}")


def ensure_database(client: MetabaseClient) -> int:
    name = "EDS CHU - Gold"
    databases = list_items(client.request("GET", "/api/database"))
    existing = next((item for item in databases if item.get("name") == name), None)
    if existing:
        database_id = int(existing["id"])
        client.request("POST", f"/api/database/{database_id}/sync_schema")
        return database_id

    created = client.request(
        "POST",
        "/api/database",
        {
            "name": name,
            "engine": "clickhouse",
            "details": {
                "host": os.environ.get("METABASE_CLICKHOUSE_HOST", "clickhouse"),
                "port": 8123,
                "user": os.environ.get("CLICKHOUSE_USER", "eds_app"),
                "password": os.environ.get(
                    "CLICKHOUSE_PASSWORD", "eds_local_password"
                ),
                "enable-multiple-db": False,
                "dbname": "gold",
                "ssl": False,
            },
            "is_full_sync": True,
        },
    )
    database_id = int(created["id"])
    client.request("POST", f"/api/database/{database_id}/sync_schema")
    print(f"METABASE_DATABASE id={database_id} name={name}")
    return database_id


def ensure_collection(client: MetabaseClient, name: str, description: str) -> int:
    collections = list_items(client.request("GET", "/api/collection"))
    existing = next((item for item in collections if item.get("name") == name), None)
    if existing:
        return int(existing["id"])
    created = client.request(
        "POST",
        "/api/collection",
        {"name": name, "description": description},
    )
    return int(created["id"])


def card_payload(
    *,
    name: str,
    description: str,
    collection_id: int,
    database_id: int,
    query: str,
    display: str,
    dimensions: list[str] | None = None,
    metrics: list[str] | None = None,
) -> dict[str, Any]:
    settings: dict[str, Any] = {}
    if dimensions:
        settings["graph.dimensions"] = dimensions
    if metrics:
        settings["graph.metrics"] = metrics
    return {
        "name": name,
        "description": description,
        "collection_id": collection_id,
        "display": display,
        "dataset_query": {
            "database": database_id,
            "type": "native",
            "native": {"query": query.strip(), "template-tags": {}},
        },
        "visualization_settings": settings,
    }


def ensure_card(client: MetabaseClient, payload: dict[str, Any]) -> int:
    cards = list_items(client.request("GET", "/api/card"))
    existing = next(
        (
            item
            for item in cards
            if item.get("name") == payload["name"]
            and item.get("collection_id") == payload["collection_id"]
        ),
        None,
    )
    if existing:
        card_id = int(existing["id"])
        client.request("PUT", f"/api/card/{card_id}", payload)
        return card_id
    return int(client.request("POST", "/api/card", payload)["id"])


def ensure_dashboard(
    client: MetabaseClient,
    name: str,
    description: str,
    collection_id: int,
    cards: list[tuple[int, int, int, int, int]],
) -> int:
    dashboards = list_items(client.request("GET", "/api/dashboard"))
    existing = next(
        (
            item
            for item in dashboards
            if item.get("name") == name and item.get("collection_id") == collection_id
        ),
        None,
    )
    if existing:
        dashboard_id = int(existing["id"])
        client.request(
            "PUT",
            f"/api/dashboard/{dashboard_id}",
            {"name": name, "description": description, "collection_id": collection_id},
        )
    else:
        dashboard_id = int(
            client.request(
                "POST",
                "/api/dashboard",
                {"name": name, "description": description, "collection_id": collection_id},
            )["id"]
        )

    layout = []
    for position, (card_id, row, col, size_x, size_y) in enumerate(cards, start=1):
        layout.append(
            {
                "id": -position,
                "card_id": card_id,
                "row": row,
                "col": col,
                "size_x": size_x,
                "size_y": size_y,
                "parameter_mappings": [],
                "visualization_settings": {},
            }
        )
    client.request("PUT", f"/api/dashboard/{dashboard_id}/cards", {"cards": layout})
    print(f"METABASE_DASHBOARD id={dashboard_id} name={name}")
    return dashboard_id


def ensure_group(client: MetabaseClient, name: str) -> int:
    groups = list_items(client.request("GET", "/api/permissions/group"))
    existing = next((item for item in groups if item.get("name") == name), None)
    if existing:
        return int(existing["id"])
    return int(
        client.request("POST", "/api/permissions/group", {"name": name})["id"]
    )


def ensure_user(
    client: MetabaseClient,
    email: str,
    password: str,
    first_name: str,
    group_id: int,
) -> int:
    users = list_items(client.request("GET", "/api/user"))
    existing = next((item for item in users if item.get("email") == email), None)
    if existing:
        user_id = int(existing["id"])
    else:
        user_id = int(
            client.request(
                "POST",
                "/api/user",
                {
                    "email": email,
                    "password": password,
                    "first_name": first_name,
                    "last_name": "EDS CHU",
                },
            )["id"]
        )

    memberships = client.request("GET", "/api/permissions/membership")
    user_memberships = memberships.get(str(user_id), [])
    if not any(
        int(item.get("group_id", -1)) == group_id for item in user_memberships
    ):
        client.request(
            "POST",
            "/api/permissions/membership",
            {"user_id": user_id, "group_id": group_id},
        )
    return user_id


def configure_permissions(
    client: MetabaseClient,
    database_id: int,
    pilotage_collection_id: int,
    research_collection_id: int,
    pilotage_group_id: int,
    research_group_id: int,
) -> None:
    groups = list_items(client.request("GET", "/api/permissions/group"))
    all_users_id = int(next(item["id"] for item in groups if item["name"] == "All Users"))

    collection_graph = client.request("GET", "/api/collection/graph")
    graph_groups = collection_graph.setdefault("groups", {})
    all_users_permissions = graph_groups.setdefault(str(all_users_id), {})
    all_users_permissions["root"] = "none"
    for collection in list_items(client.request("GET", "/api/collection")):
        if not collection.get("is_personal") and collection.get("id") != "root":
            all_users_permissions[str(collection["id"])] = "none"
    for group_id, pilotage_access, research_access in (
        (pilotage_group_id, "read", "none"),
        (research_group_id, "none", "read"),
    ):
        permissions = graph_groups.setdefault(str(group_id), {})
        permissions["root"] = "none"
        permissions[str(pilotage_collection_id)] = pilotage_access
        permissions[str(research_collection_id)] = research_access
    client.request("PUT", "/api/collection/graph", collection_graph)

    data_graph = client.request("GET", "/api/permissions/graph")
    data_groups = data_graph.setdefault("groups", {})
    for group_id in (pilotage_group_id, research_group_id):
        database_permissions = data_groups.setdefault(str(group_id), {}).setdefault(
            str(database_id), {}
        )
        database_permissions["view-data"] = "unrestricted"
        database_permissions["create-queries"] = "no"
    all_users_databases = data_groups.setdefault(str(all_users_id), {})
    for permissions in all_users_databases.values():
        permissions["create-queries"] = "no"
    all_users_database = all_users_databases.setdefault(str(database_id), {})
    # Dans Metabase Community, `blocked` est une permission avancée payante.
    # Les données restent lisibles pour exécuter les cartes enregistrées, mais
    # All Users ne peut créer aucune requête. Les collections font ensuite le
    # cloisonnement entre les deux publics.
    all_users_database["view-data"] = "unrestricted"
    all_users_database["create-queries"] = "no"
    client.request("PUT", "/api/permissions/graph", data_graph)
    print("METABASE_PERMISSIONS pilotage!=recherche")


def create_pilotage_cards(
    client: MetabaseClient, collection_id: int, database_id: int
) -> list[int]:
    definitions = [
        card_payload(
            name="Pilotage - Séjours valides",
            description="Nombre total de séjours acceptés en Silver.",
            collection_id=collection_id,
            database_id=database_id,
            query="SELECT stay_count AS sejours_valides FROM kpi_readmission_30d",
            display="scalar",
        ),
        card_payload(
            name="Pilotage - Taux de réadmission à 30 jours",
            description="Réadmissions dans les 30 jours rapportées aux 6 729 séjours.",
            collection_id=collection_id,
            database_id=database_id,
            query="SELECT readmission_30d_rate_pct AS taux_pct FROM kpi_readmission_30d",
            display="scalar",
        ),
        card_payload(
            name="Pilotage - DMS par service",
            description="Durée moyenne des séjours clos, en jours.",
            collection_id=collection_id,
            database_id=database_id,
            query="""
                SELECT service_label AS service,
                       average_length_of_stay_days AS dms_jours
                FROM kpi_dms_service
                ORDER BY dms_jours DESC
            """,
            display="bar",
            dimensions=["service"],
            metrics=["dms_jours"],
        ),
        card_payload(
            name="Pilotage - Activité quotidienne des urgences",
            description="Passages et séjours encore présents par date d'admission.",
            collection_id=collection_id,
            database_id=database_id,
            query="""
                SELECT date_key AS date,
                       passage_count AS passages,
                       ongoing_stay_count AS encore_presents
                FROM kpi_emergency_daily
                ORDER BY date_key
            """,
            display="line",
            dimensions=["date"],
            metrics=["passages", "encore_presents"],
        ),
        card_payload(
            name="Pilotage - Alertes de monitoring par jour",
            description="Nombre de relevés et d'alertes selon les seuils du corrigé.",
            collection_id=collection_id,
            database_id=database_id,
            query="""
                SELECT date_key AS date,
                       measurement_count AS releves,
                       alert_count AS alertes
                FROM kpi_monitoring_alert_daily
                ORDER BY date_key
            """,
            display="line",
            dimensions=["date"],
            metrics=["releves", "alertes"],
        ),
        card_payload(
            name="Pilotage - Activité et DMS par catégorie",
            description="Séjours totaux et clos, avec DMS calculée uniquement sur les séjours clos.",
            collection_id=collection_id,
            database_id=database_id,
            query="""
                SELECT categorie,
                       stay_count AS sejours,
                       closed_stay_count AS sejours_clos,
                       average_length_of_stay_days AS dms_jours
                FROM kpi_activity_dms_category
                ORDER BY dms_jours DESC
            """,
            display="table",
        ),
        card_payload(
            name="Pilotage - Actes par service",
            description="Nombre d'actes et moyenne par séjour comportant au moins un acte.",
            collection_id=collection_id,
            database_id=database_id,
            query="""
                SELECT service_label AS service,
                       act_count AS actes,
                       stay_with_act_count AS sejours_avec_acte,
                       average_acts_per_stay AS actes_par_sejour
                FROM kpi_acts_service
                ORDER BY actes DESC
            """,
            display="table",
        ),
        card_payload(
            name="Pilotage - Actes par type",
            description="Codes et libellés CCAM classés par fréquence.",
            collection_id=collection_id,
            database_id=database_id,
            query="""
                SELECT concat(code_ccam, ' - ', act_label) AS type_acte,
                       act_count AS actes
                FROM kpi_acts_type
                ORDER BY actes DESC
            """,
            display="bar",
            dimensions=["type_acte"],
            metrics=["actes"],
        ),
        card_payload(
            name="Pilotage - Densité d'actes par lit",
            description="Nombre d'actes rapporté à la capacité en lits ; Neurologie reste non calculable.",
            collection_id=collection_id,
            database_id=database_id,
            query="""
                SELECT service_label AS service,
                       acts_per_bed AS actes_par_lit
                FROM kpi_act_density_bed
                WHERE acts_per_bed IS NOT NULL
                ORDER BY actes_par_lit DESC
            """,
            display="bar",
            dimensions=["service"],
            metrics=["actes_par_lit"],
        ),
        card_payload(
            name="Pilotage - Montant facturé par service",
            description="Somme des tarifs CCAM des actes réalisés, selon la règle T2A du sujet.",
            collection_id=collection_id,
            database_id=database_id,
            query="""
                SELECT service_label AS service,
                       billed_amount_euros AS montant_euros
                FROM kpi_billed_amount_service
                ORDER BY montant_euros DESC
            """,
            display="bar",
            dimensions=["service"],
            metrics=["montant_euros"],
        ),
    ]
    return [ensure_card(client, payload) for payload in definitions]


def create_research_cards(
    client: MetabaseClient, collection_id: int, database_id: int
) -> list[int]:
    definitions = [
        card_payload(
            name="Recherche - Pathologies diffusables",
            description="Nombre de pathologies dont la cohorte atteint au moins 5 patients.",
            collection_id=collection_id,
            database_id=database_id,
            query="""
                SELECT count() AS pathologies_diffusables
                FROM kpi_pathology_prevalence
                WHERE publishable_patient_count IS NOT NULL
            """,
            display="scalar",
        ),
        card_payload(
            name="Recherche - Cohortes masquées",
            description="Nombre de cohortes pathologie masquées car inférieures à 5.",
            collection_id=collection_id,
            database_id=database_id,
            query="""
                SELECT count() AS cohortes_masquees
                FROM kpi_pathology_prevalence
                WHERE publishable_patient_count IS NULL
            """,
            display="scalar",
        ),
        card_payload(
            name="Recherche - Prévalence par pathologie",
            description="Patients distincts ; les cohortes de moins de 5 ne sont pas affichées.",
            collection_id=collection_id,
            database_id=database_id,
            query="""
                SELECT diagnosis_label AS pathologie,
                       publishable_patient_count AS patients
                FROM kpi_pathology_prevalence
                WHERE publishable_patient_count IS NOT NULL
                ORDER BY patients DESC
            """,
            display="bar",
            dimensions=["pathologie"],
            metrics=["patients"],
        ),
        card_payload(
            name="Recherche - Cohortes par âge et sexe",
            description="Diagnostic principal et tranches de dix ans ; effectifs < 5 masqués.",
            collection_id=collection_id,
            database_id=database_id,
            query="""
                SELECT diagnosis_code AS code_cim10,
                       age_band AS tranche_age,
                       sex AS sexe,
                       ifNull(toString(publishable_patient_count), 'Masqué') AS patients_diffusables
                FROM kpi_cohort_demographics
                ORDER BY diagnosis_code,
                         toUInt16(splitByChar('-', age_band)[1]),
                         sex
            """,
            display="table",
        ),
    ]
    return [ensure_card(client, payload) for payload in definitions]


def main() -> None:
    load_env_file(ROOT / ".env")
    port = os.environ.get("METABASE_PORT", "3000")
    client = MetabaseClient(os.environ.get("METABASE_URL", f"http://127.0.0.1:{port}"))
    wait_for_metabase(client)

    admin_email = os.environ["METABASE_ADMIN_EMAIL"]
    admin_password = os.environ["METABASE_ADMIN_PASSWORD"]
    ensure_initial_setup(client, admin_email, admin_password)
    client.login(admin_email, admin_password)

    database_id = ensure_database(client)
    pilotage_collection_id = ensure_collection(
        client,
        "Pilotage hospitalier",
        "DMS, urgences, réadmissions, surveillance et activité des actes.",
    )
    research_collection_id = ensure_collection(
        client,
        "Recherche clinique",
        "Prévalence et cohortes diffusables selon la règle des cinq patients.",
    )

    pilotage_cards = create_pilotage_cards(
        client, pilotage_collection_id, database_id
    )
    research_cards = create_research_cards(
        client, research_collection_id, database_id
    )
    ensure_dashboard(
        client,
        "Pilotage hospitalier",
        "Vue quotidienne pour la direction du CHU.",
        pilotage_collection_id,
        [
            (pilotage_cards[0], 0, 0, 6, 4),
            (pilotage_cards[1], 0, 6, 6, 4),
            (pilotage_cards[2], 4, 0, 12, 8),
            (pilotage_cards[3], 12, 0, 12, 8),
            (pilotage_cards[4], 20, 0, 12, 8),
            (pilotage_cards[5], 28, 0, 12, 8),
            (pilotage_cards[6], 36, 0, 12, 8),
            (pilotage_cards[7], 44, 0, 12, 8),
            (pilotage_cards[8], 52, 0, 12, 8),
            (pilotage_cards[9], 60, 0, 12, 8),
        ],
    )
    ensure_dashboard(
        client,
        "Recherche clinique",
        "Cohortes agrégées sans diffusion des effectifs inférieurs à cinq.",
        research_collection_id,
        [
            (research_cards[0], 0, 0, 6, 4),
            (research_cards[1], 0, 6, 6, 4),
            (research_cards[2], 4, 0, 12, 8),
            (research_cards[3], 12, 0, 12, 12),
        ],
    )

    pilotage_group_id = ensure_group(client, "Pilotage")
    research_group_id = ensure_group(client, "Recherche")
    ensure_user(
        client,
        os.environ["METABASE_PILOTAGE_EMAIL"],
        os.environ["METABASE_PILOTAGE_PASSWORD"],
        "Utilisateur Pilotage",
        pilotage_group_id,
    )
    ensure_user(
        client,
        os.environ["METABASE_RECHERCHE_EMAIL"],
        os.environ["METABASE_RECHERCHE_PASSWORD"],
        "Utilisateur Recherche",
        research_group_id,
    )
    configure_permissions(
        client,
        database_id,
        pilotage_collection_id,
        research_collection_id,
        pilotage_group_id,
        research_group_id,
    )
    print("METABASE_READY url=" + client.url)


if __name__ == "__main__":
    main()

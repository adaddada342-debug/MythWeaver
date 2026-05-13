from __future__ import annotations

import json

from mythweaver.catalog.loaders import modrinth_loader_category
from mythweaver.schemas.contracts import SearchPlan


def build_search_facets(plan: SearchPlan) -> str:
    """Encode Modrinth search facets using AND arrays and OR entries."""

    facets: list[list[str]] = [[f"project_type:{plan.project_type}"]]
    loader = modrinth_loader_category(plan.loader)
    if loader:
        facets.append([f"categories:{loader}"])
    if plan.minecraft_version != "auto":
        facets.append([f"versions:{plan.minecraft_version}"])
    if plan.categories:
        facets.append([f"categories:{category}" for category in plan.categories])
    if plan.client_side:
        facets.append([f"client_side:{plan.client_side}"])
    if plan.server_side:
        facets.append([f"server_side:{plan.server_side}"])
    return json.dumps(facets, separators=(",", ":"))

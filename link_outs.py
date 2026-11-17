"""Write ready-made search links. This module does not open those sites."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import quote_plus

from source_map import Recommendation, link_spec


def place_label(place: object) -> str:
    """City, Country for an office, or the remote area the user named."""
    if isinstance(place, str):
        return " ".join(place.split())
    remote = bool(place.get("remote", False) if isinstance(place, dict) else getattr(place, "remote", False))
    if isinstance(place, dict):
        name = str(place.get("name") or "").strip()
        area = str(place.get("indeed_location") or place.get("linkedin_location") or "").strip()
    else:
        name = str(getattr(place, "name", "") or "").strip()
        area = str(
            getattr(place, "indeed_location", "") or getattr(place, "linkedin_location", "") or ""
        ).strip()
    if remote:
        return area or name or "Remote"
    return name or area


def write_links(path: str | Path, recommendation: Recommendation, roles: list, places: list) -> int:
    """Write one line per role, place, and link-out. Return how many links were written."""
    destination = Path(path)
    lines = ["# Search links", ""]
    count = 0
    for role in roles or []:
        role_text = " ".join(str(role).split())
        if not role_text:
            continue
        for place in places or []:
            location = place_label(place)
            if not location:
                continue
            for link_id in recommendation.link_outs:
                spec = link_spec(link_id)
                if spec is None:
                    continue
                url = spec["url"].replace("{q}", quote_plus(role_text)).replace(
                    "{loc}", quote_plus(location)
                )
                lines.append(f"- [{spec['label']} — {role_text} in {location}]({url})")
                count += 1
    lines.append("")
    lines.append("These sites do not allow automatic reading, so open them yourself.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return count


def links_for_settings(settings) -> int:
    """Write output/links.md from ids already stored on a loaded config. Return the count."""
    ids = tuple(getattr(settings, "link_outs", ()) or ())
    if not ids:
        return 0
    recommendation = Recommendation(sources=(), link_outs=ids, explanation=())
    path = Path(settings.output_dir) / "links.md"
    return write_links(path, recommendation, list(settings.roles), list(settings.places))

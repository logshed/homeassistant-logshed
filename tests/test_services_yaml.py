"""Tests that services.yaml parses, as hassfest requires."""

from __future__ import annotations

from pathlib import Path

import yaml

SERVICES_YAML = Path(__file__).parent.parent / "custom_components" / "logshed" / "services.yaml"


def test_services_yaml_parses_and_describes_every_field() -> None:
    """A colon in an unquoted description makes the whole file invalid."""
    services = yaml.safe_load(SERVICES_YAML.read_text(encoding="utf-8"))
    assert set(services) == {"enable_maintenance", "disable_maintenance"}
    for service in services.values():
        for name, field in (service.get("fields") or {}).items():
            assert isinstance(field["description"], str), name

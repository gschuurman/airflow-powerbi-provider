"""Airflow provider metadata entrypoint, referenced from ``pyproject.toml``."""
from __future__ import annotations

from importlib.metadata import version
from importlib.resources import files


def get_provider_info():
    """
    Load and return this package's provider metadata for Airflow's provider discovery.

    Reads ``provider.yaml`` and stamps in the installed package version, so
    Airflow's UI and CLI can report connection types, hooks, and version info
    without a hardcoded copy.

    :return: Provider metadata dict as consumed by Airflow's provider manager.
    """
    import yaml

    package_name = "airflow-powerbi-provider"
    text = files("PowerBI_Operator").joinpath("provider.yaml").read_text(encoding="utf-8")
    data = yaml.safe_load(text)
    data["versions"] = [version(package_name)]
    return data

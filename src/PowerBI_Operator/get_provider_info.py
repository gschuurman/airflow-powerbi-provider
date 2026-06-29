from __future__ import annotations

from importlib.metadata import version
from importlib.resources import files


def get_provider_info():
    import yaml

    package_name = "airflow-powerbi-provider"
    text = files("PowerBI_Operator").joinpath("provider.yaml").read_text(encoding="utf-8")
    data = yaml.safe_load(text)
    data["versions"] = [version(package_name)]
    return data

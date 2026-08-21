"""Manifest of modules worth generating API reference pages for, consumed by product-site's docs build."""

AUTODOC_TARGETS: list[str] = [
    "PowerBI_Operator.hooks.powerbi_hook",
    "PowerBI_Operator.models.powerbi_models",
    "PowerBI_Operator.operators.powerbi_refresh_dataset_operator",
    "PowerBI_Operator.sensors.powerbi_refresh_dataset_sensor",
]

"""Data models for Power BI dataset refresh results."""
from dataclasses import dataclass

from airflow.exceptions import AirflowException


@dataclass
class PowerBiDatasetRefreshDetails:
    """
    Details of a single Power BI dataset refresh, as returned by the refresh history API.

    :param request_id: Request id of the dataset refresh.
    :param status: Refresh status, e.g. ``"Completed"``, ``"Failed"``, or ``"Unknown"`` while in progress.
    :param end_time: Timestamp the refresh finished, or ``None`` if still running.
    :param error: Error details if the refresh failed, otherwise ``None``.
    """
    request_id: str
    status: str
    end_time: str | None
    error: str | None


class PowerBIDatasetRefreshException(AirflowException):
    """An exception that indicates a dataset refresh failed to complete."""

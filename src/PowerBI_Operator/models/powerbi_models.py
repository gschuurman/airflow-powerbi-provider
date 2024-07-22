from dataclasses import dataclass

from airflow.exceptions import AirflowException


@dataclass
class PowerBiDatasetRefreshDetails:
    request_id: str
    status: str
    end_time: str
    error: str


class PowerBIDatasetRefreshException(AirflowException):
    """An exception that indicates a dataset refresh failed to complete."""

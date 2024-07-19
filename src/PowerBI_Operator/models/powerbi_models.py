from airflow.exceptions import AirflowException
from airflow.utils.pydantic import BaseModel


class PowerBiDatasetRefreshDetails(BaseModel):
    request_id: str
    status: str
    end_time: str
    error: str


class PowerBIDatasetRefreshException(AirflowException):
    """An exception that indicates a dataset refresh failed to complete."""

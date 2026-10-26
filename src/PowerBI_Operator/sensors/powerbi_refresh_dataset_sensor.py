"""Sensor for polling the status of a previously triggered Power BI dataset refresh."""
from functools import cached_property

import requests  # type: ignore
from airflow.sdk.bases.sensor import BaseSensorOperator
from azure.core.exceptions import ServiceRequestError, ServiceResponseError

from PowerBI_Operator.hooks.powerbi_hook import PowerBIHook, is_transient_error
from PowerBI_Operator.models.powerbi_models import PowerBIDatasetRefreshException, PowerBiDatasetRefreshDetails


class PowerBIDatasetRefreshSensor(BaseSensorOperator):
    """
    Polls a Power BI dataset refresh, started by an upstream task, until it terminates.

    The refresh request id is read from XCom, pushed by the upstream task
    (typically a :class:`~PowerBI_Operator.operators.powerbi_refresh_dataset_operator.PowerBIDatasetRefreshOperator`
    run with ``wait_for_termination=False``) under the key ``powerbi_dataset_refresh_id``.

    :param conn_id: Airflow connection id holding the Power BI service principal credentials.
    :param dataset_id: The dataset id.
    :param group_id: The workspace id.
    :param xcom_task_id: Task id of the upstream task that pushed the refresh request id to XCom.

    Example::

        PowerBIDatasetRefreshSensor(
            task_id="wait_for_refresh",
            conn_id="powerbi_default",
            dataset_id="abc123",
            group_id="def456",
            xcom_task_id="refresh_dataset",
        )
    """
    def __init__(
            self,
            conn_id,
            dataset_id: str,
            group_id: str,
            xcom_task_id=None,
            *args,
            **kwargs,
    ):
        """
        Initialize the sensor with connection, target dataset, and the upstream XCom source.

        :param conn_id: Airflow connection id holding the Power BI service principal credentials.
        :param dataset_id: The dataset id.
        :param group_id: The workspace id.
        :param xcom_task_id: Task id of the upstream task that pushed the refresh request id to XCom.
        """
        super(PowerBIDatasetRefreshSensor, self).__init__(*args, **kwargs)
        self.dataset_id = dataset_id
        self.group_id = group_id
        self.conn_id = conn_id
        self.xcom_task_id = xcom_task_id

    @cached_property
    def hook(self) -> PowerBIHook:
        """
        Create and return an PowerBIHook (cached), so its HTTP session and token are reused between pokes.
        """
        return PowerBIHook(
            conn_id=self.conn_id,
            dataset_id=self.dataset_id,
            group_id=self.group_id
        )

    def poke(self, context):
        """
        Check whether the dataset refresh has reached a terminal status.

        Pushes the terminal status to XCom under ``powerbi_dataset_refresh_status``
        and raises :class:`~PowerBI_Operator.models.powerbi_models.PowerBIDatasetRefreshException`
        if the refresh failed. Transient errors (see
        :func:`~PowerBI_Operator.hooks.powerbi_hook.is_transient_error`) are logged
        and the status is checked again on the next poke.

        :param context: Airflow task instance context, used to pull the refresh request id from XCom.
        :return: ``True`` once the refresh has reached a terminal status (``Failed`` or ``Completed``).
        """
        refresh_id = context["task_instance"].xcom_pull(
            task_ids=self.xcom_task_id,
            key="powerbi_dataset_refresh_id"
        )

        try:
            refresh_status_details: PowerBiDatasetRefreshDetails = self.hook.get_refresh_details_by_request_id(
                refresh_id
            )
        except (requests.RequestException, ServiceRequestError, ServiceResponseError) as error:
            if not is_transient_error(error):
                raise
            self.log.warning(f"Unable to check the status of dataset refresh {refresh_id}, retrying: {error}")
            return False

        refresh_status: str = refresh_status_details.status

        self.log.info(f"Current status: {refresh_status}")

        termination_flag = refresh_status in ["Failed", "Completed"]

        if termination_flag:
            context["ti"].xcom_push(
                key="powerbi_dataset_refresh_status",
                value=refresh_status,
            )

        if refresh_status == "Failed":
            self.log.error("")
            raise PowerBIDatasetRefreshException(
                refresh_status_details.error
            )

        return termination_flag

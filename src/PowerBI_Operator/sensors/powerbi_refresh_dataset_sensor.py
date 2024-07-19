from airflow.sensors.base import BaseSensorOperator
from airflow.utils.decorators import apply_defaults

from PowerBI_Operator.hooks.powerbi_hook import PowerBIHook
from PowerBI_Operator.models.powerbi_models import PowerBIDatasetRefreshException, PowerBiDatasetRefreshDetails


class PowerBIDatasetRefreshSensor(BaseSensorOperator):
    @apply_defaults
    def __init__(
            self,
            conn_id,
            dataset_id: str,
            group_id: str,
            xcom_task_id=None,
            *args,
            **kwargs,
    ):
        super(PowerBIDatasetRefreshSensor, self).__init__(*args, **kwargs)
        self.dataset_id = dataset_id
        self.group_id = group_id
        self.conn_id = conn_id
        self.xcom_task_id = xcom_task_id

    def poke(self, context):
        hook = PowerBIHook(
            conn_id=self.conn_id,
            dataset_id=self.dataset_id,
            group_id=self.group_id
        )

        refresh_id = context["task_instance"].xcom_pull(
            task_ids=self.xcom_task_id,
            key="powerbi_dataset_refresh_id"
        )

        refresh_status_details: PowerBiDatasetRefreshDetails = hook.get_refresh_details_by_request_id(refresh_id)
        refresh_status: str = refresh_status_details.status

        self.log.info(f"Current status: {refresh_status}")

        termination_flag = refresh_status in ["Failed", "Completed"]

        if termination_flag:
            self.xcom_push(
                context=context,
                key="powerbi_dataset_refresh_status",
                value=refresh_status,
            )

        if refresh_status == "Failed":
            raise PowerBIDatasetRefreshException(
                "Dataset refresh has failed"
            )

        return termination_flag

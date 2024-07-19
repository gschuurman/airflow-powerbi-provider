"""Standard imports"""
from functools import cached_property
from typing import Sequence

from airflow.models import BaseOperator
from airflow.models import BaseOperatorLink  # type: ignore
from airflow.utils.context import Context
from airflow.utils.decorators import apply_defaults

from PowerBI_Operator.hooks.powerbi_hook import PowerBIHook


class PowerBIDatasetRefreshOperator(BaseOperator):
    """
    Refreshes a Power BI dataset.

    By default, the operator will wait until the refresh has completed before
    exiting. The refresh status is checked every 60 seconds as a default. This
    can be changed by specifying a new value for `check_interval`.

    :param dataset_id: The dataset id.
    :param group_id: The workspace id.
    :param wait_for_termination: Wait until the pre-existing or current triggered refresh completes before exiting.
    :param force_refresh: When enabled, it will force refresh the dataset again, after pre-existing ongoing refresh request is terminated.
    :param timeout: Time in seconds to wait for a dataset to reach a terminal status for non-asynchronous waits. Used only if ``wait_for_termination`` is True.
    :param check_interval: Number of seconds to wait before rechecking the
        refresh status.
    """
    template_fields: Sequence[str] = (
        "dataset_id",
        "group_id",
    )
    template_fields_renderers = {"parameters": "json"}

    @apply_defaults
    def __init__(
            self,
            conn_id: str,
            dataset_id: str,
            group_id: str,
            wait_for_termination: bool = False,
            timeout: int = 60 * 60 * 24 * 7,
            check_interval: int = 60,
            *args,
            **kwargs,
    ) -> None:
        super(PowerBIDatasetRefreshOperator, self).__init__(*args, **kwargs)
        self.conn_id = conn_id
        self.dataset_id = dataset_id
        self.group_id = group_id
        self.wait_for_termination = wait_for_termination
        self.timeout = timeout
        self.check_interval = check_interval

    @cached_property
    def hook(self) -> PowerBIHook:
        """
        Create and return an PowerBIHook (cached).
        """
        return PowerBIHook(
            conn_id=self.conn_id,
            dataset_id=self.dataset_id,
            group_id=self.group_id
        )

    def execute(self, context: Context):
        """
        Refresh the Power BI Dataset
        """
        request_id = self.hook.trigger_dataset_refresh(self.wait_for_termination)
        self.xcom_push(
            context=context,
            key="powerbi_dataset_refresh_id",
            value=request_id
        )

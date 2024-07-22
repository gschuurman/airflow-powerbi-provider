import time
from typing import Union

import requests  # type: ignore
from airflow.exceptions import AirflowException
from airflow.hooks.base import BaseHook
from azure.identity import ClientSecretCredential

from PowerBI_Operator.models.powerbi_models import PowerBIDatasetRefreshException, PowerBiDatasetRefreshDetails


class PowerBIHook(BaseHook):
    """
    A hook to interact with Power BI.

    :param dataset_id: The dataset id.
    :param group_id: The workspace id.
    """
    hook_name: str = "Power BI"

    def __init__(
            self,
            conn_id: str,
            dataset_id: str,
            group_id: str,
    ):
        self.conn_id = conn_id
        self.dataset_id = dataset_id
        self.group_id = group_id
        self.header = None
        self._api_version = "v1.0"
        self._base_url = "https://api.powerbi.com"
        super().__init__()

    def refresh_dataset(self, dataset_id: str, group_id: str) -> str:
        """
        Triggers a refresh for the specified dataset from the given group id.

        :param dataset_id: The dataset id.
        :param group_id: The workspace id.

        :return: Request id of the dataset refresh request.
        """
        url = f"{self._base_url}/{self._api_version}/myorg/groups/{group_id}/datasets/{dataset_id}/refreshes"

        response = self._send_request("POST", url=url)
        request_id = response.headers["RequestId"]

        return request_id

    def _get_token(self) -> str:
        """
        Retrieve the access token used to authenticate against the API.
        """
        connection = self.get_connection(self.conn_id)
        client_id = connection.login
        client_secret = connection.password
        tenant_id = connection.extra_dejson.get("tenant_id")

        if not client_id:
            raise ValueError("The login is missing")
        if not client_secret:
            raise ValueError("The password is missing")
        if not tenant_id:
            raise ValueError("The key tenant_id is missing in the extra field")

        credential = ClientSecretCredential(
            client_id=client_id,
            client_secret=client_secret,
            tenant_id=tenant_id
        )

        scope = "https://analysis.windows.net/powerbi/api/.default"

        access_token = credential.get_token(scope)

        return access_token.token

    def get_refresh_history(
            self,
            dataset_id: str,
            group_id: str,
    ) -> dict:
        """
        Returns the refresh history of the specified dataset from the given group id.

        :param dataset_id: The dataset id.
        :param group_id: The workspace id.

        :return: dict object containaing all the refresh histories of the dataset.
        """
        url = f"{self._base_url}/{self._api_version}/myorg/groups/{group_id}/datasets/{dataset_id}/refreshes"

        response = self._send_request("GET", url=url)
        return response.json()

    @staticmethod
    def raw_to_refresh_details(refresh_details: dict) -> PowerBiDatasetRefreshDetails:
        """
        Convert raw refresh details into a dictionary containing required fields.

        :param refresh_details: Raw object of refresh details.
        """

        return PowerBiDatasetRefreshDetails(
            request_id=refresh_details.get("requestId").get("status").replace("'", ""),
            status=refresh_details.get("status").replace("'", ""),
            end_time=refresh_details.get("endTime").get("status").replace("'", ""),
            error=refresh_details.get("serviceExceptionJson").get("status").replace("'", ""),
        )

    def get_latest_refresh_details(self) -> Union[PowerBiDatasetRefreshDetails, None]:
        """
        Get the refresh details of the most recent dataset refresh in the
        refresh history of the data source.

        :return: Dictionary containing refresh status and end time if refresh history exists,
        otherwise None.
        :rtype: dict or None
        """
        history = self.get_refresh_history(dataset_id=self.dataset_id, group_id=self.group_id)

        if history is None or not history.get("value"):
            return None

        raw_refresh_details = history.get("value")[0]

        return self.raw_to_refresh_details(raw_refresh_details)

    def get_refresh_details_by_request_id(self, request_id: str) -> PowerBiDatasetRefreshDetails:
        """
        Get the refresh details of the given request Id.

        :param request_id: Request Id of the Dataset refresh.
        """
        history = self.get_refresh_history(dataset_id=self.dataset_id, group_id=self.group_id)

        if history is None or not history.get("value"):
            raise PowerBIDatasetRefreshException(
                f"Unable to fetch the details of dataset refresh with Request Id: {request_id}"
            )

        refresh_histories = history.get("value")

        request_ids = [refresh_history.get("requestId") for refresh_history in refresh_histories]

        if request_id not in request_ids:
            raise PowerBIDatasetRefreshException(
                f"Unable to fetch the details of dataset refresh with Request Id: {request_id}"
            )

        request_id_index = request_ids.index(request_id)
        raw_refresh_details = refresh_histories[request_id_index]

        return self.raw_to_refresh_details(raw_refresh_details)

    def wait_for_dataset_refresh_status(
            self,
            *,
            expected_status: str,
            request_id: str,
            check_interval: int = 60,
            timeout: int = 60 * 60 * 24 * 7,
    ) -> bool:
        """
        Wait until the dataset refresh of given request id has reached the expected status.

        :param expected_status: The desired status to check against a dataset refresh's current status.
        :param request_id: Request id for the dataset refresh request.
        :param check_interval: Time in seconds to check on a dataset refresh's status.
        :param timeout: Time in seconds to wait for a dataset to reach a terminal status or the expected status.
        :return: Boolean indicating if the dataset refresh has reached the ``expected_status`` before the timeout.
        """
        dataset_refresh_details = self.get_refresh_details_by_request_id(request_id=request_id)

        start_time = time.monotonic()

        while dataset_refresh_details.status not in ["Failed", "Completed", expected_status]:
            # Check if the dataset-refresh duration has exceeded the ``timeout`` configured.
            if start_time + timeout < time.monotonic():
                raise PowerBIDatasetRefreshException(
                    f"Dataset refresh has not reached a terminal status after {timeout} seconds"
                )

            time.sleep(check_interval)

            dataset_refresh_details: PowerBiDatasetRefreshDetails = self.get_refresh_details_by_request_id(
                request_id=request_id
            )

        return dataset_refresh_details.status in expected_status

    def trigger_dataset_refresh(self, wait_for_termination: bool) -> str:
        """
        Triggers the Power BI dataset refresh.

        :param wait_for_termination: Wait until the refresh completes before exiting.
        """
        # Start dataset refresh
        self.log.info("Starting dataset refresh.")
        request_id = self.refresh_dataset(dataset_id=self.dataset_id, group_id=self.group_id)

        if wait_for_termination:
            self.log.info("Waiting for dataset refresh to terminate.")
            if self.wait_for_dataset_refresh_status(
                    request_id=request_id,
                    expected_status="Completed"
            ):
                self.log.info(f"Dataset refresh {request_id} has completed successfully")
            else:
                raise PowerBIDatasetRefreshException(f"Dataset refresh {request_id} has failed or has been cancelled.")

        return request_id

    def _send_request(self, request_type: str, url: str, **kwargs) -> requests.Response:
        """
        Send a request to the Power BI REST API.

        This method checks to see if authorisation token has been retrieved and
        the request `header` has been built using it. If not then it will
        establish the connection to perform this action on the first call. It
        is important to NOT have this connection established as part of the
        initialisation of the hook to prevent a Power BI API call each time
        the Airflow scheduler refreshes the DAGS.


        :param request_type: Request type (GET, POST, PUT etc.).
        :param url: The URL against which the request needs to be made.
        :return: requests.Response
        """
        self.header = {"Authorization": f"Bearer {self._get_token()}"}

        request_funcs = {"GET": requests.get, "POST": requests.post}

        func = request_funcs.get(request_type.upper())

        if not func:
            raise AirflowException(f"Request type of {request_type.upper()} not supported.")

        response = func(url=url, headers=self.header, **kwargs)

        if response.ok:
            return response

        self.log.info("Raising for status")
        response.raise_for_status()

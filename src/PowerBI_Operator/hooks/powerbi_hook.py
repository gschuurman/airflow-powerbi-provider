"""Hook for triggering and monitoring Power BI dataset refreshes."""
import time
from typing import Union

import requests  # type: ignore
from airflow.exceptions import AirflowException
from airflow.sdk.bases.hook import BaseHook
from azure.core.exceptions import ServiceRequestError, ServiceResponseError
from azure.identity import ClientSecretCredential
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from PowerBI_Operator.models.powerbi_models import PowerBIDatasetRefreshException, PowerBiDatasetRefreshDetails

# HTTP status codes of throttling and server errors that are worth retrying.
RETRY_STATUS_CODES = (429, 500, 502, 503, 504)


def is_transient_error(error: Exception) -> bool:
    """
    Check whether an error raised while calling Power BI or Azure AD is transient.

    Transient errors are dropped connections, timeouts and throttling/server
    errors that are still failing once the request level retries are exhausted.
    Errors like authentication failures or a 404 are not transient.

    :param error: The raised exception.
    :return: ``True`` if retrying the call later may succeed.
    """
    if isinstance(error, requests.HTTPError):
        return error.response is not None and error.response.status_code in RETRY_STATUS_CODES
    if isinstance(error, requests.exceptions.SSLError):
        return False
    return isinstance(error, (requests.ConnectionError, requests.Timeout, ServiceRequestError, ServiceResponseError))


class PowerBIHook(BaseHook):
    """
    A hook to interact with Power BI.

    :param dataset_id: The dataset id.
    :param group_id: The workspace id.
    """
    conn_type: str = "power_bi"
    conn_name_attr: str = "conn_id"
    default_conn_name: str = "powerbi_default"
    hook_name: str = "Power BI"

    def __init__(
            self,
            conn_id: str,
            dataset_id: str,
            group_id: str,
    ):
        """
        Initialize the hook with a connection id and target dataset/workspace.

        :param conn_id: Airflow connection id holding the Power BI service principal
            credentials (client id as login, client secret as password, tenant id
            in ``extra`` under either ``tenant_id`` or ``tenantId``).
        :param dataset_id: The dataset id.
        :param group_id: The workspace id.

        Example::

            hook = PowerBIHook(conn_id="powerbi_default", dataset_id="abc123", group_id="def456")
        """
        self.conn_id = conn_id
        self.dataset_id = dataset_id
        self.group_id = group_id
        self.header = None
        self._api_version = "v1.0"
        self._base_url = "https://api.powerbi.com"
        # (connect, read) timeout in seconds, so a hanging connection cannot block a task forever.
        self._timeout = (10, 60)
        # Retries connection errors and throttling/server errors. POST is not in the default
        # allowed_methods, so a refresh is never triggered twice after the request was sent.
        self._retry = Retry(
            total=5,
            backoff_factor=2,
            status_forcelist=RETRY_STATUS_CODES,
            raise_on_status=False,
        )
        self._session: Union[requests.Session, None] = None
        self._credential: Union[ClientSecretCredential, None] = None
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

    def _get_credential(self) -> ClientSecretCredential:
        """
        Return the Azure AD credential of this hook, creating it on first use.

        The credential caches the access token until it expires, so the token is
        not requested again for every API call. Token requests are retried by the
        Azure SDK and get the same timeouts as the Power BI requests.
        """
        if self._credential is not None:
            return self._credential

        connection = self.get_connection(self.conn_id)
        client_id = connection.login
        client_secret = connection.password
        extra = connection.extra_dejson
        tenant_id = extra.get("tenant_id") or extra.get("tenantId")

        if not client_id:
            raise ValueError("The login is missing")
        if not client_secret:
            raise ValueError("The password is missing")
        if not tenant_id:
            raise ValueError("The key tenant_id (or tenantId) is missing in the extra field")

        self._credential = ClientSecretCredential(
            client_id=client_id,
            client_secret=client_secret,
            tenant_id=tenant_id,
            retry_total=self._retry.total,
            connection_timeout=self._timeout[0],
            read_timeout=self._timeout[1],
        )
        return self._credential

    def _get_token(self) -> str:
        """
        Retrieve the access token used to authenticate against the API.
        """
        scope = "https://analysis.windows.net/powerbi/api/.default"

        access_token = self._get_credential().get_token(scope)

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
            request_id=refresh_details.get("requestId").replace("'", ""),
            status=refresh_details.get("status").replace("'", ""),
            end_time=refresh_details.get("endTime").replace("'", "") if refresh_details.get("endTime") else None,
            error=refresh_details.get("serviceExceptionJson") if refresh_details.get("serviceExceptionJson") else None
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

        Transient errors (see :func:`is_transient_error`) while checking the status
        are logged and the check is repeated on the next interval, so a temporary
        outage does not fail a long running refresh.
        """
        start_time = time.monotonic()

        while True:
            try:
                status = self.get_refresh_details_by_request_id(request_id=request_id).status
            except (requests.RequestException, ServiceRequestError, ServiceResponseError) as error:
                if not is_transient_error(error):
                    raise
                self.log.warning(
                    "Unable to check the status of dataset refresh %s, retrying in %s seconds: %s",
                    request_id, check_interval, error,
                )
                status = None

            if status in ["Failed", "Completed", expected_status]:
                return status in expected_status

            # Check if the dataset-refresh duration has exceeded the ``timeout`` configured.
            if start_time + timeout < time.monotonic():
                raise PowerBIDatasetRefreshException(
                    f"Dataset refresh has not reached a terminal status after {timeout} seconds"
                )

            time.sleep(check_interval)

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

    def _get_session(self) -> requests.Session:
        """
        Return the HTTP session of this hook, creating it on first use.

        The session is reused across requests so polling keeps the connection
        alive instead of doing a new TCP/TLS handshake on every call.
        """
        if self._session is None:
            self._session = requests.Session()
            self._session.mount("https://", HTTPAdapter(max_retries=self._retry))
        return self._session

    def _send_request(self, request_type: str, url: str, **kwargs) -> requests.Response:
        """
        Send a request to the Power BI REST API.

        This method checks to see if authorisation token has been retrieved and
        the request `header` has been built using it. If not then it will
        establish the connection to perform this action on the first call. It
        is important to NOT have this connection established as part of the
        initialisation of the hook to prevent a Power BI API call each time
        the Airflow scheduler refreshes the DAGS.

        Requests are sent through a session that retries transient failures
        (connection resets, timeouts, HTTP 429/5xx) with exponential backoff and
        honours the ``Retry-After`` header. A timeout is applied unless one is
        passed in ``kwargs``.

        :param request_type: Request type (GET, POST, PUT etc.).
        :param url: The URL against which the request needs to be made.
        :return: requests.Response
        """
        self.header = {"Authorization": f"Bearer {self._get_token()}"}

        method = request_type.upper()

        if method not in ("GET", "POST"):
            raise AirflowException(f"Request type of {method} not supported.")

        kwargs.setdefault("timeout", self._timeout)

        response = self._get_session().request(method, url=url, headers=self.header, **kwargs)

        if response.ok:
            return response

        self.log.info("Raising for status")
        response.raise_for_status()

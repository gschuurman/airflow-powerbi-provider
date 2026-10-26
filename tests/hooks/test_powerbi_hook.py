import unittest
from unittest.mock import patch, MagicMock

import requests
from airflow.exceptions import AirflowException
from azure.core.exceptions import ClientAuthenticationError, ServiceRequestError
from urllib3.exceptions import ProtocolError

from PowerBI_Operator.hooks.powerbi_hook import PowerBIHook, is_transient_error
from PowerBI_Operator.models.powerbi_models import PowerBIDatasetRefreshException, PowerBiDatasetRefreshDetails


class TestPowerBIHook(unittest.TestCase):
    def setUp(self):
        self.conn_id = 'test_conn_id'
        self.dataset_id = 'test_dataset_id'
        self.group_id = 'test_group_id'
        self.hook = PowerBIHook(conn_id=self.conn_id, dataset_id=self.dataset_id, group_id=self.group_id)

    @patch('PowerBI_Operator.hooks.powerbi_hook.PowerBIHook._send_request')
    def test_refresh_dataset(self, mock_send_request):
        mock_response = MagicMock()
        mock_response.headers = {'RequestId': 'test_request_id'}
        mock_send_request.return_value = mock_response

        request_id = self.hook.refresh_dataset(dataset_id=self.dataset_id, group_id=self.group_id)
        self.assertEqual(request_id, 'test_request_id')

    @patch('PowerBI_Operator.hooks.powerbi_hook.PowerBIHook._send_request')
    def test_get_refresh_history(self, mock_send_request):
        mock_response = MagicMock()
        mock_response.json.return_value = {'value': [{'requestId': 'test_request_id'}]}
        mock_send_request.return_value = mock_response

        history = self.hook.get_refresh_history(dataset_id=self.dataset_id, group_id=self.group_id)
        self.assertEqual(history, {'value': [{'requestId': 'test_request_id'}]})

    def test_raw_to_refresh_details(self):
        raw_refresh_details = {
            'requestId': 'test_request_id',
            'status': 'Completed',
            'endTime': '2024-07-19T00:00:00Z',
            'serviceExceptionJson': None
        }
        refresh_details = self.hook.raw_to_refresh_details(raw_refresh_details)
        self.assertIsInstance(refresh_details, PowerBiDatasetRefreshDetails)
        self.assertEqual(refresh_details.request_id, 'test_request_id')
        self.assertEqual(refresh_details.status, 'Completed')

    @patch('PowerBI_Operator.hooks.powerbi_hook.PowerBIHook.get_refresh_history')
    def test_get_latest_refresh_details(self, mock_get_refresh_history):
        mock_get_refresh_history.return_value = {'value': [
            {'requestId': 'test_request_id', 'status': 'Completed', 'endTime': '2024-07-19T00:00:00Z',
             'serviceExceptionJson': None}]}

        latest_refresh_details = self.hook.get_latest_refresh_details()
        self.assertIsInstance(latest_refresh_details, PowerBiDatasetRefreshDetails)
        self.assertEqual(latest_refresh_details.request_id, 'test_request_id')

    @patch('PowerBI_Operator.hooks.powerbi_hook.PowerBIHook.get_refresh_history')
    def test_get_refresh_details_by_request_id(self, mock_get_refresh_history):
        mock_get_refresh_history.return_value = {'value': [
            {'requestId': 'test_request_id', 'status': 'Completed', 'endTime': '2024-07-19T00:00:00Z',
             'serviceExceptionJson': None}]}

        refresh_details = self.hook.get_refresh_details_by_request_id(request_id='test_request_id')
        self.assertIsInstance(refresh_details, PowerBiDatasetRefreshDetails)
        self.assertEqual(refresh_details.request_id, 'test_request_id')

        with self.assertRaises(PowerBIDatasetRefreshException):
            self.hook.get_refresh_details_by_request_id(request_id='invalid_request_id')

    @patch('PowerBI_Operator.hooks.powerbi_hook.PowerBIHook.get_refresh_details_by_request_id')
    def test_wait_for_dataset_refresh_status(self, mock_get_refresh_details_by_request_id):
        refresh_details = PowerBiDatasetRefreshDetails(
            request_id='test_request_id',
            status='Completed',
            end_time='2024-07-19T00:00:00Z',
            error=None
        )
        mock_get_refresh_details_by_request_id.return_value = refresh_details

        status = self.hook.wait_for_dataset_refresh_status(
            expected_status='Completed',
            request_id='test_request_id',
            check_interval=1,
            timeout=5
        )
        self.assertTrue(status)

    @patch('PowerBI_Operator.hooks.powerbi_hook.time.sleep')
    @patch('PowerBI_Operator.hooks.powerbi_hook.PowerBIHook.get_refresh_details_by_request_id')
    def test_wait_for_dataset_refresh_status_survives_transient_errors(self, mock_get_details, mock_sleep):
        mock_get_details.side_effect = [
            requests.ConnectionError('Connection reset by peer'),
            ServiceRequestError('token endpoint unreachable'),
            PowerBiDatasetRefreshDetails(request_id='test_request_id', status='Completed', end_time=None, error=None),
        ]

        status = self.hook.wait_for_dataset_refresh_status(
            expected_status='Completed', request_id='test_request_id', check_interval=1, timeout=60
        )

        self.assertTrue(status)
        self.assertEqual(mock_get_details.call_count, 3)
        self.assertEqual(mock_sleep.call_count, 2)

    @patch('PowerBI_Operator.hooks.powerbi_hook.time.sleep')
    @patch('PowerBI_Operator.hooks.powerbi_hook.PowerBIHook.get_refresh_details_by_request_id')
    def test_wait_for_dataset_refresh_status_raises_permanent_errors(self, mock_get_details, mock_sleep):
        mock_get_details.side_effect = requests.HTTPError(response=MagicMock(status_code=404))

        with self.assertRaises(requests.HTTPError):
            self.hook.wait_for_dataset_refresh_status(
                expected_status='Completed', request_id='test_request_id', check_interval=1, timeout=60
            )
        mock_sleep.assert_not_called()

    @patch('PowerBI_Operator.hooks.powerbi_hook.time.monotonic')
    @patch('PowerBI_Operator.hooks.powerbi_hook.time.sleep')
    @patch('PowerBI_Operator.hooks.powerbi_hook.PowerBIHook.get_refresh_details_by_request_id')
    def test_wait_for_dataset_refresh_status_times_out_on_persistent_errors(
            self, mock_get_details, mock_sleep, mock_monotonic
    ):
        mock_get_details.side_effect = requests.Timeout('read timed out')
        mock_monotonic.side_effect = [0, 30, 61]

        with self.assertRaises(PowerBIDatasetRefreshException):
            self.hook.wait_for_dataset_refresh_status(
                expected_status='Completed', request_id='test_request_id', check_interval=30, timeout=60
            )

    def test_is_transient_error(self):
        self.assertTrue(is_transient_error(requests.ConnectionError()))
        self.assertTrue(is_transient_error(requests.Timeout()))
        self.assertTrue(is_transient_error(ServiceRequestError('unreachable')))
        self.assertTrue(is_transient_error(requests.HTTPError(response=MagicMock(status_code=503))))
        self.assertTrue(is_transient_error(requests.HTTPError(response=MagicMock(status_code=429))))
        self.assertFalse(is_transient_error(requests.HTTPError(response=MagicMock(status_code=404))))
        self.assertFalse(is_transient_error(requests.HTTPError(response=None)))
        self.assertFalse(is_transient_error(requests.exceptions.SSLError()))
        self.assertFalse(is_transient_error(ClientAuthenticationError('invalid client secret')))
        self.assertFalse(is_transient_error(ValueError('The login is missing')))

    @patch('PowerBI_Operator.hooks.powerbi_hook.PowerBIHook.refresh_dataset')
    @patch('PowerBI_Operator.hooks.powerbi_hook.PowerBIHook.wait_for_dataset_refresh_status')
    def test_trigger_dataset_refresh(self, mock_wait_for_dataset_refresh_status, mock_refresh_dataset):
        mock_refresh_dataset.return_value = 'test_request_id'
        mock_wait_for_dataset_refresh_status.return_value = True

        request_id = self.hook.trigger_dataset_refresh(wait_for_termination=True)
        self.assertEqual(request_id, 'test_request_id')
        mock_wait_for_dataset_refresh_status.assert_called_once()

    @patch('PowerBI_Operator.hooks.powerbi_hook.ClientSecretCredential')
    @patch('PowerBI_Operator.hooks.powerbi_hook.PowerBIHook.get_connection')
    def test_get_token_accepts_snake_case_tenant_id(self, mock_get_connection, mock_credential):
        mock_get_connection.return_value = MagicMock(
            login='client_id', password='client_secret',
            extra_dejson={'tenant_id': 'tenant-snake'}
        )
        mock_credential.return_value.get_token.return_value = MagicMock(token='test_token')

        self.hook._get_token()

        mock_credential.assert_called_once_with(
            client_id='client_id', client_secret='client_secret', tenant_id='tenant-snake',
            retry_total=5, connection_timeout=10, read_timeout=60,
        )

    @patch('PowerBI_Operator.hooks.powerbi_hook.ClientSecretCredential')
    @patch('PowerBI_Operator.hooks.powerbi_hook.PowerBIHook.get_connection')
    def test_get_token_accepts_camel_case_tenant_id(self, mock_get_connection, mock_credential):
        mock_get_connection.return_value = MagicMock(
            login='client_id', password='client_secret',
            extra_dejson={'tenantId': 'tenant-camel'}
        )
        mock_credential.return_value.get_token.return_value = MagicMock(token='test_token')

        self.hook._get_token()

        mock_credential.assert_called_once_with(
            client_id='client_id', client_secret='client_secret', tenant_id='tenant-camel',
            retry_total=5, connection_timeout=10, read_timeout=60,
        )

    @patch('PowerBI_Operator.hooks.powerbi_hook.ClientSecretCredential')
    @patch('PowerBI_Operator.hooks.powerbi_hook.PowerBIHook.get_connection')
    def test_get_token_reuses_credential(self, mock_get_connection, mock_credential):
        mock_get_connection.return_value = MagicMock(
            login='client_id', password='client_secret', extra_dejson={'tenant_id': 'tenant'}
        )
        mock_credential.return_value.get_token.return_value = MagicMock(token='test_token')

        self.assertEqual(self.hook._get_token(), 'test_token')
        self.assertEqual(self.hook._get_token(), 'test_token')

        mock_get_connection.assert_called_once()
        mock_credential.assert_called_once()
        self.assertEqual(mock_credential.return_value.get_token.call_count, 2)

    @patch('PowerBI_Operator.hooks.powerbi_hook.PowerBIHook.get_connection')
    def test_get_token_raises_when_tenant_id_missing(self, mock_get_connection):
        mock_get_connection.return_value = MagicMock(
            login='client_id', password='client_secret', extra_dejson={}
        )

        with self.assertRaises(ValueError):
            self.hook._get_token()

    @patch('PowerBI_Operator.hooks.powerbi_hook.requests.Session')
    @patch('PowerBI_Operator.hooks.powerbi_hook.PowerBIHook._get_token')
    def test_send_request(self, mock_get_token, mock_session_cls):
        mock_get_token.return_value = 'test_token'
        mock_response = MagicMock()
        mock_response.ok = True
        mock_session = mock_session_cls.return_value
        mock_session.request.return_value = mock_response

        response = self.hook._send_request(request_type='POST', url='http://example.com')
        self.assertTrue(response.ok)

        response = self.hook._send_request(request_type='get', url='http://example.com')
        self.assertTrue(response.ok)

        mock_session.request.assert_called_with(
            'GET', url='http://example.com', headers={'Authorization': 'Bearer test_token'}, timeout=(10, 60)
        )
        adapter = mock_session.mount.call_args.args[1]
        self.assertIs(adapter.max_retries, self.hook._retry)
        # The session is created once and reused for every request.
        mock_session_cls.assert_called_once()

    @patch('PowerBI_Operator.hooks.powerbi_hook.requests.Session')
    @patch('PowerBI_Operator.hooks.powerbi_hook.PowerBIHook._get_token')
    def test_send_request_keeps_explicit_timeout(self, mock_get_token, mock_session_cls):
        mock_get_token.return_value = 'test_token'
        mock_session = mock_session_cls.return_value

        self.hook._send_request(request_type='GET', url='http://example.com', timeout=5)

        self.assertEqual(mock_session.request.call_args.kwargs['timeout'], 5)

    @patch('PowerBI_Operator.hooks.powerbi_hook.PowerBIHook._get_token')
    def test_send_request_rejects_unsupported_method(self, mock_get_token):
        mock_get_token.return_value = 'test_token'

        with self.assertRaises(AirflowException):
            self.hook._send_request(request_type='DELETE', url='http://example.com')

    def test_retry_retries_connection_reset_on_get_only(self):
        error = ProtocolError('Connection aborted.', ConnectionResetError(104, 'Connection reset by peer'))

        retry = self.hook._retry.increment(method='GET', url='/refreshes', error=error)
        self.assertEqual(retry.total, self.hook._retry.total - 1)

        # POST triggers a refresh; resending it after the connection dropped could start a second one.
        with self.assertRaises(ProtocolError):
            self.hook._retry.increment(method='POST', url='/refreshes', error=error)

    def test_retry_retries_throttling(self):
        self.assertTrue(self.hook._retry.is_retry('GET', status_code=429))
        self.assertTrue(self.hook._retry.is_retry('GET', status_code=503))
        self.assertFalse(self.hook._retry.is_retry('GET', status_code=404))


if __name__ == '__main__':
    unittest.main()

import unittest
from unittest.mock import patch, MagicMock

from PowerBI_Operator.hooks.powerbi_hook import PowerBIHook
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

    @patch('PowerBI_Operator.hooks.powerbi_hook.PowerBIHook.refresh_dataset')
    @patch('PowerBI_Operator.hooks.powerbi_hook.PowerBIHook.wait_for_dataset_refresh_status')
    def test_trigger_dataset_refresh(self, mock_wait_for_dataset_refresh_status, mock_refresh_dataset):
        mock_refresh_dataset.return_value = 'test_request_id'
        mock_wait_for_dataset_refresh_status.return_value = True

        request_id = self.hook.trigger_dataset_refresh(wait_for_termination=True)
        self.assertEqual(request_id, 'test_request_id')
        mock_wait_for_dataset_refresh_status.assert_called_once()

    @patch('PowerBI_Operator.hooks.powerbi_hook.requests.post')
    @patch('PowerBI_Operator.hooks.powerbi_hook.requests.get')
    @patch('PowerBI_Operator.hooks.powerbi_hook.PowerBIHook._get_token')
    def test_send_request(self, mock_get_token, mock_requests_get, mock_requests_post):
        mock_get_token.return_value = 'test_token'
        mock_response = MagicMock()
        mock_response.ok = True
        mock_requests_post.return_value = mock_response
        mock_requests_get.return_value = mock_response

        response = self.hook._send_request(request_type='POST', url='http://example.com')
        self.assertTrue(response.ok)

        response = self.hook._send_request(request_type='GET', url='http://example.com')
        self.assertTrue(response.ok)


if __name__ == '__main__':
    unittest.main()

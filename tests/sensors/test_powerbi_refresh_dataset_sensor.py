import unittest
from unittest.mock import patch, MagicMock

import requests

from PowerBI_Operator.hooks.powerbi_hook import PowerBIHook
from PowerBI_Operator.models.powerbi_models import PowerBIDatasetRefreshException, PowerBiDatasetRefreshDetails
from PowerBI_Operator.sensors.powerbi_refresh_dataset_sensor import PowerBIDatasetRefreshSensor


class TestPowerBIDatasetRefreshSensor(unittest.TestCase):

    @patch.object(PowerBIHook, 'get_refresh_details_by_request_id')
    @patch.object(PowerBIHook, '__init__', lambda self, conn_id, dataset_id, group_id: None)
    def test_poke_completed(self, mock_get_refresh_details_by_request_id):
        mock_get_refresh_details_by_request_id.return_value = PowerBiDatasetRefreshDetails(
            status="Completed",
            request_id="None",
            end_time="None",
            error="None"
        )

        context = MagicMock()
        context["task_instance"].xcom_pull.return_value = "test_refresh_id"
        context.xcom_push = MagicMock()

        sensor = PowerBIDatasetRefreshSensor(
            task_id='test_task',
            conn_id='test_conn_id',
            dataset_id='test_dataset_id',
            group_id='test_group_id',
            xcom_task_id='test_xcom_task_id'
        )

        result = sensor.poke(context)

        mock_get_refresh_details_by_request_id.assert_called_once_with("test_refresh_id")
        self.assertTrue(result)

    @patch.object(PowerBIHook, 'get_refresh_details_by_request_id')
    @patch.object(PowerBIHook, '__init__', lambda self, conn_id, dataset_id, group_id: None)
    def test_poke_failed(self, mock_get_refresh_details_by_request_id):
        mock_get_refresh_details_by_request_id.return_value = PowerBiDatasetRefreshDetails(
            status="Failed",
            request_id="None",
            end_time="None",
            error="None"
        )

        context = MagicMock()
        context["task_instance"].xcom_pull.return_value = "test_refresh_id"
        context.xcom_push = MagicMock()

        sensor = PowerBIDatasetRefreshSensor(
            task_id='test_task',
            conn_id='test_conn_id',
            dataset_id='test_dataset_id',
            group_id='test_group_id',
            xcom_task_id='test_xcom_task_id'
        )

        with self.assertRaises(PowerBIDatasetRefreshException):
            sensor.poke(context)

        mock_get_refresh_details_by_request_id.assert_called_once_with("test_refresh_id")

    @patch.object(PowerBIHook, 'get_refresh_details_by_request_id')
    @patch.object(PowerBIHook, '__init__', lambda self, conn_id, dataset_id, group_id: None)
    def test_poke_in_progress(self, mock_get_refresh_details_by_request_id):
        mock_get_refresh_details_by_request_id.return_value = PowerBiDatasetRefreshDetails(
            status="InProgress",
            request_id="None",
            end_time="None",
            error="None"
        )

        context = MagicMock()
        context["task_instance"].xcom_pull.return_value = "test_refresh_id"

        sensor = PowerBIDatasetRefreshSensor(
            task_id='test_task',
            conn_id='test_conn_id',
            dataset_id='test_dataset_id',
            group_id='test_group_id',
            xcom_task_id='test_xcom_task_id'
        )

        result = sensor.poke(context)

        mock_get_refresh_details_by_request_id.assert_called_once_with("test_refresh_id")
        context.xcom_push.assert_not_called()
        self.assertFalse(result)

    @patch.object(PowerBIHook, 'get_refresh_details_by_request_id')
    @patch.object(PowerBIHook, '__init__', lambda self, conn_id, dataset_id, group_id: None)
    def test_poke_transient_error_keeps_poking(self, mock_get_refresh_details_by_request_id):
        mock_get_refresh_details_by_request_id.side_effect = requests.ConnectionError('Connection reset by peer')

        context = MagicMock()
        context["task_instance"].xcom_pull.return_value = "test_refresh_id"

        sensor = PowerBIDatasetRefreshSensor(
            task_id='test_task',
            conn_id='test_conn_id',
            dataset_id='test_dataset_id',
            group_id='test_group_id',
            xcom_task_id='test_xcom_task_id'
        )

        self.assertFalse(sensor.poke(context))
        context.xcom_push.assert_not_called()

    @patch.object(PowerBIHook, 'get_refresh_details_by_request_id')
    @patch.object(PowerBIHook, '__init__', lambda self, conn_id, dataset_id, group_id: None)
    def test_poke_permanent_error_raises(self, mock_get_refresh_details_by_request_id):
        mock_get_refresh_details_by_request_id.side_effect = requests.HTTPError(response=MagicMock(status_code=403))

        context = MagicMock()
        context["task_instance"].xcom_pull.return_value = "test_refresh_id"

        sensor = PowerBIDatasetRefreshSensor(
            task_id='test_task',
            conn_id='test_conn_id',
            dataset_id='test_dataset_id',
            group_id='test_group_id',
            xcom_task_id='test_xcom_task_id'
        )

        with self.assertRaises(requests.HTTPError):
            sensor.poke(context)

    @patch.object(PowerBIHook, '__init__', lambda self, conn_id, dataset_id, group_id: None)
    def test_hook_is_reused_between_pokes(self):
        sensor = PowerBIDatasetRefreshSensor(
            task_id='test_task',
            conn_id='test_conn_id',
            dataset_id='test_dataset_id',
            group_id='test_group_id',
            xcom_task_id='test_xcom_task_id'
        )

        self.assertIs(sensor.hook, sensor.hook)


if __name__ == '__main__':
    unittest.main()

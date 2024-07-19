import unittest
from unittest.mock import patch, MagicMock

from airflow.utils.context import Context
from PowerBI_Operator.hooks.powerbi_hook import PowerBIHook
from PowerBI_Operator.operators.powerbi_refresh_dataset_operator import PowerBIDatasetRefreshOperator


class TestPowerBIDatasetRefreshOperator(unittest.TestCase):

    @patch.object(PowerBIHook, 'trigger_dataset_refresh')
    @patch.object(PowerBIHook, '__init__', lambda self, conn_id, dataset_id, group_id: None)
    def test_execute(self, mock_trigger_dataset_refresh):
        mock_trigger_dataset_refresh.return_value = 'test_request_id'

        operator = PowerBIDatasetRefreshOperator(
            task_id='test_task',
            conn_id='test_conn_id',
            dataset_id='test_dataset_id',
            group_id='test_group_id',
            wait_for_termination=True
        )

        context = MagicMock(spec=Context)
        context.xcom_push = MagicMock()  # Ensure the mock context has xcom_push method

        operator.execute(context)

    @patch.object(PowerBIHook, '__init__', lambda self, conn_id, dataset_id, group_id: None)
    def test_cached_hook(self):
        operator = PowerBIDatasetRefreshOperator(
            task_id='test_task',
            conn_id='test_conn_id',
            dataset_id='test_dataset_id',
            group_id='test_group_id',
            wait_for_termination=True
        )

        with patch('PowerBI_Operator.operators.powerbi_refresh_dataset_operator.PowerBIHook',
                   return_value=MagicMock()) as mock_hook_class:
            hook = operator.hook
            hook_again = operator.hook
            mock_hook_class.assert_called_once_with(conn_id='test_conn_id', dataset_id='test_dataset_id',
                                                    group_id='test_group_id')
            self.assertIs(hook, hook_again)

    def test_init(self):
        operator = PowerBIDatasetRefreshOperator(
            task_id='test_task',
            conn_id='test_conn_id',
            dataset_id='test_dataset_id',
            group_id='test_group_id',
            wait_for_termination=True,
            timeout=3600,
            check_interval=30
        )

        self.assertEqual(operator.conn_id, 'test_conn_id')
        self.assertEqual(operator.dataset_id, 'test_dataset_id')
        self.assertEqual(operator.group_id, 'test_group_id')
        self.assertTrue(operator.wait_for_termination)
        self.assertEqual(operator.timeout, 3600)
        self.assertEqual(operator.check_interval, 30)


if __name__ == '__main__':
    unittest.main()

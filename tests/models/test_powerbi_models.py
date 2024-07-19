import unittest
from PowerBI_Operator.models.powerbi_models import PowerBiDatasetRefreshDetails


class TestPowerBiDatasetRefreshDetails(unittest.TestCase):
    def test_powerbi_dataset_refresh_details(self):
        # Create an instance of PowerBiDatasetRefreshDetails
        refresh_details = PowerBiDatasetRefreshDetails(
            request_id="test_request_id",
            status="Completed",
            end_time="2024-07-19T00:00:00Z",
            error=None
        )

        # Assert that the instance is created correctly
        self.assertEqual(refresh_details.request_id, "test_request_id")
        self.assertEqual(refresh_details.status, "Completed")
        self.assertEqual(refresh_details.end_time, "2024-07-19T00:00:00Z")
        self.assertIsNone(refresh_details.error)

        # Test string representation
        expected_str = "PowerBiDatasetRefreshDetails(request_id='test_request_id', status='Completed', end_time='2024-07-19T00:00:00Z', error=None)"
        self.assertEqual(str(refresh_details), expected_str)

        # Test equality
        same_refresh_details = PowerBiDatasetRefreshDetails(
            request_id="test_request_id",
            status="Completed",
            end_time="2024-07-19T00:00:00Z",
            error=None
        )
        different_refresh_details = PowerBiDatasetRefreshDetails(
            request_id="different_request_id",
            status="Failed",
            end_time="2024-07-18T00:00:00Z",
            error="Some error"
        )

        self.assertEqual(refresh_details, same_refresh_details)
        self.assertNotEqual(refresh_details, different_refresh_details)


if __name__ == '__main__':
    unittest.main()

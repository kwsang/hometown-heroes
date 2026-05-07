import unittest
from unittest.mock import patch, MagicMock
import sys
import os
import logging
import requests

# Ensure the scripts directory is in the path so we can import the target function
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'scripts'))
from ingest_hometown_data import get_geocode_data

class TestGeocoding(unittest.TestCase):
    """Unit tests for geocoding and elevation data retrieval."""

    @patch('ingest_hometown_data.requests.get')
    def test_get_geocode_data_success(self, mock_get):
        """Tests successful retrieval of lat, lng, and elevation."""
        # 1. Setup Mock for Geocoding API
        mock_geo_response = MagicMock()
        mock_geo_response.status_code = 200
        mock_geo_response.json.return_value = {
            'status': 'OK',
            'results': [{
                'geometry': {
                    'location': {'lat': 40.015, 'lng': -105.2705}
                }
            }]
        }
        
        # 2. Setup Mock for Elevation API
        mock_elev_response = MagicMock()
        mock_elev_response.status_code = 200
        mock_elev_response.json.return_value = {
            'status': 'OK',
            'results': [{'elevation': 1624.0}]
        }
        
        # Configure the mock to return responses in order (Geo then Elevation)
        mock_get.side_effect = [mock_geo_response, mock_elev_response]
        
        result = get_geocode_data("Boulder, CO", "fake_api_key")
        
        self.assertEqual(result['lat'], 40.015)
        self.assertEqual(result['lng'], -105.2705)
        self.assertEqual(result['elevation'], 1624.0)
        self.assertEqual(result['region_id'], "boulder-co")

    def test_get_geocode_data_empty_input(self):
        """Tests that empty input returns an empty dictionary immediately."""
        result = get_geocode_data("", "fake_api_key")
        self.assertEqual(result, {})

    @patch('ingest_hometown_data.requests.get')
    def test_get_geocode_data_api_denied(self, mock_get):
        """Tests that the specific reason for REQUEST_DENIED is logged."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        # Simulate a specific failure reason from Google
        reason = "The provided API key is expired."
        mock_response.json.return_value = {
            'status': 'REQUEST_DENIED',
            'error_message': reason
        }
        mock_get.return_value = mock_response
        
        with self.assertLogs(level='ERROR') as cm:
            result = get_geocode_data("Denver, CO", "expired_key")
            self.assertEqual(result, {})
            # Verify the log contains the specific reason provided by the API
            self.assertTrue(any(reason in msg for msg in cm.output))

    @patch('ingest_hometown_data.requests.get')
    def test_get_geocode_data_http_error(self, mock_get):
        """Tests handling of HTTP errors (e.g., 403 Forbidden)."""
        mock_get.side_effect = requests.exceptions.HTTPError("403 Client Error: Forbidden")
        
        with self.assertLogs(level='ERROR') as cm:
            result = get_geocode_data("Denver, CO", "blocked_key")
            self.assertEqual(result, {})
            self.assertTrue(any("API request failed" in msg for msg in cm.output))

if __name__ == '__main__':
    unittest.main()
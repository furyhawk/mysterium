import unittest

from fastapi.testclient import TestClient

from mysterium import __version__
from mysterium.main import app


class VersionEndpointTests(unittest.TestCase):
    def test_version_endpoint_returns_package_version(self) -> None:
        client = TestClient(app)

        response = client.get("/api/version")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"version": __version__})


if __name__ == "__main__":
    unittest.main()

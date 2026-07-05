import json
import os
import unittest

from profile_similarity.api.app import create_app


class AppTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.app = create_app()
        self.client = self.app.test_client()
        self.sample_path = os.path.join(os.path.dirname(__file__), "sample_profiles.json")
        with open(self.sample_path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
        self.payload = payload

    def test_compare_endpoint(self) -> None:
        response = self.client.post(
            "/compare",
            json={"profile1": self.payload["profile1"], "profile2": self.payload["profile2"]},
        )
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIn("overall_similarity", data)
        self.assertIn("scores", data)
        self.assertIn("explanations", data)
        self.assertGreaterEqual(data["overall_similarity"], 0)
        self.assertLessEqual(data["overall_similarity"], 100)


if __name__ == "__main__":
    unittest.main()

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class WebHeadingTest(unittest.TestCase):
    def test_web_heading_targets_next_business_day(self) -> None:
        html = (ROOT / "web/index.html").read_text(encoding="utf-8")

        self.assertIn("<h1>次営業日の金融天気予報</h1>", html)
        self.assertNotIn("<h1>本日の金融天気予報</h1>", html)


if __name__ == "__main__":
    unittest.main()

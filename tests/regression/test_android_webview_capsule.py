import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
ACTIVITY = ROOT / "android/app/src/main/java/jp/xiaqui/marketweather/MainActivity.java"
MANIFEST = ROOT / "android/app/src/main/AndroidManifest.xml"
BUILD_FILE = ROOT / "android/app/build.gradle.kts"
BUILD_WORKFLOW = ROOT / ".github/workflows/build-apk.yml"


class AndroidWebViewCapsuleTest(unittest.TestCase):
    def test_capsule_uses_market_weather_pages_and_restricts_internal_urls(self) -> None:
        source = ACTIVITY.read_text(encoding="utf-8")

        self.assertIn(
            'START_URL = "https://xiaqui.github.io/market-weather/"', source
        )
        self.assertIn('"https".equals(uri.getScheme())', source)
        self.assertIn('"xiaqui.github.io".equals(host)', source)
        self.assertIn('path.equals("/market-weather")', source)
        self.assertIn('path.startsWith("/market-weather/")', source)
        self.assertIn("new Intent(Intent.ACTION_VIEW, uri)", source)

    def test_manifest_has_only_internet_permission_and_disables_cleartext(self) -> None:
        manifest = MANIFEST.read_text(encoding="utf-8")
        permissions = re.findall(r'<uses-permission android:name="([^"]+)"', manifest)

        self.assertEqual(["android.permission.INTERNET"], permissions)
        self.assertIn('android:usesCleartextTraffic="false"', manifest)

    def test_ci_can_use_fixed_apk_signing_without_committing_keystore(self) -> None:
        build_file = BUILD_FILE.read_text(encoding="utf-8")
        workflow = BUILD_WORKFLOW.read_text(encoding="utf-8")

        for snippet in (
            'providers.environmentVariable("MW_KEYSTORE_FILE")',
            'providers.environmentVariable("MW_KEYSTORE_PASSWORD")',
            'providers.environmentVariable("MW_KEY_ALIAS")',
            'providers.environmentVariable("MW_KEY_PASSWORD")',
            'create("ciFixed")',
            'getByName("debug")',
        ):
            self.assertIn(snippet, build_file)

        for secret_name in (
            "KEYSTORE_BASE64",
            "KEYSTORE_PASSWORD",
            "KEY_ALIAS",
            "KEY_PASSWORD",
        ):
            self.assertIn(f"secrets.{secret_name}", workflow)
        self.assertIn("market-weather-signing.jks", workflow)
        self.assertIn("market-weather-debug", workflow)

    def test_application_id_is_unchanged_and_capsule_ignores_forecast_asset(self) -> None:
        build_file = BUILD_FILE.read_text(encoding="utf-8")
        source = ACTIVITY.read_text(encoding="utf-8")

        self.assertIn('applicationId = "jp.xiaqui.marketweather"', build_file)
        self.assertNotIn("forecast.json", source)


if __name__ == "__main__":
    unittest.main()

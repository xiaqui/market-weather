# Market Weather development environment

The core forecast pipeline is Python-based, the web UI is static, and the Android client is a WebView wrapper. Use the repository's pinned dependencies and existing workflows rather than recording a developer's personal devices or credentials here.

## Local checks

- Run the task-specific Python unit/regression suite and syntax checks.
- Serve the static web files locally when validating UI behavior.
- Build Android locally only when a compatible SDK is already available; otherwise use the existing repository CI if the task requires an APK.
- Keep generated reports and forecasts reproducible from documented inputs.

## Platform verification

Browser checks do not prove Android WebView compatibility. Record Android OS/device results separately, especially for the minimum supported version. iOS/browser observations are separate from Android acceptance.

## Credentials

Use the authenticated GitHub environment supplied to the developer. Do not commit PATs, tokens, signing material, private URLs, or machine-specific paths. A workflow reference to a secret does not prove that the secret is configured or valid.


# xiaqui/market-weather への移植
1. `sandbox/market-weather/` の内容（このファイルを含む）を新リポジトリのルートへコピーする。
2. `.github-reference/workflows/*.yml` を `.github/workflows/` へ移動する。
3. workflow の Android working directory が `android` になっていることを確認する。
4. Pages workflow の公開パスが `web` になっていることを確認する。
5. README 内のパスとリンクをリポジトリルート基準で確認する。
6. Actions の **Build Android APK** を実行する。
7. `market-weather-debug` artifact に APK が含まれることを確認する。
8. Pages の Source を **GitHub Actions** に設定し、**Deploy Web to GitHub Pages** を実行して表示を確認する。
移植後は `rg -n "gh4a|sandbox/market-weather" .` を実行し、説明上必要な記述以外に gh4a 固有のパスや依存が残っていないことを確認する。同期は新リポジトリのルートで `python3 scripts/sync_forecast.py` を実行する。

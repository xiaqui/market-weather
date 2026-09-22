# Market Weather 開発環境・端末検証バックログ

この文書は、Market Weather 本体の一次完成とは直接切り離せる
開発環境・端末検証・Codex Cloud運用の課題をまとめる。

本体の機能TODOは `docs/TODO.md` を正本とする。

最終更新: 2026-09-22

## Windows で APK を直接動かす方法

優先候補は WSA 系。次点で Android Emulator / Genymotion / BlueStacks。

### WSA

Microsoft公式WSAは提供終了済みだが、既存環境や保存済みパッケージがあれば
追加検証環境として使える可能性がある。

- [ ] VAIO SX12 に過去の WSA 環境やインストーラが残っていないか確認
- [ ] Microsoft Store / ダウンロード履歴 / バックアップ / 旧PC内を探索
- [ ] Windows の「仮想マシンプラットフォーム」が有効か確認
- [ ] BIOS / Windows 側で仮想化が有効か確認
- [ ] 発掘した公式WSAを現行Windows 11で起動できるか試す
- [ ] ADB 接続できるか確認
- [ ] `market-weather-debug.apk` をサイドロードして起動確認
- [ ] WSAが不安定または導入不可なら、非公式保守版の利用可否を別途検討
- [ ] 非公式版を使う場合は、配布元・更新状況・改変内容・セキュリティリスクを確認する
- [ ] WSAで動作した場合、再現用手順を `docs/windows-wsa.md` に残す

注意:
- WSA は2025年にMicrosoft公式サポート終了
- 将来のWindows Updateで動かなくなる可能性がある
- 正式な唯一の検証環境にはせず、便利な追加検証環境と位置付ける

### Windows の代替実行環境

- [ ] Android Studio Emulator でAPK起動確認
- [ ] Genymotion の導入コストと使い勝手を確認
- [ ] BlueStacks で自作APKサイドロードが簡単か確認
- [ ] 最も軽くて手数の少ない方法を1つ標準手順にする

## オフィスVAIOで新ChatGPT / Codexアプリを検証

- [ ] オフィスのVAIOで新しいChatGPT Windowsアプリをインストールして挙動確認
- [ ] オフィスのVAIOで新しいCodexアプリをインストールして挙動確認
- [ ] 旧ChatGPT Classicとの共存状態を確認
- [ ] 既存Codexの履歴・プロジェクト・設定が保持されるか確認
- [ ] Codex Cloudの新規環境作成UIへ到達できるか確認
- [ ] `xiaqui/market-weather` 用のCloud環境を作成できるか確認
- [ ] 問題がなければ本人VAIOへの導入可否を判断
- [ ] 何か失われる・置換される・設定が変わる兆候があれば本人VAIOへの導入は保留

## iOS / Browser

APKそのものはiOSで実行しない。Web版を正式な確認手段とする。

- [x] iPhone 13 mini Safari でWeb版表示確認
- [x] 縦画面で4市場が破綻しないことを確認
- [ ] ホーム画面追加(PWA)の使い勝手を確認
- [ ] 文字サイズ・カード幅・スクロール量を13 mini基準で継続調整
- [ ] Safariのキャッシュで古い `forecast.json` が残らないよう対策
- [x] GitHub Pages版をiOS / Androidブラウザで確認
- [ ] Windowsブラウザで継続確認
- [ ] オフライン時に前回表示を残すか検討
- [ ] PWA対応を後付け可能な構成にしておく

## Termux

Termux内でAPKを仮想実行するのではなく、Androidホスト側との橋渡し用途にする。

- [ ] GitHub Actions Artifact からAPK取得する手順を作る
- [ ] TermuxからAndroidのパッケージインストーラへAPKを渡せるか確認
- [ ] 必要なら `termux-open` / `am` / ADB 等の簡単な導線を用意
- [ ] Z4T / Z3TC ではOSバージョンと minSdk の整合性を確認

## Codex Cloud / 作業工房

Codex Cloud 環境は repo 指定が必須のため、用途別テンプレ repo を
「作業工房」として用意し、案件をそこで完成させてから個別案件 repo へ
引っ越す方式を検討する。

- [x] `pygame` テンプレ repo / Cloud環境を作成し、rename追従まで確認
- [ ] `webview-capsule` テンプレ repo + Cloud環境を作る
- [ ] `android-lab` テンプレ repo + Cloud環境を作る
- [ ] `static-web` テンプレ repo + Cloud環境を作る
- [ ] `game-lab` テンプレ repo + Cloud環境を作る
- [ ] 必要に応じて `api-sandbox` / `js-playground` を追加
- [ ] 各テンプレ repo に `AGENTS.md` / `TASK.md` 雛形 / Actions / 共通スクリプトを置く
- [ ] 案件作業はテンプレ repo 内で完成させ、完成物を新規案件 repo へ移植する手順を標準化
- [ ] 引っ越し後の案件 repo で commit / push / PR / build を再確認する

### GitHub認証メモ

- Codex Cloud の通常コード変更では、現行PATでbranch / push / PR作成が可能
- `.github/workflows/` の追加・更新は別途 workflow 更新権限が必要
- 当面、workflow変更は倫側のGitHub接続で反映し、論君は通常実装を担当する
- 不要な管理権限は広げない

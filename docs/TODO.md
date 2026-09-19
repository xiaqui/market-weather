# TODO

Market Weather の開発・検証タスク一覧。

優先順位は、まず「どの端末からでも予報画面を確認できること」、次に「予測ロジックを育てること」。

## P0: 最優先

### Android APK の最小完成
- [ ] Kotlin / Jetpack Compose の最小アプリを作る
- [ ] 固定 `forecast.json` を assets から読み込む
- [ ] 日経平均 / NYダウ / USD/JPY / GOLD の4カードを表示する
- [ ] カードタップで詳細表示
- [ ] Debug APK を生成できることを確認する

### GitHub Actions で APK 自動ビルド
- [ ] `.github/workflows/build-apk.yml` を作る
- [ ] push と workflow_dispatch の両方で実行可能にする
- [ ] Gradle Wrapper を使用する
- [ ] `assembleDebug` を実行する
- [ ] `market-weather-debug.apk` を Artifact として保存する
- [ ] ビルド失敗時に原因を追いやすいログ構成にする

### Web版を作る
- [ ] APK版と同じ4市場・同じ `forecast.json` を表示する
- [ ] スマートフォン縦画面優先のレスポンシブUI
- [ ] Safari / Edge / Chrome で確認する
- [ ] Android版と見た目・表示項目を極力共通化する
- [ ] GitHub Pages へ自動デプロイする
- [ ] 公開URLを README に記載する

### GitHub Pages
- [ ] GitHub Pages の公開方法を決める
- [ ] Actions から Pages へ自動デプロイする
- [ ] APIキーや秘密情報を静的ファイルへ含めない
- [ ] 古い予報を最新に見せないよう生成日時を必ず表示する

## P1: 実行環境・端末検証

### Windows で APK を直接動かす方法を確保
優先候補は WSA 系。次点で Android Emulator / Genymotion / BlueStacks。

#### WSA (Windows Subsystem for Android)
Microsoft公式WSAは提供終了済みだが、既存環境や保存済みパッケージがあれば動作する可能性がある。

- [ ] VAIO SX12 に過去の WSA 環境やインストーラが残っていないか確認
- [ ] Microsoft Store / ダウンロード履歴 / バックアップ / 旧PC内を探索
- [ ] Windows の「仮想マシンプラットフォーム」が有効か確認
- [ ] BIOS / Windows 側で仮想化が有効か確認
- [ ] 発掘した公式WSAを現行Windows 11で起動できるか試す
- [ ] ADB 接続できるか確認
- [ ] `market-weather-debug.apk` をサイドロードして起動確認
- [ ] WSAが不安定または導入不可なら、非公式保守版の利用可否を別途検討
- [ ] 非公式版を使う場合は、配布元・更新状況・改変内容・セキュリティリスクを確認してから導入する
- [ ] WSAで動作した場合、再現用手順を `docs/windows-wsa.md` に残す

注意:
- WSA は2025年にMicrosoft公式サポート終了。
- 将来のWindows Updateで動かなくなる可能性があるため、正式な唯一の検証環境にはしない。
- WSAは「便利な追加検証環境」と位置付ける。

### Windows の代替実行環境
- [ ] Android Studio Emulator でAPK起動確認
- [ ] Genymotion の導入コストと使い勝手を確認
- [ ] BlueStacks で自作APKサイドロードが簡単か確認
- [ ] 最も軽くて手数の少ない方法を1つ標準手順にする

### オフィスVAIOで新ChatGPT / Codexアプリを検証
- [ ] オフィスのVAIOで新しいChatGPT Windowsアプリをインストールして挙動確認
- [ ] オフィスのVAIOで新しいCodexアプリをインストールして挙動確認
- [ ] 旧ChatGPT Classicとの共存状態を確認
- [ ] 既存Codexの履歴・プロジェクト・設定が保持されるか確認
- [ ] Codex Cloudの新規環境作成UIへ到達できるか確認
- [ ] `xiaqui/market-weather` 用のCloud環境を作成できるか確認
- [ ] 問題がなければ本人VAIOへの導入可否を判断
- [ ] 何か失われる・置換される・設定が変わる兆候があれば本人VAIOへの導入は保留

### iOS
APKそのものは実行しない。Web版を正式な確認手段とする。

- [ ] iPhone 13 mini Safari でWeb版表示確認
- [ ] 縦画面で4市場が破綻しないことを確認
- [ ] ホーム画面追加(PWA)の使い勝手を確認
- [ ] 文字サイズ・カード幅・スクロール量を13 mini基準で調整
- [ ] Safariのキャッシュで古い `forecast.json` が残らないよう対策

### Termux
Termux内でAPKを仮想実行するのではなく、Androidホスト側との橋渡し用途にする。

- [ ] GitHub Actions Artifact からAPK取得する手順を作る
- [ ] TermuxからAndroidのパッケージインストーラへAPKを渡せるか確認
- [ ] 必要なら `termux-open` / `am` / ADB 等の簡単な導線を用意
- [ ] Z4T / Z3TC ではOSバージョンと minSdk の整合性を確認

### Browser
- [ ] GitHub Pages版をWindows / iOS / Androidで確認
- [ ] オフライン時に前回表示を残すか検討
- [ ] PWA対応を後付け可能な構成にしておく
- [ ] インストール風UIは初期版では不要

## P1: データ・予測基盤

### 市場データ取得
- [ ] データ取得元を1つに固定せずProvider化
- [ ] 日経平均 / NYダウ / USDJPY / GOLD の日足取得
- [ ] タイムゾーン差と市場休場日を整理
- [ ] 欠損日・休日・時差による未来データ混入を防ぐ
- [ ] データ取得失敗時は前回JSONで表示継続できるようにする

### 特徴量
- [ ] 騰落率 1/2/5/10/20日
- [ ] 移動平均乖離 5/20/60日
- [ ] RSI 14
- [ ] MACD
- [ ] 5日 / 20日ボラティリティ
- [ ] 高値安値レンジ
- [ ] 連続上昇 / 連続下落日数
- [ ] 他市場の前日情報を特徴量として利用

### 予測モデル
- [ ] Logistic Regression
- [ ] Gradient Boosting系
- [ ] 単純Trendモデル
- [ ] まず単純平均でアンサンブル
- [ ] モデル別確率を詳細画面で表示
- [ ] モデル間のばらつきから信頼度を算出

### 予測レンジ
- [ ] 現在値とボラティリティから下限・上限を算出
- [ ] 上下対称レンジから開始
- [ ] 後で方向予測を使った非対称レンジに拡張

## P1: バックテスト

ここは精度より先に正しさを守る。

- [ ] 時系列順で学習 / 検証する
- [ ] ランダムシャッフルを禁止
- [ ] 未来データ混入テストを用意
- [ ] 方向正解率
- [ ] Brier Score
- [ ] Calibration
- [ ] レンジ内包含率
- [ ] 市場別に成績を分ける
- [ ] 年ごとの成績も確認する
- [ ] 強気相場 / 弱気相場 / 高ボラ局面で成績差を見る

## P2: UI / UX

### 天気表現
- [ ] 晴れ / 晴れ時々曇り / 曇り / 雨 / 荒天を定義
- [ ] 「方向」と「荒れやすさ」を別表示
- [ ] 色だけに依存しない
- [ ] 数値を見なくても5秒で市場の雰囲気が分かるUI

### 更新日時
- [ ] forecast生成日時
- [ ] 元データ最終日
- [ ] 「何営業日先の予報か」を明示
- [ ] 市場ごとにデータ鮮度が違う場合を考慮

### PWA
- [ ] manifest
- [ ] app icon
- [ ] service worker
- [ ] ホーム画面追加
- [ ] 更新通知 / キャッシュ更新戦略
- [ ] Web版を「簡易アプリ」として使えることを確認

## P2: GitHub運用

- [ ] READMEにAPK取得方法を記載
- [ ] READMEにWeb版URLを記載
- [ ] READMEに「予測は保証ではない」旨を記載
- [ ] Actions成功時のArtifact名を固定
- [ ] PagesデプロイWorkflowとAPK Workflowを分離するか検討
- [ ] PythonテストをAPKビルド前に走らせる
- [ ] Dependabot等は初期完成後に検討

## P3: 将来候補

初期版ではやらない。

- [ ] 3営業日予報
- [ ] 1週間予報
- [ ] S&P500
- [ ] NASDAQ
- [ ] BTC
- [ ] VIX
- [ ] 米国債利回り
- [ ] 原油
- [ ] ニュース特徴量
- [ ] 通知
- [ ] ウィジェット
- [ ] 市場レジーム分類
- [ ] 「金融天気図」表示
- [ ] モデル性能履歴
- [ ] 予報と実績の答え合わせ画面

## 初期完成の定義

以下が揃ったら「最小版完成」。

1. GitHub ActionsからAPKが生成できる
2. AndroidでAPKが起動する
3. GitHub Pagesで同じ4市場を表示できる
4. iPhone 13 miniからSafariで確認できる
5. WindowsからWeb版を確認できる
6. WindowsでAPKを直接動かす方法が最低1つ確保できる
7. 固定JSONから実データ生成JSONへ差し替え可能な構造になっている
8. 基本バックテストが動く

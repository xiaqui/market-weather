# TODO

Market Weather の開発・検証タスク一覧。

最終更新: 2026-09-22

一次完成に直接関係しない開発環境・端末検証・Codex Cloud工房の課題は
[開発環境・端末検証バックログ](development-environment.md) へ分離した。

## 現在地

### 一次完成済みの基盤
- [x] GitHub Pagesで4市場の予報画面を公開
- [x] Android APKをWebViewカプセル化し、Pages版を表示の正本に統一
- [x] GitHub ActionsでDebug APKを自動生成
- [x] Yahoo Financeから4市場の現在値・約10年の日足を取得
- [x] 形成中の日足を予測特徴量へ混ぜない
- [x] 市場別の確定時刻・休場・時差を考慮
- [x] Trend baselineを実装
- [x] Cross-Asset Historical Analog「金融天気図」を実装
- [x] Trend / Analog / 50:50 Ensembleを実装
- [x] walk-forwardバックテスト、Brier Score、非重複Validationを実装
- [x] prospective forecast保存を開始
- [x] 平日の日次自動更新workflowを実装
- [x] 自動更新成功後にGitHub Pagesへ再deployする配線を実装
- [x] 手動実行で forecast更新 → main commit → Pages反映まで確認

## P0: 一次完成前に残すもの

### 表示文言・最低限UX
- [x] 「本日の金融天気予報」を「次営業日の金融天気予報」へ変更
- [x] forecast生成日時に加えて「元データ最終日」を表示
- [x] 市場ごとに「次に予測しているセッション」を明示
- [ ] 現在値と予報値の役割をUI上でも明確に分離
- [ ] 予想レンジを最低気温 / 最高気温のように直感的に見せる
- [ ] 下限 / 上限が価格レンジであることを詳細表示で明示

### 日次更新の安定運用
- [x] `Update Daily Forecast` を `workflow_dispatch` で手動実行可能にする
- [x] 平日22:30 UTC（翌07:30 JST）に定期実行
- [x] `fetch_market_data.py` → `sync_forecast.py` を実行
- [x] forecast JSONに差分がある場合だけmainへcommit/push
- [x] 保存済み `reports/live-forecast/` を自動更新対象から除外
- [x] 更新workflow成功後にPagesをdeploy
- [ ] 数日運用してschedule起動・Yahoo取得・自動push・Pages反映が安定することを確認
- [ ] Yahoo取得失敗時に前回予報を壊さず表示継続できることを確認

## P1: データ・予測基盤

### 市場データ取得
- [x] Yahoo Finance Chart APIから日経平均 / NYダウ / USDJPY / GOLDを取得
- [x] 約10年の日足を取得
- [x] タイムゾーン差と市場休場日を考慮
- [x] 欠損日・休日・時差による未来データ混入を防ぐ
- [x] 進行中の日足を特徴量・バックテストから除外
- [ ] データ取得元をProvider化し、Yahoo依存を将来差し替え可能にする
- [ ] API失敗時の前回JSON維持を明示的にテストする

### 特徴量
- [x] 1 / 5 / 20日騰落率
- [x] 5 / 20日移動平均乖離
- [x] 5 / 20日ボラティリティ
- [x] 他市場との相対モメンタム
- [x] 対象市場休場中の他市場累積変動
- [x] 対象市場のstaleness
- [ ] 2 / 10日騰落率
- [ ] 60日移動平均乖離
- [ ] RSI 14
- [ ] MACD
- [ ] 高値安値レンジ
- [ ] 連続上昇 / 連続下落日数

### 予測モデル
- [x] 単純Trendモデル
- [x] Cross-Asset Historical Analog
- [x] Trend / Analog 50:50 Ensemble
- [x] モデル別確率を内部診断できる
- [ ] Logistic Regression
- [ ] Gradient Boosting系
- [ ] 市場ごとに入力市場を変えるtarget-specific weather mapを検証
  - Dow: VIX / S&P500 / NASDAQ / 米国金利候補
  - USDJPY: 米2年金利 / DXY / 日米金利差候補
  - GOLD: 実質金利 / DXY / VIX候補
  - BTCは補助的risk-on指標として比較候補
- [ ] 予測性能を見て本番重みを変更する場合は別Validationを用意する

### 予測レンジ
- [x] 現在値と20日ボラティリティから上下対称レンジを算出
- [ ] 方向予測を使った非対称レンジを検証
- [ ] レンジ内包含率を評価

## P1: バックテスト / prospective validation

- [x] 時系列順walk-forward
- [x] ランダムシャッフルを使わない
- [x] 未来データ混入回帰テスト
- [x] 方向正解率
- [x] Brier Score
- [x] 市場別評価
- [x] 最新252セッションをDiscoveryとして固定
- [x] 非重複Validation windowを4区間作成
- [x] naive baseline比較
- [x] Trend / Analog disagreement診断
- [x] paired comparison
- [x] Wilson confidence interval
- [x] exact binomial p-value
- [x] 最初のprospective forecastを保存
- [ ] prospective forecastを継続保存し、実績と答え合わせする
- [ ] Calibrationを評価
- [ ] レンジ内包含率を評価
- [ ] 強気 / 弱気 / 高ボラ等の市場レジーム別成績を見る
- [ ] 年単位の性能推移を見られるレポートを作る

## P2: UI / UX

### 現在値と予報の分離
- [ ] Androidネイティブ現在値更新は、起動 / フォアグラウンド復帰時の即時取得 + 下スワイプ手動更新を基本とし、60秒ごとの自動pollを外す
- [ ] 現在値だけを予報より高頻度に更新できる構成へ変更
- [ ] 可能ならブラウザ側で現在値を直接取得し、天気マーク・予報確率は次の確定足まで固定
- [ ] CORS等で難しい場合は current 専用JSONまたは軽量proxyを使う

### 日本向け表示
- [ ] NYダウに円建て表示オプション
- [ ] 円建てダウは同時点のUSD/JPYを利用
- [ ] GOLDに円/g表示オプション
- [ ] GOLD円/gは `ドル建て金価格 × USD/JPY ÷ 31.1034768`
- [ ] GOLD円/g予報を田中貴金属の店頭小売・買取価格の参考値として検証
- [ ] 消費税・スプレッド・手数料・公表時刻差は別補正で扱う

### 天気表現
- [ ] 晴れ / 晴れ時々曇り / 曇り / 雨 / 荒天の表示定義を整理
- [ ] 「方向」と「荒れやすさ」を別表示
- [ ] 色だけに依存しない
- [ ] 数値を見なくても5秒で市場の雰囲気が分かるUI
- [ ] confidenceを「予報の的中確率」と誤解しにくい表示名へ変更検討

### 更新情報
- [x] forecast生成日時を表示
- [x] 元データ最終日を表示
- [x] 「何営業日先 / 次のどのセッションの予報か」を明示
- [ ] 市場ごとのデータ鮮度差を表示

### PWA
- [ ] manifest
- [ ] app icon
- [ ] service worker
- [ ] ホーム画面追加
- [ ] 更新通知 / キャッシュ更新戦略
- [ ] Web版を簡易アプリとして使えることを確認

## P2: GitHub運用

- [x] Web版公開URLをREADMEに記載
- [x] READMEに「予測は保証ではない」旨を記載
- [x] APK Artifact名を `market-weather-debug` に固定
- [x] Pages deploy workflow と APK build workflowを分離
- [x] 日次forecast更新workflowを分離
- [x] workflow変更はCodex PAT権限に依存せず、必要なら倫側で反映できる運用を確認
- [x] READMEにAPK取得方法を明記
- [ ] PythonテストをAPKビルド前に走らせる
- [ ] Dependabot等は一次完成後に検討

## P3: 将来候補

一次完成ではやらない。

- [ ] 国内版「日本セクター天気図」
- [ ] 世界天気図 → 日本への圧力 → 国内セクター予報の階層化
- [ ] 3営業日予報
- [ ] 1週間予報
- [ ] S&P500
- [ ] NASDAQ
- [ ] BTC
- [ ] VIX
- [ ] 米国債利回り
- [ ] 実質金利
- [ ] DXY
- [ ] 原油
- [ ] ニュース特徴量
- [ ] 為替介入警報 / トリプル安注意報
- [ ] 金融地震 / 津波のようなショック・伝播表現
- [ ] 通知
- [ ] ウィジェット
- [ ] 市場レジーム分類
- [ ] 金融天気図そのものの可視化
- [ ] モデル性能履歴
- [ ] 予報と実績の答え合わせ画面

## 一次完成の定義

現在の構成に合わせて定義し直す。

1. [x] GitHub ActionsからAPKが生成できる
2. [x] AndroidでWebView APKが起動する
3. [x] GitHub Pagesで4市場を表示できる
4. [x] iPhone 13 miniからSafariで確認できる
5. [x] 固定JSONではなく実データ生成JSONで予報を表示する
6. [x] 基本バックテストが動く
7. [x] 日次更新を手動実行してPagesまで反映できる
8. [ ] 定期scheduleが数日安定して自動更新することを確認
9. [x] 次営業日予報であること・元データ鮮度をUIに明示
10. [ ] prospective forecastの答え合わせを継続できる運用を固める

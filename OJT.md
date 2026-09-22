# OJT.md

## 種別

新規タスク

## タスク名

Androidネイティブ版の現在値ライブ更新

## 目的

Market Weather の Android 版では、GitHub Pages の WebView 表示を正本として維持しつつ、
Android ネイティブ側の通信能力を使って Yahoo Finance Chart API から4市場の現在値を直接取得する。

取得した現在値だけを WebView 上の表示へ反映し、
予報値・天気・上昇確率・レンジ・信頼度・リスク・予測対象セッションは
既存の `forecast.json` の内容をそのまま使う。

ブラウザ版では Yahoo Finance への直接 `fetch()` が CORS で拒否されるため、
今回のライブ現在値取得は Android ネイティブ版だけの追加機能とする。

## 背景

現在の Android 版は `MainActivity.java` で
`https://xiaqui.github.io/market-weather/` を WebView に表示している。

既存の Web 版は `web/forecast.json` を読み込み、
現在値と予報を同じ JSON から表示している。

一方、Android ネイティブコードはブラウザの CORS 制約を受けないため、
Yahoo Finance Chart API へ直接 HTTP リクエストできる。

AP37 の既存スクリプトでは、以下の Yahoo Finance Chart API から
`meta.regularMarketPrice` を直接取得できている実績がある。

- USD/JPY
- 日経平均

今回この方式を Market Weather Android 版へ広げる。

## 対象市場

既存 Market Weather の市場ID・symbol対応を優先する。

- 日経平均: `^N225`
- NYダウ: `^DJI`
- USD/JPY: 既存実装に合わせて `JPY=X`
- GOLD: `GC=F`

USD/JPY について `USDJPY=X` ではなく、
現行 Market Weather が使用している `JPY=X` を基本とする。
変更が必要な場合は理由を報告し、勝手に他symbolへ置き換えない。

## Yahoo Finance API

Chart API を利用する。

例:

```text
https://query1.finance.yahoo.com/v8/finance/chart/%5EN225
```

現在値:

```text
chart.result[0].meta.regularMarketPrice
```

現在値時刻:

```text
chart.result[0].meta.regularMarketTime
```

APIキーや認証情報は追加しない。

## 実装方針

### 1. Androidネイティブ側で取得

`android/app/src/main/java/jp/xiaqui/marketweather/MainActivity.java`
を中心に実装する。

Android側から Yahoo Finance Chart API へ HTTPS でアクセスし、
4市場の `regularMarketPrice` と `regularMarketTime` を取得する。

新しい外部ライブラリは、明確な必要性がない限り追加しない。
標準 Android / Java API と既存依存で実装できるならそれを優先する。

ネットワーク処理は UI thread で実行しない。

### 2. WebViewへ現在値だけ渡す

Web側に、Androidネイティブから現在値を受け取るための
明示的な JavaScript 関数を用意する。

例:

```javascript
window.updateCurrentValues(...)
```

具体的な引数形式は実装しやすい形でよいが、
市場IDと現在値を安全に対応付けられる構造にする。

Android側からは `evaluateJavascript()` 等を利用し、
取得済みの値を WebView へ渡す。

DOM要素を Android 側から文字列で直接探して書き換えるより、
Web側の公開関数を1つ経由する構成を優先する。

### 3. 更新対象

ライブ更新してよいのは以下だけ。

- 現在値
- 現在値の時刻表示を追加する場合は、その時刻

以下は絶対に更新しない。

- 天気
- 上昇確率
- Trend予報
- Analog予報
- Ensemble / 最終予報
- 予想レンジ
- confidence
- risk
- last_data_date
- next_session_date
- forecast生成日時

現在値がライブ更新されても、
予報は次の確定足による日次更新まで固定する。

### 4. カードと詳細表示の整合

ライブ更新後は、
カード上の現在値だけでなく詳細ダイアログ内の「現在値」も
同じ最新値を表示すること。

詳細画面を開き直したときに
`forecast.json` 内の古い current へ戻らないようにする。

Web側で保持している市場データの current も、
ネイティブ取得値で更新できる構成にする。

### 5. 更新タイミング

ベストエフォート運用とする。

- Activity が foreground / resumed になったら、まず1回取得を試す
- foreground中だけ、おおむね60秒間隔で再取得する
- `onPause()` で定期更新を停止する
- `onResume()` で再開する
- background での常時更新は行わない
- WorkManager / foreground service / background service は使わない

60秒は固定値ではなく定数として分かりやすく定義してよい。

### 6. 失敗時

Yahoo Finance 取得に失敗してもアプリをエラー画面へ遷移させない。

- 取得できた市場だけ更新してよい
- 取得失敗した市場は直前の表示を維持
- 初回取得から失敗した場合は `forecast.json` の current をそのまま表示
- 一時的なネットワーク失敗で予報表示を消さない
- 次の定期更新時に再試行する
- 取得失敗を理由に forecast.json を書き換えない

HTTP status、JSON欠損、タイムアウト、Yahoo側エラーなどを
アプリクラッシュにしない。

## Web版への影響

通常ブラウザ版はこれまで通り動作させる。

`window.updateCurrentValues` が一度も呼ばれない場合でも、
既存の `forecast.json` だけで正常表示できること。

Safari / Chrome / GitHub Pages 側に
Yahoo Finance 直接取得処理を追加しない。

ブラウザ側から Yahoo Finance を直接 `fetch()` する実装は禁止。

## 既存構成を壊さない

以下を変更しない。

- Trendロジック
- Analogロジック
- Ensembleロジック
- weather分類
- forecast生成処理
- `shared/forecast.json` の意味
- `reports/live-forecast/`
- prospective forecast
- 日次forecast更新workflow
- Pages deploy workflow

今回 `current.json` は新設しない。

proxyも実装しない。

## セキュリティ / 安全性

- APIキーを追加しない
- secretをコードへ埋め込まない
- 外部任意URLから JavaScript bridge を呼べる構成へ広げない
- 既存の外部URLをブラウザへ逃がす挙動を維持する
- Yahooレスポンスの文字列を、そのまま実行可能JavaScriptとして連結しない
- WebViewへ渡す値は数値・既知market IDとして扱う

## テスト

最低限、以下を確認する。

### Web側

- `forecast.json` だけで従来どおり表示できる
- `updateCurrentValues` を呼ぶと対象市場の current だけ変わる
- 天気・予報確率・レンジ等は変わらない
- 詳細表示にも最新 current が反映される
- 一部市場だけ更新しても他市場を壊さない

### Android側

可能な範囲でユニットテストまたは分離可能なテストを追加する。

最低限、コード上で以下を確認可能にする。

- 4市場のsymbol対応
- Yahooレスポンスから `regularMarketPrice` を取得できる
- `regularMarketTime` を取得できる
- JSON欠損時にクラッシュしない
- Activity pause時に更新ループを停止できる
- resume時に再開できる

実機でしか確認できない部分は、その旨を最後に明記する。

## 手動確認

可能なら Android build を通す。

実機確認できない場合でも、少なくとも以下を報告する。

- APK buildの成否
- Web側テストの成否
- Android側テストの成否
- GitHub Actionsの成否
- 実機確認が未実施なら未実施と明記

## GitHub運用

今回は新規タスク。

- main最新から新branchを作る
- mainへ直接pushしない
- 実装
- test
- commit
- push
- 新しいPull Requestを作る
- mergeはしない

既存の `TASK.md` は変更・削除しない。

## 完了条件

- Android foreground時だけ Yahoo Finance から4市場の現在値を取得する
- 起動 / resume直後に取得を試す
- foreground中は約60秒ごとにベストエフォート更新する
- pause中は更新しない
- 現在値だけWebViewへ反映する
- カードと詳細表示のcurrentが一致する
- 予報値は固定されたまま
- 取得失敗時も既存表示を維持する
- Webブラウザ版は従来どおり動く
- forecast生成ロジックを変更していない
- `reports/live-forecast/` を変更していない
- proxy / current.json を追加していない
- build / tests の結果を報告する
- 新PRを作成済み
- mergeしていない

## 最後の報告

以下を報告する。

- branch名
- commit SHA
- PR番号
- 変更ファイル
- Android側の取得方式
- WebViewへの反映方式
- 更新間隔
- foreground / background の制御方法
- 4市場のsymbol
- `regularMarketPrice` / `regularMarketTime` の扱い
- 取得失敗時の挙動
- カード / 詳細表示の整合確認
- test結果
- Android build結果
- Actions結果
- 実機確認の有無
- 予報ロジックを変更していないこと
- `reports/live-forecast/` を変更していないこと
- mergeしていないこと

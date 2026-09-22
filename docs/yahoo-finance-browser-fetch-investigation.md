# Yahoo Finance Chart API ブラウザ直接取得調査

最終更新: 2026-09-22

## 結論

- ブラウザ直接取得: **不可**
- CORS結果: **Yahoo Finance Chart API はブラウザ向けの CORS 許可を返さないため `fetch()` は拒否される**
- GitHub Pagesからの利用見込み: **不可**

そのため、GitHub Pages上のフロントエンドから `fetch("https://query1.finance.yahoo.com/v8/finance/chart/...")`
を直接呼ぶ構成は採用しないほうがよい。

## 調査対象

- 日経平均: `^N225`
- NYダウ: `^DJI`
- USD/JPY: `JPY=X`
- GOLD: `GC=F`

## 調査方法

1. 既存実装とドキュメントを確認
   - `README.md`
   - `docs/TODO.md`
   - `docs/market-weather-spec.md`
   - `web/app.js`
   - `scripts/fetch_market_data.py`
2. Yahoo Finance Chart API の公開情報を確認
3. 本番コードは変更せず、調査結果のみを整理

## 既存実装から確認できたこと

- 既存の市場データ取得はブラウザではなく Python から行っている
- 既存コードは Yahoo Finance Chart API の `meta.regularMarketPrice` を現在値として使っている
- 既存コードは `meta.currentTradingPeriod.regular` を見て形成中の日足を予測入力から除外している

対象箇所:

- `scripts/fetch_market_data.py:25`
- `scripts/fetch_market_data.py:477-492`
- `scripts/fetch_market_data.py:440-456`
- `web/app.js:46-60`

## ブラウザ直接取得の可否

### 判定

**不可**

### 理由

Yahoo Finance Chart API (`query1.finance.yahoo.com/v8/finance/chart/...`) は、
ブラウザのクロスオリジン `fetch()` に必要な `Access-Control-Allow-Origin` を返さないという報告が継続しており、
フロントエンド JavaScript からの直接取得は CORS でブロックされる見込みが高い。

GitHub Pages も通常のブラウザ実行環境なので、この制約は変わらない。

参考:

- Stack Overflow: Yahoo Finance へのフロントエンド `fetch()` が CORS で拒否される報告  
  https://stackoverflow.com/questions/74644603/how-to-solve-the-issue-of-blocking-of-access-to-fetch-data-from-yahoo-finance-by
- DEV Community: Yahoo Finance Chart API のレスポンス例と `meta` フィールド解説  
  https://dev.to/avabuildsdata/how-to-get-historical-stock-data-from-yahoo-finance-without-paying-for-an-api-key-5ein
- GitHub Gist: Chart API の `meta.regularMarketPrice` / `regularMarketTime` 参照例  
  https://gist.github.com/daverich204/44d53b8e949360256fec1cb59bf5c6ed

## 4市場それぞれの取得可否

サーバー側取得前提では、4市場とも Chart API の対象として扱える見込み。
ただし**ブラウザ直接取得は4市場とも不可**。

| 市場 | Yahoo symbol | ブラウザ直接取得 | サーバー側取得 | 現在値フィールド候補 | 時刻フィールド候補 |
| --- | --- | --- | --- | --- | --- |
| 日経平均 | `^N225` | 不可 | 可 | `meta.regularMarketPrice` | `meta.regularMarketTime` |
| NYダウ | `^DJI` | 不可 | 可 | `meta.regularMarketPrice` | `meta.regularMarketTime` |
| USD/JPY | `JPY=X` | 不可 | 可 | `meta.regularMarketPrice` | `meta.regularMarketTime` |
| GOLD | `GC=F` | 不可 | 可 | `meta.regularMarketPrice` | `meta.regularMarketTime` |

## 利用できる現在値フィールド

既存実装と公開レスポンス例から、現在値用途では以下が有力。

- 第一候補: `chart.result[0].meta.regularMarketPrice`
- 補助候補: `chart.result[0].meta.previousClose`
- 補助候補: `chart.result[0].meta.chartPreviousClose`

Market Weather の既存実装は `regularMarketPrice` を採用しており、この方針を維持するのが自然。

## 利用できる時刻情報

現在値の取得時刻候補として利用できる情報は以下。

- 第一候補: `chart.result[0].meta.regularMarketTime`
  - Unix epoch seconds
  - 「その現在値がいつ時点のものか」を表す用途に最も適する
- 補助情報: `chart.result[0].meta.currentTradingPeriod.regular.start`
- 補助情報: `chart.result[0].meta.currentTradingPeriod.regular.end`

`currentTradingPeriod.regular` は「現在どの regular session か」を判断する材料として有用だが、
画面表示用の「現在値の時刻」は `regularMarketTime` を優先したほうが分かりやすい。

## GitHub Pagesからの利用可否の見込み

**不可**

理由:

- GitHub Pages は静的ホスティングであり、サーバー側で CORS を吸収できない
- ブラウザから Yahoo Finance API を直接叩く形になるため、通常の Web ブラウザと同じく CORS 制約を受ける
- したがって Pages 上でも `fetch()` の成功は期待しないほうがよい

## 次の推奨構成

### 1. ブラウザ直接取得

- **非推奨**
- CORS で止まる前提で考えるべき

### 2. `current.json`

- **条件付きで可**
- 予報 (`forecast.json`) と現在値を分離するだけなら最も単純
- ただし GitHub Pages 上で「現在値だけを予報より高頻度に更新」したい場合は、
  `current.json` の生成・配信頻度を別workflow等で上げる必要がある
- 高頻度更新の上限は GitHub Actions / Pages 運用に強く依存する

### 3. 軽量proxy

- **高頻度更新を本気でやるなら最有力**
- ブラウザは同一アプリUIのまま、現在値だけを都度API取得できる
- CORS問題をproxy側で吸収できる
- `forecast.json` は従来どおり日次更新のまま維持できる

## 推奨判断

今回の調査結果だけで選ぶなら、次の順で妥当。

1. **軽量proxy**  
   現在値を予報より高頻度で出したいという目的に最も合う
2. **`current.json`**  
   更新頻度が低くてもよい、または運用を極力単純にしたい場合の次善策
3. **ブラウザ直接取得**  
   CORSにより不採用

## TODO への影響

今回の調査は **実装完了ではない**。

`docs/TODO.md` の以下は、今回の調査だけでは完了扱いにしない。

- [ ] 現在値だけを予報より高頻度に更新できる構成へ変更
- [ ] 可能ならブラウザ側で現在値を直接取得し、天気マーク・予報確率は次の確定足まで固定
- [ ] CORS等で難しい場合は current 専用JSONまたは軽量proxyを使う

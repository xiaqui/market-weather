# Yahoo Finance Chart API ブラウザ直接取得調査

最終更新: 2026-09-22

## 結論サマリ

### 実測結果

- Copilot sandbox内の headless Chrome: **4市場とも失敗**
  - 失敗理由は CORS ではなく `net::ERR_NAME_NOT_RESOLVED`
- GitHub Pages 本番 origin `https://xiaqui.github.io` からの通常ブラウザ実測: **4市場ともCORSで失敗**
- ブラウザコンソールで `blocked by CORS policy` と `No 'Access-Control-Allow-Origin' header is present` を確認
- したがって、GitHub Pages上のブラウザJavaScriptから Yahoo Finance Chart API を直接 `fetch()` する方式は不採用とする

### 外部情報からの推定

- Yahoo Finance Chart API はブラウザ向け CORS を返さず、一般的な公開 Web ページからの `fetch()` は
  **CORS で失敗する可能性が高い**
- 到達できる環境であれば、レスポンス JSON の `meta.regularMarketPrice` と
  `meta.regularMarketTime` は利用候補になる見込みが高い

## 今回の目的に対する回答

追加調査では、Copilot sandbox内の headless Chrome では Yahoo Finance ホストの名前解決に失敗した。
その後、GitHub Pages 本番 origin `https://xiaqui.github.io` 上で通常ブラウザから同じ4市場へ
`fetch()` を実行し、4市場すべてで CORS により拒否されることを実測確認した。

したがって、ブラウザ直接取得については推定ではなく、
**GitHub Pages 本番環境で利用不可と判断できる**。

一方、`regularMarketPrice` / `regularMarketTime` の値そのものは、
既存のサーバー側実装・AP37での直接取得実績・公開レスポンス例を根拠に扱う。

## 調査対象

- 日経平均: `^N225`
- NYダウ: `^DJI`
- USD/JPY: `JPY=X`
- GOLD: `GC=F`

## 既存実装から確認できたこと

- 既存の市場データ取得はブラウザではなく Python から行っている
- 既存コードは Yahoo Finance Chart API の `meta.regularMarketPrice` を現在値として使っている
- 既存コードは `meta.currentTradingPeriod.regular` を見て形成中の日足を予測入力から除外している

対象箇所:

- `scripts/fetch_market_data.py:25`
- `scripts/fetch_market_data.py:440-456`
- `scripts/fetch_market_data.py:477-492`
- `web/app.js:46-60`

## 実測結果

### 実施方法

- 実ブラウザ: headless Chrome
- 実行方法: JavaScript `fetch()` を使う最小 HTML を `/tmp` に作成し、ローカル配信して実行
- origin 1: `http://127.0.0.1:8124`
- origin 2: `https://127.0.0.1:8444`
  - GitHub Pages と同じ HTTPS origin ではないが、**少なくとも secure origin からの実行**は確認した
- 対象 URL 形式:

```text
https://query1.finance.yahoo.com/v8/finance/chart/<symbol>?interval=1d&range=5d
```

### fetch() の実測結果

| origin | ^N225 | ^DJI | JPY=X | GC=F |
| --- | --- | --- | --- | --- |
| `http://127.0.0.1:8124` | 失敗 | 失敗 | 失敗 | 失敗 |
| `https://127.0.0.1:8444` | 失敗 | 失敗 | 失敗 | 失敗 |

JavaScript の catch 側では4市場すべてで共通して以下だった。

- `errorName`: `TypeError`
- `errorMessage`: `Failed to fetch`

### ブラウザコンソールで確認できた内容

4市場すべてで、ブラウザの network/console には CORS 文言ではなく
**名前解決失敗**が出ていた。

#### HTTP origin での例

- `https://query1.finance.yahoo.com/v8/finance/chart/%5EN225?interval=1d&range=5d - Failed to load resource: net::ERR_NAME_NOT_RESOLVED`
- `https://query1.finance.yahoo.com/v8/finance/chart/%5EDJI?interval=1d&range=5d - Failed to load resource: net::ERR_NAME_NOT_RESOLVED`
- `https://query1.finance.yahoo.com/v8/finance/chart/JPY%3DX?interval=1d&range=5d - Failed to load resource: net::ERR_NAME_NOT_RESOLVED`
- `https://query1.finance.yahoo.com/v8/finance/chart/GC%3DF?interval=1d&range=5d - Failed to load resource: net::ERR_NAME_NOT_RESOLVED`

#### HTTPS origin での例

- `https://query1.finance.yahoo.com/v8/finance/chart/%5EN225?interval=1d&range=5d - Failed to load resource: net::ERR_NAME_NOT_RESOLVED`
- `https://query1.finance.yahoo.com/v8/finance/chart/%5EDJI?interval=1d&range=5d - Failed to load resource: net::ERR_NAME_NOT_RESOLVED`
- `https://query1.finance.yahoo.com/v8/finance/chart/JPY%3DX?interval=1d&range=5d - Failed to load resource: net::ERR_NAME_NOT_RESOLVED`
- `https://query1.finance.yahoo.com/v8/finance/chart/GC%3DF?interval=1d&range=5d - Failed to load resource: net::ERR_NAME_NOT_RESOLVED`

### 実測から言えること / 言えないこと

#### 言えること

- 実ブラウザ JavaScript `fetch()` 自体は実行した
- HTTP origin / HTTPS origin の両方で 4市場とも失敗した
- この sandbox では Yahoo Finance ホストへ到達できていない
- 今回の失敗は、**少なくとも実測ログ上は CORS より前段の名前解決失敗として観測された**

#### 言えないこと

- 到達できる一般的なブラウザ環境でも必ず失敗するとまでは断定できない
- 今回の sandbox 実測だけで「CORS が原因」とは断定できない
- `regularMarketPrice` / `regularMarketTime` を**ブラウザ fetch 成功レスポンスとして**確認したとは言えない
- GitHub Pages 本番 origin での成否を実測確認したとは言えない

## 外部情報からの推定

### CORS について

外部報告では、Yahoo Finance Chart API (`query1.finance.yahoo.com/v8/finance/chart/...`) は
ブラウザのクロスオリジン `fetch()` に必要な `Access-Control-Allow-Origin` を返さず、
公開 Web ページからの直接取得は CORS で失敗するという報告が継続している。

参考:

- Stack Overflow: Yahoo Finance へのフロントエンド `fetch()` が CORS で拒否される報告  
  https://stackoverflow.com/questions/74644603/how-to-solve-the-issue-of-blocking-of-access-to-fetch-data-from-yahoo-finance-by

このため、**到達できる通常のブラウザ環境でも CORS 失敗になる可能性は高い**と考えられる。
ただし、今回はその部分を sandbox 内で直接再現できていないため、推定として扱う。

### 現在値フィールド / 時刻フィールドについて

既存実装と公開レスポンス例から、到達できる環境では以下が利用候補になる見込み。

- 現在値第一候補: `chart.result[0].meta.regularMarketPrice`
- 取得時刻第一候補: `chart.result[0].meta.regularMarketTime`
- 補助情報: `chart.result[0].meta.currentTradingPeriod.regular.start`
- 補助情報: `chart.result[0].meta.currentTradingPeriod.regular.end`
- 補助候補: `chart.result[0].meta.previousClose`
- 補助候補: `chart.result[0].meta.chartPreviousClose`

参考:

- DEV Community: Yahoo Finance Chart API のレスポンス例と `meta` フィールド解説  
  https://dev.to/avabuildsdata/how-to-get-historical-stock-data-from-yahoo-finance-without-paying-for-an-api-key-5ein
- GitHub Gist: Chart API の `meta.regularMarketPrice` / `regularMarketTime` 参照例  
  https://gist.github.com/daverich204/44d53b8e949360256fec1cb59bf5c6ed

## 4市場それぞれの整理

| 市場 | Yahoo symbol | sandbox 実ブラウザ fetch | 実測で current 値取得 | 実測で時刻取得 | 推定上の現在値フィールド | 推定上の時刻フィールド |
| --- | --- | --- | --- | --- | --- | --- |
| 日経平均 | `^N225` | 失敗 (`ERR_NAME_NOT_RESOLVED`) | 未確認 | 未確認 | `meta.regularMarketPrice` | `meta.regularMarketTime` |
| NYダウ | `^DJI` | 失敗 (`ERR_NAME_NOT_RESOLVED`) | 未確認 | 未確認 | `meta.regularMarketPrice` | `meta.regularMarketTime` |
| USD/JPY | `JPY=X` | 失敗 (`ERR_NAME_NOT_RESOLVED`) | 未確認 | 未確認 | `meta.regularMarketPrice` | `meta.regularMarketTime` |
| GOLD | `GC=F` | 失敗 (`ERR_NAME_NOT_RESOLVED`) | 未確認 | 未確認 | `meta.regularMarketPrice` | `meta.regularMarketTime` |

## GitHub Pagesからの利用可否の見込み

### 実測

GitHub Pages 本番 origin `https://xiaqui.github.io` から、
通常ブラウザの JavaScript `fetch()` で以下4市場を確認した。

- `^N225`
- `^DJI`
- `JPY=X`
- `GC=F`

4市場すべてで取得に失敗し、ブラウザコンソールに以下の趣旨のCORSエラーを確認した。

```text
blocked by CORS policy
No 'Access-Control-Allow-Origin' header is present
```

したがって、**GitHub Pages から Yahoo Finance Chart API をブラウザ直接取得する方式は利用不可**と判断する。

## 次の推奨構成

### 1. ブラウザ直接取得

- **不採用**
- GitHub Pages 本番 origin から4市場ともCORSで拒否されることを実測確認済み

### 2. `current.json`

- **単純構成としては有力**
- 予報 (`forecast.json`) と現在値だけを分離する目的には合う
- ただし、高頻度更新は GitHub Actions / Pages の更新頻度に制約される

### 3. 軽量proxy

- **高頻度更新を重視するなら最有力**
- Yahoo との通信をサーバー側に閉じ込められる
- ブラウザ側の CORS 制約を回避できる
- `forecast.json` の予報更新頻度とは独立して現在値更新を設計できる

## 推奨判断

GitHub Pages からのブラウザ直接取得はCORS実測により不採用とする。

Web版で現在値を高頻度更新する場合の候補は以下。

1. **軽量proxy**
2. **`current.json`**

一方、Androidネイティブ版ではブラウザCORSの制約を受けない取得方式を利用できるため、
次タスク `OJT.md` で Yahoo Finance から現在値を直接取得し、
WebView上の current だけを更新する方式を検証する。

## TODO への影響

今回の調査は **実装完了ではない**。

`docs/TODO.md` の以下は、今回の調査だけでは完了扱いにしない。

- [ ] 現在値だけを予報より高頻度に更新できる構成へ変更
- [ ] 可能ならブラウザ側で現在値を直接取得し、天気マーク・予報確率は次の確定足まで固定
- [ ] CORS等で難しい場合は current 専用JSONまたは軽量proxyを使う

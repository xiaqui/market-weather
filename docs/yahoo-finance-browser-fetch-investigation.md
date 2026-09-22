# Yahoo Finance Chart API ブラウザ直接取得調査

最終更新: 2026-09-22

## 結論サマリ

### 実測結果

- ブラウザ直接取得: **この sandbox 環境では未確認**
- 実ブラウザ `fetch()` 結果: **4市場とも失敗**
- 失敗理由としてブラウザコンソールで確認できた内容: **CORS ではなく `net::ERR_NAME_NOT_RESOLVED`**
- HTTPS origin 相当の確認: **ローカル HTTPS origin では実施済み**
- GitHub Pages 本番 origin での実測: **未実施**

### 外部情報からの推定

- Yahoo Finance Chart API はブラウザ向け CORS を返さず、一般的な公開 Web ページからの `fetch()` は
  **CORS で失敗する可能性が高い**
- 到達できる環境であれば、レスポンス JSON の `meta.regularMarketPrice` と
  `meta.regularMarketTime` は利用候補になる見込みが高い

## 今回の目的に対する回答

今回追加調査で確認できたのは、**実ブラウザ環境で `fetch()` を実行した事実**と、
**この sandbox では Yahoo Finance ホスト解決に失敗しているため、CORS 可否までは実測確定できなかった**、
という点である。

したがって、本ドキュメントでは以下を明確に分ける。

- **実測結果**: Chrome から実際に `fetch()` した結果
- **推定**: 外部情報・既存実装・公開レスポンス例からの判断

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

- GitHub Pages 本番 origin からの実測はしていない
- ただし、**ローカル HTTPS origin** からのブラウザ `fetch()` は実施し、4市場とも
  `ERR_NAME_NOT_RESOLVED` で失敗した

### 推定

- GitHub Pages は静的ホスティングであり、ブラウザから Yahoo Finance を直接叩く構成になる
- そのため、到達できる環境でも CORS 制約を受ける可能性が高い
- よって **GitHub Pages で安定運用できる見込みは低い** と推定する

ただし、これは今回の sandbox 実測だけではなく、外部報告も踏まえた推定である。

## 次の推奨構成

### 1. ブラウザ直接取得

- **現時点では推奨しない**
- 理由:
  - 今回の sandbox 実測では到達失敗
  - 外部報告では CORS 失敗の可能性が高い
  - つまり到達性・CORS の両面で不確実性が高い

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

今回の **実測 + 推定** を合わせると、次の順で妥当。

1. **軽量proxy**
2. **`current.json`**
3. **ブラウザ直接取得**

ただし、最終判断前に
**GitHub Pages もしくは通常ネットワークの実ブラウザから追加実測**を行う価値はある。

## TODO への影響

今回の調査は **実装完了ではない**。

`docs/TODO.md` の以下は、今回の調査だけでは完了扱いにしない。

- [ ] 現在値だけを予報より高頻度に更新できる構成へ変更
- [ ] 可能ならブラウザ側で現在値を直接取得し、天気マーク・予報確率は次の確定足まで固定
- [ ] CORS等で難しい場合は current 専用JSONまたは軽量proxyを使う

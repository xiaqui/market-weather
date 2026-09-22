const weather = {
  sunny: ["☀️", "晴れ"], partly_cloudy: ["🌤️", "晴れ時々曇り"],
  cloudy: ["☁️", "曇り"], rainy: ["🌧️", "雨"], storm: ["⛈️", "荒天"],
};
const risks = { calm: "安定", normal: "通常", caution: "注意", storm: "荒天" };
const number = new Intl.NumberFormat("ja-JP", { maximumFractionDigits: 2 });
const date = new Intl.DateTimeFormat("ja-JP", { dateStyle: "medium" });
const percent = value => `${Math.round(value * 100)}%`;
const safeCondition = value => weather[value] || ["❔", value];
let markets = [];
let selectedMarket = null;
const liveCurrentValues = new Map();
const isAndroidApp = /MarketWeatherApp\//.test(
  (typeof navigator !== "undefined" && navigator.userAgent) || ""
);
const escapeHtml = value => String(value)
  .replaceAll("&", "&amp;")
  .replaceAll("<", "&lt;")
  .replaceAll(">", "&gt;")
  .replaceAll('"', "&quot;");
function formatLocalDate(value) {
  const [year, month, day] = String(value).split("-").map(Number);
  if (!Number.isInteger(year) || !Number.isInteger(month) || !Number.isInteger(day)) {
    return value;
  }
  return date.format(new Date(year, month - 1, day));
}
function card(market) {
  const [icon, label] = safeCondition(market.weather);
  const button = document.createElement("button");
  button.type = "button";
  button.className = "market-card";
  button.innerHTML = `<div class="card-top"><div><p class="name">${market.name}</p><p class="current">${number.format(market.current)}</p></div><div class="condition"><span class="icon">${icon}</span><span class="weather-name">${label}</span></div></div><div class="stats"><div><span class="label">上昇確率</span><span class="value">${percent(market.up_probability)}</span></div><div><span class="label">信頼度</span><span class="value">${percent(market.confidence)}</span></div><div><span class="label">リスク</span><span class="value">${risks[market.risk] || market.risk}</span></div></div><p class="range">予想レンジ　${number.format(market.range_low)} ～ ${number.format(market.range_high)}</p>`;
  button.addEventListener("click", () => showDetail(market));
  return button;
}
function renderMarkets() {
  document.querySelector("#markets").replaceChildren(...markets.map(card));
}
function showDetail(market) {
  selectedMarket = market;
  renderDetail(market);
  document.querySelector("#detail").showModal();
}
function renderDetail(market) {
  const analog = market.analog_probability == null
    ? `<dt>類似天気図予報</dt><dd>データ不足</dd><dt>類似局面</dt><dd>${market.analog_count || 0}件</dd>`
    : `<dt>類似天気図予報</dt><dd>${percent(market.analog_probability)}</dd><dt>類似局面</dt><dd>${market.analog_count}件</dd>`;
  const lastDataDate = escapeHtml(market.last_data_date);
  const localizedLastDataDate = escapeHtml(formatLocalDate(market.last_data_date));
  const nextSessionDateValue = typeof market.next_session_date === "string" && market.next_session_date
    ? market.next_session_date
    : "不明";
  const nextSessionDetail = nextSessionDateValue === "不明"
    ? '<span aria-label="予測対象セッション日不明">不明</span>'
    : `<time datetime="${escapeHtml(nextSessionDateValue)}">${escapeHtml(formatLocalDate(nextSessionDateValue))}</time>`;
  document.querySelector("#detail-content").innerHTML = `<h2>${market.name} の詳細</h2><dl class="detail-list"><dt>現在値</dt><dd>${number.format(market.current)}</dd><dt>元データ最終日</dt><dd><time datetime="${lastDataDate}">${localizedLastDataDate}</time></dd><dt>予測対象セッション（次回営業日）</dt><dd>${nextSessionDetail}</dd><dt>天気</dt><dd>${safeCondition(market.weather)[1]}</dd><dt>トレンド予報</dt><dd>${percent(market.trend_probability ?? market.up_probability)}</dd>${analog}<dt>最終予報</dt><dd>${percent(market.up_probability)}</dd><dt>予想レンジ</dt><dd>${number.format(market.range_low)} ～ ${number.format(market.range_high)}</dd><dt>信頼度</dt><dd>${percent(market.confidence)}</dd><dt>リスク状態</dt><dd>${risks[market.risk] || market.risk}</dd></dl>`;
}
globalThis.updateCurrentValues = updates => {
  if (!Array.isArray(updates)) return;
  updates
    .filter(update => update && typeof update.id === "string"
      && typeof update.current === "number" && Number.isFinite(update.current))
    .forEach(update => liveCurrentValues.set(update.id, update.current));
  let changed = false;
  markets.forEach(market => {
    const current = liveCurrentValues.get(market.id);
    if (current != null) {
      market.current = current;
      changed = true;
    }
  });
  if (!changed) return;
  renderMarkets();
  if (selectedMarket && document.querySelector("#detail").open) {
    renderDetail(selectedMarket);
  }
};
function renderCurrentStatus(status) {
  if (!isAndroidApp || !status || typeof status !== "object") return;
  const line = document.querySelector("#current-status-line");
  const detail = document.querySelector("#current-status-detail");
  const diagnostics = document.querySelector("#current-status-diagnostics");
  const list = document.querySelector("#current-status-list");
  const total = Number.isFinite(status.total) ? status.total : 0;
  const successCount = Number.isFinite(status.successCount) ? status.successCount : 0;
  const failedMarkets = Array.isArray(status.failedMarkets) ? status.failedMarkets : [];
  let headline;
  if (!status.attempted) {
    headline = "現在値: 取得状況を確認中…";
  } else if (successCount === 0) {
    headline = "現在値: Yahoo取得失敗";
  } else if (failedMarkets.length === 0) {
    headline = `現在値: Yahoo取得成功 ${successCount}/${total}`;
  } else {
    headline = `現在値: Yahoo取得 ${successCount}/${total}`;
  }
  line.textContent = status.manualUpdating ? `${headline}（更新中…）` : headline;
  const detailParts = [];
  if (status.attempted && successCount === 0) {
    detailParts.push("前回値を表示中");
  }
  failedMarkets.forEach(id => detailParts.push(`${String(id).toUpperCase()}取得失敗`));
  if (status.attempted && Number.isFinite(status.lastUpdatedAt)) {
    const time = new Intl.DateTimeFormat("ja-JP", { timeStyle: "medium" })
      .format(new Date(status.lastUpdatedAt));
    detailParts.push(`更新: ${time}`);
  }
  detail.textContent = detailParts.join(" / ");
  if (Array.isArray(status.quotes) && status.quotes.length) {
    diagnostics.hidden = false;
    list.replaceChildren(...status.quotes.map(quote => {
      const item = document.createElement("li");
      const time = Number.isFinite(quote.timestamp)
        ? new Intl.DateTimeFormat("ja-JP", { dateStyle: "short", timeStyle: "medium" })
            .format(new Date(quote.timestamp * 1000))
        : "-";
      const price = Number.isFinite(quote.price) ? number.format(quote.price) : "-";
      item.textContent = `${String(quote.id).toUpperCase()}: ${quote.ok ? "成功" : "失敗"}`
        + ` regularMarketPrice=${price} regularMarketTime=${time}`;
      return item;
    }));
  } else {
    diagnostics.hidden = true;
  }
}
globalThis.updateCurrentStatus = status => {
  renderCurrentStatus(status);
};
if (isAndroidApp) {
  const statusSection = document.querySelector("#current-status");
  if (statusSection) statusSection.hidden = false;
  renderCurrentStatus({ attempted: false, total: 0, successCount: 0, failedMarkets: [], manualUpdating: false });
}
async function loadForecast() {
  try {
    const response = await fetch("forecast.json");
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const forecast = await response.json();
    document.querySelector("#generated").textContent = `生成日時 ${new Intl.DateTimeFormat("ja-JP", { dateStyle: "medium", timeStyle: "short" }).format(new Date(forecast.generated_at))}`;
    markets = forecast.markets;
    globalThis.updateCurrentValues([]);
    renderMarkets();
  } catch (error) {
    console.error(error);
    document.querySelector("#generated").hidden = true;
    document.querySelector("#error").hidden = false;
  }
}
document.querySelector("#close-detail").addEventListener("click", () => {
  document.querySelector("#detail").close();
  selectedMarket = null;
});
loadForecast();

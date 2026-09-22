const weather = {
  sunny: ["☀️", "晴れ"], partly_cloudy: ["🌤️", "晴れ時々曇り"],
  cloudy: ["☁️", "曇り"], rainy: ["🌧️", "雨"], storm: ["⛈️", "荒天"],
};
const risks = { calm: "安定", normal: "通常", caution: "注意", storm: "荒天" };
const number = new Intl.NumberFormat("ja-JP", { maximumFractionDigits: 2 });
const date = new Intl.DateTimeFormat("ja-JP", { dateStyle: "medium" });
const percent = value => `${Math.round(value * 100)}%`;
const safeCondition = value => weather[value] || ["❔", value];
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
function showDetail(market) {
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
  document.querySelector("#detail").showModal();
}
async function loadForecast() {
  try {
    const response = await fetch("forecast.json");
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const forecast = await response.json();
    document.querySelector("#generated").textContent = `生成日時 ${new Intl.DateTimeFormat("ja-JP", { dateStyle: "medium", timeStyle: "short" }).format(new Date(forecast.generated_at))}`;
    document.querySelector("#markets").append(...forecast.markets.map(card));
  } catch (error) {
    console.error(error);
    document.querySelector("#generated").hidden = true;
    document.querySelector("#error").hidden = false;
  }
}
document.querySelector("#close-detail").addEventListener("click", () => document.querySelector("#detail").close());
loadForecast();

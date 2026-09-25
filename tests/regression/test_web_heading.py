import json
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class WebHeadingTest(unittest.TestCase):
    def test_web_heading_targets_next_business_day(self) -> None:
        html = (ROOT / "web/index.html").read_text(encoding="utf-8")

        self.assertIn('<h1>次営業日の金融予報 <span id="generated">読み込み中…</span></h1>', html)
        self.assertNotIn("<h1>本日の金融天気予報</h1>", html)

    def test_next_session_is_only_rendered_in_detail_dialog(self) -> None:
        output = subprocess.run(
            [
                "node",
                "-e",
                f"""
const fs = require("fs");
const vm = require("vm");
const source = fs.readFileSync({json.dumps(str(ROOT / "web/app.js"))}, "utf8");
const elements = {{
  "#detail-content": {{ innerHTML: "" }},
  "#detail": {{ showModal() {{ this.opened = true; }}, close() {{ this.closed = true; }} }},
  "#close-detail": {{ addEventListener() {{}} }},
  "#generated": {{ textContent: "", hidden: false }},
  "#markets": {{ children: [], append(...nodes) {{ this.children.push(...nodes); }} }},
  "#error": {{ hidden: true }},
}};
const context = {{
  console,
  Intl,
  Date,
  Math,
  Number,
  String,
  document: {{
    createElement() {{
      return {{
        innerHTML: "",
        addEventListener(type, handler) {{
          this["on" + type] = handler;
        }},
      }};
    }},
    querySelector(selector) {{
      return elements[selector];
    }},
  }},
  fetch: async () => ({{
    ok: true,
    json: async () => ({{ generated_at: "2026-09-22T00:00:00+00:00", markets: [] }}),
  }}),
}};
vm.createContext(context);
vm.runInContext(source, context);
const market = {{
  name: "日経平均",
  current: 100,
  weather: "sunny",
  trend_probability: 0.6,
  up_probability: 0.7,
  analog_probability: 0.65,
  analog_count: 30,
  range_low: 95,
  range_high: 105,
  confidence: 0.8,
  risk: "normal",
  last_data_date: "2026-09-18",
  next_session_date: "2026-09-24",
}};
const button = context.card(market);
context.showDetail(market);
process.stdout.write(JSON.stringify({{
  cardHtml: button.innerHTML,
  detailHtml: elements["#detail-content"].innerHTML,
}}));
""",
            ],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        rendered = json.loads(output.stdout)

        self.assertNotIn("予測対象セッション", rendered["cardHtml"])
        self.assertNotIn("上昇確率", rendered["cardHtml"])
        self.assertNotIn("信頼度", rendered["cardHtml"])
        self.assertIn("予測対象セッション（次回営業日）", rendered["detailHtml"])
        self.assertIn("最終予報", rendered["detailHtml"])
        self.assertIn("Trend一致度", rendered["detailHtml"])
        self.assertIn("予報根拠度", rendered["detailHtml"])
        self.assertIn('datetime="2026-09-24"', rendered["detailHtml"])
        self.assertIn("2026/09/24", rendered["detailHtml"])

    def test_detail_dialog_keeps_next_session_placeholder_accessible_when_missing(self) -> None:
        output = subprocess.run(
            [
                "node",
                "-e",
                f"""
const fs = require("fs");
const vm = require("vm");
const source = fs.readFileSync({json.dumps(str(ROOT / "web/app.js"))}, "utf8");
const elements = {{
  "#detail-content": {{ innerHTML: "" }},
  "#detail": {{ showModal() {{}}, close() {{}} }},
  "#close-detail": {{ addEventListener() {{}} }},
  "#generated": {{ textContent: "", hidden: false }},
  "#markets": {{ children: [], append(...nodes) {{ this.children.push(...nodes); }} }},
  "#error": {{ hidden: true }},
}};
const context = {{
  console,
  Intl,
  Date,
  Math,
  Number,
  String,
  document: {{
    createElement() {{
      return {{
        innerHTML: "",
        addEventListener() {{}},
      }};
    }},
    querySelector(selector) {{
      return elements[selector];
    }},
  }},
  fetch: async () => ({{
    ok: true,
    json: async () => ({{ generated_at: "2026-09-22T00:00:00+00:00", markets: [] }}),
  }}),
}};
vm.createContext(context);
vm.runInContext(source, context);
context.showDetail({{
  name: "NYダウ",
  current: 100,
  weather: "cloudy",
  up_probability: 0.5,
  analog_probability: null,
  analog_count: 0,
  range_low: 95,
  range_high: 105,
  confidence: 0.8,
  risk: "normal",
  last_data_date: "2026-09-21",
}});
process.stdout.write(elements["#detail-content"].innerHTML);
""",
            ],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )

        self.assertIn('aria-label="予測対象セッション日不明"', output.stdout)
        self.assertIn(">不明</span>", output.stdout)


if __name__ == "__main__":
    unittest.main()

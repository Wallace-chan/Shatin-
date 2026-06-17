# Shatin Weather · Social Posts

沙田自動氣象站實況 + 香港天文台全港概況 → **小紅書 / Instagram / Facebook** 統一粵語帖文（繁體中文書寫）。

## 運行

```bash
pip install requests openai
export DEEPSEEK_API_KEY="sk-你的密钥"   # 可選；未設則用本地粵語模板

python generate_social_posts.py
```

輸出：`output/post_*_social_unified.txt`（及 xiaohongshu / instagram / facebook 同名副本）

## 數據來源

| 來源 | 說明 |
|------|------|
| 沙田站 CSV + rhrread | 氣溫、濕度、雨量、風況 |
| HKO 開放 API（flw / warnsum） | 全港預報、生效警告（同 [天文台官網](https://www.hko.gov.hk/tc/index.html)） |

## GitHub Actions

工作流：`.github/workflows/social-posts.yml`

| 香港時間 | 說明 |
|----------|------|
| 08:00 | 早間帖文 |
| 12:00 | 午間帖文 |
| 18:00 | 傍晚帖文 |

**Secret**：`DEEPSEEK_API_KEY`（文案 AI；可選）

產物在 Actions → **Artifacts** 下載 `output/`。

## 檔案

| 檔案 | 作用 |
|------|------|
| `generate_social_posts.py` | 主程式 |
| `shatin_weather.py` | 沙田站數據 |
| `hko_overview.py` | 全港概況 |
| `deepseek_utils.py` | DeepSeek API |
| `data/social_state.json` | 去重狀態（Actions 會提交更新） |

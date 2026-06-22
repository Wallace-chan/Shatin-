# Shatin Weather · Social Posts

沙田自動氣象站實況 + 香港天文台全港概況 → **小紅書 / Instagram / Facebook** 統一粵語帖文（繁體中文書寫）。

## 運行

```bash
pip install requests openai Pillow
export DEEPSEEK_API_KEY="sk-你的密钥"   # 可選；未設則用本地粵語模板

python generate_social_posts.py      # 三平台帖文（【本港】【沙田】格式）+ 配图
python generate_cantonese_posts.py   # 粵語口語帖文（聊天语气，无配图）
python generate_multilang_posts.py   # 普通话 / English / Urdu（各 1 个文件）
```

### 多语言帖文（普通话 / English / Urdu）

数据抓取同上。每种语言独立模块，各输出 **1 个文件**（三平台通用）：

| 文件 | 语言 |
|------|------|
| `post_*_zh.txt` | 普通话（简体） |
| `post_*_en.txt` | English |
| `post_*_ur.txt` | اردو |

```bash
python generate_multilang_posts.py
```

模块：`multilang_post_zh.py` · `multilang_post_en.py` · `multilang_post_ur.py`

### 粵語口語帖文（新）

数据抓取同上（沙田站 + 天文台全港），**正文为口语化粤语**，自然段落，不用【本港】【沙田】标题。

输出：`output/post_*_cantonese.txt`（一篇，三平台通用）

```bash
python generate_cantonese_posts.py
```

### 社交帖文 + 配图

```bash
python 上传到Wallace-Shatin-/generate_social_posts.py
```

輸出：`output/post_*_social.txt`（一篇）+ `output/images/` 配图

### 配圖（每次 3 張）

| 檔名後綴 | 風格 |
|----------|------|
| `_cartoon.png` | 沙田 3D 卡通（城門河、马鞍山等） |
| `_chinese_shatin.png` | 丰子恺 + 吴冠中融合国画 · 沙田风景 + 至少一处沙田建筑；宁可无题字、绝不加印章 |
| `_poster.png` | **天气海报**：Pollinations 免费底图 + Pillow 叠繁体天气数据（数字准确） |

卡通 / 国画：色彩明快干净；底部保留繁体天气标语。  
海报：左侧程序排版天气，右侧 AI 插画；底部标语由程序叠加。

可选环境变量：`POSTER_SIZE=1080x1620`（默认竖版海报尺寸）  
仅生成部分风格：`SOCIAL_IMAGE_STYLES=cartoon,poster`

### 生圖引擎

| 引擎 | 環境變量 | 費用 |
|------|----------|------|
| **Pollinations + flux**（預設） | `IMAGE_MODEL=flux` `IMAGE_SIZE=1536` | 免費 |
| **OpenAI DALL·E 3** | `OPENAI_API_KEY` + `IMAGE_PROVIDER=openai` | 付費 |
| 国画用 DALL·E | `OPENAI_IMAGE_STYLES=chinese_shatin` | 付費 |

跳过配图：`SKIP_IMAGES=1`  
画面完全无底部标语：`SKIP_IMAGE_CAPTION=1`

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

**手動 Run workflow**：仍可即時生成帖文與配圖，但**不會**把 `data/social_state.json` push 回倉庫，以免打亂 08:00 / 12:00 / 18:00 三次定時任務的去重狀態。定時任務之間會排隊執行，避免 `git push` 衝突。

## 檔案

| 檔案 | 作用 |
|------|------|
| `generate_cantonese_posts.py` | **粵語口語**帖文主程式 |
| `cantonese_post.py` | 口語粵語模板 / DeepSeek 提示詞 |
| `multilang_common.py` | 多语言共用数据格式化 |
| `multilang_post_zh.py` | 普通话帖文 |
| `multilang_post_en.py` | English post |
| `multilang_post_ur.py` | Urdu post |
| `generate_multilang_posts.py` | 多语言帖文主程式 |
| `generate_social_posts.py` | 社交帖文 + 配图（见上传文件夹） |
| `shatin_weather.py` | 沙田站數據 |
| `hko_overview.py` | 全港概況 |
| `deepseek_utils.py` | DeepSeek API |
| `image_utils.py` | 配圖引擎（Pollinations / OpenAI / Pillow） |
| `poster_compose.py` | 天气海报拼版（AI 底图 + 繁体数据） |
| `social_image_styles.py` | 画风提示词 |
| `data/social_state.json` | 去重狀態（僅**定時** Actions 會提交更新；按 morning/noon/evening 分 slot） |

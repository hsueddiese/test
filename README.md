# test

包含兩個小工具：

- `daily_email_summary.py` — Gmail 每日信件摘要
- `ha_client.py` — Home Assistant REST API 客戶端（連線、查詢、控制裝置）

---

# Home Assistant 客戶端（`ha_client.py`）

透過 Home Assistant 的 REST API 連線，可測試連線、列出裝置、讀取狀態、控制裝置。
只依賴 `requests`，不需要額外套件。

## ⚠️ 請在「能連到 Home Assistant 的機器」上執行

這支程式要能連到你的 Home Assistant 才有用。請在**家中網路內的電腦**，或任何
**能連到你 HA 的機器**上執行。

> **注意：Claude Code 的雲端 / 網頁版無法連到一般的 Home Assistant。**
> 雲端環境的對外代理只允許 443 埠、且會依白名單限制目標主機，因此連不到
> `:8123` 這類非標準埠、或未列入白名單的家用主機。請改用本機版 Claude Code，
> 或依下方「Synology 反向代理」把服務改到 443 埠。

## 1. 安裝

```bash
git clone <this-repo>
cd test
python3 -m pip install requests
```

## 2. 建立長期存取權杖（Long-Lived Access Token）

1. 用瀏覽器打開你的 Home Assistant
2. 點左下角你的**個人檔案**（使用者名稱）
3. 進入 **安全性（Security）** 分頁 → 捲到 **長期存取權杖**
4. 點 **建立權杖**，取個名字（例如 `claude-code`），複製下來（只會顯示一次）

## 3. 設定連線資訊

複製範本並填入你的值：

```bash
cp .env.example .env
```

編輯 `.env`：

```ini
HA_URL=https://homeassistant.local:8123   # 或你的公開網址 / 內網 IP
HA_TOKEN=貼上你的長期存取權杖
```

`.env` 已被 `.gitignore` 忽略，**不會被提交或推送**。權杖權限很大，請妥善保管；
不需要時可到「個人檔案 → 安全性」隨時撤銷。

`HA_URL` 可以是：

- 內網位址：`http://homeassistant.local:8123`、`http://192.168.1.50:8123`
- 公開網址：`https://edmy.myds.me:8123`（DDNS）
- 反向代理後的 443 網址：`https://edmy.myds.me`（見下方 Synology 設定）

## 4. 使用

```bash
python3 ha_client.py ping                 # 測試連線，顯示 HA 版本、位置、裝置數
python3 ha_client.py list                 # 列出所有實體及狀態
python3 ha_client.py list light           # 只列出名稱含 "light" 的實體
python3 ha_client.py get light.kitchen    # 顯示單一實體完整狀態
python3 ha_client.py on   light.kitchen   # 開燈
python3 ha_client.py off  light.kitchen   # 關燈
python3 ha_client.py toggle switch.fan    # 切換開關

# 呼叫任意服務：call <網域> <服務> <實體>
python3 ha_client.py call light turn_on light.kitchen
python3 ha_client.py call cover open_cover cover.garage
```

`ping` 成功時的輸出範例：

```
Connected to Home Assistant at https://homeassistant.local:8123
  API says: API running.
  Location: 家    Version: 2026.7.0
  Entities: 128
```

## 常見問題

| 症狀 | 可能原因 |
|------|----------|
| `Connection reset by peer` | 走了不支援非 443 埠的代理（例如雲端環境）；改在本機執行或用反向代理 |
| `403 CONNECT` | 目標主機被環境的對外白名單擋掉；改在本機執行 |
| `401`（token 被拒） | 權杖錯誤或已撤銷；重新產生一個 |
| 連線逾時 | HA 網址 / 埠不對，或該機器連不到 HA |

---

# 在 Synology NAS 上設定反向代理（把 HA 改到 443 埠）

`.myds.me` 是 Synology 的 DDNS。若你想用標準的 `https://你的名稱.myds.me`（443 埠）
連到 Home Assistant，而不是 `:8123`，可用 DSM 內建的反向代理。這樣做的好處：

- 對外只開 443 埠，不必額外開放 8123
- 相容只支援 443 的用戶端與代理

## 設定步驟（DSM 7.x）

1. **控制台 → 登入入口網站（Login Portal）→ 進階（Advanced）→ 反向代理伺服器**
2. 點 **新增（Create）**，填寫：

   **來源（Source）**
   | 欄位 | 值 |
   |------|-----|
   | 通訊協定 | `HTTPS` |
   | 主機名稱 | `edmy.myds.me`（改成你的） |
   | 連接埠 | `443` |
   | 啟用 HSTS | 視需要 |

   **目的地（Destination）**
   | 欄位 | 值 |
   |------|-----|
   | 通訊協定 | `HTTP` |
   | 主機名稱 | `localhost`（HA 與 NAS 同機）或 HA 的內網 IP |
   | 連接埠 | `8123` |

3. **自訂標頭（Custom Header）分頁 → 建立 → WebSocket**
   會自動加入以下兩個標頭（Home Assistant 前端需要 WebSocket）：
   - `Upgrade: $http_upgrade`
   - `Connection: $connection_upgrade`

4. 儲存。

## Home Assistant 端設定

編輯 `configuration.yaml`，讓 HA 信任來自 NAS 反向代理的連線：

```yaml
http:
  use_x_forwarded_for: true
  trusted_proxies:
    - 127.0.0.1        # 反向代理與 HA 同機時
    - ::1
    # - 192.168.1.10   # 若反向代理在別台 NAS，填其內網 IP
```

改完重新啟動 Home Assistant。

## 路由器 / DDNS

- 在路由器把對外 **443** 埠轉發到 NAS。
- 確認 Synology DDNS（`edmy.myds.me`）指向你目前的對外 IP。
- 建議在 DSM 用 Let's Encrypt 申請該網域的憑證，避免憑證警告。

完成後，`.env` 就可以改成走 443：

```ini
HA_URL=https://edmy.myds.me
HA_TOKEN=你的權杖
```

再執行 `python3 ha_client.py ping` 驗證即可。

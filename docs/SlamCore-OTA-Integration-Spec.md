# SlamCore OTA Integration Specification v1

> 文件狀態：Draft for implementation  
> Contract version：`1.0`  
> 適用專案：`SlamCore-Server`、`SlamCore-Agent`、`SlamCore-Updater`  
> 建議存放路徑：`docs/SlamCore-OTA-Integration-Spec.md`

## 1. 目的與治理原則

本文件是三個 Repository 之間的跨專案契約（single source of truth），固定以下內容：

- Server API Contract
- Agent 與 Updater API Contract
- Update State Machine
- Release Package Format
- 錯誤碼、冪等、逾時、重試及版本相容性規則

實作若與本文件不同，以本文件為準。契約變更必須先修改本文件、提升 Contract version，再修改各專案。禁止只在單一 Repository 變更公開 DTO、端點、狀態名稱或套件格式。

### 1.1 文件同步方式

建議指定一個規格主控 Repository 保存權威版本，其餘兩個 Repository 保存唯讀鏡像副本。初期可將 `SlamCore-Server` 設為主控端，因為它負責發布、任務與設備資料模型。

每份副本頂端必須保留相同的 Contract version。CI 應比較三份文件的 SHA-256，或由主控端自動同步，避免內容漂移。

### 1.2 相容性規則

- API 路徑固定使用 `/api/v1`。
- `contractVersion` 使用 `major.minor`，本版為 `1.0`。
- 新增 optional 欄位屬向後相容，可提升 minor version。
- 刪除或更名欄位、改變欄位型別、改變狀態語意、改變必要檔案，屬破壞性變更，必須提升 major version。
- 接收端必須忽略未知 JSON 欄位；不得因 minor version 新增欄位而失敗。
- JSON 欄位使用 camelCase；時間使用 UTC ISO 8601，例如 `2026-08-20T01:30:00Z`。
- ID 使用不透明字串；不得由呼叫端解析 ID 內容。
- 版本號使用 SemVer，傳輸與儲存時不含前置 `v`，例如 `1.0.6`。

## 2. 系統邊界

| 元件 | 平台 | 責任 | 不負責 |
| --- | --- | --- | --- |
| SlamCore-Server | Windows Service / .NET 8 / PostgreSQL | 設備、Release、Update Job、中央狀態 | 直接操作 Jetson |
| SlamCore-Agent | Windows Service / .NET 8 / SQLite | 輪詢 Server、控制單一 Jetson、保存本地狀態 | 解壓或部署 ROS 2 Release |
| SlamCore-Updater | Jetson Linux 背景服務 | 下載、驗證、備份、安裝、建置、重啟、健康檢查、回復 | 決定設備應更新到哪一版 |

通訊方向：Agent 主動呼叫 Server；Agent 主動呼叫 Updater。v1 不要求 Server 主動連入 Agent，也不要求 Updater 直接連 Server。

## 3. 共用 HTTP 規範

### 3.1 Header

每個 API request 應包含：

```http
Accept: application/json
Content-Type: application/json
X-SlamCore-Contract-Version: 1.0
X-Correlation-Id: <uuid>
```

觸發具副作用的操作時還必須包含：

```http
Idempotency-Key: <stable-operation-key>
```

同一 `Idempotency-Key` 與相同 request body 重送時，服務端必須回傳原操作結果，不得建立第二個 Job。相同 key 搭配不同 body 時回傳 `409 Conflict`。

### 3.2 共用錯誤格式

使用 RFC 7807 相容格式：

```json
{
  "type": "https://slamcore.local/problems/update-conflict",
  "title": "Update already in progress",
  "status": 409,
  "code": "UPDATE_ALREADY_RUNNING",
  "detail": "Device AMR-001 already has an active update job.",
  "correlationId": "7d6a89e0-7a99-4da6-a281-8e58d7252540",
  "retryable": false
}
```

最低共用錯誤碼：

| HTTP | code | retryable | 說明 |
| --- | --- | --- | --- |
| 400 | `VALIDATION_FAILED` | false | 欄位或格式錯誤 |
| 404 | `RESOURCE_NOT_FOUND` | false | Device、Release 或 Job 不存在 |
| 409 | `UPDATE_ALREADY_RUNNING` | false | 同一設備已有進行中任務 |
| 409 | `IDEMPOTENCY_CONFLICT` | false | 相同 key 搭配不同內容 |
| 422 | `INCOMPATIBLE_RELEASE` | false | 平台或契約版本不相容 |
| 503 | `DEPENDENCY_UNAVAILABLE` | true | DB、Docker 或下游服務不可用 |
| 504 | `OPERATION_TIMEOUT` | true | 下游或更新階段逾時 |

## 4. Server API Contract

Base URL：`http://<server-host>:5000/api/v1`

### 4.1 註冊或更新設備資料

`PUT /devices/{deviceId}`

```json
{
  "contractVersion": "1.0",
  "machineName": "Machine-PC-01",
  "agentVersion": "1.0.0",
  "updaterEndpoint": "http://192.168.0.50:5000",
  "platform": "jetson-orin",
  "currentReleaseVersion": "1.0.5"
}
```

成功：`200 OK`；第一次建立也回 `200 OK`，以簡化 Agent 重試。

```json
{
  "deviceId": "AMR-001",
  "registered": true,
  "serverTimeUtc": "2026-08-20T01:30:00Z",
  "pollIntervalSeconds": 300
}
```

### 4.2 Agent heartbeat 與狀態回報

`POST /devices/{deviceId}/heartbeat`

```json
{
  "contractVersion": "1.0",
  "agentStatus": "online",
  "updaterStatus": "online",
  "currentReleaseVersion": "1.0.5",
  "activeJobId": null,
  "observedAtUtc": "2026-08-20T01:30:00Z"
}
```

成功：`204 No Content`。

### 4.3 取得待執行更新

`GET /devices/{deviceId}/update-command`

無待執行命令：`204 No Content`。

有命令：`200 OK`。

```json
{
  "contractVersion": "1.0",
  "jobId": "job-01J5QZ9WZ7H1",
  "targetVersion": "1.0.6",
  "packageUrl": "http://server/releases/SlamCoreWeb.1.0.6.zip",
  "packageSha256": "<64 lowercase hex characters>",
  "platform": "jetson-orin",
  "createdAtUtc": "2026-08-20T01:25:00Z",
  "expiresAtUtc": "2026-08-21T01:25:00Z"
}
```

`jobId` 是跨三端追蹤的唯一 Job ID。Agent 傳給 Updater 時不得另建不同的業務 Job ID。

### 4.4 回報更新進度

`PUT /devices/{deviceId}/update-jobs/{jobId}/status`

```json
{
  "contractVersion": "1.0",
  "state": "building",
  "progressPercent": 65,
  "message": "Building changed ROS 2 packages",
  "errorCode": null,
  "fromVersion": "1.0.5",
  "targetVersion": "1.0.6",
  "observedAtUtc": "2026-08-20T01:42:00Z"
}
```

本端點為 idempotent。相同或較舊的狀態序號不得覆寫較新的狀態；實作可在 DTO 增加單調遞增的 `sequence` optional 欄位。

### 4.5 取得歷史

`GET /devices/{deviceId}/update-jobs?limit=50&before=<jobId>`

回傳由新至舊的 Job 摘要陣列。`limit` 預設 50，上限 200。

## 5. Agent 與 Updater API Contract

Base URL：`http://<jetson-host>:5000/api/v1`

### 5.1 Updater 狀態

`GET /status`

```json
{
  "contractVersion": "1.0",
  "serviceVersion": "1.0.0",
  "platform": "jetson-orin",
  "currentReleaseVersion": "1.0.5",
  "state": "idle",
  "activeJobId": null,
  "dockerStatus": "running",
  "healthy": true
}
```

### 5.2 啟動更新

`POST /update-jobs`

Header：`Idempotency-Key: <server-jobId>`

```json
{
  "contractVersion": "1.0",
  "jobId": "job-01J5QZ9WZ7H1",
  "targetVersion": "1.0.6",
  "packageUrl": "http://server/releases/SlamCoreWeb.1.0.6.zip",
  "packageSha256": "<64 lowercase hex characters>",
  "platform": "jetson-orin"
}
```

首次接受：`202 Accepted`。重送相同請求：`200 OK` 或 `202 Accepted`，但必須回傳同一 Job。

```json
{
  "jobId": "job-01J5QZ9WZ7H1",
  "accepted": true,
  "state": "queued",
  "statusUrl": "/api/v1/update-jobs/job-01J5QZ9WZ7H1"
}
```

### 5.3 查詢更新

`GET /update-jobs/{jobId}`

```json
{
  "contractVersion": "1.0",
  "jobId": "job-01J5QZ9WZ7H1",
  "state": "building",
  "progressPercent": 65,
  "message": "Building lp_imu",
  "fromVersion": "1.0.5",
  "targetVersion": "1.0.6",
  "errorCode": null,
  "createdAtUtc": "2026-08-20T01:31:00Z",
  "updatedAtUtc": "2026-08-20T01:42:00Z"
}
```

### 5.4 要求回復

`POST /update-jobs/{jobId}/rollback`

Header：`Idempotency-Key: rollback:<jobId>`

只允許對仍保留可用備份的 Job 執行。接受時回 `202 Accepted`；已在 rollback 中重送時回原狀態。

## 6. Update State Machine

### 6.1 標準狀態

| state | 執行端 | progress 建議區間 | 說明 |
| --- | --- | ---: | --- |
| `queued` | Agent / Updater | 0 | 已接受，尚未執行 |
| `checking` | Updater | 1–5 | 檢查版本、空間、平台與相容性 |
| `downloading` | Updater | 6–25 | 下載到暫存檔 |
| `verifying` | Updater | 26–30 | 驗證 ZIP SHA-256 與 manifest |
| `backing_up` | Updater | 31–40 | 建立可回復備份 |
| `installing` | Updater | 41–60 | 解壓及切換檔案 |
| `building` | Updater | 61–80 | 依 build manifest 增量建置 |
| `restarting` | Updater | 81–90 | 重啟 Docker / ROS 2 runtime |
| `health_checking` | Updater | 91–99 | 驗證容器、服務與版本 |
| `completed` | Updater | 100 | 新版本健康，任務成功 |
| `failed` | Updater | 保留最後值 | 任務失敗，未完成回復或不需回復 |
| `rolling_back` | Updater | 保留最後值 | 正在回復 |
| `rolled_back` | Updater | 100 | 舊版本恢復健康；原更新仍視為失敗 |

狀態字串固定為小寫 snake_case。Server、Agent 與 Updater 必須使用同一組名稱。

### 6.2 合法轉換

正常路徑：

`queued → checking → downloading → verifying → backing_up → installing → building → restarting → health_checking → completed`

例外路徑：

- `checking` 到 `backing_up` 任一階段可轉 `failed`；若尚未切換現行版本，不必 rollback。
- `installing`、`building`、`restarting`、`health_checking` 失敗時轉 `rolling_back`。
- `rolling_back → rolled_back` 或 `rolling_back → failed`。
- Terminal states：`completed`、`rolled_back`、`failed`。Terminal state 不得回到執行中狀態。
- v1 同一台 Updater 同時只允許一個 active Job。

### 6.3 逾時與重試

| 操作 | 建議 timeout | 自動重試 |
| --- | ---: | ---: |
| Agent 呼叫 Server | 15 秒 | 最多 3 次，指數退避加 jitter |
| Agent 呼叫 Updater 一般 API | 10 秒 | 最多 3 次 |
| 下載 Package | 30 分鐘 | 最多 3 次，可續傳則續傳 |
| Build | 45 分鐘 | 0 次；失敗後進 rollback |
| Restart | 5 分鐘 | 1 次 |
| Health check | 10 分鐘 | 間隔 10 秒持續檢查 |
| Rollback | 20 分鐘 | 1 次 |

Agent 重啟後必須從 SQLite 讀取 active Job，先查詢 Updater 狀態，再決定繼續監控或補回報 Server，不可直接重送新的更新。Updater 重啟後必須從持久化 Job journal 恢復，不能只保存於記憶體。

## 7. Release Package Format

### 7.1 命名

```text
SlamCoreWeb.<semver>.zip
```

範例：`SlamCoreWeb.1.0.6.zip`。檔名版本、manifest 版本與 `.slamcore_release` 版本必須完全相同。

### 7.2 ZIP 根目錄

ZIP 解開後必須只有一個產品根目錄：

```text
SlamCoreWeb/
├── .slamcore_release
├── .slamcore_build_manifest.json
├── docker-compose.yml
├── scripts/
├── src/
└── config/
```

禁止 ZIP path traversal、絕對路徑、超出根目錄的 symlink，以及大小寫衝突檔名。Updater 必須先解到 staging 目錄並驗證，不能直接覆寫現行 Release。

### 7.3 `.slamcore_release`

v1 使用 UTF-8、LF、`KEY=VALUE`：

```dotenv
FORMAT_VERSION=1
PRODUCT=SlamCoreWeb
VERSION=1.0.6
PLATFORM=jetson-orin
MIN_UPDATER_VERSION=1.0.0
CONTRACT_VERSION=1.0
```

必要欄位缺少、版本不一致或平台不符時拒絕更新並回報 `INCOMPATIBLE_RELEASE`。

### 7.4 `.slamcore_build_manifest.json`

```json
{
  "schemaVersion": 1,
  "buildMode": "incremental",
  "packages": [
    "lp_imu",
    "lp_bringup"
  ],
  "healthChecks": [
    {
      "type": "dockerContainer",
      "name": "slamcore-web",
      "expectedState": "running",
      "timeoutSeconds": 300
    }
  ]
}
```

規則：

- `schemaVersion` 必須為 Updater 支援的版本。
- `buildMode` v1 僅允許 `incremental` 或 `none`。
- `packages` 是 ROS 2 package name，不是檔案路徑；不得重複。
- Updater 必須驗證 package 存在後才呼叫 build manager。
- `healthChecks` 可為空陣列，但欄位必須存在。
- JSON 不允許註解。

### 7.5 完整性驗證

Server 保存整個 ZIP 的 SHA-256；Agent 原樣傳給 Updater；Updater 下載完成後自行計算並比較。SHA-256 不一致時不得解壓、建置或切換版本。

本次需求不定義 TLS、憑證或套件簽章；這些屬後續安全版本的擴充範圍。即使使用內網 HTTP，SHA-256 完整性驗證仍為必要步驟。

## 8. 資料持久化與一致性

- Server PostgreSQL 是中央 Job 與 Release metadata 的 system of record。
- Agent SQLite 保存 Device 設定、Server Job ID、Updater Job 狀態、最後成功同步時間與待補送事件。
- Updater 保存本地 Job journal、現行版本、前一健康版本與備份位置。
- 三端以 `jobId`、`deviceId`、`targetVersion` 關聯；禁止用 message 文字判斷狀態。
- Agent 對 Server 採 at-least-once 回報；Server API 必須 idempotent。
- 網路中斷時 Agent 將最新狀態與 terminal result 保存在 SQLite，恢復後補送。

## 9. v1 驗收案例

1. 設備註冊與重複註冊結果一致。
2. 無更新時 Server 回 `204`，Agent 不建立本地 Job。
3. 同一 Server Job 重送給 Updater 不會啟動第二次更新。
4. ZIP SHA-256 不符時停在安裝前並回 `failed`。
5. platform 或 minimum updater version 不符時回 `INCOMPATIBLE_RELEASE`。
6. 正常更新完整經過合法狀態並到達 `completed`。
7. 建置失敗會 rollback，舊版本健康後到達 `rolled_back`。
8. Agent 在更新中重啟後能恢復追蹤，不重複觸發更新。
9. Server 暫時離線時更新結果保存在 SQLite，恢復後成功補送。
10. 三個 Repository 的規格文件 Contract version 與 SHA-256 相同。

## 10. Codex 跨專案執行計畫

### Phase 0：建立整合基準

先在規格主控 Repository 建立本文件，再複製到另外兩個 Repository。此階段只更新契約文件、`AGENTS.md`、`docs/CODEX_HANDOFF.md` 與 `README.md`，不改產品程式碼。

要求 Codex：

- 盤點現有 API、DTO、狀態與套件格式。
- 建立差異表：`Existing / Spec v1 / Required change / Repository owner`。
- 不得自行改動本文件的公開契約；若發現不可實作項目，先列為 blocker。
- 在三個專案的 `AGENTS.md` 加入跨專案契約約束。
- 在 `docs/CODEX_HANDOFF.md` 記錄目前符合度、未完成項目及相依 PR。
- 在 `README.md` 加入角色、部署方式與規格文件連結。

### Phase 1：SlamCore-Updater

分支：`feature/ota-contract-v1-updater`

優先完成 Updater API、state machine、Job journal、package validation 與 rollback，因為 Agent 依賴其行為。

### Phase 2：SlamCore-Agent

分支：`feature/ota-contract-v1-agent`

在 Updater v1 contract 穩定後，完成 Server polling、Updater client、SQLite recovery、idempotency 與狀態補送。

### Phase 3：SlamCore-Server

分支：`feature/ota-contract-v1-server`

最後完成 Device、Release、Update Job API、PostgreSQL migrations、狀態驗證及冪等處理。

### Phase 4：整合驗證

分支名稱依各 Repository 慣例；建立三端測試環境，至少涵蓋第 9 節全部案例。若實作發現契約需變更，回到 Phase 0 修改規格並同步 Contract version，不得在測試中以私有例外繞過。

## 11. Codex 執行指令

以下指令在每個 Repository 根目錄個別執行。先確認工作樹乾淨並依專案實際預設分支調整起點。

### 11.1 規格主控 Repository

```bash
git switch main
git pull --ff-only
git switch -c docs/ota-integration-spec-v1
mkdir -p docs
# 將本文件放到 docs/SlamCore-OTA-Integration-Spec.md
codex "請先閱讀 AGENTS.md、docs/CODEX_HANDOFF.md、README.md 與 docs/SlamCore-OTA-Integration-Spec.md。依規格執行 Phase 0：盤點現有契約並建立差異表，只修改文件，不修改產品程式碼。更新 AGENTS.md、docs/CODEX_HANDOFF.md 與 README.md；保留既有有效內容。完成後列出變更摘要、發現的 blocker、跨 Repository 相依項目與驗證結果。"
```

### 11.2 SlamCore-Updater

```bash
git switch main
git pull --ff-only
git switch -c feature/ota-contract-v1-updater
codex "請完整閱讀 AGENTS.md、docs/CODEX_HANDOFF.md、README.md 與 docs/SlamCore-OTA-Integration-Spec.md，依 Phase 1 實作 Updater。先分析既有更新、Docker、build manager 與 rollback 流程，保留現有功能；再完成 API、冪等、持久化 state machine、package 驗證、重啟恢復與測試。同步更新 AGENTS.md、docs/CODEX_HANDOFF.md、README.md。不得自行修改跨專案契約；若契約不可實作，停止相關變更並列出 blocker。最後執行可用測試並提供結果。"
```

### 11.3 SlamCore-Agent

```powershell
git switch main
git pull --ff-only
git switch -c feature/ota-contract-v1-agent
codex "請完整閱讀 AGENTS.md、docs/CODEX_HANDOFF.md、README.md 與 docs/SlamCore-OTA-Integration-Spec.md，依 Phase 2 建立或調整 .NET 8 Windows Service Agent。完成 Server client、Updater client、SQLite persistence、active Job recovery、冪等、防重複更新與離線補送；不得建立 GUI。同步更新 AGENTS.md、docs/CODEX_HANDOFF.md、README.md，並加入 contract tests。不得自行修改跨專案契約；若契約不可實作，列出 blocker。最後執行 dotnet build 與 dotnet test 並提供結果。"
```

### 11.4 SlamCore-Server

```powershell
git switch main
git pull --ff-only
git switch -c feature/ota-contract-v1-server
codex "請完整閱讀 AGENTS.md、docs/CODEX_HANDOFF.md、README.md 與 docs/SlamCore-OTA-Integration-Spec.md，依 Phase 3 建立或調整 .NET 8 ASP.NET Core Windows Service。完成 Device、Release、Update Job API、PostgreSQL migrations、狀態轉換驗證、冪等與歷史查詢；使用 Kestrel 背景執行，不建立 GUI。同步更新 AGENTS.md、docs/CODEX_HANDOFF.md、README.md，並加入 contract/integration tests。不得自行修改跨專案契約；若契約不可實作，列出 blocker。最後執行 dotnet build 與 dotnet test 並提供結果。"
```

### 11.5 三端最終驗證提示

```text
請依 docs/SlamCore-OTA-Integration-Spec.md 第 9 節建立並執行跨專案驗收。
先確認三份規格文件 Contract version 與 SHA-256 相同，再驗證正常更新、重送、斷線恢復、Agent 重啟、SHA-256 錯誤、平台不相容、建置失敗與 rollback。
請輸出每個案例的前置條件、操作、預期結果、實際結果與證據；不要在未通過時修改契約或放寬 assertion。
```

## 12. 各專案文件必須加入的內容

### `AGENTS.md`

- 本 Repository 在 OTA 架構中的責任邊界。
- `docs/SlamCore-OTA-Integration-Spec.md` 是跨專案公開契約。
- 修改 API、DTO、state 或 package format 前，必須先更新規格與 Contract version。
- 不得破壞未知欄位容忍、冪等及重啟恢復要求。

### `docs/CODEX_HANDOFF.md`

- 目前 Contract version。
- 已實作與尚未實作的規格章節。
- 已知 blocker、migration 注意事項及跨 Repository PR/commit 參照。
- 最近一次 contract/integration test 結果。

### `README.md`

- 元件角色及部署平台。
- 背景服務安裝與啟動方式。
- 設定檔及 DB 位置。
- API 或 client 使用範例。
- 連到本整合規格、故障排除及 rollback 說明。

## 13. 後續版本待辦（不納入 v1 實作）

- 驗證與授權。
- HTTPS、憑證與 package signature。
- Server push 或訊息佇列。
- 多 Jetson 對單一 Agent。
- 分批發布、維護時段、暫停與取消。
- OpenAPI 文件自動產生 client，以及三端 schema diff CI。

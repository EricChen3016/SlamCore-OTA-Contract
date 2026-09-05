# SlamCore OTA Integration Specification v2

> 文件狀態：Draft for implementation
> Repository version：`2.1.0`
> Runtime contract version：`2.0`
> 適用專案：`SlamCore-Server`、`SlamCore-Agent`、`SlamCore-Updater`

## 1. 權威性、版本與相容性

本 repository 是 Server、Agent 與 Updater 的唯一跨專案 OTA contract。產品 repository 必須 pin reviewed commit 或 `contract-v*` tag，不得複製、延伸或重新解釋公開 API、DTO、state、錯誤碼或 release format。

- HTTP base path 保持 `/api/v1`；這是 endpoint generation，並不等於 runtime contract version。
- JSON/header 的 `contractVersion` 與 `X-SlamCore-Contract-Version` 固定為 `2.0`。
- JSON 欄位採 camelCase；時間為 UTC ISO 8601；版本為不含 `v` 的 SemVer；ID 是不透明字串。
- DTO 接收端容忍未知欄位，以利 2.x minor additions；strict release metadata 不容忍未知欄位。
- Contract 1.x 與 2.0 不相容。2.0 移除 `building` public state、改變 package metadata，並移除 Updater 的 ROS build ownership。
- Repository `2.1.0` 在 runtime `2.0` 內新增獨立、可選用的 discriminated command endpoint；既有 update-only endpoint 與 Updater wire contract 不變。

## 2. 系統責任邊界

| 元件 | 責任 | 明確不負責 |
| --- | --- | --- |
| Server | Device、Release、Update Job 與中央狀態 | 直接操作 Jetson、runtime build |
| Agent | 輪詢 Server、呼叫 Updater、持久化與補送狀態 | 解壓、activation、runtime build |
| Updater | artifact download、SHA-256/integrity 與 metadata validation、staging、activation、active release marker、managed runtime restart、health verification、rollback、crash recovery | ROS package detection/build/reconciliation；Build Manager internal state |
| SlamCoreWeb runtime startup | 依 active release reconcile ROS build state，啟動應用並收斂到健康 | OTA transaction、artifact validation、activation、rollback |

`.slamcore_build_manifest.json` 是 SlamCoreWeb Build Manager (`scripts/ros_build_manager.py`) 在 **workspace root** 自行讀寫的 internal build-state manifest，不是 release package metadata，也不是 Updater transaction state。OTA Contract 不定義其 schema。Updater **MUST NOT** parse、validate、create、mutate、delete、migrate、checkpoint 或 rollback 該檔案；未知的未來 schema/version/content 也不得造成 package 或 update rejection。Filesystem deployment 與 rollback 必須 preserve 此檔及其他 unrelated workspace-level state。

## 3. 共用 HTTP 與錯誤

每個 JSON request 使用 `Accept: application/json`、`Content-Type: application/json`、`X-SlamCore-Contract-Version: 2.0` 及 `X-Correlation-Id`。具副作用操作另帶穩定的 `Idempotency-Key`。相同 key/body 必須回原 job；相同 key/different body 回 `409 IDEMPOTENCY_CONFLICT`。

錯誤採 RFC 7807 compatible body。最低錯誤碼：

| HTTP | code | retryable | 意義 |
| --- | --- | --- | --- |
| 400 | `VALIDATION_FAILED` | false | DTO/格式無效 |
| 404 | `RESOURCE_NOT_FOUND` | false | Resource 不存在 |
| 409 | `UPDATE_ALREADY_RUNNING` | false | 已有 active job |
| 409 | `IDEMPOTENCY_CONFLICT` | false | key 被不同 request 使用 |
| 422 | `INCOMPATIBLE_RELEASE` | false | package metadata、platform、contract 或 minimum Updater 不相容 |
| 503 | `DEPENDENCY_UNAVAILABLE` | true | runtime/DB/下游不可用 |
| 504 | `OPERATION_TIMEOUT` | true | 操作或健康收斂逾時 |

## 4. Server API

Base URL：`http://<server-host>:5000/api/v1`。Machine definitions 以 `openapi/slamcore-server-v1.yaml` 及其 referenced schemas 為準。

- `POST /devices/register`：註冊/更新設備，idempotent。
- `GET /devices/{deviceId}/update`：相容用 update-only endpoint；無 update 回 `204`，且永遠不得回傳 rollback command。
- `GET /devices/{deviceId}/command`：新版 command endpoint；無命令回 `204`，有命令回 `commandType=update|rollback` 的 discriminated command。
- `POST /devices/{deviceId}/status`：依 `Idempotency-Key: status:<jobId>:<sequence>` 單調回報；舊 sequence 不得覆蓋新狀態。
  - `sequence` 以 `jobId` 為 scope，由 Agent 分配；第一筆 durably-enqueued distinct status observation 為 `0`，之後每一筆新的 durable observation 必須恰好加 `1`。
  - retry/replay 既有 observation 不分配新 sequence，必須重用完全相同的 request body、sequence 與 `Idempotency-Key`。
  - request body 的 `sequence` 必須是非負整數，且 idempotency key 的 sequence suffix 必須與 body 值相同。
  - Contract 不要求 status 透過 HTTP 抵達 Server 時連續或依 allocation order；Server 對 stale、duplicate 與 transition 的 runtime 處理由 Server implementation 負責。
- `GET /devices/{deviceId}/history`：newest-first，`limit` 1–200。

### 4.1 Explicit command identity

新版 command endpoint 的每個 `200` response 必須有 explicit `commandType`。不得從 `targetVersion`、package field 是否存在或特殊版本值推斷 command type；缺漏或未知 discriminator 必須 fail closed。

- Update command：`jobId=U`，要求 `deviceId`、`targetVersion`、`packageUrl`、`packageSha256`、`platform`、`createdAtUtc`、`expiresAtUtc`；不得有 `originalUpdateJobId`。`U` 原樣成為 Updater update identity。
- Rollback command：獨立 `jobId=R`，要求 `deviceId`、`originalUpdateJobId=U`、`createdAtUtc`、`expiresAtUtc`；不得有 `targetVersion`、`packageUrl`、`packageSha256` 或 `platform`。`R` 是 Server/Agent orchestration 與 status scope，`U` 是 Updater rollback identity。

同一 `U` 最多建立一個 logical rollback command `R`；管理端、delivery 或 restart retry 必須重用同一 `R` 與 `U`。完整 mapping、recovery 與 rollout 見 [Explicit rollback orchestration](explicit-rollback-orchestration.md)。

Server 不得在 `expiresAtUtc` 當下或之後交付 command。Agent 在第一次呼叫 Updater 前也必須檢查期限；尚未 submit 即過期的 command 不得造成 mutation，並以 terminal `failed`／`COMMAND_EXPIRED` 回報。若 submit 可能已發生（包含 response loss），期限不會取消 operation；Agent 仍使用持久化的同一 `R`、`U` 查詢或 exact-replay，直到 terminal。

## 5. Updater API

Base URL：`http://<jetson-host>:5000/api/v1`。Machine definitions 以 `openapi/slamcore-updater-v1.yaml` 及 referenced schemas 為準。

- `GET /status`：無 active job 時為 `idle` 且 `activeJobId: null`。
- `POST /update`：`Idempotency-Key: <server-jobId>`；首次接受 `202`，相同 request 可回 `200/202` 且為同一 job。
- `GET /update/{jobId}`：回 public transaction state；SlamCoreWeb startup 的內部 build progress 不得映射成 `building`。
- `POST /rollback`：body `jobId=U` 必須是 original successful update identity；只接受 `U` 仍有 retained previous release 的情況，idempotency key 固定為 `rollback:U`。Updater response 與 `GET /update/U` 的 `jobId` 仍為 `U`，不接收 Server rollback command identity `R`。

所有 runtime DTO 的 `contractVersion` 為 `2.0`。

## 6. Update state machine

| state | progress 建議 | 語意 |
| --- | ---: | --- |
| `idle` | N/A | service 可用且無 active job；不是 job lifecycle state |
| `queued` | 0 | 已接受、尚未執行 |
| `checking` | 1–5 | preflight 相容性與空間檢查 |
| `downloading` | 6–25 | 下載 artifact 到 temporary storage |
| `verifying` | 26–35 | **先驗證 ZIP SHA-256**，再安全檢查 archive 與 package metadata |
| `backing_up` | 36–45 | durable 記錄 previous active release/rollback data |
| `installing` | 46–70 | staging release 並原子切換 active link/marker |
| `restarting` | 71–85 | 啟動 managed runtime；SlamCoreWeb startup 可在內部 reconcile/build |
| `health_checking` | 86–99 | 等待新 runtime 達成 externally observable health |
| `completed` | 100 | 新 active release 已健康 |
| `rolling_back` | 保留 | 恢復 previous link/marker 並重啟/驗證舊 runtime |
| `rolled_back` | 100 | previous runtime 恢復健康；對 update `U` 表示自動 rollback 後的 update failure，對 explicit rollback `R` 表示 rollback success |
| `failed` | 保留 | activation 前失敗、不需 rollback，或 rollback 無法恢復健康 |

正常 transition：

`queued → checking → downloading → verifying → backing_up → installing → restarting → health_checking → completed`

例外 transition：

- `checking`、`downloading`、`verifying`、`backing_up` 在 active link 尚未 mutation 時可到 `failed`。
- 自 active link mutation 起，`installing`、`restarting` 或 `health_checking` 的 failure/timeout 必須到 `rolling_back`。
- `rolling_back → rolled_back`（previous runtime 健康）或 `rolling_back → failed`。
- Explicit rollback 沿用 `queued → rolling_back → rolled_back|failed` subset；允許未觀察到瞬時 `queued`。
- `completed`、`rolled_back`、`failed` 是 terminal；同一 Updater 同時最多一個 active job。
- Updater 僅依 managed runtime health 判定，不須辨識 colcon、ROS package 或其他 startup failure cause。
- Server terminal projection 必須依 command type：explicit rollback `R` 的 `rolled_back` 是成功，update `U` 的 `rolled_back` 維持失敗但已安全恢復的語意。

## 7. Timeout 與 recovery

| 操作 | Contract requirement | retry |
| --- | ---: | ---: |
| Agent→Server | 15 秒 | 最多 3 次，exponential backoff + jitter |
| Agent→Updater 一般 API | 10 秒 | 最多 3 次 |
| Artifact download | 30 分鐘 | 最多 3 次；可續傳則續傳 |
| Managed runtime startup + health convergence | **60 分鐘** | health probe 每 10 秒；不另設 Build timeout |
| Rollback restart + health convergence | 20 分鐘 | 最多 1 次 |

60 分鐘 window 包含 SlamCoreWeb startup 自行進行的 ROS reconcile/build。Updater 不呼叫 Build Manager，也不設 45-minute Build operation。

Updater journal 必須在 destructive/externally visible steps 前後 durable checkpoint，並以 idempotent recovery 收斂：

1. active-link mutation 前 crash：保留舊 active link/marker，restart 後可重做 staging/activation；不得 rollback workspace state。
2. link mutation 後、該 mutation durable checkpoint 前 crash：recovery 必須由 filesystem link、previous release journal 與 marker 判斷並完成 activation 或 rollback，不能假設 checkpoint 代表實際 filesystem；不得啟動不確定 release。
3. marker commit 後 crash：marker 是 committed active release；recovery 從 managed runtime restart/health verification 繼續。若無法健康則 rollback link **及 marker**。
4. 所有 recovery/rollback 均不得修改 `.slamcore_build_manifest.json` 或 unrelated workspace state。

Agent restart 從本地 persistent job 恢復並先查 Updater；不得建立新 job。Explicit rollback recovery 保留 `R` 與 `U`，查詢 `GET /update/U`，必要時以完全相同的 `rollback:U` request replay。Agent 對 Updater 驗證 `U`，但對 Server 以 `status:R:<sequence>` 保存與補送 rollback observation。Server 離線時 terminal result 必須保存後補送。

## 8. Contract 2.0 release package format

Archive 名稱為 `SlamCoreWeb.<semver>.zip`，解開後只有一個 `SlamCoreWeb/` product root。必須包含：

```text
SlamCoreWeb/
├── .slamcore-package.json
├── docker/
├── scripts/
├── app/
└── pkgs/
```

其他 runtime content 可存在。Archive 不得有 path traversal、absolute path、root 外 symlink、大小寫 collision 或 Git metadata。Updater 僅解至 staging；不得以 mirror/delete semantics 套用到 workspace root。

### 8.1 Package metadata：`SlamCoreWeb/.slamcore-package.json`

這是 archive 內 strict JSON metadata，由 `schemas/release/slamcore-package.schema.json` 定義。`formatVersion` 為 `2`、`contractVersion` 為 `2.0`；`product`、`version`、`platform` 與 `minimumUpdaterVersion` 必須相容。Archive filename、request `targetVersion` 與 metadata `version` 必須完全一致。不相容必須在 active-link mutation 前以 `INCOMPATIBLE_RELEASE` 失敗。

Contract 2.0 package **不得依賴** `.slamcore_release` 或 `.slamcore_build_manifest.json` 作為 metadata；後者無需存在於 ZIP，也不得被 Updater 驗證。

### 8.2 Workspace active release marker：`<workspace>/.slamcore_release`

`.slamcore_release` 僅是 workspace-level **active release marker**，由 Updater ownership。格式為 UTF-8、LF、exactly one SemVer line（例如 `1.0.6\n`），不得為 `KEY=VALUE`。它不在 release ZIP 內。

Activation 對 active link 與 marker 的 committed pair 負責：marker 以 same-directory temporary file、flush/fsync 及 atomic rename 寫入。Rollback 必須將 marker 改回 previous active version。SlamCoreWeb startup 可讀 marker 以 reconcile build state，但不得將它當 package metadata。這個 filename 在 Contract 2.0 不承擔兩種格式或責任。

### 8.3 Integrity order

Updater 完成 download 後先計算整個 ZIP SHA-256。Mismatch 時不得解壓、staging 或 mutation active state。SHA 成功後才安全解壓/validate `.slamcore-package.json`。2.0 仍不要求 TLS、authentication 或 package signature。

## 9. Contract 2.0 acceptance cases

1. Artifact SHA mismatch 在 extraction/activation 前到 `failed`，active link、marker 與 workspace state 不變。
2. `.slamcore-package.json` 缺漏、strict schema invalid、version/platform/contract/minimum Updater incompatible，在 activation 前回 `INCOMPATIBLE_RELEASE`。
3. 正常 update 依第 6 節路徑 activation，SlamCoreWeb startup 自行 reconcile，健康後 `completed`。
4. 新 managed runtime 在 60 分鐘內未健康：`rolling_back`，previous link/marker/runtime 健康後 `rolled_back`。
5. active-link mutation 前 crash 依第 7 節恢復且舊 release 保持 active。
6. active-link mutation 後、durable checkpoint 前 crash 不會把 journal 當 filesystem truth，最後完成或 rollback 一致 pair。
7. marker commit 後 crash 從 restart/health checking 恢復，失敗時 marker/link 一起 rollback。
8. update 與 rollback 前後 `.slamcore_build_manifest.json` bytes、metadata 與 existence 不被 Updater 改變/刪除。
9. stale Build Manager state 由 SlamCoreWeb startup 依 active release 自行 reconcile，不形成 Updater public `building` state。
10. 任意未知未來 `.slamcore_build_manifest.json` schema/content 不會造成 Updater rejection。
11. unrelated workspace-level files/directories 在 deployment、cleanup 與 rollback 前後保持不變。
12. idempotent retry、Agent restart recovery、Server offline result replay 維持正確。
13. Update command 在新版 `/command` endpoint 具 `commandType=update`，且既有 `/update` endpoint 保持合法、update-only。
14. Explicit rollback command 以獨立 `R` 引用 successful update `U`；Agent 在任何 mutation 前 durable 保存兩者，Updater request 使用 `jobId=U` 與 `rollback:U`。
15. Rollback command 缺少 `originalUpdateJobId`、含 package/target fields 或使用未知 `commandType` 必須在 Updater mutation 前拒絕。
16. Agent restart、Server retry、Updater restart 與 accepted-response loss 均不會改變 `R` 或 `U`，也不會建立第二個 physical rollback。
17. Explicit rollback terminal `rolled_back` 對 Server command `R` 映射為成功，device version 使用 Updater 回報、由 `U` journal 推導的 previous release。
18. 首次 Updater submission 前過期的 `R` 不會造成 mutation；已 submit 或 response-loss 中的 `R` 即使跨過 expiry，仍以同一 `R`、`U` 恢復到 terminal。

## 10. 1.x → 2.0 migration

1. Contract repository consumer pin 升至 reviewed 2.0 commit/tag；Server、Agent、Updater 一起改用 runtime `2.0`，不可混用 public states。
2. Release producer 停止建立 ZIP-root `.slamcore_release` KEY=VALUE 與 contract build manifest；在 single product root 加入 `.slamcore-package.json` format 2。
3. Updater 移除 `building`、manifest parser/build invocation/45-minute Build timeout；加入 60-minute startup/health convergence、preservation tests 與 crash-boundary recovery。
4. 既有 workspace `.slamcore_release` 若是 plain SemVer line，保留為 active marker；若曾是 1.x KEY=VALUE package metadata，必須在首次 2.0 activation **前由明確的一次性 operator migration** 轉為 active SemVer marker。Updater 2.0 不把兩種格式猜測為同一責任。
5. SlamCoreWeb startup 讀 active marker並自行 reconcile `.slamcore_build_manifest.json`；其 internal schema 可獨立演進。
6. 1.x in-flight jobs 必須在升級前完成/終止；2.0 不接受或恢復含 `building` 的 1.x public journal 為 2.0 job。

## 11. 2.0.1 → 2.1.0 explicit rollback rollout

1. 既有 `/devices/{deviceId}/update` 保持 update-only；舊 Agent 可繼續正常 update，不會收到 rollback。
2. Server 先加入 discriminated command persistence 與 `/devices/{deviceId}/command`，但在相容 Agent 部署前不得啟用 rollback command creation。
3. Agent 升級後只從 `/command` 接收新 command，依 discriminator 分支並 fail closed；SQLite 必須 durable 保存 `R` 與 `U`。
4. Updater wire API 無需改變；Agent 依既有 `POST /rollback` schema 映射 `R → U`。
5. 所有 consumer pin reviewed `2.1.0` commit 後，才可啟用 Server explicit rollback product path 與 Jetson HIL。

## 12. 後續範圍

Authentication、HTTPS、certificate、package signature、rollout waves、pause/cancel、message queue 仍不在 2.0。產品實作只能在本 contract 合併後各自升級；本 repository 不包含任何 runtime implementation。

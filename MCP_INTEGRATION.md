# MCP 接入说明 / `mcd-memory-archive`

## MCP Server

- 名称：`mcd-mcp`
- 接入地址：`https://mcp.mcd.cn`
- 协议：Streamable HTTP（JSON-RPC 直连：`initialize` → `tools/list` → `tools/call`）
- 鉴权：`Authorization: Bearer ${MCD_MCP_TOKEN}`（Token 通过环境变量注入，禁止硬编码）
- 服务端无状态：`initialize` 响应不下发 `mcp-session-id`
- 限流：单 Token 每分钟 600 次请求

## 使用的工具

| 工具 | 用途 | 入参 | 官方跨度与契约 |
|---|---|---|---|
| `query-my-account` | 积分账户 | 无 | 账户快照（非时间序列）。返回 `availablePoint` / `accumulativePoint`（历史累计获得）/ `usedPoint` / `expiredPoint` / `frozenPoint` / `currentMouthExpirePoint` / `lastMouthExpirePoint` / `nextMouthExpirePoint`，均为数字字符串。官方文档 4.5.1 |
| `order-list` | 点餐历史订单 | **无入参** | 官方 4.2.14 明文「历史订单较多时，仅返回最近 10 笔」；无日期筛选、无分页。返回 `data.list[]{orderId, orderType, createTime, beType, beCode, storeCode, storeName, orderStatus, orderProductList[]{productCode, productName, quantity, comboItemList[]}, realTotalAmount}` |
| `mall-order-list` | 麦麦商城订单 | `lastId`(Long)、`size`(Integer, ≤10) | 官方明文**近一年**；`data` 是数组包页对象 `data[0]={hasNext, lastId, list}`。官方文档 4.5.5 |
| `query-my-prizes` | 我的奖品 | `pageNum`(默认1)、`pageSize`(默认10，**最大20**) | 全部奖品记录，不限活动，按 `recordTime` 倒序。返回 `prizes[]{id, name, imageUrl, prizeType, prizeTypeText, recordTime, status, statusText, timeRemindText, sourceDesc, couponInfo{couponCode, couponId}}`。官方文档 4.3.4 |
| `now-time-info` | 服务器当前时间 | 无 | 返回 `timestamp` / `datetime` / `formatted` / `date` / `year` / `month` / `day` / `dayOfWeek` / `timezone` / `offset` / `utc`。官方文档 4.6.1 |

全部为只读工具，不涉及 `create-order` / `party-order-create` / `mall-create-order` 等任何写操作。

## 调用流程

```
now-time-info()        → 取官方服务器时间，作为档案时间基准
        ↓
query-my-account()     → 积分生命周期（累计 / 已用 / 已过期 / 可用 / 冻结）+ 闭合校验
order-list()           → 点餐订单（最多 10 笔，带 createTime）
mall-order-list()      → 商城订单（近一年，游标翻页；返回体无时间字段）
query-my-prizes()      → 奖品记录（全量，带 recordTime，pageSize 上限 20 翻页）
        ↓
三态判定（ok / empty / error）→ 脱敏 → 归一化
        ↓
build_report.py → 单文件 HTML 档案册
```

任一源失败不影响其它源，均独立记录 `status` / `code` / `message` / `traceId`。

## 实测契约（2026-10-12 live 校验 + 官方文档核对）

- 响应同时带 `content[].text` 与 `structuredContent`，**优先取 `structuredContent`**（规整 `{success, code, message, datetime, traceId, data}`）。
- **`isError` 恒为 `false`**：业务失败藏在 `structuredContent.success=false` + `code`/`message`。必须先校验 `success`。
- Token 无效 → **HTTP 401 + 纯文本响应体**（非 JSON），需单独分支，不可按 JSON 解析。
- `order-list` 空态返回 `data = {}`（连 `list` 键都没有），与"接口失败"必须区分开。
- `query-my-prizes` 的 `pageSize` 传 30 / 50 会被服务端归一化回 20，上限确为 20。
- `query-my-account` 返回含官方文档未列的 `accountId`（账户唯一标识），一律脱敏不输出。
- `query-my-prizes` 返回含 `couponInfo.couponCode` / `couponInfo.couponId`（真实券码，等同支付凭证），一律脱敏不输出。

## 业务价值

麦当劳 MCP 的账户类工具各自只覆盖一段数据且口径不一：点餐订单只有最近 10 笔、商城订单近一年但无时间字段、奖品全量却分散在分页里、积分只有快照没有流水。用户想了解自己在麦当劳留下的痕迹，需要自己挨个调接口再拼装。

本 Skill 的核心价值是把这些分散的真实数据**收敛成一个面向个人的、可直接阅读与分享的档案册**，并在产出里明确标注每个源的官方覆盖跨度与真实状态（有记录 / 暂无记录 / 接口故障），而不是让用户自己猜接口返回意味着什么。

## 速率与合规

- 单 Token 每分钟上限 600 次请求；分页抓取时每次请求间隔 0.15 秒，保持温和限速。
- 不输出真实 Token、账户标识与券码；配置文件仅用环境变量占位符。
- 餐品、价格、供应状态与账户数据一律以官方实时结果为准。
- 本项目只读，**不调用任何下单接口**，绝不代操作支付。

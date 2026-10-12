# 更新日志 / Changelog

## v1.0.0 — 2026-10-12

首个正式版本。基于有效 Token 完成麦当劳 MCP 真实联调（initialize → tools/list → 五个目标工具
tools/call），并依据官方文档（4.2.14 / 4.3.4 / 4.5.1 / 4.5.5 / 4.6.1）与 live 返回重写全部字段口径与判定规则。

### 定位调整（重要）

项目原构想为「童年回忆档案馆」。真实联调后确认麦当劳 MCP **不具备任何历史回溯能力**：

- `order-list` 无入参、无日期筛选、无分页，官方 4.2.14 明文「历史订单较多时，仅返回最近 10 笔」；
- `campaign-calendar` 传入历史日期仍返回当天，更早日期 `dailyList` 为空；
- 不存在任何「产品迭代史 / 玩具年代」数据源。

因此主动收缩叙事为「麦麦档案局 · 你的麦门真实档案」：官方接口能覆盖多久，档案就覆盖多久，
并把每个源的官方跨度直接印在产出里。宁可范围小，也不编造。

### 新增

- `scripts/mcd_mcp_client.py`：MCP Streamable HTTP 客户端（仅标准库，零依赖）。
  支持 `ping` / `tools-list` / `call` / `now-time` / `fetch-account` / `fetch-orders` /
  `fetch-mall-orders` / `fetch-prizes` / `fetch-all`；优先读取 `structuredContent`，
  网络与 5xx 自动重试，401/429 明确提示；Token 优先级 `--token` > 环境变量 > `.env`。
  内置**三态判定**（`ok` / `empty` / `error`）与**脱敏层**。
- `scripts/build_report.py`：单文件 HTML 档案册生成器（内联样式与脚本、零外部依赖、
  全量 HTML 转义防 XSS）。五个模块：积分生命周期（含闭合校验）/ 数据源状态 /
  档案时间轴 / 商城订单栏 / 档案小结。
- `scripts/selftest.py`：75 项离线自检（脱敏 / 三态 / 闭合校验 / 时间解析 / 排序 /
  统计 / HTML 渲染 / XSS / 空输入边界），不消耗 MCP 配额。
- `examples/`：真实抓取快照 `archive_live.json`（含官方 `traceId`）、真实档案册
  `archive_live.html`、样例档案册 `demo_archive.html`（带水印）。

### 关键实现约定

- **三态严格区分**：接口成功但无记录（`empty`）绝不等同于接口故障（`error`）。
  `order-list` 空态返回 `data={}`（连 `list` 键都没有），与 `success=false` 分开呈现。
- **脱敏硬约束**：`accountId`、`couponInfo.couponCode`、`couponInfo.couponId` 永不输出
  （含日志与调试）；`orderId` 仅保留后四位。
- **积分闭合校验**：累计获得 ?= 已使用 + 已过期 + 可用 + 冻结。相等标「账目自洽」，
  不等则标差额并说明来自接口未披露的其它调整——该等式并非恒成立，故只呈现校验结果，不硬断言。
- **不虚构**：官方接口没有的历史一律不做，也不靠叙事暗示。

### live 实测结论（2026-10-12）

| 源 | 结果 |
|---|---|
| `now-time-info` | ok，返回官方服务器时间 2026-10-12 13:39:40（GMT+08:00） |
| `query-my-account` | ok，可用 13.9 / 累计 113.7 / 已用 0 / 已过期 99.8 / 冻结 0，闭合校验通过 |
| `order-list` | empty，0 条（已向官方接口核对，非故障） |
| `mall-order-list` | empty，0 条 |
| `query-my-prizes` | empty，0 条 |

- `query-my-prizes` 的 `pageSize` 传 30 / 50 均被服务端归一化回 20，**上限确为 20**
  （与官方 4.3.4 一致；此前记录的「最大 50」为过时结论，已作废）。
- 无效 Token 触发 HTTP 401，被正确判定为 `error`，未误判为 `empty`。
- `tools/list` 共 35 个工具，五个目标工具全部存在。
- 全部为只读调用，未调用任何下单 / 支付 / 领券 / 抽奖工具。

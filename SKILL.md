---
name: mcd-memory-archive
description: 麦当劳「麦麦档案局」Skill。把你自己账户在麦当劳 MCP 里的真实记录——积分生命周期、点餐订单、商城订单、抽奖奖品——整理成一份可分享的单文件 HTML 档案册。适用于"整理我的麦当劳记录""我这些年攒了多少积分""我的麦门档案""查查我的点单历史"等需求。注意：档案只覆盖官方接口真实能提供的跨度，不做任何年代追溯与内容虚构。
---

# 麦麦档案局 / McMemoryArchive

每个人和麦当劳都有一段记录。本 Skill 把散落在多个 MCP 工具里的真实账户数据，收敛成一份**可分享的单文件 HTML 档案册**：积分生命周期、点餐订单、商城订单、抽奖奖品。

## 何时使用

- 用户说：整理我的麦当劳记录、我这些年攒了多少积分、我的麦门档案、查查我的点单历史、我的中奖记录
- 用户想回望自己在麦当劳留下的真实痕迹

## 前置条件

- 需要麦当劳中国 MCP Token：https://open.mcd.cn/mcp
- 配置 `mcd-mcp`（见 `mcp-config.example.json`，Token 用环境变量 `MCD_MCP_TOKEN` 占位，禁止硬编码）
- 无 Token 时可用 `--demo` 内置样例跑通演示流程，页内会打样例水印

## 核心原则

1. **只用自己的真实数据**：全部来自用户本人账户的官方接口返回，不编不猜不补。
2. **能力边界写死在明面上**：官方接口能覆盖多久，档案就覆盖多久；覆盖不到的地方明确说明，不用叙事去掩盖。
3. **三态严格区分**：接口成功但无记录 ≠ 接口故障，两者在输出里显示不同标识。
4. **隐私克制**：账户标识与券码永不输出，订单号只保留后四位。

## 标准工作流

### 第 1 步：抓齐四源 + 官方时钟

```
now-time-info()       → 官方服务器时间（文档 4.6.1），作为档案时间基准
query-my-account()    → 积分生命周期（文档 4.5.1）
order-list()          → 点餐历史订单（文档 4.2.14）
mall-order-list()     → 商城订单，近一年（文档 4.5.5）
query-my-prizes()     → 全部奖品记录，按中奖时间倒序（文档 4.3.4）
```

一次执行：`python scripts/mcd_mcp_client.py fetch-all --out examples/archive_live.json`

### 第 2 步：核对每个源的官方跨度

每个源的覆盖能力不同，**必须在输出里如实标注**：

| 源 | 官方跨度 | 契约出处 |
|---|---|---|
| `order-list` | 近期；官方明文「历史订单较多时，仅返回最近 10 笔」，无日期筛选、无分页 | 官方文档 4.2.14 |
| `mall-order-list` | 近一年；游标分页 `lastId`+`size`(≤10) | 官方文档 4.5.5 |
| `query-my-prizes` | 全部奖品记录，不限活动；`pageSize` 默认 10、**最大 20** | 官方文档 4.3.4 |
| `query-my-account` | 账户快照（非时间序列），含累计/已用/已过期/可用/冻结积分 | 官方文档 4.5.1 |

### 第 3 步：判定三态

- `ok`：接口成功且有记录 → 正常渲染
- `empty`：接口成功但无记录（如 `order-list` 返回 `success:true, data:{}`）→ 显示「已向官方接口核对，该源暂无记录」并附 `traceId`
- `error`：接口失败 / 网络失败 / Token 失效（HTTP 401）→ 显示 `code` 与 `message`，**绝不伪装成空**

> ⚠️ `isError` 恒为 `false`，业务失败藏在 `structuredContent.success=false`。只看 `isError` 会把失败当成功。

### 第 4 步：生成档案册

```
python scripts/build_report.py --input examples/archive_live.json --out examples/archive_live.html
python scripts/build_report.py --demo --out examples/demo_archive.html   # 样例，带水印
```

产出五个模块：积分生命周期（含闭合校验）→ 数据源状态 → 档案时间轴 → 商城订单栏 → 档案小结。

### 第 5 步：自检（可选）

```
python scripts/selftest.py    # 75 项离线自检，不消耗 MCP 配额
```

## 积分闭合校验

累计获得 ?= 已使用 + 已过期 + 可用 + 冻结。

- 相等 → 标注「账目自洽」
- 不等 → 标注差额，并说明「差额来自接口未披露的其它调整，不做推测」

**该等式并非恒成立**（官方示例 141760.94 ≠ 115474.14+0+7592+30），因此只呈现校验结果，不硬断言。

## 输出要求

- 必须基于真实接口返回，不得虚构任何记录。
- 每次输出含：非官方产品声明、数据以官方实时为准、已脱敏声明。
- 每个源标注官方时间跨度。

## 硬约束

- **不虚构**：官方接口没有的历史（产品迭代史、玩具年代、"童年/这些年"这类年代跨度）一律不做，也不靠叙事暗示。
- **不泄露**：`accountId`、`couponInfo.couponCode`、`couponInfo.couponId` 永不输出（含日志与调试）；`orderId` 仅显示后四位。
- **不混淆**：真实为空与接口故障必须分开呈现。
- **不跨品牌对比**。
- **不代操作**：本 Skill 只读，不调用任何下单接口。
- 单 Token 每分钟不超过 600 次请求。

## 文件说明

| 文件 | 作用 |
|---|---|
| `SKILL.md` | 本工作流定义 |
| `MCP_INTEGRATION.md` | MCP 接入说明（工具、调用流程、业务价值） |
| `README.md` | 项目介绍、安装配置、使用示例、目标用户 |
| `CONTEST_DECLARATION.md` | 参赛声明（官方文件，文件名与内容均不可改） |
| `mcp-config.example.json` | 配置示例（仅环境变量占位符） |
| `workbuddy.md` | WorkBuddy 开发上下文 |
| `references/mcp-tools.md` | 麦当劳 MCP 工具清单 |
| `scripts/mcd_mcp_client.py` | MCP Streamable HTTP 客户端（纯标准库，零依赖） |
| `scripts/build_report.py` | 单文件 HTML 档案册生成器 |
| `scripts/selftest.py` | 离线自检（75 项） |
| `examples/` | 真实响应快照与样例产出 |

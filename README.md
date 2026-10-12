# 麦麦档案局 / `mcd-memory-archive`

> 麦当劳程序员创意开发大赛参赛作品 · v1.0.0 · 已通过麦当劳 MCP 真实联调

把你自己在麦当劳留下的真实记录——积分生命周期、点餐订单、商城订单、抽奖奖品——整理成一份可分享的单文件 HTML 档案册。

## 一、项目介绍

麦当劳 MCP 提供了多个账户级工具，但它们各自只覆盖一段数据，且口径不一：点餐订单只有最近 10 笔，商城订单覆盖近一年，奖品是全量但分散在分页里，积分只有快照没有流水。用户想"看看我在麦当劳留下了什么"，得自己挨个调接口再拼。

本项目把这四源收敛成一份**档案册**：

- **积分生命周期**：累计获得 / 已使用 / 已过期 / 可用 / 冻结，配堆叠条，并做闭合校验
- **数据源状态**：每个源是"有记录""暂无记录"还是"接口故障"，一眼分清
- **档案时间轴**：点餐订单与奖品按时间倒序合并
- **商城订单栏**：该接口不返回下单时间，单独成栏，不参与排序
- **档案小结**：最早/最近记录、覆盖天数、各源条数

### 为什么不做"童年回忆 / 时光机"

最初构想是做「童年回忆档案馆」。真实联调后确认：**麦当劳 MCP 没有任何历史回溯能力**——

- `order-list` 无需入参、无日期筛选、无分页，官方明文「历史订单较多时，仅返回最近 10 笔」
- `campaign-calendar` 传入历史日期仍返回当天，更早日期返回空
- 不存在任何"产品迭代史 / 玩具年代"数据源

因此本项目**主动收缩叙事**：官方接口能覆盖多久，档案就覆盖多久，并把每个源的官方跨度直接印在产出里。宁可范围小，也不编造。

## 二、目标用户

- 想回看自己在麦当劳真实消费与积攒轨迹的普通会员
- 关注积分去向（尤其是已过期积分）的麦麦商城 / 麦享会用户
- 需要一眼分清"我没数据"和"接口坏了"的开发者

## 三、安装与配置

1. 申请麦当劳中国 MCP Token：https://open.mcd.cn/mcp
2. 在 MCP Client 中配置 `mcd-mcp`（参考 `mcp-config.example.json`，Token 用环境变量 `MCD_MCP_TOKEN` 占位，禁止硬编码）

```json
{
  "mcpServers": {
    "mcd-mcp": {
      "type": "streamablehttp",
      "url": "https://mcp.mcd.cn",
      "headers": {
        "Authorization": "Bearer ${MCD_MCP_TOKEN}"
      }
    }
  }
}
```

3. 无 Token 时可用内置样例跑通演示流程（页内打样例水印）。

## 四、使用示例

**用户**：帮我整理我在麦当劳的记录

**助手**：抓取你账户的四类真实数据，生成一份档案册——积分攒了多少、过期了多少、点过哪些单、中过什么奖，并标明每个源官方能覆盖到多久。

### 命令行

```bash
# 1) 一次抓齐四源 + 官方时钟（真实调用，输出含官方 traceId）
python scripts/mcd_mcp_client.py fetch-all --out examples/archive_live.json

# 2) 生成档案册
python scripts/build_report.py --input examples/archive_live.json --out examples/archive_live.html

# 3) 无 Token 时用样例演示（页内打「样例数据 · 非本人真实数据」水印）
python scripts/build_report.py --demo --out examples/demo_archive.html

# 4) 离线自检（75 项，不消耗 MCP 配额）
python scripts/selftest.py
```

Token 读取优先级：`--token` > 环境变量 `MCD_MCP_TOKEN` > `.env` 文件。`.env` 已在 `.gitignore` 中排除。

### 单源调试

```bash
python scripts/mcd_mcp_client.py fetch-account
python scripts/mcd_mcp_client.py fetch-orders
python scripts/mcd_mcp_client.py fetch-mall-orders
python scripts/mcd_mcp_client.py fetch-prizes
python scripts/mcd_mcp_client.py now-time
python scripts/mcd_mcp_client.py tools-list --out examples/tools_list.json
```

## 五、使用的麦当劳 MCP 工具

| 工具 | 用途 | 官方跨度 |
|---|---|---|
| `query-my-account` | 积分账户（累计/已用/已过期/可用/冻结） | 账户快照，非时间序列 |
| `order-list` | 点餐历史订单 | 近期，官方明文仅最近 10 笔 |
| `mall-order-list` | 麦麦商城订单 | 近一年，游标分页 |
| `query-my-prizes` | 积分抽奖获得的奖品 | 全部记录，按中奖时间倒序 |
| `now-time-info` | 服务器当前时间 | 档案时间基准 |

全部为只读工具，**不调用任何下单接口**。

## 六、三态判定（本项目最核心的正确性约定）

| 状态 | 判定条件 | 页面呈现 |
|---|---|---|
| `ok` | `success=true` 且有记录 | 正常渲染 |
| `empty` | `success=true` 但列表为空（如 `data={}`） | 「已向官方接口核对，该源暂无记录」+ `traceId` |
| `error` | `success=false` / 网络失败 / HTTP 401 | 红色故障卡，显示 `code` 与 `message` |

> 注意 `isError` 恒为 `false`，业务失败藏在 `structuredContent.success=false`。只看 `isError` 会把失败当成功。

## 七、合规与隐私

- 仅基于用户本人账户数据，不输出个人信息。
- `accountId`、`couponInfo.couponCode`、`couponInfo.couponId` **永不输出**（含日志与调试）。
- 订单号仅显示后四位。
- 不跨品牌对比，不代操作支付，不调用任何下单接口。
- 餐品、价格、供应状态与账户数据一律以麦当劳官方渠道实时结果为准。

## 八、项目结构

```
mcd-memory-archive/
├── SKILL.md                     工作流定义
├── README.md                    本文件
├── MCP_INTEGRATION.md           MCP 接入说明
├── CONTEST_DECLARATION.md       参赛声明（官方文件，内容不可改）
├── mcp-config.example.json      配置示例（仅环境变量占位符）
├── workbuddy.md                 WorkBuddy 开发上下文
├── CHANGELOG.md                 更新日志
├── LICENSE                      MIT
├── references/mcp-tools.md      麦当劳 MCP 工具清单
├── scripts/
│   ├── mcd_mcp_client.py        MCP 客户端（纯标准库，零依赖）
│   ├── build_report.py          单文件 HTML 档案册生成器
│   └── selftest.py              离线自检（75 项）
└── examples/
    ├── archive_live.json        真实账户抓取快照（含官方 traceId）
    ├── archive_live.html        真实账户档案册
    └── demo_archive.html        样例档案册（带水印）
```

## 九、真实调用证据

`examples/archive_live.json` 是 2026-10-12 使用有效 Token 对 `https://mcp.mcd.cn` 的真实抓取快照，五个源全部 `success=true / code=200`，并保留官方返回的 `traceId` 与服务端时间，可直接核验。

## 声明

参赛项目为麦当劳程序员创意开发大赛参赛作品，由参赛者独立开发，非麦当劳官方产品。输出仅供参考，餐品信息、价格、供应状态及账户数据一律以麦当劳官方渠道实时结果为准。

# workbuddy.md

> 本文件为使用腾讯 WorkBuddy 开发本项目的对话上下文记录，用于核验 WorkBuddy 专项奖励条件。
> 由 WorkBuddy 会话上下文整理而成。

## 项目

- 名称：麦麦档案局（mcd-memory-archive）
- 定位：基于麦当劳中国官方 MCP 的个人真实档案 Skill（积分生命周期 × 点餐订单 × 商城订单 × 抽奖奖品）
- 开发环境：腾讯 WorkBuddy（Agent 模式）
- 联调日期：2026-10-12（**全部工具均用有效 Token 完成真实调用**）

---

## 一、需求起点

用户提出：分析已有项目 `mcd-memory-archive`（原「童年回忆档案馆」），要求——
1. 使用麦当劳 MCP 真实调测，确认功能真实可用且无故障；
2. 完整检查功能、模拟测试确认可用，排查并解决功能与安全隐患，把旧配置更新到最新适配版本；
3. 推送发布到 GitHub 新建仓库，带版本号发布正式 release，并严格按官方要求提交报名。

用户明确约束：**禁止猜测，禁止使用过时落后被淘汰的旧配置，必须是真实有效的配置，
必须在麦当劳参考文档与 MCP 开发指导中真实查询到**。

## 二、调研过程（WorkBuddy 完成）

1. **发现地基问题**：live 调用 `order-list`，返回 `success:true / code:200 / data:{}`——
   空数据。进一步取 `tools/list` 的入参 schema，确认 `order-list` **无任何入参**
   （`properties` 为空、`required` 为 None），无法按日期查历史、无分页。
2. **核对官方文档**（https://open.mcd.cn/mcp/doc），拿到决定性的硬约束：
   - `order-list`（4.2.14）：无需入参，「历史订单较多时，**仅返回最近 10 笔订单**」；
   - `mall-order-list`（4.5.5）：官方明文**近一年**，游标分页 `lastId` + `size`(≤10)；
   - `query-my-prizes`（4.3.4）：全部奖品记录，按 `recordTime` 倒序，`pageSize` 默认 10、**最大 20**；
   - `query-my-account`（4.5.1）：账户快照，`accumulativePoint` 为历史累计获得，另有
     `usedPoint` / `expiredPoint` / `availablePoint` / `frozenPoint`；
   - `now-time-info`（4.6.1）：服务器当前时间。
3. **验证活动日历能否回溯**：`campaign-calendar` 传 `specifiedDate=2026-09-15` 仍返回今天
   （2026-10-12），传 2026-01-01 / 2025-06-01 返回 `dailyList` 为 0 天 → **不可回溯**。
4. **结论**：麦当劳 MCP 无任何历史回溯能力，「童年 / 考古 / 时光机 / 年鉴」类叙事无数据支撑。

## 三、 grill-me 决策树（WorkBuddy 驱动，逐分支收敛）

列出 6 个决策分支，按依赖顺序逐一定案：

| 分支 | 决策 |
|---|---|
| 1 数据源根基 | **A 收缩叙事边界**——不弃坑，但去掉无数据支撑的「童年」叙事，边界写死在 SKILL.md |
| 1.2 数据源组合 | **A 四源全上 + 视角差异化**——与已发布的 `mcd-asset-board` 靠视角而非数据源区隔：asset-board 出「待办清单」防过期，本项目只出「回望档案卡片」，不输出任何行动项 |
| 1.3 空态处理 | **A 三态区分 + 样例隔离**——真实为空 / 接口失败 / `--demo` 样例三者绝不可混同 |
| 1.4 命名 | **A 只换中文名**——repo 保留 `mcd-memory-archive`，中文名改「麦麦档案局」 |
| 5 脱敏级别 | **A 严格脱敏**——`accountId` 与 `couponCode`/`couponId` 永不输出，订单号仅后四位 |
| 4 交付形态 | **A 分层档案册**——积分生命周期 + 合并时间轴 + 档案小结 |
| 6 发布节奏 | **A v1.0.0 直发 + 响应快照举证**——真实响应 JSON（含 traceId）归档进 `examples/` |

## 四、实现与验证（WorkBuddy 完成）

- `scripts/mcd_mcp_client.py`：纯标准库 MCP 客户端，内置三态判定与脱敏层。
- `scripts/build_report.py`：单文件 HTML 生成器，内联 CSS/JS，零外部依赖，全量 HTML 转义。
- `scripts/selftest.py`：**75 项离线自检全部通过**（脱敏 6 / 数值 5 / 三态 11 /
  积分生命周期 13 / 奖品脱敏 7 / 时间轴 11 / HTML 渲染 14 / 空输入边界 8）。
- live `fetch-all`：clock 与 account 为 `ok`，orders / mall_orders / prizes 为 `empty`，
  积分闭合校验通过（113.7 = 0 + 99.8 + 13.9 + 0）。
- 脱敏复检：产出 JSON / HTML 中 `accountId`、`couponCode`、`couponId` 及真实值全部 clean。
- XSS 验证：注入 `<script>alert(1)</script>` 被完整转义为 HTML 实体。

## 五、修正的过时结论

- `query-my-prizes` 每页上限：项目旧记忆记为「最大 50」，**live 实测传 30 / 50 均被服务端
  归一化回 20**，与官方 4.3.4 一致 → 旧结论作废，代码按 20 实现并写入文档。

## 六、合规与发布

- 仓库内不含真实 Token：`.env` 已 `.gitignore`，示例仅 `${MCD_MCP_TOKEN}` 占位；提交前全仓复核。
- 未调用任何下单 / 支付 / 抽奖 / 领券工具（本项目全部为只读工具）。
- `CONTEST_DECLARATION.md` 使用官方原文（已转为 LF 行尾，与官方字节级一致），内容未作任何改动。
- 发布 v1.0.0 Release，并按官方格式提交报名 Issue。

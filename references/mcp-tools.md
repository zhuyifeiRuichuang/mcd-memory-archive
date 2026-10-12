# 麦当劳 MCP 工具清单（参考）

> 来源：https://github.com/M-China/mcd-mcp-server  ·  接入地址 `https://mcp.mcd.cn`  ·  协议 Streamable HTTP
>
> 说明：本清单取自官方 README 的 4.1 工具列表。其中 `query-partystore-date` / `query-partystore-session`
> 两项为官方文档笔误，**真实工具名含连字符**（`query-party-store-date` / `query-party-store-session`），
> 已按 live `tools/list` 实测校正。另官方列表未载 `query-promotions`（团餐促销）与
> `query-survey-coupon`（订单满意度答卷），实测 `tools/list` 共 35 个工具。

- `list-nutrition-foods`：餐品营养信息列表：能量、蛋白质、脂肪、碳水、钠、钙等营养成分。
- `delivery-query-addresses`：获取用户可配送地址列表。
- `delivery-create-address`：新增配送地址。
- `delivery-query-stores`：查询收货地址附近可配送门店。
- `query-meal-assistance`：查询企业团餐门店支持的助餐服务。
- `query-nearby-stores`：查询地址附近的麦当劳餐厅（到店/得来速）。
- `query-store-coupons`：查询用户当前门店下可用的优惠券列表。
- `query-meals`：查询当前门店可售卖的餐品菜单（分类、编码、标签、价格）。
- `query-meal-detail`：查询餐品详情/套餐组成，查看包含内容与可替换项。
- `calculate-price`：商品价格计算：商品金额、配送费、优惠金额、应付总价。
- `create-order`：创建订单（到店/外送/得来速），返回订单详情与支付链接。
- `cancel-order`：取消点餐订单。
- `query-order`：查询订单详情（状态、内容、配送信息）。
- `order-list`：查询近期到店/外送历史订单（非商城订单）。
- `campaign-calendar`：查询麦当劳中国当月营销活动日历（进行中/往期/未来）。
- `available-coupons`：麦麦省券列表查询（当前可领取的优惠券）。
- `auto-bind-coupons`：麦麦省一键领券（自动领取当前可用券，需用户同意）。
- `query-my-coupons`：我的优惠券查询（账户下所有可用券）。
- `query-my-account`：我的积分查询（可用/累计/冻结/即将过期积分）。
- `mall-points-products`：查询麦麦商城商品列表（积分兑换或现金购买）。
- `mall-product-detail`：查询麦麦商城商品详情（图片、积分、有效期、说明）。
- `mall-create-order`：积分兑换商品下单（虚拟/实物，积分校验与扣减）。
- `now-time-info`：获取当前时间信息（时间、日期、星期）。
- `query-lottery-info`：查看积分抽奖活动信息（状态、奖品、消耗规则）。
- `draw-lottery`：积分抽奖（消耗积分/次数，返回中奖结果）。
- `query-my-prizes`：查看我的奖品（抽奖获得记录，分页倒序）。
- `mall-order-list`：麦麦商城订单查询（近一年购买/兑换订单）。
- `mall-order-detail`：麦麦商城订单详情（支付积分、金额、状态）。
- `query-party-city`：主题活动城市列表查询（派对/品鉴会）。
- `query-party-store`：主题活动门店列表查询。
- `query-partystore-date`：主题活动可预约日期查询。
- `query-partystore-session`：主题活动可预约日期场次查询。
- `party-order-create`：主题活动订单创建（选定城市/门店/日期/场次后下单）。

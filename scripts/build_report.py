#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""麦麦档案局 · 单文件 HTML 档案册生成器。

输入：scripts/mcd_mcp_client.py fetch-all 产出的档案 JSON（或 --demo 内置样例）。
输出：单文件 HTML（内联 CSS/JS，零外部依赖，可直接分享）。

渲染三态（硬约定，不可混同）：
  ok    —— 正常渲染该源
  empty —— 「已向官方接口核对，该源暂无记录」，附 traceId，绝不说成故障
  error —— 红色故障卡，展示 code/message，绝不伪装成空
  demo  —— 整页加「样例数据 · 非本人真实数据」水印并换配色

脱敏（硬约定）：输入 JSON 已剔除 accountId 与 couponCode/couponId；
本模块对所有文本再做一次 HTML 转义，并在页脚标注「已脱敏」。
"""

import argparse
import datetime as dt
import html
import json
import os
import sys

TITLE = "麦麦档案局"
SUBTITLE = "你的麦门真实档案"


# ------------------------------------------------------ 工具

def esc(value) -> str:
    """HTML 转义，防 XSS。"""
    return html.escape(str(value if value is not None else ""), quote=True)


def parse_time(text: str):
    """解析 "2026-08-20 21:28:52" 形态；失败返回 None。"""
    s = str(text or "").strip()
    if not s:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return dt.datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def fmt_num(value, nd=1) -> str:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return "—"
    if abs(f - round(f)) < 1e-9:
        return str(int(round(f)))
    return ("%%.%df" % nd) % f


# ------------------------------------------------------ 聚合

def build_timeline(sources: dict) -> list:
    """把有时间戳的记录合并成倒序时间轴。商城订单无时间字段，不参与。"""
    events = []
    for key in ("prizes", "orders"):
        block = sources.get(key) or {}
        for item in (block.get("items") or []):
            when = parse_time(item.get("time"))
            if when is None:
                continue
            events.append({"when": when, "kind": key, "item": item})
    events.sort(key=lambda e: e["when"], reverse=True)
    return events


def summarize(sources: dict) -> dict:
    total = 0
    per_source = []
    for key, label in (("orders", "点餐订单"), ("mall_orders", "商城订单"), ("prizes", "我的奖品")):
        block = sources.get(key) or {}
        count = block.get("count")
        if not isinstance(count, int):
            items = block.get("items")
            count = len(items) if isinstance(items, list) else 0
        total += count
        per_source.append({
            "key": key, "label": label, "count": count,
            "status": block.get("status") or "error",
            "span": block.get("official_span") or "",
            "trace_id": block.get("trace_id") or "",
            "server_time": block.get("server_time") or "",
            "message": block.get("message") or "",
            "code": block.get("code"),
        })
    events = build_timeline(sources)
    span_days = None
    earliest = latest = None
    if events:
        latest = events[0]["when"]
        earliest = events[-1]["when"]
        span_days = (latest.date() - earliest.date()).days + 1
    return {
        "total": total,
        "per_source": per_source,
        "timeline_count": len(events),
        "earliest": earliest.strftime("%Y-%m-%d") if earliest else None,
        "latest": latest.strftime("%Y-%m-%d") if latest else None,
        "span_days": span_days,
    }


# ------------------------------------------------------ HTML 片段

def render_points(points: dict) -> str:
    avail = float(points.get("available") or 0)
    used = float(points.get("used") or 0)
    expired = float(points.get("expired") or 0)
    frozen = float(points.get("frozen") or 0)
    accum = float(points.get("accumulative") or 0)
    currency = esc(points.get("currency") or "积分")
    total_bar = max(accum, used + expired + avail + frozen, 1e-9)

    def pct(v):
        return min(100.0, max(0.0, v / total_bar * 100.0))

    closed = bool(points.get("balance_closed"))
    diff = float(points.get("balance_diff") or 0)
    if closed:
        balance_note = "四段相加与累计获得完全吻合，账目自洽。"
    else:
        balance_note = ("四段相加与累计获得相差 %s %s，差额来自接口未披露的其它调整，"
                        "本卡片不做推测。" % (fmt_num(abs(diff)), currency))

    seg = "".join(
        '<div class="seg seg-%s" style="width:%.2f%%" title="%s %s"></div>'
        % (cls, pct(val), label, fmt_num(val))
        for cls, val, label in (("used", used, "已使用"), ("expired", expired, "已过期"),
                                ("avail", avail, "可用"), ("frozen", frozen, "冻结"))
        if val > 0
    ) or '<div class="seg seg-none" style="width:100%"></div>'

    cards = "".join(
        '<div class="pcard"><div class="pcard-num">%s</div>'
        '<div class="pcard-label">%s</div></div>'
        % (fmt_num(val), label)
        for label, val in (("累计获得", accum), ("已使用", used),
                           ("已过期", expired), ("可用", avail), ("冻结", frozen))
    )
    return """
<section class="module">
  <h2>积分生命周期</h2>
  <p class="mod-note">数据来自 <code>query-my-account</code>，官方 4.5.1。为账户当前快照，非时间序列。</p>
  <div class="pcards">%s</div>
  <div class="bar" role="img" aria-label="积分构成堆叠条">%s</div>
  <ul class="legend">
    <li><span class="dot dot-used"></span>已使用 %s</li>
    <li><span class="dot dot-expired"></span>已过期 %s</li>
    <li><span class="dot dot-avail"></span>可用 %s</li>
    <li><span class="dot dot-frozen"></span>冻结 %s</li>
  </ul>
  <p class="balance %s">%s</p>
</section>
""" % (cards, seg, fmt_num(used), fmt_num(expired), fmt_num(avail), fmt_num(frozen),
       "balance-ok" if closed else "balance-warn", esc(balance_note))


def render_source_state(per_source: list) -> str:
    rows = []
    for s in per_source:
        st = s["status"]
        if st == "ok":
            badge, text = "正常", "%d 条" % s["count"]
        elif st == "empty":
            badge, text = "暂无记录", "已向官方接口核对，该源暂无记录"
        else:
            badge, text = "接口异常", "code=%s %s" % (s.get("code"), s.get("message"))
        tid = s.get("trace_id") or ""
        tid_html = ('<div class="trace">traceId %s · 服务端 %s</div>'
                    % (esc(tid[:16]) + "…" if len(tid) > 16 else esc(tid),
                       esc(s.get("server_time")))) if tid else ""
        rows.append(
            '<tr><td class="td-label">%s</td><td><span class="badge badge-%s">%s</span></td>'
            '<td class="td-text">%s%s</td><td class="td-span">%s</td></tr>'
            % (esc(s["label"]), st, badge, esc(text), tid_html, esc(s["span"])))
    return """
<section class="module">
  <h2>数据源状态</h2>
  <p class="mod-note">三态严格区分：接口成功但无记录 ≠ 接口故障。两者在下方显示不同标识。</p>
  <table class="state"><tbody>%s</tbody></table>
</section>
""" % "".join(rows)


def render_timeline(sources: dict) -> str:
    events = build_timeline(sources)
    if not events:
        return """
<section class="module">
  <h2>档案时间轴</h2>
  <div class="emptybox">暂无可排序记录。参与时间轴的源需带时间戳；
  本账户下这些源经官方接口核对后为空，故此处不做任何填充。</div>
</section>
"""
    rows = []
    for e in events:
        item = e["item"]
        if e["kind"] == "orders":
            kind = "点餐"
            title = item.get("store") or "麦当劳门店"
            prod = "".join('<span class="chip">%s ×%s</span>'
                           % (esc(p.get("name")), esc(p.get("quantity")))
                           for p in (item.get("products") or []))
            meta = " ".join(x for x in (item.get("status_text"),
                                        ("实付 ¥%s" % item["amount"]) if item.get("amount") else "",
                                        ("单号 %s" % item["order_ref"]) if item.get("order_ref") else "")
                            if x)
            body = (prod or '<span class="muted">无商品明细</span>') + (
                '<div class="meta">%s</div>' % esc(meta) if meta else "")
        else:
            kind = "奖品"
            title = item.get("name") or "未命名奖品"
            bits = [x for x in (item.get("type_text"), item.get("status_text"), item.get("from")) if x]
            body = ('<span class="chip">%s</span>' % esc(item.get("type_text") or "奖品")
                    if item.get("type_text") else "")
            body += ('<div class="meta">%s</div>' % " · ".join(esc(b) for b in bits) if bits else "")
            if item.get("remind"):
                body += '<div class="meta">%s</div>' % esc(item["remind"])
        rows.append(
            '<li class="tl-item tl-%s">'
            '<div class="tl-when"><span class="tl-date">%s</span>'
            '<span class="tl-time">%s</span></div>'
            '<div class="tl-body"><span class="tl-kind">%s</span>'
            '<div class="tl-title">%s</div>%s</div></li>'
            % (e["kind"], e["when"].strftime("%Y-%m-%d"), e["when"].strftime("%H:%M:%S"),
               kind, esc(title), body))
    return """
<section class="module">
  <h2>档案时间轴</h2>
  <p class="mod-note">按时间倒序合并点餐订单与奖品记录。商城订单接口未提供下单时间字段，单独成栏，不参与排序。</p>
  <ol class="timeline">%s</ol>
</section>
""" % "".join(rows)


def render_mall(sources: dict) -> str:
    block = sources.get("mall_orders") or {}
    items = block.get("items") or []
    if block.get("status") != "ok" or not items:
        if block.get("status") == "empty":
            note = ("已向官方接口核对，近一年内暂无麦麦商城购买或兑换记录。")
        else:
            note = ("接口异常：code=%s %s" % (block.get("code"), block.get("message")))
        return """
<section class="module">
  <h2>麦麦商城订单（近一年）</h2>
  <div class="emptybox">%s</div>
</section>
""" % esc(note)
    cards = []
    for it in items:
        goods = "".join('<span class="chip">%s%s</span>'
                        % (esc(g.get("name") or "商品"),
                           (" ×%s" % esc(g.get("quantity"))) if g.get("quantity") else "")
                        for g in (it.get("goods") or []))
        cards.append('<div class="mcard"><div class="mcard-head">%s · %s</div>%s'
                     '<div class="meta">单号 %s</div></div>'
                     % (esc(it.get("shop") or "麦麦商城"), esc(it.get("status_text") or ""),
                        goods or '<span class="muted">无明细</span>', esc(it.get("order_ref"))))
    return """
<section class="module">
  <h2>麦麦商城订单（近一年）</h2>
  <p class="mod-note">该接口返回体未提供下单时间字段，故单独成栏，不参与上方时间轴排序。</p>
  <div class="mcards">%s</div>
</section>
""" % "".join(cards)


def render_summary(summary: dict, points: dict) -> str:
    if summary["timeline_count"]:
        span = ("最早 %s，最近 %s，覆盖 %d 天" %
                (summary["earliest"], summary["latest"], summary["span_days"]))
    else:
        span = "暂无带时间戳的记录，无法计算跨度"
    return """
<section class="module">
  <h2>档案小结</h2>
  <ul class="summary">
    <li><b>%d</b> 条带时间戳记录</li>
    <li><b>%d</b> 条归档记录合计</li>
    <li><span>%s</span></li>
    <li><span>积分累计获得 %s，已过期 %s（数据来自官方接口）</span></li>
  </ul>
</section>
""" % (summary["timeline_count"], summary["total"], esc(span),
       fmt_num(points.get("accumulative")), fmt_num(points.get("expired")))


# ------------------------------------------------------ 页面

CSS = """
:root{--ink:#1f2328;--ink2:#57606a;--ink3:#8c959f;--line:#d8dee4;
--bg:#ffffff;--soft:#f6f8fa;--accent:#c8102e;--ok:#1a7f37;--warn:#9a6700;--bad:#cf222e}
*{box-sizing:border-box}
body{margin:0;padding:32px 16px 56px;background:#f0f2f5;color:var(--ink);
font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;
line-height:1.6;-webkit-font-smoothing:antialiased}
.wrap{max-width:880px;margin:0 auto}
header{background:var(--bg);border:1px solid var(--line);border-radius:14px;
padding:28px 28px 22px;margin-bottom:18px}
h1{margin:0;font-size:26px;font-weight:600;letter-spacing:-.2px}
.sub{margin:6px 0 0;color:var(--ink2);font-size:14px}
.stamp{margin-top:14px;color:var(--ink3);font-size:12px}
.watermark{margin-top:14px;padding:10px 14px;border-radius:8px;
background:#fff4ce;border:1px solid #d4a72c;color:#7a5b00;font-size:13px;font-weight:600}
.module{background:var(--bg);border:1px solid var(--line);border-radius:14px;
padding:22px 24px;margin-bottom:18px}
h2{margin:0 0 6px;font-size:17px;font-weight:600}
.mod-note{margin:0 0 16px;color:var(--ink3);font-size:12.5px}
.pcards{display:grid;grid-template-columns:repeat(auto-fit,minmax(96px,1fr));gap:10px;margin-bottom:16px}
.pcard{background:var(--soft);border-radius:10px;padding:12px 10px;text-align:center}
.pcard-num{font-size:20px;font-weight:600;font-variant-numeric:tabular-nums}
.pcard-label{font-size:12px;color:var(--ink2);margin-top:2px}
.bar{display:flex;height:14px;border-radius:7px;overflow:hidden;background:#eaeef2}
.seg{height:100%}
.seg-used{background:#8c959f}.seg-expired{background:#cf222e}
.seg-avail{background:#1a7f37}.seg-frozen{background:#bf8700}.seg-none{background:#eaeef2}
.legend{list-style:none;display:flex;flex-wrap:wrap;gap:16px;padding:0;margin:10px 0 0;font-size:12.5px;color:var(--ink2)}
.legend li{display:flex;align-items:center;gap:6px}
.dot{width:9px;height:9px;border-radius:50%;display:inline-block}
.dot-used{background:#8c959f}.dot-expired{background:#cf222e}
.dot-avail{background:#1a7f37}.dot-frozen{background:#bf8700}
.balance{margin:14px 0 0;font-size:12.5px;padding:10px 12px;border-radius:8px}
.balance-ok{background:#eaf6ec;color:#1a5c2b}
.balance-warn{background:#fff8e6;color:#7a5b00}
table.state{width:100%;border-collapse:collapse;font-size:13px}
table.state td{padding:10px 8px;border-top:1px solid var(--line);vertical-align:top}
.td-label{font-weight:600;width:96px;white-space:nowrap}
.td-text{color:var(--ink2)}
.td-span{color:var(--ink3);font-size:12px;width:38%}
.trace{color:var(--ink3);font-size:11.5px;margin-top:3px;font-family:ui-monospace,Consolas,monospace}
.badge{display:inline-block;padding:2px 9px;border-radius:20px;font-size:12px;font-weight:600;white-space:nowrap}
.badge-ok{background:#eaf6ec;color:#1a7f37}
.badge-empty{background:#eef1f4;color:#57606a}
.badge-error{background:#ffebe9;color:#cf222e}
.timeline{list-style:none;padding:0;margin:0}
.tl-item{display:flex;gap:16px;padding:14px 0;border-top:1px solid var(--line)}
.tl-item:first-child{border-top:0}
.tl-when{width:104px;flex:none}
.tl-date{display:block;font-size:13.5px;font-weight:600;font-variant-numeric:tabular-nums}
.tl-time{display:block;font-size:12px;color:var(--ink3);font-variant-numeric:tabular-nums}
.tl-body{flex:1;min-width:0}
.tl-kind{display:inline-block;font-size:11px;font-weight:600;padding:1px 7px;border-radius:5px;margin-bottom:4px}
.tl-orders .tl-kind{background:#fdeaed;color:#c8102e}
.tl-prizes .tl-kind{background:#e7f0fe;color:#1257a8}
.tl-title{font-size:14.5px;font-weight:600;word-break:break-word}
.meta{font-size:12.5px;color:var(--ink2);margin-top:3px}
.chip{display:inline-block;background:var(--soft);border:1px solid var(--line);
border-radius:6px;padding:2px 8px;font-size:12.5px;margin:4px 5px 0 0;color:var(--ink)}
.mcards{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:12px}
.mcard{background:var(--soft);border-radius:10px;padding:14px}
.mcard-head{font-size:13px;font-weight:600;margin-bottom:6px}
.emptybox{background:var(--soft);border-radius:10px;padding:18px;color:var(--ink2);font-size:13.5px}
.muted{color:var(--ink3);font-size:12.5px}
.summary{list-style:none;padding:0;margin:0;font-size:14px}
.summary li{padding:8px 0;border-top:1px solid var(--line)}
.summary li:first-child{border-top:0}
.summary b{font-size:16px;font-variant-numeric:tabular-nums}
footer{max-width:880px;margin:0 auto;color:var(--ink3);font-size:12px;padding:0 4px}
footer p{margin:6px 0}
@media(max-width:600px){.tl-item{flex-direction:column;gap:4px}.tl-when{width:auto}.td-span{display:none}}
"""

JS = """
document.addEventListener('click',function(e){
  var h=e.target.closest('.tl-item');
  if(h){h.classList.toggle('open');}
});
"""


def render(payload: dict, is_demo: bool) -> str:
    sources = payload.get("sources") or {}
    points = ((sources.get("account") or {}).get("points")) or {}
    clock = (sources.get("clock") or {}).get("data") or {}
    summary = summarize(sources)

    stamp_bits = [x for x in (clock.get("formatted"), clock.get("timezone"),
                              ("官方 traceId " + str((sources.get("clock") or {}).get("trace_id"))[:16]
                               if (sources.get("clock") or {}).get("trace_id") else ""))
                  if x]
    wm = ('<div class="watermark">样例数据 · 非本人真实数据 —— 本页由内置样例生成，'
          '用于演示档案册样式，不代表任何真实账户记录。</div>') if is_demo else ""

    body = "".join([
        render_points(points),
        render_source_state(summary["per_source"]),
        render_timeline(sources),
        render_mall(sources),
        render_summary(summary, points),
    ])

    return """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>%s · %s</title>
<style>%s</style>
</head>
<body>
<main class="wrap">
<header>
<h1>%s</h1>
<p class="sub">%s</p>
<p class="stamp">生成时间 %s · 官方服务器时间 %s</p>
%s
</header>
%s
</main>
<footer>
<p>本页由个人开发的参赛 Skill 生成，<b>非麦当劳官方产品</b>。餐品、价格、供应状态与账户数据一律以麦当劳官方渠道实时结果为准。</p>
<p>已脱敏：账户标识（accountId）、券码（couponCode / couponId）不作输出；订单号仅显示后四位。</p>
<p>数据来源：麦当劳中国 MCP（mcp.mcd.cn）—— query-my-account / order-list / mall-order-list / query-my-prizes / now-time-info。</p>
</footer>
<script>%s</script>
</body>
</html>
""" % (esc(TITLE), esc(SUBTITLE), CSS, esc(TITLE), esc(SUBTITLE),
       esc(payload.get("fetched_at") or ""), esc(" / ".join(stamp_bits)),
       wm, body, JS)


# ------------------------------------------------------ 样例

SAMPLE = {
    "fetched_at": "2026-10-12T13:00:00+08:00",
    "mcp_url": "https://mcp.mcd.cn",
    "generator": "mcd-memory-archive/1.0.0 (sample)",
    "sources": {
        "clock": {"status": "ok", "trace_id": "sample0000000000",
                  "server_time": "2026-10-12 13:00:00",
                  "data": {"formatted": "2026-10-12 13:00:00", "timezone": "GMT+08:00"}},
        "account": {"status": "ok", "trace_id": "sample0000000001",
                    "server_time": "2026-10-12 13:00:00",
                    "points": {"available": 7592.0, "accumulative": 141760.94,
                               "used": 115474.14, "expired": 18664.8, "frozen": 30.0,
                               "expire_this_month": 0.0, "expire_last_month": 0.0,
                               "expire_next_month": 0.0, "currency": "麦享会积分",
                               "balance_closed": True, "balance_diff": 0.0}},
        "orders": {"status": "ok", "trace_id": "sample0000000002",
                   "server_time": "2026-10-12 13:00:00", "count": 3,
                   "official_span": "近期（官方 4.2.14：仅返回最近 10 笔）",
                   "items": [
                       {"kind": "meal", "time": "2026-10-08 12:41:03",
                        "store": "麦当劳XX地铁站餐厅", "status_text": "订单已完成",
                        "amount": "40", "order_ref": "****8821",
                        "products": [{"name": "麦香鱼中套餐", "quantity": 1},
                                     {"name": "麦辣鸡翅", "quantity": 1}]},
                       {"kind": "meal", "time": "2026-09-21 08:12:44",
                        "store": "麦当劳XX科技园餐厅", "status_text": "订单已完成",
                        "amount": "15.9", "order_ref": "****4417",
                        "products": [{"name": "吉士蛋麦满分套餐", "quantity": 1}]},
                       {"kind": "meal", "time": "2026-08-30 22:05:19",
                        "store": "麦当劳XX路店", "status_text": "订单已完成",
                        "amount": "26.5", "order_ref": "****2093",
                        "products": [{"name": "双层吉士汉堡", "quantity": 1},
                                     {"name": "可乐中杯", "quantity": 1}]}]},
        "mall_orders": {"status": "ok", "trace_id": "sample0000000003",
                        "server_time": "2026-10-12 13:00:00", "count": 2,
                        "official_span": "近一年",
                        "items": [
                            {"kind": "mall", "time": "", "channel": "麦麦商城",
                             "status_text": "已完成", "shop": "麦麦商城",
                             "order_ref": "****7702",
                             "goods": [{"name": "麦当劳对联名周边盲盒", "spec": "单款", "quantity": 1}]},
                            {"kind": "mall", "time": "", "channel": "麦麦商城",
                             "status_text": "已完成", "shop": "麦麦商城",
                             "order_ref": "****6510",
                             "goods": [{"name": "麦麦省券包", "spec": "月度", "quantity": 1}]}]},
        "prizes": {"status": "ok", "trace_id": "sample0000000004",
                   "server_time": "2026-10-12 13:00:00", "count": 2,
                   "official_span": "全部奖品记录",
                   "items": [
                       {"kind": "prize", "time": "2026-09-02 21:28:52",
                        "name": "一等奖：早餐卡7天", "type_text": "权益卡",
                        "status_text": "已使用", "remind": "可用时间: 2026.09.10-2026.10.09",
                        "from": "奖品来自: 九宫格-dsp3"},
                       {"kind": "prize", "time": "2026-07-14 20:03:11",
                        "name": "参与奖：中薯条兑换券", "type_text": "商品券",
                        "status_text": "已过期", "remind": "可用时间: 2026.07.15-2026.08.14",
                        "from": "奖品来自: 麦麦抽奖-0721"}]},
    },
}


def main() -> int:
    parser = argparse.ArgumentParser(description="麦麦档案局 · 单文件 HTML 档案册生成器")
    parser.add_argument("--input", default="", help="档案 JSON 路径（fetch-all --out 产出）")
    parser.add_argument("--out", default="", help="输出 HTML 路径；缺省打印到标准输出")
    parser.add_argument("--demo", action="store_true", help="使用内置样例（页内打样例水印）")
    args = parser.parse_args()

    if args.demo:
        payload, is_demo = SAMPLE, True
    elif args.input:
        with open(args.input, encoding="utf-8") as fh:
            payload = json.load(fh)
        is_demo = bool(payload.get("is_sample"))
    else:
        print("需要 --input <档案JSON> 或 --demo。", file=sys.stderr)
        return 2

    text = render(payload, is_demo)
    if args.out:
        parent = os.path.dirname(os.path.abspath(args.out))
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(text)
        print("已写入：%s（%d 字节）" % (os.path.abspath(args.out), len(text.encode("utf-8"))))
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())

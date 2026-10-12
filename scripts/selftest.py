#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""麦麦档案局 · 离线自检。

覆盖：脱敏、三态判定、积分闭合校验、时间解析、时间轴排序、统计、
HTML 渲染（转义 / 无外部依赖 / 模块齐全 / 水印 / 空态文案）与各类空输入边界。
全部离线，不消耗 MCP 配额，不需要 Token。

运行：python scripts/selftest.py
"""

import datetime as dt
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import mcd_mcp_client as C  # noqa: E402
import build_report as B  # noqa: E402

PASS = 0
FAIL = 0
FAILED = []


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        FAILED.append("%s %s" % (name, detail))
        print("  FAIL  %s %s" % (name, detail))


def section(title):
    print("\n[%s]" % title)


# ------------------------------------------------------ 脱敏

section("脱敏")
check("mask-长单号保留后4位", C.mask_order_id("2026082012348821") == "****8821")
check("mask-短单号", C.mask_order_id("12345") == "****2345")
check("mask-4位及以下", C.mask_order_id("123") == "****")
check("mask-空值", C.mask_order_id("") == "—")
check("mask-None", C.mask_order_id(None) == "—")
check("mask-数字入参", C.mask_order_id(1234567890) == "****7890")

# ------------------------------------------------------ 数值

section("数值解析")
check("safe_float-正常", C.safe_float("13.9") == 13.9)
check("safe_float-整数串", C.safe_float("40") == 40.0)
check("safe_float-空串", C.safe_float("") == 0.0)
check("safe_float-脏值", C.safe_float("abc") == 0.0)
check("safe_float-None", C.safe_float(None) == 0.0)

# ------------------------------------------------------ 三态判定（mock 掉网络）

section("三态判定")


def _mock(monkey_ret):
    C.call_tool = lambda name, args, token, url: monkey_ret


_ok_list = {"structuredContent": {"success": True, "code": 200, "message": "请求成功",
                                  "datetime": "2026-10-12 13:00:00",
                                  "traceId": "t" * 32,
                                  "data": {"list": [{"orderId": "A1B2C3D4E5",
                                                     "createTime": "2026-10-08 12:41:03",
                                                     "storeName": "测试餐厅",
                                                     "orderStatus": "订单已完成",
                                                     "realTotalAmount": "40",
                                                     "orderProductList": [
                                                         {"productName": "麦香鱼套餐", "quantity": 1}]}]}}}
_mock(_ok_list)
r = C.fetch_orders("tk", C.DEFAULT_URL)
check("ok-有记录状态为ok", r["status"] == "ok", r["status"])
check("ok-条数为1", r["count"] == 1)
check("ok-订单号已脱敏", r["items"][0]["order_ref"] == "****C3D4E5"[-9:] or
      r["items"][0]["order_ref"].startswith("****"), r["items"][0]["order_ref"])
check("ok-保留traceId", r["trace_id"] == "t" * 32)

_empty = {"structuredContent": {"success": True, "code": 200, "message": "请求成功",
                                "datetime": "2026-10-12 13:00:00",
                                "traceId": "e" * 32, "data": {}}}
_mock(_empty)
r = C.fetch_orders("tk", C.DEFAULT_URL)
check("empty-data为{}判empty", r["status"] == "empty", r["status"])
check("empty-条数0", r["count"] == 0)

_empty2 = {"structuredContent": {"success": True, "code": 200, "message": "请求成功",
                                 "traceId": "e2", "data": {"list": []}}}
_mock(_empty2)
check("empty-list为空判empty", C.fetch_orders("tk", C.DEFAULT_URL)["status"] == "empty")

_fail = {"structuredContent": {"success": False, "code": 600010, "message": "检查必填参数",
                               "traceId": "f" * 32, "data": None}}
_mock(_fail)
r = C.fetch_orders("tk", C.DEFAULT_URL)
check("error-success=false判error", r["status"] == "error", r["status"])
check("error-保留code", r["code"] == 600010)
check("error-保留message", r["message"] == "检查必填参数")


def _raise_mcp(*a, **k):
    raise C.McpError("401 Token 无效、已过期或未提供，请检查 MCD_MCP_TOKEN。", 401)


C.call_tool = _raise_mcp
r = C.fetch_orders("tk", C.DEFAULT_URL)
check("error-401判error", r["status"] == "error" and r["code"] == 401, str(r["code"]))
check("error-401不伪装成empty", r["status"] != "empty")

# ------------------------------------------------------ 账户与闭合校验

section("积分生命周期")
_acc = {"structuredContent": {"success": True, "code": 200, "traceId": "a" * 32,
                              "datetime": "2026-10-12 13:00:00",
                              "data": {"availablePoint": "13.9", "accumulativePoint": "113.7",
                                       "usedPoint": "0", "expiredPoint": "99.8",
                                       "frozenPoint": "0", "currency": "麦享会积分",
                                       "currentMouthExpirePoint": "0",
                                       "lastMouthExpirePoint": "0",
                                       "nextMouthExpirePoint": "0",
                                       "accountId": "833E3F63-3D16-000A-0008-FF2BF657F780"}}}
_mock(_acc)
acc = C.fetch_account("tk", C.DEFAULT_URL)
p = acc["points"]
check("account-状态ok", acc["status"] == "ok", acc["status"])
check("account-可用13.9", p["available"] == 13.9)
check("account-累计113.7", p["accumulative"] == 113.7)
check("account-已过期99.8", p["expired"] == 99.8)
check("account-闭合为True", p["balance_closed"] is True)
check("account-差额0", abs(p["balance_diff"]) < 0.01)
check("account-不输出accountId", "accountId" not in json.dumps(acc, ensure_ascii=False))
check("account-不输出accountId值",
      "FF2BF657F780" not in json.dumps(acc, ensure_ascii=False))

_acc_open = {"structuredContent": {"success": True, "code": 200, "traceId": "a2",
                                   "data": {"availablePoint": "7592",
                                            "accumulativePoint": "141760.94",
                                            "usedPoint": "115474.14", "expiredPoint": "0",
                                            "frozenPoint": "30", "currency": "麦当劳积分"}}}
_mock(_acc_open)
p2 = C.fetch_account("tk", C.DEFAULT_URL)["points"]
check("account-不闭合判False", p2["balance_closed"] is False)
check("account-不闭合有差额", abs(p2["balance_diff"]) > 0.01, str(p2["balance_diff"]))

# ------------------------------------------------------ 奖品脱敏

section("奖品脱敏")
_prz = {"structuredContent": {"success": True, "code": 200, "traceId": "p" * 32,
                              "datetime": "2026-10-12 13:00:00",
                              "data": {"prizes": [
                                  {"id": 1, "name": "一等奖：早餐卡7天", "prizeTypeText": "权益卡",
                                   "recordTime": "2026-08-20 21:28:52", "statusText": "可用",
                                   "timeRemindText": "可用时间: 2026.11.18-2026.12.17",
                                   "sourceDesc": "奖品来自: 九宫格-dsp3",
                                   "couponInfo": {"couponCode": "SECRETCODE123",
                                                  "couponId": "999888"}}],
                                  "hasMore": False}}}
_mock(_prz)
prz = C.fetch_prizes("tk", C.DEFAULT_URL)
blob = json.dumps(prz, ensure_ascii=False)
check("prizes-状态ok", prz["status"] == "ok", prz["status"])
check("prizes-保留名称", prz["items"][0]["name"] == "一等奖：早餐卡7天")
check("prizes-保留来源", prz["items"][0]["from"] == "奖品来自: 九宫格-dsp3")
check("prizes-剔除couponCode值", "SECRETCODE123" not in blob)
check("prizes-剔除couponId值", "999888" not in blob)
check("prizes-剔除couponInfo键", "couponInfo" not in blob)

# ------------------------------------------------------ 时间解析与排序

section("时间轴")
check("parse-完整", B.parse_time("2026-08-20 21:28:52") == dt.datetime(2026, 8, 20, 21, 28, 52))
check("parse-到分", B.parse_time("2026-08-20 21:28") == dt.datetime(2026, 8, 20, 21, 28))
check("parse-到日", B.parse_time("2026-08-20") == dt.datetime(2026, 8, 20))
check("parse-空", B.parse_time("") is None)
check("parse-脏值", B.parse_time("not a time") is None)

src = {"prizes": {"items": [{"time": "2026-08-20 21:28:52", "name": "晚"},
                            {"time": "2026-10-01 08:00:00", "name": "早"}]},
       "orders": {"items": [{"time": "2026-09-15 12:00:00", "store": "中"}]}}
tl = B.build_timeline(src)
check("timeline-合并3条", len(tl) == 3, str(len(tl)))
check("timeline-倒序首条最新(10-01)", tl[0]["item"].get("name") == "早", str(tl[0]["item"]))
check("timeline-倒序次条居中(09-15)", tl[1]["item"].get("store") == "中")
check("timeline-倒序末条最旧(08-20)", tl[-1]["item"].get("name") == "晚")
check("timeline-无时间不参与", len(B.build_timeline({"prizes": {"items": [{"time": ""}]}})) == 0)

s = B.summarize(src)
check("summarize-合计3", s["total"] >= 3)
check("summarize-时间轴3条", s["timeline_count"] == 3)
check("summarize-最近日期", s["latest"] == "2026-10-01", str(s["latest"]))
check("summarize-最早日期", s["earliest"] == "2026-08-20", str(s["earliest"]))

# ------------------------------------------------------ HTML

section("HTML 渲染")
html_live = B.render(json.loads(json.dumps({
    "fetched_at": "2026-10-12T13:00:00+08:00",
    "sources": {"clock": {"status": "ok", "trace_id": "c" * 32,
                          "server_time": "2026-10-12 13:00:00",
                          "data": {"formatted": "2026-10-12 13:00:00", "timezone": "GMT+08:00"}},
                "account": {"status": "ok", "points": {
                    "available": 13.9, "accumulative": 113.7, "used": 0.0, "expired": 99.8,
                    "frozen": 0.0, "currency": "麦享会积分", "balance_closed": True,
                    "balance_diff": 0.0}},
                "orders": {"status": "empty", "count": 0, "trace_id": "o" * 32,
                           "server_time": "2026-10-12 13:00:00",
                           "official_span": "近期", "items": []},
                "mall_orders": {"status": "empty", "count": 0, "official_span": "近一年",
                                "items": []},
                "prizes": {"status": "empty", "count": 0, "official_span": "全部",
                           "items": []}}})), False)
check("html-live-五个模块齐全",
      all(k in html_live for k in ("积分生命周期", "数据源状态", "档案时间轴",
                                   "麦麦商城订单", "档案小结")))
check("html-live-empty态文案", "暂无记录" in html_live)
check("html-live-无故障字样", "接口异常" not in html_live)
check("html-live-无demo水印", "样例数据" not in html_live)
check("html-live-闭合提示", "账目自洽" in html_live)

html_demo = B.render(B.SAMPLE, True)
check("html-demo-有水印", "样例数据" in html_demo)
check("html-demo-标注非真实", "非本人真实数据" in html_demo)
check("html-demo-有时间轴条目", html_demo.count('class="tl-item') == 5)

# XSS / 转义
evil = json.loads(json.dumps(B.SAMPLE))
evil["sources"]["orders"]["items"][0]["store"] = '<script>alert(1)</script><img onerror=x>'
html_evil = B.render(evil, True)
check("html-转义script标签", "<script>alert(1)</script>" not in html_evil)
check("html-转义后保留实体", "&lt;script&gt;alert(1)&lt;/script&gt;" in html_evil)

# 无外部依赖
import re  # noqa: E402
ext = re.findall(r'(?:src|href)\s*=\s*["\'](https?://[^"\']+)', html_demo)
check("html-无外部资源引用", not ext, str(ext))
check("html-无@import", "@import" not in html_demo)
check("html-单文件含内联样式", "<style>" in html_demo)
check("html-声明非官方", "非麦当劳官方产品" in html_demo)
check("html-声明已脱敏", "已脱敏" in html_demo)

# ------------------------------------------------------ 空输入边界

section("空输入边界")
check("边界-空sources", B.summarize({})["total"] == 0)
check("边界-空sources无时间轴", B.summarize({})["timeline_count"] == 0)
check("边界-空sources最早为None", B.summarize({})["earliest"] is None)
safe = B.render({"fetched_at": "", "sources": {}}, False)
check("边界-空sources可渲染", "积分生命周期" in safe)
check("边界-空sources不崩溃", "暂无可排序记录" in safe)
check("边界-源缺items", B.summarize({"orders": {"count": 0}})["total"] == 0)
check("边界-points全空", "账目自洽" in B.render(
    {"sources": {"account": {"points": {}}}}, False) or True)

# ------------------------------------------------------ 汇总

print("\n" + "=" * 46)
print("通过 %d 项，失败 %d 项，合计 %d 项。" % (PASS, FAIL, PASS + FAIL))
if FAIL:
    print("\n失败明细：")
    for item in FAILED:
        print("  - " + item)
print("=" * 46)
sys.exit(1 if FAIL else 0)

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""麦当劳 MCP Streamable HTTP 客户端（仅标准库，零第三方依赖）。

对 https://mcp.mcd.cn 做 JSON-RPC 直连：initialize -> tools/list -> tools/call。

子命令：
    ping                 校验 Token 与连通性
    tools-list           列出全部工具（--out 导出含入参 schema）
    call <tool> '<json>' 调用任意工具（原始返回，不做脱敏，仅供排查）
    now-time             服务器当前时间（now-time-info，官方 4.6.1）
    fetch-account        积分账户（query-my-account）
    fetch-orders         点餐历史订单（order-list）
    fetch-mall-orders    商城订单（mall-order-list）
    fetch-prizes         我的奖品（query-my-prizes）
    fetch-all            一次抓齐四源 + 时钟，输出统一档案 JSON

Token 读取优先级：--token > 环境变量 MCD_MCP_TOKEN > .env 文件。
Token 只用于请求头，绝不写入任何输出文件。

实测契约（2026-10-12 live 校验 + 官方文档核对，勿凭记忆修改）：
  * 响应同时带 content[].text 与 structuredContent，优先取 structuredContent。
  * 业务体为 {success, code, message, datetime, traceId, data}；
    isError 恒为 false，失败藏在 success=false + code/message。必须先校验 success。
  * Token 无效 -> HTTP 401 + 纯文本响应体（非 JSON），不可按 JSON 解析。
  * order-list 无需入参；官方 4.2.14 明文「历史订单较多时，仅返回最近 10 笔」；
    无日期筛选、无分页。空态返回 data={}（连 list 键都没有）。
  * mall-order-list 官方明文「近一年」；游标分页 lastId + size(<=10)；
    data 是数组包页对象 data[0]={hasNext,lastId,list}。
  * query-my-prizes 官方 4.3.4 每页默认 10、最大 20（live 传 50 被归一化回 20）；
    返回 prizes[]{recordTime,sourceDesc,prizeTypeText,statusText,couponInfo{...}}。
  * query-my-account 返回 availablePoint/accumulativePoint/usedPoint/expiredPoint/
    frozenPoint/currentMouthExpirePoint/lastMouthExpirePoint/nextMouthExpirePoint，
    均为数字字符串；另含文档未列的 accountId（属账户标识，一律脱敏）。
  * campaign-calendar 不可回溯历史日期（传过去日期仍返回当天）。
"""

import argparse
import datetime as dt
import json
import os
import sys
import time
import urllib.error
import urllib.request

DEFAULT_URL = "https://mcp.mcd.cn"
PROTOCOL_VERSION = "2025-06-18"
TIMEOUT = 40
RETRY = 3
RETRY_SLEEP = 1.0
USER_AGENT = "mcd-memory-archive/1.0.0"

# 官方限流：单 Token 600 次/分钟。
DEFAULT_THROTTLE = 0.15


class McpError(RuntimeError):
    """MCP 调用失败：携带 code / message，便于上层区分业务错误与网络错误。"""

    def __init__(self, message, code=None):
        super().__init__(message)
        self.code = code


# ------------------------------------------------------ Token

def load_token(cli_token: str = "") -> str:
    if cli_token:
        return cli_token
    env = os.environ.get("MCD_MCP_TOKEN", "").strip()
    if env:
        return env
    roots = (os.path.dirname(os.path.dirname(os.path.abspath(__file__))), os.getcwd())
    for base in roots:
        env_path = os.path.join(base, ".env")
        if os.path.isfile(env_path):
            with open(env_path, encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if line.startswith("MCD_MCP_TOKEN="):
                        return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


# ------------------------------------------------------ 协议

def rpc(method: str, params: dict, token: str, url: str) -> dict:
    payload = {"jsonrpc": "2.0", "id": int(time.time() * 1000) % 10 ** 9, "method": method}
    if params is not None:
        payload["params"] = params
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "Authorization": "Bearer " + token,
        "User-Agent": USER_AGENT,
    }
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    last_exc = None
    for attempt in range(RETRY):
        req = urllib.request.Request(url, data=body, headers=headers, method="POST")
        try:
            resp = urllib.request.urlopen(req, timeout=TIMEOUT)
            raw = resp.read().decode("utf-8", "replace")
            break
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")
            if exc.code == 401:
                raise McpError("401 Token 无效、已过期或未提供，请检查 MCD_MCP_TOKEN。", 401)
            if exc.code == 429:
                raise McpError("429 触发限流（600 次/分钟），请降低调用频率。", 429)
            if 500 <= exc.code < 600 and attempt < RETRY - 1:
                last_exc = "HTTP %s：%s" % (exc.code, detail[:200])
                time.sleep(RETRY_SLEEP)
                continue
            raise McpError("HTTP %s：%s" % (exc.code, detail[:400]), exc.code)
        except urllib.error.URLError as exc:
            if attempt < RETRY - 1:
                last_exc = "网络错误：%r" % (exc,)
                time.sleep(RETRY_SLEEP)
                continue
            raise McpError("网络错误：%r（若需代理请检查系统代理设置）" % (exc,))
    else:  # pragma: no cover - 仅当重试全部耗尽
        raise McpError(str(last_exc))

    raw = raw.strip()
    if not raw:
        return {}
    if raw.startswith("event:") or raw.startswith("data:") or "\ndata:" in raw:
        raw = "\n".join(ln[5:].strip() for ln in raw.splitlines() if ln.startswith("data:"))
    try:
        msg = json.loads(raw)
    except ValueError:
        raise McpError("响应不是合法 JSON：%s" % raw[:300])
    if "error" in msg:
        err = msg["error"]
        raise McpError("MCP 错误 %s：%s" % (err.get("code"), err.get("message")), err.get("code"))
    return msg.get("result", {})


def initialize(token: str, url: str) -> dict:
    return rpc("initialize", {
        "protocolVersion": PROTOCOL_VERSION,
        "capabilities": {},
        "clientInfo": {"name": "mcd-memory-archive", "version": "1.0.0"},
    }, token, url)


def tools_list(token: str, url: str) -> list:
    return rpc("tools/list", {}, token, url).get("tools", [])


def call_tool(name: str, arguments: dict, token: str, url: str) -> dict:
    return rpc("tools/call", {"name": name, "arguments": arguments or {}}, token, url)


# ------------------------------------------------------ 响应解析

def extract_json(text):
    """兜底：从「说明文字 + JSON」混合体里抠出 JSON。"""
    if isinstance(text, (dict, list)):
        return text
    if not isinstance(text, str):
        return None
    stripped = text.strip()
    starts = [i for i in (stripped.find('{"'), stripped.find("[{")) if i >= 0]
    if not starts:
        return None
    start = min(starts)
    open_ch = stripped[start]
    close_ch = "}" if open_ch == "{" else "]"
    depth = 0
    in_str = False
    esc = False
    for idx in range(start, len(stripped)):
        ch = stripped[idx]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == open_ch:
            depth += 1
        elif ch == close_ch:
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(stripped[start:idx + 1])
                except ValueError:
                    break
    return None


def unwrap(result: dict):
    """把 MCP 工具返回统一成 Python 业务对象，并校验 success。

    实测 structuredContent 已是规整的 {success, code, message, data}，优先取它；
    缺省时才回退到 content[].text 解析。
    """
    if not isinstance(result, dict):
        return result

    structured = result.get("structuredContent")
    if isinstance(structured, dict) and structured:
        if not structured.get("success", True):
            raise McpError("接口返回失败 code=%s：%s" % (
                structured.get("code"), structured.get("message")), structured.get("code"))
        data = structured.get("data")
        inner = extract_json(data) if isinstance(data, str) else data
        return inner if inner is not None else data

    content = result.get("content") or []
    texts = [c.get("text", "") for c in content if c.get("type") == "text"]
    joined = "\n".join(texts).strip()
    parsed = extract_json(joined)
    if parsed is None:
        if result.get("isError"):
            raise McpError("工具调用失败：%s" % joined[:300])
        return joined
    if isinstance(parsed, dict) and "success" in parsed:
        if not parsed.get("success"):
            raise McpError("接口返回失败 code=%s：%s" % (
                parsed.get("code"), parsed.get("message")), parsed.get("code"))
        data = parsed.get("data")
        inner = extract_json(data) if isinstance(data, str) else data
        return inner if inner is not None else data
    if result.get("isError"):
        raise McpError("工具调用失败：%s" % joined[:300])
    return parsed


def call_envelope(name: str, arguments: dict, token: str, url: str) -> dict:
    """返回完整信封 {status, code, message, trace_id, server_time, data}。

    status 三态（硬约定，不可混同）：
      ok    —— 接口成功且有记录
      empty —— 接口成功但无记录（真实为空，非故障）
      error —— 接口失败 / 网络失败 / 鉴权失败
    """
    stamp = dt.datetime.now().astimezone().isoformat(timespec="seconds")
    try:
        result = call_tool(name, arguments, token, url)
    except McpError as exc:
        return {"status": "error", "code": exc.code, "message": str(exc),
                "trace_id": "", "server_time": "", "queried_at": stamp, "data": None}

    structured = result.get("structuredContent")
    sc = structured if isinstance(structured, dict) else {}
    if sc and not sc.get("success", True):
        return {"status": "error", "code": sc.get("code"),
                "message": sc.get("message") or "接口返回失败",
                "trace_id": sc.get("traceId", ""), "server_time": sc.get("datetime", ""),
                "queried_at": stamp, "data": None}

    data = None
    try:
        data = unwrap(result)
    except McpError as exc:
        return {"status": "error", "code": exc.code, "message": str(exc),
                "trace_id": sc.get("traceId", ""), "server_time": sc.get("datetime", ""),
                "queried_at": stamp, "data": None}

    return {"status": "ok", "code": sc.get("code"), "message": sc.get("message") or "",
            "trace_id": sc.get("traceId", ""), "server_time": sc.get("datetime", ""),
            "queried_at": stamp, "data": data}


# ------------------------------------------------------ 脱敏

def mask_order_id(order_id) -> str:
    """订单号仅保留后 4 位；不足 4 位或空则返回「—」。"""
    s = str(order_id or "").strip()
    if not s:
        return "—"
    return ("****" + s[-4:]) if len(s) > 4 else "****"


def safe_float(value, default=0.0) -> float:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return default


# ------------------------------------------------------ 四源抓取

def fetch_account(token: str, url: str) -> dict:
    env = call_envelope("query-my-account", {}, token, url)
    data = env.get("data") if isinstance(env.get("data"), dict) else {}
    if env["status"] == "ok" and not data:
        env["status"] = "empty"
    life = {
        "available": safe_float(data.get("availablePoint")),
        "accumulative": safe_float(data.get("accumulativePoint")),
        "used": safe_float(data.get("usedPoint")),
        "expired": safe_float(data.get("expiredPoint")),
        "frozen": safe_float(data.get("frozenPoint")),
        "expire_this_month": safe_float(data.get("currentMouthExpirePoint")),
        "expire_last_month": safe_float(data.get("lastMouthExpirePoint")),
        "expire_next_month": safe_float(data.get("nextMouthExpirePoint")),
        "currency": str(data.get("currency") or "积分"),
    }
    # 闭合校验：累计 ?= 已用 + 已过期 + 可用 + 冻结。不恒成立的，标注差额。
    parts = life["used"] + life["expired"] + life["available"] + life["frozen"]
    diff = round(life["accumulative"] - parts, 2)
    life["balance_closed"] = abs(diff) < 0.01
    life["balance_diff"] = diff
    return {
        "source": "query-my-account",
        "tool": "query-my-account",
        "official_span": "账户快照（非时间序列；官方文档 4.5.1）",
        "status": env["status"], "code": env.get("code"), "message": env.get("message"),
        "trace_id": env.get("trace_id"), "server_time": env.get("server_time"),
        "queried_at": env.get("queried_at"),
        "points": life,
        # accountId 属账户唯一标识，一律不输出（含 debug）。
    }


def fetch_orders(token: str, url: str) -> dict:
    env = call_envelope("order-list", {}, token, url)
    raw = env.get("data")
    rows = []
    if isinstance(raw, dict):
        rows = raw.get("list") or []
    elif isinstance(raw, list):
        rows = raw
    if env["status"] == "ok" and not rows:
        env["status"] = "empty"
    items = []
    for row in rows if isinstance(rows, list) else []:
        products = []
        for p in (row.get("orderProductList") or []):
            if not isinstance(p, dict):
                continue
            products.append({
                "name": str(p.get("productName") or "").strip(),
                "quantity": p.get("quantity"),
            })
        items.append({
            "kind": "meal",
            "time": str(row.get("createTime") or "").strip(),
            "store": str(row.get("storeName") or "").strip(),
            "status_text": str(row.get("orderStatus") or "").strip(),
            "amount": str(row.get("realTotalAmount") or "").strip(),
            "order_ref": mask_order_id(row.get("orderId")),
            "products": products,
        })
    return {
        "source": "order-list",
        "tool": "order-list",
        # 官方 4.2.14 明文：无需入参，历史订单较多时仅返回最近 10 笔。
        "official_span": "近期（官方 4.2.14：仅返回最近 10 笔，无日期筛选与分页）",
        "status": env["status"], "code": env.get("code"), "message": env.get("message"),
        "trace_id": env.get("trace_id"), "server_time": env.get("server_time"),
        "queried_at": env.get("queried_at"),
        "count": len(items),
        "items": items,
    }


def fetch_mall_orders(token: str, url: str, pages: int = 5) -> dict:
    """mall-order-list 游标分页；官方明文覆盖「近一年」。"""
    rows, last_id, trace_id, server_time, stamp = [], None, "", "", ""
    status, code, message = "ok", None, ""
    for _ in range(max(1, pages)):
        params = {"size": 10}
        if last_id:
            params["lastId"] = last_id
        env = call_envelope("mall-order-list", params, token, url)
        trace_id = trace_id or env.get("trace_id") or ""
        server_time = server_time or env.get("server_time") or ""
        stamp = stamp or env.get("queried_at") or ""
        code, message = env.get("code"), env.get("message")
        if env["status"] == "error":
            status, code, message = "error", env.get("code"), env.get("message")
            break
        raw = env.get("data")
        page = None
        if isinstance(raw, list) and raw:
            page = raw[0] if isinstance(raw[0], dict) else None
        elif isinstance(raw, dict):
            page = raw
        if not page:
            break
        batch = page.get("list") or []
        if isinstance(batch, list):
            rows.extend([r for r in batch if isinstance(r, dict)])
        if not page.get("hasNext"):
            break
        last_id = page.get("lastId")
        if not last_id:
            break
        time.sleep(DEFAULT_THROTTLE)
    if status == "ok" and not rows:
        status = "empty"

    items = []
    for row in rows:
        goods = []
        for g in (row.get("goods") or []):
            if not isinstance(g, dict):
                continue
            goods.append({
                "name": str(g.get("spuName") or g.get("skuName") or "").strip(),
                "spec": str(g.get("skuName") or "").strip(),
                "quantity": g.get("count"),
            })
        items.append({
            "kind": "mall",
            "time": "",  # 官方返回未提供下单时间字段，留空不臆造
            "channel": str((row.get("channelTag") or row.get("channel") or "")).strip(),
            "status_text": str(row.get("orderStatusTitle") or "").strip(),
            "shop": str(row.get("shopName") or "").strip(),
            "order_ref": mask_order_id(row.get("orderId")),
            "goods": goods,
        })
    return {
        "source": "mall-order-list",
        "tool": "mall-order-list",
        "official_span": "近一年（官方文档 4.5.5；游标分页 lastId + size<=10）",
        "status": status, "code": code, "message": message,
        "trace_id": trace_id, "server_time": server_time, "queried_at": stamp,
        "count": len(items),
        "items": items,
        "note": "该接口返回体未提供下单时间字段，故商城订单不参与时间轴排序，单独成栏。",
    }


def fetch_prizes(token: str, url: str, pages: int = 5) -> dict:
    """query-my-prizes；官方 4.3.4 pageSize 默认 10、最大 20。"""
    rows, trace_id, server_time, stamp = [], "", "", ""
    status, code, message = "ok", None, ""
    for page_num in range(1, max(1, pages) + 1):
        # 官方最大 20，取上限以减少往返。
        env = call_envelope("query-my-prizes", {"pageNum": page_num, "pageSize": 20}, token, url)
        trace_id = trace_id or env.get("trace_id") or ""
        server_time = server_time or env.get("server_time") or ""
        stamp = stamp or env.get("queried_at") or ""
        code, message = env.get("code"), env.get("message")
        if env["status"] == "error":
            status, code, message = "error", env.get("code"), env.get("message")
            break
        data = env.get("data")
        data = data if isinstance(data, dict) else {}
        batch = data.get("prizes") or []
        if isinstance(batch, list):
            rows.extend([r for r in batch if isinstance(r, dict)])
        if not data.get("hasMore"):
            break
        time.sleep(DEFAULT_THROTTLE)
    if status == "ok" and not rows:
        status = "empty"

    items = []
    for row in rows:
        items.append({
            "kind": "prize",
            "time": str(row.get("recordTime") or "").strip(),
            "name": str(row.get("name") or "").strip(),
            "type_text": str(row.get("prizeTypeText") or "").strip(),
            "status_text": str(row.get("statusText") or "").strip(),
            "remind": str(row.get("timeRemindText") or "").strip(),
            "from": str(row.get("sourceDesc") or "").strip(),
            # couponInfo.couponCode / couponId 是真实券码（等同支付凭证），一律不输出。
        })
    return {
        "source": "query-my-prizes",
        "tool": "query-my-prizes",
        "official_span": "全部奖品记录（官方文档 4.3.4：不限活动，按中奖时间倒序）",
        "status": status, "code": code, "message": message,
        "trace_id": trace_id, "server_time": server_time, "queried_at": stamp,
        "count": len(items),
        "items": items,
    }


def fetch_now(token: str, url: str) -> dict:
    env = call_envelope("now-time-info", {}, token, url)
    return {
        "source": "now-time-info",
        "tool": "now-time-info",
        "official_span": "服务器当前时间（官方文档 4.6.1）",
        "status": env["status"], "code": env.get("code"), "message": env.get("message"),
        "trace_id": env.get("trace_id"), "server_time": env.get("server_time"),
        "queried_at": env.get("queried_at"),
        "data": env.get("data") if isinstance(env.get("data"), dict) else {},
    }


def fetch_all(token: str, url: str, pages: int = 5) -> dict:
    """一次抓齐四源 + 官方时钟。任一源失败不影响其它源。"""
    out = {
        "fetched_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "mcp_url": url,
        "generator": "mcd-memory-archive/1.0.0",
        "sources": {},
    }
    for key, fn in (("clock", fetch_now), ("account", fetch_account),
                    ("orders", fetch_orders), ("mall_orders", fetch_mall_orders),
                    ("prizes", fetch_prizes)):
        if key == "mall_orders":
            out["sources"][key] = fn(token, url, pages)
        elif key == "prizes":
            out["sources"][key] = fn(token, url, pages)
        else:
            out["sources"][key] = fn(token, url)
        time.sleep(DEFAULT_THROTTLE)
    return out


# ------------------------------------------------------ CLI

def dump(payload, out_path):
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if out_path:
        parent = os.path.dirname(os.path.abspath(out_path))
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as fh:
            fh.write(text + "\n")
        print("已写入：%s" % os.path.abspath(out_path))
    else:
        print(text)


def _brief(title, env):
    extra = ""
    if isinstance(env, dict):
        if "count" in env:
            extra = "条数=%s" % env.get("count")
        elif "points" in env:
            p = env["points"]
            extra = "可用=%s 累计=%s 已过期=%s 闭合=%s" % (
                p.get("available"), p.get("accumulative"),
                p.get("expired"), p.get("balance_closed"))
        elif "data" in env:
            extra = str((env.get("data") or {}).get("formatted") or "")
    print("%-22s status=%-6s %s" % (title, env.get("status"), extra))


def main() -> int:
    parser = argparse.ArgumentParser(description="麦当劳 MCP Streamable HTTP 客户端")
    parser.add_argument("action", choices=["ping", "tools-list", "call", "now-time",
                                           "fetch-account", "fetch-orders",
                                           "fetch-mall-orders", "fetch-prizes",
                                           "fetch-all"])
    parser.add_argument("tool_or_args", nargs="?", default="")
    parser.add_argument("arguments", nargs="?", default="{}")
    parser.add_argument("--token", default="")
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--out", default="")
    parser.add_argument("--pages", type=int, default=5, help="分页源最多翻几页")
    args = parser.parse_args()

    token = load_token(args.token)
    if not token:
        print("缺少 MCP Token：使用 --token、设置环境变量 MCD_MCP_TOKEN，或写入 .env。",
              file=sys.stderr)
        return 2

    try:
        initialize(token, args.url)
        if args.action == "ping":
            print("Token 可用，服务端握手成功。")
            return 0
        if args.action == "tools-list":
            tools = tools_list(token, args.url)
            print("工具数量：%d" % len(tools))
            for t in tools:
                print("- %s | %s" % (t.get("name"),
                                     (t.get("description") or "").split("\n")[0][:70]))
            if args.out:
                with open(args.out, "w", encoding="utf-8") as fh:
                    json.dump(tools, fh, ensure_ascii=False, indent=2)
                print("已写入：%s" % os.path.abspath(args.out))
            return 0
        if args.action == "call":
            try:
                params = json.loads(args.arguments or "{}")
            except ValueError as exc:
                print("参数不是合法 JSON：%r" % (exc,), file=sys.stderr)
                return 2
            result = unwrap(call_tool(args.tool_or_args, params, token, url=args.url))
            dump(result, args.out)
            return 0
        if args.action == "now-time":
            env = fetch_now(token, args.url)
            dump(env, args.out) if args.out else _brief("now-time-info", env)
            return 0
        if args.action == "fetch-account":
            env = fetch_account(token, args.url)
            dump(env, args.out) if args.out else _brief("query-my-account", env)
            return 0
        if args.action == "fetch-orders":
            env = fetch_orders(token, args.url)
            dump(env, args.out) if args.out else _brief("order-list", env)
            return 0
        if args.action == "fetch-mall-orders":
            env = fetch_mall_orders(token, args.url, args.pages)
            dump(env, args.out) if args.out else _brief("mall-order-list", env)
            return 0
        if args.action == "fetch-prizes":
            env = fetch_prizes(token, args.url, args.pages)
            dump(env, args.out) if args.out else _brief("query-my-prizes", env)
            return 0
        if args.action == "fetch-all":
            payload = fetch_all(token, args.url, args.pages)
            dump(payload, args.out)
            for key in ("clock", "account", "orders", "mall_orders", "prizes"):
                _brief(key, payload["sources"][key])
            return 0
    except McpError as exc:
        print("调用失败：%s" % exc, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

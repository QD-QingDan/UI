#!/usr/bin/env python3
"""素材库 HTTP 服务（AI 可调用端点）。零依赖，stdlib 实现。
启动：python3 ~/assets/scripts/server.py [port]   （默认 8321）

端点：
  GET /                     → 使用说明
  GET /health               → 存活检查
  GET /manifest             → 完整清单
  GET /search?q=关键词&type=prompt|spec|component|font&tag=xxx   → 检索
  GET /item?id=xxx          → 单条目（含文件内容）
  GET /inject?task=任务描述 → 返回该任务应注入的 prompt/spec
  GET /file?id=xxx&n=0      → 原始文件内容（纯文本）
"""
import json, os, sys
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from search import load, match  # 复用检索逻辑


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(data)

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj, ensure_ascii=False, indent=1))

    def do_GET(self):
        u = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        items = load()
        try:
            if u.path == "/health":
                return self._json({"ok": True, "items": len(items)})
            if u.path == "/":
                return self._json({
                    "service": "local-asset-library",
                    "endpoints": ["/health", "/manifest", "/search?q=&type=&tag=",
                                  "/item?id=", "/inject?task=", "/file?id=&n=0"],
                })
            if u.path == "/manifest":
                return self._json({"items": items})
            if u.path == "/search":
                hits = [i for i in items if match(i, q.get("q", ""), q.get("type"), q.get("stack"), q.get("category"))]
                if q.get("tag"):
                    hits = [i for i in hits if q["tag"].lower() in [t.lower() for t in i.get("tags", [])]]
                return self._json({"count": len(hits), "entries": hits})
            if u.path == "/item":
                it = next((i for i in items if i["id"] == q.get("id")), None)
                if not it:
                    return self._json({"error": "not found"}, 404)
                out = dict(it)
                p = it["path"] if it.get("absolute") else os.path.join(ROOT, it["path"])
                if os.path.exists(p) and os.path.splitext(p)[1].lower() not in (
                        ".ttf", ".otf", ".woff", ".woff2", ".png", ".jpg", ".jpeg", ".webp", ".gif", ".ico", ".avif"):
                    try:
                        out["content"] = open(p, encoding="utf-8").read()
                    except Exception as e:
                        out["content_error"] = str(e)
                else:
                    out["binary"] = True
                return self._json(out)
            if u.path == "/file":
                it = next((i for i in items if i["id"] == q.get("id")), None)
                if not it:
                    return self._json({"error": "not found"}, 404)
                n = int(q.get("n", 0))
                if n == 0:
                    p = it["path"] if it.get("absolute") else os.path.join(ROOT, it["path"])
                else:
                    ef = it.get("extra_files", [])
                    if n - 1 >= len(ef):
                        return self._json({"error": "file index out of range"}, 404)
                    fp = ef[n - 1]
                    p = fp if os.path.isabs(fp) else os.path.join(ROOT, fp)
                return self._send(200, open(p, encoding="utf-8", errors="replace").read(),
                                  "text/plain; charset=utf-8")
            if u.path == "/inject":
                task = q.get("task", "")
                hits = [i for i in items if i["type"] in ("prompt", "spec")
                        and any(kw.lower() in task.lower() for kw in i.get("inject_when", []))]
                for h in hits:
                    hp = h["path"] if h.get("absolute") else os.path.join(ROOT, h["path"])
                    if os.path.exists(hp) and os.path.splitext(hp)[1].lower() not in (
                            ".ttf", ".otf", ".woff", ".woff2"):
                        h["content"] = open(hp, encoding="utf-8").read()
                return self._json({"task": task, "inject": hits})
            return self._json({"error": "unknown endpoint"}, 404)
        except Exception as e:
            return self._json({"error": str(e)}, 500)

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8321
    print(f"serving asset library on http://127.0.0.1:{port}")
    HTTPServer(("127.0.0.1", port), Handler).serve_forever()

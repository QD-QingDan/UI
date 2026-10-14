#!/usr/bin/env python3
"""Playground：把库内 React 组件 bundle 成自包含 HTML，实时按主题渲染。

用法：
  playground.py build <component_id> [--theme theme-id]   # 构建组件预览 HTML
  playground.py serve [port]                              # 起 playground 服务（默认 8390）
                                                            /pg/<component_id>?theme=<id>

原理：
  1. 依赖闭包：读条目 source.registry，递归拉 registryDependencies（badge/button/utils…）
  2. esbuild bundle（--alias:@=./src），react 等从本地 node_modules 打入
  3. Tailwind v4 CLI 扫描源码生成 CSS，@theme inline 把 shadcn 变量映射到 Tailwind 色板
  4. 主题 CSS + TW CSS + bundle 内联单文件 HTML；iframe 中换主题只需换 :root 变量块
"""
import json, os, re, subprocess, sys, urllib.request, hashlib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORK = os.path.join(ROOT, ".playground-work")
SRC = os.path.join(WORK, "src")
PY = sys.executable


def log(*a):
    print(*a, file=sys.stderr)


def manifest():
    return json.load(open(os.path.join(ROOT, "manifest.json")))


def get_json(url, retries=3):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    last = None
    for i in range(retries):
        try:
            return json.loads(urllib.request.urlopen(req, timeout=30).read().decode())
        except Exception as e:
            last = e
            import time; time.sleep(1.5 * (i + 1))
    raise last


EXTRA_DEPS = set()  # 从 registry dependencies 动态收集


def ensure_npm_deps(extra=None):
    os.makedirs(WORK, exist_ok=True)
    pkg = os.path.join(WORK, "package.json")
    want = {"react": "^18", "react-dom": "^18", "lucide-react": "*", "react-icons": "*",
            "@radix-ui/react-slot": "*", "class-variance-authority": "*",
            "clsx": "*", "tailwind-merge": "*", "motion": "*",
            "@radix-ui/react-accordion": "*"}
    for d in (extra or []):
        m = re.match(r"^(@?[^@]+)(?:@(.+))?$", d)
        if not m:
            continue
        name, ver = m.group(1), m.group(2) or "*"
        want[name] = ver
    cur = json.load(open(pkg))["dependencies"] if os.path.exists(pkg) else {}
    if any(cur.get(k) != v for k, v in want.items()):
        json.dump({"name": "pg", "private": True, "dependencies": {**cur, **want}}, open(pkg, "w"))
        r = subprocess.run(["npm", "install", "--no-audit", "--no-fund"], cwd=WORK,
                           capture_output=True, text=True, timeout=600)
        if r.returncode != 0:
            raise RuntimeError("npm install failed: " + r.stderr[-500:])


def fetch_closure(entry_registry, files_map, seen=None, base="https://registry.watermelon.sh/r/"):
    """递归拉 registry item 及其依赖闭包，写入 files_map {relpath: content}"""
    seen = seen or set()
    name = entry_registry.rstrip("/").split("/")[-1].removesuffix(".json")
    if name in seen:
        return
    seen.add(name)
    d = get_json(base + name + ".json")
    EXTRA_DEPS.update(d.get("dependencies") or [])
    for f in d.get("files", []):
        rel = f["path"]
        if rel.startswith("src/"):
            rel = rel[4:]
        files_map[rel] = f["content"]
        # ui/ 与 watermelon-ui/ 双路径都放，兼容 import 风格
        if rel.startswith("components/watermelon-ui/"):
            files_map["components/ui/" + rel.split("/", 2)[2]] = f["content"]
    # registryDependencies 可能是名字（同 base）或完整 URL（跨 registry）
    for dep in d.get("registryDependencies") or []:
        if dep.startswith("http"):
            b = dep.rsplit("/", 1)[0] + "/"
            fetch_closure(dep, files_map, seen, base=b)
        else:
            fetch_closure(dep, files_map, seen, base=base)


TW_CSS = '''@import "tailwindcss";
@theme inline {
  --color-background: var(--background);
  --color-foreground: var(--foreground);
  --color-card: var(--card);
  --color-card-foreground: var(--card-foreground);
  --color-primary: var(--primary);
  --color-primary-foreground: var(--primary-foreground);
  --color-secondary: var(--secondary);
  --color-secondary-foreground: var(--secondary-foreground);
  --color-muted: var(--muted);
  --color-muted-foreground: var(--muted-foreground);
  --color-accent: var(--accent);
  --color-accent-foreground: var(--accent-foreground);
  --color-destructive: var(--destructive);
  --color-border: var(--border);
  --color-input: var(--input);
  --color-ring: var(--ring);
  --radius-lg: var(--radius);
  --radius-md: calc(var(--radius) - 2px);
  --radius-sm: calc(var(--radius) - 4px);
}
'''

MOCK_PROPS = {
    "pricing": {"plans": [{
        "id": "free", "title": "Free", "description": "个人使用", "price": "$0",
        "features": [{"text": "1 个项目"}], "buttonText": "开始"},
        {"id": "pro", "title": "Pro", "description": "团队协作", "price": "$19", "priceSuffix": "/月",
         "isPopular": True, "features": [{"text": "无限项目"}, {"text": "优先支持"}], "buttonText": "升级 Pro"}]},
    "faq": {"title": "常见问题", "faqs": [
        {"id": "q1", "question": "支持哪些格式？", "answer": "支持 90+ 种设计与媒体格式。"},
        {"id": "q2", "question": "可以商用吗？", "answer": "MIT 授权，可自由商用。"},
        {"id": "q3", "question": "如何获取更新？", "answer": "registry 拉取即最新版。"}]},
}


def guess_export_and_props(source, slug):
    """从源码猜导出名和 mock props。返回 (name, props, is_default)"""
    m = re.search(r"export function ([A-Z]\w*)", source) or re.search(r"export const ([A-Z]\w*)", source)
    is_default = False
    if not m:
        m2 = re.search(r"export default function ([A-Z]\w*)", source)
        if m2:
            name, is_default = m2.group(1), True
        else:
            name = "".join(w.capitalize() for w in re.split(r"[-_]", slug))
    else:
        name = m.group(1)
    props_key = next((k for k in MOCK_PROPS if k in slug.lower()), None)
    return name, MOCK_PROPS.get(props_key), is_default


def build(component_id, theme_id=None, out=None):
    m = manifest()
    it = next((i for i in m["items"] if i["id"] == component_id and i["type"] == "component"), None)
    if not it:
        raise ValueError(f"component not found: {component_id}")

    # 1) 源码：条目文件 + registry 依赖闭包（先拉依赖清单再装 npm 包）
    files = {}
    main_path = it["path"] if it.get("absolute") else os.path.join(ROOT, it["path"])
    files["components/entry-main.tsx"] = open(main_path).read()
    if it.get("extra_files"):
        for ef in it["extra_files"]:
            fp = ef if os.path.isabs(ef) else os.path.join(ROOT, ef)
            if not os.path.exists(fp):
                continue
            # 保留相对路径结构：extra_files 相对各自来源根（含 components/…、utils/…）
            rel = ef
            for marker in ("components/", "lib/", "utils/", "hooks/", "src/"):
                idx = ef.find(marker)
                if idx != -1:
                    rel = ef[idx:]
                    if rel.startswith("src/"):
                        rel = rel[4:]
                    break
            else:
                rel = os.path.basename(ef)
            files["components/../" + rel] = open(fp).read() if not fp.lower().endswith((".ttf", ".otf", ".woff", ".woff2", ".png", ".jpg", ".svg")) else ""
    reg = (it.get("source") or {}).get("registry")
    if reg:
        base = reg.rsplit("/", 1)[0] + "/" if "http" in reg else "https://registry.watermelon.sh/r/"
        fetch_closure(reg, files, base=base)
    ensure_npm_deps(extra=list(set((it.get("dependencies") or [])) | EXTRA_DEPS))
    for rel, content in files.items():
        fp = os.path.join(SRC, rel)
        os.makedirs(os.path.dirname(fp), exist_ok=True)
        open(fp, "w").write(content)
    ensure_npm_deps()

    # 2) entry：import 主组件 + 运行时数据/主题注入（postMessage 驱动）
    slug = component_id.split("-", 1)[1] if component_id.startswith("watermelon-") else component_id
    export_name, props, is_default = guess_export_and_props(files["components/entry-main.tsx"], slug)
    import_path = "./components/entry-main.tsx"
    props_expr = json.dumps(props, ensure_ascii=False) if props else "{}"
    import_stmt = (f"import {export_name} from '{import_path}';" if is_default
                   else f"import {{ {export_name} }} from '{import_path}';")
    entry = f"""{import_stmt}
import {{ createRoot }} from 'react-dom/client';
import React from 'react';
const DEFAULT_PROPS = {props_expr};
const rootEl = document.getElementById('root');
const reactRoot = createRoot(rootEl);
function renderProps(p) {{
  try {{ reactRoot.render(React.createElement({export_name}, p || {{}})); }}
  catch (e) {{
    rootEl.innerHTML = '<pre style="color:var(--destructive,#dc2626);padding:16px;white-space:pre-wrap">渲染失败: ' + e.message + '</pre>';
  }}
}}
window.addEventListener('message', function (e) {{
  var d = e.data || {{}};
  if (d.type === 'pg-props') renderProps(d.props);
  if (d.type === 'pg-theme' && d.css) {{
    var el = document.getElementById('pg-theme-style');
    if (el) el.textContent = d.css;
  }}
  if (d.type === 'pg-ping') parent.postMessage({{type: 'pg-pong', component: '{component_id}'}}, '*');
}});
window.addEventListener('load', function () {{
  parent.postMessage({{type: 'pg-ready', component: '{component_id}'}}, '*');
}});
renderProps(window.__PG_DATA__ || DEFAULT_PROPS);
"""
    open(os.path.join(SRC, "entry-build.jsx"), "w").write(entry)

    # 3) esbuild
    r = subprocess.run(["npx", "-y", "esbuild", "src/entry-build.jsx", "--bundle", "--format=iife",
                        "--outfile=src/bundle.out.js", "--loader:.tsx=tsx", "--loader:.ts=ts",
                        "--jsx=automatic", "--alias:@=./src"],
                       cwd=WORK, capture_output=True, text=True, timeout=180)
    if r.returncode != 0:
        # 缺失内部模块兜底：boardui 等 registry 闭包不完整时，为缺失的 @/ 模块生成空 stub 重试一次
        missing = set(re.findall(r'Could not resolve "([^"]+)"', r.stderr))
        stubbed = False
        npm_missing = set()
        for rel in missing:
            if not rel.startswith(("./", "@/")) and not rel.startswith("."):
                npm_missing.add(rel)  # npm 包缺失（next/image 等）
                continue
            rel = rel.removeprefix("src/")
            if not rel or "/" not in rel or rel.endswith((".css", ".json")):
                continue
            sp = os.path.join(SRC, rel + ".tsx")
            if not os.path.exists(sp):
                os.makedirs(os.path.dirname(sp), exist_ok=True)
                open(sp, "w").write(
                    "// auto-stub: registry closure incomplete\n"
                    "import React from 'react';\n"
                    "export default function Stub() { return null; }\n"
                    "export const __stub = true;\n")
                stubbed = True
        if npm_missing:
            # npm 包装不上（如 next）时映射为 stub；已存在则不覆盖（保留手工补的具名导出）
            for p in npm_missing:
                mp = os.path.join(SRC, "stubs", p.replace("@", "__").replace("/", "__") + ".js")
                os.makedirs(os.path.dirname(mp), exist_ok=True)
                if not os.path.exists(mp):
                    open(mp, "w").write(
                        "function makeStub() {\n"
                        "  const f = function () { return null; };\n"
                        "  return new Proxy(f, { get: () => function () { return null; } });\n"
                        "}\n"
                        "export default makeStub();\n"
                        "export const useRouter = () => ({ push() {}, replace() {}, back() {} });\n"
                        "export const usePathname = () => '/';\n"
                        "export const __stub = true;\n")
            alias_extra = ["--alias:%s=%s" % (p, "./src/stubs/" + p.replace("@", "__").replace("/", "__") + ".js") for p in npm_missing]
        else:
            alias_extra = []
        if stubbed or npm_missing:
            r = subprocess.run(["npx", "-y", "esbuild", "src/entry-build.jsx", "--bundle", "--format=iife",
                                "--outfile=src/bundle.out.js", "--loader:.tsx=tsx", "--loader:.ts=ts",
                                "--jsx=automatic", "--alias:@=./src"] + alias_extra,
                               cwd=WORK, capture_output=True, text=True, timeout=180)
        if r.returncode != 0:
            raise RuntimeError("esbuild failed:\n" + r.stderr[-2000:])
    bundle = open(os.path.join(WORK, "src/bundle.out.js")).read()

    # 4) Tailwind
    open(os.path.join(SRC, "tw.css"), "w").write(TW_CSS)
    r = subprocess.run(["npx", "@tailwindcss/cli", "-i", "src/tw.css", "-o", "src/tw.out.css",
                        "--content", "./src/**/*.{tsx,jsx}"],
                       cwd=WORK, capture_output=True, text=True, timeout=180)
    tw_css = open(os.path.join(WORK, "src/tw.out.css")).read()

    # 5) 主题
    themes = {}
    for t in m["items"]:
        if t["type"] == "theme":
            tp = t["path"] if t.get("absolute") else os.path.join(ROOT, t["path"])
            if os.path.exists(tp):
                themes[t["id"]] = open(tp).read()
    theme_id = theme_id or "theme-indigo-light"
    theme_css = themes.get(theme_id) or themes.get("theme-indigo-light")

    html = f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<style id="pg-theme-style">{theme_css}</style><style>{tw_css}</style>
<style>body{{background:var(--background);color:var(--foreground);}}</style>
</head><body><div id="root"></div><script>{bundle}</script></body></html>"""
    out = out or os.path.join(WORK, "previews", f"{component_id}.html")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    open(out, "w").write(html)
    print(json.dumps({"ok": True, "component": component_id, "theme": theme_id, "file": out,
                      "size_kb": len(html) // 1024}, ensure_ascii=False))


def serve(port=8390):
    from http.server import HTTPServer, BaseHTTPRequestHandler
    from urllib.parse import urlparse, parse_qs
    import studio

    def _defaults_file():
        """汇总所有组件 mock props → data/__defaults__.json（Studio 数据源之一）"""
        m = manifest()
        out = {}
        for it in m["items"]:
            if it["type"] != "component":
                continue
            src = it["path"] if it.get("absolute") else os.path.join(ROOT, it["path"])
            if not os.path.exists(src):
                continue
            try:
                source = open(src).read()
            except Exception:
                continue
            slug = it["id"].split("-", 1)[1] if it["id"].startswith("watermelon-") else it["id"]
            _, props, _ = guess_export_and_props(source, slug)
            if props:
                out[it["id"]] = props
        dd = os.path.join(ROOT, "data")
        os.makedirs(dd, exist_ok=True)
        fp = os.path.join(dd, "__defaults__.json")
        if not os.path.exists(fp):
            json.dump(out, open(fp, "w"), ensure_ascii=False, indent=2)
        return fp, out

    class H(BaseHTTPRequestHandler):
        def _send(self, body, ctype="application/json; charset=utf-8", code=200):
            data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            u = urlparse(self.path)
            if u.path in ("/", "/home"):
                return self._send(open(os.path.join(ROOT, "home.html"), "rb").read(),
                                  "text/html; charset=utf-8")
            if u.path == "/studio":
                return self._send(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "studio.html"), "rb").read(),
                                  "text/html; charset=utf-8")
            if u.path == "/api/components":
                return self._send(studio.api_components())
            if u.path == "/api/themes":
                return self._send(studio.api_themes())
            if u.path == "/api/data-files":
                _defaults_file()  # 确保 defaults 存在
                return self._send(studio.api_data_files())
            if u.path == "/compare":
                return self._send(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "compare.html"), "rb").read(),
                                  "text/html; charset=utf-8")
            if u.path == "/api/scan":
                """扫描本地项目组件 → 匹配库内候选。?path=<绝对路径>"""
                q = {k: v[0] for k, v in parse_qs(u.query).items()}
                p = q.get("path") or os.path.expanduser("~/demo-app")
                if not os.path.isdir(p):
                    return self._send({"error": f"path not found: {p}"}, code=404)
                import scanner
                return self._send(scanner.scan_project(p))
            if u.path.startswith("/raw/"):
                """原始文件（SVG 等非 React 组件直接渲染本体）"""
                cid = u.path[5:]
                m = manifest()
                it = next((i for i in m["items"] if i["id"] == cid), None)
                if not it:
                    return self._send(b"<html><body>not found: " + cid.encode() + b"</body></html>",
                                      "text/html; charset=utf-8", 404)
                fp = it["path"] if it.get("absolute") else os.path.join(ROOT, it["path"])
                if not os.path.exists(fp):
                    return self._send({"error": "file missing"}, code=404)
                ctype = "image/svg+xml" if fp.endswith(".svg") else "text/plain; charset=utf-8"
                return self._send(open(fp, "rb").read(), ctype)
            if u.path.startswith("/pg/"):
                cid = u.path[4:]
                q = {k: v[0] for k, v in parse_qs(u.query).items()}
                out = os.path.join(WORK, "previews", f"{cid}.html")
                # 旧版缓存（无 postMessage entry）自动失效重建
                if os.path.exists(out) and "pg-props" not in open(out).read():
                    os.remove(out)
                if not os.path.exists(out) or q.get("rebuild"):
                    try:
                        build(cid, q.get("theme"))
                    except Exception as e:
                        # build 失败只影响该组件，服务必须存活
                        return self._send(("<html><body style='font-family:monospace;padding:24px'>"
                                           "<h3>组件构建失败: %s</h3><pre>%s</pre></body></html>" % (cid, str(e)[:500])).encode(),
                                          "text/html; charset=utf-8", 500)
                html = open(out).read()
                if q.get("data") is not None:
                    import urllib.request as _ur
                    try:
                        data_json = json.loads(q["data"])
                        html = html.replace("<script>", "<script>window.__PG_DATA__=" + json.dumps(data_json, ensure_ascii=False).replace("</", "<\\/") + ";</script>", 1)
                    except Exception:
                        pass
                if q.get("theme"):
                    m = manifest()
                    t = next((i for i in m["items"] if i["id"] == q["theme"] and i["type"] == "theme"), None)
                    if t:
                        tp = t["path"] if t.get("absolute") else os.path.join(ROOT, t["path"])
                        html = re.sub(r"/\* 主题：.*?\*/\s*:root\s*\{.*?\}", open(tp).read(), html, count=1, flags=re.S)
                return self._send(html.encode(), "text/html; charset=utf-8")
            self.send_response(404); self.end_headers()

        def log_message(self, *a):
            pass

    _defaults_file()
    print(f"playground on http://127.0.0.1:{port}/studio  (Studio) | /pg/<id>?theme=<t>")
    HTTPServer(("127.0.0.1", port), H).serve_forever()


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "build"
    if cmd == "build":
        build(sys.argv[2], theme_id=sys.argv[sys.argv.index("--theme") + 1] if "--theme" in sys.argv else None)
    elif cmd == "serve":
        serve(int(sys.argv[2]) if len(sys.argv) > 2 else 8390)

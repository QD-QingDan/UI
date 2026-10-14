#!/usr/bin/env python3
"""主题工具：列出/查看/导出/自定义主题，供 agent 组装页面时调用。

用法：
  theme.py list                          # 列出所有主题
  theme.py show <id>                     # 查看主题 CSS
  theme.py export <id> [--out 文件]       # 导出 CSS（默认 stdout）
  theme.py custom --name "My" --primary "#xx" [--background #xx] [--radius 8px]
                                          [--base indigo-light]     # 生成自定义主题
  theme.py inject <id> <html文件>         # 把主题 CSS 注入 HTML <head>
"""
import json, os, sys, argparse, re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANIFEST = os.path.join(ROOT, "manifest.json")


def themes():
    m = json.load(open(MANIFEST))
    return [i for i in m["items"] if i["type"] == "theme"]


def resolve(it):
    return it["path"] if it.get("absolute") else os.path.join(ROOT, it["path"])


def get_theme(tid):
    it = next((t for t in themes() if t["id"] == tid), None)
    if not it:
        sys.exit(f"theme not found: {tid}")
    return it, open(resolve(it)).read()


def parse_vars(css):
    """从 :root 块提取变量 dict"""
    m = re.search(r":root\s*\{(.*?)\}", css, re.S)
    if not m:
        return {}
    return dict(re.findall(r"(--[\w-]+)\s*:\s*([^;]+);", m.group(1)))


def build_custom(name, overrides, base="indigo-light.css"):
    _, css = get_theme_by_file(base)
    vars_ = parse_vars(css)
    for k, v in overrides.items():
        key = k if k.startswith("--") else "--" + k
        if key in vars_ or key in ("--radius",):
            vars_[key] = v
        else:
            print(f"  (未知变量 {key}，仍写入)")
            vars_[key] = v
    lines = [f"/* 主题：{name}（自定义，基于 {base}） */", ":root {"]
    lines += [f"  {k}: {v};" for k, v in vars_.items()]
    lines.append("}")
    return "\n".join(lines) + "\n"


def get_theme_by_file(fn):
    p = os.path.join(ROOT, "themes", fn)
    if not os.path.exists(p):
        sys.exit(f"base theme not found: {fn}")
    it = {"id": "tmp", "path": p}
    return it, open(p).read()


def register(name, css):
    m = json.load(open(MANIFEST))
    tid = "theme-" + re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    if any(i["id"] == tid for i in m["items"]):
        sys.exit(f"theme id already exists: {tid}")
    fn = tid + ".css"
    open(os.path.join(ROOT, "themes", fn), "w").write(css)
    m["items"].append({
        "id": tid, "name": name, "type": "theme", "format": "css",
        "path": f"themes/{fn}", "tags": ["theme", "custom"],
        "description": f"自定义主题：{name}",
        "inject_when": ["主题", "theme", "换肤", "配色"],
        "source_ref": {"kind": "library"},
    })
    json.dump(m, open(MANIFEST, "w"), ensure_ascii=False, indent=2)
    print(json.dumps({"id": tid, "file": f"themes/{fn}"}, ensure_ascii=False))


def inject(tid, html_path):
    _, css = get_theme(tid)
    html = open(html_path).read()
    if "<!-- theme:stylesheet -->" in html:
        html = html.replace("<!-- theme:stylesheet -->", f"<style>\n{css}</style>")
    elif "</head>" in html:
        html = html.replace("</head>", f"<style>\n{css}</style>\n</head>")
    else:
        sys.exit("no </head> found")
    open(html_path, "w").write(html)
    print(f"injected {tid} -> {html_path}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["list", "show", "export", "custom", "inject"])
    ap.add_argument("arg", nargs="?", default=None)
    ap.add_argument("--out")
    ap.add_argument("--name")
    ap.add_argument("--base", default="indigo-light.css")
    ap.add_argument("--inject_to")
    a = ap.parse_args()

    if a.cmd == "list":
        for t in themes():
            print(f'{t["id"]:24s} {t["name"]:20s} {t.get("description","")}')
    elif a.cmd == "show":
        it, css = get_theme(a.arg)
        print(css)
    elif a.cmd == "export":
        it, css = get_theme(a.arg)
        if a.out:
            open(a.out, "w").write(css)
            print("exported ->", a.out)
        else:
            print(css)
    elif a.cmd == "custom":
        if not a.name:
            sys.exit("--name required")
        # 颜色参数全部走 stdin/env 避免参数表过长：--set primary=#xx background=#xx
        sets = {}
        for s in (a.inject_to or "").split(","):
            if "=" in s:
                k, v = s.split("=", 1)
                sets[k.strip()] = v.strip()
        css = build_custom(a.name, sets, a.base)
        register(a.name, css)
    elif a.cmd == "inject":
        if not a.arg or not a.inject_to:
            sys.exit("usage: theme.py inject <theme_id> --inject_to <html>")
        inject(a.arg, a.inject_to)


if __name__ == "__main__":
    main()

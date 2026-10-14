#!/usr/bin/env python3
"""多来源索引器：把三类外部素材索引进 manifest（不拷贝文件，只建引用）。

来源（config 字段 manifest["sources"]）：
  installed  — 系统已安装字体（fc-list）
  collected  — 采集目录（~/Downloads ~/Documents ~/Pictures，存在才扫）
  project    — 本地项目（config 列表，默认扫 ~/ 下非隐藏一级目录）

只索引设计相关文件：图片/SVG/字体/组件源码/设计文档。
用法：python3 scripts/index_sources.py [--dry]
"""
import json, os, subprocess, sys, hashlib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOME = os.path.expanduser("~")

# 索引哪些扩展名
DESIGN_EXTS = {
    ".svg", ".png", ".jpg", ".jpeg", ".webp", ".gif", ".ico", ".avif",
    ".ttf", ".otf", ".woff", ".woff2",
    ".tsx", ".jsx", ".vue", ".html", ".css",
    ".lottie", ".json",  # json 仅在项目根/组件目录时收（见过滤逻辑）
}
# 忽略的目录名
SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", ".next", "dist", "build", ".hermes", ".cache"}
MAX_SIZE = 8 * 1024 * 1024  # 8MB 以上不索引

MANIFEST = os.path.join(ROOT, "manifest.json")


def load_manifest():
    with open(MANIFEST) as f:
        return json.load(f)


def save_manifest(m):
    with open(MANIFEST, "w") as f:
        json.dump(m, f, ensure_ascii=False, indent=2)


def ensure_sources_config(m):
    if "sources" not in m:
        m["sources"] = {
            "installed": {"enabled": True},
            "collected": {"enabled": True,
                          "dirs": [os.path.join(HOME, d) for d in ("Downloads", "Documents", "Pictures")]},
            "project": {"enabled": True,
                        # 自动发现：~/ 下非隐藏、含 .git 或 src 的目录
                        "discover_from_home": True,
                        "dirs": []},
        }
    return m["sources"]


def is_design_file(path, in_component_dir=False):
    ext = os.path.splitext(path)[1].lower()
    if ext == ".json":
        return in_component_dir  # 只收组件目录里的 json
    return ext in DESIGN_EXTS


def discover_projects(cfg):
    roots = list(cfg.get("dirs", []))
    if cfg.get("discover_from_home"):
        for d in sorted(os.listdir(HOME)):
            p = os.path.join(HOME, d)
            if d.startswith(".") or not os.path.isdir(p):
                continue
            if p == ROOT or os.path.realpath(p) == os.path.realpath(ROOT):
                continue
            has_marker = os.path.isdir(os.path.join(p, ".git")) or os.path.isdir(os.path.join(p, "src"))
            if has_marker:
                roots.append(p)
    return roots


def index_project(root, dry=False):
    """返回 (条目列表, 扫描文件数)。每目录聚合为一条目（避免上千条目淹没 manifest）。"""
    entries, scanned = [], 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
        depth = dirpath[len(root):].count(os.sep)
        # 超过 4 层深处不进入
        if depth >= 4:
            dirnames[:] = []
            continue
        in_comp = any(f.endswith((".tsx", ".jsx", ".vue")) for f in filenames)
        hits = [f for f in filenames if is_design_file(f, in_comp)]
        if not hits:
            continue
        scanned += len(hits)
        rel = os.path.relpath(dirpath, HOME)
        name = os.path.basename(root) + (" · " + os.path.relpath(dirpath, root) if dirpath != root else "")
        e = {
            "id": "idx-" + hashlib.md5(rel.encode()).hexdigest()[:10],
            "name": name,
            "type": "component" if in_comp else "asset",
            "format": "dir",
            "path": os.path.relpath(dirpath, HOME),
            "tags": ["indexed", "project", os.path.basename(root)],
            "description": f"项目目录索引：{len(hits)} 个设计相关文件（{', '.join(sorted({os.path.splitext(f)[1] for f in hits}))}）",
            "preview": "dir",
            "source_ref": {"kind": "project", "root": root, "files": sorted(hits)[:30]},
        }
        entries.append(e)
    return entries, scanned


def index_installed_fonts(dry=False):
    r = subprocess.run(["fc-list"], capture_output=True, text=True)
    if r.returncode != 0:
        return [], 0
    entries = []
    for line in r.stdout.strip().split("\n"):
        if ":" not in line:
            continue
        path, fam = line.split(":", 1)
        fam = fam.split(":style=")[0].strip()
        ext = os.path.splitext(path)[1].lower()
        if ext not in (".ttf", ".otf", ".woff", ".woff2"):
            continue
        rel = path  # 系统路径用绝对路径
        e = {
            "id": "font-" + hashlib.md5(path.encode()).hexdigest()[:10],
            "name": fam,
            "type": "font",
            "format": ext.lstrip("."),
            "path": rel,
            "absolute": True,
            "tags": ["indexed", "installed", "font"],
            "description": f"系统已安装字体：{fam}",
            "preview": "font",
            "source_ref": {"kind": "installed", "fc_path": path},
        }
        entries.append(e)
    return entries, len(entries)


def index_collected(dirs, dry=False):
    entries, scanned = [], 0
    for d in dirs:
        if not os.path.isdir(d):
            continue
        for dirpath, dirnames, filenames in os.walk(d):
            dirnames[:] = [x for x in dirnames if x not in SKIP_DIRS]
            for f in filenames:
                if not is_design_file(f):
                    continue
                p = os.path.join(dirpath, f)
                try:
                    if os.path.getsize(p) > MAX_SIZE:
                        continue
                except OSError:
                    continue
                scanned += 1
                rel = p
                e = {
                    "id": "col-" + hashlib.md5(p.encode()).hexdigest()[:10],
                    "name": f,
                    "type": "asset",
                    "format": os.path.splitext(f)[1].lstrip("."),
                    "path": rel,
                    "absolute": True,
                    "tags": ["indexed", "collected"],
                    "description": f"采集素材：{os.path.relpath(p, d)}",
                    "preview": "file",
                    "source_ref": {"kind": "collected", "abs": p},
                }
                entries.append(e)
    return entries, scanned


def main():
    dry = "--dry" in sys.argv
    m = load_manifest()
    cfg = ensure_sources_config(m)
    managed_prefix = ("idx-", "font-", "col-")

    # 清掉旧索引条目（幂等）
    m["items"] = [i for i in m["items"] if not i["id"].startswith(managed_prefix)]
    base = len(m["items"])
    report = {}

    if cfg["installed"]["enabled"]:
        ents, n = index_installed_fonts()
        m["items"] += ents
        report["installed"] = n

    if cfg["collected"]["enabled"]:
        ents, n = index_collected(cfg["collected"]["dirs"])
        m["items"] += ents
        report["collected"] = n

    if cfg["project"]["enabled"]:
        roots = discover_projects(cfg["project"])
        total = 0
        for root in roots:
            ents, n = index_project(root)
            m["items"] += ents
            total += n
        report["project"] = total
        report["project_roots"] = roots

    print("base items:", base, "| indexed:", report)
    if not dry:
        save_manifest(m)
        print("manifest saved:", len(m["items"]), "items")
    else:
        print("(dry run, not saved)")


if __name__ == "__main__":
    main()

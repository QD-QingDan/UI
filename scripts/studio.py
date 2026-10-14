#!/usr/bin/env python3
"""studio.py — Playground Studio：数据→组件→主题 实时映射预览台。

功能：
  数据面板：组件默认 props / 自定义 JSON / 项目数据文件（~/assets/data/*.json）
  主题面板：库内主题 + 任意 CSS 变量即时改色
  布局面板：宽/中/窄 容器宽度
  预览区：postMessage 驱动 iframe，毫秒级热更新，无需 rebuild

服务端端点（由 playground.py serve 调用）：
  GET /studio           → 本页 HTML
  GET /api/components   → 组件清单（id/name/alias/stack/category/mock 数据）
  GET /api/themes       → 主题清单（id/name/css）
  GET /api/data-files   → ~/assets/data/*.json 列表 + 内容
"""
import json
import os
import re

ROOT = os.path.expanduser("~/assets")
WORK = os.path.join(ROOT, ".playground-work")
HERE = os.path.dirname(os.path.abspath(__file__))

# ---------------------------------------------------------------- API ----

def api_components():
    m = json.load(open(os.path.join(ROOT, "manifest.json")))
    out = []
    for it in m["items"]:
        if it["type"] != "component":
            continue
        out.append({
            "id": it["id"], "name": it.get("name"), "alias": it.get("alias"),
            "stack": it.get("stack"), "category": it.get("category"),
        })
    return out


def api_themes():
    m = json.load(open(os.path.join(ROOT, "manifest.json")))
    out = []
    for it in m["items"]:
        if it["type"] != "theme":
            continue
        p = it["path"] if it.get("absolute") else os.path.join(ROOT, it["path"])
        css = open(p).read()
        swatch = dict(re.findall(r"--([a-z-]+):\s*([^;]+);", css))
        out.append({"id": it["id"], "name": it.get("name", it["id"]), "css": css, "swatch": swatch})
    return out


def api_data_files():
    d = os.path.join(ROOT, "data")
    files = []
    if os.path.isdir(d):
        for fn in sorted(os.listdir(d)):
            if fn.endswith(".json"):
                try:
                    files.append({"file": fn, "data": json.load(open(os.path.join(d, fn)))})
                except Exception as e:
                    files.append({"file": fn, "error": str(e)})
    return files


# ---------------------------------------------------------------- HTML ----

def page():
    return open(os.path.join(HERE, "studio.html")).read()

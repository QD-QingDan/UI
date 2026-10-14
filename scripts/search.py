#!/usr/bin/env python3
"""素材库检索 CLI。用法：
  search.py "关键词" [--type prompt|spec|component] [--inject]   # 搜索条目
  search.py --get <id>                                          # 输出某条目文件内容
  search.py --inject "任务描述"                                  # 列出该任务应注入的 prompt/spec
"""
import sys, json, os, argparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def load():
    with open(os.path.join(ROOT, "manifest.json")) as f:
        return json.load(f)["items"]

def match(item, kw, typ, stack=None, cat=None):
    if typ and item["type"] != typ:
        return False
    if stack and (item["type"] != "component" or item.get("stack", "other") != stack):
        return False
    if cat and (item["type"] != "component" or item.get("category", "generic") != cat):
        return False
    if not kw:
        return True
    blob = " ".join([item.get("name",""), item.get("description",""),
                     " ".join(item.get("tags",[])), item.get("path","")]).lower()
    return kw.lower() in blob

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("query", nargs="?", default="")
    ap.add_argument("--type")
    ap.add_argument("--stack")
    ap.add_argument("--category")
    ap.add_argument("--alias-only", action="store_true")
    ap.add_argument("--inject", action="store_true")
    ap.add_argument("--get")
    args = ap.parse_args()

    items = load()

    if args.get:
        it = next((i for i in items if i["id"] == args.get), None)
        if not it:
            print(json.dumps({"error": "not found"})); return
        p = it["path"] if it.get("absolute") else os.path.join(ROOT, it["path"])
        if not os.path.exists(p):
            print(json.dumps({"item": it, "content": None, "error": "file missing", "path": p}, ensure_ascii=False))
            return
        if it.get("type") in ("font", "asset") or os.path.splitext(p)[1].lower() in (
                ".ttf", ".otf", ".woff", ".woff2", ".png", ".jpg", ".jpeg", ".webp", ".gif", ".ico", ".avif"):
            # 二进制/媒体文件不读文本，只返回元数据
            print(json.dumps({"item": it, "content": None, "binary": True, "path": p}, ensure_ascii=False))
            return
        print(json.dumps({"item": it, "content": open(p).read()}, ensure_ascii=False))
        return

    if args.inject:
        hits = [i for i in items if i["type"] in ("prompt", "spec")
                and any(kw.lower() in args.query.lower() for kw in i.get("inject_when", []))]
        print(json.dumps(hits, ensure_ascii=False, indent=2))
        return

    hits = [i for i in items if match(i, args.query, args.type, args.stack, args.category)]
    if args.alias_only:
        print(json.dumps([{ "id": i["id"], "alias": i.get("alias"), "name": i["name"]} for i in hits], ensure_ascii=False, indent=1))
        return
    print(json.dumps(hits, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()

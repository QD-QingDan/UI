#!/usr/bin/env python3
"""scanner.py — 本地项目组件扫描器 + 库内组件匹配。

用法（由 playground.py serve 调用）：
  scan_project(path) → [{name, file, kind, keywords, matches: [{id, alias, score, why}]}]

匹配逻辑（可解释打分，无魔法）：
  名称 token 与 manifest 条目的 alias/tags/name/description 做交集，
  同义词表扩展（card↔卡片、hero↔横幅/首屏、faq↔问答…），
  命中 alias 最高分，tags 次之，description 最低。
"""
import json
import os
import re

ROOT = os.path.expanduser("~/assets")

# 同义词表：项目命名 → 库内检索词
SYNONYMS = {
    "card": ["card", "卡片"],
    "pricing": ["pricing", "价格", "定价"],
    "price": ["pricing", "价格"],
    "hero": ["hero", "横幅", "首屏", "banner"],
    "banner": ["hero", "横幅", "banner"],
    "faq": ["faq", "问答", "常见问题"],
    "question": ["faq", "问答"],
    "cta": ["cta", "行动号召", "转化"],
    "button": ["button", "按钮", "icon"],
    "btn": ["button", "按钮"],
    "icon": ["icon", "图标"],
    "avatar": ["avatar", "头像"],
    "nav": ["nav", "导航", "navbar", "header"],
    "navbar": ["nav", "导航", "navbar"],
    "header": ["nav", "导航", "header", "hero"],
    "footer": ["footer", "页脚"],
    "chat": ["chat", "聊天", "chatbot", "客服"],
    "message": ["chat", "聊天", "消息"],
    "form": ["form", "表单", "input"],
    "input": ["input", "输入", "form"],
    "search": ["search", "搜索", "command"],
    "tab": ["tabs", "标签页", "tab"],
    "tabs": ["tabs", "标签页"],
    "table": ["table", "表格"],
    "list": ["list", "列表"],
    "testimonial": ["testimonial", "评价", "推荐语"],
    "logo": ["logo", "图标", "icon"],
    "login": ["login", "登录", "auth"],
    "signup": ["signup", "注册", "auth"],
    "stats": ["stats", "统计", "数字"],
    "team": ["team", "团队"],
    "footer": ["footer", "页脚"],
    "steps": ["steps", "步骤"],
    "timeline": ["timeline", "时间线"],
    "newsletter": ["newsletter", "订阅", "cta"],
    "toast": ["toast", "提示"],
    "modal": ["modal", "弹窗", "dialog"],
    "dialog": ["modal", "弹窗"],
    "loading": ["loading", "加载", "spinner"],
    "spinner": ["loading", "加载"],
    "toggle": ["toggle", "开关"],
    "switch": ["toggle", "开关"],
    "badge": ["badge", "徽标"],
    "tag": ["badge", "标签", "badge"],
    "upload": ["upload", "上传"],
    "copy": ["copy", "复制"],
    "slider": ["slider", "滑动"],
    "carousel": ["carousel", "轮播"],
    "gallery": ["gallery", "画廊", "图片"],
    "contact": ["contact", "联系", "cta"],
    "about": ["about", "关于"],
    "feature": ["feature", "特性", "功能"],
    "features": ["feature", "特性", "功能"],
    "dashboard": ["dashboard", "面板"],
    "sidebar": ["sidebar", "侧栏", "nav"],
    "menu": ["menu", "菜单", "nav"],
    "dropdown": ["dropdown", "下拉", "menu"],
    "accordion": ["accordion", "折叠", "faq"],
    "calendar": ["calendar", "日历"],
    "chart": ["chart", "图表"],
}


def _tokens(name):
    """PascalCase/kebab/snake → 小写 token 列表"""
    return [t for t in re.split(r"(?<!^)(?=[A-Z])|[-_.\s]", name) if t]


def manifest_items():
    m = json.load(open(os.path.join(ROOT, "manifest.json")))
    return m["items"]


def match_component(name, items, top=5):
    """组件名 → 库内候选（打分排序 + 命中原因）"""
    toks = [t.lower() for t in _tokens(name)]
    expanded = set()
    for t in toks:
        expanded.add(t)
        expanded.update(SYNONYMS.get(t, []))

    scored = []
    for it in items:
        if it.get("type") != "component":
            continue
        score, why = 0, []
        hay_alias = (it.get("alias") or "").lower()
        alias_toks = set(_tokens(it.get("alias") or ""))
        tags = [t.lower() for t in (it.get("tags") or [])]
        desc = (it.get("description") or "").lower()
        name_l = (it.get("name") or "").lower()

        for t in expanded:
            if t in alias_toks:
                score += 5; why.append(f"alias≈{t}")
            elif any(t in tg for tg in tags):
                score += 3; why.append(f"tag≈{t}")
            elif t in name_l:
                score += 2; why.append(f"name≈{t}")
            elif t in desc:
                score += 1; why.append(f"desc≈{t}")
        if score:
            scored.append({"id": it["id"], "alias": it.get("alias"),
                           "stack": it.get("stack"), "category": it.get("category"),
                           "score": score, "why": sorted(set(why))[:3]})
    scored.sort(key=lambda x: -x["score"])
    return scored[:top]


def scan_project(path, top=5):
    """扫描项目：React(Vue) 组件文件 → 组件名 + 匹配候选。跳过 node_modules/.git/dist/build。"""
    skip = {"node_modules", ".git", "dist", "build", ".next", ".output", "coverage", ".venv"}
    results = []
    for root, dirs, files in os.walk(path):
        dirs[:] = [d for d in dirs if d not in skip and not d.startswith(".")]
        for fn in files:
            if not fn.endswith((".tsx", ".jsx", ".vue")):
                continue
            fp = os.path.join(root, fn)
            rel = os.path.relpath(fp, path)
            try:
                src = open(fp, encoding="utf-8", errors="ignore").read()
            except Exception:
                continue
            # 组件定义名（export function/const/class X extends）
            names = set(re.findall(r"export (?:default )?(?:function|const|class) ([A-Z]\w*)", src))
            names.update(re.findall(r"export default function ([A-Z]\w*)", src))
            # 文件名本身也是候选（PageCard.tsx）
            stem = os.path.splitext(fn)[0]
            if stem and stem not in ("index", "App", "main"):
                names.add(stem)
            for n in sorted(names):
                results.append({
                    "name": n, "file": rel,
                    "kind": "vue" if fn.endswith(".vue") else "react",
                    "matches": match_component(n, manifest_items(), top),
                })
    return results

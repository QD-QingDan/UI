#!/usr/bin/env python3
"""把 manifest + 素材内容内联进 preview.html（静态单文件，无服务、无 CORS 问题）。
每次库内容变化后跑一次：python3 scripts/build_preview.py

支持来源筛选：library（库内）/ installed（已安装）/ collected（采集）/ project（项目索引）
二进制/大文件不内联，字体每家族取一个样本做 base64 预览。
"""
import json, os, base64

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

with open(os.path.join(ROOT, "manifest.json")) as f:
    manifest = json.load(f)

TEXT_EXTS = {".svg", ".tsx", ".jsx", ".vue", ".html", ".css", ".md", ".txt", ".json", ".py"}
FONT_EXTS = {".ttf", ".otf", ".woff", ".woff2"}

# 内联全部主题 CSS（预览页换肤用）
THEMES = {}
TAXONOMY = manifest.get("taxonomy", {})
for it in manifest["items"]:
    if it["type"] == "theme":
        p = it["path"] if it.get("absolute") else os.path.join(ROOT, it["path"])
        if os.path.exists(p):
            THEMES[it["id"]] = {"name": it["name"], "css": open(p).read()}

def resolve(it):
    return it["path"] if it.get("absolute") else os.path.join(ROOT, it["path"])

def src_of(it):
    if it.get("source_ref"):
        return it["source_ref"]["kind"]          # installed / collected / project
    p = it["id"].split("-")[0]
    return None if p in ("comp", "prompt", "spec") else p   # watermelon / boardui

# ---- 内联策略 ----
items = []
font_seen_fam = set()
inline_budget = 12_000  # 单文件内联上限（字符）
for it in manifest["items"]:
    out = dict(it)
    out["_src"] = src_of(it) or "library"
    p = resolve(it)
    ext = os.path.splitext(p)[1].lower()
    out["_inline"] = None
    out["_b64"] = None
    out["_exists"] = os.path.exists(p)
    if out["_exists"]:
        size = os.path.getsize(p)
        if ext in FONT_EXTS and it["type"] == "font":
            fam = it["name"]
            if fam not in font_seen_fam and size < 800_000:
                font_seen_fam.add(fam)
                try:
                    out["_b64"] = base64.b64encode(open(p, "rb").read()).decode()
                except Exception:
                    pass
        elif ext in TEXT_EXTS and size < inline_budget:
            try:
                out["_inline"] = open(p, encoding="utf-8", errors="replace").read()
            except Exception:
                pass
    if it.get("extra_files"):
        for ef in it["extra_files"]:
            fp = ef if os.path.isabs(ef) else os.path.join(ROOT, ef)
            e2 = os.path.splitext(fp)[1].lower()
            if e2 in TEXT_EXTS and os.path.exists(fp) and os.path.getsize(fp) < inline_budget:
                try:
                    out["_inline_extra"] = {"path": ef, "content": open(fp, encoding="utf-8", errors="replace").read()}
                except Exception:
                    pass
                break
    items.append(out)

data = json.dumps(items, ensure_ascii=False)
themes_json = json.dumps(THEMES, ensure_ascii=False)

page = """<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
<title>素材库预览</title>
<style>
  :root { color-scheme: light; }
  body { font-family: system-ui, sans-serif; margin: 0; padding: 24px; background: var(--background, #fafafa); color: var(--foreground, #1e293b); }
  h1 { font-size: 20px; margin: 0 0 4px; }
  .sub { color: #64748b; font-size: 13px; margin-bottom: 16px; }
  .toolbar { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 10px; align-items: center; }
  .toolbar button { border: 1px solid var(--border, #cbd5e1); background: var(--card, #fff); color: inherit; border-radius: 999px; padding: 4px 12px; font-size: 12.5px; cursor: pointer; }
  .toolbar button.active { background: var(--primary, #4f46e5); color: var(--primary-foreground, #fff); border-color: var(--primary, #4f46e5); }
  .toolbar button:hover:not(.active) { border-color: var(--primary, #4f46e5); color: var(--primary, #4f46e5); }
  .tbsep { border-left: 1px solid #e2e8f0; height: 18px; }
  #search { width: 220px; padding: 6px 12px; border: 1px solid var(--input, #cbd5e1); background: var(--card, #fff); color: inherit; border-radius: 8px; font-size: 13px; }
  #count { font-size: 12.5px; color: #64748b; margin-left: auto; }
  .tagbar { display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 20px; max-height: 88px; overflow-y: auto; }
  .tagbar button { border: 1px solid var(--border, #e2e8f0); background: var(--card, #fff); border-radius: 6px; padding: 2px 9px; font-size: 11.5px; cursor: pointer; color: var(--muted-foreground, #475569); }
  .tagbar button.active { background: var(--accent, #eef2ff); border-color: var(--primary, #4f46e5); color: var(--primary, #4f46e5); }
  .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 16px; }
  .card { background: var(--card, #fff); border: 1px solid var(--border, #e2e8f0); border-radius: var(--radius, 8px); padding: 14px; box-shadow: 0 1px 2px rgba(0,0,0,.04); }
  .type { font-size: 11px; background: var(--accent, #eef2ff); color: var(--accent-foreground, #4f46e5); border-radius: 4px; padding: 2px 6px; }
  .type.src { background: #f0fdf4; color: #15803d; }
  .type.warn { background: #fef2f2; color: #b91c1c; }
  .name { font-weight: 600; margin: 8px 0 4px; }
  .desc { font-size: 12.5px; color: #475569; }
  .tags { margin-top: 8px; } .tags span { font-size: 11px; color: #64748b; background: #f1f5f9; border-radius: 4px; padding: 1px 6px; margin-right: 4px; cursor: pointer; }
  .tags span:hover { color: #4f46e5; }
  pre.body { white-space: pre-wrap; font-size: 11.5px; background: var(--muted, #f8fafc); color: var(--foreground, #1e293b); padding: 8px; border-radius: 6px; max-height: 200px; overflow: auto; margin: 10px 0 0; }
  .svgwrap { font-size: 40px; color: #4f46e5; margin-top: 10px; }
  .svgwrap svg { width: 48px; height: 48px; }
  .fontprev { margin-top: 10px; padding: 10px; border: 1px dashed #e2e8f0; border-radius: 6px; }
  .fontprev .f1 { font-size: 20px; } .fontprev .f2 { font-size: 14px; color: #64748b; }
  .files { margin-top: 8px; font-size: 11px; color: #94a3b8; word-break: break-all; }
  .empty { color:#f59e0b; font-size: 11px; }
</style>
</head>
<body>
<h1>📦 本地素材库</h1>
<div class="sub">manifest 驱动 · 三来源索引（已安装 / 采集 / 项目）+ 库内组件 · 数据内联</div>
<div class="toolbar">
  <input id="search" placeholder="搜索名称 / 描述 / 标签…">
  <button data-t="" class="active">全部</button>
  <button data-t="component">组件</button>
  <button data-t="prompt">提示词</button>
  <button data-t="spec">规范</button>
  <button data-t="font">字体</button>
  <button data-t="asset">素材</button>
  <span class="tbsep"></span>
  <button data-s="">来源:全部</button>
  <button data-s="library">库内</button>
  <button data-s="installed">已安装</button>
  <button data-s="collected">采集</button>
  <button data-s="project">项目</button>
  <span id="count"></span>
</div>
<div class="toolbar" id="stackbar" style="margin-bottom:8px">
  <span style="font-size:12px;color:#64748b">🧩 设计语言：</span>
</div>
<div class="toolbar" id="catbar" style="margin-bottom:8px">
  <span style="font-size:12px;color:#64748b">📂 分类：</span>
</div>
<div class="toolbar" id="themebar" style="margin-bottom:16px">
  <span style="font-size:12px;color:#64748b">🎨 主题：</span>
</div>
<div class="tagbar" id="tagbar"></div>
<div class="grid" id="grid"></div>
<script>
const ITEMS = __DATA__;
const esc = s => String(s ?? '').replace(/[&<>]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
let type = '', tag = '', src = '';
const TAGS = {};
ITEMS.forEach(i => (i.tags||[]).forEach(t => TAGS[t] = (TAGS[t]||0)+1));
const tagList = Object.entries(TAGS).sort((a,b) => b[1]-a[1]).slice(0, 40);
function render() {
  const q = document.getElementById('search').value.toLowerCase();
  const hits = ITEMS.filter(it =>
    ((stack || cat) ? it.type === 'component' : true) &&
    (!type || it.type === type) &&
    (!src || it._src === src) &&
    (!stack || (it.stack||'other') === stack) &&
    (!cat || (it.category||'generic') === cat) &&
    (!tag || (it.tags||[]).includes(tag)) &&
    (!q || (it.name + ' ' + (it.description||'') + ' ' + (it.tags||[]).join(' ') + ' ' + it.id + ' ' + it.path).toLowerCase().includes(q))
  );
  document.getElementById('count').textContent = `${hits.length} / ${ITEMS.length} 条`;
  document.getElementById('grid').innerHTML = hits.map(it => {
    let body = '';
    if (it.format === 'svg' && it._inline) body = `<div class="svgwrap">${it._inline}</div>`;
    else if (it.type === 'font' && it._b64) {
      const url = `data:font/${it.format};base64,${it._b64}`;
      body = `<div class="fontprev" style="font-family:'${esc(it.name)}'">
        <style>@font-face{font-family:'${esc(it.name)}';src:url('${url}');}</style>
        <div class="f1">Design 效果预览 123</div>
        <div class="f2">The quick brown fox jumps over the lazy dog</div>
      </div>`;
    }
    else if (it._inline) body = `<pre class="body">${esc(it._inline.slice(0, 500))}</pre>`;
    const nf = (it.extra_files||[]).length;
    const warn = !it._exists ? `<span class="type warn" style="margin-left:4px">missing</span>` : '';
    return `<div class="card">
      <span class="type">${esc(it.type)}</span>
      <span class="type src" style="margin-left:4px">${esc(it._src)}</span>
      ${warn}
      <div class="name">${esc(it.name)}</div>
      <div class="desc">${esc(it.description || '')}</div>
      <div class="tags">${(it.tags||[]).map(t=>`<span data-tag="${esc(t)}">${esc(t)}</span>`).join('')}</div>
      ${nf ? `<div class="files">+${nf} 个附加文件</div>` : ''}
      <div class="files">📁 ${esc(it.path)}</div>
      ${body}
    </div>`;
  }).join('') || '<div style="color:#94a3b8">无匹配条目</div>';
  document.querySelectorAll('.tags span').forEach(s => s.onclick = () => {
    tag = s.dataset.tag === tag ? '' : s.dataset.tag;
    syncTagbar(); render();
  });
}
function syncTagbar() {
  document.querySelectorAll('.tagbar button').forEach(b =>
    b.classList.toggle('active', b.dataset.tag === tag));
}
const bar = document.getElementById('tagbar');
bar.innerHTML = tagList.map(([t, n]) =>
  `<button data-tag="${esc(t)}">${esc(t)} <span style="opacity:.5">${n}</span></button>`).join('');
bar.querySelectorAll('button').forEach(b => b.onclick = () => {
  tag = b.dataset.tag === tag ? '' : b.dataset.tag;
  syncTagbar(); render();
});
const THEMES = __THEMES__;
// 主题切换器
const tb = document.getElementById('themebar');
Object.entries(THEMES).forEach(([id, t], idx) => {
  const b = document.createElement('button');
  b.textContent = t.name;
  if (idx === 0) b.classList.add('active');
  b.onclick = () => {
    let el = document.getElementById('theme-style');
    if (!el) { el = document.createElement('style'); el.id = 'theme-style'; document.head.appendChild(el); }
    el.textContent = t.css;
    tb.querySelectorAll('button').forEach(x => x.classList.toggle('active', x === b));
  };
  tb.appendChild(b);
});
const TAXONOMY = __TAXONOMY__;
let stack = '', cat = '';
// 设计语言导航（含条目计数；非标 stack 标记）
const sb = document.getElementById('stackbar');
const stackCounts = {};
ITEMS.forEach(i => { if (i.type === 'component') stackCounts[i.stack || 'other'] = (stackCounts[i.stack||'other']||0)+1; });
const stackDefs = (TAXONOMY.stacks || {});
const stackKeys = [...new Set([...Object.keys(stackCounts), ...Object.keys(stackDefs)])];
[['', '全部']].concat(stackKeys.map(k => [k, (stackDefs[k]||{}).label || k])).forEach(([k, label], idx) => {
  const b = document.createElement('button');
  const std = k === '' || (stackDefs[k]||{}).standard !== false;
  b.innerHTML = esc(label) + (k ? ` <span style="opacity:.5">${stackCounts[k]||0}</span>` : ` <span style="opacity:.5">${stackCounts[k]||0}</span>`) + (std ? '' : ' <span style="color:#f59e0b">†</span>');
  if (idx === 0) b.classList.add('active');
  b.dataset.stack = k;
  b.onclick = () => { stack = k; cat = ''; sb.querySelectorAll('button').forEach(x => x.classList.toggle('active', x === b)); renderCatbar(); render(); };
  sb.appendChild(b);
});
// 分类导航（只显示有内容的分类，跟随 stack 过滤）
const cb = document.getElementById('catbar');
const CATS = TAXONOMY.categories || [];
function renderCatbar() {
  const pool = ITEMS.filter(i => i.type === 'component' && (!stack || (i.stack||'other') === stack));
  cb.innerHTML = '<span style="font-size:12px;color:#64748b">📂 分类：</span>';
  [['', '全部']].concat(CATS.map(c => [c, c])).forEach(([k, label]) => {
    const n = pool.filter(i => (i.category||'generic') === k).length;
    if (k && !n) return;
    const b = document.createElement('button');
    b.innerHTML = esc(label) + ` <span style="opacity:.5">${n}</span>`;
    b.dataset.cat = k;
    if (cat === k) b.classList.add('active');
    b.onclick = () => { cat = k; renderCatbar(); render(); };
    cb.appendChild(b);
  });
}
renderCatbar();
document.getElementById('search').addEventListener('input', render);
document.querySelectorAll('.toolbar button[data-t]').forEach(b => b.onclick = () => {
  type = b.dataset.t;
  document.querySelectorAll('.toolbar button[data-t]').forEach(x => x.classList.toggle('active', x === b));
  render();
});
document.querySelectorAll('.toolbar button[data-s]').forEach(b => b.onclick = () => {
  src = b.dataset.s;
  document.querySelectorAll('.toolbar button[data-s]').forEach(x => x.classList.toggle('active', x === b));
  render();
});
render();
</script>
</body>
</html>"""

page = page.replace("__DATA__", data).replace("__THEMES__", themes_json).replace("__TAXONOMY__", json.dumps(TAXONOMY, ensure_ascii=False))
out = os.path.join(ROOT, "preview.html")
with open(out, "w") as f:
    f.write(page)
n_b64 = sum(1 for i in items if i["_b64"])
print("built", out, f"{len(page)} bytes, {len(items)} items, {n_b64} font previews")

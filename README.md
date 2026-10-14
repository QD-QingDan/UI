# local-asset-library

本地、免费、可被 AI/agent 调用的前端素材与组件库（Eagle 替代方案）。

## 结构

- `components/` — React+Tailwind 组件（Watermelon UI / BoardUI registry 拉取）、SVG 图标
- `fonts/` `specs/` `prompts/` `themes/` `motions/` `data/` — 字体/规范/prompt/主题/动效/项目数据
- `manifest.json` — 唯一索引（id/alias/tags/stack/category/source/dependencies）

## 脚本（scripts/）

| 脚本 | 用途 |
|---|---|
| `search.py` | CLI 检索：`search.py "pricing" [--alias-only] [--get id]` |
| `server.py` | 检索 HTTP API :8321（`/search` `/item` `/file` `/inject`） |
| `playground.py` | 组件真实渲染：`serve 8390` 后 `/studio` `/compare` `/pg/<id>` |
| `scanner.py` | 扫描本地项目组件并与库匹配（同义词表 + 可解释打分） |
| `build_preview.py` | 构建单文件静态预览页 |
| `theme.py` | 主题 list/show/export/custom/inject |
| `index_sources.py` | 三来源索引器（字体/采集/项目） |
| `up.sh` | 服务保活（幂等） |

## 快速开始

```bash
bash scripts/up.sh                # 启动（幂等）
open http://127.0.0.1:8390/       # 工作台入口
```

- Studio（数据→组件→主题映射预览）：`/studio`
- 组件对比台：`/compare`

# 组件命名规范（硬约束，生成代码前注入）

## 命名来源规则

从素材库引用组件时，**必须沿用库内 `alias` 作为项目中的组件名/文件名/CSS 类名前缀**，禁止随意改名。
通过 `search.py --get <id>` 或 HTTP `/item?id=` 获取条目的 `alias` 字段。

## alias 结构

```
<语义域>-<元素>-<变体?>
```

- **语义域**：组件所在区块或功能域（hero / pricing / cta / faq / nav / form / feedback / motion / loading）
- **元素**：它是什么（section / card / button / tabs / spinner / skeleton）
- **变体**（可选）：区分同域同类（v2 / dark / compact）

## 应用规则

| 场景 | 命名 |
|---|---|
| React 组件名 | alias 的 PascalCase：`pricing-card` → `PricingCard` |
| 组件文件名 | alias 原样 kebab-case：`pricing-card.tsx` |
| 区块容器 id | alias：`<section id="pricing-card">` |
| CSS 类名前缀 | alias 缩写域：`pc-*` 不推荐；直接用 Tailwind utility，语义锚点用 data 属性 `data-alias="pricing-card"` |
| 动效变量 | `--motion-<名称>`：如 `--motion-enter`、`--motion-duration` |
| 加载状态名 | `loading-<元素>`：`loading-hero`、`loading-pricing` |

## 动效命名

| 动效 | 名称 | 用途 |
|---|---|---|
| fade-up | `motion-fade-up` | 区块进场（配合 IntersectionObserver） |
| fade-in | `motion-fade-in` | 通用淡入 |
| stagger | `motion-stagger` | 列表/网格逐项进场（子项 delay 递增） |
| shimmer | `loading-shimmer` | 骨架屏流光 |
| pulse | `loading-pulse` | 骨架屏呼吸 |
| spinner | `loading-spinner` | 圆环加载 |

规则：动效类名加在元素上（如 `class="motion-fade-up"`），时长/曲线用 CSS 变量统一控制：

```css
:root {
  --motion-duration: 600ms;
  --motion-ease: cubic-bezier(0.16, 1, 0.3, 1);  /* ease-out-expo */
  --motion-delay-step: 80ms;                      /* stagger 步长 */
}
```

## 一致性检查

生成页面后自查：
1. 每个引用库内组件的位置，`data-alias` 是否等于库内 alias？
2. 动效类名是否都来自上表，没有自造名？
3. 时长/曲线是否走 CSS 变量，无硬编码毫秒数？

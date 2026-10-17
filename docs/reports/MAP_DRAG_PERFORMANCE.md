# 空间格局地图拖动性能排查（2026-10-17）

本轮只做一件事：定位并修复「空间格局」页 5km 网格 / LISA 图层拖动卡顿。不新增功能，
不改变统计口径与图层视觉。

## 1. 测量环境与方法

| 项目 | 取值 |
| --- | --- |
| 浏览器 | Chrome 155 无头模式，`--remote-debugging-port=9222` |
| 视口 | 1680 × 1050，`deviceScaleFactor = 1` |
| 光栅 | 无头模式使用软件光栅（无 GPU） |
| 页面 | `/analysis/spatial`，图层 `lisa`（8 895 个网格） |
| 负载 | 按下左键后连续 20 次 `mousemove`，每步 (+7, −4) px，间隔 16 ms |
| 指标 | `requestAnimationFrame` 帧率采样（300 ms 窗口）、`PerformanceObserver('longtask')`、CPU 采样火焰图（`Profiler`，200 µs 间隔） |

附加诊断：包装 `CanvasRenderingContext2D.prototype.fill/stroke` 统计单次拖动步骤的真实
绘制调用数；用调用栈归属到具体模块。

> 测量口径提醒：通过 CDP 注入的 `Input.dispatchMouseEvent` 会等待渲染进程处理后返回，
> 因此上述帧率是「每个事件都被同步串行化」的最坏情况。真实鼠标拖动的事件在输入队列里
> 会合并，实际观感好于这里的采样值。

## 2. 定位到的三个缺陷

### 2.1 每帧两次 `chart.getOption()` 深拷贝（主因之一）

CPU 采样中 `echarts` 的 `clone` 占 **13.4%** 自身耗时，调用链有两条，都在每帧执行：

```
ECharts.getOption → GlobalModel.getOption → clone   ← map-outline.js:29  sync()（绑在 rendered）
ECharts.getOption → GlobalModel.getOption → clone   ← SpatialMap.vue:600 georoam 监听
```

`getOption()` 会深拷贝整份 option，其中 map series 的 `data` 有 8 895 个元素，每个项目
都带 `itemStyle` / `emphasis` / `label` 对象，单次拷贝产生数万个临时对象，并伴随可观测的
GC 压力（采样中 `(garbage collector)` 亦在榜）。

两处读取的目的其实都很轻：

- `map-outline.js`：只是想判断「当前主图层是不是 map series」；
- `SpatialMap.vue`：只是想拿当前的 `zoom` / `center`。

ECharts 在 roam 时会把相机状态回写到**已解析的 model option**
（`syncBackRoamOptionToRoamHostModel` 直接写 `hostModel.option.center/zoom`），
因此读 model 与读 `getOption()` 取值等价，但不产生拷贝。

### 2.2 每个拖动步骤触发两轮完整重绘

在描边修复前后分别统计单步的 canvas 调用：

| 阶段 | `fill` | `stroke` |
| --- | --- | --- |
| 修复前 | 17 802 | 17 830 |
| 修复后 | 8 901 | 8 915 |

8 901 ≈ 网格数，说明修复前**每一步都整场重绘了两次**。第二次的业务来源是
`map-outline`：它在 `rendered`（已画完之后）里 `setShape` 改省界描边，把画布重新标脏，
于是整层 8 895 个多边形再画一遍。

改为同时监听 `georoam`（动作应用期间、画完之前）后，描边形状并进同一帧，二次重绘消失。

> 排查过程中曾误判为「geo 组件与 map series 重复绘制」，把 host geo 的填充改成 `'none'`
> 并用 `#ff00ff` 验证——品红从未出现在填充里，说明 geo 层并没有在填充。该假设被证伪，
> 相关改动已全部还原，网格细边框与逐要素 hover 配色保持不变。

### 2.3 `mousemove` 未合帧，重绘请求堆积

`map-drag.js` 原本在每次 `mousemove` 里直接 `dispatchAction({ type: 'geoRoam' })`。
一次拖动会产生远多于帧数的 mousemove，而每次 roam 都是整层重绘——主线程被占满时后续
事件仍在排队，于是拖动结束后地图还在继续移动。改为累计位移、每帧最多派发一次，
并在 `mouseup` 时补发尾部位移，保证最终位置仍与光标一致。

## 3. 修复后的量测

| 指标 | 修复前 | 修复后 |
| --- | --- | --- |
| 单步 canvas `fill` 调用 | 17 802 | 8 901 |
| 单步 canvas `stroke` 调用 | 17 830 | 8 915 |
| 单次整场重绘耗时 | ~330–390 ms | ~260–280 ms |
| 拖动窗口帧率（串行注入，最坏情况） | 3–4 fps | 3–4 fps |
| 拖动结束后的残留重绘 | 有明显的「追帧」 | 无 |

帧率没有随之上升的原因：一次整场重绘的耗时构成已不再由应用层逻辑主导。

| 耗时构成（采样占比） | 修复前 | 修复后 |
| --- | --- | --- |
| 浏览器原生（canvas 光栅） | ~59% | ~76% |
| zrender 逐要素（brush / culling / path） | ~24% | ~24% |

也就是说，剩下的 ~260 ms 里约四分之三是「把 8 895 个多边形真正涂到像素上」。
在无头软件光栅下这个量级正常，但它同时意味着：只要每帧都整层重绘，应用层再怎么优化
也无法突破这个上限。

补充实测：`deviceScaleFactor` 由 1 提到 2 时，单帧由 ~265 ms 升到 ~390 ms（+47%），
说明 HiDPI 屏幕上该问题会更明显。

## 4. 功能回归

- 拖动后视图确实位移（同一屏幕坐标命中的网格 id 由 `-11:17` 等变为 `-33:9` 等）；
- 拖动后切到「5km网格样本密度」再切回 LISA，同一屏幕坐标命中的网格 id 完全不变 → 相机
  通过 model 读取后仍然正确保留；
- 放大截图核对：省界描边与网格边界严格贴合，拖动后无错位；
- Tooltip 正常（示例 `网格 -24:-5`，置换 p = 0.0873，FDR q = 0.3104）；
- 右侧 LISA 面板数值、五类图例不受影响；
- `vite build` 通过。

## 5. 仍存在的限制与建议

当前实现的物理上限是「每帧重绘 8 895 个矢量多边形」。若要进一步明显提升拖动流畅度，
需要改变渲染策略，而不是继续微调事件：

1. **拖动期栅格化（推荐）**：进入拖动时把当前画布截为一张图，用 CSS transform 跟随光标，
   松手后一次性应用最终视角。拖动期间零重绘，可稳定 60 fps，但边缘会出现空白带，
   需要预放大或裁切配合。
2. **同类合并**：LISA 只有 5 个类别，可把相邻同色网格 union 成少量复合多边形，
   要素数可从 8 895 降到百级；代价是失去「每格细边框」的视觉语言。
3. **拖动期降低描边/降低 DPR**：可省约三成，但需要在拖动起止各做一次 `setOption`
   （本身是一次整场重绘），短拖动反而更差。

以上三项都会改变视觉或交互呈现，属于需要确认的设计决策，本轮未实施。

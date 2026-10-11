# 两级地图与图层

## 官方可视化 API

- [地图 JS API 2.0 总览](https://lbs.amap.com/api/jsapi-v2/summary)
- [JS API 2.0 参考手册：HeatMap](https://lbs.amap.com/api/jsapi-v2/documentation#heatmap)
- [LOCA 数据可视化 API 2.0](https://lbs.amap.com/api/loca-v2)

当前项目通过 `@amap/amap-jsapi-loader` 加载 JS API 2.0、`AMap.HeatMap` 插件和 LOCA 2.0。市州地图的 LOCA 散点图层复用后端返回的站点坐标，并通过 GeoJSON 数据源渲染；原 POI 热力图保持不变。这里的 JS API/LOCA 是地图渲染与可视化能力，不是提供充电站业务数据的接口。

全省总览使用真实湖南GeoJSON与ECharts，按POI样本数量分级设色；Hover展示市州样本数和占比，排名与指标联动，点击进入市州。

市州与区县使用高德JS API 2.0，根据范围或bbox读取真实数据库站点。默认点聚合；Marker最多500条，超过限制提示缩小范围；热力图是等权POI聚集度，不是需求或容量。区县边界、缩放、全屏和信息窗共用真实行政配置。API分页是传输方式，不在地图提供列表翻页。

空间格局支持密度、5km网格、描述性热点、1km直线样本覆盖；可达性页展示区县代表点道路观测和低可达性清单。区县选择切换为高德实景地图，筛选和URL上下文保留。

地图与图表导出保留来源、口径和时间；加载失败显示错误，不提供模拟站点回退。仅有代表点道路结果，不提供人口等时圈、供需或选址图层。

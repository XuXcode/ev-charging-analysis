# 可靠统计数据导入

## P0 官方统计独立存储

官方记录另存 `official_statistics`，保留公开统计的现有表和接口。执行迁移后使用 `--official` 导入相同CSV/JSON格式；该模式拒绝 `source_kind=public`，不会因URL或名称自动认证官方身份，导入者必须核对发布机构、原文、统计时点与口径。每行另保存 `updated_at`；当前采用不可变追加记录，不覆盖历史口径。

```powershell
cd backend
.\.conda\python.exe -m alembic upgrade head
.\.conda\python.exe -m app.services.statistics_import --official --file C:\path\to\verified-statistics.csv
```

读取接口 `GET /api/v1/statistics/official` 支持与公开接口相同的行政编码、年份、指标及分页参数。新增 `pile_count`（个）、`charging_gun_count`（把）、`public_charging_gun_count`（把）；充电桩与充电枪禁止互相替代。每条返回来源、原文URL、年份、单位、口径、更新时间与文件哈希。空表仍返回空记录，不能由POI推算官方数量。

公开统计与POI样本分开存储：`public_statistics`按单个指标记录来源、年份、口径和单位，允许只导入已知指标。不会用缺失字段补零，也不会自动填充要求完整桩型拆分的旧`StatisticSnapshot`或推算增长率。当前真实库没有可靠统计文件，导入记录为0，页面仍显示“—”。

## 格式与校验

[CSV空表头模板](statistics-template.csv)没有示例业务数值。UTF-8 CSV（可带BOM）与JSON记录数组使用以下相同字段，全部必填；JSON不得包装在`data`对象中。

| 字段              | 含义                                                      |
| ----------------- | --------------------------------------------------------- |
| region_adcode     | 湖南省、市州或已入库区县的现行六位行政编码                |
| year              | 原文统计年份，1900年至当前年份                            |
| metric            | 下表中的指标键                                            |
| value             | 原文明确提供的非负整数，小于10^14；不能把缺失值写为0      |
| unit              | 与指标字典一致的单位                                      |
| source_name       | 发布机构和统计材料名称                                    |
| source_url        | 可核对原文的公开HTTP(S)链接，不允许包含登录凭据           |
| source_kind       | official或public，由导入者按来源标注，不代表程序自动认证  |
| scope_description | 统计时点、空间范围、公共/私人范围、计数单位及任何单位换算 |

| metric                   | 名称               | unit |
| ------------------------ | ------------------ | ---- |
| station_count            | 充电站统计数量     | 座   |
| public_pile_count        | 公共充电桩统计数量 | 个   |
| dc_pile_count            | 直流充电桩统计数量 | 个   |
| ac_pile_count            | 交流充电桩统计数量 | 个   |
| new_energy_vehicle_count | 新能源汽车保有量   | 辆   |
| vehicle_count            | 汽车保有量         | 辆   |
| population               | 人口统计数量       | 人   |

若原文使用“万人”等单位，应核对并换算为字典单位，在口径字段记录原单位和换算；程序不自动猜测。未知指标、行政编码、缺失来源、非法数字或未来年份均拒绝。单文件上限10MB、100000行。先校验全部记录，再在单次事务中写入，失败不会留下部分导入。

## 命令与追溯

```powershell
cd backend
.\.conda\python.exe -m alembic upgrade head
.\.conda\python.exe -m app.services.statistics_import --file C:\path\to\verified-statistics.csv
# JSON使用同一命令，--file指向.json文件
```

每条记录保留原文件名、文件SHA256、原记录序号、规范化记录哈希、导入时间。完整相同记录重复导入跳过；来源或口径不同的记录分开保留，不合并为同一结果。保留原文件与发布材料，以便通过哈希复核。CSV序号从表头后的第一条记录计1，JSON从数组第一条计1。

`GET /api/v1/statistics/public`支持adcode（精确行政编码）、year、metric、page、page_size（最多100）。前端“查看数据质量”抽屉提供已导入统计来源入口。没有开放写入API或上传页面，导入由本地CLI执行，不新增用户权限系统。

CSV/JSON、幂等、整批拒绝、来源隔离与读取接口均使用独立MySQL测试库验证；测试数值没有写入应用数据库。实际运行空表头模板，插入0行，没有为了展示添加模拟统计。

# 青榆社区展馆固定导览

馆员把值班员的设施检查表录成不可变的图修订，按访客通行条件核对路线并发行。访客领取指定发行，逐站确认到达。值班员凭走览号读取实际经过。

## 运行

需要 Python 3.11 标准库。从项目根目录运行：

```sh
python3 -B -m gallery.web.server --database gallery.sqlite3 seed
python3 -B -m gallery.web.server --database gallery.sqlite3 serve --port 8000
```

浏览器访问 `http://127.0.0.1:8000/`。`seed` 只在设施修订为空时保存演示图，成功后输出修订号。普通启动会准备表结构。演示图可在 `/maps/1` 打开，也可在校样页手输修订号。自有图从制图页保存，新修订的页面会带出对应的校样表单。可从原图页载入原数据后另存。

演示图从 S 到 J 需 2 分钟，从 J 到 T 需 3 分钟，另有需要 `stairs` 属性的 3 分钟近路。校样的起终站用 S 和 T，留空通行属性可得到五分钟平路，填 `stairs` 可得到三分钟近路。发行后可以给同一原件开多次独立走览。值班员可从首页按号查阅。

## 表单接口

POST 使用 `application/x-www-form-urlencoded`。接口返回 HTML，创建资源成功返回 201，确认到站和读取成功返回 200。创建页给出可收藏的按号地址。

| 请求 | 字段和结果 |
| --- | --- |
| `POST /maps` | `stations` 和 `passages` 各为一段 JSON 数组。站点为 `id` 和 JSON 布尔值 `enabled`。通道为 `source`、`target`、正整数 `minutes`，以及可省略的 `requires` 字符串数组。|
| `GET /maps/{id}` | 读取设施修订，提供绑定该号的校样表单和以原图为输入的另存表单。|
| `POST /proofs` | `revision_id`、`start`、`end` 和可留空的 `allowed`，多项属性用半角逗号隔开。返回校样号和路线明细或不可达结论。|
| `GET /proofs/{id}` | 按号读回可达或不可达校样。|
| `POST /guides` | 用 `proof_id` 发行固定原件并更新当前目录。|
| `GET /guides/{id}` | 领取该发行的站序、分段、总分钟和开走览表单。|
| `POST /walks` | 用 `guide_id` 创建独立走览。|
| `POST /walks/{id}/arrivals` | 提交待确认的 `station` 和十进制 `ordinal`。起站的序次为 0，第一次到站确认的序次为 1。|
| `GET /walks/{id}` | 查看原发行号、实际到站顺序、当前待确认项或完成状态。|

站号和通行标签区分大小写，须为不含空白或控制字符的非空文本。通行标签也不能含逗号。路径只经过启用站和访客标签允许的单向边。平行边先过滤再选最小分钟。路线分钟由整数精确相加，同分时比较完整站号序列。同一有效起终站为零分钟的单站路线。

无效录入及非法端点返回 400，未知编号返回 404。不可达校样的发行、迟交或错站的到站表单返回 409。遇到到站冲突时，可用回显的当前表单继续，或查看已经完成的记录。改图、重新发行、读取原件和读取记录均不会推进走览。

## 回归与演示

物化项目的完整回归入口由控制台提供：

```sh
python3 -B check_project.py
```

本机演示使用临时数据库和本机 HTTP，覆盖显式初始化、免楼梯发行、顺序确认和旧页恢复：

```sh
python3 -B -m unittest -v tests.test_maps.MapTests.test_seed_repeat tests.test_guides.GuideTests.test_step_free_guide tests.test_walks.WalkTests.test_follow_guide tests.test_walks.WalkTests.test_conflict_retry
```

`samples/demo-map.json` 是初始化使用的设施图。`samples/signboard-example.json` 是单独的现场指示牌演练数据，包含场景输入和预期现场结果。

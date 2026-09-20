# 销售渠道净贡献分析：API 驱动的 RLVR 任务

一个可直接导入训练 Harness 的 Python 任务单元：智能体通过业务 API 查询 SQLite 模拟数据，提交结构化分析结果，由独立验证器生成 `[0, 1]` 的客观奖励。

## 任务是什么

分析 **淘宝旗舰店、京东自营供货、拼多多旗舰店、抖音店播、抖音达人带货** 五个华东渠道的 2026 年 6 月已支付订单，以 7 月 15 日为账务截止日，计算各渠道净贡献。从达到门槛的渠道中选出净贡献最高的两个，同额按渠道 ID 升序。

- 京东采用商家供货结算额，其余渠道采用商家订单实收。全为合成数据和模拟费率，不代表平台真实政策。
- 净收入 = 商家实收 − 已确认退款。
- 履约净成本 = 已入账商品成本、运费及成本贷项的有符号金额之和。
- 渠道费 = 净收入 × 渠道费率，按渠道汇总后半入取整到分。
- 净贡献 = 净收入 − 履约净成本 − 渠道费。
- 入选门槛：原始已支付订单数 ≥ 3、退款率 ≤ 20%、净贡献 > 0。完全退款的订单仍计入订单数。

跨月退款归属原始订单；申请中的退款、草稿成本和截止日以后的账务不计入；退款不会自动撤销履约成本。

完整任务由 `task_prompt(seed)` 返回。[任务设计](docs/design.md)说明三项挑战性要求、API 依赖、参考计算和训练边界。

## 本地运行

Python 3.11+，运行及测试仅使用标准库，无第三方运行依赖。

```bash
git clone https://github.com/DerrickLyaaaaa/channel-contribution-rlvr.git
cd channel-contribution-rlvr
python -m pip install -r requirements.txt
python -m examples.demo
python -m unittest discover -s tests -v
```

也可 `python -m pip install .` 安装后在其他目录导入。构建包时需从包管理器安装 setuptools；直接运行不需要。

样例包含正确答案、退款错误、排名颠倒、错误推荐、非法输出和非法 API 调用。默认 seed=0，正确答案推荐 `C01`（淘宝）和 `C02`（京东），净贡献合计 **59651 分**。

## 接入训练 Harness

```python
from rlvr_business.harness import Episode, TOOLS
from rlvr_business import reward

with Episode(seed=0) as episode:
    prompt = episode.prompt          # 发送给智能体
    tool_definitions = TOOLS          # JSON Schema 函数工具定义

    # Harness 将模型的函数名与参数转发给 step，返回值再交给模型。
    observation = episode.step("list_channels", {"region": "east"})
    # ...继续转发模型选择的业务 API...
    # final_result = 模型提交的 JSON 对象或纯 JSON 字符串
    # report = episode.grade(final_result)
    # training_reward = report["reward"]
    # 等价入口：training_reward = reward(prompt, final_result)
```

可执行的完整调用见 [examples/demo.py](examples/demo.py)，其中参考示例通过 API 回调取得所有业务数据，不导入验证器的 oracle。实例按 episode 创建，结束时关闭；并行训练使用独立进程/独立实例，不跨线程共享 SQLite 连接。

**信任边界：** 环境和验证器运行在可信 Harness 进程。智能体只获得任务文本、`TOOLS` 和 `step` 返回值；不要给它此进程的 Python 执行权限、源码/数据库文件访问权或 `grade` 工具。Python 私有属性不是安全沙箱。本项目提供函数级接口，进程隔离与模型工具路由由 Harness 负责。

## API 定义

统一入口：`env.call(name, arguments)` 或 `episode.step(name, arguments)`。

成功返回 `{"ok": true, "data": ...}`；未知 API 返回 `INVALID_API`，参数错误/关闭实例返回 `INVALID_ARGUMENT`，均不终止 episode。类方法也可直接调用，直接调用的非法参数会抛出异常，训练路由应使用统一入口。

| API | 参数 | 返回数据 |
|---|---|---|
| `list_channels` | `region: east/west` | 渠道 ID、名称、区域、负责人 |
| `get_channel_policy` | 无 | 渠道费率、门槛、收入口径与账务确认规则 |
| `list_orders` | `channel_ids, start, end, status='paid', cursor=0` | `items` 和 `next_cursor`；每页最多 5 条 |
| `list_refunds` | `order_ids, as_of` | 截至指定日的退款记录，包含 pending，需筛选状态 |
| `list_fulfillment_costs` | `order_ids, as_of` | 截至指定日的成本记录，包含 draft，需筛选状态 |
| `platform_gmv_dashboard` | 无 | 含未支付订单、未扣退款成本的消费者 GMV 排名，干扰接口 |
| `campaign_dashboard` | 无 | 广告归因 ROAS、曝光量，干扰接口 |
| `inventory_snapshot` | 无 | 库存信息，干扰接口 |

日期为 `YYYY-MM-DD`，订单 `[start,end)`，账务日期 `<= as_of`。ID 列表非空、不能重复、每批最多 20 个。分页 cursor 是非负整数偏移量；`next_cursor=null` 时结束。查询不存在的 ID 返回空数据；所有 SQL 值使用参数绑定，不接受原始 SQL。

## 最终输出与奖励

顶层必须包含 `task_id, channels, ranking, total_contribution_cents`。每个渠道使用以下结构（片段；完整结果见 [example_answer.json](docs/example_answer.json)）：

```json
{
  "channel_id": "C01",
  "order_count": 4,
  "gross_cents": 87149,
  "refund_cents": 5070,
  "net_cents": 82079,
  "cost_cents": 39133,
  "fee_cents": 2462,
  "contribution_cents": 40484,
  "eligible": true
}
```

金额是整数分，订单数是整数，eligible 是布尔值。渠道行顺序不影响评分，ranking 顺序影响评分。不接受 Markdown 代码围栏、重复 JSON 键、重复/未知渠道、额外字段、浮点数、NaN 或将布尔值当作金额。

```python
from rlvr_business import task_prompt, evaluate, reward
report = evaluate(task_prompt(0), final_result)  # dict
score = reward(task_prompt(0), final_result)    # float
```

```
R = 0.40 × 数值字段正确率（固定 5×7 分母）
  + 0.20 × 资格判断正确率（固定 5 分母）
  + 0.20 × 推荐集合完全正确
  + 0.10 × 推荐名单及顺序完全正确
  + 0.10 × 推荐集合正确且净贡献合计正确
```

遗漏渠道或数值字段不得分，不能缩小分母刷分。金额精确比较，不设近似容差；正确部分独立获得奖励。结构非法奖励 0，错误代码 `INVALID_OUTPUT`。输入任务未注册奖励 0，错误代码 `UNKNOWN_TASK`。仅全部目标正确时 `success=true, reward=1.0`。验证器不接受或检查调用轨迹。

任务自然语言输入是**版本化的注册模板**，必须与 `task_prompt(seed)` 一致；不使用 LLM 解释任意自然语言改写。支持 0–9999 的 seed，在同一业务场景内复现不同金额数据。调整规则或数据生成器后应升级任务版本，避免旧答案误用。

## Docker

```bash
docker build -t channel-contribution-rlvr .
docker run --rm --network none channel-contribution-rlvr
```

构建阶段执行单元测试；启动后自动运行样例。基础镜像包含 Python 和 SQLite，模拟数据生成器随镜像内置，每个 episode 在内存 SQLite 中初始化，无需提供数据库或下载数据。容器以非 root 用户运行。

将本地 Harness 挂载到 `/harness`，即可导入镜像里的包：

```bash
docker run --rm --network none \
  -v "$PWD/examples:/harness:ro" \
  channel-contribution-rlvr python /harness/demo.py
```

开发时可挂载整个仓库并直接运行测试：

```bash
docker run --rm -v "$PWD:/workspace:ro" -w /workspace \
  -e PYTHONPATH=/workspace channel-contribution-rlvr \
  python -m unittest discover -s tests -v
```

## 目录

```text
rlvr_business/
  config.py                 规则、阈值、渠道配置与奖励权重
  task.py                   注册的自然语言任务
  harness.py                Episode 适配器与工具 JSON Schema
  environment/data.py       SQLite 表与内置合成数据
  environment/api.py        只读业务 API 与异常封装
  verification/oracle.py    独立 SQL 参考计算
  verification/verifier.py  输出校验与最终结果奖励
examples/demo.py             仅通过 API 取数的样例
examples/challenge_probes.py 典型错误策略验证
tests/                     正确性、边界、异常与抗刷分测试
docs/                      设计文档、完整输出与验证记录
Dockerfile
.github/workflows/ci.yml     Python 测试及镜像构建运行
```

[验证记录](docs/validation.md)记录实测范围。该任务适合工具选择、跨 API 关联、条件筛选和结构化结果生成训练；尚未用实际大模型进行成功率评测，不将接口数量当作难度的实证结论。

# 角色卡格式

更新时间：2026-11-03；对应插件版本 0.2.0。

这份文档描述插件真正读取的公开格式。角色内容、状态、世界书和事件都用普通文件保存，适合按自己的习惯管理。仓库里的[书店示例](../examples/minimal/)是一份可以直接构建和导入的完整小卡。

## 目录

标准卡包是一个目录或 ZIP，根目录有 `manifest.yaml`。ZIP 外面可以再套一层目录，但导入时会把含 manifest 的那一层当作卡包根目录。

```text
example-card/
├── manifest.yaml
├── card/character.json
├── state/contract.yaml
├── state/schema.json
├── state/audit_system_prompt.md
├── prompts/first_meeting.md
├── prompts/familiar.md
├── worldbook/shop.md
├── runtime/event_pool.ejs
├── runtime/scene.ejs
├── events/welcome.md
├── events/restock.md
└── greetings/first_mes.md
```

文件名可以自行安排，但必须在 manifest 中逐项写出路径。插件不会自动扫描新的阶段、世界书或事件文件。路径使用 UTF-8 和 `/`，不能使用绝对路径、盘符、反斜杠或 `..`。

构建公开示例：

```sh
python scripts/build_example.py
```

脚本读取 `examples/minimal/` 的固定文件清单和仓库的 Apache-2.0 许可全文，生成 `dist/example-card.zip` 和带内嵌运行时文件的 `dist/example-card.json`。它不是通用打包器，不会扫描其他卡包目录。

## manifest

常用配置如下；[完整 manifest 示例](../examples/minimal/manifest.yaml)还包含第二阶段和动态世界书：

```yaml
schema: astrbot-rolecard/v1
package_id: example-card
display_name: 示例角色卡
version: 1.0.0
card:
  path: card/character.json
state:
  contract: state/contract.yaml
  schema: state/schema.json
  writable_paths: [scene]
  update_mode: audit
  audit_prompt: state/audit_system_prompt.md
runtime:
  engine: ejs
  event_pool: runtime/event_pool.ejs
  keyword_matching: false
stages:
  - id: first_meeting
    name: 初次见面
    path: prompts/first_meeting.md
worldbook:
  - name: 店铺约定
    path: worldbook/shop.md
    mode: resident
events:
  - path: events/welcome.md
adult_events: []
greeting: greetings/first_mes.md
```

字段用途：

| 字段 | 作用 |
| --- | --- |
| `schema` | 必须是 `astrbot-rolecard/v1`，表示当前公开格式。 |
| `package_id` | 存档和导入使用的 ID，必须是非空目录名。同 ID 导入会被拒绝，不会覆盖旧卡。 |
| `display_name`、`version` | 面板显示名称和卡包版本。 |
| `card.path` | V2 角色卡 JSON，默认 `card/character.json`。插件会读取 `data` 中的 `system_prompt`、`personality`、`scenario`、`description` 和 `post_history_instructions`。 |
| `state` | 状态初值、Schema、可写路径和更新模式。 |
| `runtime` | 模板引擎、事件池模板和关键词世界书开关。 |
| `stages` | 至少一个阶段；数组顺序就是允许的推进顺序。 |
| `worldbook` | 按声明顺序读取的世界书。支持 `resident`、`conditional`、`keyword` 和 `ejs`。 |
| `events`、`adult_events` | 普通事件和成人事件文件列表。成人事件只有私聊且用户开启许可时才进入候选。 |
| `greeting` | 开场白文件，默认 `greetings/first_mes.md`。 |

顶层必填项是 `schema`、`package_id` 和非空的 `stages`。省略 `display_name` 时使用角色名，省略 `version` 时使用 `1.0.0`；世界书和事件列表默认为空。阶段、事件 ID 和世界书名称请各自保持唯一。

`state.contract` 默认 `state/contract.yaml`，这个文件必须存在；若没有对象类型的 `initial_state`，插件才会回退读取角色 JSON 的 `data.extensions.mvu.initial_variables`。`state.schema` 可省略；`writable_paths` 默认空数组，表示不允许模型补丁更新任何路径；`update_mode` 默认 `audit`，`audit_prompt` 默认 `state/audit_system_prompt.md`，缺少提示文件时按空提示处理。

`runtime.engine` 默认 `declarative`，`keyword_matching` 默认 `true`。声明 `event_pool` 必须同时选择 `engine: ejs`；世界书 `mode: ejs` 也需要这个引擎才会渲染。只有事件池和 EJS 世界书会执行模板，人设、开场白和事件正文里的 `<% ... %>` 不会自动执行。

仓库的 [`manifest.schema.json`](../schemas/manifest.schema.json) 给编辑器或离线工具检查字段类型和拼写，不会自动注册到插件。插件另行检查已实现的必要规则，但没有全面验证跨文件语义，例如事件 ID 唯一性和前置事件是否存在；作者仍需自行核对这些关系。

`{{user}}` 会替换成当前用户显示名称；当前 `{{char}}` 替换成字面“角色”，不会读取角色名。需要角色姓名时请直接在正文中写明。

## 状态

`state/contract.yaml` 用 `initial_state` 提供初始值：

```yaml
initial_state:
  relation_stage: first_meeting
  trust: 0
  dependency: 0
  feminine_acceptance: 0
  lust: null
  active_event: null
  event_step: 0
  completed_events: []
  flags:
    welcome_done: false
  turn_count: 0
  event_history: {}
  scene:
    location: bookshop
```

这些是运行时已有含义的通用字段，还不能任意改名。自定义状态放在它们之外，例如示例中的 `scene`。

| 字段 | 用途和限制 |
| --- | --- |
| `relation_stage` | 当前阶段 ID，须与 stages 对应；非法阶段会回到第一个阶段。 |
| `trust`、`dependency`、`feminine_acceptance` | 核心整数指标，统一限制在 0–100；非恋爱题材也要保留这些字段。 |
| `lust` | 只有阶段 ID 为 `恋爱`、`公开恋爱`、`in_love`、`public_relationship` 时可为 0–100，其余阶段强制为 `null`。 |
| `active_event`、`event_step` | 活动事件 ID 或 `null`，以及非负进度计数。`step` 只增加计数，不执行逐步脚本。 |
| `completed_events` | 已完成事件 ID 列表，由 mutation 明确追加，运行时会去重。 |
| `flags` | 预先初始化的布尔标记，事件只能改变已经声明的标记。 |
| `turn_count` | 被运行时接受的更新轮数，供冷却计算使用，不等于聊天消息总数。 |
| `event_history` | 事件 ID 到最后结算轮数的映射。 |

自定义字段和 flags 都应在初始状态中声明；从存档恢复时，只保留初始结构中已知的顶层字段和 flags。给 `scene` 增加字段时同步更新 Schema 和模型提示。

`state/schema.json` 建议使用 Draft 2020-12 Schema，把自定义字段的枚举、数值范围和必填项写清楚。每次更新会先应用到副本，再通过 Schema；失败就整轮不保存。Schema 不能替代 `writable_paths`：真正决定 JSON Patch 能写哪里的，是 manifest 中的可写路径。

```yaml
state:
  writable_paths: [scene]
  update_mode: audit
```

路径可以写点号形式的对象路径，如 `scene.location`；也支持 `/scene/location`。开放 `scene` 会允许写整个对象和它的子树。底层只按这份白名单授权，并没有再硬编码一份保留字段禁写表；阶段、核心指标、事件和 flags 应交给事件结算，不要把它们加入白名单。

## 世界书

世界书条目形状如下：

```yaml
- name: 当前场景
  path: runtime/scene.ejs
  mode: ejs
  condition:
    path: scene.location
    value: bookshop
```

- `resident` 总是注入。
- `conditional` 按声明式条件注入，推荐使用 `all`、`any`、`not` 和 `path`。
- `keyword` 根据用户本轮文字匹配 `keywords`；将 `runtime.keyword_matching` 设为 `false` 会关闭整张卡的关键词世界书。
- `ejs` 先按 manifest 的 `condition` 过滤，再用 EJS 渲染正文。

声明式 predicate 可以用在世界书 `condition` 和事件 `pool.condition`：

```yaml
all:
  - path: scene.location
    value: bookshop
  - not:
      path: flags.welcome_done
      value: true
```

`all` 表示全部成立，`any` 表示至少一个成立，`not` 表示取反；直接写条件数组等同于 `all`。叶子条件支持点路径 `path`、`op` 和 `value`。`op` 默认 `equals`，还支持 `gte`、`lte`、`contains` 和 `not_contains`。predicate 只读取状态，不读取审计 `signals`；数值和布尔信号用事件结算字符串条件。

EJS 世界书可以调用 `getvar(path, {defaults: value})` 和 `await getwi(name)`。`getwi` 按本包条目名称查找并递归渲染正文，不会自动判断条目的 `mode`、`condition` 或关键词，所以动态模板要自行控制敏感内容。名称应保持唯一。

旧式 `### 【阶段】` 分段仍有有限兼容处理，但新卡应优先使用 manifest 条件和 EJS。

## EJS 事件池

设置 `runtime.engine: ejs` 后，可以用 `runtime.event_pool` 按当前状态筛选事件。模板必须输出 JSON 字符串数组：

```ejs
<%- JSON.stringify(eligible_events.slice(0, 1).map(event => event.id)) %>
```

可用上下文：

| 变量 | 内容 |
| --- | --- |
| `state`、`stat_data` | 当前成员、当前会话、当前卡包的状态；两者指向同一状态视图。 |
| `getvar(path, options)` | 按点路径读值，可带或不带 `state.`、`stat_data.` 前缀；只有值为 `undefined` 时才使用 `defaults`，`null` 会保留。 |
| `events` | 当前许可下事件全集。 |
| `eligible_events` | Python 已按阶段、前置条件、场景、冷却和许可筛过的候选事件。 |
| `active_event` | 当前进行中的事件对象，没有则为 `null`。活动事件存在时不会抽取新事件。 |
| `runtime` | `nsfw_enabled` 和 `private_chat`。 |

Python 先按 `pool.priority` 从高到低排序，同优先级保持声明顺序。插件会把事件池输出与合资格名单取交集、去重，按模板输出顺序保留；未知或不合资格 ID 会丢弃。世界书 EJS 上下文中的 `eligible_events` 仍是事件池执行前的候选，不是事件池最终选出的数组；活动事件存在时它为空。

模板对状态的改动不会保存到 SQLite。EJS 通过 Node.js 本地进程执行，每批模板限时 5 秒；模板报错会阻止该轮角色卡请求，不会绕过规则继续生成。它拥有本地代码权限，超时不是安全沙箱。

## 事件文件

事件是带 YAML front matter 的 Markdown：

```markdown
---
event_id: welcome
title: 第一次见面
target_stage: first_meeting
is_repeatable: false
pool:
  priority: 100
  cooldown_turns: 2
  condition:
    path: scene.location
    value: bookshop
lifecycle:
  on_success_condition: helped === true
  on_success_mutation:
    trust: "+= 5"
    completed_events: [welcome]
  on_fail_condition: declined === true
  on_fail_mutation: {}
  branches:
    pause:
      condition: paused === true
      mutation: {}
---
事件正文写在这里。不要替用户决定是否接受邀请。
```

常用字段：

- `event_id`、`title`：事件 ID 和显示标题；缺省 ID 使用文件名。
- `target_stage` 或 `guard.relation_stage`：限制关系阶段。
- `guard`：可写 `trust_min`、`dependency_min`、`feminine_acceptance_min`、`lust_min`、`flags_required`、`completed_events_required` 和 `completed_events_exclude`。
- `pool.priority`：候选排序用的数值；`pool.cooldown_turns` 根据 `event_history` 限制重复出现；`pool.condition` 使用声明式 predicate。
- `is_repeatable`：默认 `false`。非重复事件完成后不会再次进入候选。
- `lifecycle`：声明成功、失败和分支的条件与 mutation。
- `exclusive`：保留用于兼容旧卡；运行时始终只维护一个 `active_event`，它不是多事件并发开关。

`flags_required` 中的值必须是布尔值，不要写字符串 `"false"`。事件列表既可写 `{path: events/welcome.md}`，也可直接写 `events/welcome.md`。

条件字符串只支持受限语法，不执行 JavaScript。可用数字、`true`、`false`、`signals` 中的裸标识（例如 `helped` 对应 `signals.helped`）、`state` 路径、比较符 `===`、`!==`、`==`、`!=`、`>=`、`<=`、`>`、`<`，以及 `&&`、`||` 和括号。它不支持字符串字面量、`!` 或函数调用；复杂状态条件请用 predicate。条件缺省或为空会视为满足，所以成功、失败和各分支应显式写条件。

`trigger` 只会启动事件，把 `active_event` 设为事件 ID；不会在同一轮直接成功。活动事件下一轮只接受自己的 `none`、`step`、`success`、`fail` 或 `branch`。成功和分支可以把阶段推进到 stages 的下一个 ID，失败不会推进阶段。成功不会自动记录完成或 flags，必须在 mutation 里明确写出来。

mutation 支持 `relation_stage`、四项核心数值、声明过的布尔 flags、`completed_events` 列表，以及 `active_event`、`event_step`。结算会释放活动事件；通常不要手动填写后两个字段。数值直接写数字表示赋值，字符串 `"+= 5"`、`"-= 2"` 表示相对改变。`completed_events` 列表会追加而非替换；旧卡的 `push('事件ID')` 也有兼容处理。

成功、失败和分支结算都会清空活动事件，并把当前 `turn_count` 写入 `event_history`。因此暂停分支也会进入冷却，但不必记为完成。`cooldown_turns: 2` 表示结算后须再接受两轮更新，下一次生成时才重新有资格；设为可重复的事件即使已在完成列表中也能再次出现。

只有空闲状态的 `none` 且 `event_id: null` 才应用日常 `deltas`，每轮范围为 trust、dependency −3 至 +2，feminine_acceptance 0 至 +1，lust 0 至 +3。自定义 `scene` 通过 JSON Patch 改，不由 mutation 更新。

## audit 和 mvu

`audit` 是默认模式，需要配置审计 Provider。主模型正常回复后，插件把状态、候选或活动事件、本轮输入输出交给该模型。它应返回一个 JSON 对象：

```json
{"action":"success","event_id":"welcome","branch_id":null,"signals":{"helped":true},"deltas":{},"evidence":["本轮用户接受建议并完成找书交流"],"patches":[]}
```

这段是已有 welcome 活动事件成功时的格式示意，不代表任何一次实际聊天已经满足条件。`action` 支持 `none`、`trigger`、`step`、`success`、`fail`、`branch`；`branch` 需填写事件声明的 `branch_id`。没有变化时用空补丁和空增量。Python 会再校验事件、路径和条件，`signals` 与 `evidence` 仍需要模型依据真实聊天提取。

`mvu` 不调用第二个审计模型，而是在主模型回复末尾读取一个更新块：

```xml
<UpdateVariable>
<JSONPatch>[{"op":"replace","path":"/stat_data/scene/activity","value":"sorting"}]</JSONPatch>
<EventUpdate>{"action":"none","event_id":null,"branch_id":null,"signals":{},"deltas":{},"evidence":[]}</EventUpdate>
</UpdateVariable>
```

每轮只输出一个完整更新块，没有变化时 `JSONPatch` 写 `[]`，`EventUpdate` 仍需存在。MVU 模式该轮会关闭流式发送，等插件处理完整回复后发送。

两种模式的补丁都支持 RFC 6902 的 `add`、`remove`、`replace`、`move`、`copy`、`test`，以及 `delta`（数值增量）、`insert`（等同 add）和 `move.to`（目标 path 的兼容写法）。路径可带 `/stat_data/` 前缀；move/copy 的来源 `from` 和目标都要在可写范围内。更新块会在发给玩家前移除，`EventUpdate` 的动作和事件结算规则与 audit 相同。

一次更新的顺序是：用旧状态验证事件动作并结算，再应用补丁，最后检查 Schema 并保存。场景补丁不能让同一轮原本不合资格的事件追溯变成合资格；新场景通常影响下一轮候选。

如果模型给出非法更新，普通回复仍可发送，但这一轮状态不会保存。`audit_system_prompt.md` 只在 audit 模式作为审计提示使用；切换到 mvu 后，它不会被当作主模型提示注入。

## 独立 JSON

插件也能导入普通 V2 JSON。只有基础人设和开场白的普通 JSON 只能作为简单角色卡使用，不会自动生成阶段、事件或 EJS。要把完整运行时装进一个 JSON，在 `data.extensions.astrbot_runtime.files` 放入“相对路径到 UTF-8 文本”的对象：

```json
{
  "data": {
    "name": "示例角色卡",
    "extensions": {
      "astrbot_runtime": {
        "files": {
          "manifest.yaml": "schema: astrbot-rolecard/v1\n...",
          "card/character.json": "{...}",
          "state/contract.yaml": "initial_state:\n  ..."
        }
      }
    }
  }
}
```

构建内嵌 JSON 时，先从不带 `astrbot_runtime.files` 的原始角色卡和文件目录生成 `files`，再把 `files` 写入外层 JSON。不要把已经嵌入扩展的输出 JSON 再作为 `card/character.json` 放进去，否则会递归膨胀。

## 兼容和迁移

插件仍兼容旧式 `prompt/`、`worldbook/`、`event/`、`nsfw/`、`up/` 布局，也兼容单文件 V2 JSON，但新开发应使用 `astrbot-rolecard/v1`。旧卡的关键词世界书只有在 `runtime.keyword_matching` 未设为 `false` 时才会继续工作。

JSON 与 ZIP 文件均不能超过 20 MB，ZIP 解压后的文件总计不能超过 80 MB。

`package_id` 是存档键。修改 ID 会被当成一张新卡，插件不会自动迁移旧进度。更新同一张卡应保留 ID，先备份数据目录，再按[使用说明](user-guide.md)解除全部绑定、移除旧包并导入新版；结构变更要自行安排存档迁移。

状态按“会话 + 发言成员 + 卡包”分别保存，并有 SQLite 轮次快照和并发版本检查。群聊仍共用 AstrBot 的聊天上下文，独立状态不等于独立聊天记录。

## 边界

这套格式实现的是 AstrBot 本地角色卡运行时，不是酒馆完整运行环境。插件不会运行 Tavern Helper、浏览器 DOM、远程 MVU/Zod 注册脚本、swipe/删楼，也没有把所有酒馆 API 暴露给 EJS。EJS 模板拥有本地 Node 进程权限，卡包只应来自可信作者。

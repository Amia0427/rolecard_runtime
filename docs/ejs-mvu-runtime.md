# EJS 与 MVU 运行合同

更新时间：2026-11-03 CST；插件版本 0.2.0。

新卡作者可先看[卡包格式](card-format.md)和[完整示例](../examples/minimal/)，本文保留运行协议的简要说明。

## 卡包配置

```yaml
runtime:
  engine: ejs
  event_pool: runtime/event_pool.ejs
  keyword_matching: false
state:
  contract: runtime/state.yaml
  schema: runtime/schema.json
  writable_paths: [scene]
  update_mode: audit
  audit_prompt: up/updater_system_prompt.md
```

`audit` 模式由独立模型输出审计 JSON（包含 `patches`）；`mvu` 模式由主模型回复末尾输出 `<UpdateVariable><JSONPatch>...</JSONPatch><EventUpdate>...</EventUpdate></UpdateVariable>`。MVU 模式在消息接收时关闭该会话本轮流式发送，完整响应经校验并移除更新块后发送。Live/TTS 和第三方 agent 不在此次已验证范围内。

`EventUpdate` 与审计 JSON 使用同样的 `action/event_id/branch_id/signals/deltas/evidence` 字段；动作支持 none、trigger、step、success、fail、branch。普通补丁只能更新卡包声明的路径，例如上面的配置只开放 scene。阶段和 flags 由事件声明结算，日常数值按宿主原范围限制。

## EJS 上下文

- `state` 与 `stat_data`：本会话、本成员、本卡包的当前状态；模板改动不会写入 SQLite。
- `getvar('stat_data.scene.location', {defaults: 'unknown'})`：读取当前状态，也可省略 stat_data 前缀。
- `await getwi('条目名称')`：读取本包世界书正文，允许递归渲染 EJS，不扫描关键词；YAML front matter 不进入正文。
- `eligible_events`：已通过阶段、数值、flags、前置完成、场景、冷却和私聊许可的事件。
- `events`：当前许可下可见的全部事件；`active_event` 为当前事件对象或 null。
- `runtime.nsfw_enabled/private_chat`：本轮许可信息。

事件池模板输出 JSON 事件 ID 数组；宿主与 eligible 白名单取交集并去重，保留模板顺序。只注入选中候选正文；活动事件不重抽。世界书 `mode: ejs` 自动渲染，`conditional` 接受声明式 predicate。

本地依赖为 Node.js 与 npm `ejs@3.1.10`，通过异步子进程执行，每批模板 5 秒超时；无远程服务或 CDN。模板错误停止该轮角色卡请求并显示错误，不回退到无规则聊天。

## 变量与结算

JSONPatch 使用 jsonpatch 库执行 RFC 6902 的 add/remove/replace/move/copy/test，并适配参考卡的 insert、delta、move.to 写法；写入整体通过 JSON Schema 后才保存。阶段、事件结算与场景补丁属于同一次保存，任一失败不留下半份状态。

`success_condition`、`failure_condition` 与 branches 条件使用受限布尔语法或声明式条件，不能执行任意 Python。审计提示包含当前候选/活动事件正文及条件，signals 必须给出具体行为依据；宿主验证条件成立后执行卡包 mutation。

`turn_count` 表示有效审计轮数；`event_history` 记录事件最后结算轮数，重复事件据此冷却。SQLite 另存每轮快照，并用 revision 拦截并发旧响应与重置前响应；成员、会话、卡包之间不共用状态。不自动迁移旧卡包 ID 的存档，也未实现酒馆 swipe/删楼操作。

## 验收方法

插件目录运行：

```text
python -m pytest -q
node --test tests/panel_bridge.test.cjs
python -m compileall -q astrbot_plugin_rolecard_runtime
```

测试使用仓库内人工编写的通用样例，不需要任何商业或私有角色卡。公开版验收结果见 `docs/release-acceptance-2026-11-03.md`；源码与离线 hook 通过不代表真实聊天模型和 AstrBot 收发链路通过。

## 兼容范围

这里的 MVU 指受限的变量更新协议实现，不是上游 MagVarUpdate 的完整移植。只支持本文声明的操作，不运行卡包内的浏览器脚本、Tavern Helper API、Zod 注册脚本或旧式 `_.set` 命令。

EJS 模板在宿主的 Node.js 进程中执行，具备本地代码的权限。只导入可信作者提供的模板；超时机制不等于沙箱隔离。模板上下文仅包含本文列出的接口，并不兼容 ST-Prompt-Template 的全部 API。

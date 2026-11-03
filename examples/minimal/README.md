# 从这份示例开始

这是原创的书店小场景，用来演示 EJS 事件池、动态世界书和变量结算，按仓库的 Apache-2.0 许可公开。这里没有引用私人角色卡。

在仓库根目录运行 `python scripts/build_example.py`，会生成 `dist/example-card.zip` 和 `dist/example-card.json`；两份都能导入插件，选一份就行。同 ID 重复导入会被拒绝。

默认使用 audit 模式。先在插件配置里选择状态审计模型，再启用 `角色卡使用 example-card`。第一次找书交流成功后，阶段从 first_meeting 进入 familiar；熟悉之后，场景实际变为整理书架时才会出现 restock 候选。

改人设看 `card/character.json` 和 `prompts/`，改开场看 `greetings/`，改事件条件和结算看 `events/`。新增场景变量时同步修改 `state/contract.yaml`、`state/schema.json` 和审计说明。EJS 根据上一份已保存的状态选候选，本轮刚发生的转场通常在下一轮生效。

若要试主模型更新，把 `manifest.yaml` 的 `state.update_mode` 改为 `mvu`，重新打包后导入。mvu 模式会由主模型输出 JSONPatch 与 EventUpdate；事件条件与可写路径不变，`audit_system_prompt.md` 不作为主模型提示注入。

完整字段、格式边界和更新协议见仓库的 `docs/card-format.md`。阶段名、变量名和 ID 请成套修改，不要只改一个文件。

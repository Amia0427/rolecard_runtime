# AstrBot 角色卡运行时

把角色卡的阶段人设、世界书和事件池接入 AstrBot，并按玩家保存进度。支持 EJS 动态模板，以及由模型提出、程序校验的 MVU 变量更新。

安装插件后，需要导入有权使用的卡包。仓库提供了一个可自行构建的公开示例，不附带私人角色卡、剧情或玩家存档。

## 安装

目标接口为 AstrBot 4.28+，建议使用 Python 3.12 和 Node.js 18+。容器部署时，以下依赖要装在运行 AstrBot 的容器内。

1. 在 AstrBot 插件管理中填入本仓库地址安装，或把插件发行 ZIP 解压到 `data/plugins/astrbot_plugin_rolecard_runtime/`。该目录下应直接看见 `main.py` 和 `metadata.yaml`。
2. 进入这个插件目录，使用 AstrBot 自己的 Python 安装依赖，再安装 EJS：

   ```sh
   python -m pip install -r requirements.txt
   npm ci --omit=dev --ignore-scripts
   ```

3. 在 AstrBot 重载插件。若 Node 不在 PATH 中，在插件配置的 `node_executable` 填 Node 可执行文件路径。
4. 默认 `audit` 模式需要填写“专用状态审计模型 Provider ID”，使用 AstrBot 已配置模型的 ID。留空仍能回复，但不会自动更新状态。采用 `mvu` 模式的卡包由主聊天模型输出更新块，不需要额外配置审计 Provider。

从 GitHub 安装不会自动执行 npm。首次使用 EJS 报错时，先确认第二步是在插件实际安装目录执行的。

## 开始使用

1. 以管理员身份登录 AstrBot，在插件的“角色卡面板”上传 `.zip` 或 `.json` 卡包。
2. 在准备游玩的聊天里发送 `角色卡使用 卡包ID`，ID 在面板和 `角色卡列表` 中可查。
3. 收到开场白后正常聊天；发送 `角色卡状态` 查看当前阶段和事件。

暂停时发送 `角色卡停止`，以后在同一会话启用同一卡包会接着原存档；`角色卡重置` 则会重新开始。换卡、更新卡包和常见问题见 [使用说明](docs/user-guide.md)。

## 制作卡包

[卡包格式规范](docs/card-format.md) 说明 `astrbot-rolecard/v1` 的目录结构和字段，[manifest JSON Schema](schemas/manifest.schema.json) 可用于校验清单。

格式文档、Schema 和仓库自带的原创示例也按 Apache-2.0 公开，制作自己的卡包时可以直接参考和修改。

可以从 [完整示例](examples/minimal/) 开始改。示例 ID 为 `example-card`，启用 EJS、关闭关键词匹配，使用 `audit` 更新状态，导入后需要配置上文的审计 Provider。在仓库根目录运行：

```sh
python scripts/build_example.py
```

生成 `dist/example-card.zip` 和 `dist/example-card.json`，两种文件都可以在面板导入。

只查清单写法可看 [manifest 示例](examples/manifest.yaml)；编写动态模板和变量更新规则时，参照 [EJS/MVU 运行合同](docs/ejs-mvu-runtime.md)。

## 命令

| 命令 | 用途 |
| --- | --- |
| `角色卡列表` | 查看已加载卡包和异常原因 |
| `角色卡导入 <文件路径>` | 管理员导入服务器上的 ZIP / JSON；本机聊天附件也可走导入命令 |
| `角色卡删除 <卡包ID>` | 管理员删除卡包，操作前先解除全部会话绑定 |
| `角色卡使用 <卡包ID>` | 当前会话启用卡包 |
| `角色卡停止` | 解除当前会话绑定，保留存档 |
| `角色卡状态` | 查看当前成员状态 |
| `角色卡重置` | 重新开始当前成员的卡包进度 |
| `角色卡解锁成人` / `角色卡关闭成人` | 私聊的成人事件许可；群聊始终关闭 |

命令是否需要前缀、怎样唤醒机器人，沿用你的 AstrBot 设置。

## 兼容范围与运行限制

- 支持带 `manifest.yaml` 的标准 ZIP、目录、普通 V2 JSON，以及带内嵌运行时文件的 V2 JSON。普通 V2 JSON 只有基础人设和开场白时，不会自动补出阶段、事件或 EJS。
- 旧式 `prompt/`、`worldbook/`、`event/`、`nsfw/`、`up/` 布局的卡包。
- 分阶段人设、常驻/关键词/条件/EJS 世界书、场景筛选、事件前置条件、冷却及分支结算，同一时间只进行一个事件。
- `audit` 独立状态审计和 `mvu` 主模型更新；JSON Schema 校验、受限 JSON Patch、SQLite 轮次快照和并发版本检查。
- 管理面板导入、绑定、解绑、状态查询和重置；回复后发送通用 PNG 状态图，可在配置中关闭。

状态按“会话 + 发言成员 + 卡包”隔离。群聊共用会话的卡包绑定，成员各自保存状态，但聊天上下文仍由 AstrBot 管理，不会变成每人独立的聊天记录。普通导入不会覆盖同 ID 卡包，更新步骤见使用说明。

新卡可以设置 `runtime.keyword_matching: false` 关闭关键词世界书，再用状态条件和 EJS 选择事件；事件候选本身不依赖关键词。

EJS 会执行本地 JavaScript，具备本地代码权限，超时机制不等于沙箱隔离，只应导入可信来源的模板。本插件实现的是 AstrBot 的模板和受限变量更新协议，不支持 Tavern Helper、浏览器 DOM、远程 MVU/Zod 脚本或酒馆全部 API；Live/TTS 和第三方 agent 尚未验证。

## 数据与授权

默认数据在 AstrBot 数据目录的 `plugin_data/astrbot_plugin_rolecard_runtime/`，卡包在 `packages/`，状态在 `runtime.sqlite3`。升级前请停服备份整个数据目录，勿把数据库、聊天记录和卡包放进公开仓库。

插件代码采用 [Apache-2.0](LICENSE)，第三方来源与授权见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。私有角色卡、剧情和图片等资产不随插件开源授权，使用或分发时仍需取得相应权利人的许可。

内置中文字体为 LXGW WenKai Lite，按 SIL OFL 1.1 分发；`status_font_path` 可指定自己的字体文件。

## 开发与打包

```sh
python -m pip install -r requirements-dev.txt
npm ci --omit=dev --ignore-scripts
python -m pytest -q
node --test tests/panel_bridge.test.cjs
python -m compileall -q main.py astrbot_plugin_rolecard_runtime
python scripts/build_release.py
```

插件 ZIP 输出到 `dist/`，按公开文件清单打包，不包含测试、私有卡、数据库或开发日志。来源核查见 [审查记录](docs/source-audit-2026-11-03.md)，实测环境与尚未验证的范围见 [发布验收](docs/release-acceptance-2026-11-03.md)。

2026-11-03：补充公开卡包规范、完整示例和构建入口，整理安装与使用说明。

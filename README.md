# AstrBot 角色卡运行时

把阶段人设、世界书、事件池和独立存档接入 AstrBot。支持 EJS 动态模板，以及由模型提出、由程序校验的 MVU 变量更新。

公开版不附带私人角色卡、剧情和玩家存档。仓库内的样例只用于说明格式和运行测试，安装插件后还需要自行导入有权使用的卡包。

## 安装

目标接口为 AstrBot 4.28+，建议使用 Python 3.12 和 Node.js 18+；具体实测版本见发布验收。容器部署时，依赖要装在运行 AstrBot 的容器内。

1. 在 AstrBot 插件管理中填入本仓库地址安装，或把插件发行 ZIP 解压到 `data/plugins/astrbot_plugin_rolecard_runtime/`。该目录下应直接看见 `main.py` 和 `metadata.yaml`。
2. 进入这个插件目录，使用 AstrBot 自己的 Python 安装依赖，再安装 EJS：

   ```sh
   python -m pip install -r requirements.txt
   npm ci --omit=dev --ignore-scripts
   ```

3. 在 AstrBot 重载插件。若 Node 不在 PATH 中，在插件配置的 `node_executable` 填 Node 可执行文件路径。
4. 默认 `audit` 模式需要填写“专用状态审计模型 Provider ID”，使用 AstrBot 已配置模型的 ID。留空仍能回复，但不会自动更新状态；明确采用 `mvu` 模式的卡包则由主模型输出更新块，不需要第二个模型。

从 GitHub 安装不会自动代替你执行 npm。EJS 首次使用报错时，先确认第二步是在插件实际安装目录执行的。

## 三步开始

1. 以管理员身份登录 AstrBot，在插件的“角色卡面板”上传 `.zip` 或 `.json` 卡包。
2. 在准备游玩的聊天里发送 `角色卡使用 卡包ID`，ID 在面板和 `角色卡列表` 中可查。
3. 收到开场白后正常聊天；发送 `角色卡状态` 查看当前阶段和事件。

更细的操作、遇到问题怎么办，以及如何推进剧情，见 [使用说明](docs/user-guide.md)。卡包作者请看 [EJS/MVU 运行合同](docs/ejs-mvu-runtime.md) 和 [manifest 示例](examples/manifest.yaml)。

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

## 支持什么

- 带 `manifest.yaml` 的标准 ZIP、目录、普通 V2 JSON 和带内嵌运行时文件的 V2 JSON。
- 旧式 `prompt/`、`worldbook/`、`event/`、`nsfw/`、`up/` 布局的卡包。
- 分阶段人设、常驻/关键词/条件/EJS 世界书、场景筛选、事件前置条件、冷却、互斥及分支结算。
- `runtime.keyword_matching: false` 关闭该卡所有关键词世界书匹配，由状态和 EJS 选事件。
- `audit` 独立状态审计和 `mvu` 主模型更新；JSON Schema 校验、受限 JSON Patch、SQLite 轮次快照和并发版本检查。
- 管理面板导入、绑定、解绑、状态查询和重置；回复后发送通用 PNG 状态图，可在配置中关闭。

状态以“会话 + 发言成员 + 卡包”隔离。群聊的聊天上下文仍由 AstrBot 管理，并不会变成每人完全独立的聊天记录。普通导入不会覆盖同一 ID 的卡包，更新步骤见使用说明。

EJS 会执行本地 JavaScript，只导入可信来源的模板。这里实现的是 AstrBot 的模板和变量协议，不承诺运行 Tavern Helper、浏览器 DOM、远程 MVU/Zod 脚本或酒馆全部 API。

## 数据与备份

默认数据在 AstrBot 数据目录的 `plugin_data/astrbot_plugin_rolecard_runtime/`，卡包在 `packages/`，状态在 `runtime.sqlite3`。升级前请停服备份整个数据目录，勿把数据库、聊天记录和卡包放进公开仓库。

中文字体内置 LXGW WenKai Lite，按 SIL OFL 1.1 分发；`status_font_path` 可指定自己的字体文件。插件正文采用 [Apache-2.0](LICENSE)，第三方来源和各自授权见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。

## 开发与打包

```sh
python -m pip install -r requirements-dev.txt
npm ci --omit=dev --ignore-scripts
python -m pytest -q
node --test tests/panel_bridge.test.cjs
python -m compileall -q main.py astrbot_plugin_rolecard_runtime
python scripts/build_release.py
```

构建输出在本机 `dist/`，只从明确的插件文件清单打包，不包含测试、私有卡、数据库或开发日志。来源核查见 [审查记录](docs/source-audit-2026-11-03.md)，自动验收和未验证范围见 [发布验收](docs/release-acceptance-2026-11-03.md)。

2026-11-03：准备完整公开版 0.2.0，补齐安装、玩法、来源授权和公开发布边界；保留 EJS/MVU 与通用运行时能力。

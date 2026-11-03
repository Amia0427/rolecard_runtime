# 公开版来源与授权核查

日期：2026-11-03（CST）。范围：角色卡运行时 0.2.0 的公开源码与插件 ZIP。

## 结论与边界

本次从两个上游的固定版本取回源码，对照本项目模板桥接、变量处理、动态提示与审计提示。功能、协议名和接口习惯存在明确参考；当前对照未发现可识别的实质代码复制或提示词照搬。此结果不证明所有历史代码都独立创作，也不代替权利人的意见或法律判断。

公开版保留仓库原有的 Apache-2.0 LICENSE，并补充第三方来源和授权说明。MIT 参考项目的原版权与许可全文一并保留；AGPL 参考项目只记录来源，不捆绑其源码、构建物和示例。若后续查明有 AGPL 源码翻译、改写或移植，应暂停将相关部分作为 Apache 代码分发，先处理授权。

私人角色卡及剧情、专属状态图模块、角色图片、玩家数据、服务器配置和旧开发历史不进入公开仓库。公开版基于目标仓库原有初始提交组装，不合并本地开发分支；仅把通过检查的通用文件加入新提交。

## 对照证据

| 来源 | 固定版本 | 本地对照范围 | 观察 |
| --- | --- | --- | --- |
| MagicalAstrogy/MagVarUpdate | `b42817925d0391c15fa242a8238d2bbe28eb6319` | `mvu.py`、`audit.py` 对照 `src/function/update_variables.ts`、`schema.ts`、更新/请求流程与提示词 | 上游将 JSON Patch 翻译为命令并操作浏览器消息变量和内部 schema；本地直接调用 Python jsonpatch、jsonschema，在允许路径内处理并由 SQLite 保存。协议参考包括 stat_data、JSONPatch、delta、insert 和 move.to |
| zonde306/ST-Prompt-Template | `ada54bb22e3dab0a07e473d383b4c2fe40bc6573` | `ejs_bridge.cjs`、`ejs_runtime.py`、`prompt_builder.py` 对照 `src/function/ejs.ts`、`variables.ts`、`worldinfo.ts`、`utils/evaluate.ts` | 上游有浏览器宿主变量层、世界书装饰器、缓存、修改版 EJS、宏替换和完整上下文。本地由 Python 发送 JSON 至 Node，直接调用 npm EJS；getvar 在 state 中读路径，getwi 在卡包提供的字典中查找并递归渲染 |

上游取回清单包括 MagVarUpdate 的 69 个文件、ST-Prompt-Template 的 32 个文件，覆盖它们的 `src/`、相关 `util/`、LICENSE、package.json 和 README；二进制、dist/artifact、示例卡、Git 历史和嵌套子模块不在本次比对范围。上游快照只存放在私有开发输出目录，没有加入公开副本。

辅助机械检查将本地上述五个模块与取回的上游源码比较，去掉行首尾空白后，长度至少 40 个字符的相同行数为 0。该检查只帮助发现直接拷贝，无法证明没有翻译或结构改写；实际判断还依据执行流程、依赖与数据模型对照。

另由只读代理独立复核同一五个模块：确认 MVU 更新标记与操作约定的协议参考；没有发现足以确认 AGPL 实现或提示词复制的证据。其提出的详细审查文档链接缺失问题，已在本轮补齐本文，并通过本地链接检查；发行包和历史范围由主代理继续验收，没有把来源比对当作完整发布验收。

## 许可处理

- MagVarUpdate 的 LICENSE 为 MIT，版权行是 `Copyright (c) 2025 MagicalAstrogy & StageDog.`；随包文本与上游全文在忽略换行空白后相同。
- ST-Prompt-Template 的 LICENSE 为 GNU AGPL v3。使用其概念或调用同名接口，不能单独作为授权结论；如果复制、翻译或修改具体实现，必须依据实际衍生关系处理，致谢不能代替许可证。
- npm `ejs@3.1.10` 自身是 Apache-2.0，与参考插件的 AGPL 许可分别核对。插件不包含参考插件的 `src/3rdparty/ejs.js`。
- 内置 `LXGWWenKaiLite-Regular.ttf` 保留原文件及 `assets/OFL.txt`，按 SIL OFL 1.1 分发。Pillow、PyYAML、jsonschema、jsonpatch 及间接依赖按其各自版本的许可安装；详细来源见 `THIRD_PARTY_NOTICES.md`。
- 原插件元数据将作者写为 OpenAI，无法据此证明维护关系；公开副本改为本项目 contributors，并指向项目仓库，不宣称由 OpenAI 官方维护或背书。
- AstrBot 宿主采用 AGPL-3.0，本次不打包宿主源码。插件源码许可不消除组合程序分发、运行服务等场景下可能适用的宿主义务，本次不对这些场景作最终法律判断。

许可证原文入口：

- https://github.com/MagicalAstrogy/MagVarUpdate/blob/b42817925d0391c15fa242a8238d2bbe28eb6319/LICENSE
- https://github.com/zonde306/ST-Prompt-Template/blob/ada54bb22e3dab0a07e473d383b4c2fe40bc6573/LICENSE
- https://github.com/mde/ejs/blob/v3.1.10/LICENSE
- https://www.apache.org/licenses/LICENSE-2.0
- https://www.gnu.org/licenses/agpl-3.0.html

## 修改范围与验收门

本轮只组装公开发布副本；运行代码仅改插件归属信息，以及移除指向未分发的私有状态图模块的分流。事件、EJS、MVU、数据库、API、面板生产代码和依赖版本不作重写。私有卡测试改为通用人工样例，新增显式文件清单的 ZIP 构建与边界回归测试。

原开发目录通用检查基线为 88 项 Python 测试通过，1 项依赖私人发行物的测试未执行；所有私有卡集成测试均未进入公开副本。公开版完成条件为全套通用测试、Node 面板测试、语法检查、发行 ZIP 回读、公开文件及可达历史扫描通过，并在推送后回读远端文件清单。

未审查其他未指明的参考项目；未获得全部开发者的原始创作过程记录；未验证专利、商标、卡包著作权归属或上游全部历史版本。上述限制不能被“零相同行”或自动测试结果消除。

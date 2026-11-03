# 公开版 0.2.0 验收

记录日期：2026-11-03（CST）。目标是公开完整通用插件，不发布私人卡包或开发分支历史。

## 环境

Windows，Python 3.12，Node.js v26.13.0；pytest 8.4.2、PyYAML 6.0.3、Pillow 12.2.0、jsonschema 4.26.0、jsonpatch 1.33、jsonpointer 3.1.1、EJS 3.1.10。

## 自动检查

公开通用测试完整复验：Python **95 项通过**，Node 面板 **7 项通过**；Python 编译检查通过。

可复验命令：

```sh
npm ci --omit=dev --ignore-scripts
python -m pytest -q -p no:cacheprovider
node --test tests/panel_bridge.test.cjs
python -m compileall -q main.py astrbot_plugin_rolecard_runtime scripts
python scripts/build_release.py
```

Python 测试实际调用 Node 完成 EJS 渲染，覆盖 await getwi、关闭关键词、事件白名单、MVU 更新与 schema、事务保存、并发旧回复拦截、失效更新处理等路径。面板测试使用模拟桥接接口，不能等同于真实浏览器或已登录 AstrBot WebUI 验收。

## 依赖告警

`npm audit --omit=dev --json` 报告 4 条 moderate 告警，均由 `minimatch` 的 `GHSA-g3hv-75wg-m249` 沿 filelist → jake → ejs 传播，未报告 high 或 critical。已查看当前 EJS 的 `lib/ejs.js` 和桥接模块：运行时 render 路径只依赖 fs、path、utils、package.json，没有调用 jake/filelist/minimatch。工具链仍带该依赖，不能写成“零漏洞”。

本次按公开组装范围保留 EJS 3.1.10，不运行 `npm audit fix --force` 跨大版本升级。后续升级需单独验证模板兼容性。

## 发布边界

源码只来自明确的通用文件清单。ZIP 构建同样列出每个运行模块和素材，不递归收录未来新增的模块，自动测试验证额外的私人主题、卡包或数据库不会被打包。

实际检查结果：

- 待提交公开文件共 50 个，私有名称、项目绝对路径、服务器地址、私钥标记及常见凭据格式扫描未命中；没有角色卡 ZIP/JSON、SQLite 或运行日志。
- 从私有发行物本地抽取 143 条较长中文正文片段，仅用于排查公开副本的残留，没有将原文写进公开文件；公开文件未命中这些片段。这是辅助抽样，不能证明不存在任何短句相似。
- 插件 ZIP 有 35 个成员，无重复成员或损坏项；每个成员与公开副本逐字节一致。LICENSE、第三方声明、MIT 全文、通用 manifest 示例、字体及 OFL.txt 均在包内；卡包、状态数据库、测试和 node_modules 不在包内。
- 通用状态图生成 PNG 920×440，并实际查看：中文、阶段、四项数值、待机事件和已完成数无明显遮挡；预览不加入发行 ZIP。
- 文档中 6 个 Markdown 文件的本地链接全部能解析。
- 独立副本初始历史只有目标仓库原有 Initial commit；未合并私有开发仓库历史。
- 内置字体 name 表显示 LXGW WenKai Lite 1.530（2026-10-18），版权人及 OFL 1.1 声明与随附 OFL.txt 一致。

2026-11-03（CST）远端回读：已推送到指定仓库的 `main`，GitHub API 返回 50 个文件；重新 fetch 后，远端与已提交公开副本无差异。可达历史为仓库初始提交加本轮代码、文档提交，52 个文本对象扫描未命中私有名称、项目路径、服务器地址或私钥标记；远端没有私有开发分支的历史。

## 提交后记录

2026-11-03（CST）：小目标“完成通用插件的来源核查、隔离私有资产并组装公开版”已完成并提交于 `a2941d3`。原私有开发目录及其未提交修改保持原状，没有改写或推送其历史；公开提交包含 README、用户说明、第三方告知、通用源码和自造测试。

本次组装范围为 49 个新增/修改文件、5211 行已知文本变化，属于把现有插件引入空公开仓库，并非重写原插件；唯一无法按行计量的文件是已核实 OFL 许可的字体。`git diff --check` 的末尾空行和 OFL 原文尾随空白提示来自复制前的源文件，未为消除提示而改写第三方许可；关闭这两项原有空白检查后无其他格式错误。

建议今后纳入项目规范：公开插件始终从通用文件清单构建，私有角色卡、专属素材及含这些内容的提交历史不得进入公开分支。

2026-11-03（CST）：小目标“将完整通用插件推送至指定公开仓库并实际回读”已完成；推送使用快进更新，未强制覆盖远端，未创建或上传任何私人角色卡发行附件。插件 ZIP 在本机 `dist/` 保存，未另建 GitHub Release。

## 卡包格式公开与 README 整理

2026-11-03（CST）：沿用插件现有的 `astrbot-rolecard/v1`，补充[格式文档](card-format.md)、[manifest JSON Schema](../schemas/manifest.schema.json)、[原创书店示例](../examples/minimal/)和示例构建入口；README 重新整理了安装、启用和制卡步骤。运行时源码、插件版本及依赖未变，本轮没有加入任何私人角色内容。

本轮实际执行结果：

- `python -m pytest -q -p no:cacheprovider`：**102 项通过**，新增 7 项公开示例检查。
- `node --test tests/panel_bridge.test.cjs`：**7 项通过**。
- `python -m compileall -q main.py astrbot_plugin_rolecard_runtime scripts tests`：通过。
- `python scripts/build_example.py`：生成 `dist/example-card.zip` 和 `dist/example-card.json`；目录、ZIP、内嵌 JSON 的实际载入结果一致，三种方式导入仓库后重新加载也一致。
- 示例使用真实 Node/EJS 渲染，检查了 welcome 启动与成功证据、阶段与 flags 结算、restock 场景筛选、暂停分支、两轮冷却和重复成功；mvu 更新块可以提取、应用场景补丁，并影响下一轮候选。
- manifest Schema 校验通过；对事件池漏写 EJS 引擎和误选 declarative 的清单均能报错。Schema 是作者离线工具，未改成插件新增的强制清单校验。
- 7 份 Markdown 文档的 19 个本地链接均有目标；公开副本 67 个文本文件扫描未命中私人角色标识、项目绝对路径、服务器地址或常见凭据标记。

发行清单已加入格式说明、Schema、完整示例和示例构建脚本；插件 ZIP 共 52 个成员，已逐字节比对公开副本中的对应文件。它仍使用逐项公开清单，不会递归打包未来文件。样例 ZIP/JSON 和插件 ZIP 均生成在被 Git 忽略的 `dist/`，不作为源码提交。

这些检查验证的是公开文件和离线运行链路。本轮未连接服务器、发送真实模型请求或新建 GitHub Release；先前 95 项测试、35 文件发行包等记录保留为当时快照。

## 尚未验证

本轮没有连接服务器、替换在线插件或卡包，也没有发送真实聊天、调用真实模型或运行 AstrBot 宿主进程。本轮不把早前私有部署中的验收直接算作公开副本验收；Live/TTS、第三方 agent、所有操作系统与 Node 版本也未覆盖。

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

推送后的实际回读结果在本记录后续追加。

## 尚未验证

本轮没有连接服务器、替换在线插件或卡包，也没有发送真实聊天、调用真实模型或运行 AstrBot 宿主进程。本轮不把早前私有部署中的验收直接算作公开副本验收；Live/TTS、第三方 agent、所有操作系统与 Node 版本也未覆盖。

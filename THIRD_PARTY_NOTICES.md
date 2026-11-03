# 第三方来源与授权

核查日期：2026-11-03（CST）。本项目自身代码沿用仓库的 Apache License 2.0；这不改变下列第三方软件和字体的授权。

## 参考项目

### MagVarUpdate

- 来源：https://github.com/MagicalAstrogy/MagVarUpdate
- 核查版本：`b42817925d0391c15fa242a8238d2bbe28eb6319`。
- 作者声明：Copyright (c) 2025 MagicalAstrogy & StageDog.
- 上游许可：MIT，全文保存在 [licenses/MagVarUpdate-MIT.txt](licenses/MagVarUpdate-MIT.txt)。
- 参考范围：变量独立保存、模型生成更新指令、`stat_data` / `JSONPatch` 协议及 `delta`、`insert` 兼容写法。本项目通过 Python 的 jsonpatch、jsonschema 实现变量写入与校验，不附带上游浏览器脚本、提示词或示例卡。

### ST-Prompt-Template

- 来源：https://github.com/zonde306/ST-Prompt-Template
- 核查版本：`ada54bb22e3dab0a07e473d383b4c2fe40bc6573`。
- 上游许可：GNU AGPL v3.0，参见该版本的 LICENSE。
- 参考范围：动态提示词、按变量选择世界书及 `getvar` / `getwi` 的接口习惯。本项目 Node.js 桥接直接调用独立的 npm `ejs`，未打包此插件、其修改版 EJS、前端或提示词。
- 本次源码核查未发现足以确认的上游实现复制；不能仅凭接口相同就认定复制，也不能仅凭语言不同或没有逐行相同就排除改写。新增或移植该项目源码前，必须重新评估 AGPL 义务，不能只加致谢便按 Apache 发布。

## 运行依赖

| 组件 | 来源 | 许可 / 使用方式 |
| --- | --- | --- |
| EJS 3.1.10 | https://github.com/mde/ejs | Apache-2.0，通过 npm 安装；不是 ST-Prompt-Template 的仓库许可 |
| PyYAML | https://github.com/yaml/pyyaml | MIT，通过 pip 安装 |
| Pillow | https://github.com/python-pillow/Pillow | MIT-CMU（历史版本常标记 HPND），以安装版本的许可证为准，通过 pip 安装 |
| jsonschema | https://github.com/python-jsonschema/jsonschema | MIT，通过 pip 安装 |
| python-json-patch | https://github.com/stefankoegl/python-json-patch | BSD-3-Clause，通过 pip 安装 |
| python-json-pointer | https://github.com/stefankoegl/python-json-pointer | BSD-3-Clause，随 jsonpatch 安装 |
| LXGW WenKai Lite | https://github.com/lxgw/LxgwWenKai-Lite | SIL OFL 1.1；字体原文件及 OFL.txt 随插件保留 |

Node 间接依赖的版本和许可见 `package-lock.json`；依赖从包管理器安装，发布 ZIP 不内置 node_modules、Python site-packages 或 AstrBot 本体。重新分发依赖文件时，应保留各依赖自己的许可证和版权声明。

## 宿主与卡包

AstrBot 自身使用 AGPL-3.0，本项目通过其插件 API 运行，不复制或捆绑宿主源码。独立源码的 Apache 声明不代替宿主或组合分发场景中的许可义务；若将插件与宿主作为组合程序分发或提供服务，应另行评估并履行相应要求。

角色卡、世界书、剧情、图片、私人存档和聊天记录不因被本插件读取就自动获得开源授权。公开仓库和插件发行 ZIP 只包含人工编写的通用样例；私有卡包及其专属素材不在本项目 Apache 授权范围，也不随插件分发。

以上是针对当前源码和分发文件的工程核查记录，不是对所有权、专利、商标或全部历史来源的法律担保。具体对照过程及未验证范围见 [来源核查记录](docs/source-audit-2026-11-03.md)。

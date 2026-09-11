# 安装、调用与运行工具

## 安装与调用

公开仓库为 [xjx19960516/mba-thesis-writer](https://github.com/xjx19960516/mba-thesis-writer)。仓库主分支、历史版本安装包和本机安装副本可能处于不同版本，下载后先读取所选目录的 `baseline.json`。以实际文件为准，不能仅从仓库标题判断版本。

从仓库克隆或下载整个仓库ZIP时，技能位于仓库内层的 `mba-thesis-writer/`；下载 `mba-thesis-writer-<版本>-baseline.zip` 时，解压后的单一 `mba-thesis-writer/` 就是技能根目录。定位条件是同一目录下同时有 `SKILL.md`、`baseline.json`、`manifest.json`，而不是根据同名文件夹猜层级。保留随包 `.gitattributes`，避免Git自动转换换行而破坏逐文件校验。

解压后保留完整的 `mba-thesis-writer/` 文件夹。支持目录式技能的 agent/harness：把此文件夹放入该环境文档规定的技能目录，按该环境的方式刷新或重新加载。不同产品的目录和自动发现机制可能不同，不把某一产品的安装路径当作通用路径。

不能自动发现技能的环境：把整个文件夹放到其可读的工作区，直接给出以下指令（替换实际路径与任务）：

> 请读取 `<技能目录>/SKILL.md`，按任务需要读取它链接的参考文件，并使用随包模板或我提供的模板完成本次MBA论文任务。论文资料及输出保存在 `<项目目录>`。本次任务：……

`agents/openai.yaml` 只用于兼容环境的界面展示，可以被其他环境忽略；不支持 `$技能名` 的环境使用上述普通文字调用。仅复制 SKILL.md 会丢失规范、模板和工具，不能视为完整安装。不需要安装原 thesis-proposal-writer。

## 可直接交给AI的下载与调用提示词

> 请从 https://github.com/xjx19960516/mba-thesis-writer 下载完整技能。若我指定版本，选择该版本安装包并核对同名SHA256文件；否则读取仓库内技能的baseline.json，说明实际取得的版本。定位同时包含SKILL.md、baseline.json和manifest.json的技能根目录，保留全部文件，包括隐藏文件。先阅读README.md和SKILL.md。当前环境支持技能目录时按其官方安装机制安装；不支持时放到可读工作区，直接按本入口及按需参考执行。存在旧版本时先核对本地修改并保留可恢复副本，不混合不同版本的文件。有可用Python时运行scripts/doctor.py --self-test；依赖缺失时按README区分可选能力，使用环境允许的工具补齐所需能力。没有Python则如实记录未运行自检；校验失败时核对版本及下载完整性，不重写清单来掩盖差异。告诉我实际版本、技能位置、验证结果和调用方式。我的论文任务是：【填写任务】，资料与结果保存在独立项目目录：【填写目录】。

纯对话环境先确认能读取完整资源；交付Word所需的文档处理由可用工具承接。环境适配信息写入交付说明。

## 路径和可选运行工具

技能目录是只读资源，项目目录存放原始资料、研究记录和输出；工具临时文件使用临时目录。参考链接相对于所在 Markdown 文件，工具和内置模板相对于技能根目录。实际执行时解析到绝对路径，含中文、空格的路径必须作为一个参数传递。跨机器迁移项目时重新解析路径，勿沿用旧机器的绝对路径。

以下 `python` 表示当前环境允许使用的 Python 3.10+ 解释器，可能实际叫 `python3` 或为绝对路径；尖括号内容需要替换。四个审计工具及问卷生成工具使用标准库；表格生成使用python-docx。Agent也可使用环境已有的等价工具完成研究、审读和文档输出，按实际结果说明交付状态。

```text
python "<技能目录>/scripts/doctor.py" --self-test
python "<技能目录>/scripts/audit_project.py" "<项目目录>/project.json" --out "<项目目录>/project-audit.json"
python "<技能目录>/scripts/audit_text.py" "<项目目录>/thesis.md" --out "<项目目录>/text-audit.json"
python "<技能目录>/scripts/build_table.py" "<项目目录>/table.json" --out "<项目目录>/table.docx"
python "<技能目录>/scripts/audit_docx.py" "<项目目录>/table.docx" --profile "<技能目录>/assets/ustc-format.json" --out "<项目目录>/docx-audit.json"
python "<技能目录>/scripts/audit_citations.py" "<项目目录>/thesis.docx" --style numeric --out "<项目目录>/citation-audit.json"
python "<技能目录>/scripts/simulate_survey.py" "<项目目录>/simulation-spec.json" --out-dir "<项目目录>/simulation-v1"
python "<技能目录>/scripts/audit_docx.py" "<项目目录>/thesis.docx" --expect-heading "问题分析" --expect-heading "结论"
```

文件输出的父目录须已存在；问卷生成的`--out-dir`指定新的结果目录，由工具创建。输入、配置和报告使用UTF-8，JSON输入兼容UTF-8 BOM。命令可从其他工作目录执行；这些本地工具不执行联网、上传或软件安装。

最后一条中的章名须换成项目实际标题，不能把示例当作固定目录。引用扫描的用法和限制见 [成稿引用核对](citation-audit.md)；完整论文的连续写作、内部返修和交付见 [全文执行流程](full-thesis-workflow.md)。`audit_citations` 返回0也可能表示需要人工检查，必须阅读 `status` 和警告；它不验证国标全部著录规则或来源真实性，且不会覆盖已有输出报告。

若需要表格生成且当前环境允许安装依赖，在该环境指定的隔离环境使用：

```text
python -m pip install -r "<技能目录>/requirements-docx.txt"
```

不修改宿主已有的受管依赖；已有等价能力时直接使用。依赖范围是兼容声明，基线实际测试的是 Python 3.12、python-docx 1.2.0，其他组合应先运行自检。

## 环境能力与验证记录

| 能力 | 可用时 | 暂不可用时 |
|---|---|---|
| 文件访问 | 按需读本包和用户资料 | 在支持附件的环境提供所需文件；在独立交付说明登记资源获取事项 |
| 联网/学术检索 | 核验原始来源与最新现行国标 | 用已核验本地证据推进，在项目记录保留核验任务及实际核验日期 |
| 可复算分析 | 使用适合方法的分析工具 | 完成资料整理/分析设计，统计结果在实际计算后写入正文 |
| DOCX生成 | Python工具或等价文档工具生成可编辑内容 | 先交付正文与表格数据，明确 Word 交付状态 |
| 真实排版渲染 | Word、LibreOffice 或能处理 DOCX 的环境渲染器导出页面 | 继续结构检查，在独立质检说明记录尚需执行的逐页核对 |

实际导出后核对字体替代、页数、表头、续表、题注、目录及交叉引用，再逐页查看。换系统、字体或排版引擎后重新渲染。本包使用环境字体；PDF转图工具负责将已排版PDF转换为页面图像。

`doctor.py` 先核对校验清单及资源完整性，发现安装错误时保留报告并停止执行包内工具；不会自动修复或覆盖用户修改。安装正确后，`--self-test` 才运行工具行为验证，模拟材料只存在于临时目录。自检在普通Python与优化模式下执行相同检查；`self_test` 区分未请求、安装错误阻断、通过和失败。renderer 状态不是版式合格结论。

工具检查与来源审读、统计解释及逐页核对配合使用。`audit_project/audit_docx` 返回0表示无结构错误（仍可能有警告）、1表示发现错误、2表示输入/执行错误；`audit_text` 返回0表示扫描完成；表格工具返回0表示文件生成。问卷生成返回0及`simulated_generated`表示已生成配置对应的数据与报告，返回2表示输入/输出错误。`doctor` 返回1表示自检失败，可选能力缺失单独列出。报告使用独立路径，保留原稿与格式配置。

本基线实际验证 Windows、本机 Word、路径迁移与无第三方依赖模式；Linux/macOS及各商业agent/harness未逐一实机测试。可移植性来自中立入口、相对资源、标准库工具与可选依赖，各平台以本机自检和实际文件交付记录为准。

# MBA Thesis Writer

当前基线：**1.5.3** · 2026-10-16

面向完整、正式MBA学术论文的独立研究与写作技能。从题目、已通过开题、草稿或导师意见启动，完成取证、研究分析、全文、学术表达自然化、去重和Word定稿。适配营销、战略、财务、人力、运营、数字化等MBA方向，章节和方法按具体问题设计。

## 开始使用

从 [GitHub仓库](https://github.com/xjx19960516/mba-thesis-writer)下载当前安装包及同名SHA256文件，校验后解压。技能根目录同时包含`SKILL.md`、`baseline.json`与`manifest.json`，保留完整目录及隐藏文件。

支持技能的agent/harness按其机制加载；其他环境将完整目录放入可读工作区，直接读取入口。核心为Markdown和相对资源，Python工具可选，Word生成与渲染由环境已有能力承接。具体安装、依赖及命令统一见 [安装与工具指南](references/installation-and-tools.md)。

> 请使用mba-thesis-writer，先读SKILL.md，按当前任务加载相关参考。读取【项目目录】中的开题、论文、数据、导师意见和学校模板，完成【论文任务】。全文任务请连续完成全部适用章节、自然化与去重、引用核对和Word定稿；实质修订事项另附准确位置和处理方法。资料及成果存放在独立项目目录。

## 如何选择入口

| 需求 | 对应参考 |
|---|---|
| 完成全文或全稿研究深化 | [全文流程](references/full-thesis-workflow.md) |
| 设计研究、继承开题或选择方法 | [研究设计](references/research-design.md) |
| 检索、来源筛选与文献引用 | [证据与引用](references/evidence-and-citations.md) |
| 修改章节、自然化表达与全文去重 | [写作与质量](references/writing-and-quality.md) |
| 按独立说明补充资料后整合定稿 | [二轮完善](references/delivery-contract.md#补充资料后的二轮完善) |
| 问卷、真实结果、模拟或临时结果更新 | [问卷分析](references/questionnaire-and-simulation.md) |
| 制作Word、表格及检查分页 | [Word与图表](references/word-and-tables.md) |
| 成品核对、正文和独立修订说明 | [交付规范](references/delivery-contract.md) |

按阶段读取对应内容即可。引用编号扫描和问卷生成的详细协议，由相关参考链接到工具说明；长期续写使用 [项目记录](references/project-schema.md)。

## 交付与规范

主成果为完整论文DOCX，包含适用前后置内容、全部正文、图表、参考文献及必要附录。研究附件按实际使用整理，存在实质修订事项时另附《论文补充材料与修订说明》。正文采用正式学术论述，数据、方法及必要来源在对应位置准确交代。

补充资料后，可直接使用以下指令继续，执行细节见 [二轮完善](references/delivery-contract.md#补充资料后的二轮完善)：

> 使用mba-thesis-writer，读取当前论文、对应的《论文补充材料与修订说明》、本次新增资料及我的修改意见。以我的最新主稿为基稿，逐项核验并整合资料，重新分析受影响内容，同步图表、讨论、管理方案、引用及中英文摘要和结论。保留已认可修改，按新证据调整结论，完成自然化、去重、全文一致性和Word逐页复核，输出新版完整论文及更新后的独立说明，写清实际处理结果和对应位置。

规范资源包括 [全国MBA要求](references/national-requirements.md)与 [中科大格式](references/ustc-format.md)。其他学校采用其当期模板。引用基线为2026-10-15核验的GB/T 7714-2025，实施日2026-07-01；每篇论文启动及定稿重新核验，记录见 [baseline.json](baseline.json)。

## 包体结构

```text
mba-thesis-writer/
  SKILL.md                 Agent任务入口
  README.md                使用与导航
  references/              按研究、写作、交付及工具任务读取
  assets/                  MBA规范、Word模板、格式参数与示例
  scripts/                 7个可选工具
  agents/                  可选界面元数据
  baseline.json            版本与依赖
  manifest.json            逐文件SHA256
  requirements-docx.txt    可选Word工具依赖
```

## 本版说明

1.5.3校正模板验证范围的旧说明，登记已经完成的原模板29页及完整教学论文58页的Word渲染与逐页视觉核对。沿用1.5.2的研究与二轮整合流程、31个包体文件、12份专题参考、schema 2及schema 1兼容、7个工具和学校模板。

Windows、Python 3.12及python-docx 1.2.0为实测组合；运行记录和本轮范围见仓库随附的复核说明。各环境安装后可运行`python scripts/doctor.py --self-test`。本包不含企业研究资料或真实答卷。仓库尚未指定统一开源许可证，随包第三方规范和模板沿用原发布方使用条件。

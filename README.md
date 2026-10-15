# MBA Thesis Writer

当前最终版：**1.5.0**。面向完整、正式MBA学术论文的研究、分析、写作、学术表达自然化、全文去重及Word定稿技能，可在支持文件读取的agent/harness中使用。

## 下载与使用

- [完整安装包](mba-thesis-writer-1.5.0-baseline.zip) · [SHA256](mba-thesis-writer-1.5.0-baseline.zip.sha256)
- [使用说明与任务导航](mba-thesis-writer/README.md)
- [Agent执行入口](mba-thesis-writer/SKILL.md)
- [本版结构整理与验证](MBA论文Skill结构整理复核-1.5.0.md)

下载后保留完整的`mba-thesis-writer/`目录。根目录同时包含`SKILL.md`、`baseline.json`和`manifest.json`。支持技能机制时按环境加载，其他环境直接读取入口，按任务进入相关参考。详细路径和可选工具见 [安装指南](mba-thesis-writer/references/installation-and-tools.md)。

可交给AI执行：

> 请从 https://github.com/xjx19960516/mba-thesis-writer 下载当前最终版完整技能及SHA256，校验并读取baseline.json确认版本。保留完整目录和隐藏文件，先读SKILL.md，按我的任务加载相关参考。按环境安装或放入可读工作区，保留已有本地修改；有Python时运行scripts/doctor.py --self-test并报告实际结果。我的任务是【论文任务】，资料与成果存放在独立目录【项目目录】。

## 结构与能力

本版参考文件由15份合并为12份，入口缩短约41%、包内README约60%。完整论文按阶段推进，单章修改和真实问卷分析可直接进入对应参考。

研究设计、可靠来源、现行国标引用、图表、正式正文、自然化与去重、可编辑Word及逐页验收能力保留。正文呈现研究成果，材料补充和工具记录独立整理。当前规范基线为GB/T 7714-2025及随包MBA要求，学校格式使用当期模板。

仓库文件区仅保留当前最终版。包体、链接、导航及99项回归检查通过，详细范围见本版复核说明。学校模板及MBA要求沿用原发布方适用条件；仓库尚未指定统一开源许可证。

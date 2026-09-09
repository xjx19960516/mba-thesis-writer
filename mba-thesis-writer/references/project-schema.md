# 项目记录与脚本接口

项目资料写入用户工作目录，与 Skill 安装目录分开。只需要一个 `project.json` 保存索引、研究配置和质检状态；大量原始数据、论文正文、分析程序、访谈记录、文献全文另存文件并在索引引用。小任务只登记本次使用的部分，不强制建立空台账。

## 核心结构

下列键名是 `scripts/audit_project.py` 的输入协议。ID 在项目内稳定，修改章节或文献显示编号时不改 ID。日期使用 ISO 8601。未核验字段使用 null 或空值，并登记任务；空值不代表通过。

```json
{
  "schema_version": 1,
  "project": {
    "title": "研究题目",
    "mode": "proposal_to_thesis",
    "thesis_type": "topic_research",
    "stage": "research_draft",
    "citation_style": "numeric",
    "citation_standard": "GB/T 7714-2025",
    "standard_verification": {"number": "GB/T 7714-2025", "status": "current", "effective_on": "2026-07-01", "checked_on": "2026-09-09", "official_url": "本项目实际核验的官方页面URL"},
    "research_period": "实际研究期间",
    "template": "所用模板路径与版本",
    "delivery_variant": "working"
  },
  "proposal_baseline": {},
  "changes": [],
  "research_questions": [],
  "sources": [],
  "claims": [],
  "data_items": [],
  "displays": [],
  "tasks": [],
  "qa": {}
}
```

## 条目字段

- `proposal_baseline`：保存题目、对象、问题、目标、主理论、核心方法、技术路线、主体目录、预期成果、原开题文件和定位。无开题时为空。
- `project.mode` 为 topic_to_thesis / proposal_to_thesis / thesis_revision / finalization；`thesis_type` 为 topic_research / case_descriptive / case_problem / other（other另存培养单位认可依据type_authority）。`delivery_variant` 为 working / review / archive。`standard_verification` 每项目启动与定稿真实核验后填写，示例日期不照抄；脚本只查记录一致性，不联网判断“最新”。
- `changes[]`：`id, before, after, reason, impact, substantive, authorization, status`。status为proposed / approved / implemented / declined；substantive为布尔。`authorization` 记录用户原话所在回合/文件或既有授权范围；日常编辑不必逐句登记。
- `research_questions[]`：`id, question, unit, inference_goal, method, evidence_ids, chapters, output, status`。`evidence_ids` 指向 sources 或 data_items；`status` 为 planned / in_progress / answered。
- `sources[]`：`id, kind, title, publisher, origin, accessed_on, access_scope, verification, eligibility, locator, qualification, used_in_bibliography, bibliography_key`。`kind` 为 official / academic / third_party / internal / auxiliary；`origin` 为正规原始 URL 或用户本地材料路径；`locator` 为实际页码/表号/段落/记录定位；题录另加 authors/year/container/doi 等真实字段。
- `access_scope` 为 metadata_only / abstract / full_text / dataset；`verification` 为 verified / unverified；`eligibility` 为 accepted / reference_only / rejected。这些是不同维度，不把“第三方已交叉验证”另造一个与 accepted 重叠的状态。
- `qualification`：第三方必需，包含 `traceable_origin, period, population, definition, method, research_fit`。每项写实际说明，不能只填 true。原始机构单独发布的官方数据无需伪造第二出处；交叉核验另记 `corroboration`（独立原始来源 ID、差异和处理结论）。
- `claims[]`：`id, text, kind, evidence_ids, locator, section, status, reviewer_note`。`kind` 为 factual / interpretation / proposal / scenario；`status` 为 supported / pending / withdrawn。解释和建议也应写依据与边界。`locator` 是证据的具体内容定位；实际语义支撑由研究者复核，脚本只查结构。
- `data_items[]`：`id, indicator, value, unit, period, definition, population, source_ids, status`；衍生量另加 `input_ids, formula, analysis_path`；`status` 为 observed / calculated / scenario / pending。`value` 可为有限数值、非空文本或待取得时的null，不能用布尔、NaN或Infinity；情景值不得标observed。pending条目可连接待核验候选来源，脚本提示但不将其视为已验证事实。
- `displays[]`：`id, kind, number, title, research_question_id, data_ids, source_ids, first_mention, note, calculation_checked, format_checked`；可加`status`为planned / included，省略默认included。`kind`为table / figure；编号如`3.1`或附录`A.1`，与稳定ID分开。planned为研究计划，可暂缺实际数据和正文首次引用；纳入正文后必须有合格证据。两个checked字段用真实布尔值，不用字符串“true”；完全没有数值计算的定性表/图可将calculation_checked设为not_applicable，并用calculation_note说明原因，避免虚填数值复核。
- `tasks[]`：`id, need, purpose, owner, status, blocking`；任务状态为 open / done / waived；waived另存reason。只有具体理由和可接受替代路径才能 waived，不能把尚未取得的研究结果标完成。
- `qa`：`evidence_semantics, calculations, citations, repetition, academic_style, consistency, docx_structure, visual_pages`。每项为 `{status: pass|pending|not_applicable, evidence: 实际审查记录路径或说明}`。`visual_pages` 另记 rendered_file、checked_pages、total_pages。另记录外部查重报告的来源、日期、覆盖范围；没有报告就不填写查重率。

## 状态只描述已经完成的工作

`research_draft` 允许存在待取数据；`research_ready` 表示关键研究路径与现有证据可执行；`full_draft` 表示全篇正文完成，但审计可能未完成；`review_ready` 表示可供导师审阅；`submission_candidate` 需全部相关质量检查完成、关键资料任务关闭、目标版本明确。脚本不会代替导师、学校或正式查重系统作出送审决定。

数据更正后用稳定 ID 找到关联的论断、图表、章节、摘要和结论，只重做受影响的分析与检查。跨会话继续时先读项目记录与未完成任务，避免重新选题。

## 检查范围

脚本检查已回答问题、已支持论断及已纳入图表的证据状态，沿衍生数据回查来源；证据ID存在不等于可用。送审候选至少应有真实已支持的论断，不能用全部withdrawn代替研究结果。参考文献键应唯一，学术证据使用需与文后登记对应，文后条目应有研究中的实质使用位置；正文实际引用字符、题录各字段和现行国标细节仍需结合论文人工检查。

`standard_verification.official_url`指向国家市场监督管理总局体系的实际官方标准记录（如std.samr.gov.cn或openstd.samr.gov.cn）；脚本只校验域名/日期/版本记录一致性，实时状态要实际打开核对。草稿阶段可只记录本次需要的内容，待核验来源与研究任务不被冒充正式证据，也不因此阻止不受影响的写作。

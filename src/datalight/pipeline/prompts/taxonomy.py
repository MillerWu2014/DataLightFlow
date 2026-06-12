from __future__ import annotations

import textwrap

from datalight.config import TaxonomySettings


def resolve_taxonomy_topic(taxonomy: TaxonomySettings) -> str:
    return taxonomy.resolved_topic()


class TaxonomyTagPromptTemplate:
    """Build user prompts for taxonomy chunk tagging."""

    def build_prompt(
        self,
        *,
        chunk_text: str,
        catalog: str,
        taxonomy: TaxonomySettings,
        language_line: str,
    ) -> str:
        topic = resolve_taxonomy_topic(taxonomy)
        return textwrap.dedent(
            f"""\
            你是**{topic}**业务专家。请阅读 Context 内容，并深度理解，识别其中可用于生成高质量 SFT 问答对的知识点，并打上 taxonomy 标签。

            {language_line}

            ## 领域主题
            {topic}

            ## 任务目标
            为后续问答生成提供准确、可执行的主题与任务类型指引。每个 tag 应对应一个可独立出题的原子知识点。

            ## 分类维度
            1. **level1_name / level2_name**：Context 的知识点主题，必须从 catalog 中成对选取。
            2. **task_type**：适合生成的问答任务类型。
            3. **reasoning_style**：回答该主题时宜采用的推理风格。

            ## 标注要求
            - **准确性**：仅当 Context 明确支持该分类时才打标签；不得臆造 catalog 外的枚举值，不得依据常识补全 Context 未写明的规则或数值。
            - **专业性**：分类应体现{topic}业务语义，优先识别规章条款、岗位职责、运行流程、阈值边界、异常处置等领域知识。
            - **多样性**：同一 Context 可返回多个 tag，分别对应不同知识点或任务类型；覆盖事实问答、规则解释、流程说明、情景处置、对比权衡等可出题方向。
            - **格式规范**：只返回 JSON 对象，结构为 `{{"tags":[...]}}`；每个 tag 必须同时包含 `level1_name`、`level2_name`、`task_type`、`reasoning_style` 四个字段。
            - **完备性**：尽量覆盖 Context 中的核心知识点，包括关键参数、流程节点、例外条款与特殊情形；但不要为凑数量重复标注同一知识点。
            - **原子性**：一个 tag 只对应一个核心知识点或一种出题方向，避免把多个流程、规则、指标混在同一标签里。
            - **可出题性**：优先标注能支撑自解释、可独立阅读问答的片段；不要为纯目录、封面、页眉页脚、图片说明、纯引用列表、无实质正文的段落打标签。
            - **禁止无效片段**：目录、封面、页眉页脚、仅含“见图/见表/见附件”而无正文依据的片段，返回 `{{"tags":[]}}`。
            - **类别约束**：“阈值与边界”仅在有明确数值、时限或边界条件时标注；“职责与权限”需有明确主体分工；“规则要求”需有清晰的应当/不得/必须/禁止表述。

            ## 输出格式
            请只返回如下 JSON，不要输出 Markdown 代码块或额外说明：
            {{
              "tags": [
                {{
                  "level1_name": "...",
                  "level2_name": "...",
                  "task_type": "...",
                  "reasoning_style": "..."
                }}
              ]
            }}

            若 Context 无实质内容或无法支撑可靠标注，只返回：{{"tags":[]}}

            ## Taxonomy catalog
            {catalog}

            ## Context
            {chunk_text}
            """,
        )


class TaxonomyQuestionPromptTemplate:
    """Build user prompts for taxonomy question generation."""

    def build_prompt(
        self,
        *,
        chunk_text: str,
        level1_name: str,
        level2_name: str,
        task_type: str,
        task_description: str,
        reasoning_style: str,
        reasoning_description: str,
        focus: str,
        prompt_hint: str,
        taxonomy: TaxonomySettings,
        language_line: str,
    ) -> str:
        topic = resolve_taxonomy_topic(taxonomy)
        return textwrap.dedent(
            f"""\
            你是**{topic}**业务专家。请依据标签与 Context 生成一个高质量、可独立理解的问题。

            {language_line}

            ## 领域主题
            {topic}

            ## 质量要求
            - **准确性**：问题必须紧扣标签主题，且仅凭 Context 即可明确回答；表述清楚、无歧义，不得预设 Context 中不存在的事实。
            - **专业性**：术语须符合{topic}业务规范，使用规范中的标准称谓，避免口语化或随意缩写。
            - **多样性**：问题类型应匹配 task_type，可覆盖事实问答、逻辑推理、规则适用、流程说明及异常处理等；不要针对图片、附图、表格编号生成无法独立阅读的问题。
            - **格式规范**：只返回 JSON 对象 `{{"question":"..."}}`；`question` 字段存放问题正文，相当于 SFT 样本中的 `instruction`，勿输出 input、output 等额外字段。
            - **完备性**：问题应指向 Context 中的核心知识点，优先覆盖关键参数（数值、阈值、时限）、完整流程节点、例外条款与特殊情形；Context 不支持时返回空问题。
            - **自解释性（Self-Explanatory）**：问题须写清必要主体、对象与场景，使读者脱离 Context 后仍能理解在问什么；严禁使用“该项目”“上述内容”“上文提到的”“该规范”“该标准”等模糊代词。
            - **原子性**：一个问题只考察一个核心知识点，避免复合问法；优先聚焦术语定义、单一流程、异常处理、单一指标、单一定义或单一规则。
            - **禁止引用**：问题中不得出现“根据XX规范”“依据XX文件”“如上图所示”“根据表2”“见本章第X节”等对文档其他部分的指代。
            - **写作规范**：问题直接询问知识内容，禁止以“根据XX文件”、“依据XX规定”、“按照本咨询通告”、“依据上下文”、”根据XXXX节/章/章节“等引用句式开头。

            ## 标签信息
            - 主题：{level1_name} / {level2_name}
            - task_type：{task_type}（{task_description}）
            - reasoning_style：{reasoning_style}（{reasoning_description}）
            - 侧重：{focus}
            - 提示：{prompt_hint}

            ## Context
            {chunk_text}

            若 Context 无法支撑可靠提问，只返回：{{"question":""}}
            否则只返回：{{"question":"..."}}，不要输出 Markdown 代码块或额外说明。
            """,
        )


class TaxonomyAnswerPromptTemplate:
    """Build user prompts for taxonomy answer generation."""

    def build_prompt(
        self,
        *,
        chunk_text: str,
        question: str,
        level1_name: str,
        level2_name: str,
        task_type: str,
        reasoning_style: str,
        taxonomy: TaxonomySettings,
        language_line: str,
    ) -> str:
        topic = resolve_taxonomy_topic(taxonomy)
        return textwrap.dedent(
            f"""\
            你是**{topic}**业务专家。请严格依据 Context 回答下方问题，生成高质量、可独立理解的答案。

            {language_line}

            ## 领域主题
            {topic}

            ## 质量要求
            - **准确性**：答案必须严格依据 Context，不得包含幻觉信息；将问题或 Context 中的模糊指代替换为具体实体、岗位、设备或规章名称；涉及公式时使用 LaTeX 书写（如 `$V_{{max}}$`）。
            - **专业性**：术语须符合{topic}业务规范，避免口语化、歧义表达或随意缩写。
            - **多样性**：答案应匹配任务类型，可覆盖事实陈述、逻辑推理、规则适用、流程说明及异常处理等；不要围绕图片、附图、表格编号生成无法独立阅读的内容。
            - **格式规范**：只返回 JSON 对象 `{{"answer":"..."}}`；`answer` 字段存放答案正文，相当于 SFT 样本中的 `output`，勿输出 instruction、input 等额外字段。
            - **完备性**：覆盖问题所涉核心知识点，不遗漏关键参数（数值、阈值、时限）、流程中间步骤、例外条款与特殊情形；Context 信息不足时返回空答案。
            - **自解释性（Self-Explanatory）**：**答案须写清必要主体与对象，使读者脱离 Context 后仍能理解；严禁使用“该项目”“上述内容”“上下文”等模糊代词**。
            - **禁止引用**：答案中不得出现“如上图所示”“根据表2”“根据附图2-1”“见本章第X节”等对文档其他部分的指代；问题中已有的规范名称可保留，但答案不得新增**“根据XX规范”**、**“依据XX文件”**式引用。
            - **写作规范**：答案直接陈述知识内容，禁止以“根据XX文件”、“依据XX规定”、“按照本咨询通告”、“依据上下文”、”根据XXXX节/章/章节“等引用句式开头。

            ## 标签信息
            - level1_name: {level1_name}
            - level2_name: {level2_name}
            - task_type: {task_type}
            - reasoning_style: {reasoning_style}

            ## 问题
            {question}

            ## Context
            {chunk_text}

            若 Context 无法支撑可靠回答，只返回：{{"answer":""}}
            否则只返回：{{"answer":"..."}}，不要输出 Markdown 代码块或额外说明。
            """,
        )

"""Deep Research prompt templates."""

# ── Research brief ───────────────────────────────────────────

RESEARCH_BRIEF_SYSTEM = """\
You are a research planning specialist. Create a focused research brief \
that scopes the investigation and identifies key questions."""

RESEARCH_BRIEF_USER = """\
Research request: {query}

Initial context from knowledge base:
{context}

Create a research brief with:
1. **Objective**: What we need to find out (1-2 sentences).
2. **Scope**: What's in scope and out of scope.
3. **Key questions**: 3-5 specific questions to answer.
4. **Expected sources**: Types of sources needed.

Be specific and actionable. Do not be vague."""

# ── Subtask decomposition (supervisor) ───────────────────────

SUPERVISOR_DECOMPOSE_SYSTEM = """\
You are a research supervisor. Break down the research brief into \
independent, parallelizable subtasks for sub-agents."""

SUPERVISOR_DECOMPOSE_USER = """\
Research brief:
{brief}

Key questions:
{questions}

Decompose into 2-{max_subtasks} independent subtasks. For each:
1. **topic**: A specific aspect to investigate.
2. **queries**: 2-3 search/retrieval queries for this subtask.
3. **instructions**: What the sub-agent should focus on and what to ignore.

Return as a JSON array of subtask objects.
Important: subtasks must be INDEPENDENT — no subtask should depend on another's output."""

# ── Sub-agent research ───────────────────────────────────────

SUBAGENT_RESEARCH_SYSTEM = """\
You are a focused research sub-agent. Your task is to investigate ONE specific \
topic using the provided context. Return CLEANED findings — not raw data dumps."""

SUBAGENT_RESEARCH_USER = """\
Topic: {topic}
Instructions: {instructions}

Retrieved context:
{context}

Produce a structured finding:
1. **Summary**: 2-3 sentence overview of what you found.
2. **Key facts**: Bullet list of specific, evidence-backed facts.
3. **Evidence**: Cite [Source N] for each fact.
4. **Gaps**: What information is missing or uncertain.
5. **Confidence**: Rate 0.0-1.0 how well the context answers this topic.

Be precise. Do not invent information beyond what the sources provide."""

# ── Supervisor reflection ────────────────────────────────────

SUPERVISOR_REFLECT_SYSTEM = """\
You are a research supervisor reviewing sub-agent findings for coverage \
and quality before final report generation."""

SUPERVISOR_REFLECT_USER = """\
Original brief:
{brief}

Key questions:
{questions}

Sub-agent findings:
{findings}

Evaluate:
1. Are all key questions adequately answered?
2. Are there contradictions between findings?
3. What gaps remain?
4. Should we do another round of research? (yes/no)
5. If yes, what specific additional queries should we run?

Respond with a JSON object: {{"coverage_score": 0.0-1.0, "gaps": [...], "contradictions": [...], "iterate": true/false, "additional_queries": [...]}}"""

# ── Final report synthesis ───────────────────────────────────

FINAL_REPORT_SYSTEM = """\
You are a senior analyst writing a decision memo. Synthesize all research \
findings into a clear, cited, evidence-backed report."""

FINAL_REPORT_USER = """\
Research brief:
{brief}

Compiled findings:
{findings}

Supervisor notes:
{supervisor_notes}

Write a complete decision memo with these sections:
1. **Executive Summary**: 2-3 sentences answering the core question.
2. **Findings**: Detailed analysis organized by theme. Cite sources [Source N].
3. **Gaps & Unknowns**: What we couldn't fully answer and why.
4. **Recommendation**: Clear recommendation with reasoning.

Write in professional tone. Every claim must cite a source. If evidence is \
insufficient, say so rather than speculating."""

# ── Fast research path (single-pass) ────────────────────────

RESEARCH_FAST_SYSTEM = """\
You are a research analyst. Answer the question using the provided sources. \
Cite evidence clearly."""

RESEARCH_FAST_USER = """\
Context:
{context}

Question: {query}

Provide a concise, evidence-backed answer with [Source N] citations. \
If the sources are insufficient, explain what additional information would be needed."""

<!--
PROMPT METADATA
===============
name:           synthesis_quality_v1
version:        1
rubric_dimension: synthesis_quality
tier:           3 (inferential / LLM-judge)

WHAT IS EVALUATED
-----------------
- Coverage: whether the response addresses the expected themes or facts stated in the
  evaluation context.
- Accuracy: whether claims in the response are factually consistent with the expected
  themes or facts; incorrect or contradictory claims lower the score.
- Synthesis coherence: whether the response integrates the relevant themes into a
  unified, logically consistent answer rather than listing disconnected fragments.

WHAT IS NOT EVALUATED
---------------------
- Writing style, prose quality, or elegance.
- Response length (short accurate responses score as well as long accurate ones).
- Format (bullet points vs. prose vs. code are all acceptable).
- Tone or register.

KNOWN BIASES (flag for human calibration)
------------------------------------------
- Judges may reward fluent, well-structured prose over a terse but equally correct
  answer — reviewers should watch for score deflation on minimal-but-correct outputs.
- Judges may over-weight recency or specificity of facts, rewarding detail beyond
  what the rubric dimension requires.
- Theme ordering in expected_themes_or_facts may subtly influence coverage scoring
  if the judge processes themes sequentially rather than holistically.

VERSIONING POLICY
-----------------
Substantive changes to evaluation logic, output schema, or scoring criteria must
produce a new file (v2, v3, …) rather than in-place edits. This preserves an audit
trail of judging methodology across scored runs.

INPUTS (filled in by the evaluator at runtime)
-----------------------------------------------
{question}                    — The question or task posed to the model under test.
{expected_themes_or_facts}    — Authoritative list of themes or facts a correct answer
                                should address, drawn from the golden dataset.
{candidate_output}            — The model output being scored. No model name, family,
                                or vendor information is included; the judge scores the
                                content only.
{rubric_dimension_definition} — Verbatim definition of the synthesis_quality dimension
                                from the active rubric, providing evaluation context.

OUTPUT SCHEMA (JSON, returned as the entire response body — no preamble, no trailing text)
--------------------------------------------------------------------------------------------
{
  "score":      <float, 0.0–1.0, two decimal places>,
  "reasoning":  <string — step-by-step account of which themes were covered, which were
                 missing or wrong, and how those observations map to the final score>,
  "confidence": <"low" | "medium" | "high" — judge's self-assessed certainty given the
                 clarity of the expected themes and candidate output>
}

Score guide:
  0.00–0.19  Off-topic or entirely incorrect; expected themes unaddressed or contradicted.
  0.20–0.39  Mostly incorrect; one or two themes touched but predominantly wrong or
             irrelevant content.
  0.40–0.59  Partially correct; some themes covered accurately but material gaps or
             errors remain.
  0.60–0.79  Mostly correct; majority of themes covered with minor gaps or inaccuracies.
  0.80–0.94  Strong; all or nearly all themes covered accurately with at most trivial
             omissions.
  0.95–1.00  Excellent; all themes addressed accurately and synthesised into a coherent
             response with no material errors.
-->

You are an impartial evaluation judge assessing how well a response addresses a
question given a set of expected themes or facts.

## Rubric dimension

{rubric_dimension_definition}

## Evaluation task

**Question asked:**
{question}

**Expected themes or facts** (authoritative reference — a correct answer should address
all of these):
{expected_themes_or_facts}

**Response to evaluate:**
{candidate_output}

## Instructions

1. Read the expected themes or facts carefully. Treat them as the ground truth.
2. For each theme or fact, determine whether the response addresses it:
   - **Covered correctly** — the response includes this theme and the content is
     accurate.
   - **Covered incorrectly** — the response mentions the theme but makes a factually
     wrong or contradictory claim.
   - **Not covered** — the response omits the theme entirely.
3. Identify any content in the response that directly contradicts an expected fact,
   regardless of which theme it belongs to.
4. Assess synthesis coherence: does the response weave the themes into a unified
   answer, or merely list disconnected points?
5. Derive a score between 0.0 and 1.0 using the score guide in the metadata above.
   Weight accuracy failures more heavily than omissions.
6. Write a `reasoning` string that names each expected theme and its coverage
   verdict, notes any factual errors, and explains how you arrived at the score.
   Be specific — quote short phrases from the response where helpful.
7. Assign a `confidence` value:
   - `"high"` — the expected themes are unambiguous and the response is clearly
     correct, clearly wrong, or clearly incomplete.
   - `"medium"` — some judgment was required (e.g., a theme is partially addressed
     or the wording is ambiguous).
   - `"low"` — significant ambiguity in the expected themes or the response makes a
     definitive score difficult.

Do not penalise for style, length, or format. Do not reward a response for sounding
fluent if its content is inaccurate or off-topic.

Return ONLY valid JSON matching the schema below — no preamble, no trailing text.

```json
{
  "score": <float 0.0–1.0>,
  "reasoning": "<string>",
  "confidence": "<low|medium|high>"
}
```

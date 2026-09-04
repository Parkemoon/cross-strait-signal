"""LinkedIn post draft generator for the proposer (scripts/propose_linkedin_post.py).

Turns one selected cluster (shared/linkedin_selector.describe_cluster
output) into a draft post. The model writes ONLY the four prose pieces
— headline, what happened, Taiwan-side framing, PRC-side framing — from
the STORED analysis (titles, summaries, key quotes, scores). Everything
structural is assembled in code: the "Taiwan-side framing:" / "PRC-side
framing:" labels, the mean sentiment scores (computed by the selector,
never by the model), and the link line. So the format is guaranteed and
the numbers cannot be hallucinated.

Borrows the Tier-1 prompt's rule blocks (analyst intro, romanisation,
British English, terminology glossary) from ai_pipeline rather than
writing a fresh prompt — same plumbing as visits_extract.py. Uses the
Tier-2 model (gemini-3.5-flash): two calls a week, quality over cost.

`validate_post` is the hard gate for the post rules (length, first-line
length, no em-dashes, no hashtags, Chinese only when it is a stored key
quote). One retry with the violations fed back; a draft that still fails
is returned with `needs_edit` set so the email says so instead of
silently shipping a broken post. Nothing here writes to the DB.
"""
from __future__ import annotations

import re

from scraper.processors.ai_pipeline import (
    _ANALYST_INTRO,
    _BRITISH_ENGLISH_RULE,
    _ROMANISATION_RULE,
    client,
    generate_dynamic_glossary,
)
from scraper.utils.llm import parse_llm_json
from scraper.utils.usage_log import log_usage
from shared.sentiment_band import sentiment_band

_MODEL = "gemini-3.5-flash"

SITE_URL = "https://strait-signal.net/"
MAX_CHARS = 1300
MAX_FIRST_LINE = 210
MAX_QUOTES_PER_SIDE = 4

_CJK_RUN = re.compile(r'[一-鿿㐀-䶿]{2,}')
_HASHTAG = re.compile(r'(?:^|\s)#\w')

_POST_RULES = """You are drafting a LinkedIn post for Cross-Strait Signal, an open-source dashboard that reads PRC and Taiwan media side by side. The post shows ONE story as each side of the strait framed it. The reader is a professional audience; the register is plain and declarative.

Write from the STORED MATERIAL below and nothing else. Every fact, name, date, number and quotation must appear in that material. Do not add background, context, history or interpretation that is not in it. If the material does not say something, leave it out.

Return JSON with exactly these keys:
- "headline": one English line, under 200 characters, that stands alone (LinkedIn truncates after about 210 characters). Name the story, not the site.
- "what_happened": one or two short sentences on the event itself, neutral, English only.
- "tw_framing": one or two short sentences on how the Taiwan-side outlets framed the story. Name at least one outlet. You may quote a stored key quote verbatim in Chinese, followed by its English gloss in brackets; only from the TAIWAN-SIDE quotes listed.
- "prc_framing": the same for the PRC-side outlets, only from the PRC-SIDE quotes listed.

Style rules (mandatory):
- Short sentences. Plain declarative register. No rhetorical questions, no exclamation marks.
- Do NOT use em-dashes or en-dashes anywhere. Use commas or full stops.
- No hashtags. No emoji. No calls to action. No mention of sentiment scores (they are appended in code).
- Do not write the labels "Taiwan-side framing:" or "PRC-side framing:" yourself; they are added in code.
- Chinese characters may appear ONLY inside a verbatim stored key quote, and every Chinese quote must be followed by an English gloss in brackets. Never translate chrome or labels into Chinese.
- Keep the four pieces together under 900 characters so the assembled post stays under 1300.
"""


def _side_block(label: str, rows: list[dict]) -> str:
    if not rows:
        return f"{label}: (no articles)\n"
    lines = [f"{label} ({len(rows)} article(s)):"]
    for r in rows[:MAX_QUOTES_PER_SIDE]:
        lines.append(f"- Outlet: {r.get('outlet')} | Published: {(r.get('published_at') or '')[:10]}")
        lines.append(f"  Title: {r.get('title_en') or ''}")
        if r.get('summary_en'):
            lines.append(f"  Summary: {r['summary_en']}")
        if r.get('key_quote'):
            lines.append(f"  Key quote (original): {r['key_quote']}")
        if r.get('key_quote_en'):
            lines.append(f"  Key quote (English): {r['key_quote_en']}")
    if len(rows) > MAX_QUOTES_PER_SIDE:
        lines.append(f"- ({len(rows) - MAX_QUOTES_PER_SIDE} further article(s) from: "
                     + ", ".join(sorted({r.get('outlet') for r in rows[MAX_QUOTES_PER_SIDE:]})) + ")")
    return "\n".join(lines) + "\n"


def build_prompt(cluster: dict, feedback: list[str] | None = None) -> str:
    sides = cluster['sides']
    material = (
        f"STORY (cluster {cluster['cluster_id']}, {cluster['n_articles']} articles, "
        f"{(cluster.get('oldest_published') or '')[:10]} to {(cluster.get('newest_published') or '')[:10]}, "
        f"dominant topic {cluster.get('dominant_topic')}):\n\n"
        + _side_block("TAIWAN-SIDE", sides['TW'])
        + "\n" + _side_block("PRC-SIDE", sides['PRC'])
    )
    if sides.get('INTL'):
        material += "\n" + _side_block("INTERNATIONAL (context only, do not attribute framing to a side)", sides['INTL'])

    glossary_text = " ".join(
        (r.get('key_quote') or '') + ' ' + (r.get('title_en') or '')
        for rows in sides.values() for r in rows
    )
    glossary = generate_dynamic_glossary(glossary_text)

    retry = ""
    if feedback:
        retry = ("\nYOUR PREVIOUS DRAFT BROKE THESE RULES; fix every one of them:\n"
                 + "\n".join(f"- {f}" for f in feedback) + "\n")

    return (
        _ANALYST_INTRO + _POST_RULES + "\nOUTPUT RULES:\n" + _ROMANISATION_RULE
        + _BRITISH_ENGLISH_RULE + glossary + retry + "\nSTORED MATERIAL:\n\n" + material
    )


def fmt_score(v) -> str:
    """Comma-separated (the whole framing suffix already sits in brackets)."""
    if v is None:
        return "n/a"
    return f"{v:+.2f}, {sentiment_band(v)}"


def assemble_post(parts: dict, cluster: dict, site_url: str = SITE_URL) -> str:
    """Deterministic assembly: headline / what happened / two labelled
    framing lines with the code-computed mean scores / link."""
    def clean(s):
        return re.sub(r'\s+', ' ', (s or '')).strip()

    lines = [
        clean(parts.get('headline')),
        "",
        clean(parts.get('what_happened')),
        "",
        f"Taiwan-side framing: {clean(parts.get('tw_framing'))} "
        f"(mean sentiment {fmt_score(cluster.get('tw_mean'))}, "
        f"{len(cluster.get('tw_outlets', []))} outlet(s))",
        "",
        f"PRC-side framing: {clean(parts.get('prc_framing'))} "
        f"(mean sentiment {fmt_score(cluster.get('prc_mean'))}, "
        f"{len(cluster.get('prc_outlets', []))} outlet(s))",
        "",
        f"Both sides, side by side, on the feed: {site_url}",
    ]
    return "\n".join(lines)


def stored_quotes(cluster: dict) -> list[str]:
    out = []
    for rows in cluster['sides'].values():
        for r in rows:
            if r.get('key_quote'):
                out.append(r['key_quote'])
    return out


def validate_post(post: str, cluster: dict) -> list[str]:
    """Return the list of rule violations (empty = clean). Pure."""
    problems = []
    if len(post) > MAX_CHARS:
        problems.append(f"post is {len(post)} characters; limit {MAX_CHARS}")
    first = post.split("\n", 1)[0]
    if not first.strip():
        problems.append("first line is empty")
    elif len(first) > MAX_FIRST_LINE:
        problems.append(f"first line is {len(first)} characters; limit {MAX_FIRST_LINE}")
    if "—" in post or "–" in post:
        problems.append("contains an em-dash or en-dash")
    if _HASHTAG.search(post):
        problems.append("contains a hashtag")
    quotes = stored_quotes(cluster)
    for run in _CJK_RUN.findall(post):
        if not any(run in q for q in quotes):
            problems.append(f"Chinese text not found in any stored key quote: {run[:20]}")
    return problems


def _call_model(prompt: str) -> dict:
    resp = client.models.generate_content(
        model=_MODEL,
        contents=prompt,
        config={
            "response_mime_type": "application/json",
            # gemini-3.5-flash spends thinking tokens out of this budget
            # (~2k thoughts on a draft); 2000 truncated every response.
            "max_output_tokens": 8000,
            "temperature": 0.3,
            "thinking_config": {"thinking_level": "low"},
        },
    )
    log_usage("linkedin_draft", _MODEL, resp, article_id=None)
    parsed = parse_llm_json(resp.text)
    if not isinstance(parsed, dict):
        raise ValueError(f"model returned {type(parsed).__name__}, expected object")
    return parsed


def generate_draft(cluster: dict, site_url: str = SITE_URL, retries: int = 1) -> dict:
    """{'post', 'parts', 'violations', 'needs_edit', 'attempts', 'model'}.
    Raises on API / JSON failure (caller decides)."""
    feedback = None
    post, parts, problems = "", {}, []
    attempts = 0
    for attempts in range(1, retries + 2):
        parts = _call_model(build_prompt(cluster, feedback))
        post = assemble_post(parts, cluster, site_url)
        problems = validate_post(post, cluster)
        if not problems:
            break
        feedback = problems
    return {
        'post': post,
        'parts': parts,
        'violations': problems,
        'needs_edit': bool(problems),
        'attempts': attempts,
        'model': _MODEL,
        'chars': len(post),
    }

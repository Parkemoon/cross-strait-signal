"""
Lightweight translation pass for social_pulse items.
Uses Gemini Flash Lite — translation only, no classification.
Runs after social scrapers, before the main AI article pipeline.
"""

import os
import sys
import time
import json
from dotenv import load_dotenv

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

load_dotenv()

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from google import genai
from scraper.utils.db import get_connection

_GLOSSARY_PATH = os.path.join(os.path.dirname(__file__), 'glossary.json')
with open(_GLOSSARY_PATH, encoding='utf-8') as _f:
    _MASTER_GLOSSARY = json.load(_f)


def _build_glossary_block(titles):
    """Return a terminology mapping block for any glossary terms found in the batch."""
    combined = ' '.join(titles)
    found = {zh: en for zh, en in _MASTER_GLOSSARY.items() if zh in combined}
    if not found:
        return ""
    lines = [f"- {zh} MUST be translated as: {en}" for zh, en in found.items()]
    return (
        "\n\nCRITICAL TERMINOLOGY MAPPING — you are strictly forbidden from deviating from these translations:\n"
        + "\n".join(lines)
    )

client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

TRANSLATION_PROMPT = """You are translating Chinese social media content into English for a cross-strait intelligence dashboard.

Translate each item below. These are either Weibo trending keywords or PTT (Taiwan BBS) post titles.

Rules:
- Preserve political and military terminology precisely
- PTT titles use informal internet Chinese, slang, and sometimes coded language — translate the meaning, not just the words
- Weibo keywords are often 2-6 character topic labels — give a concise but clear English equivalent
- Do not add commentary or explanation
- Return ONLY a JSON array of strings, one translation per item, in the same order as input
- Example input: ["台海軍演", "共機擾台"] → Example output: ["Taiwan Strait military exercise", "PLA aircraft incursion into Taiwan airspace"]

Items to translate:
{items}

Return ONLY a JSON array of strings. No markdown, no commentary."""


def translate_social_pulse(batch_size=20):
    """Translate untranslated social_pulse items using Gemini Flash Lite."""
    conn = get_connection()

    rows = conn.execute("""
        SELECT id, title, platform FROM social_pulse
        WHERE title_en IS NULL AND item_key != '__none__'
        ORDER BY scraped_at DESC
        LIMIT 100
    """).fetchall()

    if not rows:
        print("  No social pulse items to translate")
        conn.close()
        return

    print(f"  Translating {len(rows)} social pulse items...")

    # Process in batches
    for i in range(0, len(rows), batch_size):
        batch = rows[i:i + batch_size]
        titles = [r['title'] for r in batch]

        glossary_block = _build_glossary_block(titles)
        prompt = TRANSLATION_PROMPT.format(items=str(titles)) + glossary_block

        try:
            response = client.models.generate_content(
                model='gemini-2.5-flash-lite',
                contents=prompt,
            )
            raw = response.text.strip()

            # Strip markdown code blocks if present
            if raw.startswith('```'):
                raw = raw.split('```')[1]
                if raw.startswith('json'):
                    raw = raw[4:]
                raw = raw.strip()

            translations = json.loads(raw)

            if not isinstance(translations, list) or len(translations) != len(batch):
                print(f"  Translation batch returned unexpected format, skipping")
                continue

            for row, translation in zip(batch, translations):
                conn.execute(
                    "UPDATE social_pulse SET title_en = ? WHERE id = ?",
                    (translation.strip(), row['id'])
                )
                print(f"  [{row['platform']}] {row['title'][:40]} → {translation[:50]}")

            conn.commit()
            time.sleep(0.5)  # brief pause between batches

        except Exception as e:
            print(f"  Translation batch failed: {e}")
            continue

    conn.close()
    print("  Social pulse translation complete")


if __name__ == '__main__':
    translate_social_pulse()

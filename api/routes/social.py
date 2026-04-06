from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from api.database import get_db
from scraper.processors.keyword_filter import PRC_MUST_MENTION_TAIWAN

router = APIRouter(prefix="/api/social", tags=["social"])


class TranslationCorrection(BaseModel):
    title_en_override: str


@router.get("/")
def social_pulse():
    """Return the latest social pulse snapshot: Weibo hot search + PTT trending posts."""
    conn = get_db()

    # --- Weibo: most recent scrape batch ---
    # Find the latest scraped_at for weibo, then get all items within 10 minutes of it
    latest_weibo = conn.execute("""
        SELECT MAX(scraped_at) as latest FROM social_pulse WHERE platform = 'weibo'
    """).fetchone()

    weibo_items = []
    weibo_last_updated = None

    if latest_weibo and latest_weibo['latest']:
        weibo_last_updated = latest_weibo['latest']
        rows = conn.execute("""
            SELECT id, item_key, title, title_en, title_en_override,
                   rank_position, heat_index, scraped_at
            FROM social_pulse
            WHERE platform = 'weibo'
              AND item_key != '__none__'
              AND scraped_at >= datetime(?, '-10 minutes')
            ORDER BY rank_position ASC NULLS LAST
        """, (weibo_last_updated,)).fetchall()

        for r in rows:
            title = r["title"]
            is_cross_strait = any(kw.lower() in title.lower() for kw in PRC_MUST_MENTION_TAIWAN)
            weibo_items.append({
                "id": r["id"],
                "item_key": r["item_key"],
                "title": title,
                "title_en": r["title_en_override"] or r["title_en"],
                "title_en_raw": r["title_en"],
                "title_en_override": r["title_en_override"],
                "rank_position": r["rank_position"],
                "heat_index": r["heat_index"],
                "is_cross_strait": is_cross_strait,
                "scraped_at": r["scraped_at"],
            })

    # --- PTT: last 24h, high-push posts, limit 8 ---
    latest_ptt = conn.execute("""
        SELECT MAX(scraped_at) as latest FROM social_pulse WHERE platform = 'ptt'
    """).fetchone()

    ptt_items = []
    ptt_last_updated = None

    if latest_ptt and latest_ptt['latest']:
        ptt_last_updated = latest_ptt['latest']
        rows = conn.execute("""
            SELECT id, item_key, title, title_en, title_en_override,
                   push_count, boo_count, board, url, scraped_at
            FROM social_pulse
            WHERE platform = 'ptt'
              AND scraped_at >= datetime('now', '-1 day')
              AND push_count >= 2
            ORDER BY push_count DESC
            LIMIT 8
        """).fetchall()

        for r in rows:
            ptt_items.append({
                "id": r["id"],
                "title": r["title"],
                "title_en": r["title_en_override"] or r["title_en"],
                "title_en_raw": r["title_en"],
                "title_en_override": r["title_en_override"],
                "push_count": r["push_count"],
                "boo_count": r["boo_count"],
                "board": r["board"],
                "url": r["url"],
                "scraped_at": r["scraped_at"],
            })

    conn.close()

    return {
        "weibo": {
            "items": weibo_items,
            "last_updated": weibo_last_updated,
        },
        "ptt": {
            "items": ptt_items,
            "last_updated": ptt_last_updated,
        },
    }


@router.patch("/{item_id}/translation")
def correct_translation(item_id: int, body: TranslationCorrection):
    """Save an analyst translation correction for a social pulse item."""
    conn = get_db()

    row = conn.execute("SELECT id FROM social_pulse WHERE id = ?", (item_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Social pulse item not found")

    conn.execute(
        "UPDATE social_pulse SET title_en_override = ? WHERE id = ?",
        (body.title_en_override.strip(), item_id)
    )
    conn.commit()
    conn.close()
    return {"ok": True, "id": item_id, "title_en_override": body.title_en_override.strip()}

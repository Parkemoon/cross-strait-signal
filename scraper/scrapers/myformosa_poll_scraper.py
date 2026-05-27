"""My-Formosa 美麗島民調 scraper — Phase 2d pollster-direct ingestion.

My-Formosa's polling-topical page (`Topical/formosapollster`) is rendered
client-side and the article pages are served as Big5 — Playwright handles
both cleanly in one session. We filter to anchors whose visible text
starts with "美麗島民調" (the canonical prefix the pollster uses for its
own releases; non-prefixed entries on that page are commentary, not poll
output).

Each article exposes its date in a `.date` element and the prose body
includes the methodology block (sampling design, fielding window, sample
size) that the AI poll-extraction prompt needs. The existing Step 3c
title trigger (`%民調%`) catches these once the keyword pre-filter rejects
them — and they almost always are rejected, since these are TW domestic
polls that don't mention PRC.
"""
import sys
import os
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from scraper.utils.db import get_connection, article_exists

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

LIST_URL = 'https://my-formosa.com.tw/Topical/formosapollster'
TITLE_PREFIX = '美麗島民調'


def _to_utc(date_str):
    """My-Formosa dates render as 'YYYY-MM-DD'. Anchor to midnight UTC."""
    if not date_str:
        return datetime.now(timezone.utc).isoformat()
    try:
        return datetime.strptime(date_str.strip(), '%Y-%m-%d').replace(tzinfo=timezone.utc).isoformat()
    except (ValueError, TypeError):
        return datetime.now(timezone.utc).isoformat()


def scrape_myformosa_polls():
    """Drive Playwright through the topical list + each article page."""
    from playwright.sync_api import sync_playwright

    conn = get_connection()
    source = conn.execute("SELECT * FROM sources WHERE name = 'My-Formosa'").fetchone()
    if not source:
        print("  My-Formosa source not found — run seed_sources.py first")
        conn.close()
        return 0

    print("\nScraping: My-Formosa 美麗島民調")
    new_count = 0

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.set_default_timeout(25000)
            try:
                page.goto(LIST_URL, wait_until='networkidle')
            except Exception as e:
                print(f"  Error loading list: {e}")
                return 0

            # Polls index — every anchor whose visible text starts with
            # '美麗島民調' is a pollster-owned release. Non-prefixed entries
            # ('吳子嘉：…', '國民黨自亂陣腳…') are commentary and skipped.
            entries = page.evaluate("""
                () => Array.from(document.querySelectorAll('a'))
                    .map(a => ({
                        url: a.href,
                        title: (a.textContent || '').trim(),
                    }))
                    .filter(x => x.url.includes('my-formosa.com.tw/DOC_')
                                 && x.title.startsWith('美麗島民調'))
            """)
            # Dedupe by URL — same article often appears twice (thumbnail
            # variant + headline variant).
            seen = set()
            ordered = []
            for e in entries:
                u = e['url'].split('?')[0]
                if u in seen:
                    continue
                seen.add(u)
                ordered.append({'url': u, 'title': e['title']})
            print(f"  Found {len(ordered)} 美麗島民調 entries")

            for entry in ordered:
                if article_exists(conn, entry['url']):
                    continue

                article_page = browser.new_page()
                article_page.set_default_timeout(25000)
                content, published_at = '', datetime.now(timezone.utc).isoformat()
                try:
                    article_page.goto(entry['url'], wait_until='networkidle')
                    # Date sits in a .date span next to the view counter.
                    date_text = article_page.evaluate(
                        "() => document.querySelector('.date')?.textContent?.trim()"
                    )
                    published_at = _to_utc(date_text)
                    # Pull the article body. The container varies across
                    # template versions, so try a few then fall back to
                    # the article element / main / body innerText.
                    content = article_page.evaluate("""
                        () => {
                            const sels = ['.article_content', '.content', 'article', 'main'];
                            for (const s of sels) {
                                const el = document.querySelector(s);
                                if (el && el.innerText && el.innerText.length > 300) {
                                    return el.innerText.trim();
                                }
                            }
                            return document.body.innerText.trim();
                        }
                    """) or ''
                except Exception as e:
                    print(f"    Could not fetch {entry['url']}: {e}")
                finally:
                    article_page.close()

                print(f"  New: {entry['title'][:70]}")
                conn.execute("""
                    INSERT INTO articles (source_id, url, title_original, content_original, language, published_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (source['id'], entry['url'], entry['title'], content[:25000],
                      'zh-tw', published_at))
                new_count += 1
        finally:
            browser.close()

    conn.commit()
    conn.close()
    print(f"  Saved {new_count} new articles from My-Formosa")
    return new_count


if __name__ == '__main__':
    scrape_myformosa_polls()

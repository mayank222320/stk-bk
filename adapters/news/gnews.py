import time

import feedparser
import httpx


async def fetch_google_news(symbols: list[str], window: str = "1h") -> list[dict]:
    """
    Fetch Google News RSS for specific symbols.
    window: '1h', '1d', etc.
    """
    items = []

    async with httpx.AsyncClient(follow_redirects=True) as client:
        for sym in symbols:
            url = f"https://news.google.com/rss/search?q=%22{sym}%22+when:{window}&hl=en-IN&gl=IN&ceid=IN:en"
            try:
                resp = await client.get(url, timeout=5.0)
                if resp.status_code == 200:
                    feed = feedparser.parse(resp.text)
                    for entry in feed.entries[:5]:
                        ts = time.mktime(entry.published_parsed) if hasattr(entry, "published_parsed") and entry.published_parsed else time.time()
                        items.append({
                            "title": entry.get("title", ""),
                            "url": entry.get("link", ""),
                            "source": "Google News",
                            "symbol": sym,
                            "published_ts": int(ts)
                        })
            except Exception as e:
                print(f"[GNews] Failed for {sym}: {e}")

    return items

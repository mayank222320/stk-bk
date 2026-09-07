# scheduler feature: morning & evening automated routines
# New flow:
#   STEP 1 — Gemini (Search) → generates today's dynamic watchlist
#   STEP 2 — yfinance → fetches numeric data for cross-verification only
#   STEP 3 — Gemini cross-check: if divergence found, Gemini re-verifies; Gemini data wins
#   STEP 4 — Gemini deep research → full QMAF recommendation per stock

import json
import re
import asyncio
from datetime import datetime, timezone
from pathlib import Path

from apscheduler.schedulers.asyncio import AsyncIOScheduler  # type: ignore
from apscheduler.triggers.cron import CronTrigger  # type: ignore

from core.config import (
    SCHEDULER_MORNING_TIME,
    SCHEDULER_EVENING_TIME,
    SCHEDULER_TIMEZONE,
    MAX_WATCHLIST_STOCKS,
)
from core.database import mongo
from features.market_data.service import (
    fetch_for_verification,
    cross_check,
    format_verification_block,
)
from features.market_data.technical_indicators import (
    fetch_technical_indicators,
    fetch_option_chain,
    fetch_fii_dii_flows,
    format_technical_block,
    format_option_chain_block,
    format_fii_dii_block,
)
from features.knowledge_base.service import get_simple_rag_chunks, format_rag_context
from features.gemini.service import generate_with_gemini_fallback
from features.notifications.service import broadcast
from features.performance.service import log_recommendation, evaluate_day
from features.chat_memory.service import save_morning_alert
from features.bot.setup import bot
from core.config import USER_ID


# ─────────────────────── Scheduler instance ───────────────────────
scheduler = AsyncIOScheduler(timezone=SCHEDULER_TIMEZONE)


def start_scheduler() -> None:
    morning_h, morning_m = _parse_time(SCHEDULER_MORNING_TIME)
    evening_h, evening_m = _parse_time(SCHEDULER_EVENING_TIME)

    scheduler.add_job(
        morning_routine,
        CronTrigger(hour=morning_h, minute=morning_m, timezone=SCHEDULER_TIMEZONE),
        id="morning_routine",
        replace_existing=True,
    )
    scheduler.add_job(
        evening_routine,
        CronTrigger(hour=evening_h, minute=evening_m, timezone=SCHEDULER_TIMEZONE),
        id="evening_routine",
        replace_existing=True,
    )
    # 2 in-session checks (Phase 4.6 safety net)
    for hh, mm, tag in ((12, 0, "midday"), (15, 10, "preclose")):
        scheduler.add_job(
            swing_tracker_routine,
            CronTrigger(day_of_week='mon-fri', hour=hh, minute=mm, timezone=SCHEDULER_TIMEZONE),
            id=f"swing_check_{tag}",
            replace_existing=True,
            coalesce=True,
            misfire_grace_time=1800
        )
    # EOD tracker
    scheduler.add_job(
        swing_tracker_routine,
        CronTrigger(day_of_week='mon-fri', hour=15, minute=45, timezone=SCHEDULER_TIMEZONE),
        id="swing_tracker",
        replace_existing=True,
        coalesce=True,
        misfire_grace_time=3600
    )
    scheduler.add_job(
        paper_tracker_routine,
        CronTrigger(day_of_week='mon-fri', hour=15, minute=45, timezone=SCHEDULER_TIMEZONE),
        id="paper_tracker",
        replace_existing=True,
        coalesce=True,
        misfire_grace_time=3600
    )
    scheduler.add_job(
        news_scanner_routine,
        CronTrigger(day_of_week='mon-fri', hour='9-15', minute='*/5', timezone=SCHEDULER_TIMEZONE),
        id='news_scanner',
        replace_existing=True,
    )
    scheduler.add_job(
        check_capacity,
        CronTrigger(hour=16, minute=0, timezone=SCHEDULER_TIMEZONE),
        id="storage_capacity_check",
        replace_existing=True,
    )
    scheduler.start()
    print(
        f"[Scheduler] Started — Morning: {SCHEDULER_MORNING_TIME}, "
        f"Evening: {SCHEDULER_EVENING_TIME} ({SCHEDULER_TIMEZONE})"
    )


def stop_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
        print("[Scheduler] Stopped.")


# ═══════════════════════════════════════════════════════════════════
#  MORNING ROUTINE
# ═══════════════════════════════════════════════════════════════════
async def morning_routine() -> None:
    now = datetime.now(timezone.utc)
    today = now.strftime("%Y-%m-%d")
    print(f"[Morning] Starting at {today}")

    # ── Check for weekends ─────────────────────────────────────────
    if now.weekday() >= 5:  # 5=Saturday, 6=Sunday
        print("[Morning] Weekend detected. Market closed.")
        message = "🛑 <b>Market Closed</b>\n\nToday is a weekend. The NSE is closed, so no morning stock recommendations will be generated. See you on Monday!"
        if USER_ID:
            try:
                await bot.send_message(chat_id=int(USER_ID), text=message, parse_mode="HTML")
            except Exception as e:
                print(f"[Morning] Failed to send weekend msg: {e}")
        await broadcast(text="Market closed for the weekend.", title="🛑 Weekend", ntfy_priority="default")
        return

    # ── STEP 1: Gemini generates today's dynamic watchlist ─────────
    symbols = await _gemini_generate_watchlist()
    if not symbols:
        print("[Morning] Gemini returned empty watchlist — aborting.")
        return

    print(f"[Morning] Watchlist for today: {', '.join(symbols)}")

    # ── Save today's watchlist to DB for evening routine ──────────
    if mongo.db is not None:
        await mongo.db.daily_watchlist.replace_one(
            {"date": today},
            {"date": today, "symbols": symbols, "created_at": datetime.now(timezone.utc)},
            upsert=True,
        )

    # ── Process each symbol ───────────────────────────────────────
    for symbol in symbols:
        await _process_symbol(symbol, today)
        # Add a delay between symbols to prevent Gemini API rate limits
        await asyncio.sleep(5)


async def _gemini_generate_watchlist() -> list[str]:
    """
    STEP 1: Ask Gemini (with live Google Search) to identify today's best
    NSE stocks based on current market conditions, momentum, news, and technicals.
    Returns a clean list of NSE ticker symbols.
    """
    today = datetime.now(timezone.utc).strftime("%B %d, %Y")
    prompt = f"""You are a senior Indian stock market analyst with live market access.

Today is {today} (IST).

Task: Identify the TOP {MAX_WATCHLIST_STOCKS} NSE-listed stocks most suitable for today's trading session.

Selection criteria (mandatory):
1. Strong price momentum or key technical breakout/breakdown in progress
2. Significant news catalyst today (earnings, order win, promoter activity, corporate action)
3. Above-average volume and delivery percentage
4. Clear actionable setup — not sideways/range-bound
5. Must pass QMAF valuation guard: PEG < 1.5 or P/E < 1.2x 5-year median

For each stock provide a ONE-LINE rationale.

Respond STRICTLY in this JSON format (no extra text, no markdown):
{{
  "watchlist": [
    {{"symbol": "RELIANCE", "reason": "Breakout above 200 DMA on 3x volume with gas block win"}},
    {{"symbol": "INFY", "reason": "Earnings beat, delivery surge, bullish MACD crossover"}}
  ]
}}
"""
    try:
        result = await generate_with_gemini_fallback(prompt, model=None, use_search=True)
        text = result["text"].strip()

        # Strip markdown code fences if present
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.MULTILINE)
        text = re.sub(r"\s*```$", "", text, flags=re.MULTILINE)

        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1:
            text = text[start:end+1]

        data = json.loads(text)
        watchlist = data.get("watchlist", [])
        symbols = [
            item["symbol"].strip().upper()
            for item in watchlist
            if isinstance(item, dict) and "symbol" in item
        ]
        return symbols[:MAX_WATCHLIST_STOCKS]
    except json.JSONDecodeError:
        # Fallback: extract symbols with regex if JSON parse fails
        matches = re.findall(r'"symbol"\s*:\s*"([A-Z0-9&]+)"', result["text"])
        return [m.upper() for m in matches[:MAX_WATCHLIST_STOCKS]]
    except Exception as exc:
        print(f"[Morning] Watchlist generation failed: {exc}")
        return []


async def _process_symbol(symbol: str, today: str) -> None:
    print(f"[Morning] Processing {symbol}...")

    from adapters.market.yfinance import yfinance_adapter
    from adapters.market.nse import nse_adapter

    # ── STEP 2: verification fetch & cross-check ───────────────────────
    yf_stamped = await yfinance_adapter.get_quote(symbol)
    nse_stamped = await nse_adapter.get_quote(symbol)
    yf_data = await fetch_for_verification(symbol)

    yf_price = yf_stamped.value.get("price") if yf_stamped.value else None
    nse_price = nse_stamped.value.get("price") if nse_stamped.value else None

    check = cross_check(symbol, yf_price, nse_price)
    if check["verdict"] == "significant_divergence":
        from features.notifications.service import alert_ops
        await alert_ops(f"price divergence {symbol}", check["note"])
        print(f"[Morning] Skipping {symbol} due to price divergence.")
        return

    # ── STEP 3 & 4: Retry loop for Gemini calls ───────────────────
    max_retries = 3
    gemini_research = None
    report_text = ""
    
    for attempt in range(max_retries):
        try:
            gemini_research = await _gemini_research_stock(symbol)
            if not gemini_research:
                print(f"[Morning] Gemini research returned None for {symbol} on attempt {attempt + 1}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(5)
                    continue
                print(f"[Morning] Gemini research failed for {symbol} after {max_retries} attempts — skipping.")
                return

            report_text = await _gemini_deep_recommendation(symbol, gemini_research, yf_stamped, nse_stamped)
            if report_text and not report_text.startswith("❌"):
                break # Success!
                
            print(f"[Morning] Recommendation failed for {symbol} on attempt {attempt + 1}: {report_text}")
            if attempt < max_retries - 1:
                await asyncio.sleep(5)
        except Exception as e:
            print(f"[Morning] Exception on attempt {attempt + 1} for {symbol}: {e}")
            if attempt < max_retries - 1:
                await asyncio.sleep(5)
                
    if not gemini_research or not report_text or report_text.startswith("❌"):
        print(f"[Morning] Skipping {symbol} due to repeated AI failures.")
        return

    # ── Broadcast ─────────────────────────────────────────────────
    # 1. Convert Markdown bold to HTML bold
    fmt_report = re.sub(r"\*\*(.*?)\*\*", r"<b>\1</b>", report_text)
    
    # 2. Convert Markdown table to readable list for Telegram
    fmt_report = fmt_report.replace("|-------|-------|-------|", "").replace("|---|---|---|", "")
    def format_table_row(match):
        col1, col2, col3 = [c.strip() for c in match.groups()]
        if "Level" in col1 and "Price" in col2:
            return "" # Skip header
        return f"• <b>{col1}</b>: {col2}\n  <i>{col3}</i>"
    fmt_report = re.sub(r"\|(.*?)\|(.*?)\|(.*?)\|", format_table_row, fmt_report)
    
    # 3. Clean up double empty lines caused by header removal
    fmt_report = fmt_report.replace("\n\n\n", "\n\n")

    # 4. Truncate cleanly at a newline to avoid slicing in the middle of a word
    if len(fmt_report) > 3800:
        cut_idx = fmt_report.rfind('\n', 0, 3800)
        if cut_idx == -1: cut_idx = 3800
        fmt_report = fmt_report[:cut_idx] + "\n...\n\n[View full report on StockAI Dashboard]"
        
    # 5. Telegram only supports &amp;, &lt;, &gt;, and &quot;. html.escape produces &#x27; which breaks it.
    safe_report_text = fmt_report.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    
    # 6. Restore the HTML tags we safely injected for formatting
    safe_report_text = safe_report_text.replace('&lt;b&gt;', '<b>').replace('&lt;/b&gt;', '</b>')
    safe_report_text = safe_report_text.replace('&lt;i&gt;', '<i>').replace('&lt;/i&gt;', '</i>')
    
    message = f"📊 <b>Morning Report — {symbol}</b>\n\n{safe_report_text}"
    if USER_ID:
        try:
            await bot.send_message(chat_id=int(USER_ID), text=message, parse_mode="HTML")
        except Exception as exc:
            print(f"[Morning] Telegram failed for {symbol}: {exc}")

    await broadcast(
        text=f"Morning Report — {symbol}\n\n{report_text}",
        title=f"📊 {symbol} — Stock Alert",
        ntfy_priority="max",
    )

    # ── Persist to DB ─────────────────────────────────────────────
    await save_morning_alert(symbol, report_text)

    parsed = _parse_recommendation_fields(report_text)
    await log_recommendation(
        symbol=symbol,
        recommendation=parsed.get("recommendation", "UNKNOWN"),
        entry_zone=parsed.get("entry_zone", "N/A"),
        target=parsed.get("target", "N/A"),
        stop_loss=parsed.get("stop_loss", "N/A"),
        trade_type=parsed.get("trade_type", "N/A"),
        timeframe=parsed.get("timeframe", "N/A"),
        reason=parsed.get("reason", "See full report"),
        raw_ai_output=report_text,
        market_data_snapshot=yf_data,
    )

    # Auto-log virtual paper trade
    try:
        from features.portfolio.service import log_virtual_trade
        entry_price = nse_price or yf_price or 0.0
        await log_virtual_trade(
            symbol=symbol,
            recommendation=parsed.get('recommendation', 'UNKNOWN'),
            entry_price=float(entry_price),
            target=parsed.get('target', 'N/A'),
            stop_loss=parsed.get('stop_loss', 'N/A'),
            date=today,
        )
    except Exception as e:
        print(f'[Portfolio] Failed to log virtual trade for {symbol}: {e}')

    # Create swing position from reco
    try:
        from features.swing.service import create_from_reco
        
        # parse basic numeric values from parsed text (e.g., "1200 - 1210")
        def parse_float(v, default=0.0):
            try:
                import re
                nums = re.findall(r"[\d.]+", str(v).replace(',', ''))
                return float(nums[0]) if nums else default
            except:
                return default

        ez = parsed.get("entry_zone", "0")
        import re
        nums = re.findall(r"[\d.]+", ez.replace(',', ''))
        low = float(nums[0]) if nums else 0.0
        high = float(nums[1]) if len(nums) > 1 else low

        reco_dict = {
            "symbol": symbol,
            "recommendation": parsed.get("recommendation", "UNKNOWN"),
            "entry_low": low,
            "entry_high": high,
            "target1": parse_float(parsed.get("target", "0")),
            "stop_loss": parse_float(parsed.get("stop_loss", "0")),
            "setup": parsed.get("trade_type", "UNKNOWN"),
            "thesis": parsed.get("reason", "")
        }
        await create_from_reco(reco_dict, yf_data)
        
        from features.paper_portfolio.service import log_paper_trade
        # The reco dict expects a 'levels' sub-dict for log_paper_trade based on our spec
        paper_reco = reco_dict.copy()
        paper_reco["levels"] = {
            "entry_low": low,
            "entry_high": high,
            "target1": reco_dict["target1"],
            "stop_loss": reco_dict["stop_loss"]
        }
        await log_paper_trade(paper_reco, yf_data)
        
    except Exception as e:
        print(f'[SwingTracker] Failed to create swing/paper position for {symbol}: {e}')

    print(f"[Morning] Done for {symbol}")


async def _gemini_research_stock(symbol: str) -> dict | None:
    """
    STEP 3a: Gemini performs qualitative research on the stock.
    Does not ask for numerical data.
    """
    today = datetime.now(timezone.utc).strftime("%B %d, %Y")

    prompt = f"""You are a senior Indian market analyst with live market access.

Today is {today} (IST).
Stock: {symbol} (NSE)

Tasks:
1. Gather: Recent news, upcoming catalysts in the next 10 days, earnings dates.
2. Analyze: Sector context, promoter/insider activity, regulatory/governance flags.
3. Formulate the bear case, narrative bias, and evidence quality.

Respond in this EXACT valid JSON format (no markdown, no preamble, use double quotes, no trailing commas):
{{
  "key_news": ["news item 1"],
  "catalysts_next_10d": ["catalyst 1"],
  "earnings_date": "YYYY-MM-DD|unknown",
  "sector_context": "description",
  "promoter_or_insider_activity": "description",
  "regulatory_or_governance_flags": ["flag 1"],
  "bear_case": "description",
  "narrative_bias": "bullish|bearish|neutral",
  "evidence_quality": "confirmed|reported|unverified"
}}
"""
    try:
        result = await generate_with_gemini_fallback(prompt, model=None, use_search=True)
        text = result["text"].strip()
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.MULTILINE)
        text = re.sub(r"\s*```$", "", text, flags=re.MULTILINE)
        
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1:
            text = text[start:end+1]
            
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            import ast
            return ast.literal_eval(text)
    except Exception as exc:
        raw_text = result.get("text", "N/A") if "result" in locals() else "N/A"
        print(f"[Research] Failed for {symbol}: {exc}\nRaw output: {raw_text}")
        return None


async def _gemini_deep_recommendation(
    symbol: str, research: dict, yf_stamped, nse_stamped
) -> str:
    """
    STEP 4: With verified research data, yfinance cross-check, pre-calculated
    technical indicators, NSE option chain, and FII/DII flows — generate the
    full structured recommendation using prompt.txt QMAF framework.
    """
    master_prompt = ""
    try:
        from prompts import pick_prompt
        master_prompt = pick_prompt("morning_analysis")
    except Exception as e:
        print(f"Error picking prompt: {e}")

    # ── Parallel fetch: indicators + option chain + FII/DII ──────────
    indicators, option_chain, fii_dii = await asyncio.gather(
        fetch_technical_indicators(symbol),
        fetch_option_chain(symbol),
        fetch_fii_dii_flows(),
        return_exceptions=True,
    )
    # Handle any gather exceptions gracefully
    if isinstance(indicators,  Exception): indicators  = {"error": str(indicators)}
    if isinstance(option_chain, Exception): option_chain = {"error": str(option_chain)}
    if isinstance(fii_dii,     Exception): fii_dii     = {"error": str(fii_dii)}

    # ── Pull RAG context ─────────────────────────────────────────────
    from features.knowledge_base.service import get_rag_context
    rag_context = await get_rag_context("swing_analysis", top_k=6)

    research_block      = json.dumps(research, indent=2)
    tech_block          = format_technical_block(indicators)    if isinstance(indicators,  dict) else "[Technical Indicators] N/A"
    option_chain_block  = format_option_chain_block(option_chain) if isinstance(option_chain, dict) else "[Option Chain] N/A"
    fii_dii_block       = format_fii_dii_block(fii_dii)         if isinstance(fii_dii,     dict) else "[FII/DII Flows] N/A"
    
    from core.timeutils import fmt_ist, today_ist, is_market_hours
    from core.freshness import session_state
    
    ist_time_str = fmt_ist()
    session = session_state()
    is_trading = "yes" if session != "WEEKEND" else "no"
    
    quote_stamped = nse_stamped if (nse_stamped and nse_stamped.value) else yf_stamped
    q_state = quote_stamped.state if quote_stamped else "UNAVAILABLE"
    q_src = quote_stamped.source if quote_stamped else "none"
    q_age = f"{quote_stamped.age_seconds}s" if quote_stamped else "N/A"

    prompt = f"""{master_prompt}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
MORNING ANALYSIS TASK
Stock: {symbol} (NSE)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

AS-OF: {ist_time_str}   SESSION: {session}   TRADING DAY: {is_trading}
INPUT FRESHNESS: quote {q_state} (source {q_src}, age {q_age})
Never describe data as live unless its state says LIVE.

GEMINI QUALITATIVE RESEARCH:
{research_block}

{tech_block}

{option_chain_block}

{fii_dii_block}

{rag_context}

DATA AUTHORITY (non-negotiable):
- CMP, OHLCV, RSI, MACD, EMA/SMA, ATR, Bollinger, volume, PCR, max pain and FII/DII
  above are computed from exchange data. They are AUTHORITATIVE. Never substitute a
  number from search or memory.
- If your research contradicts a number above, add a "Data Conflict" note and lower
  Data Confidence. Do not silently replace the number.
- Any figure not in the blocks above must be labelled [FROM SEARCH] with its source.
- Base the stop on atr_stop_loss_1_5x unless structure clearly justifies otherwise;
  if you deviate, say why and keep R:R to T1 at 1:2 or better.
- Horizon is SHORT SWING: 2-10 trading days. Never propose an intraday trade.
- WAIT / NO TRADE is a valid and often correct answer.
"""
    try:
        result = await generate_with_gemini_fallback(prompt, model=None, use_search=False)
        return result["text"]
    except Exception as exc:
        return f"❌ Recommendation generation failed for {symbol}: {exc}"


# ═══════════════════════════════════════════════════════════════════
#  EVENING ROUTINE
# ═══════════════════════════════════════════════════════════════════
async def evening_routine() -> None:
    now = datetime.now(timezone.utc)
    today = now.strftime("%Y-%m-%d")
    print(f"[Evening] Starting at {today}")

    # ── Check for weekends ─────────────────────────────────────────
    if now.weekday() >= 5:
        print("[Evening] Weekend detected. Market closed.")
        message = "🛑 <b>Market Closed</b>\n\nEnjoy your weekend! No evening performance evaluations will run today."
        if USER_ID:
            try:
                await bot.send_message(chat_id=int(USER_ID), text=message, parse_mode="HTML")
            except Exception as e:
                pass
        return

    # Load today's symbols from DB (set by morning routine)
    symbols: list[str] = []
    if mongo.db is not None:
        doc = await mongo.db.daily_watchlist.find_one({"date": today})
        if doc:
            symbols = doc.get("symbols", [])

    if not symbols:
        print("[Evening] No watchlist found for today — aborting.")
        msg = (
            "📋 <b>Evening Calibration</b> — No Data\n\n"
            "No morning watchlist was found for today. "
            "This usually means the morning routine did not run or the market was closed."
        )
        if USER_ID:
            try:
                await bot.send_message(chat_id=int(USER_ID), text=msg, parse_mode="HTML")
            except Exception:
                pass
        return

    results_summary = []
    cards = []
    for symbol in symbols:
        # Use yfinance for closing price verification in the evening
        yf_data = await fetch_for_verification(symbol)
        if yf_data.get("error"):
            results_summary.append(f"{symbol}: data unavailable")
            cards.append(f"⚠️ <b>{symbol}</b> — Data unavailable")
            continue

        result = await evaluate_day(
            symbol=symbol,
            day_high=yf_data.get("high") or 0,
            day_low=yf_data.get("low") or 0,
            day_close=yf_data.get("cmp") or 0,
        )

        if "error" not in result:
            outcome = result['result']
            icon = "✅" if outcome == "PASS" else "❌"
            results_summary.append(f"{symbol}: {outcome} — {result['notes']}")
            cards.append(
                f"{icon} <b>{symbol}</b> — {outcome}\n"
                f"   📌 {result['notes']}"
            )
        else:
            err = result['error']
            results_summary.append(f"{symbol}: {err}")
            # Only show skipped in a clean way, not the raw error string
            if "No morning recommendation" in err:
                cards.append(f"⏭️ <b>{symbol}</b> — No morning recommendation (skipped)")
            else:
                cards.append(f"⚠️ <b>{symbol}</b> — {err}")

    ist_now = datetime.now(timezone.utc).strftime("%d %b %Y, %I:%M %p UTC")
    if results_summary:
        summary_text = (
            f"📋 <b>Evening Calibration Report</b>\n"
            f"🕒 {ist_now}\n"
            f"────────────────────\n"
            + "\n".join(cards)
        )
        if USER_ID:
            try:
                await bot.send_message(chat_id=int(USER_ID), text=summary_text, parse_mode="HTML")
            except Exception as exc:
                print(f"[Evening] Telegram failed: {exc}")

        await broadcast(
            text="Evening Calibration\n" + "\n".join(results_summary),
            title="📋 Evening Calibration",
            ntfy_priority="default",
        )

    print(f"[Evening] Done. {len(results_summary)} symbols evaluated.")

async def swing_tracker_routine() -> None:
    from features.swing.service import track_positions
    now = datetime.now(timezone.utc)
    if now.weekday() >= 5:
        return
    print(f'[SwingTracker] Running at {now.isoformat()}')
    events = await track_positions()
    print(f'[SwingTracker] {len(events)} events processed.')
    
    if events:
        lines = []
        for evt in events:
            # evt like ("STOP", "RELIANCE", 1.2)
            lines.append(f"• {evt[0]}: <b>{evt[1]}</b>" + (f" (r={evt[2]})" if evt[2] is not None else ""))
        
        msg = f"📊 <b>Swing Update</b>\n\n" + "\n".join(lines)
        if USER_ID:
            try:
                await bot.send_message(chat_id=int(USER_ID), text=msg, parse_mode="HTML")
            except Exception:
                pass

async def paper_tracker_routine() -> None:
    from features.paper_portfolio.service import track_paper_positions
    now = datetime.now(timezone.utc)
    if now.weekday() >= 5:
        return
    print(f'[PaperTracker] Running at {now.isoformat()}')
    events = await track_paper_positions()
    print(f'[PaperTracker] {len(events)} events processed.')
    
    if events:
        lines = []
        for evt in events:
            lines.append(f"• {evt[0]}: <b>{evt[1]}</b>" + (f" (r={evt[2]})" if evt[2] is not None else ""))
        
        msg = f"📝 <b>Paper Portfolio Update</b>\n\n" + "\n".join(lines)
        if USER_ID:
            try:
                await bot.send_message(chat_id=int(USER_ID), text=msg, parse_mode="HTML")
            except Exception:
                pass

async def news_scanner_routine() -> None:
    from features.news_scanner.service import run_news_scanner
    now = datetime.now(timezone.utc)
    if now.weekday() >= 5:
        return  # Skip weekends
    await run_news_scanner()

async def custom_stock_minute_scan() -> None:
    now = datetime.now(timezone.utc)
    if now.weekday() >= 5:
        return
    if not (3 <= now.hour <= 10):
        return
    if mongo.db is None:
        return
        
    today = now.strftime("%Y-%m-%d")
    docs = await mongo.db.performance_log.find({"date": today, "is_custom": True}).to_list(length=None)
    if not docs:
        return
        
    symbols = [doc["symbol"] for doc in docs]
    from features.intraday.service import run_intraday_scan
    await run_intraday_scan(symbols_override=symbols)


# ─────────────────────── Parsing helpers ───────────────────────
def _parse_recommendation_fields(text: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    patterns = {
        "recommendation": r"Recommendation\s*:\s*([A-Z]+)",
        "entry_zone": r"Entry[^:]*:\s*([\d,.\-–₹\s]+)",
        "target": r"Target[^:]*:\s*([\d,.\-–₹\s]+)",
        "stop_loss": r"Stop-Loss[^:]*:\s*([\d,.\-–₹\s]+)",
        "trade_type": r"Trade Type\s*:\s*(\w+(?:\s\w+)?)",
        "timeframe": r"Timeframe\s*:\s*(.+?)(?:\n|$)",
        "reason": r"Details\s*:\s*(.+?)(?:\n\n|\Z)",
    }
    for field, pattern in patterns.items():
        match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
        if match:
            fields[field] = match.group(1).strip()[:500]
    return fields


def _parse_time(time_str: str) -> tuple[int, int]:
    try:
        h, m = time_str.strip().split(":")
        return int(h), int(m)
    except Exception:
        return 9, 20

async def check_capacity() -> None:
    from features.storage.service import storage_stats
    from core.retention import cleanup
    
    print("[Storage] Running daily capacity check...")
    stats = await storage_stats()
    usage = stats.get("usage_percent", 0)
    
    if usage > 80:
        msg = f"⚠️ <b>Storage Warning</b>\n\nDatabase is at {usage:.1f}% capacity. Running automated cleanup..."
        if USER_ID:
            try:
                await bot.send_message(chat_id=int(USER_ID), text=msg, parse_mode="HTML")
            except Exception:
                pass
        
        res = await cleanup(dry_run=False, confirm=True)
        counts = res.get('deleted_counts', {})
        text = "\n".join([f"{k}: {v}" for k, v in counts.items()])
        
        new_stats = res.get('post_cleanup_stats', {})
        new_usage = new_stats.get('usage_percent', 0)
        
        msg_post = f"🧹 <b>Cleanup Complete</b>\n\nNew usage: {new_usage:.1f}%\nDeleted:\n{text}"
        if USER_ID:
            try:
                await bot.send_message(chat_id=int(USER_ID), text=msg_post, parse_mode="HTML")
            except Exception:
                pass
    else:
        # Just run regular background cleanup
        await cleanup(dry_run=False, confirm=True)
        print(f"[Storage] Capacity fine ({usage:.1f}%). Ran regular background cleanup.")

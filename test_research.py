import asyncio
from features.scheduler.service import _gemini_research_stock
from features.market_data.service import fetch_for_verification

async def main():
    yf_data = await fetch_for_verification("INFY")
    res = await _gemini_research_stock("INFY", yf_data)
    print("RESULT:", res)

asyncio.run(main())

import asyncio
from datetime import datetime, timezone
import sys
import os

# Ensure we can import from features
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from features.scheduler.service import _process_symbol

async def main():
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    print(f"Testing _process_symbol for RELIANCE on {today}")
    await _process_symbol("RELIANCE", today)
    print("Test complete.")

if __name__ == "__main__":
    asyncio.run(main())

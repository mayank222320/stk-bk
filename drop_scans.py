import asyncio
import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from core.database import mongo


async def main():
    await mongo.connect()
    try:
        print("Dropping intraday_scans collection to reclaim space...")
        await mongo.db.drop_collection("intraday_scans")
        print("Dropped intraday_scans successfully.")
    except Exception as e:
        print(f"Error dropping collection: {e}")
    finally:
        await mongo.close()

if __name__ == "__main__":
    asyncio.run(main())

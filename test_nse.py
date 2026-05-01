import asyncio
from artifacts.python_backend.app.services.nse_service import NseService # Wait, python_backend is not reachable like this unless sys.path is added. Let's just do it directly.

import sys
import os
sys.path.append(os.path.abspath('artifacts/python-backend'))
from app.services.nse_service import NseService

async def main():
    nse = NseService()
    print("Fetching equity...")
    data = await nse.fetch_nse("/api/historical/fiidii?startDate=01-04-2026&endDate=24-04-2026", "test1", ttl=60)
    print(data)

asyncio.run(main())
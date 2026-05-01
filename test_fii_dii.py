import asyncio
import sys
import os

sys.path.append(os.path.abspath('artifacts/python-backend'))
from app.services.fii_dii_service import FiiDiiService

async def main():
    svc = FiiDiiService()
    print("Fetching index_future...")
    data = await svc.get_flows("index_future", days=30)
    print("Result for index_future:", data)

    print("Fetching equity...")
    data_eq = await svc.get_flows("equity", days=30)
    print("Result for equity:", data_eq)

asyncio.run(main())
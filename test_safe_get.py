import asyncio
import httpx
import time

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/",
}

_cookies = ""
_cookie_expiry = 0

async def _refresh_cookies():
    global _cookies, _cookie_expiry
    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            resp = await client.get("https://www.nseindia.com", headers=HEADERS)
            set_cookie = resp.headers.get_list("set-cookie")
            if set_cookie:
                _cookies = "; ".join([c.split(";")[0] for c in set_cookie])
                _cookie_expiry = time.time() + 20 * 60
                print("Cookies refreshed:", _cookies)
            else:
                print("No cookies found in response")
    except Exception as e:
        print("Error refreshing cookies:", e)

async def safe_get(url: str, retries: int = 3):
    global _cookies, _cookie_expiry
    for attempt in range(retries):
        if not _cookies or time.time() > _cookie_expiry:
            await _refresh_cookies()
        headers = {**HEADERS, "Cookie": _cookies}
        try:
            async with httpx.AsyncClient(timeout=12.0, follow_redirects=True) as client:
                print(f"Attempt {attempt+1} fetching {url}")
                resp = await client.get(url, headers=headers)
                print("Status code:", resp.status_code)
                if resp.status_code == 403:
                    print("Got 403, refreshing cookies")
                    _cookies = ""  # Force refresh
                    continue
                if resp.status_code == 429:
                    print("Got 429, backing off")
                    await asyncio.sleep(2 ** attempt)
                    continue
                resp.raise_for_status()
                return resp.json()
        except Exception as e:
            print("Error fetching:", e)
            await asyncio.sleep(2)
    return None

async def main():
    s = "01-03-2026"
    e = "24-04-2026"
    url = f"https://www.nseindia.com/api/historical/fiidii?startDate={s}&endDate={e}"
    data = await safe_get(url)
    print("Equity Rows:", len(data.get("data", data) if data else []))

    url_fno = f"https://www.nseindia.com/api/historical/fnoparticipants?startDate={s}&endDate={e}"
    data_fno = await safe_get(url_fno)
    print("FNO Rows:", len(data_fno.get("data", data_fno) if data_fno else []))

asyncio.run(main())
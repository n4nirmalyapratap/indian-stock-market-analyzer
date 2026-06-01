---
name: Sub-industry taxonomy and admin overrides
description: How the curated Indian market sub-industry taxonomy works and the TradingView/Chart Studio routing rule
---

## Taxonomy location
`artifacts/python-backend/app/lib/universe.py` — `SUBSECTOR_TAXONOMY` dict (50+ sub-industries covering Banking, NBFC, Capital Markets, Insurance, IT, Pharma, Healthcare, FMCG, QSR, Retail, Autos, Metals, Chemicals, Oil & Gas, Power, Capital Goods, Defence, EMS, Cables, Infrastructure, Real Estate, Consumer Durables, Textiles, Cement, Jewellery, Media, Telecom, Sugar/Agri).

Every symbol in the taxonomy is also in `SUBSECTOR_SYMBOLS` which is merged into `ALL_SYMBOLS`, so the classifier always sees and fetches Yahoo data for them.

## Seeding flow
`_seed_taxonomy_stocks()` in `synthetic_sectors_service.py` runs at the start of every `refresh_classifications()` call. It upserts stub rows (`classified_ok=False`) for every taxonomy symbol via `ON CONFLICT (symbol) DO NOTHING` — so existing Yahoo-classified rows are never overwritten, and new symbols are queued for Yahoo fetch.

## Admin overrides
Table: `sub_industry_overrides` (`symbol`, `sub_industry`, UNIQUE on both).
- Backend: `/admin/subsectors` (GET), `/admin/subsectors/overrides` (POST/DELETE), `/admin/subsectors/reclassify` (POST)
- Admin UI page: `artifacts/admin-dashboard/src/pages/SubsectorManagerPage.tsx`
- Overrides are merged at query time in both `_load_classified_stocks()` (nightly worker) and `get_drilldown()` (drill-down view).
- An override stock contributes to the market-cap-weighted index only once Yahoo has filled in its `market_cap` (classified_ok=True in `stocks`). Admin can press "Reclassify" to trigger this immediately.

## TradingView rule
**NEVER link to `/chart/:symbol` from the sector rotation pages** — that page uses TradingView. Always use `/trading?symbol=X` (Chart Studio / ECharts). The drill-down constituent links in `SectorAnalytics.tsx` use `/trading?symbol=...`.

**Why:** User explicitly said they have Chart Studio with all the modern features they want; TradingView should not be used where Chart Studio exists.

"""
One-off verification script for the multi-taxonomy XBRL parser.

Runs `_parse_xbrl` against every cached XBRL file in
/app/data/xbrl_cache and prints the resolved 4 buckets per file.
Used to confirm the parser produces complete FII/DII numbers across
all five SEBI taxonomy versions present in the cache.

Run inside the backend container:
    docker compose -f docker-compose.dev.yml exec backend \\
        python -m scripts.verify_xbrl_parser
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

# Import the parser from the live service module so this verifies
# the same code the API will use, not a copy.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.services.shareholding_service import _parse_xbrl  # noqa: E402

CACHE = Path("/app/data/xbrl_cache")


def _meta(xml: bytes) -> tuple[str, str, str]:
    """Pull (period_date, taxonomy_version, symbol) for the report row."""
    text = xml.decode("utf-8", errors="ignore")
    period = re.search(r"<xbrli:instant>(\d{4}-\d{2}-\d{2})", text)
    taxo = re.search(r"xbrl/shp/(\d{4}-\d{2}-\d{2})", text)
    sym = re.search(r"NSESymbol\">([^<]+)", text)
    return (
        period.group(1) if period else "??",
        taxo.group(1) if taxo else "??",
        sym.group(1) if sym else "??",
    )


def main() -> int:
    files = sorted(CACHE.glob("*.xml"))
    if not files:
        print(f"No files in {CACHE}", file=sys.stderr)
        return 1

    # Header
    print(f"{'period':<12} {'taxo':<12} {'sym':<9} "
          f"{'prom':>6} {'fii':>6} {'dii':>6} {'pub':>6} {'gov':>5} "
          f"{'sum':>7} {'pldg':>5} {'demat':>6} {'lock':>5} "
          f"{'#named':>6} {'flags':>5}  result")
    print("-" * 125)

    by_taxo: dict[str, list[bool]] = {}
    for f in files:
        try:
            xml = f.read_bytes()
        except Exception as e:
            print(f"  read fail {f.name}: {e}")
            continue
        period, taxo, sym = _meta(xml)
        parsed = _parse_xbrl(xml)

        if parsed is None:
            row = (f"{period:<12} {taxo:<12} {sym:<9} "
                   f"{'PARSE_FAILED':>6}")
            by_taxo.setdefault(taxo, []).append(False)
        else:
            p = parsed.get("promoter_pct")
            fi = parsed.get("fii_pct")
            di = parsed.get("dii_pct")
            pu = parsed.get("public_pct")
            gv = parsed.get("govt_pct")
            tot = sum(v for v in (p, fi, di, pu, gv) if v is not None)
            det = parsed.get("details") or {}
            n_named = len(det.get("namedHolders") or [])
            n_flags = len(det.get("flags") or {})
            pldg = parsed.get("promoter_pledge_pct")
            dmt = parsed.get("demat_pct")
            lck = parsed.get("locked_in_pct")

            def _c(v, w, dp=2):
                return (f"{v:>{w}.{dp}f}" if isinstance(v, (int, float))
                        else f"{'-':>{w}}")
            status = "OK" if (fi is not None and di is not None) else "FII/DII_MISSING"
            row = (f"{period:<12} {taxo:<12} {sym:<9} "
                   f"{_c(p,6)} {_c(fi,6)} {_c(di,6)} {_c(pu,6)} {_c(gv,5)} "
                   f"{tot:>7.2f} {_c(pldg,5,1)} {_c(dmt,6,1)} {_c(lck,5,1)} "
                   f"{n_named:>6} {n_flags:>5}  {status}")
            by_taxo.setdefault(taxo, []).append(fi is not None and di is not None)

        print(row)

    # Summary
    print()
    print("Coverage by taxonomy (files with both FII and DII resolved):")
    for taxo in sorted(by_taxo.keys()):
        results = by_taxo[taxo]
        ok = sum(1 for r in results if r)
        total = len(results)
        pct = (ok / total * 100) if total else 0
        print(f"  {taxo:<14} {ok}/{total} ({pct:.0f}%)")

    overall_ok = sum(1 for results in by_taxo.values() for r in results if r)
    overall_total = sum(len(results) for results in by_taxo.values())
    print(f"\nOverall: {overall_ok}/{overall_total} files have FII+DII "
          f"({overall_ok / overall_total * 100:.0f}%)")

    return 0 if overall_ok == overall_total else 2


if __name__ == "__main__":
    sys.exit(main())

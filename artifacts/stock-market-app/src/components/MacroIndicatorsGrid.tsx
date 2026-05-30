/**
 * Removed.
 *
 * The TE-backed macro indicators grid lived here. It was deleted because
 * the scrape pipeline (TradingEconomics + data.gov.in) couldn't reliably
 * populate the database — TE blocked our server IP, and data.gov.in's
 * resource IDs we tried returned nothing useful. The Macro Pulse page
 * now relies on the existing FRED-fed headline tiles + detailed charts.
 *
 * Kept as a no-op export so any stray import compiles. Safe to delete
 * the file from disk.
 */
export default function MacroIndicatorsGrid() {
  return null;
}

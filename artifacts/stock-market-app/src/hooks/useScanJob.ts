/**
 * useScanJob — kicks off background scans and polls them to completion.
 *
 * Why this exists
 * ---------------
 * The previous synchronous run flow blocked the UI for the entire scan
 * duration with just a "Running…" spinner. Hidden Gems scanners can
 * take 15-90 seconds (Yahoo fundamentals prefetch on cold cache),
 * which felt like a hang. Worse, navigating away cancelled the scan.
 *
 * This hook moves to a fire-and-forget model:
 *   1. `startScan(scannerId)` POSTs to /scanners/{id}/run-job which
 *      returns a jobId immediately. The actual scan runs as an asyncio
 *      task on the backend, surviving the HTTP response.
 *   2. We persist the jobId in localStorage so the user can navigate
 *      away (or refresh the tab) and resume polling on return.
 *   3. React-Query polls /scanners/jobs/{jobId} every 1s while status
 *      is "running"; refetchInterval flips to false once it terminates.
 *   4. When status flips to "completed", the result is passed to
 *      `onComplete()` — caller does whatever (show results panel).
 *
 * Single-job assumption: this hook tracks ONE active job per page.
 * Starting a new scan implicitly abandons the previous job's polling
 * (the backend task still finishes — just not displayed). That matches
 * the existing UX where only one scan can be "active" at a time.
 */
import { useCallback, useEffect, useState } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { api, type ScanResult } from "@/lib/api";


const STORAGE_KEY = "active_scan_job_v1";


// ── localStorage helpers ────────────────────────────────────────────────────
// We persist a minimal { jobId, scannerId } pair so the next mount can
// resume polling. Any failure to read/write is silent — localStorage
// can be disabled, full, or vetoed by privacy mode; in all cases the
// hook degrades gracefully to "no resume".

interface PersistedJob { jobId: string; scannerId: string; }

function readPersisted(): PersistedJob | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (parsed && typeof parsed.jobId === "string" && typeof parsed.scannerId === "string") {
      return parsed;
    }
  } catch { /* ignore */ }
  return null;
}

function writePersisted(j: PersistedJob | null): void {
  try {
    if (j) localStorage.setItem(STORAGE_KEY, JSON.stringify(j));
    else   localStorage.removeItem(STORAGE_KEY);
  } catch { /* ignore */ }
}


// ── Hook ────────────────────────────────────────────────────────────────────

export interface ScanJobProgress {
  total:   number;
  scanned: number;
  matched: number;
  failed:  number;
  errors:  number;
  stage:   string;
}

interface UseScanJobOpts {
  /** Called once when a job terminates successfully. Pass results to
   *  whatever component renders the matches table. */
  onComplete?: (result: ScanResult) => void;
  /** Called once when a job hits status === "failed". */
  onFailed?:   (error: string) => void;
}

export function useScanJob(opts: UseScanJobOpts = {}) {
  const { onComplete, onFailed } = opts;

  // Active job tuple — set on startScan() or restored from localStorage.
  // `null` means "no job in progress".
  const [active, setActive] = useState<PersistedJob | null>(() => readPersisted());

  // Poll the backend for job state. `refetchInterval` returns 1000 while
  // the job is running and false once it terminates, so we stop hitting
  // the server the moment results are available. `staleTime: 0` keeps
  // every poll fresh.
  const jobQuery = useQuery({
    queryKey: ["scan-job", active?.jobId],
    queryFn:  () => active ? api.getScanJob(active.jobId) : Promise.reject("no active job"),
    enabled:  !!active,
    refetchInterval: (q) => {
      const status = (q.state.data as any)?.status;
      return (status === "running" || status === "queued") ? 1000 : false;
    },
    staleTime: 0,
    // 404 (job expired) shouldn't retry — backend explicitly drops jobs
    // after 1h. We treat it as "session over, clear state".
    retry: (count, err: any) => err?.status !== 404 && count < 2,
  });

  // Terminal-state side effects — fire `onComplete` / `onFailed`
  // exactly once per job, then clear the active state (which stops
  // polling). The dependency-array shape uses jobId so a new job
  // re-arms the effect cleanly.
  useEffect(() => {
    const job = jobQuery.data;
    if (!job || !active) return;
    if (job.status === "completed" && job.result) {
      onComplete?.(job.result as ScanResult);
      setActive(null);
      writePersisted(null);
    } else if (job.status === "failed") {
      onFailed?.(job.error || "Scan failed");
      setActive(null);
      writePersisted(null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobQuery.data?.status, jobQuery.data?.jobId]);

  // Also clear active when the job query 404s (server forgot the job).
  useEffect(() => {
    if (jobQuery.isError && (jobQuery.error as any)?.status === 404) {
      setActive(null);
      writePersisted(null);
    }
  }, [jobQuery.isError, jobQuery.error]);

  // Start mutation — fires the run-job POST and stores the returned id.
  const startMut = useMutation({
    mutationFn: (scannerId: string) => api.runScannerAsync(scannerId),
    onSuccess:  (data) => {
      const next: PersistedJob = { jobId: data.jobId, scannerId: data.scannerId };
      setActive(next);
      writePersisted(next);
    },
  });

  const startScan = useCallback((scannerId: string) => {
    startMut.mutate(scannerId);
  }, [startMut]);

  /** Manually abandon the current job (UI side only — backend task
   *  still completes). Useful for a "Cancel" button if you add one. */
  const dismissActive = useCallback(() => {
    setActive(null);
    writePersisted(null);
  }, []);

  return {
    /** ID of the scanner currently running, or null. UI uses this to
     *  show "Running…" on the right card. */
    activeScannerId: active?.scannerId ?? null,
    /** Live progress dict, or null if no job is active. */
    progress:        (jobQuery.data?.progress as ScanJobProgress | undefined) ?? null,
    /** Live stream of matches in arrival order. Populated while a scan
     *  is running so the right panel can render results progressively
     *  instead of waiting for the whole scan to finish. Empty array
     *  (not null) when no scan is active or no matches yet. */
    partialMatches:  (jobQuery.data?.partialMatches as any[] | undefined) ?? [],
    /** Current backend status: queued | running | completed | failed.
     *  null until first poll lands. */
    status:          jobQuery.data?.status ?? null,
    /** True while the start-job HTTP call is in flight (sub-second). */
    starting:        startMut.isPending,
    /** Last error from either the start call or the poll, if any. */
    error:           (startMut.error as Error | undefined)?.message
                     ?? (jobQuery.error as Error | undefined)?.message
                     ?? null,
    startScan,
    dismissActive,
  };
}

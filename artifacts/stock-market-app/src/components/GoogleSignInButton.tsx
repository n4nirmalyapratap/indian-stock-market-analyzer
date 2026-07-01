import { useEffect, useRef, useState } from "react";

declare global {
  interface Window {
    google?: any;
    __ENV__?: Record<string, string>;
  }
}

type GoogleSignInButtonProps = {
  onCredential: (credential: string) => Promise<void>;
  text?: string;
};

const GOOGLE_SCRIPT_SRC = "https://accounts.google.com/gsi/client";

function waitForGoogleScript(timeoutMs = 8000): Promise<void> {
  if (window.google?.accounts?.id) return Promise.resolve();
  return new Promise((resolve, reject) => {
    const deadline = setTimeout(
      () => reject(new Error("Google sign-in took too long to load — check your connection and refresh.")),
      timeoutMs,
    );
    function check() {
      if (window.google?.accounts?.id) {
        clearTimeout(deadline);
        resolve();
        return;
      }
      setTimeout(check, 50);
    }
    check();

    const existing = document.querySelector(`script[src="${GOOGLE_SCRIPT_SRC}"]`);
    if (!existing) {
      const script = document.createElement("script");
      script.src = GOOGLE_SCRIPT_SRC;
      script.async = true;
      document.head.appendChild(script);
    }
  });
}

export function GoogleSignInButton({ onCredential, text = "continue_with" }: GoogleSignInButtonProps) {
  const clientId = (window.__ENV__?.VITE_GOOGLE_CLIENT_ID || import.meta.env.VITE_GOOGLE_CLIENT_ID || "").trim();
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [error, setError]   = useState("");
  const [busy, setBusy]     = useState(false);
  const [ready, setReady]   = useState(false);

  useEffect(() => {
    let cancelled = false;

    async function setup() {
      if (!clientId) {
        setError("Google sign-in is not configured. Missing VITE_GOOGLE_CLIENT_ID.");
        return;
      }
      try {
        await waitForGoogleScript();
        if (cancelled || !containerRef.current || !window.google?.accounts?.id) return;
        containerRef.current.innerHTML = "";
        window.google.accounts.id.initialize({
          client_id: clientId,
          callback: async (response: { credential?: string }) => {
            if (!response.credential) {
              setError("Google did not return a valid credential.");
              return;
            }
            setBusy(true);
            setError("");
            try {
              await onCredential(response.credential);
            } catch (err: any) {
              setError(err?.message || "Google sign-in failed.");
              setBusy(false);
            }
          },
        });
        window.google.accounts.id.renderButton(containerRef.current, {
          type: "standard",
          theme: "outline",
          size: "large",
          text,
          shape: "pill",
          width: 320,
        });
        if (!cancelled) setReady(true);
      } catch (err: any) {
        if (!cancelled) setError(err?.message || "Failed to initialize Google sign-in.");
      }
    }

    setup();
    return () => { cancelled = true; };
  }, [clientId, onCredential, text]);

  return (
    <div className="space-y-3 relative">
      {!ready && !error && (
        <div className="flex justify-center items-center h-10">
          <svg className="animate-spin w-5 h-5 text-gray-400" fill="none" viewBox="0 0 24 24">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4l3-3-3-3V0a12 12 0 100 24v-4l-3 3 3 3v4A12 12 0 014 12z" />
          </svg>
        </div>
      )}

      <div ref={containerRef} className={`flex justify-center ${ready ? "" : "hidden"}`} />

      {busy && (
        <div className="flex flex-col items-center gap-3 py-2">
          <svg className="animate-spin w-7 h-7 text-indigo-400" fill="none" viewBox="0 0 24 24">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
          </svg>
          <div className="text-center">
            <p className="text-sm font-semibold text-white">Signing you in…</p>
            <p className="text-xs text-gray-400 mt-0.5">Verifying your Google account</p>
          </div>
        </div>
      )}

      {error && (
        <div className="bg-red-500/10 border border-red-500/30 rounded-lg px-3 py-2 text-red-400 text-xs">
          {error}
        </div>
      )}
    </div>
  );
}

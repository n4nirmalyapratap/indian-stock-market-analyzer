import { useEffect, useRef, useState } from "react";

declare global {
  interface Window {
    google?: any;
    __ENV__?: Record<string, string>;
  }
}

type GoogleSignInButtonProps = {
  onCredential: (credential: string) => Promise<void>;
};

const GOOGLE_SCRIPT_ID = "google-identity-services";

function loadGoogleScript(): Promise<void> {
  if (window.google?.accounts?.id) return Promise.resolve();
  const existing = document.getElementById(GOOGLE_SCRIPT_ID) as HTMLScriptElement | null;
  if (existing) {
    return new Promise((resolve, reject) => {
      existing.addEventListener("load", () => resolve(), { once: true });
      existing.addEventListener("error", () => reject(new Error("Failed to load Google sign-in.")), { once: true });
    });
  }
  return new Promise((resolve, reject) => {
    const script = document.createElement("script");
    script.id = GOOGLE_SCRIPT_ID;
    script.src = "https://accounts.google.com/gsi/client";
    script.async = true;
    script.defer = true;
    script.onload = () => resolve();
    script.onerror = () => reject(new Error("Failed to load Google sign-in."));
    document.head.appendChild(script);
  });
}

export function GoogleSignInButton({ onCredential }: GoogleSignInButtonProps) {
  const clientId = (window.__ENV__?.VITE_GOOGLE_CLIENT_ID || import.meta.env.VITE_GOOGLE_CLIENT_ID || "").trim();
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;

    async function setup() {
      if (!clientId) {
        setError("Google sign-in is not configured. Missing VITE_GOOGLE_CLIENT_ID.");
        return;
      }
      try {
        await loadGoogleScript();
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
            } finally {
              setBusy(false);
            }
          },
        });
        window.google.accounts.id.renderButton(containerRef.current, {
          type: "standard",
          theme: "filled_blue",
          size: "large",
          shape: "pill",
          width: 320,
        });
      } catch (err: any) {
        if (!cancelled) {
          setError(err?.message || "Failed to initialize Google sign-in.");
        }
      }
    }

    setup();
    return () => {
      cancelled = true;
    };
  }, [clientId, onCredential]);

  return (
    <div className="space-y-3">
      <div ref={containerRef} className="flex justify-center" />
      {busy && (
        <div className="text-center text-xs text-gray-400">Signing you in with Google…</div>
      )}
      {error && (
        <div className="bg-red-900/40 border border-red-800 rounded-xl px-3 py-2.5 text-red-300 text-sm">
          {error}
        </div>
      )}
    </div>
  );
}

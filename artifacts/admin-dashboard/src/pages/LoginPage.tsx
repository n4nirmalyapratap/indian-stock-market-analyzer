import { useState } from "react";
import { AlertCircle } from "lucide-react";
import { api, setAdminToken } from "@/lib/api";
import { GoogleSignInButton } from "@/components/GoogleSignInButton";

export default function LoginPage({ onLogin }: { onLogin: (token: string) => void }) {
  const [error, setError] = useState("");

  return (
    <div className="min-h-screen bg-gray-950 flex flex-col items-center justify-center py-12 px-4">
      <div className="w-full max-w-sm">
        <div className="flex flex-col items-center mb-8">
          <img
            src="/niftynodes-logo-transparent.png"
            alt="Nifty Node"
            className="w-14 h-14 rounded-2xl object-contain mb-4 shadow-lg shadow-indigo-500/30"
          />
          <h1 className="text-white font-bold text-xl tracking-tight">Admin Panel</h1>
          <p className="text-gray-400 text-sm mt-1">Nifty Node — Restricted Access</p>
        </div>

        <div className="bg-gray-900 rounded-2xl border border-gray-800 p-8 shadow-2xl">
          <div className="space-y-5">
            <div className="text-center">
              <p className="text-sm text-gray-300 font-medium">Sign in with an allowlisted Google account</p>
              <p className="text-xs text-gray-500 mt-1">Password login has been removed from the admin panel.</p>
            </div>

            <GoogleSignInButton
              onCredential={async (credential) => {
                setError("");
                try {
                  const data = await api.googleLogin(credential);
                  setAdminToken(data.token);
                  onLogin(data.token);
                } catch (err: any) {
                  setError(err.message || "Google sign-in failed.");
                  throw err;
                }
              }}
            />

            {error && (
              <div className="flex items-center gap-2 bg-red-900/40 border border-red-800 rounded-xl px-3 py-2.5">
                <AlertCircle className="w-4 h-4 text-red-400 flex-shrink-0" />
                <p className="text-red-300 text-sm">{error}</p>
              </div>
            )}
          </div>
        </div>

        <p className="text-center text-xs text-gray-600 mt-6">
          Admin access only. Google allowlist required.
        </p>
      </div>
    </div>
  );
}

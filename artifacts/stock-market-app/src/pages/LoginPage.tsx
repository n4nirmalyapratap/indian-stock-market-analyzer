import { useState } from "react";
import { useCustomAuth } from "@/context/CustomAuthContext";
import { BrandLogo } from "@/components/BrandLogo";
import { GoogleSignInButton } from "@/components/GoogleSignInButton";

export default function LoginPage() {
  const { loginWithGoogle } = useCustomAuth();
  const [error, setError] = useState("");

  return (
    <div className="min-h-screen bg-gray-950 flex flex-col items-center justify-center py-12 px-4">

      {/* Brand */}
      <div className="mb-8 flex flex-col items-center">
        <BrandLogo className="w-14 h-14 rounded-full object-cover mb-3 ring-2 ring-indigo-500/30" />
        <p className="text-white font-bold text-xl tracking-tight">Nifty Node</p>
        <p className="text-gray-400 text-sm mt-1">Indian Stock Market Analysis</p>
      </div>

      {/* Card */}
      <div className="w-full max-w-sm bg-gray-900 border border-gray-800 rounded-2xl p-6 shadow-2xl">
        <div className="space-y-4">
          <div className="text-center">
            <p className="text-sm text-gray-300 font-medium">Sign in with Google</p>
            <p className="text-xs text-gray-500 mt-1">
              Google is the only supported sign-in method for this app.
            </p>
          </div>

          <GoogleSignInButton
            onCredential={async (credential) => {
              setError("");
              try {
                await loginWithGoogle(credential);
              } catch (err: any) {
                setError(err.message || "Something went wrong. Please try again.");
                throw err;
              }
            }}
          />

          {error && (
            <div className="bg-red-500/10 border border-red-500/30 rounded-lg px-3 py-2 text-red-400 text-xs">
              {error}
            </div>
          )}
        </div>
      </div>

      <p className="mt-6 text-gray-600 text-xs">
        Nifty Node · Indian Stock Market Analysis
      </p>
    </div>
  );
}

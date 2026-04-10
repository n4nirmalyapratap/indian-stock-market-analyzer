import { useState, FormEvent } from "react";
import { useCustomAuth } from "@/context/CustomAuthContext";

export default function LoginPage() {
  const { login, register } = useCustomAuth();

  const [mode,     setMode]     = useState<"login" | "register">("login");
  const [email,    setEmail]    = useState("");
  const [password, setPassword] = useState("");
  const [name,     setName]     = useState("");
  const [error,    setError]    = useState("");
  const [loading,  setLoading]  = useState(false);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      if (mode === "login") {
        await login(email, password);
      } else {
        await register(email, password, name);
      }
    } catch (err: any) {
      setError(err.message || "Something went wrong. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gray-950 flex flex-col items-center justify-center py-12 px-4">

      {/* Brand */}
      <div className="mb-8 flex flex-col items-center">
        <img
          src="/niftynodes-logo.png"
          alt="NiftyNodes"
          className="w-14 h-14 rounded-full object-cover mb-3 ring-2 ring-indigo-500/30"
        />
        <p className="text-white font-bold text-xl tracking-tight">Nifty Node</p>
        <p className="text-gray-400 text-sm mt-1">Indian Stock Market Analysis</p>
      </div>

      {/* Card */}
      <div className="w-full max-w-sm bg-gray-900 border border-gray-800 rounded-2xl p-6 shadow-2xl">

        {/* Tabs */}
        <div className="flex rounded-lg bg-gray-800 p-1 mb-6">
          {(["login", "register"] as const).map((m) => (
            <button
              key={m}
              onClick={() => { setMode(m); setError(""); }}
              className={`flex-1 py-1.5 rounded-md text-sm font-medium transition-all ${
                mode === m
                  ? "bg-indigo-600 text-white shadow"
                  : "text-gray-400 hover:text-white"
              }`}
            >
              {m === "login" ? "Sign In" : "Register"}
            </button>
          ))}
        </div>

        {/* Email + password form */}
        <form onSubmit={handleSubmit} className="space-y-3">
          {mode === "register" && (
            <div>
              <label className="block text-xs font-medium text-gray-400 mb-1">Name</label>
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Your name"
                className="w-full px-3 py-2.5 rounded-lg bg-gray-800 border border-gray-700 text-white text-sm placeholder-gray-500 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500/40 transition"
              />
            </div>
          )}

          <div>
            <label htmlFor="auth-email" className="block text-xs font-medium text-gray-400 mb-1">Email</label>
            <input
              id="auth-email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@example.com"
              required
              autoComplete="email"
              className="w-full px-3 py-2.5 rounded-lg bg-gray-800 border border-gray-700 text-white text-sm placeholder-gray-500 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500/40 transition"
            />
          </div>

          <div>
            <label htmlFor="auth-password" className="block text-xs font-medium text-gray-400 mb-1">Password</label>
            <input
              id="auth-password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder={mode === "register" ? "Min 6 characters" : "Your password"}
              required
              autoComplete={mode === "register" ? "new-password" : "current-password"}
              className="w-full px-3 py-2.5 rounded-lg bg-gray-800 border border-gray-700 text-white text-sm placeholder-gray-500 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500/40 transition"
            />
          </div>

          {error && (
            <div className="bg-red-500/10 border border-red-500/30 rounded-lg px-3 py-2 text-red-400 text-xs">
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full py-2.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-semibold transition disabled:opacity-60 disabled:cursor-not-allowed flex items-center justify-center gap-2"
          >
            {loading && (
              <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
            )}
            {mode === "login" ? "Sign In" : "Create Account"}
          </button>
        </form>

        <p className="text-center text-xs text-gray-500 mt-4">
          {mode === "login" ? "Don't have an account?" : "Already have an account?"}
          {" "}
          <button
            onClick={() => { setMode(mode === "login" ? "register" : "login"); setError(""); }}
            className="text-indigo-400 hover:text-indigo-300 font-medium transition"
          >
            {mode === "login" ? "Register" : "Sign in"}
          </button>
        </p>
      </div>

      <p className="mt-6 text-gray-600 text-xs">
        Nifty Node · Indian Stock Market Analysis
      </p>
    </div>
  );
}

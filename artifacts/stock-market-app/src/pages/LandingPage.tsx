import { useLocation } from "wouter";
import {
  BarChart3, Brain, TrendingUp, Shield, Zap, Globe,
  ArrowRight, Lock,
} from "lucide-react";

const FEATURES = [
  {
    icon: BarChart3,
    title: "Sector Rotation",
    desc: "Track money flow across all NSE sectors with live advance/decline data and phase detection.",
  },
  {
    icon: Brain,
    title: "AI Pattern Recognition",
    desc: "Auto-detect 15+ chart patterns — Golden Cross, Bullish Engulfing, RSI Divergence and more.",
  },
  {
    icon: TrendingUp,
    title: "Market Scanners",
    desc: "Build custom stock scanners with multi-condition filters across the entire NSE universe.",
  },
  {
    icon: Zap,
    title: "Real-time Analysis",
    desc: "Live stock quotes, options strategy tester, and NLP-powered market assistant.",
  },
  {
    icon: Globe,
    title: "Bot Integration",
    desc: "Receive buy/sell signals and market alerts on WhatsApp and Telegram.",
  },
  {
    icon: Shield,
    title: "Secure & Private",
    desc: "Your data stays yours. All analysis runs server-side with no third-party data sharing.",
  },
];

export default function LandingPage() {
  const [, setLocation] = useLocation();

  const handleSignIn = () => {
    setLocation("/sign-in");
  };

  return (
    <div className="min-h-screen bg-gray-950 text-white flex flex-col">

      {/* Header */}
      <header className="border-b border-white/[0.06] px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <img
            src="/niftynodes-logo.png"
            alt="NiftyNodes"
            className="w-9 h-9 rounded-full object-cover"
          />
          <div>
            <p className="font-bold text-white text-sm leading-tight">Nifty Node</p>
            <p className="text-xs text-gray-500 leading-tight">Indian Stock Market</p>
          </div>
        </div>
        <button
          onClick={handleSignIn}
          className="flex items-center gap-2 bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-medium px-4 py-2 rounded-lg transition"
        >
          Sign in <ArrowRight className="w-4 h-4" />
        </button>
      </header>

      {/* Hero */}
      <section className="flex-1 flex flex-col items-center justify-center text-center px-6 py-20">
        <div className="inline-flex items-center gap-2 bg-indigo-500/10 border border-indigo-500/20 text-indigo-400 text-xs font-medium px-3 py-1.5 rounded-full mb-6">
          <Lock className="w-3 h-3" />
          Secure — sign in to access
        </div>

        <h1 className="text-4xl md:text-5xl font-extrabold text-white leading-tight max-w-2xl mb-4">
          Indian Stock Market<br />
          <span className="text-indigo-400">Analysis Platform</span>
        </h1>

        <p className="text-gray-400 text-lg max-w-xl mb-10">
          Professional-grade tools for NSE sector rotation, pattern detection,
          custom scanners, and AI-powered market insights — all in one platform.
        </p>

        <button
          onClick={handleSignIn}
          className="flex items-center gap-3 bg-indigo-600 hover:bg-indigo-500 text-white font-semibold px-8 py-3.5 rounded-xl text-base transition shadow-lg shadow-indigo-500/20"
        >
          <svg className="w-5 h-5" viewBox="0 0 24 24">
            <path fill="currentColor" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" />
            <path fill="currentColor" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" />
            <path fill="currentColor" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" />
            <path fill="currentColor" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" />
          </svg>
          Continue with Google
        </button>

        <p className="text-gray-600 text-xs mt-4">
          Or use email · No credit card required
        </p>
      </section>

      {/* Features */}
      <section className="border-t border-white/[0.06] px-6 py-16">
        <p className="text-center text-gray-500 text-sm font-medium uppercase tracking-widest mb-10">
          What's inside
        </p>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 max-w-5xl mx-auto">
          {FEATURES.map(({ icon: Icon, title, desc }) => (
            <div
              key={title}
              className="bg-gray-900 border border-white/[0.06] rounded-xl p-5 flex gap-4"
            >
              <div className="w-9 h-9 bg-indigo-500/10 rounded-lg flex items-center justify-center flex-shrink-0">
                <Icon className="w-4.5 h-4.5 text-indigo-400" />
              </div>
              <div>
                <p className="font-semibold text-white text-sm mb-1">{title}</p>
                <p className="text-gray-500 text-xs leading-relaxed">{desc}</p>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-white/[0.06] px-6 py-5 text-center">
        <p className="text-gray-600 text-xs">
          © 2025 Nifty Node · Indian Stock Market Analysis · For educational purposes only
        </p>
      </footer>
    </div>
  );
}

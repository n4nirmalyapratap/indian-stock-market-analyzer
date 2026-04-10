import { createRoot } from "react-dom/client";
import { Component, type ErrorInfo, type ReactNode } from "react";
import App from "./App";
import "./index.css";

class RootErrorBoundary extends Component<
  { children: ReactNode },
  { error: Error | null }
> {
  state = { error: null };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("[App crash]", error, info.componentStack);
  }

  render() {
    const { error } = this.state;
    if (error) {
      return (
        <div style={{
          minHeight: "100vh", background: "#030712", color: "#f8fafc",
          display: "flex", flexDirection: "column", alignItems: "center",
          justifyContent: "center", fontFamily: "system-ui, sans-serif", padding: "2rem",
        }}>
          <div style={{
            maxWidth: 480, background: "#0f172a", border: "1px solid #1e293b",
            borderRadius: 12, padding: "2rem",
          }}>
            <h2 style={{ margin: "0 0 .75rem", color: "#f87171", fontSize: "1.1rem" }}>
              Something went wrong
            </h2>
            <pre style={{
              background: "#020617", borderRadius: 8, padding: "1rem",
              fontSize: ".75rem", color: "#94a3b8", overflowX: "auto",
              whiteSpace: "pre-wrap", wordBreak: "break-word",
            }}>
              {error.message}
            </pre>
            <button
              onClick={() => window.location.reload()}
              style={{
                marginTop: "1rem", padding: ".5rem 1.25rem", background: "#4f46e5",
                color: "#fff", border: "none", borderRadius: 8, cursor: "pointer",
                fontSize: ".875rem", fontWeight: 600,
              }}
            >
              Reload page
            </button>
          </div>
        </div>
      );
    }
    return this.state.error ? null : this.props.children;
  }
}

createRoot(document.getElementById("root")!).render(
  <RootErrorBoundary>
    <App />
  </RootErrorBoundary>
);

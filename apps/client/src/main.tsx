import React from "react";
import ReactDOM from "react-dom/client";
import { invoke } from "@tauri-apps/api/core";
import App from "./App";
import "./styles/app.css";

function isTauriRuntime(): boolean {
  return typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
}

function reportDiag(kind: string, detail: string) {
  if (isTauriRuntime()) {
    void invoke("report_client_diag", { kind, detail }).catch(() => {
      console.warn(`WAIKE_CLIENT_DIAG kind=${kind} detail=${detail}`);
    });
    return;
  }
  console.warn(`WAIKE_CLIENT_DIAG kind=${kind} detail=${detail}`);
}

function registerServiceWorker() {
  if (isTauriRuntime()) return;
  if (typeof navigator === "undefined" || !("serviceWorker" in navigator)) return;
  // Only register in secure contexts / localhost (Chrome Android USB reverse qualifies as localhost).
  const host = window.location.hostname;
  const ok =
    window.isSecureContext || host === "127.0.0.1" || host === "localhost";
  if (!ok) {
    reportDiag("sw_skip", "insecure_origin");
    return;
  }
  window.addEventListener("load", () => {
    void navigator.serviceWorker
      .register("/sw.js")
      .then((reg) => reportDiag("sw_registered", reg.scope))
      .catch((err) => reportDiag("sw_register_failed", String(err)));
  });
}

if (typeof document !== "undefined") {
  document.addEventListener("securitypolicyviolation", (ev) => {
    const detail = [
      ev.violatedDirective || "",
      ev.effectiveDirective || "",
      ev.blockedURI || "",
      ev.documentURI || "",
    ].join("|");
    reportDiag("csp_violation", detail);
  });
}

registerServiceWorker();

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);

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

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";
import "./login/index.css";
import { App } from "./App";
import { ErrorBoundary } from "./components/ui/ErrorBoundary";
import { ToastProvider } from "./components/ui/Toast";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ErrorBoundary>
      <ToastProvider>
        <App />
      </ToastProvider>
    </ErrorBoundary>
  </StrictMode>,
);

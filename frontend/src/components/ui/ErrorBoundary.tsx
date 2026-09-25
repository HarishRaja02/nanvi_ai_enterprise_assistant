import { Component, ErrorInfo, ReactNode } from "react";
import { TriangleAlert } from "lucide-react";
import { Button } from "./Button";
import { EmptyState } from "./EmptyState";

/** Last line of defence so an unexpected render error never produces a blank white screen. */
export class ErrorBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };

  static getDerivedStateFromError() { return { failed: true }; }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // Details go to the console only; never render stack traces or internals to users.
    console.error("Unhandled UI error", error, info.componentStack);
  }

  render() {
    if (!this.state.failed) return this.props.children;
    return (
      <main className="fullscreen">
        <EmptyState
          icon={TriangleAlert}
          title="Something went wrong"
          action={<Button variant="primary" onClick={() => window.location.reload()}>Reload Nanvi</Button>}
        >
          The page hit an unexpected error. Reloading usually fixes it, and your session is kept. If it keeps happening, tell your administrator.
        </EmptyState>
      </main>
    );
  }
}

import { useEffect, useState } from "react";
import { ApiError, ChatSource, NanviApiClient } from "../../api";
import { Alert } from "../ui/Alert";
import { Badge } from "../ui/Badge";
import { Button } from "../ui/Button";
import { Modal } from "../ui/Modal";
import { Skeleton } from "../ui/Skeleton";
import { SourceTile } from "./SourceTile";
import { formatDateTime } from "../../lib/format";
import { KIND_LABEL, SourceView, detectFormat, toSourceView } from "../../lib/sources";

type State =
  | { status: "loading" }
  | { status: "ok"; data: ChatSource }
  | { status: "denied"; message: string }
  | { status: "stale" };

/**
 * Opens a citation. The server is asked to re-authorize the source every time (api.source);
 * a 403/404 is shown as such rather than papered over with cached metadata.
 */
export function SourceDialog({ source, api, onClose }: { source: SourceView; api: NanviApiClient; onClose: () => void }) {
  const [state, setState] = useState<State>({ status: "loading" });

  useEffect(() => {
    let alive = true;
    setState({ status: "loading" });
    api.source(source.id).then(
      (resolved) => { if (alive) setState({ status: "ok", data: resolved }); },
      (error: unknown) => {
        if (!alive) return;
        if (error instanceof ApiError && error.status === 403) {
          setState({ status: "denied", message: "You no longer have access to this source." });
        } else {
          setState({ status: "stale" });
        }
      },
    );
    return () => { alive = false; };
  }, [api, source.id]);

  const shown: SourceView = state.status === "ok" ? toSourceView(state.data) : source;
  const href = state.status === "ok" && state.data.href && /^https:\/\//i.test(state.data.href) ? state.data.href : null;
  const timestamp = state.status === "ok" ? formatDateTime(state.data.timestamp ?? undefined) : "";
  const format = state.status === "ok" ? detectFormat(state.data, shown.kind) : source.format;

  return (
    <Modal
      title={shown.title}
      onClose={onClose}
      footer={
        <>
          {href && <Button variant="primary" onClick={() => window.open(href, "_blank", "noopener,noreferrer")}>Open source</Button>}
          <Button onClick={onClose}>Close</Button>
        </>
      }
    >
      {state.status === "loading" && (
        <div role="status" aria-label="Confirming access to this source" className="dialog-loading">
          <Skeleton width="40%" /><Skeleton width="85%" /><Skeleton width="60%" />
        </div>
      )}
      {state.status === "denied" && <Alert tone="danger" title="Source unavailable">{state.message}</Alert>}
      {state.status === "stale" && (
        <Alert tone="warning" title="Couldn't confirm access just now">
          Showing the citation details saved with this answer. Try again in a moment to open the source.
        </Alert>
      )}

      {state.status !== "denied" && state.status !== "loading" && (
        <dl className="source-details">
          <div><dt>Type</dt><dd><span className="detail-format"><SourceTile format={format} /> {KIND_LABEL[shown.kind]}</span></dd></div>
          <div><dt>Location</dt><dd>{shown.location ? <code>{shown.location}</code> : "Internal source"}</dd></div>
          {shown.page ? <div><dt>Page</dt><dd><Badge>{shown.page}</Badge></dd></div> : null}
          {shown.sheet ? <div><dt>Sheet</dt><dd>{shown.sheet}</dd></div> : null}
          {timestamp ? <div><dt>Timestamp</dt><dd>{timestamp}</dd></div> : null}
        </dl>
      )}

      <p className="modal-note">Only citation details are shown here. The server re-checks your access each time a source is opened.</p>
    </Modal>
  );
}


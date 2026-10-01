import type { SourceFormat } from "../../lib/sources";

/** Typographic format marker (PDF, XLSX, SQL, MAIL…). One quiet accent hue = "from your sources". */
export function SourceTile({ format }: { format: SourceFormat }) {
  return <span className="tile" aria-hidden="true">{format}</span>;
}

import type { ChatSource } from "../api";

export type SourceKind = "email" | "database" | "document" | "file" | "drive";
export type SourceFormat = "PDF" | "XLSX" | "DOCX" | "PPTX" | "CSV" | "MAIL" | "SQL" | "FILE" | "DRIVE";

export type SourceView = {
  id: string;
  kind: SourceKind;
  format: SourceFormat;
  title: string;
  location?: string;
  page?: number;
  sheet?: string;
  href?: string | null;
};

const EXTENSIONS: Array<[RegExp, SourceFormat]> = [
  [/\.pdf\b/, "PDF"],
  [/\.(xlsx|xlsm|xls)\b/, "XLSX"],
  [/\.(docx|doc)\b/, "DOCX"],
  [/\.(pptx|ppt)\b/, "PPTX"],
  [/\.(csv|tsv)\b/, "CSV"],
];

const MIME: Array<[RegExp, SourceFormat]> = [
  [/pdf/, "PDF"],
  [/spreadsheetml|ms-excel/, "XLSX"],
  [/wordprocessingml|msword/, "DOCX"],
  [/presentationml|ms-powerpoint/, "PPTX"],
  [/csv/, "CSV"],
];

function kindOf(sourceType: string): SourceKind {
  const t = sourceType.toLowerCase();
  if (t === "email") return "email";
  if (t === "database") return "database";
  if (t === "drive" || t === "google_drive" || t === "gdrive") return "drive";
  if (t === "document") return "document";
  return "file";
}

/** Derive a display format from what the backend gave us; never invent one it didn't imply. */
export function detectFormat(source: ChatSource, kind: SourceKind): SourceFormat {
  const title = source.title ?? source.display_name;
  if (kind === "email" || /gmail/i.test(title)) return "MAIL";
  if (kind === "database") return "SQL";
  if (kind === "drive") return "DRIVE";
  for (const candidate of [title, source.display_name, source.location ?? ""]) {
    const text = candidate.toLowerCase();
    for (const [pattern, format] of EXTENSIONS) if (pattern.test(text)) return format;
  }
  const mime = source.mime_type?.toLowerCase();
  if (mime) for (const [pattern, format] of MIME) if (pattern.test(mime)) return format;
  if (source.sheet) return "XLSX";
  if (source.page) return "PDF";
  return "FILE";
}

export function toSourceView(source: ChatSource): SourceView {
  const kind = kindOf(source.source_type);
  return {
    id: source.reference_id,
    kind,
    format: detectFormat(source, kind),
    title: source.title ?? source.display_name,
    location: source.location ?? undefined,
    page: source.page ?? undefined,
    sheet: source.sheet ?? undefined,
    href: source.href,
  };
}

export const KIND_LABEL: Record<SourceKind, string> = {
  email: "Email",
  database: "Database",
  document: "Document",
  file: "File",
  drive: "Google Drive",
};

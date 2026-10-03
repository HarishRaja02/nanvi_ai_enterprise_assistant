/**
 * Speech Normalization Layer — Enterprise Voice
 *
 * Converts visual/display text into natural, context-aware spoken text.
 * Handles:
 *   - Employee/Invoice/Project/Ticket IDs (EMP1004 → "EMP one zero zero four")
 *   - Indian currency (₹4,50,000 → "four lakh fifty thousand rupees")
 *   - International currency ($4.2M → "four point two million dollars")
 *   - Percentages (95% → "ninety-five percent")
 *   - Dates (2026-09-30 → "September thirtieth, twenty twenty-six")
 *   - Times (10:30 AM → "ten thirty A M")
 *   - Phone numbers, email addresses
 *   - Acronyms & abbreviations (API, PDF, SQL, HR, etc.)
 *   - Fiscal quarters, business abbreviations
 *   - Large numbers in Indian and international format
 *
 * IMPORTANT: This layer ONLY transforms text for speech output.
 * The displayed UI text remains untouched.
 */

// ─── Number Words ───────────────────────────────────────────────────────────

const ONES = [
  "", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine",
  "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen",
  "seventeen", "eighteen", "nineteen",
];
const TENS = [
  "", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety",
];

function numberToWords(n: number): string {
  if (n < 0) return "minus " + numberToWords(-n);
  if (n === 0) return "zero";
  if (!Number.isInteger(n)) {
    const [intPart, decPart] = n.toString().split(".");
    const intWords = numberToWords(parseInt(intPart, 10));
    const decWords = decPart.split("").map(d => ONES[parseInt(d, 10)] || d).join(" ");
    return `${intWords} point ${decWords}`;
  }
  if (n < 20) return ONES[n];
  if (n < 100) {
    const t = Math.floor(n / 10);
    const o = n % 10;
    return o ? `${TENS[t]} ${ONES[o]}` : TENS[t];
  }
  if (n < 1000) {
    const h = Math.floor(n / 100);
    const rem = n % 100;
    return rem ? `${ONES[h]} hundred ${numberToWords(rem)}` : `${ONES[h]} hundred`;
  }
  if (n < 100000) {
    const th = Math.floor(n / 1000);
    const rem = n % 1000;
    return rem ? `${numberToWords(th)} thousand ${numberToWords(rem)}` : `${numberToWords(th)} thousand`;
  }
  if (n < 10000000) {
    const lk = Math.floor(n / 100000);
    const rem = n % 100000;
    return rem ? `${numberToWords(lk)} lakh ${numberToWords(rem)}` : `${numberToWords(lk)} lakh`;
  }
  if (n < 1000000000) {
    const cr = Math.floor(n / 10000000);
    const rem = n % 10000000;
    return rem ? `${numberToWords(cr)} crore ${numberToWords(rem)}` : `${numberToWords(cr)} crore`;
  }
  // Fallback for very large numbers
  return n.toLocaleString("en-IN");
}

// ─── Digit Spelling ─────────────────────────────────────────────────────────

function spellDigits(digits: string): string {
  return digits.split("").map(d => {
    switch (d) {
      case "0": return "zero";
      case "1": return "one";
      case "2": return "two";
      case "3": return "three";
      case "4": return "four";
      case "5": return "five";
      case "6": return "six";
      case "7": return "seven";
      case "8": return "eight";
      case "9": return "nine";
      default: return d;
    }
  }).join(" ");
}

// ─── Number Formatting for Speech ───────────────────────────────────────────

export function formatNumberForSpeech(val: number, currency: "inr" | "usd" | "none" = "none"): string {
  const currLabel = currency === "inr" ? " rupees" : currency === "usd" ? " dollars" : "";

  // For INR or large Indian-scale values, use Indian numbering
  if (currency === "inr" || val >= 100000) {
    if (val >= 10000000) {
      const cr = val / 10000000;
      if (Number.isInteger(cr) || cr < 100) {
        return `${numberToWords(Math.floor(cr))}${cr % 1 ? ` point ${Math.round((cr % 1) * 10)}` : ""} crore${currLabel}`;
      }
    }
    if (val >= 100000) {
      const lk = val / 100000;
      if (Number.isInteger(lk) || lk < 100) {
        return `${numberToWords(Math.floor(lk))}${lk % 1 ? ` point ${Math.round((lk % 1) * 10)}` : ""} lakh${currLabel}`;
      }
    }
  }

  // For values that can be spoken as full words (up to ~99,99,999)
  if (val >= 1000 && val < 10000000 && Number.isInteger(val)) {
    return `${numberToWords(val)}${currLabel}`;
  }

  // International scale for USD and large international values
  if (val >= 1000000000) {
    const b = (val / 1000000000).toFixed(1).replace(/\.0$/, "");
    return `${b} billion${currLabel}`;
  }
  if (val >= 1000000) {
    const m = (val / 1000000).toFixed(1).replace(/\.0$/, "");
    return `${m} million${currLabel}`;
  }
  if (val >= 1000 && currency === "usd") {
    const k = (val / 1000).toFixed(1).replace(/\.0$/, "");
    return `${k} thousand${currLabel}`;
  }

  // Small numbers: speak as words
  if (Number.isInteger(val) && val < 1000) {
    return `${numberToWords(val)}${currLabel}`;
  }

  const formatted = Number.isInteger(val) ? val.toString() : val.toFixed(2);
  return `${formatted}${currLabel}`;
}

// ─── Date Formatting ────────────────────────────────────────────────────────

const MONTHS = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];

const ORDINALS: Record<number, string> = {
  1: "first", 2: "second", 3: "third", 4: "fourth", 5: "fifth",
  6: "sixth", 7: "seventh", 8: "eighth", 9: "ninth", 10: "tenth",
  11: "eleventh", 12: "twelfth", 13: "thirteenth", 14: "fourteenth", 15: "fifteenth",
  16: "sixteenth", 17: "seventeenth", 18: "eighteenth", 19: "nineteenth", 20: "twentieth",
  21: "twenty first", 22: "twenty second", 23: "twenty third", 24: "twenty fourth",
  25: "twenty fifth", 26: "twenty sixth", 27: "twenty seventh", 28: "twenty eighth",
  29: "twenty ninth", 30: "thirtieth", 31: "thirty first",
};

function yearToWords(year: number): string {
  if (year >= 2000 && year < 2010) return `two thousand ${year === 2000 ? "" : numberToWords(year - 2000)}`.trim();
  if (year >= 2010 && year < 2100) {
    const tens = year - 2000;
    return `twenty ${numberToWords(tens)}`;
  }
  if (year >= 1900 && year < 2000) {
    const tens = year - 1900;
    return `nineteen ${numberToWords(tens)}`;
  }
  return numberToWords(year);
}

function formatDateForSpeech(year: string, month: string, day: string): string {
  const m = parseInt(month, 10);
  const d = parseInt(day, 10);
  const y = parseInt(year, 10);
  if (isNaN(m) || isNaN(d) || isNaN(y)) return `${year}-${month}-${day}`;
  if (m < 1 || m > 12 || d < 1 || d > 31) return `${year}-${month}-${day}`;
  const monthName = MONTHS[m - 1];
  const dayOrdinal = ORDINALS[d] || `${d}th`;
  return `${monthName} ${dayOrdinal}, ${yearToWords(y)}`;
}

// ─── Acronym Handling ───────────────────────────────────────────────────────

// Acronyms that should be spelled letter-by-letter
const SPELLED_ACRONYMS = new Set([
  "API", "PDF", "CSV", "HR", "ID", "IT", "UI", "UX", "ML", "AI", "IP",
  "QA", "CRM", "ERP", "CEO", "CTO", "CFO", "COO", "VP", "EVP", "SVP",
  "PO", "PR", "KPI", "ROI", "SLA", "NDA", "MOU", "SOW", "RFP", "RFQ",
  "GST", "CGST", "SGST", "IGST", "TDS", "PAN", "CTC", "ARR", "MRR",
  "SKU", "EMI", "OTP", "PIN", "URL", "HTTP", "DNS", "SSH", "SSL", "TLS",
  "AWS", "GCP", "VM", "CPU", "GPU", "RAM", "SSD", "HDD", "USB", "HDMI",
]);

// Acronyms that should be pronounced as words
const PRONOUNCED_ACRONYMS: Record<string, string> = {
  "SQL": "sequel",
  "EBITDA": "E-BIT-DA",
  "PostgreSQL": "postgres sequel",
  "MySQL": "my sequel",
  "NASDAQ": "nasdaq",
  "UNESCO": "unesco",
  "UNICEF": "unicef",
  "NASA": "nasa",
  "ASAP": "A-SAP",
  "SCRUM": "scrum",
  "JIRA": "jira",
};

function formatAcronym(acronym: string): string {
  const upper = acronym.toUpperCase();
  if (PRONOUNCED_ACRONYMS[acronym] || PRONOUNCED_ACRONYMS[upper]) {
    return PRONOUNCED_ACRONYMS[acronym] || PRONOUNCED_ACRONYMS[upper];
  }
  if (SPELLED_ACRONYMS.has(upper)) {
    return upper.split("").join(" ");
  }
  // For unknown uppercase sequences of 2-5 chars, spell them
  if (/^[A-Z]{2,5}$/.test(acronym)) {
    return acronym.split("").join(" ");
  }
  return acronym;
}

// ─── Enterprise ID Handling ─────────────────────────────────────────────────

/**
 * Converts enterprise IDs like EMP1004, INV-2026-00421, PROJ-101 into
 * natural spoken form: "EMP one zero zero four", "invoice 2026 zero zero four two one"
 */
function formatEnterpriseId(id: string): string {
  // Common enterprise prefixes with spoken names
  const PREFIX_NAMES: Record<string, string> = {
    "EMP": "employee",
    "INV": "invoice",
    "PROJ": "project",
    "TICK": "ticket",
    "ORD": "order",
    "PO": "P O",
    "REQ": "request",
    "DOC": "document",
    "RPT": "report",
    "ACCT": "account",
    "CUST": "customer",
    "VEND": "vendor",
    "SKU": "S K U",
  };

  // Try pattern: PREFIX + digits (e.g., EMP1004)
  const prefixMatch = id.match(/^([A-Z]{2,6})(\d+)$/);
  if (prefixMatch) {
    const prefix = PREFIX_NAMES[prefixMatch[1]] || formatAcronym(prefixMatch[1]);
    const digits = spellDigits(prefixMatch[2]);
    return `${prefix} ${digits}`;
  }

  // Try pattern: PREFIX-PART1-PART2... (e.g., INV-2026-00421)
  const parts = id.split(/[-_]/);
  if (parts.length >= 2) {
    const prefix = PREFIX_NAMES[parts[0].toUpperCase()] || formatAcronym(parts[0]);
    const rest = parts.slice(1).map(part => {
      if (/^\d+$/.test(part)) {
        // For year-like 4-digit numbers, speak as number
        if (part.length === 4 && (part.startsWith("19") || part.startsWith("20"))) {
          return yearToWords(parseInt(part, 10));
        }
        return spellDigits(part);
      }
      return part;
    });
    return `${prefix} ${rest.join(" ")}`;
  }

  return id;
}

// ─── Main Speech Normalization Function ─────────────────────────────────────

export function formatSpokenNumbers(text: string): string {
  if (!text) return "";
  let s = text;

  // ── 1. Enterprise IDs (EMP1004, INV-2026-00421, PROJ-101, etc.) ──
  // Must run BEFORE general number handling to prevent IDs being partially consumed
  s = s.replace(/\b([A-Z]{2,6})-(\d[\d-]+\d)\b/g, (match) => formatEnterpriseId(match));
  s = s.replace(/\b([A-Z]{2,6})(\d{3,})\b/g, (match) => formatEnterpriseId(match));

  // ── 2. Dates: YYYY-MM-DD or DD/MM/YYYY ──
  s = s.replace(/\b(\d{4})-(\d{2})-(\d{2})\b/g, (_, y, m, d) => formatDateForSpeech(y, m, d));
  s = s.replace(/\b(\d{1,2})\/(\d{1,2})\/(\d{4})\b/g, (_, d, m, y) => formatDateForSpeech(y, m, d));

  // ── 3. Times: 10:30 AM, 14:30, 2:00 PM ──
  s = s.replace(/\b(\d{1,2}):(\d{2})\s*(AM|PM|am|pm|a\.m\.|p\.m\.)\b/g, (_, h, m, period) => {
    const hour = parseInt(h, 10);
    const min = parseInt(m, 10);
    const p = period.replace(/\./g, "").toUpperCase();
    if (min === 0) return `${numberToWords(hour)} ${p.split("").join(" ")}`;
    return `${numberToWords(hour)} ${numberToWords(min)} ${p.split("").join(" ")}`;
  });
  s = s.replace(/\b(\d{1,2}):(\d{2})\b/g, (_, h, m) => {
    const hour = parseInt(h, 10);
    const min = parseInt(m, 10);
    if (hour >= 0 && hour <= 23 && min >= 0 && min <= 59) {
      if (min === 0) return numberToWords(hour) + " hundred hours";
      return `${numberToWords(hour)} ${min < 10 ? "oh " : ""}${numberToWords(min)}`;
    }
    return `${h}:${m}`;
  });

  // ── 4. Indian currency abbreviations: ₹18.4 Cr, ₹12L, Rs 40 Lakhs, 15 Lacs ──
  s = s.replace(/(?:₹|rs\.?|inr)\s*(\d+(?:\.\d+)?)\s*(?:cr|crore|crores)\b/gi, (_, n) => {
    const val = parseFloat(n);
    return `${numberToWords(Math.floor(val))}${val % 1 ? ` point ${Math.round((val % 1) * 10)}` : ""} crore rupees`;
  });
  s = s.replace(/(?:₹|rs\.?|inr)\s*(\d+(?:\.\d+)?)\s*(?:l|lac|lacs|lakh|lakhs)\b/gi, (_, n) => {
    const val = parseFloat(n);
    return `${numberToWords(Math.floor(val))}${val % 1 ? ` point ${Math.round((val % 1) * 10)}` : ""} lakh rupees`;
  });

  // ── 5. Dollar amounts with abbreviations: $4.2M, $100K, $5B ──
  s = s.replace(/\$\s*(\d+(?:\.\d+)?)\s*b(?:illion)?\b/gi, "$1 billion dollars");
  s = s.replace(/\$\s*(\d+(?:\.\d+)?)\s*m(?:illion)?\b/gi, "$1 million dollars");
  s = s.replace(/\$\s*(\d+(?:\.\d+)?)\s*k(?: thousand)?\b/gi, "$1 thousand dollars");

  // ── 6. Indian comma-formatted rupees: ₹4,50,000 or ₹18,40,00,000 ──
  s = s.replace(/(?:₹|rs\.?|inr)\s*(\d{1,3}(?:,\d{2,3})*(?:\.\d+)?)\b/gi, (_, rawDigits) => {
    const num = parseFloat(rawDigits.replace(/,/g, ""));
    if (isNaN(num)) return rawDigits;
    return formatNumberForSpeech(num, "inr");
  });

  // ── 7. US comma-formatted dollars: $4,200,000 ──
  s = s.replace(/\$\s*(\d{1,3}(?:,\d{3})*(?:\.\d+)?)\b/g, (_, rawDigits) => {
    const num = parseFloat(rawDigits.replace(/,/g, ""));
    if (isNaN(num)) return rawDigits;
    return formatNumberForSpeech(num, "usd");
  });

  // ── 8. Percentages: 14% → "14 percent", 14.2% → "14.2 percent" ──
  s = s.replace(/(\d+(?:\.\d+)?)\s*%/g, "$1 percent");

  // ── 8b. URLs: https://example.com/report → "the report link" ──
  s = s.replace(/https?:\/\/\S+/gi, (url) => {
    const u = url.toLowerCase();
    if (u.includes("report")) return "the report link";
    if (u.includes("invoice")) return "the invoice link";
    if (u.includes("doc") || u.includes("file") || u.includes("pdf")) return "the document link";
    if (u.includes("contract")) return "the contract link";
    return "the link";
  });

  // ── 9. Email addresses: hr@nanvi.ai → "H R at nanvi dot A I" ──
  s = s.replace(/\b([a-zA-Z0-9._%+-]+)@([a-zA-Z0-9.-]+)\.([a-zA-Z]{2,})\b/g, (_, name, domain, tld) => {
    const spokenName = name.length <= 3 ? name.toUpperCase().split("").join(" ") : name;
    const spokenTld = tld.length <= 3 ? tld.toUpperCase().split("").join(" ") : tld;
    return `${spokenName} at ${domain} dot ${spokenTld}`;
  });

  // ── 10. Phone numbers: +91-9876543210, (080) 1234-5678 ──
  s = s.replace(/\+(\d{1,3})[-.\s]?(\d{3,5})[-.\s]?(\d{3,5})[-.\s]?(\d{0,5})/g, (_, cc, p1, p2, p3) => {
    const ccSpelled = spellDigits(cc);
    const parts = [p1, p2, p3].filter(Boolean).map(spellDigits);
    return `plus ${ccSpelled}, ${parts.join(", ")}`;
  });

  // ── 11. Standalone acronyms (2-5 capital letters not part of a word) ──
  s = s.replace(/\b([A-Z]{2,6})\b/g, (match) => {
    // Don't re-process if it's a normal word
    if (/^[A-Z][a-z]/.test(match)) return match;
    return formatAcronym(match);
  });

  // ── 12. Large unformatted digit strings >= 1000 (with comma or raw) ──
  s = s.replace(/\b(\d{1,3}(?:,\d{2,3})+|\d{4,})\b/g, (match) => {
    // Preserve 4-digit calendar years
    if (match.length === 4 && (match.startsWith("19") || match.startsWith("20"))) {
      return yearToWords(parseInt(match, 10));
    }
    const num = parseFloat(match.replace(/,/g, ""));
    if (isNaN(num)) return match;
    // For small-to-medium numbers, speak as words
    if (num < 10000000 && Number.isInteger(num)) {
      return numberToWords(num);
    }
    if (num >= 100000) return formatNumberForSpeech(num, "none");
    return match;
  });

  // ── 13. Fiscal quarters and business abbreviations ──
  s = s.replace(/\bQ([1-4])\b/g, "Quarter $1");
  s = s.replace(/\bFY\s*(\d{2,4})\b/gi, "Fiscal Year $1");
  s = s.replace(/\bYoY\b/gi, "year over year");
  s = s.replace(/\bMoM\b/gi, "month over month");
  s = s.replace(/\bQoQ\b/gi, "quarter over quarter");
  s = s.replace(/\bWoW\b/gi, "week over week");
  s = s.replace(/\bP&L\b/gi, "profit and loss");
  s = s.replace(/\bR&D\b/gi, "R and D");
  s = s.replace(/\bM&A\b/gi, "M and A");

  return s;
}

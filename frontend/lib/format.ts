import type { ComplaintCategory, ComplaintStatus, DocumentStatus, TaskType } from "./types";

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** Local timezone format: "12 Oct 2026, 14:05" (design.md §7). */
export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  const day = String(d.getDate()).padStart(2, "0");
  const month = MONTHS[d.getMonth()];
  const year = d.getFullYear();
  const hours = String(d.getHours()).padStart(2, "0");
  const minutes = String(d.getMinutes()).padStart(2, "0");
  return `${day} ${month} ${year}, ${hours}:${minutes}`;
}

export function formatDateOnly(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  const day = String(d.getDate()).padStart(2, "0");
  const month = MONTHS[d.getMonth()];
  return `${day} ${month} ${d.getFullYear()}`;
}

export function formatTaskType(task: TaskType | string): string {
  switch (task) {
    case "discharge_summary":
      return "Discharge summary";
    case "case_summary":
      return "Case summary";
    case "treatment_plan":
      return "Treatment plan";
    default:
      return task;
  }
}

export function formatDocStatus(status: DocumentStatus | string): string {
  switch (status) {
    case "UPLOADED":
      return "Uploaded";
    case "PROCESSING":
      return "Processing";
    case "BLOCKED":
      return "Blocked";
    case "REVIEW_REQUIRED":
      return "Review required";
    case "APPROVED":
      return "Approved";
    case "SENDING":
      return "Generating";
    case "COMPLETED":
      return "Completed";
    case "LLM_FAILED":
      return "Generation failed";
    case "FAILED":
      return "Failed";
    default:
      return status;
  }
}

export function formatComplaintStatus(status: ComplaintStatus | string): string {
  switch (status) {
    case "open":
      return "Open";
    case "in_progress":
      return "In progress";
    case "resolved":
      return "Resolved";
    default:
      return status;
  }
}

export function formatComplaintCategory(cat: ComplaintCategory | string): string {
  switch (cat) {
    case "bug":
      return "Bug";
    case "account":
      return "Account";
    case "privacy":
      return "Privacy";
    case "other":
      return "Other";
    default:
      return cat;
  }
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

/** Parse a raw User-Agent string into a friendly label like "Edge on Windows" or "Safari on iPhone". */
export function formatUserAgent(ua: string | null | undefined): string {
  if (!ua || !ua.trim()) return "Unknown browser";
  const s = ua.trim();

  let browser: string | null = null;
  if (/Claude/i.test(s)) {
    browser = "Claude desktop app";
  } else if (/Edg(?:A|iOS)?\/|Edge\//i.test(s)) {
    browser = "Edge";
  } else if (/OPR\/|Opera/i.test(s)) {
    browser = "Opera";
  } else if (/SamsungBrowser\//i.test(s)) {
    browser = "Samsung Internet";
  } else if (/Firefox\/|FxiOS\//i.test(s)) {
    browser = "Firefox";
  } else if (/Brave/i.test(s)) {
    browser = "Brave";
  } else if (/CriOS\/|Chrome\//i.test(s)) {
    browser = "Chrome";
  } else if (/Safari\//i.test(s) && !/Android/i.test(s)) {
    browser = "Safari";
  }

  let os: string | null = null;
  if (/iPhone/i.test(s)) {
    os = "iPhone";
  } else if (/iPad/i.test(s)) {
    os = "iPad";
  } else if (/Android/i.test(s)) {
    os = "Android";
  } else if (/Windows/i.test(s)) {
    os = "Windows";
  } else if (/Macintosh|Mac OS X/i.test(s)) {
    os = "macOS";
  } else if (/CrOS/i.test(s)) {
    os = "ChromeOS";
  } else if (/Linux/i.test(s)) {
    os = "Linux";
  }

  if (browser && os) return `${browser} on ${os}`;
  if (browser) return browser;
  if (os) return `Unknown browser on ${os}`;
  return "Unknown browser";
}

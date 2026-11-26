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

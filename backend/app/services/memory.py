import logging
import resource

logger = logging.getLogger("app.memory")


def get_process_rss_mb() -> float:
    """Return current process resident set size (RSS) in megabytes."""
    try:
        with open("/proc/self/status", encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("VmRSS:"):
                    parts = line.split()
                    if len(parts) >= 2:
                        return round(int(parts[1]) / 1024.0, 1)
    except OSError:
        pass
    # Fallback via ru_maxrss (KB on Linux, bytes on macOS)
    rss_kb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return round(float(rss_kb) / 1024.0, 1)


def log_process_rss(stage: str, *, document_id: str | None = None) -> float:
    """Log process RSS in MB only (never PHI or filenames)."""
    rss_mb = get_process_rss_mb()
    extra: dict[str, object] = {
        "event": "memory_rss",
        "stage": stage,
        "rss_mb": rss_mb,
    }
    if document_id is not None:
        extra["document_id"] = document_id
    logger.info("Process memory RSS", extra=extra)
    return rss_mb

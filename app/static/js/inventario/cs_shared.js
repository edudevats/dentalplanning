// Utilities shared by the Clinical Sanctuary inventory views.
window.csShared = (function () {
  function currency(v) {
    if (v == null) return "—";
    const n = Number(v);
    if (!isFinite(n)) return "—";
    return new Intl.NumberFormat("es-MX", {
      style: "currency",
      currency: "MXN",
      maximumFractionDigits: 0,
    }).format(n);
  }

  function compactNumber(v) {
    if (v == null) return "—";
    const n = Number(v);
    if (!isFinite(n)) return "—";
    const abs = Math.abs(n);
    if (abs >= 1_000_000) return (n / 1_000_000).toFixed(1) + "M";
    if (abs >= 1_000)     return (n / 1_000).toFixed(1)     + "k";
    return String(n);
  }

  function timeAgo(iso) {
    if (!iso) return "—";
    const then = new Date(iso);
    const t = then.getTime();
    if (isNaN(t)) return "—";
    const diff = Math.max(0, (Date.now() - t) / 1000);
    if (diff < 60)    return "hace " + Math.floor(diff)        + " s";
    if (diff < 3600)  return "hace " + Math.floor(diff / 60)   + " min";
    if (diff < 86400) return "hace " + Math.floor(diff / 3600) + " h";
    return "hace " + Math.floor(diff / 86400) + " d";
  }

  function statusChip(label, variant) {
    // variant: "stable" | "low" | "critical" | "neutral"
    const span = document.createElement("span");
    const tone = {
      stable:   "bg-cs-primary-container text-cs-on-primary-container",
      low:      "bg-cs-error-container/30 text-cs-error",
      critical: "bg-cs-error-container text-cs-on-error-container",
      neutral:  "bg-cs-surface-container text-cs-on-surface-var",
    }[variant] || "bg-cs-surface-container text-cs-on-surface-var";
    span.className = "inline-flex items-center px-2.5 py-1 rounded-md text-xs font-semibold " + tone;
    span.textContent = label;
    return span;
  }

  // Safe Lucide icon constructor — creates <i data-lucide="...">. Call
  // lucide.createIcons() afterwards to hydrate it.
  function lucideIcon(name, extraClasses) {
    const i = document.createElement("i");
    i.setAttribute("data-lucide", name);
    i.className = extraClasses || "h-4 w-4";
    return i;
  }

  // Initials helper for avatar badges.
  function initials(nombre) {
    return (nombre || "")
      .split(/\s+/)
      .map(w => w[0] || "")
      .join("")
      .slice(0, 2)
      .toUpperCase();
  }

  return { currency, compactNumber, timeAgo, statusChip, lucideIcon, initials };
})();

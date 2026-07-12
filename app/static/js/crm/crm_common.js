/* Utilidades compartidas de las páginas del CRM. */

/** Escapa texto para interpolar en innerHTML (previene XSS). */
function esc(s) {
  return String(s == null ? '' : s)
    .replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;').replaceAll("'", '&#39;');
}

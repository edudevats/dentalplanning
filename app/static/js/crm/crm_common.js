/* Utilidades compartidas de las páginas del CRM. */

/** Escapa texto para interpolar en innerHTML (previene XSS). */
function esc(s) {
  return String(s == null ? '' : s)
    .replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;').replaceAll("'", '&#39;');
}

/** "A, B" o "AB" -> ["A", "B"]: letras A–Z en mayúscula, sin repetir. */
function letrasDeTexto(texto) {
  const letras = String(texto || '').toUpperCase().replace(/[^A-Z]/g, '').split('');
  return [...new Set(letras)];
}

/** Guarda el formato de numeración de expedientes (solo admin).
 *  Lanza Error con el mensaje a mostrar; el servidor valida el resto de las reglas. */
async function guardarConfigExpediente(formato, textoLetras) {
  if (!formato) throw new Error('Elige cómo numeran sus expedientes');
  const letras = formato === 'letra' ? letrasDeTexto(textoLetras) : [];
  if (formato === 'letra' && !letras.length) throw new Error('Escribe al menos una letra (A–Z)');
  return API.put('/crm/expediente/config', { formato, letras });
}

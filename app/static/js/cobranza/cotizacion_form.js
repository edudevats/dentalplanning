/* Formulario de cotización. Requiere app.js. */
const CobranzaForm = (() => {
  const state = {
    id: null,
    pacienteResultados: [],
    tratamientos: [],
    especialistas: [],
    sucursales: [],
    calendario: [],
    loaded: false,
  };
  const $ = id => document.getElementById(id);

  // Espejo de app/cobranza/calculo.py: mismas tolerancias y mismo algoritmo
  // de redondeo, para que el calendario que arma el doctor aquí sea idéntico
  // al que el servidor validaría/generaría con los mismos datos.
  const TOLERANCIA = 0.01;
  const MAX_PARCIALIDADES = 120;

  // Half-up a centavos. El servidor usa round(x, 2) de Python, que es bancario:
  // difieren sólo en el empate exacto del medio centavo (19999.995), que no se
  // puede capturar porque los campos de monto están limitados a step="0.01".
  // En cualquier caso el servidor recalcula y es la fuente de verdad.
  function round2(valor) {
    return Math.round((valor + Number.EPSILON) * 100) / 100;
  }

  function round6(valor) {
    return Math.round((valor + Number.EPSILON) * 1e6) / 1e6;
  }

  function redondearAPeso(valor) {
    // Half-up a pesos enteros. Igual que _redondear_a_peso en calculo.py:
    // Math.round de JS también redondea distinto en negativos, pero aquí
    // `valor` siempre es positivo (restante/n con restante y n > 0).
    return Math.floor(valor + 0.5);
  }

  function montosPorNumero(restante, n) {
    if (!Number.isInteger(n) || n < 1) {
      throw new Error('El número de parcialidades debe ser al menos 1');
    }
    if (n > MAX_PARCIALIDADES) {
      throw new Error(`El máximo son ${MAX_PARCIALIDADES} parcialidades`);
    }
    if (restante <= TOLERANCIA) {
      throw new Error('No queda saldo por diferir');
    }
    if (n === 1) return [round2(restante)];
    const base = redondearAPeso(restante / n);
    if (base <= 0) {
      throw new Error('Son demasiadas parcialidades para ese monto: cada pago quedaría en cero');
    }
    const ultima = round2(restante - base * (n - 1));
    if (ultima <= 0) {
      throw new Error('Son demasiadas parcialidades para ese monto: el último pago quedaría en cero');
    }
    return Array(n - 1).fill(base).concat([ultima]);
  }

  function montosPorMonto(restante, monto) {
    if (monto <= 0) {
      throw new Error('El monto de la parcialidad debe ser mayor a cero');
    }
    if (restante <= TOLERANCIA) {
      throw new Error('No queda saldo por diferir');
    }
    // El round() previo absorbe el ruido de punto flotante antes del techo,
    // igual que en calculo.py (18000/1000 puede dar 17.999999999999996).
    const n = Math.ceil(round6(restante / monto));
    if (n > MAX_PARCIALIDADES) {
      throw new Error(
        `Con ese monto salen más de ${MAX_PARCIALIDADES} pagos: sube el monto de la parcialidad`,
      );
    }
    if (n === 1) return [round2(restante)];
    const ultima = round2(restante - monto * (n - 1));
    if (ultima <= 0) {
      throw new Error('Son demasiadas parcialidades para ese monto: el último pago quedaría en cero');
    }
    return Array(n - 1).fill(monto).concat([ultima]);
  }

  function localISO(date = new Date()) {
    return [
      date.getFullYear(),
      String(date.getMonth() + 1).padStart(2, '0'),
      String(date.getDate()).padStart(2, '0'),
    ].join('-');
  }

  function addDays(iso, days) {
    const [y, m, d] = iso.split('-').map(Number);
    const date = new Date(y, m - 1, d);
    date.setDate(date.getDate() + days);
    return localISO(date);
  }

  function addMonths(iso, months) {
    const [year, month, day] = iso.split('-').map(Number);
    const target = new Date(year, month - 1 + months, 1);
    const last = new Date(
      target.getFullYear(), target.getMonth() + 1, 0,
    ).getDate();
    target.setDate(Math.min(day, last));
    return localISO(target);
  }

  function fillSelect(select, items, placeholder, selected = '') {
    select.replaceChildren();
    const first = document.createElement('option');
    first.value = '';
    first.textContent = placeholder;
    select.appendChild(first);
    items.forEach(item => {
      const option = document.createElement('option');
      option.value = String(item.id);
      option.textContent = item.nombre;
      option.selected = String(item.id) === String(selected || '');
      select.appendChild(option);
    });
  }

  async function loadCatalogs(force = false) {
    if (state.loaded && !force) return;
    const results = await Promise.allSettled([
      API.get('/tratamientos'),
      API.get('/ajustes/especialistas'),
      API.get('/facturacion/sucursales'),
    ]);
    const value = (index, fallback) => (
      results[index].status === 'fulfilled' ? results[index].value : fallback
    );
    const tratamientos = value(0, []);
    const especialistas = value(1, []);
    const sucursales = value(2, []);
    state.tratamientos = Array.isArray(tratamientos) ? tratamientos : [];
    state.especialistas = Array.isArray(especialistas) ? especialistas : [];
    state.sucursales = (Array.isArray(sucursales) ? sucursales : [])
      .filter(item => item.activa !== false);
    if (results[0].status === 'rejected') {
      Toast.warning('El catálogo de tratamientos no está disponible; puedes usar conceptos libres');
    }
    state.loaded = true;
    renderCatalogs();
  }

  function renderCatalogs(selected = {}) {
    fillSelect($('cot-sucursal'), state.sucursales, 'Sucursal automática', selected.sucursal_id);
  }

  function treatmentName(id) {
    const t = state.tratamientos.find(x => String(x.id) === String(id || ''));
    return t ? t.nombre : '';
  }

  function addConcept(concept = {}) {
    const row = document.createElement('div');
    row.className = 'concepto-row grid grid-cols-1 md:grid-cols-12 gap-2 items-end rounded-lg border border-border p-3';
    row.innerHTML = `
      <label class="text-xs md:col-span-3">Catálogo
        <div class="relative mt-1">
          <input class="concepto-buscar-tratamiento w-full rounded-lg border border-border px-2 py-2 text-sm" type="text" autocomplete="off" placeholder="Buscar…" value="${esc(treatmentName(concept.tratamiento_id))}" />
          <input class="concepto-tratamiento" type="hidden" value="${concept.tratamiento_id ? esc(String(concept.tratamiento_id)) : ''}" />
        </div>
      </label>
      <label class="text-xs md:col-span-4">Descripción *
        <input class="concepto-descripcion mt-1 w-full rounded-lg border border-border px-2 py-2 text-sm" maxlength="300" value="${esc(concept.descripcion || '')}" />
      </label>
      <label class="text-xs md:col-span-2">Cantidad
        <input class="concepto-cantidad mt-1 w-full rounded-lg border border-border px-2 py-2 text-sm" type="number" min="0.01" step="0.01" value="${concept.cantidad || 1}" />
      </label>
      <label class="text-xs md:col-span-2">Precio
        <input class="concepto-precio mt-1 w-full rounded-lg border border-border px-2 py-2 text-sm" type="number" min="0" step="0.01" value="${concept.precio_unitario ?? 0}" />
      </label>
      <button type="button" class="concepto-remove md:col-span-1 rounded-lg p-2 text-danger-600 hover:bg-danger-50 cursor-pointer" aria-label="Quitar concepto">
        <i data-lucide="trash-2" class="h-4 w-4 mx-auto"></i>
      </button>`;
    const tratSearch = row.querySelector('.concepto-buscar-tratamiento');
    const tratHidden = row.querySelector('.concepto-tratamiento');
    tratSearch.addEventListener('input', () => {
      if (!tratSearch.value.trim()) tratHidden.value = '';  // concepto libre
    });
    Combobox({
      input: tratSearch,
      getItems: () => state.tratamientos,
      getMeta: t => (t.precio_paciente != null ? fmt(t.precio_paciente) : null),
      onSelect: t => {
        tratHidden.value = String(t.id);
        tratSearch.value = t.nombre;
        row.querySelector('.concepto-descripcion').value = t.nombre;
        row.querySelector('.concepto-precio').value = t.precio_paciente || 0;
        updateTotal();
      },
      clearOnSelect: false,
      emptyText: 'Sin tratamientos',
    });
    row.querySelector('.concepto-remove').addEventListener('click', () => {
      if (document.querySelectorAll('.concepto-row').length === 1) {
        Toast.warning('La cotización necesita al menos un concepto');
        return;
      }
      row.remove();
      updateTotal();
    });
    row.querySelectorAll('input').forEach(input => input.addEventListener('input', updateTotal));
    $('conceptos-list').appendChild(row);
    if (window.lucide) lucide.createIcons();
    updateTotal();
  }

  function concepts() {
    return Array.from(document.querySelectorAll('.concepto-row')).map(row => ({
      tratamiento_id: Number(row.querySelector('.concepto-tratamiento').value) || null,
      descripcion: row.querySelector('.concepto-descripcion').value.trim(),
      cantidad: Number(row.querySelector('.concepto-cantidad').value) || 0,
      precio_unitario: Number(row.querySelector('.concepto-precio').value) || 0,
    }));
  }

  function total() {
    const subtotal = concepts().reduce(
      (sum, item) => sum + item.cantidad * item.precio_unitario, 0,
    );
    const type = $('cot-descuento-tipo').value;
    const value = Number($('cot-descuento-valor').value) || 0;
    const discount = type === 'porcentaje' ? subtotal * value / 100
      : type === 'monto' ? value : 0;
    return Math.max(Math.round((subtotal - discount) * 100) / 100, 0);
  }

  function updateTotal() {
    $('cot-total-preview').textContent = fmt(total());
  }

  function planMode() {
    return document.querySelector('input[name="modo-plan"]:checked').value;
  }

  function updateMode() {
    const byAmount = planMode() === 'monto';
    $('wrap-num-pagos').classList.toggle('hidden', byAmount);
    $('wrap-monto-pago').classList.toggle('hidden', !byAmount);
  }

  function generateSchedule() {
    const quoteTotal = total();
    const advance = Number($('cot-anticipo').value) || 0;
    const remaining = round2(quoteTotal - advance);
    if (quoteTotal <= 0 || advance < 0 || remaining < 0) {
      Toast.warning('Revisa el total y el anticipo');
      return;
    }
    const rows = [];
    if (advance > TOLERANCIA) {
      rows.push({
        numero: 0,
        // El vencimiento real del anticipo lo fija el servidor al aprobar
        // (usa la fecha de aprobación, no la de captura: ver aprobar_cotizacion
        // en services.py). Se deja en blanco para que el doctor lo capture
        // explícitamente en vez de mostrar una fecha que va a cambiar.
        fecha_vencimiento: '',
        monto_programado: round2(advance),
      });
    }
    // Si el anticipo cubre el total, no hay parcialidades que generar: el
    // servidor tampoco las genera (calcular_plan corta aquí cuando el
    // restante queda por debajo de la tolerancia).
    if (remaining > TOLERANCIA) {
      let montos;
      try {
        if (planMode() === 'monto') {
          const amount = Number($('cot-monto-pago').value) || 0;
          if (amount <= 0) { Toast.warning('Captura el monto por pago'); return; }
          montos = montosPorMonto(remaining, amount);
        } else {
          const count = Number($('cot-num-pagos').value) || 0;
          if (count < 1) { Toast.warning('Captura el número de pagos'); return; }
          montos = montosPorNumero(remaining, count);
        }
      } catch (error) {
        Toast.warning(error.message);
        return;
      }
      const first = $('cot-primer-pago').value || addDays(localISO(), 30);
      montos.forEach((value, index) => {
        const number = index + 1;
        const due = $('cot-frecuencia').value === 'quincenal'
          ? addDays(first, (number - 1) * 15)
          : addMonths(first, number - 1);
        rows.push({ numero: number, fecha_vencimiento: due, monto_programado: value });
      });
    }
    state.calendario = rows;
    renderSchedule();
  }

  function renderSchedule() {
    const container = $('calendario-list');
    container.replaceChildren();
    state.calendario.forEach(item => {
      const row = document.createElement('div');
      row.className = 'grid grid-cols-12 gap-2 items-center';
      row.dataset.numero = String(item.numero);
      row.innerHTML = `
        <span class="col-span-3 text-sm font-medium">${item.numero === 0 ? 'Anticipo' : `Pago ${item.numero}`}</span>
        <input type="date" class="cal-fecha col-span-5 rounded-lg border border-border px-2 py-1.5 text-sm" value="${esc(item.fecha_vencimiento)}" />
        <input type="number" min="0.01" step="0.01" class="cal-monto col-span-4 rounded-lg border border-border px-2 py-1.5 text-sm" value="${esc(item.monto_programado)}" />`;
      container.appendChild(row);
    });
  }

  function toggleManual() {
    const manual = $('cot-calendario-manual').checked;
    $('btn-generar-calendario').classList.toggle('hidden', !manual);
    $('calendario-list').classList.toggle('hidden', !manual);
    if (manual && !state.calendario.length) generateSchedule();
  }

  function collectSchedule() {
    if (!$('cot-calendario-manual').checked) return undefined;
    return Array.from($('calendario-list').children).map(row => ({
      numero: Number(row.dataset.numero),
      fecha_vencimiento: row.querySelector('.cal-fecha').value,
      monto_programado: Number(row.querySelector('.cal-monto').value),
    }));
  }

  function reset() {
    state.id = null;
    state.calendario = [];
    $('form-cotizacion').reset();
    $('cot-paciente-search').value = '';
    $('cot-paciente').value = '';
    $('cot-especialista-search').value = '';
    $('cot-especialista').value = '';
    state.pacienteResultados = [];
    $('conceptos-list').replaceChildren();
    $('cot-valida').value = addDays(localISO(), 30);
    $('cot-primer-pago').value = addDays(localISO(), 30);
    $('cot-num-pagos').value = '1';
    $('cot-anticipo').value = '0';
    $('cot-descuento-valor').value = '0';
    $('calendario-list').replaceChildren();
    toggleManual();
    updateMode();
    addConcept();
  }

  async function open(quote = null) {
    try {
      await loadCatalogs();
      reset();
      state.id = quote && quote.id;
      $('cot-form-title').textContent = state.id ? `Editar ${quote.folio}` : 'Nueva cotización';
      if (quote) {
        renderCatalogs(quote);
        $('cot-paciente-search').value = quote.paciente_nombre || '';
        $('cot-paciente').value = quote.paciente_id ? String(quote.paciente_id) : '';
        const doctor = state.especialistas.find(
          e => String(e.id) === String(quote.especialista_id || ''),
        );
        $('cot-especialista-search').value = doctor ? doctor.nombre : '';
        $('cot-especialista').value = doctor ? String(doctor.id) : '';
        $('cot-valida').value = quote.valida_hasta || '';
        $('cot-inicio').value = quote.fecha_inicio_tratamiento || '';
        $('cot-frecuencia').value = quote.frecuencia || 'mensual';
        $('cot-factura').checked = Boolean(quote.requiere_factura);
        $('cot-descuento-tipo').value = quote.descuento_tipo || '';
        $('cot-descuento-valor').value = quote.descuento_valor || 0;
        $('cot-anticipo').value = quote.anticipo || 0;
        $('cot-primer-pago').value = quote.fecha_primer_pago || '';
        $('cot-notas').value = quote.notas || '';
        $('conceptos-list').replaceChildren();
        (quote.conceptos || []).forEach(addConcept);
        if (quote.monto_parcialidad != null) {
          document.querySelector('input[name="modo-plan"][value="monto"]').checked = true;
          $('cot-monto-pago').value = quote.monto_parcialidad;
        } else {
          $('cot-num-pagos').value = quote.num_parcialidades || 1;
        }
        state.calendario = (quote.programados || []).map(item => ({
          numero: item.numero,
          fecha_vencimiento: item.fecha_vencimiento,
          monto_programado: item.monto_programado,
        }));
        if (state.calendario.length) $('cot-calendario-manual').checked = true;
        updateMode();
        toggleManual();
        renderSchedule();
      } else {
        renderCatalogs();
      }
      updateTotal();
      Modal.open('modal-cotizacion-form');
    } catch (error) {
      Toast.error(error.message || 'No se pudo preparar el formulario');
    }
  }

  function payload() {
    const mode = planMode();
    return {
      paciente_id: Number($('cot-paciente').value),
      especialista_id: Number($('cot-especialista').value) || null,
      sucursal_id: Number($('cot-sucursal').value) || null,
      valida_hasta: $('cot-valida').value || null,
      fecha_inicio_tratamiento: $('cot-inicio').value || null,
      frecuencia: $('cot-frecuencia').value,
      num_parcialidades: mode === 'numero' ? Number($('cot-num-pagos').value) : null,
      monto_parcialidad: mode === 'monto' ? Number($('cot-monto-pago').value) : null,
      anticipo: Number($('cot-anticipo').value) || 0,
      fecha_primer_pago: $('cot-primer-pago').value || null,
      descuento_tipo: $('cot-descuento-tipo').value || null,
      descuento_valor: Number($('cot-descuento-valor').value) || 0,
      requiere_factura: $('cot-factura').checked,
      notas: $('cot-notas').value.trim() || null,
      conceptos: concepts(),
      calendario: collectSchedule(),
    };
  }

  // Marca en rojo la primera fila del calendario a la que le falta la fecha y
  // devuelve su etiqueta. El anticipo nace sin fecha a propósito (el servidor
  // la fija al aprobar), así que si el doctor edita el calendario a mano tiene
  // que capturarla él.
  function faltaFechaEnCalendario() {
    const filas = Array.from($('calendario-list').children);
    for (const fila of filas) {
      const campo = fila.querySelector('.cal-fecha');
      campo.classList.remove('border-danger-500');
      if (!campo.value) {
        campo.classList.add('border-danger-500');
        campo.focus();
        return Number(fila.dataset.numero) === 0
          ? 'el anticipo' : `el pago ${fila.dataset.numero}`;
      }
    }
    return null;
  }

  // Convierte los `details` de marshmallow (anidados por índice de fila) en un
  // texto que el usuario pueda accionar, en vez de un "Datos inválidos" pelón.
  function mensajeError(error, respaldo) {
    const data = error && error.response && error.response.data;
    const details = data && data.details;
    if (details && typeof details === 'object') {
      const partes = [];
      const recorrer = (nodo, ruta) => {
        if (Array.isArray(nodo)) {
          partes.push(ruta ? `${ruta}: ${nodo.join(' ')}` : nodo.join(' '));
          return;
        }
        if (nodo && typeof nodo === 'object') {
          for (const [clave, valor] of Object.entries(nodo)) {
            // Una clave numérica es el índice de una fila: se pega a la ruta
            // que ya venía ("calendario" + "#1"), no se agrega como nivel nuevo.
            const rama = /^\d+$/.test(clave)
              ? `${ruta} #${Number(clave) + 1}`
              : (ruta ? `${ruta} · ${clave}` : clave);
            recorrer(valor, rama);
          }
        }
      };
      recorrer(details, '');
      if (partes.length) return partes.join(' — ');
    }
    return (data && data.error) || (error && error.message) || respaldo;
  }

  async function save(event) {
    event.preventDefault();
    const body = payload();
    if (!body.paciente_id) { Toast.warning('Selecciona un paciente'); return; }
    if (body.conceptos.some(item => !item.descripcion)) {
      Toast.warning('Todos los conceptos necesitan descripción'); return;
    }
    if (body.calendario) {
      const sinFecha = faltaFechaEnCalendario();
      if (sinFecha) {
        Toast.warning(`Captura la fecha de ${sinFecha} en el calendario`);
        return;
      }
    }
    const button = $('btn-guardar-cotizacion');
    button.disabled = true;
    try {
      const quote = state.id
        ? await API.put(`/cobranza/cotizaciones/${state.id}`, body)
        : await API.post('/cobranza/cotizaciones', body);
      Modal.close('modal-cotizacion-form');
      Toast.success(state.id ? 'Cotización actualizada' : 'Cotización creada');
      await Cobranza.reload();
      Cobranza.openDetail(quote.id);
    } catch (error) {
      Toast.error(mensajeError(error, 'No se pudo guardar la cotización'));
    } finally {
      button.disabled = false;
    }
  }

  async function savePatient(event) {
    event.preventDefault();
    try {
      const patient = await API.post('/crm/pacientes', {
        nombre: $('paciente-nombre').value.trim(),
        telefono: $('paciente-telefono').value.trim() || null,
        email: $('paciente-email').value.trim() || null,
        estatus_crm: 'prospecto',
      });
      state.pacienteResultados = [
        { id: patient.id, nombre: patient.nombre, telefono: patient.telefono || null },
      ];
      $('cot-paciente-search').value = patient.nombre;
      $('cot-paciente').value = String(patient.id);
      Modal.close('modal-paciente-rapido');
      $('form-paciente-rapido').reset();
      Toast.success('Paciente creado');
    } catch (error) {
      Toast.error(error.message || 'No se pudo crear el paciente');
    }
  }

  // Doctor: filtra la lista local state.especialistas. Opcional: vaciar el
  // buscador equivale a "Sin doctor" (hidden en '').
  function setupDoctorCombobox() {
    const input = $('cot-especialista-search');
    const hidden = $('cot-especialista');
    input.addEventListener('input', () => {
      // Al teclear se invalida la selección previa hasta volver a elegir de la
      // lista, para no enviar un especialista_id que no coincida con el texto.
      hidden.value = '';
    });
    Combobox({
      input,
      getItems: () => state.especialistas,
      onSelect: e => { hidden.value = String(e.id); input.value = e.nombre; },
      clearOnSelect: false,
      emptyText: 'Sin doctores',
    });
  }

  let comboPaciente = null;

  // Paciente: busca en el servidor con debounce; el <input> oculto cot-paciente
  // guarda el id que leen payload()/save(). Reutiliza Combobox (app.js) filtrando
  // sobre state.pacienteResultados; la etiqueta incluye el teléfono para que las
  // coincidencias por teléfono no se descarten en el filtro local del Combobox.
  function setupPacienteCombobox() {
    const input = $('cot-paciente-search');
    const hidden = $('cot-paciente');
    let timer = null;
    input.addEventListener('input', () => {
      hidden.value = '';
      clearTimeout(timer);
      const q = input.value.trim();
      if (q.length < 2) {
        state.pacienteResultados = [];
        if (comboPaciente) comboPaciente.refresh();
        return;
      }
      timer = setTimeout(async () => {
        try {
          const data = await API.get('/crm/pacientes/buscar?q=' + encodeURIComponent(q));
          state.pacienteResultados = data.pacientes || [];
        } catch (error) {
          state.pacienteResultados = [];
          Toast.error('No se pudo buscar pacientes');
        }
        if (comboPaciente) comboPaciente.refresh();
      }, 250);
    });
    comboPaciente = Combobox({
      input,
      getItems: () => state.pacienteResultados,
      getLabel: p => (p.telefono ? `${p.nombre} · ${p.telefono}` : p.nombre),
      onSelect: p => { hidden.value = String(p.id); input.value = p.nombre; },
      clearOnSelect: false,
      emptyText: 'Escribe para buscar…',
    });
  }

  function init() {
    $('btn-agregar-concepto').addEventListener('click', () => addConcept());
    $('btn-generar-calendario').addEventListener('click', generateSchedule);
    $('cot-calendario-manual').addEventListener('change', toggleManual);
    $('form-cotizacion').addEventListener('submit', save);
    $('form-paciente-rapido').addEventListener('submit', savePatient);
    $('btn-nuevo-paciente').addEventListener('click', () => Modal.open('modal-paciente-rapido'));
    document.querySelectorAll('input[name="modo-plan"]').forEach(
      radio => radio.addEventListener('change', updateMode),
    );
    ['cot-descuento-tipo', 'cot-descuento-valor', 'cot-anticipo'].forEach(
      id => $(id).addEventListener('input', updateTotal),
    );
    setupPacienteCombobox();
    setupDoctorCombobox();
  }

  return { init, open, loadCatalogs, specialists: () => state.especialistas };
})();

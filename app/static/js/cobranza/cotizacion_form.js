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
    descuentosActivos: false,
    modoDescuento: 'descuento',
    cuponesPorId: {},
    // Fecha de la cotización, para validar cupones contra ELLA y no contra
    // hoy (el servidor valida contra `cot.fecha`, no contra la fecha del
    // navegador -- ver validar_cupon en ajustes/services.py). null en una
    // cotización nueva que todavía no tiene fecha asignada; la asigna el
    // servidor al crear.
    fecha: null,
    // true cuando la cotización abierta ya no está en borrador/enviada: el
    // servidor rechaza cualquier cambio (actualizar_cotizacion en services.py),
    // así que los campos de cupón se deshabilitan para no ofrecer algo que se
    // va a rechazar. El botón "Editar" de cotizaciones.js ya sólo aparece para
    // esos dos estatus; esto es una segunda capa por si se llama open() directo.
    cuponBloqueado: false,
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
      API.get('/ajustes/descuentos/config'),
      API.get('/ajustes/cupones'),
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
    // Si la config falla queda apagado: el backend rechazaría el canje de
    // todos modos, así que ocultar es la respuesta conservadora.
    const dcfg = value(3, null);
    state.descuentosActivos = Boolean(dcfg && dcfg.activo);
    $('cot-modo-wrap').classList.toggle('hidden', !state.descuentosActivos);
    // Mapa id → código para rehidratar los cupones de una cotización guardada:
    // los conceptos sólo devuelven cupon_id (cupon_codigo es load_only en
    // ConceptoSchema). Se pide aquí en vez de meterle a cobranza/routes.py una
    // dependencia de ajustes que sólo necesita esta vista.
    const cupones = value(4, []);
    state.cuponesPorId = Object.fromEntries(
      (Array.isArray(cupones) ? cupones : []).map(c => [c.id, c.codigo]),
    );
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
      <label class="text-xs md:col-span-2">Catálogo
        <div class="relative mt-1">
          <input class="concepto-buscar-tratamiento w-full rounded-lg border border-border px-2 py-2 text-sm" type="text" autocomplete="off" placeholder="Buscar…" value="${esc(treatmentName(concept.tratamiento_id))}" />
          <input class="concepto-tratamiento" type="hidden" value="${concept.tratamiento_id ? esc(String(concept.tratamiento_id)) : ''}" />
        </div>
      </label>
      <label class="text-xs md:col-span-3">Descripción *
        <input class="concepto-descripcion mt-1 w-full rounded-lg border border-border px-2 py-2 text-sm" maxlength="300" value="${esc(concept.descripcion || '')}" />
      </label>
      <label class="text-xs md:col-span-2">Cantidad
        <input class="concepto-cantidad mt-1 w-full rounded-lg border border-border px-2 py-2 text-sm" type="number" min="0.01" step="0.01" value="${concept.cantidad || 1}" />
      </label>
      <label class="text-xs md:col-span-2">Precio
        <input class="concepto-precio mt-1 w-full rounded-lg border border-border px-2 py-2 text-sm" type="number" min="0" step="0.01" value="${concept.precio_unitario ?? 0}" />
      </label>
      <label class="concepto-cupon-wrap text-xs md:col-span-2 hidden">Cupón
        <input class="concepto-cupon mt-1 w-full rounded-lg border border-border px-2 py-2 text-sm uppercase" type="text" value="${esc(state.cuponesPorId[concept.cupon_id] || '')}" ${state.cuponBloqueado ? 'disabled' : ''} />
        <p class="concepto-cupon-msg text-xs mt-1 hidden"></p>
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
        // El tratamiento cambió: cualquier precio de lista guardado
        // (dataset.precioLista) era del tratamiento VIEJO y queda inválido.
        // Se descarta -- el precio correcto de lista ahora es el que se
        // acaba de escribir arriba (el del tratamiento NUEVO), no el de
        // lista del viejo. Si el renglón trae un código de cupón capturado,
        // se revalida contra el tratamiento nuevo: el cupón está atado a un
        // tratamiento concreto, así que lo más probable es que ya no
        // aplique y haya que mostrar el error (ver hallazgo I5).
        delete row.dataset.precioLista;
        const cuponInput = row.querySelector('.concepto-cupon');
        if (cuponInput && cuponInput.value.trim()) {
          validarCuponConcepto(row);
        } else {
          updateTotal();
        }
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
    // El listener de arriba ya engancha el input de cupón a updateTotal:
    // teclear el código no cambia el total, sólo lo hace el blur de abajo
    // cuando la validación contra el servidor baja (o no) el precio mostrado.
    const cuponWrap = row.querySelector('.concepto-cupon-wrap');
    cuponWrap.classList.toggle('hidden', state.modoDescuento !== 'cupon');
    row.querySelector('.concepto-cupon')
      .addEventListener('blur', () => validarCuponConcepto(row));
    // Si el concepto viene de una cotización guardada con cupón, precargar el
    // precio de LISTA: precio_unitario ya llegó neto (services.py lo guarda
    // así) y descuento_monto es el total de la línea (unitario x cantidad),
    // así que hay que devolverlo a unitario para reconstruir el precio de
    // lista antes del cupón.
    if (concept.cupon_id && concept.descuento_monto && concept.cantidad) {
      const descUnitario = concept.descuento_monto / concept.cantidad;
      row.dataset.precioLista = String(
        Number(concept.precio_unitario || 0) + descUnitario,
      );
    }
    $('conceptos-list').appendChild(row);
    if (window.lucide) lucide.createIcons();
    updateTotal();
  }

  function concepts() {
    return Array.from(document.querySelectorAll('.concepto-row')).map(row => {
      const codigo = state.modoDescuento === 'cupon'
        ? row.querySelector('.concepto-cupon').value.trim() : '';
      const mostrado = Number(row.querySelector('.concepto-precio').value) || 0;
      return {
        tratamiento_id: Number(row.querySelector('.concepto-tratamiento').value) || null,
        descripcion: row.querySelector('.concepto-descripcion').value.trim(),
        cantidad: Number(row.querySelector('.concepto-cantidad').value) || 0,
        // Con cupón viaja el precio de LISTA (guardado en el dataset cuando el
        // cupón se validó); el servidor es quien baja el unitario y guarda
        // descuento_monto. Mandar el neto que ya se ve en pantalla haría que
        // el backend lo descontara una segunda vez.
        precio_unitario: codigo && row.dataset.precioLista
          ? Number(row.dataset.precioLista)
          : mostrado,
        cupon_codigo: codigo || null,
      };
    });
  }

  function total() {
    // Se recorre el DOM directo (no concepts()) porque el precio del input ya
    // trae el cupón aplicado: sumar cantidad x precio mostrado cuadra con lo
    // que el servidor va a guardar. concepts() en cambio manda el precio de
    // LISTA cuando hay cupón, y usar eso aquí duplicaría el descuento en la
    // vista previa.
    const subtotal = Array.from(document.querySelectorAll('.concepto-row'))
      .reduce((sum, row) => {
        const cantidad = Number(row.querySelector('.concepto-cantidad').value) || 0;
        const precio = Number(row.querySelector('.concepto-precio').value) || 0;
        return sum + cantidad * precio;
      }, 0);
    const type = $('cot-descuento-tipo').value;
    const value = Number($('cot-descuento-valor').value) || 0;
    const discount = type === 'porcentaje' ? subtotal * value / 100
      : type === 'monto' ? value : 0;
    return Math.max(Math.round((subtotal - discount) * 100) / 100, 0);
  }

  function updateTotal() {
    $('cot-total-preview').textContent = fmt(total());
  }

  // Devuelve el input .concepto-precio de un renglón al precio de LISTA
  // guardado en su dataset (si lo hay) antes de borrar el dataset. Sin esto,
  // el input se queda mostrando un neto ya descontado sin ningún cupón
  // asociado, y ese "descuento fantasma" se manda al backend como si fuera
  // el precio normal del concepto (ver hallazgo Critical de la Tarea 10).
  // Si el renglón nunca tuvo cupón (no hay dataset.precioLista), no toca el
  // input: no hay nada que restaurar.
  function restaurarPrecioLista(row) {
    const lista = row.dataset.precioLista;
    if (lista !== undefined) {
      row.querySelector('.concepto-precio').value = Number(lista).toFixed(2);
    }
    delete row.dataset.precioLista;
  }

  // Cambia entre "Descuento" (sobre el total) y "Cupón" (por renglón). Son
  // excluyentes: el servidor rechaza una cotización que traiga cupones por
  // renglón y además descuento_tipo sobre el documento (_resolver_cupon_concepto
  // en cobranza/services.py).
  //
  // El wrapper #cot-descuento-doc usa class="contents" para no romper la
  // rejilla del <section> (dos <label> como columnas propias), así que la
  // visibilidad se alterna sobre esos dos <label> hijos directamente y no
  // sobre el wrapper: si "hidden" y "contents" compitieran en el mismo
  // elemento, cuál gana depende del orden en que Tailwind (CDN/JIT) genere
  // esas utilidades, y no vale la pena apostarle a eso.
  function aplicarModo(modo) {
    state.modoDescuento = modo;
    document.querySelectorAll('.cot-modo').forEach(b => {
      const activo = b.dataset.modo === modo;
      b.className = 'cot-modo flex-1 px-3 py-2 text-sm cursor-pointer '
        + 'disabled:opacity-50 disabled:cursor-not-allowed '
        + (activo ? 'bg-primary-50 text-primary-700 font-medium'
                  : 'bg-surface text-text-secondary hover:bg-surface-hover');
    });
    const esCupon = modo === 'cupon';
    document.querySelectorAll('#cot-descuento-doc > label')
      .forEach(el => el.classList.toggle('hidden', esCupon));
    if (esCupon) {
      $('cot-descuento-tipo').value = '';
      $('cot-descuento-valor').value = 0;
    }
    document.querySelectorAll('.concepto-cupon-wrap')
      .forEach(w => w.classList.toggle('hidden', !esCupon));
    if (!esCupon) {
      // Se sale de modo Cupón: cualquier renglón que traiga un precio ya
      // descontado por un cupón (dataset.precioLista) debe volver a su
      // precio de lista antes de perder el código y el rastro del cupón —
      // si no, el neto descontado se queda en el input como si fuera el
      // precio normal del concepto.
      document.querySelectorAll('.concepto-row').forEach(restaurarPrecioLista);
      document.querySelectorAll('.concepto-cupon').forEach(i => { i.value = ''; });
      document.querySelectorAll('.concepto-cupon-msg')
        .forEach(p => p.classList.add('hidden'));
    }
    updateTotal();
  }

  // Valida el código contra el servidor al perder el foco. NO es la autoridad
  // (el servidor revalida y recalcula todo al guardar); esto sólo le da
  // retroalimentación inmediata a quien captura, igual que en /edr/ingresos.
  async function validarCuponConcepto(row) {
    const msg = row.querySelector('.concepto-cupon-msg');
    const codigo = row.querySelector('.concepto-cupon').value.trim();
    const tratId = Number(row.querySelector('.concepto-tratamiento').value) || null;
    const precioInput = row.querySelector('.concepto-precio');
    msg.classList.add('hidden');
    if (!codigo) {
      // Se borró el código: el renglón vuelve a su precio de lista (si tenía
      // uno guardado de un cupón anterior) antes de perder el rastro del
      // cupón. Dejar el neto ya descontado en el input lo convertiría en el
      // precio "normal" del concepto sin ningún cupón asociado.
      restaurarPrecioLista(row);
      updateTotal();
      return;
    }
    // Todo cupón está atado a un tratamiento (validar_cupon en
    // ajustes/services.py rechaza sin tratamiento_id), así que un concepto
    // libre nunca puede canjear uno. Se avisa aquí en vez de llamar al
    // endpoint, que además requiere tratamiento_id (ValidarCuponSchema).
    if (!tratId) {
      restaurarPrecioLista(row);
      msg.textContent = 'Elige un tratamiento del catálogo para usar un cupón';
      msg.className = 'concepto-cupon-msg text-xs mt-1 text-danger-600';
      msg.classList.remove('hidden');
      updateTotal();
      return;
    }

    // Guardamos el precio de LISTA en el dataset: el input muestra el neto,
    // pero el payload tiene que mandar el de lista (el servidor aplica el
    // cupón). Sin esto, revalidar dos veces descontaría dos veces.
    const lista = Number(row.dataset.precioLista || precioInput.value) || 0;
    try {
      const r = await API.post('/ajustes/cupones/validar', {
        codigo, tratamiento_id: tratId,
        // Contra la fecha de LA COTIZACIÓN, no la de hoy (regla del diseño;
        // el servidor valida contra `cot.fecha`). Una nueva sin fecha
        // asignada todavía cae en hoy como fallback razonable.
        fecha: state.fecha || new Date().toISOString().slice(0, 10),
        precio: lista,
      });
      row.dataset.precioLista = String(lista);
      precioInput.value = Number(r.monto).toFixed(2);
      msg.textContent = `−${fmt(r.descuento_monto)} por unidad`;
      msg.className = 'concepto-cupon-msg text-xs mt-1 text-accent-700';
      msg.classList.remove('hidden');
    } catch (err) {
      // Cupón inválido: la línea no puede quedarse con el neto de un cupón
      // que ya no aplica (o de uno anterior). El dataset todavía trae el
      // precio de lista de antes de este intento (no se toca hasta que la
      // validación es exitosa), así que restaurarPrecioLista basta; el
      // mensaje de error ya explica por qué.
      restaurarPrecioLista(row);
      msg.textContent = (err && err.message) || 'Cupón inválido';
      msg.className = 'concepto-cupon-msg text-xs mt-1 text-danger-600';
      msg.classList.remove('hidden');
    }
    updateTotal();
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
    state.fecha = null;
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
    // Una cotización nueva siempre arranca en modo Descuento y sin candado:
    // el candado sólo se activa al reabrir una ya no editable (ver open()).
    state.cuponBloqueado = false;
    document.querySelectorAll('.cot-modo').forEach(b => { b.disabled = false; });
    aplicarModo('descuento');
    addConcept();
  }

  async function open(quote = null) {
    try {
      await loadCatalogs();
      reset();
      state.id = quote && quote.id;
      state.fecha = quote ? quote.fecha : null;
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
        // Sólo se puede editar una cotización en borrador o enviada
        // (actualizar_cotizacion en cobranza/services.py rechaza el resto); el
        // botón "Editar" de cotizaciones.js ya filtra por esos estatus, pero
        // se deshabilita aquí también por si open() se llama directo.
        state.cuponBloqueado = !['borrador', 'enviada'].includes(quote.estatus);
        document.querySelectorAll('.cot-modo').forEach(b => { b.disabled = state.cuponBloqueado; });
        // El modo se deduce de los datos: si algún concepto trae cupón, la
        // cotización se armó en modo cupón. Se hace antes de crear los
        // renglones para que addConcept los pinte ya con la visibilidad correcta.
        const conCupon = (quote.conceptos || []).some(c => c.cupon_id);
        aplicarModo(conCupon ? 'cupon' : 'descuento');
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
    document.querySelectorAll('.cot-modo').forEach(
      b => b.addEventListener('click', () => aplicarModo(b.dataset.modo)),
    );
    ['cot-descuento-tipo', 'cot-descuento-valor', 'cot-anticipo'].forEach(
      id => $(id).addEventListener('input', updateTotal),
    );
    setupPacienteCombobox();
    setupDoctorCombobox();
  }

  return { init, open, loadCatalogs, specialists: () => state.especialistas };
})();

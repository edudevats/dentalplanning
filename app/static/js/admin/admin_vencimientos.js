// Panel super-admin / Vencimientos de clínicas que pagan por transferencia
(function () {
  const { currency, formatDate, confirmAction, kpiCard } = window.adminUI;

  const CANAL_LABEL = { email: 'Correo', whatsapp: 'WhatsApp' };

  function btn(label, icon, cls, onClick, disabledTitle) {
    const b = document.createElement('button');
    b.className = `inline-flex items-center gap-1 px-2.5 py-1.5 rounded-md text-xs font-semibold transition-colors cursor-pointer ${cls}`;
    const i = document.createElement('i');
    i.setAttribute('data-lucide', icon);
    i.className = 'h-3.5 w-3.5';
    b.appendChild(i);
    b.appendChild(document.createTextNode(label));
    if (disabledTitle) {
      b.disabled = true;
      b.title = disabledTitle;
      b.classList.add('opacity-50', 'cursor-not-allowed');
    } else {
      b.addEventListener('click', onClick);
    }
    return b;
  }

  function textoDias(dias) {
    if (dias < 0) return `${-dias} día${dias === -1 ? '' : 's'} de atraso`;
    if (dias === 0) return 'Vence hoy';
    return `En ${dias} día${dias === 1 ? '' : 's'}`;
  }

  function textoUltimo(u) {
    if (!u) return 'Sin avisos';
    const quien = u.origen === 'auto' ? 'auto' : 'manual';
    return `${CANAL_LABEL[u.canal] || u.canal} (${quien}) · ${formatDate(u.fecha)}`;
  }

  async function onWhatsapp(fila) {
    // Abrimos la pestaña antes del await: los navegadores bloquean window.open
    // si no ocurre en el mismo tick del click.
    const win = window.open('', '_blank');
    if (win) win.opener = null;
    let ok = false;
    try {
      const { url } = await adminApi.post(`/vencimientos/${fila.subscription_id}/whatsapp`, {});
      if (win) {
        win.location.href = url;
      } else if (!window.open(url, '_blank')) {
        Toast.show('Permite ventanas emergentes para abrir WhatsApp', 'warning');
      }
      ok = true;
    } catch (err) {
      if (win) win.close();
      Toast.show(err.message || 'No se pudo abrir WhatsApp', 'error');
    }
    if (ok) {
      try { await load(); } catch (err) { Toast.show(err.message || 'Error al cargar', 'error'); }
    }
  }

  async function onCorreo(fila, boton) {
    const ok = await confirmAction({
      title: `Enviar recordatorio — ${fila.tenant_name}`,
      message: `Se enviará un correo a ${fila.contact_email || 'los administradores de la clínica'}.`,
      confirmLabel: 'Enviar correo',
    });
    if (!ok) return;
    if (boton) boton.disabled = true;
    try {
      await adminApi.post(`/vencimientos/${fila.subscription_id}/correo`, {});
      Toast.show('Recordatorio enviado', 'success');
      await load();
    } catch (err) {
      Toast.show(err.message || 'No se pudo enviar el correo', 'error');
    } finally {
      if (boton && boton.isConnected) boton.disabled = false;
    }
  }

  function renderGrupo(containerId, filas, vencido) {
    const cont = document.getElementById(containerId);
    invDom.clearChildren(cont);
    if (!filas.length) {
      const p = document.createElement('p');
      p.className = 'text-sm text-cs-on-surface-var py-2';
      p.textContent = 'Nadie en este grupo.';
      cont.appendChild(p);
      return;
    }
    const wrap = document.createElement('div');
    wrap.className = 'overflow-x-auto';
    const t = document.createElement('table');
    t.className = 'w-full min-w-[900px] text-sm';
    const head = document.createElement('thead');
    const hr = document.createElement('tr');
    hr.className = 'text-left text-cs-on-surface-var';
    ['Clínica', 'Plan', 'Monto', 'Cobro', 'Contacto', 'Último aviso', ''].forEach(h => {
      const th = document.createElement('th');
      th.className = 'px-3 py-2 font-semibold whitespace-nowrap';
      th.textContent = h;
      hr.appendChild(th);
    });
    head.appendChild(hr);
    t.appendChild(head);
    const tb = document.createElement('tbody');
    filas.forEach(f => {
      const tr = document.createElement('tr');
      tr.className = 'border-t border-cs-surface-container';

      const tdN = document.createElement('td');
      tdN.className = 'px-3 py-2.5';
      const a = document.createElement('a');
      a.href = `/admin/tenants/${f.tenant_id}`;
      a.className = 'font-semibold text-cs-on-surface hover:underline';
      a.textContent = f.tenant_name;
      tdN.appendChild(a);

      const tdPlan = document.createElement('td');
      tdPlan.className = 'px-3 py-2.5 text-cs-on-surface-var';
      tdPlan.textContent = f.plan || '—';

      const tdM = document.createElement('td');
      tdM.className = 'px-3 py-2.5 font-semibold text-cs-on-surface whitespace-nowrap';
      tdM.textContent = currency(f.monto);

      const tdC = document.createElement('td');
      tdC.className = 'px-3 py-2.5 whitespace-nowrap';
      const fecha = document.createElement('p');
      fecha.className = 'text-cs-on-surface';
      fecha.textContent = formatDate(f.proximo_cobro);
      const dias = document.createElement('p');
      dias.className = `text-xs font-semibold ${vencido ? 'text-cs-error' : 'text-cs-on-surface-var'}`;
      dias.textContent = textoDias(f.dias);
      tdC.appendChild(fecha);
      tdC.appendChild(dias);

      const tdCt = document.createElement('td');
      tdCt.className = 'px-3 py-2.5 text-xs text-cs-on-surface-var';
      const tel = document.createElement('p');
      tel.textContent = f.contact_phone || 'Sin teléfono';
      const mail = document.createElement('p');
      mail.textContent = f.contact_email || 'Sin correo';
      tdCt.appendChild(tel);
      tdCt.appendChild(mail);

      const tdU = document.createElement('td');
      tdU.className = 'px-3 py-2.5 text-xs text-cs-on-surface-var whitespace-nowrap';
      tdU.textContent = textoUltimo(f.ultimo_recordatorio);

      const tdA = document.createElement('td');
      tdA.className = 'px-3 py-2.5';
      const acc = document.createElement('div');
      acc.className = 'flex items-center gap-1.5 justify-end';
      acc.appendChild(btn('WhatsApp', 'message-circle',
        'bg-green-600 text-white hover:bg-green-700', () => onWhatsapp(f),
        f.contact_phone ? null : 'Agrega el teléfono en la pestaña General'));
      const btnCorreo = btn('Correo', 'mail',
        'bg-cs-surface-container text-cs-on-surface hover:bg-cs-surface-container-high',
        () => onCorreo(f, btnCorreo));
      acc.appendChild(btnCorreo);
      const pago = document.createElement('a');
      pago.href = `/admin/tenants/${f.tenant_id}?tab=billing`;
      pago.className = 'inline-flex items-center gap-1 px-2.5 py-1.5 rounded-md text-xs font-semibold bg-cs-primary-container text-cs-on-primary-container hover:opacity-90';
      pago.textContent = 'Registrar pago';
      acc.appendChild(pago);
      tdA.appendChild(acc);

      [tdN, tdPlan, tdM, tdC, tdCt, tdU, tdA].forEach(td => tr.appendChild(td));
      tb.appendChild(tr);
    });
    t.appendChild(tb);
    wrap.appendChild(t);
    cont.appendChild(wrap);
  }

  function renderKpis(data) {
    const grid = document.getElementById('kpis');
    invDom.clearChildren(grid);
    grid.appendChild(kpiCard({
      label: 'Vencidos', value: data.vencidos.length, icon: 'alert-octagon',
      hint: currency(data.vencidos.reduce((s, f) => s + f.monto, 0)),
    }));
    grid.appendChild(kpiCard({
      label: 'Vencen en 7 días', value: data.semana.length, icon: 'calendar-clock',
      hint: currency(data.semana.reduce((s, f) => s + f.monto, 0)),
    }));
    grid.appendChild(kpiCard({
      label: 'Por cobrar', value: currency(data.resumen.monto), icon: 'wallet',
      hint: `${data.resumen.por_cobrar} clínicas`,
    }));
  }

  async function load() {
    const data = await adminApi.get('/vencimientos');
    document.getElementById('aviso-bancarios').classList.toggle('hidden', data.bancarios_configurados);
    renderKpis(data);
    renderGrupo('grupo-vencidos', data.vencidos, true);
    renderGrupo('grupo-semana', data.semana, false);
    renderGrupo('grupo-mes', data.mes, false);
    if (typeof lucide !== 'undefined') lucide.createIcons();
  }

  async function onEnviarPendientes() {
    const boton = document.getElementById('btn-enviar-pendientes');
    const ok = await confirmAction({
      title: 'Enviar recordatorios pendientes',
      message: 'Se enviarán los correos de 3 días antes y 2 días después que aún no hayan salido. No se repite ningún aviso ya enviado.',
      confirmLabel: 'Enviar',
    });
    if (!ok) return;
    boton.disabled = true;
    try {
      const r = await adminApi.post('/vencimientos/enviar-pendientes', {});
      const enviados = `${r.enviados} ${r.enviados === 1 ? 'correo enviado' : 'correos enviados'}`;
      const omitidos = `${r.omitidos} ${r.omitidos === 1 ? 'omitido' : 'omitidos'}`;
      Toast.show(`${enviados}, ${omitidos}`, r.omitidos ? 'warning' : 'success');
      await load();
    } catch (err) {
      Toast.show(err.message || 'Error al enviar', 'error');
    } finally {
      boton.disabled = false;
    }
  }

  document.getElementById('btn-enviar-pendientes').addEventListener('click', onEnviarPendientes);
  load().catch(err => Toast.show(err.message || 'Error al cargar', 'error'));
})();

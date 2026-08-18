// Panel super-admin / Asientos de recepcionista (compartido)
// Lo usan el detalle de clínica y la bandeja /admin/solicitudes.
(function () {
  const { statusBadge, currency, formatDate, confirmAction, openModal,
          buildField, textareaEl } = window.adminUI;

  function actionBtn(label, onClick, destructive) {
    const b = document.createElement('button');
    b.type = 'button';
    b.className = 'px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors cursor-pointer '
      + (destructive ? 'bg-cs-error-container/40 text-cs-on-error-container hover:opacity-90'
                     : 'bg-cs-surface-container text-cs-on-surface hover:bg-cs-surface-container-high');
    b.textContent = label;
    b.addEventListener('click', onClick);
    return b;
  }

  async function aprobar(id, onChange) {
    const ok = await confirmAction({ title: 'Aprobar asiento',
      message: 'Se aprobará el asiento; el tenant podrá pagarlo.', confirmLabel: 'Aprobar' });
    if (!ok) return;
    await adminApi.post(`/asientos/${id}/aprobar`, {});
    onChange();
  }

  function rechazar(id, onChange) {
    const ta = textareaEl('motivo', '', 3);
    openModal({
      title: 'Rechazar asiento',
      content: buildField('Motivo', ta),
      primary: { label: 'Rechazar', onClick: async () => {
        const motivo = ta.value.trim();
        if (motivo.length < 3) throw new Error('Escribe un motivo');
        await adminApi.post(`/asientos/${id}/rechazar`, { motivo });
        onChange();
      }},
    });
  }

  async function pagoManual(id, onChange) {
    const ok = await confirmAction({ title: 'Registrar pago manual',
      message: 'Registra un pago por transferencia y activa el asiento.', confirmLabel: 'Activar' });
    if (!ok) return;
    await adminApi.post(`/asientos/${id}/activar-manual`, {});
    onChange();
  }

  async function cancelar(id, onChange) {
    const ok = await confirmAction({ title: 'Cancelar asiento',
      message: 'Cancela la suscripción en Clip (irreversible) y el recepcionista pierde acceso.',
      confirmLabel: 'Cancelar asiento', destructive: true });
    if (!ok) return;
    await adminApi.post(`/asientos/${id}/cancelar`, {});
    onChange();
  }

  function renderRow(a, { onChange, showTenant = false } = {}) {
    const avisar = typeof onChange === 'function' ? onChange : () => {};

    const row = document.createElement('div');
    row.className = 'flex items-center gap-3 py-2 border-b border-cs-outline-variant/30';

    const info = document.createElement('div');
    info.className = 'flex-1 min-w-0 flex items-center gap-2 flex-wrap';

    if (showTenant) {
      const link = document.createElement('a');
      link.href = `/admin/tenants/${a.tenant_id}`;
      link.className = 'text-sm font-semibold text-cs-primary hover:underline';
      link.textContent = a.tenant_name || '—';
      info.appendChild(link);
    }

    const txt = document.createElement('span');
    txt.className = 'text-sm text-cs-on-surface';
    txt.textContent = `Asiento #${a.id}`
      + (a.monto != null ? ` · ${currency(a.monto)}` : '')
      + (a.usuario_email ? ` · ${a.usuario_email}` : '');
    info.appendChild(txt);
    info.appendChild(statusBadge(a.estado));

    // Tipo de asiento: distingue el add-on de recepcionista del de asistente.
    const ETIQUETA_ASIENTO = {
      recepcionista: 'Recepcionista',
      asistente: 'Asistente dental',
    };
    const rolBadge = document.createElement('span');
    rolBadge.className =
      'inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold '
      + 'bg-cs-surface-container-high text-cs-on-surface-var';
    rolBadge.textContent = ETIQUETA_ASIENTO[a.rol] || a.rol || 'Recepcionista';
    info.appendChild(rolBadge);

    if (showTenant && a.created_at) {
      const fecha = document.createElement('span');
      fecha.className = 'text-xs text-cs-on-surface-var';
      fecha.textContent = formatDate(a.created_at);
      info.appendChild(fecha);
    }

    row.appendChild(info);

    const actions = document.createElement('div');
    actions.className = 'flex items-center gap-2 shrink-0';
    if (a.estado === 'pendiente') {
      actions.appendChild(actionBtn('Aprobar', () => aprobar(a.id, avisar)));
      actions.appendChild(actionBtn('Rechazar', () => rechazar(a.id, avisar), true));
    } else if (a.estado === 'aprobada') {
      actions.appendChild(actionBtn('Pago manual', () => pagoManual(a.id, avisar)));
      actions.appendChild(actionBtn('Cancelar', () => cancelar(a.id, avisar), true));
    } else if (a.estado === 'activa') {
      actions.appendChild(actionBtn('Cancelar', () => cancelar(a.id, avisar), true));
    }
    row.appendChild(actions);

    return row;
  }

  window.adminAsientos = { renderRow };
})();

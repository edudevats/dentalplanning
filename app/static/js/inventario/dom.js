function setText(sel, value) {
  const el = typeof sel === "string" ? document.querySelector(sel) : sel;
  if (el) el.textContent = value == null ? "" : String(value);
}

function addCell(tr, value) {
  const td = document.createElement("td");
  td.textContent = value == null ? "" : String(value);
  tr.appendChild(td);
  return td;
}

function addCellNode(tr, node) {
  const td = document.createElement("td");
  td.appendChild(node);
  tr.appendChild(td);
  return td;
}

function buildRow(values) {
  const tr = document.createElement("tr");
  values.forEach(v => addCell(tr, v));
  return tr;
}

function clearChildren(el) {
  while (el.firstChild) el.removeChild(el.firstChild);
}

function makeOption(value, label) {
  const o = document.createElement("option");
  o.value = value == null ? "" : String(value);
  o.textContent = label;
  return o;
}

function makeLink(href, label) {
  const a = document.createElement("a");
  a.href = href;
  a.textContent = label;
  return a;
}

window.invDom = {
  setText, addCell, addCellNode, buildRow, clearChildren,
  makeOption, makeLink,
};

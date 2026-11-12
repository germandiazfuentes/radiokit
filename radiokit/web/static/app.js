"use strict";
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
let WS = { open: false };
let editing = null;

// ---------- utilidades ----------
async function api(method, path, body) {
  const r = await fetch(path, {
    method, headers: { "Content-Type": "application/json", "X-Radiokit": "1" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const ct = r.headers.get("Content-Type") || "";
  const data = ct.includes("json") ? await r.json() : await r.text();
  if (!r.ok) { const e = new Error(data.error || r.statusText); e.details = data.details; throw e; }
  return data;
}
function toast(msg) { const t = $("#toast"); t.textContent = msg; t.classList.add("show"); clearTimeout(t._h); t._h = setTimeout(() => t.classList.remove("show"), 3500); }
const mhz = (hz) => (hz / 1e6).toFixed(5);
const toHz = (s) => Math.round(parseFloat(String(s).replace(",", ".")) * 1e6);
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const port = () => $("#port").value;

// ---------- pestanas ----------
$$(".tabs button").forEach((b) => b.addEventListener("click", () => {
  $$(".tabs button").forEach((x) => x.classList.toggle("active", x === b));
  $$(".tab").forEach((t) => t.classList.toggle("active", t.id === "tab-" + b.dataset.tab));
  if (b.dataset.tab === "backups") loadBackups();
  if (b.dataset.tab === "radios") loadDrivers();
}));

// ---------- puertos ----------
async function loadPorts() {
  const ports = await api("GET", "/api/ports");
  const sel = $("#port"), prev = sel.value || localStorage.getItem("radiokit.port");
  sel.innerHTML = ports.map((p) => `<option value="${esc(p.port)}">${esc(p.port)} — ${esc(p.device)}</option>`).join("")
    || '<option value="">(sin puertos)</option>';
  if (prev && ports.some((p) => p.port === prev)) sel.value = prev;
}
$("#port").addEventListener("change", () => { try { localStorage.setItem("radiokit.port", port()); } catch (e) {} });
$("#btnPorts").addEventListener("click", loadPorts);

// ---------- tareas ----------
function runJob(job, title) {
  return new Promise((resolve) => {
    const dlg = $("#dlgJob");
    $("#jobTitle").textContent = title; $("#jobLog").textContent = ""; $("#jobMsg").textContent = "";
    $("#jobBar").style.width = "0"; $("#jobClose").disabled = true;
    dlg.showModal();
    const tick = async () => {
      const j = await api("GET", "/api/jobs/" + job.id);
      $("#jobBar").style.width = Math.round(100 * j.done / Math.max(j.total, 1)) + "%";
      $("#jobMsg").textContent = j.msg;
      $("#jobLog").textContent = j.log.join("\n") + (j.error ? "\n\nERROR: " + j.error : "");
      $("#jobLog").scrollTop = 1e9;
      if (j.status === "running") return setTimeout(tick, 400);
      $("#jobTitle").textContent = j.status === "ok" ? title + " — completado" : title + " — error";
      $("#jobClose").disabled = false;
      $("#jobClose").onclick = () => { dlg.close(); resolve(j); };
    };
    tick();
  });
}

$("#btnRead").addEventListener("click", async () => {
  if (!port()) return toast("Elige el puerto del cable");
  try {
    const j = await runJob(await api("POST", "/api/read", { port: port(), driver_id: $("#model").value }), "Leyendo la radio");
    if (j.status === "ok") { await refresh(); toast("Radio leida y copia guardada"); }
  } catch (e) { toast(e.message); }
});

// ---------- espacio de trabajo ----------
async function refresh() { WS = await api("GET", "/api/workspace"); render(); }

function render() {
  $("#source").textContent = WS.open ? WS.source : "Sin radio abierta";
  $("#emptyMsg").classList.toggle("hidden", WS.open);
  if (!WS.open) { $("#chTable tbody").innerHTML = ""; $("#changes").classList.add("hidden"); return; }
  const d = WS.driver, inf = WS.info || {};
  $("#radioInfo").innerHTML = `<b>${esc(d.vendor)} ${esc(d.model)}</b> · firmware ${esc(inf.firmware || WS.meta.firmware || "?")}`
    + (d.experimental ? ' · <span class="chip service">experimental: solo lectura</span>' : "");
  if (!WS.channels.length) {
    $("#emptyMsg").classList.remove("hidden");
    $("#emptyMsg").textContent = `Copia de seguridad completa guardada. ${d.notes}`;
  } else {
    $("#emptyMsg").textContent = "Lee una radio o abre una copia para empezar.";
  }
  renderChannels(); renderSettings(); renderMemory(); renderChanges();
}

function chipTone(t) { return t ? esc(t.startsWith("D") ? t : t + " Hz") : "—"; }

function renderChannels() {
  const showEmpty = $("#showEmpty").checked, f = $("#filter").value.trim().toLowerCase();
  const changed = new Set(WS.plan ? WS.plan.channels : []);
  const rows = WS.channels.filter((c) => {
    if (c.empty && !showEmpty) return false;
    if (!f) return true;
    return (c.name || "").toLowerCase().includes(f) || (!c.empty && mhz(c.rx_freq).includes(f)) || String(c.number) === f;
  }).map((c) => {
    const cls = [changed.has(c.number) ? "changed" : "", c.empty ? "isempty" : ""].join(" ");
    if (c.empty) return `<tr class="${cls}" data-n="${c.number}"><td class="num">${c.number}</td><td colspan="9">vacio — pulsa para crear</td></tr>`;
    const tx = c.tx_freq === null ? '<span class="chip rxonly">solo escucha</span>'
      : c.duplex === "" ? "=" : `${c.duplex} ${mhz(c.tx_freq)}`;
    const pmr = c.pmr446 ? `PMR ${c.pmr446}${c.pmr_subtone ? " · sub " + c.pmr_subtone : ""}` : "";
    return `<tr class="${cls}" data-n="${c.number}"><td class="num">${c.number}</td><td>${esc(c.name)}</td>
      <td class="num">${mhz(c.rx_freq)}</td><td class="num">${tx}</td><td>${chipTone(c.tx_tone)}</td><td>${chipTone(c.rx_tone)}</td>
      <td>${esc(c.power)}</td><td>${esc(c.bandwidth)}</td><td>${c.scan ? "si" : "no"}</td><td>${pmr}</td></tr>`;
  });
  $("#chTable tbody").innerHTML = rows.join("");
}
$("#showEmpty").addEventListener("change", renderChannels);
$("#filter").addEventListener("input", renderChannels);
$("#chTable tbody").addEventListener("click", (e) => {
  const tr = e.target.closest("tr[data-n]"); if (tr) openChannel(+tr.dataset.n);
});

// ---------- editor de canal ----------
function toneOptions() {
  const caps = WS.capabilities, sub = WS.pmr_subtones;
  let h = '<option value="">Ninguno</option><optgroup label="CTCSS (subtono analogico)">';
  for (const t of caps.ctcss) {
    const i = sub.indexOf(t);
    h += `<option value="${t.toFixed(1)}">${t.toFixed(1)} Hz${i >= 0 ? " — PMR sub " + (i + 1) : ""}</option>`;
  }
  h += '</optgroup><optgroup label="DCS normal">' + caps.dcs.map((c) => `<option value="D${String(c).padStart(3, "0")}N">D${String(c).padStart(3, "0")}N</option>`).join("");
  h += '</optgroup><optgroup label="DCS invertido">' + caps.dcs.map((c) => `<option value="D${String(c).padStart(3, "0")}I">D${String(c).padStart(3, "0")}I</option>`).join("");
  return h + "</optgroup>";
}

function openChannel(n) {
  const c = WS.channels.find((x) => x.number === n), F = $("#chForm"), caps = WS.capabilities;
  editing = c;
  $("#chTitle").textContent = c.empty ? `Nuevo canal ${n}` : `Canal ${n}`;
  F.tx_tone.innerHTML = F.rx_tone.innerHTML = toneOptions();
  F.power.innerHTML = caps.power_levels.map((p) => `<option>${esc(p)}</option>`).join("");
  F.pttid.innerHTML = caps.pttid.map((p) => `<option>${esc(p)}</option>`).join("");
  F.chname.maxLength = caps.name_length;
  F.chname.value = c.name || "";
  F.rx.value = c.empty ? "" : mhz(c.rx_freq);
  F.txmode.value = c.empty ? "same" : (c.tx_freq === null ? "off" : c.duplex === "" ? "same" : c.duplex === "+" || c.duplex === "-" ? (Math.abs(c.tx_freq - c.rx_freq) > 70e6 ? "split" : c.duplex) : "same");
  F.tx.value = c.empty || c.tx_freq === null ? "" : (F.txmode.value === "split" ? mhz(c.tx_freq) : (Math.abs(c.tx_freq - c.rx_freq) / 1e6).toFixed(5));
  F.tx_tone.value = c.tx_tone || ""; F.rx_tone.value = c.rx_tone || "";
  F.power.value = c.empty ? caps.power_levels[0] : c.power;
  F.bandwidth.value = c.empty ? "Narrow" : c.bandwidth;
  F.pttid.value = c.pttid || "Off";
  F.scan.checked = c.empty ? true : c.scan; F.bcl.checked = !!c.bcl;
  $("#chDelete").classList.toggle("hidden", c.empty);
  $("#chErrors").innerHTML = "";
  updateTxField(); updateHint();
  $("#dlgChannel").showModal();
}
function updateTxField() {
  const m = $("#chForm").txmode.value;
  $("#txLabel").classList.toggle("hidden", m === "same" || m === "off");
  $("#txLabel").firstChild.textContent = m === "split" ? "TX (MHz) " : "Desplazamiento (MHz) ";
}
function updateHint() {
  const F = $("#chForm"), hz = toHz(F.rx.value);
  const pmr = Math.round((hz - 446006250) / 12500);
  let h = "";
  if (hz >= 446000000 && hz <= 446200000 && Math.abs(446006250 + pmr * 12500 - hz) < 10)
    h = `PMR446 canal ${pmr + 1}. Recomendado: Narrow, potencia baja. ` + (F.tx_tone.value ? "" : "Sin subtono escuchara a todos los del canal.");
  if (F.txmode.value === "off") h += " Este canal no podra transmitir.";
  $("#chHint").textContent = h;
}
["txmode", "rx", "tx_tone"].forEach((n) => $("#chForm")[n].addEventListener("input", () => { updateTxField(); updateHint(); }));
$("#chForm").tx_tone.addEventListener("change", () => {      // por defecto, mismo tono en RX (TSQL)
  const F = $("#chForm"); if (!F.rx_tone.value) F.rx_tone.value = F.tx_tone.value; updateHint();
});

$("#chForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const action = e.submitter && e.submitter.value, F = $("#chForm");
  if (action === "cancel") return $("#dlgChannel").close();
  let ch;
  if (action === "delete") {
    if (!confirm(`¿Borrar el canal ${editing.number}?`)) return;
    ch = { number: editing.number, empty: true };
  } else {
    const rx = toHz(F.rx.value), m = F.txmode.value, txv = toHz(F.tx.value || "0");
    let tx = rx;
    if (m === "off") tx = null; else if (m === "+") tx = rx + txv; else if (m === "-") tx = rx - txv; else if (m === "split") tx = txv;
    ch = { ...editing, empty: false, name: F.chname.value.toUpperCase(), rx_freq: rx, tx_freq: tx,
      tx_tone: F.tx_tone.value || null, rx_tone: F.rx_tone.value || null, power: F.power.value,
      bandwidth: F.bandwidth.value, pttid: F.pttid.value, scan: F.scan.checked, bcl: F.bcl.checked };
    for (const k of ["duplex", "pmr446", "pmr_subtone"]) delete ch[k];
  }
  try {
    WS = await api("PUT", "/api/channel", ch); render(); $("#dlgChannel").close();
    toast("Cambio guardado en el borrador (aun no esta en la radio)");
  } catch (err) {
    $("#chErrors").innerHTML = (err.details || [err.message]).map((x) => `<li>${esc(x)}</li>`).join("");
  }
});

// ---------- ajustes ----------
function renderSettings() {
  const adv = $("#showAdvanced").checked, changed = new Set(WS.plan ? WS.plan.settings : []);
  const groups = {};
  for (const s of WS.settings) if (adv || !s.advanced) (groups[s.group] ||= []).push(s);
  $("#settingsGrid").innerHTML = Object.entries(groups).map(([g, list]) => `<div class="card"><h3>${esc(g)}</h3>${
    list.map((s) => {
      let ctl;
      if (s.kind === "list") ctl = `<select data-k="${s.key}">${s.options.map((o) => `<option ${o === s.value ? "selected" : ""}>${esc(o)}</option>`).join("")}</select>`;
      else if (s.kind === "bool") ctl = `<input type="checkbox" data-k="${s.key}" ${s.value ? "checked" : ""}>`;
      else if (s.kind === "text") ctl = `<input data-k="${s.key}" maxlength="${s.width}" value="${esc(s.value)}">`;
      else if (s.kind === "freq_fm") ctl = `<input data-k="${s.key}" inputmode="decimal" value="${s.value ?? ""}">`;
      else ctl = `<input data-k="${s.key}" type="number" min="${s.min}" max="${s.max}" value="${s.value}">`;
      return `<div class="setting ${changed.has(s.key) ? "changed" : ""}" title="${esc(s.help)}"><div class="lbl">${esc(s.label)}
        <small>${esc(s.menu ? "Menu " + s.menu : "")}${s.help ? " · " + esc(s.help) : ""}</small></div>${ctl}</div>`;
    }).join("")}</div>`).join("");
}
$("#showAdvanced").addEventListener("change", renderSettings);
$("#settingsGrid").addEventListener("change", async (e) => {
  const el = e.target.closest("[data-k]"); if (!el) return;
  const value = el.type === "checkbox" ? el.checked : el.value;
  try { WS = await api("POST", "/api/setting", { key: el.dataset.k, value }); render(); }
  catch (err) { toast(err.message); renderSettings(); }
});

// ---------- memoria ----------
function renderMemory() {
  const d = WS.driver, w = d.writable.map(([s, e]) => [parseInt(s, 16), parseInt(e, 16)]);
  const names = { user: "usuario", settings: "ajustes", service: "servicio", unknown: "desconocido" };
  $("#memTable tbody").innerHTML = d.regions.map(([s, e, n, k]) => {
    const a = parseInt(s, 16), b = parseInt(e, 16), ok = w.some(([x, y]) => x <= a && b <= y);
    return `<tr><td class="num">${s}</td><td class="num">${e}</td><td>${esc(n)}</td><td><span class="chip ${k}">${names[k] || k}</span></td><td>${ok ? "si" : "protegida"}</td></tr>`;
  }).join("");
  $("#infoBox").innerHTML = `<h3>Datos de la radio</h3><pre>${esc(JSON.stringify({ ...WS.info, ...WS.meta }, null, 2))}</pre>`;
}

// ---------- cambios pendientes ----------
function renderChanges() {
  const p = WS.plan, bar = $("#changes");
  if (WS.plan_error) { bar.classList.remove("hidden"); $("#changesText").textContent = "⚠ " + WS.plan_error; $("#btnWrite").disabled = true; return; }
  const n = p ? p.blocks.length : 0;
  bar.classList.toggle("hidden", n === 0);
  $("#btnWrite").disabled = n === 0;
  if (n) $("#changesText").innerHTML = `<b>Borrador con cambios:</b> ${p.channels.length} canal(es), ${p.settings.length} ajuste(s) · ${n} bloque(s) de memoria`;
}
$("#btnRevert").addEventListener("click", async () => {
  if (!confirm("¿Descartar todos los cambios del borrador?")) return;
  WS = await api("POST", "/api/revert"); render();
});

$("#btnWrite").addEventListener("click", () => {
  const p = WS.plan, set = WS.settings.filter((s) => p.settings.includes(s.key));
  $("#planBox").innerHTML = `<p>Se escribiran <b>${p.blocks.length}</b> bloques en: ${esc(p.regions.join(", "))}.</p>
    ${p.channels.length ? `<div>Canales: <b>${p.channels.join(", ")}</b></div>` : ""}
    ${set.length ? `<div>Ajustes:</div><ul>${set.map((s) => `<li>${esc(s.label)} → <b>${esc(s.value)}</b></li>`).join("")}</ul>` : ""}`;
  $("#writePort").textContent = port() || "(elige puerto)";
  $("#confirmWrite").checked = false; $("#btnDoWrite").disabled = true;
  $("#dlgWrite").showModal();
});
$("#confirmWrite").addEventListener("change", (e) => { $("#btnDoWrite").disabled = !e.target.checked || !port(); });
$("#dlgWrite").addEventListener("close", async () => {
  const v = $("#dlgWrite").returnValue;
  if (v !== "dry" && v !== "write") return;
  if (!port()) return toast("Elige el puerto");
  try {
    const job = await api("POST", "/api/write", { port: port(), dry_run: v === "dry", confirm: v === "write" });
    const j = await runJob(job, v === "dry" ? "Ensayo de escritura" : "Escribiendo en la radio");
    if (j.status === "ok") { await refresh(); toast(v === "dry" ? "Ensayo correcto: la radio coincide, no se ha escrito nada" : "Escrito y verificado"); }
  } catch (e) { toast(e.message); }
});

// ---------- copias y modelos ----------
async function loadBackups() {
  const [list, drv] = await Promise.all([api("GET", "/api/backups"), api("GET", "/api/drivers")]);
  const opts = drv.map((d) => `<option value="${esc(d.id)}">${esc(d.vendor)} ${esc(d.model)}</option>`).join("");
  $("#bkTable tbody").innerHTML = list.map((b) => `<tr><td class="num">${new Date(b.mtime * 1000).toLocaleString()}</td>
    <td>${esc(b.path)}</td><td>${b.model ? esc(b.model) + (b.firmware ? " · " + esc(b.firmware) : "") : `<select data-drv>${opts}</select>`}</td>
    <td><button data-open="${esc(b.path)}" data-id="${esc(b.driver_id || "")}">Abrir</button></td></tr>`).join("");
}
$("#bkTable").addEventListener("click", async (e) => {
  const b = e.target.closest("[data-open]"); if (!b) return;
  const sel = b.closest("tr").querySelector("[data-drv]");
  try {
    WS = await api("POST", "/api/open", { path: b.dataset.open, driver_id: b.dataset.id || (sel && sel.value) });
    render(); $$(".tabs button")[0].click(); toast("Copia abierta como borrador");
  } catch (err) { toast(err.message); }
});
async function loadDrivers() {
  const list = await api("GET", "/api/drivers");
  $("#driverList").innerHTML = list.map((d) => `<div class="card"><h3>${esc(d.vendor)} ${esc(d.model)}</h3>
    <div class="muted">${esc(d.aliases.join(", "))}${d.digital ? ' · <span class="chip settings">DMR</span>' : ""}${d.experimental ? ' · <span class="chip service">experimental</span>' : ""}</div><div>Protocolo: <code>${esc(d.protocol)}</code> · memoria ${d.mem_size} B</div>
    <p class="muted">${esc(d.notes)}</p></div>`).join("");
}

async function loadModels() {
  const list = await api("GET", "/api/drivers");
  $("#model").innerHTML = '<option value="">Autodetectar</option>' + list.map((d) =>
    `<option value="${esc(d.id)}">${esc(d.vendor)} ${esc(d.model)}${d.experimental ? " (experimental)" : ""}</option>`).join("");
}

// ---------- arranque ----------
loadPorts().catch((e) => toast(e.message));
loadModels().catch((e) => toast(e.message));
refresh().catch((e) => toast(e.message));

/* STT Drop — Mini App */
"use strict";

const tg = window.Telegram && window.Telegram.WebApp;
const initData = tg ? (tg.initData || "") : "";

const state = {
  me: null,        // { user_id, username, is_admin }
  products: [],
  product: null,
  selectedSize: null,
  selectedQty: 1,
  photos: [],
};

/* ---------- helpers ---------- */

function $(sel) { return document.querySelector(sel); }
function esc(s) { return String(s == null ? "" : s).replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c])); }
function fmtPrice(p) { p = Number(p || 0); return p > 0 ? p.toLocaleString("ru-RU") + " ₽" : "—"; }

async function api(path, options = {}) {
  const res = await fetch(path, {
    ...options,
    headers: {
      "X-Init-Data": initData,
      ...(options.headers || {}),
    },
  });
  if (res.status === 401) {
    toast("Ошибка авторизации Mini App");
    throw new Error("unauthorized");
  }
  return res.json();
}

let toastTimer;
function toast(text) {
  let t = $(".toast");
  if (!t) { t = document.createElement("div"); t.className = "toast"; document.body.appendChild(t); }
  t.textContent = text;
  t.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.remove("show"), 2200);
}

function stockBadge(total) {
  if (total > 0) return `<span class="stock ok">✅ В наличии: ${total} шт.</span>`;
  return `<span class="stock no">❌ Нет в наличии</span>`;
}

function backButton(cb) {
  if (!tg) return;
  tg.BackButton.show();
  tg.BackButton.onClick(() => {
    tg.BackButton.hide();
    cb();
  });
}

/* ---------- nav ---------- */

function renderNav(active) {
  const tabs = [["catalog", "🛍 Каталог"]];
  tabs.push(["orders", "📦 Мои заказы"]);
  if (state.me && state.me.is_admin) {
    tabs.push(["adminOrders", "🧾 Заказы (админ)"]);
    tabs.push(["adminAdd", "➕ Добавить товар"]);
  }
  return `<div class="nav">${tabs.map(([k, label]) =>
    `<button data-nav="${k}" class="${k === active ? "active" : ""}">${label}</button>`
  ).join("")}</div>`;
}

function bindNav() {
  document.querySelectorAll("[data-nav]").forEach(btn => {
    btn.onclick = () => {
      const k = btn.dataset.nav;
      if (k === "catalog") showCatalog();
      else if (k === "orders") showOrders();
      else if (k === "adminOrders") showAdminOrders();
      else if (k === "adminAdd") showAdminAdd();
    };
  });
}

/* ---------- catalog ---------- */

async function showCatalog() {
  if (tg) { tg.BackButton.hide(); }
  const data = await api("/api/catalog");
  state.products = data.items || [];
  const grid = state.products.map(p => `
    <div class="card" data-id="${p.id}">
      <img src="${esc(p.main_photo) || "/img/placeholder.svg"}" loading="lazy" onerror="this.src='/img/placeholder.svg'" />
      <div class="body">
        <div class="name">${esc(p.name)}</div>
        <div class="price">${fmtPrice(p.price)}</div>
        ${stockBadge(p.total_qty)}
      </div>
    </div>`).join("");
  $("#app").innerHTML = `
    <div class="topbar"><h1>Каталог</h1><button id="refresh">🔄</button></div>
    ${renderNav("catalog")}
    <div class="grid">${grid || '<div class="loader">Товаров пока нет</div>'}</div>`;
  bindNav();
  $("#refresh").onclick = () => showCatalog();
  document.querySelectorAll(".card").forEach(c => {
    c.onclick = () => showProduct(Number(c.dataset.id));
  });
}

/* ---------- product ---------- */

async function showProduct(id) {
  const data = await api(`/api/product/${id}`);
  state.product = data;
  state.photos = [data.main_photo, ...(data.photos || [])].filter(Boolean);
  state.selectedSize = null;

  const sizes = (data.sizes || []).map(s => {
    const dis = s.qty <= 0 ? "disabled" : "";
    return `<div class="size ${dis}" data-size="${esc(s.size)}">${esc(s.size)}<span class="qty">${s.qty} шт.</span></div>`;
  }).join("");

  const thumbs = state.photos.length > 1 ? `
    <div class="thumbs">${state.photos.map((ph, i) =>
      `<img src="${esc(ph)}" data-idx="${i}" class="${i === 0 ? "active" : ""}" onerror="this.style.display='none'"/>`
    ).join("")}</div>` : "";

  $("#app").innerHTML = `
    <div class="topbar"><h1>Товар</h1></div>
    <div class="product">
      <div class="gallery">
        <img class="main-img" id="mainImg" src="${esc(state.photos[0] || "")}" onerror="this.src='/img/placeholder.svg'" />
        ${thumbs}
      </div>
      <div class="p-info">
        <div class="name">${esc(data.name)}</div>
        <div class="price">${fmtPrice(data.price)}</div>
        <div class="desc">${esc(data.description || "")}</div>
      </div>
      <div class="sizes-title">📏 Размеры и наличие</div>
      <div class="sizes">${sizes || '<div class="muted" style="padding:6px 0">Размеры не заданы</div>'}</div>
      <div class="form">
        <button class="btn" id="orderBtn" disabled>Оформить заказ</button>
        ${state.me && state.me.is_admin ? '<button class="btn ghost" id="editStockBtn">⚙️ Изменить остатки</button>' : ""}
      </div>
    </div>`;

  backButton(showCatalog);

  document.querySelectorAll(".thumbs img").forEach(img => {
    img.onclick = () => {
      $("#mainImg").src = img.src;
      document.querySelectorAll(".thumbs img").forEach(x => x.classList.remove("active"));
      img.classList.add("active");
    };
  });

  document.querySelectorAll(".size:not(.disabled)").forEach(s => {
    s.onclick = () => {
      document.querySelectorAll(".size").forEach(x => x.classList.remove("selected"));
      s.classList.add("selected");
      state.selectedSize = s.dataset.size;
      $("#orderBtn").disabled = false;
    };
  });

  $("#orderBtn").onclick = () => openOrderForm();
  const editBtn = $("#editStockBtn");
  if (editBtn) editBtn.onclick = () => openStockModal();
}

/* ---------- order form ---------- */

function openOrderForm() {
  const p = state.product;
  const opts = p.transport_companies.map(c => `<option value="${esc(c)}">${esc(c)}</option>`).join("");
  document.body.insertAdjacentHTML("beforeend", `
    <div class="modal" id="orderModal">
      <div class="sheet">
        <h3>📦 Оформление заказа</h3>
        <p style="color:var(--hint)">${esc(p.name)} · размер <b>${esc(state.selectedSize)}</b></p>
        <div class="field">
          <label>Количество</label>
          <input type="number" id="qty" value="1" min="1" />
        </div>
        <div class="field">
          <label>Транспортная компания</label>
          <select id="transport">
            ${opts}
            <option value="other">Другая…</option>
          </select>
        </div>
        <div class="field hidden" id="customTransportWrap">
          <label>Своя транспортная компания</label>
          <input type="text" id="customTransport" placeholder="Название" />
        </div>
        <div class="field">
          <label>Трек-номер</label>
          <input type="text" id="track" placeholder="Вставьте или впишите трек-номер" />
        </div>
        <button class="btn" id="submitOrder">Отправить заказ</button>
        <button class="btn ghost" id="cancelOrder">Отмена</button>
      </div>
    </div>`);

  const modal = $("#orderModal");
  $("#transport").onchange = (e) => {
    $("#customTransportWrap").classList.toggle("hidden", e.target.value !== "other");
  };
  $("#cancelOrder").onclick = () => modal.remove();
  $("#submitOrder").onclick = async () => {
    const transport = $("#transport").value === "other"
      ? $("#customTransport").value.trim()
      : $("#transport").value;
    const track = $("#track").value.trim();
    const qty = Number($("#qty").value || 1);
    if (!transport) { toast("Укажите транспортную компанию"); return; }
    if (!track) { toast("Укажите трек-номер"); return; }
    const btn = $("#submitOrder"); btn.disabled = true;
    const r = await api("/api/orders", {
      method: "POST", body: JSON.stringify({
        product_id: p.id, size: state.selectedSize, qty, transport_company: transport, track_number: track,
      }),
    });
    if (r.error) { toast(r.error); btn.disabled = false; return; }
    modal.remove();
    toast("✅ Заказ принят");
    showProduct(p.id);
  };
}

/* ---------- orders ---------- */

const STATUS_LABELS = { new: "Новый", confirmed: "Подтверждён", shipped: "Отгружен", done: "Выполнен" };

async function showOrders() {
  if (tg) { tg.BackButton.hide(); }
  const data = await api("/api/orders/mine");
  const items = data.items || [];
  const list = items.map(o => `
    <div class="list-item">
      <div class="row"><span class="ttl">${esc(o.product_name)} · ${esc(o.size)}</span>
        <span class="badge ${esc(o.status)}">${STATUS_LABELS[o.status] || o.status}</span></div>
      <div class="muted">Кол-во: ${o.qty} · ТК: ${esc(o.transport_company)}</div>
      <div class="muted">Трек: <b>${esc(o.track_number)}</b></div>
      <div class="muted">${esc(o.created_at)}</div>
    </div>`).join("");
  $("#app").innerHTML = `
    <div class="topbar"><h1>Мои заказы</h1></div>
    ${renderNav("orders")}
    <div class="list">${list || '<div class="loader">Заказов пока нет</div>'}</div>`;
  bindNav();
}

/* ---------- admin: orders ---------- */

async function showAdminOrders() {
  if (tg) { tg.BackButton.hide(); }
  const data = await api("/api/admin/orders");
  const items = data.items || [];
  const list = items.map(o => `
    <div class="list-item" data-id="${o.id}">
      <div class="row"><span class="ttl">${esc(o.product_name)} · ${esc(o.size)} ×${o.qty}</span>
        <span class="badge ${esc(o.status)}">${STATUS_LABELS[o.status] || o.status}</span></div>
      <div class="muted">Продавец: ${esc(o.seller_username || o.seller_name || o.seller_id)}</div>
      <div class="muted">ТК: ${esc(o.transport_company)} · Трек: <b>${esc(o.track_number)}</b></div>
      <div class="row" style="margin-top:8px">
        ${["confirmed", "shipped", "done"].map(s =>
          `<button class="btn ghost" data-status="${s}" style="margin:0 4px 0 0;padding:8px">${STATUS_LABELS[s]}</button>`
        ).join("")}
      </div>
    </div>`).join("");
  $("#app").innerHTML = `
    <div class="topbar"><h1>Заказы (админ)</h1></div>
    ${renderNav("adminOrders")}
    <div class="list">${list || '<div class="loader">Заказов нет</div>'}</div>`;
  bindNav();
  document.querySelectorAll("[data-status]").forEach(btn => {
    btn.onclick = async () => {
      const id = btn.closest(".list-item").dataset.id;
      const r = await api(`/api/admin/orders/${id}/status`, { method: "PATCH", body: JSON.stringify({ status: btn.dataset.status }) });
      if (r.error) { toast(r.error); } else { toast("Статус обновлён"); showAdminOrders(); }
    };
  });
}

/* ---------- admin: add product ---------- */

function showAdminAdd() {
  if (tg) { tg.BackButton.hide(); }
  $("#app").innerHTML = `
    <div class="topbar"><h1>Добавить товар</h1></div>
    ${renderNav("adminAdd")}
    <div class="form">
      <div class="field"><label>Название</label><input id="pname" /></div>
      <div class="field"><label>Описание</label><textarea id="pdesc" rows="3"></textarea></div>
      <div class="field"><label>Цена, ₽</label><input id="pprice" type="number" min="0" /></div>
      <div class="field"><label>Главное фото</label><div class="upload-box" id="mainBox">📷 Выбрать фото<div id="mainPrev"></div></div><input type="file" id="mainFile" accept="image/*" class="hidden" /></div>
      <div class="field"><label>Доп. фото (до 20)</label><div class="upload-box" id="photosBox">🖼 Выбрать фото</div><input type="file" id="photosFile" accept="image/*" multiple class="hidden" /><div id="photosCount" class="muted"></div></div>
      <div class="field"><label>Размеры и остатки (пример: S:5, M:2, L:0)</label><input id="psizes" placeholder="S:5, M:2, L:0" /></div>
      <button class="btn" id="addProductBtn">Сохранить товар</button>
    </div>`;
  bindNav();

  const mainFile = $("#mainFile"), photosFile = $("#photosFile");
  let main = null, photos = [];

  $("#mainBox").onclick = () => mainFile.click();
  $("#photosBox").onclick = () => photosFile.click();
  mainFile.onchange = (e) => {
    main = e.target.files[0] || null;
    $("#mainPrev").innerHTML = main ? `<img src="${URL.createObjectURL(main)}" />` : "";
  };
  photosFile.onchange = (e) => {
    photos = Array.from(e.target.files || []);
    $("#photosCount").textContent = photos.length ? `Выбрано: ${photos.length}` : "";
  };

  $("#addProductBtn").onclick = async () => {
    const name = $("#pname").value.trim();
    if (!name) { toast("Укажите название"); return; }
    const sizesText = $("#psizes").value.trim();
    const sizes = parseSizes(sizesText);

    const fd = new FormData();
    fd.append("name", name);
    fd.append("description", $("#pdesc").value);
    fd.append("price", $("#pprice").value || "0");
    fd.append("sizes", JSON.stringify(sizes));
    if (main) fd.append("main", main);
    photos.forEach(f => fd.append("photos", f));

    const btn = $("#addProductBtn"); btn.disabled = true;
    const res = await fetch("/api/admin/products", {
      method: "POST", headers: { "X-Init-Data": initData }, body: fd,
    });
    const r = await res.json();
    if (r.error) { toast(r.error); btn.disabled = false; return; }
    toast("✅ Товар добавлен");
    showCatalog();
  };
}

function parseSizes(text) {
  return text.split(/[,;]+/).map(s => s.trim()).filter(Boolean).map(s => {
    const m = s.match(/^(.+?):(\d+)$/);
    return m ? [m[1], Number(m[2])] : [s, 0];
  });
}

/* ---------- admin: edit stock ---------- */

function openStockModal() {
  const p = state.product;
  const rows = (p.sizes || []).map(s => `
    <div class="field">
      <label>Размер ${esc(s.size)}</label>
      <input type="number" min="0" data-size="${esc(s.size)}" value="${s.qty}" />
    </div>`).join("");
  document.body.insertAdjacentHTML("beforeend", `
    <div class="modal" id="stockModal">
      <div class="sheet">
        <h3>⚙️ Остатки: ${esc(p.name)}</h3>
        ${rows || '<p class="muted">Размеры не заданы</p>'}
        <button class="btn" id="saveStock">Сохранить</button>
        <button class="btn ghost" id="closeStock">Закрыть</button>
      </div>
    </div>`);
  $("#closeStock").onclick = () => $("#stockModal").remove();
  $("#saveStock").onclick = async () => {
    const inputs = document.querySelectorAll("#stockModal input[data-size]");
    for (const inp of inputs) {
      await api("/api/admin/stock", {
        method: "PATCH", body: JSON.stringify({
          product_id: p.id, size: inp.dataset.size, qty: Number(inp.value || 0),
        }),
      });
    }
    $("#stockModal").remove();
    toast("✅ Остатки сохранены");
    showProduct(p.id);
  };
}

/* ---------- boot ---------- */

async function init() {
  if (tg) { tg.ready(); tg.expand(); }
  try {
    const me = await api("/api/me");
    state.me = me;
  } catch (e) {
    $("#app").innerHTML = '<div class="loader">Откройте приложение из Telegram</div>';
    return;
  }
  showCatalog();
}

init();

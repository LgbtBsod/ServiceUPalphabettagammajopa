/* =========================================================================
 * Service Center PWA — логика фронтенда
 * =========================================================================
 */

// Состояние приложения
const state = {
  orders: [],
  dicts: null,           // справочники
  activeStatus: 'Все',   // активный фильтр статуса
  searchQuery: '',
  editingId: null,       // ID редактируемого/просматриваемого заказа
};

// DOM элементы
const $ = (sel) => document.querySelector(sel);
const ordersList = $('#orders-list');
const searchInput = $('#search-input');
const filterRow = $('#filter-row');
const modal = $('#order-modal');
const orderForm = $('#order-form');

// ---------------------------------------------------------------------------
// API-ключ — сервер требует его на каждом /api/* запросе (require_api_key,
// см. pwa/server.py). QR-код/статус-бар в десктоп-приложении открывают эту
// страницу с ?api_key=... в URL (PWAServerManager.get_url()) — сохраняем
// его в localStorage при первой загрузке, чтобы дальнейшие открытия
// (в т.ч. установленное на главный экран PWA, где query string теряется)
// продолжали работать без повторного сканирования QR.
// ---------------------------------------------------------------------------
const API_KEY = (() => {
  const fromUrl = new URLSearchParams(window.location.search).get('api_key');
  if (fromUrl) {
    localStorage.setItem('pwa_api_key', fromUrl);
    return fromUrl;
  }
  return localStorage.getItem('pwa_api_key') || '';
})();

// ---------------------------------------------------------------------------
// API запросы
// ---------------------------------------------------------------------------
async function api(url, options = {}) {
  const opts = {
    headers: { 'Content-Type': 'application/json', 'X-API-Key': API_KEY },
    ...options,
  };
  if (opts.body && typeof opts.body !== 'string') {
    opts.body = JSON.stringify(opts.body);
  }
  const res = await fetch(url, opts);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
  return data;
}

// ---------------------------------------------------------------------------
// Загрузка данных
// ---------------------------------------------------------------------------
async function loadStats() {
  try {
    const stats = await api('/api/stats');
    $('#stat-total').textContent = stats.total || 0;
    $('#stat-repair').textContent = stats.in_repair || 0;
    $('#stat-ready').textContent = stats.ready || 0;
  } catch (e) { /* тихо */ }
}

async function loadDicts() {
  if (state.dicts) return state.dicts;
  state.dicts = await api('/api/dictionaries');
  return state.dicts;
}

async function loadOrders() {
  ordersList.innerHTML = '<div class="loading">⏳ Загрузка заказов…</div>';
  try {
    let data;
    if (state.searchQuery) {
      data = await api('/api/search?q=' + encodeURIComponent(state.searchQuery));
    } else {
      const params = new URLSearchParams();
      if (state.activeStatus !== 'Все') params.set('status', state.activeStatus);
      params.set('limit', '200');
      data = await api('/api/orders?' + params.toString());
    }
    state.orders = data.orders || [];
    renderOrders();
    $('#stat-count').textContent = `Заказов: ${data.total || state.orders.length}`;
    loadStats();
  } catch (e) {
    ordersList.innerHTML = `<div class="empty-state"><div class="ico">⚠️</div>Ошибка: ${e.message}</div>`;
  }
}

// ---------------------------------------------------------------------------
// Рендеринг списка
// ---------------------------------------------------------------------------
function renderOrders() {
  if (!state.orders.length) {
    ordersList.innerHTML = '<div class="empty-state"><div class="ico">📋</div>Нет заказов</div>';
    return;
  }
  ordersList.innerHTML = state.orders.map(renderOrderCard).join('');
  // Привязка клика + свайпа
  ordersList.querySelectorAll('.order-card').forEach((card) => {
    card.addEventListener('click', () => openOrder(parseInt(card.dataset.id)));
    // Свайп влево — быстрая смена статуса
    _attachSwipe(card, parseInt(card.dataset.id));
  });
}

// Свайп для быстрой смены статуса
function _attachSwipe(card, orderId) {
  let startX = 0, currentX = 0, swiping = false;
  card.addEventListener('touchstart', (e) => {
    startX = e.touches[0].clientX;
    swiping = true;
  }, { passive: true });
  card.addEventListener('touchmove', (e) => {
    if (!swiping) return;
    currentX = e.touches[0].clientX;
    const dx = currentX - startX;
    if (dx < -30) card.style.transform = 'translateX(-30px)';
    else card.style.transform = '';
  }, { passive: true });
  card.addEventListener('touchend', async () => {
    if (!swiping) return;
    swiping = false;
    const dx = currentX - startX;
    card.style.transform = '';
    if (dx < -60) {
      // Свайп влево → следующий статус
      const order = state.orders.find(o => o.id === orderId);
      if (!order) return;
      const statuses = state.dicts ? state.dicts.statuses : ['Диагностика','Ожидание запчастей','В ремонте','Готов к выдаче','Выдан клиенту'];
      const curIdx = statuses.indexOf(order.status);
      const nextIdx = Math.min(curIdx + 1, statuses.length - 1);
      if (nextIdx !== curIdx) {
        try {
          await api(`/api/orders/${orderId}/status`, { method: 'PUT', body: { status: statuses[nextIdx] } });
          showToast(`Статус: ${statuses[nextIdx]}`);
          loadOrders();
        } catch (e) { showToast('Ошибка смены статуса'); }
      }
    }
  });
}

function renderOrderCard(o) {
  const deviceName = [o.device_type, o.brand, o.model].filter(Boolean).join(' ') || '—';
  const price = o.total_price ? `${parseInt(o.total_price).toLocaleString('ru')} ₽` : '';
  const photosCount = (o.photos || []).length;
  const photosIco = photosCount ? ` 📸${photosCount}` : '';

  // CSS класс по статусу
  let cls = '';
  if (['Выдан клиенту', 'Отказ от ремонта'].includes(o.status)) cls = 'completed';
  else cls = 'warning';

  // Класс бейджа
  const badgeCls = 'status-' + (o.status || '').split(' ')[0];

  // Телефон: кликабельная tel:-ссылка (звонок) + копирование по клику
  // telDigits — только цифры для tel: протокола
  const phoneDisplay = o.phone || '';
  const telDigits = (o.phone || '').replace(/\D/g, '');
  const phoneHtml = phoneDisplay
    ? `<a href="tel:${telDigits}" class="order-phone" onclick="event.stopPropagation(); copyPhone('${esc(phoneDisplay)}', this)">📞 ${esc(phoneDisplay)}</a>`
    : '';

  return `
    <div class="order-card ${cls}" data-id="${o.id}">
      <div class="order-top">
        <span class="order-num">№ ${o.order_number}</span>
        <span class="order-date">${o.receipt_date || ''}</span>
      </div>
      <div class="order-client">${esc(o.client_name) || 'Без имени'}</div>
      <div class="order-phone-row">${phoneHtml}</div>
      <div class="order-device">${esc(deviceName)}${photosIco}</div>
      <div class="order-bottom">
        <span class="badge ${badgeCls}">${esc(o.status)}</span>
        ${price ? `<span class="order-price">${price}</span>` : ''}
      </div>
    </div>
  `;
}

function esc(s) {
  const d = document.createElement('div');
  d.textContent = s || '';
  return d.innerHTML;
}

// Копирование телефона в буфер обмена при тапе (плюс tel: для звонка)
function copyPhone(phone, el) {
  // На мобильных tel: откроет звонок; копируем в буфер для удобства
  if (navigator.clipboard) {
    navigator.clipboard.writeText(phone).then(() => {
      showToast('📞 Телефон скопирован: ' + phone);
    }).catch(() => {});
  }
}
window.copyPhone = copyPhone;

// ---------------------------------------------------------------------------
// Фильтры статусов
// ---------------------------------------------------------------------------
async function renderFilters() {
  const dicts = await loadDicts();
  const statuses = ['Все', ...(dicts.statuses || [])];
  filterRow.innerHTML = statuses.map((s) =>
    `<button class="filter-btn ${s === state.activeStatus ? 'active' : ''}" data-status="${esc(s)}">${esc(s)}</button>`
  ).join('');
  filterRow.querySelectorAll('.filter-btn').forEach((btn) => {
    btn.addEventListener('click', () => {
      state.activeStatus = btn.dataset.status;
      state.searchQuery = '';
      searchInput.value = '';
      filterRow.querySelectorAll('.filter-btn').forEach((b) => b.classList.remove('active'));
      btn.classList.add('active');
      loadOrders();
    });
  });
}

// ---------------------------------------------------------------------------
// Модальное окно заказа
// ---------------------------------------------------------------------------
async function openOrder(id) {
  state.editingId = id;
  await loadDicts();
  fillFormSelects();

  try {
    const o = await api('/api/orders/' + id);
    fillForm(o);
    $('#modal-title').textContent = `Заказ № ${o.order_number}`;
    renderPhotos(o.photos || []);
    state._currentPhotos = o.photos || [];
    modal.style.display = 'flex';
  } catch (e) {
    showToast('Ошибка: ' + e.message);
  }
}

function openNewOrder() {
  state.editingId = null;
  loadDicts().then(() => {
    fillFormSelects();
    orderForm.reset();
    $('#f-id').value = '';
    $('#modal-title').textContent = 'Новый заказ';
    renderPhotos([]);
    modal.style.display = 'flex';
  });
}

function fillFormSelects() {
  const d = state.dicts;
  const fill = (sel, items, withEmpty) => {
    const el = $(sel);
    el.innerHTML = (withEmpty ? ['<option value="">—</option>'] : []).concat(
      items.map((i) => `<option value="${esc(i)}">${esc(i)}</option>`)
    ).join('');
  };
  fill('#f-type', d.device_types || [], true);
  fill('#f-brand', d.brands || [], true);
  fill('#f-status', d.statuses || []);
  fill('#f-priority', d.priorities || []);
}

function fillForm(o) {
  $('#f-id').value = o.id || '';
  $('#f-client').value = o.client_name || '';
  $('#f-phone').value = o.phone || '';
  $('#f-type').value = o.device_type || '';
  $('#f-brand').value = o.brand || '';
  $('#f-model').value = o.model || '';
  $('#f-serial').value = o.serial_number || '';
  $('#f-status').value = o.status || 'Диагностика';
  $('#f-defect').value = o.defect || '';
  $('#f-price').value = o.total_price || '';
  $('#f-prepay').value = o.prepayment || '';
  $('#f-priority').value = o.priority || 'Обычный';
  $('#f-engineer').value = o.engineer || '';
  $('#f-completeness').value = o.completeness || '';
  $('#f-appearance').value = o.appearance || '';
  $('#f-notes').value = o.notes || '';
}

function collectForm() {
  return {
    client_name: $('#f-client').value.trim(),
    phone: $('#f-phone').value.trim(),
    device_type: $('#f-type').value,
    brand: $('#f-brand').value,
    model: $('#f-model').value.trim(),
    serial_number: $('#f-serial').value.trim(),
    status: $('#f-status').value,
    defect: $('#f-defect').value.trim(),
    total_price: $('#f-price').value,
    prepayment: $('#f-prepay').value,
    priority: $('#f-priority').value,
    engineer: $('#f-engineer').value.trim(),
    completeness: $('#f-completeness').value.trim(),
    appearance: $('#f-appearance').value.trim(),
    notes: $('#f-notes').value.trim(),
  };
}

// ---------------------------------------------------------------------------
// Фото
// ---------------------------------------------------------------------------
// <img src="..."> не может нести заголовок X-API-Key — ключ передаётся
// query-параметром (require_api_key принимает оба варианта, см. pwa/server.py).
function photoUrl(p) {
  return `${p.url}?api_key=${encodeURIComponent(API_KEY)}`;
}

function renderPhotos(photos) {
  const grid = $('#photos-grid');
  if (!photos.length) {
    grid.innerHTML = '<div class="photo-empty">Нет фото</div>';
    return;
  }
  grid.innerHTML = photos.map((p, i) =>
    `<img class="photo-thumb" src="${photoUrl(p)}" loading="lazy" data-idx="${i}" onclick="openPhotoViewer(state._currentPhotos, ${i})">`
  ).join('');
}

// Просмотр фото с навигацией
let _viewerPhotos = [];
let _viewerIndex = 0;

function openPhotoViewer(photos, idx) {
  _viewerPhotos = photos;
  _viewerIndex = idx;
  showViewerPhoto();
  document.getElementById('photo-viewer').style.display = 'flex';
}
function showViewerPhoto() {
  if (!_viewerPhotos.length) return;
  const p = _viewerPhotos[_viewerIndex];
  document.getElementById('photo-viewer-img').src = photoUrl(p);
  document.getElementById('photo-viewer-counter').textContent =
    `${_viewerIndex + 1} / ${_viewerPhotos.length}`;
}
function navPhoto(dir) {
  _viewerIndex += dir;
  if (_viewerIndex < 0) _viewerIndex = _viewerPhotos.length - 1;
  if (_viewerIndex >= _viewerPhotos.length) _viewerIndex = 0;
  showViewerPhoto();
}
function closePhotoViewer(event) {
  if (event && event.target.id !== 'photo-viewer') return;
  document.getElementById('photo-viewer').style.display = 'none';
}
window.openPhotoViewer = openPhotoViewer;
window.navPhoto = navPhoto;
window.closePhotoViewer = closePhotoViewer;

async function uploadPhotos(files) {
  if (!state.editingId) {
    showToast('Сначала сохраните заказ');
    return;
  }
  for (const file of files) {
    const fd = new FormData();
    fd.append('photo', file);
    try {
      const res = await fetch(`/api/orders/${state.editingId}/photos`, {
        method: 'POST',
        headers: { 'X-API-Key': API_KEY },
        body: fd,
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error);
    } catch (e) {
      showToast('Ошибка загрузки фото: ' + e.message);
    }
  }
  // Перезагружаем заказ, чтобы показать новые фото
  const o = await api('/api/orders/' + state.editingId);
  renderPhotos(o.photos || []);
  showToast('Фото загружено ✓');
}

// ---------------------------------------------------------------------------
// Сохранение
// ---------------------------------------------------------------------------
async function saveOrder(e) {
  e.preventDefault();
  const data = collectForm();
  if (!data.client_name || !data.phone) {
    showToast('Заполните имя и телефон');
    return;
  }
  try {
    if (state.editingId) {
      await api('/api/orders/' + state.editingId, { method: 'PUT', body: data });
      showToast('Заказ обновлён ✓');
    } else {
      const res = await api('/api/orders', { method: 'POST', body: data });
      state.editingId = res.id;
      showToast(`Заказ №${res.order_number} создан ✓`);
    }
    closeModal();
    loadOrders();
  } catch (e) {
    showToast('Ошибка: ' + e.message);
  }
}

async function quickStatus() {
  if (!state.editingId) return;
  try {
    await api('/api/orders/' + state.editingId + '/status', {
      method: 'PUT', body: { status: 'Готов к выдаче' }
    });
    $('#f-status').value = 'Готов к выдаче';
    showToast('Статус: Готов к выдаче ✓');
    loadOrders();
  } catch (e) { showToast('Ошибка: ' + e.message); }
}

// ---------------------------------------------------------------------------
// Утилиты
// ---------------------------------------------------------------------------
function closeModal() {
  modal.style.display = 'none';
}

let toastTimer = null;
function showToast(msg) {
  const t = $('#toast');
  t.textContent = msg;
  t.style.display = 'block';
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { t.style.display = 'none'; }, 3000);
}

// Поиск с debounce
let searchTimer = null;
searchInput.addEventListener('input', () => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => {
    state.searchQuery = searchInput.value.trim();
    if (state.searchQuery) {
      state.activeStatus = 'Все';
      filterRow.querySelectorAll('.filter-btn').forEach((b) => b.classList.toggle('active', b.dataset.status === 'Все'));
    }
    loadOrders();
  }, 400);
});

// ---------------------------------------------------------------------------
// PWA install prompt
// ---------------------------------------------------------------------------
let deferredPrompt = null;
window.addEventListener('beforeinstallprompt', (e) => {
  e.preventDefault();
  deferredPrompt = e;
  showToast('Приложение можно установить — добавьте на главный экран');
});

// ---------------------------------------------------------------------------
// Service Worker регистрация
// ---------------------------------------------------------------------------
if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('sw.js').catch(() => {});
  });
}

// ---------------------------------------------------------------------------
// Привязка событий
// ---------------------------------------------------------------------------
$('#btn-refresh').addEventListener('click', loadOrders);
$('#btn-add').addEventListener('click', openNewOrder);
$('#modal-close').addEventListener('click', closeModal);
modal.addEventListener('click', (e) => { if (e.target === modal) closeModal(); });
orderForm.addEventListener('submit', saveOrder);
$('#btn-status-quick').addEventListener('click', quickStatus);

// Фото: две кнопки — камера и галерея
function handlePhotoInput(e) {
  if (e.target.files.length) uploadPhotos(Array.from(e.target.files));
  e.target.value = '';
}
const camInput = document.getElementById('photo-input-camera');
const galInput = document.getElementById('photo-input-gallery');
if (camInput) camInput.addEventListener('change', handlePhotoInput);
if (galInput) galInput.addEventListener('change', handlePhotoInput);

// Авто-refresh каждые 60 сек
setInterval(() => { if (!state.editingId) loadOrders(); }, 60000);

// ---------------------------------------------------------------------------
// Скрытие адресной строки на мобильных
// ---------------------------------------------------------------------------
function hideAddressBar() {
  // Классический приём: прокрутка на 1px скрывает адресную строку в Android Chrome
  setTimeout(() => {
    window.scrollTo(0, 1);
    // Для iOS Safari
    if (document.documentElement.scrollHeight > window.innerHeight) {
      window.scrollTo(0, 1);
    }
  }, 100);
}

// При загрузке и при повороте экрана
window.addEventListener('load', hideAddressBar);
window.addEventListener('orientationchange', () => setTimeout(hideAddressBar, 300));

// Запрос полноэкранного режима при первом взаимодействии (для Android)
let _fullscreenRequested = false;
function requestFullscreenOnce() {
  if (_fullscreenRequested) return;
  _fullscreenRequested = true;
  const el = document.documentElement;
  if (el.requestFullscreen) {
    el.requestFullscreen().catch(() => {});
  } else if (el.webkitRequestFullscreen) {
    el.webkitRequestFullscreen();
  }
}
// Полноэкранный режим требует жеста пользователя (тап)
document.addEventListener('click', requestFullscreenOnce, { once: true });

// ---------------------------------------------------------------------------
// Старт
// ---------------------------------------------------------------------------
(async () => {
  hideAddressBar();
  await renderFilters();
  await loadOrders();
})();

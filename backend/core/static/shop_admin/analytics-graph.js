document.querySelectorAll('.analytics-chart-panel').forEach((panel) => {
  const list = panel.querySelector('.analytics-chart');
  const chart = panel.querySelector('.analytics-line-chart');
  const controls = panel.querySelector('.analytics-view-controls');
  // The list is newest first, while the chart reads from left to right.
  const rows = [...list.querySelectorAll('.analytics-point')].reverse();
  if (!rows.length) return;
  const values = rows.map((row) => Number(row.dataset.value));
  if (values.some((value) => !Number.isFinite(value))) return;

  const max = Math.max(...values, 0);
  const ns = 'http://www.w3.org/2000/svg';
  const makeSvg = (name, attrs, className) => {
    const element = document.createElementNS(ns, name);
    Object.entries(attrs).forEach(([key, value]) => element.setAttribute(key, String(value)));
    if (className) element.classList.add(className);
    return element;
  };
  const positions = values.map((value, index) => ({
    x: rows.length === 1 ? 300 : 20 + index * 560 / (rows.length - 1),
    y: max ? 210 - value / max * 180 : 210,
  }));
  const svg = makeSvg('svg', { viewBox: '0 0 600 240', preserveAspectRatio: 'none', 'aria-hidden': 'true' }, 'analytics-line-svg');
  [30, 120, 210].forEach((y) => svg.append(makeSvg('line', { x1: 20, x2: 580, y1: y, y2: y }, 'analytics-grid-line')));
  const points = positions.map(({ x, y }) => `${x.toFixed(2)},${y.toFixed(2)}`).join(' ');
  const area = makeSvg('polygon', { points: `20,210 ${points} 580,210` }, 'analytics-line-area');
  svg.append(area, makeSvg('polyline', { points }, 'analytics-line'));
  // At long ranges the marks are sampled visually; every interval remains
  // reachable with the pointer and with the arrow keys.
  const stride = Math.max(1, Math.ceil(rows.length / 90));
  positions.forEach(({ x, y }, index) => {
    if (index % stride === 0 || index === rows.length - 1) {
      svg.append(makeSvg('circle', { cx: x, cy: y, r: 3.5 }, 'analytics-line-dot'));
    }
  });
  const cursor = makeSvg('circle', { cx: positions[0].x, cy: positions[0].y, r: 6 }, 'analytics-line-cursor');
  cursor.setAttribute('visibility', 'hidden');
  svg.append(cursor);
  const plot = document.createElement('div');
  plot.className = 'analytics-plot';
  plot.tabIndex = 0;
  plot.setAttribute('role', 'slider');
  plot.setAttribute('aria-label', panel.querySelector('h2').textContent + ': выберите интервал стрелками');
  plot.setAttribute('aria-valuemin', '1');
  plot.setAttribute('aria-valuemax', String(rows.length));
  plot.setAttribute('aria-valuenow', '1');
  plot.setAttribute('aria-valuetext', `${rows[0].dataset.label}: ${rows[0].querySelector('strong').textContent}`);
  plot.append(svg);

  const labels = document.createElement('div');
  labels.className = 'analytics-axis-labels';
  const first = document.createElement('span'); first.textContent = rows[0].dataset.label;
  const last = document.createElement('span'); last.textContent = rows.length > 1 ? rows[rows.length - 1].dataset.label : '';
  labels.append(first, last);
  const summary = document.createElement('p');
  summary.className = 'analytics-graph-summary';
  summary.textContent = 'Наведите на точку или выберите её стрелками. Для всех значений откройте список.';
  const details = document.createElement('div');
  details.className = 'analytics-point-details';
  details.hidden = true;
  const title = document.createElement('strong');
  const status = document.createElement('p');
  status.className = 'analytics-detail-status';
  status.setAttribute('role', 'status');
  const entries = document.createElement('ul');
  entries.className = 'analytics-detail-orders';
  const more = document.createElement('button');
  more.type = 'button';
  more.textContent = 'Показать ещё';
  more.hidden = true;
  details.append(title, status, entries, more);
  chart.append(plot, labels, summary, details);

  let active = -1;
  let currentPage = 0;
  let timer;
  let serial = 0;
  const cache = new Map();
  const formatDate = (value) => value.split('-').reverse().join('.');
  const formatMoney = (value) => {
    const [whole, fraction = '00'] = String(value).split('.');
    return whole.replace(/\B(?=(\d{3})+(?!\d))/g, ' ') + ',' + fraction.padEnd(2, '0');
  };
  const appendOrders = (orders) => {
    orders.forEach((order) => {
      const entry = document.createElement('li');
      const amount = formatMoney(order.total);
      entry.textContent = `Заказ №${order.id} · ${amount} ₽ · ${formatDate(order.date)}`;
      entries.append(entry);
    });
  };
  const load = async (index, page) => {
    const row = rows[index];
    const endpoint = panel.closest('.analytics-charts').dataset.ordersUrl;
    if (!endpoint || !row.dataset.start || !row.dataset.end) {
      status.textContent = 'Не удалось загрузить заказы.';
      return;
    }
    const request = ++serial;
    status.textContent = 'Загрузка заказов…';
    more.hidden = true;
    const url = new URL(endpoint, window.location.href);
    url.searchParams.set('start', row.dataset.start);
    url.searchParams.set('end', row.dataset.end);
    url.searchParams.set('page', String(page));
    try {
      const key = url.href;
      let data = cache.get(key);
      if (!data) {
        const response = await fetch(url, { credentials: 'same-origin', headers: { Accept: 'application/json' } });
        if (!response.ok) throw new Error('request failed');
        data = await response.json();
        cache.set(key, data);
      }
      if (request !== serial || index !== active) return;
      if (page === 1) entries.replaceChildren();
      appendOrders(data.orders);
      currentPage = data.page;
      status.textContent = entries.children.length ? '' : 'За этот интервал заказов нет.';
      more.hidden = !data.has_next;
    } catch {
      if (request !== serial || index !== active) return;
      status.textContent = 'Не удалось загрузить заказы. Выберите точку ещё раз.';
      active = -1;
    }
  };
  const select = (index, immediate = false) => {
    if (index === active && !details.hidden) return;
    active = index;
    serial += 1;
    clearTimeout(timer);
    const row = rows[index];
    cursor.setAttribute('cx', positions[index].x);
    cursor.setAttribute('cy', positions[index].y);
    cursor.setAttribute('visibility', 'visible');
    plot.setAttribute('aria-valuenow', String(index + 1));
    plot.setAttribute('aria-valuetext', `${row.dataset.label}: ${row.querySelector('strong').textContent}`);
    const interval = row.dataset.start === row.dataset.end ? formatDate(row.dataset.start) : `${formatDate(row.dataset.start)} — ${formatDate(row.dataset.end)}`;
    title.textContent = `${interval} · ${row.querySelector('strong').textContent}`;
    details.hidden = false;
    details.scrollTop = 0;
    entries.replaceChildren();
    status.textContent = 'Загрузка заказов…';
    more.hidden = true;
    timer = setTimeout(() => load(index, 1), immediate ? 0 : 180);
  };
  const fromPointer = (event) => {
    const bounds = svg.getBoundingClientRect();
    const x = (event.clientX - bounds.left) * 600 / bounds.width;
    return rows.length === 1 ? 0 : Math.max(0, Math.min(rows.length - 1, Math.round((x - 20) / 560 * (rows.length - 1))));
  };
  plot.addEventListener('pointermove', (event) => {
    if (event.pointerType !== 'touch') select(fromPointer(event));
  });
  plot.addEventListener('pointerdown', (event) => select(fromPointer(event), true));
  plot.addEventListener('focus', () => select(active < 0 ? rows.length - 1 : active, true));
  plot.addEventListener('keydown', (event) => {
    let index = active < 0 ? rows.length - 1 : active;
    if (event.key === 'ArrowLeft' || event.key === 'ArrowDown') index -= 1;
    else if (event.key === 'ArrowRight' || event.key === 'ArrowUp') index += 1;
    else if (event.key === 'Home') index = 0;
    else if (event.key === 'End') index = rows.length - 1;
    else return;
    event.preventDefault();
    select(Math.max(0, Math.min(rows.length - 1, index)), true);
  });
  more.addEventListener('click', () => load(active, currentPage + 1));

  const setView = (view) => {
    const graph = view === 'graph';
    chart.hidden = !graph;
    list.hidden = graph;
    controls.querySelectorAll('button').forEach((button) => {
      button.setAttribute('aria-pressed', String(button.dataset.view === view));
    });
  };
  controls.addEventListener('click', (event) => {
    const button = event.target.closest('button[data-view]');
    if (button) setView(button.dataset.view);
  });
  controls.hidden = false;
  setView('graph');
});

/* 录制管理台 —— 原生 ES2020，零框架零依赖。
   DOM 一律用 createElement + textContent 构造，从不拼 HTML 字符串：
   主播名和直播标题都是外部可控内容，这样天然没有注入面。 */

/* ---------- 主题：在 body 绘制前就定好，避免首屏闪白 ---------- */
(function () {
  var t = null;
  try { t = localStorage.getItem('dlr-theme'); } catch (e) { /* 隐私模式 */ }
  if (t === 'dark' || t === 'light') document.documentElement.dataset.theme = t;
})();

const $ = (sel, root) => (root || document).querySelector(sel);
const KEYSEP = String.fromCharCode(31);   // 与后端 api.py 的 KEYSEP 一致

/* ---------- DOM 构造 ---------- */
function h(tag, props, ...kids) {
  const el = document.createElement(tag);
  if (props) for (const [k, v] of Object.entries(props)) {
    if (v === null || v === undefined || v === false) continue;
    if (k === 'class') el.className = v;
    else if (k === 'text') el.textContent = v;
    else if (k === 'html') throw new Error('不允许 innerHTML');
    else if (k.startsWith('on')) el.addEventListener(k.slice(2), v);
    else if (k === 'style' && typeof v === 'object') Object.assign(el.style, v);
    else if (v === true) el.setAttribute(k, '');
    else el.setAttribute(k, v);
  }
  for (const kid of kids.flat()) {
    if (kid === null || kid === undefined || kid === false) continue;
    el.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
  }
  return el;
}

/* ---------- 网络 ---------- */
async function api(path, body) {
  const opt = { headers: {}, cache: 'no-store' };
  if (body !== undefined) {
    opt.method = 'POST';
    opt.headers['Content-Type'] = 'application/json';
    opt.headers['X-DLR-CSRF'] = '1';          // 见 server.py 的 CSRF 说明
    opt.body = JSON.stringify(body);
  }
  const res = await fetch(path, opt);
  let data = null;
  try { data = await res.json(); } catch (e) { /* 空响应 */ }
  if (!res.ok) {
    const err = new Error((data && data.error) || `HTTP ${res.status}`);
    err.status = res.status;
    err.detail = data && data.detail;
    throw err;
  }
  return data;
}

/* ---------- 状态 ---------- */
const S = {
  meta: null, fields: [], values: {}, edits: new Map(),
  rooms: [], roomsRev: null, roomsMeta: {}, status: null,
  tab: 'overview', search: '', pollTimer: null, pollMs: 0, tickTimer: null,
  groupByPlatform: true,
  fails: 0, revealed: new Set(),
};

const kk = (f) => f.section + KEYSEP + f.key;
const fmtBytes = (n) => {
  if (!Number.isFinite(n)) return '—';
  const u = ['B', 'KB', 'MB', 'GB', 'TB', 'PB'];
  let i = 0; while (n >= 1024 && i < u.length - 1) { n /= 1024; i++; }
  return (i >= 3 ? n.toFixed(1) : Math.round(n)) + ' ' + u[i];
};
// 卡片很窄, 长路径只保留首尾各一段, 完整路径挂在 title 上
const shortPath = (p) => {
  if (!p || p.length <= 28) return p;
  const parts = p.split('/').filter(Boolean);
  if (parts.length <= 2) return '…' + p.slice(-26);
  return `/${parts[0]}/…/${parts[parts.length - 1]}`;
};
const fmtDur = (s) => {
  s = Math.max(0, Math.floor(s));
  const p = (x) => String(x).padStart(2, '0');
  return `${p(Math.floor(s / 3600))}:${p(Math.floor(s / 60) % 60)}:${p(s % 60)}`;
};

/* ---------- 提示条 ---------- */
function toast(msg, kind, sub, ms) {
  const el = h('div', { class: 'toast ' + (kind || 'ok') },
    h('div', { text: msg }), sub ? h('div', { class: 'sub', text: sub }) : null);
  $('#toasts').append(el);
  setTimeout(() => el.remove(), ms || (kind === 'err' ? 8000 : 4200));
}

/* ================================================================ 启动 */

document.addEventListener('DOMContentLoaded', init);

async function init() {
  try {
    const [meta, schema, cfg] = await Promise.all([
      api('/api/meta'), api('/api/schema'), api('/api/config'),
    ]);
    S.meta = meta; S.fields = schema.fields; S.values = cfg.values;
  } catch (e) {
    $('#boot').textContent = '连接录制程序失败：' + e.message;
    return;
  }
  $('#boot').hidden = true;
  $('#app').hidden = false;
  $('#version').textContent = S.meta.version || '';

  buildTabs();
  wireChrome();
  renderForms();
  await refreshRooms().catch(() => {});
  await poll();
  startPolling();
}

function buildTabs() {
  const defs = [
    ['overview', '概览'], ['rooms', '直播间'], ['record', '录制设置'],
    ['push', '推送'], ['creds', '凭据'], ['webui', '界面设置'],
  ];
  const nav = $('#tabs');
  nav.replaceChildren(...defs.map(([id, label]) => h('button', {
    type: 'button', role: 'tab', 'data-tab': id,
    'aria-selected': id === S.tab ? 'true' : 'false',
    onclick: () => switchTab(id),
  }, label, id === 'overview' ? h('span', { class: 'badge', hidden: true, id: 'rec-badge' }) : null)));
}

function switchTab(id) {
  S.tab = id;
  for (const b of $('#tabs').children) b.setAttribute('aria-selected', b.dataset.tab === id ? 'true' : 'false');
  for (const v of $('#views').children) v.hidden = v.dataset.view !== id;
  if (id === 'rooms') refreshRooms().catch(err => toast(err.message, 'err'));
  if (id === 'webui') { refreshBackups(); refreshLogs(); }
  if (id === 'overview') poll();
}

function wireChrome() {
  $('#theme-btn').addEventListener('click', cycleTheme);
  $('#save-btn').addEventListener('click', save);
  $('#discard-btn').addEventListener('click', discard);
  $('#room-add-btn').addEventListener('click', () => openRoomDialog(null));
  $('#room-enable-all').addEventListener('click', () => toggleAll(true));
  $('#room-disable-all').addEventListener('click', () => toggleAll(false));
  $('#room-search').addEventListener('input', (e) => { S.search = e.target.value.trim(); renderRooms(); });

  let grouped = true;
  try { grouped = localStorage.getItem('dlr-group') !== '0'; } catch (e) { /* 隐私模式 */ }
  S.groupByPlatform = grouped;
  $('#room-group').checked = grouped;
  $('#room-group').addEventListener('change', (e) => {
    S.groupByPlatform = e.target.checked;
    try { localStorage.setItem('dlr-group', e.target.checked ? '1' : '0'); } catch (err) { /* 隐私模式 */ }
    renderRooms();
  });
  $('#log-refresh').addEventListener('click', refreshLogs);

  document.addEventListener('keydown', (e) => {
    if ((e.metaKey || e.ctrlKey) && e.key === 's') { e.preventDefault(); if (S.edits.size) save(); }
  });
  window.addEventListener('beforeunload', (e) => {
    if (S.edits.size) { e.preventDefault(); e.returnValue = ''; }
  });
  document.addEventListener('visibilitychange', () => {
    if (document.hidden) stopPolling(); else { poll(); startPolling(); }
  });
}

function cycleTheme() {
  const cur = document.documentElement.dataset.theme || 'auto';
  const next = cur === 'auto' ? 'light' : (cur === 'light' ? 'dark' : 'auto');
  if (next === 'auto') delete document.documentElement.dataset.theme;
  else document.documentElement.dataset.theme = next;
  try { localStorage.setItem('dlr-theme', next); } catch (e) { /* 隐私模式 */ }
  toast({ auto: '主题：跟随系统', light: '主题：浅色', dark: '主题：深色' }[next]);
}

/* ================================================================ 概览 */

const POLL_FAST = 2000, POLL_SLOW = 10000;   // 连续失败后退避, 恢复后自动调回

function startPolling(ms) {
  stopPolling();
  S.pollMs = ms || POLL_FAST;
  S.pollTimer = setInterval(poll, S.pollMs);
}
function stopPolling() { clearInterval(S.pollTimer); S.pollTimer = null; }

async function poll() {
  try {
    S.status = await api('/api/status');
    if (S.fails) {                    // 刚从断连中恢复
      $('#conn').textContent = '';
      $('#conn').classList.remove('bad');
      S.fails = 0;
      if (S.pollTimer && S.pollMs !== POLL_FAST) startPolling(POLL_FAST);
    }
  } catch (e) {
    S.fails++;
    if (S.fails >= 3) {
      $('#conn').textContent = '与录制程序失去连接';
      $('#conn').classList.add('bad');
      if (S.pollTimer && S.pollMs !== POLL_SLOW) startPolling(POLL_SLOW);
    }
    return;
  }
  renderOverview();
  if (S.tab === 'rooms' && S.status.rooms_rev && S.status.rooms_rev !== S.roomsRev) {
    refreshRooms().catch(() => {});
  }
}

function renderOverview() {
  const st = S.status || {};
  const rec = st.recording || [];
  const eff = st.effective || {};
  const disk = st.disk || {};

  $('#live-dot').classList.toggle('on', rec.length > 0);
  const badge = $('#rec-badge');
  if (badge) { badge.hidden = rec.length === 0; badge.textContent = String(rec.length); }
  document.title = rec.length ? `● ${rec.length} 录制中 · 录制管理台` : '录制管理台';

  const card = (k, v, sub, flag) => h('div', { class: 'card' + (flag ? ' flag' : '') },
    h('div', { class: 'k', text: k }), h('div', { class: 'v', text: v }),
    sub ? h('div', { class: 'sub', text: sub }) : null);

  const diskSub = disk.exists === false
    ? '保存路径不存在，录制会落到系统盘！'
    : shortPath(disk.path || '');
  const diskCard = card('磁盘剩余', disk.ok ? fmtBytes(disk.free) : '读取失败',
    diskSub, disk.exists === false);
  const subEl = diskCard.querySelector('.sub');
  if (subEl) subEl.title = st.effective?.video_save_path || disk.path || '';   // 悬停看完整路径

  $('#stat-cards').replaceChildren(
    card('正在录制', String(rec.length), rec.length ? '' : '暂无'),
    card('监测中', String(st.monitoring ?? '—'), '个直播间'),
    card('并发线程数', String(eff.max_request ?? '启动中'), '程序动态调节'),
    card('瞬时错误数', String(st.error_count ?? '—'), (st.error_count || 0) >= 5 ? '偏高' : '',
      (st.error_count || 0) >= 5),
    diskCard,
  );

  if (!rec.length) {
    $('#recording-wrap').replaceChildren(
      h('div', { class: 'empty', text: st.monitoring ? '监测中，暂时没有直播间在开播' : '还没有启用任何直播间' }));
  } else {
    const rows = rec.map(r => h('tr',
      null,
      h('td', null, h('span', { class: 'tag live', text: '● REC' })),
      h('td', { text: r.name }),
      h('td', null, h('span', { class: 'tag', text: r.quality || '—' })),
      h('td', { class: 'mono', text: r.start_at }),
      h('td', { class: 'mono', 'data-elapsed': r.elapsed, text: fmtDur(r.elapsed) })));
    $('#recording-wrap').replaceChildren(h('div', { class: 'tbl-scroll' },
      h('table', { class: 'tbl' },
        h('thead', null, h('tr', null, ...['', '直播间', '清晰度', '开始时间', '已录时长']
          .map(t => h('th', { text: t })))),
        h('tbody', null, ...rows))));
  }

  const B = (v) => v === true ? '是' : (v === false ? '否' : '启动中');
  const cfgOf = (sec, key) => {
    const f = S.fields.find(x => x.section === sec && x.key === key);
    return f ? currentValue(f) : null;
  };
  // live 是运行期真实值, cfg 是配置文件里的值, show 只负责显示格式。
  // 比较必须拿两个原始值比, 之前拿带"秒"单位的显示串去比配置值, 永远不相等 -> 误报。
  const effCard = (label, live, cfg, show) => {
    const unknown = live === null || live === undefined;
    const same = unknown || cfg === null || String(cfg) === String(live);
    return h('div', { class: 'card' + (same ? '' : ' flag') },
      h('div', { class: 'k', text: label }),
      h('div', { class: 'v', text: unknown ? '启动中' : (show ? show(live) : String(live)) }),
      same ? null : h('div', { class: 'sub', text: `配置文件里是 ${cfg}` }));
  };
  $('#effective-cards').replaceChildren(
    effCard('保存格式', eff.video_save_type,
      (cfgOf('录制设置', '视频保存格式ts|mkv|flv|mp4|mp3音频|m4a音频') || '').toUpperCase()),
    effCard('清晰度', eff.video_record_quality, cfgOf('录制设置', '原画|超清|高清|标清|流畅')),
    effCard('分段', eff.split_video_by_time, null,
      (v) => v ? `每 ${eff.split_time} 秒` : '关闭'),
    effCard('检测间隔', eff.delay_default, cfgOf('录制设置', '循环时间(秒)'), (v) => `${v} 秒`),
    effCard('代理', eff.use_proxy, null, B),
  );

  clearInterval(S.tickTimer);
  S.tickTimer = setInterval(() => {
    for (const td of document.querySelectorAll('[data-elapsed]')) {
      const n = Number(td.dataset.elapsed) + 1;
      td.dataset.elapsed = n;
      td.textContent = fmtDur(n);
    }
  }, 1000);
}

/* ================================================================ 直播间 */

async function refreshRooms() {
  const d = await api('/api/rooms');
  S.rooms = d.rooms; S.roomsRev = d.rev; S.roomsMeta = d;
  renderRooms();
}

function roomRow(r) {
  const tr = h('tr', { class: r.enabled ? '' : 'off', draggable: 'true', 'data-url': r.url });

  tr.addEventListener('dragstart', e => { e.dataTransfer.setData('text/plain', r.url); tr.style.opacity = '.4'; });
  tr.addEventListener('dragend', () => { tr.style.opacity = ''; });
  tr.addEventListener('dragover', e => { e.preventDefault(); tr.classList.add('dragover'); });
  tr.addEventListener('dragleave', () => tr.classList.remove('dragover'));
  tr.addEventListener('drop', e => {
    e.preventDefault(); tr.classList.remove('dragover');
    reorder(e.dataTransfer.getData('text/plain'), r.url);
  });

  const cb = h('input', {
    type: 'checkbox', checked: r.enabled,
    onchange: (e) => toggleRoom(r, e.target.checked, e.target),
  });

  const qsel = h('select', { onchange: (e) => updateRoom(r, { quality: e.target.value }) },
    h('option', { value: '', selected: !r.quality }, `跟随全局（${S.roomsMeta.default_quality || '原画'}）`),
    ...(S.roomsMeta.qualities || []).map(qv =>
      h('option', { value: qv, selected: r.quality === qv }, qv)));

  tr.append(
    h('td', { class: 'grip', title: '拖动排序', text: '⠿' }),
    h('td', null, cb),
    h('td', null,
      h('div', { class: 'url', text: r.url }),
      h('div', { class: 'tags' },
        // 停用的不显示任何运行状态; 启用且真的在录 -> 录制中; 否则 -> 监测中
        !r.enabled ? null
          : (r.recording ? h('span', { class: 'tag live', text: '● 录制中' })
                         : h('span', { class: 'tag', text: '监测中' })),
        r.skipped ? h('span', { class: 'tag warn', text: '本次运行已跳过，需重启程序' }) : null,
        !r.known_platform ? h('span', { class: 'tag warn', text: '未知平台' }) : null)),
    h('td', { text: r.name || '—' }),
    h('td', null, qsel),
    h('td', null,
      h('button', { class: 'btn tiny', type: 'button', onclick: () => openRoomDialog(r) }, '编辑'),
      ' ',
      h('button', { class: 'btn tiny danger', type: 'button', onclick: () => removeRoom(r) }, '删除')),
  );
  return tr;
}

function renderRooms() {
  const q = S.search.toLowerCase();
  const list = S.rooms.filter(r => !q || r.url.toLowerCase().includes(q) || (r.name || '').toLowerCase().includes(q));
  const wrap = $('#rooms-wrap');

  if (!list.length) {
    wrap.replaceChildren(h('div', { class: 'empty', text: S.rooms.length ? '没有匹配的直播间' : '还没有添加任何直播间' }));
    return;
  }

  const head = h('thead', null, h('tr', null,
    ...['', '启用', '直播间地址', '主播', '清晰度', ''].map(t => h('th', { text: t }))));

  let bodies;
  if (S.groupByPlatform) {
    // 按平台分组。顺序取"每个平台在文件里首次出现的位置", 不强行字典序,
    // 这样用户自己在文件里的编排习惯还看得出来。
    const groups = new Map();
    for (const r of list) {
      const p = r.platform || '其他平台';
      if (!groups.has(p)) groups.set(p, []);
      groups.get(p).push(r);
    }
    bodies = [...groups.entries()].map(([name, rows]) => {
      const on = rows.filter(x => x.enabled).length;
      const rec = rows.filter(x => x.enabled && x.recording).length;
      const header = h('tr', { class: 'grp' }, h('td', { colspan: '6' },
        name,
        h('span', { class: 'cnt', text: `${rows.length} 个 · 启用 ${on}` }),
        rec ? h('span', { class: 'rec', text: `● 录制中 ${rec}` }) : null));
      return h('tbody', null, header, ...rows.map(roomRow));
    });
  } else {
    bodies = [h('tbody', null, ...list.map(roomRow))];
  }

  wrap.replaceChildren(h('div', { class: 'tbl-scroll' },
    h('table', { class: 'tbl' }, head, ...bodies)));
}

async function roomOp(path, body, okMsg, sub) {
  try {
    const d = await api(path, Object.assign({ rev: S.roomsRev }, body));
    S.rooms = d.rooms; S.roomsRev = d.rev; S.roomsMeta = d;
    renderRooms();
    if (okMsg) toast(okMsg, d.warning ? 'warn' : 'ok', d.warning || sub);
    poll().catch(() => {});      // 顺带刷新概览的录制数
    return true;
  } catch (e) {
    if (e.status === 409) {
      toast('列表已被录制程序改动，已为你刷新', 'warn', '请重新操作一次');
      await refreshRooms().catch(() => {});
    } else {
      toast(e.message, 'err');
      await refreshRooms().catch(() => {});
    }
    return false;
  }
}

const toggleRoom = (r, on, el) => {
  if (el) el.disabled = true;
  return roomOp('/api/rooms/toggle', { url: r.url, enabled: on },
    on ? `已启用 ${r.name || r.url}` : `已停用 ${r.name || r.url}`,
    on ? '录制程序最长约 3 秒后开始监测' : '正在录制的话会优雅停止，文件正常保存')
    .finally(() => { if (el) el.disabled = false; });
};

const toggleAll = (on) => {
  if (!on && !confirm('确定要停用全部直播间吗？正在录制的会优雅停止并保存文件。')) return;
  roomOp('/api/rooms/toggle_all', { enabled: on }, on ? '已全部启用' : '已全部停用');
};

const updateRoom = (r, patch) => roomOp('/api/rooms/update',
  Object.assign({ url: r.url, quality: r.quality, new_url: r.url, name: r.name }, patch), '已保存');

const removeRoom = (r) => {
  if (!confirm(`确定删除 ${r.name || r.url} 吗？\n已经录好的文件不受影响。`)) return;
  roomOp('/api/rooms/delete', { url: r.url }, '已删除');
};

const reorder = (from, to) => {
  if (from === to) return;
  const order = S.rooms.map(r => r.url);
  const i = order.indexOf(from); if (i < 0) return;
  order.splice(i, 1);
  const j = order.indexOf(to);
  order.splice(j < 0 ? order.length : j, 0, from);
  roomOp('/api/rooms/reorder', { order });
};

function openRoomDialog(room) {
  const dlg = $('#room-dialog'), form = $('#room-form');
  $('#room-dialog-title').textContent = room ? '编辑直播间' : '新增直播间';
  $('#room-dialog-err').hidden = true;
  form.url.value = room ? room.url : '';
  form.name.value = room ? (room.name || '') : '';
  form.quality.replaceChildren(
    h('option', { value: '' }, `跟随全局（${S.roomsMeta.default_quality || '原画'}）`),
    ...(S.roomsMeta.qualities || []).map(q => h('option', { value: q }, q)));
  form.quality.value = room ? (room.quality || '') : '';

  const onClose = async () => {
    dlg.removeEventListener('close', onClose);
    if (dlg.returnValue !== 'ok') return;
    const body = { url: form.url.value.trim(), name: form.name.value.trim(), quality: form.quality.value };
    const ok = room
      ? await roomOp('/api/rooms/update', Object.assign({ url: room.url, new_url: body.url }, body), '已保存')
      : await roomOp('/api/rooms/add', body, '已添加');
    if (!ok) openRoomDialog(room);
  };
  dlg.addEventListener('close', onClose);
  dlg.showModal();
}

/* ================================================================ 配置表单 */

function currentValue(f) {
  const key = kk(f);
  if (S.edits.has(key)) return S.edits.get(key);
  const v = S.values[key];
  if (v && typeof v === 'object' && v.masked) return S.revealed.has(key) ? (v.plain ?? '') : null;
  return v;
}

function renderForms() {
  const groups = { record: ['录制设置'], push: ['推送配置'], creds: ['Cookie', '账号密码', 'Authorization'], webui: ['网页界面'] };
  for (const [view, sections] of Object.entries(groups)) {
    const host = $('#form-' + view);
    const byGroup = new Map();
    for (const f of S.fields) {
      if (!sections.includes(f.section)) continue;
      const g = (sections.length > 1 ? f.section + ' · ' : '') + f.group;
      if (!byGroup.has(g)) byGroup.set(g, []);
      byGroup.get(g).push(f);
    }
    const blocks = [...byGroup.entries()].map(([name, fields], i) =>
      h('details', { class: 'group', open: i < 2 || view === 'webui' },
        h('summary', null, name, h('span', { class: 'muted', text: ` · ${fields.length} 项` })),
        h('div', { class: 'body' }, ...fields.map(fieldRow))));
    host.replaceChildren(...blocks);
  }
  renderLanCard();
  applyDepends();
}

function fieldRow(f) {
  const key = kk(f);
  const locked = (S.meta.readonly_keys || []).some(([s, k]) => s === f.section.toLowerCase() && k === f.key.toLowerCase());
  const row = h('div', { class: 'field' + (locked ? ' locked' : ''), 'data-key': key });
  row.append(h('div', { class: 'lab' }, f.label,
    f.restart ? h('span', { class: 'req', text: '改动后需重启程序' })
      : (f.next_only ? h('span', { class: 'req', text: '下次开录时生效' }) : null)));

  const ctl = h('div', { class: 'ctl' });
  ctl.append(buildControl(f, locked));
  row.append(ctl);
  if (f.help) row.append(h('div', { class: 'note', text: f.help }));
  if (f.warn) row.append(h('div', { class: 'note warn', text: '注意：' + f.warn }));
  if (locked) row.append(h('div', { class: 'note warn', text: '你正在通过局域网访问，这一项被锁定为只读' }));
  row.append(h('div', { class: 'note err', hidden: true }));
  return row;
}

function buildControl(f, locked) {
  const key = kk(f);
  const v = currentValue(f);
  const set = (val) => edit(f, val);
  const dis = locked || undefined;

  if (f.type === 'bool') {
    const cb = h('input', { type: 'checkbox', checked: !!v, disabled: dis, onchange: e => set(e.target.checked) });
    return h('label', { class: 'switch' }, cb, h('span', { text: v ? '已开启' : '已关闭' }));
  }
  if (f.type === 'select') {
    return h('select', { disabled: dis, onchange: e => set(e.target.value) },
      ...f.choices.map(([val, lab]) => h('option', { value: val, selected: String(v ?? '') === val }, lab)));
  }
  if (f.type === 'multiselect') {
    const cur = new Set(Array.isArray(v) ? v : []);
    return h('div', { class: 'chips' }, ...f.choices.map(([val, lab]) =>
      h('label', null,
        h('input', {
          type: 'checkbox', checked: cur.has(val), disabled: dis,
          onchange: e => { e.target.checked ? cur.add(val) : cur.delete(val); set([...cur]); },
        }), lab)));
  }
  if (f.type === 'csv') {
    return h('textarea', {
      placeholder: f.placeholder, disabled: dis,
      onchange: e => set(e.target.value.split(/[,，]/).map(s => s.trim()).filter(Boolean)),
    }, Array.isArray(v) ? v.join(', ') : (v || ''));
  }
  if (f.type === 'textarea') {
    return h('textarea', { placeholder: f.placeholder, disabled: dis, onchange: e => set(e.target.value) }, v || '');
  }
  if (f.secret) {
    const meta = S.values[key] || {};
    const shown = S.edits.has(key) || S.revealed.has(key);
    const input = h('input', {
      type: shown ? 'text' : 'password', disabled: dis,
      placeholder: meta.empty ? '（未设置）' : (meta.hint || ''),
      value: shown ? (S.edits.get(key) ?? meta.plain ?? '') : '',
      onchange: e => set(e.target.value),
    });
    const btn = h('button', { class: 'btn tiny', type: 'button' }, shown ? '隐藏' : '显示');
    btn.addEventListener('click', async () => {
      if (S.revealed.has(key)) { S.revealed.delete(key); return rerenderField(f); }
      try {
        const d = await api(`/api/config/reveal?section=${encodeURIComponent(f.section)}&key=${encodeURIComponent(f.key)}`);
        meta.plain = d.value; S.revealed.add(key); rerenderField(f);
      } catch (e) { toast(e.message, 'err'); }
    });
    return h('div', { class: 'secret-row' }, input, btn);
  }
  const type = f.type === 'int' || f.type === 'float' ? 'number' : 'text';
  return h('input', {
    type, disabled: dis, placeholder: f.placeholder,
    min: f.minv, max: f.maxv, step: f.type === 'float' ? 'any' : '1',
    value: v ?? '', onchange: e => set(e.target.value),
  });
}

function rerenderField(f) {
  const row = document.querySelector(`.field[data-key="${cssEsc(kk(f))}"]`);
  if (!row) return;
  const fresh = fieldRow(f);
  row.replaceWith(fresh);
  markDirty(f);
  applyDepends();
}
const cssEsc = (s) => (window.CSS && CSS.escape) ? CSS.escape(s) : s.replace(/[^\w-]/g, m => '\\' + m);

function edit(f, val) {
  const key = kk(f);
  const orig = S.values[key];
  const same = (orig && typeof orig === 'object' && orig.masked)
    ? false                                   // 密文改过就算改过，无法比较
    : JSON.stringify(orig ?? '') === JSON.stringify(val ?? '');
  if (same) S.edits.delete(key); else S.edits.set(key, val);
  markDirty(f);
  updateDirtyBar();
  applyDepends();
  if (f.type === 'bool') {
    const row = document.querySelector(`.field[data-key="${cssEsc(key)}"] .switch span`);
    if (row) row.textContent = val ? '已开启' : '已关闭';
  }
}

function markDirty(f) {
  const row = document.querySelector(`.field[data-key="${cssEsc(kk(f))}"]`);
  if (row) row.classList.toggle('dirty', S.edits.has(kk(f)));
}

function updateDirtyBar() {
  const n = S.edits.size;
  $('#dirtybar').hidden = n === 0;
  $('#dirty-count').textContent = n ? `${n} 项待保存` : '';
}

function applyDepends() {
  for (const f of S.fields) {
    if (!f.depends || !f.depends.length) continue;
    const [depKey, expect] = f.depends;
    const dep = S.fields.find(x => x.section === f.section && x.key === depKey);
    if (!dep) continue;
    const dv = currentValue(dep);
    let on;
    if (expect === true) on = !!dv;
    else if (Array.isArray(dv)) on = dv.some(x => String(x).toLowerCase() === String(expect).toLowerCase());
    else on = String(dv ?? '').toLowerCase().includes(String(expect).toLowerCase());
    const row = document.querySelector(`.field[data-key="${cssEsc(kk(f))}"]`);
    if (row) row.hidden = !on;
  }
}

async function save() {
  const idx = new Map(S.fields.map(f => [kk(f), f]));
  const changes = [...S.edits.entries()].map(([key, value]) => {
    const f = idx.get(key);
    return { section: f.section, key: f.key, value };
  });
  for (const row of document.querySelectorAll('.field .note.err')) row.hidden = true;
  $('#save-btn').disabled = true;
  try {
    const d = await api('/api/config', { changes });
    S.edits.clear();
    S.revealed.clear();
    const cfg = await api('/api/config');
    S.values = cfg.values;
    renderForms();
    updateDirtyBar();
    const nextOnly = changes.some(c => (idx.get(c.section + KEYSEP + c.key) || {}).next_only);
    let sub = '录制程序约 3 秒后自动生效';
    if (nextOnly) sub += '；不会打断正在进行的录制，下次开录时才用新设置';
    if (d.restart_required && d.restart_required.length) {
      sub = `${d.restart_required.join('、')} 需要重启程序才生效`;
    }
    toast(`已保存 ${d.saved} 项`, 'ok', sub);
    if (d.drifted && d.drifted.length) {
      toast('有 ' + d.drifted.length + ' 项写入后被覆盖', 'warn', d.drifted.join('、'));
    }
  } catch (e) {
    if (e.status === 422 && e.detail) {
      for (const [key, msg] of Object.entries(e.detail)) {
        const row = document.querySelector(`.field[data-key="${cssEsc(key)}"] .note.err`);
        if (row) { row.textContent = msg; row.hidden = false; }
      }
      toast(e.message, 'err', '有问题的项已在表单里标红，你的输入没有丢失');
    } else {
      toast('保存失败：' + e.message, 'err', '你的输入没有丢失，可以修改后重试');
    }
  } finally {
    $('#save-btn').disabled = false;
  }
}

function discard() {
  if (!confirm(`放弃 ${S.edits.size} 项未保存的修改？`)) return;
  S.edits.clear();
  renderForms();
  updateDirtyBar();
}

/* ================================================================ 界面设置页 */

function renderLanCard() {
  const m = S.meta, host = $('#lan-card');
  const kids = [];
  if (m.lan_enabled) {
    kids.push(h('div', { class: 'banner' },
      h('h3', { text: '局域网访问已开启 —— 请认真读完下面几条' }),
      h('ul', null,
        h('li', { text: '这是明文 HTTP，没有 TLS。访问令牌、以及你点"显示"时拉取的 Cookie 和邮箱授权码，都会以明文经过 Wi-Fi。' }),
        h('li', { text: '拿到令牌就等于拿到你所有平台的 Cookie 和账号密码。' }),
        h('li', null, '"自定义脚本"等同于任意命令执行。',
          m.lan_lock_script ? '目前已锁定为只读（推荐保持）。' : '目前未锁定，建议开启锁定。'),
        h('li', null, '更安全的做法：监听地址改回 ', h('code', { text: '127.0.0.1' }),
          '，手机通过 ', h('code', { text: 'ssh -L 8787:127.0.0.1:8787 用户名@这台机器' }),
          ' 端口转发，或者用 Tailscale 之类的内网 VPN。'),
        h('li', { text: '绝对不要把这个端口转发到公网路由器上。' })),
    ));
    if (m.lan_urls && m.lan_urls.length) {
      kids.push(h('h2', { text: '手机访问' }));
      kids.push(h('p', { class: 'hint', text: '在同一 Wi-Fi 下打开下面的地址。第一次带令牌访问后会种一个 Cookie，之后就不用再带了。' }));
      kids.push(h('div', { class: 'cards' }, ...m.lan_urls.map(u =>
        h('div', { class: 'card' },
          h('div', { class: 'k', text: '访问地址' }),
          h('div', { class: 'url', text: u }),
          h('button', {
            class: 'btn tiny', type: 'button', style: { marginTop: '.4rem' },
            onclick: () => navigator.clipboard?.writeText(u).then(
              () => toast('已复制'), () => toast('复制失败，请手动选中', 'err')),
          }, '复制')))));
    }
  } else {
    kids.push(h('div', { class: 'banner' },
      h('h3', { text: '当前只监听本机，其他设备无法访问' }),
      h('ul', null,
        h('li', null, '这是最安全的默认值。想从手机访问，把上面的"监听地址"改成 ',
          h('code', { text: '0.0.0.0' }), ' 并重启程序，系统会自动生成一个访问令牌。'),
        h('li', { text: '开启前请先想清楚：这个界面能读写你全部平台的 Cookie 和账号密码，而且是明文传输。' }))));
  }
  host.replaceChildren(...kids);
}

async function refreshBackups() {
  try {
    const d = await api('/api/backups');
    const wrap = $('#backups-wrap');
    if (!d.backups.length) return wrap.replaceChildren(h('div', { class: 'empty', text: '还没有备份' }));
    wrap.replaceChildren(h('div', { class: 'tbl-scroll' }, h('table', { class: 'tbl' },
      h('thead', null, h('tr', null, ...['备份文件', '对应', '大小', '时间', '']
        .map(t => h('th', { text: t })))),
      h('tbody', null, ...d.backups.map(b => h('tr', null,
        h('td', { class: 'mono', text: b.name }),
        h('td', { text: b.target }),
        h('td', { text: fmtBytes(b.size) }),
        h('td', { text: new Date(b.mtime * 1000).toLocaleString('zh-CN') }),
        h('td', null, h('button', { class: 'btn tiny', type: 'button', onclick: () => restore(b) }, '还原'))))))));
  } catch (e) { toast(e.message, 'err'); }
}

async function restore(b) {
  if (!confirm(`用这份备份覆盖当前的 ${b.target} 吗？\n\n${b.name}\n\n当前内容会先被自动备份一份。`)) return;
  try {
    await api('/api/restore', { name: b.name });
    toast('已还原 ' + b.target, 'ok', '录制程序约 3 秒后按新配置运行');
    const cfg = await api('/api/config');
    S.values = cfg.values; S.edits.clear(); renderForms(); updateDirtyBar();
    await refreshRooms().catch(() => {});
    refreshBackups();
  } catch (e) { toast(e.message, 'err'); }
}

async function refreshLogs() {
  try {
    const d = await api('/api/logs?lines=300');
    $('#log-box').textContent = d.missing ? '（还没有日志文件）' : (d.lines.join('\n') || '（空）');
    $('#log-box').scrollTop = $('#log-box').scrollHeight;
  } catch (e) { $('#log-box').textContent = '读取失败：' + e.message; }
}

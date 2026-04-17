function escapeHtml(s) {
  const d = document.createElement("div");
  d.textContent = s == null ? "" : String(s);
  return d.innerHTML;
}

function formatBytes(n) {
  if (!n && n !== 0) return "—";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let i = 0;
  let v = n;
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024;
    i += 1;
  }
  return `${v.toFixed(v >= 10 || i === 0 ? 0 : 1)} ${units[i]}`;
}

function formatTimestamp(ts) {
  if (!ts) return "—";
  const d = new Date(ts * 1000);
  return d.toLocaleString();
}

const state = {
  cameras: [],
  activeCamId: null,
  offset: 0,
  limit: 50,
};

async function loadSummary() {
  const res = await fetch("/api/recordings");
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

async function loadCamera(camId, offset, limit) {
  const res = await fetch(
    `/api/recordings/${encodeURIComponent(camId)}?offset=${offset}&limit=${limit}`,
  );
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

function renderCamList(summary) {
  const list = document.getElementById("cam-list");
  list.innerHTML = "";
  for (const cam of summary.cameras) {
    const li = document.createElement("button");
    li.className = "cam-item";
    li.dataset.id = cam.id;
    if (cam.id === state.activeCamId) li.classList.add("active");
    li.innerHTML =
      `<span class="cam-item-name">${escapeHtml(cam.name)}</span>` +
      `<span class="cam-item-meta muted">${cam.count} · ${escapeHtml(formatBytes(cam.size_bytes))}</span>`;
    li.addEventListener("click", () => selectCamera(cam.id));
    list.appendChild(li);
  }
  const summaryEl = document.getElementById("summary");
  summaryEl.textContent =
    `${summary.total_recordings} recording(s) across ${summary.cameras.length} camera(s) · ${formatBytes(summary.total_bytes)} total`;
}

async function selectCamera(camId) {
  state.activeCamId = camId;
  state.offset = 0;
  document.querySelectorAll(".cam-item").forEach((el) => {
    el.classList.toggle("active", el.dataset.id === camId);
  });
  const cam = state.cameras.find((c) => c.id === camId);
  document.getElementById("cam-name").textContent = cam ? cam.name : camId;
  await renderRecordings();
}

async function renderRecordings() {
  const list = document.getElementById("rec-list");
  const pager = document.getElementById("pager");
  const meta = document.getElementById("cam-meta");
  list.innerHTML = `<li class="muted">Loading…</li>`;
  pager.innerHTML = "";
  try {
    const page = await loadCamera(state.activeCamId, state.offset, state.limit);
    meta.textContent = `${page.total} recording(s)`;
    if (!page.items.length) {
      list.innerHTML = `<li class="muted">No recordings.</li>`;
      return;
    }
    list.innerHTML = "";
    for (const item of page.items) {
      const li = document.createElement("li");
      li.className = "rec-item";
      li.innerHTML =
        `<button class="rec-play" aria-label="Play">▶</button>` +
        `<div class="rec-meta">` +
        `<span class="rec-started">${escapeHtml(formatTimestamp(item.started_at || item.mtime))}</span>` +
        `<span class="rec-size muted">${escapeHtml(formatBytes(item.size_bytes))}</span>` +
        `<span class="rec-name muted">${escapeHtml(item.filename)}</span>` +
        `</div>` +
        `<a class="rec-dl" href="${escapeHtml(item.url)}" download>Download</a>`;
      li.querySelector(".rec-play").addEventListener("click", () => {
        const player = document.getElementById("player");
        player.style.display = "block";
        player.src = item.url;
        player.play().catch(() => {});
      });
      list.appendChild(li);
    }
    const totalPages = Math.ceil(page.total / state.limit);
    const currentPage = Math.floor(state.offset / state.limit) + 1;
    if (totalPages > 1) {
      const prev = document.createElement("button");
      prev.textContent = "← Newer";
      prev.disabled = state.offset === 0;
      prev.addEventListener("click", () => {
        state.offset = Math.max(0, state.offset - state.limit);
        renderRecordings();
      });
      const next = document.createElement("button");
      next.textContent = "Older →";
      next.disabled = state.offset + state.limit >= page.total;
      next.addEventListener("click", () => {
        state.offset += state.limit;
        renderRecordings();
      });
      const info = document.createElement("span");
      info.className = "muted";
      info.textContent = `Page ${currentPage} / ${totalPages}`;
      pager.appendChild(prev);
      pager.appendChild(info);
      pager.appendChild(next);
    }
  } catch (e) {
    list.innerHTML = `<li class="err">${escapeHtml(e.message || String(e))}</li>`;
  }
}

async function init() {
  try {
    const summary = await loadSummary();
    state.cameras = summary.cameras;
    renderCamList(summary);
    const firstWithRecordings = summary.cameras.find((c) => c.count > 0) || summary.cameras[0];
    if (firstWithRecordings) {
      await selectCamera(firstWithRecordings.id);
    }
  } catch (e) {
    document.getElementById("summary").textContent =
      `Failed to load: ${e.message || e}`;
  }
}

init();

function escapeHtml(s) {
  const d = document.createElement("div");
  d.textContent = s == null ? "" : String(s);
  return d.innerHTML;
}

function attachHls(video, url) {
  if (window.Hls && window.Hls.isSupported()) {
    const hls = new Hls({
      enableWorker: true,
      lowLatencyMode: true,
      backBufferLength: 30,
    });
    hls.loadSource(url);
    hls.attachMedia(video);
    hls.on(window.Hls.Events.ERROR, (_, data) => {
      if (data.fatal) {
        console.warn("HLS fatal error", data);
        if (data.type === window.Hls.ErrorTypes.NETWORK_ERROR) {
          hls.startLoad();
        } else if (data.type === window.Hls.ErrorTypes.MEDIA_ERROR) {
          hls.recoverMediaError();
        }
      }
    });
    return hls;
  }
  if (video.canPlayType("application/vnd.apple.mpegurl")) {
    video.src = url;
    return null;
  }
  throw new Error("HLS not supported in this browser.");
}

function stateLabel(cam) {
  const hls = (cam.pipelines && cam.pipelines.hls) || {};
  const rec = (cam.pipelines && cam.pipelines.record) || {};
  const parts = [];
  const label = (role, st) => {
    if (!st || !st.configured) return null;
    return `${role}: ${st.state || "?"}`;
  };
  const hlsLbl = label("live", hls);
  const recLbl = label("record", rec);
  if (hlsLbl) parts.push(hlsLbl);
  if (recLbl) parts.push(recLbl);
  if (cam.hls_playlist_age_s != null) {
    parts.push(`age ${cam.hls_playlist_age_s.toFixed(1)}s`);
  }
  return parts.join(" · ") || "—";
}

function overallState(cam) {
  const hls = cam.pipelines && cam.pipelines.hls;
  const rec = cam.pipelines && cam.pipelines.record;
  const active = [hls, rec].filter((p) => p && p.configured);
  if (active.length === 0) return "disabled";
  if (active.some((p) => p.state === "failed")) return "failed";
  if (hls && hls.configured) {
    if (!hls.running) return hls.state === "restarting" ? "restarting" : "pending";
    if (cam.hls_fresh === false) return "stalled";
    return "ok";
  }
  if (active.every((p) => p.running)) return "ok";
  return "pending";
}

async function refreshHealth(cards) {
  try {
    const res = await fetch("/api/health");
    if (!res.ok) return;
    const data = await res.json();
    for (const cam of data.cameras) {
      const card = cards.get(cam.id);
      if (!card) continue;
      const state = overallState(cam);
      const dot = card.querySelector(".dot");
      const status = card.querySelector(".status");
      dot.dataset.state = state;
      dot.title = state;
      status.textContent = stateLabel(cam);
    }
  } catch (e) {
    console.warn("health poll failed", e);
  }
}

async function init() {
  const grid = document.getElementById("grid");
  const status = document.getElementById("status");
  try {
    const res = await fetch("/api/cameras");
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const cameras = await res.json();
    const liveCameras = cameras.filter((c) => c.live && c.hls_url);
    status.textContent = `${liveCameras.length} live camera(s)`;
    grid.innerHTML = "";
    const cards = new Map();
    for (const cam of liveCameras) {
      const card = document.createElement("article");
      card.className = "card";
      card.innerHTML =
        `<header class="card-head">` +
        `<span class="dot" data-state="pending" title="pending"></span>` +
        `<h2>${escapeHtml(cam.name)}</h2>` +
        `<span class="meta muted">${escapeHtml(cam.id)}</span>` +
        `</header>` +
        `<video controls muted playsinline></video>` +
        `<p class="status muted">connecting…</p>`;
      const video = card.querySelector("video");
      grid.appendChild(card);
      cards.set(cam.id, card);
      try {
        attachHls(video, cam.hls_url);
      } catch (e) {
        const p = document.createElement("p");
        p.className = "err";
        p.textContent = e.message || String(e);
        card.appendChild(p);
      }
    }
    if (liveCameras.length === 0) {
      grid.innerHTML = `<p class="muted" style="padding:1rem 1.5rem">No live cameras enabled. Set <code>live: true</code> in config/cameras.yaml.</p>`;
      return;
    }
    refreshHealth(cards);
    setInterval(() => refreshHealth(cards), 3000);
  } catch (e) {
    status.textContent = "Failed to load cameras.";
    grid.innerHTML =
      `<p class="err" style="padding:1rem 1.5rem">${escapeHtml(e.message || String(e))}</p>`;
  }
}

init();

function escapeHtml(s) {
  const d = document.createElement("div");
  d.textContent = s == null ? "" : String(s);
  return d.innerHTML;
}

function attachHls(video, url, targetLatencySeconds) {
  if (window.Hls && window.Hls.isSupported()) {
    const latency = Math.max(2, Number(targetLatencySeconds || 3));
    const hls = new Hls({
      enableWorker: true,
      lowLatencyMode: true,
      liveSyncDuration: latency,
      liveMaxLatencyDuration: latency * 2,
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

function multiscreenState(ms) {
  if (!ms || !ms.pipeline || !ms.pipeline.configured) return "disabled";
  if (ms.pipeline.state === "failed") return "failed";
  if (!ms.pipeline.running) {
    return ms.pipeline.state === "restarting" ? "restarting" : "pending";
  }
  if (ms.hls_fresh === false) return "stalled";
  return "ok";
}

function multiscreenLabel(ms) {
  if (!ms || !ms.pipeline || !ms.pipeline.configured) return "disabled";
  const parts = [`live: ${ms.pipeline.state || "?"}`];
  if (ms.hls_playlist_age_s != null) {
    parts.push(`age ${ms.hls_playlist_age_s.toFixed(1)}s`);
  }
  return parts.join(" · ");
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
    const ms = data.multiscreen;
    if (ms && ms.active && ms.output_id) {
      const card = cards.get(ms.output_id);
      if (card) {
        const state = multiscreenState(ms);
        const dot = card.querySelector(".dot");
        const status = card.querySelector(".status");
        dot.dataset.state = state;
        dot.title = state;
        status.textContent = multiscreenLabel(ms);
      }
    }
  } catch (e) {
    console.warn("health poll failed", e);
  }
}

async function init() {
  const grid = document.getElementById("grid");
  const status = document.getElementById("status");
  const tabSingles = document.getElementById("tab-singles");
  const tabMultiscreen = document.getElementById("tab-multiscreen");
  let selectedView = "singles";
  let cards = new Map();

  const setActiveTab = (view, hasMultiscreen) => {
    selectedView = view;
    tabSingles.classList.toggle("active", view === "singles");
    tabSingles.setAttribute("aria-selected", String(view === "singles"));
    tabMultiscreen.classList.toggle("active", view === "multiscreen");
    tabMultiscreen.setAttribute("aria-selected", String(view === "multiscreen"));
    tabMultiscreen.disabled = !hasMultiscreen;
  };

  const renderCard = (cam) => {
    const card = document.createElement("article");
    card.className = "card";
    card.innerHTML =
      `<header class="card-head">` +
      `<span class="dot" data-state="pending" title="pending"></span>` +
      `<h2>${escapeHtml(cam.name)}</h2>` +
      `<span class="meta muted">${escapeHtml(cam.id)}</span>` +
      `</header>` +
      `<video controls muted autoplay playsinline></video>` +
      `<p class="status muted">connecting…</p>`;
    const video = card.querySelector("video");
    grid.appendChild(card);
    cards.set(cam.id, card);
    try {
      attachHls(video, cam.hls_url, cam.target_latency_seconds);
    } catch (e) {
      const p = document.createElement("p");
      p.className = "err";
      p.textContent = e.message || String(e);
      card.appendChild(p);
    }
  };

  try {
    const [camsRes, msRes] = await Promise.all([
      fetch("/api/cameras"),
      fetch("/api/multiscreen"),
    ]);
    if (!camsRes.ok) throw new Error(`HTTP ${camsRes.status}`);
    const cameras = await camsRes.json();
    const multiscreen = msRes.ok ? await msRes.json() : null;
    const liveCameras = cameras.filter((c) => c.live && c.hls_url);
    const hasMultiscreen = !!(multiscreen && multiscreen.active && multiscreen.hls_url);
    const renderView = () => {
      grid.innerHTML = "";
      cards = new Map();
      if (selectedView === "multiscreen") {
        if (!hasMultiscreen) {
          status.textContent = "Multiscreen is not active.";
          grid.innerHTML =
            `<p class="muted" style="padding:1rem 1.5rem">Multiscreen is disabled or unavailable. Enable <code>multiscreen.enabled: true</code> in config/cameras.yaml.</p>`;
          return;
        }
        status.textContent = "1 live stream (multiscreen)";
        renderCard({
          id: multiscreen.output_id,
          name: "Multiscreen",
          hls_url: multiscreen.hls_url,
        });
        return;
      }
      status.textContent = `${liveCameras.length} live camera(s)`;
      for (const cam of liveCameras) {
        renderCard(cam);
      }
      if (liveCameras.length === 0) {
        grid.innerHTML = `<p class="muted" style="padding:1rem 1.5rem">No live cameras enabled. Set <code>live: true</code> in config/cameras.yaml.</p>`;
      }
    };

    setActiveTab(selectedView, hasMultiscreen);
    renderView();

    tabSingles.addEventListener("click", () => {
      if (selectedView === "singles") return;
      setActiveTab("singles", hasMultiscreen);
      renderView();
    });
    tabMultiscreen.addEventListener("click", () => {
      if (!hasMultiscreen || selectedView === "multiscreen") return;
      setActiveTab("multiscreen", hasMultiscreen);
      renderView();
    });

    if (!hasMultiscreen && selectedView === "multiscreen") {
      setActiveTab("singles", hasMultiscreen);
      renderView();
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

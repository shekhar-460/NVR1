function escapeHtml(s) {
  const d = document.createElement("div");
  d.textContent = s == null ? "" : String(s);
  return d.innerHTML;
}

function cameraIdFromPath() {
  const parts = window.location.pathname.replace(/\/+$/, "").split("/");
  if (parts.length >= 3 && parts[1] === "cam") return parts[2];
  return null;
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

function setCardLoading(card, isLoading, message) {
  card.classList.toggle("is-loading", isLoading);
  const loader = card.querySelector(".stream-loader-text");
  if (loader && message) loader.textContent = message;
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

async function refreshHealth(card, cameraId) {
  try {
    const res = await fetch("/api/health");
    if (!res.ok) return;
    const data = await res.json();
    const cam = data.cameras.find((c) => c.id === cameraId);
    if (!cam) return;
    const state = overallState(cam);
    const dot = card.querySelector(".dot");
    const status = card.querySelector(".status");
    dot.dataset.state = state;
    dot.title = state;
    status.textContent = stateLabel(cam);
    setCardLoading(card, state !== "ok", "Waiting for stream…");
  } catch (e) {
    console.warn("health poll failed", e);
  }
}

async function init() {
  const cameraId = cameraIdFromPath();
  const single = document.getElementById("single");
  const status = document.getElementById("status");
  const pageTitle = document.getElementById("page-title");
  const pageSubtitle = document.getElementById("page-subtitle");

  if (!cameraId) {
    status.textContent = "Camera not specified.";
    single.innerHTML =
      `<p class="err" style="padding:1rem 0">Invalid URL. Open <a href="/">all cameras</a> and pick a stream.</p>`;
    return;
  }

  try {
    const res = await fetch("/api/cameras");
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const cameras = await res.json();
    const cam = cameras.find((c) => c.id === cameraId);
    if (!cam) {
      status.textContent = "Camera not found.";
      single.innerHTML =
        `<p class="err" style="padding:1rem 0">Unknown camera <code>${escapeHtml(cameraId)}</code>. <a href="/">Back</a></p>`;
      return;
    }
    if (!cam.live || !cam.hls_url) {
      status.textContent = "Camera not live.";
      single.innerHTML =
        `<p class="err" style="padding:1rem 0"><strong>${escapeHtml(cam.name)}</strong> is not enabled for live view. <a href="/">Back</a></p>`;
      return;
    }

    document.title = `NVR — ${cam.name}`;
    pageTitle.textContent = cam.name;
    pageSubtitle.textContent = `${cam.id} · single stream`;

    const card = document.createElement("article");
    card.className = "card card--solo";
    card.innerHTML =
      `<header class="card-head">` +
      `<span class="dot" data-state="pending" title="pending"></span>` +
      `<h2>${escapeHtml(cam.name)}</h2>` +
      `<span class="meta muted">${escapeHtml(cam.id)}</span>` +
      `</header>` +
      `<div class="stream-wrap stream-wrap--solo">` +
      `<video controls muted autoplay playsinline></video>` +
      `<div class="stream-loader" aria-live="polite">` +
      `<span class="stream-loader-spinner" aria-hidden="true"></span>` +
      `<span class="stream-loader-text">Waiting for stream…</span>` +
      `</div>` +
      `</div>` +
      `<p class="status muted">connecting…</p>` +
      `<p class="stream-url muted"><a href="${escapeHtml(cam.hls_url)}">${escapeHtml(cam.hls_url)}</a></p>`;

    const video = card.querySelector("video");
    const onLoading = () => setCardLoading(card, true, "Waiting for stream…");
    const onPlaying = () => setCardLoading(card, false);
    video.addEventListener("loadstart", onLoading);
    video.addEventListener("waiting", onLoading);
    video.addEventListener("stalled", onLoading);
    video.addEventListener("error", onLoading);
    video.addEventListener("canplay", onPlaying);
    video.addEventListener("playing", onPlaying);
    single.appendChild(card);
    onLoading();

    try {
      attachHls(video, cam.hls_url, cam.target_latency_seconds);
    } catch (e) {
      const p = document.createElement("p");
      p.className = "err";
      p.textContent = e.message || String(e);
      card.appendChild(p);
    }

    status.textContent = "Live";
    refreshHealth(card, cameraId);
    setInterval(() => refreshHealth(card, cameraId), 3000);
  } catch (e) {
    status.textContent = "Failed to load camera.";
    single.innerHTML =
      `<p class="err" style="padding:1rem 0">${escapeHtml(e.message || String(e))}</p>`;
  }
}

init();

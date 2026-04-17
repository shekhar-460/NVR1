function escapeHtml(s) {
  const d = document.createElement("div");
  d.textContent = s;
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
    return;
  }
  if (video.canPlayType("application/vnd.apple.mpegurl")) {
    video.src = url;
    return;
  }
  throw new Error("HLS not supported in this browser.");
}

async function init() {
  const grid = document.getElementById("grid");
  const status = document.getElementById("status");
  try {
    const res = await fetch("/api/cameras");
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const cameras = await res.json();
    status.textContent = `${cameras.length} camera(s) — HLS loading…`;
    grid.innerHTML = "";
    for (const cam of cameras) {
      const card = document.createElement("article");
      card.className = "card";
      card.innerHTML =
        `<h2>${escapeHtml(cam.name)}</h2>` +
        `<p class="meta muted">${escapeHtml(cam.id)}</p>` +
        `<video controls muted playsinline></video>`;
      const video = card.querySelector("video");
      grid.appendChild(card);
      try {
        attachHls(video, cam.hls_url);
      } catch (e) {
        const p = document.createElement("p");
        p.className = "err";
        p.textContent = e.message || String(e);
        card.appendChild(p);
      }
    }
    status.textContent = `${cameras.length} camera(s)`;
  } catch (e) {
    status.textContent = "Failed to load cameras.";
    grid.innerHTML =
      `<p class="err" style="padding:1rem 1.5rem">${escapeHtml(e.message || String(e))}</p>`;
  }
}

init();

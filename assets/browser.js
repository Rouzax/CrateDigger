"use strict";
const A = "assets/";
let DATA = null;
let layout = "artist_flat";

async function init() {
  DATA = await (await fetch(A + "library.json")).json();
  document.getElementById("browser-layout").addEventListener("change", (e) => {
    layout = e.target.value;
    renderTree();
    clearStage();
  });
  renderTree();
}
document.addEventListener("DOMContentLoaded", init);

function renderTree() {
  const root = document.getElementById("browser-tree");
  root.innerHTML = "";
  for (const node of DATA.trees[layout]) root.appendChild(renderNode(node, 0));
}

function renderNode(node, depth) {
  const el = document.createElement("div");
  el.className = "tree-node depth-" + depth;
  const row = document.createElement("button");
  row.className = "tree-row tree-" + node.type;
  row.textContent = (node.type === "folder" ? "📁 " : "🎬 ") + node.label;
  el.appendChild(row);
  if (node.type === "folder") {
    const kids = document.createElement("div");
    kids.className = "tree-kids";
    for (const c of node.children) kids.appendChild(renderNode(c, depth + 1));
    row.addEventListener("click", () => {
      kids.classList.toggle("open");
      if (node.poster) showPoster(node.poster, node.label);
    });
    el.appendChild(kids);
  } else {
    row.addEventListener("click", () => showSet(node.id));
  }
  return el;
}

function showPoster(file, alt) {
  const img = document.getElementById("browser-poster");
  img.src = A + file; img.alt = alt;
  document.getElementById("browser-meta").hidden = true;
}
function clearStage() {
  const img = document.getElementById("browser-poster");
  img.removeAttribute("src"); img.alt = "";
  document.getElementById("browser-meta").hidden = true;
}
function showSet(id) {
  const s = DATA.sets[id];
  showPoster(s.set_poster, s.title);
  const meta = document.getElementById("browser-meta");
  meta.hidden = false;
  const chapters = s.chapters.map(
    (c) => `<li><span class="t">${c.time}</span> ${escapeHtml(c.title)}</li>`).join("");
  meta.innerHTML = `
    <h3>${escapeHtml(s.title)}</h3>
    <dl>
      <dt>Artists</dt><dd>${s.artists.map(escapeHtml).join(", ")}</dd>
      <dt>Album</dt><dd>${escapeHtml(s.album)}</dd>
      <dt>Premiered</dt><dd>${escapeHtml(s.premiered)}</dd>
      <dt>Genres</dt><dd>${s.genres.map(escapeHtml).join(", ")}</dd>
      <dt>Stage</dt><dd>${escapeHtml(s.studio)}</dd>
      <dt>Runtime</dt><dd>${escapeHtml(s.runtime)} min</dd>
      <dt>Tags</dt><dd>${s.tags.map(escapeHtml).join(", ")}</dd>
    </dl>
    <h4>Tracklist (${s.chapters.length})</h4>
    <ol class="tracklist">${chapters}</ol>`;
}
function escapeHtml(t) {
  return String(t).replace(/[&<>"']/g, (c) => (
    {"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[c]));
}

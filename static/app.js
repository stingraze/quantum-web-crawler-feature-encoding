const el = {
  seedUrl: document.getElementById("seedUrl"),
  maxPages: document.getElementById("maxPages"),
  maxDepth: document.getElementById("maxDepth"),
  concurrency: document.getElementById("concurrency"),
  requestTimeout: document.getElementById("requestTimeout"),
  maxQuantumPages: document.getElementById("maxQuantumPages"),
  sameDomainOnly: document.getElementById("sameDomainOnly"),
  startBtn: document.getElementById("startBtn"),
  stopBtn: document.getElementById("stopBtn"),
  runStatus: document.getElementById("runStatus"),
  statsGrid: document.getElementById("statsGrid"),
  nodeDetails: document.getElementById("nodeDetails"),
  circuitImage: document.getElementById("circuitImage"),
  circuitPlaceholder: document.getElementById("circuitPlaceholder"),
  featureCards: document.getElementById("featureCards"),
  logList: document.getElementById("logList"),
  graphSvg: document.getElementById("graphSvg"),
  graphTooltip: document.getElementById("graphTooltip"),
};

const state = {
  selectedNodeId: null,
  source: null,
  graph: { nodes: [], edges: [] },
  meta: {},
  latestCircuitMeta: null,
  pageQuantum: new Map(),
  graphView: {
    initialized: false,
    width: 800,
    height: 560,
    svg: null,
    root: null,
    linkLayer: null,
    nodeLayer: null,
    labelLayer: null,
    simulation: null,
    zoom: null,
    simNodes: [],
    simNodeById: new Map(),
    simEdges: [],
  },
};

const STATUS_COLORS = {
  queued: "var(--status-queued)",
  fetching: "var(--status-fetching)",
  crawled: "var(--status-crawled)",
  quantum_skipped_limit: "var(--status-fetching)",
  error: "var(--status-error)",
  unknown: "var(--status-unknown)",
};

async function api(path, options = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(data.error || `Request failed: ${res.status}`);
  }
  return data;
}

function logMessage(message, type = "info") {
  const row = document.createElement("div");
  row.className = `log-item ${type}`;
  row.textContent = message;
  el.logList.prepend(row);
  while (el.logList.children.length > 120) {
    el.logList.removeChild(el.logList.lastChild);
  }
}

function renderStats(meta = {}) {
  const cards = [
    ["Nodes", meta.node_count ?? 0],
    ["Edges", meta.edge_count ?? 0],
    ["Queued", meta.queued_count ?? 0],
    ["Visited", meta.visited_count ?? 0],
    ["Extracted", meta.extracted_count ?? 0],
    ["Quantum cap", meta.config?.max_quantum_pages ?? 0],
    ["Errors", meta.error_count ?? 0],
    ["Duration", `${meta.duration_sec ?? 0}s`],
  ];
  el.statsGrid.innerHTML = cards
    .map(
      ([label, value]) => `
        <div class="stat-card">
          <div class="stat-label">${label}</div>
          <div class="stat-value">${value}</div>
        </div>
      `,
    )
    .join("");

  const running = !!meta.running;
  el.runStatus.textContent = running ? "Running" : "Idle";
  el.runStatus.classList.toggle("running", running);
  el.runStatus.classList.toggle("idle", !running);
}

function renderDetails() {
  const node = state.graph.nodes.find((n) => n.id === state.selectedNodeId);
  if (!node) {
    el.nodeDetails.innerHTML = "Select a node to inspect the crawled page, URL, depth, and extracted features.";
    return;
  }

  const quantumRecord = state.pageQuantum.get(node.url) || null;
  const featureSource = quantumRecord?.features || node.features || {};
  const featureEntries = Object.entries(featureSource);
  const featuresHtml = featureEntries.length
    ? featureEntries
        .map(
          ([key, value]) => `
            <div class="mini-feature-row">
              <span>${key}</span>
              <strong>${Number(value).toFixed(3)}</strong>
            </div>
          `,
        )
        .join("")
    : '<div class="details-empty">No extracted features yet.</div>';

  el.nodeDetails.innerHTML = `
    <div class="detail-stack">
      <div class="detail-header-row">
        <span class="status-dot" style="background:${STATUS_COLORS[node.status] || STATUS_COLORS.unknown}"></span>
        <strong>${escapeHtml(node.label || node.url)}</strong>
      </div>
      <div class="detail-meta"><span>Status</span><strong>${escapeHtml(quantumRecord?.status || node.status)}</strong></div>
      <div class="detail-meta"><span>Depth</span><strong>${quantumRecord?.depth ?? node.depth ?? 0}</strong></div>
      <div class="detail-meta"><span>Domain</span><strong>${escapeHtml(node.domain || "")}</strong></div>
      <div class="detail-meta"><span>Quantum</span><strong>${quantumRecord?.has_circuit ? "Extracted" : (quantumRecord?.status === "quantum_skipped_limit" ? "Skipped by limit" : "Pending")}</strong></div>
      <div class="detail-url">${escapeHtml(node.url || "")}</div>
      ${node.title ? `<div class="detail-title">${escapeHtml(node.title)}</div>` : ""}
      ${(quantumRecord?.error || node.error) ? `<div class="detail-error">${escapeHtml(quantumRecord?.error || node.error)}</div>` : ""}
      <div class="detail-divider"></div>
      <div class="mini-feature-grid">${featuresHtml}</div>
    </div>
  `;
}

function renderCircuit(meta = state.latestCircuitMeta, imageUrl = null) {
  state.latestCircuitMeta = meta || null;
  const hasCircuit = !!meta;
  el.circuitImage.style.display = hasCircuit ? "block" : "none";
  el.circuitPlaceholder.style.display = hasCircuit ? "none" : "grid";

  if (!hasCircuit) {
    el.featureCards.innerHTML = "";
    return;
  }

  el.circuitImage.src = imageUrl || `/api/circuit/latest.png?t=${Date.now()}`;
  const features = Object.entries(meta.features || {});
  el.featureCards.innerHTML = `
    <div class="feature-card lead">
      <div class="feature-name">Page</div>
      <div class="feature-value">${escapeHtml(meta.title || meta.url || "Untitled")}</div>
      <div class="feature-subvalue">Depth ${meta.depth ?? 0}</div>
    </div>
    ${features
      .map(
        ([name, value]) => `
          <div class="feature-card">
            <div class="feature-name">${escapeHtml(name)}</div>
            <div class="feature-value">${Number(value).toFixed(3)}</div>
            <div class="feature-bar"><span style="width:${Math.max(4, Math.round(Number(value) * 100))}%"></span></div>
          </div>
        `,
      )
      .join("")}
  `;
}


function ingestPageQuantum(items = []) {
  state.pageQuantum = new Map((items || []).map((item) => [item.url, item]));
}

async function renderCircuitForSelectedNode() {
  const node = state.graph.nodes.find((n) => n.id === state.selectedNodeId);
  if (!node) {
    renderCircuit(null);
    return;
  }

  const record = state.pageQuantum.get(node.url);
  if (!record?.has_circuit) {
    if (state.latestCircuitMeta && state.latestCircuitMeta.url === node.url) {
      renderCircuit(state.latestCircuitMeta);
    } else {
      renderCircuit(null);
    }
    return;
  }

  try {
    const data = await api(`/api/page-quantum?url=${encodeURIComponent(node.url)}`);
    const item = data.item || record;
    state.pageQuantum.set(node.url, item);
    renderCircuit(item, `/api/circuit/by-url.png?url=${encodeURIComponent(node.url)}&t=${Date.now()}`);
  } catch (error) {
    logMessage(error.message, "error");
    renderCircuit(null);
  }
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function mountStream() {
  if (state.source) {
    state.source.close();
  }

  const source = new EventSource("/api/stream");
  state.source = source;

  source.addEventListener("snapshot", (event) => {
    const payload = JSON.parse(event.data);
    state.graph = payload.graph || { nodes: [], edges: [] };
    state.meta = payload.meta || {};
    ingestPageQuantum(payload.page_quantum || []);
    renderStats(state.meta);
    renderGraph();
    renderDetails();
    if (payload.latest_circuit_meta) {
      renderCircuit(payload.latest_circuit_meta);
    }
    if (state.selectedNodeId) {
      renderCircuitForSelectedNode();
    }
    if (payload.message) {
      logMessage(payload.message, "snapshot");
    }
  });

  source.addEventListener("error", (event) => {
    if (event?.data) {
      try {
        const payload = JSON.parse(event.data);
        logMessage(payload.message || "Crawler error", "error");
      } catch {
        logMessage("Crawler error", "error");
      }
    }
  });

  source.onerror = () => {
    logMessage("Stream disconnected. Retrying automatically.", "warn");
  };
}

function initGraphRenderer() {
  if (state.graphView.initialized) {
    return;
  }

  const view = state.graphView;
  const svg = d3.select(el.graphSvg);
  view.svg = svg;
  updateGraphViewport();

  const defs = svg.append("defs");

  const glow = defs
    .append("filter")
    .attr("id", "nodeGlow")
    .attr("x", "-80%")
    .attr("y", "-80%")
    .attr("width", "260%")
    .attr("height", "260%");

  glow.append("feGaussianBlur").attr("stdDeviation", "3.5").attr("result", "blur");
  glow
    .append("feColorMatrix")
    .attr("in", "blur")
    .attr("type", "matrix")
    .attr(
      "values",
      "1 0 0 0 0  0 1 0 0 0  0 0 1 0 0  0 0 0 0.55 0",
    )
    .attr("result", "glowColor");
  const merge = glow.append("feMerge");
  merge.append("feMergeNode").attr("in", "glowColor");
  merge.append("feMergeNode").attr("in", "SourceGraphic");

  view.root = svg.append("g").attr("class", "graph-root");
  view.linkLayer = view.root.append("g").attr("class", "links");
  view.nodeLayer = view.root.append("g").attr("class", "nodes");
  view.labelLayer = view.root.append("g").attr("class", "labels");

  view.zoom = d3
    .zoom()
    .scaleExtent([0.35, 3.5])
    .on("zoom", (event) => {
      view.root.attr("transform", event.transform);
    });

  svg.call(view.zoom).on("dblclick.zoom", null);

  view.simulation = d3
    .forceSimulation([])
    .force(
      "link",
      d3
        .forceLink([])
        .id((d) => d.id)
        .distance((d) => edgeDistance(d))
        .strength((d) => edgeStrength(d)),
    )
    .force("charge", d3.forceManyBody().strength((d) => -140 - Math.min(90, (d.outDegree || 0) * 10)))
    .force("x", d3.forceX((d) => d.targetX).strength(0.08))
    .force("y", d3.forceY((d) => d.targetY).strength(0.08))
    .force("collide", d3.forceCollide((d) => 16 + Math.min(14, (d.depth || 0) * 2.5)).iterations(2))
    .force("bounds", createBoundsForce(() => state.graphView.width, () => state.graphView.height, 26))
    .alphaMin(0.02)
    .alphaDecay(0.035)
    .velocityDecay(0.18)
    .on("tick", tickGraph);

  window.addEventListener("resize", handleResize);
  state.graphView.initialized = true;
}

function handleResize() {
  updateGraphViewport();
  if (state.graph.nodes.length) {
    renderGraph();
  }
}

function updateGraphViewport() {
  const wrap = el.graphSvg.getBoundingClientRect();
  state.graphView.width = Math.max(800, wrap.width || 800);
  state.graphView.height = Math.max(560, wrap.height || 560);
  state.graphView.svg.attr("viewBox", `0 0 ${state.graphView.width} ${state.graphView.height}`);
}

function renderGraph() {
  initGraphRenderer();
  updateGraphViewport();

  const view = state.graphView;
  const dataNodes = state.graph.nodes.map((d) => ({ ...d }));
  const dataEdges = state.graph.edges.map((d) => ({ ...d }));

  const xExtent = d3.extent(dataNodes, (d) => d.x || 0);
  const yExtent = d3.extent(dataNodes, (d) => d.y || 0);
  const pad = 72;
  const xScale = d3.scaleLinear().domain(expandExtent(xExtent)).range([pad, view.width - pad]);
  const yScale = d3.scaleLinear().domain(expandExtent(yExtent)).range([pad, view.height - pad]);

  const nextSimNodes = [];
  const nextById = new Map();
  const incomingIds = new Set();

  for (const node of dataNodes) {
    incomingIds.add(node.id);
    const targetX = xScale(node.x || 0);
    const targetY = yScale(node.y || 0);
    const existing = view.simNodeById.get(node.id);

    if (existing) {
      Object.assign(existing, node, {
        targetX,
        targetY,
        x: Number.isFinite(existing.x) ? existing.x : targetX,
        y: Number.isFinite(existing.y) ? existing.y : targetY,
      });
      existing.labelShort = truncateLabel(node.label || node.url || "", 18);
      existing.degree = 0;
      existing.outDegree = 0;
      nextSimNodes.push(existing);
      nextById.set(existing.id, existing);
    } else {
      const bornNearX = targetX + (Math.random() - 0.5) * 38;
      const bornNearY = targetY + (Math.random() - 0.5) * 38;
      const created = {
        ...node,
        targetX,
        targetY,
        x: bornNearX,
        y: bornNearY,
        vx: (Math.random() - 0.5) * 1.8,
        vy: (Math.random() - 0.5) * 1.8,
        degree: 0,
        outDegree: 0,
        labelShort: truncateLabel(node.label || node.url || "", 18),
      };
      nextSimNodes.push(created);
      nextById.set(created.id, created);
    }
  }

  const nextEdges = [];
  const edgeSeen = new Set();
  for (const edge of dataEdges) {
    if (!nextById.has(edge.source) || !nextById.has(edge.target)) {
      continue;
    }
    const key = `${edge.source}→${edge.target}`;
    if (edgeSeen.has(key)) {
      continue;
    }
    edgeSeen.add(key);

    const sourceNode = nextById.get(edge.source);
    const targetNode = nextById.get(edge.target);
    sourceNode.outDegree = (sourceNode.outDegree || 0) + 1;
    sourceNode.degree = (sourceNode.degree || 0) + 1;
    targetNode.degree = (targetNode.degree || 0) + 1;

    nextEdges.push({
      id: key,
      source: edge.source,
      target: edge.target,
      weight: Number(edge.weight || 1),
      sameDomain: sourceNode.domain && targetNode.domain && sourceNode.domain === targetNode.domain,
    });
  }

  view.simNodes = nextSimNodes;
  view.simNodeById = nextById;
  view.simEdges = nextEdges;

  const linkSelection = view.linkLayer
    .selectAll("path.edge-path")
    .data(view.simEdges, (d) => d.id)
    .join(
      (enter) =>
        enter
          .append("path")
          .attr("class", "edge-path")
          .attr("fill", "none")
          .attr("stroke", "rgba(148,163,184,0.28)")
          .attr("stroke-linecap", "round")
          .attr("stroke-width", (d) => 1 + Math.min(2.6, d.weight * 0.38))
          .attr("d", (d) => initialEdgePath(d, nextById)),
      (update) => update,
      (exit) => exit.transition().duration(220).style("opacity", 0).remove(),
    );

  const nodeSelection = view.nodeLayer
    .selectAll("circle.node-core")
    .data(view.simNodes, (d) => d.id)
    .join(
      (enter) =>
        enter
          .append("circle")
          .attr("class", "node-core")
          .attr("r", (d) => 8 + Math.min(7, d.depth || 0))
          .attr("fill", (d) => STATUS_COLORS[d.status] || STATUS_COLORS.unknown)
          .attr("stroke", "rgba(255,255,255,0.78)")
          .attr("stroke-width", (d) => (d.id === state.selectedNodeId ? 2.8 : 1.15))
          .attr("filter", "url(#nodeGlow)")
          .style("cursor", "pointer")
          .call((enterSel) =>
            enterSel
              .on("mouseenter", (_, d) => showTooltip(d))
              .on("mousemove", (event) => moveTooltip(event))
              .on("mouseleave", hideTooltip)
              .on("click", (_, d) => {
                state.selectedNodeId = d.id;
                renderDetails();
                renderCircuitForSelectedNode();
                refreshNodeStyles();
              })
              .call(
                d3
                  .drag()
                  .on("start", (event) => {
                    if (!event.active) view.simulation.alphaTarget(0.12).restart();
                  })
                  .on("drag", (event, d) => {
                    d.x = event.x;
                    d.y = event.y;
                    d.targetX = event.x;
                    d.targetY = event.y;
                  })
                  .on("end", (event) => {
                    if (!event.active) view.simulation.alphaTarget(0.04);
                  }),
              ),
          ),
      (update) => update,
      (exit) => exit.transition().duration(220).attr("r", 0).remove(),
    );

  const labelSelection = view.labelLayer
    .selectAll("text.node-label")
    .data(view.simNodes, (d) => d.id)
    .join(
      (enter) =>
        enter
          .append("text")
          .attr("class", "node-label")
          .attr("text-anchor", "middle")
          .attr("dy", 24)
          .text((d) => d.labelShort),
      (update) => update.text((d) => d.labelShort),
      (exit) => exit.transition().duration(180).style("opacity", 0).remove(),
    );

  view.linkSelection = linkSelection;
  view.nodeSelection = nodeSelection;
  view.labelSelection = labelSelection;

  refreshNodeStyles();

  view.simulation.nodes(view.simNodes);
  view.simulation.force("link").links(view.simEdges);
  view.simulation.alpha(Math.max(view.metaAlpha || 0.78, 0.72)).alphaTarget(0.045).restart();
  view.metaAlpha = 0.82;
}

function tickGraph() {
  const view = state.graphView;
  if (!view.initialized) {
    return;
  }

  view.linkSelection?.attr("d", (d) => curvedEdgePath(d));
  view.nodeSelection
    ?.attr("cx", (d) => d.x)
    .attr("cy", (d) => d.y);
  view.labelSelection
    ?.attr("x", (d) => d.x)
    .attr("y", (d) => d.y);
}

function refreshNodeStyles() {
  const view = state.graphView;
  view.nodeSelection
    ?.attr("fill", (d) => STATUS_COLORS[d.status] || STATUS_COLORS.unknown)
    .attr("stroke-width", (d) => (d.id === state.selectedNodeId ? 2.8 : 1.15))
    .attr("r", (d) => {
      const base = 8 + Math.min(7, d.depth || 0);
      return d.id === state.selectedNodeId ? base + 1.8 : base;
    });

  view.linkSelection?.attr("stroke", (d) =>
    d.sameDomain ? "rgba(121,167,255,0.32)" : "rgba(148,163,184,0.22)",
  );
}

function createBoundsForce(widthGetter, heightGetter, padding = 20) {
  let nodes = [];
  function force(alpha) {
    const width = widthGetter();
    const height = heightGetter();
    for (const node of nodes) {
      if (node.x < padding) node.vx += (padding - node.x) * 0.06 * alpha;
      if (node.x > width - padding) node.vx -= (node.x - (width - padding)) * 0.06 * alpha;
      if (node.y < padding) node.vy += (padding - node.y) * 0.06 * alpha;
      if (node.y > height - padding) node.vy -= (node.y - (height - padding)) * 0.06 * alpha;
    }
  }
  force.initialize = (newNodes) => {
    nodes = newNodes;
  };
  return force;
}

function edgeDistance(edge) {
  const base = edge.sameDomain ? 92 : 126;
  return base + Math.min(36, Number(edge.weight || 1) * 4);
}

function edgeStrength(edge) {
  return edge.sameDomain ? 0.12 : 0.06;
}

function curvedEdgePath(edge) {
  const source = typeof edge.source === "object" ? edge.source : state.graphView.simNodeById.get(edge.source);
  const target = typeof edge.target === "object" ? edge.target : state.graphView.simNodeById.get(edge.target);
  if (!source || !target) {
    return "";
  }

  const sx = source.x;
  const sy = source.y;
  const tx = target.x;
  const ty = target.y;
  const dx = tx - sx;
  const dy = ty - sy;
  const len = Math.max(1, Math.hypot(dx, dy));
  const nx = -dy / len;
  const ny = dx / len;
  const bendSign = stringHash(edge.id) % 2 === 0 ? 1 : -1;
  const bendAmount = Math.min(18, len * 0.1) * bendSign;
  const cx = (sx + tx) / 2 + nx * bendAmount;
  const cy = (sy + ty) / 2 + ny * bendAmount;
  return `M${sx},${sy} Q${cx},${cy} ${tx},${ty}`;
}

function initialEdgePath(edge, byId) {
  const source = byId.get(edge.source);
  const target = byId.get(edge.target);
  if (!source || !target) {
    return "";
  }
  return curvedEdgePath({ ...edge, source, target });
}

function stringHash(text) {
  let hash = 0;
  for (let i = 0; i < text.length; i += 1) {
    hash = ((hash << 5) - hash + text.charCodeAt(i)) | 0;
  }
  return Math.abs(hash);
}

function expandExtent(extent) {
  const lo = Number(extent[0] ?? -1);
  const hi = Number(extent[1] ?? 1);
  if (lo === hi) {
    return [lo - 1, hi + 1];
  }
  return [lo, hi];
}

function truncateLabel(label, maxLen) {
  if (label.length <= maxLen) return label;
  return `${label.slice(0, maxLen - 1)}…`;
}

function showTooltip(node) {
  el.graphTooltip.classList.remove("hidden");
  el.graphTooltip.innerHTML = `
    <div class="tooltip-title">${escapeHtml(node.title || node.label || node.url)}</div>
    <div>${escapeHtml(node.url || "")}</div>
    <div>Depth ${node.depth ?? 0} · ${escapeHtml(node.status || "unknown")}</div>
  `;
}

function moveTooltip(event) {
  const padding = 18;
  el.graphTooltip.style.left = `${event.pageX + padding}px`;
  el.graphTooltip.style.top = `${event.pageY + padding}px`;
}

function hideTooltip() {
  el.graphTooltip.classList.add("hidden");
}

async function startCrawl() {
  try {
    const body = {
      seed_url: el.seedUrl.value.trim(),
      max_pages: Number(el.maxPages.value),
      max_depth: Number(el.maxDepth.value),
      concurrency: Number(el.concurrency.value),
      request_timeout: Number(el.requestTimeout.value),
      max_quantum_pages: Number(el.maxQuantumPages.value),
      same_domain_only: el.sameDomainOnly.checked,
    };
    const data = await api("/api/crawl/start", {
      method: "POST",
      body: JSON.stringify(body),
    });
    logMessage(`Started crawl: ${data.config.seed_url}`, "snapshot");
  } catch (error) {
    logMessage(error.message, "error");
  }
}

async function stopCrawl() {
  try {
    await api("/api/crawl/stop", { method: "POST", body: "{}" });
    logMessage("Stop requested.", "warn");
  } catch (error) {
    logMessage(error.message, "error");
  }
}

async function boot() {
  el.startBtn.addEventListener("click", startCrawl);
  el.stopBtn.addEventListener("click", stopCrawl);

  const initial = await api("/api/state");
  state.graph = initial.graph || { nodes: [], edges: [] };
  state.meta = initial.meta || {};
  ingestPageQuantum(initial.page_quantum || []);
  renderStats(state.meta);
  renderGraph();
  renderDetails();
  if (initial.latest_circuit_meta) {
    renderCircuit(initial.latest_circuit_meta);
  }
  mountStream();
}

boot().catch((error) => {
  logMessage(error.message, "error");
});

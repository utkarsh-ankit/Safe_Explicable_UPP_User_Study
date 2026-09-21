(() => {
  const cfg = window.STUDY_CONFIG;
  const taskIndex = window.TASK_INDEX;
  const grid = document.getElementById("grid");
  const overlay = document.getElementById("pathOverlay");
  const statusBox = document.getElementById("statusBox");
  const routeSummary = document.getElementById("routeSummary");
  const submitButton = document.getElementById("submitButton");
  const errorBox = document.getElementById("submitError");
  const startTime = performance.now();
  const events = [];
  let trajectory = [cfg.start.slice()];

  const key = (p) => `${p[0]},${p[1]}`;
  const blockedCells = new Set((cfg.blocked_cells || []).map(key));
  const busy = new Set((cfg.visible_busy || []).map(key));
  const coffee = new Set((cfg.coffee || []).map(key));
  const roomByCell = new Map();
  Object.entries(cfg.room_cells || {}).forEach(([room, locations]) => {
    locations.forEach((loc) => roomByCell.set(key(loc), room));
  });
  const blockedEdges = new Set((cfg.blocked_edges || []).map(e => {
    const a = `${e[0]},${e[1]}`;
    const b = `${e[2]},${e[3]}`;
    return [a, b].sort().join("|");
  }));
  const cells = new Map();

  grid.style.gridTemplateColumns = `repeat(${cfg.grid_size}, 1fr)`;
  grid.style.gridTemplateRows = `repeat(${cfg.grid_size}, 1fr)`;

  function edgeKey(a, b) {
    return [key(a), key(b)].sort().join("|");
  }

  function adjacent(a, b) {
    return Math.abs(a[0] - b[0]) + Math.abs(a[1] - b[1]) === 1;
  }

  function inBounds(p) {
    return p[0] >= 0 && p[1] >= 0 && p[0] < cfg.grid_size && p[1] < cfg.grid_size;
  }

  function validStep(a, b) {
    if (!inBounds(b)) return false;
    if (!adjacent(a, b)) return false;
    if (blockedCells.has(key(b))) return false;
    if (blockedEdges.has(edgeKey(a, b))) return false;
    return true;
  }

  function isSearchHallway(r, c) {
    return r === 0 || c === 0 || r === cfg.grid_size - 1 || c === cfg.grid_size - 1;
  }

  function isSearchCorridor(r, c) {
    const mid = Math.floor(cfg.grid_size / 2);
    return r === mid || c === mid;
  }

  function addWallBorders(cell, r, c) {
    const directions = [
      [[r, c], [r - 1, c], "borderTop"],
      [[r, c], [r + 1, c], "borderBottom"],
      [[r, c], [r, c - 1], "borderLeft"],
      [[r, c], [r, c + 1], "borderRight"],
    ];
    directions.forEach(([a, b, property]) => {
      if (blockedEdges.has(edgeKey(a, b))) cell.style[property] = "4px solid #111827";
    });
  }

  function addMarker(cell, className, text, ariaLabel) {
    const marker = document.createElement("span");
    marker.className = `cell_marker ${className}`;
    marker.textContent = text;
    marker.setAttribute("aria-label", ariaLabel || text);
    cell.appendChild(marker);
  }

  function buildGrid() {
    for (let r = 0; r < cfg.grid_size; r += 1) {
      for (let c = 0; c < cfg.grid_size; c += 1) {
        const cell = document.createElement("button");
        cell.type = "button";
        cell.className = "grid_cell";
        cell.dataset.row = r;
        cell.dataset.col = c;
        const locKey = `${r},${c}`;

        if (cfg.domain === "search_recon") {
          if (roomByCell.has(locKey)) {
            cell.classList.add("room_floor");
            cell.dataset.room = roomByCell.get(locKey);
          } else if (isSearchHallway(r, c)) {
            cell.classList.add("hallway_floor");
          } else if (isSearchCorridor(r, c)) {
            cell.classList.add("corridor_floor");
          } else {
            cell.classList.add("interior_floor");
          }
        }

        if (blockedCells.has(locKey)) cell.classList.add("wall");
        if (busy.has(locKey)) cell.classList.add("busy");
        if (coffee.has(locKey)) cell.classList.add("coffee");
        if (cfg.office && key(cfg.office) === locKey) cell.classList.add("goal");

        if (cfg.visible_debris && cfg.visible_debris[locKey]) {
          const level = cfg.visible_debris[locKey];
          cell.classList.add("debris", level);
          addMarker(cell, "debris_marker", level === "high" ? "H" : "L", `${level} debris`);
        }

        if (cfg.photo_targets) {
          Object.entries(cfg.photo_targets).forEach(([name, loc]) => {
            if (key(loc) === locKey) {
              cell.classList.add("photo");
              addMarker(cell, "photo_marker", name, `Photo target ${name}`);
            }
          });
        }

        if (cfg.domain === "office" && coffee.has(locKey)) {
          const label = (cfg.coffee_labels || {})[locKey] || "C";
          addMarker(cell, "coffee_marker", label, `Coffee source ${label}`);
        } else if (cfg.office && key(cfg.office) === locKey) {
          addMarker(cell, "office_marker", "O", "Delivery office");
        } else if (cfg.labels && cfg.labels[locKey] && !cell.querySelector(".cell_marker")) {
          addMarker(cell, "label_marker", cfg.labels[locKey], cfg.labels[locKey]);
        }

        if (key(cfg.start) === locKey) {
          cell.classList.add("start_cell");
          addMarker(cell, "robot_marker", "▲", "Robot start");
        }

        addWallBorders(cell, r, c);
        if (!blockedCells.has(locKey)) {
          cell.addEventListener("click", () => addPoint([r, c]));
        } else {
          cell.disabled = true;
        }
        grid.appendChild(cell);
        cells.set(locKey, cell);
      }
    }
  }

  function completionState() {
    if (cfg.completion === "office") {
      const picked = trajectory.some(p => coffee.has(key(p)));
      const delivered = picked && key(trajectory[trajectory.length - 1]) === key(cfg.office);
      return {
        complete: delivered,
        text: delivered ? "Coffee collected and delivered." : picked ? "Coffee collected. Continue to office O." : "Collect coffee from A or B, then deliver it to O.",
      };
    }
    const targets = new Set();
    Object.entries(cfg.photo_targets).forEach(([name, loc]) => {
      if (trajectory.some(p => key(p) === key(loc))) targets.add(name);
    });
    const home = key(trajectory[trajectory.length - 1]) === key(cfg.start);
    const complete = targets.size === Object.keys(cfg.photo_targets).length && home && trajectory.length > 1;
    return {
      complete,
      text: complete ? "All four photos collected and robot returned to S." : `${targets.size}/${Object.keys(cfg.photo_targets).length} photo targets visited${targets.size === Object.keys(cfg.photo_targets).length ? ". Return to S." : "."}`,
    };
  }

  function validNextPoints() {
    const current = trajectory[trajectory.length - 1];
    return [
      [current[0] - 1, current[1]],
      [current[0] + 1, current[1]],
      [current[0], current[1] - 1],
      [current[0], current[1] + 1],
    ].filter((p) => validStep(current, p));
  }

  function addPoint(point) {
    const last = trajectory[trajectory.length - 1];
    if (key(point) === key(last)) return;
    if (!validStep(last, point)) {
      events.push({type: "invalid_click", point, time_ms: Math.round(performance.now() - startTime)});
      errorBox.textContent = "Choose one of the highlighted adjacent floor cells.";
      return;
    }
    errorBox.textContent = "";
    trajectory.push(point);
    events.push({type: "add", point, time_ms: Math.round(performance.now() - startTime)});
    render();
  }

  function makeSvg(tag, attrs = {}) {
    const item = document.createElementNS("http://www.w3.org/2000/svg", tag);
    Object.entries(attrs).forEach(([name, value]) => item.setAttribute(name, value));
    return item;
  }

  function drawLines() {
    overlay.innerHTML = "";
    const board = grid.getBoundingClientRect();
    overlay.setAttribute("viewBox", `0 0 ${board.width} ${board.height}`);

    const defs = makeSvg("defs");
    const marker = makeSvg("marker", {
      id: "routeArrow",
      markerWidth: "8",
      markerHeight: "8",
      refX: "6.5",
      refY: "3.5",
      orient: "auto",
      markerUnits: "strokeWidth",
    });
    marker.appendChild(makeSvg("path", {d: "M0,0 L0,7 L7,3.5 z", fill: "#173b68"}));
    defs.appendChild(marker);
    overlay.appendChild(defs);

    const cellW = board.width / cfg.grid_size;
    const cellH = board.height / cfg.grid_size;
    const pointXY = (p) => [(p[1] + 0.5) * cellW, (p[0] + 0.5) * cellH];

    for (let i = 0; i < trajectory.length - 1; i += 1) {
      const [x1, y1] = pointXY(trajectory[i]);
      const [x2, y2] = pointXY(trajectory[i + 1]);
      const dx = x2 - x1;
      const dy = y2 - y1;
      const trim = Math.min(cellW, cellH) * 0.20;
      const length = Math.max(1, Math.hypot(dx, dy));
      const ux = dx / length;
      const uy = dy / length;
      const line = makeSvg("line", {
        x1: x1 + ux * trim,
        y1: y1 + uy * trim,
        x2: x2 - ux * trim,
        y2: y2 - uy * trim,
        "marker-end": "url(#routeArrow)",
        class: "route_segment",
      });
      overlay.appendChild(line);
    }

    if (trajectory.length > 1) {
      trajectory.forEach((p, index) => {
        if (index === 0) return;
        const [x, y] = pointXY(p);
        const circle = makeSvg("circle", {
          cx: x,
          cy: y,
          r: Math.max(7, Math.min(cellW, cellH) * 0.13),
          class: index === trajectory.length - 1 ? "route_node current_node" : "route_node",
        });
        overlay.appendChild(circle);
        if (index === trajectory.length - 1) {
          const label = makeSvg("text", {
            x,
            y: y + 4,
            "text-anchor": "middle",
            class: "route_label current_label",
          });
          label.textContent = String(index);
          overlay.appendChild(label);
        }
      });
    }
  }

  function render() {
    cells.forEach(cell => {
      cell.classList.remove("path_cell", "current", "next_choice");
    });
    trajectory.forEach((point) => {
      const cell = cells.get(key(point));
      if (cell) cell.classList.add("path_cell");
    });
    const current = cells.get(key(trajectory[trajectory.length - 1]));
    if (current) current.classList.add("current");
    validNextPoints().forEach((point) => {
      const cell = cells.get(key(point));
      if (cell) cell.classList.add("next_choice");
    });
    const state = completionState();
    statusBox.textContent = state.text;
    routeSummary.textContent = `${trajectory.length - 1} moves selected.`;
    submitButton.disabled = !state.complete;
    requestAnimationFrame(drawLines);
  }

  document.getElementById("undoButton").addEventListener("click", () => {
    if (trajectory.length > 1) {
      const removed = trajectory.pop();
      events.push({type: "undo", point: removed, time_ms: Math.round(performance.now() - startTime)});
      render();
    }
  });

  document.getElementById("resetButton").addEventListener("click", () => {
    trajectory = [cfg.start.slice()];
    events.push({type: "reset", time_ms: Math.round(performance.now() - startTime)});
    errorBox.textContent = "";
    render();
  });

  submitButton.addEventListener("click", async () => {
    submitButton.disabled = true;
    errorBox.textContent = "";
    const body = {
      task_index: taskIndex,
      trajectory,
      events,
      response_time_ms: Math.round(performance.now() - startTime),
      confidence: document.getElementById("confidence").value,
      explanation: document.getElementById("explanation").value,
    };
    try {
      const response = await fetch("/api/trial", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify(body),
      });
      const result = await response.json();
      if (!response.ok || !result.ok) throw new Error(result.error || "Submission failed");
      window.location.assign(result.next_url);
    } catch (error) {
      errorBox.textContent = error.message;
      submitButton.disabled = false;
    }
  });

  window.addEventListener("resize", drawLines);
  buildGrid();
  render();
})();

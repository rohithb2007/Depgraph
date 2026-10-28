const $ = (id) => document.getElementById(id);
let config,
  current,
  selectedId,
  polling = false,
  renderedKey,
  historyKey;
const renderKey = (run) =>
  [run.id, run.status, run.events.length, run.patch_hash, run.finished_at].join(
    "|",
  );
const el = (tag, text, cls) => {
  const n = document.createElement(tag);
  if (text !== undefined) n.textContent = text;
  if (cls) n.className = cls;
  return n;
};
function notice(message) {
  $("notice").textContent = message;
  $("notice").hidden = !message;
}
async function api(path, body) {
  const options =
    body === undefined
      ? {}
      : {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-DepGraph-Token": config.token,
          },
          body: JSON.stringify(body),
        };
  const response = await fetch(path, options);
  const result = await response.json();
  if (!response.ok)
    throw new Error(result.error || `Request failed (${response.status})`);
  return result;
}
function tab(name) {
  document
    .querySelectorAll(".tab-panel")
    .forEach((n) => (n.hidden = n.id !== name));
  document
    .querySelectorAll("[data-tab]")
    .forEach((n) =>
      n.setAttribute("aria-selected", String(n.dataset.tab === name)),
    );
}
document
  .querySelectorAll("[data-tab]")
  .forEach((n) => (n.onclick = () => tab(n.dataset.tab)));
$("overview-nav").onclick = () => tab("overview");
function badge(text, outcome) {
  return el(
    "span",
    text.replaceAll("_", " "),
    "badge " +
      (["ready", "upgraded", "repaired", "applied"].includes(outcome)
        ? "good"
        : [
              "rolled_back",
              "failed",
              "policy_blocked",
              "baseline_failed",
            ].includes(outcome)
          ? "warn"
          : ""),
  );
}
async function history() {
  const runs = await api("/api/runs");
  const key = selectedId + JSON.stringify(runs);
  if (key === historyKey) return runs;
  historyKey = key;
  $("history-count").textContent = runs.length;
  if (!runs.length) return;
  $("history").replaceChildren(
    ...runs.map((run) => {
      const b = el(
        "button",
        (run.demo ? "Offline fixture" : run.repo.split(/[\\/]/).pop()) +
          " · " +
          run.id.slice(0, 6),
        run.id === selectedId ? "selected" : "",
      );
      b.append(
        el(
          "small",
          `${run.status.replaceAll("_", " ")} · ${new Date(run.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}`,
        ),
      );
      b.onclick = () => select(run.id);
      return b;
    }),
  );
  return runs;
}
async function select(id) {
  selectedId = id;
  $("detail").hidden = true;
  current = await api(`/api/runs/${id}`);
  render(current);
  await history();
}
function render(run) {
  renderedKey = renderKey(run);
  const cs = run.candidates || [];
  const active = ["queued", "running"].includes(run.status);
  $("demo-button").disabled = config.busy || active;
  $("analyze-button").disabled = !config.repo || config.busy || active;
  $("run-title").textContent =
    `${run.demo ? "Offline compatibility fixture" : run.repo.split(/[\\/]/).pop()} / ${run.id.slice(0, 8)}`;
  $("run-label").replaceWith(
    Object.assign(badge(run.status.toUpperCase(), run.status), {
      id: "run-label",
    }),
  );
  $("metric-deps").textContent = run.dependencies.length;
  $("metric-deps-note").textContent =
    `${run.graph.files.length} Python files inspected`;
  $("metric-verified").textContent = cs.filter((c) =>
    ["upgraded", "repaired"].includes(c.outcome),
  ).length;
  $("metric-repaired").textContent = cs.filter(
    (c) => c.outcome === "repaired",
  ).length;
  $("metric-blocked").textContent = cs.filter((c) =>
    ["rolled_back", "policy_blocked", "lookup_failed"].includes(c.outcome),
  ).length;
  $("event-count").textContent = run.events.length;
  $("patch-count").textContent = run.changes.length;
  $("candidate-note").textContent = `${cs.length} decisions recorded`;
  $("export-button").disabled = false;
  $("apply-button").disabled =
    run.demo || run.status !== "ready" || config.busy;
  $("policy-note").textContent = run.demo
    ? "DEMO · Local API fixtures, deterministic repair rule, real subprocess tests. Security results are fixture data."
    : `REAL ANALYSIS · Major upgrades ${run.policy.allow_major ? "allowed" : "blocked"}. Unknown security ${run.policy.allow_unknown_security ? "allowed by explicit override" : "blocked"}. Tests execute trusted code.`;
  $("integrity-label").textContent = `${run.events.length} HASH-LINKED EVENTS`;
  $("footer-status").textContent =
    `${run.demo ? "Offline fixture" : "Real analysis"} · Python ${run.python}`;
  if (run.error) notice(run.error);
  else if (run.status === "baseline_failed")
    notice(
      "Baseline validation failed. No upgrades were attempted. Inspect execution evidence for command output.",
    );
  else if (run.demo && run.status === "ready")
    notice(
      "Demo complete: real tests verified a clean upgrade, a compatibility repair, and a rollback. Original fixture unchanged.",
    );
  else if (run.status === "applied")
    notice(
      "Reviewed patch applied successfully. The complete evidence is available for export.",
    );
  else if (active)
    notice("Maintenance in progress. Each stage is persisted as it completes.");
  else notice("");
  renderGraph(run);
  $("dependencies").replaceChildren(
    ...(cs.length
      ? cs.map((c, i) => {
          const row = el("tr");
          const name = el("td");
          name.append(
            el("span", "◇", "package-cube"),
            document.createTextNode(c.name),
          );
          const version = el("td", `${c.from} → ${c.to}`, "version-path");
          const impact = el("td", `${c.impact?.length || 0} files`, "muted");
          const risk = el("td", c.risk ? `${c.risk.score} / 100` : "—", "risk");
          const status = el("td");
          status.append(badge(c.outcome, c.outcome));
          const action = el("td");
          const b = el("button", "Inspect ↗");
          b.onclick = () => inspect(i);
          action.append(b);
          row.append(name, version, impact, risk, status, action);
          return row;
        })
      : [
          Object.assign(el("tr"), {
            innerHTML:
              '<td colspan="6" class="table-empty">Waiting for dependency decisions…</td>',
          }),
        ]),
  );
  $("events").replaceChildren(
    ...run.events.map((event) => {
      const node = el("div", undefined, "event");
      node.append(
        el(
          "div",
          `${String(event.sequence).padStart(2, "0")} / ${event.stage.toUpperCase()} · ${new Date(event.at).toLocaleTimeString()}`,
          "event-meta",
        ),
        el("h3", event.message),
        el("small", `SHA256 ${event.hash}`),
      );
      return node;
    }),
  );
  if (run.baseline) {
    const section = el("div", undefined, "detail");
    section.append(el("h3", "Baseline validation"));
    appendValidation(section, run.baseline, "Baseline commands");
    $("events").append(section);
  }
  $("diffs").replaceChildren(
    ...(run.changes.length
      ? run.changes.map((change) => {
          const node = el("div", undefined, "diff-file");
          node.append(el("h3", change.path));
          const pre = el("pre");
          change.diff
            .split("\n")
            .forEach((line) =>
              pre.append(
                el(
                  "span",
                  line,
                  "diff-line " +
                    (line.startsWith("+")
                      ? "add"
                      : line.startsWith("-")
                        ? "remove"
                        : line.startsWith("@@")
                          ? "hunk"
                          : ""),
                ),
              ),
            );
          node.append(pre);
          return node;
        })
      : [
          el(
            "p",
            active
              ? "A patch will appear after all validations finish."
              : "No validated changes in this run.",
            "muted",
          ),
        ]),
  );
}
function appendValidation(parent, validation, title) {
  const details = el("details"),
    summary = el(
      "summary",
      `${title} · ${validation.passed ? "passed" : "failed"} (${validation.stage})`,
    );
  details.append(summary);
  for (const c of validation.commands || [])
    details.append(
      el(
        "pre",
        `$ ${c.command.join(" ")}\nexit=${c.return_code} · ${c.duration}s${c.timed_out ? " · TIMED OUT" : ""}\n${c.stdout}\n${c.stderr}`,
      ),
    );
  parent.append(details);
}
function inspect(index) {
  const c = current.candidates[index],
    node = $("detail");
  node.hidden = false;
  node.replaceChildren(el("h3", `${c.name} · ${c.from} → ${c.to}`));
  node.append(
    el(
      "p",
      c.reason ||
        c.risk?.reasons.join(" · ") ||
        "No upgrade candidate selected.",
    ),
  );
  if (c.security)
    node.append(
      el(
        "p",
        `Security: ${c.security.status} · ${c.security.source}${c.security.ids.length ? " · " + c.security.ids.join(", ") : ""}`,
      ),
    );
  if (c.validation)
    appendValidation(node, c.validation, "Initial upgrade validation");
  for (const a of c.attempts) {
    node.append(
      el(
        "p",
        a.rejected || `${a.proposal.root_cause} · ${a.proposal.provider}`,
      ),
    );
    if (a.validation) appendValidation(node, a.validation, "Repair validation");
  }
  node.scrollIntoView({ behavior: "smooth", block: "nearest" });
}
function renderGraph(run) {
  const ns = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(ns, "svg");
  svg.setAttribute("viewBox", "0 0 620 254");
  svg.setAttribute("role", "img");
  svg.setAttribute("aria-label", "Static import impact graph");
  const files = [...new Set(run.graph.edges.map((e) => e.file))].slice(0, 6),
    deps = run.dependencies.slice(0, 8);
  const sy = (i, n) => 32 + (n === 1 ? 90 : (i * 188) / Math.max(1, n - 1));
  function shape(tag, attrs, text) {
    const n = document.createElementNS(ns, tag);
    for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v);
    if (text) n.textContent = text;
    return n;
  }
  for (const edge of run.graph.edges) {
    const fi = files.indexOf(edge.file),
      di = deps.findIndex((d) => d.name === edge.package);
    if (fi < 0 || di < 0) continue;
    const y1 = sy(fi, files.length),
      y2 = sy(di, deps.length);
    svg.append(
      shape("path", {
        d: `M 205 ${y1} C 290 ${y1}, 300 ${y2}, 395 ${y2}`,
        stroke: "#345349",
        "stroke-width": "1.3",
        fill: "none",
      }),
    );
  }
  files.forEach((f, i) => {
    const y = sy(i, files.length);
    svg.append(
      shape("rect", {
        x: 25,
        y: y - 15,
        width: 180,
        height: 30,
        rx: 5,
        fill: "#192531",
        stroke: "#3e5369",
      }),
      shape(
        "text",
        { x: 38, y: y + 4 },
        f.length > 24 ? "…" + f.slice(-23) : f,
      ),
    );
  });
  deps.forEach((d, i) => {
    const y = sy(i, deps.length),
      c = run.candidates.find((c) => c.name === d.name),
      g = shape("g", {
        class: "package-node",
        tabindex: 0,
        role: "button",
        "aria-label": `Inspect ${d.name}`,
      });
    g.append(
      shape("rect", {
        x: 395,
        y: y - 15,
        width: 195,
        height: 30,
        rx: 5,
        fill: "#12241f",
        stroke: c?.outcome === "rolled_back" ? "#a58255" : "#3b6354",
      }),
      shape("text", { x: 409, y: y + 4 }, `${d.name}  ${c?.to || d.version}`),
    );
    const action = () => {
      const index = run.candidates.findIndex((c) => c.name === d.name);
      if (index >= 0) inspect(index);
    };
    g.onclick = action;
    g.onkeydown = (e) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        action();
      }
    };
    svg.append(g);
  });
  $("graph").replaceChildren(svg);
}
async function start(path) {
  $("demo-button").disabled = true;
  $("analyze-button").disabled = true;
  try {
    const r = await api(path, {});
    config.busy = true;
    await select(r.id);
    tab("overview");
  } catch (e) {
    notice(e.message);
    config = await api("/api/config");
    $("demo-button").disabled = config.busy;
    $("analyze-button").disabled = !config.repo || config.busy;
  }
}
$("demo-button").onclick = () => start("/api/demo");
$("analyze-button").onclick = () => start("/api/analyze");
$("export-button").onclick = () => {
  if (!current) return;
  const url = URL.createObjectURL(
    new Blob([JSON.stringify(current, null, 2)], { type: "application/json" }),
  );
  const a = el("a");
  a.href = url;
  a.download = `depgraph-${current.id}.json`;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
};
$("apply-button").onclick = () => $("apply-dialog").showModal();
$("cancel-apply").onclick = () => $("apply-dialog").close();
$("confirm-apply").onclick = async () => {
  const id = selectedId;
  $("apply-dialog").close();
  try {
    await api(`/api/runs/${id}/apply`, {});
    await select(id);
  } catch (e) {
    notice(e.message);
  }
};
async function tick() {
  if (polling) return;
  polling = true;
  try {
    config = await api("/api/config");
    if (selectedId) {
      current = await api(`/api/runs/${selectedId}`);
      if (renderKey(current) !== renderedKey) render(current);
      else {
        $("demo-button").disabled = config.busy;
        $("analyze-button").disabled = !config.repo || config.busy;
        $("apply-button").disabled =
          current.demo || current.status !== "ready" || config.busy;
      }
    } else {
      $("demo-button").disabled = config.busy;
      $("analyze-button").disabled = !config.repo || config.busy;
    }
    await history();
  } catch (e) {
    notice("Engine connection interrupted. " + e.message);
  } finally {
    polling = false;
  }
}
(async () => {
  try {
    config = await api("/api/config");
    $("analyze-button").disabled = !config.repo || config.busy;
    const runs = await history();
    if (runs?.length) await select(runs[0].id);
    setInterval(tick, 1800);
  } catch (e) {
    notice(e.message);
  }
})();

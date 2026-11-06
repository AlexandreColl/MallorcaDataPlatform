// Architecture diagram of the README, in light and dark: `node scripts/architecture/diagram.mjs`.
//
// The layout is written by hand (a grid of nodes and orthogonal arrows) so the picture says exactly what the platform
// does; Graphviz-style auto layout would decide the positions instead. Logos: Simple Icons 13.21.0 (CC0), vendored in
// icons.json with each brand's colour. Delta Lake has no Simple Icons logo, so it is drawn as a plain triangle.
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const ICONS = JSON.parse(fs.readFileSync(path.join(here, "icons.json"), "utf8"));
const OUT = path.resolve(here, "../../docs/img");

const THEMES = {
  light: {
    bg: "#f6f8f6", card: "#ffffff", border: "#d5dfd8", text: "#0f1a14", muted: "#55665c", faint: "#e9efeb",
    compose: "#9db3a5", chip: "#eef5f0",
  },
  dark: {
    bg: "#0a120d", card: "#111c15", border: "#24372b", text: "#e7efe9", muted: "#9db1a4", faint: "#17251c",
    compose: "#3d5a47", chip: "#14251a",
  },
};
// What each node does, by colour.
const ROLE = {
  source: { color: "#64748b", label: "Fuentes" },
  processing: { color: "#ea580c", label: "Procesamiento" },
  storage: { color: "#2563eb", label: "Almacenamiento" },
  serving: { color: "#7c3aed", label: "Servicio" },
  orchestration: { color: "#15803d", label: "Orquestación" },
};
const LAYER = {
  bronze: { color: "#b45309", label: "Bronze · MinIO", detail: "Respuesta cruda de cada fuente, versionada" },
  silver: { color: "#8394a8", label: "Silver · Delta Lake y Postgres", detail: "Esquema común, calidad marcada" },
  gold: { color: "#ca8a04", label: "Gold · Postgres (dbt)", detail: "Marts con contrato para los dashboards" },
};
const FONT = "Inter, 'Segoe UI', Helvetica, Arial, sans-serif";

const W = 1400;
const H = 920;
const NODE_W = 220;
const NODE_H = 130;
const COL = [325, 585, 845];
const ROW = { B: 292, C: 464, D: 636 };

const esc = (s) => s.replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;");

function text(x, y, value, { size = 12, weight = 400, fill, anchor = "start", spacing = 0 } = {}) {
  const ls = spacing ? ` letter-spacing="${spacing}"` : "";
  return `<text x="${x}" y="${y}" font-size="${size}" font-weight="${weight}" fill="${fill}" text-anchor="${anchor}"${ls}>${esc(value)}</text>`;
}

function icon(name, x, y, size = 26, color) {
  const i = ICONS[name];
  const scale = size / 24;
  return `<path transform="translate(${x} ${y}) scale(${scale})" d="${i.d}" fill="${color ?? i.hex}"/>`;
}

/** Delta Lake: a plain triangle in its teal. */
function delta(x, y, size = 24) {
  return `<path d="M${x + size / 2} ${y + 2} L${x + size - 1} ${y + size - 2} L${x + 1} ${y + size - 2} Z" fill="none" stroke="#00ADD4" stroke-width="3" stroke-linejoin="round"/>`;
}

function badge(x, y, layer, t) {
  const l = LAYER[layer];
  const label = layer.toUpperCase();
  const w = label.length * 7 + 16;
  return `<rect x="${x}" y="${y}" width="${w}" height="18" rx="9" fill="${l.color}" fill-opacity="${t === THEMES.dark ? 0.28 : 0.16}"/>` +
    text(x + w / 2, y + 12.5, label, { size: 9.5, weight: 700, fill: l.color, anchor: "middle", spacing: 0.6 });
}

function step(x, y, label, t) {
  return `<circle cx="${x}" cy="${y}" r="11" fill="${ROLE.orchestration.color}"/>` +
    text(x, y + 4, label, { size: label.length > 1 ? 9 : 11, weight: 700, fill: "#ffffff", anchor: "middle" }) +
    (t ? "" : "");
}

/** A card with a coloured top edge, logos, a title, a coloured subtitle and up to three lines of detail. */
function node(t, { x, y, w = NODE_W, h = NODE_H, role, icons = [], title, subtitle, lines = [], layers = [], steps }) {
  const color = ROLE[role].color;
  let s = `<g>`;
  s += `<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="12" fill="${t.card}" stroke="${t.border}"/>`;
  s += `<path d="M${x} ${y + 12} a12 12 0 0 1 12 -12 h${w - 24} a12 12 0 0 1 12 12 v-8 h-${w} z" fill="${color}" transform="translate(0 0)"/>`;
  let ix = x + 16;
  for (const name of icons) {
    s += name === "delta" ? delta(ix, y + 18, 24) : icon(name, ix, y + 18, 24);
    ix += 32;
  }
  let bx = x + w - 14;
  if (steps) {
    s += step(x + w - 25, y + 30, steps, t);
    bx -= 30;
  }
  for (const layer of [...layers].reverse()) {
    const bw = layer.length * 7 + 16;
    bx -= bw;
    s += badge(bx, y + 21, layer, t);
    bx -= 6;
  }
  s += text(x + 16, y + 64, title, { size: 15, weight: 650, fill: t.text });
  s += text(x + 16, y + 82, subtitle, { size: 11.5, weight: 600, fill: color });
  lines.forEach((line, i) => {
    s += text(x + 16, y + 101 + i * 15, line, { size: 11.5, fill: t.muted });
  });
  return `${s}</g>`;
}

/** An orthogonal arrow through the given points, in the colour of what it carries. */
function arrow(points, color, { dashed = false, label, labelAt, t } = {}) {
  const d = points.map(([x, y], i) => `${i ? "L" : "M"}${x} ${y}`).join(" ");
  const id = `arrow-${color.slice(1)}`;
  let s = `<path d="${d}" fill="none" stroke="${color}" stroke-width="2"${dashed ? ' stroke-dasharray="5 5"' : ""} marker-end="url(#${id})"/>`;
  if (label) {
    const [lx, ly] = labelAt;
    const w = label.length * 6 + 12;
    s += `<rect x="${lx - w / 2}" y="${ly - 10}" width="${w}" height="18" rx="9" fill="${t.bg}"/>`;
    s += text(lx, ly + 3, label, { size: 10.5, weight: 600, fill: color, anchor: "middle" });
  }
  return s;
}

function markers() {
  return Object.values(ROLE)
    .map(
      ({ color }) =>
        `<marker id="arrow-${color.slice(1)}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0 0 L10 5 L0 10 z" fill="${color}"/></marker>`,
    )
    .join("");
}

function sources(t) {
  const x = 30;
  const y = 120;
  const w = 240;
  const h = 670;
  const groups = [
    ["Tiempo y aire", ["AEMET (33 estaciones)", "SOCIB · Open-Meteo", "EEA · Govern (2002-2021)"]],
    ["Avisos", ["AEMET Meteoalerta (CAP)"]],
    ["Mar y sismos", ["Open-Meteo Marine · IGN"]],
    ["Movilidad", ["EMT Palma · CTM (GTFS)"]],
    ["Turismo, agua y energía", ["Dataestur · REData", "Reservas hídricas (Govern)"]],
    ["Población", ["INE, padrón desde 1996"]],
  ];
  let s = `<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="14" fill="${t.card}" stroke="${t.border}"/>`;
  s += `<path d="M${x} ${y + 14} a14 14 0 0 1 14 -14 h${w - 28} a14 14 0 0 1 14 14 v-8 h-${w} z" fill="${ROLE.source.color}"/>`;
  s += text(x + 20, y + 44, "14 fuentes abiertas", { size: 17, weight: 700, fill: t.text });
  s += text(x + 20, y + 64, "APIs REST, GTFS, CAP, CKAN y ficheros", { size: 11.5, fill: t.muted });
  let gy = y + 104;
  for (const [title, items] of groups) {
    s += text(x + 20, gy, title.toUpperCase(), { size: 10, weight: 700, fill: ROLE.source.color, spacing: 0.7 });
    gy += 20;
    for (const item of items) {
      s += `<circle cx="${x + 26}" cy="${gy - 4}" r="3" fill="${ROLE.source.color}"/>`;
      s += text(x + 38, gy, item, { size: 12.5, fill: t.text });
      gy += 20;
    }
    gy += 14;
  }
  s += `<line x1="${x + 20}" y1="${y + h - 78}" x2="${x + w - 20}" y2="${y + h - 78}" stroke="${t.faint}" stroke-width="1.5"/>`;
  s += text(x + 20, y + h - 52, "Un conector por fuente:", { size: 11.5, weight: 600, fill: t.text });
  s += text(x + 20, y + h - 35, "YAML, extractor y tests con", { size: 11.5, fill: t.muted });
  s += text(x + 20, y + h - 19, "respuestas reales grabadas", { size: 11.5, fill: t.muted });
  return s;
}

function airflow(t) {
  const x = COL[0];
  const y = 142;
  const w = COL[2] + NODE_W - x;
  const h = 122;
  const color = ROLE.orchestration.color;
  let s = `<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="12" fill="${t.card}" stroke="${t.border}"/>`;
  s += `<rect x="${x}" y="${y}" width="5" height="${h}" rx="2.5" fill="${color}"/>`;
  s += icon("apacheairflow", x + 20, y + 14, 26);
  s += text(x + 56, y + 32, "Apache Airflow", { size: 15, weight: 650, fill: t.text });
  s += text(x + 180, y + 32, "DAG mallorca_pipeline, cada día · parámetros: fuentes, días y región", { size: 11.5, weight: 600, fill: color });
  const chips = [
    ["1", "ingest", "una tarea por conector"],
    ["2", "detect_anomalies", "z-score e Isolation Forest"],
    ["3", "correct_values", "interpolación y apoyo"],
    ["4", "dbt_build", "modelos y tests"],
  ];
  const pad = 20;
  const between = 30;
  const cw = (w - 2 * pad - 3 * between) / 4;
  let cx = x + pad;
  chips.forEach(([n, name, detail], i) => {
    const cy = y + 50;
    s += `<rect x="${cx}" y="${cy}" width="${cw}" height="54" rx="10" fill="${t.chip}" stroke="${t.border}"/>`;
    s += step(cx + 20, cy + 18, n);
    s += text(cx + 38, cy + 22, name, { size: 12.5, weight: 650, fill: t.text });
    s += text(cx + 14, cy + 42, detail, { size: 10.5, fill: t.muted });
    if (i < chips.length - 1) {
      s += arrow([[cx + cw + 4, cy + 27], [cx + cw + between - 6, cy + 27]], color);
    }
    cx += cw + between;
  });
  return s;
}

function rail(t) {
  const x = 1115;
  const y = 120;
  const w = 255;
  const h = 670;
  const items = [
    { icon: null, title: "Calidad en cada carga", lines: ["Rango, huecos, duplicados y QC", "de la fuente: marca, no borra", "(quality.check_results)"] },
    { icon: "dbt", title: "Contratos y tests", lines: ["Contrato en cada mart, tests de", "relaciones y rangos, slim CI", "con selección por estado"] },
    { icon: null, title: "Linaje", lines: ["OpenLineage desde Airflow y dbt,", "por columna, en Marquez (opcional)"] },
    { icon: "githubactions", title: "CI/CD", lines: ["ruff, PySpark, dbt en vacío, E2E", "que relanza el DAG y exige", "idempotencia; imágenes en GHCR"] },
    { icon: "terraform", title: "Despliegue en AWS", lines: ["S3, Glue y Athena en Terraform,", "validado con AWS simulado", "(sin desplegar)"] },
  ];
  let s = `<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="14" fill="${t.card}" stroke="${t.border}"/>`;
  s += text(x + 20, y + 40, "Calidad, linaje y despliegue", { size: 15, weight: 700, fill: t.text });
  s += text(x + 20, y + 59, "Lo que hace fiable cada dato", { size: 11.5, fill: t.muted });
  let iy = y + 92;
  for (const item of items) {
    if (item.icon) s += icon(item.icon, x + 20, iy - 2, 20);
    else s += `<circle cx="${x + 30}" cy="${iy + 8}" r="8" fill="none" stroke="${ROLE.orchestration.color}" stroke-width="2.5"/><circle cx="${x + 30}" cy="${iy + 8}" r="2.5" fill="${ROLE.orchestration.color}"/>`;
    s += text(x + 50, iy + 13, item.title, { size: 13, weight: 650, fill: t.text });
    item.lines.forEach((line, i) => {
      s += text(x + 50, iy + 32 + i * 15, line, { size: 11, fill: t.muted });
    });
    iy += 36 + item.lines.length * 15 + 26;
  }
  return s;
}

function legend(t) {
  const y = 815;
  let s = `<rect x="30" y="${y}" width="${W - 60}" height="78" rx="14" fill="${t.card}" stroke="${t.border}"/>`;
  s += text(52, y + 28, "CAPAS MEDALLION", { size: 10, weight: 700, fill: t.muted, spacing: 0.7 });
  let x = 52;
  for (const l of Object.values(LAYER)) {
    s += `<rect x="${x}" y="${y + 40}" width="14" height="14" rx="4" fill="${l.color}"/>`;
    s += text(x + 22, y + 51, l.label, { size: 12, weight: 650, fill: t.text });
    s += text(x + 22, y + 67, l.detail, { size: 10.5, fill: t.muted });
    x += 250;
  }
  s += text(830, y + 28, "FUNCIÓN", { size: 10, weight: 700, fill: t.muted, spacing: 0.7 });
  x = 830;
  for (const r of Object.values(ROLE)) {
    s += `<circle cx="${x + 6}" cy="${y + 50}" r="6" fill="${r.color}"/>`;
    s += text(x + 18, y + 54, r.label, { size: 12, fill: t.text });
    x += r.label.length * 6.6 + 34;
  }
  return s;
}

function diagram(t) {
  const P = ROLE.processing.color;
  const S = ROLE.storage.color;
  const V = ROLE.serving.color;
  const [c1, c2, c3] = COL;
  const mid = NODE_H / 2;
  let s = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" font-family="${FONT}">`;
  s += `<title>Arquitectura de Mallorca Data Platform</title>`;
  s += `<desc>Catorce fuentes abiertas entran por conectores en Python a bronze (MinIO), PySpark las normaliza en silver (Delta Lake y Postgres), Python marca anomalías y propone correcciones, dbt construye gold en Postgres, y la API, la web y Grafana lo sirven. Airflow orquesta cada paso.</desc>`;
  s += `<defs>${markers()}</defs>`;
  s += `<rect width="${W}" height="${H}" fill="${t.bg}"/>`;

  // Header
  s += text(30, 44, "MALLORCA DATA PLATFORM", { size: 12, weight: 700, fill: ROLE.orchestration.color, spacing: 1.6 });
  s += text(30, 80, "De 14 fuentes abiertas a la isla en cifras", { size: 28, weight: 750, fill: t.text });
  s += text(W - 30, 80, "Un docker compose up levanta la plataforma entera, en local", { size: 13, fill: t.muted, anchor: "end" });

  s += sources(t);

  // Docker Compose boundary
  s += `<rect x="296" y="120" width="800" height="670" rx="18" fill="none" stroke="${t.compose}" stroke-width="2" stroke-dasharray="8 6"/>`;
  s += `<rect x="316" y="110" width="150" height="22" rx="11" fill="${t.bg}"/>`;
  s += icon("docker", 322, 111, 20);
  s += text(348, 126, "Docker Compose", { size: 12.5, weight: 650, fill: t.muted });

  s += airflow(t);

  // Row B: ingestion into bronze and silver
  s += node(t, { x: c1, y: ROW.B, role: "processing", icons: ["python"], title: "Conectores", subtitle: "Python · extract() y normalize()", lines: ["Ventanas de días completos", "y recuperación de huecos"], steps: "1" });
  s += node(t, { x: c2, y: ROW.B, role: "storage", icons: ["minio"], title: "MinIO", subtitle: "Almacenamiento S3", lines: ["Clave determinista por ventana,", "bucket versionado"], layers: ["bronze"] });
  s += node(t, { x: c3, y: ROW.B, role: "processing", icons: ["apachespark", "delta"], title: "PySpark + Delta Lake", subtitle: "Esquema común y calidad", lines: ["MERGE solo de lo que cambia,", "historial y time travel"], layers: ["silver"], steps: "1" });

  // Row C: the warehouse, dbt and the anomaly detectors
  s += node(t, { x: c1, y: ROW.C, role: "processing", icons: ["dbt"], title: "dbt Core", subtitle: "SQL · staging → marts", lines: ["Incremental, contratos, tests", "y exposures por dashboard"], layers: ["gold"], steps: "4" });
  s += node(t, { x: c2, y: ROW.C, role: "storage", icons: ["postgresql"], title: "PostgreSQL", subtitle: "Warehouse", lines: ["silver · quality · ops · gold", "Upsert idempotente"], layers: ["silver", "gold"] });
  s += node(t, { x: c3, y: ROW.C, role: "processing", icons: ["python"], title: "Anomalías y correcciones", subtitle: "Python · scikit-learn", lines: ["Marca valores raros y propone", "relleno con su confianza"], steps: "2·3" });

  // Row D: serving
  s += node(t, { x: c1, y: ROW.D, role: "serving", icons: ["grafana"], title: "Grafana", subtitle: "Operar la plataforma", lines: ["Dashboards, alertas, calidad", "y correcciones"] });
  s += node(t, { x: c2, y: ROW.D, role: "serving", icons: ["fastapi"], title: "API REST", subtitle: "FastAPI · solo lectura", lines: ["Usuario de solo lectura,", "OpenAPI y paginación"] });
  s += node(t, { x: c3, y: ROW.D, role: "serving", icons: ["react", "apacheecharts", "maplibre"], title: "Web", subtitle: "La isla en cifras", lines: ["Seis dashboards, modo claro", "y oscuro, solo lee la API"] });

  // Arrows
  const right = (c) => c + NODE_W;
  const gap = (a, b) => [right(a) + 2, b - 4];
  const [b1, b2] = gap(c1, c2);
  const [b3, b4] = gap(c2, c3);
  s += arrow([[272, ROW.B + mid], [c1 - 4, ROW.B + mid]], ROLE.source.color);
  s += arrow([[b1, ROW.B + mid], [b2, ROW.B + mid]], P);
  s += arrow([[b3, ROW.B + mid], [b4, ROW.B + mid]], S);
  // Spark writes silver to Postgres too
  s += arrow([[c3 + NODE_W / 2, ROW.B + NODE_H + 2], [c3 + NODE_W / 2, ROW.B + NODE_H + 22], [c2 + NODE_W / 2, ROW.B + NODE_H + 22], [c2 + NODE_W / 2, ROW.C - 4]], P);
  // dbt and the detectors read and write the warehouse
  s += arrow([[b1, ROW.C + mid - 12], [b2, ROW.C + mid - 12]], S);
  s += arrow([[b2, ROW.C + mid + 12], [b1, ROW.C + mid + 12]], P);
  s += arrow([[b3, ROW.C + mid - 12], [b4, ROW.C + mid - 12]], S);
  s += arrow([[b4, ROW.C + mid + 12], [b3, ROW.C + mid + 12]], P);
  // Gold is served
  s += arrow([[c2 + NODE_W / 2, ROW.C + NODE_H + 2], [c2 + NODE_W / 2, ROW.D - 4]], S);
  s += arrow([[c2 + 40, ROW.C + NODE_H + 2], [c2 + 40, ROW.C + NODE_H + 22], [c1 + NODE_W / 2, ROW.C + NODE_H + 22], [c1 + NODE_W / 2, ROW.D - 4]], S);
  s += arrow([[b3, ROW.D + mid], [b4, ROW.D + mid]], V);

  s += rail(t);
  s += legend(t);
  return `${s}</svg>\n`;
}

for (const [name, theme] of Object.entries(THEMES)) {
  const file = path.join(OUT, name === "light" ? "architecture.svg" : "architecture-dark.svg");
  fs.writeFileSync(file, diagram(theme));
  console.log(path.relative(process.cwd(), file));
}

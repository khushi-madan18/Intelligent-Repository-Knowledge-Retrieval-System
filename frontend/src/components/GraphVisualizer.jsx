import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

const SAMPLE_GRAPH = {
  nodes: [
    {
      id: "module:api",
      label: "api",
      type: "module",
      file_path: "src/reporag/api/main.py",
      start_line: 1,
      end_line: 42,
      module: "api",
    },
    {
      id: "class:RepoService",
      label: "RepoService",
      type: "class",
      file_path: "src/reporag/api/repos.py",
      start_line: 14,
      end_line: 76,
      module: "api",
    },
    {
      id: "fn:ingest_repo",
      label: "ingest_repo",
      type: "function",
      file_path: "src/reporag/api/repos.py",
      start_line: 80,
      end_line: 112,
      module: "api",
    },
    {
      id: "module:graph",
      label: "graph",
      type: "module",
      file_path: "src/reporag/graph/call_graph.py",
      start_line: 1,
      end_line: 50,
      module: "graph",
    },
    {
      id: "fn:build_call_graph",
      label: "build_call_graph",
      type: "function",
      file_path: "src/reporag/graph/call_graph.py",
      start_line: 51,
      end_line: 132,
      module: "graph",
    },
  ],
  edges: [
    { id: "e1", source: "module:api", target: "class:RepoService", type: "imports" },
    { id: "e2", source: "class:RepoService", target: "fn:ingest_repo", type: "calls" },
    { id: "e3", source: "fn:ingest_repo", target: "fn:build_call_graph", type: "calls" },
    { id: "e4", source: "fn:build_call_graph", target: "module:graph", type: "imports" },
  ],
};

const NODE_STYLES = {
  function: "fill-teal-600 stroke-teal-900",
  class: "fill-rose-500 stroke-rose-900",
  module: "fill-slate-700 stroke-slate-950",
};

const EDGE_STYLES = {
  calls: "stroke-teal-600",
  imports: "stroke-slate-400 stroke-dasharray-4",
  inherits: "stroke-rose-500 stroke-[3]",
};

export default function GraphVisualizer({ apiFetch, repositoryId }) {
  const [graphType, setGraphType] = useState("call");
  const [rawGraph, setRawGraph] = useState(SAMPLE_GRAPH);
  const [status, setStatus] = useState("sample");
  const [selectedNode, setSelectedNode] = useState(null);
  const [moduleFilter, setModuleFilter] = useState("all");
  const [search, setSearch] = useState("");
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [dragStart, setDragStart] = useState(null);

  useEffect(() => {
    let active = true;
    apiFetch(`/api/v1/repos/${repositoryId}/graph?type=${graphType}`)
      .then((payload) => {
        if (!active) {
          return;
        }
        if (payload.nodes?.length) {
          setRawGraph({
            nodes: payload.nodes,
            edges: payload.edges || [],
          });
          setStatus("live");
        }
      })
      .catch(() => {
        if (active) {
          setRawGraph(SAMPLE_GRAPH);
          setStatus("sample");
        }
      });
    return () => {
      active = false;
    };
  }, [apiFetch, graphType, repositoryId]);

  const modules = useMemo(
    () => Array.from(new Set(rawGraph.nodes.map((node) => node.module || "root"))).sort(),
    [rawGraph.nodes],
  );

  const visibleGraph = useMemo(() => {
    const normalizedSearch = search.trim().toLowerCase();
    const filteredNodes = rawGraph.nodes.filter((node) => {
      const inModule = moduleFilter === "all" || (node.module || "root") === moduleFilter;
      const matchesSearch =
        !normalizedSearch ||
        node.label.toLowerCase().includes(normalizedSearch) ||
        node.id.toLowerCase().includes(normalizedSearch);
      return inModule && matchesSearch;
    });
    const nodeIds = new Set(filteredNodes.map((node) => node.id));
    return {
      nodes: filteredNodes,
      edges: rawGraph.edges.filter(
        (edge) => nodeIds.has(edge.source) && nodeIds.has(edge.target),
      ),
    };
  }, [moduleFilter, rawGraph, search]);

  const layout = useMemo(() => createForceLayout(visibleGraph), [visibleGraph]);
  const selected = selectedNode && layout.nodeMap.get(selectedNode.id);

  function startPan(event) {
    setDragStart({ x: event.clientX - pan.x, y: event.clientY - pan.y });
  }

  function movePan(event) {
    if (!dragStart) {
      return;
    }
    setPan({ x: event.clientX - dragStart.x, y: event.clientY - dragStart.y });
  }

  function stopPan() {
    setDragStart(null);
  }

  function wheelZoom(event) {
    event.preventDefault();
    const next = event.deltaY > 0 ? zoom - 0.08 : zoom + 0.08;
    setZoom(Math.min(1.8, Math.max(0.55, next)));
  }

  return (
    <section className="mt-6">
      <div className="flex flex-col justify-between gap-4 md:flex-row md:items-end">
        <div>
          <p className="section-label">Graph visualizer</p>
          <h2 className="mt-3 text-2xl font-semibold tracking-tight">
            Explore calls, imports, and inheritance.
          </h2>
        </div>
        <span className="badge self-start md:self-auto">
          {status === "live" ? "API graph" : "Sample graph"}
        </span>
      </div>

      <div className="mt-5 grid gap-5 lg:grid-cols-[1fr_18rem]">
        <div className="panel">
          <div className="grid gap-3 md:grid-cols-[9rem_1fr_1fr_auto_auto_auto] md:items-end">
            <label className="text-sm font-medium">
              Graph
              <select
                className="input mt-2"
                onChange={(event) => setGraphType(event.target.value)}
                value={graphType}
              >
                <option value="call">Call graph</option>
                <option value="dependency">Dependency graph</option>
              </select>
            </label>
            <label className="text-sm font-medium">
              Module
              <select
                className="input mt-2"
                onChange={(event) => setModuleFilter(event.target.value)}
                value={moduleFilter}
              >
                <option value="all">All modules</option>
                {modules.map((moduleName) => (
                  <option key={moduleName} value={moduleName}>
                    {moduleName}
                  </option>
                ))}
              </select>
            </label>
            <label className="text-sm font-medium">
              Search
              <input
                className="input mt-2"
                onChange={(event) => setSearch(event.target.value)}
                placeholder="find node"
                value={search}
              />
            </label>
            <button className="btn-secondary justify-center" onClick={() => setZoom(zoom + 0.1)} type="button">
              +
            </button>
            <button className="btn-secondary justify-center" onClick={() => setZoom(zoom - 0.1)} type="button">
              -
            </button>
            <button className="btn-secondary justify-center" onClick={() => setPan({ x: 0, y: 0 })} type="button">
              Reset
            </button>
          </div>

          <div
            className="mt-5 h-[34rem] overflow-hidden rounded-lg border border-line bg-slate-50"
            onMouseDown={startPan}
            onMouseLeave={stopPan}
            onMouseMove={movePan}
            onMouseUp={stopPan}
            onWheel={wheelZoom}
            role="presentation"
          >
            <svg className="h-full w-full" viewBox="0 0 960 540">
              <defs>
                <marker
                  id="arrow"
                  markerHeight="8"
                  markerWidth="8"
                  orient="auto"
                  refX="7"
                  refY="4"
                >
                  <path d="M0,0 L8,4 L0,8 Z" fill="#64748b" />
                </marker>
              </defs>
              <g transform={`translate(${pan.x} ${pan.y}) scale(${zoom})`}>
                {layout.edges.map((edge) => (
                  <line
                    className={`${EDGE_STYLES[edge.type] || "stroke-slate-400"} stroke-2`}
                    key={edge.id || `${edge.source}-${edge.target}`}
                    markerEnd="url(#arrow)"
                    x1={edge.sourceNode.x}
                    x2={edge.targetNode.x}
                    y1={edge.sourceNode.y}
                    y2={edge.targetNode.y}
                  />
                ))}
                {layout.nodes.map((node) => (
                  <NodeShape
                    highlighted={isHighlighted(node, search)}
                    key={node.id}
                    node={node}
                    onClick={(event) => {
                      event.stopPropagation();
                      setSelectedNode(node);
                    }}
                    selected={selectedNode?.id === node.id}
                  />
                ))}
              </g>
            </svg>
          </div>
        </div>

        <aside className="panel h-fit">
          <p className="text-sm font-semibold">Node details</p>
          {selected ? (
            <div className="mt-4 space-y-3 text-sm">
              <span className="badge">{selected.type}</span>
              <p className="font-medium">{selected.label}</p>
              <p className="break-words text-slate-500">{selected.id}</p>
              <p className="break-words text-slate-600">{selected.file_path}</p>
              {selected.file_path ? (
                <Link className="btn-primary justify-center" to={nodeCodeUrl(repositoryId, selected)}>
                  Open code
                </Link>
              ) : null}
            </div>
          ) : (
            <p className="mt-3 text-sm text-slate-500">Click a node to inspect it.</p>
          )}

          <div className="mt-6 border-t border-line pt-4 text-xs text-slate-500">
            <p>Circles are functions, diamonds are classes, squares are modules.</p>
            <p className="mt-2">Solid edges call, dashed edges import, bold rose edges inherit.</p>
          </div>
        </aside>
      </div>
    </section>
  );
}

function NodeShape({ highlighted, node, onClick, selected }) {
  const style = NODE_STYLES[node.type] || NODE_STYLES.function;
  const selectedStyle = selected ? "stroke-[5]" : "stroke-2";
  const highlightStyle = highlighted ? "drop-shadow-[0_0_8px_rgba(13,148,136,0.75)]" : "";

  return (
    <g className="cursor-pointer" onClick={onClick}>
      {node.type === "module" ? (
        <rect
          className={`${style} ${selectedStyle} ${highlightStyle}`}
          height="38"
          rx="6"
          width="72"
          x={node.x - 36}
          y={node.y - 19}
        />
      ) : node.type === "class" ? (
        <polygon
          className={`${style} ${selectedStyle} ${highlightStyle}`}
          points={`${node.x},${node.y - 27} ${node.x + 32},${node.y} ${node.x},${node.y + 27} ${node.x - 32},${node.y}`}
        />
      ) : (
        <circle
          className={`${style} ${selectedStyle} ${highlightStyle}`}
          cx={node.x}
          cy={node.y}
          r="22"
        />
      )}
      <text
        className="pointer-events-none select-none fill-slate-900 text-[12px] font-semibold"
        textAnchor="middle"
        x={node.x}
        y={node.y + 42}
      >
        {shortLabel(node.label)}
      </text>
    </g>
  );
}

function createForceLayout(graph) {
  const centerX = 480;
  const centerY = 270;
  const modules = Array.from(new Set(graph.nodes.map((node) => node.module || "root")));
  const moduleCenters = new Map(
    modules.map((moduleName, index) => {
      const angle = (index / Math.max(modules.length, 1)) * Math.PI * 2 - Math.PI / 2;
      return [
        moduleName,
        {
          x: centerX + Math.cos(angle) * 260,
          y: centerY + Math.sin(angle) * 150,
        },
      ];
    }),
  );

  const grouped = new Map();
  for (const node of graph.nodes) {
    const moduleName = node.module || "root";
    grouped.set(moduleName, [...(grouped.get(moduleName) || []), node]);
  }

  const positioned = [];
  for (const [moduleName, nodes] of grouped.entries()) {
    const center = moduleCenters.get(moduleName);
    nodes.forEach((node, index) => {
      const angle = (index / Math.max(nodes.length, 1)) * Math.PI * 2;
      const radius = 44 + Math.min(nodes.length, 12) * 8;
      positioned.push({
        ...node,
        x: center.x + Math.cos(angle) * radius,
        y: center.y + Math.sin(angle) * radius,
      });
    });
  }

  const nodeMap = new Map(positioned.map((node) => [node.id, node]));
  const edges = graph.edges
    .map((edge) => ({
      ...edge,
      sourceNode: nodeMap.get(edge.source),
      targetNode: nodeMap.get(edge.target),
    }))
    .filter((edge) => edge.sourceNode && edge.targetNode);

  return { edges, nodeMap, nodes: positioned };
}

function isHighlighted(node, search) {
  const value = search.trim().toLowerCase();
  return Boolean(value && `${node.id} ${node.label}`.toLowerCase().includes(value));
}

function nodeCodeUrl(repositoryId, node) {
  const search = new URLSearchParams({
    file: node.file_path,
    lines: `${node.start_line || 1}-${node.end_line || node.start_line || 1}`,
  });
  return `/repos/${repositoryId}?${search.toString()}`;
}

function shortLabel(label) {
  return label.length > 20 ? `${label.slice(0, 18)}...` : label;
}

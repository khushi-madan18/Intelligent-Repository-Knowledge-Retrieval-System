import { useMemo, useState } from "react";

function buildTree(files) {
  const root = { name: "root", path: "", type: "directory", children: [] };
  files.forEach((file) => {
    const parts = file.path.split("/").filter(Boolean);
    let cursor = root;
    parts.forEach((part, index) => {
      const path = parts.slice(0, index + 1).join("/");
      const type = index === parts.length - 1 ? "file" : "directory";
      let child = cursor.children.find((node) => node.name === part);
      if (!child) {
        child = {
          name: part,
          path,
          type,
          language: type === "file" ? file.language : undefined,
          children: [],
        };
        cursor.children.push(child);
      }
      cursor = child;
    });
  });
  return sortTree(root.children);
}

function sortTree(nodes) {
  return nodes
    .map((node) => ({
      ...node,
      children: sortTree(node.children || []),
    }))
    .sort((left, right) => {
      if (left.type !== right.type) {
        return left.type === "directory" ? -1 : 1;
      }
      return left.name.localeCompare(right.name);
    });
}

export default function FileTree({ files, selectedPath, onSelect }) {
  const tree = useMemo(() => buildTree(files), [files]);
  const [expanded, setExpanded] = useState(() => new Set(["src", "frontend"]));

  function toggle(path) {
    setExpanded((current) => {
      const next = new Set(current);
      if (next.has(path)) {
        next.delete(path);
      } else {
        next.add(path);
      }
      return next;
    });
  }

  return (
    <div className="rounded-lg border border-line bg-white">
      <div className="border-b border-line px-4 py-3">
        <p className="text-sm font-semibold">Files</p>
      </div>
      <div className="max-h-[640px] overflow-auto p-2 text-sm">
        {tree.map((node) => (
          <TreeNode
            expanded={expanded}
            key={node.path}
            node={node}
            onSelect={onSelect}
            selectedPath={selectedPath}
            toggle={toggle}
          />
        ))}
      </div>
    </div>
  );
}

function TreeNode({ node, expanded, selectedPath, onSelect, toggle, depth = 0 }) {
  const isDirectory = node.type === "directory";
  const isExpanded = expanded.has(node.path);
  const isSelected = selectedPath === node.path;
  const icon = isDirectory ? (isExpanded ? "v" : ">") : fileIcon(node.language);

  return (
    <div>
      <button
        className={`flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left transition ${
          isSelected ? "bg-teal-50 text-brand" : "hover:bg-slate-50"
        }`}
        style={{ paddingLeft: `${depth * 14 + 8}px` }}
        type="button"
        onClick={() => (isDirectory ? toggle(node.path) : onSelect(node))}
      >
        <span className="w-4 text-slate-500">{icon}</span>
        <span className="truncate">{node.name}</span>
      </button>
      {isDirectory && isExpanded
        ? node.children.map((child) => (
            <TreeNode
              depth={depth + 1}
              expanded={expanded}
              key={child.path}
              node={child}
              onSelect={onSelect}
              selectedPath={selectedPath}
              toggle={toggle}
            />
          ))
        : null}
    </div>
  );
}

function fileIcon(language) {
  if (language === "python") {
    return "Py";
  }
  if (language === "javascript") {
    return "JS";
  }
  if (language === "typescript") {
    return "TS";
  }
  return "{}";
}

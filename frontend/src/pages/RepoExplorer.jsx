import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";

import CodeViewer from "../components/CodeViewer.jsx";
import FileTree from "../components/FileTree.jsx";
import GraphVisualizer from "../components/GraphVisualizer.jsx";
import RepoSelector from "../components/RepoSelector.jsx";
import { useAuth } from "../context/AuthContext.jsx";

const SAMPLE_FILES = [
  {
    path: "src/auth.py",
    language: "python",
    content:
      "def authenticate_user(email, token):\n    if not token:\n        return False\n    return email.endswith('@example.com')\n",
  },
  {
    path: "frontend/src/App.jsx",
    language: "javascript",
    content:
      "import { Routes, Route } from 'react-router-dom';\n\nexport default function App() {\n  return <Routes />;\n}\n",
  },
  {
    path: "frontend/src/api/client.ts",
    language: "typescript",
    content:
      "type ApiResult = {\n  answer: string;\n};\n\nexport async function queryRepo(): Promise<ApiResult> {\n  return { answer: 'ok' };\n}\n",
  },
];

export default function RepoExplorer() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const { apiFetch } = useAuth();
  const [view, setView] = useState(searchParams.get("view") || "files");
  const [files, setFiles] = useState(SAMPLE_FILES);
  const [selectedPath, setSelectedPath] = useState(
    searchParams.get("file") || SAMPLE_FILES[0].path,
  );
  const [selectedContent, setSelectedContent] = useState(SAMPLE_FILES[0].content);
  const [language, setLanguage] = useState(SAMPLE_FILES[0].language);
  const [highlightRange, setHighlightRange] = useState(
    parseRange(searchParams.get("lines")),
  );
  const [status, setStatus] = useState("sample");
  const [error, setError] = useState("");

  const selectedFile = useMemo(
    () => files.find((file) => file.path === selectedPath),
    [files, selectedPath],
  );

  useEffect(() => {
    let active = true;
    apiFetch(`/api/v1/repos/${id}/tree`)
      .then((payload) => {
        if (!active) {
          return;
        }
        const fetchedFiles = payload.files || [];
        if (fetchedFiles.length) {
          setFiles(fetchedFiles);
          setSelectedPath((current) => current || fetchedFiles[0].path);
          setStatus("live");
        }
      })
      .catch(() => {
        if (active) {
          setStatus("sample");
        }
      });
    return () => {
      active = false;
    };
  }, [apiFetch, id]);

  useEffect(() => {
    if (!selectedFile) {
      return;
    }
    setLanguage(selectedFile.language);
    setSearchParams((current) => {
      const next = new URLSearchParams(current);
      next.set("file", selectedFile.path);
      if (highlightRange) {
        next.set("lines", `${highlightRange.start}-${highlightRange.end}`);
      } else {
        next.delete("lines");
      }
      return next;
    });

    if (selectedFile.content !== undefined) {
      setSelectedContent(selectedFile.content);
      return;
    }

    apiFetch(`/api/v1/repos/${id}/files?path=${encodeURIComponent(selectedFile.path)}`)
      .then((payload) => setSelectedContent(payload.content || ""))
      .catch((err) => setError(err.message));
  }, [apiFetch, highlightRange, id, selectedFile, setSearchParams]);

  function selectFile(file) {
    setSelectedPath(file.path);
    setError("");
  }

  function updateHighlightRange(range) {
    setHighlightRange(range);
  }

  function updateView(nextView) {
    setView(nextView);
    setSearchParams((current) => {
      const next = new URLSearchParams(current);
      next.set("view", nextView);
      return next;
    });
  }

  return (
    <section>
      <div className="flex flex-col justify-between gap-4 md:flex-row md:items-end">
        <div>
          <Link className="text-sm font-medium text-brand" to="/repos">
            Back to repositories
          </Link>
          <p className="section-label mt-5">Repository explorer</p>
          <h1 className="mt-3 text-3xl font-semibold tracking-tight">{id}</h1>
          <p className="mt-2 max-w-2xl text-slate-600">
            Browse files, inspect syntax-highlighted source, and highlight line
            ranges for citation cross-references.
          </p>
        </div>
        <div className="flex flex-col items-start gap-3 md:items-end">
          <RepoSelector
            apiFetch={apiFetch}
            currentRepoId={id}
            onSelect={(repoId) => navigate(`/repos/${repoId}`)}
          />
          <span className="badge self-start md:self-auto">
            {status === "live" ? "API data" : "Sample data"}
          </span>
        </div>
      </div>

      {error ? <p className="mt-4 text-sm text-accent">{error}</p> : null}

      <div className="mt-6 flex gap-2">
        <button
          className={view === "files" ? "btn-primary" : "btn-secondary"}
          onClick={() => updateView("files")}
          type="button"
        >
          Files
        </button>
        <button
          className={view === "graph" ? "btn-primary" : "btn-secondary"}
          onClick={() => updateView("graph")}
          type="button"
        >
          Graph
        </button>
      </div>

      {view === "graph" ? (
        <GraphVisualizer apiFetch={apiFetch} repositoryId={id} />
      ) : (
        <div className="mt-6 grid gap-5 lg:grid-cols-[18rem_1fr]">
          <FileTree
            files={files}
            onSelect={selectFile}
            selectedPath={selectedPath}
          />
          <CodeViewer
            code={selectedContent}
            filePath={selectedPath}
            highlightRange={highlightRange}
            language={language}
            onHighlightRangeChange={updateHighlightRange}
          />
        </div>
      )}
    </section>
  );
}

function parseRange(value) {
  if (!value) {
    return null;
  }
  const match = value.match(/^(\d+)(?:-(\d+))?$/);
  if (!match) {
    return null;
  }
  const start = Number(match[1]);
  const end = Number(match[2] || match[1]);
  return { start: Math.min(start, end), end: Math.max(start, end) };
}

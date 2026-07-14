import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { useAuth } from "../context/AuthContext.jsx";

export default function Repos() {
  const { apiFetch } = useAuth();
  const [repos, setRepos] = useState([]);
  const [source, setSource] = useState("");
  const [status, setStatus] = useState("idle");
  const [error, setError] = useState("");

  useEffect(() => {
    apiFetch("/api/v1/repos")
      .then((payload) => setRepos(payload.repositories || []))
      .catch((err) => setError(err.message));
  }, [apiFetch]);

  async function ingestRepository(event) {
    event.preventDefault();
    setStatus("saving");
    setError("");
    try {
      const body = source.startsWith("http")
        ? { repo_url: source }
        : { local_path: source };
      const created = await apiFetch("/api/v1/repos/ingest", {
        method: "POST",
        body: JSON.stringify(body),
      });
      setRepos((current) => [created, ...current]);
      setSource("");
      setStatus("idle");
    } catch (err) {
      setError(err.message);
      setStatus("idle");
    }
  }

  return (
    <section>
      <p className="section-label">Repositories</p>
      <h1 className="mt-3 text-3xl font-semibold tracking-tight">
        Ingest and inspect repositories.
      </h1>

      <form className="panel mt-6 flex flex-col gap-3 md:flex-row" onSubmit={ingestRepository}>
        <input
          className="input"
          value={source}
          onChange={(event) => setSource(event.target.value)}
          placeholder="https://github.com/org/repo or local path"
          required
        />
        <button className="btn-primary md:w-36" type="submit" disabled={status === "saving"}>
          {status === "saving" ? "Starting" : "Ingest"}
        </button>
      </form>

      {error ? <p className="mt-4 text-sm text-accent">{error}</p> : null}

      <div className="mt-6 grid gap-3">
        {repos.length === 0 ? (
          <div className="panel text-sm text-slate-600">No repositories yet.</div>
        ) : (
          repos.map((repo) => (
            <Link className="panel block hover:border-brand" key={repo.id} to={`/repos/${repo.id}`}>
              <div className="flex flex-col justify-between gap-3 md:flex-row md:items-center">
                <div>
                  <p className="font-medium">{repo.source}</p>
                  <p className="mt-1 text-sm text-slate-500">
                    Branch {repo.branch} | {repo.file_count} files
                  </p>
                </div>
                <span className="badge">{repo.status}</span>
              </div>
            </Link>
          ))
        )}
      </div>
    </section>
  );
}

import { useEffect, useState } from "react";

export default function RepoSelector({ apiFetch, currentRepoId, onSelect }) {
  const [repos, setRepos] = useState([]);

  useEffect(() => {
    let active = true;
    apiFetch("/api/v1/repos")
      .then((payload) => {
        if (active) {
          setRepos(payload.repositories || []);
        }
      })
      .catch(() => setRepos([]));
    return () => {
      active = false;
    };
  }, [apiFetch]);

  return (
    <label className="text-sm font-medium text-slate-600">
      Repository
      <select
        className="input mt-2 w-64"
        onChange={(event) => onSelect(event.target.value)}
        value={currentRepoId}
      >
        <option value={currentRepoId}>{currentRepoId}</option>
        {repos
          .filter((repo) => String(repo.id) !== String(currentRepoId))
          .map((repo) => (
            <option key={repo.id} value={repo.id}>
              {repo.source || repo.id}
            </option>
          ))}
      </select>
    </label>
  );
}

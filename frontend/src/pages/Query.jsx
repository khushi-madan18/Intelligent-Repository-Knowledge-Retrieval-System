import { useState } from "react";

import { useAuth } from "../context/AuthContext.jsx";

export default function Query() {
  const { apiFetch } = useAuth();
  const [query, setQuery] = useState("");
  const [answer, setAnswer] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function submitQuery(event) {
    event.preventDefault();
    setLoading(true);
    setError("");
    setAnswer(null);
    try {
      const payload = await apiFetch("/api/v1/query", {
        method: "POST",
        body: JSON.stringify({ query, query_type: "exploratory" }),
      });
      setAnswer(payload);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <section>
      <p className="section-label">Query</p>
      <h1 className="mt-3 text-3xl font-semibold tracking-tight">
        Ask repository questions.
      </h1>

      <form className="panel mt-6" onSubmit={submitQuery}>
        <label className="text-sm font-medium" htmlFor="query">
          Question
        </label>
        <textarea
          className="input mt-2 min-h-32"
          id="query"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Explain the authentication flow"
          required
        />
        <button className="btn-primary mt-4" type="submit" disabled={loading}>
          {loading ? "Searching" : "Ask"}
        </button>
      </form>

      {error ? <p className="mt-4 text-sm text-accent">{error}</p> : null}

      {answer ? (
        <div className="panel mt-6">
          <h2 className="text-lg font-semibold">Answer</h2>
          <p className="mt-3 whitespace-pre-wrap text-slate-700">{answer.answer}</p>
          <div className="mt-5">
            <p className="text-sm font-medium">Citations</p>
            <div className="mt-2 flex flex-wrap gap-2">
              {answer.citations?.length ? (
                answer.citations.map((citation) => (
                  <span className="badge" key={citation.marker}>
                    {citation.marker}
                  </span>
                ))
              ) : (
                <span className="text-sm text-slate-500">No citations returned.</span>
              )}
            </div>
          </div>
        </div>
      ) : null}
    </section>
  );
}

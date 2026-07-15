import { useMemo, useState } from "react";

import AnswerDisplay from "../components/AnswerDisplay.jsx";
import QueryInput from "../components/QueryInput.jsx";
import { useAuth } from "../context/AuthContext.jsx";

export default function QueryInterface() {
  const { apiFetch } = useAuth();
  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [repositoryId, setRepositoryId] = useState("sample-repo");

  const hasHistory = messages.length > 0;
  const history = useMemo(
    () => messages.filter((message) => message.role === "user").map((message) => message.content),
    [messages],
  );

  async function submitQuery(query) {
    const userMessage = {
      id: crypto.randomUUID(),
      role: "user",
      content: query,
    };
    setMessages((current) => [...current, userMessage]);
    setLoading(true);
    setError("");

    try {
      const payload = await apiFetch("/api/v1/query", {
        method: "POST",
        body: JSON.stringify({
          query,
          query_type: "exploratory",
          repository_id: repositoryId || null,
        }),
      });
      setMessages((current) => [
        ...current,
        {
          id: crypto.randomUUID(),
          role: "assistant",
          content: payload.answer || "No answer returned.",
          citations: payload.citations || [],
          metadata: payload.metadata || {},
        },
      ]);
    } catch (err) {
      setError(err.message);
      setMessages((current) => [
        ...current,
        {
          id: crypto.randomUUID(),
          role: "assistant",
          content: "I could not complete that query. Check the API connection and try again.",
          citations: [],
        },
      ]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <section>
      <div className="flex flex-col justify-between gap-4 md:flex-row md:items-end">
        <div>
          <p className="section-label">Conversational Q&A</p>
          <h1 className="mt-3 text-3xl font-semibold tracking-tight">
            Ask, inspect citations, jump to code.
          </h1>
          <p className="mt-2 max-w-2xl text-slate-600">
            Answers keep citation markers inline. Click any citation to open the
            repository explorer at the referenced file and line range.
          </p>
        </div>
        <label className="text-sm font-medium text-slate-600">
          Repository ID
          <input
            className="input mt-2 w-56"
            onChange={(event) => setRepositoryId(event.target.value)}
            value={repositoryId}
          />
        </label>
      </div>

      <div className="mt-6 grid gap-5 lg:grid-cols-[1fr_16rem]">
        <div className="space-y-4">
          <QueryInput disabled={loading} onSubmit={submitQuery} />
          {error ? <p className="text-sm text-accent">{error}</p> : null}
          <div className="space-y-4">
            {hasHistory ? (
              messages.map((message) => (
                <AnswerDisplay
                  key={message.id}
                  message={message}
                  repositoryId={repositoryId}
                />
              ))
            ) : (
              <div className="panel text-sm text-slate-600">
                Start by asking where a function is defined, how a flow works, or
                which files are involved in a feature.
              </div>
            )}
            {loading ? (
              <div className="panel flex items-center gap-3 text-sm text-slate-600">
                <span className="h-2 w-2 animate-pulse rounded-full bg-brand" />
                Searching code, graph, and citations...
              </div>
            ) : null}
          </div>
        </div>

        <aside className="panel h-fit">
          <p className="text-sm font-semibold">Session history</p>
          <div className="mt-3 space-y-2">
            {history.length ? (
              history.map((item, index) => (
                <p className="rounded-md bg-slate-50 p-2 text-xs text-slate-600" key={`${item}-${index}`}>
                  {item}
                </p>
              ))
            ) : (
              <p className="text-sm text-slate-500">No queries yet.</p>
            )}
          </div>
        </aside>
      </div>
    </section>
  );
}

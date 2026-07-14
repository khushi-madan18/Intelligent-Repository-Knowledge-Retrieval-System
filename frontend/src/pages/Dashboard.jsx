import { Link } from "react-router-dom";

import { useAuth } from "../context/AuthContext.jsx";

export default function Dashboard() {
  const { user } = useAuth();

  return (
    <section>
      <p className="section-label">Dashboard</p>
      <div className="mt-3 flex flex-col justify-between gap-4 md:flex-row md:items-end">
        <div>
          <h1 className="text-3xl font-semibold tracking-tight">
            Good to see you{user?.display_name ? `, ${user.display_name}` : ""}.
          </h1>
          <p className="mt-2 max-w-2xl text-slate-600">
            Ingest repositories, inspect their structure, and ask cited
            questions from the query workspace.
          </p>
        </div>
        <Link className="btn-primary" to="/query">
          Ask a question
        </Link>
      </div>

      <div className="mt-8 grid gap-4 md:grid-cols-3">
        <SummaryCard label="Repositories" value="0" helper="Ready to ingest" />
        <SummaryCard label="Queries" value="0" helper="No recent activity" />
        <SummaryCard label="Auth" value="JWT" helper="In-memory token state" />
      </div>
    </section>
  );
}

function SummaryCard({ label, value, helper }) {
  return (
    <div className="panel">
      <p className="text-sm font-medium text-slate-500">{label}</p>
      <p className="mt-3 text-3xl font-semibold">{value}</p>
      <p className="mt-2 text-sm text-slate-500">{helper}</p>
    </div>
  );
}

import { Link, useParams } from "react-router-dom";

export default function RepoDetail() {
  const { id } = useParams();

  return (
    <section>
      <Link className="text-sm font-medium text-brand" to="/repos">
        Back to repositories
      </Link>
      <div className="panel mt-4">
        <p className="section-label">Repository</p>
        <h1 className="mt-3 text-3xl font-semibold tracking-tight">{id}</h1>
        <p className="mt-3 max-w-2xl text-slate-600">
          Detailed file graphs, symbols, and ingestion activity will appear here
          as the repository explorer milestone expands.
        </p>
      </div>
    </section>
  );
}

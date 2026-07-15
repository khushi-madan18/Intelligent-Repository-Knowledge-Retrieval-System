import { Link } from "react-router-dom";

export function parseCitationMarker(marker) {
  const match = marker.match(/^\[([^:]+):(\d+)-(\d+)\]$/);
  if (!match) {
    return null;
  }
  return {
    filePath: match[1],
    startLine: Number(match[2]),
    endLine: Number(match[3]),
  };
}

export default function CitationLink({ citation, repositoryId }) {
  const parsed = parseCitationMarker(citation.marker);
  if (!parsed || !repositoryId) {
    return <span className="badge">{citation.marker}</span>;
  }

  const search = new URLSearchParams({
    file: parsed.filePath,
    lines: `${parsed.startLine}-${parsed.endLine}`,
  });

  return (
    <Link
      className={`badge transition hover:bg-teal-100 ${
        citation.valid === false ? "bg-red-50 text-accent hover:bg-red-100" : ""
      }`}
      to={`/repos/${repositoryId}?${search.toString()}`}
    >
      {citation.marker}
    </Link>
  );
}

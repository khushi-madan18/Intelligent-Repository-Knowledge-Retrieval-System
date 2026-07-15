import CitationLink from "./CitationLink.jsx";

const CITATION_PATTERN = /(\[[^\[\]]+?:\d+-\d+\])/g;

export default function AnswerDisplay({ message, repositoryId }) {
  if (message.role === "user") {
    return (
      <article className="ml-auto max-w-3xl rounded-lg bg-brand px-4 py-3 text-sm leading-6 text-white">
        {message.content}
      </article>
    );
  }

  return (
    <article className="panel max-w-4xl">
      <div className="prose-lite">{renderAnswer(message.content, message.citations, repositoryId)}</div>
      {message.citations?.length ? (
        <div className="mt-5 border-t border-line pt-4">
          <p className="text-sm font-medium">Citations</p>
          <div className="mt-2 flex flex-wrap gap-2">
            {message.citations.map((citation) => (
              <CitationLink
                citation={citation}
                key={citation.marker}
                repositoryId={repositoryId}
              />
            ))}
          </div>
        </div>
      ) : null}
    </article>
  );
}

function renderAnswer(answer, citations = [], repositoryId) {
  return answer.split("\n").map((paragraph, index) => (
    <p className="mb-3 last:mb-0" key={`${paragraph}-${index}`}>
      {renderInline(paragraph, citations, repositoryId)}
    </p>
  ));
}

function renderInline(text, citations, repositoryId) {
  return text.split(CITATION_PATTERN).map((part, index) => {
    const citation = citations.find((item) => item.marker === part);
    if (citation) {
      return (
        <CitationLink
          citation={citation}
          key={`${part}-${index}`}
          repositoryId={repositoryId}
        />
      );
    }
    if (part.startsWith("`") && part.endsWith("`")) {
      return (
        <code className="rounded bg-slate-100 px-1 py-0.5 text-sm text-ink" key={`${part}-${index}`}>
          {part.slice(1, -1)}
        </code>
      );
    }
    return part;
  });
}

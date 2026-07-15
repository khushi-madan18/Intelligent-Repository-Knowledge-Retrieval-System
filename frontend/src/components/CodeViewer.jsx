const KEYWORDS = {
  python: [
    "async",
    "await",
    "class",
    "def",
    "elif",
    "else",
    "except",
    "False",
    "for",
    "from",
    "if",
    "import",
    "in",
    "is",
    "None",
    "not",
    "pass",
    "raise",
    "return",
    "True",
    "try",
    "while",
    "with",
  ],
  javascript: [
    "async",
    "await",
    "class",
    "const",
    "else",
    "export",
    "false",
    "for",
    "from",
    "function",
    "if",
    "import",
    "let",
    "new",
    "null",
    "return",
    "true",
  ],
  typescript: [
    "async",
    "await",
    "class",
    "const",
    "else",
    "export",
    "false",
    "for",
    "from",
    "function",
    "if",
    "import",
    "interface",
    "let",
    "new",
    "null",
    "return",
    "type",
    "true",
  ],
};

export default function CodeViewer({
  code,
  filePath,
  language,
  highlightRange,
  onHighlightRangeChange,
}) {
  const lines = code ? code.split("\n") : [];

  if (!filePath) {
    return (
      <div className="panel flex min-h-[360px] items-center justify-center text-sm text-slate-500">
        Select a file to preview its contents.
      </div>
    );
  }

  return (
    <div className="overflow-hidden rounded-lg border border-line bg-slate-950 text-slate-100 shadow-panel">
      <div className="flex flex-col justify-between gap-3 border-b border-slate-800 bg-slate-900 px-4 py-3 md:flex-row md:items-center">
        <div>
          <p className="text-sm font-semibold">{filePath}</p>
          <p className="mt-1 text-xs text-slate-400">{language || "plain text"}</p>
        </div>
        <HighlightControl
          highlightRange={highlightRange}
          onChange={onHighlightRangeChange}
        />
      </div>
      <pre className="max-h-[640px] overflow-auto py-3 text-sm leading-6">
        {lines.map((line, index) => {
          const lineNumber = index + 1;
          const highlighted = isHighlighted(lineNumber, highlightRange);
          return (
            <div
              className={`grid grid-cols-[4rem_1fr] ${
                highlighted ? "bg-amber-300/20" : ""
              }`}
              key={`${filePath}-${lineNumber}`}
            >
              <span className="select-none border-r border-slate-800 pr-3 text-right text-slate-500">
                {lineNumber}
              </span>
              <code
                className="min-w-0 px-4 font-mono"
                dangerouslySetInnerHTML={{
                  __html: highlightSyntax(line || " ", language),
                }}
              />
            </div>
          );
        })}
      </pre>
    </div>
  );
}

function HighlightControl({ highlightRange, onChange }) {
  return (
    <label className="flex items-center gap-2 text-xs text-slate-300">
      Lines
      <input
        className="w-24 rounded-md border border-slate-700 bg-slate-950 px-2 py-1 text-slate-100 outline-none focus:border-brand"
        placeholder="3-8"
        value={highlightRangeToText(highlightRange)}
        onChange={(event) => onChange(parseHighlightRange(event.target.value))}
      />
    </label>
  );
}

function highlightRangeToText(range) {
  if (!range) {
    return "";
  }
  return `${range.start}-${range.end}`;
}

function parseHighlightRange(value) {
  const match = value.match(/^(\d+)(?:-(\d+))?$/);
  if (!match) {
    return null;
  }
  const start = Number(match[1]);
  const end = Number(match[2] || match[1]);
  return { start: Math.min(start, end), end: Math.max(start, end) };
}

function isHighlighted(lineNumber, range) {
  return Boolean(range && lineNumber >= range.start && lineNumber <= range.end);
}

function highlightSyntax(line, language) {
  const escaped = escapeHtml(line);
  const keywordPattern = KEYWORDS[language]?.join("|");
  if (!keywordPattern) {
    return escaped;
  }
  return escaped
    .replace(
      /(&quot;.*?&quot;|&#039;.*?&#039;|`.*?`)/g,
      '<span class="text-emerald-300">$1</span>',
    )
    .replace(
      new RegExp(`\\b(${keywordPattern})\\b`, "g"),
      '<span class="text-sky-300">$1</span>',
    )
    .replace(
      /(#[^\n]*|\/\/[^\n]*)/g,
      '<span class="text-slate-500">$1</span>',
    );
}

function escapeHtml(value) {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

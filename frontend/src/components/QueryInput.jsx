import { useState } from "react";

export default function QueryInput({ disabled, onSubmit }) {
  const [value, setValue] = useState("");

  function submit(event) {
    event.preventDefault();
    const query = value.trim();
    if (!query) {
      return;
    }
    onSubmit(query);
    setValue("");
  }

  return (
    <form className="panel" onSubmit={submit}>
      <label className="text-sm font-medium" htmlFor="query">
        Ask a question
      </label>
      <div className="mt-2 flex flex-col gap-3 md:flex-row">
        <textarea
          className="input min-h-24 md:min-h-0"
          disabled={disabled}
          id="query"
          onChange={(event) => setValue(event.target.value)}
          placeholder="How does authentication flow from login to token refresh?"
          value={value}
        />
        <button className="btn-primary justify-center md:w-32" disabled={disabled} type="submit">
          {disabled ? "Thinking" : "Send"}
        </button>
      </div>
    </form>
  );
}

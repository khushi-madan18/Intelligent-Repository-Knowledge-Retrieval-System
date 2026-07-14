import { Navigate, useLocation } from "react-router-dom";

import { useAuth } from "../context/AuthContext.jsx";

export default function Login() {
  const { isAuthenticated, loginWithGoogle } = useAuth();
  const location = useLocation();
  const redirectTo = location.state?.from?.pathname || "/";

  if (isAuthenticated) {
    return <Navigate to={redirectTo} replace />;
  }

  return (
    <section className="mx-auto grid max-w-4xl gap-8 py-10 md:grid-cols-[1fr_0.9fr] md:items-center">
      <div>
        <p className="section-label">Repository intelligence</p>
        <h1 className="mt-3 text-4xl font-semibold tracking-tight text-ink">
          Sign in to explore code with citations.
        </h1>
        <p className="mt-4 max-w-xl text-base leading-7 text-slate-600">
          RepoRAG connects repository structure, retrieval, and cited answers in
          one workspace. Use Google OAuth to enter the app.
        </p>
      </div>

      <div className="panel">
        <h2 className="text-xl font-semibold">Welcome back</h2>
        <p className="mt-2 text-sm leading-6 text-slate-600">
          Authentication starts at the backend OAuth endpoint and returns JWT
          access and refresh tokens for API calls.
        </p>
        <button
          className="btn-primary mt-6 w-full justify-center"
          type="button"
          onClick={loginWithGoogle}
        >
          Continue with Google
        </button>
      </div>
    </section>
  );
}

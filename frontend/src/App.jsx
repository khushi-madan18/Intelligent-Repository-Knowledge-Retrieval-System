import { Link, NavLink, Route, Routes } from "react-router-dom";

import ProtectedRoute from "./components/ProtectedRoute.jsx";
import { useAuth } from "./context/AuthContext.jsx";
import Dashboard from "./pages/Dashboard.jsx";
import Login from "./pages/Login.jsx";
import QueryInterface from "./pages/QueryInterface.jsx";
import RepoExplorer from "./pages/RepoExplorer.jsx";
import Repos from "./pages/Repos.jsx";

function AppShell() {
  const { isAuthenticated, logout, user } = useAuth();

  return (
    <div className="min-h-screen bg-mist text-ink">
      <header className="border-b border-line bg-white">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-5 py-4">
          <Link to="/" className="text-lg font-semibold tracking-tight">
            RepoRAG
          </Link>
          <nav className="flex items-center gap-2 text-sm">
            {isAuthenticated ? (
              <>
                <NavItem to="/repos">Repos</NavItem>
                <NavItem to="/query">Query</NavItem>
                <span className="hidden text-slate-500 sm:inline">
                  {user?.email || "Signed in"}
                </span>
                <button className="btn-secondary" type="button" onClick={logout}>
                  Logout
                </button>
              </>
            ) : (
              <NavItem to="/login">Login</NavItem>
            )}
          </nav>
        </div>
      </header>

      <main className="mx-auto max-w-6xl px-5 py-8">
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route element={<ProtectedRoute />}>
            <Route path="/" element={<Dashboard />} />
            <Route path="/repos" element={<Repos />} />
            <Route path="/repos/:id" element={<RepoExplorer />} />
            <Route path="/query" element={<QueryInterface />} />
          </Route>
        </Routes>
      </main>
    </div>
  );
}

function NavItem({ to, children }) {
  return (
    <NavLink
      to={to}
      className={({ isActive }) =>
        `rounded-md px-3 py-2 transition ${
          isActive ? "bg-teal-50 text-brand" : "text-slate-600 hover:bg-slate-100"
        }`
      }
    >
      {children}
    </NavLink>
  );
}

export default function App() {
  return <AppShell />;
}

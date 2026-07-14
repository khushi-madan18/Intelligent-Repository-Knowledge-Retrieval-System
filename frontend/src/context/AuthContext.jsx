import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";

import { apiFetch, googleLoginUrl, setAccessToken } from "../api/client.js";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [accessToken, setStoredAccessToken] = useState(null);
  const [refreshToken, setRefreshToken] = useState(null);
  const [user, setUser] = useState(null);
  const [status, setStatus] = useState("anonymous");

  const applyTokens = useCallback((payload) => {
    setStoredAccessToken(payload.access_token);
    setRefreshToken(payload.refresh_token || null);
    setAccessToken(payload.access_token);
    setUser(payload.user || null);
    setStatus("authenticated");
  }, []);

  const loginWithGoogle = useCallback(() => {
    window.location.assign(googleLoginUrl());
  }, []);

  const logout = useCallback(() => {
    setStoredAccessToken(null);
    setRefreshToken(null);
    setUser(null);
    setAccessToken(null);
    setStatus("anonymous");
  }, []);

  const refresh = useCallback(async () => {
    if (!refreshToken) {
      return null;
    }
    const payload = await apiFetch("/auth/refresh", {
      method: "POST",
      body: JSON.stringify({ refresh_token: refreshToken }),
    });
    setStoredAccessToken(payload.access_token);
    setRefreshToken(payload.refresh_token);
    setAccessToken(payload.access_token);
    return payload;
  }, [refreshToken]);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const access = params.get("access_token");
    const refreshFromUrl = params.get("refresh_token");
    if (access) {
      applyTokens({
        access_token: access,
        refresh_token: refreshFromUrl,
        user: null,
      });
      window.history.replaceState({}, document.title, window.location.pathname);
    }
  }, [applyTokens]);

  const value = useMemo(
    () => ({
      accessToken,
      refreshToken,
      user,
      status,
      isAuthenticated: Boolean(accessToken),
      applyTokens,
      loginWithGoogle,
      logout,
      refresh,
      apiFetch,
    }),
    [
      accessToken,
      refreshToken,
      user,
      status,
      applyTokens,
      loginWithGoogle,
      logout,
      refresh,
    ],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used inside AuthProvider");
  }
  return context;
}

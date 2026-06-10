import { createContext, useCallback, useContext, useMemo, useState } from "react";
import { apiPost } from "../api/client";

type TokenResponse = {
  access_token: string;
  token_type: string;
};

type AuthContextValue = {
  token: string | null;
  username: string | null;
  isAuthenticated: boolean;
  login: (username: string, password: string) => Promise<void>;
  register: (username: string, password: string) => Promise<void>;
  logout: () => void;
};

const AuthContext = createContext<AuthContextValue | null>(null);
const TOKEN_KEY = "worldcup_sim_token";
const USER_KEY = "worldcup_sim_username";

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [token, setToken] = useState<string | null>(() => localStorage.getItem(TOKEN_KEY));
  const [username, setUsername] = useState<string | null>(() => localStorage.getItem(USER_KEY));

  const saveSession = useCallback((nextToken: string, nextUsername: string) => {
    localStorage.setItem(TOKEN_KEY, nextToken);
    localStorage.setItem(USER_KEY, nextUsername);
    setToken(nextToken);
    setUsername(nextUsername);
  }, []);

  const login = useCallback(
    async (nextUsername: string, password: string) => {
      const response = await apiPost<TokenResponse>("/auth/login", { username: nextUsername, password });
      saveSession(response.access_token, nextUsername);
    },
    [saveSession],
  );

  const register = useCallback(
    async (nextUsername: string, password: string) => {
      const response = await apiPost<TokenResponse>("/auth/register", { username: nextUsername, password });
      saveSession(response.access_token, nextUsername);
    },
    [saveSession],
  );

  const logout = useCallback(() => {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
    setToken(null);
    setUsername(null);
  }, []);

  const value = useMemo(
    () => ({
      token,
      username,
      isAuthenticated: Boolean(token),
      login,
      register,
      logout,
    }),
    [login, logout, register, token, username],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const value = useContext(AuthContext);
  if (!value) {
    throw new Error("useAuth must be used inside AuthProvider");
  }
  return value;
}

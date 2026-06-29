import React, { createContext, useContext, useEffect, useState } from "react";
import { api, setToken, clearToken } from "@/src/api";

type User = any;
type Ctx = {
  user: User | null;
  ready: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, username: string, display_name?: string) => Promise<void>;
  logout: () => Promise<void>;
  refresh: () => Promise<void>;
  setUser: (u: User) => void;
};

const AuthContext = createContext<Ctx>({} as Ctx);
export const useAuth = () => useContext(AuthContext);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [ready, setReady] = useState(false);

  const refresh = async () => {
    try {
      const u = await api.get("/auth/me");
      setUser(u);
    } catch {
      setUser(null);
      await clearToken();
    }
  };

  useEffect(() => {
    (async () => {
      await refresh();
      setReady(true);
    })();
  }, []);

  const login = async (email: string, password: string) => {
    const { token, user } = await api.post("/auth/login", { email, password });
    await setToken(token);
    setUser(user);
  };

  const register = async (email: string, password: string, username: string, display_name?: string) => {
    const { token, user } = await api.post("/auth/register", { email, password, username, display_name });
    await setToken(token);
    setUser(user);
  };

  const logout = async () => {
    await clearToken();
    setUser(null);
  };

  return (
    <AuthContext.Provider value={{ user, ready, login, register, logout, refresh, setUser }}>
      {children}
    </AuthContext.Provider>
  );
}

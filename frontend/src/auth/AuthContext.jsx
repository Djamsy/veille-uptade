import React, {createContext, useContext, useEffect, useState} from "react";
import { api } from "../api";
const Ctx = createContext(null);

export function AuthProvider({ children }) {
  const [token, setToken] = useState(() => localStorage.getItem("access_token"));
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(!!token);

  useEffect(() => {
    (async () => {
      if (!token) return setLoading(false);
      try { const me = await api.get("/auth/me"); setUser(me.user || me); }
      catch { localStorage.removeItem("access_token"); setToken(null); setUser(null); }
      finally { setLoading(false); }
    })();
  }, [token]);

  async function login(email, password) {
    const { access_token } = await api.post("/auth/login", { email, password });
    localStorage.setItem("access_token", access_token);
    setToken(access_token);
    const me = await api.get("/auth/me"); setUser(me.user || me);
  }
  function logout(){ localStorage.removeItem("access_token"); setToken(null); setUser(null); }

  return <Ctx.Provider value={{ user, token, loading, login, logout }}>{children}</Ctx.Provider>;
}
export const useAuth = () => useContext(Ctx);

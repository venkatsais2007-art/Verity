import { createContext, useContext, useState } from "react";
import { api } from "./api";

const AuthCtx = createContext(null);
export const useAuth = () => useContext(AuthCtx);

export function AuthProvider({ children }) {
  const [session, setSession] = useState(() => {
    try { return JSON.parse(localStorage.getItem("verity_session")); }
    catch { return null; }
  });

  async function login(company_id, employee_id, password) {
    const data = await api("/login", {
      method: "POST",
      body: { company_id, employee_id, password },
    });
    localStorage.setItem("verity_session", JSON.stringify(data));
    setSession(data);
  }

  function logout() {
    localStorage.removeItem("verity_session");
    setSession(null);
  }

  return (
    <AuthCtx.Provider value={{ user: session?.user, token: session?.token, login, logout }}>
      {children}
    </AuthCtx.Provider>
  );
}
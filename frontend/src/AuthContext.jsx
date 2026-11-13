import { useEffect, useState } from "react";
import { api } from "./api";
import { AuthCtx } from "./useAuth";

export function AuthProvider({ children }) {
  const [session, setSession] = useState(() => {
    try { return JSON.parse(localStorage.getItem("verity_session")); }
    catch {
      localStorage.removeItem("verity_session");
      return null;
    }
  });
  const [loading, setLoading] = useState(true);
  const [verified, setVerified] = useState(false);

  useEffect(() => {
    let active = true;
    if (!session?.token) {
      setVerified(false);
      setLoading(false);
      return () => { active = false; };
    }
    setLoading(true);
    setVerified(false);
    api("/me", { token: session.token })
      .then((user) => {
        if (active) {
          setSession((current) => current?.token === session.token ? { ...current, user } : current);
          setVerified(true);
        }
      })
      .catch((error) => {
        if (active && error.status === 401) {
          localStorage.removeItem("verity_session");
          setSession(null);
          setVerified(false);
        }
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => { active = false; };
  }, [session?.token]);

  useEffect(() => {
    function clearUnauthorizedSession() {
      localStorage.removeItem("verity_session");
      setSession(null);
      setVerified(false);
    }
    window.addEventListener("verity:unauthorized", clearUnauthorizedSession);
    return () => window.removeEventListener("verity:unauthorized", clearUnauthorizedSession);
  }, []);

  async function login(company_id, employee_id, password) {
    const data = await api("/login", {
      method: "POST",
      body: { company_id, employee_id, password },
    });
    localStorage.setItem("verity_session", JSON.stringify(data));
    setSession(data);
    setVerified(true);
  }

  function logout() {
    localStorage.removeItem("verity_session");
    setSession(null);
    setVerified(false);
  }

  return (
    <AuthCtx.Provider value={{ user: session?.user, token: session?.token, login, logout, loading, verified }}>
      {children}
    </AuthCtx.Provider>
  );
}
/**
 * context/UserContext.tsx — Global current-user state.
 *
 * Persists the logged-in user to localStorage so a page refresh does not
 * log the user out. This is a simplified auth model — a real app would
 * use JWT tokens or session cookies.
 *
 * Usage:
 *   const { user, setUser, clearUser } = useUser();
 */

import React, {
  createContext,
  useCallback,
  useContext,
  useState,
} from "react";
import type { User } from "../types";

interface UserContextValue {
  user: User | null;
  setUser: (user: User) => void;
  clearUser: () => void;
}

const UserContext = createContext<UserContextValue | null>(null);

const STORAGE_KEY = "ecommerce_user";

function loadUserFromStorage(): User | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? (JSON.parse(raw) as User) : null;
  } catch {
    return null;
  }
}

export function UserProvider({ children }: { children: React.ReactNode }) {
  const [user, setUserState] = useState<User | null>(loadUserFromStorage);

  const setUser = useCallback((newUser: User) => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(newUser));
    setUserState(newUser);
  }, []);

  const clearUser = useCallback(() => {
    localStorage.removeItem(STORAGE_KEY);
    setUserState(null);
  }, []);

  return (
    <UserContext.Provider value={{ user, setUser, clearUser }}>
      {children}
    </UserContext.Provider>
  );
}

export function useUser(): UserContextValue {
  const ctx = useContext(UserContext);
  if (!ctx) throw new Error("useUser must be used inside <UserProvider>");
  return ctx;
}

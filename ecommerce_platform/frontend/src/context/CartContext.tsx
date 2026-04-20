/**
 * context/CartContext.tsx — Global cart state and drawer visibility.
 *
 * The session ID is a UUID generated once per browser and stored in
 * localStorage. It identifies the cart in Valkey on the backend.
 *
 * Usage:
 *   const { sessionId, cartCount, isDrawerOpen, openDrawer, refreshCart } = useCart();
 */

import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
} from "react";
import { getCart } from "../api/client";
import type { Cart } from "../types";

interface CartContextValue {
  sessionId: string;
  cart: Cart | null;
  cartCount: number;
  isDrawerOpen: boolean;
  openDrawer: () => void;
  closeDrawer: () => void;
  refreshCart: () => Promise<void>;
}

const CartContext = createContext<CartContextValue | null>(null);

/** Generate a simple UUID v4 for the session ID */
function generateSessionId(): string {
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === "x" ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

function getOrCreateSessionId(): string {
  const stored = localStorage.getItem("ecommerce_session_id");
  if (stored) return stored;
  const newId = generateSessionId();
  localStorage.setItem("ecommerce_session_id", newId);
  return newId;
}

export function CartProvider({ children }: { children: React.ReactNode }) {
  const [sessionId] = useState<string>(getOrCreateSessionId);
  const [cart, setCart] = useState<Cart | null>(null);
  const [isDrawerOpen, setIsDrawerOpen] = useState(false);

  const refreshCart = useCallback(async () => {
    try {
      const freshCart = await getCart(sessionId);
      setCart(freshCart);
    } catch {
      setCart(null);
    }
  }, [sessionId]);

  // Load cart once on mount
  useEffect(() => {
    refreshCart();
  }, [refreshCart]);

  const cartCount = cart?.items.reduce((sum, item) => sum + item.quantity, 0) ?? 0;

  return (
    <CartContext.Provider
      value={{
        sessionId,
        cart,
        cartCount,
        isDrawerOpen,
        openDrawer: () => setIsDrawerOpen(true),
        closeDrawer: () => setIsDrawerOpen(false),
        refreshCart,
      }}
    >
      {children}
    </CartContext.Provider>
  );
}

export function useCart(): CartContextValue {
  const ctx = useContext(CartContext);
  if (!ctx) throw new Error("useCart must be used inside <CartProvider>");
  return ctx;
}

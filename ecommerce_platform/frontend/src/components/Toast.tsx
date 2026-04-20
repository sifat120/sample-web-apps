/**
 * components/Toast.tsx — Ephemeral notification system.
 *
 * Toasts appear in the bottom-right corner and auto-dismiss after 3 seconds.
 * They are used for "Added to cart", error messages, etc.
 *
 * Usage:
 *   const { addToast } = useToast();
 *   addToast("Added to cart!", "success");
 *   addToast("Something went wrong", "error");
 */

import React, {
  createContext,
  useCallback,
  useContext,
  useState,
} from "react";

type ToastType = "success" | "error" | "info";

interface ToastMessage {
  id: number;
  message: string;
  type: ToastType;
}

interface ToastContextValue {
  addToast: (message: string, type?: ToastType) => void;
}

const ToastContext = createContext<ToastContextValue | null>(null);

let nextId = 0;

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<ToastMessage[]>([]);

  const addToast = useCallback((message: string, type: ToastType = "info") => {
    const id = nextId++;
    setToasts((prev) => [...prev, { id, message, type }]);
    // Auto-remove after 3 seconds
    setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id));
    }, 3000);
  }, []);

  const typeStyles: Record<ToastType, string> = {
    success: "bg-emerald-600",
    error:   "bg-red-600",
    info:    "bg-indigo-600",
  };

  const typeIcons: Record<ToastType, string> = {
    success: "✓",
    error:   "✕",
    info:    "ℹ",
  };

  return (
    <ToastContext.Provider value={{ addToast }}>
      {children}

      {/* Toast container — fixed bottom-right, stacks upward */}
      <div className="fixed bottom-6 right-6 z-50 flex flex-col gap-2">
        {toasts.map((toast) => (
          <div
            key={toast.id}
            className={`${typeStyles[toast.type]} animate-fade-in flex items-center gap-3 rounded-xl px-4 py-3 text-white shadow-lg`}
          >
            <span className="text-lg font-bold">{typeIcons[toast.type]}</span>
            <span className="text-sm font-medium">{toast.message}</span>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast(): ToastContextValue {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error("useToast must be used inside <ToastProvider>");
  return ctx;
}

/**
 * components/CartDrawer.tsx — Slide-over cart panel.
 *
 * Appears from the right side when the cart icon is clicked.
 * Shows all cart items, allows removal, displays the total,
 * and has a "Checkout" button that navigates to /checkout.
 */

import { useNavigate } from "react-router-dom";
import { removeFromCart } from "../api/client";
import { useCart } from "../context/CartContext";
import { useToast } from "./Toast";

export default function CartDrawer() {
  const { cart, isDrawerOpen, closeDrawer, refreshCart, sessionId } = useCart();
  const { addToast } = useToast();
  const navigate = useNavigate();

  async function handleRemove(productId: number, name: string) {
    try {
      await removeFromCart(sessionId, productId);
      await refreshCart();
      addToast(`"${name}" removed`, "info");
    } catch (err) {
      addToast(err instanceof Error ? err.message : "Could not remove item", "error");
    }
  }

  function handleCheckout() {
    closeDrawer();
    navigate("/checkout");
  }

  return (
    <>
      {/* Semi-transparent backdrop — clicking it closes the drawer */}
      {isDrawerOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/30 backdrop-blur-sm"
          onClick={closeDrawer}
        />
      )}

      {/* Drawer panel */}
      <div
        className={`fixed right-0 top-0 z-50 flex h-full w-full max-w-md flex-col bg-white shadow-2xl transition-transform duration-300 ${
          isDrawerOpen ? "translate-x-0" : "translate-x-full"
        }`}
      >
        {/* Header */}
        <div className="flex items-center justify-between border-b border-slate-100 px-6 py-4">
          <h2 className="text-lg font-bold text-slate-900">
            Your Cart
            {cart && cart.items.length > 0 && (
              <span className="ml-2 rounded-full bg-indigo-100 px-2 py-0.5 text-sm font-semibold text-indigo-700">
                {cart.items.reduce((s, i) => s + i.quantity, 0)}
              </span>
            )}
          </h2>
          <button
            onClick={closeDrawer}
            className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-700 transition"
          >
            ✕
          </button>
        </div>

        {/* Item list */}
        <div className="flex-1 overflow-y-auto px-6 py-4">
          {!cart || cart.items.length === 0 ? (
            <div className="flex flex-col items-center gap-3 py-20 text-slate-400">
              <span className="text-5xl">🛒</span>
              <p className="text-sm">Your cart is empty</p>
            </div>
          ) : (
            <ul className="space-y-4">
              {cart.items.map((item) => (
                <li
                  key={item.product_id}
                  className="flex items-start gap-4 rounded-xl bg-slate-50 p-4"
                >
                  <div className="flex-1 min-w-0">
                    <p className="font-medium text-slate-900 truncate">{item.name}</p>
                    <p className="text-sm text-slate-500">
                      ${item.price.toFixed(2)} × {item.quantity}
                    </p>
                  </div>
                  <div className="flex flex-col items-end gap-2 shrink-0">
                    <span className="font-semibold text-indigo-600">
                      ${item.subtotal.toFixed(2)}
                    </span>
                    <button
                      onClick={() => handleRemove(item.product_id, item.name)}
                      className="text-xs text-red-400 hover:text-red-600 transition"
                    >
                      Remove
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>

        {/* Footer with total and checkout CTA */}
        {cart && cart.items.length > 0 && (
          <div className="border-t border-slate-100 px-6 py-5 space-y-4">
            <div className="flex justify-between text-base font-semibold text-slate-900">
              <span>Total</span>
              <span>${cart.total.toFixed(2)}</span>
            </div>
            <button
              onClick={handleCheckout}
              className="w-full rounded-xl bg-indigo-600 py-3 text-sm font-semibold text-white transition hover:bg-indigo-700"
            >
              Checkout →
            </button>
          </div>
        )}
      </div>
    </>
  );
}

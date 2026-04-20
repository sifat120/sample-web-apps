/**
 * pages/CheckoutPage.tsx — Sign-in (lightweight) + place order + confirmation.
 *
 * Three states are rendered conditionally:
 *   1. NOT signed in            → show email+name form (createUser)
 *   2. Signed in, has cart      → show order summary + "Place order" button
 *   3. After successful order   → show confirmation with order id & items
 *
 * Auth model:
 *   The backend currently exposes only `POST /users` (create) and
 *   `GET /users/{id}` — there is no email-based lookup endpoint, so we
 *   cannot "sign in" an existing user from email alone. Instead we keep
 *   the simplification used by `UserContext`: the user enters their email
 *   and name once, we POST /users, and we persist the returned User in
 *   localStorage. Subsequent visits skip the form. A real app would replace
 *   this with proper authentication (JWT / sessions / OAuth).
 */

import { FormEvent, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { checkout, createUser, getUser } from "../api/client";
import LoadingSpinner from "../components/LoadingSpinner";
import { useToast } from "../components/Toast";
import { useCart } from "../context/CartContext";
import { useUser } from "../context/UserContext";
import type { Order } from "../types";

export default function CheckoutPage() {
  const { user } = useUser();
  const { cart, refreshCart } = useCart();
  const [confirmedOrder, setConfirmedOrder] = useState<Order | null>(null);

  // ---- After-purchase confirmation view ----
  if (confirmedOrder) {
    return <OrderConfirmation order={confirmedOrder} />;
  }

  // ---- Cart still loading? ----
  if (cart === null) {
    return <LoadingSpinner message="Loading your cart…" />;
  }

  // ---- Empty cart guard ----
  if (cart.items.length === 0) {
    return (
      <div className="mx-auto max-w-md rounded-2xl bg-white p-8 text-center shadow-sm ring-1 ring-slate-100">
        <span className="text-5xl">🛒</span>
        <h1 className="mt-4 text-xl font-bold text-slate-900">
          Your cart is empty
        </h1>
        <p className="mt-2 text-sm text-slate-500">
          Add some products before checking out.
        </p>
        <Link
          to="/"
          className="mt-6 inline-block rounded-xl bg-indigo-600 px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-indigo-700"
        >
          Browse products
        </Link>
      </div>
    );
  }

  // ---- Not signed in: show inline form ----
  if (!user) {
    return (
      <div className="grid gap-6 md:grid-cols-[1fr_360px]">
        <SignInPanel />
        <CartSummary />
      </div>
    );
  }

  // ---- Signed in + has cart: show place-order panel ----
  return (
    <div className="grid gap-6 md:grid-cols-[1fr_360px]">
      <PlaceOrderPanel onPlaced={(order) => {
        setConfirmedOrder(order);
        // Clear the local cart state so the badge in the navbar zeroes out.
        refreshCart();
      }} />
      <CartSummary />
    </div>
  );
}

// ---- Sign-in / register form ---------------------------------------------

function SignInPanel() {
  const { setUser } = useUser();
  const { addToast } = useToast();

  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  // Fallback path for the "email already registered" case — we ask the user
  // for their numeric id since the backend has no email-based lookup.
  const [needsId, setNeedsId] = useState(false);
  const [userId, setUserId] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    try {
      if (needsId) {
        // User came back; look up by id and store the result.
        const existing = await getUser(Number(userId));
        setUser(existing);
        addToast(`Welcome back, ${existing.name}!`, "success");
      } else {
        const created = await createUser(email.trim(), name.trim());
        setUser(created);
        addToast(`Welcome, ${created.name}!`, "success");
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Sign-in failed";
      // The backend returns 409 with this exact detail message when the
      // email is taken. Switch to the "enter your id" fallback flow.
      if (msg === "Email already registered") {
        setNeedsId(true);
        addToast("Email already registered — please enter your user id", "info");
      } else {
        addToast(msg, "error");
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <section className="rounded-2xl bg-white p-6 shadow-sm ring-1 ring-slate-100">
      <h1 className="text-xl font-bold text-slate-900">
        {needsId ? "Welcome back" : "Sign in to checkout"}
      </h1>
      <p className="mt-1 text-sm text-slate-500">
        {needsId
          ? "Enter your existing user id to continue."
          : "First time? We’ll create an account for you."}
      </p>

      <form onSubmit={handleSubmit} className="mt-5 space-y-4">
        {needsId ? (
          <Field
            label="User id"
            type="number"
            value={userId}
            onChange={setUserId}
            required
            min={1}
          />
        ) : (
          <>
            <Field
              label="Email"
              type="email"
              value={email}
              onChange={setEmail}
              required
            />
            <Field
              label="Full name"
              type="text"
              value={name}
              onChange={setName}
              required
            />
          </>
        )}

        <button
          type="submit"
          disabled={submitting}
          className="w-full rounded-xl bg-indigo-600 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-indigo-700 disabled:opacity-50"
        >
          {submitting ? "Working…" : needsId ? "Continue" : "Create account"}
        </button>

        {needsId && (
          <button
            type="button"
            onClick={() => setNeedsId(false)}
            className="w-full text-center text-xs text-slate-500 hover:text-indigo-600"
          >
            ← Use a different email
          </button>
        )}
      </form>
    </section>
  );
}

// ---- Place-order panel (after sign-in) -----------------------------------

function PlaceOrderPanel({ onPlaced }: { onPlaced: (order: Order) => void }) {
  const { user, clearUser } = useUser();
  const { sessionId } = useCart();
  const { addToast } = useToast();
  const [submitting, setSubmitting] = useState(false);

  async function handlePlaceOrder() {
    if (!user) return;
    setSubmitting(true);
    try {
      const order = await checkout(sessionId, user.id);
      addToast(`Order #${order.id} placed!`, "success");
      onPlaced(order);
    } catch (err) {
      addToast(
        err instanceof Error ? err.message : "Checkout failed",
        "error"
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <section className="rounded-2xl bg-white p-6 shadow-sm ring-1 ring-slate-100">
      <h1 className="text-xl font-bold text-slate-900">Review & place order</h1>

      <div className="mt-4 rounded-xl bg-slate-50 p-4 text-sm">
        <p className="font-medium text-slate-700">Signed in as</p>
        <p className="text-slate-900">{user!.name}</p>
        <p className="text-slate-500">{user!.email}</p>
        <button
          onClick={clearUser}
          className="mt-2 text-xs text-slate-500 underline hover:text-indigo-600"
        >
          Use a different account
        </button>
      </div>

      <button
        onClick={handlePlaceOrder}
        disabled={submitting}
        className="mt-6 w-full rounded-xl bg-indigo-600 px-4 py-3 text-sm font-semibold text-white transition hover:bg-indigo-700 disabled:opacity-50"
      >
        {submitting ? "Placing order…" : "Place order"}
      </button>

      <p className="mt-3 text-center text-xs text-slate-400">
        This is a demo — no real payment is collected.
      </p>
    </section>
  );
}

// ---- Cart summary side panel ---------------------------------------------

function CartSummary() {
  const { cart } = useCart();
  if (!cart) return null;

  return (
    <aside className="h-fit rounded-2xl bg-white p-6 shadow-sm ring-1 ring-slate-100">
      <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">
        Order summary
      </h2>

      <ul className="mt-4 divide-y divide-slate-100">
        {cart.items.map((item) => (
          <li
            key={item.product_id}
            className="flex items-start justify-between gap-2 py-3 text-sm"
          >
            <div className="min-w-0">
              <p className="truncate font-medium text-slate-900">{item.name}</p>
              <p className="text-xs text-slate-500">
                ${item.price.toFixed(2)} × {item.quantity}
              </p>
            </div>
            <span className="font-semibold text-slate-700">
              ${item.subtotal.toFixed(2)}
            </span>
          </li>
        ))}
      </ul>

      <div className="mt-4 flex items-center justify-between border-t border-slate-100 pt-4 text-base font-semibold text-slate-900">
        <span>Total</span>
        <span>${cart.total.toFixed(2)}</span>
      </div>
    </aside>
  );
}

// ---- Order confirmation --------------------------------------------------

function OrderConfirmation({ order }: { order: Order }) {
  return (
    <div className="mx-auto max-w-xl rounded-2xl bg-white p-8 text-center shadow-sm ring-1 ring-slate-100">
      <span className="inline-flex h-16 w-16 items-center justify-center rounded-full bg-emerald-100 text-3xl text-emerald-600">
        ✓
      </span>

      <h1 className="mt-4 text-2xl font-bold text-slate-900">
        Thank you for your order!
      </h1>
      <p className="mt-1 text-sm text-slate-500">
        Order <span className="font-mono">#{order.id}</span> · status: {order.status}
      </p>

      <ul className="mt-6 divide-y divide-slate-100 text-left text-sm">
        {order.items.map((item) => (
          <li
            key={item.product_id}
            className="flex items-center justify-between py-3"
          >
            <span>
              <span className="font-medium text-slate-900">
                {item.product_name}
              </span>{" "}
              <span className="text-slate-500">× {item.quantity}</span>
            </span>
            <span className="text-slate-700">
              ${(item.unit_price * item.quantity).toFixed(2)}
            </span>
          </li>
        ))}
      </ul>

      <div className="mt-4 flex items-center justify-between border-t border-slate-100 pt-4 font-semibold text-slate-900">
        <span>Total paid</span>
        <span>${order.total.toFixed(2)}</span>
      </div>

      <Link
        to="/"
        className="mt-8 inline-block rounded-xl bg-indigo-600 px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-indigo-700"
      >
        Continue shopping
      </Link>
    </div>
  );
}

// ---- Generic labelled input ----------------------------------------------

function Field({
  label,
  ...inputProps
}: {
  label: string;
  type: string;
  value: string;
  onChange: (v: string) => void;
  required?: boolean;
  min?: number;
}) {
  const { value, onChange, ...rest } = inputProps;
  return (
    <label className="block">
      <span className="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-500">
        {label}
      </span>
      <input
        {...rest}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none transition focus:border-indigo-300 focus:ring-2 focus:ring-indigo-100"
      />
    </label>
  );
}

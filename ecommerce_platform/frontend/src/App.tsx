/**
 * App.tsx — Top-level layout, providers, and route table.
 *
 * Provider order matters — inner providers can read from outer ones:
 *   ToastProvider   (no deps)               → outermost
 *     UserProvider  (no deps)
 *       CartProvider (uses Toast indirectly via children)
 *
 * Layout:
 *   ┌──────────────────────────┐
 *   │ <Navbar/>  (sticky top)  │
 *   ├──────────────────────────┤
 *   │ <main> page content      │
 *   ├──────────────────────────┤
 *   │ <footer>                 │
 *   └──────────────────────────┘
 *   <CartDrawer/> overlays the whole app when opened.
 *
 * Routes:
 *   /               → HomePage      (search results / catalog)
 *   /products/:id   → ProductPage   (product detail)
 *   /checkout       → CheckoutPage  (sign-in + place order)
 *   /admin          → AdminPage     (create + edit products, upload images)
 *   /health         → HealthPage    (backend service status)
 *   *               → NotFound      (catch-all)
 */

import { Link, Route, Routes } from "react-router-dom";

import CartDrawer from "./components/CartDrawer";
import Navbar from "./components/Navbar";
import { ToastProvider } from "./components/Toast";
import { CartProvider } from "./context/CartContext";
import { UserProvider } from "./context/UserContext";

import AdminPage from "./pages/AdminPage";
import CheckoutPage from "./pages/CheckoutPage";
import HealthPage from "./pages/HealthPage";
import HomePage from "./pages/HomePage";
import ProductPage from "./pages/ProductPage";

export default function App() {
  return (
    <ToastProvider>
      <UserProvider>
        <CartProvider>
          {/* Page chrome: sticky navbar at the top, footer at the bottom */}
          <div className="flex min-h-screen flex-col bg-slate-50 text-slate-900">
            <Navbar />

            {/* Main content area — every page renders inside this <main> */}
            <main className="mx-auto w-full max-w-7xl flex-1 px-4 py-8 sm:px-6">
              <Routes>
                <Route path="/" element={<HomePage />} />
                <Route path="/products/:id" element={<ProductPage />} />
                <Route path="/checkout" element={<CheckoutPage />} />
                <Route path="/admin" element={<AdminPage />} />
                <Route path="/health" element={<HealthPage />} />
                <Route path="*" element={<NotFound />} />
              </Routes>
            </main>

            <footer className="border-t border-slate-200 bg-white py-6 text-center text-xs text-slate-500">
              ShopLocal · Sample e-commerce app · FastAPI + React
            </footer>

            {/* The cart drawer is rendered once at the app root — it slides
                in from the right whenever CartContext.isDrawerOpen is true. */}
            <CartDrawer />
          </div>
        </CartProvider>
      </UserProvider>
    </ToastProvider>
  );
}

/** Catch-all route shown when no other route matches. */
function NotFound() {
  return (
    <div className="flex flex-col items-center gap-4 py-24 text-center">
      <span className="text-6xl">🤷</span>
      <h1 className="text-2xl font-bold">Page not found</h1>
      <p className="text-sm text-slate-500">The page you’re looking for doesn’t exist.</p>
      <Link
        to="/"
        className="rounded-xl bg-indigo-600 px-4 py-2 text-sm font-semibold text-white transition hover:bg-indigo-700"
      >
        Back to products
      </Link>
    </div>
  );
}

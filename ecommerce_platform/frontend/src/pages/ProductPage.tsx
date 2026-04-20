/**
 * pages/ProductPage.tsx — Single product detail view.
 *
 * Loaded for the route `/products/:id`.
 *
 * Demonstrates how the cache-aside pattern is invisible to the frontend:
 * the second time you land on this page within the 60s TTL, the API serves
 * the response from Valkey instead of PostgreSQL — but the React code is
 * identical either way.
 *
 * Layout:
 *   ┌──────────────┬───────────────────────┐
 *   │ Image        │ Name + price          │
 *   │              │ Stock badge           │
 *   │              │ Description           │
 *   │              │ Quantity selector     │
 *   │              │ [ Add to Cart ]       │
 *   └──────────────┴───────────────────────┘
 */

import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { addToCart, getProduct, getProductImageUrl } from "../api/client";
import LoadingSpinner from "../components/LoadingSpinner";
import { useToast } from "../components/Toast";
import { useCart } from "../context/CartContext";
import type { Product } from "../types";

export default function ProductPage() {
  // useParams gives us the URL segment matched by `:id`.
  // The value is always a string — convert to number for the API call.
  const { id } = useParams<{ id: string }>();
  const productId = id ? Number(id) : NaN;

  const navigate = useNavigate();
  const { sessionId, refreshCart, openDrawer } = useCart();
  const { addToast } = useToast();

  const [product, setProduct] = useState<Product | null>(null);
  const [imageUrl, setImageUrl] = useState<string | null>(null);
  const [quantity, setQuantity] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);

  // Fetch product details + image URL in parallel whenever the URL id changes.
  useEffect(() => {
    if (Number.isNaN(productId)) {
      setError("Invalid product id");
      setLoading(false);
      return;
    }

    let cancelled = false;
    setLoading(true);
    setError(null);

    Promise.all([getProduct(productId), getProductImageUrl(productId)])
      .then(([prod, url]) => {
        if (cancelled) return;
        setProduct(prod);
        setImageUrl(url);
        // Reset the quantity input when navigating between products.
        setQuantity(1);
      })
      .catch((err: Error) => {
        if (!cancelled) setError(err.message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [productId]);

  async function handleAddToCart() {
    if (!product) return;
    setAdding(true);
    try {
      await addToCart(sessionId, product.id, quantity);
      await refreshCart();
      openDrawer();
      addToast(`Added ${quantity} × "${product.name}" to cart`, "success");
    } catch (err) {
      addToast(
        err instanceof Error ? err.message : "Could not add to cart",
        "error"
      );
    } finally {
      setAdding(false);
    }
  }

  if (loading) return <LoadingSpinner message="Loading product…" />;

  if (error || !product) {
    return (
      <div className="rounded-2xl border border-red-200 bg-red-50 p-6 text-center">
        <p className="mb-3 text-sm text-red-700">
          {error ?? "Product not found"}
        </p>
        <button
          onClick={() => navigate(-1)}
          className="rounded-xl bg-white px-4 py-2 text-sm font-medium text-slate-700 ring-1 ring-slate-200 hover:bg-slate-50"
        >
          ← Go back
        </button>
      </div>
    );
  }

  // Cap the quantity input at the current stock so the user can't request
  // more than is available. The backend is still the authoritative check —
  // this is a UX improvement, not a security boundary.
  const maxQty = Math.max(product.stock, 1);
  const outOfStock = product.stock === 0;

  return (
    <div>
      <Link
        to="/"
        className="mb-5 inline-flex items-center gap-1 text-sm text-slate-500 hover:text-indigo-600"
      >
        ← Back to products
      </Link>

      <div className="grid gap-8 rounded-2xl bg-white p-6 shadow-sm ring-1 ring-slate-100 md:grid-cols-2 md:p-8">
        {/* ---- Image ---- */}
        <div className="flex aspect-square items-center justify-center overflow-hidden rounded-xl bg-slate-100">
          {imageUrl ? (
            <img
              src={imageUrl}
              alt={product.name}
              className="h-full w-full object-cover"
            />
          ) : (
            <span className="text-7xl text-slate-300">🛍</span>
          )}
        </div>

        {/* ---- Details ---- */}
        <div className="flex flex-col gap-5">
          {product.category && (
            <span className="self-start rounded-full bg-indigo-50 px-3 py-1 text-xs font-medium capitalize text-indigo-700">
              {product.category}
            </span>
          )}

          <div>
            <h1 className="text-3xl font-bold text-slate-900">{product.name}</h1>
            <p className="mt-2 text-3xl font-semibold text-indigo-600">
              ${product.price.toFixed(2)}
            </p>
          </div>

          <StockBadge stock={product.stock} />

          {product.description && (
            <p className="leading-relaxed text-slate-600">
              {product.description}
            </p>
          )}

          {/* Quantity + Add to Cart */}
          {!outOfStock && (
            <div className="mt-2 flex items-end gap-3">
              <label className="flex flex-col text-xs font-medium uppercase tracking-wide text-slate-500">
                Quantity
                <input
                  type="number"
                  min={1}
                  max={maxQty}
                  value={quantity}
                  onChange={(e) =>
                    setQuantity(
                      // Clamp the input to [1, stock]
                      Math.max(
                        1,
                        Math.min(maxQty, Number(e.target.value) || 1)
                      )
                    )
                  }
                  className="mt-1 w-24 rounded-lg border border-slate-200 px-3 py-2 text-base text-slate-900 outline-none focus:border-indigo-300 focus:ring-2 focus:ring-indigo-100"
                />
              </label>

              <button
                onClick={handleAddToCart}
                disabled={adding}
                className="flex-1 rounded-xl bg-indigo-600 px-4 py-3 text-sm font-semibold text-white transition hover:bg-indigo-700 disabled:opacity-50"
              >
                {adding ? "Adding…" : "Add to Cart"}
              </button>
            </div>
          )}

          {outOfStock && (
            <button
              disabled
              className="rounded-xl bg-slate-200 px-4 py-3 text-sm font-semibold text-slate-500"
            >
              Out of stock
            </button>
          )}

          <p className="text-xs text-slate-400">
            Product ID: {product.id} · Added{" "}
            {new Date(product.created_at).toLocaleDateString()}
          </p>
        </div>
      </div>
    </div>
  );
}

function StockBadge({ stock }: { stock: number }) {
  if (stock === 0) {
    return (
      <span className="self-start rounded-full bg-red-100 px-3 py-1 text-sm font-medium text-red-700">
        Out of stock
      </span>
    );
  }
  if (stock <= 5) {
    return (
      <span className="self-start rounded-full bg-amber-100 px-3 py-1 text-sm font-medium text-amber-700">
        Only {stock} left in stock
      </span>
    );
  }
  return (
    <span className="self-start rounded-full bg-emerald-100 px-3 py-1 text-sm font-medium text-emerald-700">
      In stock ({stock} available)
    </span>
  );
}

/**
 * pages/HomePage.tsx — Product catalog & search results.
 *
 * The page is *URL-driven*: filters are read from the query string so a user
 * can copy/paste, refresh, or bookmark a search and get the same results.
 *
 * Supported query parameters (all optional):
 *   ?q=hiking         — full-text search term
 *   ?category=footwear
 *   ?min_price=20
 *   ?max_price=200
 *
 * Layout:
 *   ┌──────────────┬──────────────────────────┐
 *   │ Filters      │ Product grid             │
 *   │ (sidebar)    │ (responsive 1-4 cols)    │
 *   └──────────────┴──────────────────────────┘
 */

import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { searchProducts } from "../api/client";
import LoadingSpinner from "../components/LoadingSpinner";
import ProductCard from "../components/ProductCard";
import type { ProductSearchResult } from "../types";

// Hard-coded list of categories. The backend does not currently expose a
// "list all categories" endpoint, so we ship a sensible default set here.
// Users can still filter by any category typed in via the Admin page.
const CATEGORIES = ["footwear", "clothing", "electronics", "home", "outdoors"];

export default function HomePage() {
  // useSearchParams is react-router's hook for reading & writing the query
  // string. Updating it triggers a re-render with the new params, similar
  // to useState — but the URL stays in sync.
  const [searchParams, setSearchParams] = useSearchParams();

  const q = searchParams.get("q") ?? "";
  const category = searchParams.get("category") ?? "";
  const minPrice = searchParams.get("min_price") ?? "";
  const maxPrice = searchParams.get("max_price") ?? "";

  const [results, setResults] = useState<ProductSearchResult[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Re-run the search whenever any URL filter changes.
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    searchProducts({
      q: q || undefined,
      category: category || undefined,
      min_price: minPrice ? Number(minPrice) : undefined,
      max_price: maxPrice ? Number(maxPrice) : undefined,
    })
      .then((data) => {
        // Guard against state updates after unmount or after the user has
        // started a newer search (avoids race conditions where a slow request
        // overwrites a fresh one).
        if (!cancelled) setResults(data);
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
  }, [q, category, minPrice, maxPrice]);

  /**
   * Helper to update a single query-string parameter. Clearing the value
   * (passing "") removes the parameter entirely — keeps the URL clean.
   */
  function updateParam(name: string, value: string) {
    const next = new URLSearchParams(searchParams);
    if (value) next.set(name, value);
    else next.delete(name);
    setSearchParams(next);
  }

  return (
    <div className="grid gap-6 lg:grid-cols-[220px_1fr]">
      {/* ---- Filter sidebar ---- */}
      <aside className="space-y-6 rounded-2xl bg-white p-5 shadow-sm ring-1 ring-slate-100 lg:sticky lg:top-20 lg:self-start">
        <div>
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-500">
            Category
          </h2>
          <ul className="space-y-1">
            <CategoryButton
              label="All"
              active={!category}
              onClick={() => updateParam("category", "")}
            />
            {CATEGORIES.map((c) => (
              <CategoryButton
                key={c}
                label={c}
                active={category === c}
                onClick={() => updateParam("category", c)}
              />
            ))}
          </ul>
        </div>

        <div>
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-500">
            Price
          </h2>
          <div className="flex items-center gap-2">
            <PriceInput
              placeholder="Min"
              value={minPrice}
              onChange={(v) => updateParam("min_price", v)}
            />
            <span className="text-slate-400">–</span>
            <PriceInput
              placeholder="Max"
              value={maxPrice}
              onChange={(v) => updateParam("max_price", v)}
            />
          </div>
        </div>

        {(q || category || minPrice || maxPrice) && (
          <button
            onClick={() => setSearchParams(new URLSearchParams())}
            className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm text-slate-600 transition hover:bg-slate-50"
          >
            Clear all filters
          </button>
        )}
      </aside>

      {/* ---- Results ---- */}
      <section>
        <header className="mb-5 flex items-baseline justify-between">
          <h1 className="text-2xl font-bold text-slate-900">
            {q ? `Results for “${q}”` : "All products"}
          </h1>
          {!loading && (
            <span className="text-sm text-slate-500">
              {results.length} item{results.length === 1 ? "" : "s"}
            </span>
          )}
        </header>

        {loading ? (
          <LoadingSpinner message="Searching products…" />
        ) : error ? (
          <ErrorMessage message={error} />
        ) : results.length === 0 ? (
          <EmptyState />
        ) : (
          <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            {results.map((product) => (
              <ProductCard key={product.id} product={product} />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

// ---- Sub-components ------------------------------------------------------

function CategoryButton({
  label,
  active,
  onClick,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <li>
      <button
        onClick={onClick}
        className={`w-full rounded-lg px-3 py-2 text-left text-sm capitalize transition ${
          active
            ? "bg-indigo-50 font-semibold text-indigo-700"
            : "text-slate-600 hover:bg-slate-50"
        }`}
      >
        {label}
      </button>
    </li>
  );
}

function PriceInput({
  placeholder,
  value,
  onChange,
}: {
  placeholder: string;
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <input
      type="number"
      inputMode="decimal"
      min={0}
      placeholder={placeholder}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="w-full rounded-lg border border-slate-200 bg-white px-2 py-1.5 text-sm outline-none transition focus:border-indigo-300 focus:ring-2 focus:ring-indigo-100"
    />
  );
}

function EmptyState() {
  return (
    <div className="flex flex-col items-center gap-3 rounded-2xl bg-white py-20 text-center text-slate-400 shadow-sm ring-1 ring-slate-100">
      <span className="text-5xl">🔎</span>
      <p className="text-sm">No products match your filters.</p>
      <p className="text-xs text-slate-400">
        Try removing a filter or searching for something else.
      </p>
    </div>
  );
}

function ErrorMessage({ message }: { message: string }) {
  return (
    <div className="rounded-2xl border border-red-200 bg-red-50 p-6 text-sm text-red-700">
      <strong className="block mb-1">Couldn’t load products</strong>
      {message}
    </div>
  );
}

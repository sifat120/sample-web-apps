/**
 * components/Navbar.tsx — Top navigation bar.
 *
 * Contains:
 *   - Logo / home link
 *   - Nav links (Products, Admin, Health)
 *   - Search bar with autocomplete
 *   - Cart icon with item-count badge
 *   - User indicator (shows name or "Sign in" prompt)
 */

import React, { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { autocompleteProducts } from "../api/client";
import { useCart } from "../context/CartContext";
import { useUser } from "../context/UserContext";

export default function Navbar() {
  const navigate = useNavigate();
  const { cartCount, openDrawer } = useCart();
  const { user, clearUser } = useUser();

  const [query, setQuery] = useState("");
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const searchRef = useRef<HTMLDivElement>(null);

  // Fetch autocomplete suggestions as the user types, debounced 200ms
  useEffect(() => {
    if (query.length < 2) {
      setSuggestions([]);
      return;
    }

    const timer = setTimeout(async () => {
      try {
        const results = await autocompleteProducts(query);
        setSuggestions(results);
        setShowSuggestions(results.length > 0);
      } catch {
        setSuggestions([]);
      }
    }, 200);

    return () => clearTimeout(timer);
  }, [query]);

  // Close suggestion dropdown when clicking outside
  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (searchRef.current && !searchRef.current.contains(e.target as Node)) {
        setShowSuggestions(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  function handleSearch(e: React.FormEvent) {
    e.preventDefault();
    setShowSuggestions(false);
    if (query.trim()) navigate(`/?q=${encodeURIComponent(query.trim())}`);
  }

  function handleSuggestionClick(suggestion: string) {
    setQuery(suggestion);
    setShowSuggestions(false);
    navigate(`/?q=${encodeURIComponent(suggestion)}`);
  }

  return (
    <nav className="sticky top-0 z-30 border-b border-slate-200 bg-white/95 backdrop-blur-sm">
      <div className="mx-auto flex max-w-7xl items-center gap-4 px-4 py-3 sm:px-6">

        {/* Logo */}
        <Link
          to="/"
          className="flex items-center gap-2 text-xl font-bold text-indigo-600 shrink-0"
        >
          <span className="text-2xl">🛒</span>
          <span className="hidden sm:block">ShopLocal</span>
        </Link>

        {/* Search bar with autocomplete */}
        <div ref={searchRef} className="relative flex-1 max-w-lg">
          <form onSubmit={handleSearch}>
            <div className="flex items-center rounded-xl border border-slate-200 bg-slate-50 focus-within:border-indigo-300 focus-within:ring-2 focus-within:ring-indigo-100 transition">
              <span className="pl-3 text-slate-400">🔍</span>
              <input
                type="text"
                placeholder="Search products…"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onFocus={() => suggestions.length > 0 && setShowSuggestions(true)}
                className="flex-1 bg-transparent px-3 py-2 text-sm text-slate-900 placeholder-slate-400 outline-none"
              />
              {query && (
                <button
                  type="button"
                  onClick={() => { setQuery(""); setSuggestions([]); }}
                  className="pr-3 text-slate-400 hover:text-slate-600"
                >
                  ✕
                </button>
              )}
            </div>
          </form>

          {/* Autocomplete dropdown */}
          {showSuggestions && (
            <ul className="absolute mt-1 w-full rounded-xl border border-slate-200 bg-white py-1 shadow-lg z-50">
              {suggestions.map((s) => (
                <li key={s}>
                  <button
                    onClick={() => handleSuggestionClick(s)}
                    className="w-full px-4 py-2 text-left text-sm text-slate-700 hover:bg-indigo-50 hover:text-indigo-700 transition"
                  >
                    🔍 {s}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>

        {/* Nav links */}
        <div className="hidden md:flex items-center gap-1">
          <NavLink to="/">Products</NavLink>
          <NavLink to="/admin">Admin</NavLink>
          <NavLink to="/health">Health</NavLink>
        </div>

        {/* User indicator */}
        {user ? (
          <div className="group relative hidden sm:block shrink-0">
            <button className="flex items-center gap-2 rounded-xl px-3 py-2 text-sm text-slate-700 hover:bg-slate-100 transition">
              <span className="flex h-7 w-7 items-center justify-center rounded-full bg-indigo-100 text-xs font-bold text-indigo-700">
                {user.name[0].toUpperCase()}
              </span>
              <span className="hidden lg:block max-w-[100px] truncate">{user.name}</span>
            </button>
            {/* Hover dropdown */}
            <div className="invisible absolute right-0 mt-1 w-44 rounded-xl border border-slate-100 bg-white py-1 shadow-lg group-hover:visible">
              <div className="border-b border-slate-100 px-4 py-2">
                <p className="text-xs text-slate-500">Signed in as</p>
                <p className="truncate text-sm font-medium text-slate-800">{user.email}</p>
              </div>
              <button
                onClick={clearUser}
                className="w-full px-4 py-2 text-left text-sm text-red-500 hover:bg-red-50 transition"
              >
                Sign out
              </button>
            </div>
          </div>
        ) : (
          <Link
            to="/checkout"
            className="hidden sm:block shrink-0 rounded-xl border border-slate-200 px-3 py-2 text-sm text-slate-600 hover:bg-slate-50 transition"
          >
            Sign in
          </Link>
        )}

        {/* Cart icon with badge */}
        <button
          onClick={openDrawer}
          className="relative shrink-0 rounded-xl p-2.5 text-slate-600 transition hover:bg-indigo-50 hover:text-indigo-600"
        >
          <span className="text-xl">🛒</span>
          {cartCount > 0 && (
            <span className="absolute -right-0.5 -top-0.5 flex h-5 w-5 items-center justify-center rounded-full bg-indigo-600 text-[10px] font-bold text-white">
              {cartCount > 99 ? "99+" : cartCount}
            </span>
          )}
        </button>
      </div>
    </nav>
  );
}

function NavLink({ to, children }: { to: string; children: React.ReactNode }) {
  return (
    <Link
      to={to}
      className="rounded-lg px-3 py-2 text-sm font-medium text-slate-600 transition hover:bg-slate-100 hover:text-slate-900"
    >
      {children}
    </Link>
  );
}

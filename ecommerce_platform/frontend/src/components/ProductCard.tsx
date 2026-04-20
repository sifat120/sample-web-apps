/**
 * components/ProductCard.tsx — Product summary card used in the grid.
 *
 * Shows the product image (or a placeholder), name, category, price,
 * stock badge, and an "Add to Cart" button.
 */

import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { addToCart, getProductImageUrl } from "../api/client";
import { useCart } from "../context/CartContext";
import { useToast } from "./Toast";
import type { ProductSearchResult } from "../types";

interface Props {
  product: ProductSearchResult;
}

export default function ProductCard({ product }: Props) {
  const navigate = useNavigate();
  const { sessionId, refreshCart, openDrawer } = useCart();
  const { addToast } = useToast();
  const [imageUrl, setImageUrl] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);

  // Fetch the pre-signed image URL on mount
  useEffect(() => {
    getProductImageUrl(product.id).then(setImageUrl);
  }, [product.id]);

  async function handleAddToCart(e: React.MouseEvent) {
    // Prevent the click from bubbling up to the card's navigate handler
    e.stopPropagation();
    setAdding(true);
    try {
      await addToCart(sessionId, product.id, 1);
      await refreshCart();
      openDrawer();
      addToast(`"${product.name}" added to cart`, "success");
    } catch (err) {
      addToast(err instanceof Error ? err.message : "Could not add to cart", "error");
    } finally {
      setAdding(false);
    }
  }

  // Search results don't include stock (the backend's ProductSearchResult
  // schema only returns id/name/category/price/score for index efficiency).
  // The full stock count is shown on the product detail page after navigation.
  const categoryBadge = product.category ? (
    <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs font-medium capitalize text-slate-600">
      {product.category}
    </span>
  ) : null;

  return (
    <div
      onClick={() => navigate(`/products/${product.id}`)}
      className="group flex cursor-pointer flex-col rounded-2xl bg-white shadow-sm ring-1 ring-slate-100 transition hover:shadow-md hover:ring-indigo-200"
    >
      {/* Product image */}
      <div className="relative h-48 overflow-hidden rounded-t-2xl bg-slate-100">
        {imageUrl ? (
          <img
            src={imageUrl}
            alt={product.name}
            className="h-full w-full object-cover transition group-hover:scale-105"
          />
        ) : (
          <div className="flex h-full items-center justify-center text-4xl text-slate-300">
            🛍
          </div>
        )}
        {product.category && (
          <span className="absolute left-3 top-3 rounded-full bg-white/80 px-2 py-0.5 text-xs font-medium capitalize text-slate-600 backdrop-blur-sm">
            {product.category}
          </span>
        )}
      </div>

      {/* Card body */}
      <div className="flex flex-1 flex-col gap-2 p-4">
        <h3 className="font-semibold text-slate-900 leading-tight line-clamp-2">
          {product.name}
        </h3>

        <div className="flex items-center gap-2 flex-wrap">{categoryBadge}</div>

        <div className="mt-auto flex items-center justify-between pt-2">
          <span className="text-lg font-bold text-indigo-600">
            ${product.price.toFixed(2)}
          </span>
          <button
            onClick={handleAddToCart}
            disabled={adding}
            className="rounded-xl bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white transition hover:bg-indigo-700 disabled:opacity-50"
          >
            {adding ? "Adding…" : "Add to Cart"}
          </button>
        </div>
      </div>
    </div>
  );
}

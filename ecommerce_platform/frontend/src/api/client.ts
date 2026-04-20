/**
 * api/client.ts — Typed API functions for every backend endpoint.
 *
 * All requests go through /api which Vite proxies to http://localhost:8000.
 * Every function is async and returns a typed result or throws an Error
 * with the server's error message so the UI can display it.
 *
 * Usage:
 *   import { searchProducts, addToCart } from "../api/client";
 *   const results = await searchProducts({ q: "boots", category: "footwear" });
 */

import type {
  Cart,
  HealthStatus,
  Order,
  Product,
  ProductCreatePayload,
  ProductSearchResult,
  ProductUpdatePayload,
  User,
} from "../types";

const BASE = "/api";

// ---- Helper --------------------------------------------------------------

/**
 * Wraps fetch() with JSON parsing and unified error handling.
 * Throws an Error with the server's detail message on non-2xx responses.
 */
async function request<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const response = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...options.headers },
    ...options,
  });

  if (!response.ok) {
    // FastAPI returns { detail: "..." } for errors
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail ?? `HTTP ${response.status}`);
  }

  return response.json() as Promise<T>;
}

// ---- Health --------------------------------------------------------------

export function getHealth(): Promise<HealthStatus> {
  return request<HealthStatus>("/health");
}

// ---- Users ---------------------------------------------------------------

export function createUser(email: string, name: string): Promise<User> {
  return request<User>("/users", {
    method: "POST",
    body: JSON.stringify({ email, name }),
  });
}

export function getUser(userId: number): Promise<User> {
  return request<User>(`/users/${userId}`);
}

// ---- Products ------------------------------------------------------------

export function createProduct(data: ProductCreatePayload): Promise<Product> {
  return request<Product>("/products", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export function getProduct(productId: number): Promise<Product> {
  return request<Product>(`/products/${productId}`);
}

export function updateProduct(
  productId: number,
  data: ProductUpdatePayload
): Promise<Product> {
  return request<Product>(`/products/${productId}`, {
    method: "PUT",
    body: JSON.stringify(data),
  });
}

/** Full-text search with optional category and price range filters. */
export function searchProducts(params: {
  q?: string;
  category?: string;
  min_price?: number;
  max_price?: number;
}): Promise<ProductSearchResult[]> {
  const query = new URLSearchParams();
  if (params.q) query.set("q", params.q);
  if (params.category) query.set("category", params.category);
  if (params.min_price != null) query.set("min_price", String(params.min_price));
  if (params.max_price != null) query.set("max_price", String(params.max_price));
  return request<ProductSearchResult[]>(`/products/search?${query}`);
}

/** Returns name suggestions for autocomplete as the user types. */
export function autocompleteProducts(q: string): Promise<string[]> {
  return request<string[]>(
    `/products/search/autocomplete?q=${encodeURIComponent(q)}`
  );
}

/** Get the pre-signed image download URL for a product. */
export async function getProductImageUrl(
  productId: number
): Promise<string | null> {
  try {
    const data = await request<{ url: string }>(`/products/${productId}/image-url`);
    return data.url;
  } catch {
    return null; // Product has no image yet
  }
}

/** Upload a product image. Returns the storage key. */
export async function uploadProductImage(
  productId: number,
  file: File
): Promise<string> {
  const formData = new FormData();
  formData.append("file", file);

  // Cannot use the helper here because we must NOT set Content-Type manually
  // (the browser sets it with the correct multipart boundary automatically)
  const response = await fetch(`${BASE}/products/${productId}/image`, {
    method: "POST",
    body: formData,
  });

  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail ?? `HTTP ${response.status}`);
  }

  const data = await response.json();
  return data.key as string;
}

// ---- Cart ----------------------------------------------------------------

export function getCart(sessionId: string): Promise<Cart> {
  return request<Cart>(`/cart/${encodeURIComponent(sessionId)}`);
}

export function addToCart(
  sessionId: string,
  productId: number,
  quantity: number
): Promise<{ session_id: string; product_id: number; quantity: number }> {
  return request(`/cart/${encodeURIComponent(sessionId)}/items`, {
    method: "POST",
    body: JSON.stringify({ product_id: productId, quantity }),
  });
}

export function removeFromCart(
  sessionId: string,
  productId: number
): Promise<{ removed_product_id: number }> {
  return request(`/cart/${encodeURIComponent(sessionId)}/items/${productId}`, {
    method: "DELETE",
  });
}

export function clearCart(
  sessionId: string
): Promise<{ cleared_session: string }> {
  return request(`/cart/${encodeURIComponent(sessionId)}`, {
    method: "DELETE",
  });
}

// ---- Orders --------------------------------------------------------------

export function checkout(
  sessionId: string,
  userId: number
): Promise<Order> {
  return request<Order>("/orders/checkout", {
    method: "POST",
    body: JSON.stringify({ session_id: sessionId, user_id: userId }),
  });
}

export function getOrder(orderId: number): Promise<Order> {
  return request<Order>(`/orders/${orderId}`);
}

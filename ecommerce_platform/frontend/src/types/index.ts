/**
 * types/index.ts — TypeScript interfaces that mirror the FastAPI Pydantic schemas.
 *
 * Keeping these in sync with the backend means TypeScript will catch mismatches
 * between what the frontend expects and what the API actually returns.
 */

// ---- Users ---------------------------------------------------------------

export interface User {
  id: number;
  email: string;
  name: string;
}

// ---- Products ------------------------------------------------------------

export interface Product {
  id: number;
  name: string;
  description: string | null;
  category: string | null;
  price: number;
  stock: number;
  seller_id: number | null;
  image_url: string | null;
  created_at: string;
}

export interface ProductSearchResult {
  id: number;
  name: string;
  category: string | null;
  price: number;
  score: number;
}

export interface ProductCreatePayload {
  name: string;
  description?: string;
  category?: string;
  price: number;
  stock: number;
}

export interface ProductUpdatePayload {
  name?: string;
  description?: string;
  category?: string;
  price?: number;
  stock?: number;
}

// ---- Cart ----------------------------------------------------------------

export interface CartItem {
  product_id: number;
  name: string;
  price: number;
  quantity: number;
  subtotal: number;
}

export interface Cart {
  session_id: string;
  items: CartItem[];
  total: number;
}

// ---- Orders --------------------------------------------------------------

export interface OrderItem {
  product_id: number;
  product_name: string;
  quantity: number;
  unit_price: number;
}

export interface Order {
  id: number;
  user_id: number;
  status: string;
  total: number;
  created_at: string;
  items: OrderItem[];
}

// ---- Health --------------------------------------------------------------

export interface HealthStatus {
  redis: string;
  postgres: string;
  elasticsearch: string;
}

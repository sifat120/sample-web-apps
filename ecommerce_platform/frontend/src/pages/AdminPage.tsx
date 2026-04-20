/**
 * pages/AdminPage.tsx — Seller / admin tools.
 *
 * Two main features:
 *   1. Create a new product (POST /products) — name, description, category,
 *      price, stock. After creation, the user can also upload an image.
 *   2. Edit price / stock of any product the user has created in this session
 *      (PUT /products/:id) — useful for testing the cache-invalidation
 *      behaviour: refresh the product page right after editing and you'll see
 *      the updated value immediately even though Redis just had a stale copy.
 *
 * The list of "session products" is intentionally **not** persisted across
 * reloads — there is no backend "list all products" endpoint, so we only
 * remember what was created in this browser tab.
 *
 * Auth note: the backend does not protect these endpoints. In a real app this
 * page would be gated by a "seller" role check.
 */

import { FormEvent, useState } from "react";

import {
  createProduct,
  updateProduct,
  uploadProductImage,
} from "../api/client";
import { useToast } from "../components/Toast";
import type { Product } from "../types";

export default function AdminPage() {
  const { addToast } = useToast();

  // Products created by the user during this session. Acts as both a record
  // of recent work and the source list for in-place edits.
  const [sessionProducts, setSessionProducts] = useState<Product[]>([]);

  function addSessionProduct(p: Product) {
    // newest first
    setSessionProducts((prev) => [p, ...prev.filter((q) => q.id !== p.id)]);
  }

  function updateSessionProduct(p: Product) {
    setSessionProducts((prev) => prev.map((q) => (q.id === p.id ? p : q)));
  }

  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_1fr]">
      <CreateProductForm
        onCreated={(p) => {
          addSessionProduct(p);
          addToast(`Product "${p.name}" created (#${p.id})`, "success");
        }}
      />

      <SessionProductsList
        products={sessionProducts}
        onUpdated={(p) => {
          updateSessionProduct(p);
          addToast(`Product #${p.id} updated`, "success");
        }}
      />
    </div>
  );
}

// ---- Create product ------------------------------------------------------

function CreateProductForm({ onCreated }: { onCreated: (p: Product) => void }) {
  const { addToast } = useToast();

  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [category, setCategory] = useState("");
  const [price, setPrice] = useState("");
  const [stock, setStock] = useState("");
  const [submitting, setSubmitting] = useState(false);

  // Image upload is gated until the product is created (we need its id).
  const [lastCreatedId, setLastCreatedId] = useState<number | null>(null);
  const [uploading, setUploading] = useState(false);

  async function handleCreate(e: FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    try {
      const created = await createProduct({
        name: name.trim(),
        description: description.trim() || undefined,
        category: category.trim() || undefined,
        price: Number(price),
        stock: Number(stock),
      });
      onCreated(created);
      setLastCreatedId(created.id);
      // Reset most fields, but keep category so creating a batch is faster.
      setName("");
      setDescription("");
      setPrice("");
      setStock("");
    } catch (err) {
      addToast(
        err instanceof Error ? err.message : "Could not create product",
        "error"
      );
    } finally {
      setSubmitting(false);
    }
  }

  async function handleImageUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file || lastCreatedId == null) return;
    setUploading(true);
    try {
      await uploadProductImage(lastCreatedId, file);
      addToast(`Image uploaded for product #${lastCreatedId}`, "success");
    } catch (err) {
      addToast(
        err instanceof Error ? err.message : "Image upload failed",
        "error"
      );
    } finally {
      setUploading(false);
      // Allow re-uploading the same file later by clearing the input value.
      e.target.value = "";
    }
  }

  return (
    <section className="rounded-2xl bg-white p-6 shadow-sm ring-1 ring-slate-100">
      <h1 className="text-xl font-bold text-slate-900">Create a product</h1>
      <p className="mt-1 text-sm text-slate-500">
        Saved to PostgreSQL and immediately indexed in Elasticsearch.
      </p>

      <form onSubmit={handleCreate} className="mt-5 space-y-4">
        <Field label="Name" value={name} onChange={setName} required />
        <Field
          label="Description"
          value={description}
          onChange={setDescription}
          textarea
        />
        <div className="grid grid-cols-2 gap-3">
          <Field
            label="Category"
            value={category}
            onChange={setCategory}
            placeholder="e.g. footwear"
          />
          <Field
            label="Price"
            type="number"
            value={price}
            onChange={setPrice}
            required
            step="0.01"
            min={0}
          />
        </div>
        <Field
          label="Stock"
          type="number"
          value={stock}
          onChange={setStock}
          required
          min={0}
        />

        <button
          type="submit"
          disabled={submitting}
          className="w-full rounded-xl bg-indigo-600 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-indigo-700 disabled:opacity-50"
        >
          {submitting ? "Creating…" : "Create product"}
        </button>
      </form>

      {/* Image upload — only shown after a product is created in this session */}
      {lastCreatedId != null && (
        <div className="mt-6 rounded-xl border border-dashed border-slate-300 bg-slate-50 p-4">
          <p className="text-sm font-medium text-slate-700">
            Upload an image for product #{lastCreatedId}
          </p>
          <p className="mt-0.5 text-xs text-slate-500">
            Stored in Azurite (or Azure Blob Storage in production); a SAS URL is generated on demand.
          </p>
          <input
            type="file"
            accept="image/*"
            disabled={uploading}
            onChange={handleImageUpload}
            className="mt-3 block w-full text-sm text-slate-600 file:mr-3 file:rounded-lg file:border-0 file:bg-indigo-600 file:px-3 file:py-1.5 file:text-sm file:font-semibold file:text-white hover:file:bg-indigo-700 disabled:opacity-50"
          />
          {uploading && (
            <p className="mt-2 text-xs text-slate-500">Uploading…</p>
          )}
        </div>
      )}
    </section>
  );
}

// ---- Edit existing (session) products -----------------------------------

function SessionProductsList({
  products,
  onUpdated,
}: {
  products: Product[];
  onUpdated: (p: Product) => void;
}) {
  return (
    <section className="rounded-2xl bg-white p-6 shadow-sm ring-1 ring-slate-100">
      <h2 className="text-xl font-bold text-slate-900">
        Recently created in this session
      </h2>
      <p className="mt-1 text-sm text-slate-500">
        Edit price or stock to see Redis cache invalidation in action — the
        next product fetch will read fresh data from PostgreSQL.
      </p>

      {products.length === 0 ? (
        <div className="mt-6 rounded-xl bg-slate-50 p-6 text-center text-sm text-slate-400">
          No products yet — create one on the left.
        </div>
      ) : (
        <ul className="mt-5 space-y-3">
          {products.map((p) => (
            <EditableProductRow key={p.id} product={p} onUpdated={onUpdated} />
          ))}
        </ul>
      )}
    </section>
  );
}

function EditableProductRow({
  product,
  onUpdated,
}: {
  product: Product;
  onUpdated: (p: Product) => void;
}) {
  const { addToast } = useToast();
  const [price, setPrice] = useState(String(product.price));
  const [stock, setStock] = useState(String(product.stock));
  const [saving, setSaving] = useState(false);

  // Disable the "Save" button if neither field has changed from the latest
  // server value — prevents accidental no-op PUTs.
  const dirty =
    Number(price) !== product.price || Number(stock) !== product.stock;

  async function handleSave() {
    setSaving(true);
    try {
      const updated = await updateProduct(product.id, {
        price: Number(price),
        stock: Number(stock),
      });
      onUpdated(updated);
    } catch (err) {
      addToast(
        err instanceof Error ? err.message : "Update failed",
        "error"
      );
    } finally {
      setSaving(false);
    }
  }

  return (
    <li className="flex flex-wrap items-center gap-3 rounded-xl bg-slate-50 p-3">
      <div className="min-w-0 flex-1">
        <p className="truncate font-medium text-slate-900">{product.name}</p>
        <p className="text-xs text-slate-500">
          #{product.id}
          {product.category ? ` · ${product.category}` : ""}
        </p>
      </div>

      <input
        type="number"
        step="0.01"
        min={0}
        value={price}
        onChange={(e) => setPrice(e.target.value)}
        className="w-24 rounded-lg border border-slate-200 px-2 py-1 text-sm outline-none focus:border-indigo-300 focus:ring-2 focus:ring-indigo-100"
      />
      <input
        type="number"
        min={0}
        value={stock}
        onChange={(e) => setStock(e.target.value)}
        className="w-20 rounded-lg border border-slate-200 px-2 py-1 text-sm outline-none focus:border-indigo-300 focus:ring-2 focus:ring-indigo-100"
      />

      <button
        onClick={handleSave}
        disabled={!dirty || saving}
        className="rounded-lg bg-indigo-600 px-3 py-1.5 text-sm font-semibold text-white transition hover:bg-indigo-700 disabled:opacity-40"
      >
        {saving ? "…" : "Save"}
      </button>
    </li>
  );
}

// ---- Generic labelled input (supports textarea) -------------------------

function Field({
  label,
  value,
  onChange,
  type = "text",
  textarea = false,
  ...rest
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  type?: string;
  textarea?: boolean;
  required?: boolean;
  placeholder?: string;
  min?: number;
  step?: string;
}) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-500">
        {label}
      </span>
      {textarea ? (
        <textarea
          value={value}
          onChange={(e) => onChange(e.target.value)}
          rows={3}
          {...rest}
          className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none transition focus:border-indigo-300 focus:ring-2 focus:ring-indigo-100"
        />
      ) : (
        <input
          type={type}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          {...rest}
          className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none transition focus:border-indigo-300 focus:ring-2 focus:ring-indigo-100"
        />
      )}
    </label>
  );
}

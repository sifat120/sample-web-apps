-- E-Commerce Platform — PostgreSQL schema
-- Run automatically by docker-compose via the init container hook.

CREATE TABLE IF NOT EXISTS users (
    id         SERIAL PRIMARY KEY,
    email      VARCHAR(255) UNIQUE NOT NULL,
    name       VARCHAR(255) NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS products (
    id          SERIAL PRIMARY KEY,
    name        VARCHAR(255) NOT NULL,
    description TEXT,
    category    VARCHAR(100),
    price       NUMERIC(10, 2) NOT NULL CHECK (price > 0),
    stock       INTEGER NOT NULL DEFAULT 0 CHECK (stock >= 0),
    seller_id   INTEGER REFERENCES users(id),
    image_url   VARCHAR(500),
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    updated_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS orders (
    id         SERIAL PRIMARY KEY,
    user_id    INTEGER NOT NULL REFERENCES users(id),
    status     VARCHAR(50) NOT NULL DEFAULT 'confirmed',
    total      NUMERIC(10, 2) NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS order_items (
    id           SERIAL PRIMARY KEY,
    order_id     INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    product_id   INTEGER NOT NULL REFERENCES products(id),
    product_name VARCHAR(255) NOT NULL,
    quantity     INTEGER NOT NULL CHECK (quantity > 0),
    unit_price   NUMERIC(10, 2) NOT NULL
);

CREATE TABLE IF NOT EXISTS reviews (
    id         SERIAL PRIMARY KEY,
    product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    user_id    INTEGER NOT NULL REFERENCES users(id),
    rating     SMALLINT NOT NULL CHECK (rating BETWEEN 1 AND 5),
    body       TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (product_id, user_id)
);

-- Seed data: one seller and a few products for easy local testing
INSERT INTO users (email, name) VALUES
    ('seller@example.com', 'Demo Seller'),
    ('buyer@example.com',  'Demo Buyer')
ON CONFLICT DO NOTHING;

INSERT INTO products (name, description, category, price, stock, seller_id) VALUES
    ('Hiking Boots',    'Waterproof leather boots for all terrain',      'footwear',     89.99, 50, 1),
    ('Trail Backpack',  '45L backpack with rain cover',                   'bags',         129.99, 30, 1),
    ('Camping Tent',    '2-person ultralight tent, 3-season',             'camping',      249.99, 15, 1),
    ('Wool Socks',      'Merino wool, moisture-wicking, 3-pack',          'footwear',     24.99, 100, 1),
    ('Trekking Poles',  'Collapsible aluminum poles with carbide tips',   'accessories',  59.99, 40, 1)
ON CONFLICT DO NOTHING;

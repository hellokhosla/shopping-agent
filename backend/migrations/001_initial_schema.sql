CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE OR REPLACE FUNCTION arr_text(a text[]) RETURNS text
  LANGUAGE sql IMMUTABLE PARALLEL SAFE
  AS $$ SELECT coalesce(array_to_string(a, ' '), '') $$;

CREATE TABLE IF NOT EXISTS retailers (
  retailer_id    text PRIMARY KEY CHECK (retailer_id ~ '^[a-z0-9_]+$'),
  display_name   text NOT NULL,
  config         jsonb NOT NULL,
  config_hash    text NOT NULL,
  help_page_url  text,
  loaded_at      timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS products (
  product_id         bigserial PRIMARY KEY,
  retailer_id        text NOT NULL REFERENCES retailers(retailer_id),
  external_id        text NOT NULL,
  title              text NOT NULL,
  brand              text,
  product_line       text,
  department         text NOT NULL,
  product_type       text NOT NULL,
  source_categories  text[] NOT NULL DEFAULT '{}',
  tags               text[] NOT NULL DEFAULT '{}',
  description        text,
  best_for           text,
  features           text[] NOT NULL DEFAULT '{}',
  attrs              jsonb NOT NULL DEFAULT '{}',
  occasion_tags      text[] NOT NULL DEFAULT '{}',
  style_tags         text[] NOT NULL DEFAULT '{}',
  size_class         text CHECK (size_class IN ('mini_carry_on','carry_on','medium','large','set')),
  rating             numeric(2,1) CHECK (rating BETWEEN 0 AND 5),
  review_count       int CHECK (review_count >= 0),
  promotion          text,
  image_url          text,
  product_url        text,
  search_text        text NOT NULL,
  search_tsv         tsvector GENERATED ALWAYS AS (
                       setweight(to_tsvector('simple', coalesce(brand,'') || ' ' || coalesce(product_line,'')), 'A') ||
                       setweight(to_tsvector('english', title), 'A') ||
                       setweight(to_tsvector('english', product_type || ' ' || arr_text(source_categories)), 'B') ||
                       setweight(to_tsvector('english', arr_text(tags) || ' ' || coalesce(best_for,'') || ' ' ||
                                                         arr_text(occasion_tags) || ' ' || arr_text(style_tags)), 'C') ||
                       setweight(to_tsvector('english', coalesce(description,'')), 'D')
                     ) STORED,
  embedding          vector(1024),
  embedding_model    text,
  embedded_at        timestamptz,
  synthetic_flags    text[] NOT NULL DEFAULT '{}'
                     CHECK (synthetic_flags <@ ARRAY['sizes','stock','dimensions','occasion_tags','style_tags']),
  is_active          boolean NOT NULL DEFAULT true,
  source_payload     jsonb,
  created_at         timestamptz NOT NULL DEFAULT now(),
  updated_at         timestamptz NOT NULL DEFAULT now(),
  UNIQUE (retailer_id, external_id),
  UNIQUE (product_id, retailer_id)
);

CREATE TABLE IF NOT EXISTS variants (
  variant_id           bigserial PRIMARY KEY,
  product_id           bigint NOT NULL,
  retailer_id          text NOT NULL,
  external_variant_id  text,
  sku                  text,
  colour_raw           text,
  colour_family        text CHECK (colour_family IS NULL OR colour_family IN
                         ('black_grey','white','brown','green','blue',
                          'purple','red_pink','yellow_gold','orange','multi')),
  colour_shade         text,
  size_label           text,
  size_norm            text NOT NULL DEFAULT 'ONE_SIZE',
  price                numeric(10,2) NOT NULL CHECK (price > 0),
  was_price            numeric(10,2),
  in_stock             boolean NOT NULL,
  image_url            text,
  variant_url          text,
  FOREIGN KEY (product_id, retailer_id)
    REFERENCES products (product_id, retailer_id) ON DELETE CASCADE,
  CHECK (was_price IS NULL OR was_price > price),
  UNIQUE (variant_id, retailer_id)
);

CREATE UNIQUE INDEX IF NOT EXISTS variants_product_colour_size_uq
  ON variants (product_id, (coalesce(colour_raw, '')), size_norm);

CREATE TABLE IF NOT EXISTS size_class_dims (
  retailer_id  text NOT NULL REFERENCES retailers(retailer_id),
  size_class   text NOT NULL,
  h_in         numeric(4,1) NOT NULL,
  w_in         numeric(4,1) NOT NULL,
  d_in         numeric(4,1) NOT NULL,
  is_typical   boolean NOT NULL DEFAULT true,
  source       text NOT NULL,
  PRIMARY KEY (retailer_id, size_class)
);

CREATE TABLE IF NOT EXISTS airline_limits (
  airline      text NOT NULL,
  bag_type     text NOT NULL CHECK (bag_type IN ('carry_on','personal_item')),
  max_h_in     numeric(4,1) NOT NULL,
  max_w_in     numeric(4,1) NOT NULL,
  max_d_in     numeric(4,1) NOT NULL,
  max_lb       numeric(4,1),
  source_url   text NOT NULL,
  checked_on   date NOT NULL,
  PRIMARY KEY (airline, bag_type)
);

CREATE TABLE IF NOT EXISTS review_cache (
  product_id      bigint PRIMARY KEY,
  retailer_id     text NOT NULL,
  reviews         jsonb NOT NULL,
  highlights      jsonb,
  rating_basis    numeric(2,1),
  is_synthetic    boolean NOT NULL DEFAULT true,
  pregenerated    boolean NOT NULL DEFAULT false,
  model           text NOT NULL,
  prompt_version  text NOT NULL,
  generated_at    timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY (product_id, retailer_id)
    REFERENCES products (product_id, retailer_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS sessions (
  session_id   text PRIMARY KEY,
  retailer_id  text NOT NULL REFERENCES retailers(retailer_id),
  created_at   timestamptz NOT NULL DEFAULT now(),
  UNIQUE (session_id, retailer_id)
);

CREATE TABLE IF NOT EXISTS cart_items (
  cart_item_id  bigserial PRIMARY KEY,
  session_id    text NOT NULL,
  retailer_id   text NOT NULL,
  variant_id    bigint NOT NULL,
  qty           int NOT NULL DEFAULT 1 CHECK (qty > 0),
  outfit_id     text,
  price_at_add  numeric(10,2) NOT NULL,
  added_at      timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY (session_id, retailer_id)
    REFERENCES sessions (session_id, retailer_id) ON DELETE CASCADE,
  FOREIGN KEY (variant_id, retailer_id)
    REFERENCES variants (variant_id, retailer_id),
  UNIQUE (session_id, variant_id)
);

CREATE INDEX IF NOT EXISTS variants_filter_idx
  ON variants (retailer_id, product_id) INCLUDE (price, colour_family, colour_shade, size_norm, in_stock);
CREATE INDEX IF NOT EXISTS variants_colour_idx
  ON variants (retailer_id, colour_family, price) WHERE in_stock;
CREATE INDEX IF NOT EXISTS products_type_idx
  ON products (retailer_id, product_type) WHERE is_active;
CREATE INDEX IF NOT EXISTS products_size_idx
  ON products (retailer_id, size_class) WHERE size_class IS NOT NULL;
CREATE INDEX IF NOT EXISTS products_tags_idx ON products USING gin (tags);
CREATE INDEX IF NOT EXISTS products_occasion_idx ON products USING gin (occasion_tags);
CREATE INDEX IF NOT EXISTS products_tsv_idx ON products USING gin (search_tsv);
CREATE INDEX IF NOT EXISTS products_title_trgm ON products USING gin (title gin_trgm_ops);
CREATE INDEX IF NOT EXISTS products_brand_trgm ON products USING gin (brand gin_trgm_ops);
CREATE INDEX IF NOT EXISTS products_embedding_idx ON products USING hnsw (embedding vector_cosine_ops);

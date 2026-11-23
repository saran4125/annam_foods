CREATE TABLE IF NOT EXISTS catalog_inventorybucket (
 id bigserial PRIMARY KEY,tenant_id bigint NOT NULL REFERENCES tenancy_tenant(id),item_id bigint NOT NULL REFERENCES catalog_menuitem(id),
 bucket_key varchar(120) NOT NULL,slot_id bigint REFERENCES catalog_slot(id),on_date date,
 tracked boolean NOT NULL DEFAULT false,remaining bigint NOT NULL DEFAULT 0 CHECK(remaining>=0),revision bigint NOT NULL DEFAULT 0,
 UNIQUE(tenant_id,bucket_key),CHECK((slot_id IS NULL AND on_date IS NULL) OR (slot_id IS NOT NULL AND on_date IS NOT NULL))
);
CREATE TABLE IF NOT EXISTS orders_stockreservation (
 id bigserial PRIMARY KEY,tenant_id bigint NOT NULL REFERENCES tenancy_tenant(id),order_id bigint NOT NULL REFERENCES orders_order(id),
 reservation_key varchar(140) NOT NULL,bucket_id bigint REFERENCES catalog_inventorybucket(id),schedule_id bigint REFERENCES catalog_menuschedule(id),
 quantity bigint NOT NULL CHECK(quantity>0),released boolean NOT NULL DEFAULT false,created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,released_at timestamptz,
 UNIQUE(tenant_id,order_id,reservation_key),CHECK(bucket_id IS NOT NULL OR schedule_id IS NOT NULL)
);
CREATE INDEX IF NOT EXISTS idx_inventory_item ON catalog_inventorybucket(tenant_id,item_id,slot_id,on_date);
CREATE INDEX IF NOT EXISTS idx_reservation_order ON orders_stockreservation(tenant_id,order_id,released);

CREATE TABLE IF NOT EXISTS orders_inventoryclaim(id bigserial PRIMARY KEY,tenant_id bigint NOT NULL REFERENCES tenancy_tenant(id),order_id bigint NOT NULL REFERENCES orders_order(id),UNIQUE(tenant_id,order_id));

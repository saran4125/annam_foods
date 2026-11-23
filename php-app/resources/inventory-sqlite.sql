CREATE TABLE IF NOT EXISTS catalog_inventorybucket (
 id INTEGER PRIMARY KEY AUTOINCREMENT,tenant_id INTEGER NOT NULL REFERENCES tenancy_tenant(id),item_id INTEGER NOT NULL REFERENCES catalog_menuitem(id),
 bucket_key TEXT NOT NULL,slot_id INTEGER REFERENCES catalog_slot(id),on_date TEXT,
 tracked INTEGER NOT NULL DEFAULT 0,remaining INTEGER NOT NULL DEFAULT 0 CHECK(remaining>=0),revision INTEGER NOT NULL DEFAULT 0,
 UNIQUE(tenant_id,bucket_key),CHECK((slot_id IS NULL AND on_date IS NULL) OR (slot_id IS NOT NULL AND on_date IS NOT NULL))
);
CREATE TABLE IF NOT EXISTS orders_stockreservation (
 id INTEGER PRIMARY KEY AUTOINCREMENT,tenant_id INTEGER NOT NULL REFERENCES tenancy_tenant(id),order_id INTEGER NOT NULL REFERENCES orders_order(id),
 reservation_key TEXT NOT NULL,bucket_id INTEGER REFERENCES catalog_inventorybucket(id),schedule_id INTEGER REFERENCES catalog_menuschedule(id),
 quantity INTEGER NOT NULL CHECK(quantity>0),released INTEGER NOT NULL DEFAULT 0,created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,released_at TEXT,
 UNIQUE(tenant_id,order_id,reservation_key),CHECK(bucket_id IS NOT NULL OR schedule_id IS NOT NULL)
);
CREATE INDEX IF NOT EXISTS idx_inventory_item ON catalog_inventorybucket(tenant_id,item_id,slot_id,on_date);
CREATE INDEX IF NOT EXISTS idx_reservation_order ON orders_stockreservation(tenant_id,order_id,released);

CREATE TABLE IF NOT EXISTS orders_inventoryclaim(id INTEGER PRIMARY KEY AUTOINCREMENT,tenant_id INTEGER NOT NULL REFERENCES tenancy_tenant(id),order_id INTEGER NOT NULL REFERENCES orders_order(id),UNIQUE(tenant_id,order_id));

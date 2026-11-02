<?php
declare(strict_types=1);
namespace Annam;

/** Additive compatibility upgrade for a restored database. No Python is needed. */
final class Schema {
    public static function ensure(Database $db): void {
        $db->transaction(function()use($db){
            $db->one("SELECT pg_advisory_xact_lock(hashtext('annam-php-parity-v2'))");
            foreach([
                "ALTER TABLE payments_refund ADD COLUMN IF NOT EXISTS processed_at timestamptz",
                "ALTER TABLE payments_paymentintent ADD COLUMN IF NOT EXISTS captured_at timestamptz",
                "ALTER TABLE catalog_menuitem ADD COLUMN IF NOT EXISTS in_stock boolean NOT NULL DEFAULT true",
                "ALTER TABLE catalog_menuitem ADD COLUMN IF NOT EXISTS weight varchar(100) NOT NULL DEFAULT ''",
                "ALTER TABLE catalog_menuitem ADD COLUMN IF NOT EXISTS admin_notes text NOT NULL DEFAULT ''",
                "ALTER TABLE catalog_slot ADD COLUMN IF NOT EXISTS order_days_before smallint NOT NULL DEFAULT 1",
                "ALTER TABLE catalog_slot ADD COLUMN IF NOT EXISTS order_opens_at time NOT NULL DEFAULT '00:00:00'",
                "CREATE TABLE IF NOT EXISTS php_login_attempt(id bigserial PRIMARY KEY,tenant_id bigint NOT NULL REFERENCES tenancy_tenant(id),fingerprint varchar(64) NOT NULL,attempted_at timestamptz NOT NULL)",
                "CREATE INDEX IF NOT EXISTS php_login_attempt_scope ON php_login_attempt(tenant_id,fingerprint,attempted_at)",
                "CREATE TABLE IF NOT EXISTS operations_ratelimitbucket(id bigserial PRIMARY KEY,tenant_id bigint NOT NULL REFERENCES tenancy_tenant(id),key varchar(64) NOT NULL,window_start timestamptz NOT NULL,expires_at timestamptz NOT NULL,attempts integer NOT NULL DEFAULT 0,UNIQUE(tenant_id,key,window_start))",
                "CREATE INDEX IF NOT EXISTS php_rate_expiry ON operations_ratelimitbucket(expires_at)",
                "CREATE TABLE IF NOT EXISTS operations_workerpulse(id bigserial PRIMARY KEY,tenant_id bigint NOT NULL REFERENCES tenancy_tenant(id),name varchar(40) NOT NULL,updated_at timestamptz NOT NULL,UNIQUE(tenant_id,name))",
                "CREATE TABLE IF NOT EXISTS catalog_catalogsyncrun(id bigserial PRIMARY KEY,tenant_id bigint NOT NULL REFERENCES tenancy_tenant(id),version varchar(100) NOT NULL,digest varchar(64) NOT NULL,report jsonb NOT NULL,applied_at timestamptz NOT NULL,UNIQUE(tenant_id,version))",
                "CREATE TABLE IF NOT EXISTS orders_couriercharge(id bigserial PRIMARY KEY,tenant_id bigint NOT NULL REFERENCES tenancy_tenant(id),order_id bigint NOT NULL UNIQUE REFERENCES orders_order(id),amount numeric(10,2),dispatched_at timestamptz,courier_name varchar(120) NOT NULL,tracking_number varchar(120) NOT NULL,paid_at timestamptz,payment_reference varchar(120) NOT NULL,created_at timestamptz NOT NULL)",
                "CREATE TABLE IF NOT EXISTS payments_courierpayment(id uuid PRIMARY KEY,tenant_id bigint NOT NULL REFERENCES tenancy_tenant(id),charge_id bigint NOT NULL REFERENCES orders_couriercharge(id),connection_id bigint NOT NULL REFERENCES payments_razorpayconnection(id),mode varchar(4) NOT NULL,key_id varchar(80) NOT NULL,amount bigint NOT NULL,currency varchar(3) NOT NULL,provider_order_id varchar(80) NOT NULL,payment_id varchar(80) NOT NULL,state varchar(16) NOT NULL,captured_at timestamptz,created_at timestamptz NOT NULL,updated_at timestamptz NOT NULL,UNIQUE(tenant_id,charge_id,mode))",
                "CREATE UNIQUE INDEX IF NOT EXISTS php_courier_provider_order ON payments_courierpayment(tenant_id,provider_order_id) WHERE provider_order_id<>''",
                "CREATE UNIQUE INDEX IF NOT EXISTS php_courier_provider_payment ON payments_courierpayment(tenant_id,payment_id) WHERE payment_id<>''",
                "CREATE INDEX IF NOT EXISTS idx_order_recent ON orders_order(tenant_id,placed_at DESC)"
            ] as $sql)$db->rows($sql);
        });
    }
}

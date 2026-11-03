-- SQLite 3.35+ schema; decimal currency uses TEXT affinity for exact amounts.

PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS "auth_group" (
  "id" INTEGER PRIMARY KEY AUTOINCREMENT,
  "name" TEXT NOT NULL,
  UNIQUE (name)
);

CREATE TABLE IF NOT EXISTS "auth_group_permissions" (
  "id" INTEGER PRIMARY KEY AUTOINCREMENT,
  "group_id" INTEGER NOT NULL,
  "permission_id" INTEGER NOT NULL,
  UNIQUE (group_id, permission_id),
  FOREIGN KEY (permission_id) REFERENCES auth_permission(id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (group_id) REFERENCES auth_group(id) DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE IF NOT EXISTS "auth_permission" (
  "id" INTEGER PRIMARY KEY AUTOINCREMENT,
  "name" TEXT NOT NULL,
  "content_type_id" INTEGER NOT NULL,
  "codename" TEXT NOT NULL,
  UNIQUE (content_type_id, codename),
  FOREIGN KEY (content_type_id) REFERENCES django_content_type(id) DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE IF NOT EXISTS "auth_user" (
  "id" INTEGER PRIMARY KEY AUTOINCREMENT,
  "password" TEXT NOT NULL,
  "last_login" TIMESTAMP,
  "is_superuser" BOOLEAN NOT NULL,
  "username" TEXT NOT NULL,
  "first_name" TEXT NOT NULL,
  "last_name" TEXT NOT NULL,
  "email" TEXT NOT NULL,
  "is_staff" BOOLEAN NOT NULL,
  "is_active" BOOLEAN NOT NULL,
  "date_joined" TIMESTAMP NOT NULL,
  UNIQUE (username)
);

CREATE TABLE IF NOT EXISTS "auth_user_groups" (
  "id" INTEGER PRIMARY KEY AUTOINCREMENT,
  "user_id" INTEGER NOT NULL,
  "group_id" INTEGER NOT NULL,
  UNIQUE (user_id, group_id),
  FOREIGN KEY (group_id) REFERENCES auth_group(id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (user_id) REFERENCES auth_user(id) DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE IF NOT EXISTS "auth_user_user_permissions" (
  "id" INTEGER PRIMARY KEY AUTOINCREMENT,
  "user_id" INTEGER NOT NULL,
  "permission_id" INTEGER NOT NULL,
  UNIQUE (user_id, permission_id),
  FOREIGN KEY (permission_id) REFERENCES auth_permission(id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (user_id) REFERENCES auth_user(id) DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE IF NOT EXISTS "billing_invoice" (
  "id" INTEGER PRIMARY KEY AUTOINCREMENT,
  "kind" TEXT NOT NULL,
  "series" TEXT NOT NULL,
  "number" TEXT NOT NULL,
  "financial_year" TEXT NOT NULL,
  "sequence_no" INTEGER NOT NULL,
  "seller" JSON_TEXT NOT NULL,
  "buyer" JSON_TEXT NOT NULL,
  "lines" JSON_TEXT NOT NULL,
  "taxable" DECIMAL_TEXT NOT NULL,
  "cgst" DECIMAL_TEXT NOT NULL,
  "sgst" DECIMAL_TEXT NOT NULL,
  "igst" DECIMAL_TEXT NOT NULL,
  "round_off" DECIMAL_TEXT NOT NULL,
  "total" DECIMAL_TEXT NOT NULL,
  "amount_words" TEXT NOT NULL,
  "payment_mode" TEXT NOT NULL,
  "payment_ref" TEXT NOT NULL,
  "pdf" TEXT NOT NULL,
  "issued_at" TIMESTAMP NOT NULL,
  "sent_customer_at" TIMESTAMP,
  "sent_owner_at" TIMESTAMP,
  "order_id" INTEGER,
  "original_id" INTEGER,
  "tenant_id" INTEGER NOT NULL,
  CHECK ((sequence_no >= 0)),
  UNIQUE (tenant_id, number),
  UNIQUE (tenant_id, series, financial_year, sequence_no),
  FOREIGN KEY (order_id) REFERENCES orders_order(id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (original_id) REFERENCES billing_invoice(id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (tenant_id) REFERENCES tenancy_tenant(id) DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE IF NOT EXISTS "billing_invoicerequest" (
  "id" INTEGER PRIMARY KEY AUTOINCREMENT,
  "phone" TEXT NOT NULL,
  "details" TEXT NOT NULL,
  "wants_gst" BOOLEAN NOT NULL,
  "gst_details" JSON_TEXT NOT NULL,
  "status" TEXT NOT NULL,
  "reason" TEXT NOT NULL,
  "handled_by" TEXT NOT NULL,
  "created_at" TIMESTAMP NOT NULL,
  "resolved_at" TIMESTAMP,
  "customer_id" INTEGER,
  "invoice_id" INTEGER,
  "order_id" INTEGER,
  "tenant_id" INTEGER NOT NULL,
  FOREIGN KEY (customer_id) REFERENCES orders_customer(id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (invoice_id) REFERENCES billing_invoice(id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (order_id) REFERENCES orders_order(id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (tenant_id) REFERENCES tenancy_tenant(id) DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE IF NOT EXISTS "billing_invoicesequence" (
  "id" INTEGER PRIMARY KEY AUTOINCREMENT,
  "series" TEXT NOT NULL,
  "financial_year" TEXT NOT NULL,
  "next_no" INTEGER NOT NULL,
  "tenant_id" INTEGER NOT NULL,
  CHECK ((next_no >= 0)),
  UNIQUE (tenant_id, series, financial_year),
  FOREIGN KEY (tenant_id) REFERENCES tenancy_tenant(id) DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE IF NOT EXISTS "catalog_catalogsyncrun" (
  "id" INTEGER PRIMARY KEY AUTOINCREMENT,
  "version" TEXT NOT NULL,
  "digest" TEXT NOT NULL,
  "report" JSON_TEXT NOT NULL,
  "applied_at" TIMESTAMP NOT NULL,
  "tenant_id" INTEGER NOT NULL,
  UNIQUE (tenant_id, version),
  FOREIGN KEY (tenant_id) REFERENCES tenancy_tenant(id) DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE IF NOT EXISTS "catalog_menucategory" (
  "id" INTEGER PRIMARY KEY AUTOINCREMENT,
  "name" TEXT NOT NULL,
  "sort" INTEGER NOT NULL,
  "active" BOOLEAN NOT NULL,
  "tenant_id" INTEGER NOT NULL,
  "description" TEXT NOT NULL,
  "image" TEXT NOT NULL,
  "parent_id" INTEGER,
  "slug" TEXT NOT NULL,
  CHECK ((sort >= 0)),
  FOREIGN KEY (parent_id) REFERENCES catalog_menucategory(id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (tenant_id) REFERENCES tenancy_tenant(id) DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE IF NOT EXISTS "catalog_menuday" (
  "id" INTEGER PRIMARY KEY AUTOINCREMENT,
  "on_date" DATE NOT NULL,
  "revision" INTEGER NOT NULL,
  "updated_at" TIMESTAMP NOT NULL,
  "slot_id" INTEGER NOT NULL,
  "tenant_id" INTEGER NOT NULL,
  CHECK ((revision >= 0)),
  UNIQUE (tenant_id, slot_id, on_date),
  FOREIGN KEY (slot_id) REFERENCES catalog_slot(id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (tenant_id) REFERENCES tenancy_tenant(id) DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE IF NOT EXISTS "catalog_menuitem" (
  "id" INTEGER PRIMARY KEY AUTOINCREMENT,
  "name" TEXT NOT NULL,
  "description" TEXT NOT NULL,
  "price" DECIMAL_TEXT NOT NULL,
  "image" TEXT NOT NULL,
  "is_veg" BOOLEAN NOT NULL,
  "tags" JSON_TEXT NOT NULL,
  "active" BOOLEAN NOT NULL,
  "sort" INTEGER NOT NULL,
  "category_id" INTEGER,
  "tenant_id" INTEGER NOT NULL,
  "fulfilment" TEXT NOT NULL,
  "retailer_id" TEXT,
  "sac" TEXT NOT NULL,
  "tax_rate" DECIMAL_TEXT,
  "admin_notes" TEXT NOT NULL,
  "in_stock" BOOLEAN NOT NULL,
  "weight" TEXT NOT NULL,
  CHECK ((sort >= 0)),
  UNIQUE (tenant_id, retailer_id),
  FOREIGN KEY (category_id) REFERENCES catalog_menucategory(id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (tenant_id) REFERENCES tenancy_tenant(id) DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE IF NOT EXISTS "catalog_menuschedule" (
  "id" INTEGER PRIMARY KEY AUTOINCREMENT,
  "mode" TEXT NOT NULL,
  "on_date" DATE,
  "weekday" INTEGER,
  "available" BOOLEAN NOT NULL,
  "qty_limit" INTEGER,
  "qty_sold" INTEGER NOT NULL,
  "price_override" DECIMAL_TEXT,
  "item_id" INTEGER NOT NULL,
  "tenant_id" INTEGER NOT NULL,
  "slot_id" INTEGER NOT NULL,
  CHECK ((qty_limit >= 0)),
  CHECK ((qty_sold >= 0)),
  CHECK ((weekday >= 0)),
  CHECK (((((mode) = 'date') AND (on_date IS NOT NULL) AND (weekday IS NULL)) OR (((mode) = 'weekday') AND (on_date IS NULL) AND (weekday IS NOT NULL)))),
  FOREIGN KEY (item_id) REFERENCES catalog_menuitem(id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (slot_id) REFERENCES catalog_slot(id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (tenant_id) REFERENCES tenancy_tenant(id) DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE IF NOT EXISTS "catalog_slot" (
  "id" INTEGER PRIMARY KEY AUTOINCREMENT,
  "key" TEXT NOT NULL,
  "label" TEXT NOT NULL,
  "order_cutoff" TIME NOT NULL,
  "delivery_from" TIME,
  "delivery_to" TIME,
  "sort" INTEGER NOT NULL,
  "active" BOOLEAN NOT NULL,
  "tenant_id" INTEGER NOT NULL,
  "order_days_before" INTEGER NOT NULL,
  "order_opens_at" TIME NOT NULL,
  CHECK ((order_days_before >= 0)),
  CHECK ((sort >= 0)),
  UNIQUE (tenant_id, key),
  FOREIGN KEY (tenant_id) REFERENCES tenancy_tenant(id) DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE IF NOT EXISTS "content_banner" (
  "id" INTEGER PRIMARY KEY AUTOINCREMENT,
  "title" TEXT NOT NULL,
  "subtitle" TEXT NOT NULL,
  "image" TEXT NOT NULL,
  "link" TEXT NOT NULL,
  "active" BOOLEAN NOT NULL,
  "sort" INTEGER NOT NULL,
  "tenant_id" INTEGER NOT NULL,
  CHECK ((sort >= 0)),
  FOREIGN KEY (tenant_id) REFERENCES tenancy_tenant(id) DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE IF NOT EXISTS "content_page" (
  "id" INTEGER PRIMARY KEY AUTOINCREMENT,
  "slug" TEXT NOT NULL,
  "title" TEXT NOT NULL,
  "body_md" TEXT NOT NULL,
  "seo_description" TEXT NOT NULL,
  "published" BOOLEAN NOT NULL,
  "show_in_nav" BOOLEAN NOT NULL,
  "sort" INTEGER NOT NULL,
  "updated_at" TIMESTAMP NOT NULL,
  "tenant_id" INTEGER NOT NULL,
  CHECK ((sort >= 0)),
  UNIQUE (tenant_id, slug),
  FOREIGN KEY (tenant_id) REFERENCES tenancy_tenant(id) DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE IF NOT EXISTS "content_storefrontimage" (
  "id" TEXT PRIMARY KEY NOT NULL,
  "name" TEXT NOT NULL,
  "content_type" TEXT NOT NULL,
  "data" BLOB NOT NULL,
  "width" INTEGER NOT NULL,
  "height" INTEGER NOT NULL,
  "created_at" TIMESTAMP NOT NULL,
  "tenant_id" INTEGER NOT NULL,
  CHECK ((height >= 0)),
  CHECK ((width >= 0)),
  FOREIGN KEY (tenant_id) REFERENCES tenancy_tenant(id) DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE IF NOT EXISTS "delivery_deliveryzone" (
  "id" INTEGER PRIMARY KEY AUTOINCREMENT,
  "pincode" TEXT NOT NULL,
  "area_name" TEXT NOT NULL,
  "delivery_fee" DECIMAL_TEXT NOT NULL,
  "min_order" DECIMAL_TEXT NOT NULL,
  "slot_keys" JSON_TEXT NOT NULL,
  "active" BOOLEAN NOT NULL,
  "tenant_id" INTEGER NOT NULL,
  UNIQUE (tenant_id, pincode, area_name),
  FOREIGN KEY (tenant_id) REFERENCES tenancy_tenant(id) DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE IF NOT EXISTS "django_admin_log" (
  "id" INTEGER PRIMARY KEY AUTOINCREMENT,
  "action_time" TIMESTAMP NOT NULL,
  "object_id" TEXT,
  "object_repr" TEXT NOT NULL,
  "action_flag" INTEGER NOT NULL,
  "change_message" TEXT NOT NULL,
  "content_type_id" INTEGER,
  "user_id" INTEGER NOT NULL,
  CHECK ((action_flag >= 0)),
  FOREIGN KEY (content_type_id) REFERENCES django_content_type(id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (user_id) REFERENCES auth_user(id) DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE IF NOT EXISTS "django_content_type" (
  "id" INTEGER PRIMARY KEY AUTOINCREMENT,
  "app_label" TEXT NOT NULL,
  "model" TEXT NOT NULL,
  UNIQUE (app_label, model)
);

CREATE TABLE IF NOT EXISTS "django_migrations" (
  "id" INTEGER PRIMARY KEY AUTOINCREMENT,
  "app" TEXT NOT NULL,
  "name" TEXT NOT NULL,
  "applied" TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS "django_session" (
  "session_key" TEXT PRIMARY KEY NOT NULL,
  "session_data" TEXT NOT NULL,
  "expire_date" TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS "jobs_dailykitchenrun" (
  "id" INTEGER PRIMARY KEY AUTOINCREMENT,
  "local_date" DATE NOT NULL,
  "started_at" TIMESTAMP NOT NULL,
  "tenant_id" INTEGER NOT NULL,
  UNIQUE (tenant_id, local_date),
  FOREIGN KEY (tenant_id) REFERENCES tenancy_tenant(id) DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE IF NOT EXISTS "messaging_outboundmessage" (
  "id" INTEGER PRIMARY KEY AUTOINCREMENT,
  "to_phone" TEXT NOT NULL,
  "payload" JSON_TEXT NOT NULL,
  "purpose" TEXT NOT NULL,
  "status" TEXT NOT NULL,
  "provider" TEXT NOT NULL,
  "provider_message_id" TEXT NOT NULL,
  "attempts" INTEGER NOT NULL,
  "last_error" TEXT NOT NULL,
  "next_attempt_at" TIMESTAMP NOT NULL,
  "dedupe_key" TEXT NOT NULL,
  "created_at" TIMESTAMP NOT NULL,
  "sent_at" TIMESTAMP,
  "tenant_id" INTEGER NOT NULL,
  "claimed_at" TIMESTAMP,
  CHECK ((attempts >= 0)),
  FOREIGN KEY (tenant_id) REFERENCES tenancy_tenant(id) DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE IF NOT EXISTS "messaging_whatsappconversation" (
  "id" INTEGER PRIMARY KEY AUTOINCREMENT,
  "phone" TEXT NOT NULL,
  "display_name" TEXT NOT NULL,
  "last_message_at" TIMESTAMP NOT NULL,
  "last_inbound_at" TIMESTAMP,
  "preview" TEXT NOT NULL,
  "unread_count" INTEGER NOT NULL,
  "tenant_id" INTEGER NOT NULL,
  CHECK ((unread_count >= 0)),
  UNIQUE (tenant_id, phone),
  FOREIGN KEY (tenant_id) REFERENCES tenancy_tenant(id) DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE IF NOT EXISTS "messaging_whatsappforwardevent" (
  "id" INTEGER PRIMARY KEY AUTOINCREMENT,
  "digest" TEXT NOT NULL,
  "payload" JSON_TEXT NOT NULL,
  "status" TEXT NOT NULL,
  "attempts" INTEGER NOT NULL,
  "next_attempt_at" TIMESTAMP NOT NULL,
  "claimed_at" TIMESTAMP,
  "last_error" TEXT NOT NULL,
  "created_at" TIMESTAMP NOT NULL,
  "tenant_id" INTEGER NOT NULL,
  CHECK ((attempts >= 0)),
  UNIQUE (tenant_id, digest),
  FOREIGN KEY (tenant_id) REFERENCES tenancy_tenant(id) DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE IF NOT EXISTS "messaging_whatsappmessage" (
  "id" INTEGER PRIMARY KEY AUTOINCREMENT,
  "direction" TEXT NOT NULL,
  "kind" TEXT NOT NULL,
  "body" TEXT NOT NULL,
  "provider_message_id" TEXT NOT NULL,
  "status" TEXT NOT NULL,
  "occurred_at" TIMESTAMP NOT NULL,
  "created_at" TIMESTAMP NOT NULL,
  "payload" JSON_TEXT NOT NULL,
  "media_id" TEXT NOT NULL,
  "filename" TEXT NOT NULL,
  "mime_type" TEXT NOT NULL,
  "actor" TEXT NOT NULL,
  "conversation_id" INTEGER NOT NULL,
  "outbound_id" INTEGER,
  "tenant_id" INTEGER NOT NULL,
  UNIQUE (outbound_id),
  FOREIGN KEY (conversation_id) REFERENCES messaging_whatsappconversation(id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (outbound_id) REFERENCES messaging_outboundmessage(id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (tenant_id) REFERENCES tenancy_tenant(id) DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE IF NOT EXISTS "messaging_whatsappreceipt" (
  "id" INTEGER PRIMARY KEY AUTOINCREMENT,
  "provider_message_id" TEXT NOT NULL,
  "status" TEXT NOT NULL,
  "phone" TEXT NOT NULL,
  "occurred_at" TIMESTAMP NOT NULL,
  "tenant_id" INTEGER NOT NULL,
  UNIQUE (tenant_id, provider_message_id, status),
  FOREIGN KEY (tenant_id) REFERENCES tenancy_tenant(id) DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE IF NOT EXISTS "operations_ratelimitbucket" (
  "id" INTEGER PRIMARY KEY AUTOINCREMENT,
  "key" TEXT NOT NULL,
  "window_start" TIMESTAMP NOT NULL,
  "expires_at" TIMESTAMP NOT NULL,
  "attempts" INTEGER NOT NULL,
  "tenant_id" INTEGER NOT NULL,
  CHECK ((attempts >= 0)),
  UNIQUE (tenant_id, key, window_start),
  FOREIGN KEY (tenant_id) REFERENCES tenancy_tenant(id) DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE IF NOT EXISTS "operations_workerpulse" (
  "id" INTEGER PRIMARY KEY AUTOINCREMENT,
  "name" TEXT NOT NULL,
  "updated_at" TIMESTAMP NOT NULL,
  "tenant_id" INTEGER NOT NULL,
  UNIQUE (tenant_id, name),
  FOREIGN KEY (tenant_id) REFERENCES tenancy_tenant(id) DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE IF NOT EXISTS "orders_address" (
  "id" INTEGER PRIMARY KEY AUTOINCREMENT,
  "label" TEXT NOT NULL,
  "line1" TEXT NOT NULL,
  "line2" TEXT NOT NULL,
  "landmark" TEXT NOT NULL,
  "pincode" TEXT NOT NULL,
  "is_default" BOOLEAN NOT NULL,
  "tenant_id" INTEGER NOT NULL,
  "zone_id" INTEGER,
  "customer_id" INTEGER NOT NULL,
  FOREIGN KEY (customer_id) REFERENCES orders_customer(id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (tenant_id) REFERENCES tenancy_tenant(id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (zone_id) REFERENCES delivery_deliveryzone(id) DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE IF NOT EXISTS "orders_couriercharge" (
  "id" INTEGER PRIMARY KEY AUTOINCREMENT,
  "amount" DECIMAL_TEXT,
  "dispatched_at" TIMESTAMP,
  "courier_name" TEXT NOT NULL,
  "tracking_number" TEXT NOT NULL,
  "paid_at" TIMESTAMP,
  "payment_reference" TEXT NOT NULL,
  "created_at" TIMESTAMP NOT NULL,
  "order_id" INTEGER NOT NULL,
  "tenant_id" INTEGER NOT NULL,
  UNIQUE (order_id),
  FOREIGN KEY (order_id) REFERENCES orders_order(id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (tenant_id) REFERENCES tenancy_tenant(id) DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE IF NOT EXISTS "orders_customer" (
  "id" INTEGER PRIMARY KEY AUTOINCREMENT,
  "phone" TEXT NOT NULL,
  "name" TEXT NOT NULL,
  "email" TEXT NOT NULL,
  "source" TEXT NOT NULL,
  "first_seen" TIMESTAMP NOT NULL,
  "last_seen" TIMESTAMP NOT NULL,
  "notes" TEXT NOT NULL,
  "tenant_id" INTEGER NOT NULL,
  "billing_address" TEXT NOT NULL,
  "business_name" TEXT NOT NULL,
  "gstin" TEXT NOT NULL,
  UNIQUE (tenant_id, phone),
  FOREIGN KEY (tenant_id) REFERENCES tenancy_tenant(id) DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE IF NOT EXISTS "orders_order" (
  "id" INTEGER PRIMARY KEY AUTOINCREMENT,
  "order_no" TEXT NOT NULL,
  "channel" TEXT NOT NULL,
  "status" TEXT NOT NULL,
  "payment_status" TEXT NOT NULL,
  "delivery_date" DATE,
  "items" JSON_TEXT NOT NULL,
  "address" JSON_TEXT NOT NULL,
  "subtotal" DECIMAL_TEXT NOT NULL,
  "delivery_fee" DECIMAL_TEXT NOT NULL,
  "discount" DECIMAL_TEXT NOT NULL,
  "total" DECIMAL_TEXT NOT NULL,
  "coupon_code" TEXT NOT NULL,
  "placed_at" TIMESTAMP NOT NULL,
  "cancelled_reason" TEXT NOT NULL,
  "customer_id" INTEGER NOT NULL,
  "slot_id" INTEGER,
  "tenant_id" INTEGER NOT NULL,
  "buyer_gst" JSON_TEXT NOT NULL,
  "external_ref" TEXT NOT NULL,
  "fulfilment" TEXT NOT NULL,
  "payment_mode" TEXT NOT NULL,
  "rider_name" TEXT NOT NULL,
  "rider_phone" TEXT NOT NULL,
  "source" TEXT NOT NULL,
  "payment_reference" TEXT NOT NULL,
  "pricing" JSON_TEXT NOT NULL,
  UNIQUE (tenant_id, order_no),
  FOREIGN KEY (customer_id) REFERENCES orders_customer(id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (slot_id) REFERENCES catalog_slot(id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (tenant_id) REFERENCES tenancy_tenant(id) DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE IF NOT EXISTS "orders_orderevent" (
  "id" INTEGER PRIMARY KEY AUTOINCREMENT,
  "from_status" TEXT NOT NULL,
  "to_status" TEXT NOT NULL,
  "actor" TEXT NOT NULL,
  "note" TEXT NOT NULL,
  "at" TIMESTAMP NOT NULL,
  "order_id" INTEGER NOT NULL,
  "tenant_id" INTEGER NOT NULL,
  FOREIGN KEY (order_id) REFERENCES orders_order(id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (tenant_id) REFERENCES tenancy_tenant(id) DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE IF NOT EXISTS "payments_courierpayment" (
  "id" TEXT PRIMARY KEY NOT NULL,
  "mode" TEXT NOT NULL,
  "key_id" TEXT NOT NULL,
  "amount" INTEGER NOT NULL,
  "currency" TEXT NOT NULL,
  "provider_order_id" TEXT NOT NULL,
  "payment_id" TEXT NOT NULL,
  "state" TEXT NOT NULL,
  "captured_at" TIMESTAMP,
  "created_at" TIMESTAMP NOT NULL,
  "updated_at" TIMESTAMP NOT NULL,
  "charge_id" INTEGER NOT NULL,
  "connection_id" INTEGER NOT NULL,
  "tenant_id" INTEGER NOT NULL,
  CHECK ((amount >= 0)),
  UNIQUE (tenant_id, charge_id, mode),
  FOREIGN KEY (charge_id) REFERENCES orders_couriercharge(id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (connection_id) REFERENCES payments_razorpayconnection(id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (tenant_id) REFERENCES tenancy_tenant(id) DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE IF NOT EXISTS "payments_paymentevent" (
  "id" INTEGER PRIMARY KEY AUTOINCREMENT,
  "mode" TEXT NOT NULL,
  "event_id" TEXT NOT NULL,
  "kind" TEXT NOT NULL,
  "processed_at" TIMESTAMP NOT NULL,
  "tenant_id" INTEGER NOT NULL,
  UNIQUE (tenant_id, mode, event_id),
  FOREIGN KEY (tenant_id) REFERENCES tenancy_tenant(id) DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE IF NOT EXISTS "payments_paymentintent" (
  "id" TEXT PRIMARY KEY NOT NULL,
  "key_id" TEXT NOT NULL,
  "mode" TEXT NOT NULL,
  "amount" INTEGER NOT NULL,
  "currency" TEXT NOT NULL,
  "provider_order_id" TEXT NOT NULL,
  "payment_id" TEXT NOT NULL,
  "state" TEXT NOT NULL,
  "refunded_amount" INTEGER NOT NULL,
  "bill_error" TEXT NOT NULL,
  "created_at" TIMESTAMP NOT NULL,
  "updated_at" TIMESTAMP NOT NULL,
  "credit_note_id" INTEGER,
  "order_id" INTEGER NOT NULL,
  "tenant_id" INTEGER NOT NULL,
  "connection_id" INTEGER NOT NULL,
  "captured_at" TIMESTAMP,
  CHECK ((amount >= 0)),
  CHECK ((refunded_amount >= 0)),
  UNIQUE (order_id),
  FOREIGN KEY (connection_id) REFERENCES payments_razorpayconnection(id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (credit_note_id) REFERENCES billing_invoice(id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (order_id) REFERENCES orders_order(id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (tenant_id) REFERENCES tenancy_tenant(id) DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE IF NOT EXISTS "payments_razorpayconnection" (
  "id" INTEGER PRIMARY KEY AUTOINCREMENT,
  "mode" TEXT NOT NULL,
  "enabled" BOOLEAN NOT NULL,
  "key_id" TEXT NOT NULL,
  "_key_secret" TEXT NOT NULL,
  "_webhook_secret" TEXT NOT NULL,
  "updated_at" TIMESTAMP NOT NULL,
  "tenant_id" INTEGER NOT NULL,
  UNIQUE (tenant_id, mode),
  FOREIGN KEY (tenant_id) REFERENCES tenancy_tenant(id) DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE IF NOT EXISTS "payments_refund" (
  "id" TEXT PRIMARY KEY NOT NULL,
  "amount" INTEGER NOT NULL,
  "provider_id" TEXT NOT NULL,
  "state" TEXT NOT NULL,
  "reason" TEXT NOT NULL,
  "actor" TEXT NOT NULL,
  "created_at" TIMESTAMP NOT NULL,
  "updated_at" TIMESTAMP NOT NULL,
  "intent_id" TEXT NOT NULL,
  "tenant_id" INTEGER NOT NULL,
  "processed_at" TIMESTAMP,
  CHECK ((amount >= 0)),
  FOREIGN KEY (intent_id) REFERENCES payments_paymentintent(id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (tenant_id) REFERENCES tenancy_tenant(id) DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE IF NOT EXISTS "php_login_attempt" (
  "id" INTEGER PRIMARY KEY AUTOINCREMENT,
  "tenant_id" INTEGER NOT NULL,
  "fingerprint" TEXT NOT NULL,
  "attempted_at" TIMESTAMP NOT NULL,
  FOREIGN KEY (tenant_id) REFERENCES tenancy_tenant(id) DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE IF NOT EXISTS "tenancy_billingprofile" (
  "id" INTEGER PRIMARY KEY AUTOINCREMENT,
  "legal_name" TEXT NOT NULL,
  "address" TEXT NOT NULL,
  "state" TEXT NOT NULL,
  "state_code" TEXT NOT NULL,
  "gstin" TEXT NOT NULL,
  "fssai_no" TEXT NOT NULL,
  "gst_mode" TEXT NOT NULL,
  "tax_rate" DECIMAL_TEXT NOT NULL,
  "sac" TEXT NOT NULL,
  "prices_include_tax" BOOLEAN NOT NULL,
  "number_format" TEXT NOT NULL,
  "round_total" BOOLEAN NOT NULL,
  "delivery_fee_taxable" BOOLEAN NOT NULL,
  "footer" TEXT NOT NULL,
  "layout" TEXT NOT NULL,
  "tenant_id" INTEGER NOT NULL,
  "bill_request_daily_limit" INTEGER NOT NULL,
  "bill_request_promise_hours" INTEGER NOT NULL,
  "bill_timing" TEXT NOT NULL,
  "invoice_prefix" TEXT NOT NULL,
  CHECK ((bill_request_daily_limit >= 0)),
  CHECK ((bill_request_promise_hours >= 0)),
  UNIQUE (tenant_id),
  FOREIGN KEY (tenant_id) REFERENCES tenancy_tenant(id) DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE IF NOT EXISTS "tenancy_customdomain" (
  "id" INTEGER PRIMARY KEY AUTOINCREMENT,
  "hostname" TEXT NOT NULL,
  "verification_token" TEXT NOT NULL,
  "status" TEXT NOT NULL,
  "ownership_verified_at" TIMESTAMP,
  "dns_verified_at" TIMESTAMP,
  "connection_requested_at" TIMESTAMP,
  "tls_verified_at" TIMESTAMP,
  "checked_at" TIMESTAMP,
  "provider_id" TEXT NOT NULL,
  "detail" TEXT NOT NULL,
  "created_at" TIMESTAMP NOT NULL,
  "mapping_id" INTEGER,
  "tenant_id" INTEGER NOT NULL,
  UNIQUE (hostname),
  UNIQUE (mapping_id),
  FOREIGN KEY (mapping_id) REFERENCES tenancy_tenantdomain(id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (tenant_id) REFERENCES tenancy_tenant(id) DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE IF NOT EXISTS "tenancy_ownerinvitation" (
  "id" INTEGER PRIMARY KEY AUTOINCREMENT,
  "email" TEXT NOT NULL,
  "token_hash" TEXT NOT NULL,
  "expires_at" TIMESTAMP NOT NULL,
  "accepted_at" TIMESTAMP,
  "revoked_at" TIMESTAMP,
  "created_at" TIMESTAMP NOT NULL,
  "tenant_id" INTEGER NOT NULL,
  "user_id" INTEGER NOT NULL,
  UNIQUE (token_hash),
  FOREIGN KEY (tenant_id) REFERENCES tenancy_tenant(id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (user_id) REFERENCES auth_user(id) DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE IF NOT EXISTS "tenancy_platformauditevent" (
  "id" INTEGER PRIMARY KEY AUTOINCREMENT,
  "action" TEXT NOT NULL,
  "details" JSON_TEXT NOT NULL,
  "created_at" TIMESTAMP NOT NULL,
  "actor_id" INTEGER,
  "tenant_id" INTEGER NOT NULL,
  FOREIGN KEY (tenant_id) REFERENCES tenancy_tenant(id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (actor_id) REFERENCES auth_user(id) DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE IF NOT EXISTS "tenancy_tenant" (
  "id" INTEGER PRIMARY KEY AUTOINCREMENT,
  "slug" TEXT NOT NULL,
  "name" TEXT NOT NULL,
  "primary_domain" TEXT NOT NULL,
  "status" TEXT NOT NULL,
  "created_at" TIMESTAMP NOT NULL,
  UNIQUE (slug)
);

CREATE TABLE IF NOT EXISTS "tenancy_tenantconfig" (
  "id" INTEGER PRIMARY KEY AUTOINCREMENT,
  "brand_name" TEXT NOT NULL,
  "tagline" TEXT NOT NULL,
  "theme" JSON_TEXT NOT NULL,
  "support_phone" TEXT NOT NULL,
  "timezone" TEXT NOT NULL,
  "currency" TEXT NOT NULL,
  "menu_mode" TEXT NOT NULL,
  "kitchen_open" TIME,
  "kitchen_close" TIME,
  "features" JSON_TEXT NOT NULL,
  "tenant_id" INTEGER NOT NULL,
  "bot_idle_reset_hours" INTEGER NOT NULL,
  "kitchen_closed_window" JSON_TEXT NOT NULL,
  "owner_phones" JSON_TEXT NOT NULL,
  "preset_data" JSON_TEXT NOT NULL,
  "preset_name" TEXT NOT NULL,
  "home_sections" JSON_TEXT NOT NULL,
  "storefront_design" JSON_TEXT NOT NULL,
  "checkout_settings" JSON_TEXT NOT NULL,
  CHECK ((bot_idle_reset_hours >= 0)),
  UNIQUE (tenant_id),
  FOREIGN KEY (tenant_id) REFERENCES tenancy_tenant(id) DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE IF NOT EXISTS "tenancy_tenantdomain" (
  "id" INTEGER PRIMARY KEY AUTOINCREMENT,
  "hostname" TEXT NOT NULL,
  "is_primary" BOOLEAN NOT NULL,
  "tenant_id" INTEGER NOT NULL,
  UNIQUE (hostname),
  FOREIGN KEY (tenant_id) REFERENCES tenancy_tenant(id) DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE IF NOT EXISTS "tenancy_tenantsecrets" (
  "id" INTEGER PRIMARY KEY AUTOINCREMENT,
  "wa_provider" TEXT NOT NULL,
  "wa_phone_number_id" TEXT NOT NULL,
  "wa_waba_id" TEXT NOT NULL,
  "wa_verify_token" TEXT NOT NULL,
  "wa_token_enc" TEXT NOT NULL,
  "wa_app_secret_enc" TEXT NOT NULL,
  "n8n_send_url" TEXT NOT NULL,
  "n8n_auth_token_enc" TEXT NOT NULL,
  "razorpay_key_id" TEXT NOT NULL,
  "razorpay_secret_enc" TEXT NOT NULL,
  "rzp_webhook_secret_enc" TEXT NOT NULL,
  "razorpay_live_mode" BOOLEAN NOT NULL,
  "tenant_id" INTEGER NOT NULL,
  "wa_sync_token_enc" TEXT NOT NULL,
  "n8n_receive_url" TEXT NOT NULL,
  UNIQUE (tenant_id),
  FOREIGN KEY (tenant_id) REFERENCES tenancy_tenant(id) DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE IF NOT EXISTS "tenancy_tenantuser" (
  "id" INTEGER PRIMARY KEY AUTOINCREMENT,
  "role" TEXT NOT NULL,
  "created_at" TIMESTAMP NOT NULL,
  "tenant_id" INTEGER NOT NULL,
  "user_id" INTEGER NOT NULL,
  UNIQUE (tenant_id, user_id),
  FOREIGN KEY (tenant_id) REFERENCES tenancy_tenant(id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (user_id) REFERENCES auth_user(id) DEFERRABLE INITIALLY DEFERRED
);

CREATE UNIQUE INDEX IF NOT EXISTS auth_group_name_key ON auth_group (name);

CREATE UNIQUE INDEX IF NOT EXISTS auth_group_permissions_group_id_permission_id_0cd325b0_uniq ON auth_group_permissions (group_id, permission_id);

CREATE UNIQUE INDEX IF NOT EXISTS auth_permission_content_type_id_codename_01ab375a_uniq ON auth_permission (content_type_id, codename);

CREATE UNIQUE INDEX IF NOT EXISTS auth_user_groups_user_id_group_id_94350c0c_uniq ON auth_user_groups (user_id, group_id);

CREATE UNIQUE INDEX IF NOT EXISTS auth_user_user_permissions_user_id_permission_id_14a6b632_uniq ON auth_user_user_permissions (user_id, permission_id);

CREATE UNIQUE INDEX IF NOT EXISTS auth_user_username_key ON auth_user (username);

CREATE UNIQUE INDEX IF NOT EXISTS django_content_type_app_label_model_76bd3d3b_uniq ON django_content_type (app_label, model);

CREATE UNIQUE INDEX IF NOT EXISTS messaging_whatsappmessage_outbound_id_key ON messaging_whatsappmessage (outbound_id);

CREATE UNIQUE INDEX IF NOT EXISTS orders_couriercharge_order_id_key ON orders_couriercharge (order_id);

CREATE UNIQUE INDEX IF NOT EXISTS payments_paymentintent_order_id_key ON payments_paymentintent (order_id);

CREATE UNIQUE INDEX IF NOT EXISTS tenancy_billingprofile_tenant_id_key ON tenancy_billingprofile (tenant_id);

CREATE UNIQUE INDEX IF NOT EXISTS tenancy_customdomain_hostname_key ON tenancy_customdomain (hostname);

CREATE UNIQUE INDEX IF NOT EXISTS tenancy_customdomain_mapping_id_key ON tenancy_customdomain (mapping_id);

CREATE UNIQUE INDEX IF NOT EXISTS tenancy_ownerinvitation_token_hash_key ON tenancy_ownerinvitation (token_hash);

CREATE UNIQUE INDEX IF NOT EXISTS tenancy_tenant_slug_key ON tenancy_tenant (slug);

CREATE UNIQUE INDEX IF NOT EXISTS tenancy_tenantconfig_tenant_id_key ON tenancy_tenantconfig (tenant_id);

CREATE UNIQUE INDEX IF NOT EXISTS tenancy_tenantdomain_hostname_key ON tenancy_tenantdomain (hostname);

CREATE UNIQUE INDEX IF NOT EXISTS tenancy_tenantsecrets_tenant_id_key ON tenancy_tenantsecrets (tenant_id);

CREATE UNIQUE INDEX IF NOT EXISTS uniq_courier_payment_mode ON payments_courierpayment (tenant_id, charge_id, mode);

CREATE UNIQUE INDEX IF NOT EXISTS uniq_invoice_sequence_fy ON billing_invoicesequence (tenant_id, series, financial_year);

CREATE UNIQUE INDEX IF NOT EXISTS uniq_kitchen_daily_run ON jobs_dailykitchenrun (tenant_id, local_date);

CREATE UNIQUE INDEX IF NOT EXISTS uniq_menu_day ON catalog_menuday (tenant_id, slot_id, on_date);

CREATE UNIQUE INDEX IF NOT EXISTS uniq_rzp_event ON payments_paymentevent (tenant_id, mode, event_id);

CREATE UNIQUE INDEX IF NOT EXISTS uniq_rzp_mode ON payments_razorpayconnection (tenant_id, mode);

CREATE UNIQUE INDEX IF NOT EXISTS uniq_tenant_customer_phone ON orders_customer (tenant_id, phone);

CREATE UNIQUE INDEX IF NOT EXISTS uniq_tenant_invoice_number ON billing_invoice (tenant_id, number);

CREATE UNIQUE INDEX IF NOT EXISTS uniq_tenant_invoice_sequence_value ON billing_invoice (tenant_id, series, financial_year, sequence_no);

CREATE UNIQUE INDEX IF NOT EXISTS uniq_tenant_order_no ON orders_order (tenant_id, order_no);

CREATE UNIQUE INDEX IF NOT EXISTS uniq_tenant_page_slug ON content_page (tenant_id, slug);

CREATE UNIQUE INDEX IF NOT EXISTS uniq_tenant_retailer_id ON catalog_menuitem (tenant_id, retailer_id);

CREATE UNIQUE INDEX IF NOT EXISTS uniq_tenant_slot_key ON catalog_slot (tenant_id, key);

CREATE UNIQUE INDEX IF NOT EXISTS uniq_tenant_user ON tenancy_tenantuser (tenant_id, user_id);

CREATE UNIQUE INDEX IF NOT EXISTS uniq_wa_conversation_phone ON messaging_whatsappconversation (tenant_id, phone);

CREATE UNIQUE INDEX IF NOT EXISTS uniq_wa_forward_event ON messaging_whatsappforwardevent (tenant_id, digest);

CREATE UNIQUE INDEX IF NOT EXISTS uniq_wa_message_receipt ON messaging_whatsappreceipt (tenant_id, provider_message_id, status);

CREATE UNIQUE INDEX IF NOT EXISTS uniq_zone_pincode_area ON delivery_deliveryzone (tenant_id, pincode, area_name);

CREATE UNIQUE INDEX IF NOT EXISTS unique_catalog_sync_version ON catalog_catalogsyncrun (tenant_id, version);

CREATE UNIQUE INDEX IF NOT EXISTS unique_rate_limit_window ON operations_ratelimitbucket (tenant_id, key, window_start);

CREATE UNIQUE INDEX IF NOT EXISTS unique_worker_pulse ON operations_workerpulse (tenant_id, name);

CREATE INDEX IF NOT EXISTS auth_group_permissions_group_id_b120cbf9 ON auth_group_permissions (group_id);

CREATE INDEX IF NOT EXISTS auth_group_permissions_permission_id_84c5c92e ON auth_group_permissions (permission_id);

CREATE INDEX IF NOT EXISTS auth_permission_content_type_id_2f476e4b ON auth_permission (content_type_id);

CREATE INDEX IF NOT EXISTS auth_user_groups_group_id_97559544 ON auth_user_groups (group_id);

CREATE INDEX IF NOT EXISTS auth_user_groups_user_id_6a12ed8b ON auth_user_groups (user_id);

CREATE INDEX IF NOT EXISTS auth_user_user_permissions_permission_id_1fbb5f2c ON auth_user_user_permissions (permission_id);

CREATE INDEX IF NOT EXISTS auth_user_user_permissions_user_id_a95ead1b ON auth_user_user_permissions (user_id);

CREATE INDEX IF NOT EXISTS billing_invoice_order_id_2948c8f7 ON billing_invoice (order_id);

CREATE INDEX IF NOT EXISTS billing_invoice_original_id_86a9f2ce ON billing_invoice (original_id);

CREATE INDEX IF NOT EXISTS billing_invoice_tenant_id_0888f9df ON billing_invoice (tenant_id);

CREATE INDEX IF NOT EXISTS billing_invoicerequest_created_at_70487c71 ON billing_invoicerequest (created_at);

CREATE INDEX IF NOT EXISTS billing_invoicerequest_customer_id_06a0d4a4 ON billing_invoicerequest (customer_id);

CREATE INDEX IF NOT EXISTS billing_invoicerequest_invoice_id_802717f7 ON billing_invoicerequest (invoice_id);

CREATE INDEX IF NOT EXISTS billing_invoicerequest_order_id_31dc9088 ON billing_invoicerequest (order_id);

CREATE INDEX IF NOT EXISTS billing_invoicerequest_phone_125c5fc7 ON billing_invoicerequest (phone);

CREATE INDEX IF NOT EXISTS billing_invoicerequest_status_71e7476c ON billing_invoicerequest (status);

CREATE INDEX IF NOT EXISTS billing_invoicerequest_tenant_id_7fe47dad ON billing_invoicerequest (tenant_id);

CREATE INDEX IF NOT EXISTS billing_invoicesequence_tenant_id_2ee0d973 ON billing_invoicesequence (tenant_id);

CREATE INDEX IF NOT EXISTS catalog_catalogsyncrun_tenant_id_3e10cfee ON catalog_catalogsyncrun (tenant_id);

CREATE INDEX IF NOT EXISTS catalog_menucategory_parent_id_36eafa4a ON catalog_menucategory (parent_id);

CREATE INDEX IF NOT EXISTS catalog_menucategory_slug_f96c0a2a ON catalog_menucategory (slug);

CREATE INDEX IF NOT EXISTS catalog_menucategory_tenant_id_9b0be947 ON catalog_menucategory (tenant_id);

CREATE INDEX IF NOT EXISTS catalog_menuday_slot_id_6fb4ee8d ON catalog_menuday (slot_id);

CREATE INDEX IF NOT EXISTS catalog_menuday_tenant_id_62dce57b ON catalog_menuday (tenant_id);

CREATE INDEX IF NOT EXISTS catalog_menuitem_category_id_2298ca03 ON catalog_menuitem (category_id);

CREATE INDEX IF NOT EXISTS catalog_menuitem_tenant_id_7d9de300 ON catalog_menuitem (tenant_id);

CREATE INDEX IF NOT EXISTS catalog_menuschedule_item_id_b6830f74 ON catalog_menuschedule (item_id);

CREATE INDEX IF NOT EXISTS catalog_menuschedule_slot_id_0cc815f4 ON catalog_menuschedule (slot_id);

CREATE INDEX IF NOT EXISTS catalog_menuschedule_tenant_id_18ea9e81 ON catalog_menuschedule (tenant_id);

CREATE INDEX IF NOT EXISTS catalog_slot_key_c11c8a4d ON catalog_slot (key);

CREATE INDEX IF NOT EXISTS catalog_slot_tenant_id_607a04c4 ON catalog_slot (tenant_id);

CREATE INDEX IF NOT EXISTS content_banner_tenant_id_f8f9f148 ON content_banner (tenant_id);

CREATE INDEX IF NOT EXISTS content_page_slug_d48c800c ON content_page (slug);

CREATE INDEX IF NOT EXISTS content_page_tenant_id_9357010a ON content_page (tenant_id);

CREATE INDEX IF NOT EXISTS content_storefrontimage_tenant_id_f432ef07 ON content_storefrontimage (tenant_id);

CREATE INDEX IF NOT EXISTS delivery_deliveryzone_pincode_88e29d32 ON delivery_deliveryzone (pincode);

CREATE INDEX IF NOT EXISTS delivery_deliveryzone_tenant_id_28d93b04 ON delivery_deliveryzone (tenant_id);

CREATE INDEX IF NOT EXISTS django_admin_log_content_type_id_c4bce8eb ON django_admin_log (content_type_id);

CREATE INDEX IF NOT EXISTS django_admin_log_user_id_c564eba6 ON django_admin_log (user_id);

CREATE INDEX IF NOT EXISTS django_session_expire_date_a5c62663 ON django_session (expire_date);

CREATE INDEX IF NOT EXISTS idx_order_recent ON orders_order (tenant_id, placed_at DESC);

CREATE INDEX IF NOT EXISTS idx_order_service ON orders_order (tenant_id, delivery_date, slot_id);

CREATE INDEX IF NOT EXISTS idx_outbound_due ON messaging_outboundmessage (status, next_attempt_at);

CREATE INDEX IF NOT EXISTS idx_wa_conversation_time ON messaging_whatsappmessage (tenant_id, conversation_id, occurred_at);

CREATE INDEX IF NOT EXISTS jobs_dailykitchenrun_tenant_id_4af8706b ON jobs_dailykitchenrun (tenant_id);

CREATE INDEX IF NOT EXISTS messaging_outboundmessage_next_attempt_at_ab2dafd4 ON messaging_outboundmessage (next_attempt_at);

CREATE INDEX IF NOT EXISTS messaging_outboundmessage_status_9ba08cb9 ON messaging_outboundmessage (status);

CREATE INDEX IF NOT EXISTS messaging_outboundmessage_tenant_id_76b91991 ON messaging_outboundmessage (tenant_id);

CREATE INDEX IF NOT EXISTS messaging_outboundmessage_to_phone_4054fc74 ON messaging_outboundmessage (to_phone);

CREATE INDEX IF NOT EXISTS messaging_whatsappconversation_last_message_at_26ad05a1 ON messaging_whatsappconversation (last_message_at);

CREATE INDEX IF NOT EXISTS messaging_whatsappconversation_tenant_id_66edfe46 ON messaging_whatsappconversation (tenant_id);

CREATE INDEX IF NOT EXISTS messaging_whatsappforwardevent_status_67e40780 ON messaging_whatsappforwardevent (status);

CREATE INDEX IF NOT EXISTS messaging_whatsappforwardevent_tenant_id_04dbef17 ON messaging_whatsappforwardevent (tenant_id);

CREATE INDEX IF NOT EXISTS messaging_whatsappmessage_conversation_id_23391755 ON messaging_whatsappmessage (conversation_id);

CREATE INDEX IF NOT EXISTS messaging_whatsappmessage_tenant_id_88c017a2 ON messaging_whatsappmessage (tenant_id);

CREATE INDEX IF NOT EXISTS messaging_whatsappreceipt_tenant_id_3b71f677 ON messaging_whatsappreceipt (tenant_id);

CREATE INDEX IF NOT EXISTS operations_ratelimitbucket_expires_at_7ca9fce4 ON operations_ratelimitbucket (expires_at);

CREATE INDEX IF NOT EXISTS operations_ratelimitbucket_tenant_id_fd0732c8 ON operations_ratelimitbucket (tenant_id);

CREATE INDEX IF NOT EXISTS operations_workerpulse_tenant_id_cf546887 ON operations_workerpulse (tenant_id);

CREATE INDEX IF NOT EXISTS orders_address_customer_id_b8a7cdae ON orders_address (customer_id);

CREATE INDEX IF NOT EXISTS orders_address_tenant_id_8ef17553 ON orders_address (tenant_id);

CREATE INDEX IF NOT EXISTS orders_address_zone_id_d4fbf01b ON orders_address (zone_id);

CREATE INDEX IF NOT EXISTS orders_couriercharge_tenant_id_1fb96294 ON orders_couriercharge (tenant_id);

CREATE INDEX IF NOT EXISTS orders_customer_phone_853b078c ON orders_customer (phone);

CREATE INDEX IF NOT EXISTS orders_customer_tenant_id_d6b567bb ON orders_customer (tenant_id);

CREATE INDEX IF NOT EXISTS orders_order_customer_id_0b76f6a4 ON orders_order (customer_id);

CREATE INDEX IF NOT EXISTS orders_order_delivery_date_61fa62d1 ON orders_order (delivery_date);

CREATE INDEX IF NOT EXISTS orders_order_order_no_ac790d02 ON orders_order (order_no);

CREATE INDEX IF NOT EXISTS orders_order_payment_status_d9b0ddfc ON orders_order (payment_status);

CREATE INDEX IF NOT EXISTS orders_order_slot_id_258459b2 ON orders_order (slot_id);

CREATE INDEX IF NOT EXISTS orders_order_status_445594e5 ON orders_order (status);

CREATE INDEX IF NOT EXISTS orders_order_tenant_id_36ad426c ON orders_order (tenant_id);

CREATE INDEX IF NOT EXISTS orders_orderevent_order_id_b26297f3 ON orders_orderevent (order_id);

CREATE INDEX IF NOT EXISTS orders_orderevent_tenant_id_9d0acdb2 ON orders_orderevent (tenant_id);

CREATE INDEX IF NOT EXISTS payments_courierpayment_charge_id_d9e228dd ON payments_courierpayment (charge_id);

CREATE INDEX IF NOT EXISTS payments_courierpayment_connection_id_095d6116 ON payments_courierpayment (connection_id);

CREATE INDEX IF NOT EXISTS payments_courierpayment_tenant_id_87320e17 ON payments_courierpayment (tenant_id);

CREATE INDEX IF NOT EXISTS payments_paymentevent_tenant_id_d967b16c ON payments_paymentevent (tenant_id);

CREATE INDEX IF NOT EXISTS payments_paymentintent_connection_id_5d24e260 ON payments_paymentintent (connection_id);

CREATE INDEX IF NOT EXISTS payments_paymentintent_credit_note_id_3e6b7b29 ON payments_paymentintent (credit_note_id);

CREATE INDEX IF NOT EXISTS payments_paymentintent_tenant_id_9c6e13d7 ON payments_paymentintent (tenant_id);

CREATE INDEX IF NOT EXISTS payments_razorpayconnection_tenant_id_5001cc39 ON payments_razorpayconnection (tenant_id);

CREATE INDEX IF NOT EXISTS payments_refund_intent_id_0fcc71c9 ON payments_refund (intent_id);

CREATE INDEX IF NOT EXISTS payments_refund_tenant_id_88619fac ON payments_refund (tenant_id);

CREATE INDEX IF NOT EXISTS tenancy_customdomain_tenant_id_71922daa ON tenancy_customdomain (tenant_id);

CREATE INDEX IF NOT EXISTS tenancy_ownerinvitation_tenant_id_bc570f1f ON tenancy_ownerinvitation (tenant_id);

CREATE INDEX IF NOT EXISTS tenancy_ownerinvitation_user_id_7c49006c ON tenancy_ownerinvitation (user_id);

CREATE INDEX IF NOT EXISTS tenancy_platformauditevent_actor_id_5bebac6f ON tenancy_platformauditevent (actor_id);

CREATE INDEX IF NOT EXISTS tenancy_platformauditevent_tenant_id_ffb8d43e ON tenancy_platformauditevent (tenant_id);

CREATE INDEX IF NOT EXISTS tenancy_tenantdomain_tenant_id_bc59a9d0 ON tenancy_tenantdomain (tenant_id);

CREATE INDEX IF NOT EXISTS tenancy_tenantuser_tenant_id_f9502d60 ON tenancy_tenantuser (tenant_id);

CREATE INDEX IF NOT EXISTS tenancy_tenantuser_user_id_ce1e809a ON tenancy_tenantuser (user_id);

CREATE UNIQUE INDEX IF NOT EXISTS uniq_courier_provider_order ON payments_courierpayment (tenant_id, provider_order_id) WHERE (NOT ((provider_order_id) = ''));

CREATE UNIQUE INDEX IF NOT EXISTS uniq_courier_provider_payment ON payments_courierpayment (tenant_id, payment_id) WHERE (NOT ((payment_id) = ''));

CREATE UNIQUE INDEX IF NOT EXISTS uniq_dated_schedule_row ON catalog_menuschedule (tenant_id, item_id, slot_id, on_date) WHERE ((mode) = 'date');

CREATE UNIQUE INDEX IF NOT EXISTS uniq_outbound_dedupe_key ON messaging_outboundmessage (tenant_id, dedupe_key) WHERE (NOT ((dedupe_key) = ''));

CREATE UNIQUE INDEX IF NOT EXISTS php_courier_provider_payment ON payments_courierpayment (tenant_id, payment_id) WHERE ((payment_id) <> '');

CREATE UNIQUE INDEX IF NOT EXISTS uniq_primary_invoice_per_order ON billing_invoice (tenant_id, order_id) WHERE ((order_id IS NOT NULL) AND (NOT ((kind) = 'credit_note')));

CREATE UNIQUE INDEX IF NOT EXISTS uniq_rzp_active ON payments_razorpayconnection (tenant_id) WHERE enabled;

CREATE UNIQUE INDEX IF NOT EXISTS uniq_rzp_active_refund ON payments_refund (tenant_id, intent_id) WHERE (NOT ((state) = 'failed'));

CREATE UNIQUE INDEX IF NOT EXISTS uniq_rzp_capture ON payments_paymentintent (tenant_id, payment_id) WHERE (NOT ((payment_id) = ''));

CREATE UNIQUE INDEX IF NOT EXISTS uniq_rzp_order ON payments_paymentintent (tenant_id, provider_order_id) WHERE (NOT ((provider_order_id) = ''));

CREATE UNIQUE INDEX IF NOT EXISTS uniq_tenant_category_slug ON catalog_menucategory (tenant_id, slug) WHERE (NOT ((slug) = ''));

CREATE UNIQUE INDEX IF NOT EXISTS uniq_tenant_order_external_ref ON orders_order (tenant_id, external_ref) WHERE (NOT ((external_ref) = ''));

CREATE UNIQUE INDEX IF NOT EXISTS uniq_wa_message_provider_id ON messaging_whatsappmessage (tenant_id, provider_message_id) WHERE (NOT ((provider_message_id) = ''));

CREATE UNIQUE INDEX IF NOT EXISTS uniq_weekly_schedule_row ON catalog_menuschedule (tenant_id, item_id, slot_id, weekday) WHERE ((mode) = 'weekday');

CREATE INDEX IF NOT EXISTS php_login_attempt_scope ON php_login_attempt (tenant_id, fingerprint, attempted_at);

CREATE INDEX IF NOT EXISTS php_rate_expiry ON operations_ratelimitbucket (expires_at);

CREATE UNIQUE INDEX IF NOT EXISTS php_courier_provider_order ON payments_courierpayment (tenant_id, provider_order_id) WHERE ((provider_order_id) <> '');

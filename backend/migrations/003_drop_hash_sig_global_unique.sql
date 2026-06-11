-- hash_sig was globally unique before multi-customer ingest.
-- Uniqueness is now scoped to (customer_id, hash_sig).
DROP INDEX IF EXISTS ix_activities_hash_sig;

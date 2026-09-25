-- ============================================================
-- NexStore VAULT — Supabase PostgreSQL Schema Script
-- Paste this script into your Supabase Dashboard -> SQL Editor -> Run
-- ============================================================

-- 1. Storage Nodes Table
CREATE TABLE IF NOT EXISTS vault_nodes (
    node_id TEXT PRIMARY KEY,
    status TEXT NOT NULL DEFAULT 'ONLINE',
    capacity BIGINT NOT NULL,
    used_capacity BIGINT NOT NULL DEFAULT 0,
    object_count INTEGER NOT NULL DEFAULT 0,
    last_heartbeat TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    network_status TEXT NOT NULL DEFAULT 'CONNECTED',
    health_status TEXT NOT NULL DEFAULT 'HEALTHY',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 2. Objects Metadata Table
CREATE TABLE IF NOT EXISTS vault_objects (
    object_id TEXT PRIMARY KEY,
    filename TEXT NOT NULL,
    size BIGINT NOT NULL,
    content_type TEXT NOT NULL,
    checksum TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    replication_factor INTEGER NOT NULL DEFAULT 3,
    status TEXT NOT NULL DEFAULT 'HEALTHY',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 3. Replicas Metadata Table
CREATE TABLE IF NOT EXISTS vault_replicas (
    replica_id TEXT PRIMARY KEY,
    object_id TEXT NOT NULL REFERENCES vault_objects(object_id) ON DELETE CASCADE,
    node_id TEXT NOT NULL REFERENCES vault_nodes(node_id),
    checksum TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    status TEXT NOT NULL DEFAULT 'HEALTHY',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_vault_replicas_obj ON vault_replicas(object_id);
CREATE INDEX IF NOT EXISTS idx_vault_replicas_node ON vault_replicas(node_id);

-- 4. Repair Jobs Table
CREATE TABLE IF NOT EXISTS vault_repair_jobs (
    repair_id TEXT PRIMARY KEY,
    object_id TEXT NOT NULL,
    source_node_id TEXT,
    failed_node_id TEXT,
    target_node_id TEXT,
    reason TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'QUEUED',
    progress INTEGER NOT NULL DEFAULT 0,
    started_at TIMESTAMPTZ DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    duration_ms INTEGER,
    error_message TEXT
);

-- 5. Activity Event Logs Table
CREATE TABLE IF NOT EXISTS vault_activity_logs (
    event_id BIGSERIAL PRIMARY KEY,
    event_type TEXT NOT NULL,
    message TEXT NOT NULL,
    object_id TEXT,
    node_id TEXT,
    severity TEXT NOT NULL DEFAULT 'INFO',
    details TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Enable Row Level Security (RLS) and permit anon access for prototype demo
ALTER TABLE vault_nodes ENABLE ROW LEVEL SECURITY;
ALTER TABLE vault_objects ENABLE ROW LEVEL SECURITY;
ALTER TABLE vault_replicas ENABLE ROW LEVEL SECURITY;
ALTER TABLE vault_repair_jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE vault_activity_logs ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Allow public read access to nodes" ON vault_nodes FOR ALL USING (true);
CREATE POLICY "Allow public read access to objects" ON vault_objects FOR ALL USING (true);
CREATE POLICY "Allow public read access to replicas" ON vault_replicas FOR ALL USING (true);
CREATE POLICY "Allow public read access to repairs" ON vault_repair_jobs FOR ALL USING (true);
CREATE POLICY "Allow public read access to activity" ON vault_activity_logs FOR ALL USING (true);

-- 6. Supabase Storage Bucket for Physical File Objects
INSERT INTO storage.buckets (id, name, public)
VALUES ('vault-objects', 'vault-objects', true)
ON CONFLICT (id) DO UPDATE SET public = true;

CREATE POLICY "Allow public select from vault-objects"
ON storage.objects FOR SELECT
USING (bucket_id = 'vault-objects');

CREATE POLICY "Allow public insert into vault-objects"
ON storage.objects FOR INSERT
WITH CHECK (bucket_id = 'vault-objects');

CREATE POLICY "Allow public update on vault-objects"
ON storage.objects FOR UPDATE
USING (bucket_id = 'vault-objects');

CREATE POLICY "Allow public delete from vault-objects"
ON storage.objects FOR DELETE
USING (bucket_id = 'vault-objects');

-- RFP Approval — Part 3
-- Adds columns and tables needed for the human-in-the-loop approval pipeline.
-- Run after 005 and after the SQLModel create_all has been applied.

-- Add approval columns to rfp_department_sections (idempotent via IF NOT EXISTS)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'rfp_department_sections' AND column_name = 'approval_status'
    ) THEN
        ALTER TABLE rfp_department_sections
            ADD COLUMN approval_status VARCHAR(32) NOT NULL DEFAULT 'pending',
            ADD COLUMN approved_by VARCHAR(255),
            ADD COLUMN approved_at TIMESTAMP WITH TIME ZONE;
    END IF;
END $$;

-- Final document table
CREATE TABLE IF NOT EXISTS rfp_final_documents (
    id SERIAL PRIMARY KEY,
    ticket_id VARCHAR(50) NOT NULL REFERENCES rfp_tickets(ticket_id) ON DELETE CASCADE,
    document_type VARCHAR(100),
    content TEXT,
    file_path VARCHAR(500),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_final_doc_ticket ON rfp_final_documents(ticket_id);

-- Durable, queryable approval/arbitration audit events.
CREATE TABLE IF NOT EXISTS rfp_approval_traces (
    id SERIAL PRIMARY KEY,
    ticket_id VARCHAR(50) NOT NULL REFERENCES rfp_tickets(ticket_id) ON DELETE CASCADE,
    department_id VARCHAR(100),
    agent VARCHAR(255) NOT NULL,
    input_data JSONB NOT NULL DEFAULT '{}'::jsonb,
    output_data JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_rfp_approval_trace_ticket
    ON rfp_approval_traces(ticket_id, id);

-- Langgraph checkpoint tables (required by langgraph-checkpoint-postgres)
-- These are created automatically by PostgresSaver.setup() but we include
-- them here for explicit schema management.

CREATE TABLE IF NOT EXISTS langgraph_checkpoints (
    thread_id TEXT NOT NULL,
    checkpoint_ns TEXT NOT NULL DEFAULT '',
    checkpoint_id TEXT NOT NULL,
    parent_checkpoint_id TEXT,
    type TEXT,
    checkpoint JSONB,
    metadata JSONB,
    PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id)
);

CREATE TABLE IF NOT EXISTS langgraph_checkpoint_writes (
    thread_id TEXT NOT NULL,
    checkpoint_ns TEXT NOT NULL DEFAULT '',
    checkpoint_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    idx INTEGER NOT NULL,
    channel TEXT NOT NULL,
    type TEXT,
    value JSONB,
    PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id, task_id, idx)
);

CREATE TABLE IF NOT EXISTS langgraph_checkpoint_blobs (
    blob_hash TEXT PRIMARY KEY,
    blob BYTEA
);

-- Run in Supabase SQL Editor
create extension if not exists vector;

-- Run this second part after backend bootstraps tables at least once.
create index if not exists idx_brand_manual_chunks_embedding
on brand_manual_chunks
using ivfflat (embedding vector_cosine_ops)
with (lists = 100);

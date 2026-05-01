-- BAAI/bge-m3 produces 1024-dimensional dense vectors.
-- Previous schema used vector(1536) (e.g. OpenAI-style), causing insert failures and rejected versions.

TRUNCATE TABLE chunk_embeddings;

ALTER TABLE chunk_embeddings
    ALTER COLUMN embedding TYPE vector(1024);

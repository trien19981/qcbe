-- Add similarity_score to diff_changes for semantic diff results
ALTER TABLE diff_changes ADD COLUMN IF NOT EXISTS similarity_score FLOAT;

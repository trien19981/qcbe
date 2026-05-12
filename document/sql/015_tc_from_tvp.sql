-- Step 3: testcases reference TVP làm input chính + technique tagging.

ALTER TABLE testcases
  ADD COLUMN IF NOT EXISTS source_tvp_id UUID REFERENCES test_viewpoints(id) ON DELETE SET NULL;

ALTER TABLE testcases
  ADD COLUMN IF NOT EXISTS technique TEXT;

ALTER TABLE testcases
  ADD COLUMN IF NOT EXISTS source_tvp_section TEXT;

CREATE INDEX IF NOT EXISTS idx_testcases_source_tvp ON testcases(source_tvp_id);
CREATE INDEX IF NOT EXISTS idx_testcases_technique ON testcases(project_id, technique);

ALTER TABLE tc_generate_jobs
  ADD COLUMN IF NOT EXISTS tvp_id UUID REFERENCES test_viewpoints(id) ON DELETE SET NULL;

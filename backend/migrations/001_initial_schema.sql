CREATE INDEX IF NOT EXISTS ix_activities_started_at ON activities (started_at);
CREATE INDEX IF NOT EXISTS ix_activities_match_status ON activities (match_status);
CREATE INDEX IF NOT EXISTS ix_segment_stats_total_traversals ON segment_stats (total_traversals);
CREATE INDEX IF NOT EXISTS ix_segment_stats_unique_activities ON segment_stats (unique_activities);

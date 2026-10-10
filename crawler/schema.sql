CREATE TABLE IF NOT EXISTS jobs (
    id text PRIMARY KEY,
    source text NOT NULL CHECK (source IN ('indeed', 'linkedin', 'reed')),
    source_job_id text NOT NULL CHECK (source_job_id <> ''),
    url text NOT NULL,
    title text NOT NULL,
    company text,
    company_logo_url text,
    location text NOT NULL,
    work_type text CHECK (work_type IN ('full time', 'part time', 'contract', 'temporary')),
    salary_min numeric,
    salary_max numeric,
    salary_period text CHECK (salary_period IN ('year', 'day', 'hour')),
    posted_at timestamptz,
    description text NOT NULL,
    canonical_job_id text NOT NULL,
    content_hash text NOT NULL,
    first_seen_at timestamptz NOT NULL,
    last_seen_at timestamptz NOT NULL,
    removed_at timestamptz,
    UNIQUE (source, source_job_id),
    CHECK (id = source || ':' || source_job_id),
    CHECK (last_seen_at >= first_seen_at),
    CHECK (salary_min IS NULL OR salary_max IS NULL OR salary_min <= salary_max)
);

CREATE TABLE IF NOT EXISTS listing_state (
    job_id text PRIMARY KEY REFERENCES jobs(id),
    last_detail_refresh_at timestamptz NOT NULL
);

CREATE INDEX IF NOT EXISTS jobs_live_source_idx ON jobs(source) WHERE removed_at IS NULL;
CREATE INDEX IF NOT EXISTS jobs_canonical_idx ON jobs(canonical_job_id);

CREATE TABLE IF NOT EXISTS listing_exclusions (
    source text NOT NULL,
    source_job_id text NOT NULL,
    checked_at timestamptz NOT NULL,
    reason text NOT NULL,
    PRIMARY KEY (source, source_job_id)
);

CREATE TABLE IF NOT EXISTS canonical_groups (
    id text PRIMARY KEY,
    created_order bigserial UNIQUE NOT NULL,
    created_at timestamptz NOT NULL
);

CREATE TABLE IF NOT EXISTS dedupe_features (
    job_id text PRIMARY KEY REFERENCES jobs(id),
    content_hash text NOT NULL,
    rule_version integer NOT NULL,
    company_key text,
    role_family text NOT NULL,
    location_key text NOT NULL,
    profile jsonb NOT NULL
);
CREATE INDEX IF NOT EXISTS dedupe_candidate_idx ON dedupe_features(company_key, role_family, location_key);
ALTER TABLE dedupe_features ADD COLUMN IF NOT EXISTS legal_employer_key text;
ALTER TABLE dedupe_features ADD COLUMN IF NOT EXISTS evidence_hash text NOT NULL DEFAULT '';
CREATE INDEX IF NOT EXISTS dedupe_legal_candidate_idx ON dedupe_features(legal_employer_key, role_family, location_key);

CREATE TABLE IF NOT EXISTS listing_match_evidence (
    job_id text PRIMARY KEY REFERENCES jobs(id),
    content_hash text NOT NULL,
    kind text NOT NULL CHECK (kind = 'jsonld_employer_reference'),
    issuer text NOT NULL,
    reference text NOT NULL
);

CREATE TABLE IF NOT EXISTS dedupe_evidence (
    left_id text NOT NULL REFERENCES jobs(id),
    right_id text NOT NULL REFERENCES jobs(id),
    left_hash text NOT NULL,
    right_hash text NOT NULL,
    rule_version integer NOT NULL,
    reason text NOT NULL,
    scores jsonb NOT NULL,
    PRIMARY KEY (left_id, right_id),
    CHECK (left_id < right_id)
);

CREATE TABLE IF NOT EXISTS pending_candidates (
    source text NOT NULL CHECK (source IN ('indeed', 'linkedin', 'reed')),
    source_job_id text NOT NULL,
    url text NOT NULL,
    posted_at timestamptz,
    first_discovered_at timestamptz NOT NULL,
    last_discovered_at timestamptz NOT NULL,
    last_attempt_at timestamptz,
    attempts integer NOT NULL DEFAULT 0,
    force_detail boolean NOT NULL DEFAULT false,
    PRIMARY KEY (source, source_job_id)
);
CREATE INDEX IF NOT EXISTS pending_candidates_schedule_idx
    ON pending_candidates(source, last_attempt_at, first_discovered_at);

CREATE TABLE IF NOT EXISTS crawl_progress (
    source text PRIMARY KEY CHECK (source IN ('indeed', 'linkedin', 'reed')),
    cycle_id uuid NOT NULL,
    plan_hash text NOT NULL,
    started_at timestamptz NOT NULL,
    completed_at timestamptz,
    auth_limited boolean NOT NULL DEFAULT false
);

CREATE TABLE IF NOT EXISTS discovery_checkpoints (
    source text NOT NULL REFERENCES crawl_progress(source),
    query text NOT NULL,
    location text NOT NULL,
    cycle_id uuid NOT NULL,
    state jsonb NOT NULL,
    updated_at timestamptz NOT NULL,
    PRIMARY KEY (source, query, location)
);

CREATE TABLE IF NOT EXISTS listing_quarantine (
    job_id text PRIMARY KEY,
    reason text NOT NULL,
    evidence_capture text NOT NULL,
    snapshot jsonb NOT NULL,
    quarantined_at timestamptz NOT NULL
);

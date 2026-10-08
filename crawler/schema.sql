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

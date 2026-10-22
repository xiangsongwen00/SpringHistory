CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE SCHEMA IF NOT EXISTS history;
CREATE TABLE IF NOT EXISTS history.import_runs (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 input_file text NOT NULL, input_sha256 text NOT NULL,
 started_at timestamptz NOT NULL DEFAULT now(), completed_at timestamptz,
 status text NOT NULL CHECK(status IN ('running','succeeded','failed')),
 record_count integer NOT NULL DEFAULT 0, error text
);
CREATE TABLE IF NOT EXISTS history.books (
 book_id text PRIMARY KEY, title text NOT NULL,
 updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS history.chapters (
 chapter_id text PRIMARY KEY, book_id text NOT NULL REFERENCES history.books(book_id),
 chapter_index integer NOT NULL CHECK(chapter_index>=0), title text NOT NULL,
 source_file text NOT NULL, source_sha256 text NOT NULL CHECK(source_sha256 ~ '^[a-f0-9]{64}$'),
 decoder text NOT NULL, verification_status text NOT NULL
   CHECK(verification_status IN ('decoded_unverified','verified_sample','metadata_only')),
 original_text text, normalized_text text,
 normalization_version text NOT NULL DEFAULT 'nfkc-v1',
 metadata jsonb NOT NULL DEFAULT '{}',
 import_run_id bigint NOT NULL REFERENCES history.import_runs(id),
 updated_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(book_id,chapter_index),
 CHECK((verification_status='metadata_only' AND original_text IS NULL AND normalized_text IS NULL)
    OR (verification_status<>'metadata_only' AND length(original_text)>0 AND normalized_text IS NOT NULL))
);
CREATE TABLE IF NOT EXISTS history.paragraphs (
 chapter_id text NOT NULL REFERENCES history.chapters(chapter_id) ON DELETE CASCADE,
 ordinal integer NOT NULL CHECK(ordinal>=0), original_text text NOT NULL CHECK(length(original_text)>0),
 normalized_text text NOT NULL, PRIMARY KEY(chapter_id,ordinal)
);
CREATE INDEX IF NOT EXISTS chapters_book_idx ON history.chapters(book_id,chapter_index);
CREATE INDEX IF NOT EXISTS paragraphs_original_trgm ON history.paragraphs USING gin(original_text gin_trgm_ops);
CREATE INDEX IF NOT EXISTS paragraphs_normalized_trgm ON history.paragraphs USING gin(normalized_text gin_trgm_ops);

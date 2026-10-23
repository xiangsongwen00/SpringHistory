-- Original chapters/paragraphs remain immutable during restoration import.
CREATE TABLE IF NOT EXISTS history.character_notes (
 chapter_id text PRIMARY KEY REFERENCES history.chapters(chapter_id) ON DELETE CASCADE,
 source_sha256 text NOT NULL, decoder text NOT NULL, text_sha256 text NOT NULL,
 mapping_version text NOT NULL, record jsonb NOT NULL,
 reading_text text NOT NULL, replacements integer NOT NULL CHECK(replacements>=0),
 unresolved integer NOT NULL CHECK(unresolved>=0), updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS history.chapter_assets (
 chapter_id text NOT NULL REFERENCES history.chapters(chapter_id) ON DELETE CASCADE,
 ordinal integer NOT NULL CHECK(ordinal>=0), kind text NOT NULL CHECK(kind IN ('pict','object')),
 source_sha256 text NOT NULL, decoder text NOT NULL, raw_rtf_sha256 text NOT NULL,
 start_byte integer NOT NULL, end_byte integer NOT NULL CHECK(end_byte>start_byte),
 parent_ordinal integer, format text NOT NULL, status text NOT NULL,
 raw_group_sha256 text NOT NULL, raw_group bytea NOT NULL,
 payload_sha256 text, payload bytea,
 PRIMARY KEY(chapter_id,ordinal)
);

# Style Corpus

This directory stores the daily writer's long-term style corpus.

Rules:

- Formal private corpus entries should come from Gmail samples only.
- Until Gmail access is re-authorized, public reference material can be used to validate schemas and extraction logic, but should not be treated as the formal private corpus.
- Each entry should follow the `style_corpus_entry` schema used by `build_tech_daily_style_corpus.py`.

Recommended layout:

- `gmail/` for formal private samples
- `public/` for public schema-validation samples

The builder script is intentionally conservative: it extracts short structured segments and metadata, not full article archives.

# Catalog Digest Cache

The requirements tooling maintains an in-process cache of parsed catalog
sections to avoid repeatedly reading large Markdown files. Cached entries are
keyed by each catalog's filesystem signature (size + nanosecond mtime) and are
shared across:

- `reqflow.RequirementPlanner` overlap detection
- `reqflow.cli.review` validation runs

## Footprint

- Stored in memory only for the lifetime of the Python process.
- Snapshot text is retained once per catalog file; parsed sections are cached
  on-demand.
- No files are written to disk, so the cache size is bounded by the number of
  active catalogs in the current process.

## Invalidation

- All catalog-writing helpers in `reqflow.catalog` automatically invalidate the
  corresponding cache entry.
- `reqflow.cli.review` offers `--refresh-cache` to force a reload the next time
  the command runs.
- `reqflow.catalog_cache.catalog_cache.clear()` is available for test fixtures
  and tooling that need to flush every cached entry explicitly.

When a catalog changes on disk, the next read detects the updated signature and
refreshes the snapshot automatically, ensuring cached data never drifts from
the source files.

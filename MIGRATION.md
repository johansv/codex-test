# Reqflow migration (2025-10-27)

## Moved modules

| Old path | New path |
| --- | --- |
| src/agentlab/utils/approvals.py | src/reqflow/approvals.py |
| src/agentlab/cli/amend.py | src/reqflow/cli/amend.py |
| src/agentlab/cli/batch.py | src/reqflow/cli/batch.py |
| src/agentlab/cli/bulk_amend.py | src/reqflow/cli/bulk_amend.py |
| src/agentlab/cli/capture.py | src/reqflow/cli/capture.py |
| src/agentlab/cli/dev.py | src/reqflow/cli/dev.py |
| src/agentlab/cli/doc_refactor.py | src/reqflow/cli/doc_refactor.py |
| src/agentlab/cli/mark_done.py | src/reqflow/cli/mark_done.py |
| src/agentlab/cli/mark_done_nonfunctional.py | src/reqflow/cli/mark_done_nonfunctional.py |
| src/agentlab/cli/requirements.py | src/reqflow/cli/requirements.py |
| src/agentlab/cli/review.py | src/reqflow/cli/review.py |
| src/agentlab/cli/slice.py | src/reqflow/cli/slice.py |
| src/agentlab/cli/start.py | src/reqflow/cli/start.py |
| src/agentlab/cli/start_nonfunctional.py | src/reqflow/cli/start_nonfunctional.py |
| tests/agentlab/cli/test_amend_cli.py | tests/reqflow/cli/test_amend_cli.py |
| tests/agentlab/cli/test_batch_cli.py | tests/reqflow/cli/test_batch_cli.py |
| tests/agentlab/cli/test_bulk_amend_cli.py | tests/reqflow/cli/test_bulk_amend_cli.py |
| tests/agentlab/cli/test_capture_cli.py | tests/reqflow/cli/test_capture_cli.py |
| tests/agentlab/cli/test_dev_cli.py | tests/reqflow/cli/test_dev_cli.py |
| tests/agentlab/cli/test_doc_refactor_cli.py | tests/reqflow/cli/test_doc_refactor_cli.py |
| tests/agentlab/cli/test_mark_done_cli.py | tests/reqflow/cli/test_mark_done_cli.py |
| tests/agentlab/cli/test_mark_done_nonfunctional_cli.py | tests/reqflow/cli/test_mark_done_nonfunctional_cli.py |
| tests/agentlab/cli/test_requirements_cli.py | tests/reqflow/cli/test_requirements_cli.py |
| tests/agentlab/cli/test_review_cli.py | tests/reqflow/cli/test_review_cli.py |
| tests/agentlab/cli/test_slice_cli.py | tests/reqflow/cli/test_slice_cli.py |
| tests/agentlab/cli/test_start_cli.py | tests/reqflow/cli/test_start_cli.py |
| tests/agentlab/cli/test_start_nonfunctional_cli.py | tests/reqflow/cli/test_start_nonfunctional_cli.py |
| assets/config/approval-policy.toml | assets/reqflow/approval-policy.toml |

## New console scripts

```
reqflow-capture = reqflow.cli.capture:main
reqflow-req = reqflow.cli.requirements:main
reqflow-dev = reqflow.cli.dev:main
reqflow-mark-done = reqflow.cli.mark_done:main
reqflow-mark-done-nf = reqflow.cli.mark_done_nonfunctional:main
reqflow-start = reqflow.cli.start:main
reqflow-start-nf = reqflow.cli.start_nonfunctional:main
reqflow-amend = reqflow.cli.amend:main
reqflow-bulk-amend = reqflow.cli.bulk_amend:main
reqflow-batch = reqflow.cli.batch:main
reqflow-review = reqflow.cli.review:main
reqflow-slice = reqflow.cli.slice:main
reqflow-doc-refactor = reqflow.cli.doc_refactor:main
```

Legacy `agentlab-*` console scripts now resolve to the same `reqflow.cli` modules; update automation at your earliest convenience.

## Deprecation shims

* `src/agentlab/cli/__init__.py` provides dynamic access to `reqflow.cli.*`.
* `src/agentlab/cli/<name>.py` modules re-export the new CLIs.
* `src/agentlab/utils/approvals.py` re-exports `reqflow.approvals`.

These shims emit `DeprecationWarning` and will be removed after 2025-12-31.

## Verification commands

```
pip install -e .
pytest -q
python -c "import reqflow; print(reqflow.__name__)"
```

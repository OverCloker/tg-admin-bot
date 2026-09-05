# Code audit — 2026-09-05

Scope: bot/API role checks, Mini App owner restrictions, source encodings,
dependency consistency, regression suite, and local Bot API build configuration.

## Fixes

- The legacy admin API treated every BOT_ADMIN_IDS member as an owner. Owner
  operations now require the resolved OWNER_ID, consistently with Mini App.
  This affects permission management, access keys and other owner-only routes.
  An explicit owner no longer needs membership in the legacy admin list.
- Local Bot API compilation now defaults to one parallel job. Compose explicitly
  passes CMAKE_BUILD_PARALLEL_LEVEL into the build; a host environment variable
  alone was insufficient. This reduces peak build memory demand, but cannot
  guarantee that a small server has enough RAM.
- Docker context excludes pytest temporary directories, portable copies and
  local publisher state. Git ignores generated pytest directories and SQLite
  backups. Existing user files and backups were preserved.
- Encoding regression coverage now includes media_publisher.

## Verification

- 202 tests passed, including eight new owner-access cases and existing
  moderation, gift idempotency, media and security regression tests.
- compileall succeeded for app and media_publisher.
- pip check: no broken requirements.
- UTF-8/BOM/common mojibake checks passed for app, tests, media_publisher and
  supported root-level text files.
- git diff --check passed.

## Remaining limitations

- Docker is unavailable on the audited Windows environment. The image build,
  actual Debian memory consumption and live Telegram permissions were not tested.
- Four FastAPI on_event deprecation warnings remain. Lifecycle migration should
  include worker startup/shutdown tests; they do not fail the current suite.
- The local Bot API source defaults to master and base images use moving tags.
  Reproducible releases will require explicitly selected and tested revisions.
- This is a focused code audit, not an exhaustive vulnerability assessment.
  Existing cached Telegram admin membership and global application-admin policy
  need to be considered when changing the intended scope of group administrators.
- Encoding checks cover source files, not existing production database contents.

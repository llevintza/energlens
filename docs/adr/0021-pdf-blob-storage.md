# 0021. Keep bill PDFs in an object store, behind a two-backend Protocol

- **Status:** Accepted
- **Date:** 2026-08-13
- **Deciders:** llevintza
- **Landed in:** PR #94 (`25f6436`)
- **Related:** [ADR-0011](0011-backend-hosting-render.md), [ADR-0012](0012-database-hosting-neon.md), [ADR-0014](0014-split-liveness-and-readiness-health-checks.md), [ADR-0020](0020-invoice-identity-not-billing-period.md), issues #54, #49, #24

## Context

Until now nothing in this repo had ever handled a file. Extraction lived in the
`energlens-ingest` CLI, which reads PDFs off a developer's own disk; the only file-ish
column was `bills.raw_file_ref`, a `String(500)` holding a bare filename that resolves to
nothing on any machine but the one that ran the import. A browser had no way to reach the
extractor at all.

Three things forced the question of whether to keep the bytes:

- **The extraction agent needs the source.** #59 runs extraction server-side and #24 shows
  the user what was extracted next to where it came from. Both need the document to still
  exist after the request that uploaded it.
- **Re-extraction is not free.** Extraction costs roughly 1–2¢ per bill against a paid API.
  Discarding the PDF means any re-run — a better prompt, a fixed region profile, an
  eval — re-uploads and re-pays.
- **Keeping them is a privacy decision, not a storage one.** `AGENTS.md` says "never commit
  real bill PDFs" and `.gitignore` carries `*.pdf`. An electricity bill has a name, an
  address, a customer code and a meter serial on it. The instinct behind that rule does not
  stop at the repository boundary.

The hosting constraints were fixed before this decision and are not negotiable within it:

| Constraint | Source | Consequence |
| --- | --- | --- |
| Render's filesystem is ephemeral; `render.yaml` declares no `disk:`, and disks are not available on `plan: free` | [ADR-0011](0011-backend-hosting-render.md) | Local disk cannot be the production answer |
| Neon free tier caps at **0.5 GB** total | [ADR-0012](0012-database-hosting-neon.md) | See the arithmetic below |
| `make check` must never touch the network | `AGENTS.md` | Whatever is chosen must have an offline implementation |
| A contributor with no cloud account must be able to run the app | `README.md` setup | Same |

## Decision

**We store bill PDFs as objects, addressed by their SHA-256, behind a `StorageBackend`
`Protocol` with two implementations** — `LocalStorage` (the default) and `S3Storage` (any
S3-compatible endpoint).

The Protocol is the load-bearing part, not the S3 client. It is what lets the default be a
directory on disk, so the suite runs offline and a fresh clone needs no account, while the
deployment can be switched to a real bucket with an environment change and no code change.

Four properties of the implementation are deliberate:

- **The key is `{place_id}/{sha256}.pdf`** — content-addressed, and namespaced per place.
  `UniqueConstraint(place_id, sha256)` makes re-upload idempotent: the same file returns the
  existing row with `200` instead of creating a second row and paying for a second
  extraction. Per place rather than globally, so one user cannot learn that another has
  already uploaded a given file by watching for a `200` where they expected a `201`.
- **The object is written before the row.** The reverse order can commit a row whose object
  was never written — and because the row *is* the dedupe index, every later upload of that
  file would then return `200` for a document that cannot be downloaded. Content-addressing
  makes put-first strictly safer: a failed insert leaves an object under a key the retry
  reuses.
- **Account deletion removes the objects.** Every foreign key into `bill_documents` is
  `ON DELETE CASCADE`, so the database drops the rows on its own — silently, and without
  touching a byte. `app/services/documents.py` collects the keys before the delete and
  purges them after the commit, from all three routes that can destroy a document.
- **`signature_version="s3v4"`.** boto3 still presigns with SigV2 under some client
  configurations, and Cloudflare R2 and Backblaze B2 reject SigV2 outright. That failure
  would have appeared only as a broken download against a real bucket.

**Production currently runs `STORAGE_BACKEND=local`, and that is a known temporary state.**
No bucket is provisioned. Uploads work; the objects do not survive a deploy or an idle
spin-down, after which `GET /{id}/content` returns `410 Gone` while the metadata still
answers. The README's Deployment section is the runbook for making it durable, and doing so
requires no code change.

## Consequences

### What this buys

- The database stays small and the bytes stay cheap. Object storage at this size is free on
  both providers considered, with no egress charge.
- Re-uploading a file costs one hash and one `SELECT`, so the ingest path is idempotent by
  construction — the same property `uq_bills_place_invoice` gives bills.
- `make check` runs with no credentials and no network, including the S3 tests.
- Switching a deployment to durable storage is five environment variables.

### What this costs

- **boto3 and botocore are now backend dependencies** — roughly 100 MB on disk and ~30 MB of
  RSS if imported. Mitigated by importing them lazily inside `app/storage/s3.py`, so a
  deployment on local storage never pays for them, but they are in the lockfile and in the
  build either way.
- **Two backends is two code paths**, and the one production will eventually run is the one
  the suite exercises only against a stub.
- **A second store to keep consistent with Postgres.** There is no transaction spanning both,
  so the failure modes below are real rather than theoretical.
- **We now hold personal data outside the database**, which makes "delete my account" a
  larger promise than it was. That is the cost this ADR most wants a future reader to notice.

## Limitations

- **10 MB per upload** (`UPLOAD_MAX_BYTES`), enforced twice: `MaxBodySizeMiddleware` rejects
  on `Content-Length` before the body is read, and the handler's read loop bounds memory
  whatever the client declared. The second is necessary because FastAPI parses the multipart
  body *before* it solves dependencies — so neither the route nor its auth dependency can
  stop an oversized body from arriving.
- **20 uploads per user per day** (`UPLOAD_DAILY_LIMIT`), counted from UTC midnight.
  **This counts live rows, not uploads.** Deleting your own documents lowers the count, so
  it limits what you are keeping rather than what you have sent. At this cap, with storage as
  the only cost, that is the correct metric — deleting genuinely frees the limited resource.
  It stops being correct the moment each new document triggers a paid API call.
- **An object delete that fails after its row is committed leaks.** The object is
  unreferenced and unreachable through the API — naming it needs both a place UUID and the
  file's own digest — but it is still stored, and it is still someone's electricity bill.
  Logged at ERROR with the key; grep for `failed to delete stored object`. There is no
  reconciliation sweep.
- **Signed URLs are capability URLs.** A `GET /{id}/content` against an S3 backend returns a
  302 to a URL that carries no authentication of its own. Expiry is 300 s.
- **Neon storage is not the binding constraint, and was never going to be.** At ~265 KB per
  bill, Neon's 0.5 GB free tier holds roughly 1,900 documents — about 160 years of monthly
  bills for one place. The reason not to use `bytea` is not capacity.

## Alternatives considered

| Option | Why not |
| --- | --- |
| **Postgres `bytea`** | One store, real transactions, and account deletion becomes a cascade with nothing left over — genuinely attractive. Rejected because it puts multi-megabyte blobs in the row store that every `SELECT *` and every `pg_dump` then carries, on the tier with no backups ([ADR-0012](0012-database-hosting-neon.md) calls backups "the genuine risk here, not storage"). It also makes the 0.5 GB ceiling shared between the data we query and the data we merely keep. |
| **Discard the PDF after extraction** | Cheapest and the best privacy answer. Rejected because #24 shows the user the source alongside the extraction, and because re-running extraction with a better prompt would mean asking the user to re-upload thirty files. |
| **A Render persistent disk** | Would make `LocalStorage` viable in production. Rejected: disks are not on the free plan, they pin the service to one instance, and they would put the decision inside the hosting choice rather than beside it. |
| **An async S3 client (aioboto3, aiobotocore)** | Avoids the threadpool hop. Rejected for one more dependency in a 512 MB process at a workload of one to three files at a time; `run_in_threadpool` is the right trade at this size. |
| **A single backend, S3 only, with MinIO for tests** | Removes a code path. Rejected because it makes `make setup` require Docker — which this repo deliberately does not ([`scripts/pgdev.sh`](../../scripts/pgdev.sh) exists precisely so Postgres does not) — and puts a container in the gate. |
| **Probing the bucket in `/health/db`** | See below. |

### On ADR-0014's readiness trigger

[ADR-0014](0014-split-liveness-and-readiness-health-checks.md) names this exact moment as a
revisit trigger: *"More dependencies are added (cache, queue, object storage) → `/health/db`
becomes `/health/ready` reporting per-dependency status."*

**The trigger has fired and we are deliberately not acting on it yet.** With
`STORAGE_BACKEND=local` a readiness probe would stat a directory and report success no
matter what — a check that cannot fail is worse than no check, because it reads as coverage.
And once S3 is live, a HEAD per probe adds latency to an endpoint monitoring hits on a
schedule and turns our readiness into a public oracle for a third party's availability. The
condition for acting is in the triggers below, and it is specific.

## Revisit when

- [ ] **A bucket is provisioned and `STORAGE_BACKEND=s3` is live** → then split `/health/db`
      into `/health/ready` with per-dependency status, per ADR-0014. Not before: until then
      there is nothing to probe.
- [ ] **#59 lands and each new document triggers a paid extraction** → the daily limit must
      move off deletable rows onto an append-only counter, because delete-and-reupload will
      then buy unbounded API spend rather than unbounded storage.
- [ ] **`failed to delete stored object` appears more than a handful of times** → build the
      reconciliation sweep (list keys, left-join `bill_documents.storage_key`, delete the
      orphans). Cheap to write, not worth writing before there is evidence it is needed.
- [ ] **Stored objects pass ~5 GB** → the free tiers below start to matter and the retention
      question ("do we keep every bill forever?") has to be answered rather than deferred.
- [ ] **A deletion-verification requirement arrives** (a real user asking, or a regulation)
      → best-effort erasure stops being adequate and the tombstone table becomes necessary.
- [ ] **Uploads become more than a handful at a time** → the buffer-to-cap design puts
      ~40–60 MB per concurrent upload against 512 MB; measure before assuming.

## Migration path

The Protocol is the migration path, and that is most of why it exists.

1. **Local → object store**: create a bucket, set the five `S3_*` variables plus
   `STORAGE_BACKEND=s3` on the service, redeploy. No code change. Existing objects do not
   move — with Render's ephemeral disk there are none worth moving.
2. **Between S3-compatible providers** (R2 → B2 → AWS): `rclone sync` the bucket, change
   `S3_ENDPOINT_URL`, `S3_REGION` and the credentials. `storage_key` is provider-agnostic,
   so no rows change.
3. **Off object storage entirely** (to `bytea`, or to a disk): write a third implementation
   of the same four methods and a one-off script that reads every `storage_key` through the
   old backend and writes it through the new one. `bill_documents` needs no migration —
   `storage_key` is opaque by design.

Estimated effort for (1): **under an hour**, most of it waiting for a deploy. For (3): a
day, and the schema is not the hard part — verifying nothing was lost in transit is.

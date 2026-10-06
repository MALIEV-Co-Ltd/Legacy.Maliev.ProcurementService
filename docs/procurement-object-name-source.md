# Literal purchase-order file object names

Unpublished draft based on accepted Procurement main `30a46c2eb7f1a8ef630440d2aaec4aa72e6bf7dc`.
Initial `5fac706a7983a6d359b39acbd670e6800afe020e` and latest source snapshot
`135e526d0dab85c415b3afdcefd7b70fe2c82e2f` share FilesController blob
`158240d27dd9119b88599c6e7f5294c77d948cfe` at
`Maliev.PurchaseOrderService.Api/Controllers/FilesController.cs`.
Both POST query metadata and PUT body metadata persist ObjectName directly from the caller.
The target currently silently trims its leading/trailing whitespace, changing the storage identity.

Remove only the two ObjectName.Trim calls. Preserve bucket handling, blank-field checks,
owner checks, nullable owner-update semantics, timestamps, routes, permissions, DTOs and metadata-only
storage behavior. No object transfer/provider call or live GCS compatibility claim. Address normalization
and whole navigation/source graph parity are not included or claimed closed.

Strengthen the existing normal Program/JWT/live-permission/PostgreSQL file lifecycle case with
significant spaces, ASCII-escaped Thai and literal percent/underscore object names through encoded
POST query and PUT JSON. Exact Location/detail/parent-list HTTP readbacks and persisted names are checked.
An unrelated second-owner file retains every returned scalar through the first file's update/delete.
The removed owner's list still returns404; DELETE/replay and both parent rows remain covered.
No new case is added: full293 and existing focused counts remain unchanged.

Native build/tests/formatting/coverage remain pending hosted-only execution after full actual diff review.
No local .NET/SDK/testhost/Docker, commit, publication, deployment or whole initial-source closure.
Require fresh full293, nullable24, focused48, master-query19, durable-create6 and authenticated15+9,
raw four-assembly coverage >=80 percent with generated lines/no exclusions, zero-warning/error build
and all relevant static/security checks. Earlier accepted main evidence cannot pass this draft.

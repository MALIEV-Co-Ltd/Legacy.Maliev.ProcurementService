# Actual Auth Program / Procurement join candidate

The versioned public graph freezes accepted Auth b27, Defaults7ed,
CompatibilityContracts78 and Procurement26da4a1. The owning service's actual
production/build inputs and public Procurement runtime fixture must equal the
frozen witness before the new harness executes. No production source is changed.

The harness references the public producer PostgreSQL fixtures and configures
normal Auth and Procurement Programs. Auth creates employee tokens through the
actual password-login endpoint and persists the corresponding refresh session.
Procurement's actual registered token provider posts to the actual Auth
service-login endpoint. That endpoint verifies a synthetic test-only registry
hash and issues the workload token using its normal RS256 issuer. The test client
is configured only with `iam.auth.check-permission`; this is explicit fixture
enrollment, not production enrollment or an employee grant.

Only the named Auth primary HTTP transport forwards to Auth TestServer. It retains
the production request guard, late-response ownership handler and shared
resilience. The controlled IAM primary HTTP transport validates the actual issued
service JWT using normal Auth JWT validation parameters. It independently checks
the employee principal, exact permission/resource, `bypassCache:true` and separate
live credential. It never issues tokens or replaces IIamServiceClient,
authentication, authorization, identity readers, session stores or issuers.

Eleven HTTP join executions cover fresh live create/deny with distinct databases,
supplier deletion/fresh denial despite the real employee's signed supplier grant,
wrong secret and unknown-client actual Auth401 responses, missing live credential,
IAM refusal/malformed responses and consumer issuer/audience refusal. Denials
require unchanged PostgreSQL rows. Actual envelopes, token kinds, algorithm and
persisted employee session binding are inspected without printing credentials or
token material. Owned seed/normalized-host connection pools are cleared after
host/context disposal; producer fixtures initialize/dispose once per class.
Cleanup attempts every owned resource while preserving the first exception;
four additional deterministic cleanup executions cover early/middle/late and
multiple failures. The strict harness gate requires all fifteen executions.
Supplier checks cover the unchanged resource-scope feature's disabled/global mode
and explicitly enabled/exact-route mode. Both require fresh live decisions and
retain the denied supplier; no production feature flag is activated.

Hosted build, exact joined execution names/cardinality, full Procurement suite,
focused lifecycle suite, generated-inclusive full-service coverage >=80% per
assembly, formatting, audit and credential scans are required before acceptance.
Joined raw coverage is retained and must include executable lines from both real
API assemblies; it is not a replacement for full-service coverage acceptance.

This candidate is not yet executed. Actual production client enrollment, legacy
IAM bridge reachability/authorization and joined BFF proof remain separate
obligations. It does not close the initial source baseline or change production
permissions, deployment flags, provider activation, migrations or persisted data.

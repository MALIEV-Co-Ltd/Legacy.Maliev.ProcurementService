# Source Procurement master query slice

Initial source5fac706a7983a6d359b39acbd670e6800afe020e remains partial. This slice
covers only Supplier and PurchaseOrder controller list query behavior, verified
against immutable135e526. Hosted tests-first37321105626 built with zero warnings
and errors, then recorded243 existing passes plus4 genuine source behavior failures.

Supplier integer parsing selects only the identifier; nonnumeric text matches
lowercased nullable fields against the original literal search. PurchaseOrders
match identifier substrings plus lowercased nullable notes against lowercased
literal search. Nonempty whitespace is retained and percent/underscore are literal.
Both return404 when the selected page has no rows. Existing default50/max250 bounds,
authentication/live policies, contact mapping, schemas and PascalCase DTOs remain.
Intranet consumers already map404 to empty results and supply bounded page sizes.

Nineteen declared HTTP/PostgreSQL regressions include integer boundaries, literal
case/wildcards, null fields and both separate databases. Existing actual Auth join
still requires15 cases and byte-identical runtime/build/public-fixture inputs to
the frozen query candidate8f2c5fc. Its manifest declares exactly one intentional
production blob change and freezes the other51 input blobs against26da4a1.
Defaults7ed, Authb27, Contracts78 and WorkflowsE3 remain unchanged.

Candidate commits are hosted-validation inputs, not accepted production witnesses.
Acceptance requires final full/focused/Auth/lifecycle/raw/static validation and
normal protected merge with fresh-main proof. No local native runtime, deployment,
production enrollment, source SQL writes or whole-source closure is authorized.

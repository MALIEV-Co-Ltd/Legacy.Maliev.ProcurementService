"""Issue29 current consumer only; historical source graphs remain frozen."""

ADDRESS_BINDINGS = {
    "Legacy.Maliev.ProcurementService.Api/Controllers/SupplierAddressesController.cs": (
        "63dfa7c375090e0a1d3dd191f7430b1519c8bdea", "82e9080b60dd2e89882167ad9e19848d78eef5ee"),
    "Legacy.Maliev.ProcurementService.Api/Controllers/PurchaseOrderAddressesController.cs": (
        "91b6bf11646f89f5c6736e7f54af964e044ae6ed", "4c7704ebc099c3e6cc2ee3596cbcc847d348ff16"),
}
ADDRESS_TEST = "Legacy.Maliev.ProcurementService.Tests/Controllers/ProcurementAddressNullBoundaryTests.cs"
ADDRESS_TEST_BLOB = "43a7688f76cfe4a8b19d1e7171e070aaa6c31226"


def address_consumer_inputs(previous):
    current = dict(previous)
    for path, (before, after) in ADDRESS_BINDINGS.items():
        if previous.get(path) != "100644 blob " + before:
            raise ValueError("Exact address null-body consumer preimage differs: " + path)
        current[path] = "100644 blob " + after
    return current


def require_address_runtime(candidate, blob):
    for path, (_, expected) in ADDRESS_BINDINGS.items():
        if blob(candidate, path) != expected:
            raise ValueError("Exact address null-body consumer postimage differs: " + path)
    require_address_test(candidate, blob)
    return set(ADDRESS_BINDINGS)


def require_address_test(candidate, blob):
    if blob(candidate, ADDRESS_TEST) != ADDRESS_TEST_BLOB:
        raise ValueError("Exact eight-row address null-body test successor differs")
    return ADDRESS_TEST

# Current Supplier mutation successor; the preceding address transition stays frozen.
SUPPLIER_MUTATION_BINDINGS = {
    "Legacy.Maliev.ProcurementService.Api/Controllers/SuppliersController.cs": (
        "aa83c9ddc65ccac0bfc90974f64a817ad8cbbc68", "f010e662b533449c49f8080be48ceb0a7dcfdc0f"),
    "Legacy.Maliev.ProcurementService.Api/Controllers/SupplierAddressesController.cs": (
        "82e9080b60dd2e89882167ad9e19848d78eef5ee", "2b0028e2498e1255203b17f74a62a9d4023a9c46"),
}
SUPPLIER_MUTATION_TESTS = {
    "Legacy.Maliev.ProcurementService.Tests/Controllers/ProcurementSupplierMutationSourceTests.cs":
        "8a4f380fdba53512b48bb8e4c864f67ccc84584f",
    "Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementSupplierMissingParentHttpTests.cs":
        "4a816860f2910ade0c0c0d7319314382d7edcc65",
}


def supplier_mutation_consumer_inputs(previous):
    current = dict(previous)
    for path, (before, after) in SUPPLIER_MUTATION_BINDINGS.items():
        if previous.get(path) != "100644 blob " + before:
            raise ValueError("Exact Supplier mutation consumer preimage differs: " + path)
        current[path] = "100644 blob " + after
    return current


def supplier_mutation_runtime_blob(path, previous):
    if path in SUPPLIER_MUTATION_BINDINGS:
        before, after = SUPPLIER_MUTATION_BINDINGS[path]
        if previous != before:
            raise ValueError("Exact Supplier mutation runtime preimage differs: " + path)
        return after
    return previous


def require_supplier_mutation_runtime(candidate, blob):
    for path, (_, expected) in SUPPLIER_MUTATION_BINDINGS.items():
        if blob(candidate, path) != expected:
            raise ValueError("Exact Supplier mutation runtime successor differs: " + path)

    def previous_blob(root, path):
        actual = blob(root, path)
        if path in SUPPLIER_MUTATION_BINDINGS:
            before, after = SUPPLIER_MUTATION_BINDINGS[path]
            if actual != after:
                raise ValueError("Supplier mutation current runtime changed: " + path)
            return before
        return actual

    return require_address_runtime(candidate, previous_blob) | set(SUPPLIER_MUTATION_BINDINGS)


def require_supplier_mutation_tests(candidate, baseline, blob, git, base):
    for path, expected in SUPPLIER_MUTATION_TESTS.items():
        if (blob(candidate, path) != expected
                or git(candidate, "rev-parse", "HEAD:" + path).decode().strip() != expected):
            raise ValueError("Exact Supplier mutation working/HEAD test successor differs: " + path)
        if (baseline / path).exists():
            raise ValueError("Supplier mutation test must not be present in the frozen baseline: " + path)
    if git(baseline, "ls-tree", "-r", "--name-only", base, "--", *SUPPLIER_MUTATION_TESTS).strip():
        raise ValueError("Supplier mutation test must be absent from the frozen base object")
    return set(SUPPLIER_MUTATION_TESTS)


# Current Supplier-address parent audit successor; all preceding transitions stay frozen.
SUPPLIER_PARENT_AUDIT_REPOSITORY = "Legacy.Maliev.ProcurementService.Data/ProcurementRepositories.cs"
SUPPLIER_PARENT_AUDIT_PREVIOUS_BLOB = "f116b6f1f0258f2f3bfd0eb35190bd14a64c06f4"
SUPPLIER_PARENT_AUDIT_RUNTIME_BLOB = "54cb841a000af128f8cac90028966577983f3228"
SUPPLIER_PARENT_AUDIT_TEST = "Legacy.Maliev.ProcurementService.Tests/Integration/SupplierAddressParentAuditSourceHttpTests.cs"
SUPPLIER_PARENT_AUDIT_TEST_BLOB = "52aa910abfbbb7c19aa4e4cf84ac3c87e7975f00"


def supplier_parent_audit_consumer_inputs(previous):
    path = SUPPLIER_PARENT_AUDIT_REPOSITORY
    if previous.get(path) != "100644 blob " + SUPPLIER_PARENT_AUDIT_PREVIOUS_BLOB:
        raise ValueError("Exact Supplier parent-audit consumer preimage differs: " + path)
    current = dict(previous)
    current[path] = "100644 blob " + SUPPLIER_PARENT_AUDIT_RUNTIME_BLOB
    return current


def supplier_parent_audit_runtime_blob(path, previous):
    if path != SUPPLIER_PARENT_AUDIT_REPOSITORY:
        return previous
    if previous != SUPPLIER_PARENT_AUDIT_PREVIOUS_BLOB:
        raise ValueError("Exact Supplier parent-audit runtime preimage differs: " + path)
    return SUPPLIER_PARENT_AUDIT_RUNTIME_BLOB


def require_supplier_parent_audit_runtime(candidate, blob):
    path = SUPPLIER_PARENT_AUDIT_REPOSITORY
    if blob(candidate, path) != SUPPLIER_PARENT_AUDIT_RUNTIME_BLOB:
        raise ValueError("Exact Supplier parent-audit runtime successor differs: " + path)
    return {path}


def require_supplier_parent_audit_tests(candidate, baseline, blob, git, base):
    path = SUPPLIER_PARENT_AUDIT_TEST
    expected = SUPPLIER_PARENT_AUDIT_TEST_BLOB
    if (blob(candidate, path) != expected
            or git(candidate, "rev-parse", "HEAD:" + path).decode().strip() != expected):
        raise ValueError("Exact Supplier parent-audit working/HEAD test successor differs: " + path)
    if (baseline / path).exists():
        raise ValueError("Supplier parent-audit test must be absent from the frozen working baseline: " + path)
    if git(baseline, "ls-tree", "-r", "--name-only", base, "--", path).strip():
        raise ValueError("Supplier parent-audit test must be absent from the frozen base object")
    return {path}

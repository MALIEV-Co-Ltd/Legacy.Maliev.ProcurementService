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

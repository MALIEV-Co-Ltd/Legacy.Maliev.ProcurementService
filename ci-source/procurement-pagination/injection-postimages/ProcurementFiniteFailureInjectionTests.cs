namespace Legacy.Maliev.ProcurementService.Tests.Integration;

public sealed class ProcurementFiniteFailureInjectionTests
{
    private static ProcurementRuntimeFixture NewFixture() => new ProcurementRuntimeFixture<ProcurementPaginationSourceTests>();
    private static Exception First(Exception failure) => failure is AggregateException aggregate ? First(aggregate.InnerExceptions[0]) : failure;
    private static bool Contains<T>(Exception failure) where T : Exception => failure is T
        || failure is AggregateException aggregate && aggregate.InnerExceptions.Any(Contains<T>);
    private static void BothDisposed()
    {
        Assert.Contains("Supplier", ProcurementQualificationFaults.DisposalAttempts);
        Assert.Contains("PurchaseOrder", ProcurementQualificationFaults.DisposalAttempts);
    }

    [Fact]
    public async Task ConstructorSecondRole()
    {
        ProcurementQualificationFaults.Configure("constructor-second-role");
        var failure = Record.Exception(() => NewFixture());
        Assert.NotNull(failure); Assert.IsType<ProcurementQualificationFailure>(First(failure));
        Assert.Equal(1, ProcurementQualificationFaults.ConstructedDisposals);
        await ProcurementQualificationFaults.CompleteAsync();
    }

    private static async Task SetupFailure(string name, bool writer)
    {
        ProcurementQualificationFaults.Configure(name);
        var fixture = NewFixture();
        try
        {
            var failure = await Record.ExceptionAsync(fixture.InitializeAsync);
            Assert.NotNull(failure);
            if (writer) Assert.IsType<ObjectDisposedException>(First(failure));
            else Assert.IsType<ProcurementQualificationFailure>(First(failure));
            BothDisposed();
            if (name is "order-start-after-supplier" or "receipt-start-write")
                Assert.Single(ProcurementQualificationFaults.StartedIds);
        }
        finally { await fixture.DisposeAsync(); }
        await ProcurementQualificationFaults.CompleteAsync();
    }

    [Fact] public Task SupplierStart() => SetupFailure("supplier-start", false);
    [Fact] public Task OrderStartAfterSupplier() => SetupFailure("order-start-after-supplier", false);
    [Fact] public Task ReceiptAdmissionWrite() => SetupFailure("receipt-admission-write", true);
    [Fact] public Task ReceiptStartWrite() => SetupFailure("receipt-start-write", true);

    [Fact]
    public async Task ReceiptDisposalWrite()
    {
        ProcurementQualificationFaults.Configure("receipt-disposal-write");
        foreach (var point in new[] { "receipt-dispose-start-write", "receipt-dispose-return-write" })
        {
            ProcurementQualificationFaults.Fault = "";
            var fixture = NewFixture();
            try
            {
                await fixture.InitializeAsync();
                ProcurementQualificationFaults.Fault = point;
                var failure = await Record.ExceptionAsync(fixture.DisposeAsync);
                Assert.NotNull(failure); Assert.True(Contains<ObjectDisposedException>(failure)); BothDisposed();
            }
            finally { await fixture.DisposeAsync(); }
        }
        await ProcurementQualificationFaults.CompleteAsync();
    }

    [Fact]
    public async Task DisposalTimeout()
    {
        ProcurementQualificationFaults.Configure("disposal-timeout");
        var fixture = NewFixture();
        try
        {
            await fixture.InitializeAsync();
            var failure = await Record.ExceptionAsync(fixture.DisposeAsync);
            Assert.NotNull(failure); Assert.True(Contains<TimeoutException>(failure)); BothDisposed();
            Assert.Single(ProcurementQualificationFaults.PendingDisposals);
            await ProcurementQualificationFaults.CompleteAsync();
            Assert.True(ProcurementQualificationFaults.PendingDisposals[0].IsCompletedSuccessfully);
        }
        finally { await fixture.DisposeAsync(); }
    }

    [Fact]
    public async Task ConcurrentAppendRead()
    {
        ProcurementQualificationFaults.Configure("concurrent-append-read");
        var fixture = NewFixture();
        try { await fixture.InitializeAsync(); }
        finally { await fixture.DisposeAsync(); }
        await ProcurementQualificationFaults.CompleteAsync();
    }

    [Fact]
    public async Task ShortSerialFixtures()
    {
        ProcurementQualificationFaults.Configure("short-serial-fixtures");
        Func<ProcurementRuntimeFixture>[] factories = [
            () => new ProcurementRuntimeFixture<ProcurementPaginationSourceTests>(),
            () => new ProcurementRuntimeFixture<ProcurementPaginationWireContractTests>(),
            () => new ProcurementRuntimeFixture<ProcurementIndependentContactTests>(),
        ];
        foreach (var create in factories)
        {
            var fixture = create();
            try { await fixture.InitializeAsync(); }
            finally { await fixture.DisposeAsync(); }
        }
        Assert.Equal(6, ProcurementQualificationFaults.StartedIds.Count);
        await ProcurementQualificationFaults.CompleteAsync();
    }
}

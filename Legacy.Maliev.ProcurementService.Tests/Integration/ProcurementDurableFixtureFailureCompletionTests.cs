namespace Legacy.Maliev.ProcurementService.Tests.Integration;

public sealed class ProcurementDurableFixtureFailureCompletionTests
{
    [Fact]
    public async Task SuccessfulMigrationsWithObservationFailure_RecordStagePublishAndAttemptEveryCleanup()
    {
        var expected = new IOException("Synthetic endpoint observation failure.");
        var events = new List<string>();
        var stage = "purchase-order-migration";
        var lifetime = new ProcurementFixtureLifetime();
        var actual = await Assert.ThrowsAsync<IOException>(() => ProcurementDurableFixtureFailureCompletion.CompleteAsync(
            [], [expected], observationOnly =>
            {
                Assert.True(observationOnly);
                stage = "connection-observation";
            }, () =>
            {
                events.Add("before-cleanup");
                ProcurementFixtureDiagnosticFailures.PublishOrThrow(() => { }, [expected]);
                return Task.CompletedTask;
            }, () => lifetime.CleanupAsync(
                () => { events.Add("factory"); return Task.CompletedTask; },
                () => { events.Add("supplier"); return Task.CompletedTask; },
                () => { events.Add("purchase-order"); return Task.CompletedTask; },
                () => { events.Add("key"); return Task.CompletedTask; })));
        Assert.Same(expected, actual);
        Assert.Equal("connection-observation", stage);
        Assert.Equal(new[] { "before-cleanup", "factory", "supplier", "purchase-order", "key" }, events);
        Assert.Empty(lifetime.UnsettledOperations);
    }

    [Fact]
    public async Task MigrationObservationAndCleanupFailures_RetainPrimaryAndEveryOriginalInOrder()
    {
        var primary = new IOException("Synthetic migration failure.");
        var observation = new InvalidOperationException("Synthetic observation failure.");
        var publication = new IOException("Synthetic receipt publication failure.");
        var firstCleanup = new IOException("Synthetic first cleanup failure.");
        var secondCleanup = new InvalidOperationException("Synthetic second cleanup failure.");
        var events = new List<string>();
        var stage = "supplier-migration";
        var lifetime = new ProcurementFixtureLifetime();
        var actual = await Assert.ThrowsAsync<AggregateException>(() => ProcurementDurableFixtureFailureCompletion.CompleteAsync(
            [primary], [observation], observationOnly =>
            {
                if (observationOnly) stage = "connection-observation";
                Assert.False(observationOnly);
            }, () =>
            {
                events.Add("before-cleanup");
                ProcurementFixtureDiagnosticFailures.PublishOrThrow(() => throw publication, [observation]);
                return Task.CompletedTask;
            }, () => lifetime.CleanupAsync(
                () => { events.Add("factory"); return Task.FromException(firstCleanup); },
                () => { events.Add("supplier"); return Task.FromException(secondCleanup); },
                () => { events.Add("purchase-order"); return Task.CompletedTask; },
                () => { events.Add("key"); return Task.CompletedTask; })));
        Assert.Equal("supplier-migration", stage);
        Assert.Collection(actual.InnerExceptions,
            error => Assert.Same(primary, error),
            error => Assert.Same(observation, error),
            error => Assert.Same(publication, error),
            error => Assert.Same(firstCleanup, error),
            error => Assert.Same(secondCleanup, error));
        Assert.Equal(new[] { "before-cleanup", "factory", "supplier", "purchase-order", "key" }, events);
        Assert.Empty(lifetime.UnsettledOperations);
    }

    [Fact]
    public async Task ReferenceDeduplication_PreservesDistinctInstancesWithIdenticalTypeAndMessage()
    {
        var primary = new IOException("Identical synthetic failure.");
        var distinct = new IOException("Identical synthetic failure.");
        var actual = await Assert.ThrowsAsync<AggregateException>(() => ProcurementDurableFixtureFailureCompletion.CompleteAsync(
            [primary], [primary, distinct], observationOnly => Assert.False(observationOnly),
            () => Task.FromException(new AggregateException(primary, distinct)),
            () => Task.FromException(primary)));
        Assert.Collection(actual.InnerExceptions,
            error => Assert.Same(primary, error),
            error => Assert.Same(distinct, error));
    }
}

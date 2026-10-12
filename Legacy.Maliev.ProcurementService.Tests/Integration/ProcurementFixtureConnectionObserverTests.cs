using System.Data;
using System.Text.Json;
using Microsoft.EntityFrameworkCore.Diagnostics;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Infrastructure;
using Microsoft.Extensions.DependencyInjection;
using Npgsql;

namespace Legacy.Maliev.ProcurementService.Tests.Integration;

public sealed class ProcurementFixtureConnectionObserverTests
{
    [Fact]
    public void AdditionalOptionsRegistration_PreservesConfiguredConnectionTimeoutAndRetryPolicy()
    {
        const string configured = "Host=127.0.0.1;Port=32123;Database=fixture;Pooling=true;Minimum Pool Size=2;Maximum Pool Size=20";
        var services = new ServiceCollection();
        services.AddDbContext<ObservationContext>(options => options.UseNpgsql(configured,
            provider => provider.CommandTimeout(120).EnableRetryOnFailure(5, TimeSpan.FromSeconds(10), null)));
        var journal = new ProcurementConnectionJournal();
        var observer = new ProcurementFixtureConnectionObserver(journal, "supplier", configured);
        services.ConfigureDbContext<ObservationContext>(options => options.AddInterceptors(observer));
        using var provider = services.BuildServiceProvider();
        using var scope = provider.CreateScope();
        var context = scope.ServiceProvider.GetRequiredService<ObservationContext>();
        var connection = context.Database.GetDbConnection();
        Assert.Equal(configured, connection.ConnectionString);
        Assert.Equal(ConnectionState.Closed, connection.State);
        Assert.Equal(120, context.Database.GetCommandTimeout());
        Assert.True(context.Database.CreateExecutionStrategy().RetriesOnFailure);
        var options = scope.ServiceProvider.GetRequiredService<DbContextOptions<ObservationContext>>();
        Assert.Same(observer, Assert.Single(options.GetExtension<CoreOptionsExtension>().Interceptors!));
        Assert.Empty(journal.Stop().Events);
    }

    [Fact]
    public async Task SyncAndAsyncCallbacks_CompleteImmediatelyPreserveCancellationAndForwardCorrelation()
    {
        using var connection = new NpgsqlConnection("Host=127.0.0.1;Database=fixture");
        var journal = new ProcurementConnectionJournal();
        var observer = new ProcurementFixtureConnectionObserver(journal, "supplier", connection.ConnectionString);
        var id = Guid.NewGuid();
        var opened = new ConnectionEndEventData(null!, (_, _) => throw new InvalidOperationException("No message rendering."),
            connection, null, id, false, DateTimeOffset.UtcNow, TimeSpan.Zero);
        var failed = new ConnectionErrorEventData(null!, (_, _) => throw new InvalidOperationException("No message rendering."),
            connection, null, id, new IOException("Synthetic private message."), true, DateTimeOffset.UtcNow, TimeSpan.Zero);
        observer.ConnectionOpened(connection, opened);
        observer.ConnectionFailed(connection, failed);
        using var cancellation = new CancellationTokenSource();
        cancellation.Cancel();
        var openTask = observer.ConnectionOpenedAsync(connection, opened, cancellation.Token);
        var failureTask = observer.ConnectionFailedAsync(connection, failed, cancellation.Token);
        Assert.True(openTask.IsCompletedSuccessfully);
        Assert.True(failureTask.IsCompletedSuccessfully);
        await openTask;
        await failureTask;
        var snapshot = journal.Stop();
        Assert.Equal(new[] { "opened", "failed", "opened", "failed" }, snapshot.Events.Select(row => row.Kind));
        Assert.All(snapshot.Events, row => Assert.Equal(id, row.ConnectionId));
        Assert.All(snapshot.Events, row => Assert.Null(row.BackendProcessId));
        Assert.All(snapshot.Events.Skip(2), row => Assert.True(row.CancellationRequested));
        Assert.Equal(ConnectionState.Closed, connection.State);
        Assert.Empty(snapshot.Failures);
    }

    [Fact]
    public void ClosedConnectionFailedEvent_DoesNotOpenOrReadBackendIdentityOrExposeSecrets()
    {
        var syntheticPassword = Guid.NewGuid().ToString("N");
        var configured = new NpgsqlConnectionStringBuilder
        {
            Host = "127.0.0.1",
            Port = 32123,
            Database = "synthetic-private-db",
            Username = "synthetic-private-user",
            Password = syntheticPassword,
        }.ConnectionString;
        using var connection = new NpgsqlConnection(configured);
        var journal = new ProcurementConnectionJournal();
        var observer = new ProcurementFixtureConnectionObserver(journal, "supplier", configured);
        var id = Guid.NewGuid();
        observer.Capture(connection, "failed", id, true, true, new IOException(syntheticPassword));
        var snapshot = journal.Stop();
        var row = Assert.Single(snapshot.Events);
        Assert.Equal(ConnectionState.Closed, connection.State);
        Assert.Equal(configured, connection.ConnectionString);
        Assert.Equal(id, row.ConnectionId);
        Assert.True(row.ConfiguredEndpointMatches);
        Assert.True(row.CancellationRequested);
        Assert.True(row.IsAsync);
        Assert.False(row.Open);
        Assert.Null(row.BackendProcessId);
        Assert.Equal(nameof(IOException), row.FailureType);
        Assert.Empty(snapshot.Failures);
        var json = JsonSerializer.Serialize(snapshot.Events);
        Assert.DoesNotContain(syntheticPassword, json);
        Assert.DoesNotContain("synthetic-private", json);
        Assert.DoesNotContain("127.0.0.1", json);
    }

    [Fact]
    public void MissingOpenedCallback_IsNotInventedFromConfiguredEndpoint()
    {
        using var connection = new NpgsqlConnection("Host=127.0.0.1;Port=32123;Database=fixture");
        var journal = new ProcurementConnectionJournal();
        var observer = new ProcurementFixtureConnectionObserver(journal, "purchase-order", connection.ConnectionString);
        observer.Capture(connection, "failed", Guid.NewGuid(), false, false, new IOException());
        var snapshot = journal.Stop();
        Assert.All(snapshot.Events, row => Assert.Equal("failed", row.Kind));
        Assert.All(snapshot.Events, row => Assert.Null(row.BackendProcessId));
        Assert.Empty(snapshot.Failures);
    }

    [Fact]
    public void EventOrderAndRoleCorrelation_AreStableAndSnapshotsDetached()
    {
        var journal = new ProcurementConnectionJournal();
        var id = Guid.NewGuid();
        journal.Record("supplier", "opened", id, false, false, null, () => (true, 123, true));
        journal.Record("purchase-order", "failed", id, true, false, nameof(IOException), () => (false, null, false));
        var first = journal.Stop();
        Assert.Equal(new[] { 1, 2 }, first.Events.Select(row => row.Sequence));
        Assert.Equal(new[] { "supplier", "purchase-order" }, first.Events.Select(row => row.Role));
        Assert.True(first.Events[1].ElapsedMilliseconds >= first.Events[0].ElapsedMilliseconds);
        first.Events[0] = first.Events[1];
        Assert.Equal("supplier", journal.Stop().Events[0].Role);
    }

    [Fact]
    public void StoppedJournal_DoesNotReadProviderOrRecordLaterTestEvents()
    {
        var journal = new ProcurementConnectionJournal();
        journal.Stop();
        journal.Record("supplier", "opened", Guid.NewGuid(), true, false, null,
            () => throw new InvalidOperationException("Must not read provider after setup."));
        var snapshot = journal.Stop();
        Assert.Empty(snapshot.Events);
        Assert.Empty(snapshot.Failures);
    }

    [Fact]
    public void EventLimit_IsFailClosedAndDoesNotReadAdditionalProviderState()
    {
        var journal = new ProcurementConnectionJournal();
        for (var index = 0; index < ProcurementConnectionJournal.MaximumEvents; index++)
            journal.Record("supplier", "opened", Guid.NewGuid(), true, false, null, () => (true, 123, true));
        for (var index = 0; index < 10; index++)
            journal.Record("supplier", "opened", Guid.NewGuid(), true, false, null,
                () => throw new IOException("Must not read excess event."));
        var snapshot = journal.Stop();
        Assert.Equal(ProcurementConnectionJournal.MaximumEvents, snapshot.Events.Length);
        Assert.True(snapshot.Overflow);
        Assert.IsType<InvalidOperationException>(Assert.Single(snapshot.Failures));
    }

    [Fact]
    public async Task CaptureFailures_RetainEveryOriginalAndAllowPrimaryAndCleanupCustody()
    {
        var journal = new ProcurementConnectionJournal();
        var first = new IOException("Identical synthetic capture failure.");
        var second = new IOException("Identical synthetic capture failure.");
        var primary = new IOException("Synthetic migration failure.");
        var cleanup = new IOException("Synthetic cleanup failure.");
        journal.Record("supplier", "opened", Guid.NewGuid(), true, false, null, () => throw first);
        journal.Record("supplier", "opened", Guid.NewGuid(), true, false, null, () => throw second);
        var snapshot = journal.Stop();
        Assert.Equal(2, snapshot.Events.Length);
        var actual = await Assert.ThrowsAsync<AggregateException>(() => ProcurementDurableFixtureFailureCompletion.CompleteAsync(
            [primary], snapshot.Failures, onlyObserver => Assert.False(onlyObserver),
            () => Task.CompletedTask, () => Task.FromException(cleanup)));
        Assert.Collection(actual.InnerExceptions, error => Assert.Same(primary, error),
            error => Assert.Same(first, error), error => Assert.Same(second, error), error => Assert.Same(cleanup, error));
    }

    private sealed class ObservationContext(DbContextOptions<ObservationContext> options) : DbContext(options);
}

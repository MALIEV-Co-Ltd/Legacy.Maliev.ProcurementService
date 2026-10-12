using System.Text;
using System.Text.Json;
using Microsoft.Extensions.Time.Testing;

namespace Legacy.Maliev.ProcurementService.Tests.Integration;

public sealed class ProcurementFixtureStartupJournalTests
{
    [Fact]
    public async Task SharedPendingPublication_SecondCleanupCallerObservesSameTaskAndLateOriginalFailure()
    {
        var owner = new ProcurementFixtureStartupPublicationOwner();
        var entered = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var release = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var late = new IOException("Synthetic late publication failure.");
        var invoked = 0;
        var first = owner.GetOrStart(() => ProcurementFixtureStartupPublication.PublishAsync(async _ =>
        {
            invoked++;
            entered.TrySetResult();
            await release.Task;
            throw late;
        }, [], CancellationToken.None));
        await entered.Task.WaitAsync(TimeSpan.FromSeconds(2));
        var second = owner.GetOrStart(() => throw new InvalidOperationException("Publication must not be restarted."));
        Assert.Same(first, second);
        Assert.False(second.IsCompleted);
        var clock = new FakeTimeProvider();
        var lifetime = new ProcurementFixtureLifetime(clock);
        var hostEntered = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var cleaned = 0;
        var callback = ProcurementFixtureStartupPublication.CleanupAsync(() => second, () =>
        {
            cleaned++;
            hostEntered.TrySetResult();
            return Task.CompletedTask;
        });
        var cleanup = lifetime.CleanupAsync(() => callback,
            () => { cleaned++; return Task.CompletedTask; },
            () => { cleaned++; return Task.CompletedTask; },
            () => { cleaned++; return Task.CompletedTask; });
        try
        {
            await hostEntered.Task.WaitAsync(TimeSpan.FromSeconds(2));
            clock.Advance(ProcurementFixtureLifetime.CleanupDeadline + TimeSpan.FromSeconds(1));
            await Assert.ThrowsAsync<TimeoutException>(() => cleanup);
            Assert.Equal(4, cleaned);
            Assert.Contains(callback, lifetime.UnsettledOperations);
            Assert.False(first.IsCompleted);
        }
        finally { release.TrySetResult(); }
        Assert.Same(late, await Assert.ThrowsAsync<IOException>(() => first));
        Assert.Same(late, await Assert.ThrowsAsync<IOException>(() => second));
        Assert.Same(late, await Assert.ThrowsAsync<IOException>(() => callback));
        Assert.Same(first, owner.GetOrStart(() => Task.CompletedTask));
        Assert.Contains(lifetime.ObservedFailures, error => ReferenceEquals(error, late));
        Assert.Empty(lifetime.UnsettledOperations);
        Assert.Equal(1, invoked);
    }

    [Fact]
    public async Task SharedPublication_SuccessAndSynchronousFailureAreRetainedWithoutRestart()
    {
        var success = new ProcurementFixtureStartupPublicationOwner();
        var first = success.GetOrStart(() => Task.CompletedTask);
        await first;
        Assert.Same(first, success.GetOrStart(() => throw new IOException("Must not run.")));
        var failure = new ProcurementFixtureStartupPublicationOwner();
        var original = new IOException("Synthetic synchronous publisher refusal.");
        var refused = failure.GetOrStart(() => throw original);
        Assert.Same(original, await Assert.ThrowsAsync<IOException>(() => refused));
        var again = failure.GetOrStart(() => Task.CompletedTask);
        Assert.Same(refused, again);
        Assert.Same(original, await Assert.ThrowsAsync<IOException>(() => again));
    }

    [Fact]
    public async Task BlockedPublication_OriginalCleanupBudgetStillReleasesHostAndEveryOtherResource()
    {
        var clock = new FakeTimeProvider();
        var lifetime = new ProcurementFixtureLifetime(clock);
        var entered = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var hostEntered = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var release = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var publication = ProcurementFixtureStartupPublication.PublishAsync(_ =>
        {
            entered.TrySetResult();
            return release.Task; // Deliberately uncooperative storage: timeout is not settlement.
        }, [], CancellationToken.None);
        var cleaned = 0;
        var first = ProcurementFixtureStartupPublication.CleanupAsync(() => publication, () =>
        {
            cleaned++;
            hostEntered.TrySetResult();
            return Task.CompletedTask;
        });
        var all = lifetime.CleanupAsync(() => first,
            () => { cleaned++; return Task.CompletedTask; },
            () => { cleaned++; return Task.CompletedTask; },
            () => { cleaned++; return Task.CompletedTask; });
        try
        {
            await Task.WhenAll(entered.Task, hostEntered.Task).WaitAsync(TimeSpan.FromSeconds(2));
            clock.Advance(ProcurementFixtureLifetime.CleanupDeadline + TimeSpan.FromSeconds(1));
            await Assert.ThrowsAsync<TimeoutException>(() => all);
            Assert.Equal(4, cleaned);
            Assert.Contains(first, lifetime.UnsettledOperations);
        }
        finally { release.TrySetResult(); await first; }
        Assert.Equal(4, cleaned);
        Assert.Empty(lifetime.UnsettledOperations);
    }

    [Fact]
    public async Task PublicationRefusalAndHostFailure_RetainBothOriginalsFromActualCallbackSeam()
    {
        var publication = new IOException("Synthetic publication refusal.");
        var host = new InvalidOperationException("Synthetic host failure.");
        var invoked = false;
        var actual = await Assert.ThrowsAsync<AggregateException>(() => ProcurementFixtureStartupPublication.CleanupAsync(
            () => ProcurementFixtureStartupPublication.PublishAsync(_ => throw publication, [], CancellationToken.None),
            () => { invoked = true; throw host; }));
        Assert.True(invoked);
        Assert.Equal(new Exception[] { publication, host }, actual.InnerExceptions);
    }

    [Fact]
    public async Task PublicationAndHostCancellation_RetainBothOriginalTokensFromActualCallbackSeam()
    {
        using var first = new CancellationTokenSource();
        using var second = new CancellationTokenSource();
        first.Cancel();
        second.Cancel();
        var publication = new OperationCanceledException(first.Token);
        var host = new OperationCanceledException(second.Token);
        var actual = await Assert.ThrowsAsync<AggregateException>(() => ProcurementFixtureStartupPublication.CleanupAsync(
            () => ProcurementFixtureStartupPublication.PublishAsync(_ => throw publication, [], first.Token), () => throw host));
        Assert.Equal(new Exception[] { publication, host }, actual.InnerExceptions);
        Assert.Equal(first.Token, publication.CancellationToken);
        Assert.Equal(second.Token, host.CancellationToken);
    }

    [Fact]
    public async Task SynchronousFirstThrow_DoesNotPreventSecondInvocationAndRetainsOriginal()
    {
        var journal = new ProcurementFixtureStartupJournal();
        var first = new IOException("Synthetic original.");
        var invoked = false;
        var supplier = journal.StartAsync("supplier", () => throw first, CancellationToken.None);
        var order = journal.StartAsync("purchase-order", () => { invoked = true; return Task.CompletedTask; }, CancellationToken.None);
        Assert.Same(first, await Assert.ThrowsAsync<IOException>(() => Task.WhenAll(supplier, order)));
        Assert.True(invoked);
        Assert.Empty(journal.Stop().Failures);
    }

    [Fact]
    public async Task ConcurrentStarts_DoNotGateSecondInvocationOnFirstSettlement()
    {
        var journal = new ProcurementFixtureStartupJournal();
        var release = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var supplier = journal.StartAsync("supplier", () => release.Task, CancellationToken.None);
        var invoked = false;
        var order = journal.StartAsync("purchase-order", () => { invoked = true; return Task.CompletedTask; }, CancellationToken.None);
        try { Assert.True(invoked); Assert.False(supplier.IsCompleted); }
        finally { release.TrySetResult(); await Task.WhenAll(supplier, order); }
    }

    [Fact]
    public async Task BothAsynchronousFailures_RetainEveryOriginal()
    {
        var journal = new ProcurementFixtureStartupJournal();
        var first = new IOException("Synthetic first.");
        var second = new InvalidOperationException("Synthetic second.");
        var starts = Task.WhenAll(journal.StartAsync("supplier", () => Task.FromException(first), CancellationToken.None),
            journal.StartAsync("purchase-order", () => Task.FromException(second), CancellationToken.None));
        await Record.ExceptionAsync(() => starts);
        Assert.Equal(new Exception[] { first, second }, starts.Exception!.InnerExceptions);
    }

    [Fact]
    public async Task Cancellation_PreservesOriginalExceptionTokenAndCanceledTask()
    {
        var journal = new ProcurementFixtureStartupJournal();
        using var cancellation = new CancellationTokenSource();
        cancellation.Cancel();
        var original = new OperationCanceledException(cancellation.Token);
        var task = journal.StartAsync("supplier", () => throw original, cancellation.Token);
        Assert.Same(original, await Assert.ThrowsAsync<OperationCanceledException>(() => task));
        Assert.True(task.IsCanceled);
        Assert.True(journal.Stop().Events.Last().CancellationRequested);
    }

    [Fact]
    public void CallbackObservationFailure_IsRetainedWithoutThrowingIntoProvider()
    {
        var journal = new ProcurementFixtureStartupJournal();
        var original = new IOException("Synthetic metadata failure.");
        journal.Record("supplier", "provider-created-inspected", () => throw original);
        Assert.Same(original, Assert.Single(journal.Stop().Failures));
    }

    [Fact]
    public Task MixedFaultAndCancellation_RetainBothOriginalsAndTokenThroughEveryCleanup()
        => AssertOriginalOutcomeCustodyAsync(false);

    [Fact]
    public Task TwoCanceledStarts_RetainBothOriginalsAndDistinctTokensThroughEveryCleanup()
        => AssertOriginalOutcomeCustodyAsync(true);

    private static async Task AssertOriginalOutcomeCustodyAsync(bool bothCanceled)
    {
        using var firstCancellation = new CancellationTokenSource();
        using var secondCancellation = new CancellationTokenSource();
        firstCancellation.Cancel();
        secondCancellation.Cancel();
        Exception first = bothCanceled ? new OperationCanceledException(firstCancellation.Token) : new IOException("Synthetic fault.");
        var second = new OperationCanceledException(secondCancellation.Token);
        var journal = new ProcurementFixtureStartupJournal();
        var observation = new IOException("Synthetic observation.");
        var publication = new UnauthorizedAccessException("Synthetic publication.");
        var cleanup = new IOException("Synthetic cleanup.");
        journal.Record("supplier", "provider-created-inspected", () => throw observation);
        var lifetime = new ProcurementFixtureLifetime();
        var cleaned = 0;
        var releaseSecond = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        async Task CancelSecondAsync() { await releaseSecond.Task; throw second; }
        var actual = await Assert.ThrowsAsync<AggregateException>(() => lifetime.InitializeAsync(async _ =>
        {
            var supplier = journal.StartAsync("supplier", () => throw first, firstCancellation.Token);
            var order = journal.StartAsync("purchase-order", CancelSecondAsync, secondCancellation.Token);
            // Stop must not discard originals, including later canceled completions.
            var snapshot = journal.Stop();
            releaseSecond.TrySetResult();
            try { await Task.WhenAll(supplier, order); }
            catch
            {
                var originals = journal.OriginalFailures.ToList();
                Assert.Equal(new[] { first, second }, originals);
                try { ProcurementFixtureDiagnosticFailures.PublishOrThrow(() => throw publication, snapshot.Failures); }
                catch (Exception failure) { originals.Add(failure); }
                throw new AggregateException(originals);
            }
        }, () => lifetime.CleanupAsync(Enumerable.Range(0, 4).Select(index => new Func<Task>(() =>
        {
            cleaned++;
            return index == 1 ? Task.FromException(cleanup) : Task.CompletedTask;
        })).ToArray()), TimeSpan.FromSeconds(2)));
        Assert.Equal(4, cleaned);
        var errors = actual.Flatten().InnerExceptions;
        foreach (var expected in new[] { first, second, observation, publication, cleanup })
            Assert.Contains(errors, error => ReferenceEquals(expected, error));
        Assert.Equal(secondCancellation.Token, second.CancellationToken);
        if (bothCanceled) Assert.Equal(firstCancellation.Token, ((OperationCanceledException)first).CancellationToken);
        Assert.Empty(lifetime.UnsettledOperations);
    }

    [Fact]
    public async Task ConcurrentJournalWrites_HaveUniqueMonotonicSequenceAndDetachedSnapshots()
    {
        var journal = new ProcurementFixtureStartupJournal();
        await Task.WhenAll(Enumerable.Range(0, 16).Select(_ => Task.Run(() => journal.Record("supplier", "provider-creating"))));
        var snapshot = journal.Stop();
        Assert.Equal(Enumerable.Range(1, 16), snapshot.Events.Select(item => item.Sequence));
        Assert.True(snapshot.Events.Zip(snapshot.Events.Skip(1)).All(pair => pair.First.ElapsedTicks <= pair.Second.ElapsedTicks));
        snapshot.Events[0] = snapshot.Events[0] with { Phase = "changed" };
        Assert.Equal("provider-creating", journal.Stop().Events[0].Phase);
        Assert.Empty(snapshot.Failures);
    }

    [Fact]
    public void OverflowFailsClosedAndStoppedJournalDoesNotReadLaterProviderState()
    {
        var journal = new ProcurementFixtureStartupJournal();
        for (var index = 0; index < 32; index++) journal.Record("supplier", "provider-creating");
        var reads = 0;
        journal.Record("supplier", "provider-created-inspected", () => { reads++; return new string('a', 64); });
        var snapshot = journal.Stop();
        journal.Record("supplier", "provider-created-inspected", () => { reads++; return new string('a', 64); });
        Assert.Equal(0, reads);
        Assert.True(snapshot.Overflow);
        Assert.Single(snapshot.Failures);
        Assert.Equal(32, snapshot.Events.Length);
        var invalid = new ProcurementFixtureStartupJournal();
        for (var index = 0; index < 100; index++) invalid.Record("unknown", "provider-creating");
        Assert.Equal(33, invalid.Stop().Failures.Length);
    }

    [Fact]
    public void UnknownRolePhaseAndPartialId_AreErrorsAndNeverInventMissingEvents()
    {
        var journal = new ProcurementFixtureStartupJournal();
        journal.Record("other", "provider-creating");
        journal.Record("supplier", "docker-start-call");
        journal.Record("supplier", "provider-created-inspected", () => new string('a', 12));
        journal.Record("supplier", "provider-creating");
        var snapshot = journal.Stop();
        Assert.Equal(3, snapshot.Failures.Length);
        Assert.Null(Assert.Single(snapshot.Events).ContainerId);
    }

    [Fact]
    public void ReceiptAllowlist_ExcludesOriginalErrorMessageAndMarksApiTimingUnknown()
    {
        var journal = new ProcurementFixtureStartupJournal();
        var privateValue = Guid.NewGuid().ToString("N");
        journal.Record("supplier", "wrapper-settled", failure: new IOException(privateValue));
        var snapshot = journal.Stop();
        var bytes = ProcurementFixtureStartupJournal.Serialize(Guid.NewGuid().ToString("N"), Guid.NewGuid().ToString("N"), snapshot.Events, false);
        var text = Encoding.UTF8.GetString(bytes);
        Assert.DoesNotContain(privateValue, text);
        using var parsed = JsonDocument.Parse(bytes);
        Assert.Equal(11, parsed.RootElement.EnumerateObject().Count());
        Assert.Equal(8, parsed.RootElement.GetProperty("Events")[0].EnumerateObject().Count());
        Assert.False(parsed.RootElement.GetProperty("ExactDockerApiTiming").GetBoolean());
        Assert.True(bytes.Length <= ProcurementFixtureStartupJournal.MaximumBytes);
    }

    [Fact]
    public void ForgedReceiptMetadataAndUnboundedEvents_AreRejected()
    {
        var run = Guid.NewGuid().ToString("N");
        var item = new ProcurementStartupEvent(1, 0, DateTimeOffset.UtcNow, "supplier", "provider-creating", null, null, null);
        Assert.Throws<InvalidOperationException>(() => ProcurementFixtureStartupJournal.Serialize("invalid", run, [item], false));
        Assert.Throws<InvalidOperationException>(() => ProcurementFixtureStartupJournal.Serialize(run, run, [item with { FailureType = "unsafe\nvalue" }], false));
        Assert.Throws<InvalidOperationException>(() => ProcurementFixtureStartupJournal.Serialize(run, run, [item with { Sequence = 2 }], false));
        Assert.Throws<InvalidOperationException>(() => ProcurementFixtureStartupJournal.Serialize(run, run, [item with { Phase = "provider-created-inspected" }], false));
        Assert.Throws<InvalidOperationException>(() => ProcurementFixtureStartupJournal.Serialize(run, run, [item with { ContainerId = new string('a', 64) }], false));
        Assert.Throws<InvalidOperationException>(() => ProcurementFixtureStartupJournal.Serialize(run, run, Enumerable.Repeat(item, 33).ToArray(), false));
    }

    [Fact]
    public async Task ObserverOnlyFailureAfterSuccessfulStarts_StillRunsEveryCleanup()
    {
        var journal = new ProcurementFixtureStartupJournal();
        var original = new IOException("Synthetic observer.");
        journal.Record("supplier", "provider-created-inspected", () => throw original);
        var cleaned = 0;
        var lifetime = new ProcurementFixtureLifetime();
        var actual = await Assert.ThrowsAsync<IOException>(() => lifetime.InitializeAsync(async _ =>
        {
            await Task.WhenAll(journal.StartAsync("supplier", () => Task.CompletedTask, CancellationToken.None),
                journal.StartAsync("purchase-order", () => Task.CompletedTask, CancellationToken.None));
            ProcurementFixtureDiagnosticFailures.PublishOrThrow(() => { }, journal.Stop().Failures);
        }, () => lifetime.CleanupAsync(Enumerable.Range(0, 4).Select(_ => new Func<Task>(() => { cleaned++; return Task.CompletedTask; })).ToArray()), TimeSpan.FromSeconds(2)));
        Assert.Same(original, actual);
        Assert.Equal(4, cleaned);
        Assert.Empty(lifetime.UnsettledOperations);
    }

    [Fact]
    public async Task PrimaryObserverPublicationAndAllCleanupErrors_RetainOriginalReferences()
    {
        var primary = new IOException("Synthetic primary.");
        var observer = new InvalidOperationException("Synthetic observer.");
        var publication = new UnauthorizedAccessException("Synthetic publication.");
        var releases = Enumerable.Range(0, 4).Select(_ => new IOException("Synthetic cleanup.")).ToArray();
        var lifetime = new ProcurementFixtureLifetime();
        var attempted = 0;
        var actual = await Assert.ThrowsAsync<AggregateException>(() => lifetime.InitializeAsync(_ =>
        {
            ProcurementFixtureDiagnosticFailures.PublishOrThrow(() => throw publication, [primary, observer]);
            return Task.CompletedTask;
        }, () => lifetime.CleanupAsync(releases.Select(error => new Func<Task>(() => { attempted++; throw error; })).ToArray()), TimeSpan.FromSeconds(2)));
        Assert.Equal(4, attempted);
        var originals = actual.Flatten().InnerExceptions;
        foreach (var expected in new Exception[] { primary, observer, publication }.Concat(releases))
            Assert.Contains(originals, item => ReferenceEquals(item, expected));
        Assert.Empty(lifetime.UnsettledOperations);
    }
}

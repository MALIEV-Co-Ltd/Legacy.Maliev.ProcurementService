using Docker.DotNet.Models;
using Microsoft.Extensions.Time.Testing;

namespace Legacy.Maliev.ProcurementService.Tests.Integration;

public sealed class ProcurementFixtureLifetimeTests
{
    [Theory]
    [InlineData(0)]
    [InlineData(1)]
    [InlineData(2)]
    [InlineData(3)]
    public async Task CleanupFailure_StillAttemptsAllFourOwnedReleases(int position)
    {
        var lifetime = new ProcurementFixtureLifetime();
        var released = new List<int>();
        var expected = new IOException("Synthetic release failure.");
        var releases = Enumerable.Range(0, 4).Select(index => new Func<Task>(() =>
        {
            released.Add(index);
            return index == position ? Task.FromException(expected) : Task.CompletedTask;
        })).ToArray();
        var actual = await Assert.ThrowsAsync<IOException>(() => lifetime.CleanupAsync(releases));
        Assert.Same(expected, actual);
        Assert.Equal([0, 1, 2, 3], released);
        Assert.Empty(lifetime.UnsettledOperations);
    }

    [Fact]
    public async Task MultipleCleanupFailures_RetainEveryOriginalException()
    {
        var lifetime = new ProcurementFixtureLifetime();
        var first = new IOException("Synthetic first failure.");
        var second = new InvalidOperationException("Synthetic second failure.");
        var lastReleased = false;
        var actual = await Assert.ThrowsAsync<AggregateException>(() => lifetime.CleanupAsync(
            () => Task.FromException(first), () => throw second,
            () => { lastReleased = true; return Task.CompletedTask; }));
        Assert.Equal(new Exception[] { first, second }, actual.InnerExceptions);
        Assert.True(lastReleased);
        Assert.Empty(lifetime.UnsettledOperations);
    }

    [Fact]
    public async Task SuccessfulCleanup_ReleasesAllAndLeavesNoPendingHandles()
    {
        var lifetime = new ProcurementFixtureLifetime();
        var released = 0;
        await lifetime.CleanupAsync(() => { released++; return Task.CompletedTask; }, () => { released++; return Task.CompletedTask; });
        Assert.Equal(2, released);
        Assert.Empty(lifetime.UnsettledOperations);
        Assert.Empty(lifetime.ObservedFailures);
    }

    [Fact]
    public async Task SetupFailure_PreservesPrimaryAndRunsCleanup()
    {
        var lifetime = new ProcurementFixtureLifetime();
        var primary = new IOException("Synthetic setup failure.");
        var cleaned = false;
        var actual = await Assert.ThrowsAsync<IOException>(() => lifetime.InitializeAsync(_ => Task.FromException(primary),
            () => { cleaned = true; return Task.CompletedTask; }, TimeSpan.FromMinutes(2)));
        Assert.Same(primary, actual);
        Assert.True(cleaned);
        Assert.Empty(lifetime.UnsettledOperations);
    }

    [Fact]
    public async Task SetupAndCleanupFailures_RetainPrimaryAndBothCleanupErrors()
    {
        var lifetime = new ProcurementFixtureLifetime();
        var primary = new IOException("Synthetic setup failure.");
        var first = new InvalidOperationException("Synthetic host release failure.");
        var second = new IOException("Synthetic container release failure.");
        var actual = await Assert.ThrowsAsync<AggregateException>(() => lifetime.InitializeAsync(_ => Task.FromException(primary),
            () => lifetime.CleanupAsync(() => Task.FromException(first), () => Task.FromException(second)), TimeSpan.FromMinutes(2)));
        Assert.Equal(new Exception[] { primary, first, second }, actual.InnerExceptions);
    }

    [Fact]
    public async Task SynchronousSetupFailure_StillRunsCleanup()
    {
        var lifetime = new ProcurementFixtureLifetime();
        var expected = new InvalidOperationException("Synthetic synchronous setup failure.");
        var cleaned = false;
        var actual = await Assert.ThrowsAsync<InvalidOperationException>(() => lifetime.InitializeAsync(_ => throw expected,
            () => { cleaned = true; return Task.CompletedTask; }, TimeSpan.FromMinutes(2)));
        Assert.Same(expected, actual);
        Assert.True(cleaned);
    }

    [Fact]
    public async Task InitializationDeadline_CancelsCooperatingWorkAndCleansUp()
    {
        var clock = new SignaledClock();
        var lifetime = new ProcurementFixtureLifetime(clock);
        var canceled = new TaskCompletionSource();
        var cleaned = false;
        var initialization = lifetime.InitializeAsync(async token =>
        {
            try { await Task.Delay(Timeout.InfiniteTimeSpan, token); }
            catch (OperationCanceledException error) when (token.IsCancellationRequested && error.CancellationToken == token)
            {
                canceled.TrySetResult();
                throw;
            }
        }, () => { cleaned = true; return Task.CompletedTask; }, TimeSpan.FromMinutes(2));
        await clock.TimerCreated.Task;
        clock.Advance(TimeSpan.FromMinutes(2));
        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => initialization);
        Assert.True(canceled.Task.IsCompletedSuccessfully);
        Assert.True(cleaned);
        Assert.Empty(lifetime.UnsettledOperations);

        // Disposing a registration before dispatch suppresses its callback while the awaited
        // operation still observes cancellation. That callback is not the work-settlement oracle.
        using var replay = new CancellationTokenSource();
        var callbackReached = false;
        var registration = replay.Token.Register(() => callbackReached = true);
        var delay = Task.Delay(Timeout.InfiniteTimeSpan, replay.Token);
        registration.Dispose();
        replay.Cancel();
        var replayFailure = await Assert.ThrowsAnyAsync<OperationCanceledException>(() => delay);
        Assert.Equal(replay.Token, replayFailure.CancellationToken);
        Assert.False(callbackReached);
    }

    [Fact]
    public async Task CleanupTimeout_AttemptsNextReleaseAndRetainsUnfinishedHandleAndLateFault()
    {
        var clock = new SignaledClock();
        var lifetime = new ProcurementFixtureLifetime(clock);
        var unfinished = new TaskCompletionSource();
        var nextReleased = false;
        var cleanup = lifetime.CleanupAsync(() => unfinished.Task, () => { nextReleased = true; return Task.CompletedTask; });
        await clock.TimerCreated.Task;
        clock.Advance(ProcurementFixtureLifetime.CleanupDeadline);
        await Assert.ThrowsAsync<TimeoutException>(() => cleanup);
        Assert.True(nextReleased);
        Assert.Contains(unfinished.Task, lifetime.UnsettledOperations);
        var late = new IOException("Synthetic late cleanup fault.");
        unfinished.SetException(late);
        await Assert.ThrowsAsync<IOException>(() => unfinished.Task);
        Assert.Empty(lifetime.UnsettledOperations);
        Assert.Contains(late, lifetime.ObservedFailures);
    }

    [Fact]
    public async Task SetupThatIgnoresCancellation_IsReportedUnsettledAfterBoundedCleanup()
    {
        var clock = new SignaledClock();
        var lifetime = new ProcurementFixtureLifetime(clock);
        var unfinished = new TaskCompletionSource();
        var cleaned = false;
        var initialization = lifetime.InitializeAsync(_ => unfinished.Task,
            () => { cleaned = true; return Task.CompletedTask; }, TimeSpan.FromMinutes(2));
        await clock.TimerCreated.Task;
        clock.ResetSignal();
        clock.Advance(TimeSpan.FromMinutes(2));
        await clock.TimerCreated.Task;
        clock.Advance(ProcurementFixtureLifetime.CleanupDeadline);
        var actual = await Assert.ThrowsAsync<AggregateException>(() => initialization);
        Assert.IsAssignableFrom<OperationCanceledException>(actual.InnerExceptions[0]);
        Assert.IsType<TimeoutException>(actual.InnerExceptions[1]);
        Assert.True(cleaned);
        Assert.Contains(unfinished.Task, lifetime.UnsettledOperations);
        unfinished.SetResult();
        Assert.Empty(lifetime.UnsettledOperations);
    }

    [Fact]
    public async Task SuccessfulSetup_DoesNotInvokeFailureCleanup()
    {
        var lifetime = new ProcurementFixtureLifetime();
        await lifetime.InitializeAsync(_ => Task.CompletedTask, () => throw new InvalidOperationException("Unexpected cleanup."), TimeSpan.FromMinutes(2));
        Assert.Empty(lifetime.UnsettledOperations);
    }

    [Fact]
    public async Task CancellationCallbackFailure_DoesNotLosePrimaryOrSkipCleanup()
    {
        var lifetime = new ProcurementFixtureLifetime();
        var primary = new IOException("Synthetic setup failure.");
        var cancellationFailure = new InvalidOperationException("Synthetic cancellation callback failure.");
        var cleaned = false;
        var actual = await Assert.ThrowsAsync<AggregateException>(() => lifetime.InitializeAsync(token =>
        {
            token.Register(() => throw cancellationFailure);
            return Task.FromException(primary);
        }, () => { cleaned = true; return Task.CompletedTask; }, TimeSpan.FromMinutes(2)));
        Assert.Same(primary, actual.InnerExceptions[0]);
        Assert.Contains(cancellationFailure, actual.Flatten().InnerExceptions);
        Assert.True(cleaned);
    }

    [Fact]
    public void ContainerPolicy_BoundsMemoryCpuLoopbackAndPreservesPostgresArguments()
    {
        string[] command = ["-c", "fsync=off", "-c", "full_page_writes=off", "-c", "synchronous_commit=off"];
        var parameters = new CreateContainerParameters
        {
            Cmd = command,
            HostConfig = new HostConfig { PortBindings = new Dictionary<string, IList<PortBinding>> { ["5432/tcp"] = [new PortBinding { HostIP = "0.0.0.0", HostPort = "12345" }] } },
        };
        ProcurementFixtureContainerPolicy.Apply(parameters);
        Assert.Equal(ProcurementFixtureContainerPolicy.MemoryBytes, parameters.HostConfig.Memory);
        Assert.Equal(parameters.HostConfig.Memory, parameters.HostConfig.MemorySwap);
        Assert.Equal(ProcurementFixtureContainerPolicy.NanoCpus, parameters.HostConfig.NanoCPUs);
        Assert.Equal("127.0.0.1", parameters.HostConfig.PortBindings["5432/tcp"].Single().HostIP);
        Assert.Equal(command, parameters.Cmd);
        Assert.Equal(new[] { "sh", "-c", "exec timeout --signal=INT --kill-after=10s 1800 docker-entrypoint.sh \"$@\"", "procurement-owned-fixture" }, parameters.Entrypoint);
    }

    private sealed class SignaledClock : TimeProvider
    {
        private readonly FakeTimeProvider inner = new();
        internal TaskCompletionSource TimerCreated { get; private set; } = new(TaskCreationOptions.RunContinuationsAsynchronously);
        internal void ResetSignal() => TimerCreated = new(TaskCreationOptions.RunContinuationsAsynchronously);
        internal void Advance(TimeSpan amount) => inner.Advance(amount);
        public override DateTimeOffset GetUtcNow() => inner.GetUtcNow();
        public override long GetTimestamp() => inner.GetTimestamp();
        public override long TimestampFrequency => inner.TimestampFrequency;
        public override ITimer CreateTimer(TimerCallback callback, object? state, TimeSpan dueTime, TimeSpan period)
        {
            var timer = inner.CreateTimer(callback, state, dueTime, period);
            TimerCreated.TrySetResult();
            return timer;
        }
    }
}

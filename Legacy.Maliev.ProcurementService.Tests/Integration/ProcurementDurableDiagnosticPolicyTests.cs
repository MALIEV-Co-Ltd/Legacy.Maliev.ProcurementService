using System.Text;
using System.Text.Json;

using Docker.DotNet;
using Docker.DotNet.Models;

using Microsoft.Extensions.Time.Testing;

using Moq;

namespace Legacy.Maliev.ProcurementService.Tests.Integration;

public sealed class ProcurementDurableDiagnosticPolicyTests
{
    [Fact]
    public void DiagnosticPolicy_PreservesArgumentsAndBoundsActualCreateParameters()
    {
        string[] command = ["-c", "fsync=off"];
        var parameters = new CreateContainerParameters
        {
            Cmd = command,
            HostConfig = new HostConfig { PortBindings = new Dictionary<string, IList<PortBinding>>
            {
                ["5432/tcp"] = [new PortBinding { HostIP = "0.0.0.0", HostPort = "12345" }],
            } },
        };
        ProcurementDurableDiagnosticContainerPolicy.Apply(parameters);
        Assert.Equal(command, parameters.Cmd);
        Assert.Equal(1073741824, parameters.HostConfig.Memory);
        Assert.Equal(parameters.HostConfig.Memory, parameters.HostConfig.MemorySwap);
        Assert.Equal(750000000, parameters.HostConfig.NanoCPUs);
        Assert.Equal("127.0.0.1", parameters.HostConfig.PortBindings["5432/tcp"].Single().HostIP);
        Assert.Equal("exec timeout --signal=INT --kill-after=10s 1800 docker-entrypoint.sh \"$@\"", parameters.Entrypoint[2]);
        Assert.Equal("procurement-durable-diagnostic-fixture", parameters.Entrypoint[3]);
    }

    [Fact]
    public void DiagnosticEndpoint_RejectsRemoteAndUnsupportedEndpoints()
    {
        Assert.Equal("unix:///var/run/docker.sock", ProcurementDurableDiagnosticContainerPolicy.Endpoint(null, false, true));
        Assert.Equal("npipe://./pipe/docker_engine", ProcurementDurableDiagnosticContainerPolicy.Endpoint(null, true, false));
        Assert.Throws<InvalidOperationException>(() => ProcurementDurableDiagnosticContainerPolicy.Endpoint("tcp://remote.invalid:2375", false, true));
        Assert.Throws<PlatformNotSupportedException>(() => ProcurementDurableDiagnosticContainerPolicy.Endpoint(null, false, false));
    }

    [Fact]
    public async Task Initialization_PreservesFirstFailureObservesBeforeCleanupAndRetainsAllFailures()
    {
        var owner = new ProcurementDurableDiagnosticInitialization();
        var primary = new IOException("Synthetic primary.");
        var observation = new InvalidOperationException("Synthetic observation.");
        var release = new IOException("Synthetic release.");
        var order = new List<string>();
        var actual = await Assert.ThrowsAsync<AggregateException>(() => owner.RunAsync(_ => Task.FromException(primary),
            failures => { Assert.Same(primary, failures.First()); order.Add("observe"); throw observation; },
            () => { order.Add("cleanup"); throw release; }));
        Assert.Same(primary, actual.InnerExceptions[0]);
        Assert.Contains(observation, actual.InnerExceptions);
        Assert.Contains(release, actual.InnerExceptions);
        Assert.Equal(["observe", "cleanup"], order);
        Assert.Empty(owner.UnsettledOperations);
    }

    [Fact]
    public async Task Initialization_SynchronousAllocationFailureStillObservesAndCleans()
    {
        var owner = new ProcurementDurableDiagnosticInitialization();
        var primary = new IOException("Synthetic allocation.");
        var cleaned = false;
        var actual = await Assert.ThrowsAsync<IOException>(() => owner.RunAsync(_ => throw primary,
            failures => { Assert.Same(primary, failures.Single()); return Task.CompletedTask; },
            () => { cleaned = true; return Task.CompletedTask; }));
        Assert.Same(primary, actual);
        Assert.True(cleaned);
    }

    [Fact]
    public async Task Initialization_UnsettledWorkIsReportedAndLateFaultRemainsOwned()
    {
        var clock = new SignaledClock();
        var owner = new ProcurementDurableDiagnosticInitialization(clock);
        var pending = new TaskCompletionSource();
        var entered = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var cleaned = false;
        var observedUnsettled = false;
        var run = owner.RunAsync(cancellationToken => { _ = owner.Track(pending.Task); entered.SetResult(); return pending.Task; },
            _ => { observedUnsettled = owner.UnsettledOperations.Contains(pending.Task); return Task.CompletedTask; },
            () => { cleaned = true; return Task.CompletedTask; });
        await entered.Task;
        await clock.TimerCreated.Task;
        clock.ResetSignal();
        clock.Advance(TimeSpan.FromMinutes(2));
        await clock.TimerCreated.Task;
        clock.Advance(TimeSpan.FromSeconds(30));
        await Assert.ThrowsAsync<AggregateException>(() => run);
        Assert.True(cleaned);
        Assert.True(observedUnsettled);
        Assert.Contains(pending.Task, owner.UnsettledOperations);
        var late = new IOException("Synthetic late fault.");
        var owned = owner.UnsettledOperations.ToArray();
        pending.SetException(late);
        await Assert.ThrowsAsync<IOException>(() => pending.Task);
        await Assert.ThrowsAsync<IOException>(() => Task.WhenAll(owned));
        // Join actual owned handles, not an arbitrary polling loop.
        Assert.Empty(owner.UnsettledOperations);
        Assert.Contains(late, owner.ObservedFailures);
    }

    [Fact]
    public async Task Initialization_TwoTrackedStartsRetainFailureWhileOtherSettles()
    {
        var owner = new ProcurementDurableDiagnosticInitialization();
        var first = new IOException("Synthetic first start.");
        var second = new IOException("Synthetic second start.");
        var other = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var run = owner.RunAsync(async cancellationToken =>
        {
            _ = owner.Track(other.Task);
            await owner.Track(Task.FromException(first));
        }, failures => { Assert.Contains(first, failures); Assert.Contains(second, failures); return Task.CompletedTask; },
            () => Task.CompletedTask);
        other.SetException(second);
        var actual = await Assert.ThrowsAsync<AggregateException>(() => run);
        Assert.Contains(first, actual.InnerExceptions);
        Assert.Contains(second, actual.InnerExceptions);
        Assert.Empty(owner.UnsettledOperations);
    }

    [Fact]
    public void ServerCategories_DoNotPersistSecretSqlOrUnclassifiedMessages()
    {
        const string privateText = "SELECT private_customer; password=never-persist; token=secret";
        var category = ProcurementDurableServerLogObserver.Classify(privateText
            + "\n2026-10-12 04:04:34 UTC [94] LOG:  received fast shutdown request\n"
            + "2026-10-12 04:04:34 UTC [94] FATAL:  " + privateText + "\n");
        Assert.Equal(ProcurementServerLogCategory.ShutdownRequested, category);
        var json = JsonSerializer.Serialize(new ProcurementServerLogObservation(true, false, 100, category, DateTimeOffset.UtcNow, null));
        Assert.DoesNotContain(privateText, json, StringComparison.Ordinal);
        Assert.DoesNotContain("password", json, StringComparison.Ordinal);
        Assert.Equal(ProcurementServerLogCategory.None, ProcurementDurableServerLogObserver.Classify("SELECT 'received fast shutdown request'"));
        Assert.Equal(ProcurementServerLogCategory.BackendSignalTermination, ProcurementDurableServerLogObserver.Classify(
            "2026-10-12 04:04:34 UTC [94] LOG:  server process (PID 95) was terminated by signal 11: Segmentation fault\n"));
    }

    [Fact]
    public async Task ServerLogs_BoundBytesAndDisposeStreamWithoutPersistingRawContent()
    {
        var raw = new DisposedStream(Encoding.UTF8.GetBytes(new string('x', 20000)));
        var containers = new Mock<IContainerOperations>(MockBehavior.Strict);
        containers.Setup(value => value.GetContainerLogsAsync("owned-id", false,
            It.Is<ContainerLogsParameters>(parameters => parameters.Follow == false && parameters.Tail == "64"), It.IsAny<CancellationToken>()))
            .ReturnsAsync(new MultiplexedStream(raw, false));
        var result = await ProcurementDurableServerLogObserver.CaptureAsync(containers.Object, "owned-id", false, DateTimeOffset.UtcNow, CancellationToken.None);
        Assert.True(result.Available);
        Assert.True(result.Truncated);
        Assert.Equal(16384, result.BytesRead);
        Assert.True(raw.Disposed);
        Assert.False(result.ConnectionDeathProven);
        Assert.Equal(ProcurementServerLogCategory.None, result.Categories);
        containers.VerifyAll();
    }

    [Fact]
    public async Task ServerLogs_InvalidUtf8IsUnavailableWithoutLeakingExceptionMessage()
    {
        var raw = new DisposedStream([0xff, 0xfe, (byte)'\n']);
        var containers = new Mock<IContainerOperations>();
        containers.Setup(value => value.GetContainerLogsAsync(It.IsAny<string>(), It.IsAny<bool>(), It.IsAny<ContainerLogsParameters>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(new MultiplexedStream(raw, false));
        var result = await ProcurementDurableServerLogObserver.CaptureAsync(containers.Object, "owned-id", false, DateTimeOffset.UtcNow, CancellationToken.None);
        Assert.False(result.Available);
        Assert.Equal(typeof(DecoderFallbackException).FullName, result.FailureType);
        Assert.True(raw.Disposed);
        Assert.False(result.ConnectionDeathProven);
    }

    [Fact]
    public async Task ClosedOwner_RefusesNewFactoryAllocationAfterCleanup()
    {
        var tracker = new ProcurementFixtureLifetime();
        var owner = new ProcurementDurableAllocationOwner(tracker.TrackOwnedTask);
        var created = 0;
        owner.Close();
        await Assert.ThrowsAsync<ObjectDisposedException>(() => owner.AllocateAsync("host",
            () => { created++; return Task.FromResult(new object()); }, _ => { }, _ => Task.CompletedTask, CancellationToken.None));
        Assert.Equal(0, created);
        Assert.Empty(tracker.UnsettledOperations);
        Assert.Equal(0, owner.PendingReservations);
    }

    [Fact]
    public async Task RacingAllocation_LateSuccessAfterBoundedCleanupReleasesExactValueOnce()
    {
        var clock = new SignaledClock();
        var tracker = new ProcurementFixtureLifetime(clock);
        var owner = new ProcurementDurableAllocationOwner(tracker.TrackOwnedTask);
        var created = new TaskCompletionSource<object>(TaskCreationOptions.RunContinuationsAsynchronously);
        var exact = new object();
        var published = 0;
        var releases = 0;
        var allocation = owner.AllocateAsync("host", () => created.Task, _ => published++, value =>
        {
            Assert.Same(exact, value);
            releases++;
            return Task.CompletedTask;
        }, CancellationToken.None);
        Assert.Equal(1, owner.PendingReservations);
        owner.Close();
        var cleanup = tracker.CleanupAsync(() => owner.ReleaseAsync("host"));
        await clock.TimerCreated.Task;
        clock.Advance(TimeSpan.FromSeconds(30));
        await Assert.ThrowsAsync<TimeoutException>(() => cleanup);
        Assert.Equal(0, published);
        Assert.NotEmpty(tracker.UnsettledOperations);
        created.SetResult(exact);
        await Assert.ThrowsAsync<ObjectDisposedException>(() => allocation);
        var release = owner.ReleaseAsync("host");
        await release;
        Assert.Same(release, owner.ReleaseAsync("host"));
        Assert.Equal(0, published);
        Assert.Equal(1, releases);
        Assert.Equal(0, owner.PendingReservations);
        Assert.Empty(tracker.UnsettledOperations);
    }

    [Fact]
    public async Task ReleaseDependencies_WaitForLateActualStartBeforeDisposingProvider()
    {
        var tracker = new ProcurementFixtureLifetime();
        var owner = new ProcurementDurableAllocationOwner(tracker.TrackOwnedTask);
        var start = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var disposed = false;
        await owner.AllocateAsync("supplier", () => Task.FromResult(new object()), _ => { },
            _ => owner.ReleaseAfterAsync(["supplier-start"], () => { disposed = true; return Task.CompletedTask; }), CancellationToken.None);
        await owner.AllocateAsync("supplier-start", () => Task.FromResult(start.Task), _ => { }, value => value, CancellationToken.None);
        owner.Close();
        var release = owner.ReleaseAsync("supplier");
        Assert.False(disposed);
        Assert.False(release.IsCompleted);
        start.SetResult();
        await release;
        Assert.True(disposed);
        Assert.Empty(tracker.UnsettledOperations);
    }

    [Fact]
    public async Task FactoryRelease_WaitsForActualServiceScopeCreationBeforeDisposal()
    {
        var tracker = new ProcurementFixtureLifetime();
        var owner = new ProcurementDurableAllocationOwner(tracker.TrackOwnedTask);
        var scope = new TaskCompletionSource<object>(TaskCreationOptions.RunContinuationsAsynchronously);
        var disposed = false;
        await owner.AllocateAsync("host", () => Task.FromResult(new object()), _ => { }, async _ =>
        {
            await owner.AwaitCreationSettlementAsync("scope");
            disposed = true;
        }, CancellationToken.None);
        var allocation = owner.AllocateAsync("scope", () => scope.Task, _ => { }, _ => Task.CompletedTask, CancellationToken.None);
        owner.Close();
        var release = owner.ReleaseAsync("host");
        Assert.False(disposed);
        Assert.False(release.IsCompleted);
        scope.SetResult(new object());
        await Assert.ThrowsAsync<ObjectDisposedException>(() => allocation);
        await release;
        Assert.True(disposed);
        Assert.Empty(tracker.UnsettledOperations);
    }

    [Fact]
    public async Task FailedStartDependency_StillDisposesExactProviderOnceAndRetainsFailure()
    {
        var tracker = new ProcurementFixtureLifetime();
        var owner = new ProcurementDurableAllocationOwner(tracker.TrackOwnedTask);
        var exact = new object();
        var failedStart = new IOException("Synthetic failed start.");
        var disposals = 0;
        await owner.AllocateAsync("supplier", () => Task.FromResult(exact), _ => { }, value =>
            owner.ReleaseAfterAsync(["supplier-start"], () =>
            {
                Assert.Same(exact, value);
                disposals++;
                return Task.CompletedTask;
            }), CancellationToken.None);
        await owner.AllocateAsync("supplier-start", () => Task.FromResult(Task.FromException(failedStart)), _ => { }, value => value, CancellationToken.None);
        owner.Close();
        var release = owner.ReleaseAsync("supplier");
        Assert.Same(failedStart, await Assert.ThrowsAsync<IOException>(() => release));
        Assert.Same(release, owner.ReleaseAsync("supplier"));
        Assert.Equal(1, disposals);
        Assert.Empty(tracker.UnsettledOperations);
        Assert.Contains(failedStart, tracker.ObservedFailures);
    }

    [Fact]
    public async Task FailedMigrationDependenciesAndDisposal_RetainEveryFailureAndDisposeOnce()
    {
        var tracker = new ProcurementFixtureLifetime();
        var owner = new ProcurementDurableAllocationOwner(tracker.TrackOwnedTask);
        var supplierFailure = new IOException("Synthetic supplier migration.");
        var orderFailure = new InvalidOperationException("Synthetic order migration.");
        var disposeFailure = new IOException("Synthetic scope disposal.");
        var exact = new object();
        var disposals = 0;
        await owner.AllocateAsync("scope", () => Task.FromResult(exact), _ => { }, value =>
            owner.ReleaseAfterAsync(["supplier-migration", "purchase-order-migration"], () =>
            {
                Assert.Same(exact, value);
                disposals++;
                throw disposeFailure;
            }), CancellationToken.None);
        await owner.AllocateAsync("supplier-migration", () => Task.FromResult(Task.FromException(supplierFailure)), _ => { }, value => value, CancellationToken.None);
        await owner.AllocateAsync("purchase-order-migration", () => Task.FromResult(Task.FromException(orderFailure)), _ => { }, value => value, CancellationToken.None);
        owner.Close();
        var release = owner.ReleaseAsync("scope");
        var actual = await Assert.ThrowsAsync<AggregateException>(() => release);
        Assert.Equal(new Exception[] { supplierFailure, orderFailure, disposeFailure }, actual.InnerExceptions);
        Assert.Same(release, owner.ReleaseAsync("scope"));
        Assert.Equal(1, disposals);
        Assert.Empty(tracker.UnsettledOperations);
        Assert.Contains(supplierFailure, tracker.ObservedFailures);
        Assert.Contains(orderFailure, tracker.ObservedFailures);
        Assert.Contains(disposeFailure, tracker.ObservedFailures);
    }

    private sealed class DisposedStream(byte[] bytes) : MemoryStream(bytes)
    {
        internal bool Disposed { get; private set; }
        protected override void Dispose(bool disposing) { Disposed = true; base.Dispose(disposing); }
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

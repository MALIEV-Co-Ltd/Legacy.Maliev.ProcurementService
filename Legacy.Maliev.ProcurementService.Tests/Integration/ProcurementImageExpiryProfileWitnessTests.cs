using System.Net;
using System.Text.Json;
using Docker.DotNet;
using Docker.DotNet.Models;
using Microsoft.Extensions.Time.Testing;
using System.Runtime.ExceptionServices;

namespace Legacy.Maliev.ProcurementService.Tests.Integration;

public sealed class ProcurementImageExpiryProfileWitnessTests
{
    [Theory(Skip = "Pending reviewed finite-lifecycle integration and native admission")]
    [InlineData("18.1-bookworm", "bookworm")]
    [InlineData("18.1-alpine", "alpine")]
    public async Task ImageSpecificControl_HasFiniteOwnerCleanup(string tag, string profile)
    {
        using var configuration = new DockerClientConfiguration(new Uri(OperatingSystem.IsWindows() ? "npipe://./pipe/docker_engine" : "unix:///var/run/docker.sock"));
        using var docker = configuration.CreateClient();
        // Alpine is a candidate: this test must fail if its binary/options or exit semantics differ.
        var launcher = profile switch
        {
            "bookworm" => "exec timeout --signal=INT --kill-after=1s 2 \"$@\"",
            "alpine" => "exec /bin/busybox timeout -s INT -k 1 2 \"$@\"",
            _ => throw new ArgumentOutOfRangeException(nameof(profile)),
        };
        var role = "expiry-profile-" + profile;
        string? imageId = null;
        string[] imageDigests = [];
        var run = Guid.NewGuid().ToString("N");
        var parentRun = Guid.TryParse(Environment.GetEnvironmentVariable("MALIEV_TEST_RESOURCE_RUN_ID"), out var parent) ? parent.ToString("N") : run;
        string? id = null;
        string[] controlVolumes = [];
        var volumesAbsent = new List<string>();
        var lifetime = new ProcurementFixtureLifetime();
        var expiryCandidate = false;
        var ownerWatchdogInvoked = false;
        Lifecycle? stoppedByOwnerEvidence = null;
        var ownerActions = new List<string>();
        var scopeCaptured = false;
        Lifecycle? acquiredEvidence = null;
        Lifecycle? runningEvidence = null;
        Lifecycle? stoppedEvidence = null;
        var cleanupGate = new object();
        Task? cleanupCompletion = null;
        var absent = false;
        long exitCode = -1;
        var elapsed = TimeSpan.Zero;
        void RequireOwned(ContainerInspectResponse actual)
        {
            Assert.Equal(id, actual.ID);
            Assert.Equal(imageId, actual.Image);
            Assert.Equal(imageId, actual.Config.Image);
            Assert.Equal(acquiredEvidence!.CreatedAt, Stamp(actual.Created));
            Assert.Equal(acquiredEvidence.Labels.OrderBy(p => p.Key, StringComparer.Ordinal),
                Capture(actual).Labels.OrderBy(p => p.Key, StringComparer.Ordinal));
            if (runningEvidence is not null)
            {
                Assert.Equal(runningEvidence.StartedAt, Stamp(actual.State.StartedAt));
                if (actual.State.Running) Assert.Equal(runningEvidence.ProcessId, actual.State.Pid);
            }
            Assert.Equal(run, actual.Config.Labels["maliev.codex.run"]);
            Assert.Equal(parentRun, actual.Config.Labels["maliev.codex.parent-run"]);
            Assert.Equal(role, actual.Config.Labels["maliev.codex.role"]);
            Assert.Equal(ProcurementFixtureContainerPolicy.Owner, actual.Config.Labels["maliev.codex.owner"]);
            Assert.Equal("false", actual.Config.Labels["maliev.codex.persistent-data"]);
            Assert.NotEmpty(actual.Mounts);
            Assert.All(actual.Mounts, mount => Assert.Equal("volume", mount.Type));
            Assert.Equal(controlVolumes.Order(StringComparer.Ordinal), actual.Mounts.Select(m => m.Name).Order(StringComparer.Ordinal));
            Assert.Equal(acquiredEvidence!.Mounts, Capture(actual).Mounts);
            Assert.Equal(new[] { "sh", "-c", launcher, "procurement-expiry-profile" }, actual.Config.Entrypoint);
            Assert.Equal(new[] { "sh", "-c", "trap \"\" INT TERM; while :; do sleep 1; done" }, actual.Config.Cmd);
            Assert.Equal(64 * 1024 * 1024, actual.HostConfig.Memory);
            Assert.Equal(actual.HostConfig.Memory, actual.HostConfig.MemorySwap);
            Assert.Equal(100_000_000, actual.HostConfig.NanoCPUs);
        }

        Task CleanupAsync()
        {
            lock (cleanupGate)
                return cleanupCompletion ??= Task.Run(() => lifetime.CleanupAsync(
                    ReleaseAsync, PublishAsync));
        }

        async Task ReleaseAsync()
        {
            if (id is null) return;
            using var cleanupDeadline = new CancellationTokenSource(TimeSpan.FromSeconds(20));
            // An unavailable initial inspection does not authorize arbitrary mount deletion.
            if (!scopeCaptured || acquiredEvidence is null)
            {
                var recoveryRead = Task.Run(async () =>
                {
                    var file = Path.Combine(Environment.GetEnvironmentVariable("VSTestResultsDirectory") ?? "TestResults",
                        "owner-recovery", id + ".json");
                    await using var stream = new FileStream(file, FileMode.Open, FileAccess.Read,
                        FileShare.Read, 4096, FileOptions.Asynchronous);
                    Assert.InRange(stream.Length, 1, 65536);
                    return await JsonSerializer.DeserializeAsync<RecoveryScope>(stream,
                        cancellationToken: cleanupDeadline.Token);
                });
                // Keep the actual worker registered after a canceled WaitAsync wrapper returns.
                lifetime.TrackOwnedTask(recoveryRead);
                var scope = await recoveryRead.WaitAsync(cleanupDeadline.Token);
                Assert.NotNull(scope);
                Assert.Equal(1, scope.SchemaVersion);
                Assert.True(scope.AcquisitionEligible);
                Assert.Equal(parentRun, scope.ObserverRunId);
                Assert.Equal(id, scope.ContainerId);
                Assert.Equal(id, scope.Scope.ContainerId);
                Assert.Equal(imageId, scope.Scope.ImageId);
                acquiredEvidence = scope.Scope;
                controlVolumes = scope.Scope.Mounts.Select(m => m.Name).ToArray();
                scopeCaptured = true;
                if (scope.Scope.Running) runningEvidence = scope.Scope;
            }
            var owned = await docker.Containers.InspectContainerAsync(id, cleanupDeadline.Token);
            RequireOwned(owned);
            if (runningEvidence is not null)
            {
                Assert.Equal(runningEvidence.StartedAt, Stamp(owned.State.StartedAt));
                if (owned.State.Running) Assert.Equal(runningEvidence.ProcessId, owned.State.Pid);
            }
            if (owned.State.Running)
            {
                // Exact owner-controlled recovery, graceful signal then daemon-enforced kill.
                ownerActions.Add("stop-requested:" + id);
                var accepted = await docker.Containers.StopContainerAsync(id,
                    new ContainerStopParameters { WaitBeforeKillSeconds = 1 }, cleanupDeadline.Token);
                ownerActions.Add(accepted ? "stop-accepted:" + id : "stop-noop-race:" + id);
                // A natural stop racing the request is allowed only after fresh immutable recheck.
                owned = await docker.Containers.InspectContainerAsync(id, cleanupDeadline.Token);
                RequireOwned(owned);
                Assert.False(owned.State.Running);
                stoppedByOwnerEvidence = Capture(owned);
                ownerActions.Add("stop-observed:" + id);
            }
            RequireOwned(owned);
            Assert.False(owned.State.Running);
            ownerActions.Add("remove-requested:" + id);
            await docker.Containers.RemoveContainerAsync(id, new ContainerRemoveParameters
            { Force = false, RemoveVolumes = true }, cleanupDeadline.Token);
            await RequireContainerAbsentAsync(docker, id, cleanupDeadline.Token);
            foreach (var volume in controlVolumes)
            {
                await RequireVolumeAbsentAsync(docker, volume, cleanupDeadline.Token);
                volumesAbsent.Add(volume);
            }
            absent = true;
        }

        Task PublishAsync() => Task.Run(async () =>
        {
            // Task exists before directory/open/serialization work; lifetime tracks late failure.
            using var publicationDeadline = new CancellationTokenSource(TimeSpan.FromSeconds(10));
            var token = publicationDeadline.Token;
            token.ThrowIfCancellationRequested();
            var directory = Path.Combine(Environment.GetEnvironmentVariable("VSTestResultsDirectory") ?? "TestResults", "fixture-containment");
            Directory.CreateDirectory(directory);
            token.ThrowIfCancellationRequested();
            var bytes = JsonSerializer.SerializeToUtf8Bytes(new
            {
                Scenario = role,
                Profile = profile,
                Image = "postgres:" + tag,
                ImageId = imageId,
                ImageDigests = imageDigests,
                Launcher = launcher,
                ResourceRunId = run,
                ContainerId = id,
                ParentRunId = parentRun,
                Owner = ProcurementFixtureContainerPolicy.Owner,
                ScopeCaptured = scopeCaptured,
                Volumes = controlVolumes.ToArray(),
                VolumesAbsent = volumesAbsent.ToArray(),
                Acquired = acquiredEvidence,
                Running = runningEvidence,
                StoppedBeforeCleanup = stoppedEvidence,
                LauncherExpiryCandidate = expiryCandidate,
                OwnerWatchdogInvoked = ownerWatchdogInvoked,
                StoppedByOwner = stoppedByOwnerEvidence,
                OwnerActions = ownerActions.ToArray(),
                FiniteLifecycleOwnerCleanupObserved = absent,
                // Qualification belongs to the exact independently joined terminal receipt.
                FiniteLifecycleQualified = false,
                ExternalTerminationExcluded = false,
                NaturalExpiryProven = false,
                // Independent observation must supply these facts; owner booleans cannot qualify.
                ExitCode = exitCode,
                ElapsedSeconds = elapsed.TotalSeconds,
                ContainerAbsent = absent,
                PublicationSnapshotPendingCount = lifetime.UnsettledOperations.Count,
                PayloadWrittenBeforePublicationCompletion = true,
                ObservedOperationFailureTypes = lifetime.ObservedFailures.Select(error => error.GetType().FullName).ToArray(),
                PersistentData = false,
            });
            Assert.InRange(bytes.Length, 1, 65536);
            token.ThrowIfCancellationRequested();
            await using var stream = new FileStream(Path.Combine(directory, role + ".json"),
                FileMode.CreateNew, FileAccess.Write, FileShare.None, 4096, FileOptions.Asynchronous);
            await stream.WriteAsync(bytes, token);
            await stream.FlushAsync(token);
        });
        await lifetime.InitializeAsync(async token =>
        {
            // A focused run on a clean runner must not depend on another test pulling this image.
            using var acquisition = CancellationTokenSource.CreateLinkedTokenSource(token);
            acquisition.CancelAfter(TimeSpan.FromSeconds(90));
            var progress = new ImageAcquisitionProgress();
            await docker.Images.CreateImageAsync(new ImagesCreateParameters { FromImage = "postgres", Tag = tag },
                new AuthConfig(), progress, acquisition.Token);
            Assert.False(progress.Failed, "Owned expiry-control image acquisition failed.");
            var image = await docker.Images.InspectImageAsync("postgres:" + tag, acquisition.Token);
            Assert.False(string.IsNullOrWhiteSpace(image.ID));
            imageId = image.ID;
            imageDigests = image.RepoDigests.ToArray();
            var created = await docker.Containers.CreateContainerAsync(new CreateContainerParameters
            {
                Image = imageId,
                Entrypoint = ["sh", "-c", launcher, "procurement-expiry-profile"],
                Cmd = ["sh", "-c", "trap \"\" INT TERM; while :; do sleep 1; done"],
                ExposedPorts = new Dictionary<string, EmptyStruct> { ["5432/tcp"] = default },
                Labels = new Dictionary<string, string>
                {
                    ["maliev.codex.owner"] = ProcurementFixtureContainerPolicy.Owner,
                    ["maliev.codex.run"] = run,
                    ["maliev.codex.parent-run"] = parentRun,
                    ["maliev.codex.role"] = role,
                    ["maliev.codex.expires-utc"] = DateTimeOffset.UtcNow.AddSeconds(30).ToString("O"),
                    ["maliev.codex.persistent-data"] = "false",
                },
                HostConfig = new HostConfig
                {
                    Memory = 64 * 1024 * 1024,
                    MemorySwap = 64 * 1024 * 1024,
                    NanoCPUs = 100_000_000,
                    PortBindings = new Dictionary<string, IList<PortBinding>>
                    {
                        ["5432/tcp"] = new List<PortBinding> { new() { HostIP = "127.0.0.1", HostPort = "" } },
                    },
                },
            }, token);
            id = created.ID;
            // Retain exact returned ID and original mounts before optional assertions/start.
            var acquired = await docker.Containers.InspectContainerAsync(id, token);
            controlVolumes = acquired.Mounts.Select(mount => mount.Name).ToArray();
            scopeCaptured = true;
            acquiredEvidence = Capture(acquired);
            RequireOwned(acquired);
            Assert.NotEmpty(controlVolumes);
            Assert.Equal(controlVolumes.Length, controlVolumes.Distinct(StringComparer.Ordinal).Count());
            var started = System.Diagnostics.Stopwatch.StartNew();
            Assert.True(await docker.Containers.StartContainerAsync(id, new ContainerStartParameters(), token));
            var running = await docker.Containers.InspectContainerAsync(id, token);
            runningEvidence = Capture(running);
            RequireOwned(running);
            Assert.True(running.State.Running);
            Assert.True(running.State.Pid > 0);
            Assert.False(running.State.OOMKilled);
            RequireBinding(running);
            Assert.True(DateTimeOffset.TryParse(runningEvidence.StartedAt, out var birth));
            Assert.True(birth > DateTimeOffset.UnixEpoch);
            using var controlWatchdog = CancellationTokenSource.CreateLinkedTokenSource(token);
            controlWatchdog.CancelAfter(TimeSpan.FromSeconds(15));
            try
            {
                ContainerInspectResponse actual;
                do
                {
                    await Task.Delay(TimeSpan.FromMilliseconds(100), controlWatchdog.Token);
                    actual = await docker.Containers.InspectContainerAsync(id, controlWatchdog.Token);
                } while (actual.State.Running);
                stoppedEvidence = Capture(actual);
                RequireOwned(actual);
                Assert.Equal(runningEvidence.StartedAt, stoppedEvidence.StartedAt);
                elapsed = started.Elapsed;
                exitCode = actual.State.ExitCode;
                // A measured candidate is descriptive, not a launcher-causality assertion.
                expiryCandidate = !actual.State.OOMKilled && exitCode == 137 &&
                    elapsed >= TimeSpan.FromSeconds(2) && elapsed <= TimeSpan.FromSeconds(15);
            }
            catch (OperationCanceledException) when (!token.IsCancellationRequested && controlWatchdog.IsCancellationRequested)
            {
                ownerWatchdogInvoked = true;
                elapsed = started.Elapsed;
                // Existing shared owner cleanup follows, including exact-ID Stop/Remove.
            }
        }, CleanupAsync, TimeSpan.FromMinutes(2));
        await CleanupAsync();
        Assert.True(cleanupCompletion!.IsCompletedSuccessfully);
        Assert.Empty(lifetime.UnsettledOperations);
        Assert.Empty(lifetime.ObservedFailures);
    }


    [Fact]
    public async Task RecoveryRead_BlockedTaskRemainsOwnedAfterDeadline()
    {
        var clock = new FakeTimeProvider();
        var lifetime = new ProcurementFixtureLifetime(clock);
        var entered = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var release = new TaskCompletionSource<RecoveryScope?>(TaskCreationOptions.RunContinuationsAsynchronously);
        var realBudget = new RecoverySeamBudget();
        using var primaryLease = new CancellationTokenSource(TimeSpan.FromSeconds(15));
        Exception? primaryFailure = null;
        Exception? cleanupFailure = null;
        var actualRead = Task.Run(async () => { entered.TrySetResult(); return await release.Task; });
        lifetime.TrackOwnedTask(actualRead);
        using var deadline = new CancellationTokenSource(TimeSpan.FromSeconds(20), clock);
        var wrapper = actualRead.WaitAsync(deadline.Token);
        try
        {
            await entered.Task.WaitAsync(primaryLease.Token);
            clock.Advance(TimeSpan.FromSeconds(20));
            await Assert.ThrowsAnyAsync<OperationCanceledException>(() => wrapper);
            Assert.False(actualRead.IsCompleted);
            Assert.Contains(actualRead, lifetime.UnsettledOperations);
            release.SetResult(null);
            await actualRead.WaitAsync(primaryLease.Token);
            Assert.True(SpinWait.SpinUntil(() => !lifetime.UnsettledOperations.Contains(actualRead),
                TimeSpan.FromSeconds(1)));
            Assert.Empty(lifetime.ObservedFailures);
        }
        catch (Exception error) { primaryFailure = error; }
        finally
        {
            release.TrySetResult(null);
            try
            {
                using var cleanupLease = new CancellationTokenSource(realBudget.RemainingCleanupTime());
                await actualRead.WaitAsync(cleanupLease.Token);
                while (lifetime.UnsettledOperations.Contains(actualRead))
                    await Task.Delay(TimeSpan.FromMilliseconds(1), cleanupLease.Token);
            }
            catch (Exception error) { cleanupFailure = error; }
        }
        RethrowSeamFailures(primaryFailure, cleanupFailure);
    }

    [Fact]
    public async Task RecoveryRead_PostTimeoutFaultRetainsOriginalReference()
    {
        var clock = new FakeTimeProvider();
        var lifetime = new ProcurementFixtureLifetime(clock);
        var entered = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var release = new TaskCompletionSource<RecoveryScope?>(TaskCreationOptions.RunContinuationsAsynchronously);
        var expected = new IOException("Synthetic recovery read fault after caller timeout.");
        var realBudget = new RecoverySeamBudget();
        using var primaryLease = new CancellationTokenSource(TimeSpan.FromSeconds(15));
        Exception? primaryFailure = null;
        Exception? cleanupFailure = null;
        var actualRead = Task.Run(async () => { entered.TrySetResult(); return await release.Task; });
        lifetime.TrackOwnedTask(actualRead);
        using var deadline = new CancellationTokenSource(TimeSpan.FromSeconds(20), clock);
        var wrapper = actualRead.WaitAsync(deadline.Token);
        try
        {
            await entered.Task.WaitAsync(primaryLease.Token);
            clock.Advance(TimeSpan.FromSeconds(20));
            await Assert.ThrowsAnyAsync<OperationCanceledException>(() => wrapper);
            Assert.Contains(actualRead, lifetime.UnsettledOperations);
            release.SetException(expected);
            var actual = await Assert.ThrowsAsync<IOException>(() => actualRead.WaitAsync(primaryLease.Token));
            Assert.Same(expected, actual);
            Assert.True(SpinWait.SpinUntil(() => lifetime.ObservedFailures.Any(error => ReferenceEquals(error, expected)) &&
                !lifetime.UnsettledOperations.Contains(actualRead), TimeSpan.FromSeconds(1)));
            Assert.Contains(expected, lifetime.ObservedFailures);
        }
        catch (Exception error) { primaryFailure = error; }
        finally
        {
            release.TrySetResult(null);
            try
            {
                using var cleanupLease = new CancellationTokenSource(realBudget.RemainingCleanupTime());
                try { await actualRead.WaitAsync(cleanupLease.Token); }
                catch (IOException error) when (ReferenceEquals(error, expected)) { }
                while (lifetime.UnsettledOperations.Contains(actualRead))
                    await Task.Delay(TimeSpan.FromMilliseconds(1), cleanupLease.Token);
            }
            catch (Exception error) { cleanupFailure = error; }
        }
        RethrowSeamFailures(primaryFailure, cleanupFailure);
    }

    [Fact]
    public void RecoveryRead_ExpiredTotalLeaseRefusesFalseSettlement()
    {
        var clock = new FakeTimeProvider();
        var budget = new RecoverySeamBudget(clock);
        var lifetime = new ProcurementFixtureLifetime(clock);
        // No worker is launched: this actual pending task is completed synchronously in finally.
        var read = new TaskCompletionSource<RecoveryScope?>();
        lifetime.TrackOwnedTask(read.Task);
        var primary = new IOException("Synthetic primary seam failure.");
        try
        {
            clock.Advance(TimeSpan.FromSeconds(20));
            var cleanup = Assert.Throws<TimeoutException>(() => budget.RemainingCleanupTime());
            Assert.Contains(read.Task, lifetime.UnsettledOperations);
            var aggregate = Assert.Throws<AggregateException>(() => RethrowSeamFailures(primary, cleanup));
            Assert.Same(primary, aggregate.InnerExceptions[0]);
            Assert.Same(cleanup, aggregate.InnerExceptions[1]);
        }
        finally { read.SetResult(null); }
        Assert.Empty(lifetime.UnsettledOperations);
    }

    private sealed class RecoverySeamBudget(TimeProvider? timeProvider = null)
    {
        private readonly TimeProvider clock = timeProvider ?? TimeProvider.System;
        private readonly long started = (timeProvider ?? TimeProvider.System).GetTimestamp();
        internal TimeSpan RemainingCleanupTime()
        {
            var remaining = TimeSpan.FromSeconds(20) - clock.GetElapsedTime(started);
            if (remaining <= TimeSpan.Zero)
                throw new TimeoutException("Total recovery seam lease expired; settlement is unproven.");
            return remaining;
        }
    }

    private static void RethrowSeamFailures(Exception? primary, Exception? cleanup)
    {
        if (primary is not null && cleanup is not null)
            throw new AggregateException("Recovery seam primary and cleanup failed.", primary, cleanup);
        if (primary is not null) ExceptionDispatchInfo.Capture(primary).Throw();
        if (cleanup is not null) ExceptionDispatchInfo.Capture(cleanup).Throw();
    }

    private sealed class ImageAcquisitionProgress : IProgress<JSONMessage>
    {
        private int failed;
        internal bool Failed => Volatile.Read(ref failed) != 0;
        public void Report(JSONMessage message)
        {
            // Keep error custody without persisting registry output or authentication metadata.
            if (message.Error is not null)
                Interlocked.Exchange(ref failed, 1);
        }
    }

    private static async Task RequireContainerAbsentAsync(DockerClient docker, string id, CancellationToken token)
    {
        try { await docker.Containers.InspectContainerAsync(id, token); }
        catch (DockerApiException error) when (error.StatusCode == HttpStatusCode.NotFound) { return; }
        throw new Xunit.Sdk.XunitException("Owned container remains after fixture cleanup.");
    }

    private static async Task RequireVolumeAbsentAsync(DockerClient docker, string name, CancellationToken token)
    {
        try { await docker.Volumes.InspectAsync(name, token); }
        catch (DockerApiException error) when (error.StatusCode == HttpStatusCode.NotFound) { return; }
        throw new Xunit.Sdk.XunitException("Owned disposable volume remains after fixture cleanup.");
    }

    private static void RequireBinding(ContainerInspectResponse actual)
    {
        Assert.Equal(new[] { "5432/tcp" }, actual.NetworkSettings.Ports.Keys);
        var binding = Assert.Single(actual.NetworkSettings.Ports["5432/tcp"]);
        Assert.Equal("127.0.0.1", binding.HostIP);
        Assert.True(int.TryParse(binding.HostPort, out var port));
        Assert.InRange(port, 1, 65535);
    }

    private static string Stamp(object value) => JsonSerializer.Serialize(value).Trim('"');

    private static Lifecycle Capture(ContainerInspectResponse actual) => new(
        DateTimeOffset.UtcNow, System.Diagnostics.Stopwatch.GetTimestamp(),
        actual.ID, actual.Image, Stamp(actual.Created), Stamp(actual.State.StartedAt),
        Stamp(actual.State.FinishedAt), actual.State.Pid, actual.State.Running,
        actual.State.OOMKilled, actual.State.ExitCode, actual.HostConfig.Memory,
        actual.HostConfig.MemorySwap, actual.HostConfig.NanoCPUs,
        actual.Config.Entrypoint.ToArray(), actual.Config.Cmd.ToArray(),
        actual.Config.Labels.Where(p => p.Key.StartsWith("maliev.codex.", StringComparison.Ordinal))
            .ToDictionary(p => p.Key, p => p.Value),
        actual.Mounts.Select(m => new MountEvidence(m.Type, m.Name, m.Destination, m.RW)).OrderBy(m => m.Name, StringComparer.Ordinal).ToArray(),
        actual.NetworkSettings?.Ports?.SelectMany(p => (p.Value ?? []).Select(b =>
            new BindingEvidence(p.Key, b.HostIP, b.HostPort))).ToArray() ?? []);

    private sealed record RecoveryScope(int SchemaVersion, string ObserverRunId, string ContainerId,
        bool AcquisitionEligible, Lifecycle Scope);
    private sealed record MountEvidence(string Type, string Name, string Destination, bool ReadWrite);
    private sealed record BindingEvidence(string ContainerPort, string HostIp, string HostPort);
    private sealed record Lifecycle(DateTimeOffset ObservedAtUtc, long ObservedTicks,
        string ContainerId, string ImageId, string CreatedAt, string StartedAt, string FinishedAt,
        long ProcessId, bool Running, bool OomKilled, long ExitCode, long MemoryBytes,
        long MemorySwapBytes, long NanoCpus, string[] Entrypoint, string[] Command,
        Dictionary<string, string> Labels, MountEvidence[] Mounts, BindingEvidence[] Bindings);

}

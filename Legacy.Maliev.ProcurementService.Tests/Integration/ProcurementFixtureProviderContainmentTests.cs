using System.Net;
using System.Text.Json;
using Docker.DotNet;
using Docker.DotNet.Models;

namespace Legacy.Maliev.ProcurementService.Tests.Integration;

public sealed class ProcurementFixtureProviderContainmentTests
{
    [Fact]
    public async Task ForcedExpiry_StopsSignalIgnoringOwnedChild()
    {
        using var configuration = new DockerClientConfiguration(new Uri(OperatingSystem.IsWindows() ? "npipe://./pipe/docker_engine" : "unix:///var/run/docker.sock"));
        using var docker = configuration.CreateClient();
        var run = Guid.NewGuid().ToString("N");
        string? id = null;
        var lifetime = new ProcurementFixtureLifetime();
        var expired = false;
        var absent = false;
        long exitCode = -1;
        var elapsed = TimeSpan.Zero;
        async Task CleanupAsync() => await lifetime.CleanupAsync(async () =>
        {
            if (id is null) return;
            using var cleanupDeadline = new CancellationTokenSource(TimeSpan.FromSeconds(20));
            var owned = await docker.Containers.InspectContainerAsync(id, cleanupDeadline.Token);
            Assert.Equal(run, owned.Config.Labels["maliev.codex.run"]);
            Assert.Equal(ProcurementFixtureContainerPolicy.Owner, owned.Config.Labels["maliev.codex.owner"]);
            Assert.All(owned.Mounts, mount => Assert.Equal("volume", mount.Type));
            var volumes = owned.Mounts.Select(mount => mount.Name).ToArray();
            // Only this exact disposable control is removed, including on failed expiry.
            await docker.Containers.RemoveContainerAsync(id, new ContainerRemoveParameters { Force = owned.State.Running, RemoveVolumes = true }, cleanupDeadline.Token);
            await RequireContainerAbsentAsync(docker, id, cleanupDeadline.Token);
            foreach (var volume in volumes) await RequireVolumeAbsentAsync(docker, volume, cleanupDeadline.Token);
            absent = true;
        }, () =>
        {
            var directory = Path.Combine(Environment.GetEnvironmentVariable("VSTestResultsDirectory") ?? "TestResults", "fixture-containment");
            Directory.CreateDirectory(directory);
            File.WriteAllText(Path.Combine(directory, "forced-expiry.json"), JsonSerializer.Serialize(new
            {
                Scenario = "forced-expiry", ResourceRunId = run, ContainerId = id,
                ExpiredBeforeCleanup = expired, ExitCode = exitCode, ElapsedSeconds = elapsed.TotalSeconds,
                ContainerAbsent = absent, UnsettledOperations = lifetime.UnsettledOperations.Count,
                ObservedOperationFailureTypes = lifetime.ObservedFailures.Select(error => error.GetType().FullName).ToArray(),
                PersistentData = false,
            }));
            return Task.CompletedTask;
        });
        await lifetime.InitializeAsync(async token =>
        {
            // A focused run on a clean runner must not depend on another test pulling this image.
            using var acquisition = CancellationTokenSource.CreateLinkedTokenSource(token);
            acquisition.CancelAfter(TimeSpan.FromSeconds(90));
            var progress = new ImageAcquisitionProgress();
            await docker.Images.CreateImageAsync(new ImagesCreateParameters { FromImage = "postgres", Tag = "18.1-bookworm" },
                new AuthConfig(), progress, acquisition.Token);
            Assert.False(progress.Failed, "Owned expiry-control image acquisition failed.");
            var image = await docker.Images.InspectImageAsync("postgres:18.1-bookworm", acquisition.Token);
            Assert.False(string.IsNullOrWhiteSpace(image.ID));
            var created = await docker.Containers.CreateContainerAsync(new CreateContainerParameters
            {
                Image = "postgres:18.1-bookworm",
                Entrypoint = ["sh", "-c", "exec timeout --signal=INT --kill-after=1s 2 sh -c 'trap \"\" INT TERM; while :; do sleep 1; done'"],
                Labels = new Dictionary<string, string>
                {
                    ["maliev.codex.owner"] = ProcurementFixtureContainerPolicy.Owner,
                    ["maliev.codex.run"] = run,
                    ["maliev.codex.role"] = "forced-expiry-control",
                    ["maliev.codex.expires-utc"] = DateTimeOffset.UtcNow.AddSeconds(30).ToString("O"),
                    ["maliev.codex.persistent-data"] = "false",
                },
                HostConfig = new HostConfig { Memory = 64 * 1024 * 1024, MemorySwap = 64 * 1024 * 1024, NanoCPUs = 100_000_000 },
            }, token);
            id = created.ID;
            var started = System.Diagnostics.Stopwatch.StartNew();
            Assert.True(await docker.Containers.StartContainerAsync(id, new ContainerStartParameters(), token));
            var running = await docker.Containers.InspectContainerAsync(id, token);
            Assert.True(running.State.Running);
            ContainerInspectResponse actual;
            do
            {
                await Task.Delay(TimeSpan.FromMilliseconds(100), token);
                actual = await docker.Containers.InspectContainerAsync(id, token);
            } while (actual.State.Running);
            elapsed = started.Elapsed;
            exitCode = actual.State.ExitCode;
            Assert.Equal(137, exitCode);
            Assert.InRange(elapsed, TimeSpan.FromSeconds(2), TimeSpan.FromSeconds(15));
            expired = true;
        }, CleanupAsync, TimeSpan.FromMinutes(2));
        await CleanupAsync();
    }

    private sealed class ImageAcquisitionProgress : IProgress<JSONMessage>
    {
        private int failed;
        internal bool Failed => Volatile.Read(ref failed) != 0;
        public void Report(JSONMessage message)
        {
            // Keep error custody without persisting registry output or authentication metadata.
            if (message.Error is not null || !string.IsNullOrEmpty(message.ErrorMessage))
                Interlocked.Exchange(ref failed, 1);
        }
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task OwnedProviderBoundsAndNaturalCleanup_AreObserved(bool failAfterProvidersStart)
    {
        using var configuration = new DockerClientConfiguration(new Uri(OperatingSystem.IsWindows() ? "npipe://./pipe/docker_engine" : "unix:///var/run/docker.sock"));
        using var docker = configuration.CreateClient();
        var fixture = new ProcurementRuntimeFixture();
        var probe = new ProcurementFixtureLifetime();
        var resources = new List<ProviderResource>();
        var containersAbsent = new List<string>();
        var volumesAbsent = new List<string>();
        var cleanupObserved = false;
        var observedAt = DateTimeOffset.UtcNow;
        var expectedFailure = new IOException("Synthetic failure after both owned providers started.");

        async Task CleanupAsync() => await probe.CleanupAsync(
            fixture.DisposeAsync,
            async () =>
            {
                using var deadline = new CancellationTokenSource(TimeSpan.FromSeconds(20));
                Assert.Equal(2, resources.Count);
                foreach (var row in resources)
                {
                    await RequireContainerAbsentAsync(docker, row.Id, deadline.Token);
                    containersAbsent.Add(row.Id);
                }
                foreach (var volume in resources.SelectMany(row => row.Volumes).Distinct(StringComparer.Ordinal))
                {
                    await RequireVolumeAbsentAsync(docker, volume, deadline.Token);
                    volumesAbsent.Add(volume);
                }
                Assert.Equal(0, fixture.UnsettledOperationCount);
                cleanupObserved = true;
            },
            () =>
            {
                var directory = Path.Combine(Environment.GetEnvironmentVariable("VSTestResultsDirectory") ?? "TestResults", "fixture-containment");
                Directory.CreateDirectory(directory);
                File.WriteAllText(Path.Combine(directory, failAfterProvidersStart ? "partial-setup-failure.json" : "successful-lifecycle.json"), JsonSerializer.Serialize(new
                {
                    Scenario = failAfterProvidersStart ? "partial-setup-failure" : "successful-lifecycle",
                    fixture.ResourceRunId,
                    Owner = ProcurementFixtureContainerPolicy.Owner,
                    ObservedAtUtc = observedAt,
                    CompletedAtUtc = DateTimeOffset.UtcNow,
                    Resources = resources,
                    ContainersAbsent = containersAbsent,
                    VolumesAbsent = volumesAbsent,
                    CleanupObserved = cleanupObserved,
                    UnsettledOperations = fixture.UnsettledOperationCount,
                    ObservedOperationFailureTypes = fixture.ObservedOperationFailures.Select(error => error.GetType().FullName).ToArray(),
                    DestructiveObserverActions = 0,
                    PersistentData = false,
                }));
                return Task.CompletedTask;
            });

        await probe.InitializeAsync(async token =>
        {
            if (failAfterProvidersStart)
            {
                var actual = await Assert.ThrowsAsync<IOException>(() => fixture.InitializeAsync(async startupToken =>
                {
                    resources = await ObserveAsync(docker, fixture.ResourceRunId, startupToken);
                    throw expectedFailure;
                }));
                Assert.Same(expectedFailure, actual);
            }
            else
            {
                await fixture.InitializeAsync();
                resources = await ObserveAsync(docker, fixture.ResourceRunId, token);
            }
        }, CleanupAsync, TimeSpan.FromMinutes(3));
        await CleanupAsync();
    }

    private static async Task<List<ProviderResource>> ObserveAsync(DockerClient docker, string run, CancellationToken token)
    {
        var matches = await docker.Containers.ListContainersAsync(new ContainersListParameters
        {
            All = true,
            Filters = new Dictionary<string, IDictionary<string, bool>> { ["label"] = new Dictionary<string, bool> { ["maliev.codex.run=" + run] = true } },
        }, token);
        Assert.Equal(2, matches.Count);
        var rows = new List<ProviderResource>();
        foreach (var match in matches)
        {
            var actual = await docker.Containers.InspectContainerAsync(match.ID, token);
            Assert.True(actual.State.Running);
            Assert.Equal(ProcurementFixtureContainerPolicy.MemoryBytes, actual.HostConfig.Memory);
            Assert.Equal(actual.HostConfig.Memory, actual.HostConfig.MemorySwap);
            Assert.Equal(ProcurementFixtureContainerPolicy.NanoCpus, actual.HostConfig.NanoCPUs);
            Assert.Equal(ProcurementFixtureContainerPolicy.Owner, actual.Config.Labels["maliev.codex.owner"]);
            Assert.Equal(run, actual.Config.Labels["maliev.codex.run"]);
            Assert.Equal("false", actual.Config.Labels["maliev.codex.persistent-data"]);
            Assert.True(Guid.TryParse(actual.Config.Labels["maliev.codex.parent-run"], out _));
            var expiry = DateTimeOffset.Parse(actual.Config.Labels["maliev.codex.expires-utc"]);
            Assert.InRange(expiry - DateTimeOffset.UtcNow, TimeSpan.FromMinutes(20), TimeSpan.FromMinutes(32));
            Assert.Equal(new[] { "sh", "-c", "exec timeout --signal=INT --kill-after=10s 1800 docker-entrypoint.sh \"$@\"", "procurement-owned-fixture" }, actual.Config.Entrypoint);
            var ips = actual.NetworkSettings.Ports["5432/tcp"].Select(binding => binding.HostIP).ToArray();
            Assert.NotEmpty(ips);
            Assert.All(ips, ip => Assert.Equal("127.0.0.1", ip));
            var volumes = actual.Mounts.Where(mount => mount.Type == "volume").Select(mount => mount.Name).ToArray();
            Assert.NotEmpty(volumes);
            rows.Add(new ProviderResource(actual.ID, actual.Config.Labels["maliev.codex.role"], actual.Created.ToString(), actual.State.StartedAt.ToString(), actual.State.Pid,
                actual.HostConfig.Memory, actual.HostConfig.MemorySwap, actual.HostConfig.NanoCPUs, actual.Config.Entrypoint.ToArray(), actual.Config.Cmd.ToArray(),
                actual.Config.Labels.Where(pair => pair.Key.StartsWith("maliev.codex.", StringComparison.Ordinal) || pair.Key == "org.testcontainers.session-id").ToDictionary(pair => pair.Key, pair => pair.Value), ips, volumes));
        }
        Assert.Equal(new[] { "purchase-order", "supplier" }, rows.Select(row => row.Role).OrderBy(role => role, StringComparer.Ordinal));
        return rows;
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

    private sealed record ProviderResource(string Id, string Role, string Created, string StartedAt, long ProcessId, long MemoryBytes, long MemorySwapBytes, long NanoCpus,
        string[] Entrypoint, string[] Command, Dictionary<string, string> Labels, string[] HostIps, string[] Volumes);
}

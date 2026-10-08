using DotNet.Testcontainers.Containers;
using Testcontainers.PostgreSql;

namespace Legacy.Maliev.ProcurementService.Tests;

internal static class OwnedProcurementTestContainers
{
    internal static string DockerEndpoint => OperatingSystem.IsWindows() ? "npipe://./pipe/docker_engine"
        : OperatingSystem.IsLinux() ? "unix:///var/run/docker.sock"
        : throw new PlatformNotSupportedException("Owned Procurement tests require the reviewed local Docker endpoint.");
    private static readonly string Run = Guid.NewGuid().ToString("N");
    internal static readonly string ParentRun = Environment.GetEnvironmentVariable("MALIEV_TEST_RESOURCE_RUN_ID") ?? Guid.NewGuid().ToString("N");
    private static string Expiry => DateTime.UtcNow.AddMinutes(32).ToString("O");

    internal static PostgreSqlBuilder Postgres(string image) => new PostgreSqlBuilder(image)
        .WithDockerEndpoint(DockerEndpoint)
        .WithLabel("maliev.codex.owner", "commerce-procurement-qualification-20261007")
        .WithLabel("maliev.codex.parent-run", ParentRun)
        .WithLabel("maliev.codex.run", Run).WithLabel("maliev.codex.expires-utc", Expiry)
        .WithLabel("maliev.codex.persistent-data", "false")
        .WithCreateParameterModifier(parameters =>
        {
            parameters.Entrypoint = ["sh", "-c"];
            parameters.Cmd = ["exec timeout 1800 docker-entrypoint.sh postgres -c fsync=off -c full_page_writes=off -c synchronous_commit=off"];
            parameters.HostConfig!.Memory = 1024 * 1024 * 1024;
            parameters.HostConfig.MemorySwap = 1024 * 1024 * 1024;
            parameters.HostConfig.NanoCPUs = 750000000;
            parameters.HostConfig.Tmpfs = new Dictionary<string, string> { ["/var/lib/postgresql"] = "rw,size=512m" };
            foreach (var bindings in parameters.HostConfig.PortBindings.Values)
                foreach (var binding in bindings) binding.HostIP = "127.0.0.1";
        });

    internal static async Task SetupAsync(Func<CancellationToken, Task> setup, Func<Task> cleanup)
    {
        using var lifetime = new CancellationTokenSource(TimeSpan.FromSeconds(120));
        try { await setup(lifetime.Token); }
        catch (Exception setupFailure)
        {
            try { await cleanup(); }
            catch (Exception cleanupFailure) { throw new AggregateException(setupFailure, cleanupFailure); }
            throw;
        }
    }

    internal static async Task CleanupAsync(params Func<Task>[] cleanup)
    {
        var failures = new List<Exception>();
        foreach (var dispose in cleanup)
        {
            try { await WaitForCleanupAsync(dispose()); }
            catch (Exception failure) { failures.Add(failure); }
        }
        if (failures.Count > 0) throw new AggregateException("Owned Procurement test resource cleanup failed.", failures);
    }

    internal static Task DisposeAsync(params IContainer[] containers) =>
        CleanupAsync(containers.Select<IContainer, Func<Task>>(container => () => container.DisposeAsync().AsTask()).ToArray());

    internal static Task WaitForCleanupAsync(Task disposal)
    {
        _ = disposal.ContinueWith(task =>
        {
            var failure = task.Exception;
            Console.Error.WriteLine($"Owned cleanup fault observed: {failure?.GetType().Name}.");
        }, CancellationToken.None, TaskContinuationOptions.OnlyOnFaulted | TaskContinuationOptions.ExecuteSynchronously, TaskScheduler.Default);
        return disposal.WaitAsync(TimeSpan.FromSeconds(30));
    }
}

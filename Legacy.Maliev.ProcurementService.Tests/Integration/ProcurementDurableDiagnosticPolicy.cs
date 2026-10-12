using System.Runtime.ExceptionServices;
using System.Text;
using System.Text.RegularExpressions;

using Docker.DotNet;
using Docker.DotNet.Models;

using Testcontainers.PostgreSql;

namespace Legacy.Maliev.ProcurementService.Tests.Integration;

internal static class ProcurementDurableDiagnosticContainerPolicy
{
    internal const string Owner = "procurement-durable-create-fixture";
    internal const long MemoryBytes = 1073741824;
    internal const long NanoCpus = 750000000;

    internal static string Endpoint(string? configured, bool windows, bool linux)
    {
        var local = windows ? "npipe://./pipe/docker_engine" : linux ? "unix:///var/run/docker.sock"
            : throw new PlatformNotSupportedException("Diagnostic fixture requires local Docker.");
        if (!string.IsNullOrEmpty(configured) && configured != local)
            throw new InvalidOperationException("Diagnostic fixture local endpoint mismatch.");
        return local;
    }

    internal static PostgreSqlContainer Build(string run, string role) => new PostgreSqlBuilder("postgres:18.1-bookworm")
        .WithDockerEndpoint(Endpoint(Environment.GetEnvironmentVariable("DOCKER_HOST"), OperatingSystem.IsWindows(), OperatingSystem.IsLinux()))
        .WithLabel("maliev.codex.owner", Owner)
        .WithLabel("maliev.codex.run", run)
        .WithLabel("maliev.codex.role", role)
        .WithLabel("maliev.codex.parent-run", Guid.TryParse(Environment.GetEnvironmentVariable("MALIEV_TEST_RESOURCE_RUN_ID"), out var parent) ? parent.ToString("N") : run)
        .WithLabel("maliev.codex.expires-utc", DateTime.UtcNow.AddMinutes(32).ToString("O"))
        .WithLabel("maliev.codex.persistent-data", "false")
        .WithCreateParameterModifier(Apply)
        .Build();

    internal static void Apply(CreateContainerParameters parameters)
    {
        parameters.Entrypoint = ["sh", "-c", "exec timeout --signal=INT --kill-after=10s 1800 docker-entrypoint.sh \"$@\"", "procurement-durable-diagnostic-fixture"];
        parameters.HostConfig!.Memory = MemoryBytes;
        parameters.HostConfig.MemorySwap = MemoryBytes;
        parameters.HostConfig.NanoCPUs = NanoCpus;
        foreach (var bindings in parameters.HostConfig.PortBindings.Values)
            foreach (var binding in bindings) binding.HostIP = "127.0.0.1";
    }
}

// Separate from runtime fixture lifetime: one owner cancels, settles, observes then releases.
internal sealed class ProcurementDurableDiagnosticInitialization(TimeProvider? timeProvider = null)
{
    private readonly TimeProvider clock = timeProvider ?? TimeProvider.System;
    private readonly ProcurementFixtureLifetime tracking = new(timeProvider);
    internal IReadOnlyList<Task> UnsettledOperations => tracking.UnsettledOperations;
    internal IReadOnlyList<Exception> ObservedFailures => tracking.ObservedFailures;
    internal static readonly TimeSpan InitializationDeadline = TimeSpan.FromMinutes(2);
    internal static readonly TimeSpan SettlementDeadline = TimeSpan.FromSeconds(30);

    internal Task Track(Task operation)
    {
        tracking.TrackOwnedTask(operation);
        return operation;
    }

    internal async Task RunAsync(Func<CancellationToken, Task> initialize,
        Func<IReadOnlyCollection<Exception>, Task> observeFailure, Func<Task> cleanup, Action? closeOwner = null)
    {
        using var cancellation = new CancellationTokenSource(InitializationDeadline, clock);
        var failures = new List<Exception>();
        try
        {
            var actual = Track(Task.Run(() => initialize(cancellation.Token)));
            await actual.WaitAsync(cancellation.Token);
            return;
        }
        catch (Exception primary) { failures.Add(primary); }
        try { closeOwner?.Invoke(); }
        catch (Exception closeFailure) { failures.Add(closeFailure); }
        try { cancellation.Cancel(); }
        catch (Exception cancellationFailure) { failures.Add(cancellationFailure); }
        var pending = UnsettledOperations;
        if (pending.Count > 0)
        {
            try { await Task.WhenAll(pending).WaitAsync(SettlementDeadline, clock); }
            catch (Exception settlementFailure) { failures.Add(settlementFailure); }
        }
        failures.AddRange(ObservedFailures);
        // Observer exceptions never skip cleanup or replace the original first failure.
        try { await observeFailure(failures.Distinct<Exception>(ReferenceEqualityComparer.Instance).ToArray()); }
        catch (Exception observationFailure) { failures.Add(observationFailure); }
        try { await cleanup(); }
        catch (Exception cleanupFailure) { failures.Add(cleanupFailure); }
        var distinct = failures.Distinct<Exception>(ReferenceEqualityComparer.Instance).ToArray();
        if (distinct.Length == 1) ExceptionDispatchInfo.Capture(distinct[0]).Throw();
        throw new AggregateException("Diagnostic fixture initialization and cleanup failed.", distinct);
    }
}

[Flags]
internal enum ProcurementServerLogCategory
{
    None = 0,
    ShutdownRequested = 1,
    ShutdownCompleted = 2,
    AdministratorTermination = 4,
    BackendSignalTermination = 8,
    CrashRecovery = 16,
}

internal sealed record ProcurementServerLogObservation(bool Available, bool Truncated, int BytesRead,
    ProcurementServerLogCategory Categories, DateTimeOffset CapturedAtUtc, string? FailureType,
    bool ConnectionDeathProven = false);

internal static class ProcurementDurableServerLogObserver
{
    internal const int MaximumBytes = 16384;
    private static readonly Regex Prefix = new(@"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(?:\.\d+)? [A-Z+0-9:]+ \[\d+\] (?:LOG|FATAL|PANIC):  ",
        RegexOptions.CultureInvariant | RegexOptions.NonBacktracking, TimeSpan.FromMilliseconds(100));

    internal static ProcurementServerLogCategory Classify(string text)
    {
        var result = ProcurementServerLogCategory.None;
        foreach (var line in text.Split('\n'))
        {
            var prefix = Prefix.Match(line);
            if (!prefix.Success) continue;
            var message = line[prefix.Length..].TrimEnd('\r');
            if (message is "received fast shutdown request" or "received smart shutdown request" or "received immediate shutdown request")
                result |= ProcurementServerLogCategory.ShutdownRequested;
            else if (message == "database system is shut down") result |= ProcurementServerLogCategory.ShutdownCompleted;
            else if (message == "terminating connection due to administrator command") result |= ProcurementServerLogCategory.AdministratorTermination;
            else if (Regex.IsMatch(message, @"^server process \(PID \d+\) was terminated by signal \d+: [A-Za-z ]+$", RegexOptions.CultureInvariant | RegexOptions.NonBacktracking, TimeSpan.FromMilliseconds(100)))
                result |= ProcurementServerLogCategory.BackendSignalTermination;
            else if (message is "all server processes terminated; reinitializing" or "database system was not properly shut down; automatic recovery in progress")
                result |= ProcurementServerLogCategory.CrashRecovery;
        }
        return result;
    }

    // Caller must first verify exact inspected ID/owner/run/role. No SQL or connection probes.
    internal static async Task<ProcurementServerLogObservation> CaptureAsync(IContainerOperations containers,
        string id, DateTimeOffset since, CancellationToken outer)
    {
        using var deadline = CancellationTokenSource.CreateLinkedTokenSource(outer);
        deadline.CancelAfter(TimeSpan.FromSeconds(2));
        var buffer = new byte[4096];
        using var stdout = new MemoryStream();
        using var stderr = new MemoryStream();
        var count = 0;
        try
        {
            using var stream = await containers.GetContainerLogsAsync(id, new ContainerLogsParameters
            {
                ShowStdout = true, ShowStderr = true, Follow = false, Timestamps = false, Tail = "64",
                Since = since.ToUnixTimeSeconds().ToString(System.Globalization.CultureInfo.InvariantCulture),
                Until = DateTimeOffset.UtcNow.ToUnixTimeSeconds().ToString(System.Globalization.CultureInfo.InvariantCulture),
            }, deadline.Token);
            while (count < MaximumBytes)
            {
                var read = await stream.ReadOutputAsync(buffer, 0, Math.Min(buffer.Length, MaximumBytes - count), deadline.Token);
                if (read.EOF) break;
                count += read.Count;
                var destination = read.Target == MultiplexedStream.TargetStream.StandardError ? stderr : stdout;
                destination.Write(buffer, 0, read.Count);
            }
            // Only complete lines are classified; partial/truncated lines cannot assert a category.
            var encoding = new UTF8Encoding(false, true);
            static string CompleteLines(string text) => text.LastIndexOf('\n') is var end && end >= 0 ? text[..(end + 1)] : "";
            var categories = Classify(CompleteLines(encoding.GetString(stdout.GetBuffer().AsSpan(0, checked((int)stdout.Length))))) | Classify(CompleteLines(encoding.GetString(stderr.GetBuffer().AsSpan(0, checked((int)stderr.Length)))));
            return new(true, count == MaximumBytes, count, categories, DateTimeOffset.UtcNow, null);
        }
        catch (Exception failure) { return new(false, count == MaximumBytes, count, ProcurementServerLogCategory.None, DateTimeOffset.UtcNow, failure.GetType().FullName); }
        finally
        {
            Array.Clear(buffer);
            System.Security.Cryptography.CryptographicOperations.ZeroMemory(stdout.GetBuffer());
            System.Security.Cryptography.CryptographicOperations.ZeroMemory(stderr.GetBuffer());
        }
    }
}

internal sealed class ProcurementDurableAllocationOwner(Action<Task> trackRelease)
{
    private readonly object gate = new();
    private readonly Dictionary<string, ILease> leases = new(StringComparer.Ordinal);
    private bool closed;

    internal void Close()
    {
        lock (gate) closed = true;
    }

    internal int PendingReservations
    {
        get { lock (gate) return leases.Values.Count(value => !value.CreationSettled); }
    }

    // Reserve exact release ownership before creation; closure cannot miss an in-flight value.
    // Creation/disposal run outside the gate. Only simple fixture-field publication is inside it.
    internal async Task AllocateAsync<T>(string role, Func<Task<T>> create,
        Action<T> publish, Func<T, Task> release, CancellationToken token)
    {
        Lease<T> lease;
        lock (gate)
        {
            token.ThrowIfCancellationRequested();
            if (closed) throw new ObjectDisposedException("Diagnostic fixture allocation owner");
            if (leases.ContainsKey(role)) throw new InvalidOperationException("Diagnostic resource role already reserved.");
            lease = new(release);
            leases.Add(role, lease);
        }
        T value;
        try { value = await create(); }
        catch { lease.NoValue(); throw; }
        var published = false;
        try
        {
            lock (gate)
            {
                lease.SetValue(value);
                if (!closed && !token.IsCancellationRequested)
                {
                    publish(value);
                    published = true;
                }
            }
        }
        catch (Exception primary)
        {
            await ReleasePreservingPrimaryAsync(lease, primary);
            throw;
        }
        if (!published)
        {
            Exception primary = token.IsCancellationRequested ? new OperationCanceledException(token)
                : new ObjectDisposedException("Diagnostic fixture allocation owner");
            await ReleasePreservingPrimaryAsync(lease, primary);
        }
    }

    internal Task ReleaseAsync(string role)
    {
        ILease? lease;
        lock (gate) leases.TryGetValue(role, out lease);
        return lease is null ? Task.CompletedTask : OwnedRelease(lease);
    }

    internal Task AwaitCreationSettlementAsync(string role)
    {
        ILease? lease;
        lock (gate) leases.TryGetValue(role, out lease);
        return lease is null ? Task.CompletedTask : lease.CreationSettlement;
    }

    internal async Task ReleaseAfterAsync(string[] dependencies, Func<Task> release)
    {
        var failures = new List<Exception>();
        foreach (var dependency in dependencies)
        {
            try { await ReleaseAsync(dependency); }
            catch (Exception failure) { failures.Add(failure); }
        }
        try { await release(); }
        catch (Exception releaseFailure) { failures.Add(releaseFailure); }
        if (failures.Count == 1) ExceptionDispatchInfo.Capture(failures[0]).Throw();
        if (failures.Count > 1) throw new AggregateException(failures);
    }

    private Task OwnedRelease(ILease lease)
    {
        var actual = lease.ReleaseOnce;
        trackRelease(actual);
        return actual;
    }

    private async Task ReleasePreservingPrimaryAsync(ILease lease, Exception primary)
    {
        try { await OwnedRelease(lease); }
        catch (Exception releaseFailure) { throw new AggregateException(primary, releaseFailure); }
        ExceptionDispatchInfo.Capture(primary).Throw();
    }

    private interface ILease
    {
        bool CreationSettled { get; }
        Task CreationSettlement { get; }
        Task ReleaseOnce { get; }
    }

    private sealed class Lease<T> : ILease
    {
        private readonly TaskCompletionSource<(bool Present, T Value)> created = new(TaskCreationOptions.RunContinuationsAsynchronously);
        private readonly Lazy<Task> releaseOnce;
        internal Lease(Func<T, Task> release)
        {
            releaseOnce = new(async () =>
            {
                var result = await created.Task;
                if (result.Present) await release(result.Value);
            }, LazyThreadSafetyMode.ExecutionAndPublication);
        }
        public bool CreationSettled => created.Task.IsCompleted;
        public Task CreationSettlement => created.Task;
        public Task ReleaseOnce => releaseOnce.Value;
        internal void SetValue(T value) => created.TrySetResult((true, value));
        internal void NoValue() => created.TrySetResult((false, default!));
    }
}

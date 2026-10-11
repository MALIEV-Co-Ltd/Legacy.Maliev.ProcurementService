using System.Diagnostics;
using System.Text.Json;
using System.Runtime.ExceptionServices;

namespace Legacy.Maliev.ProcurementService.Tests.Integration;

internal sealed record ProcurementStartupEvent(int Sequence, long ElapsedTicks, DateTimeOffset ObservedAtUtc,
    string Role, string Phase, string? ContainerId, string? FailureType, bool? CancellationRequested);

internal sealed class ProcurementFixtureStartupJournal
{
    internal const int MaximumEvents = 32;
    internal const int MaximumBytes = 64 * 1024;
    private readonly object gate = new();
    private readonly long started = Stopwatch.GetTimestamp();
    private readonly List<ProcurementStartupEvent> events = [];
    private readonly List<Exception> failures = [];
    private readonly Dictionary<string, Exception> originalFailures = new(StringComparer.Ordinal);
    private bool stopped;
    private bool overflow;
    private int attempts;

    // Internal custody is independent of Task.WhenAll.Exception, which omits canceled children.
    // Completion after Stop still retains original outcomes; nothing here is serialized.
    internal Exception[] OriginalFailures
    {
        get
        {
            lock (gate)
                return new[] { "supplier", "purchase-order" }.Where(originalFailures.ContainsKey)
                    .Select(role => originalFailures[role]).ToArray();
        }
    }

    private static void Validate(string role, string phase, string? id, string? type)
    {
        if (role is not ("supplier" or "purchase-order")) throw new InvalidOperationException("Unknown startup role.");
        if (phase is not ("wrapper-invoked" or "wrapper-settled" or "provider-creating" or
            "provider-created-inspected" or "provider-port-mapping-ready" or "provider-readiness-complete"))
            throw new InvalidOperationException("Unknown startup phase.");
        if (id is not null && (id.Length != 64 || id.Any(value => !char.IsAsciiHexDigit(value))))
            throw new InvalidOperationException("Startup observation requires a full container ID.");
        if (phase is "provider-created-inspected" or "provider-port-mapping-ready" or "provider-readiness-complete")
        {
            if (id is null) throw new InvalidOperationException("Allocated provider observation requires a container ID.");
        }
        else if (id is not null) throw new InvalidOperationException("Pre-allocation or wrapper observation cannot assign a container ID.");
        if (type is not null && (type.Length is 0 or > 256 || type.Any(value =>
            !char.IsAsciiLetterOrDigit(value) && value is not ('.' or '_' or '+' or '`'))))
            throw new InvalidOperationException("Startup failure type is outside the allowlist.");
    }

    internal void Record(string role, string phase, Func<string?>? readId = null, Exception? failure = null,
        bool? cancellationRequested = null)
    {
        lock (gate)
        {
            if (stopped) return;
            if (attempts == MaximumEvents)
            {
                if (!overflow) failures.Add(new InvalidOperationException("Startup observation event limit exceeded."));
                overflow = true;
                return;
            }
            attempts++;
            try
            {
                // Validate role and phase before reading provider state.
                if (role is not ("supplier" or "purchase-order")) throw new InvalidOperationException("Unknown startup role.");
                if (phase is not ("wrapper-invoked" or "wrapper-settled" or "provider-creating" or
                    "provider-created-inspected" or "provider-port-mapping-ready" or "provider-readiness-complete"))
                    throw new InvalidOperationException("Unknown startup phase.");
                var id = readId?.Invoke();
                var type = failure?.GetType().FullName;
                Validate(role, phase, id, type);
                events.Add(new(events.Count + 1, Stopwatch.GetTimestamp() - started, DateTimeOffset.UtcNow,
                    role, phase, id, type, cancellationRequested));
            }
            catch (Exception observationFailure) { failures.Add(observationFailure); }
        }
    }

    internal async Task StartAsync(string role, Func<Task> start, CancellationToken token)
    {
        Record(role, "wrapper-invoked", cancellationRequested: token.IsCancellationRequested);
        Exception? original = null;
        try { await start(); }
        catch (Exception error)
        {
            original = error;
            lock (gate) originalFailures.TryAdd(role, error);
            throw;
        }
        finally { Record(role, "wrapper-settled", failure: original, cancellationRequested: token.IsCancellationRequested); }
    }

    internal (ProcurementStartupEvent[] Events, Exception[] Failures, bool Overflow) Stop()
    {
        lock (gate)
        {
            stopped = true;
            return (events.ToArray(), failures.ToArray(), overflow);
        }
    }

    internal static byte[] Serialize(string run, string parentRun, ProcurementStartupEvent[] observations, bool overflow,
        Exception[]? observationFailures = null)
    {
        if (!Guid.TryParseExact(run, "N", out _) || !Guid.TryParseExact(parentRun, "N", out _))
            throw new InvalidOperationException("Startup receipt requires bounded run identities.");
        if (observations.Length > MaximumEvents) throw new InvalidOperationException("Startup receipt event limit exceeded.");
        if (observationFailures?.Length > MaximumEvents + 1) throw new InvalidOperationException("Startup receipt failure limit exceeded.");
        long elapsed = -1;
        for (var index = 0; index < observations.Length; index++)
        {
            var item = observations[index];
            Validate(item.Role, item.Phase, item.ContainerId, item.FailureType);
            if (item.Sequence != index + 1 || item.ElapsedTicks < 0 || item.ElapsedTicks < elapsed || item.ObservedAtUtc.Offset != TimeSpan.Zero)
                throw new InvalidOperationException("Startup receipt order or clock metadata is invalid.");
            elapsed = item.ElapsedTicks;
        }
        var types = (observationFailures ?? []).Select(error => error.GetType().FullName).ToArray();
        foreach (var type in types) Validate("supplier", "wrapper-settled", null, type);
        var bytes = JsonSerializer.SerializeToUtf8Bytes(new
        {
            SchemaVersion = 1,
            ResourceRunId = run,
            ParentRunId = parentRun,
            Owner = ProcurementFixtureContainerPolicy.Owner,
            Schedule = "concurrent",
            ClockFrequency = Stopwatch.Frequency,
            Events = observations,
            Overflow = overflow,
            ObservationFailureTypes = types,
            ExactDockerApiTiming = false,
            DestructiveObserverActions = 0,
        });
        if (bytes.Length > MaximumBytes) throw new InvalidOperationException("Startup receipt byte limit exceeded.");
        return bytes;
    }
}

internal sealed class ProcurementFixtureStartupPublicationOwner
{
    private readonly object gate = new();
    private Task? publication;

    internal Task GetOrStart(Func<Task> publish)
    {
        lock (gate) return publication ??= StartAsync(publish);
    }

    private static async Task StartAsync(Func<Task> publish)
    {
        // The shared task is retained before storage or serialization can execute.
        await Task.Yield();
        await publish();
    }
}

internal static class ProcurementFixtureStartupPublication
{
    internal static async Task PublishAsync(Func<CancellationToken, Task> publish, Exception[] observed, CancellationToken token)
    {
        // Return the owned task before invoking storage. No synchronous filesystem operation
        // can prevent the caller from tracking this task and starting independent cleanup.
        await Task.Yield();
        var failures = observed.ToList();
        try { await publish(token); }
        catch (Exception error) { failures.Add(error); }
        ThrowOriginals(failures);
    }

    internal static async Task CleanupAsync(Func<Task> publish, Func<Task> disposeHost)
    {
        var publication = CaptureAsync(publish);
        var host = CaptureAsync(disposeHost);
        var failures = await Task.WhenAll(publication, host);
        ThrowOriginals(failures.OfType<Exception>().ToList());
    }

    private static async Task<Exception?> CaptureAsync(Func<Task> operation)
    {
        await Task.Yield();
        try { await operation(); return null; }
        catch (Exception error) { return error; }
    }

    private static void ThrowOriginals(List<Exception> failures)
    {
        if (failures.Count == 1) ExceptionDispatchInfo.Capture(failures[0]).Throw();
        if (failures.Count > 1) throw new AggregateException(failures);
    }
}

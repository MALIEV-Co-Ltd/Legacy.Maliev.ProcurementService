using System.Diagnostics;
using System.Runtime.ExceptionServices;
using System.Text.Json;
using Docker.DotNet.Models;

namespace Legacy.Maliev.ProcurementService.Tests.Integration;

internal enum ProcurementFixtureConsumer
{
    UnattributedRuntime, UnattributedDurable, DurableCreate, DurableChildCreate,
    SupplierTransaction, ChildLifecycle, OpenApiContract, SourceStrings,
}

internal sealed record ProcurementFixtureOwnerIdentity(string? ConsumerClass, string FixtureType,
    string FixtureKind, string FixtureInstanceId, string ResourceRunId, DateTimeOffset ClockOriginUtc,
    long ClockOriginTicks, long ClockFrequency, bool DirectNativeExecutionJoin);

internal sealed record ProcurementFixtureOwnerEvent(int Sequence, int CleanupInvocation,
    string Phase, DateTimeOffset ObservedAtUtc, long ElapsedTicks, string? Role, string? FailureType);

internal sealed class ProcurementFixtureOwnerCorrelation
{
    internal const int MaximumEvents = 64;
    internal const int MaximumCleanupInvocations = 16;
    private const string Prefix = "Legacy.Maliev.ProcurementService.Tests.";
    private readonly object gate = new();
    private readonly List<ProcurementFixtureOwnerEvent> events = [];
    private readonly List<Exception> failures = [];
    private readonly List<object> resources = [];
    private readonly HashSet<string> inspectedRoles = new(StringComparer.Ordinal);
    private readonly Func<int, string, CancellationToken, Task> publishCore;
    private int cleanupInvocation;
    private bool overflow;
    private readonly Dictionary<(int Invocation, string Phase), ProcurementFixtureStartupPublicationOwner> publications = [];
    internal ProcurementFixtureOwnerIdentity Identity { get; }
    internal Exception[] OriginalObservationFailures
    {
        get { lock (gate) return failures.ToArray(); }
    }

    internal static (string? Consumer, string Fixture, string Kind) Validate(
        ProcurementFixtureConsumer consumer, string actualType)
    {
        var expected = consumer switch
        {
            ProcurementFixtureConsumer.UnattributedRuntime => ((string?)null, Prefix + "Integration.ProcurementRuntimeFixture", "runtime"),
            ProcurementFixtureConsumer.UnattributedDurable => ((string?)null, Prefix + "Integration.ProcurementDurableCreateFixture", "durable"),
            ProcurementFixtureConsumer.DurableCreate => (Prefix + "Integration.ProcurementDurableCreateTests", Prefix + "Integration.DurableCreateOwnedFixture", "durable"),
            ProcurementFixtureConsumer.DurableChildCreate => (Prefix + "Integration.ProcurementDurableChildCreateTests", Prefix + "Integration.DurableChildCreateOwnedFixture", "durable"),
            ProcurementFixtureConsumer.SupplierTransaction => (Prefix + "Integration.ProcurementSupplierTransactionBoundaryTests", Prefix + "Integration.SupplierTransactionOwnedFixture", "runtime"),
            ProcurementFixtureConsumer.ChildLifecycle => (Prefix + "Integration.ProcurementChildLifecycleTests", Prefix + "Integration.ChildLifecycleOwnedFixture", "runtime"),
            ProcurementFixtureConsumer.OpenApiContract => (Prefix + "Controllers.ProcurementOpenApiHttpContractTests", Prefix + "Integration.OpenApiContractOwnedFixture", "runtime"),
            ProcurementFixtureConsumer.SourceStrings => (Prefix + "Data.ProcurementSourceStringMigrationTests", Prefix + "Data.ProcurementSourceStringMigrationTests", "strings"),
            _ => throw new ArgumentOutOfRangeException(nameof(consumer)),
        };
        if (actualType != expected.Item2) throw new InvalidOperationException("Fixture consumer mapping mismatch.");
        return expected;
    }

    internal ProcurementFixtureOwnerCorrelation(ProcurementFixtureConsumer consumer, string actualType, string run,
        Func<int, string, CancellationToken, Task>? publication = null)
    {
        var validated = Validate(consumer, actualType);
        if (!Guid.TryParseExact(run, "N", out _)) throw new InvalidOperationException("Invalid fixture run identity.");
        Identity = new(validated.Consumer, validated.Fixture, validated.Kind, Guid.NewGuid().ToString("N"),
            run, DateTimeOffset.UtcNow, Stopwatch.GetTimestamp(), Stopwatch.Frequency, false);
        publishCore = publication ?? PublishCoreAsync;
        Record(0, "identity-before-allocation");
    }

    internal int BeginCleanup()
    {
        lock (gate)
        {
            var invocation = ++cleanupInvocation;
            if (invocation > MaximumCleanupInvocations && !overflow)
            {
                overflow = true;
                failures.Add(new InvalidOperationException("Fixture cleanup receipt limit exceeded."));
            }
            Record(invocation, "cleanup-invoked");
            return invocation;
        }
    }

    internal void Record(int invocation, string phase, string? role = null, Exception? failure = null)
    {
        lock (gate)
        {
            if (phase is not ("identity-before-allocation" or "initialize-invoked" or "cleanup-invoked" or "callback-invoked" or "callback-settled" or "callback-failed") ||
                role is not (null or "supplier" or "purchase-order" or "source-string-postgres" or "host" or "rsa" or "observer"))
            {
                if (failures.Count < 32) failures.Add(new InvalidOperationException("Fixture event metadata is outside the allowlist."));
                else overflow = true;
                return;
            }
            if (events.Count == MaximumEvents)
            {
                if (!overflow) failures.Add(new InvalidOperationException("Fixture owner event limit exceeded."));
                overflow = true;
                return;
            }
            events.Add(new(events.Count + 1, invocation, phase, DateTimeOffset.UtcNow,
                Stopwatch.GetTimestamp() - Identity.ClockOriginTicks, role, failure?.GetType().FullName));
        }
    }

    internal async Task ObserveCleanupAsync(int invocation, string role, Func<Task> release)
    {
        Record(invocation, "callback-invoked", role);
        try { await release(); Record(invocation, "callback-settled", role); }
        catch (Exception original) { Record(invocation, "callback-failed", role, original); throw; }
    }

    internal static void PreserveOwnedScope(Action recordOriginalScope, Action correlate, ICollection<Exception> errors)
    {
        // An optional correlation refusal cannot erase ownership already established by the original observer.
        recordOriginalScope();
        try { correlate(); }
        catch (Exception correlationFailure) { errors.Add(correlationFailure); }
    }

    internal void CaptureInspection(string role, string declaredId, ContainerInspectResponse actual,
        string? expectedOwner, bool requireLoopback)
    {
        var allowedRoles = Identity.FixtureKind == "strings" ? new[] { "source-string-postgres" } : new[] { "supplier", "purchase-order" };
        if (!allowedRoles.Contains(role, StringComparer.Ordinal) || declaredId.Length != 64 ||
            declaredId.Any(value => !char.IsAsciiHexDigit(value) || char.IsUpper(value)) || actual.ID != declaredId)
            throw new InvalidOperationException("Fixture provider identity mismatch.");
        var labels = actual.Config.Labels;
        string? Label(string name) => labels.TryGetValue(name, out var value) ? value : null;
        if (expectedOwner is not null && (Label("maliev.codex.owner") != expectedOwner ||
            Label("maliev.codex.run") != Identity.ResourceRunId || Label("maliev.codex.role") != role))
            throw new InvalidOperationException("Fixture provider ownership mismatch.");
        var session = Label("org.testcontainers.session-id");
        if (!Guid.TryParseExact(session, "D", out _)) throw new InvalidOperationException("Fixture session custody missing.");
        var bindings = actual.NetworkSettings.Ports?.SelectMany(pair => (pair.Value ?? []).Select(binding =>
            new { ContainerPort = pair.Key, binding.HostIP, binding.HostPort })).ToArray() ?? [];
        if (requireLoopback && bindings.Any(binding => binding.HostIP != "127.0.0.1"))
            throw new InvalidOperationException("Fixture endpoint is not loopback.");
        lock (gate)
        {
            if (!inspectedRoles.Add(role)) throw new InvalidOperationException("Duplicate fixture provider role.");
            if (resources.Count == 2) throw new InvalidOperationException("Fixture provider receipt limit exceeded.");
            resources.Add(new
            {
                Role = role, DeclaredContainerId = declaredId, InspectedContainerId = actual.ID,
                OwnerLabelsAvailable = expectedOwner is not null,
                Labels = labels.Where(pair => pair.Key is "maliev.codex.owner" or "maliev.codex.run" or
                    "maliev.codex.role" or "maliev.codex.parent-run" or "maliev.codex.expires-utc" or
                    "maliev.codex.persistent-data" or "org.testcontainers.session-id").ToDictionary(pair => pair.Key, pair => pair.Value),
                ActualBindings = bindings, ActualTcpPeerProven = false,
                ResourceContainmentQualified = false,
            });
        }
    }

    internal byte[] Serialize(int invocation, string phase)
    {
        lock (gate)
        {
            if (invocation < 0 || invocation > MaximumCleanupInvocations + 1 || phase is not ("setup" or "after-cleanup") ||
                (invocation == 0) != (phase == "setup"))
                throw new InvalidOperationException("Fixture receipt metadata limit exceeded.");
            var bytes = JsonSerializer.SerializeToUtf8Bytes(new
            {
                SchemaVersion = 1, Identity, CleanupInvocation = invocation, Phase = phase,
                Events = events.ToArray(), Resources = resources.ToArray(), Overflow = overflow,
                ObservationFailureTypes = failures.Select(error => error.GetType().FullName).ToArray(),
                NativeExecutionId = (string?)null, TerminalCleanupProven = false,
                ActualTcpPeerProven = false, BackendProcessIdIsContainerAttribution = false,
            });
            if (bytes.Length > 65536) throw new InvalidOperationException("Fixture owner receipt byte limit exceeded.");
            return bytes;
        }
    }

    internal Task PublishAsync(int invocation, string phase, CancellationToken token)
    {
        lock (gate)
        {
            if (invocation < 0 || phase is not ("setup" or "after-cleanup") ||
                (invocation == 0) != (phase == "setup"))
                throw new InvalidOperationException("Fixture receipt metadata limit exceeded.");
            // One extra overflow receipt is bounded and shared; later invocations get its actual faulted Task.
            // Its diagnostic never claims the later invocation's terminal cleanup or native identity.
            var receiptInvocation = Math.Min(invocation, MaximumCleanupInvocations + 1);
            if (!publications.TryGetValue((receiptInvocation, phase), out var publication))
                publications.Add((receiptInvocation, phase), publication = new());
            return publication.GetOrStart(() => CompletePublicationAsync(receiptInvocation, phase, token));
        }
    }

    private async Task CompletePublicationAsync(int invocation, string phase, CancellationToken token)
    {
        // Storage runs first. Late observation errors are detached only after the actual write settles.
        Exception? writeFailure = null;
        try { await publishCore(invocation, phase, token); }
        catch (Exception originalWriteFailure) { writeFailure = originalWriteFailure; }
        var originals = OriginalObservationFailures.ToList();
        if (writeFailure is not null) originals.Add(writeFailure);
        if (originals.Count == 1) ExceptionDispatchInfo.Capture(originals[0]).Throw();
        if (originals.Count > 1) throw new AggregateException(originals);
    }

    private async Task PublishCoreAsync(int invocation, string phase, CancellationToken token)
    {
        await Task.Yield();
        var directory = Environment.GetEnvironmentVariable("VSTestResultsDirectory") ?? "TestResults";
        var path = Path.Combine(directory, "fixture-owner-" + Identity.ResourceRunId + "-" + invocation + "-" + phase + ".json");
        await using var output = new FileStream(path, FileMode.CreateNew, FileAccess.Write, FileShare.None, 4096, true);
        await output.WriteAsync(Serialize(invocation, phase), token);
    }
}

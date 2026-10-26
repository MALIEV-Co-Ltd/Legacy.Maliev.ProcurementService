using System.Diagnostics;
using System.Text;
using System.Text.Json;
using Testcontainers.PostgreSql;

namespace Legacy.Maliev.ProcurementService.Tests.Integration;

internal sealed class ProcurementQualificationFailure : Exception
{
    internal ProcurementQualificationFailure() : base("Pinned qualification fault.") { }
}

internal static class ProcurementQualificationFaults
{
    internal static string Case { get; private set; } = "";
    internal static string Fault { get; set; } = "";
    internal static int ConstructedDisposals { get; private set; }
    internal static List<string> DisposalAttempts { get; } = [];
    internal static List<Task> PendingDisposals { get; } = [];
    internal static Dictionary<string, string> StartedIds { get; } = [];
    private static Dictionary<PostgreSqlContainer, string> StartedContainers { get; } = [];
    private static int sequence;
    private static string DirectoryPath => Environment.GetEnvironmentVariable("MALIEV_QUALIFICATION_CONTROLS")
        ?? throw new InvalidOperationException("Qualification control directory missing.");

    internal static void Configure(string name)
    {
        if (Environment.GetEnvironmentVariable("MALIEV_QUALIFICATION_CASE") != name)
            throw new InvalidOperationException("Qualification case selection differs.");
        if (!Path.IsPathFullyQualified(DirectoryPath) || !Directory.Exists(DirectoryPath))
            throw new InvalidOperationException("Qualification control directory invalid.");
        Case = Fault = name;
        sequence = ConstructedDisposals = 0;
        DisposalAttempts.Clear(); PendingDisposals.Clear(); StartedIds.Clear(); StartedContainers.Clear();
    }

    internal static void ThrowAt(string point)
    {
        if (Case.Length > 0 && Fault == point) throw new ProcurementQualificationFailure();
    }

    private static async Task RequestAsync(string kind, string id = "", string role = "", string fixture = "", string testClass = "", CancellationToken cancellation = default)
    {
        var eventSequence = Interlocked.Increment(ref sequence);
        if (eventSequence > 64) throw new InvalidOperationException("Control event quota exceeded.");
        var file = Path.Combine(DirectoryPath, eventSequence.ToString("D4") + ".json");
        var bytes = Encoding.UTF8.GetBytes(JsonSerializer.Serialize(new
        {
            sequence = eventSequence, @case = Case, kind, id, role, fixture, testClass,
            parentRun = OwnedProcurementTestContainers.ParentRun,
        }));
        if (bytes.Length > 2048) throw new InvalidOperationException("Control byte quota exceeded.");
        using (var stream = new FileStream(file + ".tmp", FileMode.CreateNew, FileAccess.Write, FileShare.None))
        { stream.Write(bytes); stream.Flush(true); }
        File.Move(file + ".tmp", file);
        var watch = Stopwatch.StartNew();
        while (watch.Elapsed < TimeSpan.FromSeconds(20))
        {
            cancellation.ThrowIfCancellationRequested();
            if (File.Exists(file + ".ack") && File.ReadAllText(file + ".ack") == "approved") return;
            await Task.Delay(50, cancellation);
        }
        throw new TimeoutException("Independent qualification observation missing.");
    }

    internal static async Task StartedAsync(PostgreSqlContainer container, string role, string fixture, string testClass, CancellationToken cancellation)
    {
        if (Case.Length == 0) return;
        var id = container.Id;
        StartedIds.Add(id, role); StartedContainers.Add(container, id);
        await RequestAsync("health", id, role, fixture, testClass, cancellation);
    }

    internal static async Task DisposeConstructedAsync(PostgreSqlContainer container)
    {
        ConstructedDisposals++;
        await OwnedProcurementTestContainers.DisposeAsync(container);
    }

    internal static async Task DisposeRoleAsync(PostgreSqlContainer container, string role)
    {
        if (Case.Length == 0) { await OwnedProcurementTestContainers.DisposeAsync(container); return; }
        DisposalAttempts.Add(role);
        StartedContainers.TryGetValue(container, out var startedId);
        if (Fault == "disposal-timeout" && role == "Supplier")
        {
            async Task Underlying()
            {
                await Task.Delay(TimeSpan.FromSeconds(31));
                await OwnedProcurementTestContainers.DisposeAsync(container);
                if (startedId is not null) await RequestAsync("absence", startedId, role);
            }
            var pending = Underlying(); PendingDisposals.Add(pending);
            await OwnedProcurementTestContainers.WaitForCleanupAsync(pending);
            return;
        }
        await OwnedProcurementTestContainers.DisposeAsync(container);
        if (startedId is not null) await RequestAsync("absence", startedId, role);
    }

    internal static void WriteReceipt(FileStream stream, byte[] bytes, string kind, string role)
    {
        bool fail = Case.Length > 0 && ((Fault == "receipt-admission-write" && kind == "admission")
            || (Fault == "receipt-start-write" && kind == "start") || Fault == "receipt-" + kind + "-write");
        if (fail) stream.Dispose(); // Execute the real failing FileStream.Write, not a simulated outcome.
        if (Fault == "concurrent-append-read" && kind == "admission" && role == "Supplier")
        {
            stream.Write(bytes.AsSpan(0, bytes.Length / 2)); stream.Flush(true);
            RequestAsync("truncated-read").GetAwaiter().GetResult();
            stream.Write(bytes.AsSpan(bytes.Length / 2)); stream.Flush(true);
            RequestAsync("complete-read").GetAwaiter().GetResult();
            return;
        }
        stream.Write(bytes);
    }

    internal static async Task CompleteAsync()
    {
        foreach (var pending in PendingDisposals) await pending.WaitAsync(TimeSpan.FromSeconds(60));
        await RequestAsync("case-complete");
    }
}

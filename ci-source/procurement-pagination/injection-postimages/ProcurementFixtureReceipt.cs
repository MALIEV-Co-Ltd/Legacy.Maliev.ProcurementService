using System.Globalization;
using System.Text;
using System.Text.Json;
using Testcontainers.PostgreSql;

namespace Legacy.Maliev.ProcurementService.Tests.Integration;

internal sealed class ProcurementFixtureReceipt
{
    private readonly string fixture = Guid.NewGuid().ToString("N");
    private readonly string testClass;
    private readonly string phase;
    private readonly string parent;
    private readonly string file;
    private int sequence;

    internal ProcurementFixtureReceipt(Type owner)
    {
        testClass = owner.FullName ?? throw new InvalidOperationException("Compiled class identity missing.");
        if (testClass is not ("Legacy.Maliev.ProcurementService.Tests.Integration.ProcurementPaginationSourceTests"
            or "Legacy.Maliev.ProcurementService.Tests.Integration.ProcurementPaginationWireContractTests"
            or "Legacy.Maliev.ProcurementService.Tests.Integration.ProcurementIndependentContactTests"))
            throw new InvalidOperationException("Unreviewed fixture owner.");
        phase = Environment.GetEnvironmentVariable("MALIEV_TEST_RESOURCE_PHASE") ?? "";
        if (phase is not ("baseline" or "candidate" or "candidate-full")) throw new InvalidOperationException("Receipt phase missing.");
        parent = OwnedProcurementTestContainers.ParentRun;
        if (!Guid.TryParseExact(parent, "D", out _)) throw new InvalidOperationException("Parent identity invalid.");
        var directory = Environment.GetEnvironmentVariable("MALIEV_TEST_RESOURCE_RECEIPTS") ?? "";
        if (!Path.IsPathFullyQualified(directory) || !Directory.Exists(directory)) throw new InvalidOperationException("Receipt directory missing.");
        file = Path.Combine(directory, fixture + ".jsonl");
        using var created = new FileStream(file, FileMode.CreateNew, FileAccess.Write, FileShare.Read);
    }

    internal string FixtureIdentity => fixture;
    internal string TestClass => testClass;

    internal PostgreSqlBuilder Builder(string role) => OwnedProcurementTestContainers.Postgres("postgres:18.1-bookworm")
        .WithLabel("maliev.codex.fixture-instance", fixture)
        .WithLabel("maliev.codex.test-class", testClass)
        .WithLabel("maliev.codex.database-role", role)
        .WithLabel("maliev.codex.phase", phase);

    internal void Record(string kind, string role, string id)
    {
        if (role is not ("Supplier" or "PurchaseOrder") || kind is not ("admission" or "start" or "dispose-start" or "dispose-return"))
            throw new InvalidOperationException("Receipt event invalid.");
        long available = 0;
        if (kind == "admission")
        {
            var line = File.ReadLines("/proc/meminfo").Single(value => value.StartsWith("MemAvailable:", StringComparison.Ordinal));
            available = long.Parse(line.Split(' ', StringSplitOptions.RemoveEmptyEntries)[1], CultureInfo.InvariantCulture);
            if (available < 4194304) throw new InvalidOperationException("Fresh 4GiB fixture admission unavailable.");
        }
        if (sequence >= 8) throw new InvalidOperationException("Receipt event bound exceeded.");
        var bytes = Encoding.UTF8.GetBytes(JsonSerializer.Serialize(new
        {
            parentRun = parent, phase, testClass, fixture, role, id, kind,
            sequence = sequence + 1, utc = DateTimeOffset.UtcNow.ToString("O"), availableKiB = available,
        }) + "\n");
        if (bytes.Length > 2048) throw new InvalidOperationException("Receipt line bound exceeded.");
        using var stream = new FileStream(file, FileMode.Append, FileAccess.Write, FileShare.Read);
        if (stream.Length + bytes.Length > 16384) throw new InvalidOperationException("Receipt byte bound exceeded.");
        ProcurementQualificationFaults.WriteReceipt(stream, bytes, kind, role);
        stream.Flush(true);
        sequence++;
    }
}

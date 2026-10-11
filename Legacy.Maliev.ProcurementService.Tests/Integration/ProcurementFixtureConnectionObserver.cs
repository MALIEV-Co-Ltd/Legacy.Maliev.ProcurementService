using System.Data;
using System.Data.Common;
using System.Diagnostics;
using Microsoft.EntityFrameworkCore.Diagnostics;
using Npgsql;

namespace Legacy.Maliev.ProcurementService.Tests.Integration;

internal sealed record ProcurementConnectionEvent(int Sequence, double ElapsedMilliseconds, string Role,
    string Kind, Guid ConnectionId, bool IsAsync, bool CancellationRequested, bool? Open,
    int? BackendProcessId, bool? ConfiguredEndpointMatches, string? FailureType, string? CaptureFailureType);

internal sealed class ProcurementConnectionJournal
{
    internal const int MaximumEvents = 32;
    private readonly object gate = new();
    private readonly long started = Stopwatch.GetTimestamp();
    private readonly List<ProcurementConnectionEvent> events = [];
    private readonly List<Exception> failures = [];
    private bool stopped;
    private bool overflow;

    internal void Record(string role, string kind, Guid connectionId, bool isAsync, bool cancellationRequested,
        string? failureType, Func<(bool Open, int? BackendProcessId, bool? EndpointMatches)> read)
    {
        lock (gate)
        {
            if (stopped) return;
            if (events.Count == MaximumEvents)
            {
                if (!overflow) failures.Add(new InvalidOperationException("Connection observation event limit exceeded."));
                overflow = true;
                return;
            }
            var elapsed = Stopwatch.GetElapsedTime(started).TotalMilliseconds;
            try
            {
                var actual = read();
                events.Add(new(events.Count + 1, elapsed, role, kind, connectionId, isAsync,
                    cancellationRequested, actual.Open, actual.BackendProcessId, actual.EndpointMatches, failureType, null));
            }
            catch (Exception error)
            {
                failures.Add(error);
                events.Add(new(events.Count + 1, elapsed, role, kind, connectionId, isAsync,
                    cancellationRequested, null, null, null, failureType, SafeType(error)));
            }
        }
    }

    internal static string SafeType(Exception error)
    {
        var name = error.GetType().Name;
        return name.Length <= 128 ? name : name[..128];
    }

    internal (ProcurementConnectionEvent[] Events, Exception[] Failures, bool Overflow) Stop()
    {
        lock (gate)
        {
            stopped = true;
            return (events.ToArray(), failures.ToArray(), overflow);
        }
    }
}

internal sealed class ProcurementFixtureConnectionObserver(ProcurementConnectionJournal journal, string role,
    string expectedConnection) : DbConnectionInterceptor
{
    internal void Capture(DbConnection connection, string kind, Guid id, bool isAsync, bool canceled, Exception? failure)
        => journal.Record(role, kind, id, isAsync, canceled, failure is null ? null : ProcurementConnectionJournal.SafeType(failure), () =>
        {
            // Read only existing provider state; ProcessID reads the already-bound connector.
            // Do not read PostgreSqlVersion: its temporary binding scope could allocate in multiplexing mode.
            var open = connection.State == ConnectionState.Open;
            var configured = new NpgsqlConnectionStringBuilder(connection.ConnectionString);
            var expected = new NpgsqlConnectionStringBuilder(expectedConnection);
            var matches = configured.Host == expected.Host && configured.Port == expected.Port && configured.Database == expected.Database;
            int? pid = kind == "opened" && open && connection is NpgsqlConnection npgsql ? npgsql.ProcessID : null;
            return (open, pid, matches);
        });

    public override void ConnectionOpened(DbConnection connection, ConnectionEndEventData eventData)
        => Capture(connection, "opened", eventData.ConnectionId, false, false, null);

    public override Task ConnectionOpenedAsync(DbConnection connection, ConnectionEndEventData eventData, CancellationToken cancellationToken = default)
    {
        Capture(connection, "opened", eventData.ConnectionId, true, cancellationToken.IsCancellationRequested, null);
        return Task.CompletedTask;
    }

    public override void ConnectionFailed(DbConnection connection, ConnectionErrorEventData eventData)
        => Capture(connection, "failed", eventData.ConnectionId, false, false, eventData.Exception);

    public override Task ConnectionFailedAsync(DbConnection connection, ConnectionErrorEventData eventData, CancellationToken cancellationToken = default)
    {
        Capture(connection, "failed", eventData.ConnectionId, true, cancellationToken.IsCancellationRequested, eventData.Exception);
        return Task.CompletedTask;
    }
}

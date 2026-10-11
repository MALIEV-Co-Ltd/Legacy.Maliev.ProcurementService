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
    private readonly Dictionary<string, Guid> firstReaderCommands = [];
    private readonly List<ProcurementReaderCommandEvent> readerCommands = [];
    private readonly HashSet<(string Role, string Kind)> recordedReaderKinds = [];
    private readonly HashSet<string> uncapturedReaderRoles = [];
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

    internal void RecordFirstReader(string role, string kind, Guid commandId, Guid connectionId,
        bool isAsync, bool cancellationRequested, Exception? failure)
    {
        lock (gate)
        {
            if (stopped) return;
            // Fixed two-role enrollment; never read command SQL, parameters, or a connection.
            if (role is not ("supplier" or "purchase-order")) return;
            if (kind is not ("reader-start" or "reader-executed" or "command-failed")) return;
            if (!firstReaderCommands.TryGetValue(role, out var first))
            {
                if (kind != "reader-start") { uncapturedReaderRoles.Add(role); return; }
                firstReaderCommands.Add(role, commandId);
                first = commandId;
            }
            if (first != commandId) { uncapturedReaderRoles.Add(role); return; }
            // At most one of each callback kind per enrolled role: six rows, no overflow error.
            if (!recordedReaderKinds.Add((role, kind))) return;
            readerCommands.Add(new(readerCommands.Count + 1, Stopwatch.GetElapsedTime(started).TotalMilliseconds,
                role, kind, commandId, connectionId, isAsync, cancellationRequested,
                failure is null ? null : SafeType(failure)));
        }
    }

    internal static string SafeType(Exception error)
    {
        var name = error.GetType().Name;
        return name.Length <= 128 ? name : name[..128];
    }

    internal (ProcurementConnectionEvent[] Events, Exception[] Failures, bool Overflow,
        ProcurementReaderCommandEvent[] ReaderCommands, string[] UncapturedReaderRoles) Stop()
    {
        lock (gate)
        {
            stopped = true;
            return (events.ToArray(), failures.ToArray(), overflow, readerCommands.ToArray(),
                uncapturedReaderRoles.Order(StringComparer.Ordinal).ToArray());
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

internal sealed record ProcurementReaderCommandEvent(int Sequence, double ElapsedMilliseconds, string Role,
    string Kind, Guid CommandId, Guid ConnectionId, bool IsAsync, bool CancellationRequested, string? FailureType);

internal sealed class ProcurementFixtureFirstReaderObserver(ProcurementConnectionJournal journal, string role)
    : DbCommandInterceptor
{
    // Executed means a reader was returned, never that its stream was fully consumed.
    public override InterceptionResult<DbDataReader> ReaderExecuting(DbCommand command, CommandEventData eventData,
        InterceptionResult<DbDataReader> result)
    {
        journal.RecordFirstReader(role, "reader-start", eventData.CommandId, eventData.ConnectionId, false, false, null);
        return result;
    }

    public override ValueTask<InterceptionResult<DbDataReader>> ReaderExecutingAsync(DbCommand command,
        CommandEventData eventData, InterceptionResult<DbDataReader> result, CancellationToken cancellationToken = default)
    {
        journal.RecordFirstReader(role, "reader-start", eventData.CommandId, eventData.ConnectionId, true,
            cancellationToken.IsCancellationRequested, null);
        return ValueTask.FromResult(result);
    }

    public override DbDataReader ReaderExecuted(DbCommand command, CommandExecutedEventData eventData, DbDataReader result)
    {
        journal.RecordFirstReader(role, "reader-executed", eventData.CommandId, eventData.ConnectionId, false, false, null);
        return result;
    }

    public override ValueTask<DbDataReader> ReaderExecutedAsync(DbCommand command, CommandExecutedEventData eventData,
        DbDataReader result, CancellationToken cancellationToken = default)
    {
        journal.RecordFirstReader(role, "reader-executed", eventData.CommandId, eventData.ConnectionId, true,
            cancellationToken.IsCancellationRequested, null);
        return ValueTask.FromResult(result);
    }

    public override void CommandFailed(DbCommand command, CommandErrorEventData eventData)
        => journal.RecordFirstReader(role, "command-failed", eventData.CommandId, eventData.ConnectionId, false, false,
            eventData.Exception);

    public override Task CommandFailedAsync(DbCommand command, CommandErrorEventData eventData,
        CancellationToken cancellationToken = default)
    {
        journal.RecordFirstReader(role, "command-failed", eventData.CommandId, eventData.ConnectionId, true,
            cancellationToken.IsCancellationRequested, eventData.Exception);
        return Task.CompletedTask;
    }
}

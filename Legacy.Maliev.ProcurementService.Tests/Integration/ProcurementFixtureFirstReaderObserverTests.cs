using System.Data;
using System.Data.Common;
using System.Text.Json;
using Microsoft.EntityFrameworkCore.Diagnostics;

namespace Legacy.Maliev.ProcurementService.Tests.Integration;

public sealed class ProcurementFixtureFirstReaderObserverTests
{
    [Fact]
    public void LongHealthySequence_EnrollsFirstReaderPerRoleWithoutManufacturingFailure()
    {
        var journal = new ProcurementConnectionJournal();
        foreach (var role in new[] { "supplier", "purchase-order" })
        {
            var connection = Guid.NewGuid();
            journal.Record(role, "opened", connection, true, false, null, () => (true, 123, true));
            for (var index = 0; index < 10000; index++)
            {
                var command = Guid.NewGuid();
                journal.RecordFirstReader(role, "reader-start", command, connection, true, false, null);
                journal.RecordFirstReader(role, "reader-executed", command, connection, true, false, null);
            }
        }
        var snapshot = journal.Stop();
        Assert.Equal(2, snapshot.Events.Length);
        Assert.Equal(4, snapshot.ReaderCommands.Length);
        Assert.Equal(new[] { "purchase-order", "supplier" }, snapshot.UncapturedReaderRoles);
        Assert.Empty(snapshot.Failures);
        Assert.False(snapshot.Overflow);
        Assert.True(JsonSerializer.SerializeToUtf8Bytes(snapshot.ReaderCommands).Length < 65536);
    }

    [Fact]
    public async Task OriginalProviderFailure_RemainsPrimaryAfterExecutedCallbackAndLaterCommands()
    {
        var journal = new ProcurementConnectionJournal();
        var command = Guid.NewGuid();
        var connection = Guid.NewGuid();
        var primary = new IOException("Synthetic private provider message.");
        journal.RecordFirstReader("supplier", "reader-start", command, connection, true, false, null);
        journal.RecordFirstReader("supplier", "reader-executed", command, connection, true, false, null);
        journal.RecordFirstReader("supplier", "command-failed", command, connection, true, false, primary);
        for (var index = 0; index < 1000; index++)
            journal.RecordFirstReader("supplier", "command-failed", Guid.NewGuid(), connection, true, false, primary);
        var snapshot = journal.Stop();
        Assert.Equal(new[] { "reader-start", "reader-executed", "command-failed" }, snapshot.ReaderCommands.Select(row => row.Kind));
        Assert.Equal(nameof(IOException), snapshot.ReaderCommands[2].FailureType);
        Assert.Empty(snapshot.Failures);
        var actual = await Assert.ThrowsAsync<IOException>(() => ProcurementDurableFixtureFailureCompletion.CompleteAsync(
            [primary], snapshot.Failures, _ => { }, () => Task.CompletedTask, () => Task.CompletedTask));
        Assert.Same(primary, actual);
        Assert.DoesNotContain("Synthetic private", JsonSerializer.Serialize(snapshot.ReaderCommands));
    }

    [Fact]
    public void PartialDuplicateAndStoppedCallbacks_AreBoundedAndDoNotInventEnrollment()
    {
        var journal = new ProcurementConnectionJournal();
        var id = Guid.NewGuid();
        journal.RecordFirstReader("supplier", "command-failed", id, id, true, true, new IOException());
        journal.RecordFirstReader("supplier", "reader-start", id, id, true, true, null);
        for (var index = 0; index < 1000; index++)
            journal.RecordFirstReader("supplier", "reader-start", id, id, true, true, null);
        var snapshot = journal.Stop();
        var row = Assert.Single(snapshot.ReaderCommands);
        Assert.Equal("reader-start", row.Kind);
        Assert.Equal(new[] { "supplier" }, snapshot.UncapturedReaderRoles);
        journal.RecordFirstReader("purchase-order", "reader-start", id, id, false, false, null);
        Assert.Single(journal.Stop().ReaderCommands);
        Assert.Empty(snapshot.Failures);
    }

    [Fact]
    public async Task Callbacks_NeverAccessCommandOrConnectionAndReturnOriginalReaderAndSuppression()
    {
        var journal = new ProcurementConnectionJournal();
        var observer = new ProcurementFixtureFirstReaderObserver(journal, "supplier");
        var commandId = Guid.NewGuid();
        var connectionId = Guid.NewGuid();
        using var reader = new DataTable().CreateDataReader();
        var executing = new CommandEventData(null!, (_, _) => throw new InvalidOperationException("No rendering."),
            null!, null!, "", null, DbCommandMethod.ExecuteReader, commandId, connectionId, true, false,
            DateTimeOffset.UtcNow, CommandSource.Migrations);
        var executed = new CommandExecutedEventData(null!, (_, _) => throw new InvalidOperationException("No rendering."),
            null!, null!, "", null, DbCommandMethod.ExecuteReader, commandId, connectionId, reader, true, false,
            DateTimeOffset.UtcNow, TimeSpan.Zero, CommandSource.Migrations);
        var error = new IOException("Private message.");
        var failed = new CommandErrorEventData(null!, (_, _) => throw new InvalidOperationException("No rendering."),
            null!, null!, "", null, DbCommandMethod.ExecuteReader, commandId, connectionId, error, true, false,
            DateTimeOffset.UtcNow, TimeSpan.Zero, CommandSource.Migrations);
        var result = InterceptionResult<DbDataReader>.SuppressWithResult(reader);
        Assert.Same(reader, observer.ReaderExecuting(null!, executing, result).Result);
        Assert.Same(reader, observer.ReaderExecuted(null!, executed, reader));
        using var cancellation = new CancellationTokenSource();
        cancellation.Cancel();
        var started = observer.ReaderExecutingAsync(null!, executing, result, cancellation.Token);
        var returned = observer.ReaderExecutedAsync(null!, executed, reader, cancellation.Token);
        var fault = observer.CommandFailedAsync(null!, failed, cancellation.Token);
        Assert.True(started.IsCompletedSuccessfully);
        Assert.True(returned.IsCompletedSuccessfully);
        Assert.True(fault.IsCompletedSuccessfully);
        Assert.Same(reader, (await started).Result);
        Assert.Same(reader, await returned);
        await fault;
        Assert.Same(error, failed.Exception);
        Assert.All(journal.Stop().ReaderCommands, row => Assert.Equal(commandId, row.CommandId));
    }
}

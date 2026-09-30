using System.Data.Common;
using System.Net;
using System.Net.Http.Json;
using Legacy.Maliev.ProcurementService.Api.Authorization;
using Legacy.Maliev.ProcurementService.Application.Interfaces;
using Legacy.Maliev.ProcurementService.Application.Models;
using Legacy.Maliev.ProcurementService.Data;
using Legacy.Maliev.ProcurementService.Domain;
using Microsoft.AspNetCore.Hosting;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Diagnostics;
using Microsoft.EntityFrameworkCore.Storage;
using Microsoft.Extensions.DependencyInjection;
using Npgsql;

namespace Legacy.Maliev.ProcurementService.Tests.Integration;

// Caller-supplied retry-unit tests characterize storage faults beyond the currently
// rejected production manual transaction. They are not hosted authority acceptance.
public sealed class ProcurementSupplierTransactionBoundaryTests(ProcurementRuntimeFixture fixture)
    : IClassFixture<ProcurementRuntimeFixture>, IAsyncLifetime
{
    public Task InitializeAsync() => fixture.ResetAsync();
    public Task DisposeAsync() => Task.CompletedTask;

    [Fact]
    public async Task DeleteAddress_NormalConfiguredHttpPipeline_DetachesOnlyTheCurrentAddress()
    {
        var id = await SeedSupplierAsync();
        int addressId;
        await using (var seed = fixture.Factory.Services.CreateAsyncScope())
        {
            var database = seed.ServiceProvider.GetRequiredService<SupplierDbContext>();
            var address = new SupplierAddress { Address1 = "Existing", CountryId = 1 };
            database.Addresses.Add(address);
            await database.SaveChangesAsync();
            addressId = address.Id;
            (await database.Suppliers.SingleAsync()).AddressId = addressId;
            await database.SaveChangesAsync();
        }
        await using var factory = fixture.CreateFactory(true);
        using var client = fixture.ClientAs(factory, "service:procurement-parity", ProcurementPermissions.SupplierAddressesDelete);
        using var response = await client.DeleteAsync($"/suppliers/{id}/addresses/{addressId}");
        Assert.Equal(HttpStatusCode.NoContent, response.StatusCode);
        await using var scope = factory.Services.CreateAsyncScope();
        var current = scope.ServiceProvider.GetRequiredService<SupplierDbContext>();
        Assert.Null((await current.Suppliers.AsNoTracking().SingleAsync()).AddressId);
        Assert.Empty(await current.Addresses.AsNoTracking().ToArrayAsync());
    }

    [Fact]
    public async Task CallerSuppliedRetryUnit_FailureBetweenSaves_RollsBackInsertedAddressAndPointer()
    {
        var id = await SeedSupplierAsync();
        var fault = new BetweenSavesFault(transient: false);
        await using var factory = fixture.Factory.WithWebHostBuilder(builder => builder.ConfigureServices(services =>
            services.AddDbContext<SupplierDbContext>(options => options.AddInterceptors(fault))));
        await using (var scope = factory.Services.CreateAsyncScope())
        {
            var database = scope.ServiceProvider.GetRequiredService<SupplierDbContext>();
            var repository = scope.ServiceProvider.GetRequiredService<ISupplierRepository>();
            await Assert.ThrowsAsync<InvalidOperationException>(() => database.Database.CreateExecutionStrategy()
                .ExecuteAsync(() => repository.CreateAddressAsync(id, Address("Failed insert"), CancellationToken.None)));
        }
        Assert.True(fault.FaultReachedAfterInsert);
        await AssertGraphAsync(factory.Services, addressCount: 0, expectedAddressId: null);
    }

    [Fact]
    public async Task CallerSuppliedRetryUnit_TransientBetweenSaves_UsesFreshStateAndExactlyOneCommittedAddress()
    {
        var id = await SeedSupplierAsync();
        var fault = new BetweenSavesFault(transient: true);
        await using var factory = fixture.Factory.WithWebHostBuilder(builder => builder.ConfigureServices(services =>
            services.AddDbContext<SupplierDbContext>(options => options.AddInterceptors(fault))));
        SupplierAddressResponse? result = null;
        Exception? failure;
        await using (var scope = factory.Services.CreateAsyncScope())
        {
            var database = scope.ServiceProvider.GetRequiredService<SupplierDbContext>();
            var repository = scope.ServiceProvider.GetRequiredService<ISupplierRepository>();
            failure = await Record.ExceptionAsync(async () => result = await database.Database.CreateExecutionStrategy()
                .ExecuteAsync(() => repository.CreateAddressAsync(id, Address("Retried insert"), CancellationToken.None)));
        }
        Assert.True(fault.FaultReachedAfterInsert);
        Assert.True(failure is null, failure?.GetType().Name);
        Assert.NotNull(result);
        Assert.True(fault.ContextIds.Count >= 2, "A retried unit must not reuse rolled-back tracked entities.");
        await AssertGraphAsync(factory.Services, addressCount: 1, expectedAddressId: result.Id);
    }

    [Fact]
    public async Task CallerSuppliedRetryUnit_ActualCommitThenLostAcknowledgement_DoesNotCreateSecondAddress()
    {
        var id = await SeedSupplierAsync();
        var fault = new LostCommitAcknowledgement();
        await using var factory = fixture.Factory.WithWebHostBuilder(builder => builder.ConfigureServices(services =>
            services.AddDbContext<SupplierDbContext>(options => options.AddInterceptors(fault))));
        Exception? failure;
        await using (var scope = factory.Services.CreateAsyncScope())
        {
            var database = scope.ServiceProvider.GetRequiredService<SupplierDbContext>();
            var repository = scope.ServiceProvider.GetRequiredService<ISupplierRepository>();
            failure = await Record.ExceptionAsync(() => database.Database.CreateExecutionStrategy()
                .ExecuteAsync(() => repository.CreateAddressAsync(id, Address("Unknown acknowledgement"), CancellationToken.None)));
        }
        Assert.True(fault.CommittedFaultReached);
        await using var verify = factory.Services.CreateAsyncScope();
        var current = verify.ServiceProvider.GetRequiredService<SupplierDbContext>();
        var addresses = await current.Addresses.AsNoTracking().ToArrayAsync();
        Assert.Single(addresses);
        Assert.Equal(addresses[0].Id, (await current.Suppliers.AsNoTracking().SingleAsync()).AddressId);
        Assert.NotNull(failure); // An ambiguous acknowledgement is not invented success.
        Assert.IsNotType<NpgsqlException>(failure); // Must stop the generic transient retry.
    }

    [Fact]
    public async Task CallerSuppliedRetryUnit_CancellationAtHeldParentLock_DoesNotInsertCandidateBeforeIntentRead()
    {
        var id = await SeedSupplierAsync();
        var commands = new AddressInsertObserver();
        await using var factory = fixture.Factory.WithWebHostBuilder(builder => builder.ConfigureServices(services =>
            services.AddDbContext<SupplierDbContext>(options => options.AddInterceptors(commands))));
        await using var lockerScope = factory.Services.CreateAsyncScope();
        var locker = lockerScope.ServiceProvider.GetRequiredService<SupplierDbContext>();
        await locker.Database.OpenConnectionAsync();
        await using var held = await locker.Database.BeginTransactionAsync();
        await LockParentAsync(locker, held, id);
        using var cancellation = new CancellationTokenSource();
        await using var attemptScope = factory.Services.CreateAsyncScope();
        var database = attemptScope.ServiceProvider.GetRequiredService<SupplierDbContext>();
        var repository = attemptScope.ServiceProvider.GetRequiredService<ISupplierRepository>();
        var pending = database.Database.CreateExecutionStrategy().ExecuteAsync(() => repository.CreateAddressAsync(id, Address("Cancelled candidate"), cancellation.Token));
        Exception? failure;
        int observedInserts;
        try
        {
            await WaitForBlockedAttemptsAsync(locker, held, 1);
            observedInserts = commands.InsertCount;
            cancellation.Cancel();
            failure = await Record.ExceptionAsync(() => pending);
        }
        finally
        {
            cancellation.Cancel();
            await Record.ExceptionAsync(() => pending);
            await held.RollbackAsync();
        }
        Assert.IsAssignableFrom<OperationCanceledException>(failure);
        await AssertGraphAsync(factory.Services, 0, null);
        Assert.Equal(0, observedInserts);
    }

    [Fact]
    public async Task CallerSuppliedRetryUnits_ConcurrentExplicitReplacements_LockParentBeforeInsertsAndRetainSourceSemantics()
    {
        var id = await SeedSupplierAsync();
        var commands = new AddressInsertObserver();
        await using var factory = fixture.Factory.WithWebHostBuilder(builder => builder.ConfigureServices(services =>
            services.AddDbContext<SupplierDbContext>(options => options.AddInterceptors(commands))));
        await using var lockerScope = factory.Services.CreateAsyncScope();
        var locker = lockerScope.ServiceProvider.GetRequiredService<SupplierDbContext>();
        await locker.Database.OpenConnectionAsync();
        await using var held = await locker.Database.BeginTransactionAsync();
        await LockParentAsync(locker, held, id);
        var first = AttachAsync("Explicit replacement one");
        var second = AttachAsync("Explicit replacement two");
        int observedInserts;
        try
        {
            await WaitForBlockedAttemptsAsync(locker, held, 2);
            observedInserts = commands.InsertCount;
        }
        finally
        {
            await held.RollbackAsync();
        }
        var results = await Task.WhenAll(first, second);
        Assert.All(results, value => Assert.NotNull(value));
        await using var verify = factory.Services.CreateAsyncScope();
        var current = verify.ServiceProvider.GetRequiredService<SupplierDbContext>();
        Assert.Equal(2, await current.Addresses.CountAsync());
        Assert.Contains((await current.Suppliers.AsNoTracking().SingleAsync()).AddressId, results.Select(value => (int?)value!.Id));
        Assert.Equal(0, observedInserts);

        async Task<SupplierAddressResponse?> AttachAsync(string line)
        {
            await using var scope = factory.Services.CreateAsyncScope();
            var database = scope.ServiceProvider.GetRequiredService<SupplierDbContext>();
            var repository = scope.ServiceProvider.GetRequiredService<ISupplierRepository>();
            return await database.Database.CreateExecutionStrategy().ExecuteAsync(() => repository.CreateAddressAsync(id, Address(line), CancellationToken.None));
        }
    }

    private static async Task LockParentAsync(SupplierDbContext database, IDbContextTransaction transaction, int id)
    {
        await using var command = new NpgsqlCommand("SELECT \"ID\" FROM \"Supplier\" WHERE \"ID\" = @id FOR UPDATE",
            (NpgsqlConnection)database.Database.GetDbConnection(), (NpgsqlTransaction)transaction.GetDbTransaction());
        command.Parameters.AddWithValue("id", id);
        Assert.Equal(id, await command.ExecuteScalarAsync());
    }

    [Fact]
    public async Task CreateAddress_NormalHttpLostCommitAcknowledgement_ReturnsGeneric503WithoutReplay()
    {
        var id = await SeedSupplierAsync();
        var fault = new LostCommitAcknowledgement();
        await using var factory = fixture.Factory.WithWebHostBuilder(builder => builder.ConfigureServices(services =>
            services.AddDbContext<SupplierDbContext>(options => options.AddInterceptors(fault))));
        using var client = fixture.ClientAs(factory, "employee:transaction", ProcurementPermissions.SupplierAddressesWrite);
        using var response = await client.PostAsJsonAsync($"/suppliers/{id}/addresses", Address("Private address"));
        Assert.True(fault.CommittedFaultReached);
        Assert.Equal(HttpStatusCode.ServiceUnavailable, response.StatusCode);
        Assert.DoesNotContain("Private address", await response.Content.ReadAsStringAsync());
        await using var scope = factory.Services.CreateAsyncScope();
        var database = scope.ServiceProvider.GetRequiredService<SupplierDbContext>();
        var address = Assert.Single(await database.Addresses.AsNoTracking().ToArrayAsync());
        Assert.Equal(address.Id, (await database.Suppliers.AsNoTracking().SingleAsync()).AddressId);
    }

    [Fact]
    public async Task CreateAddress_CancellationAfterKnownCommit_ReturnsCommittedResultWithoutReplay()
    {
        var id = await SeedSupplierAsync();
        using var cancellation = new CancellationTokenSource();
        var fault = new CancelAfterKnownCommit(cancellation);
        await using var factory = fixture.Factory.WithWebHostBuilder(builder => builder.ConfigureServices(services =>
            services.AddDbContext<SupplierDbContext>(options => options.AddInterceptors(fault))));
        await using var scope = factory.Services.CreateAsyncScope();
        var result = await scope.ServiceProvider.GetRequiredService<ISupplierRepository>().CreateAddressAsync(id, Address("Known commit"), cancellation.Token);
        Assert.True(cancellation.IsCancellationRequested);
        Assert.NotNull(result);
        await AssertGraphAsync(factory.Services, 1, result.Id);
    }

    private sealed class CancelAfterKnownCommit(CancellationTokenSource cancellation) : DbTransactionInterceptor
    {
        public override Task TransactionCommittedAsync(DbTransaction transaction, TransactionEndEventData eventData, CancellationToken cancellationToken = default)
        {
            cancellation.Cancel();
            return Task.CompletedTask;
        }
    }

    [Fact]
    public async Task CallerSuppliedRetryUnit_TransactionTeardownAfterCommit_DoesNotReplayCommittedMutation()
    {
        var id = await SeedSupplierAsync();
        var fault = new TransactionTeardownFailure();
        await using var factory = fixture.Factory.WithWebHostBuilder(builder => builder.ConfigureServices(services =>
            services.AddDbContext<SupplierDbContext>(options => options.AddInterceptors(fault))));
        await using var scope = factory.Services.CreateAsyncScope();
        var database = scope.ServiceProvider.GetRequiredService<SupplierDbContext>();
        var repository = scope.ServiceProvider.GetRequiredService<ISupplierRepository>();
        var failure = await Record.ExceptionAsync(() => database.Database.CreateExecutionStrategy().ExecuteAsync(() =>
            repository.CreateAddressAsync(id, Address("Committed before teardown"), CancellationToken.None)));
        Assert.True(fault.FaultReached);
        await using var verify = factory.Services.CreateAsyncScope();
        var current = verify.ServiceProvider.GetRequiredService<SupplierDbContext>();
        var address = Assert.Single(await current.Addresses.AsNoTracking().ToArrayAsync());
        Assert.Equal(address.Id, (await current.Suppliers.AsNoTracking().SingleAsync()).AddressId);
        Assert.IsType<ProcurementTransactionUncertainException>(failure);
    }

    private sealed class TransactionTeardownFailure : DbConnectionInterceptor
    {
        public bool FaultReached { get; private set; }
        public override ValueTask<InterceptionResult> ConnectionDisposingAsync(DbConnection connection, ConnectionEventData eventData, InterceptionResult result)
        {
            if (FaultReached) return ValueTask.FromResult(result);
            FaultReached = true;
            throw new NpgsqlException("controlled teardown interruption", new IOException("controlled connection failure"));
        }
    }

    private static async Task WaitForBlockedAttemptsAsync(SupplierDbContext database, IDbContextTransaction transaction, int count)
    {
        var deadline = DateTime.UtcNow.AddSeconds(10);
        while (DateTime.UtcNow < deadline)
        {
            await using var command = new NpgsqlCommand("SELECT COUNT(DISTINCT pid)::int FROM pg_locks WHERE NOT granted AND pid <> pg_backend_pid()",
                (NpgsqlConnection)database.Database.GetDbConnection(), (NpgsqlTransaction)transaction.GetDbTransaction());
            if ((int)(await command.ExecuteScalarAsync())! >= count) return;
            await Task.Yield();
        }
        Assert.Fail("The controlled operations never reached the held parent database lock.");
    }

    private async Task<int> SeedSupplierAsync()
    {
        using var client = fixture.Client(ProcurementPermissions.SuppliersCreate);
        using var response = await client.PostAsJsonAsync("/Suppliers", new UpsertSupplierRequest("Transaction supplier", null, null, null, null, null, null, null));
        Assert.Equal(HttpStatusCode.Created, response.StatusCode);
        return (await response.Content.ReadFromJsonAsync<SupplierResponse>())!.Id;
    }
    private static UpsertSupplierAddressRequest Address(string line) => new(null, line, null, null, null, null, 1);
    private static async Task AssertGraphAsync(IServiceProvider services, int addressCount, int? expectedAddressId)
    {
        await using var scope = services.CreateAsyncScope();
        var database = scope.ServiceProvider.GetRequiredService<SupplierDbContext>();
        Assert.Equal(addressCount, await database.Addresses.CountAsync());
        Assert.Equal(expectedAddressId, (await database.Suppliers.AsNoTracking().SingleAsync()).AddressId);
        Assert.Empty(await scope.ServiceProvider.GetRequiredService<PurchaseOrderDbContext>().Addresses.ToArrayAsync());
    }

    private sealed class BetweenSavesFault(bool transient) : SaveChangesInterceptor
    {
        public bool FaultReachedAfterInsert { get; private set; }
        public HashSet<Guid> ContextIds { get; } = [];
        public override ValueTask<InterceptionResult<int>> SavingChangesAsync(DbContextEventData eventData, InterceptionResult<int> result, CancellationToken cancellationToken = default)
        {
            var database = eventData.Context!;
            ContextIds.Add(database.ContextId.InstanceId);
            if (!FaultReachedAfterInsert && database.ChangeTracker.Entries<Supplier>().Any(value => value.State == EntityState.Modified)
                && database.ChangeTracker.Entries<SupplierAddress>().Any(value => value.State == EntityState.Unchanged && value.Entity.Id > 0))
            {
                FaultReachedAfterInsert = true;
                if (transient) throw new NpgsqlException("controlled precommit interruption", new IOException("controlled connection failure"));
                throw new InvalidOperationException("controlled second-save failure");
            }
            return ValueTask.FromResult(result);
        }
    }

    private sealed class LostCommitAcknowledgement : DbTransactionInterceptor
    {
        public bool CommittedFaultReached { get; private set; }
        public override Task TransactionCommittedAsync(DbTransaction transaction, TransactionEndEventData eventData, CancellationToken cancellationToken = default)
        {
            if (!CommittedFaultReached)
            {
                CommittedFaultReached = true;
                throw new NpgsqlException("controlled lost commit acknowledgement", new IOException("controlled connection failure"));
            }
            return Task.CompletedTask;
        }
    }

    private sealed class AddressInsertObserver : DbCommandInterceptor
    {
        private int inserts;
        public int InsertCount => Volatile.Read(ref inserts);
        public override ValueTask<InterceptionResult<DbDataReader>> ReaderExecutingAsync(DbCommand command, CommandEventData eventData,
            InterceptionResult<DbDataReader> result, CancellationToken cancellationToken = default)
        {
            if (command.CommandText.Contains("INSERT INTO \"Address\"", StringComparison.Ordinal)) Interlocked.Increment(ref inserts);
            return ValueTask.FromResult(result);
        }
    }
}

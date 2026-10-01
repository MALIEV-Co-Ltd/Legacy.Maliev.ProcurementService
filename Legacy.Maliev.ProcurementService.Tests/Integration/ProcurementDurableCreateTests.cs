using System.IdentityModel.Tokens.Jwt;
using System.Net;
using System.Net.Http.Headers;
using System.Net.Http.Json;
using System.Security.Claims;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Legacy.Maliev.ProcurementService.Api.Authorization;
using Legacy.Maliev.ProcurementService.Application.Models;
using Legacy.Maliev.ProcurementService.Data;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Mvc.Testing;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Infrastructure;
using Microsoft.Extensions.Caching.Distributed;
using Microsoft.Extensions.Caching.Memory;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.DependencyInjection.Extensions;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Options;
using Microsoft.Extensions.Time.Testing;
using Microsoft.IdentityModel.Tokens;
using Testcontainers.PostgreSql;

namespace Legacy.Maliev.ProcurementService.Tests.Integration;

public sealed class ProcurementDurableCreateTests(ProcurementDurableCreateFixture fixture)
    : IClassFixture<ProcurementDurableCreateFixture>, IAsyncLifetime
{
    public Task InitializeAsync() => fixture.ResetAsync();
    public Task DisposeAsync() => Task.CompletedTask;

    [Fact]
    public async Task SupplierCreate_IdempotencyResponseWriteFails_AcknowledgedRetryDoesNotDuplicate()
    {
        using var client = fixture.Client(ProcurementPermissions.SuppliersCreate);
        client.DefaultRequestHeaders.Add("Idempotency-Key", "owned-failed-response-store");
        fixture.Cache.FailWrite = true;
        var first = await CreateSupplierAsync(client, "Retry supplier");
        fixture.Cache.FailWrite = false;
        var retry = await CreateSupplierAsync(client, "Retry supplier");
        Assert.Equal(first.Id, retry.Id);
        await using var scope = fixture.Factory.Services.CreateAsyncScope();
        Assert.Single(await scope.ServiceProvider.GetRequiredService<SupplierDbContext>().Suppliers.ToArrayAsync());
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task Create_CacheLossAfterAcknowledgement_ReplaysExactResponse(bool purchaseOrder)
    {
        await using var factory = fixture.CreateFactory(purchaseOrder);
        using var client = Client(factory, purchaseOrder, "actor-one");
        fixture.Cache.FailWrite = true;
        using var first = await PostAsync(client, purchaseOrder, Payload(purchaseOrder, "Original"));
        var body = await first.Content.ReadAsStringAsync();
        fixture.Cache.FailWrite = false;
        fixture.Clock.Advance(TimeSpan.FromMinutes(1));
        using var replay = await PostAsync(client, purchaseOrder, Payload(purchaseOrder, "Original"));
        Assert.Equal(HttpStatusCode.Created, first.StatusCode);
        Assert.Equal(HttpStatusCode.Created, replay.StatusCode);
        Assert.Equal(body, await replay.Content.ReadAsStringAsync());
        Assert.Equal(first.Headers.Location, replay.Headers.Location);
        Assert.Equal(1, await CountAsync(purchaseOrder));
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task Create_SameActorAndKeyChangedPayload_ConflictsWithoutMutation(bool purchaseOrder)
    {
        await using var factory = fixture.CreateFactory(purchaseOrder);
        using var client = Client(factory, purchaseOrder, "actor-one");
        using var first = await PostAsync(client, purchaseOrder, Payload(purchaseOrder, "Original"));
        using var conflict = await PostAsync(client, purchaseOrder, Payload(purchaseOrder, "Changed"));
        Assert.Equal(HttpStatusCode.Created, first.StatusCode);
        Assert.Equal(HttpStatusCode.Conflict, conflict.StatusCode);
        Assert.Equal(1, await CountAsync(purchaseOrder));
        var error = await conflict.Content.ReadAsStringAsync();
        Assert.DoesNotContain("Original", error);
        Assert.DoesNotContain("Changed", error);
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task Create_DifferentSignedActorSameKey_HasIndependentNamespace(bool purchaseOrder)
    {
        await using var factory = fixture.CreateFactory(purchaseOrder);
        using var firstClient = Client(factory, purchaseOrder, "actor-one");
        using var peerClient = Client(factory, purchaseOrder, "actor-two");
        using var first = await PostAsync(firstClient, purchaseOrder, Payload(purchaseOrder, "First actor"));
        using var peer = await PostAsync(peerClient, purchaseOrder, Payload(purchaseOrder, "Second actor"));
        Assert.Equal(HttpStatusCode.Created, first.StatusCode);
        Assert.Equal(HttpStatusCode.Created, peer.StatusCode);
        Assert.NotEqual(await IdAsync(first), await IdAsync(peer));
        Assert.Equal(2, await CountAsync(purchaseOrder));
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task Create_IndependentHostsConcurrentSameKey_CommitOneResponse(bool purchaseOrder)
    {
        var barrier = new BeforeRootSaveBarrier(purchaseOrder);
        await using var firstFactory = fixture.CreateFactory(purchaseOrder).WithWebHostBuilder(builder => builder.ConfigureServices(services =>
        {
            services.AddDbContext<SupplierDbContext>(options => options.AddInterceptors(barrier));
            services.AddDbContext<PurchaseOrderDbContext>(options => options.AddInterceptors(barrier));
        }));
        await using var secondFactory = fixture.CreateFactory(purchaseOrder);
        using var firstClient = Client(firstFactory, purchaseOrder, "actor-one");
        using var peerClient = Client(secondFactory, purchaseOrder, "actor-one");
        var firstTask = PostAsync(firstClient, purchaseOrder, Payload(purchaseOrder, "Concurrent"));
        HttpResponseMessage peer;
        try
        {
            await barrier.Entered.Task.WaitAsync(TimeSpan.FromSeconds(10));
            peer = await PostAsync(peerClient, purchaseOrder, Payload(purchaseOrder, "Concurrent"));
        }
        finally { barrier.Release.TrySetResult(); }
        using var first = await firstTask;
        using (peer)
        {
            Assert.Equal(HttpStatusCode.Created, first.StatusCode);
            Assert.Equal(HttpStatusCode.Created, peer.StatusCode);
            Assert.Equal(await peer.Content.ReadAsStringAsync(), await first.Content.ReadAsStringAsync());
            Assert.Equal(1, await CountAsync(purchaseOrder));
        }
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task Create_HealthyReplayRequiresCurrentPermission(bool purchaseOrder)
    {
        await using var factory = fixture.CreateFactory(purchaseOrder);
        using var allowed = Client(factory, purchaseOrder, "actor-one");
        using var first = await PostAsync(allowed, purchaseOrder, Payload(purchaseOrder, "Original"));
        using var denied = fixture.ClientAs(factory, Subject(purchaseOrder, "actor-one"));
        using var replay = await PostAsync(denied, purchaseOrder, Payload(purchaseOrder, "Original"));
        Assert.Equal(HttpStatusCode.Created, first.StatusCode);
        Assert.Equal(HttpStatusCode.Forbidden, replay.StatusCode);
        Assert.Equal(1, await CountAsync(purchaseOrder));
    }

    [Fact]
    public async Task SupplierCreate_NullAndOmittedFields_ReplaySameEffectivePayload()
    {
        using var client = fixture.Client(ProcurementPermissions.SuppliersCreate);
        using var first = await PostAsync(client, false, new { Name = "Optional fields" });
        using var replay = await PostAsync(client, false, Request("Optional fields"));
        Assert.Equal(HttpStatusCode.Created, first.StatusCode);
        Assert.Equal(await first.Content.ReadAsStringAsync(), await replay.Content.ReadAsStringAsync());
        Assert.Equal(1, await CountAsync(false));
    }

    [Fact]
    public async Task SupplierCreate_EmptyAndNullAreDifferentEffectivePayloads_Conflict()
    {
        using var client = fixture.Client(ProcurementPermissions.SuppliersCreate);
        using var first = await PostAsync(client, false, Request("Optional fields"));
        using var conflict = await PostAsync(client, false, Request("Optional fields") with { Website = "" });
        Assert.Equal(HttpStatusCode.Created, first.StatusCode);
        Assert.Equal(HttpStatusCode.Conflict, conflict.StatusCode);
        Assert.Equal(1, await CountAsync(false));
    }

    private HttpClient Client(WebApplicationFactory<Program> factory, bool purchaseOrder, string actor) =>
        fixture.ClientAs(factory, Subject(purchaseOrder, actor), purchaseOrder ? ProcurementPermissions.PurchaseOrdersCreate : ProcurementPermissions.SuppliersCreate);

    [Fact]
    public async Task SupplierCreate_AmbiguousSignedSubject_RejectsBeforeReceiptOrEffect()
    {
        using var client = fixture.ClientWithClaims(fixture.Factory,
            [new Claim("sub", "employee:first"), new Claim("sub", "employee:second"), new Claim("permission", ProcurementPermissions.SuppliersCreate)]);
        using var response = await PostAsync(client, false, Request("No ambiguous owner"));
        Assert.Equal(HttpStatusCode.Unauthorized, response.StatusCode);
        Assert.Equal(0, await CountAsync(false));
    }

    [Fact]
    public async Task SupplierCreate_WrongSignedIssuer_NormalMiddlewareRejectsWithoutEffect()
    {
        using var client = fixture.ClientWithClaims(fixture.Factory,
            [new Claim("sub", "employee:first"), new Claim("permission", ProcurementPermissions.SuppliersCreate)], "https://wrong-issuer.invalid");
        using var response = await PostAsync(client, false, Request("No untrusted issuer"));
        Assert.Equal(HttpStatusCode.Unauthorized, response.StatusCode);
        Assert.Equal(0, await CountAsync(false));
    }

    [Fact]
    public async Task PurchaseOrderCreate_DefaultOffExactServicePolicy_StillDeniesBeforeCreate()
    {
        using var client = fixture.ClientAs(fixture.Factory, "service:actor-one", ProcurementPermissions.PurchaseOrdersCreate);
        using var response = await PostAsync(client, true, Payload(true, "No policy bypass"));
        Assert.Equal(HttpStatusCode.Forbidden, response.StatusCode);
        Assert.Equal(0, await CountAsync(true));
    }

    [Theory]
    [InlineData(false, "multiple")]
    [InlineData(false, "oversized")]
    [InlineData(true, "multiple")]
    [InlineData(true, "oversized")]
    public async Task Create_InvalidIdempotencyHeader_RejectsBeforeEffect(bool purchaseOrder, string invalid)
    {
        await using var factory = fixture.CreateFactory(purchaseOrder);
        using var client = Client(factory, purchaseOrder, "actor-one");
        using var message = new HttpRequestMessage(HttpMethod.Post, purchaseOrder ? "/PurchaseOrders" : "/Suppliers") { Content = JsonContent.Create(Payload(purchaseOrder, "No invalid key")) };
        Assert.True(message.Headers.TryAddWithoutValidation("Idempotency-Key", invalid == "multiple" ? ["first-key", "second-key"] : [new string('k', 257)]));
        using var response = await client.SendAsync(message);
        Assert.Equal(HttpStatusCode.BadRequest, response.StatusCode);
        Assert.Equal(0, await CountAsync(purchaseOrder));
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task OwningDatabase_MigrationsContainIndependentDurableReceiptSchema(bool purchaseOrder)
    {
        await using var scope = fixture.Factory.Services.CreateAsyncScope();
        DbContext database = purchaseOrder ? scope.ServiceProvider.GetRequiredService<PurchaseOrderDbContext>() : scope.ServiceProvider.GetRequiredService<SupplierDbContext>();
        var expected = purchaseOrder ? "PurchaseOrderCreateReceipt" : "SupplierCreateReceipt";
        var tables = await database.Database.SqlQueryRaw<string>("SELECT tablename AS \"Value\" FROM pg_catalog.pg_tables WHERE schemaname = 'public'").ToListAsync();
        Assert.Contains(expected, tables);
        Assert.DoesNotContain(purchaseOrder ? "SupplierCreateReceipt" : "PurchaseOrderCreateReceipt", tables);
    }
    private static string Subject(bool purchaseOrder, string actor) => (purchaseOrder ? "service:" : "employee:") + actor;

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task Create_IndependentHostsConcurrentDifferentPayload_LoserConflictsAndRollsBackRoot(bool purchaseOrder)
    {
        var barrier = new BeforeRootSaveBarrier(purchaseOrder);
        await using var firstFactory = fixture.CreateFactory(purchaseOrder).WithWebHostBuilder(builder => builder.ConfigureServices(services =>
        {
            services.AddDbContext<SupplierDbContext>(options => options.AddInterceptors(barrier));
            services.AddDbContext<PurchaseOrderDbContext>(options => options.AddInterceptors(barrier));
        }));
        await using var peerFactory = fixture.CreateFactory(purchaseOrder);
        using var firstClient = Client(firstFactory, purchaseOrder, "actor-one");
        using var peerClient = Client(peerFactory, purchaseOrder, "actor-one");
        var firstTask = PostAsync(firstClient, purchaseOrder, Payload(purchaseOrder, "Losing payload"));
        HttpResponseMessage peer;
        try
        {
            await barrier.Entered.Task.WaitAsync(TimeSpan.FromSeconds(10));
            peer = await PostAsync(peerClient, purchaseOrder, Payload(purchaseOrder, "Winning payload"));
        }
        finally { barrier.Release.TrySetResult(); }
        using var first = await firstTask;
        using (peer)
        {
            Assert.Equal(HttpStatusCode.Created, peer.StatusCode);
            Assert.Equal(HttpStatusCode.Conflict, first.StatusCode);
            Assert.Equal(1, await CountAsync(purchaseOrder));
            Assert.Equal(1, await ReceiptCountAsync(purchaseOrder));
            using var replay = await PostAsync(peerClient, purchaseOrder, Payload(purchaseOrder, "Winning payload"));
            Assert.Equal(await peer.Content.ReadAsStringAsync(), await replay.Content.ReadAsStringAsync());
        }
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task Create_RenewedSignedToken_ReplaysOriginalBytesAndLocationAfterEntityDeletion(bool purchaseOrder)
    {
        await using var factory = fixture.CreateFactory(purchaseOrder);
        using var firstClient = Client(factory, purchaseOrder, "actor-one");
        using var first = await PostAsync(firstClient, purchaseOrder, Payload(purchaseOrder, "Historical"));
        var id = await IdAsync(first);
        await using (var scope = fixture.Factory.Services.CreateAsyncScope())
        {
            if (purchaseOrder) await scope.ServiceProvider.GetRequiredService<PurchaseOrderDbContext>().PurchaseOrders.Where(value => value.Id == id).ExecuteDeleteAsync();
            else await scope.ServiceProvider.GetRequiredService<SupplierDbContext>().Suppliers.Where(value => value.Id == id).ExecuteDeleteAsync();
        }
        fixture.Clock.Advance(TimeSpan.FromMinutes(1));
        using var renewed = Client(factory, purchaseOrder, "actor-one");
        Assert.NotEqual(firstClient.DefaultRequestHeaders.Authorization?.Parameter, renewed.DefaultRequestHeaders.Authorization?.Parameter);
        using var replay = await PostAsync(renewed, purchaseOrder, Payload(purchaseOrder, "Historical"));
        Assert.Equal(HttpStatusCode.Created, replay.StatusCode);
        Assert.Equal(await first.Content.ReadAsByteArrayAsync(), await replay.Content.ReadAsByteArrayAsync());
        Assert.Equal(first.Headers.Location, replay.Headers.Location);
        Assert.Equal(0, await CountAsync(purchaseOrder));
        Assert.Equal(1, await ReceiptCountAsync(purchaseOrder));
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task Create_CorruptPersistedResponse_FailsClosedWithoutAnotherRoot(bool purchaseOrder)
    {
        await using var factory = fixture.CreateFactory(purchaseOrder);
        using var client = Client(factory, purchaseOrder, "actor-one");
        using var first = await PostAsync(client, purchaseOrder, Payload(purchaseOrder, "Stored"));
        Assert.Equal(HttpStatusCode.Created, first.StatusCode);
        await using var scope = fixture.Factory.Services.CreateAsyncScope();
        var database = Database(scope.ServiceProvider, purchaseOrder);
        await database.Database.ExecuteSqlRawAsync(purchaseOrder
            ? "UPDATE \"PurchaseOrderCreateReceipt\" SET \"ResponseBody\" = {0}"
            : "UPDATE \"SupplierCreateReceipt\" SET \"ResponseBody\" = {0}", new object[] { Encoding.UTF8.GetBytes("{\"Id\":999}") });
        using var replay = await PostAsync(client, purchaseOrder, Payload(purchaseOrder, "Stored"));
        Assert.Equal(HttpStatusCode.ServiceUnavailable, replay.StatusCode);
        Assert.Equal(1, await CountAsync(purchaseOrder));
        Assert.Equal(1, await ReceiptCountAsync(purchaseOrder));
        Assert.DoesNotContain("Stored", await replay.Content.ReadAsStringAsync());
    }

    [Theory]
    [InlineData(false, "missing")]
    [InlineData(true, "missing")]
    [InlineData(false, "check")]
    [InlineData(true, "check")]
    [InlineData(false, "primary")]
    [InlineData(true, "primary")]
    [InlineData(false, "nullable")]
    [InlineData(true, "nullable")]
    public async Task Create_PhysicalReceiptSchemaDrift_WithMigrationHistoryIntact_Returns503BeforeEffect(bool purchaseOrder, string drift)
    {
        await using var factory = fixture.CreateFactory(purchaseOrder);
        using var client = Client(factory, purchaseOrder, "actor-one");
        await using var scope = fixture.Factory.Services.CreateAsyncScope();
        var database = Database(scope.ServiceProvider, purchaseOrder);
        var table = Table(purchaseOrder);
        var alter = drift switch
        {
            "missing" => $"ALTER TABLE \"{table}\" RENAME TO \"OwnedHiddenReceipt\"",
            "check" => $"ALTER TABLE \"{table}\" DROP CONSTRAINT \"CK_{table}_Complete\"",
            "primary" => $"ALTER TABLE \"{table}\" DROP CONSTRAINT \"PK_{table}\"",
            _ => $"ALTER TABLE \"{table}\" ALTER COLUMN \"ResponseDigest\" DROP NOT NULL"
        };
        var restore = drift switch
        {
            "missing" => $"ALTER TABLE \"OwnedHiddenReceipt\" RENAME TO \"{table}\"",
            "check" => $"ALTER TABLE \"{table}\" ADD CONSTRAINT \"CK_{table}_Complete\" CHECK (\"EntityId\" > 0 AND octet_length(\"ResponseBody\") > 0)",
            "primary" => $"ALTER TABLE \"{table}\" ADD CONSTRAINT \"PK_{table}\" PRIMARY KEY (\"IssuerDigest\", \"SubjectDigest\", \"Operation\", \"KeyDigest\")",
            _ => $"ALTER TABLE \"{table}\" ALTER COLUMN \"ResponseDigest\" SET NOT NULL"
        };
        var migrations = (await database.Database.GetAppliedMigrationsAsync()).ToArray();
        await database.Database.ExecuteSqlRawAsync(alter);
        try
        {
            using var response = await PostAsync(client, purchaseOrder, Payload(purchaseOrder, "No unsafe fallback"));
            Assert.Equal(HttpStatusCode.ServiceUnavailable, response.StatusCode);
            Assert.Equal(0, await CountAsync(purchaseOrder));
            Assert.Equal(migrations, (await database.Database.GetAppliedMigrationsAsync()).ToArray());
        }
        finally { await database.Database.ExecuteSqlRawAsync(restore); }
        using var recovered = await PostAsync(client, purchaseOrder, Payload(purchaseOrder, "No unsafe fallback"));
        Assert.Equal(HttpStatusCode.Created, recovered.StatusCode);
        Assert.Equal(1, await CountAsync(purchaseOrder));
    }

    [Theory]
    [InlineData(false, false)]
    [InlineData(true, false)]
    [InlineData(false, true)]
    [InlineData(true, true)]
    public async Task Create_ActualCommitThenLostAcknowledgementOrTeardown_FreshReceiptProvesNoReplay(bool purchaseOrder, bool teardown)
    {
        var acknowledgement = new LostAcknowledgement();
        var disposal = new LostTeardown();
        Microsoft.EntityFrameworkCore.Diagnostics.IInterceptor fault = teardown ? disposal : acknowledgement;
        await using var factory = fixture.CreateFactory(purchaseOrder).WithWebHostBuilder(builder => builder.ConfigureServices(services =>
        {
            services.AddDbContext<SupplierDbContext>(options => options.AddInterceptors(fault));
            services.AddDbContext<PurchaseOrderDbContext>(options => options.AddInterceptors(fault));
        }));
        using var client = Client(factory, purchaseOrder, "actor-one");
        using var first = await PostAsync(client, purchaseOrder, Payload(purchaseOrder, "Committed fault"));
        Assert.True(teardown ? disposal.Reached : acknowledgement.Reached);
        Assert.Equal(HttpStatusCode.Created, first.StatusCode);
        Assert.Equal(1, await CountAsync(purchaseOrder));
        Assert.Equal(1, await ReceiptCountAsync(purchaseOrder));
        using var replay = await PostAsync(client, purchaseOrder, Payload(purchaseOrder, "Committed fault"));
        Assert.Equal(await first.Content.ReadAsByteArrayAsync(), await replay.Content.ReadAsByteArrayAsync());
        Assert.Equal(first.Headers.Location, replay.Headers.Location);
    }

    private static string Table(bool purchaseOrder) => purchaseOrder ? "PurchaseOrderCreateReceipt" : "SupplierCreateReceipt";

    [Theory]
    [InlineData(false, "rls")]
    [InlineData(true, "rls")]
    [InlineData(false, "forced-rls")]
    [InlineData(true, "forced-rls")]
    [InlineData(false, "default")]
    [InlineData(true, "default")]
    [InlineData(false, "trigger")]
    [InlineData(true, "trigger")]
    [InlineData(false, "extra-fk")]
    [InlineData(true, "extra-fk")]
    [InlineData(false, "generated")]
    [InlineData(true, "generated")]
    [InlineData(false, "deferrable")]
    [InlineData(true, "deferrable")]
    public async Task Create_UnknownPhysicalReceiptBehavior_RejectsBeforeRootSave(bool purchaseOrder, string drift)
    {
        var observer = new RootSaveObserver();
        await using var factory = fixture.CreateFactory(purchaseOrder).WithWebHostBuilder(builder => builder.ConfigureServices(services =>
        {
            services.AddDbContext<SupplierDbContext>(options => options.AddInterceptors(observer));
            services.AddDbContext<PurchaseOrderDbContext>(options => options.AddInterceptors(observer));
        }));
        using var client = Client(factory, purchaseOrder, "actor-one");
        await using var scope = fixture.Factory.Services.CreateAsyncScope();
        var database = Database(scope.ServiceProvider, purchaseOrder);
        var table = Table(purchaseOrder);
        var root = purchaseOrder ? "PurchaseOrder" : "Supplier";
        var alter = drift switch
        {
            "rls" => $"ALTER TABLE \"{table}\" ENABLE ROW LEVEL SECURITY",
            "forced-rls" => $"ALTER TABLE \"{table}\" ENABLE ROW LEVEL SECURITY; ALTER TABLE \"{table}\" FORCE ROW LEVEL SECURITY",
            "default" => $"ALTER TABLE \"{table}\" ALTER COLUMN \"ResponseVersion\" SET DEFAULT 1",
            "trigger" => $"CREATE FUNCTION public.owned_receipt_noop() RETURNS trigger LANGUAGE plpgsql AS 'BEGIN RETURN NEW; END'; CREATE TRIGGER \"OwnedReceiptNoop\" BEFORE INSERT ON \"{table}\" FOR EACH ROW EXECUTE FUNCTION public.owned_receipt_noop()",
            "extra-fk" => $"ALTER TABLE \"{table}\" ADD CONSTRAINT \"OwnedUnexpectedForeignKey\" FOREIGN KEY (\"EntityId\") REFERENCES \"{root}\" (\"ID\") NOT VALID",
            "generated" => $"ALTER TABLE \"{table}\" ADD COLUMN \"OwnedUnexpectedGenerated\" integer GENERATED ALWAYS AS (1) STORED",
            _ => $"ALTER TABLE \"{table}\" DROP CONSTRAINT \"PK_{table}\"; ALTER TABLE \"{table}\" ADD CONSTRAINT \"PK_{table}\" PRIMARY KEY (\"IssuerDigest\", \"SubjectDigest\", \"Operation\", \"KeyDigest\") DEFERRABLE INITIALLY IMMEDIATE"
        };
        var restore = drift switch
        {
            "rls" or "forced-rls" => $"ALTER TABLE \"{table}\" NO FORCE ROW LEVEL SECURITY; ALTER TABLE \"{table}\" DISABLE ROW LEVEL SECURITY",
            "default" => $"ALTER TABLE \"{table}\" ALTER COLUMN \"ResponseVersion\" DROP DEFAULT",
            "trigger" => $"DROP TRIGGER \"OwnedReceiptNoop\" ON \"{table}\"; DROP FUNCTION public.owned_receipt_noop()",
            "extra-fk" => $"ALTER TABLE \"{table}\" DROP CONSTRAINT \"OwnedUnexpectedForeignKey\"",
            "generated" => $"ALTER TABLE \"{table}\" DROP COLUMN \"OwnedUnexpectedGenerated\"",
            _ => $"ALTER TABLE \"{table}\" DROP CONSTRAINT \"PK_{table}\"; ALTER TABLE \"{table}\" ADD CONSTRAINT \"PK_{table}\" PRIMARY KEY (\"IssuerDigest\", \"SubjectDigest\", \"Operation\", \"KeyDigest\")"
        };
        await database.Database.ExecuteSqlRawAsync(alter);
        try
        {
            using var response = await PostAsync(client, purchaseOrder, Payload(purchaseOrder, "No unknown schema"));
            Assert.Equal(HttpStatusCode.ServiceUnavailable, response.StatusCode);
            Assert.Equal(0, observer.Count);
            Assert.Equal(0, await CountAsync(purchaseOrder));
        }
        finally { await database.Database.ExecuteSqlRawAsync(restore); }
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task MigrationDown_RefusesDestructiveReceiptRemovalAndPreservesCommittedProof(bool purchaseOrder)
    {
        await using var factory = fixture.CreateFactory(purchaseOrder);
        using var client = Client(factory, purchaseOrder, "actor-one");
        using var created = await PostAsync(client, purchaseOrder, Payload(purchaseOrder, "Retained proof"));
        Assert.Equal(HttpStatusCode.Created, created.StatusCode);
        await using var scope = fixture.Factory.Services.CreateAsyncScope();
        var database = Database(scope.ServiceProvider, purchaseOrder);
        var migrator = database.GetService<Microsoft.EntityFrameworkCore.Migrations.IMigrator>();
        var before = (await database.Database.GetAppliedMigrationsAsync()).ToArray();
        try
        {
            var failure = await Record.ExceptionAsync(() => migrator.MigrateAsync(purchaseOrder ? "20260721031258_FixTimestampColumnType" : "20260721031252_FixTimestampColumnType"));
            Assert.IsType<InvalidOperationException>(failure);
            Assert.Equal(before, (await database.Database.GetAppliedMigrationsAsync()).ToArray());
            Assert.Equal(1, await ReceiptCountAsync(purchaseOrder));
            Assert.Equal(1, await CountAsync(purchaseOrder));
        }
        finally { await migrator.MigrateAsync(); }
    }

    private sealed class RootSaveObserver : Microsoft.EntityFrameworkCore.Diagnostics.SaveChangesInterceptor
    {
        public int Count { get; private set; }
        public override ValueTask<Microsoft.EntityFrameworkCore.Diagnostics.InterceptionResult<int>> SavingChangesAsync(Microsoft.EntityFrameworkCore.Diagnostics.DbContextEventData eventData,
            Microsoft.EntityFrameworkCore.Diagnostics.InterceptionResult<int> result, CancellationToken cancellationToken = default)
        {
            if (eventData.Context!.ChangeTracker.Entries().Any(value => value.Metadata.ClrType.Name is "Supplier" or "PurchaseOrder" && value.State == EntityState.Added)) Count++;
            return ValueTask.FromResult(result);
        }
    }

    [Theory]
    [InlineData(false, "transient")]
    [InlineData(true, "transient")]
    [InlineData(false, "rollback")]
    [InlineData(true, "rollback")]
    [InlineData(false, "cancel")]
    [InlineData(true, "cancel")]
    public async Task Create_FailureBetweenRootAndReceipt_ConfirmedRollbackOrFreshRetryPreservesAtomicity(bool purchaseOrder, string mode)
    {
        using var cancellation = new CancellationTokenSource();
        var fault = new ReceiptStageFault(mode, cancellation);
        var completed = new CompletedRequest();
        await using var factory = fixture.CreateFactory(purchaseOrder).WithWebHostBuilder(builder => builder.ConfigureServices(services =>
        {
            services.AddDbContext<SupplierDbContext>(options => options.AddInterceptors(fault));
            services.AddDbContext<PurchaseOrderDbContext>(options => options.AddInterceptors(fault));
            services.AddSingleton<IStartupFilter>(completed);
        }));
        using var client = Client(factory, purchaseOrder, "actor-one");
        using var message = new HttpRequestMessage(HttpMethod.Post, purchaseOrder ? "/PurchaseOrders" : "/Suppliers") { Content = JsonContent.Create(Payload(purchaseOrder, "Precommit fault")) };
        message.Headers.Add("Idempotency-Key", "owned-precommit-fault");
        HttpResponseMessage? response = null;
        var failure = await Record.ExceptionAsync(async () => response = await client.SendAsync(message, cancellation.Token));
        await completed.Completed.Task.WaitAsync(TimeSpan.FromSeconds(10));
        Assert.True(fault.ReachedAfterRootSave);
        using (response)
        {
            if (mode == "cancel") Assert.IsAssignableFrom<OperationCanceledException>(failure);
            else
            {
                Assert.Null(failure);
                Assert.NotNull(response);
                Assert.Equal(mode == "transient" ? HttpStatusCode.Created : HttpStatusCode.ServiceUnavailable, response.StatusCode);
            }
        }
        Assert.Equal(mode == "transient" ? 1 : 0, await CountAsync(purchaseOrder));
        Assert.Equal(mode == "transient" ? 1 : 0, await ReceiptCountAsync(purchaseOrder));
        if (mode == "transient") Assert.True(fault.ContextIds.Count >= 2, "Confirmed rollback retry requires fresh tracked state.");
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task Create_CommitAttemptExceptionWithoutReceipt_DoesNotRetryMutationAndReturns503(bool purchaseOrder)
    {
        var fault = new BeforeCommitFailure();
        await using var factory = fixture.CreateFactory(purchaseOrder).WithWebHostBuilder(builder => builder.ConfigureServices(services =>
        {
            services.AddDbContext<SupplierDbContext>(options => options.AddInterceptors(fault));
            services.AddDbContext<PurchaseOrderDbContext>(options => options.AddInterceptors(fault));
        }));
        using var client = Client(factory, purchaseOrder, "actor-one");
        using var incomplete = await PostAsync(client, purchaseOrder, Payload(purchaseOrder, "Unconfirmed commit"));
        Assert.Equal(1, fault.Attempts);
        Assert.Equal(HttpStatusCode.ServiceUnavailable, incomplete.StatusCode);
        Assert.Equal(0, await CountAsync(purchaseOrder));
        Assert.Equal(0, await ReceiptCountAsync(purchaseOrder));
        using var retry = await PostAsync(client, purchaseOrder, Payload(purchaseOrder, "Unconfirmed commit"));
        Assert.Equal(HttpStatusCode.Created, retry.StatusCode);
        Assert.Equal(1, await CountAsync(purchaseOrder));
        Assert.Equal(1, await ReceiptCountAsync(purchaseOrder));
    }

    private sealed class ReceiptStageFault(string mode, CancellationTokenSource cancellation) : Microsoft.EntityFrameworkCore.Diagnostics.SaveChangesInterceptor
    {
        public bool ReachedAfterRootSave { get; private set; }
        public HashSet<Guid> ContextIds { get; } = [];
        public override ValueTask<Microsoft.EntityFrameworkCore.Diagnostics.InterceptionResult<int>> SavingChangesAsync(Microsoft.EntityFrameworkCore.Diagnostics.DbContextEventData eventData,
            Microsoft.EntityFrameworkCore.Diagnostics.InterceptionResult<int> result, CancellationToken cancellationToken = default)
        {
            var context = eventData.Context!;
            ContextIds.Add(context.ContextId.InstanceId);
            if (!ReachedAfterRootSave && context.ChangeTracker.Entries().Any(value => value.Metadata.ClrType.Name == "CreateReceiptRecord" && value.State == EntityState.Added)
                && context.ChangeTracker.Entries().Any(value => value.Metadata.ClrType.Name is "Supplier" or "PurchaseOrder" && value.State == EntityState.Unchanged))
            {
                ReachedAfterRootSave = true;
                if (mode == "cancel") { cancellation.Cancel(); throw new OperationCanceledException(cancellationToken); }
                if (mode == "transient") throw new Npgsql.NpgsqlException("controlled precommit interruption", new IOException("controlled transport fault"));
                throw new InvalidOperationException("controlled unapplied receipt interruption");
            }
            return ValueTask.FromResult(result);
        }
    }
    private sealed class CompletedRequest : IStartupFilter
    {
        public TaskCompletionSource Completed { get; } = new(TaskCreationOptions.RunContinuationsAsynchronously);
        public Action<Microsoft.AspNetCore.Builder.IApplicationBuilder> Configure(Action<Microsoft.AspNetCore.Builder.IApplicationBuilder> next) => application =>
        {
            application.Use(nextMiddleware => async context =>
            {
                try { await nextMiddleware(context); }
                finally { if (context.Request.Method == "POST") Completed.TrySetResult(); }
            });
            next(application);
        };
    }
    private sealed class BeforeCommitFailure : Microsoft.EntityFrameworkCore.Diagnostics.DbTransactionInterceptor
    {
        public int Attempts { get; private set; }
        public override ValueTask<Microsoft.EntityFrameworkCore.Diagnostics.InterceptionResult> TransactionCommittingAsync(System.Data.Common.DbTransaction transaction, Microsoft.EntityFrameworkCore.Diagnostics.TransactionEventData eventData,
            Microsoft.EntityFrameworkCore.Diagnostics.InterceptionResult result, CancellationToken cancellationToken = default)
        {
            if (++Attempts == 1) throw new Npgsql.NpgsqlException("controlled commit attempt interruption", new IOException("controlled transport fault"));
            return ValueTask.FromResult(result);
        }
    }

    [Theory]
    [InlineData(false, "comma")]
    [InlineData(true, "comma")]
    [InlineData(false, "control")]
    [InlineData(true, "control")]
    [InlineData(false, "blank")]
    [InlineData(true, "blank")]
    [InlineData(false, "unicode-overflow")]
    [InlineData(true, "unicode-overflow")]
    public async Task Create_MalformedExactKey_RejectsWithoutReceipt(bool purchaseOrder, string kind)
    {
        await using var factory = fixture.CreateFactory(purchaseOrder);
        using var client = Client(factory, purchaseOrder, "actor-one");
        var key = kind switch { "comma" => "one,two", "control" => "one\ttwo", "blank" => "   ", _ => new string('é', 129) };
        using var response = await PostWithKeyAsync(client, purchaseOrder, Payload(purchaseOrder, "Invalid exact key"), key);
        Assert.Equal(HttpStatusCode.BadRequest, response.StatusCode);
        Assert.Equal(0, await CountAsync(purchaseOrder));
        Assert.Equal(0, await ReceiptCountAsync(purchaseOrder));
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task Create_ExactKeyCaseAndUtf8Boundary_AreDistinctValidatedNamespaces(bool purchaseOrder)
    {
        await using var factory = fixture.CreateFactory(purchaseOrder);
        using var client = Client(factory, purchaseOrder, "actor-one");
        foreach (var key in new[] { "Exact-Key", "exact-key", new string('é', 128) })
        {
            using var first = await PostWithKeyAsync(client, purchaseOrder, Payload(purchaseOrder, "Exact key"), key);
            using var replay = await PostWithKeyAsync(client, purchaseOrder, Payload(purchaseOrder, "Exact key"), key);
            Assert.Equal(HttpStatusCode.Created, first.StatusCode);
            Assert.Equal(HttpStatusCode.Created, replay.StatusCode);
            Assert.Equal(await first.Content.ReadAsByteArrayAsync(), await replay.Content.ReadAsByteArrayAsync());
        }
        Assert.Equal(3, await CountAsync(purchaseOrder));
        Assert.Equal(3, await ReceiptCountAsync(purchaseOrder));
    }

    [Theory]
    [InlineData(false, false)]
    [InlineData(true, false)]
    [InlineData(false, true)]
    [InlineData(true, true)]
    public async Task Create_DefaultOffOrAbsentKey_PreservesLegacyRootBehaviorWithoutReceipts(bool purchaseOrder, bool enabled)
    {
        await using var factory = fixture.CreateFactory(purchaseOrder, enabled);
        using var client = Client(factory, purchaseOrder, "actor-one");
        for (var attempt = 0; attempt < 2; attempt++)
        {
            using var response = await PostWithKeyAsync(client, purchaseOrder, Payload(purchaseOrder, "Legacy no durable activation"), enabled ? null : "owned-off-key");
            Assert.Equal(HttpStatusCode.Created, response.StatusCode);
            fixture.Cache.Clear();
        }
        Assert.Equal(2, await CountAsync(purchaseOrder));
        Assert.Equal(0, await ReceiptCountAsync(purchaseOrder));
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task Create_CommittedReceiptWithUnavailableFreshProof_Returns503WithoutReplayingEffect(bool purchaseOrder)
    {
        var fault = new PostCommitAction(async () =>
        {
            await using var scope = fixture.Factory.Services.CreateAsyncScope();
            await Database(scope.ServiceProvider, purchaseOrder).Database.ExecuteSqlRawAsync(purchaseOrder
                ? "ALTER TABLE \"PurchaseOrderCreateReceipt\" DROP CONSTRAINT \"CK_PurchaseOrderCreateReceipt_Complete\""
                : "ALTER TABLE \"SupplierCreateReceipt\" DROP CONSTRAINT \"CK_SupplierCreateReceipt_Complete\"");
        });
        await using var factory = fixture.CreateFactory(purchaseOrder).WithWebHostBuilder(builder => builder.ConfigureServices(services =>
        {
            services.AddDbContext<SupplierDbContext>(options => options.AddInterceptors(fault));
            services.AddDbContext<PurchaseOrderDbContext>(options => options.AddInterceptors(fault));
        }));
        using var client = Client(factory, purchaseOrder, "actor-one");
        try
        {
            using var incomplete = await PostAsync(client, purchaseOrder, Payload(purchaseOrder, "Committed unavailable proof"));
            Assert.Equal(HttpStatusCode.ServiceUnavailable, incomplete.StatusCode);
            Assert.Equal(1, fault.Attempts);
            Assert.Equal(1, await CountAsync(purchaseOrder));
            Assert.Equal(1, await ReceiptCountAsync(purchaseOrder));
        }
        finally
        {
            await using var scope = fixture.Factory.Services.CreateAsyncScope();
            await Database(scope.ServiceProvider, purchaseOrder).Database.ExecuteSqlRawAsync(purchaseOrder
                ? "ALTER TABLE \"PurchaseOrderCreateReceipt\" ADD CONSTRAINT \"CK_PurchaseOrderCreateReceipt_Complete\" CHECK (\"EntityId\" > 0 AND octet_length(\"ResponseBody\") > 0)"
                : "ALTER TABLE \"SupplierCreateReceipt\" ADD CONSTRAINT \"CK_SupplierCreateReceipt_Complete\" CHECK (\"EntityId\" > 0 AND octet_length(\"ResponseBody\") > 0)");
        }
        using var recovered = await PostAsync(client, purchaseOrder, Payload(purchaseOrder, "Committed unavailable proof"));
        Assert.Equal(HttpStatusCode.Created, recovered.StatusCode);
        Assert.Equal(1, await CountAsync(purchaseOrder));
        Assert.Equal(1, await ReceiptCountAsync(purchaseOrder));
    }

    private sealed class PostCommitAction(Func<Task> action) : Microsoft.EntityFrameworkCore.Diagnostics.DbTransactionInterceptor
    {
        public int Attempts { get; private set; }
        public override async Task TransactionCommittedAsync(System.Data.Common.DbTransaction transaction, Microsoft.EntityFrameworkCore.Diagnostics.TransactionEndEventData eventData, CancellationToken cancellationToken = default)
        {
            if (++Attempts == 1)
            {
                await action();
                throw new Npgsql.NpgsqlException("controlled lost acknowledgement", new IOException("controlled transport fault"));
            }
        }
    }

    [Theory]
    [InlineData(false, false)]
    [InlineData(true, false)]
    [InlineData(false, true)]
    [InlineData(true, true)]
    public async Task Create_CallerAbortAfterCommitOrDuringFreshProof_PreservesReceiptAndPropagatesAbort(bool purchaseOrder, bool duringProbe)
    {
        using var cancellation = new CancellationTokenSource();
        var completed = new CompletedRequest();
        var lostAck = new PostCommitAction(() =>
        {
            if (!duringProbe) cancellation.Cancel();
            return Task.CompletedTask;
        });
        var proofAbort = new CancelFreshProof(() => lostAck.Attempts > 0, cancellation);
        await using var factory = fixture.CreateFactory(purchaseOrder).WithWebHostBuilder(builder => builder.ConfigureServices(services =>
        {
            services.AddDbContext<SupplierDbContext>(options => options.AddInterceptors(lostAck, proofAbort));
            services.AddDbContext<PurchaseOrderDbContext>(options => options.AddInterceptors(lostAck, proofAbort));
            services.AddSingleton<IStartupFilter>(completed);
        }));
        using var client = Client(factory, purchaseOrder, "actor-one");
        using var message = new HttpRequestMessage(HttpMethod.Post, purchaseOrder ? "/PurchaseOrders" : "/Suppliers") { Content = JsonContent.Create(Payload(purchaseOrder, "Committed caller abort")) };
        message.Headers.Add("Idempotency-Key", "owned-durable-create");
        var failure = await Record.ExceptionAsync(async () =>
        {
            using var response = await client.SendAsync(message, cancellation.Token);
        });
        await completed.Completed.Task.WaitAsync(TimeSpan.FromSeconds(10));
        Assert.IsAssignableFrom<OperationCanceledException>(failure);
        Assert.Equal(1, lostAck.Attempts);
        Assert.Equal(duringProbe, proofAbort.Reached);
        Assert.Equal(1, await CountAsync(purchaseOrder));
        Assert.Equal(1, await ReceiptCountAsync(purchaseOrder));
        using var recovered = await PostAsync(client, purchaseOrder, Payload(purchaseOrder, "Committed caller abort"));
        Assert.Equal(HttpStatusCode.Created, recovered.StatusCode);
        Assert.Equal(1, await CountAsync(purchaseOrder));
        Assert.Equal(1, await ReceiptCountAsync(purchaseOrder));
    }

    private sealed class CancelFreshProof(Func<bool> committed, CancellationTokenSource cancellation) : Microsoft.EntityFrameworkCore.Diagnostics.DbCommandInterceptor
    {
        public bool Reached { get; private set; }
        public override ValueTask<Microsoft.EntityFrameworkCore.Diagnostics.InterceptionResult<System.Data.Common.DbDataReader>> ReaderExecutingAsync(System.Data.Common.DbCommand command,
            Microsoft.EntityFrameworkCore.Diagnostics.CommandEventData eventData, Microsoft.EntityFrameworkCore.Diagnostics.InterceptionResult<System.Data.Common.DbDataReader> result, CancellationToken cancellationToken = default)
        {
            if (!Reached && !cancellation.IsCancellationRequested && committed() && command.CommandText.Contains("CreateReceipt\"", StringComparison.Ordinal))
            {
                Reached = true;
                cancellation.Cancel();
                throw new OperationCanceledException(cancellationToken);
            }
            return ValueTask.FromResult(result);
        }
    }

    [Fact]
    public async Task PurchaseOrderCreate_SameSignedServiceAndKeyChangedEmployeeId_ConflictsWithoutChangingActorOrEffect()
    {
        await using var factory = fixture.CreateFactory(true);
        using var client = Client(factory, true, "legacy-intranet");
        var original = (UpsertPurchaseOrderRequest)Payload(true, "Employee scalar is not actor authority");
        using var first = await PostAsync(client, true, original);
        using var conflict = await PostAsync(client, true, original with { EmployeeId = original.EmployeeId + 1 });
        Assert.Equal(HttpStatusCode.Created, first.StatusCode);
        Assert.Equal(HttpStatusCode.Conflict, conflict.StatusCode);
        Assert.Equal(1, await CountAsync(true));
        Assert.Equal(1, await ReceiptCountAsync(true));
        await using var scope = fixture.Factory.Services.CreateAsyncScope();
        var stored = await scope.ServiceProvider.GetRequiredService<PurchaseOrderDbContext>().PurchaseOrders.SingleAsync();
        Assert.Equal(original.EmployeeId, stored.EmployeeId);
        using var replay = await PostAsync(client, true, original);
        Assert.Equal(HttpStatusCode.Created, replay.StatusCode);
        Assert.Equal(await first.Content.ReadAsByteArrayAsync(), await replay.Content.ReadAsByteArrayAsync());
    }
    private static async Task<HttpResponseMessage> PostWithKeyAsync(HttpClient client, bool purchaseOrder, object payload, string? key)
    {
        using var message = new HttpRequestMessage(HttpMethod.Post, purchaseOrder ? "/PurchaseOrders" : "/Suppliers") { Content = JsonContent.Create(payload) };
        if (key is not null) Assert.True(message.Headers.TryAddWithoutValidation("Idempotency-Key", key));
        return await client.SendAsync(message);
    }
    private static DbContext Database(IServiceProvider services, bool purchaseOrder) => purchaseOrder
        ? services.GetRequiredService<PurchaseOrderDbContext>() : services.GetRequiredService<SupplierDbContext>();
    private async Task<int> ReceiptCountAsync(bool purchaseOrder)
    {
        await using var scope = fixture.Factory.Services.CreateAsyncScope();
        return await Database(scope.ServiceProvider, purchaseOrder).Database.SqlQueryRaw<int>(purchaseOrder
            ? "SELECT count(*)::int AS \"Value\" FROM \"PurchaseOrderCreateReceipt\""
            : "SELECT count(*)::int AS \"Value\" FROM \"SupplierCreateReceipt\"").SingleAsync();
    }
    private sealed class LostAcknowledgement : Microsoft.EntityFrameworkCore.Diagnostics.DbTransactionInterceptor
    {
        public bool Reached { get; private set; }
        public override Task TransactionCommittedAsync(System.Data.Common.DbTransaction transaction, Microsoft.EntityFrameworkCore.Diagnostics.TransactionEndEventData eventData, CancellationToken cancellationToken = default)
        {
            if (!Reached) { Reached = true; throw new Npgsql.NpgsqlException("controlled lost acknowledgement", new IOException("controlled transport fault")); }
            return Task.CompletedTask;
        }
    }
    private sealed class LostTeardown : Microsoft.EntityFrameworkCore.Diagnostics.DbConnectionInterceptor
    {
        public bool Reached { get; private set; }
        public override ValueTask<Microsoft.EntityFrameworkCore.Diagnostics.InterceptionResult> ConnectionDisposingAsync(System.Data.Common.DbConnection connection, Microsoft.EntityFrameworkCore.Diagnostics.ConnectionEventData eventData, Microsoft.EntityFrameworkCore.Diagnostics.InterceptionResult result)
        {
            if (!Reached) { Reached = true; throw new Npgsql.NpgsqlException("controlled teardown interruption", new IOException("controlled transport fault")); }
            return ValueTask.FromResult(result);
        }
    }
    private static object Payload(bool purchaseOrder, string text) => purchaseOrder
        ? new UpsertPurchaseOrderRequest(92742, text, null, null, null, null, null, null, null, null, null, null, null, null, null, 93742, text)
        : Request(text);
    private static UpsertSupplierRequest Request(string name) => new(name, null, null, null, null, null, null, null);
    private static async Task<HttpResponseMessage> PostAsync(HttpClient client, bool purchaseOrder, object payload)
    {
        using var message = new HttpRequestMessage(HttpMethod.Post, purchaseOrder ? "/PurchaseOrders" : "/Suppliers") { Content = JsonContent.Create(payload) };
        message.Headers.Add("Idempotency-Key", "owned-durable-create");
        return await client.SendAsync(message);
    }
    private static async Task<int> IdAsync(HttpResponseMessage response) =>
        (await response.Content.ReadFromJsonAsync<JsonElement>()).GetProperty("Id").GetInt32();
    private async Task<int> CountAsync(bool purchaseOrder)
    {
        await using var scope = fixture.Factory.Services.CreateAsyncScope();
        return purchaseOrder ? await scope.ServiceProvider.GetRequiredService<PurchaseOrderDbContext>().PurchaseOrders.CountAsync()
            : await scope.ServiceProvider.GetRequiredService<SupplierDbContext>().Suppliers.CountAsync();
    }
    private static async Task<SupplierResponse> CreateSupplierAsync(HttpClient client, string name)
    {
        using var response = await client.PostAsJsonAsync("/Suppliers", Request(name));
        Assert.Equal(HttpStatusCode.Created, response.StatusCode);
        return (await response.Content.ReadFromJsonAsync<SupplierResponse>())!;
    }
    private sealed class BeforeRootSaveBarrier(bool purchaseOrder) : Microsoft.EntityFrameworkCore.Diagnostics.SaveChangesInterceptor
    {
        public TaskCompletionSource Entered { get; } = new(TaskCreationOptions.RunContinuationsAsynchronously);
        public TaskCompletionSource Release { get; } = new(TaskCreationOptions.RunContinuationsAsynchronously);
        private int reached;
        public override async ValueTask<Microsoft.EntityFrameworkCore.Diagnostics.InterceptionResult<int>> SavingChangesAsync(
            Microsoft.EntityFrameworkCore.Diagnostics.DbContextEventData eventData,
            Microsoft.EntityFrameworkCore.Diagnostics.InterceptionResult<int> result, CancellationToken cancellationToken = default)
        {
            if (((purchaseOrder && eventData.Context is PurchaseOrderDbContext) || (!purchaseOrder && eventData.Context is SupplierDbContext))
                && Interlocked.Exchange(ref reached, 1) == 0)
            {
                Entered.TrySetResult();
                await Release.Task.WaitAsync(cancellationToken);
            }
            return result;
        }
    }
}

public sealed class ProcurementDurableCreateFixture : IAsyncLifetime
{
    private readonly PostgreSqlContainer supplier = new PostgreSqlBuilder("postgres:18.1-bookworm").Build();
    private readonly PostgreSqlContainer order = new PostgreSqlBuilder("postgres:18.1-bookworm").Build();
    private readonly RSA signingKey = RSA.Create(2048);
    public ProcurementDurableCreateFactory Factory { get; private set; } = null!;
    public ProcurementDurableCreateCache Cache { get; } = new();
    public FakeTimeProvider Clock { get; } = new(new DateTimeOffset(2026, 10, 1, 0, 0, 0, TimeSpan.Zero));
    public ProcurementDurableCreateFactory CreateFactory(bool optIn, bool durable = true) => new(supplier.GetConnectionString(), order.GetConnectionString(), signingKey, Cache, Clock, optIn, durable);

    public async Task InitializeAsync()
    {
        await Task.WhenAll(supplier.StartAsync(), order.StartAsync());
        Factory = CreateFactory(false);
        await using var scope = Factory.Services.CreateAsyncScope();
        await scope.ServiceProvider.GetRequiredService<SupplierDbContext>().Database.MigrateAsync();
        await scope.ServiceProvider.GetRequiredService<PurchaseOrderDbContext>().Database.MigrateAsync();
    }

    public async Task ResetAsync()
    {
        Cache.FailRemoval = Cache.FailWrite = false;
        Cache.Clear();
        await using var scope = Factory.Services.CreateAsyncScope();
        await scope.ServiceProvider.GetRequiredService<SupplierDbContext>().Database.ExecuteSqlRawAsync("TRUNCATE TABLE \"SupplierCreateReceipt\", \"Supplier\", \"Address\" RESTART IDENTITY CASCADE");
        await scope.ServiceProvider.GetRequiredService<PurchaseOrderDbContext>().Database.ExecuteSqlRawAsync("TRUNCATE TABLE \"PurchaseOrderCreateReceipt\", \"PurchaseOrder\", \"Address\", \"OrderItem\", \"PurchaseOrderFile\" RESTART IDENTITY CASCADE");
    }

    public HttpClient Client(params string[] permissions)
        => ClientAs(Factory, "employee:procurement-parity", permissions);

    public HttpClient ClientAs(WebApplicationFactory<Program> factory, string subject, params string[] permissions)
    {
        var claims = new[] { new Claim(JwtRegisteredClaimNames.Sub, subject) }
            .Concat(permissions.Select(value => new Claim("permission", value))).Append(new Claim("jti", Guid.NewGuid().ToString("D")));
        return ClientWithClaims(factory, claims);
    }

    public HttpClient ClientWithClaims(WebApplicationFactory<Program> factory, IEnumerable<Claim> claims, string issuer = "https://procurement-parity.invalid")
    {
        var client = factory.CreateClient();
        var token = new JwtSecurityToken(issuer, "procurement-parity", claims,
            DateTime.UtcNow.AddMinutes(-1), DateTime.UtcNow.AddMinutes(5), new SigningCredentials(new RsaSecurityKey(signingKey), SecurityAlgorithms.RsaSha256));
        client.DefaultRequestHeaders.Authorization = new AuthenticationHeaderValue("Bearer", new JwtSecurityTokenHandler().WriteToken(token));
        return client;
    }

    public async Task DisposeAsync()
    {
        if (Factory is not null) await Factory.DisposeAsync();
        await supplier.DisposeAsync();
        await order.DisposeAsync();
        signingKey.Dispose();
    }
}

public sealed class ProcurementDurableCreateFactory(string supplierConnection, string orderConnection, RSA key, ProcurementDurableCreateCache cache, TimeProvider clock, bool optIn, bool durable) : WebApplicationFactory<Program>
{
    protected override void ConfigureWebHost(IWebHostBuilder builder)
    {
        builder.UseEnvironment("Production");
        builder.ConfigureServices(services =>
        {
            services.RemoveAll<IDistributedCache>();
            services.AddSingleton<IDistributedCache>(cache);
            services.RemoveAll<TimeProvider>();
            services.AddSingleton(clock);
        });
    }

    protected override IHost CreateHost(IHostBuilder builder)
    {
        builder.ConfigureHostConfiguration(configuration => configuration.AddInMemoryCollection(new Dictionary<string, string?>
        {
            ["Jwt:PublicKey"] = Convert.ToBase64String(Encoding.UTF8.GetBytes(key.ExportSubjectPublicKeyInfoPem())),
            ["Jwt:Issuer"] = "https://procurement-parity.invalid",
            ["Jwt:Audience"] = "procurement-parity",
            ["Features:AllowExactServiceClaimsForLiveCheck"] = optIn.ToString(),
            ["Procurement:DurableCreates:Enabled"] = durable.ToString(),
            ["ConnectionStrings:SupplierDbContext"] = supplierConnection,
            ["ConnectionStrings:PurchaseOrderDbContext"] = orderConnection,
            ["Cache:RedisEnabled"] = "false",
            ["Observability:TracingEnabled"] = "false",
            ["Observability:RuntimeMetricsEnabled"] = "false",
        }));
        return base.CreateHost(builder);
    }
}

public sealed class ProcurementDurableCreateCache : IDistributedCache
{
    private MemoryDistributedCache inner = Create();
    public bool FailWrite { get; set; }
    public bool FailRemoval { get; set; }
    private int delayedWrites;
    public TaskCompletionSource WriteEntered { get; private set; } = new(TaskCreationOptions.RunContinuationsAsynchronously);
    public TaskCompletionSource ReleaseWrite { get; private set; } = new(TaskCreationOptions.RunContinuationsAsynchronously);
    public void DelayNextWrite()
    {
        WriteEntered = new(TaskCreationOptions.RunContinuationsAsynchronously);
        ReleaseWrite = new(TaskCreationOptions.RunContinuationsAsynchronously);
        delayedWrites = 1;
    }
    private static MemoryDistributedCache Create() => new(Options.Create(new MemoryDistributedCacheOptions()));
    public void Clear() => inner = Create();
    public byte[]? Get(string key) => inner.Get(key);
    public Task<byte[]?> GetAsync(string key, CancellationToken token = default) => inner.GetAsync(key, token);
    public void Set(string key, byte[] value, DistributedCacheEntryOptions options) => inner.Set(key, value, options);
    public async Task SetAsync(string key, byte[] value, DistributedCacheEntryOptions options, CancellationToken token = default)
    {
        if (FailWrite) throw new InvalidOperationException("controlled cache write failure");
        if (Interlocked.Exchange(ref delayedWrites, 0) == 1)
        {
            WriteEntered.TrySetResult();
            await ReleaseWrite.Task.WaitAsync(token);
        }
        await inner.SetAsync(key, value, options, token);
    }
    public void Remove(string key) => inner.Remove(key);
    public Task RemoveAsync(string key, CancellationToken token = default) =>
        FailRemoval ? Task.FromException(new InvalidOperationException("controlled cache removal failure")) : inner.RemoveAsync(key, token);
    public void Refresh(string key) => inner.Refresh(key);
    public Task RefreshAsync(string key, CancellationToken token = default) => inner.RefreshAsync(key, token);
}

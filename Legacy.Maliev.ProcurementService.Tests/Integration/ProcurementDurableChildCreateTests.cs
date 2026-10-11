using System.Data.Common;
using System.Net;
using System.Net.Http.Json;
using System.Security.Cryptography;
using System.Text.Json;
using Legacy.Maliev.ProcurementService.Api.Authorization;
using Legacy.Maliev.ProcurementService.Application.Models;
using Legacy.Maliev.ProcurementService.Data;
using Legacy.Maliev.ProcurementService.Domain;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Mvc.Testing;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Diagnostics;
using Microsoft.EntityFrameworkCore.Infrastructure;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;

namespace Legacy.Maliev.ProcurementService.Tests.Integration;

public sealed class ProcurementDurableChildCreateTests(ProcurementDurableCreateFixture fixture)
    : IClassFixture<ProcurementDurableCreateFixture>, IAsyncLifetime
{
    private static readonly string[] Scenarios = ["default-off", "no-header", "replay", "cache-loss", "payload-conflict", "parent-conflict", "actor", "multiple-key", "blank-key", "long-key", "canonical", "updated-body", "corrupt-digest", "corrupt-parent", "missing-table", "wrong-operation", "database-unavailable", "rollback", "concurrent", "concurrent-conflict", "lost-ack", "rollback-uncertain", "deleted-child", "permission"];
    public static IEnumerable<object[]> Cases()
    {
        foreach (var file in new[] { false, true }) foreach (var scenario in Scenarios) yield return [file, scenario];
        yield return [false, "reparent"];
        yield return [true, "reparent"];
        yield return [false, "parent-to-null"];
        yield return [false, "null-to-parent"];
        yield return [false, "null-replay"];
        yield return [false, "deleted-parent"];
        yield return [true, "deleted-parent"];
    }
    public async Task InitializeAsync()
    {
        await fixture.ResetAsync();
        await using var scope = fixture.Factory.Services.CreateAsyncScope();
        await scope.ServiceProvider.GetRequiredService<PurchaseOrderDbContext>().Database.ExecuteSqlRawAsync("TRUNCATE TABLE \"OrderItemCreateReceipt\", \"PurchaseOrderFileCreateReceipt\"");
    }
    public Task DisposeAsync() => Task.CompletedTask;

    [Theory]
    [MemberData(nameof(Cases))]
    public async Task ChildCreate_AtomicReplayAndAssociationContract(bool file, string scenario)
    {
        var parent = await SeedParentAsync();
        var otherParent = await SeedParentAsync();
        int? originalParent = scenario is "null-replay" or "null-to-parent" ? null : parent;
        await using var app = App(scenario != "default-off");
        using var client = Client(app, "service:child-one", file);
        var key = "child-attempt";
        if (scenario == "blank-key") key = " ";
        if (scenario == "long-key") key = new string('k', 257);
        if (scenario is "multiple-key" or "blank-key" or "long-key")
        {
            using var invalid = await PostAsync(client, file, originalParent, key, multiple: scenario == "multiple-key");
            Assert.Equal(HttpStatusCode.BadRequest, invalid.StatusCode);
            await CountsAsync(file, 0, 0);
            return;
        }
        if (scenario == "database-unavailable")
        {
            await using var unavailable = App(true, orderConnection: "Host=127.0.0.1;Port=1;Database=child-refusal;Timeout=1;Command Timeout=1;Pooling=false");
            using var writer = Client(unavailable, "service:child-one", file);
            using var refusal = await PostAsync(writer, file, originalParent, key);
            Assert.Equal(HttpStatusCode.ServiceUnavailable, refusal.StatusCode);
            await CountsAsync(file, 0, 0);
            using var recovery = await PostAsync(client, file, originalParent, key);
            Assert.Equal(HttpStatusCode.Created, recovery.StatusCode);
            await CountsAsync(file, 1, 1);
            return;
        }
        if (scenario is "rollback" or "lost-ack" or "rollback-uncertain")
        {
            var acknowledgement = new LostChildAcknowledgement();
            var receiptFault = new ChildReceiptSaveFault();
            var rollbackFault = scenario == "rollback-uncertain" ? new ChildRollbackFault() : null;
            await using var faulty = App(true, scenario == "lost-ack" ? acknowledgement : receiptFault, secondFault: rollbackFault);
            using var writer = Client(faulty, "service:child-one", file);
            using var result = await PostAsync(writer, file, originalParent, key);
            Assert.True(scenario == "lost-ack" ? acknowledgement.Reached : receiptFault.Reached);
            if (rollbackFault is not null) Assert.True(rollbackFault.Reached);
            Assert.Equal(scenario == "lost-ack" ? HttpStatusCode.Created : HttpStatusCode.ServiceUnavailable, result.StatusCode);
            await CountsAsync(file, scenario == "lost-ack" ? 1 : 0, scenario == "lost-ack" ? 1 : 0);
            using var retry = await PostAsync(client, file, originalParent, key);
            Assert.Equal(HttpStatusCode.Created, retry.StatusCode);
            await CountsAsync(file, 1, 1);
            return;
        }
        if (scenario is "missing-table" or "wrong-operation")
        {
            var table = Table(file);
            await using var scope = fixture.Factory.Services.CreateAsyncScope();
            var database = scope.ServiceProvider.GetRequiredService<PurchaseOrderDbContext>();
            var mutate = scenario == "missing-table" ? $"ALTER TABLE \"{table}\" RENAME TO \"HeldChildReceipt\"" : $"ALTER TABLE \"{table}\" DROP CONSTRAINT \"CK_{table}_Operation\"; ALTER TABLE \"{table}\" ADD CONSTRAINT \"CK_{table}_Operation\" CHECK (\"Operation\" = 9)";
            var restore = scenario == "missing-table" ? $"ALTER TABLE \"HeldChildReceipt\" RENAME TO \"{table}\"" : $"ALTER TABLE \"{table}\" DROP CONSTRAINT \"CK_{table}_Operation\"; ALTER TABLE \"{table}\" ADD CONSTRAINT \"CK_{table}_Operation\" CHECK (\"Operation\" = {(file ? 4 : 3)})";
            await database.Database.ExecuteSqlRawAsync(mutate);
            try { using var refusal = await PostAsync(client, file, originalParent, key); Assert.Equal(HttpStatusCode.ServiceUnavailable, refusal.StatusCode); }
            finally { await database.Database.ExecuteSqlRawAsync(restore); }
            await CountsAsync(file, 0, 0);
            return;
        }
        if (scenario is "concurrent" or "concurrent-conflict")
        {
            var barrier = new ReceiptBarrier();
            await using var firstApp = App(true, barrier);
            await using var secondApp = App(true, barrier);
            using var firstClient = Client(firstApp, "service:child-one", file);
            using var secondClient = Client(secondApp, "service:child-one", file);
            var first = PostAsync(firstClient, file, originalParent, key);
            Task<HttpResponseMessage>? second = null;
            try
            {
                await barrier.Entered.Task.WaitAsync(TimeSpan.FromSeconds(10));
                second = PostAsync(secondClient, file, originalParent, key, scenario == "concurrent-conflict" ? "changed" : "original");
                await barrier.BothEntered.Task.WaitAsync(TimeSpan.FromSeconds(10));
                barrier.Release.TrySetResult();
                using var winner = await first.WaitAsync(TimeSpan.FromSeconds(20));
                barrier.PeerRelease.TrySetResult();
                using var peer = await second.WaitAsync(TimeSpan.FromSeconds(20));
                Assert.Equal(HttpStatusCode.Created, winner.StatusCode);
                Assert.Equal(scenario == "concurrent-conflict" ? HttpStatusCode.Conflict : HttpStatusCode.Created, peer.StatusCode);
                if (scenario == "concurrent") Assert.Equal(await winner.Content.ReadAsStringAsync(), await peer.Content.ReadAsStringAsync());
                await CountsAsync(file, 1, 1);
            }
            finally
            {
                barrier.Release.TrySetResult();
                barrier.PeerRelease.TrySetResult();
                using var firstResponse = await first.WaitAsync(TimeSpan.FromSeconds(20));
                if (second is not null) { using var secondResponse = await second.WaitAsync(TimeSpan.FromSeconds(20)); }
            }
            return;
        }
using var created = await PostAsync(client, file, originalParent, scenario == "no-header" ? null : key);
        Assert.Equal(HttpStatusCode.Created, created.StatusCode);
        Assert.Equal("application/json", created.Content.Headers.ContentType!.MediaType);
        var body = await created.Content.ReadAsStringAsync();
        using var json = JsonDocument.Parse(body);
        var id = json.RootElement.GetProperty("Id").GetInt32();
        if (scenario == "null-replay")
        {
            Assert.False(json.RootElement.TryGetProperty("PurchaseOrderId", out _));
            await using var scope = fixture.Factory.Services.CreateAsyncScope();
            var database = scope.ServiceProvider.GetRequiredService<PurchaseOrderDbContext>();
            Assert.Equal(2, await database.PurchaseOrders.ExecuteDeleteAsync());
            Assert.Empty(await database.PurchaseOrders.ToArrayAsync());
        }
        var expected = HttpStatusCode.Created;
        var count = 1;
        var receipts = scenario is "default-off" or "no-header" ? 0 : 1;
        var nextParent = originalParent;
        var text = "original";
        if (scenario is "default-off" or "no-header") count = 2;
        if (scenario == "cache-loss") { fixture.Cache.Clear(); fixture.Cache.FailWrite = true; }
        if (scenario == "payload-conflict") { text = "changed"; expected = HttpStatusCode.Conflict; }
        if (scenario == "parent-conflict") { nextParent = otherParent; expected = HttpStatusCode.Conflict; }
        if (scenario == "actor")
        {
            using var actor = Client(app, "service:child-two", file);
            using var independent = await PostAsync(actor, file, originalParent, key);
            Assert.Equal(HttpStatusCode.Created, independent.StatusCode);
            await CountsAsync(file, 2, 2);
            return;
        }
        if (scenario == "permission")
        {
            using var denied = fixture.ClientAs(app, "service:child-one", ProcurementPermissions.PurchaseOrdersRead);
            using var result = await PostAsync(denied, file, originalParent, key);
            Assert.Equal(HttpStatusCode.Forbidden, result.StatusCode);
            await CountsAsync(file, 1, 1);
            return;
        }
        if (scenario is "updated-body" or "reparent" or "parent-to-null" or "null-to-parent" or "deleted-parent")
        {
            var changedParent = scenario == "parent-to-null" ? null : scenario is "reparent" or "null-to-parent" or "deleted-parent" ? otherParent : originalParent;
            using var update = await client.PutAsJsonAsync(file ? $"/purchaseorders/files/{id}" : $"/purchaseorders/orderitems/{id}", file
                ? (object)new UpsertPurchaseOrderFileRequest(changedParent, "edited-bucket", "edited-object")
                : new UpsertOrderItemRequest(changedParent, "edited-part", "edited-description", 8, 9.25m));
            Assert.Equal(HttpStatusCode.NoContent, update.StatusCode);
            if (scenario != "updated-body") expected = HttpStatusCode.Conflict;
            if (scenario == "deleted-parent")
            {
                await using var scope = fixture.Factory.Services.CreateAsyncScope();
                Assert.Equal(1, await scope.ServiceProvider.GetRequiredService<PurchaseOrderDbContext>().PurchaseOrders.Where(value => value.Id == parent).ExecuteDeleteAsync());
            }
        }
        if (scenario == "deleted-child")
        {
            using var delete = await client.DeleteAsync(file ? $"/purchaseorders/files/{id}" : $"/purchaseorders/orderitems/{id}");
            Assert.Equal(HttpStatusCode.NoContent, delete.StatusCode);
            expected = HttpStatusCode.Conflict; count = 0;
        }
        if (scenario is "corrupt-digest" or "corrupt-parent")
        {
            await using var scope = fixture.Factory.Services.CreateAsyncScope();
            var database = scope.ServiceProvider.GetRequiredService<PurchaseOrderDbContext>();
            if (scenario == "corrupt-digest") await database.Database.ExecuteSqlRawAsync(file
                ? "UPDATE \"PurchaseOrderFileCreateReceipt\" SET \"ResponseDigest\"=decode(repeat('00',32),'hex')"
                : "UPDATE \"OrderItemCreateReceipt\" SET \"ResponseDigest\"=decode(repeat('00',32),'hex')");
            else
            {
                var properties = JsonSerializer.Deserialize<Dictionary<string, JsonElement>>(body)!;
                properties.Remove("PurchaseOrderId");
                var missing = JsonSerializer.Serialize(properties);
                var variants = new List<string> { missing };
                if (!file)
                {
                    variants.Add(body.Replace($"\"PurchaseOrderId\":{parent}", "\"PurchaseOrderId\":null", StringComparison.Ordinal));
                    variants.Add(body.Replace($"\"PurchaseOrderId\":{parent}", $"\"PurchaseOrderId\":{otherParent}", StringComparison.Ordinal));
                    variants.Add(body.Replace($"\"PurchaseOrderId\":{parent}", "\"PurchaseOrderId\":\"invalid\"", StringComparison.Ordinal));
                    variants.Add(body.Replace("\"PurchaseOrderId\"", "\"purchaseOrderId\"", StringComparison.Ordinal));
                    variants.Add(body.Insert(1, $"\"PurchaseOrderId\":{otherParent},"));
                }
                foreach (var invalid in variants)
                {
                    Assert.NotEqual(body, invalid);
                    var corrupted = System.Text.Encoding.UTF8.GetBytes(invalid);
                    await database.Database.ExecuteSqlRawAsync(file
                        ? "UPDATE \"PurchaseOrderFileCreateReceipt\" SET \"ResponseBody\"={0}, \"ResponseDigest\"={1}"
                        : "UPDATE \"OrderItemCreateReceipt\" SET \"ResponseBody\"={0}, \"ResponseDigest\"={1}", corrupted, SHA256.HashData(corrupted));
                    using var shapeRefusal = await PostAsync(client, file, originalParent, key);
                    Assert.Equal(HttpStatusCode.ServiceUnavailable, shapeRefusal.StatusCode);
                    await CountsAsync(file, 1, 1);
                }
            }
            expected = HttpStatusCode.ServiceUnavailable;
        }
        if (scenario == "canonical")
        {
            using var canonical = new HttpRequestMessage(HttpMethod.Post, file ? $"/purchaseorders/{originalParent}/files?bucket=owned-fixture&objectName=%6Friginal" : "/purchaseorders/orderitems");
            canonical.Headers.Add("Idempotency-Key", key);
            if (!file) canonical.Content = JsonContent.Create(new { PurchaseOrderId = originalParent, PartNumber = "original", Quantity = 3, UnitPrice = 12.34m });
            using var canonicalResult = await client.SendAsync(canonical);
            Assert.Equal(HttpStatusCode.Created, canonicalResult.StatusCode);
            Assert.Equal(body, await canonicalResult.Content.ReadAsStringAsync());
            if (!file)
            {
                using var emptyDescription = new HttpRequestMessage(HttpMethod.Post, "/purchaseorders/orderitems") { Content = JsonContent.Create(new UpsertOrderItemRequest(originalParent, "original", "", 3, 12.34m)) };
                emptyDescription.Headers.Add("Idempotency-Key", key);
                using var mismatch = await client.SendAsync(emptyDescription);
                Assert.Equal(HttpStatusCode.Conflict, mismatch.StatusCode);
            }
        }
        var beforeReplay = await SnapshotAsync();
        using var replay = await PostAsync(client, file, nextParent, scenario == "no-header" ? null : key, text);
        Assert.Equal(expected, replay.StatusCode);
        if (expected == HttpStatusCode.Created && scenario is not ("default-off" or "no-header"))
        {
            Assert.Equal("application/json", replay.Content.Headers.ContentType!.MediaType);
            Assert.Equal("utf-8", replay.Content.Headers.ContentType.CharSet);
            Assert.Equal(body, await replay.Content.ReadAsStringAsync());
            Assert.Equal(created.Headers.Location, replay.Headers.Location);
            Assert.Contains("no-store", replay.Headers.CacheControl!.ToString());
        }
        await CountsAsync(file, count, receipts);
        if (scenario is not ("default-off" or "no-header")) Assert.Equal(beforeReplay, await SnapshotAsync());
    }

    [Fact]
    public async Task FileCreate_MissingParentDoesNotCreateReceiptOrMetadata()
    {
        await using var app = App(true);
        using var client = Client(app, "service:child-one", true);
        using var result = await PostAsync(client, true, 999999, "missing-parent");
        Assert.Equal(HttpStatusCode.NotFound, result.StatusCode);
        await CountsAsync(true, 0, 0);
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task ChildReceiptMigration_PreservesParentConstraintAndRefusesProofRemoval(bool file)
    {
        var parent = await SeedParentAsync();
        await using var app = App(true);
        using var client = Client(app, "service:child-one", file);
        using var result = await PostAsync(client, file, parent, "retained-child-proof");
        Assert.Equal(HttpStatusCode.Created, result.StatusCode);
        await using var scope = fixture.Factory.Services.CreateAsyncScope();
        var database = scope.ServiceProvider.GetRequiredService<PurchaseOrderDbContext>();
        var constraints = await database.Database.SqlQueryRaw<string>("SELECT pg_get_constraintdef(oid) AS \"Value\" FROM pg_constraint WHERE conname='CK_PurchaseOrderCreateReceipt_Operation'").ToArrayAsync();
        Assert.Single(constraints);
        Assert.Equal("CHECKOperation=2", new string(constraints[0].Where(character => !char.IsWhiteSpace(character) && character is not '(' and not ')' and not '"').ToArray()));
        var migrations = (await database.Database.GetAppliedMigrationsAsync()).ToArray();
        var actual = await Record.ExceptionAsync(() => database.GetService<Microsoft.EntityFrameworkCore.Migrations.IMigrator>().MigrateAsync(migrations[^2]));
        Assert.IsType<InvalidOperationException>(actual);
        Assert.Equal(migrations, (await database.Database.GetAppliedMigrationsAsync()).ToArray());
        await CountsAsync(file, 1, 1);
    }
private WebApplicationFactory<Program> App(bool enabled, IInterceptor? fault = null, string? orderConnection = null, IInterceptor? secondFault = null) => fixture.CreateFactory(true).WithWebHostBuilder(builder =>
    {
        builder.ConfigureAppConfiguration((_, config) =>
        {
            var settings = new Dictionary<string, string?> { ["Procurement:DurableChildCreates:Enabled"] = enabled.ToString() };
            if (orderConnection is not null) settings["ConnectionStrings:PurchaseOrderDbContext"] = orderConnection;
            config.AddInMemoryCollection(settings);
        });
        if (fault is not null) builder.ConfigureServices(services => services.AddDbContext<PurchaseOrderDbContext>(options =>
        {
            options.AddInterceptors(fault);
            if (secondFault is not null) options.AddInterceptors(secondFault);
        }));
    });
        private HttpClient Client(WebApplicationFactory<Program> app, string actor, bool file)
    {
        var client = fixture.ClientAs(app, actor,
            file ? ProcurementPermissions.FilesWrite : ProcurementPermissions.OrderItemsWrite,
            file ? ProcurementPermissions.FilesDelete : ProcurementPermissions.OrderItemsDelete);
        client.Timeout = TimeSpan.FromSeconds(30);
        return client;
    }
private static async Task<HttpResponseMessage> PostAsync(HttpClient client, bool file, int? parent, string? key, string text = "original", bool multiple = false)
    {
        using var request = new HttpRequestMessage(HttpMethod.Post, file ? $"/purchaseorders/{parent}/files?bucket=owned-fixture&objectName={Uri.EscapeDataString(text)}" : "/purchaseorders/orderitems");
        if (!file) request.Content = JsonContent.Create(new UpsertOrderItemRequest(parent, text, null, 3, 12.34m));
        if (key is not null) request.Headers.TryAddWithoutValidation("Idempotency-Key", multiple ? [key, "other"] : [key]);
        return await client.SendAsync(request);
    }
    private async Task<int> SeedParentAsync()
    {
        await using var scope = fixture.Factory.Services.CreateAsyncScope();
        var database = scope.ServiceProvider.GetRequiredService<PurchaseOrderDbContext>();
        var parent = new PurchaseOrder { Notes = "Child replay fixture" };
        database.PurchaseOrders.Add(parent); await database.SaveChangesAsync(); return parent.Id;
    }
    private static string Table(bool file) => file ? "PurchaseOrderFileCreateReceipt" : "OrderItemCreateReceipt";
    private async Task CountsAsync(bool file, int children, int receipts)
    {
        await using var scope = fixture.Factory.Services.CreateAsyncScope();
        var database = scope.ServiceProvider.GetRequiredService<PurchaseOrderDbContext>();
        Assert.Equal(children, file ? await database.Files.CountAsync() : await database.OrderItems.CountAsync());
        Assert.Equal(receipts, await database.Database.SqlQueryRaw<int>(file
            ? "SELECT count(*)::int AS \"Value\" FROM \"PurchaseOrderFileCreateReceipt\""
            : "SELECT count(*)::int AS \"Value\" FROM \"OrderItemCreateReceipt\"").SingleAsync());
        Assert.Equal(0, file ? await database.OrderItems.CountAsync() : await database.Files.CountAsync());
        Assert.Empty(await scope.ServiceProvider.GetRequiredService<SupplierDbContext>().Suppliers.ToArrayAsync());
        Assert.Empty(await scope.ServiceProvider.GetRequiredService<SupplierDbContext>().Addresses.ToArrayAsync());
        Assert.Empty(await database.Addresses.ToArrayAsync());
        Assert.Equal(0, await database.Database.SqlQueryRaw<int>("SELECT count(*)::int AS \"Value\" FROM \"PurchaseOrderCreateReceipt\"").SingleAsync());
    }
    private async Task<string> SnapshotAsync()
    {
        await using var scope = fixture.Factory.Services.CreateAsyncScope();
        var suppliers = scope.ServiceProvider.GetRequiredService<SupplierDbContext>();
        var orders = scope.ServiceProvider.GetRequiredService<PurchaseOrderDbContext>();
        return JsonSerializer.Serialize(new
        {
            Suppliers = await suppliers.Suppliers.AsNoTracking().OrderBy(value => value.Id).ToArrayAsync(),
            SupplierAddresses = await suppliers.Addresses.AsNoTracking().OrderBy(value => value.Id).ToArrayAsync(),
            Parents = await orders.PurchaseOrders.AsNoTracking().OrderBy(value => value.Id).ToArrayAsync(),
            Addresses = await orders.Addresses.AsNoTracking().OrderBy(value => value.Id).ToArrayAsync(),
            Items = await orders.OrderItems.AsNoTracking().OrderBy(value => value.Id).ToArrayAsync(),
            Files = await orders.Files.AsNoTracking().OrderBy(value => value.Id).ToArrayAsync(),
            ItemReceipts = await orders.Database.SqlQueryRaw<string>("SELECT row_to_json(t)::text AS \"Value\" FROM \"OrderItemCreateReceipt\" t ORDER BY \"IssuerDigest\", \"SubjectDigest\", \"KeyDigest\"").ToArrayAsync(),
            FileReceipts = await orders.Database.SqlQueryRaw<string>("SELECT row_to_json(t)::text AS \"Value\" FROM \"PurchaseOrderFileCreateReceipt\" t ORDER BY \"IssuerDigest\", \"SubjectDigest\", \"KeyDigest\"").ToArrayAsync()
        });
    }
private sealed class ReceiptBarrier : SaveChangesInterceptor
    {
        public TaskCompletionSource Entered { get; } = new(TaskCreationOptions.RunContinuationsAsynchronously);
        public TaskCompletionSource Release { get; } = new(TaskCreationOptions.RunContinuationsAsynchronously);
        public TaskCompletionSource BothEntered { get; } = new(TaskCreationOptions.RunContinuationsAsynchronously);
        public TaskCompletionSource PeerRelease { get; } = new(TaskCreationOptions.RunContinuationsAsynchronously);
        private int enteredCount;
        public override async ValueTask<InterceptionResult<int>> SavingChangesAsync(DbContextEventData data, InterceptionResult<int> result, CancellationToken token = default)
        {
            if (data.Context!.ChangeTracker.Entries().Any(value => value.Metadata.ClrType.Name.EndsWith("ChildReceiptRecord", StringComparison.Ordinal)))
                        {
                Entered.TrySetResult();
                var position = Interlocked.Increment(ref enteredCount);
                if (position == 2) BothEntered.TrySetResult();
                await (position == 1 ? Release.Task : PeerRelease.Task).WaitAsync(TimeSpan.FromSeconds(10), token);
            }
            return result;
        }
    }
        private sealed class ChildReceiptSaveFault : SaveChangesInterceptor
    {
        public bool Reached { get; private set; }
        public override ValueTask<InterceptionResult<int>> SavingChangesAsync(DbContextEventData data, InterceptionResult<int> result, CancellationToken token = default)
        {
            if (data.Context!.ChangeTracker.Entries().Any(value => value.Metadata.ClrType.Name.EndsWith("ChildReceiptRecord", StringComparison.Ordinal) && value.State == EntityState.Added))
            { Reached = true; throw new InvalidOperationException("Controlled refusal after entity save and before receipt save."); }
            return ValueTask.FromResult(result);
        }
    }
    private sealed class ChildRollbackFault : DbTransactionInterceptor
    {
        public bool Reached { get; private set; }
        public override ValueTask<InterceptionResult> TransactionRollingBackAsync(DbTransaction transaction, TransactionEventData data, InterceptionResult result, CancellationToken token = default)
        {
            Reached = true;
            throw new InvalidOperationException("Controlled rollback acknowledgement loss.");
        }
    }
    private sealed class LostChildAcknowledgement : DbTransactionInterceptor
    {
        public bool Reached { get; private set; }
        public override Task TransactionCommittedAsync(DbTransaction transaction, TransactionEndEventData data, CancellationToken token = default)
        {
            if (!Reached) { Reached = true; throw new Npgsql.NpgsqlException("Controlled child acknowledgement loss.", new IOException("Controlled transport failure.")); }
            return Task.CompletedTask;
        }
    }
}

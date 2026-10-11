using System.Net;
using System.Net.Http.Json;
using Legacy.Maliev.ProcurementService.Api.Authorization;
using Legacy.Maliev.ProcurementService.Application.Interfaces;
using Legacy.Maliev.ProcurementService.Application.Models;
using Legacy.Maliev.ProcurementService.Data;
using Legacy.Maliev.ProcurementService.Domain;
using Microsoft.AspNetCore.Mvc.Testing;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.DependencyInjection;

namespace Legacy.Maliev.ProcurementService.Tests.Integration;

public sealed class PurchaseOrderFileBucketWriteGuardTests(ProcurementRuntimeFixture fixture)
    : IClassFixture<ProcurementRuntimeFixture>, IAsyncLifetime
{
    public Task InitializeAsync() => fixture.ResetAsync();
    public Task DisposeAsync() => Task.CompletedTask;

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task LiteralUtf16Boundary_RoundTripsCreateAndUpdateWithUnboundedObjectName(bool supplementary)
    {
        await using var app = fixture.CreateFactory(true);
        await SeedAsync(app);
        using var client = fixture.ClientAs(app, "service:procurement-parity", ProcurementPermissions.FilesWrite, ProcurementPermissions.FilesRead);
        var exact = supplementary ? string.Concat(Enumerable.Repeat("😀", 24)) + "  " : new string('ก', 48) + "  ";
        Assert.Equal(50, exact.Length);
        var objectName = " " + new string('ก', 200) + ".step ";
        using var created = await CreateAsync(client, 93, exact, objectName);
        Assert.Equal(HttpStatusCode.Created, created.StatusCode);
        var file = (await created.Content.ReadFromJsonAsync<PurchaseOrderFileResponse>())!;
        Assert.Equal(exact, file.Bucket);
        Assert.Equal(objectName, file.ObjectName);
        using var update = await client.PutAsJsonAsync($"/purchaseorders/files/{file.Id}", new UpsertPurchaseOrderFileRequest(93, exact, objectName + " revision "));
        Assert.Equal(HttpStatusCode.NoContent, update.StatusCode);
        var fresh = (await client.GetFromJsonAsync<PurchaseOrderFileResponse>($"/purchaseorders/files/{file.Id}"))!;
        Assert.Equal(exact, fresh.Bucket);
        Assert.Equal(objectName + " revision ", fresh.ObjectName);
        await using var scope = app.Services.CreateAsyncScope();
        var stored = await scope.ServiceProvider.GetRequiredService<PurchaseOrderDbContext>().Files.AsNoTracking().SingleAsync();
        Assert.Equal(fresh, Response(stored));
    }

    [Theory]
    [InlineData("")]
    [InlineData("  ")]
    [InlineData(" ก padded ")]
    public async Task JsonUpdateAndDirectWrites_PreserveAcceptedEmptyAndPadding(string literal)
    {
        await using var app = fixture.CreateFactory(true);
        await SeedAsync(app);
        await using var scope = app.Services.CreateAsyncScope();
        var repository = scope.ServiceProvider.GetRequiredService<IPurchaseOrderRepository>();
        var file = (await repository.CreateFileAsync(93, literal, "long-" + new string('ก', 100), default))!;
        Assert.Equal(literal, file.Bucket);
        using var client = fixture.ClientAs(app, "service:procurement-parity", ProcurementPermissions.FilesWrite, ProcurementPermissions.FilesRead);
        using var update = await client.PutAsJsonAsync($"/purchaseorders/files/{file.Id}", new UpsertPurchaseOrderFileRequest(93, literal, "literal.step"));
        Assert.Equal(HttpStatusCode.NoContent, update.StatusCode);
        var fresh = (await client.GetFromJsonAsync<PurchaseOrderFileResponse>($"/purchaseorders/files/{file.Id}"))!;
        Assert.Equal(literal, fresh.Bucket);
        Assert.True(await repository.UpdateFileAsync(file.Id, new UpsertPurchaseOrderFileRequest(93, literal, "direct.step"), default));
        await using var read = app.Services.CreateAsyncScope();
        Assert.Equal(literal, (await read.ServiceProvider.GetRequiredService<PurchaseOrderDbContext>().Files.AsNoTracking().SingleAsync()).Bucket);
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task ApiOverflowAt51_IsBadRequestAndLeavesBothDatabaseGraphsUnchanged(bool supplementary)
    {
        await using var app = fixture.CreateFactory(true);
        await SeedAsync(app);
        using var client = fixture.ClientAs(app, "service:procurement-parity", ProcurementPermissions.FilesWrite, ProcurementPermissions.FilesRead);
        using var created = await CreateAsync(client, 93, "original", "original.step");
        Assert.Equal(HttpStatusCode.Created, created.StatusCode);
        var file = (await created.Content.ReadFromJsonAsync<PurchaseOrderFileResponse>())!;
        var before = await GraphAsync(app);
        var invalid = supplementary ? string.Concat(Enumerable.Repeat("😀", 25)) + "ก" : new string('ก', 51);
        Assert.Equal(51, invalid.Length);
        using var create = await CreateAsync(client, 93, invalid, "changed.step");
        using var update = await client.PutAsJsonAsync($"/purchaseorders/files/{file.Id}", new UpsertPurchaseOrderFileRequest(93, invalid, "changed.step"));
        Assert.Equal(HttpStatusCode.BadRequest, create.StatusCode);
        Assert.Equal(HttpStatusCode.BadRequest, update.StatusCode);
        Assert.Equal(before, await GraphAsync(app));
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task MissingParentOrFile_PrecedesBucketOverflow(bool update)
    {
        await using var app = fixture.CreateFactory(true);
        await SeedAsync(app);
        using var client = fixture.ClientAs(app, "service:procurement-parity", ProcurementPermissions.FilesWrite);
        var before = await GraphAsync(app);
        var invalid = new string('ก', 51);
        using var response = update
            ? await client.PutAsJsonAsync("/purchaseorders/files/999999", new UpsertPurchaseOrderFileRequest(999999, invalid, "changed.step"))
            : await CreateAsync(client, 999999, invalid, "changed.step");
        Assert.Equal(HttpStatusCode.NotFound, response.StatusCode);
        Assert.Equal(before, await GraphAsync(app));
    }

    [Theory]
    [InlineData(null)]
    [InlineData("bmp")]
    [InlineData("supplementary")]
    public async Task DirectRepositoryInvalidBucket_FailsBeforeTrackedMutationAndRetainsMissingPrecedence(string? mode)
    {
        await using var app = fixture.CreateFactory(true);
        await SeedAsync(app);
        await using var scope = app.Services.CreateAsyncScope();
        var repository = scope.ServiceProvider.GetRequiredService<IPurchaseOrderRepository>();
        var file = (await repository.CreateFileAsync(93, "original", "original.step", default))!;
        var before = await GraphAsync(app);
        var invalid = mode is null ? null : mode == "bmp" ? new string('ก', 51) : string.Concat(Enumerable.Repeat("😀", 26));
        await Assert.ThrowsAsync<ArgumentException>(() => repository.CreateFileAsync(93, invalid!, "changed.step", default));
        await Assert.ThrowsAsync<ArgumentException>(() => repository.UpdateFileAsync(file.Id, new UpsertPurchaseOrderFileRequest(93, invalid!, "changed.step"), default));
        Assert.Null(await repository.CreateFileAsync(999999, invalid!, "changed.step", default));
        Assert.False(await repository.UpdateFileAsync(999999, new UpsertPurchaseOrderFileRequest(93, invalid!, "changed.step"), default));
        var database = scope.ServiceProvider.GetRequiredService<PurchaseOrderDbContext>();
        Assert.DoesNotContain(database.ChangeTracker.Entries(), entry => entry.State is EntityState.Modified or EntityState.Added or EntityState.Deleted);
        Assert.Equal(file, Response(await database.Files.FindAsync(file.Id) ?? throw new InvalidOperationException("Synthetic file disappeared.")));
        Assert.Equal(before, await GraphAsync(app));
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task MissingAuthorization_RefusesBeforeFileMutation(bool authenticated)
    {
        await using var app = fixture.CreateFactory(true);
        await SeedAsync(app);
        using var client = authenticated ? fixture.ClientAs(app, "service:procurement-parity", ProcurementPermissions.PurchaseOrdersRead) : app.CreateClient();
        var before = await GraphAsync(app);
        using var response = await CreateAsync(client, 93, new string('ก', 51), "changed.step");
        Assert.Equal(authenticated ? HttpStatusCode.Forbidden : HttpStatusCode.Unauthorized, response.StatusCode);
        Assert.Equal(before, await GraphAsync(app));
    }

    private static Task<HttpResponseMessage> CreateAsync(HttpClient client, int owner, string bucket, string objectName) => client.PostAsync($"/purchaseorders/{owner}/files?bucket={Uri.EscapeDataString(bucket)}&objectName={Uri.EscapeDataString(objectName)}", null);
    private static PurchaseOrderFileResponse Response(PurchaseOrderFile row) => new(row.Id, row.PurchaseOrderId, row.Bucket, row.ObjectName, row.CreatedDate, row.ModifiedDate);
    private static async Task SeedAsync(WebApplicationFactory<Program> app)
    {
        await using var scope = app.Services.CreateAsyncScope();
        var orders = scope.ServiceProvider.GetRequiredService<PurchaseOrderDbContext>();
        orders.PurchaseOrders.Add(new PurchaseOrder { Id = 93 });
        await orders.SaveChangesAsync();
        var suppliers = scope.ServiceProvider.GetRequiredService<SupplierDbContext>();
        suppliers.Suppliers.Add(new Supplier { Id = 91, Name = "Synthetic retained supplier" });
        await suppliers.SaveChangesAsync();
    }
    private static async Task<string> GraphAsync(WebApplicationFactory<Program> app)
    {
        await using var scope = app.Services.CreateAsyncScope();
        using var lifetime = new CancellationTokenSource(TimeSpan.FromSeconds(45));
        var snapshots = new List<string>();
        foreach (var boundary in new[]
        {
            (Context: (DbContext)scope.ServiceProvider.GetRequiredService<SupplierDbContext>(), Tables: new[] { "Address", "Supplier", "SupplierCreateReceipt" }),
            (Context: (DbContext)scope.ServiceProvider.GetRequiredService<PurchaseOrderDbContext>(), Tables: new[] { "Address", "PurchaseOrder", "OrderItem", "PurchaseOrderFile", "PurchaseOrderCreateReceipt" }),
        })
            foreach (var table in boundary.Tables)
            {
                var sql = $"SELECT COALESCE(jsonb_agg(to_jsonb(r) ORDER BY to_jsonb(r)::text)::text,'[]') AS \"Value\" FROM public.\"{table}\" r";
                snapshots.Add(boundary.Context.GetType().Name + ":" + table + ":" + await boundary.Context.Database.SqlQueryRaw<string>(sql).SingleAsync(lifetime.Token));
            }
        return string.Join("\n", snapshots);
    }
}

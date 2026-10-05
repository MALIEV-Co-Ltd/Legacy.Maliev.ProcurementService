using System.Net;
using System.Text.Json;
using Legacy.Maliev.ProcurementService.Api.Authorization;
using Legacy.Maliev.ProcurementService.Data;
using Legacy.Maliev.ProcurementService.Domain;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.DependencyInjection;

namespace Legacy.Maliev.ProcurementService.Tests.Integration;

public sealed class ProcurementNullableSortSourceTests(ProcurementRuntimeFixture fixture)
    : IClassFixture<ProcurementRuntimeFixture>, IAsyncLifetime
{
    public Task InitializeAsync() => fixture.ResetAsync();
    public Task DisposeAsync() => Task.CompletedTask;

    [Theory]
    [InlineData(false, "SupplierName_Ascending", "11,33,44,22")]
    [InlineData(false, "2", "11,33,44,22")]
    [InlineData(false, "SupplierName_Descending", "22,33,44,11")]
    [InlineData(false, "3", "22,33,44,11")]
    [InlineData(false, "SupplierCreatedDate_Ascending", "11,33,44,22")]
    [InlineData(false, "4", "11,33,44,22")]
    [InlineData(false, "SupplierCreatedDate_Descending", "22,33,44,11")]
    [InlineData(false, "5", "22,33,44,11")]
    [InlineData(false, "SupplierModifiedDate_Ascending", "11,22,33,44")]
    [InlineData(false, "6", "11,22,33,44")]
    [InlineData(false, "SupplierModifiedDate_Descending", "33,44,22,11")]
    [InlineData(false, "7", "33,44,22,11")]
    [InlineData(true, "PurchaseOrderCreatedDate_Ascending", "101,303,404,202")]
    [InlineData(true, "2", "101,303,404,202")]
    [InlineData(true, "PurchaseOrderCreatedDate_Descending", "202,303,404,101")]
    [InlineData(true, "3", "202,303,404,101")]
    public async Task EightNullableBranches_SourceNullPlacementAndStableTiesThroughNamedAndNumericHttp(bool purchaseOrder, string sort, string ids)
    {
        await SeedAsync();
        var before = await SnapshotAsync();
        using var client = fixture.Client(purchaseOrder ? ProcurementPermissions.PurchaseOrdersRead : ProcurementPermissions.SuppliersRead);
        using var response = await client.GetAsync($"{Route(purchaseOrder)}?sort={sort}&size=10");
        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        using var document = JsonDocument.Parse(await response.Content.ReadAsStringAsync());
        Assert.Equal(ids.Split(',').Select(int.Parse), Ids(document.RootElement));
        Assert.Equal(4, document.RootElement.GetProperty("TotalRecords").GetInt32());
        Assert.Equal(before, await SnapshotAsync());
    }

    [Theory]
    [InlineData(false, "SupplierName_Ascending", 2, 33)]
    [InlineData(false, "SupplierModifiedDate_Descending", 2, 44)]
    [InlineData(true, "PurchaseOrderCreatedDate_Ascending", 3, 404)]
    [InlineData(true, "PurchaseOrderCreatedDate_Descending", 3, 404)]
    public async Task NullableSort_StableIdentifierTiePrecedesPagingAndKeepsMetadata(bool purchaseOrder, string sort, int index, int id)
    {
        await SeedAsync();
        var before = await SnapshotAsync();
        using var client = fixture.Client(purchaseOrder ? ProcurementPermissions.PurchaseOrdersRead : ProcurementPermissions.SuppliersRead);
        using var response = await client.GetAsync($"{Route(purchaseOrder)}?sort={sort}&index={index}&size=1");
        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        using var document = JsonDocument.Parse(await response.Content.ReadAsStringAsync());
        var page = document.RootElement;
        Assert.Equal(new[] { id }, Ids(page));
        Assert.Equal(index, page.GetProperty("PageIndex").GetInt32());
        Assert.Equal(4, page.GetProperty("TotalPages").GetInt32());
        Assert.Equal(4, page.GetProperty("TotalRecords").GetInt32());
        Assert.Equal(before, await SnapshotAsync());
    }

    [Theory]
    [InlineData(false, true)]
    [InlineData(false, false)]
    [InlineData(true, true)]
    [InlineData(true, false)]
    public async Task SortedRead_AnonymousOrWrongPermissionCannotDiscloseOrMutateMasters(bool purchaseOrder, bool anonymous)
    {
        await SeedAsync();
        var before = await SnapshotAsync();
        using var client = anonymous ? fixture.Factory.CreateClient() : fixture.Client();
        using var response = await client.GetAsync(Route(purchaseOrder) + "?sort=2");
        Assert.Equal(anonymous ? HttpStatusCode.Unauthorized : HttpStatusCode.Forbidden, response.StatusCode);
        Assert.DoesNotContain("Zulu", await response.Content.ReadAsStringAsync(), StringComparison.Ordinal);
        Assert.Equal(before, await SnapshotAsync());
    }

    private static string Route(bool purchaseOrder) => purchaseOrder ? "/PurchaseOrders" : "/Suppliers";
    private static int[] Ids(JsonElement page) => page.GetProperty("Items").EnumerateArray()
        .Select(row => row.GetProperty("Id").GetInt32()).ToArray();

    private async Task SeedAsync()
    {
        await using var scope = fixture.Factory.Services.CreateAsyncScope();
        var supplier = scope.ServiceProvider.GetRequiredService<SupplierDbContext>();
        supplier.Suppliers.AddRange(new Supplier { Id = 11, Name = null },
            new Supplier { Id = 22, Name = "Zulu", CreatedDate = Day(3), ModifiedDate = Day(1) },
            new Supplier { Id = 33, Name = "Alpha", CreatedDate = Day(1), ModifiedDate = Day(3) },
            new Supplier { Id = 44, Name = "Alpha", CreatedDate = Day(1), ModifiedDate = Day(3) });
        await supplier.SaveChangesAsync();
        // Insert defaults supply dates; explicitly store NULL after insert to exercise the actual PostgreSQL rows.
        await supplier.Suppliers.Where(row => row.Id == 11).ExecuteUpdateAsync(setters => setters
            .SetProperty(row => row.Name, (string?)null)
            .SetProperty(row => row.CreatedDate, (DateTime?)null)
            .SetProperty(row => row.ModifiedDate, (DateTime?)null));
        var orders = scope.ServiceProvider.GetRequiredService<PurchaseOrderDbContext>();
        orders.PurchaseOrders.AddRange(new PurchaseOrder { Id = 101 },
            new PurchaseOrder { Id = 202, CreatedDate = Day(3) },
            new PurchaseOrder { Id = 303, CreatedDate = Day(1) },
            new PurchaseOrder { Id = 404, CreatedDate = Day(1) });
        await orders.SaveChangesAsync();
        await orders.PurchaseOrders.Where(row => row.Id == 101)
            .ExecuteUpdateAsync(setters => setters.SetProperty(row => row.CreatedDate, (DateTime?)null));
        Assert.True(await supplier.Suppliers.AnyAsync(row => row.Id == 11 && row.Name == null && row.CreatedDate == null && row.ModifiedDate == null));
        Assert.True(await orders.PurchaseOrders.AnyAsync(row => row.Id == 101 && row.CreatedDate == null));
    }

    private static DateTime Day(int day) => new(2026, 10, day);

    private async Task<(string Supplier, string PurchaseOrder)> SnapshotAsync()
    {
        await using var scope = fixture.Factory.Services.CreateAsyncScope();
        var suppliers = scope.ServiceProvider.GetRequiredService<SupplierDbContext>();
        var orders = scope.ServiceProvider.GetRequiredService<PurchaseOrderDbContext>();
        return (JsonSerializer.Serialize(await suppliers.Suppliers.AsNoTracking().OrderBy(row => row.Id).ToArrayAsync()),
            JsonSerializer.Serialize(await orders.PurchaseOrders.AsNoTracking().OrderBy(row => row.Id).ToArrayAsync()));
    }
}

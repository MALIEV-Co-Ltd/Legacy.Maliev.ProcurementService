using System.Net;
using System.Text.Json;
using Legacy.Maliev.ProcurementService.Api.Authorization;
using Legacy.Maliev.ProcurementService.Data;
using Legacy.Maliev.ProcurementService.Domain;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.DependencyInjection;

namespace Legacy.Maliev.ProcurementService.Tests.Integration;

// Additive source attachment. Execute only with the separately reviewed pagination candidate.
public sealed class ProcurementPaginationWireContractTests(ProcurementRuntimeFixture<ProcurementPaginationWireContractTests> fixture)
    : IClassFixture<ProcurementRuntimeFixture<ProcurementPaginationWireContractTests>>, IAsyncLifetime
{
    public Task InitializeAsync() => fixture.ResetAsync();
    public Task DisposeAsync() => Task.CompletedTask;

    public static IEnumerable<object[]> Cases()
    {
        foreach (var supplier in new[] { true, false })
            foreach (var descending in new[] { false, true })
                foreach (var page in new[] { 0, 1, 2, 3, 4 })
                    yield return [supplier, descending, page];
    }

    [Theory]
    [MemberData(nameof(Cases))]
    public async Task ListPage_PreservesRawEnvelopeFlagsNullOmissionAndEmptyStatus(bool supplier, bool descending, int page)
    {
        (int Id, string? Text)[] rows = Enumerable.Range(1001, 503).Select(id => (Id: id, Text: "match " + id))
            .Concat(Enumerable.Range(2001, 7).Select(id => (Id: id, Text: "other " + id))).ToArray();
        await using (var scope = fixture.Factory.Services.CreateAsyncScope())
        {
            if (supplier)
            {
                var db = scope.ServiceProvider.GetRequiredService<SupplierDbContext>();
                db.Suppliers.AddRange(rows.Select(row => new Supplier { Id = row.Id, Name = row.Text }));
                await db.SaveChangesAsync();
            }
            else
            {
                var db = scope.ServiceProvider.GetRequiredService<PurchaseOrderDbContext>();
                db.PurchaseOrders.AddRange(rows.Select(row => new PurchaseOrder { Id = row.Id, Notes = row.Text }));
                await db.SaveChangesAsync();
            }
        }
        var omitted = page == 0;
        var effectivePage = omitted ? 1 : page;
        var take = omitted ? 503 : 251;
        var expectedPages = omitted ? 1 : 3;
        var orderedIds = descending ? Enumerable.Range(1001, 503).Reverse() : Enumerable.Range(1001, 503);
        var expectedIds = orderedIds.Skip((effectivePage - 1) * take).Take(take).ToArray();
        var route = supplier ? "/Suppliers" : "/PurchaseOrders";
        var sort = supplier ? descending ? "SupplierId_Descending" : "SupplierId_Ascending"
            : descending ? "PurchaseOrderId_Descending" : "PurchaseOrderId_Ascending";
        var query = "?search=match&sort=" + sort + (omitted ? string.Empty : $"&index={page}&size=251");
        using var client = fixture.Client(supplier ? ProcurementPermissions.SuppliersRead : ProcurementPermissions.PurchaseOrdersRead);
        using var response = await client.GetAsync(route + query);
        Assert.Equal(expectedIds.Length == 0 ? HttpStatusCode.NotFound : HttpStatusCode.OK, response.StatusCode);
        if (expectedIds.Length != 0)
        {
            Assert.Equal("application/json", response.Content.Headers.ContentType?.MediaType);
            await using var stream = await response.Content.ReadAsStreamAsync();
            using var document = await JsonDocument.ParseAsync(stream);
            var wire = document.RootElement;
            Assert.Equal(JsonValueKind.Object, wire.ValueKind);
            Assert.Equal(new[] { "HasNextPage", "HasPreviousPage", "Items", "PageIndex", "TotalPages", "TotalRecords" },
                wire.EnumerateObject().Select(property => property.Name).OrderBy(name => name, StringComparer.Ordinal));
            Assert.Equal(effectivePage, wire.GetProperty("PageIndex").GetInt32());
            Assert.Equal(expectedPages, wire.GetProperty("TotalPages").GetInt32());
            Assert.Equal(503, wire.GetProperty("TotalRecords").GetInt32());
            Assert.Equal(effectivePage < expectedPages, wire.GetProperty("HasNextPage").GetBoolean());
            Assert.Equal(effectivePage > 1, wire.GetProperty("HasPreviousPage").GetBoolean());
            var items = wire.GetProperty("Items");
            Assert.Equal(JsonValueKind.Array, items.ValueKind);
            Assert.Equal(expectedIds, items.EnumerateArray().Select(item => item.GetProperty("Id").GetInt32()));
            foreach (var item in items.EnumerateArray())
            {
                Assert.False(item.TryGetProperty("id", out _));
                Assert.False(item.TryGetProperty(supplier ? "Website" : "SupplierId", out _));
                Assert.Equal("match " + item.GetProperty("Id").GetInt32(), item.GetProperty(supplier ? "Name" : "Notes").GetString());
            }
        }
        await using var readScope = fixture.Factory.Services.CreateAsyncScope();
        if (supplier)
        {
            var persisted = await readScope.ServiceProvider.GetRequiredService<SupplierDbContext>().Suppliers.AsNoTracking()
                .OrderBy(row => row.Id).Select(row => new { row.Id, Text = row.Name }).ToArrayAsync();
            Assert.Equal(rows, persisted.Select(row => (row.Id, row.Text)));
        }
        else
        {
            var persisted = await readScope.ServiceProvider.GetRequiredService<PurchaseOrderDbContext>().PurchaseOrders.AsNoTracking()
                .OrderBy(row => row.Id).Select(row => new { row.Id, Text = row.Notes }).ToArrayAsync();
            Assert.Equal(rows, persisted.Select(row => (row.Id, row.Text)));
        }
    }
}

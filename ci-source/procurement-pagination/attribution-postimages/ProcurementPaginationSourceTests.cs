using System.Globalization;
using System.Net;
using System.Net.Http.Json;
using Legacy.Maliev.ProcurementService.Api.Authorization;
using Legacy.Maliev.ProcurementService.Application.Models;
using Legacy.Maliev.ProcurementService.Data;
using Legacy.Maliev.ProcurementService.Domain;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.DependencyInjection;

namespace Legacy.Maliev.ProcurementService.Tests.Integration;

public sealed class ProcurementPaginationSourceTests(ProcurementRuntimeFixture<ProcurementPaginationSourceTests> fixture)
    : IClassFixture<ProcurementRuntimeFixture<ProcurementPaginationSourceTests>>, IAsyncLifetime
{
    public Task InitializeAsync() => fixture.ResetAsync();
    public Task DisposeAsync() => Task.CompletedTask;

    public static IEnumerable<object?[]> Cases()
    {
        (int? Size, int? Index, string? Search)[] cases =
        [
            (null, null, "match"), (null, 0, "match"), (null, -4, "match"),
            (null, 2, "match"), (null, int.MaxValue, "match"),
            (12, 21, "match"), (12, 22, "match"),
            (50, null, "match"), (250, null, "match"), (251, null, "match"), (999, null, "match"),
            (251, 2, "match"), (251, 3, "match"), (999, 2, "match"),
            (null, null, null), (null, null, "1001"), (null, null, "absent")
        ];
        foreach (var supplier in new[] { true, false })
            foreach (var value in cases)
                foreach (var descending in new[] { false, true })
                    yield return [supplier, value.Size, value.Index, value.Search, descending];
    }

    [Theory]
    [MemberData(nameof(Cases))]
    public async Task LegacyListUsesFilteredCountAndPreservesExplicitPositiveSize(
        bool supplier, int? size, int? index, string? search, bool descending)
    {
        var rows = Enumerable.Range(0, 503).Select(i => (Id: 1001 + i, Text: "match ผู้ขาย " + i))
            .Concat(Enumerable.Range(0, 7).Select(i => (Id: 11001 + i, Text: "other " + i))).ToArray();
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

        var filtered = rows.Where(row => string.IsNullOrEmpty(search)
            || (supplier && int.TryParse(search, out var numeric) ? row.Id == numeric
                : row.Text.Contains(search!, StringComparison.OrdinalIgnoreCase)
                    || (!supplier && row.Id.ToString(CultureInfo.InvariantCulture).Contains(search!, StringComparison.Ordinal)))).ToArray();
        var page = Math.Max(index ?? 1, 1);
        // The expected omission follows original CountAsync after filtering, and positive explicit size uses the original uncapped Take(size).
        var take = size is null ? filtered.Length : Math.Max(size.Value, 1);
        var offset = ((long)page - 1) * take;
        var ordered = descending ? filtered.Reverse() : filtered.AsEnumerable();
        var expectedIds = ordered.Where((_, position) => position >= offset && position < offset + take)
            .Select(row => row.Id).ToArray();
        var parameters = new List<string>();
        if (descending) parameters.Add("sort=" + (supplier ? "SupplierId_Descending" : "PurchaseOrderId_Descending"));
        if (size is not null) parameters.Add("size=" + size.Value.ToString(CultureInfo.InvariantCulture));
        if (index is not null) parameters.Add("index=" + index.Value.ToString(CultureInfo.InvariantCulture));
        if (search is not null) parameters.Add("search=" + Uri.EscapeDataString(search));
        var route = supplier ? "/Suppliers" : "/PurchaseOrders";
        using var client = fixture.Client(supplier ? ProcurementPermissions.SuppliersRead : ProcurementPermissions.PurchaseOrdersRead);
        using var response = await client.GetAsync(route + "?" + string.Join("&", parameters));
        Assert.Equal(expectedIds.Length == 0 ? HttpStatusCode.NotFound : HttpStatusCode.OK, response.StatusCode);
        if (expectedIds.Length != 0)
        {
            if (supplier)
            {
                var wire = (await response.Content.ReadFromJsonAsync<PaginatedResponse<SupplierResponse>>())!;
                Assert.Equal(expectedIds, wire.Items.Select(row => row.Id));
                Assert.Equal(filtered.Length, wire.TotalRecords);
                Assert.Equal(page, wire.PageIndex);
                Assert.Equal((int)Math.Ceiling(filtered.Length / (double)take), wire.TotalPages);
            }
            else
            {
                var wire = (await response.Content.ReadFromJsonAsync<PaginatedResponse<PurchaseOrderResponse>>())!;
                Assert.Equal(expectedIds, wire.Items.Select(row => row.Id));
                Assert.Equal(filtered.Length, wire.TotalRecords);
                Assert.Equal(page, wire.PageIndex);
                Assert.Equal((int)Math.Ceiling(filtered.Length / (double)take), wire.TotalPages);
            }
        }
        await using var readScope = fixture.Factory.Services.CreateAsyncScope();
        if (supplier)
            Assert.Equal(rows.Select(row => row.Id), await readScope.ServiceProvider.GetRequiredService<SupplierDbContext>()
                .Suppliers.AsNoTracking().OrderBy(row => row.Id).Select(row => row.Id).ToArrayAsync());
        else
            Assert.Equal(rows.Select(row => row.Id), await readScope.ServiceProvider.GetRequiredService<PurchaseOrderDbContext>()
                .PurchaseOrders.AsNoTracking().OrderBy(row => row.Id).Select(row => row.Id).ToArrayAsync());
    }
}

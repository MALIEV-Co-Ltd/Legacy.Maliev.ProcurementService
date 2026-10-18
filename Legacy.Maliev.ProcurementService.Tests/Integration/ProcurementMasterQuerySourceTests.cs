using System.Net;
using System.Net.Http.Json;
using System.Text.Json;
using Legacy.Maliev.ProcurementService.Api.Authorization;
using Legacy.Maliev.ProcurementService.Application.Models;
using Legacy.Maliev.ProcurementService.Data;
using Legacy.Maliev.ProcurementService.Domain;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Infrastructure;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Mvc.Testing;
using Microsoft.Extensions.DependencyInjection.Extensions;
using Microsoft.Extensions.DependencyInjection;

namespace Legacy.Maliev.ProcurementService.Tests.Integration;

public sealed class ProcurementMasterQuerySourceTests(ProcurementRuntimeFixture fixture)
    : IClassFixture<ProcurementRuntimeFixture>, IAsyncLifetime
{
    private WebApplicationFactory<Program> historicalFactory = null!;

    public async Task InitializeAsync()
    {
        await fixture.ResetAsync();
        await using var scope = fixture.Factory.Services.CreateAsyncScope();
        var current = scope.ServiceProvider.GetRequiredService<SupplierDbContext>();
        string connection = current.Database.GetConnectionString()!;
        // This class alone models a historical nullable-Name schema in its disposable owned database.
        // Current source requiredness remains independently asserted by the normal model/schema cases.
        await current.Database.ExecuteSqlRawAsync("ALTER TABLE \"Supplier\" ALTER COLUMN \"Name\" DROP NOT NULL");
        historicalFactory = fixture.Factory.WithWebHostBuilder(builder => builder.ConfigureServices(services =>
        {
            services.RemoveAll<SupplierDbContext>();
            services.RemoveAll<DbContextOptions<SupplierDbContext>>();
            services.AddDbContext<SupplierDbContext>(options => options.UseNpgsql(connection)
                .ReplaceService<IModelCustomizer, HistoricalNullableSupplierModelCustomizer>());
        }));
    }

    public async Task DisposeAsync()
    {
        if (historicalFactory is not null)
            await historicalFactory.DisposeAsync();
    }


    [Fact]
    public async Task SupplierNumericSearch_SourceMatchesOnlyIdentifier_NotTextContainingSameDigits()
    {
        await using (var scope = historicalFactory.Services.CreateAsyncScope())
        {
            var database = scope.ServiceProvider.GetRequiredService<SupplierDbContext>();
            database.Suppliers.AddRange(new Supplier { Id = 1234, Name = "Exact identity" },
                new Supplier { Id = 4567, Name = "Text mentions1234", Website = "https://supplier1234.invalid" });
            await database.SaveChangesAsync();
        }
        using var client = fixture.ClientAs(historicalFactory, "employee:procurement-parity", ProcurementPermissions.SuppliersRead);
        using var response = await client.GetAsync("/Suppliers?search=1234&index=1&size=10");
        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        var page = (await response.Content.ReadFromJsonAsync<PaginatedResponse<SupplierResponse>>())!;
        Assert.Equal(1234, Assert.Single(page.Items).Id);
        Assert.Equal(1, page.TotalRecords);
        await using var readScope = historicalFactory.Services.CreateAsyncScope();
        Assert.Equal(2, await readScope.ServiceProvider.GetRequiredService<SupplierDbContext>().Suppliers.CountAsync());
    }

    [Fact]
    public async Task PurchaseOrderNumericSearch_SourceMatchesIdentifierSubstring()
    {
        await using (var scope = historicalFactory.Services.CreateAsyncScope())
        {
            var database = scope.ServiceProvider.GetRequiredService<PurchaseOrderDbContext>();
            database.PurchaseOrders.AddRange(new PurchaseOrder { Id = 203 }, new PurchaseOrder { Id = 1203 },
                new PurchaseOrder { Id = 999, Notes = "Contains203 in notes" }, new PurchaseOrder { Id = 2000 });
            await database.SaveChangesAsync();
        }
        using var client = fixture.ClientAs(historicalFactory, "employee:procurement-parity", ProcurementPermissions.PurchaseOrdersRead);
        using var response = await client.GetAsync("/PurchaseOrders?search=203&index=1&size=10");
        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        var page = (await response.Content.ReadFromJsonAsync<PaginatedResponse<PurchaseOrderResponse>>())!;
        Assert.Equal(new[] { 203, 999, 1203 }, page.Items.Select(item => item.Id));
        Assert.Equal(3, page.TotalRecords);
        await using var readScope = historicalFactory.Services.CreateAsyncScope();
        Assert.Equal(4, await readScope.ServiceProvider.GetRequiredService<PurchaseOrderDbContext>().PurchaseOrders.CountAsync());
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task PageBeyondLast_SourceReturnsNotFound(bool purchaseOrder)
    {
        await SeedAsync(purchaseOrder, 1, 1000);
        using var client = fixture.ClientAs(historicalFactory, "employee:procurement-parity", purchaseOrder ? ProcurementPermissions.PurchaseOrdersRead : ProcurementPermissions.SuppliersRead);
        using var response = await client.GetAsync($"/{(purchaseOrder ? "PurchaseOrders" : "Suppliers")}?index=2&size=1");
        Assert.Equal(HttpStatusCode.NotFound, response.StatusCode);
        await using var scope = historicalFactory.Services.CreateAsyncScope();
        if (purchaseOrder) Assert.Equal(1, await scope.ServiceProvider.GetRequiredService<PurchaseOrderDbContext>().PurchaseOrders.CountAsync());
        else Assert.Equal(1, await scope.ServiceProvider.GetRequiredService<SupplierDbContext>().Suppliers.CountAsync());
    }

    [Theory]
    [InlineData("001234", 1234)]
    [InlineData(" 1234 ", 1234)]
    [InlineData("2147483648", 4567)]
    [InlineData("part1234", 4567)]
    [InlineData("PART1234", null)]
    [InlineData("%", 6789)]
    [InlineData("ชิ้นงาน", 4567)]
    [InlineData(" part1234 ", null)]
    [InlineData(" ", 0)]
    public async Task SupplierSearch_SourceIntegerParsingAndLiteralTextRemainDistinct(string search, int? expectedId)
    {
        await using (var scope = historicalFactory.Services.CreateAsyncScope())
        {
            var database = scope.ServiceProvider.GetRequiredService<SupplierDbContext>();
            database.Suppliers.AddRange(new Supplier { Id = 1234, Name = "Exact identity" },
                new Supplier { Id = 4567, Name = "part1234ชิ้นงาน", Website = "https://001234.invalid", TaxNumber = "2147483648" },
                new Supplier { Id = 6789, Name = "Percent%Underscore_" }, new Supplier { Id = 8900, Name = null });
            await database.SaveChangesAsync();
        }
        using var client = fixture.ClientAs(historicalFactory, "employee:procurement-parity", ProcurementPermissions.SuppliersRead);
        using var response = await client.GetAsync($"/Suppliers?search={Uri.EscapeDataString(search)}&size=10");
        if (expectedId == 0)
        {
            // MVC binds a whitespace-only query string as null before repository filtering.
            Assert.Equal(HttpStatusCode.OK, response.StatusCode);
            var page = (await response.Content.ReadFromJsonAsync<PaginatedResponse<SupplierResponse>>())!;
            Assert.Equal(new[] { 1234, 4567, 6789, 8900 }, page.Items.Select(item => item.Id));
            Assert.Equal(4, page.TotalRecords);
        }
        else if (expectedId is null) Assert.Equal(HttpStatusCode.NotFound, response.StatusCode);
        else
        {
            Assert.Equal(HttpStatusCode.OK, response.StatusCode);
            var page = (await response.Content.ReadFromJsonAsync<PaginatedResponse<SupplierResponse>>())!;
            Assert.Equal(expectedId.Value, Assert.Single(page.Items).Id);
            Assert.Equal(1, page.TotalRecords);
        }
        await using var readScope = historicalFactory.Services.CreateAsyncScope();
        Assert.Equal(4, await readScope.ServiceProvider.GetRequiredService<SupplierDbContext>().Suppliers.CountAsync());
    }

    [Theory]
    [InlineData("PROBE", 999)]
    [InlineData("001203", 999)]
    [InlineData("%", 6789)]
    [InlineData("_", 6789)]
    [InlineData(" probe ", null)]
    [InlineData("ใบสั่งซื้อ", 999)]
    public async Task PurchaseOrderSearch_SourceLowercaseLiteralAndNullNotesRemainDistinct(string search, int? expectedId)
    {
        await using (var scope = historicalFactory.Services.CreateAsyncScope())
        {
            var database = scope.ServiceProvider.GetRequiredService<PurchaseOrderDbContext>();
            database.PurchaseOrders.AddRange(new PurchaseOrder { Id = 1203, Notes = null },
                new PurchaseOrder { Id = 999, Notes = "Probe001203ใบสั่งซื้อ" },
                new PurchaseOrder { Id = 6789, Notes = "Percent%Underscore_" });
            await database.SaveChangesAsync();
        }
        using var client = fixture.ClientAs(historicalFactory, "employee:procurement-parity", ProcurementPermissions.PurchaseOrdersRead);
        using var response = await client.GetAsync($"/PurchaseOrders?search={Uri.EscapeDataString(search)}&size=10");
        if (expectedId is null) Assert.Equal(HttpStatusCode.NotFound, response.StatusCode);
        else
        {
            Assert.Equal(HttpStatusCode.OK, response.StatusCode);
            var page = (await response.Content.ReadFromJsonAsync<PaginatedResponse<PurchaseOrderResponse>>())!;
            Assert.Equal(expectedId.Value, Assert.Single(page.Items).Id);
            Assert.Equal(1, page.TotalRecords);
        }
        await using var readScope = historicalFactory.Services.CreateAsyncScope();
        Assert.Equal(3, await readScope.ServiceProvider.GetRequiredService<PurchaseOrderDbContext>().PurchaseOrders.CountAsync());
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task SupplierOmittedSize_ReturnsAllMatchesAndWholePascalPager(bool filtered)
    {
        await SeedSupplierOmittedSizeRowsAsync(51, filtered);
        var before = await SupplierOmittedSizeSnapshotAsync();
        using var client = fixture.Client(ProcurementPermissions.SuppliersRead);
        using var response = await client.GetAsync(filtered
            ? "/Suppliers?search=match"
            : "/Suppliers");
        await AssertSupplierOmittedSizePageAsync(response, Enumerable.Range(1, 51), 1, 51, 1, false, false);
        using var nullSize = await client.GetAsync(filtered
            ? "/Suppliers?search=match&size="
            : "/Suppliers?size=");
        await AssertSupplierOmittedSizePageAsync(nullSize, Enumerable.Range(1, 51), 1, 51, 1, false, false);
        Assert.Equal(before, await SupplierOmittedSizeSnapshotAsync());
    }

    [Fact]
    public async Task SupplierExplicitSize10_RetainsRequestedSecondPage()
    {
        await SeedSupplierOmittedSizeRowsAsync(51, false);
        var before = await SupplierOmittedSizeSnapshotAsync();
        using var client = fixture.Client(ProcurementPermissions.SuppliersRead);
        using var response = await client.GetAsync("/Suppliers?size=10&index=2");
        await AssertSupplierOmittedSizePageAsync(response, Enumerable.Range(11, 10), 2, 51, 6, true, true);
        Assert.Equal(before, await SupplierOmittedSizeSnapshotAsync());
    }

    [Fact]
    public async Task SupplierExplicitUpperBoundAndIndexFloor_RemainUnchanged()
    {
        await SeedSupplierOmittedSizeRowsAsync(251, false);
        var before = await SupplierOmittedSizeSnapshotAsync();
        using var client = fixture.Client(ProcurementPermissions.SuppliersRead);
        using var response = await client.GetAsync("/Suppliers?size=251&index=0");
        await AssertSupplierOmittedSizePageAsync(response, Enumerable.Range(1, 250), 1, 251, 2, true, false);
        Assert.Equal(before, await SupplierOmittedSizeSnapshotAsync());
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task SupplierOmittedSize_RetainsReadAuthorization(bool anonymous)
    {
        await SeedSupplierOmittedSizeRowsAsync(51, false);
        var before = await SupplierOmittedSizeSnapshotAsync();
        using var client = anonymous
            ? fixture.Factory.CreateClient()
            : fixture.Client(ProcurementPermissions.SuppliersUpdate);
        using var response = await client.GetAsync("/Suppliers");
        Assert.Equal(anonymous ? HttpStatusCode.Unauthorized : HttpStatusCode.Forbidden, response.StatusCode);
        Assert.Equal(before, await SupplierOmittedSizeSnapshotAsync());
    }

    [Fact]
    public async Task SupplierOmittedSize_NoMatchesStillReturnNotFound()
    {
        await SeedSupplierOmittedSizeRowsAsync(51, false);
        var before = await SupplierOmittedSizeSnapshotAsync();
        using var client = fixture.Client(ProcurementPermissions.SuppliersRead);
        using var response = await client.GetAsync("/Suppliers?search=absent");
        Assert.Equal(HttpStatusCode.NotFound, response.StatusCode);
        Assert.Equal(before, await SupplierOmittedSizeSnapshotAsync());
    }

    // Follow-up source policy: explicit positive sizes have no 250-row cap; zero has no items.
    // The accepted omitted-size cases above remain unchanged in this tests-first baseline.
    [Theory]
    [InlineData(251, false)]
    [InlineData(251, true)]
    [InlineData(1000, false)]
    [InlineData(1000, true)]
    [InlineData(int.MaxValue, false)]
    [InlineData(int.MaxValue, true)]
    public async Task SupplierExplicitSourceParity_PositiveSizeReturnsRequestedPages(int size, bool filtered)
    {
        await SeedSupplierOmittedSizeRowsAsync(1000, filtered);
        var before = await SupplierOmittedSizeSnapshotAsync();
        using var client = fixture.Client(ProcurementPermissions.SuppliersRead);
        using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(90));
        try
        {
            int pages = size == 251 ? 4 : 1;
            var actualIds = new List<int>();
            for (int index = 1; index <= pages; index++)
            {
                string query = $"/Suppliers?size={size}&index={index}" + (filtered ? "&search=match" : "");
                using var response = await client.GetAsync(query, timeout.Token);
                int first = (index - 1) * size + 1;
                int count = Math.Min(size, 1001 - first);
                await AssertSupplierOmittedSizePageAsync(response, Enumerable.Range(first, count),
                    index, 1000, pages, index < pages, index > 1);
                var page = (await response.Content.ReadFromJsonAsync<PaginatedResponse<SupplierResponse>>(timeout.Token))!;
                actualIds.AddRange(page.Items.Select(item => item.Id));
            }
            Assert.Equal(Enumerable.Range(1, 1000), actualIds);
            Assert.Equal(1000, actualIds.Distinct().Count());
            using var exhausted = await client.GetAsync(
                $"/Suppliers?size={size}&index={pages + 1}" + (filtered ? "&search=match" : ""), timeout.Token);
            Assert.Equal(HttpStatusCode.NotFound, exhausted.StatusCode);
        }
        finally
        {
            Assert.Equal(before, await SupplierOmittedSizeSnapshotAsync());
        }
    }

    [Theory]
    [InlineData("populated", 0)]
    [InlineData("populated", 1)]
    [InlineData("populated", int.MaxValue)]
    [InlineData("filtered", 0)]
    [InlineData("filtered", 1)]
    [InlineData("absent", 0)]
    [InlineData("absent", 1)]
    [InlineData("empty", 0)]
    [InlineData("empty", 1)]
    public async Task SupplierExplicitSourceParity_ZeroSizeReturnsNotFound(string cohort, int index)
    {
        await SeedSupplierOmittedSizeRowsAsync(cohort == "empty" ? 0 : 3, cohort == "filtered");
        var before = await SupplierOmittedSizeSnapshotAsync();
        using var client = fixture.Client(ProcurementPermissions.SuppliersRead);
        using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(90));
        try
        {
            string filter = cohort == "filtered" ? "&search=match"
                : cohort == "absent" ? "&search=absent-witness" : "";
            using var response = await client.GetAsync($"/Suppliers?size=0&index={index}{filter}", timeout.Token);
            Assert.Equal(HttpStatusCode.NotFound, response.StatusCode);
        }
        finally
        {
            Assert.Equal(before, await SupplierOmittedSizeSnapshotAsync());
        }
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task SupplierExplicitSourceParity_RetainsReadAuthorization(bool anonymous)
    {
        await SeedSupplierOmittedSizeRowsAsync(3, false);
        var before = await SupplierOmittedSizeSnapshotAsync();
        using var client = anonymous
            ? fixture.Factory.CreateClient()
            : fixture.Client(ProcurementPermissions.SuppliersUpdate);
        using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(90));
        try
        {
            foreach (int size in new[] { 0, 251, 1000, int.MaxValue })
            {
                foreach (string filter in new[] { "", "&search=match" })
                {
                    using var response = await client.GetAsync($"/Suppliers?size={size}{filter}", timeout.Token);
                    Assert.Equal(anonymous ? HttpStatusCode.Unauthorized : HttpStatusCode.Forbidden, response.StatusCode);
                }
            }
        }
        finally
        {
            Assert.Equal(before, await SupplierOmittedSizeSnapshotAsync());
        }
    }

    [Theory]
    [InlineData(-1)]
    [InlineData(int.MinValue)]
    public async Task SupplierExplicitSourceParity_RetainsNegativeSizeAndIndexFloors(int size)
    {
        await SeedSupplierOmittedSizeRowsAsync(3, false);
        var before = await SupplierOmittedSizeSnapshotAsync();
        using var client = fixture.Client(ProcurementPermissions.SuppliersRead);
        using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(90));
        try
        {
            foreach (int index in new[] { 0, -1, 1 })
            {
                using var response = await client.GetAsync($"/Suppliers?size={size}&index={index}", timeout.Token);
                await AssertSupplierOmittedSizePageAsync(response, new[] { 1 }, 1, 3, 3, true, false);
            }
            using var missing = await client.GetAsync($"/Suppliers?size={size}&search=absent-witness", timeout.Token);
            Assert.Equal(HttpStatusCode.NotFound, missing.StatusCode);
        }
        finally
        {
            Assert.Equal(before, await SupplierOmittedSizeSnapshotAsync());
        }
    }

    private async Task SeedSupplierOmittedSizeRowsAsync(int count, bool includeNonmatching)
    {
        await using var scope = fixture.Factory.Services.CreateAsyncScope();
        var database = scope.ServiceProvider.GetRequiredService<SupplierDbContext>();
        database.Suppliers.AddRange(Enumerable.Range(1, count)
            .Select(id => new Supplier { Id = id, Name = $"match supplier{id}" }));
        if (includeNonmatching)
        {
            database.Suppliers.AddRange(new Supplier { Id = 1001, Name = "excluded supplier" },
                new Supplier { Id = 1002, Name = "another excluded supplier" });
        }
        await database.SaveChangesAsync();
    }

    private async Task<string> SupplierOmittedSizeSnapshotAsync()
    {
        await using var scope = fixture.Factory.Services.CreateAsyncScope();
        var database = scope.ServiceProvider.GetRequiredService<SupplierDbContext>();
        var rows = await database.Suppliers.AsNoTracking().OrderBy(row => row.Id)
            .Select(row => new
            {
                row.Id,
                row.Name,
                row.Website,
                row.TaxNumber,
                row.Email,
                row.Note,
                row.AddressId,
                row.Telephone,
                row.Mobile,
                row.Fax,
                row.CreatedDate,
                row.ModifiedDate,
            }).ToArrayAsync();
        return JsonSerializer.Serialize(rows);
    }

    private static async Task AssertSupplierOmittedSizePageAsync(HttpResponseMessage response,
        IEnumerable<int> expectedIds, int expectedIndex, int expectedRecords, int expectedPages,
        bool expectedNext, bool expectedPrevious)
    {
        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        using var document = JsonDocument.Parse(await response.Content.ReadAsStringAsync());
        var page = document.RootElement;
        Assert.Equal(new[] { "HasNextPage", "HasPreviousPage", "Items", "PageIndex", "TotalPages", "TotalRecords" },
            page.EnumerateObject().Select(property => property.Name).OrderBy(name => name, StringComparer.Ordinal));
        Assert.Equal(expectedIds, page.GetProperty("Items").EnumerateArray().Select(item => item.GetProperty("Id").GetInt32()));
        Assert.Equal(expectedIndex, page.GetProperty("PageIndex").GetInt32());
        Assert.Equal(expectedRecords, page.GetProperty("TotalRecords").GetInt32());
        Assert.Equal(expectedPages, page.GetProperty("TotalPages").GetInt32());
        Assert.Equal(expectedNext, page.GetProperty("HasNextPage").GetBoolean());
        Assert.Equal(expectedPrevious, page.GetProperty("HasPreviousPage").GetBoolean());
    }

    private async Task SeedAsync(bool purchaseOrder, int count, int firstId)
    {
        await using var scope = historicalFactory.Services.CreateAsyncScope();
        if (purchaseOrder)
        {
            var database = scope.ServiceProvider.GetRequiredService<PurchaseOrderDbContext>();
            database.PurchaseOrders.AddRange(Enumerable.Range(firstId, count).Select(id => new PurchaseOrder { Id = id }));
            await database.SaveChangesAsync();
        }
        else
        {
            var database = scope.ServiceProvider.GetRequiredService<SupplierDbContext>();
            database.Suppliers.AddRange(Enumerable.Range(firstId, count).Select(id => new Supplier { Id = id, Name = $"Supplier{id}" }));
            await database.SaveChangesAsync();
        }
    }
}

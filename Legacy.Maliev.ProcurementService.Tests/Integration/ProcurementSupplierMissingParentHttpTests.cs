using System.Net;
using System.Net.Http.Headers;
using System.Net.Http.Json;
using System.Text.Json;
using Legacy.Maliev.ProcurementService.Api.Authorization;
using Legacy.Maliev.ProcurementService.Application.Models;
using Legacy.Maliev.ProcurementService.Data;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.DependencyInjection;

namespace Legacy.Maliev.ProcurementService.Tests.Integration;

public sealed class ProcurementSupplierMissingParentHttpTests(ProcurementRuntimeFixture fixture)
    : IClassFixture<ProcurementRuntimeFixture>, IAsyncLifetime
{
    public Task InitializeAsync() => fixture.ResetAsync();
    public Task DisposeAsync() => Task.CompletedTask;

    [Theory]
    [InlineData("text/plain")]
    [InlineData("application/json")]
    public async Task CreateAddress_MissingSupplier_PreservesLiteralResponseWithoutInsertingAddress(string accept)
    {
        using var client = fixture.Client(ProcurementPermissions.SupplierAddressesWrite);
        client.DefaultRequestHeaders.Accept.Add(new MediaTypeWithQualityHeaderValue(accept));
        using var cancellation = new CancellationTokenSource(TimeSpan.FromSeconds(30));
        using var response = await client.PostAsJsonAsync("/suppliers/999999/addresses",
            new UpsertSupplierAddressRequest(null, "Source boundary", null, null, null, null, 66), cancellation.Token);

        Assert.Equal(HttpStatusCode.NotFound, response.StatusCode);
        Assert.Equal(accept, response.Content.Headers.ContentType?.MediaType);
        var body = await response.Content.ReadAsStringAsync(cancellation.Token);
        Assert.Equal("Supplier does not exist", accept == "application/json" ? JsonSerializer.Deserialize<string>(body) : body);
        Assert.Null(response.Headers.Location);
        await using var scope = fixture.Factory.Services.CreateAsyncScope();
        var database = scope.ServiceProvider.GetRequiredService<SupplierDbContext>();
        Assert.Empty(await database.Suppliers.AsNoTracking().ToArrayAsync(cancellation.Token));
        Assert.Empty(await database.Addresses.AsNoTracking().ToArrayAsync(cancellation.Token));
    }
}

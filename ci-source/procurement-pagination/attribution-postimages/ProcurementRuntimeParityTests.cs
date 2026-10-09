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

public sealed class ProcurementRuntimeParityTests(ProcurementRuntimeFixture fixture)
    : IClassFixture<ProcurementRuntimeFixture>, IAsyncLifetime
{
    public Task InitializeAsync() => fixture.ResetAsync();
    public Task DisposeAsync() => Task.CompletedTask;

    [Fact]
    public async Task SupplierAddress_ActualConfiguredRetryPipeline_AttachesAtomically()
    {
        using var client = fixture.Client(ProcurementPermissions.SuppliersCreate, ProcurementPermissions.SupplierAddressesWrite);
        var supplier = await CreateSupplierAsync(client, "Supplier transaction control");
        using var attached = await client.PostAsJsonAsync($"/suppliers/{supplier.Id}/addresses",
            new UpsertSupplierAddressRequest(null, "Bangkok", null, null, null, null, 1));
        Assert.Equal(HttpStatusCode.Created, attached.StatusCode);
        var address = await attached.Content.ReadFromJsonAsync<SupplierAddressResponse>();
        Assert.NotNull(address);
        await using var scope = fixture.Factory.Services.CreateAsyncScope();
        var database = scope.ServiceProvider.GetRequiredService<SupplierDbContext>();
        Assert.Equal(address.Id, (await database.Suppliers.AsNoTracking().SingleAsync()).AddressId);
        Assert.Equal(address.Id, (await database.Addresses.AsNoTracking().SingleAsync()).Id);
        Assert.Empty(await scope.ServiceProvider.GetRequiredService<PurchaseOrderDbContext>().Addresses.ToArrayAsync());
    }

    [Fact]
    public async Task SupplierUpdate_CommittedWriteWithRemovalFailure_SubsequentReadSeesCurrentDatabase()
    {
        using var client = fixture.Client(ProcurementPermissions.SuppliersCreate, ProcurementPermissions.SuppliersRead, ProcurementPermissions.SuppliersUpdate);
        var supplier = await CreateSupplierAsync(client, "Original");
        Assert.Equal("Original", (await client.GetFromJsonAsync<SupplierResponse>($"/Suppliers/{supplier.Id}"))!.Name);
        fixture.Cache.FailRemoval = true;
        using var updated = await client.PutAsJsonAsync($"/Suppliers/{supplier.Id}", Request("Committed update"));
        Assert.Equal(HttpStatusCode.NoContent, updated.StatusCode);
        await using var scope = fixture.Factory.Services.CreateAsyncScope();
        Assert.Equal("Committed update", (await scope.ServiceProvider.GetRequiredService<SupplierDbContext>().Suppliers.AsNoTracking().SingleAsync()).Name);
        fixture.Cache.FailRemoval = false;
        Assert.Equal("Committed update", (await client.GetFromJsonAsync<SupplierResponse>($"/Suppliers/{supplier.Id}"))!.Name);
    }

    [Fact]
    public async Task SupplierCreate_HealthySequentialIdempotency_ReplaysOneCommittedRow()
    {
        using var client = fixture.Client(ProcurementPermissions.SuppliersCreate);
        client.DefaultRequestHeaders.Add("Idempotency-Key", "owned-healthy-response-store");
        var first = await CreateSupplierAsync(client, "Healthy supplier");
        var replay = await CreateSupplierAsync(client, "Healthy supplier");
        Assert.Equal(first.Id, replay.Id);
        await using var scope = fixture.Factory.Services.CreateAsyncScope();
        Assert.Single(await scope.ServiceProvider.GetRequiredService<SupplierDbContext>().Suppliers.ToArrayAsync());
    }

    [Fact]
    public async Task SupplierCreate_AnonymousOrWrongSignedGrant_DoesNotMutateEitherDatabase()
    {
        using var anonymous = fixture.Factory.CreateClient();
        using var wrong = fixture.Client(ProcurementPermissions.SuppliersRead);
        using var deniedIdentity = await anonymous.PostAsJsonAsync("/Suppliers", Request("Denied"));
        using var deniedPermission = await wrong.PostAsJsonAsync("/Suppliers", Request("Denied"));
        Assert.Equal(HttpStatusCode.Unauthorized, deniedIdentity.StatusCode);
        Assert.Equal(HttpStatusCode.Forbidden, deniedPermission.StatusCode);
        await using var scope = fixture.Factory.Services.CreateAsyncScope();
        Assert.Empty(await scope.ServiceProvider.GetRequiredService<SupplierDbContext>().Suppliers.ToArrayAsync());
        Assert.Empty(await scope.ServiceProvider.GetRequiredService<PurchaseOrderDbContext>().PurchaseOrders.ToArrayAsync());
    }

    [Fact]
    public async Task SupplierAddress_ActualRepositoryUnderRegisteredStrategy_DoesNotRejectItsOwnTransaction()
    {
        using var client = fixture.Client(ProcurementPermissions.SuppliersCreate);
        var supplier = await CreateSupplierAsync(client, "Repository transaction control");
        await using var scope = fixture.Factory.Services.CreateAsyncScope();
        var repository = scope.ServiceProvider.GetRequiredService<Legacy.Maliev.ProcurementService.Application.Interfaces.ISupplierRepository>();
        var failure = await Record.ExceptionAsync(() => repository.CreateAddressAsync(supplier.Id,
            new UpsertSupplierAddressRequest(null, "Bangkok", null, null, null, null, 1), CancellationToken.None));
        Assert.True(failure is null, failure?.Message);
    }

    [Theory]
    [InlineData(false, "service:procurement-parity", "exact")]
    [InlineData(true, "employee:procurement-parity", "exact")]
    [InlineData(true, "service:procurement-parity", "missing")]
    [InlineData(true, "service:procurement-parity", "wildcard")]
    [InlineData(true, "service:procurement-parity", "wrong")]
    [InlineData(true, "Service:procurement-parity", "exact")]
    public async Task PurchaseOrderWrite_OnlyOptedInExactServiceGrantCanReachDatabase(bool optIn, string subject, string grant)
    {
        await using var factory = fixture.CreateFactory(optIn);
        var permissions = grant switch
        {
            "exact" => new[] { ProcurementPermissions.PurchaseOrdersCreate },
            "wildcard" => new[] { "*" },
            "wrong" => new[] { ProcurementPermissions.PurchaseOrdersRead },
            _ => Array.Empty<string>(),
        };
        using var client = fixture.ClientAs(factory, subject, permissions);
        using var response = await client.PostAsJsonAsync("/PurchaseOrders", new { Notes = "Denied local grant" });
        Assert.Equal(HttpStatusCode.Forbidden, response.StatusCode);
        await using var scope = factory.Services.CreateAsyncScope();
        Assert.Empty(await scope.ServiceProvider.GetRequiredService<PurchaseOrderDbContext>().PurchaseOrders.ToArrayAsync());
    }

    [Fact]
    public async Task PurchaseOrderGraph_EnabledExactServiceGrant_IsolatedSchemasComputedItemAndForeignKeyFailure()
    {
        await using var factory = fixture.CreateFactory(true);
        using var client = fixture.ClientAs(factory, "service:procurement-parity", ProcurementPermissions.PurchaseOrderAddressesWrite,
            ProcurementPermissions.PurchaseOrdersCreate, ProcurementPermissions.OrderItemsWrite, ProcurementPermissions.FilesWrite);
        using var addressResponse = await client.PostAsJsonAsync("/purchaseorders/addresses", new UpsertPurchaseOrderAddressRequest(null, "  Bangkok  ", null, null, null, null, 1));
        Assert.Equal(HttpStatusCode.Created, addressResponse.StatusCode);
        var address = await addressResponse.Content.ReadFromJsonAsync<PurchaseOrderAddressResponse>();
        Assert.NotNull(address);
        Assert.Equal("  Bangkok  ", address.AddressLine1);
        using var orderResponse = await client.PostAsJsonAsync("/PurchaseOrders", new { SupplierId = 92742, EmployeeId = 93742, ShippingAddressId = address.Id, BillingAddressId = address.Id });
        Assert.Equal(HttpStatusCode.Created, orderResponse.StatusCode);
        var order = await orderResponse.Content.ReadFromJsonAsync<PurchaseOrderResponse>();
        Assert.NotNull(order);
        using var itemResponse = await client.PostAsJsonAsync("/purchaseorders/orderitems", new UpsertOrderItemRequest(order.Id, "part", null, 3, 12.34m));
        Assert.Equal(HttpStatusCode.Created, itemResponse.StatusCode);
        Assert.Equal(37.02m, (await itemResponse.Content.ReadFromJsonAsync<OrderItemResponse>())!.Subtotal);
        using var fileResponse = await client.PostAsync($"/purchaseorders/{order.Id}/files?bucket=owned-fixture&objectName=metadata-only", null);
        Assert.Equal(HttpStatusCode.Created, fileResponse.StatusCode);
        using var invalidItem = await client.PostAsJsonAsync("/purchaseorders/orderitems", new UpsertOrderItemRequest(999999, "invalid-parent", null, 1, 1));
        Assert.Equal(HttpStatusCode.InternalServerError, invalidItem.StatusCode);
        await using var scope = factory.Services.CreateAsyncScope();
        var database = scope.ServiceProvider.GetRequiredService<PurchaseOrderDbContext>();
        Assert.Single(await database.OrderItems.ToArrayAsync());
        Assert.Single(await database.Files.ToArrayAsync());
        Assert.Equal(92742, (await database.PurchaseOrders.SingleAsync()).SupplierId);
        Assert.Empty(await scope.ServiceProvider.GetRequiredService<SupplierDbContext>().Addresses.ToArrayAsync());
        Assert.Empty(await scope.ServiceProvider.GetRequiredService<SupplierDbContext>().Suppliers.ToArrayAsync());
    }

    [Fact]
    public async Task PurchaseOrderUpdate_StaleExpectedModifiedDate_PreservesFirstCommittedWrite()
    {
        await using var factory = fixture.CreateFactory(true);
        using var client = fixture.ClientAs(factory, "service:procurement-parity", ProcurementPermissions.PurchaseOrdersCreate, ProcurementPermissions.PurchaseOrdersUpdate);
        using var created = await client.PostAsJsonAsync("/PurchaseOrders", new { Notes = "Original" });
        Assert.Equal(HttpStatusCode.Created, created.StatusCode);
        var order = (await created.Content.ReadFromJsonAsync<PurchaseOrderResponse>())!;
        client.DefaultRequestHeaders.Add("X-Expected-Modified-Date", new DateTimeOffset(DateTime.SpecifyKind(order.ModifiedDate!.Value, DateTimeKind.Utc)).ToString("O"));
        fixture.Clock.Advance(TimeSpan.FromSeconds(1));
        using var first = await client.PutAsJsonAsync($"/PurchaseOrders/{order.Id}", new { Notes = "First" });
        Assert.Equal(HttpStatusCode.NoContent, first.StatusCode);
        fixture.Clock.Advance(TimeSpan.FromSeconds(1));
        using var stale = await client.PutAsJsonAsync($"/PurchaseOrders/{order.Id}", new { Notes = "Stale" });
        Assert.Equal(HttpStatusCode.Conflict, stale.StatusCode);
        await using var scope = factory.Services.CreateAsyncScope();
        Assert.Equal("First", (await scope.ServiceProvider.GetRequiredService<PurchaseOrderDbContext>().PurchaseOrders.SingleAsync()).Notes);
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task DetailRead_CommittedUpdateWithRemovalFailure_ReturnsOwningDatabaseState(bool purchaseOrder)
    {
        await using var factory = fixture.CreateFactory(purchaseOrder);
        using var client = DetailClient(factory, purchaseOrder);
        var route = purchaseOrder ? "/PurchaseOrders" : "/Suppliers";
        using var create = await client.PostAsJsonAsync(route, DetailPayload(purchaseOrder, "Original"));
        Assert.Equal(HttpStatusCode.Created, create.StatusCode);
        using var created = JsonDocument.Parse(await create.Content.ReadAsStringAsync());
        var id = created.RootElement.GetProperty("Id").GetInt32();
        using var prime = await client.GetAsync($"{route}/{id}");
        Assert.Equal(HttpStatusCode.OK, prime.StatusCode);
        fixture.Cache.FailRemoval = true;
        using var update = await client.PutAsJsonAsync($"{route}/{id}", DetailPayload(purchaseOrder, "Committed"));
        Assert.Equal(HttpStatusCode.NoContent, update.StatusCode);
        fixture.Cache.FailRemoval = false;
        await AssertStoredDetailAsync(factory, purchaseOrder, "Committed");
        using var current = JsonDocument.Parse(await client.GetStringAsync($"{route}/{id}"));
        Assert.Equal("Committed", current.RootElement.GetProperty(purchaseOrder ? "Notes" : "Name").GetString());
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task DetailRead_LateStaleCacheFillAfterSuccessfulInvalidation_CannotOverrideCommittedState(bool purchaseOrder)
    {
        await using var factory = fixture.CreateFactory(purchaseOrder);
        using var client = DetailClient(factory, purchaseOrder);
        var route = purchaseOrder ? "/PurchaseOrders" : "/Suppliers";
        using var create = await client.PostAsJsonAsync(route, DetailPayload(purchaseOrder, "Original"));
        Assert.Equal(HttpStatusCode.Created, create.StatusCode);
        using var created = JsonDocument.Parse(await create.Content.ReadAsStringAsync());
        var id = created.RootElement.GetProperty("Id").GetInt32();
        using var prime = await client.GetAsync($"{route}/{id}");
        var oldBytes = purchaseOrder
            ? JsonSerializer.SerializeToUtf8Bytes((await prime.Content.ReadFromJsonAsync<PurchaseOrderResponse>())!, new JsonSerializerOptions(JsonSerializerDefaults.Web))
            : JsonSerializer.SerializeToUtf8Bytes((await prime.Content.ReadFromJsonAsync<SupplierResponse>())!, new JsonSerializerOptions(JsonSerializerDefaults.Web));
        fixture.Cache.DelayNextWrite();
        var fill = fixture.Cache.SetAsync($"{(purchaseOrder ? "purchase-order" : "supplier")}:{id}", oldBytes, new DistributedCacheEntryOptions());
        try
        {
            await fixture.Cache.WriteEntered.Task.WaitAsync(TimeSpan.FromSeconds(10));
            using var update = await client.PutAsJsonAsync($"{route}/{id}", DetailPayload(purchaseOrder, "Committed"));
            Assert.Equal(HttpStatusCode.NoContent, update.StatusCode);
            await AssertStoredDetailAsync(factory, purchaseOrder, "Committed");
            fixture.Cache.ReleaseWrite.TrySetResult();
            await fill;
            using var current = JsonDocument.Parse(await client.GetStringAsync($"{route}/{id}"));
            Assert.Equal("Committed", current.RootElement.GetProperty(purchaseOrder ? "Notes" : "Name").GetString());
        }
        finally
        {
            fixture.Cache.ReleaseWrite.TrySetResult();
            await fill;
        }
    }

    private HttpClient DetailClient(ProcurementRuntimeFactory factory, bool purchaseOrder) => purchaseOrder
        ? fixture.ClientAs(factory, "service:procurement-parity", ProcurementPermissions.PurchaseOrdersCreate, ProcurementPermissions.PurchaseOrdersRead, ProcurementPermissions.PurchaseOrdersUpdate)
        : fixture.ClientAs(factory, "employee:procurement-parity", ProcurementPermissions.SuppliersCreate, ProcurementPermissions.SuppliersRead, ProcurementPermissions.SuppliersUpdate);
    private static object DetailPayload(bool purchaseOrder, string value) => purchaseOrder ? new { Notes = value } : Request(value);
    private static async Task AssertStoredDetailAsync(ProcurementRuntimeFactory factory, bool purchaseOrder, string expected)
    {
        await using var scope = factory.Services.CreateAsyncScope();
        var actual = purchaseOrder
            ? (await scope.ServiceProvider.GetRequiredService<PurchaseOrderDbContext>().PurchaseOrders.AsNoTracking().SingleAsync()).Notes
            : (await scope.ServiceProvider.GetRequiredService<SupplierDbContext>().Suppliers.AsNoTracking().SingleAsync()).Name;
        Assert.Equal(expected, actual);
    }

    private static UpsertSupplierRequest Request(string name) => new(name, null, null, null, null, null, null, null);
    private static async Task<SupplierResponse> CreateSupplierAsync(HttpClient client, string name)
    {
        using var response = await client.PostAsJsonAsync("/Suppliers", Request(name));
        Assert.Equal(HttpStatusCode.Created, response.StatusCode);
        var supplier = await response.Content.ReadFromJsonAsync<SupplierResponse>();
        Assert.NotNull(supplier);
        return supplier;
    }
}

public class ProcurementRuntimeFixture : IAsyncLifetime
{
    private readonly PostgreSqlContainer supplier;
    private readonly PostgreSqlContainer order;
    private readonly ProcurementFixtureReceipt? ownership;
    private bool disposed;

    public ProcurementRuntimeFixture() : this(null) { }

    protected ProcurementRuntimeFixture(Type? testClass)
    {
        PostgreSqlContainer? acquired = null;
        try
        {
            ownership = testClass is null ? null : new ProcurementFixtureReceipt(testClass);
            acquired = (ownership is null ? OwnedProcurementTestContainers.Postgres("postgres:18.1-bookworm")
                : ownership.Builder("Supplier")).Build();
            supplier = acquired;
            order = (ownership is null ? OwnedProcurementTestContainers.Postgres("postgres:18.1-bookworm")
                : ownership.Builder("PurchaseOrder")).Build();
        }
        catch (Exception original)
        {
            var failures = new List<Exception> { original };
            if (acquired is not null)
            {
                try { OwnedProcurementTestContainers.DisposeAsync(acquired).GetAwaiter().GetResult(); }
                catch (Exception cleanup) { failures.Add(cleanup); }
            }
            signingKey.Dispose();
            if (failures.Count > 1) throw new AggregateException(failures);
            throw;
        }
    }
    private readonly RSA signingKey = RSA.Create(2048);
    public ProcurementRuntimeFactory Factory { get; private set; } = null!;
    public ProcurementFaultCache Cache { get; } = new();
    public FakeTimeProvider Clock { get; } = new(new DateTimeOffset(2026, 10, 1, 0, 0, 0, TimeSpan.Zero));
    public ProcurementRuntimeFactory CreateFactory(bool optIn) => new(supplier.GetConnectionString(), order.GetConnectionString(), signingKey, Cache, Clock, optIn);

    public async Task InitializeAsync()
    {
        await OwnedProcurementTestContainers.SetupAsync(async cancellation =>
        {
            ownership?.Record("admission", "Supplier", "");
            await supplier.StartAsync(cancellation);
            ownership?.Record("start", "Supplier", supplier.Id);
            ownership?.Record("admission", "PurchaseOrder", "");
            await order.StartAsync(cancellation);
            ownership?.Record("start", "PurchaseOrder", order.Id);
            Factory = CreateFactory(false);
            await using var scope = Factory.Services.CreateAsyncScope();
            await scope.ServiceProvider.GetRequiredService<SupplierDbContext>().Database.MigrateAsync(cancellation);
            await scope.ServiceProvider.GetRequiredService<PurchaseOrderDbContext>().Database.MigrateAsync(cancellation);
        }, DisposeAsync);
    }

    public async Task ResetAsync()
    {
        Cache.FailRemoval = Cache.FailWrite = false;
        Cache.Clear();
        await using var scope = Factory.Services.CreateAsyncScope();
        await scope.ServiceProvider.GetRequiredService<SupplierDbContext>().Database.ExecuteSqlRawAsync("TRUNCATE TABLE \"Supplier\", \"Address\" RESTART IDENTITY CASCADE");
        await scope.ServiceProvider.GetRequiredService<PurchaseOrderDbContext>().Database.ExecuteSqlRawAsync("TRUNCATE TABLE \"PurchaseOrder\", \"Address\", \"OrderItem\", \"PurchaseOrderFile\" RESTART IDENTITY CASCADE");
    }

    public HttpClient Client(params string[] permissions)
        => ClientAs(Factory, "employee:procurement-parity", permissions);

    public HttpClient ClientAs(WebApplicationFactory<Program> factory, string subject, params string[] permissions)
    {
        var client = factory.CreateClient();
        var claims = new[] { new Claim(JwtRegisteredClaimNames.Sub, subject) }
            .Concat(permissions.Select(value => new Claim("permission", value)));
        var token = new JwtSecurityToken("https://procurement-parity.invalid", "procurement-parity", claims,
            DateTime.UtcNow.AddMinutes(-1), DateTime.UtcNow.AddMinutes(5), new SigningCredentials(new RsaSecurityKey(signingKey), SecurityAlgorithms.RsaSha256));
        client.DefaultRequestHeaders.Authorization = new AuthenticationHeaderValue("Bearer", new JwtSecurityTokenHandler().WriteToken(token));
        return client;
    }

    public string SignedToken(string subject, DateTime expires, params string[] permissions)
    {
        var claims = new[] { new Claim(JwtRegisteredClaimNames.Sub, subject), new Claim("identity_kind", subject.StartsWith("service:", StringComparison.Ordinal) ? "service" : "employee") }
            .Concat(permissions.Select(value => new Claim("permission", value)));
        var token = new JwtSecurityToken("https://procurement-parity.invalid", "procurement-parity", claims,
            expires.AddMinutes(-10), expires, new SigningCredentials(new RsaSecurityKey(signingKey), SecurityAlgorithms.RsaSha256));
        return new JwtSecurityTokenHandler().WriteToken(token);
    }

    public ClaimsPrincipal ValidateSignedToken(string token) => new JwtSecurityTokenHandler { MapInboundClaims = false }.ValidateToken(token,
        new TokenValidationParameters
        {
            ValidIssuer = "https://procurement-parity.invalid",
            ValidAudience = "procurement-parity",
            IssuerSigningKey = new RsaSecurityKey(signingKey),
            ValidateIssuerSigningKey = true,
            ValidAlgorithms = [SecurityAlgorithms.RsaSha256],
            ClockSkew = TimeSpan.Zero,
        }, out _);

    public async Task DisposeAsync()
    {
        if (disposed) return;
        disposed = true;
        var failures = new List<Exception>();
        if (Factory is not null)
        {
            try { await OwnedProcurementTestContainers.WaitForCleanupAsync(Factory.DisposeAsync().AsTask()); }
            catch (Exception failure) { failures.Add(failure); }
        }
        await DisposeRoleAsync(supplier, "Supplier", failures);
        await DisposeRoleAsync(order, "PurchaseOrder", failures);
        signingKey.Dispose();
        if (failures.Count > 0) throw new AggregateException("Fixture cleanup failed.", failures);
    }
    private async Task DisposeRoleAsync(PostgreSqlContainer container, string role, List<Exception> failures)
    {
        // Receipt failures cannot skip either disposal or mask the initiating setup failure.
        try { ownership?.Record("dispose-start", role, container.Id); }
        catch (Exception failure) { failures.Add(failure); }
        try
        {
            await OwnedProcurementTestContainers.DisposeAsync(container);
            try { ownership?.Record("dispose-return", role, container.Id); }
            catch (Exception failure) { failures.Add(failure); }
        }
        catch (Exception failure) { failures.Add(failure); }
    }
}

public sealed class ProcurementRuntimeFixture<TTestClass> : ProcurementRuntimeFixture
{
    public ProcurementRuntimeFixture() : base(typeof(TTestClass)) { }
}

public sealed class ProcurementRuntimeFactory(string supplierConnection, string orderConnection, RSA key, ProcurementFaultCache cache, TimeProvider clock, bool optIn) : WebApplicationFactory<Program>
{
    public IReadOnlyDictionary<string, string?> WorkloadSettings { get; set; } = new Dictionary<string, string?>();
    public Func<HttpRequestMessage, CancellationToken, Task<HttpResponseMessage>>? AuthTransport { get; set; }
    public Func<HttpRequestMessage, CancellationToken, Task<HttpResponseMessage>>? IamTransport { get; set; }

    protected override void ConfigureWebHost(IWebHostBuilder builder)
    {
        builder.UseEnvironment("Production");
        builder.ConfigureServices(services =>
        {
            services.RemoveAll<IDistributedCache>();
            services.AddSingleton<IDistributedCache>(cache);
            services.RemoveAll<TimeProvider>();
            services.AddSingleton(clock);
            var authTransport = AuthTransport;
            if (authTransport is not null)
                services.AddHttpClient("LegacyAuthServiceTokenExchange").ConfigurePrimaryHttpMessageHandler(() => new ProcurementAuthorityTransport(authTransport));
            var iamTransport = IamTransport;
            if (iamTransport is not null)
                services.AddHttpClient("IAMService").ConfigurePrimaryHttpMessageHandler(() => new ProcurementAuthorityTransport(iamTransport));
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
            ["ConnectionStrings:SupplierDbContext"] = supplierConnection,
            ["ConnectionStrings:PurchaseOrderDbContext"] = orderConnection,
            ["Cache:RedisEnabled"] = "false",
            ["Observability:TracingEnabled"] = "false",
            ["Observability:RuntimeMetricsEnabled"] = "false",
        }).AddInMemoryCollection(WorkloadSettings));
        return base.CreateHost(builder);
    }
}

public sealed class ProcurementFaultCache : IDistributedCache
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

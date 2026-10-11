using System.IdentityModel.Tokens.Jwt;
using System.Collections.Concurrent;
using System.Runtime.ExceptionServices;
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

public sealed class ProcurementRuntimeFixture : IAsyncLifetime
{
    private readonly PostgreSqlContainer supplier;
    private readonly PostgreSqlContainer order;
    private readonly RSA signingKey = RSA.Create(2048);
    private readonly ProcurementFixtureLifetime lifetime = new();
    private readonly List<string> failedStartupContainerIds = [];
    private readonly List<string> failedStartupVolumeIds = [];
    private bool startupFailed;
    public string ResourceRunId { get; } = Guid.NewGuid().ToString("N");
    public int UnsettledOperationCount => lifetime.UnsettledOperations.Count;
    public IReadOnlyList<Exception> ObservedOperationFailures => lifetime.ObservedFailures;

    public ProcurementRuntimeFixture()
    {
        supplier = ProcurementFixtureContainerPolicy.Build(ResourceRunId, "supplier");
        order = ProcurementFixtureContainerPolicy.Build(ResourceRunId, "purchase-order");
    }
    public ProcurementRuntimeFactory Factory { get; private set; } = null!;
    public ProcurementFaultCache Cache { get; } = new();
    public FakeTimeProvider Clock { get; } = new(new DateTimeOffset(2026, 10, 1, 0, 0, 0, TimeSpan.Zero));
    public ProcurementRuntimeFactory CreateFactory(bool optIn) => new(supplier.GetConnectionString(), order.GetConnectionString(), signingKey, Cache, Clock, optIn);

    public Task InitializeAsync() => InitializeAsync(null);
    internal Task InitializeAsync(Func<CancellationToken, Task>? afterProvidersStarted) => lifetime.InitializeAsync(async token =>
    {
        var supplierStart = supplier.StartAsync(token);
        var orderStart = order.StartAsync(token);
        var starts = Task.WhenAll(supplierStart, orderStart);
        try { await starts; }
        catch (Exception primary)
        {
            startupFailed = true;
            var failures = starts.Exception?.InnerExceptions.ToList() ?? [primary];
            try { await WriteFailedStartupEvidenceAsync(supplierStart, orderStart); }
            catch (Exception observationFailure) { failures.Add(observationFailure); }
            if (failures.Count > 1) throw new AggregateException(failures);
            ExceptionDispatchInfo.Capture(primary).Throw();
            throw;
        }
        if (afterProvidersStarted is not null) await afterProvidersStarted(token);
        Factory = CreateFactory(false);
        await using var scope = Factory.Services.CreateAsyncScope();
        await scope.ServiceProvider.GetRequiredService<SupplierDbContext>().Database.MigrateAsync(token);
        await scope.ServiceProvider.GetRequiredService<PurchaseOrderDbContext>().Database.MigrateAsync(token);
    }, DisposeAsync, TimeSpan.FromMinutes(2));

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

    public Task DisposeAsync() => lifetime.CleanupAsync(
        () => Factory is null ? Task.CompletedTask : Factory.DisposeAsync().AsTask(),
        () => supplier.DisposeAsync().AsTask(),
        () => order.DisposeAsync().AsTask(),
        () => { signingKey.Dispose(); return Task.CompletedTask; },
        WriteFailedStartupCleanupEvidenceAsync);

    private async Task WriteFailedStartupEvidenceAsync(Task supplierStart, Task orderStart)
    {
        using var configuration = new Docker.DotNet.DockerClientConfiguration(new Uri(OperatingSystem.IsWindows() ? "npipe://./pipe/docker_engine" : "unix:///var/run/docker.sock"));
        using var docker = configuration.CreateClient();
        using var deadline = new CancellationTokenSource(TimeSpan.FromSeconds(15));
        var rows = new List<object>();
        var observationFailures = new List<Exception>();
        foreach (var (container, role, start) in new[] { (supplier, "supplier", supplierStart), (order, "purchase-order", orderStart) })
        {
            try
            {
                var actual = await docker.Containers.InspectContainerAsync(container.Id, deadline.Token);
                if (actual.Config.Labels["maliev.codex.owner"] != ProcurementFixtureContainerPolicy.Owner || actual.Config.Labels["maliev.codex.run"] != ResourceRunId)
                    throw new InvalidOperationException("Startup observer ownership mismatch.");
                failedStartupContainerIds.Add(actual.ID);
                var volumes = actual.Mounts.Where(mount => mount.Type == "volume").Select(mount => mount.Name).ToArray();
                failedStartupVolumeIds.AddRange(volumes);
                rows.Add(new
                {
                    Id = actual.ID,
                    Role = role,
                    StartTaskStatus = start.Status.ToString(),
                    Created = actual.Created.ToString(),
                    StartedAt = actual.State.StartedAt.ToString(),
                    ProcessId = actual.State.Pid,
                    actual.State.Running,
                    Labels = actual.Config.Labels.Where(pair => pair.Key is "maliev.codex.owner" or "maliev.codex.run" or "maliev.codex.parent-run" or "maliev.codex.role" or "maliev.codex.expires-utc" or "maliev.codex.persistent-data" or "org.testcontainers.session-id").ToDictionary(pair => pair.Key, pair => pair.Value),
                    actual.HostConfig.Memory,
                    actual.HostConfig.MemorySwap,
                    actual.HostConfig.NanoCPUs,
                    RequestedBindings = actual.HostConfig.PortBindings?.SelectMany(pair => (pair.Value ?? []).Select(binding => new { ContainerPort = pair.Key, binding.HostIP, binding.HostPort })).ToArray() ?? [],
                    ActualBindings = actual.NetworkSettings.Ports?.SelectMany(pair => (pair.Value ?? []).Select(binding => new { ContainerPort = pair.Key, binding.HostIP, binding.HostPort })).ToArray() ?? [],
                    Volumes = volumes,
                });
            }
            catch (Exception observationFailure)
            {
                observationFailures.Add(observationFailure);
                rows.Add(new { Role = role, StartTaskStatus = start.Status.ToString(), ObservationFailureType = observationFailure.GetType().FullName });
            }
        }
        ProcurementFixtureDiagnosticFailures.PublishOrThrow(() => WriteStartupEvidence("before-cleanup", new
        {
            ResourceRunId,
            ObservedAtUtc = DateTimeOffset.UtcNow,
            Resources = rows,
            StartFailureTypes = new[] { supplierStart, orderStart }.SelectMany(start => start.Exception?.InnerExceptions.Select(error => error.GetType().FullName) ?? []),
            UnsettledOperations = UnsettledOperationCount,
            DestructiveObserverActions = 0,
            PortAllocationCause = "UNKNOWN: requested and actual bindings observed without a listener attribution or retry",
        }), observationFailures);
    }

    private async Task WriteFailedStartupCleanupEvidenceAsync()
    {
        if (!startupFailed) return;
        using var configuration = new Docker.DotNet.DockerClientConfiguration(new Uri(OperatingSystem.IsWindows() ? "npipe://./pipe/docker_engine" : "unix:///var/run/docker.sock"));
        using var docker = configuration.CreateClient();
        using var deadline = new CancellationTokenSource(TimeSpan.FromSeconds(15));
        var containersAbsent = new List<string>();
        var volumesAbsent = new List<string>();
        var failures = new List<Exception>();
        foreach (var id in failedStartupContainerIds.Distinct(StringComparer.Ordinal))
        {
            try
            {
                await docker.Containers.InspectContainerAsync(id, deadline.Token);
                failures.Add(new InvalidOperationException("Observed startup container remains after cleanup."));
            }
            catch (Docker.DotNet.DockerApiException error) when (error.StatusCode == HttpStatusCode.NotFound) { containersAbsent.Add(id); }
            catch (Exception error) { failures.Add(error); }
        }
        foreach (var name in failedStartupVolumeIds.Distinct(StringComparer.Ordinal))
        {
            try
            {
                await docker.Volumes.InspectAsync(name, deadline.Token);
                failures.Add(new InvalidOperationException("Observed startup volume remains after cleanup."));
            }
            catch (Docker.DotNet.DockerApiException error) when (error.StatusCode == HttpStatusCode.NotFound) { volumesAbsent.Add(name); }
            catch (Exception error) { failures.Add(error); }
        }
        ProcurementFixtureDiagnosticFailures.PublishOrThrow(() => WriteStartupEvidence("after-cleanup", new
        {
            ResourceRunId,
            ObservedAtUtc = DateTimeOffset.UtcNow,
            ContainersObserved = failedStartupContainerIds,
            VolumesObserved = failedStartupVolumeIds,
            ContainersAbsent = containersAbsent,
            VolumesAbsent = volumesAbsent,
            PendingOperationsAtObservation = UnsettledOperationCount,
            IncludesCurrentReadOnlyObserver = true,
            ObservedOperationFailureTypes = ObservedOperationFailures.Select(error => error.GetType().FullName).ToArray(),
            CleanupObservationFailureTypes = failures.Select(error => error.GetType().FullName).ToArray(),
            DestructiveObserverActions = 0,
            FullStartupCustody = failedStartupContainerIds.Distinct(StringComparer.Ordinal).Count() == 2,
        }), failures);
    }

    private void WriteStartupEvidence(string phase, object evidence)
    {
        var directory = Path.Combine(Environment.GetEnvironmentVariable("VSTestResultsDirectory") ?? "TestResults", "fixture-startup-failures");
        Directory.CreateDirectory(directory);
        File.WriteAllText(Path.Combine(directory, ResourceRunId + "-" + phase + ".json"), JsonSerializer.Serialize(evidence));
    }
}

internal static class ProcurementFixtureDiagnosticFailures
{
    internal static void PublishOrThrow(Action publish, IReadOnlyCollection<Exception> observedFailures)
    {
        var failures = observedFailures.ToList();
        try { publish(); }
        catch (Exception publicationFailure) { failures.Add(publicationFailure); }
        if (failures.Count == 1) ExceptionDispatchInfo.Capture(failures[0]).Throw();
        if (failures.Count > 1) throw new AggregateException(failures);
    }
}


internal static class ProcurementFixtureContainerPolicy
{
    internal const long MemoryBytes = 1024L * 1024 * 1024;
    internal const long NanoCpus = 750_000_000;
    internal const string Owner = "procurement-runtime-fixture";

    internal static PostgreSqlContainer Build(string run, string role) => new PostgreSqlBuilder("postgres:18.1-bookworm")
        .WithDockerEndpoint(OperatingSystem.IsWindows() ? "npipe://./pipe/docker_engine" : OperatingSystem.IsLinux() ? "unix:///var/run/docker.sock" : throw new PlatformNotSupportedException("Owned Procurement fixtures require the local Docker endpoint."))
        .WithLabel("maliev.codex.owner", Owner)
        .WithLabel("maliev.codex.run", run)
        .WithLabel("maliev.codex.parent-run", Guid.TryParse(Environment.GetEnvironmentVariable("MALIEV_TEST_RESOURCE_RUN_ID"), out var parent) ? parent.ToString("N") : run)
        .WithLabel("maliev.codex.role", role)
        .WithLabel("maliev.codex.expires-utc", DateTime.UtcNow.AddMinutes(32).ToString("O"))
        .WithLabel("maliev.codex.persistent-data", "false")
        .WithCreateParameterModifier(Apply)
        .Build();

    internal static void Apply(Docker.DotNet.Models.CreateContainerParameters parameters)
    {
        // Preserve the pinned builder's existing PostgreSQL command and arguments.
        parameters.Entrypoint = ["sh", "-c", "exec timeout --signal=INT --kill-after=10s 1800 docker-entrypoint.sh \"$@\"", "procurement-owned-fixture"];
        parameters.HostConfig!.Memory = MemoryBytes;
        parameters.HostConfig.MemorySwap = MemoryBytes;
        parameters.HostConfig.NanoCPUs = NanoCpus;
        foreach (var bindings in parameters.HostConfig.PortBindings.Values)
            foreach (var binding in bindings) binding.HostIP = "127.0.0.1";
    }
}

internal sealed class ProcurementFixtureLifetime(TimeProvider? timeProvider = null)
{
    private readonly TimeProvider clock = timeProvider ?? TimeProvider.System;
    private readonly ConcurrentDictionary<Task, byte> operations = new();
    private readonly ConcurrentDictionary<Exception, byte> observedFailures = new(ReferenceEqualityComparer.Instance);
    internal IReadOnlyList<Task> UnsettledOperations => operations.Keys.ToArray();
    internal IReadOnlyList<Exception> ObservedFailures => observedFailures.Keys.ToArray();
    internal static readonly TimeSpan CleanupDeadline = TimeSpan.FromSeconds(30);

    private void Record(Exception failure)
    {
        observedFailures.TryAdd(failure, 0);
        if (failure is AggregateException aggregate)
            foreach (var inner in aggregate.InnerExceptions) Record(inner);
    }

    private Task Observe(Task operation)
    {
        operations.TryAdd(operation, 0);
        _ = operation.ContinueWith(completed =>
        {
            if (completed.Exception is not null)
                foreach (var failure in completed.Exception.InnerExceptions) Record(failure);
            operations.TryRemove(completed, out _);
        }, CancellationToken.None, TaskContinuationOptions.ExecuteSynchronously, TaskScheduler.Default);
        return operation;
    }

    internal async Task InitializeAsync(Func<CancellationToken, Task> initialize, Func<Task> cleanup, TimeSpan deadline)
    {
        using var cancellation = new CancellationTokenSource(deadline, clock);
        Task? initialization = null;
        try
        {
            initialization = Observe(initialize(cancellation.Token));
            await initialization.WaitAsync(cancellation.Token);
        }
        catch (Exception primary)
        {
            Record(primary);
            var failures = new List<Exception> { primary };
            try { cancellation.Cancel(); }
            catch (Exception cancellationFailure) { Record(cancellationFailure); failures.Add(cancellationFailure); }
            if (initialization is not null && !initialization.IsCompleted)
            {
                try { await initialization.WaitAsync(CleanupDeadline, clock); }
                catch (OperationCanceledException) when (initialization.IsCanceled) { }
                catch (Exception settlementFailure) { Record(settlementFailure); failures.Add(settlementFailure); }
            }
            try { await cleanup(); }
            catch (AggregateException cleanupFailure) { Record(cleanupFailure); failures.AddRange(cleanupFailure.InnerExceptions); }
            catch (Exception cleanupFailure) { Record(cleanupFailure); failures.Add(cleanupFailure); }
            if (failures.Count == 1) ExceptionDispatchInfo.Capture(primary).Throw();
            throw new AggregateException("Owned fixture initialization and cleanup failed.", failures);
        }
    }

    internal async Task CleanupAsync(params Func<Task>[] releases)
    {
        var failures = new List<Exception>();
        foreach (var release in releases)
        {
            try { await Observe(release()).WaitAsync(CleanupDeadline, clock); }
            catch (Exception failure) { Record(failure); failures.Add(failure); }
        }
        if (failures.Count == 1) ExceptionDispatchInfo.Capture(failures[0]).Throw();
        if (failures.Count > 1) throw new AggregateException("Owned fixture cleanup failed.", failures);
    }
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
            services.Configure<HostOptions>(options => options.StartupTimeout = TimeSpan.FromSeconds(30));
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

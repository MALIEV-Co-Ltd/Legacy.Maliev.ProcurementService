using System.Net;
using System.Net.Http.Headers;
using System.Net.Http.Json;
using System.Security.Cryptography;
using System.Text.Json;
using Legacy.Maliev.ProcurementService.Api.Authorization;
using Legacy.Maliev.ProcurementService.Data;
using Legacy.Maliev.ProcurementService.Domain;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.DependencyInjection;

namespace Legacy.Maliev.ProcurementService.Tests.Integration;

/// <summary>Actual Program and registered workload/IAM clients; only remote HTTP authorities are controlled.</summary>
public sealed class ProcurementAuthenticatedIamTests(ProcurementRuntimeFixture fixture)
    : IClassFixture<ProcurementRuntimeFixture>, IAsyncLifetime
{
    public Task InitializeAsync() => fixture.ResetAsync();
    public Task DisposeAsync() => Task.CompletedTask;

    [Fact]
    public async Task EmployeeLiveCreate_UsesWorkloadBearerAndFreshDecisionWithoutClaimFallback()
    {
        var authority = new Authority(fixture);
        await using var app = Configure(authority);
        using var client = fixture.ClientAs(app, Authority.Employee, ProcurementPermissions.PurchaseOrderAddressesWrite);
        using var created = await client.PostAsJsonAsync("/purchaseorders/addresses", Address());
        Assert.Equal(HttpStatusCode.Created, created.StatusCode);
        authority.Allowed = false;
        using var denied = await client.PostAsJsonAsync("/purchaseorders/addresses", Address());
        Assert.Equal(HttpStatusCode.Forbidden, denied.StatusCode);
        Assert.Equal(1, authority.AuthCalls);
        Assert.Equal(2, authority.IamCalls);
        Assert.Null(authority.TransportFailure);
        await using var scope = app.Services.CreateAsyncScope();
        Assert.Single(await scope.ServiceProvider.GetRequiredService<PurchaseOrderDbContext>().Addresses.AsNoTracking().ToListAsync());
        Assert.Empty(await scope.ServiceProvider.GetRequiredService<SupplierDbContext>().Addresses.AsNoTracking().ToListAsync());
    }

    [Fact]
    public async Task EmployeeSupplierDelete_UsesExactOwnedResourceAndNoEmployeeTokenAsWorkload()
    {
        int supplierId;
        await using (var scope = fixture.Factory.Services.CreateAsyncScope())
        {
            var database = scope.ServiceProvider.GetRequiredService<SupplierDbContext>();
            var supplier = new Supplier { Name = "Live resource authority" };
            database.Suppliers.Add(supplier);
            await database.SaveChangesAsync();
            supplierId = supplier.Id;
        }
        var authority = new Authority(fixture)
        {
            Permission = ProcurementPermissions.SuppliersDelete,
            Resource = $"/suppliers/{supplierId}",
        };
        await using var app = Configure(authority);
        using var client = fixture.ClientAs(app, Authority.Employee);
        using var deleted = await client.DeleteAsync($"/Suppliers/{supplierId}");
        Assert.Equal(HttpStatusCode.NoContent, deleted.StatusCode);
        Assert.Equal(1, authority.AuthCalls);
        Assert.Equal(1, authority.IamCalls);
        Assert.Null(authority.TransportFailure);
        await using var readScope = app.Services.CreateAsyncScope();
        Assert.Empty(await readScope.ServiceProvider.GetRequiredService<SupplierDbContext>().Suppliers.AsNoTracking().ToListAsync());
    }

    [Theory]
    [InlineData("missing-client")]
    [InlineData("missing-live-key")]
    [InlineData("short-secret")]
    [InlineData("long-secret")]
    [InlineData("auth-http")]
    [InlineData("iam-http")]
    [InlineData("auth-denied")]
    [InlineData("unknown-client")]
    [InlineData("wrong-secret")]
    [InlineData("auth-unavailable")]
    [InlineData("auth-malformed")]
    [InlineData("auth-oversized")]
    [InlineData("iam-denied")]
    [InlineData("iam-unauthorized")]
    [InlineData("iam-unavailable")]
    [InlineData("iam-malformed")]
    [InlineData("iam-redirect")]
    public async Task EmployeeLiveWrite_AuthorityFailureCannotUseSignedPermissionOrPersist(string mode)
    {
        var authority = new Authority(fixture) { Mode = mode };
        await using var app = Configure(authority);
        using var client = fixture.ClientAs(app, Authority.Employee, ProcurementPermissions.PurchaseOrderAddressesWrite);
        using var denied = await client.PostAsJsonAsync("/purchaseorders/addresses", Address());
        Assert.Equal(HttpStatusCode.Forbidden, denied.StatusCode);
        Assert.Equal(mode.StartsWith("iam-", StringComparison.Ordinal) && mode != "iam-http" ? 1 : 0, authority.IamCalls);
        Assert.Equal(mode is "missing-client" or "missing-live-key" or "short-secret" or "long-secret" or "auth-http" or "iam-http" ? 0 : 1, authority.AuthCalls);
        Assert.Null(authority.TransportFailure);
        await using var scope = app.Services.CreateAsyncScope();
        Assert.Empty(await scope.ServiceProvider.GetRequiredService<PurchaseOrderDbContext>().Addresses.AsNoTracking().ToListAsync());
        Assert.Empty(await scope.ServiceProvider.GetRequiredService<SupplierDbContext>().Addresses.AsNoTracking().ToListAsync());
    }

    [Fact]
    public async Task ExpiredEmployeeJwt_NeverReachesWorkloadExchangeOrIam()
    {
        var authority = new Authority(fixture);
        await using var app = Configure(authority);
        using var client = app.CreateClient();
        client.DefaultRequestHeaders.Authorization = new AuthenticationHeaderValue("Bearer",
            fixture.SignedToken(Authority.Employee, DateTime.UtcNow.AddMinutes(-10), ProcurementPermissions.PurchaseOrderAddressesWrite));
        using var denied = await client.PostAsJsonAsync("/purchaseorders/addresses", Address());
        Assert.Equal(HttpStatusCode.Unauthorized, denied.StatusCode);
        Assert.Equal(0, authority.AuthCalls);
        Assert.Equal(0, authority.IamCalls);
    }

    [Fact]
    public async Task WorkloadResponseBodyDeadline_DeniesWithoutIamOrPersistence()
    {
        var authority = new Authority(fixture) { Mode = "auth-stalled-body" };
        await using var app = Configure(authority);
        using var client = fixture.ClientAs(app, Authority.Employee, ProcurementPermissions.PurchaseOrderAddressesWrite);
        var request = client.PostAsJsonAsync("/purchaseorders/addresses", Address());
        await authority.BodyReadEntered.Task.WaitAsync(TimeSpan.FromSeconds(5));
        fixture.Clock.Advance(TimeSpan.FromSeconds(11));
        using var denied = await request.WaitAsync(TimeSpan.FromSeconds(5));
        Assert.Equal(HttpStatusCode.Forbidden, denied.StatusCode);
        Assert.Equal(1, authority.AuthCalls);
        Assert.Equal(0, authority.IamCalls);
        await using var scope = app.Services.CreateAsyncScope();
        Assert.Empty(await scope.ServiceProvider.GetRequiredService<PurchaseOrderDbContext>().Addresses.AsNoTracking().ToListAsync());
    }

    [Theory]
    [InlineData("response")]
    [InlineData("stream")]
    [InlineData("fault")]
    public async Task WorkloadDeadline_IgnoringCancellationKeepsLateResourceOwnership(string kind)
    {
        var authority = new Authority(fixture);
        await using var app = Configure(authority);
        var entered = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var disposed = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var responseCompletion = new TaskCompletionSource<HttpResponseMessage>(TaskCreationOptions.RunContinuationsAsynchronously);
        var streamCompletion = new TaskCompletionSource<Stream>(TaskCreationOptions.RunContinuationsAsynchronously);
        app.AuthTransport = (_, _) =>
        {
            if (kind == "stream")
                return Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK) { Content = new LateStreamContent(entered, streamCompletion.Task) });
            entered.TrySetResult();
            return responseCompletion.Task;
        };
        using var client = fixture.ClientAs(app, Authority.Employee, ProcurementPermissions.PurchaseOrderAddressesWrite);
        var request = client.PostAsJsonAsync("/purchaseorders/addresses", Address());
        await entered.Task.WaitAsync(TimeSpan.FromSeconds(5));
        fixture.Clock.Advance(TimeSpan.FromSeconds(11));
        using var denied = await request.WaitAsync(TimeSpan.FromSeconds(5));
        Assert.Equal(HttpStatusCode.Forbidden, denied.StatusCode);
        Assert.Equal(0, authority.IamCalls);
        if (kind == "stream") streamCompletion.SetResult(new TrackedStream(disposed));
        else if (kind == "response") responseCompletion.SetResult(new HttpResponseMessage(HttpStatusCode.OK) { Content = new TrackedContent(disposed) });
        else responseCompletion.SetException(new HttpRequestException("Synthetic late transport failure."));
        if (kind != "fault") await disposed.Task.WaitAsync(TimeSpan.FromSeconds(5));
        await using var scope = app.Services.CreateAsyncScope();
        Assert.Empty(await scope.ServiceProvider.GetRequiredService<PurchaseOrderDbContext>().Addresses.AsNoTracking().ToListAsync());
    }

    private ProcurementRuntimeFactory Configure(Authority authority)
    {
        var app = fixture.CreateFactory(false);
        app.WorkloadSettings = authority.Settings();
        app.AuthTransport = authority.AuthAsync;
        app.IamTransport = authority.IamAsync;
        return app;
    }

    private static object Address() => new { AddressLine1 = "Bangkok", CountryId = 66 };

    private sealed class Authority
    {
        internal const string Employee = "employee:procurement-live";
        private const string ClientId = "legacy-procurement-fixture";
        private readonly string secret = Convert.ToHexString(RandomNumberGenerator.GetBytes(32));
        private readonly string liveKey = Convert.ToHexString(RandomNumberGenerator.GetBytes(32));
        private readonly ProcurementRuntimeFixture fixture;
        private readonly string workload;
        internal Authority(ProcurementRuntimeFixture fixture)
        {
            this.fixture = fixture;
            workload = fixture.SignedToken("service:" + ClientId, DateTime.UtcNow.AddMinutes(5), "iam.auth.check-permission");
        }
        internal string Mode { get; init; } = "allow";
        internal string Permission { get; init; } = ProcurementPermissions.PurchaseOrderAddressesWrite;
        internal string Resource { get; init; } = "global";
        internal bool Allowed { get; set; } = true;
        internal int AuthCalls { get; private set; }
        internal int IamCalls { get; private set; }
        internal string? TransportFailure { get; private set; }
        internal TaskCompletionSource BodyReadEntered { get; } = new(TaskCreationOptions.RunContinuationsAsynchronously);

        internal IReadOnlyDictionary<string, string?> Settings()
        {
            var settings = new Dictionary<string, string?>
            {
                ["ServiceAuthentication:ClientId"] = ClientId,
                ["ServiceAuthentication:ClientSecret"] = secret,
                ["Services:Auth:BaseUrl"] = "https://auth.procurement.invalid",
                ["Services:IAMService:BaseUrl"] = "https://iam.procurement.invalid",
                ["IAM:LivePermissionChecks:Credential"] = liveKey,
                ["Features:ResourceScopedAuthEnabled"] = "true",
            };
            switch (Mode)
            {
                case "missing-client": settings.Remove("ServiceAuthentication:ClientId"); break;
                case "missing-live-key": settings.Remove("IAM:LivePermissionChecks:Credential"); break;
                case "short-secret": settings["ServiceAuthentication:ClientSecret"] = new string('a', 8); break;
                case "long-secret": settings["ServiceAuthentication:ClientSecret"] = new string('a', 1025); break;
                case "auth-http": settings["Services:Auth:BaseUrl"] = "http://auth.procurement.invalid"; break;
                case "iam-http": settings["Services:IAMService:BaseUrl"] = "http://iam.procurement.invalid"; break;
                case "unknown-client": settings["ServiceAuthentication:ClientId"] = "unregistered-procurement-fixture"; break;
                case "wrong-secret": settings["ServiceAuthentication:ClientSecret"] = Convert.ToHexString(RandomNumberGenerator.GetBytes(32)); break;
            }
            return settings;
        }

        internal async Task<HttpResponseMessage> AuthAsync(HttpRequestMessage request, CancellationToken cancellationToken)
        {
            try { return await AuthCoreAsync(request, cancellationToken); }
            catch (Exception exception) { TransportFailure = exception.GetType().Name; throw; }
        }

        private async Task<HttpResponseMessage> AuthCoreAsync(HttpRequestMessage request, CancellationToken cancellationToken)
        {
            AuthCalls++;
            Assert.Equal(HttpMethod.Post, request.Method);
            Assert.Equal("https://auth.procurement.invalid/auth/v1/service/login", request.RequestUri!.AbsoluteUri);
            Assert.Null(request.Headers.Authorization);
            using var json = JsonDocument.Parse(await request.Content!.ReadAsStringAsync(cancellationToken));
            Assert.Equal(new[] { "clientId", "clientSecret" }, json.RootElement.EnumerateObject().Select(value => value.Name).Order().ToArray());
            if (Mode == "unknown-client")
            {
                Assert.Equal("unregistered-procurement-fixture", json.RootElement.GetProperty("clientId").GetString());
                return Response(HttpStatusCode.Unauthorized, new { });
            }
            Assert.Equal(ClientId, json.RootElement.GetProperty("clientId").GetString());
            if (Mode == "wrong-secret")
            {
                Assert.False(string.Equals(secret, json.RootElement.GetProperty("clientSecret").GetString(), StringComparison.Ordinal), "The intentionally rejected fixture credential was not forwarded.");
                return Response(HttpStatusCode.Unauthorized, new { });
            }
            Assert.True(string.Equals(secret, json.RootElement.GetProperty("clientSecret").GetString(), StringComparison.Ordinal), "Fixture credential mismatch; values withheld.");
            return Mode switch
            {
                "auth-denied" => Response(HttpStatusCode.Unauthorized, new { }),
                "auth-unavailable" => Response(HttpStatusCode.ServiceUnavailable, new { }),
                "auth-malformed" => Response(HttpStatusCode.OK, new { }),
                "auth-oversized" => new(HttpStatusCode.OK) { Content = new StringContent(new string('a', 32769)) },
                "auth-stalled-body" => new(HttpStatusCode.OK) { Content = new StalledContent(BodyReadEntered) },
                _ => Response(HttpStatusCode.OK, new { accessToken = workload, expiresIn = 300 }),
            };
        }

        internal async Task<HttpResponseMessage> IamAsync(HttpRequestMessage request, CancellationToken cancellationToken)
        {
            try { return await IamCoreAsync(request, cancellationToken); }
            catch (Exception exception) { TransportFailure = exception.GetType().Name; throw; }
        }

        private async Task<HttpResponseMessage> IamCoreAsync(HttpRequestMessage request, CancellationToken cancellationToken)
        {
            IamCalls++;
            Assert.Equal(HttpMethod.Post, request.Method);
            Assert.Equal("https://iam.procurement.invalid/iam/v1/auth/check-permission", request.RequestUri!.AbsoluteUri);
            Assert.Equal("Bearer", request.Headers.Authorization?.Scheme);
            Assert.True(string.Equals(workload, request.Headers.Authorization?.Parameter, StringComparison.Ordinal), "Fixture workload bearer mismatch; value withheld.");
            var principal = fixture.ValidateSignedToken(request.Headers.Authorization!.Parameter!);
            Assert.Equal("service:" + ClientId, principal.FindFirst("sub")?.Value);
            Assert.Equal("service", principal.FindFirst("identity_kind")?.Value);
            Assert.True(string.Equals(liveKey, Assert.Single(request.Headers.GetValues("X-Maliev-IAM-Live-Check-Key")), StringComparison.Ordinal), "Fixture live credential mismatch; value withheld.");
            using var json = JsonDocument.Parse(await request.Content!.ReadAsStringAsync(cancellationToken));
            Assert.Equal(Employee, json.RootElement.GetProperty("principalId").GetString());
            Assert.Equal(Permission, json.RootElement.GetProperty("permissionId").GetString());
            Assert.Equal(Resource, json.RootElement.GetProperty("resourcePath").GetString());
            Assert.True(json.RootElement.GetProperty("bypassCache").GetBoolean());
            return Mode switch
            {
                "iam-unauthorized" => Response(HttpStatusCode.Unauthorized, new { }),
                "iam-unavailable" => Response(HttpStatusCode.ServiceUnavailable, new { }),
                "iam-malformed" => Response(HttpStatusCode.OK, new { allowed = "invalid" }),
                "iam-redirect" => new(HttpStatusCode.Redirect) { Headers = { Location = new Uri("https://refused.invalid") } },
                _ => Response(HttpStatusCode.OK, new { allowed = Allowed && Mode != "iam-denied" }),
            };
        }

        private static HttpResponseMessage Response(HttpStatusCode status, object body) => new(status) { Content = JsonContent.Create(body) };
    }

    private sealed class TrackedContent(TaskCompletionSource disposed) : ByteArrayContent([])
    {
        protected override void Dispose(bool disposing)
        {
            base.Dispose(disposing);
            if (disposing) disposed.TrySetResult();
        }
    }

    private sealed class TrackedStream(TaskCompletionSource disposed) : MemoryStream
    {
        protected override void Dispose(bool disposing)
        {
            base.Dispose(disposing);
            if (disposing) disposed.TrySetResult();
        }
    }

    private sealed class LateStreamContent(TaskCompletionSource entered, Task<Stream> completion) : HttpContent
    {
        protected override bool TryComputeLength(out long length) { length = 0; return false; }
        protected override Task SerializeToStreamAsync(Stream stream, TransportContext? context) => throw new InvalidOperationException("Direct stream control required.");
        protected override Task<Stream> CreateContentReadStreamAsync(CancellationToken cancellationToken)
        {
            entered.TrySetResult();
            return completion;
        }
    }

    private sealed class StalledContent(TaskCompletionSource entered) : HttpContent
    {
        private readonly CancellationTokenSource disposed = new();
        protected override bool TryComputeLength(out long length) { length = 0; return false; }
        protected override Task SerializeToStreamAsync(Stream stream, TransportContext? context) => throw new InvalidOperationException("Cancellation-aware body read required.");
        protected override async Task SerializeToStreamAsync(Stream stream, TransportContext? context, CancellationToken cancellationToken)
        {
            entered.TrySetResult();
            using var linked = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken, disposed.Token);
            await Task.Delay(Timeout.InfiniteTimeSpan, linked.Token);
        }

        protected override void Dispose(bool disposing)
        {
            if (disposing) disposed.Cancel();
            base.Dispose(disposing);
        }
    }
}

internal sealed class ProcurementAuthorityTransport(Func<HttpRequestMessage, CancellationToken, Task<HttpResponseMessage>> send) : HttpMessageHandler
{
    protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken) => send(request, cancellationToken);
}

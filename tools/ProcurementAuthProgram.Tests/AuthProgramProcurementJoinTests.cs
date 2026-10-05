extern alias auth_api;
using FrozenAuthEntryPoint = auth_api::Program;
using System.IdentityModel.Tokens.Jwt;
using System.Net;
using System.Net.Http.Headers;
using System.Net.Http.Json;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Legacy.Maliev.AuthService.Application;
using Legacy.Maliev.AuthService.Domain;
using Legacy.Maliev.AuthService.Infrastructure;
using Legacy.Maliev.ProcurementService.Api.Authorization;
using Legacy.Maliev.ProcurementService.Data;
using Legacy.Maliev.ProcurementService.Domain;
using Legacy.Maliev.ProcurementService.Tests.Integration;
using Microsoft.AspNetCore.Authentication.JwtBearer;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Identity;
using Microsoft.AspNetCore.Mvc.Testing;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Options;
using Microsoft.IdentityModel.Tokens;
using Npgsql;

namespace Procurement.AuthProgram.Tests;

public sealed class AuthProgramProcurementJoinTests(JoinPostgresFixture fixture) : IClassFixture<JoinPostgresFixture>
{
    [Fact]
    public async Task RealEmployeeAndWorkloadEndpoints_LiveCreateThenFreshDeny()
    {
        await using var join = await Join.CreateAsync(fixture);
        await using var app = join.ProcurementFactory();
        using var client = join.EmployeeClient(app);
        using var created = await client.PostAsJsonAsync("/purchaseorders/addresses", Address());
        Assert.Equal(HttpStatusCode.Created, created.StatusCode);
        join.Allowed = false;
        using var denied = await client.PostAsJsonAsync("/purchaseorders/addresses", Address());
        Assert.Equal(HttpStatusCode.Forbidden, denied.StatusCode);
        Assert.Equal(1, join.WorkloadCalls);
        Assert.Equal([200], join.WorkloadStatuses);
        Assert.Equal(2, join.IamCalls);
        Assert.Null(join.TransportFailure);
        await using var scope = app.Services.CreateAsyncScope();
        Assert.Single(await scope.ServiceProvider.GetRequiredService<PurchaseOrderDbContext>().Addresses.AsNoTracking().ToListAsync());
        Assert.Empty(await scope.ServiceProvider.GetRequiredService<SupplierDbContext>().Addresses.AsNoTracking().ToListAsync());
        var session = Assert.Single(await join.State.RefreshSessions.AsNoTracking().ToListAsync());
        Assert.Equal(Join.Employee, session.IdentityId);
        Assert.Null(session.RevokedAt);
        Assert.Equal(session.Id.ToString("D"), join.Validate(join.EmployeeToken).FindFirst("sid")?.Value);
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task RealWorkloadBearer_SupplierDeleteUsesEmployeeAndExactResource(bool resourceScoped)
    {
        await using var join = await Join.CreateAsync(fixture);
        int id;
        int retainedId;
        await using (var seed = join.Procurement.Factory.Services.CreateAsyncScope())
        {
            var database = seed.ServiceProvider.GetRequiredService<SupplierDbContext>();
            var row = new Supplier { Name = "Auth producer join fixture" };
            var retained = new Supplier { Name = "Fresh denied supplier fixture" };
            database.Suppliers.AddRange(row, retained);
            await database.SaveChangesAsync();
            id = row.Id;
            retainedId = retained.Id;
        }
        join.Permission = ProcurementPermissions.SuppliersDelete;
        join.ResourceScoped = resourceScoped;
        join.Resource = resourceScoped ? $"/suppliers/{id}" : "global";
        await using var app = join.ProcurementFactory();
        using var client = join.EmployeeClient(app);
        using var deleted = await client.DeleteAsync($"/Suppliers/{id}");
        Assert.Equal(HttpStatusCode.NoContent, deleted.StatusCode);
        Assert.Contains(join.Validate(join.EmployeeToken).FindAll("permissions"), claim => claim.Value == ProcurementPermissions.SuppliersDelete);
        join.Resource = resourceScoped ? $"/suppliers/{retainedId}" : "global";
        join.Allowed = false;
        using var denied = await client.DeleteAsync($"/Suppliers/{retainedId}");
        Assert.Equal(HttpStatusCode.Forbidden, denied.StatusCode);
        Assert.Equal(1, join.WorkloadCalls);
        Assert.Equal([200], join.WorkloadStatuses);
        Assert.Equal(2, join.IamCalls);
        Assert.Null(join.TransportFailure);
        await using var scope = app.Services.CreateAsyncScope();
        Assert.Equal(retainedId, Assert.Single(await scope.ServiceProvider.GetRequiredService<SupplierDbContext>().Suppliers.AsNoTracking().ToListAsync()).Id);
        Assert.Empty(await scope.ServiceProvider.GetRequiredService<PurchaseOrderDbContext>().Addresses.AsNoTracking().ToListAsync());
    }

    [Theory]
    [InlineData("wrong-secret")]
    [InlineData("unknown-client")]
    [InlineData("missing-live-key")]
    [InlineData("iam-denied")]
    [InlineData("iam-unauthorized")]
    [InlineData("iam-malformed")]
    [InlineData("wrong-issuer")]
    [InlineData("wrong-audience")]
    public async Task ActualProducerRefusalOrConsumerTrustFailure_CannotPersist(string mode)
    {
        await using var join = await Join.CreateAsync(fixture);
        join.Mode = mode;
        await using var app = join.ProcurementFactory();
        using var client = join.EmployeeClient(app);
        using var denied = await client.PostAsJsonAsync("/purchaseorders/addresses", Address());
        var untrusted = mode is "wrong-issuer" or "wrong-audience";
        Assert.Equal(untrusted ? HttpStatusCode.Unauthorized : HttpStatusCode.Forbidden, denied.StatusCode);
        Assert.Equal(untrusted || mode == "missing-live-key" ? 0 : 1, join.WorkloadCalls);
        Assert.Equal(mode.StartsWith("iam-", StringComparison.Ordinal) ? 1 : 0, join.IamCalls);
        if (mode is "wrong-secret" or "unknown-client") Assert.Equal([401], join.WorkloadStatuses);
        if (mode.StartsWith("iam-", StringComparison.Ordinal)) Assert.Equal([200], join.WorkloadStatuses);
        Assert.Null(join.TransportFailure);
        await using var scope = app.Services.CreateAsyncScope();
        Assert.Empty(await scope.ServiceProvider.GetRequiredService<PurchaseOrderDbContext>().Addresses.AsNoTracking().ToListAsync());
        Assert.Empty(await scope.ServiceProvider.GetRequiredService<SupplierDbContext>().Addresses.AsNoTracking().ToListAsync());
    }

    private static object Address() => new { AddressLine1 = "Auth producer fixture", CountryId = 66 };

    private sealed class Join : IAsyncDisposable
    {
        internal const string Employee = "employee:procurement-auth-join";
        private const string ClientId = "procurement-join-test-only";
        private const string Issuer = "https://procurement-auth-program.invalid";
        private const string Audience = "procurement-auth-program-services";
        private readonly Legacy.Maliev.AuthService.Tests.PostgresFixture postgres;
        private readonly RSA signing = RSA.Create(2048);
        private readonly string password = Convert.ToHexString(RandomNumberGenerator.GetBytes(32));
        private readonly string secret = Convert.ToHexString(RandomNumberGenerator.GetBytes(32));
        private readonly string liveKey = Convert.ToHexString(RandomNumberGenerator.GetBytes(32));
        private CustomerIdentityDbContext customers = null!;
        private EmployeeIdentityDbContext employees = null!;
        private Factory auth = null!;
        private HttpMessageInvoker authTransport = null!;
        private bool authStarted;
        internal ProcurementRuntimeFixture Procurement { get; }
        internal RefreshSessionDbContext State { get; private set; } = null!;
        internal string EmployeeToken { get; private set; } = null!;
        internal string Mode { get; set; } = "allow";
        internal bool Allowed { get; set; } = true;
        internal bool ResourceScoped { get; set; }
        internal string Permission { get; set; } = ProcurementPermissions.PurchaseOrderAddressesWrite;
        internal string Resource { get; set; } = "global";
        internal int WorkloadCalls { get; private set; }
        internal List<int> WorkloadStatuses { get; } = [];
        internal int IamCalls { get; private set; }
        internal string? TransportFailure { get; private set; }

        private Join(JoinPostgresFixture fixture)
        {
            postgres = fixture.Auth;
            Procurement = fixture.Procurement;
        }

        internal static async Task<Join> CreateAsync(JoinPostgresFixture fixture)
        {
            var join = new Join(fixture);
            try
            {
                await join.Procurement.ResetAsync();
                join.Procurement.Clock.SetUtcNow(DateTimeOffset.UtcNow);
                join.customers = await join.postgres.CreateCustomerContextAsync();
                join.employees = await join.postgres.CreateEmployeeContextAsync();
                join.State = await join.postgres.CreateStateContextAsync();
                var row = new LegacyIdentityRow
                {
                    Id = Employee,
                    DatabaseID = 42,
                    UserName = "procurement-join@example.invalid",
                    NormalizedUserName = "PROCUREMENT-JOIN@EXAMPLE.INVALID",
                    Email = "procurement-join@example.invalid",
                    NormalizedEmail = "PROCUREMENT-JOIN@EXAMPLE.INVALID",
                    EmailConfirmed = true,
                    SecurityStamp = Guid.NewGuid().ToString("D"),
                    ConcurrencyStamp = Guid.NewGuid().ToString("D"),
                    LockoutEnabled = true,
                };
                row.PasswordHash = new PasswordHasher<LegacyIdentityRow>().HashPassword(row, join.password);
                join.employees.Users.Add(row);
                await join.employees.SaveChangesAsync();
                join.auth = new Factory(join);
                using var client = join.auth.CreateClient(new WebApplicationFactoryClientOptions { BaseAddress = new Uri("https://localhost"), AllowAutoRedirect = false });
                join.authStarted = true;
                using var login = await client.PostAsJsonAsync("/auth/v1/login", new LoginRequest(row.UserName, join.password, IdentityKind.Employee));
                Assert.Equal(HttpStatusCode.OK, login.StatusCode);
                var body = await login.Content.ReadFromJsonAsync<JsonElement>();
                Assert.Equal(["accessToken", "expiresIn", "refreshExpiresAt", "refreshToken", "tokenType"], body.EnumerateObject().Select(property => property.Name).Order().ToArray());
                var issued = body.Deserialize<TokenResponse>(new JsonSerializerOptions(JsonSerializerDefaults.Web))!;
                Assert.Equal("Bearer", issued.TokenType);
                Assert.Equal(900, issued.ExpiresIn);
                join.EmployeeToken = issued.AccessToken;
                var principal = join.Validate(join.EmployeeToken);
                Assert.Equal(Employee, principal.FindFirst("sub")?.Value);
                Assert.Equal("employee", principal.FindFirst("identity_kind")?.Value);
                Assert.NotNull(principal.FindFirst("sid"));
                join.authTransport = new HttpMessageInvoker(join.auth.Server.CreateHandler());
                return join;
            }
            catch
            {
                try { await join.DisposeAsync(); }
                catch { /* Cleanup attempted every owner; preserve the original startup failure. */ }
                throw;
            }
        }

        internal System.Security.Claims.ClaimsPrincipal Validate(string token)
        {
            var parameters = auth.Services.GetRequiredService<IOptionsMonitor<JwtBearerOptions>>()
                .Get(JwtBearerDefaults.AuthenticationScheme).TokenValidationParameters;
            var principal = new JwtSecurityTokenHandler { MapInboundClaims = false }.ValidateToken(token, parameters, out var validated);
            Assert.Equal(SecurityAlgorithms.RsaSha256, Assert.IsType<JwtSecurityToken>(validated).Header.Alg);
            return principal;
        }

        internal ProcurementRuntimeFactory ProcurementFactory()
        {
            var app = Procurement.CreateFactory(false);
            app.WorkloadSettings = new Dictionary<string, string?>
            {
                ["Jwt:Issuer"] = Mode == "wrong-issuer" ? "https://untrusted-producer.invalid" : Issuer,
                ["Jwt:Audience"] = Mode == "wrong-audience" ? "untrusted-audience" : Audience,
                ["Jwt:PublicKey"] = Convert.ToBase64String(Encoding.UTF8.GetBytes(signing.ExportSubjectPublicKeyInfoPem())),
                ["Services:Auth:BaseUrl"] = "https://procurement-auth-program.invalid",
                ["Services:IAMService:BaseUrl"] = "https://procurement-join-iam.invalid",
                ["ServiceAuthentication:ClientId"] = Mode == "unknown-client" ? "unenrolled-test-only" : ClientId,
                ["ServiceAuthentication:ClientSecret"] = Mode == "wrong-secret" ? Convert.ToHexString(RandomNumberGenerator.GetBytes(32)) : secret,
                ["IAM:LivePermissionChecks:Credential"] = Mode == "missing-live-key" ? null : liveKey,
                ["Features:ResourceScopedAuthEnabled"] = ResourceScoped.ToString(),
            };
            app.AuthTransport = AuthAsync;
            app.IamTransport = IamAsync;
            return app;
        }

        internal HttpClient EmployeeClient(ProcurementRuntimeFactory app)
        {
            var client = app.CreateClient(new WebApplicationFactoryClientOptions { BaseAddress = new Uri("https://localhost"), AllowAutoRedirect = false });
            client.DefaultRequestHeaders.Authorization = new AuthenticationHeaderValue("Bearer", EmployeeToken);
            return client;
        }

        private async Task<HttpResponseMessage> AuthAsync(HttpRequestMessage request, CancellationToken cancellationToken)
        {
            WorkloadCalls++;
            try
            {
                Assert.Equal(HttpMethod.Post, request.Method);
                Assert.Equal("https://procurement-auth-program.invalid/auth/v1/service/login", request.RequestUri!.AbsoluteUri);
                Assert.Null(request.Headers.Authorization);
                using var json = JsonDocument.Parse(await request.Content!.ReadAsStringAsync(cancellationToken));
                Assert.Equal(["clientId", "clientSecret"], json.RootElement.EnumerateObject().Select(property => property.Name).Order().ToArray());
                var response = await authTransport.SendAsync(request, cancellationToken);
                WorkloadStatuses.Add((int)response.StatusCode);
                if (response.IsSuccessStatusCode)
                {
                    // Inspect a buffered copy: ReadFromJsonAsync disposes its content
                    // stream, which the registered Procurement guard must still read.
                    using var inspected = JsonDocument.Parse(await response.Content.ReadAsStringAsync(cancellationToken));
                    var body = inspected.RootElement;
                    Assert.Equal(["accessToken", "expiresIn", "tokenType"], body.EnumerateObject().Select(property => property.Name).Order().ToArray());
                    var issued = body.Deserialize<ServiceTokenResponse>(new JsonSerializerOptions(JsonSerializerDefaults.Web))!;
                    Assert.Equal("Bearer", issued.TokenType);
                    Assert.Equal(900, issued.ExpiresIn);
                    var principal = Validate(issued.AccessToken);
                    Assert.Equal("service:" + ClientId, principal.FindFirst("sub")?.Value);
                    Assert.Equal("service", principal.FindFirst("identity_kind")?.Value);
                }
                return response;
            }
            catch (Exception exception)
            {
                TransportFailure = exception.GetType().Name;
                throw;
            }
        }

        private async Task<HttpResponseMessage> IamAsync(HttpRequestMessage request, CancellationToken cancellationToken)
        {
            IamCalls++;
            try
            {
                Assert.Equal(HttpMethod.Post, request.Method);
                Assert.Equal("https://procurement-join-iam.invalid/iam/v1/auth/check-permission", request.RequestUri!.AbsoluteUri);
                Assert.Equal("Bearer", request.Headers.Authorization?.Scheme);
                var token = request.Headers.Authorization!.Parameter!;
                Assert.False(string.Equals(token, EmployeeToken, StringComparison.Ordinal), "Employee bearer must not become the workload bearer.");
                var workload = Validate(token);
                Assert.Equal("service:" + ClientId, workload.FindFirst("sub")?.Value);
                Assert.Equal("service", workload.FindFirst("identity_kind")?.Value);
                Assert.Null(workload.FindFirst("sid"));
                Assert.Contains(workload.FindAll("permissions"), claim => claim.Value == "iam.auth.check-permission");
                Assert.True(string.Equals(liveKey, Assert.Single(request.Headers.GetValues("X-Maliev-IAM-Live-Check-Key")), StringComparison.Ordinal), "Live credential mismatch; value withheld.");
                using var json = JsonDocument.Parse(await request.Content!.ReadAsStringAsync(cancellationToken));
                Assert.Equal(Employee, json.RootElement.GetProperty("principalId").GetString());
                Assert.Equal(Permission, json.RootElement.GetProperty("permissionId").GetString());
                Assert.Equal(Resource, json.RootElement.GetProperty("resourcePath").GetString());
                Assert.True(json.RootElement.GetProperty("bypassCache").GetBoolean());
                return Mode switch
                {
                    "iam-unauthorized" => new(HttpStatusCode.Unauthorized) { Content = JsonContent.Create(new { }) },
                    "iam-malformed" => new(HttpStatusCode.OK) { Content = JsonContent.Create(new { allowed = "invalid" }) },
                    _ => new(HttpStatusCode.OK) { Content = JsonContent.Create(new { allowed = Allowed && Mode != "iam-denied" }) },
                };
            }
            catch (Exception exception)
            {
                TransportFailure = exception.GetType().Name;
                throw;
            }
        }

        public async ValueTask DisposeAsync()
        {
            var connections = new List<NpgsqlConnection>();
            var releases = new List<Func<ValueTask>>
            {
                () => { authTransport?.Dispose(); return ValueTask.CompletedTask; },
            };
            if (authStarted)
            {
                releases.Add(async () =>
                {
                    await using var scope = auth.Services.CreateAsyncScope();
                    connections.Add((NpgsqlConnection)scope.ServiceProvider.GetRequiredService<CustomerIdentityDbContext>().Database.GetDbConnection());
                    connections.Add((NpgsqlConnection)scope.ServiceProvider.GetRequiredService<EmployeeIdentityDbContext>().Database.GetDbConnection());
                    connections.Add((NpgsqlConnection)scope.ServiceProvider.GetRequiredService<RefreshSessionDbContext>().Database.GetDbConnection());
                });
            }
            if (auth is not null) releases.Add(() => auth.DisposeAsync());
            foreach (var context in new DbContext?[] { customers, employees, State })
            {
                if (context is null) continue;
                releases.Add(() => { connections.Add((NpgsqlConnection)context.Database.GetDbConnection()); return ValueTask.CompletedTask; });
                releases.Add(() => context.DisposeAsync());
            }
            releases.Add(() => OwnedCleanup.RunAsync(connections.Select(connection => new Func<ValueTask>(() =>
            {
                NpgsqlConnection.ClearPool(connection);
                return ValueTask.CompletedTask;
            })).ToArray()));
            releases.Add(() => { signing.Dispose(); return ValueTask.CompletedTask; });
            await OwnedCleanup.RunAsync(releases.ToArray());
        }

        private sealed class Factory(Join join) : WebApplicationFactory<FrozenAuthEntryPoint>
        {
            protected override void ConfigureWebHost(IWebHostBuilder builder)
            {
                builder.UseEnvironment("Production");
                builder.UseContentRoot(Path.GetFullPath(Path.Combine(AppContext.BaseDirectory, "../../../../../.joined-public/Legacy.Maliev.AuthService/Legacy.Maliev.AuthService.Api")));
                builder.UseSetting("CORS:AllowedOrigins", "https://procurement-auth-program.invalid");
                builder.ConfigureAppConfiguration((_, configuration) => configuration.AddInMemoryCollection(new Dictionary<string, string?>
                {
                    ["ConnectionStrings:CustomerIdentity"] = join.customers.Database.GetConnectionString(),
                    ["ConnectionStrings:EmployeeIdentity"] = join.employees.Database.GetConnectionString(),
                    ["ConnectionStrings:RefreshSessions"] = join.State.Database.GetConnectionString(),
                    ["Jwt:Issuer"] = Issuer,
                    ["Jwt:Audience"] = Audience,
                    ["Jwt:PrivateKeyPem"] = join.signing.ExportPkcs8PrivateKeyPem(),
                    ["Jwt:KeyId"] = "procurement-auth-program-test-only",
                    ["Jwt:AccessTokenLifetimeSeconds"] = "900",
                    ["ServiceClients:Clients:" + ClientId + ":SecretSha256"] = ServiceClientCredential.HashSecret(join.secret),
                    ["ServiceClients:Clients:" + ClientId + ":Permissions:0"] = "iam.auth.check-permission",
                    ["Services:IAMService:BaseUrl"] = "https://procurement-join-iam.invalid",
                    ["EmployeeRecovery:Enabled"] = "false",
                    ["QualificationIntrospection:Enabled"] = "false",
                    ["Observability:RuntimeMetricsEnabled"] = "false",
                }));
                // Normal Auth Program owns readers, issuers, sessions, JWT and clients.
                // No application, authorization or authentication service is replaced.
            }
        }
    }
}

public sealed class JoinPostgresFixture : IAsyncLifetime
{
    public Legacy.Maliev.AuthService.Tests.PostgresFixture Auth { get; } = new();
    public ProcurementRuntimeFixture Procurement { get; } = new();
    public Task InitializeAsync() => Task.WhenAll(Auth.InitializeAsync(), Procurement.InitializeAsync());
    public async Task DisposeAsync()
    {
        await OwnedCleanup.RunAsync(() => new ValueTask(Procurement.DisposeAsync()), () => new ValueTask(Auth.DisposeAsync()));
    }
}

using System.Collections.Concurrent;
using System.Globalization;
using System.IdentityModel.Tokens.Jwt;
using System.Net;
using System.Net.Http.Headers;
using System.Security.Claims;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Xml.Linq;
using Legacy.Maliev.ProcurementService.Api.Authorization;
using Legacy.Maliev.ProcurementService.Application.Interfaces;
using Legacy.Maliev.ProcurementService.Application.Models;
using Legacy.Maliev.ProcurementService.Data;
using Legacy.Maliev.ProcurementService.Domain;
using Maliev.Aspire.ServiceDefaults.IAM;
using Maliev.Aspire.ServiceDefaults.Logging;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.Mvc.Testing;
using Microsoft.AspNetCore.TestHost;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Caching.Distributed;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.DependencyInjection.Extensions;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Logging.Abstractions;
using Microsoft.Extensions.Logging.Console;
using Microsoft.Extensions.Options;
using Microsoft.IdentityModel.Tokens;
using Moq;
using Testcontainers.PostgreSql;

namespace Legacy.Maliev.ProcurementService.Tests.Startup;

public sealed class ProcurementStartupLoggingTests(ProcurementLoggingPostgresFixture fixture) : IClassFixture<ProcurementLoggingPostgresFixture>
{
    private const string Sensitive = "private-supplier@example.invalid";

    [Theory]
    [InlineData("/Suppliers/81927", "PostgresException")]
    [InlineData("/PurchaseOrders/81927", "PostgresException")]
    [InlineData("/acceptance/save-supplier", "DbUpdateException")]
    [InlineData("/acceptance/save-order", "DbUpdateException")]
    public async Task ProductionDatabaseFailure_PreservesSafeIncidentWithoutProviderMessages(string path, string exceptionType)
    {
        // Missing schemas force real read/save failures without persisting application data.
        using var factory = Factory();
        using var client = factory.AuthorizedClient();
        using var response = await client.GetAsync(path);
        Assert.Equal(HttpStatusCode.InternalServerError, response.StatusCode);
        var body = await response.Content.ReadAsStringAsync();
        using var error = JsonDocument.Parse(body);
        Assert.Equal(JsonValueKind.Null, error.RootElement.GetProperty("details").ValueKind);
        using var failure = factory.Failure();
        Assert.Equal("CRITICAL", failure.RootElement.GetProperty("severity").GetString());
        var state = failure.RootElement.GetProperty("State");
        Assert.Equal(exceptionType, state.GetProperty("ExceptionType").GetString());
        Assert.Equal(error.RootElement.GetProperty("traceId").GetString(), state.GetProperty("IncidentId").GetString());
        Assert.All(factory.Logs.Lines, line =>
        {
            Assert.DoesNotContain("42P01", line);
            Assert.DoesNotContain("does not exist", line);
            Assert.DoesNotContain("Npgsql.Internal", line);
            Assert.DoesNotContain("SELECT", line);
            Assert.DoesNotContain(Sensitive, line);
        });
        Assert.DoesNotContain("PostgresException", body);
        Assert.DoesNotContain(Sensitive, body);
    }

    [Theory]
    [InlineData("/Suppliers/81927", "Suppliers/{supplierId:int}")]
    [InlineData("/PurchaseOrders/81927", "PurchaseOrders/{purchaseOrderId:int}")]
    public async Task ProductionControllerFailure_UsesActualJwtAuthorizationAndRedactedStructuredEvent(string path, string template)
    {
        using var factory = Factory(stubService: true);
        factory.Service.Setup(service => service.GetSupplierAsync(81927, It.IsAny<CancellationToken>())).ThrowsAsync(new Exception(Sensitive));
        factory.Service.Setup(service => service.GetPurchaseOrderAsync(81927, It.IsAny<CancellationToken>())).ThrowsAsync(new Exception(Sensitive));
        using var client = factory.AuthorizedClient();
        using var request = new HttpRequestMessage(HttpMethod.Get, $"{path}?search={Sensitive}");
        request.Headers.Add("traceparent", "00-0123456789abcdef0123456789abcdef-0123456789abcdef-01");
        request.Headers.Add("X-Correlation-ID", "procurement-acceptance");
        request.Headers.Add("Idempotency-Key", Sensitive);
        using var response = await client.SendAsync(request);
        Assert.Equal(HttpStatusCode.InternalServerError, response.StatusCode);
        using var error = JsonDocument.Parse(await response.Content.ReadAsStringAsync());
        Assert.Equal("An internal server error occurred", error.RootElement.GetProperty("error").GetString());
        Assert.Equal(500, error.RootElement.GetProperty("statusCode").GetInt32());
        Assert.Equal(JsonValueKind.Null, error.RootElement.GetProperty("details").ValueKind);
        Assert.Equal("procurement-acceptance", Assert.Single(response.Headers.GetValues("X-Correlation-ID")));
        using var failure = factory.Failure();
        var root = failure.RootElement;
        var state = root.GetProperty("State");
        Assert.Equal("Critical", root.GetProperty("LogLevel").GetString());
        Assert.Equal("CRITICAL", root.GetProperty("severity").GetString());
        Assert.Equal("Legacy.Maliev.ProcurementService.Api", state.GetProperty("Service").GetString());
        Assert.Equal("GET", state.GetProperty("Method").GetString());
        Assert.Equal(template, state.GetProperty("Path").GetString());
        Assert.Equal(500, state.GetProperty("StatusCode").GetInt32());
        Assert.Equal(error.RootElement.GetProperty("traceId").GetString(), state.GetProperty("IncidentId").GetString());
        Assert.Equal(TimeSpan.Zero, DateTimeOffset.Parse(state.GetProperty("OccurredAtUtc").GetString()!, CultureInfo.InvariantCulture).Offset);
        Assert.Equal(TimeSpan.Zero, DateTimeOffset.Parse(root.GetProperty("Timestamp").GetString()!, CultureInfo.InvariantCulture).Offset);
        Assert.Contains("0123456789abcdef0123456789abcdef", root.GetProperty("Scopes").GetRawText());
        Assert.Contains("procurement-acceptance", root.GetProperty("Scopes").GetRawText());
        Assert.All(factory.Logs.Lines, line =>
        {
            Assert.DoesNotContain("81927", line);
            Assert.DoesNotContain(Sensitive, line);
            Assert.DoesNotContain(client.DefaultRequestHeaders.Authorization!.Parameter!, line);
        });
        Assert.Contains(factory.Logs.Lines, line => line.Contains("responded 500", StringComparison.Ordinal));
    }

    [Fact]
    public async Task ProductionStartup_EnforcesAnonymousAndPermissionBoundariesAndLegacyJson()
    {
        using var factory = Factory(stubService: true);
        factory.Service.Setup(service => service.GetSupplierAsync(7, It.IsAny<CancellationToken>()))
            .ReturnsAsync(new SupplierResponse(7, "Fixture supplier", null, null, null, null, null, null, null, null, null, null));
        using var anonymous = factory.CreateClient();
        Assert.Equal(HttpStatusCode.Unauthorized, (await anonymous.GetAsync("/Suppliers/7")).StatusCode);
        Assert.Equal(HttpStatusCode.Unauthorized, (await anonymous.GetAsync("/PurchaseOrders/7")).StatusCode);
        using var unprivileged = factory.AuthorizedClient(permissions: false);
        Assert.Equal(HttpStatusCode.Forbidden, (await unprivileged.GetAsync("/Suppliers/7")).StatusCode);
        using var allowed = factory.AuthorizedClient();
        using var supplier = JsonDocument.Parse(await allowed.GetStringAsync("/Suppliers/7"));
        Assert.Equal(7, supplier.RootElement.GetProperty("Id").GetInt32());
        Assert.Equal("Fixture supplier", supplier.RootElement.GetProperty("Name").GetString());
        Assert.False(supplier.RootElement.TryGetProperty("Website", out _));
        Assert.False(supplier.RootElement.TryGetProperty("id", out _));
        // A JWT mutation claim must not bypass an authoritative live denial.
        Assert.Equal(HttpStatusCode.Forbidden, (await allowed.DeleteAsync("/PurchaseOrders/7")).StatusCode);
        factory.Iam.Verify(client => client.CheckPermissionLiveAsync(It.IsAny<string>(),
            ProcurementPermissions.PurchaseOrdersDelete, It.IsAny<string?>(), It.IsAny<CancellationToken>()), Times.AtLeastOnce);
        Assert.Equal("Healthy", await anonymous.GetStringAsync("/procurement/liveness"));
    }

    [Fact]
    public async Task ProductionStartedResponse_DoesNotAppendFailureDetailsOrChangeStatus()
    {
        using var factory = Factory();
        using var client = factory.AuthorizedClient();
        using var response = await client.GetAsync($"/acceptance/started/{Sensitive}");
        Assert.Equal(HttpStatusCode.Accepted, response.StatusCode);
        Assert.Equal("accepted", await response.Content.ReadAsStringAsync());
        using var failure = factory.Failure();
        Assert.Equal(202, failure.RootElement.GetProperty("State").GetProperty("StatusCode").GetInt32());
        Assert.All(factory.Logs.Lines, line => Assert.DoesNotContain(Sensitive, line));
    }

    [Fact]
    public async Task ProductionCacheFailure_KeepsFallbackAndTypeOnlyDiagnostics()
    {
        using var factory = Factory();
        using var scope = factory.Services.CreateScope();
        var cache = new Mock<IDistributedCache>();
        cache.Setup(value => value.GetAsync(It.IsAny<string>(), It.IsAny<CancellationToken>())).ThrowsAsync(new Exception(Sensitive));
        var adapter = new DistributedProcurementCache(cache.Object,
            scope.ServiceProvider.GetRequiredService<ILogger<DistributedProcurementCache>>());
        Assert.Null(await adapter.GetAsync<SupplierResponse>(Sensitive, CancellationToken.None));
        var line = Assert.Single(factory.Logs.Lines, value => value.Contains("Procurement cache read failed", StringComparison.Ordinal));
        using var document = JsonDocument.Parse(line);
        Assert.Equal("WARNING", document.RootElement.GetProperty("severity").GetString());
        Assert.Equal("Exception", document.RootElement.GetProperty("Exception").GetString());
        Assert.DoesNotContain(Sensitive, line);
    }

    [Fact]
    public void ProductionArtifact_PreservesNativeProvidersDependenciesAndIsolatedXml()
    {
        using var factory = Factory();
        var providers = factory.Services.GetServices<ILoggerProvider>().Select(provider => provider.GetType().FullName!).ToArray();
        Assert.Contains(providers, name => name.Contains("ConsoleLoggerProvider", StringComparison.Ordinal));
        Assert.Contains(providers, name => name.Contains("OpenTelemetryLoggerProvider", StringComparison.Ordinal));
        Assert.DoesNotContain(providers, name => name.Contains("NLog", StringComparison.Ordinal));
        Assert.Equal(MalievCloudJsonConsoleFormatter.FormatterName,
            factory.Services.GetRequiredService<IOptionsMonitor<ConsoleLoggerOptions>>().CurrentValue.FormatterName);
        var tracking = factory.Services.GetRequiredService<IOptions<LoggerFactoryOptions>>().Value.ActivityTrackingOptions;
        Assert.True(tracking.HasFlag(ActivityTrackingOptions.TraceId | ActivityTrackingOptions.SpanId | ActivityTrackingOptions.ParentId));
        using var dependencies = JsonDocument.Parse(File.ReadAllText(Path.Combine(AppContext.BaseDirectory, "Legacy.Maliev.ProcurementService.Api.deps.json")));
        var libraries = dependencies.RootElement.GetProperty("libraries").EnumerateObject().Select(property => property.Name).ToArray();
        Assert.Contains(libraries, name => name.StartsWith("Legacy.Maliev.ServiceDefaults/", StringComparison.Ordinal));
        Assert.DoesNotContain(libraries, name => name.Contains("NativeLogging", StringComparison.Ordinal)
            || name.Contains("NLog", StringComparison.Ordinal) || name.Contains("LoggerService", StringComparison.Ordinal));
        var root = new DirectoryInfo(AppContext.BaseDirectory);
        while (root is not null && !File.Exists(Path.Combine(root.FullName, "Legacy.Maliev.ProcurementService.slnx"))) root = root.Parent;
        Assert.NotNull(root);
        var assemblyPath = typeof(Program).Assembly.Location;
        // The project reference places the API XML next to the actual built assembly.
        var xml = XDocument.Load(Path.ChangeExtension(assemblyPath, ".xml"));
        Assert.Equal("Legacy.Maliev.ProcurementService.Api", xml.Root?.Element("assembly")?.Element("name")?.Value);
        Assert.NotEmpty(xml.Root?.Element("members")?.Elements("member") ?? []);
        Assert.False(File.Exists(Path.Combine(root.FullName, "Legacy.Maliev.ProcurementService.Api", "Legacy.Maliev.ProcurementService.Api.xml")));
    }

    private ProcurementFactory Factory(bool stubService = false) => new(fixture.SupplierConnection, fixture.OrderConnection, stubService);

    private sealed class ProcurementFactory(string supplierConnection, string orderConnection, bool stubService) : WebApplicationFactory<Program>
    {
        private readonly RSA _rsa = RSA.Create(2048);
        public Mock<IProcurementService> Service { get; } = new(MockBehavior.Strict);
        public Mock<IIamServiceClient> Iam { get; } = new();
        public CaptureProvider Logs { get; } = new();

        public HttpClient AuthorizedClient(bool permissions = true)
        {
            var client = CreateClient();
            var claims = new List<Claim> { new(JwtRegisteredClaimNames.Sub, "employee:acceptance") };
            if (permissions) claims.AddRange(new[] { ProcurementPermissions.SuppliersRead, ProcurementPermissions.PurchaseOrdersRead,
                ProcurementPermissions.PurchaseOrdersDelete }.Select(permission => new Claim("permission", permission)));
            var token = new JwtSecurityToken("https://iam.maliev.com", "maliev-services", claims,
                DateTime.UtcNow.AddMinutes(-1), DateTime.UtcNow.AddMinutes(5), new SigningCredentials(new RsaSecurityKey(_rsa), SecurityAlgorithms.RsaSha256));
            client.DefaultRequestHeaders.Authorization = new AuthenticationHeaderValue("Bearer", new JwtSecurityTokenHandler().WriteToken(token));
            return client;
        }

        protected override void ConfigureWebHost(IWebHostBuilder builder)
        {
            builder.UseEnvironment("Production");
            builder.ConfigureTestServices(services =>
            {
                if (stubService)
                {
                    services.RemoveAll<IProcurementService>();
                    services.AddSingleton(Service.Object);
                }
                Iam.Setup(client => client.CheckPermissionAsync(It.IsAny<string>(), It.IsAny<string>(), It.IsAny<string?>(), It.IsAny<CancellationToken>())).ReturnsAsync(false);
                Iam.Setup(client => client.CheckPermissionLiveAsync(It.IsAny<string>(), It.IsAny<string>(), It.IsAny<string?>(), It.IsAny<CancellationToken>())).ReturnsAsync(false);
                services.RemoveAll<IIamServiceClient>();
                services.AddSingleton(Iam.Object);
                services.AddControllers().AddApplicationPart(typeof(ProcurementAcceptanceController).Assembly);
                services.AddSingleton<ILoggerProvider>(provider =>
                {
                    Logs.Formatter = new MalievCloudJsonConsoleFormatter(provider.GetRequiredService<IOptionsMonitor<JsonConsoleFormatterOptions>>());
                    return Logs;
                });
            });
        }

        protected override IHost CreateHost(IHostBuilder builder)
        {
            builder.ConfigureHostConfiguration(configuration => configuration.AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["Jwt:PublicKey"] = Convert.ToBase64String(Encoding.UTF8.GetBytes(_rsa.ExportSubjectPublicKeyInfoPem())),
                ["ConnectionStrings:SupplierDbContext"] = supplierConnection,
                ["ConnectionStrings:PurchaseOrderDbContext"] = orderConnection,
                ["Cache:RedisEnabled"] = "false",
                ["Observability:TracingEnabled"] = "true",
                ["Observability:RuntimeMetricsEnabled"] = "false",
                ["Logging:LogLevel:Default"] = "Information",
            }));
            return base.CreateHost(builder);
        }

        public JsonDocument Failure() => JsonDocument.Parse(Assert.Single(Logs.Lines, line => line.Contains("UnhandledRequestFailure", StringComparison.Ordinal)));
        protected override void Dispose(bool disposing)
        {
            base.Dispose(disposing);
            if (disposing) _rsa.Dispose();
        }
    }

    private sealed class CaptureProvider : ILoggerProvider, ISupportExternalScope
    {
        private IExternalScopeProvider _scopes = new LoggerExternalScopeProvider();
        public ConcurrentQueue<string> Lines { get; } = new();
        public MalievCloudJsonConsoleFormatter Formatter { get; set; } = null!;
        public ILogger CreateLogger(string categoryName) => new CaptureLogger(this, categoryName);
        public void SetScopeProvider(IExternalScopeProvider scopeProvider) => _scopes = scopeProvider;
        public void Dispose() { }
        private sealed class CaptureLogger(CaptureProvider provider, string category) : ILogger
        {
            public IDisposable? BeginScope<TState>(TState state) where TState : notnull => provider._scopes.Push(state);
            public bool IsEnabled(LogLevel logLevel) => true;
            public void Log<TState>(LogLevel level, EventId eventId, TState state, Exception? exception, Func<TState, Exception?, string> formatter)
            {
                using var writer = new StringWriter(CultureInfo.InvariantCulture);
                provider.Formatter.Write(new LogEntry<TState>(level, category, eventId, state, exception, formatter), provider._scopes, writer);
                provider.Lines.Enqueue(writer.ToString());
            }
        }
    }
}

public sealed class ProcurementLoggingPostgresFixture : IAsyncLifetime
{
    private readonly PostgreSqlContainer _suppliers = new PostgreSqlBuilder("postgres:18-alpine").Build();
    private readonly PostgreSqlContainer _orders = new PostgreSqlBuilder("postgres:18-alpine").Build();
    public string SupplierConnection => _suppliers.GetConnectionString();
    public string OrderConnection => _orders.GetConnectionString();
    public Task InitializeAsync() => Task.WhenAll(_suppliers.StartAsync(), _orders.StartAsync());
    public async Task DisposeAsync()
    {
        await _suppliers.DisposeAsync();
        await _orders.DisposeAsync();
    }
}

// Loaded by the test factory only, never production startup.
[ApiController]
[Authorize]
public sealed class ProcurementAcceptanceController : ControllerBase
{
    [HttpGet("acceptance/save-supplier")]
    public async Task SaveSupplierAsync([FromServices] SupplierDbContext database)
    {
        database.Suppliers.Add(new Supplier { Name = "private-supplier@example.invalid" });
        await database.SaveChangesAsync();
    }
    [HttpGet("acceptance/save-order")]
    public async Task SaveOrderAsync([FromServices] PurchaseOrderDbContext database)
    {
        database.PurchaseOrders.Add(new PurchaseOrder { SupplierContactPerson = "private-supplier@example.invalid" });
        await database.SaveChangesAsync();
    }
    [HttpGet("acceptance/started/{value}")]
    public async Task StartedAsync()
    {
        Response.StatusCode = StatusCodes.Status202Accepted;
        await Response.WriteAsync("accepted");
        await Response.Body.FlushAsync();
        throw new Exception("private-supplier@example.invalid");
    }
}

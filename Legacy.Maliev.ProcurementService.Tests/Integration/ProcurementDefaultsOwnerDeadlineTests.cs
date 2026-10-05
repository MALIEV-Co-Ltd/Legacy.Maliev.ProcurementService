using System.Collections.Concurrent;
using System.Net;
using System.Net.Http.Json;
using System.Security.Cryptography;
using System.Text.Json;
using Legacy.Maliev.ProcurementService.Api.Authorization;
using Legacy.Maliev.ProcurementService.Data;
using Maliev.Aspire.ServiceDefaults.LegacyAuth;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Mvc.Testing;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging;

namespace Legacy.Maliev.ProcurementService.Tests.Integration;

/// <summary>Normal Procurement DI and local guards consuming the reviewed shared owner deadline.</summary>
public sealed class ProcurementDefaultsOwnerDeadlineTests(ProcurementRuntimeFixture fixture)
    : IClassFixture<ProcurementRuntimeFixture>, IAsyncLifetime
{
    public Task InitializeAsync() => fixture.ResetAsync();
    public Task DisposeAsync() => Task.CompletedTask;

    [Theory]
    [InlineData("response")]
    [InlineData("stream")]
    [InlineData("fault")]
    public async Task SharedDeadline_DeniesThenRetriesWithoutCachingLateResult(string kind)
    {
        var authority = new Authority(fixture);
        var entered = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var response = new TaskCompletionSource<HttpResponseMessage>(TaskCreationOptions.RunContinuationsAsynchronously);
        var stream = new TaskCompletionSource<Stream>(TaskCreationOptions.RunContinuationsAsynchronously);
        var disposed = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var lateToken = fixture.SignedToken("service:legacy-procurement-defaults-fixture", DateTime.UtcNow.AddMinutes(7), "iam.auth.check-permission");
        var lateBytes = JsonSerializer.SerializeToUtf8Bytes(new { accessToken = lateToken, expiresIn = 300 });
        var lateContent = new CountingContent(lateBytes, disposed);
        var lateStream = new CountingStream(lateBytes, disposed);
        var exchanges = 0;
        await using var original = authority.Factory();
        original.AuthTransport = (request, token) =>
        {
            if (Interlocked.Increment(ref exchanges) != 1) return authority.AuthAsync(request, token);
            authority.AssertRequest(request);
            if (kind == "stream")
                return Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK) { Content = new DeferredContent(entered, stream.Task) });
            entered.TrySetResult();
            return response.Task;
        };
        await using var app = WithDeadline(original, TimeSpan.FromMilliseconds(250));
        using var client = fixture.ClientAs(app, Authority.Employee, ProcurementPermissions.PurchaseOrderAddressesWrite);
        var pending = client.PostAsJsonAsync("/purchaseorders/addresses", Address());
        try
        {
            await entered.Task.WaitAsync(TimeSpan.FromSeconds(5));
            using var denied = await pending.WaitAsync(TimeSpan.FromSeconds(5));
            Assert.Equal(HttpStatusCode.Forbidden, denied.StatusCode);
            Assert.Equal(1, exchanges);
            Assert.Equal(0, authority.IamCalls);
            await AssertRowsAsync(app, 0);
            using var recovered = await client.PostAsJsonAsync("/purchaseorders/addresses", Address()).WaitAsync(TimeSpan.FromSeconds(5));
            Assert.Equal(HttpStatusCode.Created, recovered.StatusCode);
            Assert.Equal(2, exchanges);
            Assert.Equal(1, authority.IamCalls);
            if (kind == "stream") stream.SetResult(lateStream);
            else if (kind == "response") response.SetResult(new HttpResponseMessage(HttpStatusCode.OK) { Content = lateContent });
            else response.SetException(new HttpRequestException("Synthetic late exchange fault."));
            if (kind != "fault")
            {
                await disposed.Task.WaitAsync(TimeSpan.FromSeconds(5));
                Assert.Equal(1, kind == "response" ? lateContent.Disposals : lateStream.Disposals);
            }
            var provider = app.Services.GetRequiredService<ILegacyServiceAccessTokenProvider>();
            Assert.Equal(authority.Workload, await provider.GetAccessTokenAsync());
            Assert.Equal(2, exchanges);
            await AssertRowsAsync(app, 1);
        }
        finally
        {
            if (kind == "stream") stream.TrySetResult(lateStream);
            else if (!response.Task.IsCompleted) response.TrySetResult(new HttpResponseMessage(HttpStatusCode.OK) { Content = lateContent });
            try { (await pending.WaitAsync(TimeSpan.FromSeconds(5))).Dispose(); }
            catch (Exception exception) when (exception is HttpRequestException or OperationCanceledException or TimeoutException) { }
        }
    }

    [Fact]
    public async Task CallerCancellation_PreservesCoalescingCacheAndFreshLiveWrite()
    {
        var authority = new Authority(fixture);
        var entered = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var release = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var transportToken = CancellationToken.None;
        var exchanges = 0;
        await using var original = authority.Factory();
        original.AuthTransport = async (request, token) =>
        {
            if (Interlocked.Increment(ref exchanges) == 1)
            {
                transportToken = token;
                entered.TrySetResult();
                await release.Task;
            }
            return await authority.AuthAsync(request, token);
        };
        await using var app = WithDeadline(original, TimeSpan.FromSeconds(5));
        var provider = app.Services.GetRequiredService<ILegacyServiceAccessTokenProvider>();
        using var caller = new CancellationTokenSource();
        var canceled = provider.GetAccessTokenAsync(caller.Token).AsTask();
        var survivors = Enumerable.Range(0, 4).Select(_ => provider.GetAccessTokenAsync().AsTask()).ToArray();
        try
        {
            await entered.Task.WaitAsync(TimeSpan.FromSeconds(5));
            caller.Cancel();
            await Assert.ThrowsAnyAsync<OperationCanceledException>(() => canceled);
            Assert.False(transportToken.IsCancellationRequested);
            release.TrySetResult();
            Assert.All(await Task.WhenAll(survivors).WaitAsync(TimeSpan.FromSeconds(5)), token => Assert.Equal(authority.Workload, token));
            Assert.Equal(1, exchanges);
            using var client = fixture.ClientAs(app, Authority.Employee, ProcurementPermissions.PurchaseOrderAddressesWrite);
            using var created = await client.PostAsJsonAsync("/purchaseorders/addresses", Address());
            Assert.Equal(HttpStatusCode.Created, created.StatusCode);
            Assert.Equal(1, exchanges);
            Assert.Equal(1, authority.IamCalls);
            await AssertRowsAsync(app, 1);
            fixture.Clock.Advance(TimeSpan.FromSeconds(241));
            Assert.Equal(authority.Workload, await provider.GetAccessTokenAsync());
            Assert.Equal(2, exchanges);
        }
        finally
        {
            release.TrySetResult();
            await Task.WhenAll(survivors).WaitAsync(TimeSpan.FromSeconds(5));
        }
    }

    [Fact]
    public async Task LocalAdmissionGuard_RejectsShortSecretBeforePrimaryTransport()
    {
        var authority = new Authority(fixture);
        await using var original = authority.Factory();
        original.WorkloadSettings = authority.Settings(secret: "invalid");
        await using var app = WithDeadline(original, TimeSpan.FromMilliseconds(250));
        using var client = fixture.ClientAs(app, Authority.Employee, ProcurementPermissions.PurchaseOrderAddressesWrite);
        using var denied = await client.PostAsJsonAsync("/purchaseorders/addresses", Address());
        Assert.Equal(HttpStatusCode.Forbidden, denied.StatusCode);
        Assert.Equal(0, authority.AuthCalls);
        Assert.Equal(0, authority.IamCalls);
        await AssertRowsAsync(app, 0);
    }

    [Fact]
    public async Task MalformedAuthorityDiagnostics_DoNotExposeBodySecretOrPrivateOrigin()
    {
        var authority = new Authority(fixture);
        var logs = new ProviderWarnings();
        const string privateOrigin = "http://10.254.253.252/internal-source";
        await using var original = authority.Factory();
        original.AuthTransport = (_, _) => Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK)
        {
            Content = new StringContent(privateOrigin + authority.Secret + authority.Workload),
        });
        await using var app = original.WithWebHostBuilder(builder => builder.ConfigureServices(services =>
            services.AddLogging(logging => logging.AddProvider(logs))));
        using var client = fixture.ClientAs(app, Authority.Employee, ProcurementPermissions.PurchaseOrderAddressesWrite);
        using var denied = await client.PostAsJsonAsync("/purchaseorders/addresses", Address());
        Assert.Equal(HttpStatusCode.Forbidden, denied.StatusCode);
        Assert.NotEmpty(logs.Messages);
        foreach (var message in logs.Messages)
        {
            Assert.DoesNotContain(privateOrigin, message, StringComparison.Ordinal);
            Assert.DoesNotContain(authority.Secret, message, StringComparison.Ordinal);
            Assert.DoesNotContain(authority.Workload, message, StringComparison.Ordinal);
        }
        Assert.Equal(0, authority.IamCalls);
        await AssertRowsAsync(app, 0);
    }

    private static WebApplicationFactory<Program> WithDeadline(ProcurementRuntimeFactory original, TimeSpan timeout)
        => original.WithWebHostBuilder(builder => builder.ConfigureServices(services =>
            services.AddHttpClient(LegacyServiceAccessTokenProvider.HttpClientName, client => client.Timeout = timeout)));

    private static object Address() => new { AddressLine1 = "Bangkok", CountryId = 66 };

    private static async Task AssertRowsAsync(WebApplicationFactory<Program> app, int expected)
    {
        await using var scope = app.Services.CreateAsyncScope();
        Assert.Equal(expected, await scope.ServiceProvider.GetRequiredService<PurchaseOrderDbContext>().Addresses.CountAsync());
        Assert.Empty(await scope.ServiceProvider.GetRequiredService<SupplierDbContext>().Addresses.AsNoTracking().ToArrayAsync());
    }

    private sealed class Authority(ProcurementRuntimeFixture fixture)
    {
        internal const string Employee = "employee:procurement-defaults";
        private const string ClientId = "legacy-procurement-defaults-fixture";
        internal string Secret { get; } = Convert.ToHexString(RandomNumberGenerator.GetBytes(32));
        private readonly string liveKey = Convert.ToHexString(RandomNumberGenerator.GetBytes(32));
        internal string Workload { get; } = fixture.SignedToken("service:" + ClientId, DateTime.UtcNow.AddMinutes(5), "iam.auth.check-permission");
        internal int AuthCalls { get; private set; }
        internal int IamCalls { get; private set; }

        internal IReadOnlyDictionary<string, string?> Settings(string? secret = null) => new Dictionary<string, string?>
        {
            ["ServiceAuthentication:ClientId"] = ClientId,
            ["ServiceAuthentication:ClientSecret"] = secret ?? Secret,
            ["Services:Auth:BaseUrl"] = "https://auth.procurement.invalid",
            ["Services:IAMService:BaseUrl"] = "https://iam.procurement.invalid",
            ["IAM:LivePermissionChecks:Credential"] = liveKey,
            ["Features:ResourceScopedAuthEnabled"] = "true",
        };

        internal ProcurementRuntimeFactory Factory()
        {
            var factory = fixture.CreateFactory(false);
            factory.WorkloadSettings = Settings();
            factory.AuthTransport = AuthAsync;
            factory.IamTransport = IamAsync;
            return factory;
        }

        internal void AssertRequest(HttpRequestMessage request)
        {
            Assert.Equal(HttpMethod.Post, request.Method);
            Assert.Equal("https://auth.procurement.invalid/auth/v1/service/login", request.RequestUri!.AbsoluteUri);
            Assert.Null(request.Headers.Authorization);
        }

        internal async Task<HttpResponseMessage> AuthAsync(HttpRequestMessage request, CancellationToken token)
        {
            AuthCalls++;
            AssertRequest(request);
            using var json = JsonDocument.Parse(await request.Content!.ReadAsStringAsync(token));
            Assert.Equal(new[] { "clientId", "clientSecret" }, json.RootElement.EnumerateObject().Select(row => row.Name).Order().ToArray());
            Assert.Equal(ClientId, json.RootElement.GetProperty("clientId").GetString());
            Assert.True(string.Equals(Secret, json.RootElement.GetProperty("clientSecret").GetString(), StringComparison.Ordinal), "Synthetic credential mismatch; value withheld.");
            return new(HttpStatusCode.OK) { Content = JsonContent.Create(new { accessToken = Workload, expiresIn = 300 }) };
        }

        internal Task<HttpResponseMessage> IamAsync(HttpRequestMessage request, CancellationToken token)
        {
            IamCalls++;
            Assert.Equal("https://iam.procurement.invalid/iam/v1/auth/check-permission", request.RequestUri!.AbsoluteUri);
            Assert.True(string.Equals(Workload, request.Headers.Authorization?.Parameter, StringComparison.Ordinal), "Synthetic bearer mismatch; value withheld.");
            Assert.True(string.Equals(liveKey, Assert.Single(request.Headers.GetValues("X-Maliev-IAM-Live-Check-Key")), StringComparison.Ordinal), "Synthetic live key mismatch; value withheld.");
            return Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK) { Content = JsonContent.Create(new { allowed = true }) });
        }
    }

    private sealed class CountingContent(byte[] bytes, TaskCompletionSource disposed) : ByteArrayContent(bytes)
    {
        internal int Disposals { get; private set; }
        protected override void Dispose(bool disposing)
        {
            base.Dispose(disposing);
            if (!disposing) return;
            Disposals++;
            disposed.TrySetResult();
        }
    }

    private sealed class CountingStream(byte[] bytes, TaskCompletionSource disposed) : MemoryStream(bytes)
    {
        internal int Disposals { get; private set; }
        protected override void Dispose(bool disposing)
        {
            base.Dispose(disposing);
            if (!disposing) return;
            Disposals++;
            disposed.TrySetResult();
        }
    }

    private sealed class DeferredContent(TaskCompletionSource entered, Task<Stream> stream) : HttpContent
    {
        protected override bool TryComputeLength(out long length) { length = 0; return false; }
        protected override Task SerializeToStreamAsync(Stream destination, TransportContext? context) => throw new InvalidOperationException("Controlled direct stream required.");
        protected override Task<Stream> CreateContentReadStreamAsync(CancellationToken cancellationToken)
        {
            entered.TrySetResult();
            return stream;
        }
    }

    private sealed class ProviderWarnings : ILoggerProvider
    {
        internal ConcurrentQueue<string> Messages { get; } = new();
        public ILogger CreateLogger(string categoryName) => new Capture(categoryName, Messages);
        public void Dispose() { }

        private sealed class Capture(string category, ConcurrentQueue<string> messages) : ILogger
        {
            public IDisposable? BeginScope<TState>(TState state) where TState : notnull => null;
            public bool IsEnabled(LogLevel level) => level >= LogLevel.Warning;
            public void Log<TState>(LogLevel level, EventId eventId, TState state, Exception? exception, Func<TState, Exception?, string> formatter)
            {
                if (IsEnabled(level) && category.EndsWith(nameof(LegacyServiceAccessTokenProvider), StringComparison.Ordinal))
                    messages.Enqueue(formatter(state, exception));
            }
        }
    }
}

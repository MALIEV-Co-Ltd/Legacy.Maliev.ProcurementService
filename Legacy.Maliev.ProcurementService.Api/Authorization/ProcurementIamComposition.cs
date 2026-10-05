using Maliev.Aspire.ServiceDefaults.IAM;
using Maliev.Aspire.ServiceDefaults.LegacyAuth;

namespace Legacy.Maliev.ProcurementService.Api.Authorization;

/// <summary>Normal live-IAM composition using the existing runtime workload exchange, never a local grant.</summary>
internal static class ProcurementIamComposition
{
    internal static void AddProcurementIamComposition(this IHostApplicationBuilder builder)
    {
        builder.AddLegacyAuthServiceTokenExchange();
        builder.Services.AddTransient<ProcurementWorkloadExchangeGuard>();
        builder.Services.AddHttpClient(LegacyServiceAccessTokenProvider.HttpClientName, client =>
        {
            client.BaseAddress = ResolveOrigin(builder.Configuration["Services:Auth:BaseUrl"]
                ?? builder.Configuration["Services:Auth"], builder.Environment, iam: false);
            client.Timeout = TimeSpan.FromSeconds(10);
        })
        .ConfigurePrimaryHttpMessageHandler(DisableRedirects)
        .RedactLoggedHeaders(["Authorization"])
        .AddHttpMessageHandler<ProcurementWorkloadExchangeGuard>()
        .ConfigureAdditionalHttpMessageHandlers((handlers, _) =>
        {
            // Local contract rejection is not a transient network failure. Keep it
            // outside inherited retry while preserving that policy for accepted requests.
            var guard = handlers.OfType<ProcurementWorkloadExchangeGuard>().Single();
            handlers.Remove(guard);
            handlers.Insert(0, guard);
        });

        builder.Services.AddScoped<IIamServiceClient, IamServiceClient>();
        builder.Services.AddHttpClient("IAMService", client =>
        {
            client.BaseAddress = ResolveOrigin(builder.Configuration["Services:IAMService:BaseUrl"]
                ?? builder.Configuration["Services:IAM:BaseUrl"] ?? builder.Configuration["Services:IAM"], builder.Environment, iam: true);
            client.Timeout = TimeSpan.FromSeconds(10);
        })
        .ConfigurePrimaryHttpMessageHandler(DisableRedirects)
        .RedactLoggedHeaders(["Authorization", "X-Maliev-IAM-Live-Check-Key"])
        .AddServiceDiscovery()
        .AddLegacyServiceAuthentication();
    }

    internal static Uri ResolveOrigin(string? configured, IHostEnvironment environment, bool iam)
    {
        // Existing Defaults IAM routing convention only; unresolved routing/credentials remain fail closed.
        if (configured is null && iam) return new Uri("https+http://IAMService");
        if (string.IsNullOrWhiteSpace(configured) || configured.Length > 2048 || configured.Any(char.IsWhiteSpace) || configured.Contains('\\')
            || !Uri.TryCreate(configured, UriKind.Absolute, out var uri)
            || string.IsNullOrWhiteSpace(uri.Host) || !string.IsNullOrEmpty(uri.UserInfo)
            || uri.AbsolutePath != "/" || !string.IsNullOrEmpty(uri.Query) || !string.IsNullOrEmpty(uri.Fragment))
            throw InvalidOrigin();
        var logicalIam = iam && uri.Scheme == "https+http" && uri.Port == -1
            && uri.Host is "iamservice" or "legacy-maliev-iam-service";
        var comparison = logicalIam ? StringComparison.OrdinalIgnoreCase : StringComparison.Ordinal;
        var authority = uri.GetLeftPart(UriPartial.Authority);
        if (!string.Equals(configured, authority, comparison) && !string.Equals(configured, authority + "/", comparison))
            throw InvalidOrigin();
        if (uri.Scheme == "https") return uri;
        if (logicalIam) return uri;
        if (uri.Scheme == "http" && (environment.IsDevelopment() || environment.IsEnvironment("Testing"))
            && uri.IsLoopback) return uri;
        throw InvalidOrigin();
    }

    private static void DisableRedirects(HttpMessageHandler handler, IServiceProvider _)
    {
        if (handler is SocketsHttpHandler sockets) sockets.AllowAutoRedirect = false;
        else if (handler is HttpClientHandler http) http.AllowAutoRedirect = false;
        else throw new InvalidOperationException("Procurement workload clients require a redirect-disabled primary handler.");
    }

    private static InvalidOperationException InvalidOrigin() => new("Procurement workload clients require an approved service origin.");
}

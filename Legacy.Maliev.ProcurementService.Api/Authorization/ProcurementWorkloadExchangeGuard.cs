namespace Legacy.Maliev.ProcurementService.Api.Authorization;

/// <summary>Bounds the shared provider's response-body read even when it performs its exchange with CancellationToken.None.</summary>
internal sealed class ProcurementWorkloadExchangeGuard(IConfiguration configuration, IHostEnvironment environment, TimeProvider clock) : DelegatingHandler
{
    protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        var clientId = configuration["ServiceAuthentication:ClientId"];
        var secret = configuration["ServiceAuthentication:ClientSecret"];
        if (string.IsNullOrWhiteSpace(clientId) || clientId.Length > 128 || clientId != clientId.Trim()
            || string.IsNullOrWhiteSpace(secret) || secret.Length is < 16 or > 1024)
            throw new HttpRequestException("Procurement workload exchange configuration was rejected.");
        var origin = ProcurementIamComposition.ResolveOrigin(configuration["Services:Auth:BaseUrl"]
            ?? configuration["Services:Auth"], environment, iam: false);
        if (request.Method != HttpMethod.Post || request.RequestUri != new Uri(origin, "/auth/v1/service/login")
            || request.Headers.Authorization is not null || request.Content is null)
            throw new HttpRequestException("Procurement workload exchange request was rejected.");

        using var deadline = new CancellationTokenSource(TimeSpan.FromSeconds(10), clock);
        using var linked = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken, deadline.Token);
        var response = await base.SendAsync(request, linked.Token);
        try
        {
            if (response.Content.Headers.ContentLength is > 32768) throw OversizedBody();
            var declaredLength = response.Content.Headers.ContentLength;
            await using var stream = await response.Content.ReadAsStreamAsync(linked.Token);
            using var content = new MemoryStream();
            var buffer = new byte[4096];
            while (true)
            {
                var remaining = 32769 - (int)content.Length;
                var read = await stream.ReadAsync(buffer.AsMemory(0, Math.Min(buffer.Length, remaining)), linked.Token);
                if (read == 0) break;
                if (content.Length + read > 32768) throw OversizedBody();
                content.Write(buffer, 0, read);
            }
            if (declaredLength is long declared && declared != content.Length)
                throw new HttpRequestException("Procurement workload exchange response had an inconsistent byte length.");
            var replacement = new ByteArrayContent(content.ToArray());
            foreach (var header in response.Content.Headers)
                if (!header.Key.Equals("Content-Length", StringComparison.OrdinalIgnoreCase))
                    replacement.Headers.TryAddWithoutValidation(header.Key, header.Value);
            response.Content.Dispose();
            response.Content = replacement;
            return response;
        }
        catch
        {
            response.Dispose();
            throw;
        }
    }

    private static HttpRequestException OversizedBody() => new("Procurement workload exchange response exceeded its byte budget.");
}

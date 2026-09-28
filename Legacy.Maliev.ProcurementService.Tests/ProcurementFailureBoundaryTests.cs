using System.Reflection;
using Legacy.Maliev.ProcurementService.Api.Controllers;
using Maliev.Aspire.ServiceDefaults.Middleware;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.Routing;
using Microsoft.AspNetCore.Routing.Patterns;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;
using Moq;

namespace Legacy.Maliev.ProcurementService.Tests;

public sealed class ProcurementFailureBoundaryTests
{
    [Theory]
    [InlineData(typeof(SuppliersController), "Suppliers", "{supplierId:int}", "/Suppliers/81927")]
    [InlineData(typeof(PurchaseOrdersController), "PurchaseOrders", "{purchaseOrderId:int}", "/PurchaseOrders/81927")]
    public async Task UnhandledRequest_UsesRedactedRouteAndTraceId(
        Type controllerType, string controllerRoute, string actionRoute, string requestPath)
    {
        Assert.Equal("[controller]", controllerType.GetCustomAttribute<RouteAttribute>()?.Template);
        Assert.Contains(controllerType.GetMethods(), method => method
            .GetCustomAttributes<HttpGetAttribute>()
            .Any(attribute => attribute.Template == actionRoute));

        var pattern = $"{controllerRoute}/{actionRoute}";
        var logger = new CapturingLogger<ExceptionHandlingMiddleware>();
        var environment = new Mock<IHostEnvironment>();
        environment.SetupGet(value => value.EnvironmentName).Returns("Production");
        environment.SetupGet(value => value.ApplicationName).Returns("Legacy.Maliev.ProcurementService.Api");
        var context = new DefaultHttpContext();
        context.Request.Method = "GET";
        context.Request.Path = requestPath;
        context.TraceIdentifier = "procurement-incident-123";
        context.Response.Body = new MemoryStream();
        context.SetEndpoint(new RouteEndpointBuilder(
            _ => Task.CompletedTask,
            RoutePatternFactory.Parse(pattern),
            0).Build());

        var middleware = new ExceptionHandlingMiddleware(
            _ => throw new InvalidOperationException("protected-supplier-or-order-detail"),
            logger, environment.Object);
        await middleware.InvokeAsync(context);

        var entry = Assert.Single(logger.Entries);
        Assert.Equal(LogLevel.Critical, entry.Level);
        Assert.Null(entry.Exception);
        Assert.Equal("UnhandledRequestFailure", entry.Values["EventName"]);
        Assert.Equal(pattern, entry.Values["Path"]);
        Assert.Equal("Legacy.Maliev.ProcurementService.Api", entry.Values["Service"]);
        Assert.DoesNotContain(requestPath, entry.Message, StringComparison.Ordinal);
        Assert.DoesNotContain("protected-supplier-or-order-detail", entry.Message, StringComparison.Ordinal);
        context.Response.Body.Position = 0;
        using var reader = new StreamReader(context.Response.Body);
        var response = await reader.ReadToEndAsync();
        Assert.Contains(context.TraceIdentifier, response, StringComparison.Ordinal);
        Assert.DoesNotContain("protected-supplier-or-order-detail", response, StringComparison.Ordinal);
    }

    [Theory]
    [InlineData("Suppliers/{supplierId:int}", "/Suppliers/81927")]
    [InlineData("PurchaseOrders/{purchaseOrderId:int}", "/PurchaseOrders/81927")]
    public async Task CorrelationScope_ContainsTemplateButNoLiteralProcurementPath(
        string pattern, string requestPath)
    {
        var logger = new CapturingLogger<CorrelationIdMiddleware>();
        var context = new DefaultHttpContext();
        context.Request.Method = "GET";
        context.Request.Path = requestPath;
        context.Request.Headers["X-Correlation-ID"] = "procurement-incident-123";
        context.SetEndpoint(new RouteEndpointBuilder(
            _ => Task.CompletedTask,
            RoutePatternFactory.Parse(pattern),
            0).Build());

        await new CorrelationIdMiddleware(_ => Task.CompletedTask, logger).InvokeAsync(context);

        Assert.Equal("procurement-incident-123", context.Response.Headers["X-Correlation-ID"].ToString());
        Assert.Equal("procurement-incident-123", logger.Scope["CorrelationId"]);
        Assert.Equal(pattern, logger.Scope["RouteTemplate"]);
        Assert.DoesNotContain("RequestPath", logger.Scope.Keys);
        Assert.DoesNotContain(requestPath, string.Join(' ', logger.Scope.Values), StringComparison.Ordinal);
    }

    private sealed class CapturingLogger<T> : ILogger<T>
    {
        public List<LogEntry> Entries { get; } = [];
        public IReadOnlyDictionary<string, object?> Scope { get; private set; } = new Dictionary<string, object?>();

        public IDisposable BeginScope<TState>(TState state) where TState : notnull
        {
            Scope = state is IEnumerable<KeyValuePair<string, object?>> values
                ? values.ToDictionary(item => item.Key, item => item.Value)
                : throw new InvalidOperationException("Correlation scope is not structured.");
            return NoopScope.Instance;
        }

        public bool IsEnabled(LogLevel logLevel) => true;

        public void Log<TState>(LogLevel logLevel, EventId eventId, TState state,
            Exception? exception, Func<TState, Exception?, string> formatter)
        {
            var values = state is IEnumerable<KeyValuePair<string, object?>> structured
                ? structured.ToDictionary(item => item.Key, item => item.Value)
                : new Dictionary<string, object?>();
            Entries.Add(new LogEntry(logLevel, formatter(state, exception), values, exception));
        }
    }

    private sealed record LogEntry(LogLevel Level, string Message,
        IReadOnlyDictionary<string, object?> Values, Exception? Exception);

    private sealed class NoopScope : IDisposable
    {
        public static NoopScope Instance { get; } = new();
        public void Dispose() { }
    }
}

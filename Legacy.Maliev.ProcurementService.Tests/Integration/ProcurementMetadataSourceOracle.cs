using System.Net;
using System.Reflection;
using System.Text;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.Mvc.ApplicationParts;
using Microsoft.AspNetCore.Mvc.Controllers;
using Microsoft.AspNetCore.TestHost;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using Newtonsoft.Json;
using Newtonsoft.Json.Serialization;
using OriginalSupplier = Maliev.SupplierService.Data.Database.SupplierContext.Supplier;
using OriginalSupplierAddress = Maliev.SupplierService.Data.Database.SupplierContext.Address;
using OriginalOrderAddress = Maliev.PurchaseOrderService.Data.Database.PurchaseOrderContext.Address;
using OriginalFile = Maliev.PurchaseOrderService.Data.Database.PurchaseOrderContext.PurchaseOrderFile;

namespace Legacy.Maliev.ProcurementService.Tests.Integration;

// Public-source protocol reconstruction on the supported .NET 10 MVC pipeline,
// not evidence of the original deployed .NET 8/Newtonsoft binary.
// Stock formatter/provider/pool Git blobs are byte-identical in aspnetcore v8.0.3
// and v10.0.12, respectively:
// 81e33dc6092be72906e491953c0051d2a8516a47
// 2f1cfd6f20c6f9c17219f537e613c07d36af3ac1
// 8d0918986e4f96a9168c98dedcd69b2cc50fa920
// No EF/SDK executes here.
internal sealed class ProcurementMetadataSourceOracle : IDisposable
{
    private readonly IHost host;
    public SourceAdmissionState State { get; } = new();
    public HttpClient Client { get; }

    public ProcurementMetadataSourceOracle()
    {
        host = new HostBuilder().ConfigureWebHost(builder => builder
            .UseTestServer()
            .ConfigureServices(services =>
            {
                services.AddSingleton(State);
                services.AddControllers()
                    .AddApplicationPart(typeof(ProcurementOriginalMetadataController).Assembly)
                    .ConfigureApplicationPartManager(manager =>
                    {
                        manager.FeatureProviders.Clear();
                        manager.FeatureProviders.Add(new OriginalControllerFeature());
                    })
                    .AddNewtonsoftJson(options =>
                    {
                        // Defaults, including MaxDepth32, TypeNameNone and metadata
                        // Default, come from the stock MVC provider, not bare JsonConvert.
                        options.SerializerSettings.NullValueHandling = NullValueHandling.Ignore;
                        options.SerializerSettings.ReferenceLoopHandling = ReferenceLoopHandling.Ignore;
                        options.SerializerSettings.SerializationBinder = State;
                    });
            })
            .Configure(app =>
            {
                app.Use(async (context, next) =>
                {
                    try { await next(context); }
                    catch (Exception exception)
                    {
                        // Test transport captures unexpected formatter exceptions as
                        // 500 while retaining their exact type. No blanket 400 conversion.
                        State.Unexpected = exception.GetType();
                        context.Response.StatusCode = (int)HttpStatusCode.InternalServerError;
                    }
                });
                app.UseRouting();
                app.UseEndpoints(endpoints => endpoints.MapControllers());
            })).Build();
        try
        {
            host.Start();
            Client = host.GetTestClient();
        }
        catch (Exception startupFailure)
        {
            try { host.Dispose(); }
            catch (Exception cleanupFailure)
            {
                throw new AggregateException("Source oracle startup and cleanup failed.", startupFailure, cleanupFailure);
            }
            throw;
        }
    }

    public async Task<HttpResponseMessage> SendAsync(string contract, string body, Encoding? encoding = null)
    {
        using var content = new StringContent(body, encoding ?? Encoding.UTF8, "application/json");
        return await Client.PostAsync("/original-metadata/" + contract, content);
    }

    public void Dispose()
    {
        Client.Dispose();
        host.Dispose();
    }

    private sealed class OriginalControllerFeature : IApplicationFeatureProvider<ControllerFeature>
    {
        public void PopulateFeature(IEnumerable<ApplicationPart> parts, ControllerFeature feature) =>
            feature.Controllers.Add(typeof(ProcurementOriginalMetadataController).GetTypeInfo());
    }
}

public sealed class SourceAdmissionState : ISerializationBinder
{
    public int Entries { get; set; }
    public int BinderCalls { get; private set; }
    public Type? Unexpected { get; set; }
    public object? Captured { get; set; }

    public Type BindToType(string? assemblyName, string typeName)
    {
        BinderCalls++;
        throw new InvalidOperationException("TypeNameHandling.None must not invoke a binder.");
    }

    public void BindToName(Type serializedType, out string? assemblyName, out string? typeName)
    {
        assemblyName = null;
        typeName = null;
    }
}

[ApiController]
[Route("original-metadata")]
public sealed class ProcurementOriginalMetadataController : ControllerBase
{
    private readonly SourceAdmissionState state;
    public ProcurementOriginalMetadataController(SourceAdmissionState state) => this.state = state;

    [HttpPost("supplier")]
    public IActionResult Supplier(OriginalSupplier item) => Enter(item);
    [HttpPost("supplier-address")]
    public IActionResult SupplierAddress(OriginalSupplierAddress item) => Enter(item);
    [HttpPost("order-address")]
    public IActionResult OrderAddress(OriginalOrderAddress item) => Enter(item);
    [HttpPost("file")]
    public IActionResult FileMetadata(OriginalFile item) => Enter(item);

    private IActionResult Enter(object? item)
    {
        if (item is null) return BadRequest();
        state.Entries++;
        state.Captured = item;
        return Ok(new { Entered = true });
    }
}

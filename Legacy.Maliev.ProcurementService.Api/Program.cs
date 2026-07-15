using System.Text.Json.Serialization;
using Legacy.Maliev.ProcurementService.Application.Interfaces;
using Legacy.Maliev.ProcurementService.Application.Services;
using Legacy.Maliev.ProcurementService.Data;
using Maliev.Aspire.ServiceDefaults;

var builder = WebApplication.CreateBuilder(args);

builder.AddServiceDefaults();
builder.AddDefaultApiVersioning();
builder.AddPostgresDbContext<SupplierDbContext>(connectionName: "SupplierDbContext");
builder.AddPostgresDbContext<PurchaseOrderDbContext>(connectionName: "PurchaseOrderDbContext");
builder.AddStandardCache("legacy:procurement:");
builder.AddStandardCors();
builder.AddJwtAuthentication();
builder.AddStandardMiddleware(options => options.EnableRequestLogging = true);
builder.AddStandardOpenApi(
    title: "Legacy MALIEV Procurement Service API",
    description: "Temporary .NET 10 compatibility service preserving Supplier and PurchaseOrder contracts across two isolated databases.");

builder.Services.AddControllers().AddJsonOptions(options =>
{
    options.JsonSerializerOptions.DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull;
    options.JsonSerializerOptions.PropertyNamingPolicy = null;
    options.JsonSerializerOptions.DictionaryKeyPolicy = null;
});
builder.Services.AddSingleton(TimeProvider.System);
builder.Services.AddScoped<ISupplierRepository, SupplierRepository>();
builder.Services.AddScoped<IPurchaseOrderRepository, PurchaseOrderRepository>();
builder.Services.AddScoped<DistributedProcurementCache>();
builder.Services.AddScoped<IProcurementCache>(provider => provider.GetRequiredService<DistributedProcurementCache>());
builder.Services.AddScoped<IIdempotencyStore>(provider => provider.GetRequiredService<DistributedProcurementCache>());
builder.Services.AddScoped<IProcurementService, ProcurementApplicationService>();

var app = builder.Build();

app.UseStandardMiddleware();
app.UseCors();
app.UseAuthentication();
app.UseAuthorization();
app.MapDefaultEndpoints("procurement");
app.MapControllers();
app.MapApiDocumentation(servicePrefix: "procurement");

await app.RunAsync();

/// <summary>Legacy Procurement Service entry point.</summary>
public partial class Program;

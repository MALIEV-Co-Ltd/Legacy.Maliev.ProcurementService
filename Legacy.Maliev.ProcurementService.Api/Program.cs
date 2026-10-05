using System.Text.Json.Serialization;
using Legacy.Maliev.ProcurementService.Api.Authorization;
using Legacy.Maliev.ProcurementService.Application.Interfaces;
using Legacy.Maliev.ProcurementService.Application.Services;
using Legacy.Maliev.ProcurementService.Data;
using Maliev.Aspire.ServiceDefaults;
using Microsoft.EntityFrameworkCore.Diagnostics;

var builder = WebApplication.CreateBuilder(args);

builder.AddServiceDefaults();
builder.AddDefaultApiVersioning();
// These EF diagnostics embed exception text/stacks before the formatter can redact them.
// Standard middleware retains the actionable correlated, type-only critical failure event.
builder.AddPostgresDbContext<SupplierDbContext>(connectionName: "SupplierDbContext", configureOptions: (_, options) =>
    options.ConfigureWarnings(warnings => warnings.Ignore(
        CoreEventId.QueryIterationFailed, CoreEventId.SaveChangesFailed, CoreEventId.ExecutionStrategyRetrying)));
builder.AddPostgresDbContext<PurchaseOrderDbContext>(connectionName: "PurchaseOrderDbContext", configureOptions: (_, options) =>
    options.ConfigureWarnings(warnings => warnings.Ignore(
        CoreEventId.QueryIterationFailed, CoreEventId.SaveChangesFailed, CoreEventId.ExecutionStrategyRetrying)));
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
builder.Services.ConfigureHttpJsonOptions(options =>
{
    options.SerializerOptions.DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull;
    options.SerializerOptions.PropertyNamingPolicy = null;
    options.SerializerOptions.DictionaryKeyPolicy = null;
});
// Activate this API assembly's XML documentation support for the published contract.
builder.Services.AddOpenApi("v1");
builder.Services.AddSingleton(TimeProvider.System);
builder.AddProcurementIamComposition();
builder.Services.AddScoped<ISupplierRepository, SupplierRepository>();
builder.Services.AddScoped<IPurchaseOrderRepository, PurchaseOrderRepository>();
builder.Services.AddScoped<DistributedProcurementCache>();
builder.Services.AddScoped<IProcurementCache>(provider => provider.GetRequiredService<DistributedProcurementCache>());
builder.Services.AddScoped<IIdempotencyStore>(provider => provider.GetRequiredService<DistributedProcurementCache>());
builder.Services.AddScoped<IProcurementService, ProcurementApplicationService>();
builder.Services.AddScoped<IDurableProcurementCreates, DurableProcurementCreates>();
builder.Services.AddScoped<Legacy.Maliev.ProcurementService.Api.DurableCreateEndpoint>();

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

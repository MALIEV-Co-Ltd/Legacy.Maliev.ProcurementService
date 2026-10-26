using System.Text;
using System.Text.Json;
using Legacy.Maliev.ProcurementService.Application.Interfaces;
using Legacy.Maliev.ProcurementService.Application.Models;
using Microsoft.AspNetCore.Mvc;
using Microsoft.Extensions.Options;

namespace Legacy.Maliev.ProcurementService.Api;

/// <summary>Separately default-off keyed child handling; authorization still runs on the owning controller.</summary>
public sealed class DurableChildCreateEndpoint(IConfiguration configuration, IDurableProcurementChildCreates creates, DurableCreateEndpoint binding, IOptions<JsonOptions> json)
{
    /// <summary>Whether the separately reviewed child receipt rollout is enabled.</summary>
    public bool Enabled => configuration.GetValue<bool>("Procurement:DurableChildCreates:Enabled");
    /// <summary>Captures an item's exact public creation response in its owning transaction.</summary>
    public async Task<ActionResult> ItemAsync(ControllerBase controller, UpsertOrderItemRequest request, CancellationToken token)
    {
        if (!binding.TryBinding(controller, request, 3, out var receipt)) return controller.BadRequest();
        var result = await creates.CreateItemAsync(request, receipt!, value => JsonSerializer.SerializeToUtf8Bytes(value, json.Value.JsonSerializerOptions), token);
        return Map(controller, result, "GetOrderItem", "orderItemId");
    }
    /// <summary>Binds effective decoded query strings and the parent path without trimming.</summary>
    public async Task<ActionResult> FileAsync(ControllerBase controller, int parent, string bucket, string objectName, CancellationToken token)
    {
        if (!binding.TryBinding(controller, new FilePayload(parent, bucket, objectName), 4, out var receipt)) return controller.BadRequest();
        var result = await creates.CreateFileAsync(parent, bucket, objectName, receipt!, value => JsonSerializer.SerializeToUtf8Bytes(value, json.Value.JsonSerializerOptions), token);
        return Map(controller, result, "GetPurchaseOrderFile", "id");
    }
    private sealed record FilePayload(int PurchaseOrderId, string Bucket, string ObjectName);
    private static ActionResult Map(ControllerBase controller, DurableCreateResult result, string route, string idName)
    {
        controller.Response.Headers.CacheControl = "no-store";
        if (result.Status == DurableCreateStatus.Conflict) return controller.Conflict();
        if (result.Status == DurableCreateStatus.NotFound) return controller.NotFound();
        if (result.Status != DurableCreateStatus.CreatedOrReplayed || result.Response is null) return controller.StatusCode(StatusCodes.Status503ServiceUnavailable);
        controller.Response.Headers.Location = controller.Url.Link(route, new Dictionary<string, object> { [idName] = result.Response.EntityId });
        return new ContentResult { StatusCode = StatusCodes.Status201Created, ContentType = "application/json; charset=utf-8", Content = Encoding.UTF8.GetString(result.Response.Body) };
    }
}
using Legacy.Maliev.ProcurementService.Api.Authorization;
using Legacy.Maliev.ProcurementService.Application.Interfaces;
using Legacy.Maliev.ProcurementService.Application.Models;
using Maliev.Aspire.ServiceDefaults.Authorization;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;

namespace Legacy.Maliev.ProcurementService.Api.Controllers;

/// <summary>Legacy purchase-order routes.</summary>
/// <param name="service">Procurement application service.</param>
/// <param name="idempotency">Create-response idempotency store.</param>
[ApiController]
[Route("[controller]")]
[Authorize]
public sealed class PurchaseOrdersController(IProcurementService service, IIdempotencyStore idempotency) : ControllerBase
{
    /// <summary>Creates a purchase order.</summary>
    [HttpPost]
    [RequirePermission(ProcurementPermissions.PurchaseOrdersCreate, RequireLiveCheck = true, IsCritical = true)]
    public async Task<IActionResult> CreatePurchaseOrderAsync(UpsertPurchaseOrderRequest item, [FromHeader(Name = "Idempotency-Key")] string? idempotencyKey, CancellationToken cancellationToken)
    {
        var order = await IdempotentCreates.GetOrCreateAsync(idempotency, "purchase-order", idempotencyKey, () => service.CreatePurchaseOrderAsync(item, cancellationToken), cancellationToken);
        return CreatedAtRoute("GetPurchaseOrder", new { purchaseOrderId = order.Id }, order);
    }

    /// <summary>Deletes a purchase order.</summary>
    [HttpDelete("{purchaseOrderId:int}")]
    [RequirePermission(ProcurementPermissions.PurchaseOrdersDelete, ResourcePathTemplate = "/purchaseorders/{purchaseOrderId}", RequireLiveCheck = true, IsCritical = true)]
    public async Task<IActionResult> DeletePurchaseOrderAsync(int purchaseOrderId, CancellationToken cancellationToken) =>
        await service.DeletePurchaseOrderAsync(purchaseOrderId, cancellationToken) ? NoContent() : NotFound();

    /// <summary>Gets a purchase-order page.</summary>
    [HttpGet]
    [RequirePermission(ProcurementPermissions.PurchaseOrdersRead)]
    public async Task<ActionResult<PaginatedResponse<PurchaseOrderResponse>>> GetPaginatedAsync(
        [FromQuery] PurchaseOrderSortType? sort, [FromQuery] string? search, [FromQuery] int? index, [FromQuery] int? size, CancellationToken cancellationToken)
    {
        var orders = await service.GetPurchaseOrdersAsync(sort, search, index, size, cancellationToken);
        return orders is null ? NotFound() : orders;
    }

    /// <summary>Gets one purchase order.</summary>
    [HttpGet("{purchaseOrderId:int}", Name = "GetPurchaseOrder")]
    [RequirePermission(ProcurementPermissions.PurchaseOrdersRead, ResourcePathTemplate = "/purchaseorders/{purchaseOrderId}")]
    public async Task<ActionResult<PurchaseOrderResponse>> GetPurchaseOrderAsync(int purchaseOrderId, CancellationToken cancellationToken)
    {
        var order = await service.GetPurchaseOrderAsync(purchaseOrderId, cancellationToken);
        return order is null ? NotFound() : order;
    }

    /// <summary>Updates a purchase order with optional optimistic concurrency.</summary>
    [HttpPut("{purchaseOrderId:int}")]
    [RequirePermission(ProcurementPermissions.PurchaseOrdersUpdate, ResourcePathTemplate = "/purchaseorders/{purchaseOrderId}", RequireLiveCheck = true, IsCritical = true)]
    public async Task<ActionResult> UpdatePurchaseOrderAsync(int purchaseOrderId, UpsertPurchaseOrderRequest item, [FromHeader(Name = "X-Expected-Modified-Date")] DateTimeOffset? expectedModifiedDate, CancellationToken cancellationToken) =>
        (await service.UpdatePurchaseOrderAsync(purchaseOrderId, item, expectedModifiedDate, cancellationToken)) switch
        {
            UpdateResult.Updated => NoContent(),
            UpdateResult.Conflict => Conflict("Purchase order was modified by another request."),
            _ => NotFound(),
        };
}

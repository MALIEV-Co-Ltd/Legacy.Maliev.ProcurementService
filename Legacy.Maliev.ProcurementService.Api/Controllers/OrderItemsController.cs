using Legacy.Maliev.ProcurementService.Api.Authorization;
using Legacy.Maliev.ProcurementService.Application.Interfaces;
using Legacy.Maliev.ProcurementService.Application.Models;
using Maliev.Aspire.ServiceDefaults.Authorization;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;

namespace Legacy.Maliev.ProcurementService.Api.Controllers;

/// <summary>Legacy purchase-order line-item routes.</summary>
/// <param name="service">Procurement application service.</param>
[ApiController]
[Route("purchaseorders/orderitems")]
[Authorize]
public sealed class OrderItemsController(IProcurementService service) : ControllerBase
{
    /// <summary>Creates an order item.</summary>
    [HttpPost]
    [RequirePermission(ProcurementPermissions.OrderItemsWrite, RequireLiveCheck = true)]
    public async Task<ActionResult> CreateOrderItemAsync(UpsertOrderItemRequest item, CancellationToken cancellationToken)
    {
        var created = await service.CreateOrderItemAsync(item, cancellationToken); return CreatedAtRoute("GetOrderItem", new { orderItemId = created.Id }, created);
    }
    /// <summary>Deletes an order item.</summary>
    [HttpDelete("{orderItemId:int}")]
    [RequirePermission(ProcurementPermissions.OrderItemsDelete, RequireLiveCheck = true)]
    public async Task<ActionResult> DeleteOrderItemAsync(int orderItemId, CancellationToken cancellationToken) => await service.DeleteOrderItemAsync(orderItemId, cancellationToken) ? NoContent() : NotFound();
    /// <summary>Gets one order item.</summary>
    [HttpGet("{orderItemId:int}", Name = "GetOrderItem")]
    [RequirePermission(ProcurementPermissions.OrderItemsRead, RequireLiveCheck = true)]
    public async Task<ActionResult<OrderItemResponse>> GetOrderItemAsync(int orderItemId, CancellationToken cancellationToken)
    {
        var item = await service.GetOrderItemAsync(orderItemId, cancellationToken); return item is null ? NotFound() : item;
    }
    /// <summary>Gets items owned by a purchase order.</summary>
    [HttpGet("/purchaseorders/{purchaseOrderId:int}/orderitems")]
    [RequirePermission(ProcurementPermissions.OrderItemsRead, ResourcePathTemplate = "/purchaseorders/{purchaseOrderId}", RequireLiveCheck = true)]
    public async Task<ActionResult<IReadOnlyList<OrderItemResponse>>> GetOrderItemsAsync(int purchaseOrderId, CancellationToken cancellationToken)
    {
        if (purchaseOrderId == 0) return BadRequest("Purchase order id is required"); var items = await service.GetOrderItemsAsync(purchaseOrderId, cancellationToken); return items.Count == 0 ? NotFound() : Ok(items);
    }
    /// <summary>Updates an order item with optional optimistic concurrency.</summary>
    [HttpPut("{orderItemId:int}")]
    [RequirePermission(ProcurementPermissions.OrderItemsWrite, RequireLiveCheck = true)]
    public async Task<ActionResult> UpdateOrderItemAsync(int orderItemId, UpsertOrderItemRequest item, [FromHeader(Name = "X-Expected-Modified-Date")] DateTimeOffset? expectedModifiedDate, CancellationToken cancellationToken) =>
        (await service.UpdateOrderItemAsync(orderItemId, item, expectedModifiedDate, cancellationToken)) switch { UpdateResult.Updated => NoContent(), UpdateResult.Conflict => Conflict("Order item was modified by another request."), _ => NotFound() };
}

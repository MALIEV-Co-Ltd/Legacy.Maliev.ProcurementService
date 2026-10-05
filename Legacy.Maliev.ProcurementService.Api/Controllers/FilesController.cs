using Legacy.Maliev.ProcurementService.Api.Authorization;
using Legacy.Maliev.ProcurementService.Application.Interfaces;
using Legacy.Maliev.ProcurementService.Application.Models;
using Maliev.Aspire.ServiceDefaults.Authorization;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;

namespace Legacy.Maliev.ProcurementService.Api.Controllers;

/// <summary>Legacy purchase-order GCS metadata routes.</summary>
/// <param name="service">Procurement application service.</param>
[ApiController]
[Route("purchaseorders/files")]
[Authorize]
public sealed class FilesController(IProcurementService service) : ControllerBase
{
    /// <summary>Creates purchase-order file metadata.</summary>
    /// <param name="purchaseOrderId">The purchase order that owns the metadata.</param>
    /// <param name="bucket" example="purchase-order-documents">The existing storage bucket name.</param>
    /// <param name="objectName" example="orders/purchase-order.pdf">The existing object name, decoded from its query value.</param>
    /// <param name="cancellationToken">Request cancellation.</param>
    /// <response code="201">The retained file metadata.</response>
    /// <response code="400">Bucket or object name is blank.</response>
    /// <response code="404">The purchase order does not exist.</response>
    [HttpPost("/purchaseorders/{purchaseOrderId:int}/files")]
    [ProducesResponseType<PurchaseOrderFileResponse>(StatusCodes.Status201Created)]
    [ProducesResponseType(StatusCodes.Status400BadRequest)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    [RequirePermission(ProcurementPermissions.FilesWrite, ResourcePathTemplate = "/purchaseorders/{purchaseOrderId}", RequireLiveCheck = true)]
    public async Task<ActionResult> CreatePurchaseOrderFileEntryAsync(int purchaseOrderId, [FromQuery] string bucket, [FromQuery] string objectName, CancellationToken cancellationToken)
    {
        if (string.IsNullOrWhiteSpace(bucket) || string.IsNullOrWhiteSpace(objectName)) return BadRequest(); var file = await service.CreatePurchaseOrderFileAsync(purchaseOrderId, bucket, objectName, cancellationToken); return file is null ? NotFound() : CreatedAtRoute("GetPurchaseOrderFile", new { id = file.Id }, file);
    }
    /// <summary>Deletes purchase-order file metadata.</summary>
    [HttpDelete("{id:int}")]
    [RequirePermission(ProcurementPermissions.FilesDelete, RequireLiveCheck = true)]
    public async Task<ActionResult> DeletePurchaseOrderFileAsync(int id, CancellationToken cancellationToken) => await service.DeletePurchaseOrderFileAsync(id, cancellationToken) ? NoContent() : NotFound();
    /// <summary>Gets one purchase-order file metadata row.</summary>
    [HttpGet("{id:int}", Name = "GetPurchaseOrderFile")]
    [RequirePermission(ProcurementPermissions.FilesRead)]
    public async Task<ActionResult<PurchaseOrderFileResponse>> GetPurchaseOrderFileAsync(int id, CancellationToken cancellationToken)
    {
        var file = await service.GetPurchaseOrderFileAsync(id, cancellationToken); return file is null ? NotFound() : file;
    }
    /// <summary>Gets file metadata rows owned by a purchase order.</summary>
    [HttpGet("/purchaseorders/{purchaseOrderId:int}/files")]
    [RequirePermission(ProcurementPermissions.FilesRead, ResourcePathTemplate = "/purchaseorders/{purchaseOrderId}")]
    public async Task<ActionResult<IReadOnlyList<PurchaseOrderFileResponse>>> GetPurchaseOrderFilesAsync(int purchaseOrderId, CancellationToken cancellationToken)
    {
        var files = await service.GetPurchaseOrderFilesAsync(purchaseOrderId, cancellationToken); return files.Count == 0 ? NotFound() : Ok(files);
    }
    /// <summary>Updates purchase-order file metadata.</summary>
    [HttpPut("{id:int}")]
    [RequirePermission(ProcurementPermissions.FilesWrite, RequireLiveCheck = true)]
    public async Task<ActionResult> UpdatePurchaseOrderFileAsync(int id, UpsertPurchaseOrderFileRequest item, CancellationToken cancellationToken)
    {
        if (string.IsNullOrWhiteSpace(item.Bucket) || string.IsNullOrWhiteSpace(item.ObjectName)) return BadRequest(); return await service.UpdatePurchaseOrderFileAsync(id, item, cancellationToken) ? NoContent() : NotFound();
    }
}

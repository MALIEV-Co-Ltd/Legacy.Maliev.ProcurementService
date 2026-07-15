using Legacy.Maliev.ProcurementService.Api.Authorization;
using Legacy.Maliev.ProcurementService.Application.Interfaces;
using Legacy.Maliev.ProcurementService.Application.Models;
using Maliev.Aspire.ServiceDefaults.Authorization;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;

namespace Legacy.Maliev.ProcurementService.Api.Controllers;

/// <summary>Legacy supplier master-data routes.</summary>
/// <param name="service">Procurement application service.</param>
/// <param name="idempotency">Create-response idempotency store.</param>
[ApiController]
[Route("[controller]")]
[Authorize]
public sealed class SuppliersController(IProcurementService service, IIdempotencyStore idempotency) : ControllerBase
{
    /// <summary>Creates a supplier.</summary>
    [HttpPost]
    [RequirePermission(ProcurementPermissions.SuppliersCreate)]
    public async Task<IActionResult> CreateSupplierAsync(UpsertSupplierRequest item, [FromHeader(Name = "Idempotency-Key")] string? idempotencyKey, CancellationToken cancellationToken)
    {
        var supplier = await IdempotentCreates.GetOrCreateAsync(idempotency, "supplier", idempotencyKey, () => service.CreateSupplierAsync(item, cancellationToken), cancellationToken);
        return CreatedAtRoute("GetSupplier", new { supplierId = supplier.Id }, supplier);
    }

    /// <summary>Deletes a supplier.</summary>
    [HttpDelete("{supplierId:int}")]
    [RequirePermission(ProcurementPermissions.SuppliersDelete, ResourcePathTemplate = "/suppliers/{supplierId}", RequireLiveCheck = true, IsCritical = true)]
    public async Task<ActionResult> DeleteSupplierAsync(int supplierId, CancellationToken cancellationToken) =>
        await service.DeleteSupplierAsync(supplierId, cancellationToken) ? NoContent() : NotFound();

    /// <summary>Gets a supplier page.</summary>
    [HttpGet]
    [RequirePermission(ProcurementPermissions.SuppliersRead)]
    public async Task<ActionResult<PaginatedResponse<SupplierResponse>>> GetPaginatedSuppliersAsync(
        [FromQuery] SupplierSortType? sort, [FromQuery] string? search, [FromQuery] int? index, [FromQuery] int? size, CancellationToken cancellationToken)
    {
        var suppliers = await service.GetSuppliersAsync(sort, search, index, size, cancellationToken);
        return suppliers is null ? NotFound() : suppliers;
    }

    /// <summary>Gets one supplier.</summary>
    [HttpGet("{supplierId:int}", Name = "GetSupplier")]
    [RequirePermission(ProcurementPermissions.SuppliersRead, ResourcePathTemplate = "/suppliers/{supplierId}")]
    public async Task<ActionResult<SupplierResponse>> GetSupplierAsync(int supplierId, CancellationToken cancellationToken)
    {
        var supplier = await service.GetSupplierAsync(supplierId, cancellationToken);
        return supplier is null ? NotFound() : supplier;
    }

    /// <summary>Updates a supplier.</summary>
    [HttpPut("{supplierId:int}")]
    [RequirePermission(ProcurementPermissions.SuppliersUpdate, ResourcePathTemplate = "/suppliers/{supplierId}")]
    public async Task<ActionResult> UpdateSupplierAsync(int supplierId, UpsertSupplierRequest item, CancellationToken cancellationToken) =>
        await service.UpdateSupplierAsync(supplierId, item, cancellationToken) ? NoContent() : NotFound();
}

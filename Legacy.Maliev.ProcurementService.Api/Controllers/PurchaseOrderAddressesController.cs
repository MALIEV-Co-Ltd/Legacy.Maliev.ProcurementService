using Legacy.Maliev.ProcurementService.Api.Authorization;
using Legacy.Maliev.ProcurementService.Application.Interfaces;
using Legacy.Maliev.ProcurementService.Application.Models;
using Maliev.Aspire.ServiceDefaults.Authorization;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;

namespace Legacy.Maliev.ProcurementService.Api.Controllers;

/// <summary>Legacy PurchaseOrder-database address routes.</summary>
/// <param name="service">Procurement application service.</param>
[ApiController]
[Route("purchaseorders/addresses")]
[Authorize]
public sealed class PurchaseOrderAddressesController(IProcurementService service) : ControllerBase
{
    /// <summary>Creates a purchase-order address.</summary>
    [HttpPost]
    [RequirePermission(ProcurementPermissions.PurchaseOrderAddressesWrite, RequireLiveCheck = true)]
    public async Task<ActionResult> CreateAddressAsync(UpsertPurchaseOrderAddressRequest item, CancellationToken cancellationToken)
    {
        if (string.IsNullOrWhiteSpace(item.AddressLine1)) return BadRequest();
        var address = await service.CreatePurchaseOrderAddressAsync(item, cancellationToken);
        return CreatedAtRoute("GetPurchaseOrderAddress", new { addressId = address.Id }, address);
    }
    /// <summary>Deletes a purchase-order address.</summary>
    [HttpDelete("{addressId:int}")]
    [RequirePermission(ProcurementPermissions.PurchaseOrderAddressesDelete, RequireLiveCheck = true)]
    public async Task<ActionResult> DeleteAddressAsync(int addressId, CancellationToken cancellationToken) => await service.DeletePurchaseOrderAddressAsync(addressId, cancellationToken) ? NoContent() : NotFound();
    /// <summary>Gets one purchase-order address.</summary>
    [HttpGet("{addressId:int}", Name = "GetPurchaseOrderAddress")]
    [RequirePermission(ProcurementPermissions.PurchaseOrderAddressesRead)]
    public async Task<ActionResult<PurchaseOrderAddressResponse>> GetAddressAsync(int addressId, CancellationToken cancellationToken)
    {
        var address = await service.GetPurchaseOrderAddressAsync(addressId, cancellationToken); return address is null ? NotFound() : address;
    }
    /// <summary>Gets all purchase-order addresses.</summary>
    [HttpGet]
    [RequirePermission(ProcurementPermissions.PurchaseOrderAddressesRead)]
    public async Task<ActionResult<IReadOnlyList<PurchaseOrderAddressResponse>>> GetAddressesAsync(CancellationToken cancellationToken)
    {
        var addresses = await service.GetPurchaseOrderAddressesAsync(cancellationToken); return addresses.Count == 0 ? NotFound() : Ok(addresses);
    }
    /// <summary>Updates a purchase-order address.</summary>
    [HttpPut("{addressId:int}")]
    [RequirePermission(ProcurementPermissions.PurchaseOrderAddressesWrite, RequireLiveCheck = true)]
    public async Task<ActionResult> UpdateAddressAsync(int addressId, UpsertPurchaseOrderAddressRequest item, CancellationToken cancellationToken)
    {
        if (string.IsNullOrWhiteSpace(item.AddressLine1)) return BadRequest(); return await service.UpdatePurchaseOrderAddressAsync(addressId, item, cancellationToken) ? NoContent() : NotFound();
    }
}

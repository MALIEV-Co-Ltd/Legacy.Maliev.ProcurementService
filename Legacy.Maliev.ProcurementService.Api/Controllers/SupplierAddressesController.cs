using Legacy.Maliev.ProcurementService.Api.Authorization;
using Legacy.Maliev.ProcurementService.Application.Interfaces;
using Legacy.Maliev.ProcurementService.Application.Models;
using Maliev.Aspire.ServiceDefaults.Authorization;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;

namespace Legacy.Maliev.ProcurementService.Api.Controllers;

/// <summary>Legacy Supplier-database address routes.</summary>
/// <param name="service">Procurement application service.</param>
[ApiController]
[Route("suppliers/addresses")]
[Authorize]
public sealed class SupplierAddressesController(IProcurementService service) : ControllerBase
{
    /// <summary>Creates and attaches a supplier address.</summary>
    [HttpPost("/suppliers/{supplierId:int}/addresses")]
    [RequirePermission(ProcurementPermissions.SupplierAddressesWrite, ResourcePathTemplate = "/suppliers/{supplierId}")]
    public async Task<ActionResult> CreateSupplierAddressAsync(int supplierId, UpsertSupplierAddressRequest item, CancellationToken cancellationToken)
    {
        if (string.IsNullOrWhiteSpace(item.Address1) || item.CountryId == 0) return BadRequest();
        var address = await service.CreateSupplierAddressAsync(supplierId, item, cancellationToken);
        return address is null ? NotFound() : CreatedAtRoute("GetSupplierAddressRecord", new { addressId = address.Id }, address);
    }

    /// <summary>Deletes a supplier-owned address.</summary>
    [HttpDelete("/suppliers/{supplierId:int}/addresses/{addressId:int}")]
    [RequirePermission(ProcurementPermissions.SupplierAddressesDelete, ResourcePathTemplate = "/suppliers/{supplierId}/addresses/{addressId}", RequireLiveCheck = true)]
    public async Task<ActionResult> DeleteSupplierAddressAsync(int supplierId, int addressId, CancellationToken cancellationToken) =>
        await service.DeleteSupplierAddressAsync(supplierId, addressId, cancellationToken) ? NoContent() : NotFound();

    /// <summary>Gets an address record by identifier.</summary>
    [HttpGet("{addressId:int}", Name = "GetSupplierAddressRecord")]
    [RequirePermission(ProcurementPermissions.SupplierAddressesRead)]
    public async Task<ActionResult<SupplierAddressResponse>> GetAddressAsync(int addressId, CancellationToken cancellationToken)
    {
        var address = await service.GetSupplierAddressByIdAsync(addressId, cancellationToken);
        return address is null ? NotFound() : address;
    }

    /// <summary>Gets the address attached to a supplier.</summary>
    [HttpGet("/suppliers/{supplierId:int}/addresses", Name = "GetSupplierAddress")]
    [RequirePermission(ProcurementPermissions.SupplierAddressesRead, ResourcePathTemplate = "/suppliers/{supplierId}")]
    public async Task<ActionResult<SupplierAddressResponse>> GetSupplierAddressAsync(int supplierId, CancellationToken cancellationToken)
    {
        var address = await service.GetSupplierAddressAsync(supplierId, cancellationToken);
        return address is null ? NotFound() : address;
    }

    /// <summary>Updates a Supplier-database address.</summary>
    [HttpPut("{addressId:int}")]
    [RequirePermission(ProcurementPermissions.SupplierAddressesWrite)]
    public async Task<ActionResult> UpdateSupplierAddressAsync(int addressId, UpsertSupplierAddressRequest item, CancellationToken cancellationToken)
    {
        if (string.IsNullOrWhiteSpace(item.Address1) || item.CountryId == 0) return BadRequest();
        return await service.UpdateSupplierAddressAsync(addressId, item, cancellationToken) ? NoContent() : NotFound();
    }
}

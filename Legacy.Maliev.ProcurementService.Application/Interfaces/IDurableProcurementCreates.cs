using Legacy.Maliev.ProcurementService.Application.Models;

namespace Legacy.Maliev.ProcurementService.Application.Interfaces;

/// <summary>Transactional owning-database root-create receipts.</summary>
public interface IDurableProcurementCreates
{
    /// <summary>Creates or replays a supplier under its exact immutable binding.</summary>
    Task<DurableCreateResult> CreateSupplierAsync(UpsertSupplierRequest request, CreateReceiptBinding binding, Func<SupplierResponse, byte[]> capture, CancellationToken token);
    /// <summary>Creates or replays a purchase order under its exact immutable binding.</summary>
    Task<DurableCreateResult> CreatePurchaseOrderAsync(UpsertPurchaseOrderRequest request, CreateReceiptBinding binding, Func<PurchaseOrderResponse, byte[]> capture, CancellationToken token);
}

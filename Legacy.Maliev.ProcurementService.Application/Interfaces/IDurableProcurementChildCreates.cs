using Legacy.Maliev.ProcurementService.Application.Models;

namespace Legacy.Maliev.ProcurementService.Application.Interfaces;

/// <summary>Default-off atomic purchase-order child creates in their owning database.</summary>
public interface IDurableProcurementChildCreates
{
    /// <summary>Creates or replays an item with verified request and current parent association.</summary>
    Task<DurableCreateResult> CreateItemAsync(UpsertOrderItemRequest request, CreateReceiptBinding binding, Func<OrderItemResponse, byte[]> capture, CancellationToken token);
    /// <summary>Creates or replays file metadata with verified path and current parent association.</summary>
    Task<DurableCreateResult> CreateFileAsync(int purchaseOrderId, string bucket, string objectName, CreateReceiptBinding binding, Func<PurchaseOrderFileResponse, byte[]> capture, CancellationToken token);
}
using Legacy.Maliev.ProcurementService.Application.Interfaces;
using Legacy.Maliev.ProcurementService.Application.Models;

namespace Legacy.Maliev.ProcurementService.Application.Services;

/// <summary>Coordinates the two preserved procurement databases and Redis cache.</summary>
public sealed class ProcurementApplicationService(
    ISupplierRepository suppliers,
    IPurchaseOrderRepository purchaseOrders,
    IProcurementCache cache) : IProcurementService
{
    /// <inheritdoc />
    public async Task<SupplierResponse> CreateSupplierAsync(UpsertSupplierRequest request, CancellationToken cancellationToken) => await suppliers.CreateSupplierAsync(request, cancellationToken);
    /// <inheritdoc />
    public async Task<bool> DeleteSupplierAsync(int id, CancellationToken cancellationToken)
    {
        var deleted = await suppliers.DeleteSupplierAsync(id, cancellationToken);
        if (deleted) await cache.RemoveAsync(SupplierKey(id), cancellationToken);
        return deleted;
    }
    /// <inheritdoc />
    public async Task<SupplierResponse?> GetSupplierAsync(int id, CancellationToken cancellationToken)
    {
        var cached = await cache.GetAsync<SupplierResponse>(SupplierKey(id), cancellationToken);
        if (cached is not null) return cached;
        var supplier = await suppliers.GetSupplierAsync(id, cancellationToken);
        if (supplier is not null) await cache.SetAsync(SupplierKey(id), supplier, TimeSpan.FromMinutes(5), cancellationToken);
        return supplier;
    }
    /// <inheritdoc />
    public Task<PaginatedResponse<SupplierResponse>?> GetSuppliersAsync(SupplierSortType? sort, string? search, int? index, int? size, CancellationToken cancellationToken) =>
        suppliers.GetSuppliersAsync(sort, search, Math.Max(index ?? 1, 1), Math.Clamp(size ?? 50, 1, 250), cancellationToken);
    /// <inheritdoc />
    public async Task<bool> UpdateSupplierAsync(int id, UpsertSupplierRequest request, CancellationToken cancellationToken)
    {
        var updated = await suppliers.UpdateSupplierAsync(id, request, cancellationToken);
        if (updated) await cache.RemoveAsync(SupplierKey(id), cancellationToken);
        return updated;
    }
    /// <inheritdoc />
    public async Task<SupplierAddressResponse?> CreateSupplierAddressAsync(int supplierId, UpsertSupplierAddressRequest request, CancellationToken cancellationToken)
    {
        var address = await suppliers.CreateAddressAsync(supplierId, request, cancellationToken);
        if (address is not null) await cache.RemoveAsync(SupplierKey(supplierId), cancellationToken);
        return address;
    }
    /// <inheritdoc />
    public async Task<bool> DeleteSupplierAddressAsync(int supplierId, int addressId, CancellationToken cancellationToken)
    {
        var deleted = await suppliers.DeleteAddressAsync(supplierId, addressId, cancellationToken);
        if (deleted) await cache.RemoveAsync(SupplierKey(supplierId), cancellationToken);
        return deleted;
    }
    /// <inheritdoc />
    public Task<SupplierAddressResponse?> GetSupplierAddressByIdAsync(int addressId, CancellationToken cancellationToken) => suppliers.GetAddressAsync(addressId, cancellationToken);
    /// <inheritdoc />
    public Task<SupplierAddressResponse?> GetSupplierAddressAsync(int supplierId, CancellationToken cancellationToken) => suppliers.GetSupplierAddressAsync(supplierId, cancellationToken);
    /// <inheritdoc />
    public Task<bool> UpdateSupplierAddressAsync(int addressId, UpsertSupplierAddressRequest request, CancellationToken cancellationToken) => suppliers.UpdateAddressAsync(addressId, request, cancellationToken);

    /// <inheritdoc />
    public Task<PurchaseOrderResponse> CreatePurchaseOrderAsync(UpsertPurchaseOrderRequest request, CancellationToken cancellationToken) => purchaseOrders.CreatePurchaseOrderAsync(request, cancellationToken);
    /// <inheritdoc />
    public async Task<bool> DeletePurchaseOrderAsync(int id, CancellationToken cancellationToken)
    {
        var deleted = await purchaseOrders.DeletePurchaseOrderAsync(id, cancellationToken);
        if (deleted) await cache.RemoveAsync(PurchaseOrderKey(id), cancellationToken);
        return deleted;
    }
    /// <inheritdoc />
    public async Task<PurchaseOrderResponse?> GetPurchaseOrderAsync(int id, CancellationToken cancellationToken)
    {
        var cached = await cache.GetAsync<PurchaseOrderResponse>(PurchaseOrderKey(id), cancellationToken);
        if (cached is not null) return cached;
        var purchaseOrder = await purchaseOrders.GetPurchaseOrderAsync(id, cancellationToken);
        if (purchaseOrder is not null) await cache.SetAsync(PurchaseOrderKey(id), purchaseOrder, TimeSpan.FromMinutes(2), cancellationToken);
        return purchaseOrder;
    }
    /// <inheritdoc />
    public Task<PaginatedResponse<PurchaseOrderResponse>?> GetPurchaseOrdersAsync(PurchaseOrderSortType? sort, string? search, int? index, int? size, CancellationToken cancellationToken) =>
        purchaseOrders.GetPurchaseOrdersAsync(sort, search, Math.Max(index ?? 1, 1), Math.Clamp(size ?? 50, 1, 250), cancellationToken);
    /// <inheritdoc />
    public async Task<UpdateResult> UpdatePurchaseOrderAsync(int id, UpsertPurchaseOrderRequest request, DateTimeOffset? expectedModifiedDate, CancellationToken cancellationToken)
    {
        var result = await purchaseOrders.UpdatePurchaseOrderAsync(id, request, expectedModifiedDate, cancellationToken);
        if (result == UpdateResult.Updated) await cache.RemoveAsync(PurchaseOrderKey(id), cancellationToken);
        return result;
    }
    /// <inheritdoc />
    public Task<PurchaseOrderAddressResponse> CreatePurchaseOrderAddressAsync(UpsertPurchaseOrderAddressRequest request, CancellationToken cancellationToken) => purchaseOrders.CreateAddressAsync(request, cancellationToken);
    /// <inheritdoc />
    public Task<bool> DeletePurchaseOrderAddressAsync(int id, CancellationToken cancellationToken) => purchaseOrders.DeleteAddressAsync(id, cancellationToken);
    /// <inheritdoc />
    public Task<PurchaseOrderAddressResponse?> GetPurchaseOrderAddressAsync(int id, CancellationToken cancellationToken) => purchaseOrders.GetAddressAsync(id, cancellationToken);
    /// <inheritdoc />
    public Task<IReadOnlyList<PurchaseOrderAddressResponse>> GetPurchaseOrderAddressesAsync(CancellationToken cancellationToken) => purchaseOrders.GetAddressesAsync(cancellationToken);
    /// <inheritdoc />
    public Task<bool> UpdatePurchaseOrderAddressAsync(int id, UpsertPurchaseOrderAddressRequest request, CancellationToken cancellationToken) => purchaseOrders.UpdateAddressAsync(id, request, cancellationToken);
    /// <inheritdoc />
    public Task<OrderItemResponse> CreateOrderItemAsync(UpsertOrderItemRequest request, CancellationToken cancellationToken) => purchaseOrders.CreateOrderItemAsync(request, cancellationToken);
    /// <inheritdoc />
    public Task<bool> DeleteOrderItemAsync(int id, CancellationToken cancellationToken) => purchaseOrders.DeleteOrderItemAsync(id, cancellationToken);
    /// <inheritdoc />
    public Task<OrderItemResponse?> GetOrderItemAsync(int id, CancellationToken cancellationToken) => purchaseOrders.GetOrderItemAsync(id, cancellationToken);
    /// <inheritdoc />
    public Task<IReadOnlyList<OrderItemResponse>> GetOrderItemsAsync(int purchaseOrderId, CancellationToken cancellationToken) => purchaseOrders.GetOrderItemsAsync(purchaseOrderId, cancellationToken);
    /// <inheritdoc />
    public Task<UpdateResult> UpdateOrderItemAsync(int id, UpsertOrderItemRequest request, DateTimeOffset? expectedModifiedDate, CancellationToken cancellationToken) => purchaseOrders.UpdateOrderItemAsync(id, request, expectedModifiedDate, cancellationToken);
    /// <inheritdoc />
    public Task<PurchaseOrderFileResponse?> CreatePurchaseOrderFileAsync(int purchaseOrderId, string bucket, string objectName, CancellationToken cancellationToken) => purchaseOrders.CreateFileAsync(purchaseOrderId, bucket, objectName, cancellationToken);
    /// <inheritdoc />
    public Task<bool> DeletePurchaseOrderFileAsync(int id, CancellationToken cancellationToken) => purchaseOrders.DeleteFileAsync(id, cancellationToken);
    /// <inheritdoc />
    public Task<PurchaseOrderFileResponse?> GetPurchaseOrderFileAsync(int id, CancellationToken cancellationToken) => purchaseOrders.GetFileAsync(id, cancellationToken);
    /// <inheritdoc />
    public Task<IReadOnlyList<PurchaseOrderFileResponse>> GetPurchaseOrderFilesAsync(int purchaseOrderId, CancellationToken cancellationToken) => purchaseOrders.GetFilesAsync(purchaseOrderId, cancellationToken);
    /// <inheritdoc />
    public Task<bool> UpdatePurchaseOrderFileAsync(int id, UpsertPurchaseOrderFileRequest request, CancellationToken cancellationToken) => purchaseOrders.UpdateFileAsync(id, request, cancellationToken);

    private static string SupplierKey(int id) => $"supplier:{id}";
    private static string PurchaseOrderKey(int id) => $"purchase-order:{id}";
}

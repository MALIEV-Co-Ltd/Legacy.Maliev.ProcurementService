using Legacy.Maliev.ProcurementService.Application.Models;

namespace Legacy.Maliev.ProcurementService.Application.Interfaces;

/// <summary>Combined supplier and purchase-order application boundary.</summary>
public interface IProcurementService
{
    /// <summary>Creates a supplier.</summary>
    Task<SupplierResponse> CreateSupplierAsync(UpsertSupplierRequest request, CancellationToken cancellationToken);
    /// <summary>Deletes a supplier.</summary>
    Task<bool> DeleteSupplierAsync(int id, CancellationToken cancellationToken);
    /// <summary>Gets one supplier.</summary>
    Task<SupplierResponse?> GetSupplierAsync(int id, CancellationToken cancellationToken);
    /// <summary>Gets a supplier page.</summary>
    Task<PaginatedResponse<SupplierResponse>?> GetSuppliersAsync(SupplierSortType? sort, string? search, int? index, int? size, CancellationToken cancellationToken);
    /// <summary>Updates a supplier.</summary>
    Task<bool> UpdateSupplierAsync(int id, UpsertSupplierRequest request, CancellationToken cancellationToken);
    /// <summary>Creates and attaches a supplier address.</summary>
    Task<SupplierAddressResponse?> CreateSupplierAddressAsync(int supplierId, UpsertSupplierAddressRequest request, CancellationToken cancellationToken);
    /// <summary>Deletes a supplier-owned address.</summary>
    Task<bool> DeleteSupplierAddressAsync(int supplierId, int addressId, CancellationToken cancellationToken);
    /// <summary>Gets a Supplier-database address.</summary>
    Task<SupplierAddressResponse?> GetSupplierAddressByIdAsync(int addressId, CancellationToken cancellationToken);
    /// <summary>Gets the address attached to a supplier.</summary>
    Task<SupplierAddressResponse?> GetSupplierAddressAsync(int supplierId, CancellationToken cancellationToken);
    /// <summary>Updates a Supplier-database address.</summary>
    Task<bool> UpdateSupplierAddressAsync(int addressId, UpsertSupplierAddressRequest request, CancellationToken cancellationToken);

    /// <summary>Creates a purchase order.</summary>
    Task<PurchaseOrderResponse> CreatePurchaseOrderAsync(UpsertPurchaseOrderRequest request, CancellationToken cancellationToken);
    /// <summary>Deletes a purchase order.</summary>
    Task<bool> DeletePurchaseOrderAsync(int id, CancellationToken cancellationToken);
    /// <summary>Gets one purchase order.</summary>
    Task<PurchaseOrderResponse?> GetPurchaseOrderAsync(int id, CancellationToken cancellationToken);
    /// <summary>Gets a purchase-order page.</summary>
    Task<PaginatedResponse<PurchaseOrderResponse>?> GetPurchaseOrdersAsync(PurchaseOrderSortType? sort, string? search, int? index, int? size, CancellationToken cancellationToken);
    /// <summary>Updates a purchase order with optional ModifiedDate concurrency.</summary>
    Task<UpdateResult> UpdatePurchaseOrderAsync(int id, UpsertPurchaseOrderRequest request, DateTimeOffset? expectedModifiedDate, CancellationToken cancellationToken);
    /// <summary>Creates a PurchaseOrder-database address.</summary>
    Task<PurchaseOrderAddressResponse> CreatePurchaseOrderAddressAsync(UpsertPurchaseOrderAddressRequest request, CancellationToken cancellationToken);
    /// <summary>Deletes a PurchaseOrder-database address.</summary>
    Task<bool> DeletePurchaseOrderAddressAsync(int id, CancellationToken cancellationToken);
    /// <summary>Gets one PurchaseOrder-database address.</summary>
    Task<PurchaseOrderAddressResponse?> GetPurchaseOrderAddressAsync(int id, CancellationToken cancellationToken);
    /// <summary>Gets PurchaseOrder-database addresses.</summary>
    Task<IReadOnlyList<PurchaseOrderAddressResponse>> GetPurchaseOrderAddressesAsync(CancellationToken cancellationToken);
    /// <summary>Updates a PurchaseOrder-database address.</summary>
    Task<bool> UpdatePurchaseOrderAddressAsync(int id, UpsertPurchaseOrderAddressRequest request, CancellationToken cancellationToken);
    /// <summary>Creates an order item.</summary>
    Task<OrderItemResponse> CreateOrderItemAsync(UpsertOrderItemRequest request, CancellationToken cancellationToken);
    /// <summary>Deletes an order item.</summary>
    Task<bool> DeleteOrderItemAsync(int id, CancellationToken cancellationToken);
    /// <summary>Gets one order item.</summary>
    Task<OrderItemResponse?> GetOrderItemAsync(int id, CancellationToken cancellationToken);
    /// <summary>Gets items owned by a purchase order.</summary>
    Task<IReadOnlyList<OrderItemResponse>> GetOrderItemsAsync(int purchaseOrderId, CancellationToken cancellationToken);
    /// <summary>Updates an order item with optional ModifiedDate concurrency.</summary>
    Task<UpdateResult> UpdateOrderItemAsync(int id, UpsertOrderItemRequest request, DateTimeOffset? expectedModifiedDate, CancellationToken cancellationToken);
    /// <summary>Creates purchase-order GCS metadata.</summary>
    Task<PurchaseOrderFileResponse?> CreatePurchaseOrderFileAsync(int purchaseOrderId, string bucket, string objectName, CancellationToken cancellationToken);
    /// <summary>Deletes purchase-order GCS metadata.</summary>
    Task<bool> DeletePurchaseOrderFileAsync(int id, CancellationToken cancellationToken);
    /// <summary>Gets one purchase-order file metadata row.</summary>
    Task<PurchaseOrderFileResponse?> GetPurchaseOrderFileAsync(int id, CancellationToken cancellationToken);
    /// <summary>Gets file metadata rows owned by a purchase order.</summary>
    Task<IReadOnlyList<PurchaseOrderFileResponse>> GetPurchaseOrderFilesAsync(int purchaseOrderId, CancellationToken cancellationToken);
    /// <summary>Updates purchase-order file metadata.</summary>
    Task<bool> UpdatePurchaseOrderFileAsync(int id, UpsertPurchaseOrderFileRequest request, CancellationToken cancellationToken);
}

/// <summary>Supplier database persistence boundary.</summary>
public interface ISupplierRepository
{
    /// <summary>Creates a supplier.</summary>
    Task<SupplierResponse> CreateSupplierAsync(UpsertSupplierRequest request, CancellationToken cancellationToken);
    /// <summary>Deletes a supplier.</summary>
    Task<bool> DeleteSupplierAsync(int id, CancellationToken cancellationToken);
    /// <summary>Gets a supplier.</summary>
    Task<SupplierResponse?> GetSupplierAsync(int id, CancellationToken cancellationToken);
    /// <summary>Gets a supplier page.</summary>
    Task<PaginatedResponse<SupplierResponse>?> GetSuppliersAsync(SupplierSortType? sort, string? search, int pageIndex, int pageSize, CancellationToken cancellationToken);
    /// <summary>Updates a supplier.</summary>
    Task<bool> UpdateSupplierAsync(int id, UpsertSupplierRequest request, CancellationToken cancellationToken);
    /// <summary>Creates and attaches an address.</summary>
    Task<SupplierAddressResponse?> CreateAddressAsync(int supplierId, UpsertSupplierAddressRequest request, CancellationToken cancellationToken);
    /// <summary>Deletes a supplier-owned address.</summary>
    Task<bool> DeleteAddressAsync(int supplierId, int addressId, CancellationToken cancellationToken);
    /// <summary>Gets an address by identifier.</summary>
    Task<SupplierAddressResponse?> GetAddressAsync(int addressId, CancellationToken cancellationToken);
    /// <summary>Gets the attached supplier address.</summary>
    Task<SupplierAddressResponse?> GetSupplierAddressAsync(int supplierId, CancellationToken cancellationToken);
    /// <summary>Updates an address.</summary>
    Task<bool> UpdateAddressAsync(int addressId, UpsertSupplierAddressRequest request, CancellationToken cancellationToken);
}

/// <summary>PurchaseOrder database persistence boundary.</summary>
public interface IPurchaseOrderRepository
{
    /// <summary>Creates a purchase order.</summary>
    Task<PurchaseOrderResponse> CreatePurchaseOrderAsync(UpsertPurchaseOrderRequest request, CancellationToken cancellationToken);
    /// <summary>Deletes a purchase order.</summary>
    Task<bool> DeletePurchaseOrderAsync(int id, CancellationToken cancellationToken);
    /// <summary>Gets a purchase order.</summary>
    Task<PurchaseOrderResponse?> GetPurchaseOrderAsync(int id, CancellationToken cancellationToken);
    /// <summary>Gets a purchase-order page.</summary>
    Task<PaginatedResponse<PurchaseOrderResponse>?> GetPurchaseOrdersAsync(PurchaseOrderSortType? sort, string? search, int pageIndex, int pageSize, CancellationToken cancellationToken);
    /// <summary>Updates a purchase order.</summary>
    Task<UpdateResult> UpdatePurchaseOrderAsync(int id, UpsertPurchaseOrderRequest request, DateTimeOffset? expectedModifiedDate, CancellationToken cancellationToken);
    /// <summary>Creates an address.</summary>
    Task<PurchaseOrderAddressResponse> CreateAddressAsync(UpsertPurchaseOrderAddressRequest request, CancellationToken cancellationToken);
    /// <summary>Deletes an address.</summary>
    Task<bool> DeleteAddressAsync(int id, CancellationToken cancellationToken);
    /// <summary>Gets an address.</summary>
    Task<PurchaseOrderAddressResponse?> GetAddressAsync(int id, CancellationToken cancellationToken);
    /// <summary>Gets addresses.</summary>
    Task<IReadOnlyList<PurchaseOrderAddressResponse>> GetAddressesAsync(CancellationToken cancellationToken);
    /// <summary>Updates an address.</summary>
    Task<bool> UpdateAddressAsync(int id, UpsertPurchaseOrderAddressRequest request, CancellationToken cancellationToken);
    /// <summary>Creates an order item.</summary>
    Task<OrderItemResponse> CreateOrderItemAsync(UpsertOrderItemRequest request, CancellationToken cancellationToken);
    /// <summary>Deletes an order item.</summary>
    Task<bool> DeleteOrderItemAsync(int id, CancellationToken cancellationToken);
    /// <summary>Gets an order item.</summary>
    Task<OrderItemResponse?> GetOrderItemAsync(int id, CancellationToken cancellationToken);
    /// <summary>Gets order items.</summary>
    Task<IReadOnlyList<OrderItemResponse>> GetOrderItemsAsync(int purchaseOrderId, CancellationToken cancellationToken);
    /// <summary>Updates an order item.</summary>
    Task<UpdateResult> UpdateOrderItemAsync(int id, UpsertOrderItemRequest request, DateTimeOffset? expectedModifiedDate, CancellationToken cancellationToken);
    /// <summary>Creates file metadata.</summary>
    Task<PurchaseOrderFileResponse?> CreateFileAsync(int purchaseOrderId, string bucket, string objectName, CancellationToken cancellationToken);
    /// <summary>Deletes file metadata.</summary>
    Task<bool> DeleteFileAsync(int id, CancellationToken cancellationToken);
    /// <summary>Gets file metadata.</summary>
    Task<PurchaseOrderFileResponse?> GetFileAsync(int id, CancellationToken cancellationToken);
    /// <summary>Gets purchase-order files.</summary>
    Task<IReadOnlyList<PurchaseOrderFileResponse>> GetFilesAsync(int purchaseOrderId, CancellationToken cancellationToken);
    /// <summary>Updates file metadata.</summary>
    Task<bool> UpdateFileAsync(int id, UpsertPurchaseOrderFileRequest request, CancellationToken cancellationToken);
}

/// <summary>Redis cache boundary for authorized procurement reads.</summary>
public interface IProcurementCache
{
    /// <summary>Gets a cached value.</summary>
    Task<T?> GetAsync<T>(string key, CancellationToken cancellationToken) where T : class;
    /// <summary>Stores a cached value.</summary>
    Task SetAsync<T>(string key, T value, TimeSpan lifetime, CancellationToken cancellationToken) where T : class;
    /// <summary>Removes a cached value.</summary>
    Task RemoveAsync(string key, CancellationToken cancellationToken);
}

/// <summary>Redis-backed idempotency boundary for create requests.</summary>
public interface IIdempotencyStore
{
    /// <summary>Gets an earlier create response.</summary>
    Task<T?> GetAsync<T>(string scope, string key, CancellationToken cancellationToken) where T : class;
    /// <summary>Stores a successful create response.</summary>
    Task SetAsync<T>(string scope, string key, T response, CancellationToken cancellationToken) where T : class;
}

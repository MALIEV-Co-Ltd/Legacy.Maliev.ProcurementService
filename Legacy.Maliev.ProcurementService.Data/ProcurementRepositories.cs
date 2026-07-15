using Legacy.Maliev.ProcurementService.Application.Interfaces;
using Legacy.Maliev.ProcurementService.Application.Models;
using Legacy.Maliev.ProcurementService.Domain;
using Microsoft.EntityFrameworkCore;

namespace Legacy.Maliev.ProcurementService.Data;

/// <summary>Supplier database repository.</summary>
public sealed class SupplierRepository(SupplierDbContext dbContext, TimeProvider timeProvider) : ISupplierRepository
{
    /// <inheritdoc />
    public async Task<SupplierResponse> CreateSupplierAsync(UpsertSupplierRequest request, CancellationToken cancellationToken)
    {
        var now = Now();
        var entity = new Supplier { Name = request.Name, Website = request.Website, TaxNumber = request.TaxNumber, Email = request.Email, Note = request.Note, Telephone = request.Telephone, Mobile = request.Mobile, Fax = request.Fax, CreatedDate = now, ModifiedDate = now };
        dbContext.Suppliers.Add(entity);
        await dbContext.SaveChangesAsync(cancellationToken);
        return ToResponse(entity);
    }

    /// <inheritdoc />
    public async Task<bool> DeleteSupplierAsync(int id, CancellationToken cancellationToken) =>
        await dbContext.Suppliers.Where(value => value.Id == id).ExecuteDeleteAsync(cancellationToken) == 1;

    /// <inheritdoc />
    public Task<SupplierResponse?> GetSupplierAsync(int id, CancellationToken cancellationToken) =>
        Project(dbContext.Suppliers.AsNoTracking().Where(value => value.Id == id)).SingleOrDefaultAsync(cancellationToken);

    /// <inheritdoc />
    public async Task<PaginatedResponse<SupplierResponse>?> GetSuppliersAsync(SupplierSortType? sort, string? search, int pageIndex, int pageSize, CancellationToken cancellationToken)
    {
        IQueryable<Supplier> query = dbContext.Suppliers.AsNoTracking();
        if (!string.IsNullOrWhiteSpace(search))
        {
            var value = search.Trim();
            var numeric = int.TryParse(value, out var id);
            var pattern = $"%{value}%";
            query = query.Where(supplier => (numeric && supplier.Id == id)
                || (supplier.Name != null && EF.Functions.ILike(supplier.Name, pattern))
                || (supplier.Website != null && EF.Functions.ILike(supplier.Website, pattern))
                || (supplier.TaxNumber != null && EF.Functions.ILike(supplier.TaxNumber, pattern))
                || (supplier.Email != null && EF.Functions.ILike(supplier.Email, pattern)));
        }
        query = sort switch
        {
            SupplierSortType.SupplierId_Descending => query.OrderByDescending(value => value.Id),
            SupplierSortType.SupplierName_Ascending => query.OrderBy(value => value.Name),
            SupplierSortType.SupplierName_Descending => query.OrderByDescending(value => value.Name),
            SupplierSortType.SupplierCreatedDate_Ascending => query.OrderBy(value => value.CreatedDate),
            SupplierSortType.SupplierCreatedDate_Descending => query.OrderByDescending(value => value.CreatedDate),
            SupplierSortType.SupplierModifiedDate_Ascending => query.OrderBy(value => value.ModifiedDate),
            SupplierSortType.SupplierModifiedDate_Descending => query.OrderByDescending(value => value.ModifiedDate),
            _ => query.OrderBy(value => value.Id),
        };
        var total = await query.CountAsync(cancellationToken);
        if (total == 0) return null;
        var items = await Project(query).Skip((pageIndex - 1) * pageSize).Take(pageSize).ToListAsync(cancellationToken);
        return new(items, pageIndex, (int)Math.Ceiling(total / (double)pageSize), total);
    }

    /// <inheritdoc />
    public async Task<bool> UpdateSupplierAsync(int id, UpsertSupplierRequest request, CancellationToken cancellationToken)
    {
        var entity = await dbContext.Suppliers.FindAsync([id], cancellationToken);
        if (entity is null) return false;
        entity.Name = request.Name; entity.Website = request.Website; entity.TaxNumber = request.TaxNumber; entity.Email = request.Email;
        entity.Note = request.Note; entity.Telephone = request.Telephone; entity.Mobile = request.Mobile; entity.Fax = request.Fax; entity.ModifiedDate = Now();
        await dbContext.SaveChangesAsync(cancellationToken);
        return true;
    }

    /// <inheritdoc />
    public async Task<SupplierAddressResponse?> CreateAddressAsync(int supplierId, UpsertSupplierAddressRequest request, CancellationToken cancellationToken)
    {
        var supplier = await dbContext.Suppliers.FindAsync([supplierId], cancellationToken);
        if (supplier is null) return null;
        await using var transaction = await dbContext.Database.BeginTransactionAsync(cancellationToken);
        var now = Now();
        var address = new SupplierAddress { Building = request.Building, Address1 = request.Address1, Address2 = request.Address2, City = request.City, State = request.State, PostalCode = request.PostalCode, CountryId = request.CountryId, CreatedDate = now, ModifiedDate = now };
        dbContext.Addresses.Add(address);
        await dbContext.SaveChangesAsync(cancellationToken);
        supplier.AddressId = address.Id;
        supplier.ModifiedDate = now;
        await dbContext.SaveChangesAsync(cancellationToken);
        await transaction.CommitAsync(cancellationToken);
        return ToResponse(address);
    }

    /// <inheritdoc />
    public async Task<bool> DeleteAddressAsync(int supplierId, int addressId, CancellationToken cancellationToken)
    {
        var supplier = await dbContext.Suppliers.SingleOrDefaultAsync(value => value.Id == supplierId && value.AddressId == addressId, cancellationToken);
        if (supplier is null) return false;
        await using var transaction = await dbContext.Database.BeginTransactionAsync(cancellationToken);
        supplier.AddressId = null;
        supplier.ModifiedDate = Now();
        await dbContext.SaveChangesAsync(cancellationToken);
        var deleted = await dbContext.Addresses.Where(value => value.Id == addressId).ExecuteDeleteAsync(cancellationToken) == 1;
        await transaction.CommitAsync(cancellationToken);
        return deleted;
    }

    /// <inheritdoc />
    public Task<SupplierAddressResponse?> GetAddressAsync(int addressId, CancellationToken cancellationToken) =>
        dbContext.Addresses.AsNoTracking().Where(value => value.Id == addressId).Select(ProjectAddress()).SingleOrDefaultAsync(cancellationToken);
    /// <inheritdoc />
    public Task<SupplierAddressResponse?> GetSupplierAddressAsync(int supplierId, CancellationToken cancellationToken) =>
        dbContext.Suppliers.AsNoTracking().Where(value => value.Id == supplierId && value.AddressId != null)
            .Select(value => value.Address!).Select(ProjectAddress()).SingleOrDefaultAsync(cancellationToken);
    /// <inheritdoc />
    public async Task<bool> UpdateAddressAsync(int addressId, UpsertSupplierAddressRequest request, CancellationToken cancellationToken)
    {
        var entity = await dbContext.Addresses.FindAsync([addressId], cancellationToken);
        if (entity is null) return false;
        entity.Building = request.Building; entity.Address1 = request.Address1; entity.Address2 = request.Address2; entity.City = request.City;
        entity.State = request.State; entity.PostalCode = request.PostalCode; entity.CountryId = request.CountryId; entity.ModifiedDate = Now();
        await dbContext.SaveChangesAsync(cancellationToken);
        return true;
    }

    private DateTime Now() => timeProvider.GetUtcNow().UtcDateTime;
    private static SupplierResponse ToResponse(Supplier value) => new(value.Id, value.Name, value.Website, value.TaxNumber, value.Email, value.Note, value.AddressId, value.Telephone, value.Mobile, value.Fax, value.CreatedDate, value.ModifiedDate);
    private static SupplierAddressResponse ToResponse(SupplierAddress value) => new(value.Id, value.Building, value.Address1, value.Address2, value.City, value.State, value.PostalCode, value.CountryId, value.ModifiedDate, value.CreatedDate);
    private static IQueryable<SupplierResponse> Project(IQueryable<Supplier> query) => query.Select(value => new SupplierResponse(value.Id, value.Name, value.Website, value.TaxNumber, value.Email, value.Note, value.AddressId, value.Telephone, value.Mobile, value.Fax, value.CreatedDate, value.ModifiedDate));
    private static System.Linq.Expressions.Expression<Func<SupplierAddress, SupplierAddressResponse>> ProjectAddress() => value => new SupplierAddressResponse(value.Id, value.Building, value.Address1, value.Address2, value.City, value.State, value.PostalCode, value.CountryId, value.ModifiedDate, value.CreatedDate);
}

/// <summary>PurchaseOrder database repository.</summary>
public sealed class PurchaseOrderRepository(PurchaseOrderDbContext dbContext, TimeProvider timeProvider) : IPurchaseOrderRepository
{
    /// <inheritdoc />
    public async Task<PurchaseOrderResponse> CreatePurchaseOrderAsync(UpsertPurchaseOrderRequest request, CancellationToken cancellationToken)
    {
        var entity = Map(new PurchaseOrder(), request); var now = Now(); entity.CreatedDate = now; entity.ModifiedDate = now;
        dbContext.PurchaseOrders.Add(entity); await dbContext.SaveChangesAsync(cancellationToken); return ToResponse(entity);
    }
    /// <inheritdoc />
    public async Task<bool> DeletePurchaseOrderAsync(int id, CancellationToken cancellationToken) => await dbContext.PurchaseOrders.Where(value => value.Id == id).ExecuteDeleteAsync(cancellationToken) == 1;
    /// <inheritdoc />
    public Task<PurchaseOrderResponse?> GetPurchaseOrderAsync(int id, CancellationToken cancellationToken) => Project(dbContext.PurchaseOrders.AsNoTracking().Where(value => value.Id == id)).SingleOrDefaultAsync(cancellationToken);
    /// <inheritdoc />
    public async Task<PaginatedResponse<PurchaseOrderResponse>?> GetPurchaseOrdersAsync(PurchaseOrderSortType? sort, string? search, int pageIndex, int pageSize, CancellationToken cancellationToken)
    {
        IQueryable<PurchaseOrder> query = dbContext.PurchaseOrders.AsNoTracking();
        if (!string.IsNullOrWhiteSpace(search))
        {
            var value = search.Trim(); var numeric = int.TryParse(value, out var id); var pattern = $"%{value}%";
            query = query.Where(order => (numeric && order.Id == id) || (order.Notes != null && EF.Functions.ILike(order.Notes, pattern)));
        }
        query = sort switch { PurchaseOrderSortType.PurchaseOrderId_Descending => query.OrderByDescending(value => value.Id), PurchaseOrderSortType.PurchaseOrderCreatedDate_Ascending => query.OrderBy(value => value.CreatedDate), PurchaseOrderSortType.PurchaseOrderCreatedDate_Descending => query.OrderByDescending(value => value.CreatedDate), _ => query.OrderBy(value => value.Id) };
        var total = await query.CountAsync(cancellationToken); if (total == 0) return null;
        var items = await Project(query).Skip((pageIndex - 1) * pageSize).Take(pageSize).ToListAsync(cancellationToken);
        return new(items, pageIndex, (int)Math.Ceiling(total / (double)pageSize), total);
    }
    /// <inheritdoc />
    public async Task<UpdateResult> UpdatePurchaseOrderAsync(int id, UpsertPurchaseOrderRequest request, DateTimeOffset? expectedModifiedDate, CancellationToken cancellationToken)
    {
        var entity = await dbContext.PurchaseOrders.FindAsync([id], cancellationToken); if (entity is null) return UpdateResult.NotFound;
        if (expectedModifiedDate is not null) dbContext.Entry(entity).Property(value => value.ModifiedDate).OriginalValue = expectedModifiedDate.Value.UtcDateTime;
        Map(entity, request).ModifiedDate = Now();
        try { await dbContext.SaveChangesAsync(cancellationToken); return UpdateResult.Updated; }
        catch (DbUpdateConcurrencyException) { return UpdateResult.Conflict; }
    }
    /// <inheritdoc />
    public async Task<PurchaseOrderAddressResponse> CreateAddressAsync(UpsertPurchaseOrderAddressRequest request, CancellationToken cancellationToken)
    {
        var now = Now(); var entity = new PurchaseOrderAddress { Building = request.Building, AddressLine1 = request.AddressLine1.Trim(), AddressLine2 = request.AddressLine2, City = request.City, State = request.State, PostalCode = request.PostalCode, CountryId = request.CountryId, CreatedDate = now, ModifiedDate = now };
        dbContext.Addresses.Add(entity); await dbContext.SaveChangesAsync(cancellationToken); return ToResponse(entity);
    }
    /// <inheritdoc />
    public async Task<bool> DeleteAddressAsync(int id, CancellationToken cancellationToken) => await dbContext.Addresses.Where(value => value.Id == id).ExecuteDeleteAsync(cancellationToken) == 1;
    /// <inheritdoc />
    public Task<PurchaseOrderAddressResponse?> GetAddressAsync(int id, CancellationToken cancellationToken) => dbContext.Addresses.AsNoTracking().Where(value => value.Id == id).Select(ProjectAddress()).SingleOrDefaultAsync(cancellationToken);
    /// <inheritdoc />
    public async Task<IReadOnlyList<PurchaseOrderAddressResponse>> GetAddressesAsync(CancellationToken cancellationToken) => await dbContext.Addresses.AsNoTracking().OrderBy(value => value.Id).Select(ProjectAddress()).ToListAsync(cancellationToken);
    /// <inheritdoc />
    public async Task<bool> UpdateAddressAsync(int id, UpsertPurchaseOrderAddressRequest request, CancellationToken cancellationToken)
    {
        var entity = await dbContext.Addresses.FindAsync([id], cancellationToken); if (entity is null) return false;
        entity.Building = request.Building; entity.AddressLine1 = request.AddressLine1.Trim(); entity.AddressLine2 = request.AddressLine2; entity.City = request.City; entity.State = request.State; entity.PostalCode = request.PostalCode; entity.CountryId = request.CountryId; entity.ModifiedDate = Now();
        await dbContext.SaveChangesAsync(cancellationToken); return true;
    }
    /// <inheritdoc />
    public async Task<OrderItemResponse> CreateOrderItemAsync(UpsertOrderItemRequest request, CancellationToken cancellationToken)
    {
        var now = Now(); var entity = new OrderItem { PurchaseOrderId = request.PurchaseOrderId, PartNumber = request.PartNumber, Description = request.Description, Quantity = request.Quantity, UnitPrice = request.UnitPrice, CreatedDate = now, ModifiedDate = now };
        dbContext.OrderItems.Add(entity); await dbContext.SaveChangesAsync(cancellationToken); return (await GetOrderItemAsync(entity.Id, cancellationToken))!;
    }
    /// <inheritdoc />
    public async Task<bool> DeleteOrderItemAsync(int id, CancellationToken cancellationToken) => await dbContext.OrderItems.Where(value => value.Id == id).ExecuteDeleteAsync(cancellationToken) == 1;
    /// <inheritdoc />
    public Task<OrderItemResponse?> GetOrderItemAsync(int id, CancellationToken cancellationToken) => dbContext.OrderItems.AsNoTracking().Where(value => value.Id == id).Select(ProjectOrderItem()).SingleOrDefaultAsync(cancellationToken);
    /// <inheritdoc />
    public async Task<IReadOnlyList<OrderItemResponse>> GetOrderItemsAsync(int purchaseOrderId, CancellationToken cancellationToken) => await dbContext.OrderItems.AsNoTracking().Where(value => value.PurchaseOrderId == purchaseOrderId).OrderBy(value => value.Id).Select(ProjectOrderItem()).ToListAsync(cancellationToken);
    /// <inheritdoc />
    public async Task<UpdateResult> UpdateOrderItemAsync(int id, UpsertOrderItemRequest request, DateTimeOffset? expectedModifiedDate, CancellationToken cancellationToken)
    {
        var entity = await dbContext.OrderItems.FindAsync([id], cancellationToken); if (entity is null) return UpdateResult.NotFound;
        if (expectedModifiedDate is not null) dbContext.Entry(entity).Property(value => value.ModifiedDate).OriginalValue = expectedModifiedDate.Value.UtcDateTime;
        entity.PurchaseOrderId = request.PurchaseOrderId; entity.PartNumber = request.PartNumber; entity.Description = request.Description; entity.Quantity = request.Quantity; entity.UnitPrice = request.UnitPrice; entity.ModifiedDate = Now();
        try { await dbContext.SaveChangesAsync(cancellationToken); return UpdateResult.Updated; }
        catch (DbUpdateConcurrencyException) { return UpdateResult.Conflict; }
    }
    /// <inheritdoc />
    public async Task<PurchaseOrderFileResponse?> CreateFileAsync(int purchaseOrderId, string bucket, string objectName, CancellationToken cancellationToken)
    {
        if (!await dbContext.PurchaseOrders.AnyAsync(value => value.Id == purchaseOrderId, cancellationToken)) return null;
        var now = Now(); var entity = new PurchaseOrderFile { PurchaseOrderId = purchaseOrderId, Bucket = bucket.Trim(), ObjectName = objectName.Trim(), CreatedDate = now, ModifiedDate = now };
        dbContext.Files.Add(entity); await dbContext.SaveChangesAsync(cancellationToken); return ToResponse(entity);
    }
    /// <inheritdoc />
    public async Task<bool> DeleteFileAsync(int id, CancellationToken cancellationToken) => await dbContext.Files.Where(value => value.Id == id).ExecuteDeleteAsync(cancellationToken) == 1;
    /// <inheritdoc />
    public Task<PurchaseOrderFileResponse?> GetFileAsync(int id, CancellationToken cancellationToken) => dbContext.Files.AsNoTracking().Where(value => value.Id == id).Select(ProjectFile()).SingleOrDefaultAsync(cancellationToken);
    /// <inheritdoc />
    public async Task<IReadOnlyList<PurchaseOrderFileResponse>> GetFilesAsync(int purchaseOrderId, CancellationToken cancellationToken) => await dbContext.Files.AsNoTracking().Where(value => value.PurchaseOrderId == purchaseOrderId).OrderBy(value => value.Id).Select(ProjectFile()).ToListAsync(cancellationToken);
    /// <inheritdoc />
    public async Task<bool> UpdateFileAsync(int id, UpsertPurchaseOrderFileRequest request, CancellationToken cancellationToken)
    {
        var entity = await dbContext.Files.FindAsync([id], cancellationToken); if (entity is null) return false;
        entity.PurchaseOrderId = request.PurchaseOrderId ?? entity.PurchaseOrderId; entity.Bucket = request.Bucket.Trim(); entity.ObjectName = request.ObjectName.Trim(); entity.ModifiedDate = Now(); await dbContext.SaveChangesAsync(cancellationToken); return true;
    }

    private DateTime Now() => timeProvider.GetUtcNow().UtcDateTime;
    private static PurchaseOrder Map(PurchaseOrder value, UpsertPurchaseOrderRequest request)
    {
        value.SupplierId = request.SupplierId; value.SupplierContactPerson = request.SupplierContactPerson; value.ShippingAddressId = request.ShippingAddressId;
        value.ShippingContactPerson = request.ShippingContactPerson; value.ShippingTelephone = request.ShippingTelephone; value.ShippingMobile = request.ShippingMobile; value.ShippingFax = request.ShippingFax;
        value.BillingAddressId = request.BillingAddressId; value.BillingContactPerson = request.BillingContactPerson; value.BillingTelephone = request.BillingTelephone; value.BillingMobile = request.BillingMobile; value.BillingFax = request.BillingFax;
        value.Fob = request.Fob; value.Terms = request.Terms; value.ShippingMethod = request.ShippingMethod; value.EmployeeId = request.EmployeeId; value.Notes = request.Notes; return value;
    }
    private static PurchaseOrderResponse ToResponse(PurchaseOrder value) => new(value.Id, value.SupplierId, value.SupplierContactPerson, value.ShippingAddressId, value.ShippingContactPerson, value.ShippingTelephone, value.ShippingMobile, value.ShippingFax, value.BillingAddressId, value.BillingContactPerson, value.BillingTelephone, value.BillingMobile, value.BillingFax, value.Fob, value.Terms, value.ShippingMethod, value.EmployeeId, value.Notes, value.CreatedDate, value.ModifiedDate);
    private static PurchaseOrderAddressResponse ToResponse(PurchaseOrderAddress value) => new(value.Id, value.Building, value.AddressLine1, value.AddressLine2, value.City, value.State, value.PostalCode, value.CountryId, value.CreatedDate, value.ModifiedDate);
    private static PurchaseOrderFileResponse ToResponse(PurchaseOrderFile value) => new(value.Id, value.PurchaseOrderId, value.Bucket, value.ObjectName, value.CreatedDate, value.ModifiedDate);
    private static IQueryable<PurchaseOrderResponse> Project(IQueryable<PurchaseOrder> query) => query.Select(value => new PurchaseOrderResponse(value.Id, value.SupplierId, value.SupplierContactPerson, value.ShippingAddressId, value.ShippingContactPerson, value.ShippingTelephone, value.ShippingMobile, value.ShippingFax, value.BillingAddressId, value.BillingContactPerson, value.BillingTelephone, value.BillingMobile, value.BillingFax, value.Fob, value.Terms, value.ShippingMethod, value.EmployeeId, value.Notes, value.CreatedDate, value.ModifiedDate));
    private static System.Linq.Expressions.Expression<Func<PurchaseOrderAddress, PurchaseOrderAddressResponse>> ProjectAddress() => value => new PurchaseOrderAddressResponse(value.Id, value.Building, value.AddressLine1, value.AddressLine2, value.City, value.State, value.PostalCode, value.CountryId, value.CreatedDate, value.ModifiedDate);
    private static System.Linq.Expressions.Expression<Func<OrderItem, OrderItemResponse>> ProjectOrderItem() => value => new OrderItemResponse(value.Id, value.PurchaseOrderId, value.PartNumber, value.Description, value.Quantity, value.UnitPrice, value.Subtotal, value.CreatedDate, value.ModifiedDate);
    private static System.Linq.Expressions.Expression<Func<PurchaseOrderFile, PurchaseOrderFileResponse>> ProjectFile() => value => new PurchaseOrderFileResponse(value.Id, value.PurchaseOrderId, value.Bucket, value.ObjectName, value.CreatedDate, value.ModifiedDate);
}

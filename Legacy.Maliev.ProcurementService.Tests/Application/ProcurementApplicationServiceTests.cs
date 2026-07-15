using Legacy.Maliev.ProcurementService.Application.Interfaces;
using Legacy.Maliev.ProcurementService.Application.Models;
using Legacy.Maliev.ProcurementService.Application.Services;
using Moq;

namespace Legacy.Maliev.ProcurementService.Tests.Application;

public sealed class ProcurementApplicationServiceTests
{
    [Fact]
    public async Task GetSupplier_UsesCacheBeforePostgres()
    {
        var expected = new SupplierResponse(7, "Cached", null, null, null, null, null, null, null, null, null, null);
        var supplierRepository = new Mock<ISupplierRepository>();
        var cache = new Mock<IProcurementCache>();
        cache.Setup(value => value.GetAsync<SupplierResponse>("supplier:7", It.IsAny<CancellationToken>())).ReturnsAsync(expected);
        var service = CreateService(supplierRepository.Object, Mock.Of<IPurchaseOrderRepository>(), cache.Object);

        var actual = await service.GetSupplierAsync(7, CancellationToken.None);

        Assert.Same(expected, actual);
        supplierRepository.Verify(value => value.GetSupplierAsync(It.IsAny<int>(), It.IsAny<CancellationToken>()), Times.Never);
    }

    [Fact]
    public async Task GetPurchaseOrder_CachesPostgresResultForTwoMinutes()
    {
        var expected = new PurchaseOrderResponse(8, null, null, null, null, null, null, null, null, null, null, null, null, null, null, null, null, null, null, null);
        var repository = new Mock<IPurchaseOrderRepository>();
        repository.Setup(value => value.GetPurchaseOrderAsync(8, It.IsAny<CancellationToken>())).ReturnsAsync(expected);
        var cache = new Mock<IProcurementCache>();
        var service = CreateService(Mock.Of<ISupplierRepository>(), repository.Object, cache.Object);

        Assert.Same(expected, await service.GetPurchaseOrderAsync(8, CancellationToken.None));

        cache.Verify(value => value.SetAsync("purchase-order:8", expected, TimeSpan.FromMinutes(2), It.IsAny<CancellationToken>()), Times.Once);
    }

    [Fact]
    public async Task ListBoundaries_NormalizePageAndClampSizeWithoutChangingWireContract()
    {
        var suppliers = new Mock<ISupplierRepository>();
        suppliers.Setup(value => value.GetSuppliersAsync(null, "needle", 1, 250, It.IsAny<CancellationToken>()))
            .ReturnsAsync((PaginatedResponse<SupplierResponse>?)null);
        var service = CreateService(suppliers.Object, Mock.Of<IPurchaseOrderRepository>(), Mock.Of<IProcurementCache>());

        await service.GetSuppliersAsync(null, "needle", -4, 10_000, CancellationToken.None);

        suppliers.VerifyAll();
    }

    private static ProcurementApplicationService CreateService(
        ISupplierRepository suppliers,
        IPurchaseOrderRepository purchaseOrders,
        IProcurementCache cache) => new(suppliers, purchaseOrders, cache);
}

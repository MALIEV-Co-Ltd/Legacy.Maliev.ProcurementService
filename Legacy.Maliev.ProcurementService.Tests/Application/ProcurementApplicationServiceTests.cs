using Legacy.Maliev.ProcurementService.Application.Interfaces;
using Legacy.Maliev.ProcurementService.Application.Models;
using Legacy.Maliev.ProcurementService.Application.Services;
using Moq;

namespace Legacy.Maliev.ProcurementService.Tests.Application;

public sealed class ProcurementApplicationServiceTests
{
    [Fact]
    public async Task GetSupplier_UsesPostgresDespiteStaleCacheWithoutReadingOrFillingCache()
    {
        var expected = new SupplierResponse(7, "Committed", null, null, null, null, null, null, null, null, null, null);
        var stale = expected with { Name = "Cached" };
        var supplierRepository = new Mock<ISupplierRepository>();
        var cache = new Mock<IProcurementCache>();
        cache.Setup(value => value.GetAsync<SupplierResponse>("supplier:7", It.IsAny<CancellationToken>())).ReturnsAsync(stale);
        supplierRepository.Setup(value => value.GetSupplierAsync(7, It.IsAny<CancellationToken>())).ReturnsAsync(expected);
        var service = CreateService(supplierRepository.Object, Mock.Of<IPurchaseOrderRepository>(), cache.Object);

        var actual = await service.GetSupplierAsync(7, CancellationToken.None);

        Assert.Same(expected, actual);
        supplierRepository.Verify(value => value.GetSupplierAsync(7, It.IsAny<CancellationToken>()), Times.Once);
        cache.VerifyNoOtherCalls();
    }

    [Fact]
    public async Task GetPurchaseOrder_UsesPostgresDespiteStaleCacheWithoutReadingOrFillingCache()
    {
        var expected = new PurchaseOrderResponse(8, null, null, null, null, null, null, null, null, null, null, null, null, null, null, null, null, null, null, null);
        var repository = new Mock<IPurchaseOrderRepository>();
        repository.Setup(value => value.GetPurchaseOrderAsync(8, It.IsAny<CancellationToken>())).ReturnsAsync(expected);
        var cache = new Mock<IProcurementCache>();
        cache.Setup(value => value.GetAsync<PurchaseOrderResponse>("purchase-order:8", It.IsAny<CancellationToken>())).ReturnsAsync(expected with { Notes = "Stale" });
        var service = CreateService(Mock.Of<ISupplierRepository>(), repository.Object, cache.Object);

        Assert.Same(expected, await service.GetPurchaseOrderAsync(8, CancellationToken.None));

        repository.Verify(value => value.GetPurchaseOrderAsync(8, It.IsAny<CancellationToken>()), Times.Once);
        cache.VerifyNoOtherCalls();
    }

    [Theory]
    [InlineData(false, false)]
    [InlineData(false, true)]
    [InlineData(true, false)]
    [InlineData(true, true)]
    public async Task DetailRead_PropagatesRepositoryErrorAndCancellationWithoutCache(bool purchaseOrder, bool cancelled)
    {
        using var cancellation = new CancellationTokenSource();
        if (cancelled) cancellation.Cancel();
        Exception expected = cancelled ? new OperationCanceledException(cancellation.Token) : new IOException("Repository unavailable");
        var suppliers = new Mock<ISupplierRepository>();
        var orders = new Mock<IPurchaseOrderRepository>();
        suppliers.Setup(value => value.GetSupplierAsync(7, cancellation.Token)).ThrowsAsync(expected);
        orders.Setup(value => value.GetPurchaseOrderAsync(7, cancellation.Token)).ThrowsAsync(expected);
        var cache = new Mock<IProcurementCache>(MockBehavior.Strict);
        var service = CreateService(suppliers.Object, orders.Object, cache.Object);
        var actual = await Record.ExceptionAsync(async () =>
        {
            if (purchaseOrder) await service.GetPurchaseOrderAsync(7, cancellation.Token);
            else await service.GetSupplierAsync(7, cancellation.Token);
        });
        Assert.Same(expected, actual);
        cache.VerifyNoOtherCalls();
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

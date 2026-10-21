using Legacy.Maliev.ProcurementService.Api.Controllers;
using Legacy.Maliev.ProcurementService.Application.Interfaces;
using Legacy.Maliev.ProcurementService.Application.Models;
using Microsoft.AspNetCore.Mvc;
using Moq;

namespace Legacy.Maliev.ProcurementService.Tests.Controllers;

public sealed class ProcurementAddressNullBoundaryTests
{
    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task SupplierNullBody_ReturnsEmptyBadRequestBeforeApplicationAccess(bool update)
    {
        const int id = int.MaxValue;
        var service = new Mock<IProcurementService>(MockBehavior.Strict);
        var controller = new SupplierAddressesController(service.Object);

        var result = update
            ? await controller.UpdateSupplierAddressAsync(id, null!, default)
            : await controller.CreateSupplierAddressAsync(id, null!, default);

        Assert.IsType<BadRequestResult>(result);
        service.VerifyNoOtherCalls();
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task PurchaseOrderNullBody_ReturnsEmptyBadRequestBeforeApplicationAccess(bool update)
    {
        const int id = int.MaxValue;
        var service = new Mock<IProcurementService>(MockBehavior.Strict);
        var controller = new PurchaseOrderAddressesController(service.Object);

        var result = update
            ? await controller.UpdateAddressAsync(id, null!, default)
            : await controller.CreateAddressAsync(null!, default);

        Assert.IsType<BadRequestResult>(result);
        service.VerifyNoOtherCalls();
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task SupplierNonNullBody_PreservesRequestTokenAndExistingResult(bool update)
    {
        const int id = int.MaxValue;
        var request = new UpsertSupplierAddressRequest(null, " Main ", null, null, null, null, 66);
        var address = new SupplierAddressResponse(7, null, " Main ", null, null, null, null, 66, null, null);
        using var cancellation = new CancellationTokenSource();
        var token = cancellation.Token;
        var service = new Mock<IProcurementService>(MockBehavior.Strict);
        var controller = new SupplierAddressesController(service.Object);
        if (update)
        {
            service.Setup(value => value.UpdateSupplierAddressAsync(id, request, token)).ReturnsAsync(true);

            var result = await controller.UpdateSupplierAddressAsync(id, request, token);

            Assert.IsType<NoContentResult>(result);
            service.Verify(value => value.UpdateSupplierAddressAsync(id,
                It.Is<UpsertSupplierAddressRequest>(actual => ReferenceEquals(actual, request)), token), Times.Once);
        }
        else
        {
            service.Setup(value => value.CreateSupplierAddressAsync(id, request, token)).ReturnsAsync(address);

            var result = await controller.CreateSupplierAddressAsync(id, request, token);

            var created = Assert.IsType<CreatedAtRouteResult>(result);
            Assert.Equal("GetSupplierAddressRecord", created.RouteName);
            Assert.Equal(7, created.RouteValues!["addressId"]);
            Assert.Same(address, created.Value);
            service.Verify(value => value.CreateSupplierAddressAsync(id,
                It.Is<UpsertSupplierAddressRequest>(actual => ReferenceEquals(actual, request)), token), Times.Once);
        }
        service.VerifyNoOtherCalls();
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task PurchaseOrderNonNullBody_PreservesRequestTokenAndExistingResult(bool update)
    {
        const int id = int.MaxValue;
        var request = new UpsertPurchaseOrderAddressRequest(null, " Main ", null, null, null, null, 66);
        var address = new PurchaseOrderAddressResponse(7, null, " Main ", null, null, null, null, 66, null, null);
        using var cancellation = new CancellationTokenSource();
        var token = cancellation.Token;
        var service = new Mock<IProcurementService>(MockBehavior.Strict);
        var controller = new PurchaseOrderAddressesController(service.Object);
        if (update)
        {
            service.Setup(value => value.UpdatePurchaseOrderAddressAsync(id, request, token)).ReturnsAsync(true);

            var result = await controller.UpdateAddressAsync(id, request, token);

            Assert.IsType<NoContentResult>(result);
            service.Verify(value => value.UpdatePurchaseOrderAddressAsync(id,
                It.Is<UpsertPurchaseOrderAddressRequest>(actual => ReferenceEquals(actual, request)), token), Times.Once);
        }
        else
        {
            service.Setup(value => value.CreatePurchaseOrderAddressAsync(request, token)).ReturnsAsync(address);

            var result = await controller.CreateAddressAsync(request, token);

            var created = Assert.IsType<CreatedAtRouteResult>(result);
            Assert.Equal("GetPurchaseOrderAddress", created.RouteName);
            Assert.Equal(7, created.RouteValues!["addressId"]);
            Assert.Same(address, created.Value);
            service.Verify(value => value.CreatePurchaseOrderAddressAsync(
                It.Is<UpsertPurchaseOrderAddressRequest>(actual => ReferenceEquals(actual, request)), token), Times.Once);
        }
        service.VerifyNoOtherCalls();
    }
}

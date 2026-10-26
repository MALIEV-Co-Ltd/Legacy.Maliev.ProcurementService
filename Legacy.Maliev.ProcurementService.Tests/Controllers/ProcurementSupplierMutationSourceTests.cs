using Legacy.Maliev.ProcurementService.Api.Controllers;
using Legacy.Maliev.ProcurementService.Application.Interfaces;
using Legacy.Maliev.ProcurementService.Application.Models;
using Microsoft.AspNetCore.Mvc;
using Moq;

namespace Legacy.Maliev.ProcurementService.Tests.Controllers;

public sealed class ProcurementSupplierMutationSourceTests
{
    [Theory]
    [InlineData(null)]
    [InlineData("null-source-control")]
    public async Task CreateSupplier_NullBody_ReturnsEmptyBadRequestBeforeApplicationOrIdempotency(string? key)
    {
        var service = new Mock<IProcurementService>(MockBehavior.Strict);
        var idempotency = new Mock<IIdempotencyStore>(MockBehavior.Strict);
        var controller = new SuppliersController(service.Object, idempotency.Object);

        var result = await controller.CreateSupplierAsync(null!, key, CancellationToken.None);

        Assert.Equal(400, Assert.IsType<BadRequestResult>(result).StatusCode);
        service.VerifyNoOtherCalls();
        idempotency.VerifyNoOtherCalls();
    }

    [Theory]
    [InlineData(101)]
    [InlineData(int.MaxValue)]
    public async Task UpdateSupplier_NullBody_ReturnsEmptyBadRequestBeforeLookup(int id)
    {
        var service = new Mock<IProcurementService>(MockBehavior.Strict);
        var idempotency = new Mock<IIdempotencyStore>(MockBehavior.Strict);
        var controller = new SuppliersController(service.Object, idempotency.Object);

        var result = await controller.UpdateSupplierAsync(id, null!, CancellationToken.None);

        Assert.Equal(400, Assert.IsType<BadRequestResult>(result).StatusCode);
        service.VerifyNoOtherCalls();
        idempotency.VerifyNoOtherCalls();
    }

    [Theory]
    [InlineData(101)]
    [InlineData(int.MaxValue)]
    public async Task CreateAddress_MissingSupplier_ReturnsOriginalLiteralAndForwardsRequest(int id)
    {
        var request = new UpsertSupplierAddressRequest(null, "Source boundary", null, null, null, null, 66);
        using var cancellation = new CancellationTokenSource();
        var service = new Mock<IProcurementService>(MockBehavior.Strict);
        service.Setup(value => value.CreateSupplierAddressAsync(id, request, cancellation.Token))
            .ReturnsAsync((SupplierAddressResponse?)null);
        var controller = new SupplierAddressesController(service.Object);

        var result = await controller.CreateSupplierAddressAsync(id, request, cancellation.Token);

        var missing = Assert.IsType<NotFoundObjectResult>(result);
        Assert.Equal(404, missing.StatusCode);
        Assert.Equal("Supplier does not exist", Assert.IsType<string>(missing.Value));
        service.Verify(value => value.CreateSupplierAddressAsync(id,
            It.Is<UpsertSupplierAddressRequest>(actual => ReferenceEquals(actual, request)), cancellation.Token), Times.Once);
        service.VerifyNoOtherCalls();
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task UpdateSupplier_NonNullBody_PreservesRequestTokenAndResult(bool found)
    {
        const int id = 101;
        var request = new UpsertSupplierRequest("Source supplier", null, null, null, null, null, null, null);
        using var cancellation = new CancellationTokenSource();
        var service = new Mock<IProcurementService>(MockBehavior.Strict);
        var idempotency = new Mock<IIdempotencyStore>(MockBehavior.Strict);
        service.Setup(value => value.UpdateSupplierAsync(id, request, cancellation.Token)).ReturnsAsync(found);
        var controller = new SuppliersController(service.Object, idempotency.Object);

        var result = await controller.UpdateSupplierAsync(id, request, cancellation.Token);

        if (found) Assert.IsType<NoContentResult>(result);
        else Assert.IsType<NotFoundResult>(result);
        service.Verify(value => value.UpdateSupplierAsync(id,
            It.Is<UpsertSupplierRequest>(actual => ReferenceEquals(actual, request)), cancellation.Token), Times.Once);
        service.VerifyNoOtherCalls();
        idempotency.VerifyNoOtherCalls();
    }
}

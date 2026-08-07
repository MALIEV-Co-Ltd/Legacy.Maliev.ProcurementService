using Legacy.Maliev.ProcurementService.Application.Models;
using Legacy.Maliev.ProcurementService.Application.Interfaces;
using Legacy.Maliev.ProcurementService.Data;
using Microsoft.Extensions.Caching.Distributed;
using Microsoft.Extensions.Caching.Memory;
using Microsoft.Extensions.Logging.Abstractions;
using Microsoft.Extensions.Options;
using Moq;

namespace Legacy.Maliev.ProcurementService.Tests.Caching;

public sealed class DistributedProcurementCacheTests
{
    [Fact]
    public async Task IdempotencyStore_RoundTripsResponseWithoutUsingRawClientKey()
    {
        IDistributedCache distributed = new MemoryDistributedCache(Options.Create(new MemoryDistributedCacheOptions()));
        IIdempotencyStore store = new DistributedProcurementCache(distributed, NullLogger<DistributedProcurementCache>.Instance);
        var response = new SupplierResponse(42, "Legacy", null, null, null, null, null, null, null, null, null, null);

        await store.SetAsync("supplier", "customer-visible-key", response, CancellationToken.None);
        var loaded = await store.GetAsync<SupplierResponse>("supplier", "customer-visible-key", CancellationToken.None);

        Assert.Equal(response, loaded);
        Assert.Null(await distributed.GetAsync("idempotency:supplier:customer-visible-key"));
    }

    [Fact]
    public async Task Cache_RoundTripsAuthorizedReadAndSupportsInvalidation()
    {
        IDistributedCache distributed = new MemoryDistributedCache(Options.Create(new MemoryDistributedCacheOptions()));
        var cache = new DistributedProcurementCache(distributed, NullLogger<DistributedProcurementCache>.Instance);
        var response = new PurchaseOrderResponse(7, 3, "Supplier", null, null, null, null, null, null, null, null, null, null, null, null, null, 9, "note", null, null);

        await cache.SetAsync("purchase-order:7", response, TimeSpan.FromMinutes(2), CancellationToken.None);
        Assert.Equal(response, await cache.GetAsync<PurchaseOrderResponse>("purchase-order:7", CancellationToken.None));
        await cache.RemoveAsync("purchase-order:7", CancellationToken.None);
        Assert.Null(await cache.GetAsync<PurchaseOrderResponse>("purchase-order:7", CancellationToken.None));
    }

    [Fact]
    public async Task GetAsync_does_not_swallow_cancellation()
    {
        var cancellationToken = new CancellationToken(canceled: true);
        var distributed = new Mock<IDistributedCache>();
        distributed.Setup(value => value.GetAsync(It.IsAny<string>(), It.IsAny<CancellationToken>()))
            .ThrowsAsync(new OperationCanceledException(cancellationToken));
        var cache = new DistributedProcurementCache(distributed.Object, NullLogger<DistributedProcurementCache>.Instance);

        await Assert.ThrowsAsync<OperationCanceledException>(
            () => cache.GetAsync<SupplierResponse>("key", cancellationToken));
    }

    [Fact]
    public async Task SetAsync_does_not_swallow_cancellation()
    {
        var cancellationToken = new CancellationToken(canceled: true);
        var distributed = new Mock<IDistributedCache>();
        distributed.Setup(value => value.SetAsync(
                It.IsAny<string>(),
                It.IsAny<byte[]>(),
                It.IsAny<DistributedCacheEntryOptions>(),
                It.IsAny<CancellationToken>()))
            .ThrowsAsync(new OperationCanceledException(cancellationToken));
        var cache = new DistributedProcurementCache(distributed.Object, NullLogger<DistributedProcurementCache>.Instance);

        await Assert.ThrowsAsync<OperationCanceledException>(
            () => cache.SetAsync("key", new SupplierResponse(42, "Legacy", null, null, null, null, null, null, null, null, null, null), TimeSpan.FromMinutes(1), cancellationToken));
    }

    [Fact]
    public async Task RemoveAsync_does_not_swallow_cancellation()
    {
        var cancellationToken = new CancellationToken(canceled: true);
        var distributed = new Mock<IDistributedCache>();
        distributed.Setup(value => value.RemoveAsync(It.IsAny<string>(), It.IsAny<CancellationToken>()))
            .ThrowsAsync(new OperationCanceledException(cancellationToken));
        var cache = new DistributedProcurementCache(distributed.Object, NullLogger<DistributedProcurementCache>.Instance);

        await Assert.ThrowsAsync<OperationCanceledException>(() => cache.RemoveAsync("key", cancellationToken));
    }
}

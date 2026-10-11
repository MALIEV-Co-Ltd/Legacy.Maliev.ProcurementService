using System.Data;
using System.Security.Cryptography;
using System.Text.Json;
using Legacy.Maliev.ProcurementService.Application.Interfaces;
using Legacy.Maliev.ProcurementService.Application.Models;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Infrastructure;
using Npgsql;

namespace Legacy.Maliev.ProcurementService.Data;

/// <summary>Default-off atomic child receipts; root receipts and cache arbitration are independent.</summary>
public sealed class DurableProcurementChildCreates(PurchaseOrderDbContext orders, TimeProvider clock) : IDurableProcurementChildCreates
{
    /// <inheritdoc />
    public Task<DurableCreateResult> CreateItemAsync(UpsertOrderItemRequest request, CreateReceiptBinding binding, Func<OrderItemResponse, byte[]> capture, CancellationToken token) =>
        ExecuteAsync<OrderItemChildReceiptRecord>(binding, "OrderItemCreateReceipt", 3, request.PurchaseOrderId, false, async context =>
        {
            var value = await new PurchaseOrderRepository(context, clock).CreateOrderItemAsync(request, token);
            return new DurableCreateResponse(value.Id, capture(value));
        }, token);

    /// <inheritdoc />
    public Task<DurableCreateResult> CreateFileAsync(int purchaseOrderId, string bucket, string objectName, CreateReceiptBinding binding, Func<PurchaseOrderFileResponse, byte[]> capture, CancellationToken token) =>
        ExecuteAsync<FileChildReceiptRecord>(binding, "PurchaseOrderFileCreateReceipt", 4, purchaseOrderId, true, async context =>
        {
            var value = await new PurchaseOrderRepository(context, clock).CreateFileAsync(purchaseOrderId, bucket, objectName, token);
            return value is null ? null : new DurableCreateResponse(value.Id, capture(value));
        }, token);

    private PurchaseOrderDbContext Fresh() => new((DbContextOptions<PurchaseOrderDbContext>)orders.GetService<IDbContextOptions>());
    private async Task<DurableCreateResult> ExecuteAsync<TReceipt>(CreateReceiptBinding binding, string table, short operation, int? originalParent, bool file,
        Func<PurchaseOrderDbContext, Task<DurableCreateResponse?>> create, CancellationToken token) where TReceipt : class, new()
    {
        if (binding.Operation != operation) return Unavailable();
        try
        {
            await using var strategyContext = Fresh();
            return await strategyContext.Database.CreateExecutionStrategy().ExecuteAsync(async () =>
            {
                var submitted = false;
                var rollbackUnconfirmed = false;
                try
                {
                    await using var context = Fresh();
                    if (!await ReceiptReadiness.IsReadyAsync(context, table, operation, token)) return Unavailable();
                    await using var transaction = await context.Database.BeginTransactionAsync(IsolationLevel.RepeatableRead, token);
                    rollbackUnconfirmed = true;
                    try
                    {
                        var prior = await ProbeAsync<TReceipt>(context, binding, originalParent, file, token);
                        if (prior is not null) return prior;
                        var response = await create(context);
                        if (response is null)
                        {
                            await transaction.RollbackAsync(token);
                            rollbackUnconfirmed = false;
                            return new DurableCreateResult(DurableCreateStatus.NotFound);
                        }
                        var receipt = new TReceipt();
                        context.Add(receipt);
                        var entry = context.Entry(receipt);
                        entry.Property("IssuerDigest").CurrentValue = binding.IssuerDigest;
                        entry.Property("SubjectDigest").CurrentValue = binding.SubjectDigest;
                        entry.Property("Operation").CurrentValue = operation;
                        entry.Property("KeyDigest").CurrentValue = binding.KeyDigest;
                        entry.Property("CanonicalVersion").CurrentValue = binding.CanonicalVersion;
                        entry.Property("PayloadDigest").CurrentValue = binding.PayloadDigest;
                        entry.Property("EntityId").CurrentValue = response.EntityId;
                        entry.Property("ResponseVersion").CurrentValue = (short)1;
                        entry.Property("ResponseBody").CurrentValue = response.Body;
                        entry.Property("ResponseDigest").CurrentValue = SHA256.HashData(response.Body);
                        entry.Property("CreatedAtUtc").CurrentValue = clock.GetUtcNow();
                        await context.SaveChangesAsync(token);
                        token.ThrowIfCancellationRequested();
                        submitted = true;
                        await transaction.CommitAsync(token);
                        return new DurableCreateResult(DurableCreateStatus.CreatedOrReplayed, response);
                    }
                    catch (Exception error) when (!submitted)
                    {
                        using var cleanup = new CancellationTokenSource(TimeSpan.FromSeconds(5));
                        await transaction.RollbackAsync(cleanup.Token);
                        rollbackUnconfirmed = false;
                        if (error is DbUpdateException { InnerException: PostgresException { SqlState: PostgresErrorCodes.UniqueViolation } postgres }
                            && string.Equals(postgres.ConstraintName, $"PK_{table}", StringComparison.Ordinal)) throw new ReceiptCollisionException();
                        throw;
                    }
                }
                catch when (submitted || rollbackUnconfirmed) { throw new OutcomeUncertainException(); }
            });
        }
        catch (Exception error) when (error is OutcomeUncertainException or ReceiptCollisionException)
        {
            token.ThrowIfCancellationRequested();
            using var deadline = new CancellationTokenSource(TimeSpan.FromSeconds(5));
            using var probeToken = CancellationTokenSource.CreateLinkedTokenSource(token, deadline.Token);
            try
            {
                await using var strategyContext = Fresh();
                // Retry-enabled EF providers require the read-only snapshot transaction inside their strategy too.
                return await strategyContext.Database.CreateExecutionStrategy().ExecuteAsync(async probeCancellation =>
                {
                    await using var context = Fresh();
                    if (!await ReceiptReadiness.IsReadyAsync(context, table, operation, probeCancellation)) return Unavailable();
                    await using var transaction = await context.Database.BeginTransactionAsync(IsolationLevel.RepeatableRead, probeCancellation);
                    return await ProbeAsync<TReceipt>(context, binding, originalParent, file, probeCancellation) ?? Unavailable();
                }, probeToken.Token);
            }
            catch (OperationCanceledException) when (token.IsCancellationRequested) { throw; }
            catch { return Unavailable(); }
        }
        catch (OperationCanceledException) when (token.IsCancellationRequested) { throw; }
        catch { return Unavailable(); }
    }

    private static async Task<DurableCreateResult?> ProbeAsync<TReceipt>(PurchaseOrderDbContext context, CreateReceiptBinding binding, int? originalParent, bool file, CancellationToken token) where TReceipt : class
    {
        var receipt = await context.Set<TReceipt>().AsNoTracking().Where(value =>
            EF.Property<byte[]>(value, "IssuerDigest") == binding.IssuerDigest && EF.Property<byte[]>(value, "SubjectDigest") == binding.SubjectDigest
            && EF.Property<short>(value, "Operation") == binding.Operation && EF.Property<byte[]>(value, "KeyDigest") == binding.KeyDigest)
            .Select(value => new ReceiptData(EF.Property<short>(value, "CanonicalVersion"), EF.Property<byte[]>(value, "PayloadDigest"), EF.Property<short>(value, "ResponseVersion"),
                EF.Property<int>(value, "EntityId"), EF.Property<byte[]>(value, "ResponseBody"), EF.Property<byte[]>(value, "ResponseDigest"))).SingleOrDefaultAsync(token);
        if (receipt is null) return null;
        // The matched canonical effective request, not an omitted JSON property, proves original ownership.
        if (receipt.CanonicalVersion != binding.CanonicalVersion || !CryptographicOperations.FixedTimeEquals(receipt.PayloadDigest, binding.PayloadDigest)) return new(DurableCreateStatus.Conflict);
        if (receipt.ResponseVersion != 1 || receipt.EntityId <= 0 || !CryptographicOperations.FixedTimeEquals(SHA256.HashData(receipt.Body), receipt.ResponseDigest)
            || !ResponseAssociationIsValid(receipt.Body, receipt.EntityId, originalParent, file)) return Unavailable();
        var association = file
            ? await context.Files.AsNoTracking().Where(value => value.Id == receipt.EntityId).Select(value => new Association(value.PurchaseOrderId)).SingleOrDefaultAsync(token)
            : await context.OrderItems.AsNoTracking().Where(value => value.Id == receipt.EntityId).Select(value => new Association(value.PurchaseOrderId)).SingleOrDefaultAsync(token);
        if (association is null || association.Parent != originalParent || (originalParent is not null && !await context.PurchaseOrders.AnyAsync(value => value.Id == originalParent, token)))
            return new(DurableCreateStatus.Conflict);
        return new(DurableCreateStatus.CreatedOrReplayed, new(receipt.EntityId, receipt.Body));
    }

    private static bool ResponseAssociationIsValid(byte[] body, int id, int? parent, bool file)
    {
        try
        {
            using var document = JsonDocument.Parse(body);
            if (document.RootElement.ValueKind != JsonValueKind.Object) return false;
            var properties = document.RootElement.EnumerateObject().ToArray();
            if (properties.Select(value => value.Name).Distinct(StringComparer.Ordinal).Count() != properties.Length) return false;
            if (properties.Any(value => (string.Equals(value.Name, "Id", StringComparison.OrdinalIgnoreCase) && value.Name != "Id")
                || (string.Equals(value.Name, "PurchaseOrderId", StringComparison.OrdinalIgnoreCase) && value.Name != "PurchaseOrderId"))) return false;
            if (!document.RootElement.TryGetProperty("Id", out var entity) || !entity.TryGetInt32(out var actualId) || actualId != id) return false;
            var serializer = new JsonSerializerOptions { UnmappedMemberHandling = System.Text.Json.Serialization.JsonUnmappedMemberHandling.Disallow };
            if (file)
            {
                var response = JsonSerializer.Deserialize<PurchaseOrderFileResponse>(body, serializer);
                if (response is null || string.IsNullOrWhiteSpace(response.Bucket) || string.IsNullOrWhiteSpace(response.ObjectName)) return false;
            }
            else if (JsonSerializer.Deserialize<OrderItemResponse>(body, serializer) is null) return false;
            if (!document.RootElement.TryGetProperty("PurchaseOrderId", out var owner)) return !file && parent is null;
            if (owner.ValueKind == JsonValueKind.Null) return !file && parent is null;
            return owner.TryGetInt32(out var actualParent) && parent is not null && actualParent == parent;
        }
        catch (Exception error) when (error is JsonException or InvalidOperationException or FormatException) { return false; }
    }
    private sealed record ReceiptData(short CanonicalVersion, byte[] PayloadDigest, short ResponseVersion, int EntityId, byte[] Body, byte[] ResponseDigest);
    private sealed record Association(int? Parent);
    private static DurableCreateResult Unavailable() => new(DurableCreateStatus.Unavailable);
    private sealed class OutcomeUncertainException : Exception;
    private sealed class ReceiptCollisionException : Exception;
}

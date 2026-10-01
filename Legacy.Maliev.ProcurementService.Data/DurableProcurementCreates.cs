using System.Security.Cryptography;
using System.Text.Json;
using Legacy.Maliev.ProcurementService.Application.Interfaces;
using Legacy.Maliev.ProcurementService.Application.Models;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Infrastructure;
using Npgsql;

namespace Legacy.Maliev.ProcurementService.Data;

/// <summary>Durable root creates within each independently owned database.</summary>
public sealed class DurableProcurementCreates(SupplierDbContext suppliers, PurchaseOrderDbContext orders, TimeProvider clock) : IDurableProcurementCreates
{
    /// <inheritdoc />
    public Task<DurableCreateResult> CreateSupplierAsync(UpsertSupplierRequest request, CreateReceiptBinding binding, Func<SupplierResponse, byte[]> capture, CancellationToken token)
    {
        var options = (DbContextOptions<SupplierDbContext>)suppliers.GetService<IDbContextOptions>();
        return ExecuteAsync(() => new SupplierDbContext(options), binding, "SupplierCreateReceipt", async context =>
        {
            var value = await new SupplierRepository(context, clock).CreateSupplierAsync(request, token);
            return new DurableCreateResponse(value.Id, capture(value));
        }, token);
    }

    /// <inheritdoc />
    public Task<DurableCreateResult> CreatePurchaseOrderAsync(UpsertPurchaseOrderRequest request, CreateReceiptBinding binding, Func<PurchaseOrderResponse, byte[]> capture, CancellationToken token)
    {
        var options = (DbContextOptions<PurchaseOrderDbContext>)orders.GetService<IDbContextOptions>();
        return ExecuteAsync(() => new PurchaseOrderDbContext(options), binding, "PurchaseOrderCreateReceipt", async context =>
        {
            var value = await new PurchaseOrderRepository(context, clock).CreatePurchaseOrderAsync(request, token);
            return new DurableCreateResponse(value.Id, capture(value));
        }, token);
    }

    private async Task<DurableCreateResult> ExecuteAsync<TContext>(Func<TContext> fresh, CreateReceiptBinding binding, string table,
        Func<TContext, Task<DurableCreateResponse>> create, CancellationToken token) where TContext : DbContext
    {
        try
        {
            await using var strategyContext = fresh();
            return await strategyContext.Database.CreateExecutionStrategy().ExecuteAsync(async () =>
            {
                var submitted = false;
                var rollbackUnconfirmed = false;
                try
                {
                    await using var context = fresh();
                    if (!await ReceiptReadiness.IsReadyAsync(context, table, binding.Operation, token)) return Unavailable();
                    var prior = await ProbeAsync(context, binding, token);
                    if (prior is not null) return prior;
                    await using var transaction = await context.Database.BeginTransactionAsync(token);
                    rollbackUnconfirmed = true;
                    try
                    {
                        var response = await create(context);
                        context.Set<CreateReceiptRecord>().Add(new()
                        {
                            IssuerDigest = binding.IssuerDigest,
                            SubjectDigest = binding.SubjectDigest,
                            Operation = binding.Operation,
                            KeyDigest = binding.KeyDigest,
                            CanonicalVersion = binding.CanonicalVersion,
                            PayloadDigest = binding.PayloadDigest,
                            EntityId = response.EntityId,
                            ResponseVersion = 1,
                            ResponseBody = response.Body,
                            ResponseDigest = SHA256.HashData(response.Body),
                            CreatedAtUtc = clock.GetUtcNow()
                        });
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
                        if (IsReceiptCollision(error, table)) throw new ReceiptCollisionException();
                        throw;
                    }
                }
                catch when (submitted || rollbackUnconfirmed)
                {
                    // Includes rollback failure and asynchronous transaction/context disposal.
                    throw new OutcomeUncertainException();
                }
            });
        }
        catch (Exception error) when (error is OutcomeUncertainException or ReceiptCollisionException)
        {
            token.ThrowIfCancellationRequested();
            using var deadline = new CancellationTokenSource(TimeSpan.FromSeconds(5));
            using var probeToken = CancellationTokenSource.CreateLinkedTokenSource(token, deadline.Token);
            try
            {
                await using var context = fresh();
                if (!await ReceiptReadiness.IsReadyAsync(context, table, binding.Operation, probeToken.Token)) return Unavailable();
                return await ProbeAsync(context, binding, probeToken.Token) ?? Unavailable();
            }
            catch (OperationCanceledException) when (token.IsCancellationRequested) { throw; }
            catch { return Unavailable(); }
        }
        catch (OperationCanceledException) when (token.IsCancellationRequested) { throw; }
        catch { return Unavailable(); }
    }

    private static bool IsReceiptCollision(Exception error, string table) =>
        error is DbUpdateException { InnerException: PostgresException { SqlState: PostgresErrorCodes.UniqueViolation } postgres }
        && string.Equals(postgres.ConstraintName, $"PK_{table}", StringComparison.Ordinal);

    private static async Task<DurableCreateResult?> ProbeAsync(DbContext context, CreateReceiptBinding binding, CancellationToken token)
    {
        var receipt = await context.Set<CreateReceiptRecord>().AsNoTracking().SingleOrDefaultAsync(value =>
            value.IssuerDigest == binding.IssuerDigest && value.SubjectDigest == binding.SubjectDigest
            && value.Operation == binding.Operation && value.KeyDigest == binding.KeyDigest, token);
        if (receipt is null) return null;
        if (receipt.CanonicalVersion != binding.CanonicalVersion || !CryptographicOperations.FixedTimeEquals(receipt.PayloadDigest, binding.PayloadDigest))
            return new(DurableCreateStatus.Conflict);
        if (receipt.ResponseVersion != 1 || receipt.EntityId <= 0 || !CryptographicOperations.FixedTimeEquals(SHA256.HashData(receipt.ResponseBody), receipt.ResponseDigest)) return Unavailable();
        try
        {
            using var document = JsonDocument.Parse(receipt.ResponseBody);
            if (document.RootElement.ValueKind != JsonValueKind.Object || document.RootElement.GetProperty("Id").GetInt32() != receipt.EntityId) return Unavailable();
        }
        catch (Exception error) when (error is JsonException or InvalidOperationException or KeyNotFoundException or FormatException) { return Unavailable(); }
        return new(DurableCreateStatus.CreatedOrReplayed, new(receipt.EntityId, receipt.ResponseBody));
    }

    private static DurableCreateResult Unavailable() => new(DurableCreateStatus.Unavailable);
    private sealed class OutcomeUncertainException : Exception;
    private sealed class ReceiptCollisionException : Exception;
}

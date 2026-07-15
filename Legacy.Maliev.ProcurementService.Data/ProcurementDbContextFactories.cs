using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Design;

namespace Legacy.Maliev.ProcurementService.Data;

/// <summary>Design-time Supplier database context factory.</summary>
public sealed class SupplierDbContextFactory : IDesignTimeDbContextFactory<SupplierDbContext>
{
    /// <inheritdoc />
    public SupplierDbContext CreateDbContext(string[] args) => new(new DbContextOptionsBuilder<SupplierDbContext>()
        .UseNpgsql(Require("ConnectionStrings__SupplierDbContext")).Options);

    private static string Require(string name) => Environment.GetEnvironmentVariable(name)
        ?? throw new InvalidOperationException($"{name} is required for migration commands.");
}

/// <summary>Design-time PurchaseOrder database context factory.</summary>
public sealed class PurchaseOrderDbContextFactory : IDesignTimeDbContextFactory<PurchaseOrderDbContext>
{
    /// <inheritdoc />
    public PurchaseOrderDbContext CreateDbContext(string[] args) => new(new DbContextOptionsBuilder<PurchaseOrderDbContext>()
        .UseNpgsql(Require("ConnectionStrings__PurchaseOrderDbContext")).Options);

    private static string Require(string name) => Environment.GetEnvironmentVariable(name)
        ?? throw new InvalidOperationException($"{name} is required for migration commands.");
}

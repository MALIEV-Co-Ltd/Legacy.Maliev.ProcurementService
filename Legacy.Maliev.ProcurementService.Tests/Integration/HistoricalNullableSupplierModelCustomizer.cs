using Legacy.Maliev.ProcurementService.Data;
using Legacy.Maliev.ProcurementService.Domain;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Infrastructure;

namespace Legacy.Maliev.ProcurementService.Tests.Integration;

/// <summary>Read-only historical nullable-Name characterization; never a production model configuration.</summary>
public sealed class HistoricalNullableSupplierModelCustomizer(ModelCustomizerDependencies dependencies)
    : RelationalModelCustomizer(dependencies)
{
    public override void Customize(ModelBuilder modelBuilder, DbContext context)
    {
        base.Customize(modelBuilder, context);
        if (context is SupplierDbContext)
            modelBuilder.Entity<Supplier>().Property(value => value.Name).IsRequired(false);
    }
}

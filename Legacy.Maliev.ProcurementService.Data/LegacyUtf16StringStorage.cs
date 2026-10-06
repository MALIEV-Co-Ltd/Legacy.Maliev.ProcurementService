using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Metadata;
using Microsoft.EntityFrameworkCore.Metadata.Builders;

namespace Legacy.Maliev.ProcurementService.Data;

/// <summary>Preserves source SQL Server Unicode length limits in PostgreSQL without modifying literals.</summary>
internal static class LegacyUtf16StringStorage
{
    internal static void Configure<TEntity>(EntityTypeBuilder<TEntity> entity, string tableName) where TEntity : class
    {
        var properties = entity.Metadata.GetProperties()
            .Where(property => property.ClrType == typeof(string) && property.GetMaxLength() is > 0)
            .OrderBy(property => property.Name, StringComparer.Ordinal)
            .ToArray();
        entity.ToTable(tableName, table =>
        {
            foreach (var property in properties)
            {
                string column = property.GetColumnName(StoreObjectIdentifier.Table(tableName, null))!;
                int limit = property.GetMaxLength()!.Value;
                // PostgreSQL counts Unicode scalar values; each supplementary scalar is two UTF16 units.
                string sql = $"""char_length("{column}") + char_length(regexp_replace("{column}", U&'[^\+010000-\+10FFFF]', '', 'g')) <= {limit}""";
                table.HasCheckConstraint($"CK_{tableName}_{column}_UTF16", sql);
            }
        });
    }
}

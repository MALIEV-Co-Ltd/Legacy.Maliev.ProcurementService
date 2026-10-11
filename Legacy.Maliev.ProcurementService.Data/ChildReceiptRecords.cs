using Microsoft.EntityFrameworkCore;

namespace Legacy.Maliev.ProcurementService.Data;

internal sealed class OrderItemChildReceiptRecord
{
    public byte[] IssuerDigest { get; set; } = [];
    public byte[] SubjectDigest { get; set; } = [];
    public short Operation { get; set; }
    public byte[] KeyDigest { get; set; } = [];
    public short CanonicalVersion { get; set; }
    public byte[] PayloadDigest { get; set; } = [];
    public short ResponseVersion { get; set; }
    public int EntityId { get; set; }
    public byte[] ResponseBody { get; set; } = [];
    public byte[] ResponseDigest { get; set; } = [];
    public DateTimeOffset CreatedAtUtc { get; set; }
}

internal sealed class FileChildReceiptRecord
{
    public byte[] IssuerDigest { get; set; } = [];
    public byte[] SubjectDigest { get; set; } = [];
    public short Operation { get; set; }
    public byte[] KeyDigest { get; set; } = [];
    public short CanonicalVersion { get; set; }
    public byte[] PayloadDigest { get; set; } = [];
    public short ResponseVersion { get; set; }
    public int EntityId { get; set; }
    public byte[] ResponseBody { get; set; } = [];
    public byte[] ResponseDigest { get; set; } = [];
    public DateTimeOffset CreatedAtUtc { get; set; }
}

internal static class ChildReceiptSchema
{
    internal static void Configure<TEntity>(ModelBuilder builder, string table, short operation) where TEntity : class
    {
        var entity = builder.Entity<TEntity>();
        entity.ToTable(table, options =>
        {
            foreach (var check in CreateReceiptSchema.Checks(table, operation)) options.HasCheckConstraint(check.Key, check.Value);
        });
        entity.HasKey("IssuerDigest", "SubjectDigest", "Operation", "KeyDigest").HasName($"PK_{table}");
        foreach (var property in new[] { "IssuerDigest", "SubjectDigest", "KeyDigest", "PayloadDigest", "ResponseBody", "ResponseDigest" }) entity.Property<byte[]>(property).IsRequired();
    }
}
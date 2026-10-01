using Microsoft.EntityFrameworkCore;

namespace Legacy.Maliev.ProcurementService.Data;

internal sealed class CreateReceiptRecord
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

internal static class CreateReceiptSchema
{
    public static IReadOnlyDictionary<string, string> Checks(string table, short operation) => new Dictionary<string, string>
    {
        [$"CK_{table}_Digests"] = "octet_length(\"IssuerDigest\") = 32 AND octet_length(\"SubjectDigest\") = 32 AND octet_length(\"KeyDigest\") = 32 AND octet_length(\"PayloadDigest\") = 32 AND octet_length(\"ResponseDigest\") = 32",
        [$"CK_{table}_Operation"] = $"\"Operation\" = {operation}",
        [$"CK_{table}_Versions"] = "\"CanonicalVersion\" = 1 AND \"ResponseVersion\" = 1",
        [$"CK_{table}_Complete"] = "\"EntityId\" > 0 AND octet_length(\"ResponseBody\") > 0"
    };

    public static void Configure(ModelBuilder builder, string table, short operation)
    {
        var entity = builder.Entity<CreateReceiptRecord>();
        entity.ToTable(table, options =>
        {
            foreach (var check in Checks(table, operation)) options.HasCheckConstraint(check.Key, check.Value);
        });
        entity.HasKey(value => new { value.IssuerDigest, value.SubjectDigest, value.Operation, value.KeyDigest }).HasName($"PK_{table}");
        entity.Property(value => value.IssuerDigest).IsRequired();
        entity.Property(value => value.SubjectDigest).IsRequired();
        entity.Property(value => value.KeyDigest).IsRequired();
        entity.Property(value => value.PayloadDigest).IsRequired();
        entity.Property(value => value.ResponseBody).IsRequired();
        entity.Property(value => value.ResponseDigest).IsRequired();
    }
}

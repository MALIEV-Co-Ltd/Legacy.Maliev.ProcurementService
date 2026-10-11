using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace Legacy.Maliev.ProcurementService.Data.Migrations.PurchaseOrder;

/// <summary>Adds separate immutable child receipt tables; activation is a separate rollout decision.</summary>
public partial class AddDurablePurchaseOrderChildReceipts : Migration
{
    /// <inheritdoc />
    protected override void Up(MigrationBuilder migrationBuilder)
    {
        AddReceipt(migrationBuilder, "OrderItemCreateReceipt", 3);
        AddReceipt(migrationBuilder, "PurchaseOrderFileCreateReceipt", 4);
    }
    private static void AddReceipt(MigrationBuilder migrationBuilder, string table, short operation)
    {
        migrationBuilder.CreateTable(
            name: table,
            columns: columns => new
            {
                IssuerDigest = columns.Column<byte[]>(type: "bytea", nullable: false),
                SubjectDigest = columns.Column<byte[]>(type: "bytea", nullable: false),
                Operation = columns.Column<short>(type: "smallint", nullable: false),
                KeyDigest = columns.Column<byte[]>(type: "bytea", nullable: false),
                CanonicalVersion = columns.Column<short>(type: "smallint", nullable: false),
                PayloadDigest = columns.Column<byte[]>(type: "bytea", nullable: false),
                ResponseVersion = columns.Column<short>(type: "smallint", nullable: false),
                EntityId = columns.Column<int>(type: "integer", nullable: false),
                ResponseBody = columns.Column<byte[]>(type: "bytea", nullable: false),
                ResponseDigest = columns.Column<byte[]>(type: "bytea", nullable: false),
                CreatedAtUtc = columns.Column<DateTimeOffset>(type: "timestamp with time zone", nullable: false)
            },
            constraints: columns =>
            {
                columns.PrimaryKey($"PK_{table}", value => new { value.IssuerDigest, value.SubjectDigest, value.Operation, value.KeyDigest });
                columns.CheckConstraint($"CK_{table}_Digests", "octet_length(\"IssuerDigest\") = 32 AND octet_length(\"SubjectDigest\") = 32 AND octet_length(\"KeyDigest\") = 32 AND octet_length(\"PayloadDigest\") = 32 AND octet_length(\"ResponseDigest\") = 32");
                columns.CheckConstraint($"CK_{table}_Operation", $"\"Operation\" = {operation}");
                columns.CheckConstraint($"CK_{table}_Versions", "\"CanonicalVersion\" = 1 AND \"ResponseVersion\" = 1");
                columns.CheckConstraint($"CK_{table}_Complete", "\"EntityId\" > 0 AND octet_length(\"ResponseBody\") > 0");
            });
    }
    /// <inheritdoc />
    protected override void Down(MigrationBuilder migrationBuilder) =>
        throw new InvalidOperationException("Durable child receipts cannot be removed by migration rollback.");
}
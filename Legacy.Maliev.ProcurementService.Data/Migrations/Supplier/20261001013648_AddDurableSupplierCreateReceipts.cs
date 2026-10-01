using System;
using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace Legacy.Maliev.ProcurementService.Data.Migrations.Supplier
{
    /// <inheritdoc />
    public partial class AddDurableSupplierCreateReceipts : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.CreateTable(
                name: "SupplierCreateReceipt",
                columns: table => new
                {
                    IssuerDigest = table.Column<byte[]>(type: "bytea", nullable: false),
                    SubjectDigest = table.Column<byte[]>(type: "bytea", nullable: false),
                    Operation = table.Column<short>(type: "smallint", nullable: false),
                    KeyDigest = table.Column<byte[]>(type: "bytea", nullable: false),
                    CanonicalVersion = table.Column<short>(type: "smallint", nullable: false),
                    PayloadDigest = table.Column<byte[]>(type: "bytea", nullable: false),
                    ResponseVersion = table.Column<short>(type: "smallint", nullable: false),
                    EntityId = table.Column<int>(type: "integer", nullable: false),
                    ResponseBody = table.Column<byte[]>(type: "bytea", nullable: false),
                    ResponseDigest = table.Column<byte[]>(type: "bytea", nullable: false),
                    CreatedAtUtc = table.Column<DateTimeOffset>(type: "timestamp with time zone", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_SupplierCreateReceipt", x => new { x.IssuerDigest, x.SubjectDigest, x.Operation, x.KeyDigest });
                    table.CheckConstraint("CK_SupplierCreateReceipt_Complete", "\"EntityId\" > 0 AND octet_length(\"ResponseBody\") > 0");
                    table.CheckConstraint("CK_SupplierCreateReceipt_Digests", "octet_length(\"IssuerDigest\") = 32 AND octet_length(\"SubjectDigest\") = 32 AND octet_length(\"KeyDigest\") = 32 AND octet_length(\"PayloadDigest\") = 32 AND octet_length(\"ResponseDigest\") = 32");
                    table.CheckConstraint("CK_SupplierCreateReceipt_Operation", "\"Operation\" = 1");
                    table.CheckConstraint("CK_SupplierCreateReceipt_Versions", "\"CanonicalVersion\" = 1 AND \"ResponseVersion\" = 1");
                });
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            throw new InvalidOperationException("Durable create receipts cannot be removed by migration rollback.");
        }
    }
}

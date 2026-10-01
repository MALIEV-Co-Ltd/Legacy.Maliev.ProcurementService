using System;
using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace Legacy.Maliev.ProcurementService.Data.Migrations.PurchaseOrder
{
    /// <inheritdoc />
    public partial class AddDurablePurchaseOrderCreateReceipts : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.CreateTable(
                name: "PurchaseOrderCreateReceipt",
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
                    table.PrimaryKey("PK_PurchaseOrderCreateReceipt", x => new { x.IssuerDigest, x.SubjectDigest, x.Operation, x.KeyDigest });
                    table.CheckConstraint("CK_PurchaseOrderCreateReceipt_Complete", "\"EntityId\" > 0 AND octet_length(\"ResponseBody\") > 0");
                    table.CheckConstraint("CK_PurchaseOrderCreateReceipt_Digests", "octet_length(\"IssuerDigest\") = 32 AND octet_length(\"SubjectDigest\") = 32 AND octet_length(\"KeyDigest\") = 32 AND octet_length(\"PayloadDigest\") = 32 AND octet_length(\"ResponseDigest\") = 32");
                    table.CheckConstraint("CK_PurchaseOrderCreateReceipt_Operation", "\"Operation\" = 2");
                    table.CheckConstraint("CK_PurchaseOrderCreateReceipt_Versions", "\"CanonicalVersion\" = 1 AND \"ResponseVersion\" = 1");
                });
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            throw new InvalidOperationException("Durable create receipts cannot be removed by migration rollback.");
        }
    }
}

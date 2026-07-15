using System;
using Microsoft.EntityFrameworkCore.Migrations;
using Npgsql.EntityFrameworkCore.PostgreSQL.Metadata;

#nullable disable

namespace Legacy.Maliev.ProcurementService.Data.Migrations.PurchaseOrder
{
    /// <inheritdoc />
    public partial class InitialPurchaseOrderPostgresCompatibility : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.CreateTable(
                name: "Address",
                columns: table => new
                {
                    ID = table.Column<int>(type: "integer", nullable: false)
                        .Annotation("Npgsql:ValueGenerationStrategy", NpgsqlValueGenerationStrategy.IdentityByDefaultColumn),
                    Building = table.Column<string>(type: "character varying(256)", maxLength: 256, nullable: true),
                    AddressLine1 = table.Column<string>(type: "character varying(256)", maxLength: 256, nullable: false),
                    AddressLine2 = table.Column<string>(type: "character varying(256)", maxLength: 256, nullable: true),
                    City = table.Column<string>(type: "character varying(256)", maxLength: 256, nullable: true),
                    State = table.Column<string>(type: "character varying(256)", maxLength: 256, nullable: true),
                    PostalCode = table.Column<string>(type: "character varying(256)", maxLength: 256, nullable: true),
                    CountryID = table.Column<int>(type: "integer", nullable: false),
                    CreatedDate = table.Column<DateTime>(type: "timestamp with time zone", nullable: true, defaultValueSql: "CURRENT_TIMESTAMP"),
                    ModifiedDate = table.Column<DateTime>(type: "timestamp with time zone", nullable: true, defaultValueSql: "CURRENT_TIMESTAMP")
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_Address", x => x.ID);
                });

            migrationBuilder.CreateTable(
                name: "PurchaseOrder",
                columns: table => new
                {
                    ID = table.Column<int>(type: "integer", nullable: false)
                        .Annotation("Npgsql:ValueGenerationStrategy", NpgsqlValueGenerationStrategy.IdentityByDefaultColumn),
                    SupplierID = table.Column<int>(type: "integer", nullable: true),
                    SupplierContactPerson = table.Column<string>(type: "character varying(256)", maxLength: 256, nullable: true),
                    ShippingAddressID = table.Column<int>(type: "integer", nullable: true),
                    ShippingContactPerson = table.Column<string>(type: "character varying(256)", maxLength: 256, nullable: true),
                    ShippingTelephone = table.Column<string>(type: "character varying(256)", maxLength: 256, nullable: true),
                    ShippingMobile = table.Column<string>(type: "character varying(256)", maxLength: 256, nullable: true),
                    ShippingFax = table.Column<string>(type: "character varying(256)", maxLength: 256, nullable: true),
                    BillingAddressID = table.Column<int>(type: "integer", nullable: true),
                    BillingContactPerson = table.Column<string>(type: "character varying(256)", maxLength: 256, nullable: true),
                    BillingTelephone = table.Column<string>(type: "character varying(256)", maxLength: 256, nullable: true),
                    BillingMobile = table.Column<string>(type: "character varying(256)", maxLength: 256, nullable: true),
                    BillingFax = table.Column<string>(type: "character varying(256)", maxLength: 256, nullable: true),
                    FOB = table.Column<string>(type: "text", nullable: true),
                    Terms = table.Column<string>(type: "character varying(256)", maxLength: 256, nullable: true),
                    ShippingMethod = table.Column<string>(type: "character varying(256)", maxLength: 256, nullable: true),
                    EmployeeID = table.Column<int>(type: "integer", nullable: true),
                    Notes = table.Column<string>(type: "text", nullable: true),
                    CreatedDate = table.Column<DateTime>(type: "timestamp with time zone", nullable: true, defaultValueSql: "CURRENT_TIMESTAMP"),
                    ModifiedDate = table.Column<DateTime>(type: "timestamp with time zone", nullable: true, defaultValueSql: "CURRENT_TIMESTAMP")
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_PurchaseOrder", x => x.ID);
                    table.ForeignKey(
                        name: "FK_PurchaseOrder_Address",
                        column: x => x.ShippingAddressID,
                        principalTable: "Address",
                        principalColumn: "ID");
                    table.ForeignKey(
                        name: "FK_PurchaseOrder_Address1",
                        column: x => x.BillingAddressID,
                        principalTable: "Address",
                        principalColumn: "ID");
                });

            migrationBuilder.CreateTable(
                name: "OrderItem",
                columns: table => new
                {
                    ID = table.Column<int>(type: "integer", nullable: false)
                        .Annotation("Npgsql:ValueGenerationStrategy", NpgsqlValueGenerationStrategy.IdentityByDefaultColumn),
                    PurchaseOrderID = table.Column<int>(type: "integer", nullable: true),
                    PartNumber = table.Column<string>(type: "character varying(100)", maxLength: 100, nullable: true),
                    Description = table.Column<string>(type: "text", nullable: true),
                    Quantity = table.Column<int>(type: "integer", nullable: true),
                    UnitPrice = table.Column<decimal>(type: "numeric(18,2)", nullable: true),
                    Subtotal = table.Column<decimal>(type: "numeric(18,2)", nullable: true, computedColumnSql: "(\"UnitPrice\" * \"Quantity\")::numeric(18,2)", stored: true),
                    CreatedDate = table.Column<DateTime>(type: "timestamp with time zone", nullable: true, defaultValueSql: "CURRENT_TIMESTAMP"),
                    ModifiedDate = table.Column<DateTime>(type: "timestamp with time zone", nullable: true, defaultValueSql: "CURRENT_TIMESTAMP")
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_OrderItem", x => x.ID);
                    table.ForeignKey(
                        name: "FK_OrderItem_PurchaseOrder",
                        column: x => x.PurchaseOrderID,
                        principalTable: "PurchaseOrder",
                        principalColumn: "ID");
                });

            migrationBuilder.CreateTable(
                name: "PurchaseOrderFile",
                columns: table => new
                {
                    ID = table.Column<int>(type: "integer", nullable: false)
                        .Annotation("Npgsql:ValueGenerationStrategy", NpgsqlValueGenerationStrategy.IdentityByDefaultColumn),
                    PurchaseOrderID = table.Column<int>(type: "integer", nullable: false),
                    Bucket = table.Column<string>(type: "character varying(50)", maxLength: 50, nullable: false),
                    ObjectName = table.Column<string>(type: "text", nullable: false),
                    CreatedDate = table.Column<DateTime>(type: "timestamp with time zone", nullable: true, defaultValueSql: "CURRENT_TIMESTAMP"),
                    ModifiedDate = table.Column<DateTime>(type: "timestamp with time zone", nullable: true, defaultValueSql: "CURRENT_TIMESTAMP")
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_PurchaseOrderFile", x => x.ID);
                    table.ForeignKey(
                        name: "FK_PurchaseOrderFile_PurchaseOrder",
                        column: x => x.PurchaseOrderID,
                        principalTable: "PurchaseOrder",
                        principalColumn: "ID");
                });

            migrationBuilder.CreateIndex(
                name: "IX_OrderItem_PurchaseOrderID",
                table: "OrderItem",
                column: "PurchaseOrderID");

            migrationBuilder.CreateIndex(
                name: "IX_PurchaseOrder_BillingAddressID",
                table: "PurchaseOrder",
                column: "BillingAddressID");

            migrationBuilder.CreateIndex(
                name: "IX_PurchaseOrder_ShippingAddressID",
                table: "PurchaseOrder",
                column: "ShippingAddressID");

            migrationBuilder.CreateIndex(
                name: "IX_PurchaseOrderFile_PurchaseOrderID",
                table: "PurchaseOrderFile",
                column: "PurchaseOrderID");
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropTable(
                name: "OrderItem");

            migrationBuilder.DropTable(
                name: "PurchaseOrderFile");

            migrationBuilder.DropTable(
                name: "PurchaseOrder");

            migrationBuilder.DropTable(
                name: "Address");
        }
    }
}

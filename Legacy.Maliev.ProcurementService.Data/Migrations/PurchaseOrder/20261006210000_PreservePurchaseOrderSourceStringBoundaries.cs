using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace Legacy.Maliev.ProcurementService.Data.Migrations.PurchaseOrder;

/// <inheritdoc />
public partial class PreservePurchaseOrderSourceStringBoundaries : Migration
{
    /// <inheritdoc />
    protected override void Up(MigrationBuilder migrationBuilder)
    {
        // PostgreSQL validates every retained row; no defaults, replacement values or DML are supplied.
        migrationBuilder.Sql("SET LOCAL search_path = public; SET LOCAL lock_timeout = '5s'; SET LOCAL statement_timeout = '30s'; LOCK TABLE public.\"Address\" IN ACCESS EXCLUSIVE MODE; LOCK TABLE public.\"OrderItem\" IN ACCESS EXCLUSIVE MODE; LOCK TABLE public.\"PurchaseOrder\" IN ACCESS EXCLUSIVE MODE; LOCK TABLE public.\"PurchaseOrderFile\" IN ACCESS EXCLUSIVE MODE;");

        migrationBuilder.AddCheckConstraint(name: "CK_Address_AddressLine1_UTF16", table: "Address", sql: "char_length(\"AddressLine1\") + char_length(regexp_replace(\"AddressLine1\", U&'[^\\+010000-\\+10FFFF]', '', 'g')) <= 256");
        migrationBuilder.AddCheckConstraint(name: "CK_Address_AddressLine2_UTF16", table: "Address", sql: "char_length(\"AddressLine2\") + char_length(regexp_replace(\"AddressLine2\", U&'[^\\+010000-\\+10FFFF]', '', 'g')) <= 256");
        migrationBuilder.AddCheckConstraint(name: "CK_Address_Building_UTF16", table: "Address", sql: "char_length(\"Building\") + char_length(regexp_replace(\"Building\", U&'[^\\+010000-\\+10FFFF]', '', 'g')) <= 256");
        migrationBuilder.AddCheckConstraint(name: "CK_Address_City_UTF16", table: "Address", sql: "char_length(\"City\") + char_length(regexp_replace(\"City\", U&'[^\\+010000-\\+10FFFF]', '', 'g')) <= 256");
        migrationBuilder.AddCheckConstraint(name: "CK_Address_PostalCode_UTF16", table: "Address", sql: "char_length(\"PostalCode\") + char_length(regexp_replace(\"PostalCode\", U&'[^\\+010000-\\+10FFFF]', '', 'g')) <= 256");
        migrationBuilder.AddCheckConstraint(name: "CK_Address_State_UTF16", table: "Address", sql: "char_length(\"State\") + char_length(regexp_replace(\"State\", U&'[^\\+010000-\\+10FFFF]', '', 'g')) <= 256");
        migrationBuilder.AddCheckConstraint(name: "CK_OrderItem_PartNumber_UTF16", table: "OrderItem", sql: "char_length(\"PartNumber\") + char_length(regexp_replace(\"PartNumber\", U&'[^\\+010000-\\+10FFFF]', '', 'g')) <= 100");
        migrationBuilder.AddCheckConstraint(name: "CK_PurchaseOrder_BillingContactPerson_UTF16", table: "PurchaseOrder", sql: "char_length(\"BillingContactPerson\") + char_length(regexp_replace(\"BillingContactPerson\", U&'[^\\+010000-\\+10FFFF]', '', 'g')) <= 256");
        migrationBuilder.AddCheckConstraint(name: "CK_PurchaseOrder_BillingFax_UTF16", table: "PurchaseOrder", sql: "char_length(\"BillingFax\") + char_length(regexp_replace(\"BillingFax\", U&'[^\\+010000-\\+10FFFF]', '', 'g')) <= 256");
        migrationBuilder.AddCheckConstraint(name: "CK_PurchaseOrder_BillingMobile_UTF16", table: "PurchaseOrder", sql: "char_length(\"BillingMobile\") + char_length(regexp_replace(\"BillingMobile\", U&'[^\\+010000-\\+10FFFF]', '', 'g')) <= 256");
        migrationBuilder.AddCheckConstraint(name: "CK_PurchaseOrder_BillingTelephone_UTF16", table: "PurchaseOrder", sql: "char_length(\"BillingTelephone\") + char_length(regexp_replace(\"BillingTelephone\", U&'[^\\+010000-\\+10FFFF]', '', 'g')) <= 256");
        migrationBuilder.AddCheckConstraint(name: "CK_PurchaseOrder_ShippingContactPerson_UTF16", table: "PurchaseOrder", sql: "char_length(\"ShippingContactPerson\") + char_length(regexp_replace(\"ShippingContactPerson\", U&'[^\\+010000-\\+10FFFF]', '', 'g')) <= 256");
        migrationBuilder.AddCheckConstraint(name: "CK_PurchaseOrder_ShippingFax_UTF16", table: "PurchaseOrder", sql: "char_length(\"ShippingFax\") + char_length(regexp_replace(\"ShippingFax\", U&'[^\\+010000-\\+10FFFF]', '', 'g')) <= 256");
        migrationBuilder.AddCheckConstraint(name: "CK_PurchaseOrder_ShippingMethod_UTF16", table: "PurchaseOrder", sql: "char_length(\"ShippingMethod\") + char_length(regexp_replace(\"ShippingMethod\", U&'[^\\+010000-\\+10FFFF]', '', 'g')) <= 256");
        migrationBuilder.AddCheckConstraint(name: "CK_PurchaseOrder_ShippingMobile_UTF16", table: "PurchaseOrder", sql: "char_length(\"ShippingMobile\") + char_length(regexp_replace(\"ShippingMobile\", U&'[^\\+010000-\\+10FFFF]', '', 'g')) <= 256");
        migrationBuilder.AddCheckConstraint(name: "CK_PurchaseOrder_ShippingTelephone_UTF16", table: "PurchaseOrder", sql: "char_length(\"ShippingTelephone\") + char_length(regexp_replace(\"ShippingTelephone\", U&'[^\\+010000-\\+10FFFF]', '', 'g')) <= 256");
        migrationBuilder.AddCheckConstraint(name: "CK_PurchaseOrder_SupplierContactPerson_UTF16", table: "PurchaseOrder", sql: "char_length(\"SupplierContactPerson\") + char_length(regexp_replace(\"SupplierContactPerson\", U&'[^\\+010000-\\+10FFFF]', '', 'g')) <= 256");
        migrationBuilder.AddCheckConstraint(name: "CK_PurchaseOrder_Terms_UTF16", table: "PurchaseOrder", sql: "char_length(\"Terms\") + char_length(regexp_replace(\"Terms\", U&'[^\\+010000-\\+10FFFF]', '', 'g')) <= 256");
        migrationBuilder.AddCheckConstraint(name: "CK_PurchaseOrderFile_Bucket_UTF16", table: "PurchaseOrderFile", sql: "char_length(\"Bucket\") + char_length(regexp_replace(\"Bucket\", U&'[^\\+010000-\\+10FFFF]', '', 'g')) <= 50");
    }

    /// <inheritdoc />
    protected override void Down(MigrationBuilder migrationBuilder)
    {
        migrationBuilder.Sql("SET LOCAL search_path = public; SET LOCAL lock_timeout = '5s'; SET LOCAL statement_timeout = '30s'; LOCK TABLE public.\"Address\" IN ACCESS EXCLUSIVE MODE; LOCK TABLE public.\"OrderItem\" IN ACCESS EXCLUSIVE MODE; LOCK TABLE public.\"PurchaseOrder\" IN ACCESS EXCLUSIVE MODE; LOCK TABLE public.\"PurchaseOrderFile\" IN ACCESS EXCLUSIVE MODE;");
        migrationBuilder.DropCheckConstraint(name: "CK_Address_AddressLine1_UTF16", table: "Address");
        migrationBuilder.DropCheckConstraint(name: "CK_Address_AddressLine2_UTF16", table: "Address");
        migrationBuilder.DropCheckConstraint(name: "CK_Address_Building_UTF16", table: "Address");
        migrationBuilder.DropCheckConstraint(name: "CK_Address_City_UTF16", table: "Address");
        migrationBuilder.DropCheckConstraint(name: "CK_Address_PostalCode_UTF16", table: "Address");
        migrationBuilder.DropCheckConstraint(name: "CK_Address_State_UTF16", table: "Address");
        migrationBuilder.DropCheckConstraint(name: "CK_OrderItem_PartNumber_UTF16", table: "OrderItem");
        migrationBuilder.DropCheckConstraint(name: "CK_PurchaseOrder_BillingContactPerson_UTF16", table: "PurchaseOrder");
        migrationBuilder.DropCheckConstraint(name: "CK_PurchaseOrder_BillingFax_UTF16", table: "PurchaseOrder");
        migrationBuilder.DropCheckConstraint(name: "CK_PurchaseOrder_BillingMobile_UTF16", table: "PurchaseOrder");
        migrationBuilder.DropCheckConstraint(name: "CK_PurchaseOrder_BillingTelephone_UTF16", table: "PurchaseOrder");
        migrationBuilder.DropCheckConstraint(name: "CK_PurchaseOrder_ShippingContactPerson_UTF16", table: "PurchaseOrder");
        migrationBuilder.DropCheckConstraint(name: "CK_PurchaseOrder_ShippingFax_UTF16", table: "PurchaseOrder");
        migrationBuilder.DropCheckConstraint(name: "CK_PurchaseOrder_ShippingMethod_UTF16", table: "PurchaseOrder");
        migrationBuilder.DropCheckConstraint(name: "CK_PurchaseOrder_ShippingMobile_UTF16", table: "PurchaseOrder");
        migrationBuilder.DropCheckConstraint(name: "CK_PurchaseOrder_ShippingTelephone_UTF16", table: "PurchaseOrder");
        migrationBuilder.DropCheckConstraint(name: "CK_PurchaseOrder_SupplierContactPerson_UTF16", table: "PurchaseOrder");
        migrationBuilder.DropCheckConstraint(name: "CK_PurchaseOrder_Terms_UTF16", table: "PurchaseOrder");
        migrationBuilder.DropCheckConstraint(name: "CK_PurchaseOrderFile_Bucket_UTF16", table: "PurchaseOrderFile");

    }
}

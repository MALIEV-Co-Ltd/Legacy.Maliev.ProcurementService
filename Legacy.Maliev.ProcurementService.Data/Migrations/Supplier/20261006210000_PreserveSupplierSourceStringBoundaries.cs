using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace Legacy.Maliev.ProcurementService.Data.Migrations.Supplier;

/// <inheritdoc />
public partial class PreserveSupplierSourceStringBoundaries : Migration
{
    /// <inheritdoc />
    protected override void Up(MigrationBuilder migrationBuilder)
    {
        // PostgreSQL validates every retained row; no defaults, replacement values or DML are supplied.
        migrationBuilder.Sql("SET LOCAL search_path = public; SET LOCAL lock_timeout = '5s'; SET LOCAL statement_timeout = '30s'; LOCK TABLE public.\"Address\" IN ACCESS EXCLUSIVE MODE; LOCK TABLE public.\"Supplier\" IN ACCESS EXCLUSIVE MODE;");
        migrationBuilder.AlterColumn<string>(name: "Name", table: "Supplier", type: "character varying(256)", maxLength: 256, nullable: false, oldClrType: typeof(string), oldType: "character varying(256)", oldMaxLength: 256, oldNullable: true);
        migrationBuilder.AlterColumn<string>(name: "Address1", table: "Address", type: "character varying(256)", maxLength: 256, nullable: false, oldClrType: typeof(string), oldType: "character varying(256)", oldMaxLength: 256, oldNullable: true);
        migrationBuilder.AddCheckConstraint(name: "CK_Address_Address1_UTF16", table: "Address", sql: "char_length(\"Address1\") + char_length(regexp_replace(\"Address1\", U&'[^\\+010000-\\+10FFFF]', '', 'g')) <= 256");
        migrationBuilder.AddCheckConstraint(name: "CK_Address_Address2_UTF16", table: "Address", sql: "char_length(\"Address2\") + char_length(regexp_replace(\"Address2\", U&'[^\\+010000-\\+10FFFF]', '', 'g')) <= 256");
        migrationBuilder.AddCheckConstraint(name: "CK_Address_Building_UTF16", table: "Address", sql: "char_length(\"Building\") + char_length(regexp_replace(\"Building\", U&'[^\\+010000-\\+10FFFF]', '', 'g')) <= 256");
        migrationBuilder.AddCheckConstraint(name: "CK_Address_City_UTF16", table: "Address", sql: "char_length(\"City\") + char_length(regexp_replace(\"City\", U&'[^\\+010000-\\+10FFFF]', '', 'g')) <= 256");
        migrationBuilder.AddCheckConstraint(name: "CK_Address_PostalCode_UTF16", table: "Address", sql: "char_length(\"PostalCode\") + char_length(regexp_replace(\"PostalCode\", U&'[^\\+010000-\\+10FFFF]', '', 'g')) <= 256");
        migrationBuilder.AddCheckConstraint(name: "CK_Address_State_UTF16", table: "Address", sql: "char_length(\"State\") + char_length(regexp_replace(\"State\", U&'[^\\+010000-\\+10FFFF]', '', 'g')) <= 256");
        migrationBuilder.AddCheckConstraint(name: "CK_Supplier_Email_UTF16", table: "Supplier", sql: "char_length(\"Email\") + char_length(regexp_replace(\"Email\", U&'[^\\+010000-\\+10FFFF]', '', 'g')) <= 256");
        migrationBuilder.AddCheckConstraint(name: "CK_Supplier_Fax_UTF16", table: "Supplier", sql: "char_length(\"Fax\") + char_length(regexp_replace(\"Fax\", U&'[^\\+010000-\\+10FFFF]', '', 'g')) <= 256");
        migrationBuilder.AddCheckConstraint(name: "CK_Supplier_Mobile_UTF16", table: "Supplier", sql: "char_length(\"Mobile\") + char_length(regexp_replace(\"Mobile\", U&'[^\\+010000-\\+10FFFF]', '', 'g')) <= 256");
        migrationBuilder.AddCheckConstraint(name: "CK_Supplier_Name_UTF16", table: "Supplier", sql: "char_length(\"Name\") + char_length(regexp_replace(\"Name\", U&'[^\\+010000-\\+10FFFF]', '', 'g')) <= 256");
        migrationBuilder.AddCheckConstraint(name: "CK_Supplier_TaxNumber_UTF16", table: "Supplier", sql: "char_length(\"TaxNumber\") + char_length(regexp_replace(\"TaxNumber\", U&'[^\\+010000-\\+10FFFF]', '', 'g')) <= 256");
        migrationBuilder.AddCheckConstraint(name: "CK_Supplier_Telephone_UTF16", table: "Supplier", sql: "char_length(\"Telephone\") + char_length(regexp_replace(\"Telephone\", U&'[^\\+010000-\\+10FFFF]', '', 'g')) <= 256");
        migrationBuilder.AddCheckConstraint(name: "CK_Supplier_Website_UTF16", table: "Supplier", sql: "char_length(\"Website\") + char_length(regexp_replace(\"Website\", U&'[^\\+010000-\\+10FFFF]', '', 'g')) <= 256");
    }

    /// <inheritdoc />
    protected override void Down(MigrationBuilder migrationBuilder)
    {
        migrationBuilder.Sql("SET LOCAL search_path = public; SET LOCAL lock_timeout = '5s'; SET LOCAL statement_timeout = '30s'; LOCK TABLE public.\"Address\" IN ACCESS EXCLUSIVE MODE; LOCK TABLE public.\"Supplier\" IN ACCESS EXCLUSIVE MODE;");
        migrationBuilder.DropCheckConstraint(name: "CK_Address_Address1_UTF16", table: "Address");
        migrationBuilder.DropCheckConstraint(name: "CK_Address_Address2_UTF16", table: "Address");
        migrationBuilder.DropCheckConstraint(name: "CK_Address_Building_UTF16", table: "Address");
        migrationBuilder.DropCheckConstraint(name: "CK_Address_City_UTF16", table: "Address");
        migrationBuilder.DropCheckConstraint(name: "CK_Address_PostalCode_UTF16", table: "Address");
        migrationBuilder.DropCheckConstraint(name: "CK_Address_State_UTF16", table: "Address");
        migrationBuilder.DropCheckConstraint(name: "CK_Supplier_Email_UTF16", table: "Supplier");
        migrationBuilder.DropCheckConstraint(name: "CK_Supplier_Fax_UTF16", table: "Supplier");
        migrationBuilder.DropCheckConstraint(name: "CK_Supplier_Mobile_UTF16", table: "Supplier");
        migrationBuilder.DropCheckConstraint(name: "CK_Supplier_Name_UTF16", table: "Supplier");
        migrationBuilder.DropCheckConstraint(name: "CK_Supplier_TaxNumber_UTF16", table: "Supplier");
        migrationBuilder.DropCheckConstraint(name: "CK_Supplier_Telephone_UTF16", table: "Supplier");
        migrationBuilder.DropCheckConstraint(name: "CK_Supplier_Website_UTF16", table: "Supplier");
        migrationBuilder.AlterColumn<string>(name: "Name", table: "Supplier", type: "character varying(256)", maxLength: 256, nullable: true, oldClrType: typeof(string), oldType: "character varying(256)", oldMaxLength: 256);
        migrationBuilder.AlterColumn<string>(name: "Address1", table: "Address", type: "character varying(256)", maxLength: 256, nullable: true, oldClrType: typeof(string), oldType: "character varying(256)", oldMaxLength: 256);
    }
}

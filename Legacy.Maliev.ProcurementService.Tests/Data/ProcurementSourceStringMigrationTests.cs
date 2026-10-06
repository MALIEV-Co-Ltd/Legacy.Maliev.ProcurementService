using Legacy.Maliev.ProcurementService.Data;
using Microsoft.EntityFrameworkCore;
using Npgsql;
using Testcontainers.PostgreSql;

namespace Legacy.Maliev.ProcurementService.Tests.Data;

public sealed class ProcurementSourceStringMigrationTests : IAsyncLifetime
{
    private readonly PostgreSqlContainer postgres = new PostgreSqlBuilder("postgres:18.1-alpine").Build();

    public async Task InitializeAsync()
    {
        using var timeout = new CancellationTokenSource(TimeSpan.FromMinutes(2));
        await postgres.StartAsync(timeout.Token);
    }

    public async Task DisposeAsync() => await postgres.DisposeAsync();

    [Theory]
    [InlineData(false, "Name", "null")]
    [InlineData(false, "Address1", "null")]
    [InlineData(false, "Name", "oversize")]
    [InlineData(true, "PartNumber", "oversize")]
    public async Task InvalidRetainedRowsRejectMigrationWithoutChangingRowsSchemaOrHistory(bool purchaseOrder, string field, string kind)
    {
        await using var context = Context(purchaseOrder);
        string previous = Previous(purchaseOrder);
        await context.Database.MigrateAsync(previous);
        string table = field == "Address1" ? "Address" : purchaseOrder ? "OrderItem" : "Supplier";
        string? literal = kind == "null" ? null : string.Concat(Enumerable.Repeat(char.ConvertFromUtf32(0x1F600), purchaseOrder ? 51 : 129));
        await InsertAsync(context, table, field, literal);
        string before = await RowsAsync(context, table);
        string[] history = (await context.Database.GetAppliedMigrationsAsync()).ToArray();
        int constraints = await ConstraintsAsync(context);
        var exception = await Assert.ThrowsAsync<PostgresException>(() => context.Database.MigrateAsync());
        Assert.Equal(kind == "null" ? PostgresErrorCodes.NotNullViolation : PostgresErrorCodes.CheckViolation, exception.SqlState);
        Assert.Equal(before, await RowsAsync(context, table));
        Assert.Equal(history, (await context.Database.GetAppliedMigrationsAsync()).ToArray());
        Assert.Equal(constraints, await ConstraintsAsync(context));
        if (!purchaseOrder)
            Assert.Equal(2, await NullableSourcePropertiesAsync(context));
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task ValidRetainedLiteralsSurviveUpgradeRepeatAndRollback(bool purchaseOrder)
    {
        await using var context = Context(purchaseOrder);
        await context.Database.MigrateAsync(Previous(purchaseOrder));
        string table = purchaseOrder ? "OrderItem" : "Supplier";
        string field = purchaseOrder ? "PartNumber" : "Name";
        string literal = string.Concat(Enumerable.Repeat(char.ConvertFromUtf32(0x1F600), purchaseOrder ? 50 : 128));
        await InsertAsync(context, table, field, literal);
        if (!purchaseOrder)
            await InsertAsync(context, "Address", "Address1", " ");
        string before = await RowsAsync(context, table);
        string? addressBefore = purchaseOrder ? null : await RowsAsync(context, "Address");
        await context.Database.MigrateAsync();
        Assert.Equal(purchaseOrder ? 19 : 13, await ConstraintsAsync(context));
        if (!purchaseOrder)
            Assert.Equal(0, await NullableSourcePropertiesAsync(context));
        await context.Database.MigrateAsync();
        Assert.Equal(before, await RowsAsync(context, table));
        await context.Database.MigrateAsync(Previous(purchaseOrder));
        Assert.Equal(0, await ConstraintsAsync(context));
        Assert.Equal(before, await RowsAsync(context, table));
        if (!purchaseOrder)
        {
            Assert.Equal(addressBefore, await RowsAsync(context, "Address"));
            Assert.Equal(2, await NullableSourcePropertiesAsync(context));
        }
    }

    [Fact]
    public async Task PostgreSqlUnicodeExpressionCountsSupplementaryScalarsAsTwoUtf16Units()
    {
        await using var context = Context(false);
        int units = await context.Database.SqlQueryRaw<int>(
            """
            SELECT (char_length({0}::text) + char_length(regexp_replace({0}::text, U&'[^\+010000-\+10FFFF]', '', 'g')))::int AS "Value"
            """,
            "Aไทย" + char.ConvertFromUtf32(0x1F600) + " ").SingleAsync();
        Assert.Equal(7, units);
    }

    private DbContext Context(bool purchaseOrder) => purchaseOrder
        ? new PurchaseOrderDbContext(new DbContextOptionsBuilder<PurchaseOrderDbContext>().UseNpgsql(postgres.GetConnectionString()).Options)
        : new SupplierDbContext(new DbContextOptionsBuilder<SupplierDbContext>().UseNpgsql(postgres.GetConnectionString()).Options);

    private static string Previous(bool purchaseOrder) => purchaseOrder
        ? "20261001013651_AddDurablePurchaseOrderCreateReceipts"
        : "20261001013648_AddDurableSupplierCreateReceipts";

    private static Task<int> InsertAsync(DbContext context, string table, string field, string? literal)
    {
        // Identifiers come from fixed SQL cases; only the synthetic value is parameterized.
        string sql = (table, field) switch
        {
            ("Address", "Address1") => "INSERT INTO \"Address\" (\"ID\", \"Address1\", \"CountryID\") VALUES (1, @literal, 0)",
            ("Supplier", "Name") => "INSERT INTO \"Supplier\" (\"ID\", \"Name\") VALUES (1, @literal)",
            ("OrderItem", "PartNumber") => "INSERT INTO \"OrderItem\" (\"ID\", \"PartNumber\") VALUES (1, @literal)",
            _ => throw new ArgumentOutOfRangeException(nameof(table)),
        };
        return context.Database.ExecuteSqlRawAsync(sql,
            new NpgsqlParameter("literal", NpgsqlTypes.NpgsqlDbType.Varchar) { Value = (object?)literal ?? DBNull.Value });
    }

    private static Task<string> RowsAsync(DbContext context, string table)
    {
        string sql = table switch
        {
            "Address" => "SELECT COALESCE(jsonb_agg(to_jsonb(t) ORDER BY t.\"ID\"), '[]'::jsonb)::text AS \"Value\" FROM \"Address\" t",
            "Supplier" => "SELECT COALESCE(jsonb_agg(to_jsonb(t) ORDER BY t.\"ID\"), '[]'::jsonb)::text AS \"Value\" FROM \"Supplier\" t",
            "OrderItem" => "SELECT COALESCE(jsonb_agg(to_jsonb(t) ORDER BY t.\"ID\"), '[]'::jsonb)::text AS \"Value\" FROM \"OrderItem\" t",
            _ => throw new ArgumentOutOfRangeException(nameof(table)),
        };
        return context.Database.SqlQueryRaw<string>(sql).SingleAsync();
    }

    private static Task<int> ConstraintsAsync(DbContext context) => context.Database.SqlQueryRaw<int>(
        "SELECT COUNT(*)::int AS \"Value\" FROM pg_constraint WHERE connamespace = 'public'::regnamespace AND contype = 'c' AND right(conname, 6) = '_UTF16'").SingleAsync();

    private static Task<int> NullableSourcePropertiesAsync(DbContext context) => context.Database.SqlQueryRaw<int>(
        "SELECT COUNT(*)::int AS \"Value\" FROM information_schema.columns WHERE table_schema = 'public' AND is_nullable = 'YES' AND ((table_name = 'Supplier' AND column_name = 'Name') OR (table_name = 'Address' AND column_name = 'Address1'))").SingleAsync();
}

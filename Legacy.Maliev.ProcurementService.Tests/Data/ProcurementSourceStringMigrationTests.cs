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
        // Exercise this original reversible string boundary without applying later immutable child receipts.
        await context.Database.MigrateAsync(StringBoundary(purchaseOrder));
        Assert.Equal(StringBoundary(purchaseOrder), (await context.Database.GetAppliedMigrationsAsync()).Last());
        Assert.Equal(purchaseOrder ? 19 : 13, await ConstraintsAsync(context));
        if (!purchaseOrder)
            Assert.Equal(0, await NullableSourcePropertiesAsync(context));
        await context.Database.MigrateAsync(StringBoundary(purchaseOrder));
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

    /// <summary>Rejects retained PostgreSQL scalar-valid buckets that exceed the source UTF16 limit.</summary>
    /// <param name="supplementaryCount">The synthetic supplementary scalar count retained before upgrade.</param>
    /// <param name="suffix">A synthetic BMP suffix used to exercise the first invalid UTF16 length.</param>
    [Theory]
    [InlineData(25, "ก")]
    [InlineData(26, "")]
    public async Task RetainedBucketOverflow_RefusesUpgradeWithoutChangingRowsSchemaOrHistory(int supplementaryCount, string suffix)
    {
        using var lifetime = new CancellationTokenSource(TimeSpan.FromSeconds(90));
        await using var context = Context(true);
        await context.Database.MigrateAsync(Previous(true), lifetime.Token);
        await context.Database.ExecuteSqlRawAsync("INSERT INTO public.\"PurchaseOrder\" (\"ID\") VALUES (1)", lifetime.Token);
        var literal = string.Concat(Enumerable.Repeat(char.ConvertFromUtf32(0x1F600), supplementaryCount)) + suffix;
        Assert.True(literal.Length > 50);
        await WriteBucketAsync(context, false, 1, literal, lifetime.Token);
        var before = await BucketStateAsync(context, lifetime.Token);

        var error = await Assert.ThrowsAsync<PostgresException>(
            () => context.Database.MigrateAsync(StringBoundary(true), lifetime.Token));

        Assert.Equal(PostgresErrorCodes.CheckViolation, error.SqlState);
        Assert.Equal("CK_PurchaseOrderFile_Bucket_UTF16", error.ConstraintName);
        Assert.Equal(before, await BucketStateAsync(context, lifetime.Token));
    }

    /// <summary>Preserves valid literals across the original boundary and rejects direct SQL insert/update bypasses.</summary>
    /// <param name="kind">Selects a fixed synthetic empty, padded, BMP or supplementary boundary literal.</param>
    [Theory]
    [InlineData("empty")]
    [InlineData("padding")]
    [InlineData("padded")]
    [InlineData("bmp50")]
    [InlineData("supplementary50")]
    [InlineData("mixed50")]
    public async Task BucketStorageBoundary_PreservesLiteralsAndRejectsDirectSqlBypasses(string kind)
    {
        using var lifetime = new CancellationTokenSource(TimeSpan.FromSeconds(90));
        await using var context = Context(true);
        await context.Database.MigrateAsync(Previous(true), lifetime.Token);
        await context.Database.ExecuteSqlRawAsync("INSERT INTO public.\"PurchaseOrder\" (\"ID\") VALUES (1)", lifetime.Token);
        var pair = char.ConvertFromUtf32(0x1F600);
        var literal = kind switch
        {
            "empty" => "",
            "padding" => "  ",
            "padded" => " ก padded ",
            "bmp50" => new string('ก', 50),
            "supplementary50" => string.Concat(Enumerable.Repeat(pair, 25)),
            "mixed50" => string.Concat(Enumerable.Repeat(pair, 24)) + "ก ",
            _ => throw new ArgumentOutOfRangeException(nameof(kind)),
        };
        await WriteBucketAsync(context, false, 1, literal, lifetime.Token);
        var before = await BucketRowsAsync(context, lifetime.Token);
        await context.Database.MigrateAsync(StringBoundary(true), lifetime.Token);
        Assert.Equal(before, await BucketRowsAsync(context, lifetime.Token));
        Assert.Equal(1, await context.Database.SqlQueryRaw<int>(
            """
            SELECT COUNT(*)::int AS "Value" FROM pg_constraint
            WHERE conrelid = 'public."PurchaseOrderFile"'::regclass AND contype = 'c'
              AND conname = 'CK_PurchaseOrderFile_Bucket_UTF16' AND convalidated
            """).SingleAsync(lifetime.Token));
        var guarded = await BucketStateAsync(context, lifetime.Token);

        foreach (var (invalid, state) in new (string? Literal, string State)[]
        {
            (null, PostgresErrorCodes.NotNullViolation),
            (new string('ก', 51), "22001"),
            (string.Concat(Enumerable.Repeat(pair, 25)) + "ก", PostgresErrorCodes.CheckViolation),
            (string.Concat(Enumerable.Repeat(pair, 26)), PostgresErrorCodes.CheckViolation),
        })
        {
            foreach (var update in new[] { false, true })
            {
                var error = await Assert.ThrowsAsync<PostgresException>(
                    () => WriteBucketAsync(context, update, update ? 1 : 2, invalid, lifetime.Token));
                Assert.Equal(state, error.SqlState);
                if (state == PostgresErrorCodes.CheckViolation)
                    Assert.Equal("CK_PurchaseOrderFile_Bucket_UTF16", error.ConstraintName);
                Assert.Equal(guarded, await BucketStateAsync(context, lifetime.Token));
            }
        }

        await context.Database.MigrateAsync(StringBoundary(true), lifetime.Token);
        Assert.Equal(guarded, await BucketStateAsync(context, lifetime.Token));
        // Target the original reversible boundary; later child-receipt migrations stay unapplied.
        await context.Database.MigrateAsync(Previous(true), lifetime.Token);
        Assert.Equal(before, await BucketRowsAsync(context, lifetime.Token));
        await context.Database.MigrateAsync(StringBoundary(true), lifetime.Token);
        Assert.Equal(guarded, await BucketStateAsync(context, lifetime.Token));
    }

    /// <summary>Proves both directions retain rows/schema/history when the existing lock budget refuses admission.</summary>
    /// <param name="downgrade">Whether to contend with removal rather than addition of the original constraints.</param>
    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task BucketBoundaryLockRefusal_PreservesRowsSchemaAndHistory(bool downgrade)
    {
        using var lifetime = new CancellationTokenSource(TimeSpan.FromSeconds(90));
        await using var context = Context(true);
        await context.Database.MigrateAsync(downgrade ? StringBoundary(true) : Previous(true), lifetime.Token);
        await context.Database.ExecuteSqlRawAsync("INSERT INTO public.\"PurchaseOrder\" (\"ID\") VALUES (1)", lifetime.Token);
        await WriteBucketAsync(context, false, 1, " ก retained ", lifetime.Token);
        var before = await BucketStateAsync(context, lifetime.Token);
        await using (var blocker = new NpgsqlConnection(postgres.GetConnectionString()))
        {
            await blocker.OpenAsync(lifetime.Token);
            await using var transaction = await blocker.BeginTransactionAsync(lifetime.Token);
            await using var command = new NpgsqlCommand(
                "LOCK TABLE public.\"PurchaseOrderFile\" IN ACCESS SHARE MODE", blocker, transaction);
            await command.ExecuteNonQueryAsync(lifetime.Token);
            var error = await Assert.ThrowsAsync<PostgresException>(
                () => context.Database.MigrateAsync(downgrade ? Previous(true) : StringBoundary(true), lifetime.Token));
            Assert.Equal(PostgresErrorCodes.LockNotAvailable, error.SqlState);
            Assert.Equal(before, await BucketStateAsync(context, lifetime.Token));
            await transaction.RollbackAsync(lifetime.Token);
        }
        await context.Database.MigrateAsync(downgrade ? Previous(true) : StringBoundary(true), lifetime.Token);
        Assert.Equal(1, await context.Database.SqlQueryRaw<int>(
            "SELECT COUNT(*)::int AS \"Value\" FROM public.\"PurchaseOrderFile\" WHERE \"ID\" = 1 AND \"Bucket\" = ' ก retained '")
            .SingleAsync(lifetime.Token));
    }

    private static Task<int> WriteBucketAsync(DbContext context, bool update, int id, string? bucket, CancellationToken token)
    {
        var sql = update
            ? "UPDATE public.\"PurchaseOrderFile\" SET \"Bucket\" = @bucket WHERE \"ID\" = @id"
            : "INSERT INTO public.\"PurchaseOrderFile\" (\"ID\", \"PurchaseOrderID\", \"Bucket\", \"ObjectName\") VALUES (@id, 1, @bucket, ' synthetic/object.step ')";
        return context.Database.ExecuteSqlRawAsync(sql,
            new object[]
            {
                new NpgsqlParameter("id", id),
                new NpgsqlParameter("bucket", NpgsqlTypes.NpgsqlDbType.Varchar) { Value = (object?)bucket ?? DBNull.Value },
            }, token);
    }

    private static Task<string> BucketRowsAsync(DbContext context, CancellationToken token) =>
        context.Database.SqlQueryRaw<string>(
            """
            SELECT jsonb_build_object(
              'parents', (SELECT COALESCE(jsonb_agg(to_jsonb(r) ORDER BY r."ID"), '[]'::jsonb) FROM public."PurchaseOrder" r),
              'files', (SELECT COALESCE(jsonb_agg(to_jsonb(r) ORDER BY r."ID"), '[]'::jsonb) FROM public."PurchaseOrderFile" r)
            )::text AS "Value"
            """).SingleAsync(token);

    private static async Task<string> BucketStateAsync(DbContext context, CancellationToken token)
    {
        var rows = await BucketRowsAsync(context, token);
        var schema = await context.Database.SqlQueryRaw<string>(
            """
            SELECT jsonb_build_object(
              'constraints', (SELECT COALESCE(jsonb_agg(jsonb_build_object(
                'name', conname, 'type', contype, 'validated', convalidated,
                'definition', pg_get_constraintdef(oid)) ORDER BY conname), '[]'::jsonb)
                FROM pg_constraint WHERE conrelid IN
                  ('public."Address"'::regclass, 'public."OrderItem"'::regclass,
                   'public."PurchaseOrder"'::regclass, 'public."PurchaseOrderFile"'::regclass)),
              'columns', (SELECT COALESCE(jsonb_agg(to_jsonb(c) ORDER BY c.table_name, c.ordinal_position), '[]'::jsonb)
                FROM information_schema.columns c WHERE c.table_schema = 'public'
                  AND c.table_name IN ('Address', 'OrderItem', 'PurchaseOrder', 'PurchaseOrderFile'))
            )::text AS "Value"
            """).SingleAsync(token);
        var history = string.Join("\n", await context.Database.GetAppliedMigrationsAsync(token));
        return rows + "\n" + schema + "\n" + history;
    }

    private DbContext Context(bool purchaseOrder) => purchaseOrder
        ? new PurchaseOrderDbContext(new DbContextOptionsBuilder<PurchaseOrderDbContext>().UseNpgsql(postgres.GetConnectionString()).Options)
        : new SupplierDbContext(new DbContextOptionsBuilder<SupplierDbContext>().UseNpgsql(postgres.GetConnectionString()).Options);

    private static string Previous(bool purchaseOrder) => purchaseOrder
        ? "20261001013651_AddDurablePurchaseOrderCreateReceipts"
        : "20261001013648_AddDurableSupplierCreateReceipts";

    private static string StringBoundary(bool purchaseOrder) => purchaseOrder
        ? "20261006210000_PreservePurchaseOrderSourceStringBoundaries"
        : "20261006210000_PreserveSupplierSourceStringBoundaries";

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

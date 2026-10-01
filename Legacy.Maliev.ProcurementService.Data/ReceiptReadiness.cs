using System.Data.Common;
using Microsoft.EntityFrameworkCore;

namespace Legacy.Maliev.ProcurementService.Data;

internal static class ReceiptReadiness
{
    private static readonly IReadOnlyDictionary<string, string> Columns = new Dictionary<string, string>
    {
        ["IssuerDigest"] = "bytea",
        ["SubjectDigest"] = "bytea",
        ["Operation"] = "int2",
        ["KeyDigest"] = "bytea",
        ["CanonicalVersion"] = "int2",
        ["PayloadDigest"] = "bytea",
        ["ResponseVersion"] = "int2",
        ["EntityId"] = "int4",
        ["ResponseBody"] = "bytea",
        ["ResponseDigest"] = "bytea",
        ["CreatedAtUtc"] = "timestamptz"
    };

    public static async Task<bool> IsReadyAsync(DbContext context, string table, short operation, CancellationToken token)
    {
        await context.Database.OpenConnectionAsync(token);
        var connection = context.Database.GetDbConnection();
        var tables = await ReadAsync(connection, "SELECT c.relrowsecurity::text, c.relforcerowsecurity::text, c.relhasrules::text FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND c.relname=@table AND c.relkind='r'", table, token);
        if (tables.Count != 1 || tables[0].Any(value => value != "false")) return false;
        var columns = await ReadAsync(connection, "SELECT a.attname, t.typname, a.attnotnull::text, a.atthasdef::text, a.attgenerated::text, a.attidentity::text FROM pg_catalog.pg_attribute a JOIN pg_catalog.pg_class c ON c.oid=a.attrelid JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace JOIN pg_catalog.pg_type t ON t.oid=a.atttypid WHERE n.nspname='public' AND c.relname=@table AND c.relkind='r' AND a.attnum>0 AND NOT a.attisdropped", table, token);
        if (columns.Count != Columns.Count || columns.Any(row => !Columns.TryGetValue(row[0], out var type) || type != row[1] || row[2] != "true" || row[3] != "false" || row[4] != "" || row[5] != "")) return false;
        var constraints = await ReadAsync(connection, "SELECT con.conname, pg_catalog.pg_get_constraintdef(con.oid), con.contype::text, con.convalidated::text, con.condeferrable::text, con.condeferred::text FROM pg_catalog.pg_constraint con JOIN pg_catalog.pg_class c ON c.oid=con.conrelid JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND c.relname=@table", table, token);
        // PostgreSQL 18 also records the required columns as native NOT NULL constraints.
        // Their column shape is checked above; they are not additional arbitration constraints.
        if (constraints.Count(row => row[2] != "n") != 5 || constraints.Any(row => row[3] != "true" || row[4] != "false" || row[5] != "false")) return false;
        foreach (var expected in CreateReceiptSchema.Checks(table, operation))
        {
            if (!constraints.Any(row => row[0] == expected.Key && row[2] == "c" && Normalize(row[1]) == Normalize("CHECK " + expected.Value))) return false;
        }
        if (!constraints.Any(row => row[0] == $"PK_{table}" && row[2] == "p" && Normalize(row[1]) == Normalize("PRIMARY KEY (IssuerDigest, SubjectDigest, Operation, KeyDigest)"))) return false;
        if (constraints.Any(row => row[2] == "f")) return false;
        var triggers = await ReadAsync(connection, "SELECT t.tgname FROM pg_catalog.pg_trigger t JOIN pg_catalog.pg_class c ON c.oid=t.tgrelid JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND c.relname=@table", table, token);
        if (triggers.Count != 0) return false;
        var indexes = await ReadAsync(connection, "SELECT i.relname, x.indisvalid::text, x.indisready::text FROM pg_catalog.pg_index x JOIN pg_catalog.pg_class i ON i.oid=x.indexrelid JOIN pg_catalog.pg_class c ON c.oid=x.indrelid JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND c.relname=@table AND x.indisprimary AND x.indisunique AND x.indimmediate", table, token);
        return indexes.Any(row => row[0] == $"PK_{table}" && row[1] == "true" && row[2] == "true");
    }

    private static string Normalize(string value) => new(value.Where(character => !char.IsWhiteSpace(character) && character is not '(' and not ')' and not '"').ToArray());
    private static async Task<List<string[]>> ReadAsync(DbConnection connection, string sql, string table, CancellationToken token)
    {
        await using var command = connection.CreateCommand();
        command.CommandText = sql;
        command.CommandTimeout = 5;
        var parameter = command.CreateParameter(); parameter.ParameterName = "table"; parameter.Value = table; command.Parameters.Add(parameter);
        await using var reader = await command.ExecuteReaderAsync(token);
        var rows = new List<string[]>();
        while (await reader.ReadAsync(token)) rows.Add(Enumerable.Range(0, reader.FieldCount).Select(reader.GetString).ToArray());
        return rows;
    }
}

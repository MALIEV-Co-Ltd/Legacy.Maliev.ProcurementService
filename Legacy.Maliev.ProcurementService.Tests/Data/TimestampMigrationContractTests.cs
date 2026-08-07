using System.Text.RegularExpressions;
using System.Runtime.CompilerServices;

namespace Legacy.Maliev.ProcurementService.Tests.Data;

public sealed class TimestampMigrationContractTests
{
    [Theory]
    [InlineData(
        "Legacy.Maliev.ProcurementService.Data/Migrations/PurchaseOrder/20260721031258_FixTimestampColumnType.cs",
        "PurchaseOrderFile", "ModifiedDate", "PurchaseOrderFile", "CreatedDate", "PurchaseOrder", "ModifiedDate", "PurchaseOrder", "CreatedDate", "OrderItem", "ModifiedDate", "OrderItem", "CreatedDate", "Address", "ModifiedDate", "Address", "CreatedDate")]
    [InlineData(
        "Legacy.Maliev.ProcurementService.Data/Migrations/Supplier/20260721031252_FixTimestampColumnType.cs",
        "Supplier", "ModifiedDate", "Supplier", "CreatedDate", "Address", "ModifiedDate", "Address", "CreatedDate")]
    public void TimestampMigrations_UseExplicitUtcConversions(string relativePath, params string[] tableColumns)
    {
        var source = File.ReadAllText(FindRepositoryFile(relativePath));

        Assert.DoesNotContain("migrationBuilder.AlterColumn<DateTime>", source, StringComparison.Ordinal);
        Assert.Equal(2, Regex.Matches(source, "toTimestampWithoutTimeZone:").Count);
        Assert.Contains("ALTER COLUMN \"{column}\" DROP DEFAULT;", source, StringComparison.Ordinal);
        Assert.Contains("USING \"{column}\" AT TIME ZONE 'UTC'", source, StringComparison.Ordinal);

        for (var index = 0; index < tableColumns.Length; index += 2)
        {
            Assert.Contains($"(\"{tableColumns[index]}\", \"{tableColumns[index + 1]}\")", source, StringComparison.Ordinal);
        }
    }

    private static string FindRepositoryFile(string relativePath, [CallerFilePath] string sourceFile = "")
    {
        foreach (var start in new[] { new DirectoryInfo(Path.GetDirectoryName(sourceFile)!), new DirectoryInfo(Directory.GetCurrentDirectory()), new DirectoryInfo(AppContext.BaseDirectory) })
        {
            for (var directory = start; directory is not null; directory = directory.Parent)
            {
                var candidate = Path.Combine(directory.FullName, relativePath.Replace('/', Path.DirectorySeparatorChar));
                if (File.Exists(candidate))
                {
                    return candidate;
                }
            }
        }

        throw new FileNotFoundException($"Could not find migration source '{relativePath}'.");
    }
}

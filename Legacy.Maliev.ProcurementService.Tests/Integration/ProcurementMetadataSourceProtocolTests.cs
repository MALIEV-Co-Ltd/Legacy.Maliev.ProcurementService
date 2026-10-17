using System.Net;
using Microsoft.AspNetCore.Mvc.NewtonsoftJson;
using Newtonsoft.Json;
using OriginalSupplier = Maliev.SupplierService.Data.Database.SupplierContext.Supplier;
using OriginalSupplierAddress = Maliev.SupplierService.Data.Database.SupplierContext.Address;
using OriginalOrderAddress = Maliev.PurchaseOrderService.Data.Database.PurchaseOrderContext.Address;
using OriginalFile = Maliev.PurchaseOrderService.Data.Database.PurchaseOrderContext.PurchaseOrderFile;

namespace Legacy.Maliev.ProcurementService.Tests.Integration;

internal static class ProcurementMetadataVectors
{
    public static readonly string[] Contracts = ["supplier", "supplier-address", "order-address", "file"];
    public static readonly string[] RejectedPrefixes =
    [
        "\"$ref\":1,", "\"$ref\":true,", "\"$ref\":false,", "\"$ref\":[],", "\"$ref\":{},",
        "\"$ref\":\"SYNTHETIC-PRIVATE-METADATA\",", "\"$ref\":\"\",",
        "\"$values\":[],", "\"$values\":null,", "\"$values\":{},", "\"$values\":1,",
        "\"$id\":[],", "\"$id\":[{}],",
        "\"$id\":{\"$ref\":1},",
        "\"$id\":\"r\",\"$ref\":\"r\",",
        "\"$ref\":null,\"$ref\":1,",
        "\"$type\":\"ignored\",\"$ref\":1,",
        "\"$\\u0072ef\":1,",
    ];
    public static readonly string[] AdmittedPrefixes =
    [
        "", "\"$ref\":null,", "\"$id\":\"r\",", "\"$id\":1,", "\"$id\":true,", "\"$id\":null,",
        "\"$type\":\"Not.A.Real.Type, Not.An.Assembly\",", "\"$type\":1,", "\"$type\":false,",
        "\"$ref\":null,\"$id\":\"r\",\"$type\":\"ignored\",",
        "\"$id\":\"first\",\"$id\":\"second\",",
        "\"$unknown\":0,\"$ref\":1,",
        "\"$REF\":1,", "\"ordinary\":0,\"$ref\":1,",
    ];
    public static readonly string[] UnexpectedPrefixes = ["\"$type\":null,", "\"$type\":{},", "\"$type\":[],"];

    public static string Members(string contract, string text = "outer", int country = 66) => contract switch
    {
        "supplier" => "\"Name\":\"" + text + "\",\"Website\":\"site\",\"Email\":\"mail\"",
        "supplier-address" => "\"Address1\":\"" + text + "\",\"CountryId\":" + country,
        "order-address" => "\"AddressLine1\":\"" + text + "\",\"CountryId\":" + country,
        _ => "\"PurchaseOrderId\":7004,\"Bucket\":\"" + text + "\",\"ObjectName\":\"name\"",
    };
    public static string Body(string contract, string prefix = "", string suffix = "") => "{" + prefix + Members(contract) + suffix + "}";
    public static string ScalarName(string contract) => contract switch
    {
        "supplier" => "Name",
        "supplier-address" => "Address1",
        "order-address" => "AddressLine1",
        _ => "Bucket",
    };
    public static Type OriginalType(string contract) => contract switch
    {
        "supplier" => typeof(OriginalSupplier),
        "supplier-address" => typeof(OriginalSupplierAddress),
        "order-address" => typeof(OriginalOrderAddress),
        _ => typeof(OriginalFile),
    };
}

public sealed class ProcurementMetadataSourceProtocolTests
{
    public static IEnumerable<object[]> Rejected => ProcurementMetadataVectors.Contracts.SelectMany(contract =>
        ProcurementMetadataVectors.RejectedPrefixes.Select(prefix => new object[] { contract, prefix }));
    public static IEnumerable<object[]> Admitted => ProcurementMetadataVectors.Contracts.SelectMany(contract =>
        ProcurementMetadataVectors.AdmittedPrefixes.Select(prefix => new object[] { contract, prefix }));
    public static IEnumerable<object[]> Unexpected => ProcurementMetadataVectors.Contracts.SelectMany(contract =>
        ProcurementMetadataVectors.UnexpectedPrefixes.Select(prefix => new object[] { contract, prefix }));
    public static IEnumerable<object[]> Roots => ProcurementMetadataVectors.Contracts.Select(contract => new object[] { contract });

    [Theory]
    [MemberData(nameof(Rejected))]
    public async Task StockMvc_RejectsLeadingMetadataBeforeAction(string contract, string prefix)
    {
        using var oracle = new ProcurementMetadataSourceOracle();
        using var response = await oracle.SendAsync(contract, ProcurementMetadataVectors.Body(contract, prefix));
        Assert.Equal(HttpStatusCode.BadRequest, response.StatusCode);
        Assert.Equal(0, oracle.State.Entries);
        Assert.Null(oracle.State.Unexpected);
        Assert.Equal(0, oracle.State.BinderCalls);
    }

    [Theory]
    [MemberData(nameof(Admitted))]
    public async Task StockMvc_PreservesPrefixStopRulesAndNeverActivatesTypeNames(string contract, string prefix)
    {
        using var oracle = new ProcurementMetadataSourceOracle();
        using var response = await oracle.SendAsync(contract, ProcurementMetadataVectors.Body(contract, prefix));
        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        Assert.Equal(1, oracle.State.Entries);
        Assert.Equal("outer", ReadScalar(oracle.State.Captured!, contract));
        Assert.Equal(0, oracle.State.BinderCalls);
        Assert.Null(oracle.State.Unexpected);
    }

    [Theory]
    [MemberData(nameof(Roots))]
    public async Task StockMvc_LateMetadataIsOrdinaryUnknownMember(string contract)
    {
        using var oracle = new ProcurementMetadataSourceOracle();
        using var response = await oracle.SendAsync(contract, ProcurementMetadataVectors.Body(contract, suffix: ",\"$ref\":1,\"$values\":[],\"$type\":null"));
        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        Assert.Equal("outer", ReadScalar(oracle.State.Captured!, contract));
        Assert.Equal(0, oracle.State.BinderCalls);
    }

    [Theory]
    [MemberData(nameof(Roots))]
    public async Task StockMvc_UnregisteredReferenceIsGenuineNoValueNotActionNullGuard(string contract)
    {
        using var oracle = new ProcurementMetadataSourceOracle();
        using var response = await oracle.SendAsync(contract, "{\"$ref\":\"missing\"}");
        Assert.Equal(HttpStatusCode.BadRequest, response.StatusCode);
        Assert.Contains("A non-empty request body is required.", await response.Content.ReadAsStringAsync(), StringComparison.Ordinal);
        Assert.Equal(0, oracle.State.Entries);
        Assert.Null(oracle.State.Captured);
        Assert.Null(oracle.State.Unexpected);
    }

    [Theory]
    [MemberData(nameof(Unexpected))]
    public async Task StockMvc_TypeNullOrContainerRetainsUnexpectedExceptionPolicy(string contract, string prefix)
    {
        using var oracle = new ProcurementMetadataSourceOracle();
        using var response = await oracle.SendAsync(contract, ProcurementMetadataVectors.Body(contract, prefix));
        Assert.Equal(HttpStatusCode.InternalServerError, response.StatusCode);
        Assert.Equal(typeof(NullReferenceException), oracle.State.Unexpected);
        Assert.Equal(0, oracle.State.Entries);
        Assert.Equal(0, oracle.State.BinderCalls);
    }

    [Theory]
    [MemberData(nameof(Roots))]
    public async Task StockMvc_EmptyIdObjectEndsRootBeforeOuterFields(string contract)
    {
        using var oracle = new ProcurementMetadataSourceOracle();
        using var response = await oracle.SendAsync(contract, ProcurementMetadataVectors.Body(contract, "\"$id\":{},"));
        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        Assert.Null(ReadScalar(oracle.State.Captured!, contract));
        Assert.Equal(1, oracle.State.Entries);
        if (contract is "supplier-address" or "order-address")
            Assert.Equal(0, oracle.State.Captured!.GetType().GetProperty("CountryId")!.GetValue(oracle.State.Captured));
    }

    [Theory]
    [MemberData(nameof(Roots))]
    public async Task StockMvc_IdObjectCanSupplyTheActualRootMembers(string contract)
    {
        using var oracle = new ProcurementMetadataSourceOracle();
        var prefix = "\"$id\":{" + ProcurementMetadataVectors.Members(contract, "inner", 77) + "},";
        using var response = await oracle.SendAsync(contract, ProcurementMetadataVectors.Body(contract, prefix));
        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        Assert.Equal("inner", ReadScalar(oracle.State.Captured!, contract));
        if (contract is "supplier-address" or "order-address")
            Assert.Equal(77, oracle.State.Captured!.GetType().GetProperty("CountryId")!.GetValue(oracle.State.Captured));
    }

    [Fact]
    public void StockOptions_KeepOriginalSourceDefaultsAndObliviousRootShapes()
    {
        var settings = JsonSerializerSettingsProvider.CreateSerializerSettings();
        Assert.Equal(32, settings.MaxDepth);
        Assert.Equal(TypeNameHandling.None, settings.TypeNameHandling);
        Assert.Equal(MetadataPropertyHandling.Default, settings.MetadataPropertyHandling);
        Assert.Equal(MissingMemberHandling.Ignore, settings.MissingMemberHandling);
        Assert.False(Newtonsoft.Json.JsonSerializer.Create(settings).CheckAdditionalContent);
        foreach (var contract in ProcurementMetadataVectors.Contracts)
        {
            var type = ProcurementMetadataVectors.OriginalType(contract);
            Assert.DoesNotContain(type.GetCustomAttributes(false), value => value is JsonObjectAttribute or JsonConverterAttribute);
            Assert.DoesNotContain(type.GetProperties(), property => property.GetCustomAttributes(false).Any(value => value is JsonPropertyAttribute));
        }
    }

    public static IEnumerable<object[]> GrammarCases => ProcurementMetadataVectors.Contracts.SelectMany(contract =>
        new[] { "single_quotes", "unquoted_names", "trailing_comma", "comments", "additional_content", "hex_integer", "octal_integer" }
            .Select(kind => new object[] { contract, kind }));

    [Theory]
    [MemberData(nameof(GrammarCases))]
    public async Task StockMvc_SourceGrammarAndAdditionalContentPolicyAreObserved(string contract, string kind)
    {
        var body = ProcurementMetadataVectors.Body(contract);
        body = kind switch
        {
            "single_quotes" => body.Replace('"', '\''),
            "unquoted_names" => System.Text.RegularExpressions.Regex.Replace(body, "\"([A-Za-z][A-Za-z0-9]*)\":", "$1:"),
            "trailing_comma" => body[..^1] + ",}",
            "comments" => "/*before*/" + body.Insert(1, "/*member*/") + "/*after*/",
            "additional_content" => body + " " + ProcurementMetadataVectors.Body(contract, "\"Name\":\"second\","),
            "hex_integer" => body.Replace(":66", ":0x42", StringComparison.Ordinal).Replace(":7004", ":0x1b5c", StringComparison.Ordinal),
            "octal_integer" => body.Replace(":66", ":0102", StringComparison.Ordinal).Replace(":7004", ":015534", StringComparison.Ordinal),
            _ => throw new InvalidOperationException(),
        };
        using var oracle = new ProcurementMetadataSourceOracle();
        using var response = await oracle.SendAsync(contract, body);
        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        Assert.Equal("outer", ReadScalar(oracle.State.Captured!, contract));
        Assert.Equal(1, oracle.State.Entries);
        Assert.Equal(0, oracle.State.BinderCalls);
    }

    public static TheoryData<string, string, bool> GraphCases => new()
    {
        { "supplier", "\"Address\":{\"CountryId\":\" 66 \",\"Supplier\":[{\"Name\":123}]},", true },
        { "supplier", "\"Address\":1,", false },
        { "supplier", "\"Address\":{\"CountryId\":true},", false },
        { "supplier-address", "\"Supplier\":[{\"Name\":123,\"Address\":{\"CountryId\":\"66\"}}],", true },
        { "supplier-address", "\"Supplier\":{},", false },
        { "supplier-address", "\"Supplier\":[{\"CreatedDate\":true}],", false },
        { "order-address", "\"PurchaseOrderBillingAddress\":[{\"OrderItem\":[{\"Quantity\":\"2\",\"UnitPrice\":\"1.25\"}],\"PurchaseOrderFile\":[{\"Bucket\":123}]}],", true },
        { "order-address", "\"PurchaseOrderShippingAddress\":{},", false },
        { "order-address", "\"PurchaseOrderBillingAddress\":[{\"OrderItem\":[{\"UnitPrice\":{}}]}],", false },
        { "file", "\"PurchaseOrder\":{\"ShippingAddress\":{\"CountryId\":66},\"OrderItem\":[{\"Quantity\":2,\"UnitPrice\":1.25}]},", true },
        { "file", "\"PurchaseOrder\":1,", false },
        { "file", "\"PurchaseOrder\":{\"OrderItem\":[{\"Quantity\":[]}]},", false },
    };

    [Theory]
    [MemberData(nameof(GraphCases))]
    public async Task StockMvc_ValidatesTypedDiscardedGraphsWithoutExecutingBusinessCode(string contract, string prefix, bool valid)
    {
        using var oracle = new ProcurementMetadataSourceOracle();
        using var response = await oracle.SendAsync(contract, ProcurementMetadataVectors.Body(contract, prefix));
        Assert.Equal(valid ? HttpStatusCode.OK : HttpStatusCode.BadRequest, response.StatusCode);
        Assert.Equal(valid ? 1 : 0, oracle.State.Entries);
        Assert.Null(oracle.State.Unexpected);
        Assert.Equal(0, oracle.State.BinderCalls);
    }

    [Fact]
    public async Task StockMvc_ResolvesAnInertSupplierCycleAndKeepsReferenceIdsRequestLocal()
    {
        using var oracle = new ProcurementMetadataSourceOracle();
        var body = "{\"$id\":\"root\",\"Address\":{\"Supplier\":[{\"$ref\":\"root\"}]},\"Name\":\"outer\"}";
        using var first = await oracle.SendAsync("supplier", body);
        Assert.Equal(HttpStatusCode.OK, first.StatusCode);
        var supplier = Assert.IsType<OriginalSupplier>(oracle.State.Captured);
        Assert.Same(supplier, Assert.Single(supplier.Address.Supplier));
        using var second = await oracle.SendAsync("supplier", "{\"$ref\":\"root\"}");
        Assert.Equal(HttpStatusCode.BadRequest, second.StatusCode);
        Assert.Equal(1, oracle.State.Entries);
        Assert.Equal(0, oracle.State.BinderCalls);
    }

    public static TheoryData<string, int> FileOwnerDefaults => new()
    {
        { "", 0 }, { "\"PurchaseOrderId\":null,", 0 }, { "\"PurchaseOrderId\":\"\",", 0 },
        { "\"PurchaseOrderId\":66,", 66 }, { "\"PurchaseOrderId\":\" 66 \",", 66 },
        { "\"PurchaseOrderId\":0,", 0 }, { "\"PurchaseOrderId\":-1,", -1 },
        { "\"PurchaseOrderId\":66,\"PurchaseOrderId\":null,", 66 },
        { "\"PurchaseOrderId\":null,\"PurchaseOrderId\":66,", 66 },
        { "\"PurchaseOrderId\":66,\"PurchaseOrderId\":\"\",", 66 },
    };

    [Theory]
    [MemberData(nameof(FileOwnerDefaults))]
    public async Task StockMvc_FileOwnerIsOriginalNonNullableIntAndNeverInventsExistingOwner(string members, int expected)
    {
        using var oracle = new ProcurementMetadataSourceOracle();
        using var response = await oracle.SendAsync("file", "{" + members + "\"Bucket\":\"bucket\",\"ObjectName\":\"object\"}");
        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        Assert.Equal(expected, Assert.IsType<OriginalFile>(oracle.State.Captured).PurchaseOrderId);
    }

    [Theory]
    [MemberData(nameof(Roots))]
    public async Task StockMvc_NullAuditFieldsAndMissingObliviousStringsDoNotInventImplicitRequired(string contract)
    {
        using var oracle = new ProcurementMetadataSourceOracle();
        using var response = await oracle.SendAsync(contract, "{\"Id\":null,\"CreatedDate\":null,\"ModifiedDate\":null}");
        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        Assert.Null(ReadScalar(oracle.State.Captured!, contract));
        Assert.Equal(1, oracle.State.Entries);
    }

    private static object? ReadScalar(object value, string contract) =>
        value.GetType().GetProperty(ProcurementMetadataVectors.ScalarName(contract))!.GetValue(value);
}

using System.Globalization;
using System.Net;
using System.Net.Http.Json;
using System.Runtime.CompilerServices;
using System.Text;
using System.Text.Json;
using Legacy.Maliev.ProcurementService.Api.Authorization;
using Legacy.Maliev.ProcurementService.Application.Models;
using Legacy.Maliev.ProcurementService.Data;
using Legacy.Maliev.ProcurementService.Domain;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Options;
using Newtonsoft.Json;

using JsonException = System.Text.Json.JsonException;
using JsonSerializer = System.Text.Json.JsonSerializer;

namespace Legacy.Maliev.ProcurementService.Tests.Integration;

public sealed class PurchaseOrderFileMetadataBindingTests(ProcurementRuntimeFixture fixture)
    : IClassFixture<ProcurementRuntimeFixture>, IAsyncLifetime
{
    private const string FileConverter = "Legacy.Maliev.ProcurementService.Api.Serialization.PurchaseOrderFileMetadataRequestJsonConverter";
    private ProcurementRuntimeFactory app = null!;
    private JsonSerializerOptions Options => app.Services.GetRequiredService<IOptions<Microsoft.AspNetCore.Mvc.JsonOptions>>().Value.JsonSerializerOptions;

    private static readonly IReadOnlyDictionary<string, (string Field, string Token)> PrimitiveVectors = new Dictionary<string, (string Field, string Token)>(StringComparer.Ordinal)
    {
        ["bucket_empty"] = ("Bucket", "\"\""),
        ["bucket_padded"] = ("Bucket", "\" ก padded %_ \""),
        ["bucket_thai"] = ("Bucket", "\"ไทย\""),
        ["bucket_integer"] = ("Bucket", "-42"),
        ["bucket_decimal"] = ("Bucket", "12.50"),
        ["bucket_exponent"] = ("Bucket", "1e2"),
        ["bucket_true"] = ("Bucket", "true"),
        ["bucket_false"] = ("Bucket", "false"),
        ["object_empty"] = ("ObjectName", "\"\""),
        ["object_padded"] = ("ObjectName", "\" ก padded %_ \""),
        ["object_thai"] = ("ObjectName", "\"ไทย\""),
        ["object_integer"] = ("ObjectName", "-42"),
        ["object_decimal"] = ("ObjectName", "12.50"),
        ["object_exponent"] = ("ObjectName", "1e2"),
        ["object_true"] = ("ObjectName", "true"),
        ["object_false"] = ("ObjectName", "false"),
    };

    private static readonly IReadOnlyDictionary<string, string> EdgeVectors = new Dictionary<string, string>(StringComparer.Ordinal)
    {
        ["null"] = "null",
        ["negative_zero"] = "-0",
        ["capital_exponent"] = "1E+03",
        ["large_integer"] = "9223372036854775808",
        ["large_exponent"] = "1e400",
    };

    private static readonly IReadOnlyDictionary<string, string> OrderedVectors = new Dictionary<string, string>(StringComparer.Ordinal)
    {
        ["replace"] = "\"first\",\"last\"",
        ["null_after"] = "\"first\",null",
        ["null_before"] = "null,\"last\"",
        ["empty_after"] = "\"first\",\"\"",
        ["repeat_null"] = "\"first\",null,null",
        ["null_only"] = "null",
        ["omitted"] = "",
        ["mixed_case"] = "\"first\",\"last\",null",
    };

    private static readonly IReadOnlyDictionary<string, (string Field, string Token, string Position)> MalformedVectors = new Dictionary<string, (string Field, string Token, string Position)>(StringComparer.Ordinal)
    {
        ["bucket_object_only"] = ("Bucket", "{}", "only"),
        ["bucket_object_before"] = ("Bucket", "{}", "before"),
        ["bucket_object_after"] = ("Bucket", "{}", "after"),
        ["bucket_array_only"] = ("Bucket", "[]", "only"),
        ["bucket_array_before"] = ("Bucket", "[]", "before"),
        ["bucket_array_after"] = ("Bucket", "[]", "after"),
        ["object_object_only"] = ("ObjectName", "{}", "only"),
        ["object_object_before"] = ("ObjectName", "{}", "before"),
        ["object_object_after"] = ("ObjectName", "{}", "after"),
        ["object_array_only"] = ("ObjectName", "[]", "only"),
        ["object_array_before"] = ("ObjectName", "[]", "before"),
        ["object_array_after"] = ("ObjectName", "[]", "after"),
    };

    private static readonly IReadOnlyDictionary<string, string> ParentVectors = new Dictionary<string, string>(StringComparer.Ordinal)
    {
        ["omitted"] = "",
        ["null"] = "\"PurchaseOrderId\":null",
        ["zero"] = "\"PurchaseOrderId\":0",
        ["negative"] = "\"PurchaseOrderId\":-1",
        ["positive"] = "\"PurchaseOrderId\":9100",
        ["quoted"] = "\"PurchaseOrderId\":\"9100\"",
        ["quoted_spaces"] = "\"PurchaseOrderId\":\" 9100 \"",
        ["quoted_plus"] = "\"PurchaseOrderId\":\"+9100\"",
        ["empty"] = "\"PurchaseOrderId\":\"\"",
        ["blank"] = "\"PurchaseOrderId\":\" \"",
        ["fraction"] = "\"PurchaseOrderId\":1.5",
        ["integral_float"] = "\"PurchaseOrderId\":1.0",
        ["exponent"] = "\"PurchaseOrderId\":1e2",
        ["overflow"] = "\"PurchaseOrderId\":2147483648",
        ["true"] = "\"PurchaseOrderId\":true",
        ["false"] = "\"PurchaseOrderId\":false",
        ["object"] = "\"PurchaseOrderId\":{}",
        ["array"] = "\"PurchaseOrderId\":[]",
        ["duplicate_null"] = "\"PurchaseOrderId\":9200,\"purchaseorderid\":null",
        ["duplicate_number"] = "\"PurchaseOrderId\":null,\"PURCHASEORDERID\":9200",
        ["bad_then_valid"] = "\"PurchaseOrderId\":{},\"PurchaseOrderId\":9100",
        ["valid_then_bad"] = "\"PurchaseOrderId\":9100,\"PurchaseOrderId\":[]",
        ["string_null"] = "\"PurchaseOrderId\":\"null\"",
        ["minimum"] = "\"PurchaseOrderId\":-2147483648",
    };

    private static readonly IReadOnlyDictionary<string, (string Name, string? Recognized)> CasingVectors = new Dictionary<string, (string Name, string? Recognized)>(StringComparer.Ordinal)
    {
        ["bucket"] = ("bucket", "Bucket"),
        ["bucket_mixed"] = ("bUcKeT", "Bucket"),
        ["object_lower"] = ("objectname", "ObjectName"),
        ["foreign"] = ("Kucket", null),
    };

    private static readonly IReadOnlyDictionary<string, (string Field, string Tokens)> HttpOrderedVectors = new Dictionary<string, (string Field, string Tokens)>(StringComparer.Ordinal)
    {
        ["bucket_null"] = ("Bucket", "\"first\",null"),
        ["object_null"] = ("ObjectName", "\"first\",null"),
        ["bucket_empty"] = ("Bucket", "\"first\",\"\""),
        ["object_empty"] = ("ObjectName", "\"first\",\"\""),
    };

    private static readonly IReadOnlyDictionary<string, (string Field, string Token, string Position)> HttpMalformedVectors = new Dictionary<string, (string Field, string Token, string Position)>(StringComparer.Ordinal)
    {
        ["bucket_object_before"] = ("Bucket", "{}", "before"),
        ["bucket_array_before"] = ("Bucket", "[]", "before"),
        ["object_object_before"] = ("ObjectName", "{}", "before"),
        ["object_array_before"] = ("ObjectName", "[]", "before"),
    };

    private static readonly IReadOnlyDictionary<string, string> HttpParentVectors = new Dictionary<string, string>(StringComparer.Ordinal)
    {
        ["omitted"] = "",
        ["null"] = "\"PurchaseOrderId\":null",
        ["positive"] = "\"PurchaseOrderId\":9100",
        ["quoted"] = "\"PurchaseOrderId\":\"9100\"",
        ["duplicate_null"] = "\"PurchaseOrderId\":9200,\"purchaseorderid\":null",
        ["duplicate_number"] = "\"PurchaseOrderId\":null,\"PURCHASEORDERID\":9200",
        ["other"] = "\"PurchaseOrderId\":9200",
    };

    private static readonly IReadOnlyDictionary<string, string> RootVectors = new Dictionary<string, string>(StringComparer.Ordinal)
    {
        ["null"] = "null",
        ["array"] = "[]",
        ["true"] = "true",
        ["number"] = "42",
        ["text"] = "\"text\"",
    };

    public static IEnumerable<object[]> PrimitiveCases => CaseIds(PrimitiveVectors);
    public static IEnumerable<object[]> EdgeCases => CaseIds(EdgeVectors);
    public static IEnumerable<object[]> OrderedCases => CaseIds(OrderedVectors);
    public static IEnumerable<object[]> MalformedCases => CaseIds(MalformedVectors);
    public static IEnumerable<object[]> ParentCases => CaseIds(ParentVectors);
    public static IEnumerable<object[]> CasingCases => CaseIds(CasingVectors);
    public static IEnumerable<object[]> HttpOrderedCases => CaseIds(HttpOrderedVectors);
    public static IEnumerable<object[]> HttpMalformedCases => CaseIds(HttpMalformedVectors);
    public static IEnumerable<object[]> HttpParentCases => CaseIds(HttpParentVectors);
    public static IEnumerable<object[]> RootCases => CaseIds(RootVectors);
    public static IEnumerable<object[]> DeniedCases => new[] { new object[] { "anonymous" }, new object[] { "wrong_permission" } };

    public async Task InitializeAsync()
    {
        try
        {
            await fixture.ResetAsync();
            app = fixture.CreateFactory(true);
            await using var scope = app.Services.CreateAsyncScope();
            var suppliers = scope.ServiceProvider.GetRequiredService<SupplierDbContext>();
            suppliers.Suppliers.Add(new Supplier { Id = 9100, Name = "Untouched synthetic supplier" });
            await suppliers.SaveChangesAsync();
            var orders = scope.ServiceProvider.GetRequiredService<PurchaseOrderDbContext>();
            orders.PurchaseOrders.AddRange(
                new PurchaseOrder { Id = 9100, Notes = "Untouched first parent" },
                new PurchaseOrder { Id = 9200, Notes = "Untouched second parent" });
            var now = Now();
            orders.Files.AddRange(
                new PurchaseOrderFile { Id = 9100, PurchaseOrderId = 9100, Bucket = "seed", ObjectName = "seed.step", CreatedDate = now, ModifiedDate = now },
                new PurchaseOrderFile { Id = 9200, PurchaseOrderId = 9200, Bucket = "sentinel", ObjectName = "untouched.step", CreatedDate = now, ModifiedDate = now });
            await orders.SaveChangesAsync();
        }
        catch (Exception initializationFailure)
        {
            try { await DisposeAsync(); }
            catch (Exception cleanupFailure)
            {
                throw new AggregateException("File metadata initialization and cleanup both failed.", initializationFailure, cleanupFailure);
            }
            throw;
        }
    }

    public Task DisposeAsync()
    {
        var owned = app;
        app = null!;
        return owned is null ? Task.CompletedTask : owned.DisposeAsync().AsTask();
    }

    [Theory]
    [MemberData(nameof(PrimitiveCases))]
    public void PrimitiveMembers_UsePublicTypedStringReader(string caseId)
    {
        var (field, token) = PrimitiveVectors[caseId];
        using var reader = PublicReader(token);
        var expected = reader.ReadAsString();
        var value = Bind(Payload(field, token));
        Assert.Equal(expected, Field(value, field));
        Assert.Null(value.PurchaseOrderId);
    }

    [Theory]
    [MemberData(nameof(EdgeCases))]
    public void TextEdges_MatchPublicTypedReaderWithoutOwnerCoercion(string caseId)
    {
        var token = EdgeVectors[caseId];
        using var reader = PublicReader(token);
        var expected = reader.ReadAsString();
        var value = Bind($"{{\"Bucket\":{token},\"ObjectName\":{token}}}");
        Assert.Equal(expected, value.Bucket);
        Assert.Equal(expected, value.ObjectName);
        Assert.Null(value.PurchaseOrderId);
    }

    [Theory]
    [MemberData(nameof(OrderedCases))]
    public void OrderedOccurrences_MatchNullIgnoringPublicProjection(string caseId)
    {
        foreach (var field in new[] { "Bucket", "ObjectName" })
        {
            var payload = Repeated(field, OrderedVectors[caseId]);
            var expected = PublicProjection(payload);
            var actual = Bind(payload);
            Assert.Equal(expected.Bucket, actual.Bucket);
            Assert.Equal(expected.ObjectName, actual.ObjectName);
            Assert.Null(actual.PurchaseOrderId);
        }
    }

    [Theory]
    [MemberData(nameof(MalformedCases))]
    public void MalformedRecognizedOccurrence_CannotBeHiddenByAnotherValue(string caseId)
    {
        var value = MalformedVectors[caseId];
        var tokens = value.Position == "only" ? value.Token
            : value.Position == "before" ? value.Token + ",\"valid\"" : "\"valid\"," + value.Token;
        var payload = Repeated(value.Field, tokens);
        Assert.ThrowsAny<Newtonsoft.Json.JsonException>(() => PublicProjection(payload));
        var expectedError = Assert.Throws<JsonException>(() => JsonSerializer.Deserialize<UpsertPurchaseOrderFileRequest>(payload, WithoutFileConverter()));
        var actualError = Assert.Throws<JsonException>(() => Bind(payload));
        Assert.Equal(expectedError.Path, actualError.Path);
    }

    [Theory]
    [MemberData(nameof(CasingCases))]
    public void PropertyNames_MatchPublicPropertyCollection(string caseId)
    {
        var (name, recognized) = CasingVectors[caseId];
        var properties = new Newtonsoft.Json.Serialization.JsonPropertyCollection(typeof(MetadataProjection));
        properties.AddProperty(new Newtonsoft.Json.Serialization.JsonProperty { PropertyName = "Bucket" });
        properties.AddProperty(new Newtonsoft.Json.Serialization.JsonProperty { PropertyName = "ObjectName" });
        Assert.Equal(recognized, properties.GetClosestMatchProperty(name)?.PropertyName);
        var actual = Bind($"{{\"{name}\":{(recognized is null ? "{}" : "123")}}}");
        Assert.Equal(recognized == "Bucket" ? "123" : null, actual.Bucket);
        Assert.Equal(recognized == "ObjectName" ? "123" : null, actual.ObjectName);
    }

    [Theory]
    [MemberData(nameof(ParentCases))]
    public void ParentRepresentations_DelegateToUnchangedMvcReader(string caseId)
    {
        var payload = WithParent(ParentVectors[caseId]);
        UpsertPurchaseOrderFileRequest? expected = null;
        UpsertPurchaseOrderFileRequest? actual = null;
        var expectedError = Record.Exception(() => { expected = JsonSerializer.Deserialize<UpsertPurchaseOrderFileRequest>(payload, WithoutFileConverter()); });
        var actualError = Record.Exception(() => { actual = Bind(payload); });
        if (expectedError is null)
        {
            Assert.Null(actualError);
            Assert.Equal(expected, actual);
        }
        else
        {
            Assert.NotNull(actualError);
            Assert.Equal(expectedError.GetType(), actualError.GetType());
            Assert.Equal(Assert.IsType<JsonException>(expectedError).Path, Assert.IsType<JsonException>(actualError).Path);
        }
    }

    [Theory]
    [MemberData(nameof(PrimitiveCases))]
    public async Task HttpPrimitiveMembers_RoundTripExactly(string caseId)
    {
        var (field, token) = PrimitiveVectors[caseId];
        var payload = Payload(field, token);
        var expected = PublicProjection(payload);
        await AssertRoundTripAsync(payload, expected.Bucket!, expected.ObjectName!, 9100);
    }

    [Theory]
    [MemberData(nameof(HttpOrderedCases))]
    public async Task HttpOrderedNullAndEmpty_KeepLiteralMetadata(string caseId)
    {
        var (field, tokens) = HttpOrderedVectors[caseId];
        var payload = Repeated(field, tokens);
        var expected = PublicProjection(payload);
        await AssertRoundTripAsync(payload, expected.Bucket!, expected.ObjectName!, 9100);
    }

    [Theory]
    [MemberData(nameof(HttpMalformedCases))]
    public async Task HttpMalformedOccurrence_IsBadRequestWithoutWrites(string caseId)
    {
        var value = HttpMalformedVectors[caseId];
        var malformed = value.Token == "{}" ? "{\"private\":\"SYNTHETIC-PRIVATE-METADATA\"}" : "[\"SYNTHETIC-PRIVATE-METADATA\"]";
        await AssertRefusedAsync(Repeated(value.Field, malformed + ",\"valid\""), HttpStatusCode.BadRequest);
    }

    [Theory]
    [MemberData(nameof(HttpParentCases))]
    public async Task HttpParentValues_RetainExistingNullablePolicy(string caseId)
    {
        var payload = WithParent(HttpParentVectors[caseId]);
        var expected = JsonSerializer.Deserialize<UpsertPurchaseOrderFileRequest>(payload, WithoutFileConverter())!;
        await AssertRoundTripAsync(payload, expected.Bucket, expected.ObjectName, expected.PurchaseOrderId ?? 9100);
    }

    [Theory]
    [MemberData(nameof(DeniedCases))]
    public async Task HttpDeniedActor_CannotMutateMetadata(string caseId)
    {
        using var client = caseId == "anonymous" ? app.CreateClient()
            : fixture.ClientAs(app, "service:procurement-parity", ProcurementPermissions.PurchaseOrdersRead);
        var before = await SnapshotAsync();
        using var response = await SendAsync(client, WithParent(""));
        Assert.Equal(caseId == "anonymous" ? HttpStatusCode.Unauthorized : HttpStatusCode.Forbidden, response.StatusCode);
        Assert.Equal(before, await SnapshotAsync());
    }

    [Theory]
    [MemberData(nameof(RootCases))]
    public Task HttpWrongRoot_IsBadRequestWithoutWrites(string caseId)
        => AssertRefusedAsync(RootVectors[caseId], HttpStatusCode.BadRequest);

    [Fact]
    public void Converter_IsRequestLocalAndPreservesDefaultWriteAndUnknownHandling()
    {
        Assert.Throws<JsonException>(() => JsonSerializer.Deserialize<UpsertPurchaseOrderFileRequest>("{\"Bucket\":123}"));
        var minimalOptions = app.Services.GetRequiredService<IOptions<Microsoft.AspNetCore.Http.Json.JsonOptions>>().Value.SerializerOptions;
        Assert.Throws<JsonException>(() => JsonSerializer.Deserialize<UpsertPurchaseOrderFileRequest>("{\"Bucket\":123}", minimalOptions));
        Assert.Throws<JsonException>(() => JsonSerializer.Deserialize<PurchaseOrderFileResponse>("{\"Bucket\":123}", Options));
        var literal = new UpsertPurchaseOrderFileRequest(null, " bucket ", " ไทย %_.step ");
        Assert.Equal(JsonSerializer.Serialize(literal, WithoutFileConverter()), JsonSerializer.Serialize(literal, Options));
        using var wire = JsonDocument.Parse(JsonSerializer.Serialize(literal, Options));
        Assert.Equal(new[] { "Bucket", "ObjectName" }, wire.RootElement.EnumerateObject().Select(value => value.Name).ToArray());
        Assert.Equal(JsonValueKind.String, wire.RootElement.GetProperty("Bucket").ValueKind);
        Assert.Equal(JsonValueKind.String, wire.RootElement.GetProperty("ObjectName").ValueKind);
        var payload = "{\"Bucket\":\"bucket\",\"ObjectName\":\"name\",\"Id\":7007,\"CreatedDate\":[],\"ModifiedDate\":true,\"Unknown\":{\"Bucket\":[]}}";
        Assert.NotNull(JsonSerializer.Deserialize<UpsertPurchaseOrderFileRequest>(payload, WithoutFileConverter()));
        Assert.Throws<JsonException>(() => Bind(payload));
        var unknown = "{\"Bucket\":\"bucket\",\"ObjectName\":\"name\",\"Id\":7007,\"Unknown\":{\"Bucket\":[],\"CreatedDate\":[],\"ModifiedDate\":true}}";
        Assert.Equal(JsonSerializer.Deserialize<UpsertPurchaseOrderFileRequest>(unknown, WithoutFileConverter()), Bind(unknown));
        Assert.Throws<JsonException>(() => Bind("{\"Bucket\":\"bucket\"} {}"));
    }

    [MethodImpl(MethodImplOptions.NoInlining)]
    private UpsertPurchaseOrderFileRequest Bind(string payload)
        => JsonSerializer.Deserialize<UpsertPurchaseOrderFileRequest>(payload, Options)!;

    private JsonSerializerOptions WithoutFileConverter() => NativeMvcOptions();

    private const string OwnedConfigure = "Legacy.Maliev.ProcurementService.Api.Serialization.ProcurementIgnoredBodyIdJsonOptions";

    private static bool IsOwnedConfigure(IConfigureOptions<Microsoft.AspNetCore.Mvc.JsonOptions> action)
        => action.GetType().FullName == OwnedConfigure && action.GetType().Assembly == typeof(ProcurementPermissions).Assembly;

    private static Microsoft.AspNetCore.Mvc.JsonOptions ConstructNativeMvcOptions(
        IConfigureOptions<Microsoft.AspNetCore.Mvc.JsonOptions>[] setups,
        IPostConfigureOptions<Microsoft.AspNetCore.Mvc.JsonOptions>[] posts,
        IValidateOptions<Microsoft.AspNetCore.Mvc.JsonOptions>[] validations)
    {
        var nativeSetups = setups.Where(action => !IsOwnedConfigure(action)).ToArray();
        Assert.InRange(setups.Length - nativeSetups.Length, 0, 1);
        var index = 0;
        foreach (var action in setups)
        {
            if (IsOwnedConfigure(action)) continue;
            Assert.Same(action, nativeSetups[index++]);
        }
        Assert.Equal(nativeSetups.Length, index);
        // OptionsFactory preserves ordered named/default Configure actions, followed by
        // every PostConfigure and validator. No candidate resolver is inspected or unwrapped.
        return new OptionsFactory<Microsoft.AspNetCore.Mvc.JsonOptions>(nativeSetups, posts, validations)
            .Create(Microsoft.Extensions.Options.Options.DefaultName);
    }

    private JsonSerializerOptions NativeMvcOptions()
    {
        Assert.IsType<OptionsFactory<Microsoft.AspNetCore.Mvc.JsonOptions>>(app.Services.GetRequiredService<IOptionsFactory<Microsoft.AspNetCore.Mvc.JsonOptions>>());
        var setups = app.Services.GetServices<IConfigureOptions<Microsoft.AspNetCore.Mvc.JsonOptions>>().ToArray();
        var posts = app.Services.GetServices<IPostConfigureOptions<Microsoft.AspNetCore.Mvc.JsonOptions>>().ToArray();
        var validations = app.Services.GetServices<IValidateOptions<Microsoft.AspNetCore.Mvc.JsonOptions>>().ToArray();
        var configured = ConstructNativeMvcOptions(setups, posts, validations);
        var native = new JsonSerializerOptions(configured.JsonSerializerOptions);
        // Historical0c/9005 controls already removed this exact pre-existing whole-DTO
        // converter. Keep that bounded native comparison policy on read-only baselines.
        for (var index = native.Converters.Count - 1; index >= 0; index--)
            if (native.Converters[index].GetType().FullName ==
                    FileConverter
                && native.Converters[index].GetType().Assembly == typeof(ProcurementPermissions).Assembly)
                native.Converters.RemoveAt(index);
        foreach (var requestType in new[] { typeof(UpsertSupplierAddressRequest), typeof(UpsertPurchaseOrderAddressRequest), typeof(UpsertPurchaseOrderFileRequest) })
        {
            var metadata = native.GetTypeInfo(requestType);
            Assert.Equal(System.Text.Json.Serialization.Metadata.JsonTypeInfoKind.Object, metadata.Kind);
            Assert.DoesNotContain(metadata.Properties, property => property.Name == "Id");
            Assert.DoesNotContain(metadata.Properties, property => property.CustomConverter?.GetType().FullName is
                "Legacy.Maliev.ProcurementService.Api.Serialization.IgnoredBodyInt32JsonConverter" or
                FileConverter);
        }
        return native;
    }

    private static IEnumerable<object[]> CaseIds<T>(IReadOnlyDictionary<string, T> vectors)
        => vectors.Keys.Select(value => new object[] { value });
    private static JsonTextReader PublicReader(string token)
        => new(new StringReader(token)) { Culture = CultureInfo.InvariantCulture, CloseInput = true };
    private static MetadataProjection PublicProjection(string payload)
        => JsonConvert.DeserializeObject<MetadataProjection>(payload, new JsonSerializerSettings { NullValueHandling = NullValueHandling.Ignore })!;
    private static string? Field(UpsertPurchaseOrderFileRequest request, string field)
        => field == "Bucket" ? request.Bucket : request.ObjectName;
    private static string Payload(string field, string token)
    {
        var other = field == "Bucket" ? "ObjectName" : "Bucket";
        return $"{{\"{other}\":\"unchanged\",\"{field}\":{token}}}";
    }
    private static string Repeated(string field, string tokens)
    {
        var other = field == "Bucket" ? "ObjectName" : "Bucket";
        var values = tokens.Length == 0 ? Array.Empty<string>() : tokens.Split(',');
        return $"{{\"{other}\":\"unchanged\"" + string.Concat(values.Select((token, index) =>
            $",\"{(index % 2 == 0 ? field : field.ToLowerInvariant())}\":{token}")) + "}";
    }
    private static string WithParent(string fragment)
        => "{\"Bucket\":\"literal\",\"ObjectName\":\" literal ไทย %_.step \"" + (fragment.Length == 0 ? "" : "," + fragment) + "}";
    private HttpClient Writer() => fixture.ClientAs(app, "service:procurement-parity", ProcurementPermissions.FilesWrite, ProcurementPermissions.FilesRead);
    private DateTime Now() => DateTime.SpecifyKind(fixture.Clock.GetUtcNow().UtcDateTime, DateTimeKind.Unspecified);
    private static async Task<HttpResponseMessage> SendAsync(HttpClient client, string payload)
    {
        using var content = new StringContent(payload, Encoding.UTF8, "application/json");
        return await client.PutAsync("/purchaseorders/files/9100", content);
    }

    private async Task AssertRoundTripAsync(string payload, string bucket, string objectName, int owner)
    {
        using var client = Writer();
        var original = (await client.GetFromJsonAsync<PurchaseOrderFileResponse>("/purchaseorders/files/9100"))!;
        var untouched = await SnapshotAsync(excludeTarget: true);
        fixture.Clock.Advance(TimeSpan.FromSeconds(1));
        using var response = await SendAsync(client, payload);
        Assert.Equal(HttpStatusCode.NoContent, response.StatusCode);
        using var fresh = await client.GetAsync("/purchaseorders/files/9100");
        Assert.Equal(HttpStatusCode.OK, fresh.StatusCode);
        var current = (await fresh.Content.ReadFromJsonAsync<PurchaseOrderFileResponse>())!;
        Assert.Equal(9100, current.Id);
        Assert.Equal(owner, current.PurchaseOrderId);
        Assert.Equal(bucket, current.Bucket);
        Assert.Equal(objectName, current.ObjectName);
        Assert.Equal(original.CreatedDate, current.CreatedDate);
        Assert.Equal(Now(), current.ModifiedDate);
        Assert.True(current.ModifiedDate > original.ModifiedDate);
        using var wire = JsonDocument.Parse(await fresh.Content.ReadAsStringAsync());
        Assert.Equal(JsonValueKind.String, wire.RootElement.GetProperty("Bucket").ValueKind);
        Assert.Equal(JsonValueKind.String, wire.RootElement.GetProperty("ObjectName").ValueKind);
        var list = (await client.GetFromJsonAsync<PurchaseOrderFileResponse[]>($"/purchaseorders/{owner}/files"))!;
        Assert.Equal(current, Assert.Single(list, value => value.Id == current.Id));
        if (owner != original.PurchaseOrderId)
        {
            using var oldOwner = await client.GetAsync($"/purchaseorders/{original.PurchaseOrderId}/files");
            Assert.Equal(HttpStatusCode.NotFound, oldOwner.StatusCode);
        }
        await using var scope = app.Services.CreateAsyncScope();
        var db = scope.ServiceProvider.GetRequiredService<PurchaseOrderDbContext>();
        var row = await db.Files.AsNoTracking().SingleAsync(value => value.Id == 9100);
        Assert.Equal(current, new PurchaseOrderFileResponse(row.Id, row.PurchaseOrderId, row.Bucket, row.ObjectName, row.CreatedDate, row.ModifiedDate));
        Assert.Equal(untouched, await SnapshotAsync(excludeTarget: true));
    }

    private async Task AssertRefusedAsync(string payload, HttpStatusCode status)
    {
        using var client = Writer();
        var before = await SnapshotAsync();
        using var response = await SendAsync(client, payload);
        Assert.Equal(status, response.StatusCode);
        Assert.DoesNotContain("SYNTHETIC-PRIVATE-METADATA", await response.Content.ReadAsStringAsync(), StringComparison.Ordinal);
        Assert.Equal(before, await SnapshotAsync());
    }

    private async Task<string> SnapshotAsync(bool excludeTarget = false)
    {
        await using var scope = app.Services.CreateAsyncScope();
        using var lifetime = new CancellationTokenSource(TimeSpan.FromSeconds(45));
        var snapshots = new List<string>();
        foreach (var boundary in new[]
        {
            (Context: (DbContext)scope.ServiceProvider.GetRequiredService<SupplierDbContext>(), Tables: new[] { "Address", "Supplier", "SupplierCreateReceipt" }),
            (Context: (DbContext)scope.ServiceProvider.GetRequiredService<PurchaseOrderDbContext>(), Tables: new[] { "Address", "PurchaseOrder", "OrderItem", "PurchaseOrderFile", "PurchaseOrderCreateReceipt" }),
        })
            foreach (var table in boundary.Tables)
            {
                var filter = excludeTarget && table == "PurchaseOrderFile" ? " WHERE \"ID\" <> 9100" : "";
                var sql = $"SELECT COALESCE(jsonb_agg(to_jsonb(r) ORDER BY to_jsonb(r)::text)::text,'[]') AS \"Value\" FROM (SELECT * FROM public.\"{table}\"{filter}) r";
                snapshots.Add(boundary.Context.GetType().Name + ":" + table + ":" + await boundary.Context.Database.SqlQueryRaw<string>(sql).SingleAsync(lifetime.Token));
            }
        return string.Join("\n", snapshots);
    }

    private sealed class MetadataProjection
    {
        public string? Bucket { get; set; }
        public string? ObjectName { get; set; }
    }
}

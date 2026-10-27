using System.Net;
using System.Net.Http.Json;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization.Metadata;
using Legacy.Maliev.ProcurementService.Api.Authorization;
using Legacy.Maliev.ProcurementService.Api.Serialization;
using Legacy.Maliev.ProcurementService.Application.Models;
using Legacy.Maliev.ProcurementService.Data;
using Legacy.Maliev.ProcurementService.Domain;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Options;

namespace Legacy.Maliev.ProcurementService.Tests.Integration;

public sealed class ProcurementMetadataIgnoredBodyIdTests(ProcurementRuntimeFixture fixture)
    : IClassFixture<ProcurementRuntimeFixture>, IAsyncLifetime
{
    private ProcurementRuntimeFactory app = null!;
    private static readonly string[] Operations = ["supplier_post", "supplier_put", "address_post", "address_put", "file_put"];
    private JsonSerializerOptions Options => app.Services.GetRequiredService<IOptions<Microsoft.AspNetCore.Mvc.JsonOptions>>().Value.JsonSerializerOptions;
    private DateTime Now() => DateTime.SpecifyKind(fixture.Clock.GetUtcNow().UtcDateTime, DateTimeKind.Unspecified);

    public async Task InitializeAsync()
    {
        try
        {
            await fixture.ResetAsync();
            app = fixture.CreateFactory(true);
            await using var scope = app.Services.CreateAsyncScope();
            var suppliers = scope.ServiceProvider.GetRequiredService<SupplierDbContext>();
            suppliers.Addresses.AddRange(
                new SupplierAddress { Id = 7001, Address1 = "original", CountryId = 1, CreatedDate = Now(), ModifiedDate = Now() },
                new SupplierAddress { Id = 7007, Address1 = "untouched body identity", CountryId = 1 });
            suppliers.Suppliers.Add(new Supplier { Id = 7002, Name = "owner", AddressId = 7001, CreatedDate = Now(), ModifiedDate = Now() });
            await suppliers.SaveChangesAsync();
            var orders = scope.ServiceProvider.GetRequiredService<PurchaseOrderDbContext>();
            orders.Addresses.AddRange(
                new PurchaseOrderAddress { Id = 7003, AddressLine1 = "original", CountryId = 1, CreatedDate = Now(), ModifiedDate = Now() },
                new PurchaseOrderAddress { Id = 7007, AddressLine1 = "untouched body identity", CountryId = 1 });
            orders.PurchaseOrders.Add(new PurchaseOrder { Id = 7004, SupplierId = 7002, ShippingAddressId = 7003, BillingAddressId = 7003 });
            orders.OrderItems.Add(new OrderItem { Id = 7005, PurchaseOrderId = 7004, PartNumber = "untouched" });
            orders.Files.AddRange(
                new PurchaseOrderFile { Id = 7006, PurchaseOrderId = 7004, Bucket = "original", ObjectName = "original", CreatedDate = Now(), ModifiedDate = Now() },
                new PurchaseOrderFile { Id = 7007, PurchaseOrderId = 7004, Bucket = "untouched", ObjectName = "body identity" });
            await orders.SaveChangesAsync();
        }
        catch (Exception initializationFailure)
        {
            try { await DisposeAsync(); }
            catch (Exception cleanupFailure)
            {
                throw new AggregateException("Ignored metadata identity initialization and cleanup both failed.", initializationFailure, cleanupFailure);
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

    public static IEnumerable<object[]> ValidIds => Cross(["0", "-17", "2147483647", "-2147483648", "\"42\"", "\" +42 \"", "\"\"", "null", "123", "7007"]);
    public static IEnumerable<object[]> InvalidIds => Cross(["1.5", "1e3", "true", "false", "[]", "{}", "2147483648", "-2147483649", "\"nope\"", "\"1.0\"", "\"2147483648\"", "\"null\""]);
    public static IEnumerable<object[]> DuplicateIds => Operations.SelectMany(operation => new[]
    {
        new object[] { operation, "\"Id\":{},\"id\":1,", false },
        new object[] { operation, "\"Id\":1,\"id\":[],", false },
        new object[] { operation, "\"Id\":2147483647,\"id\":null,", true },
        new object[] { operation, "\"Id\":null,\"ID\":7007,", true },
    });
    public static IEnumerable<object[]> OmittedIds => Operations.Select(operation => new object[] { operation });
    public static IEnumerable<object[]> DeniedIds => Operations.SelectMany(operation => new[] { new object[] { operation, true }, new object[] { operation, false } });
    public static IEnumerable<object[]> MissingRecords => Operations.Where(operation => operation != "address_post").Select(operation => new object[] { operation });

    [Theory]
    [MemberData(nameof(ValidIds))]
    public Task ValidBodyIdentity_IsParsedThenDiscardedWithoutChangingRouteOrGraph(string operation, string token)
        => AssertAppliedAsync(operation, "\"iD\":" + token + ",");

    [Theory]
    [MemberData(nameof(InvalidIds))]
    public async Task InvalidBodyIdentity_IsBadRequestWithoutAnyWrite(string operation, string token)
    {
        using var client = Writer();
        var before = await SnapshotAsync();
        using var response = await SendAsync(client, operation, "\"Id\":" + token + ",");
        Assert.Equal(HttpStatusCode.BadRequest, response.StatusCode);
        Assert.Equal(before, await SnapshotAsync());
    }

    [Theory]
    [MemberData(nameof(DuplicateIds))]
    public async Task EveryIdentityOccurrence_IsValidatedBeforeDiscard(string operation, string members, bool accepted)
    {
        if (accepted) { await AssertAppliedAsync(operation, members); return; }
        using var client = Writer();
        var before = await SnapshotAsync();
        using var response = await SendAsync(client, operation, members);
        Assert.Equal(HttpStatusCode.BadRequest, response.StatusCode);
        Assert.Equal(before, await SnapshotAsync());
    }

    [Theory]
    [MemberData(nameof(OmittedIds))]
    public Task OmittedIdentityAndUnknownNestedMembers_PreserveExistingContract(string operation)
        => AssertAppliedAsync(operation, "\"Unknown\":{\"Id\":{}},");

    [Theory]
    [MemberData(nameof(DeniedIds))]
    public async Task AuthenticationAndAuthorization_PrecedeIdentityBinding(string operation, bool anonymous)
    {
        using var client = anonymous ? app.CreateClient() : fixture.ClientAs(app, "service:procurement-parity", ProcurementPermissions.PurchaseOrdersRead);
        var before = await SnapshotAsync();
        using var response = await SendAsync(client, operation, "\"Id\":{},");
        Assert.Equal(anonymous ? HttpStatusCode.Unauthorized : HttpStatusCode.Forbidden, response.StatusCode);
        Assert.Equal(before, await SnapshotAsync());
    }

    [Theory]
    [MemberData(nameof(MissingRecords))]
    public async Task ValidIgnoredIdentity_DoesNotReplaceMissingRouteOrOwner(string operation)
    {
        using var client = Writer();
        var before = await SnapshotAsync();
        using var response = await SendAsync(client, operation, "\"Id\":7007,", missing: true);
        Assert.Equal(HttpStatusCode.NotFound, response.StatusCode);
        Assert.Equal(before, await SnapshotAsync());
    }

    [Fact]
    public void NativeMetadata_HasExactOwnedPropertiesAndUnchangedWriteShapes()
    {
        var owned = Assert.Single(app.Services.GetServices<IConfigureOptions<Microsoft.AspNetCore.Mvc.JsonOptions>>(), IsOwnedConfigure);
        AssertNativeFactoryOrderingAndValidation(owned);
        foreach (var type in new[] { typeof(UpsertSupplierAddressRequest), typeof(UpsertPurchaseOrderAddressRequest), typeof(UpsertPurchaseOrderFileRequest) })
        {
            var metadata = Options.GetTypeInfo(type);
            Assert.Equal(JsonTypeInfoKind.Object, metadata.Kind);
            var identity = Assert.Single(metadata.Properties, property => property.Name == "Id");
            Assert.Equal(typeof(int?), identity.PropertyType);
            Assert.Equal("IgnoredBodyInt32JsonConverter", identity.CustomConverter!.GetType().Name);
            Assert.NotNull(identity.Set);
            var value = JsonSerializer.Deserialize("{\"Id\":7007}", type, Options)!;
            identity.Set!(value, 123);
            Assert.Null(identity.Get!(value));
            Assert.False(identity.ShouldSerialize!(value, null));
            using var wire = JsonDocument.Parse(JsonSerializer.Serialize(value, type, Options));
            Assert.False(wire.RootElement.TryGetProperty("Id", out _));
            Assert.DoesNotContain(type.GetProperties(), property => property.Name == "Id");
            Assert.Equal(type == typeof(UpsertPurchaseOrderFileRequest) ? 3 : 7, type.GetProperties().Length);
        }
        var file = Options.GetTypeInfo(typeof(UpsertPurchaseOrderFileRequest));
        Assert.NotNull(file.CreateObject);
        Assert.Equal(new[] { "Bucket", "ObjectName" }, file.Properties.Where(property => property.CustomConverter is PurchaseOrderFileMetadataRequestJsonConverter).Select(property => property.Name).Order().ToArray());
        Assert.DoesNotContain(Options.Converters, converter => converter is PurchaseOrderFileMetadataRequestJsonConverter);
        foreach (var type in new[] { typeof(SupplierAddressResponse), typeof(PurchaseOrderAddressResponse), typeof(PurchaseOrderFileResponse) })
            Assert.DoesNotContain(Options.GetTypeInfo(type).Properties, property => property.CustomConverter?.GetType().Name == "IgnoredBodyInt32JsonConverter");
        var minimal = app.Services.GetRequiredService<IOptions<Microsoft.AspNetCore.Http.Json.JsonOptions>>().Value.SerializerOptions;
        Assert.Throws<JsonException>(() => JsonSerializer.Deserialize<UpsertPurchaseOrderFileRequest>("{\"Bucket\":123}", minimal));
    }

    public static IEnumerable<object[]> MalformedPaths
        => new[] { "supplier", "address", "file" }.SelectMany(contract =>
            new[] { "id_missing", "id_string", "unknown_object", "unknown_array", "text_string", "numeric_syntax", "numeric_object" }
                .Select(caseId => new object[] { contract, caseId }));

    private static Type RequestType(string contract) => contract switch
    {
        "supplier" => typeof(UpsertSupplierAddressRequest),
        "address" => typeof(UpsertPurchaseOrderAddressRequest),
        _ => typeof(UpsertPurchaseOrderFileRequest),
    };

    private static string MalformedPayload(string contract, string caseId)
    {
        var text = contract == "supplier" ? "Address1" : contract == "address" ? "AddressLine1" : "Bucket";
        var numeric = contract == "file" ? "PurchaseOrderId" : "CountryId";
        return caseId switch
        {
            "id_missing" => "{\"Id\":",
            "id_string" => "{\"Id\":\"unterminated",
            "unknown_object" => "{\"Unknown\":{\"Nested\":",
            "unknown_array" => "{\"Unknown\":[1,",
            "text_string" => "{\"" + text + "\":\"unterminated",
            "numeric_syntax" => "{\"" + numeric + "\":tru}",
            _ => "{\"" + numeric + "\":{},\"Id\":1}",
        };
    }

    [Theory]
    [MemberData(nameof(MalformedPaths))]
    public void MalformedSyntaxAndUnchangedMembers_KeepActualNativePropertyPath(string contract, string caseId)
    {
        var type = RequestType(contract);
        var payload = MalformedPayload(contract, caseId);
        var native = NativeMvcOptions();
        // This control adds only a known native Id slot so the two traversals have
        // the same property location; its standard int reader performs no compatibility coercion.
        native = new JsonSerializerOptions(native);
        native.TypeInfoResolver = native.TypeInfoResolver!.WithAddedModifier(metadata =>
        {
            if (metadata.Type != type) return;
            var identity = metadata.CreateJsonPropertyInfo(typeof(int?), "Id");
            identity.Get = static _ => null;
            identity.Set = static (_, _) => { };
            identity.ShouldSerialize = static (_, _) => false;
            metadata.Properties.Add(identity);
        });
        Assert.DoesNotContain(native.GetTypeInfo(type).Properties, property => IsOwnedPropertyReader(property.CustomConverter));
        var expected = Assert.Throws<JsonException>(() => JsonSerializer.Deserialize(payload, type, native));
        var actual = Assert.Throws<JsonException>(() => JsonSerializer.Deserialize(payload, type, Options));
        Assert.Equal(expected.Path, actual.Path);
        Assert.NotNull(actual.Path);
    }

    private static void AssertNativeFactoryOrderingAndValidation(IConfigureOptions<Microsoft.AspNetCore.Mvc.JsonOptions> owned)
    {
        var events = new List<string>();
        var name = Microsoft.Extensions.Options.Options.DefaultName;
        var setups = new IConfigureOptions<Microsoft.AspNetCore.Mvc.JsonOptions>[]
        {
            new ConfigureNamedOptions<Microsoft.AspNetCore.Mvc.JsonOptions>(name, _ => events.Add("configure0")),
            owned,
            new ConfigureNamedOptions<Microsoft.AspNetCore.Mvc.JsonOptions>("other-name", _ => events.Add("wrong-name")),
            new ConfigureNamedOptions<Microsoft.AspNetCore.Mvc.JsonOptions>(null, _ => events.Add("configure1")),
        };
        var posts = new IPostConfigureOptions<Microsoft.AspNetCore.Mvc.JsonOptions>[]
        {
            new PostConfigureOptions<Microsoft.AspNetCore.Mvc.JsonOptions>(name, options =>
            {
                events.Add("post0");
                options.AllowInputFormatterExceptionMessages = false;
            }),
            new PostConfigureOptions<Microsoft.AspNetCore.Mvc.JsonOptions>(name, options =>
            {
                Assert.False(options.AllowInputFormatterExceptionMessages);
                events.Add("post1");
            }),
        };
        var validations = new IValidateOptions<Microsoft.AspNetCore.Mvc.JsonOptions>[]
        {
            new ValidateOptions<Microsoft.AspNetCore.Mvc.JsonOptions>(name, options =>
            {
                events.Add("validate0");
                return !options.AllowInputFormatterExceptionMessages;
            }, "postconfigure must run"),
            new ValidateOptions<Microsoft.AspNetCore.Mvc.JsonOptions>(name, _ =>
            {
                events.Add("validate1");
                return true;
            }, "second validator must run"),
        };
        Assert.False(ConstructNativeMvcOptions(setups, posts, validations).AllowInputFormatterExceptionMessages);
        Assert.Equal(new[] { "configure0", "configure1", "post0", "post1", "validate0", "validate1" }, events);
        events.Clear();
        var failures = new IValidateOptions<Microsoft.AspNetCore.Mvc.JsonOptions>[]
        {
            new ValidateOptions<Microsoft.AspNetCore.Mvc.JsonOptions>(name, _ => { events.Add("fail0"); return false; }, "first failure"),
            new ValidateOptions<Microsoft.AspNetCore.Mvc.JsonOptions>(name, _ => { events.Add("fail1"); return false; }, "second failure"),
        };
        var error = Assert.Throws<OptionsValidationException>(() => ConstructNativeMvcOptions(new[] { owned }, [], failures));
        Assert.Equal(new[] { "first failure", "second failure" }, error.Failures);
        Assert.Equal(new[] { "fail0", "fail1" }, events);
    }

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
                    "Legacy.Maliev.ProcurementService.Api.Serialization.PurchaseOrderFileMetadataRequestJsonConverter"
                && native.Converters[index].GetType().Assembly == typeof(ProcurementPermissions).Assembly)
                native.Converters.RemoveAt(index);
        foreach (var requestType in new[] { typeof(UpsertSupplierAddressRequest), typeof(UpsertPurchaseOrderAddressRequest), typeof(UpsertPurchaseOrderFileRequest) })
        {
            var metadata = native.GetTypeInfo(requestType);
            Assert.Equal(System.Text.Json.Serialization.Metadata.JsonTypeInfoKind.Object, metadata.Kind);
            Assert.DoesNotContain(metadata.Properties, property => property.Name == "Id");
            Assert.DoesNotContain(metadata.Properties, property => property.CustomConverter?.GetType().FullName is
                "Legacy.Maliev.ProcurementService.Api.Serialization.IgnoredBodyInt32JsonConverter" or
                "Legacy.Maliev.ProcurementService.Api.Serialization.PurchaseOrderFileMetadataRequestJsonConverter");
        }
        return native;
    }

    private static bool IsOwnedPropertyReader(System.Text.Json.Serialization.JsonConverter? converter)
        => converter?.GetType().FullName is
            "Legacy.Maliev.ProcurementService.Api.Serialization.IgnoredBodyInt32JsonConverter" or
            "Legacy.Maliev.ProcurementService.Api.Serialization.PurchaseOrderFileMetadataRequestJsonConverter";

    private static IEnumerable<object[]> Cross(string[] tokens)
        => Operations.SelectMany(operation => tokens.Select(token => new object[] { operation, token }));
    private HttpClient Writer() => fixture.ClientAs(app, "service:procurement-parity",
        ProcurementPermissions.SupplierAddressesWrite, ProcurementPermissions.SupplierAddressesRead,
        ProcurementPermissions.PurchaseOrderAddressesWrite, ProcurementPermissions.PurchaseOrderAddressesRead,
        ProcurementPermissions.FilesWrite, ProcurementPermissions.FilesRead);

    private static async Task<HttpResponseMessage> SendAsync(HttpClient client, string operation, string members, bool missing = false)
    {
        var target = missing ? 999999 : operation == "supplier_put" ? 7001 : operation == "address_put" ? 7003 : 7006;
        var owner = missing ? 999999 : 7002;
        var payload = operation.StartsWith("supplier", StringComparison.Ordinal)
            ? "{" + members + "\"Building\":true,\"Address1\":\"ชื่อไทย\",\"Address2\":1.2300E+03,\"CountryId\":66}"
            : operation == "file_put"
                ? "{" + members + "\"PurchaseOrderId\":7004,\"Bucket\":true,\"ObjectName\":1.2300E+03}"
                : "{" + members + "\"Building\":true,\"AddressLine1\":\"ชื่อไทย\",\"AddressLine2\":1.2300E+03,\"CountryId\":66}";
        using var content = new StringContent(payload, Encoding.UTF8, "application/json");
        return operation switch
        {
            "supplier_post" => await client.PostAsync($"/suppliers/{owner}/addresses", content),
            "supplier_put" => await client.PutAsync($"/suppliers/addresses/{target}", content),
            "address_post" => await client.PostAsync("/purchaseorders/addresses", content),
            "address_put" => await client.PutAsync($"/purchaseorders/addresses/{target}", content),
            _ => await client.PutAsync($"/purchaseorders/files/{target}", content),
        };
    }

    private async Task AssertAppliedAsync(string operation, string members)
    {
        using var client = Writer();
        var update = operation.EndsWith("put", StringComparison.Ordinal);
        var target = operation == "supplier_put" ? 7001 : operation == "address_put" ? 7003 : operation == "file_put" ? 7006 : 0;
        var before = await SnapshotAsync(operation, target);
        await using var initialScope = app.Services.CreateAsyncScope();
        var initialSuppliers = initialScope.ServiceProvider.GetRequiredService<SupplierDbContext>();
        var ownerBefore = await initialSuppliers.Suppliers.AsNoTracking().SingleAsync(value => value.Id == 7002);
        fixture.Clock.Advance(TimeSpan.FromSeconds(1));
        using var response = await SendAsync(client, operation, members);
        Assert.Equal(update ? HttpStatusCode.NoContent : HttpStatusCode.Created, response.StatusCode);
        if (!update)
        {
            using var created = JsonDocument.Parse(await response.Content.ReadAsStringAsync());
            target = created.RootElement.GetProperty("Id").GetInt32();
            Assert.InRange(target, 1, 100);
            Assert.NotNull(response.Headers.Location);
            using var location = await client.GetAsync(response.Headers.Location);
            Assert.Equal(HttpStatusCode.OK, location.StatusCode);
        }
        await using var scope = app.Services.CreateAsyncScope();
        var suppliers = scope.ServiceProvider.GetRequiredService<SupplierDbContext>();
        var orders = scope.ServiceProvider.GetRequiredService<PurchaseOrderDbContext>();
        if (operation.StartsWith("supplier", StringComparison.Ordinal))
        {
            var row = await suppliers.Addresses.AsNoTracking().SingleAsync(value => value.Id == target);
            Assert.Equal("ชื่อไทย", row.Address1);
            Assert.Equal("true", row.Building);
            Assert.Equal("1.2300E+03", row.Address2);
            Assert.Equal(66, row.CountryId);
            Assert.Equal(Now(), row.ModifiedDate);
            Assert.Equal(update ? Now().AddSeconds(-1) : Now(), row.CreatedDate);
            var ownerAfter = await suppliers.Suppliers.AsNoTracking().SingleAsync(value => value.Id == 7002);
            Assert.Equal(ownerBefore.Name, ownerAfter.Name);
            Assert.Equal(ownerBefore.CreatedDate, ownerAfter.CreatedDate);
            Assert.Equal(ownerBefore.ModifiedDate, ownerAfter.ModifiedDate);
            Assert.Equal(update ? ownerBefore.AddressId : target, ownerAfter.AddressId);
            ownerAfter.AddressId = ownerBefore.AddressId;
            ownerAfter.ModifiedDate = ownerBefore.ModifiedDate;
            Assert.Equal(JsonSerializer.Serialize(ownerBefore), JsonSerializer.Serialize(ownerAfter));
        }
        else if (operation == "file_put")
        {
            var row = await orders.Files.AsNoTracking().SingleAsync(value => value.Id == target);
            Assert.Equal(7004, row.PurchaseOrderId);
            Assert.Equal("true", row.Bucket);
            Assert.Equal("1.2300E+03", row.ObjectName);
            Assert.Equal(Now().AddSeconds(-1), row.CreatedDate);
            Assert.Equal(Now(), row.ModifiedDate);
        }
        else
        {
            var row = await orders.Addresses.AsNoTracking().SingleAsync(value => value.Id == target);
            Assert.Equal("ชื่อไทย", row.AddressLine1);
            Assert.Equal("true", row.Building);
            Assert.Equal("1.2300E+03", row.AddressLine2);
            Assert.Equal(66, row.CountryId);
            Assert.Equal(update ? Now().AddSeconds(-1) : Now(), row.CreatedDate);
            Assert.Equal(Now(), row.ModifiedDate);
        }
        Assert.Equal(before, await SnapshotAsync(operation, target));
    }

    private async Task<string> SnapshotAsync(string? operation = null, int target = 0)
    {
        await using var scope = app.Services.CreateAsyncScope();
        var suppliers = scope.ServiceProvider.GetRequiredService<SupplierDbContext>();
        var orders = scope.ServiceProvider.GetRequiredService<PurchaseOrderDbContext>();
        return JsonSerializer.Serialize(new
        {
            Suppliers = await suppliers.Suppliers.AsNoTracking().Where(value => operation != "supplier_post" || value.Id != 7002).OrderBy(value => value.Id).ToArrayAsync(),
            SupplierAddresses = await suppliers.Addresses.AsNoTracking().Where(value => operation == null || !operation.StartsWith("supplier") || value.Id != target).OrderBy(value => value.Id).ToArrayAsync(),
            PurchaseOrders = await orders.PurchaseOrders.AsNoTracking().OrderBy(value => value.Id).ToArrayAsync(),
            PurchaseOrderAddresses = await orders.Addresses.AsNoTracking().Where(value => operation == null || !operation.StartsWith("address") || value.Id != target).OrderBy(value => value.Id).ToArrayAsync(),
            OrderItems = await orders.OrderItems.AsNoTracking().OrderBy(value => value.Id).ToArrayAsync(),
            Files = await orders.Files.AsNoTracking().Where(value => operation != "file_put" || value.Id != target).OrderBy(value => value.Id).ToArrayAsync(),
        });
    }
}

using System.Collections.Concurrent;
using System.Globalization;
using System.Net;
using System.Net.Http.Headers;
using System.Text;
using System.Text.Json;
using Legacy.Maliev.ProcurementService.Api.Authorization;
using Legacy.Maliev.ProcurementService.Application.Interfaces;
using Legacy.Maliev.ProcurementService.Application.Models;
using Legacy.Maliev.ProcurementService.Data;
using Legacy.Maliev.ProcurementService.Domain;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.Mvc.Controllers;
using Microsoft.AspNetCore.Mvc.Formatters;
using Microsoft.AspNetCore.Mvc.Infrastructure;
using Microsoft.AspNetCore.Mvc.ModelBinding;
using Microsoft.AspNetCore.Mvc.Testing;
using Microsoft.AspNetCore.Routing;
using Microsoft.AspNetCore.Hosting;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Options;

namespace Legacy.Maliev.ProcurementService.Tests.Integration;

// Actual normal HTTP uses the retained RS256/two-database fixture. All fixtures
// and buffered streams are owned and disposed. No local test execution is claimed.
public sealed class ProcurementSourceBodyAdmissionTests(ProcurementRuntimeFixture fixture)
    : IClassFixture<ProcurementRuntimeFixture>, IAsyncLifetime
{
    private ProcurementRuntimeFactory owner = null!;
    private WebApplicationFactory<Program> app = null!;
    private readonly BodyAdmissionLogs logs = new();
    private const string MarkerKey = "supplier:7002";
    private const string MarkerValue = "SYNTHETIC-BODY-CACHE";
    private const string PrivateToken = "SYNTHETIC-PRIVATE-METADATA";
    private static readonly string[] Operations =
    [
        "supplier_post", "supplier_put", "supplier_address_post", "supplier_address_put",
        "order_address_post", "order_address_put", "file_put",
    ];

    public static IEnumerable<object[]> RejectedBodies => Operations.SelectMany(operation =>
        ProcurementMetadataVectors.RejectedPrefixes.Select(prefix => new object[] { operation, prefix }));
    public static IEnumerable<object[]> AdmittedBodies => Operations.SelectMany(operation =>
        ProcurementMetadataVectors.AdmittedPrefixes.Select(prefix => new object[] { operation, prefix }));
    public static IEnumerable<object[]> NoValueBodies => Operations.SelectMany(operation =>
        new[] { "{\"$ref\":\"missing\"}", "{\"$ref\":\"\"}" }.Select(body => new object[] { operation, body }));
    public static IEnumerable<object[]> UnexpectedBodies => Operations.Select(operation => new object[] { operation });
    public static IEnumerable<object[]> Contracts => ProcurementMetadataVectors.Contracts.Select(contract => new object[] { contract });
    public static IEnumerable<object[]> CursorContracts => ProcurementMetadataVectors.Contracts.SelectMany(contract =>
        new[] { new object[] { contract, false }, new object[] { contract, true } });
    public static IEnumerable<object[]> DeniedBodies => Operations.SelectMany(operation =>
        new[] { new object[] { operation, false }, new object[] { operation, true } });
    public static IEnumerable<object[]> MissingBodies => Operations.Where(operation => operation is not ("supplier_post" or "order_address_post"))
        .Select(operation => new object[] { operation });
    public static IEnumerable<object[]> EncodedBodies => Operations.SelectMany(operation =>
        new[] { new object[] { operation, false }, new object[] { operation, true } });

    public async Task InitializeAsync()
    {
        try
        {
            await fixture.ResetAsync();
            owner = fixture.CreateFactory(true);
            app = owner.WithWebHostBuilder(builder => builder.ConfigureLogging(logging => logging.AddProvider(logs)));
            await using var scope = app.Services.CreateAsyncScope();
            var suppliers = scope.ServiceProvider.GetRequiredService<SupplierDbContext>();
            suppliers.Addresses.AddRange(
                new SupplierAddress { Id = 7001, Address1 = "original", CountryId = 1, CreatedDate = Now(), ModifiedDate = Now() },
                new SupplierAddress { Id = 7007, Address1 = "untouched", CountryId = 1 });
            suppliers.Suppliers.Add(new Supplier { Id = 7002, Name = "owner", AddressId = 7001, CreatedDate = Now(), ModifiedDate = Now() });
            await suppliers.SaveChangesAsync();
            var orders = scope.ServiceProvider.GetRequiredService<PurchaseOrderDbContext>();
            orders.Addresses.AddRange(
                new PurchaseOrderAddress { Id = 7003, AddressLine1 = "original", CountryId = 1, CreatedDate = Now(), ModifiedDate = Now() },
                new PurchaseOrderAddress { Id = 7007, AddressLine1 = "untouched", CountryId = 1 });
            orders.PurchaseOrders.Add(new PurchaseOrder { Id = 7004, SupplierId = 7002, ShippingAddressId = 7003, BillingAddressId = 7003 });
            orders.OrderItems.Add(new OrderItem { Id = 7005, PurchaseOrderId = 7004, PartNumber = "untouched" });
            orders.Files.Add(new PurchaseOrderFile { Id = 7006, PurchaseOrderId = 7004, Bucket = "untouched", ObjectName = "untouched", CreatedDate = Now(), ModifiedDate = Now() });
            await orders.SaveChangesAsync();
        }
        catch (Exception initializationFailure)
        {
            try { await DisposeAsync(); }
            catch (Exception cleanupFailure)
            {
                throw new AggregateException("Body admission initialization and cleanup failed.", initializationFailure, cleanupFailure);
            }
            throw;
        }
    }

    public async Task DisposeAsync()
    {
        var child = app;
        app = null!;
        var parent = owner;
        owner = null!;
        try { if (child is not null) await child.DisposeAsync(); }
        finally { if (parent is not null) await parent.DisposeAsync(); }
    }

    [Theory]
    [MemberData(nameof(RejectedBodies))]
    public async Task NormalHttp_InvalidLeadingMetadataNeverReachesWrites(string operation, string prefix)
    {
        using var client = Writer();
        await SetMarkerAsync();
        var before = await SnapshotAsync();
        using var response = await SendAsync(client, operation, ProcurementMetadataVectors.Body(Contract(operation), prefix));
        Assert.Equal(HttpStatusCode.BadRequest, response.StatusCode);
        Assert.Equal(before, await SnapshotAsync());
        Assert.Equal(MarkerValue, await MarkerAsync());
        Assert.DoesNotContain(PrivateToken, await response.Content.ReadAsStringAsync(), StringComparison.Ordinal);
        Assert.DoesNotContain(logs.Messages, value => value.Contains(PrivateToken, StringComparison.Ordinal));
    }

    [Theory]
    [MemberData(nameof(AdmittedBodies))]
    public async Task NormalHttp_AdmittedPrefixesPreserveScalarWritesAndServerAuthority(string operation, string prefix)
    {
        using var client = Writer();
        fixture.Clock.Advance(TimeSpan.FromSeconds(1));
        using var response = await SendAsync(client, operation, ProcurementMetadataVectors.Body(Contract(operation), prefix));
        var update = operation.EndsWith("put", StringComparison.Ordinal);
        Assert.Equal(update ? HttpStatusCode.NoContent : HttpStatusCode.Created, response.StatusCode);
        var id = operation switch
        {
            "supplier_put" => 7002, "supplier_address_put" => 7001,
            "order_address_put" => 7003, "file_put" => 7006, _ => 0,
        };
        if (!update)
        {
            using var created = JsonDocument.Parse(await response.Content.ReadAsStringAsync());
            id = created.RootElement.GetProperty("Id").GetInt32();
            Assert.True(id > 0);
            Assert.NotNull(response.Headers.Location);
            using var read = await client.GetAsync(response.Headers.Location);
            Assert.Equal(HttpStatusCode.OK, read.StatusCode);
        }
        await using var scope = app.Services.CreateAsyncScope();
        var suppliers = scope.ServiceProvider.GetRequiredService<SupplierDbContext>();
        var orders = scope.ServiceProvider.GetRequiredService<PurchaseOrderDbContext>();
        if (operation is "supplier_post" or "supplier_put")
        {
            var row = await suppliers.Suppliers.AsNoTracking().SingleAsync(value => value.Id == id);
            Assert.Equal("outer", row.Name);
            Assert.Equal("site", row.Website);
            Assert.Equal("mail", row.Email);
            Assert.Equal(Now(), row.ModifiedDate);
            Assert.Equal(update ? Now().AddSeconds(-1) : Now(), row.CreatedDate);
        }
        else if (operation.StartsWith("supplier_address", StringComparison.Ordinal))
        {
            var row = await suppliers.Addresses.AsNoTracking().SingleAsync(value => value.Id == id);
            Assert.Equal("outer", row.Address1);
            Assert.Equal(66, row.CountryId);
            Assert.Equal(Now(), row.ModifiedDate);
            Assert.Equal(update ? Now().AddSeconds(-1) : Now(), row.CreatedDate);
            if (!update)
                Assert.Equal(id, (await suppliers.Suppliers.AsNoTracking().SingleAsync(value => value.Id == 7002)).AddressId);
        }
        else if (operation.StartsWith("order_address", StringComparison.Ordinal))
        {
            var row = await orders.Addresses.AsNoTracking().SingleAsync(value => value.Id == id);
            Assert.Equal("outer", row.AddressLine1);
            Assert.Equal(66, row.CountryId);
            Assert.Equal(Now(), row.ModifiedDate);
            Assert.Equal(update ? Now().AddSeconds(-1) : Now(), row.CreatedDate);
        }
        else
        {
            var row = await orders.Files.AsNoTracking().SingleAsync(value => value.Id == id);
            Assert.Equal("outer", row.Bucket);
            Assert.Equal("name", row.ObjectName);
            Assert.Equal(7004, row.PurchaseOrderId);
            Assert.Equal(Now(), row.ModifiedDate);
            Assert.Equal(Now().AddSeconds(-1), row.CreatedDate);
        }
    }

    [Theory]
    [MemberData(nameof(NoValueBodies))]
    public async Task NormalHttp_UnregisteredReferencesFlowThroughRequiredBodyBinding(string operation, string body)
    {
        using var client = Writer();
        var before = await SnapshotAsync();
        using var response = await SendAsync(client, operation, body);
        Assert.Equal(HttpStatusCode.BadRequest, response.StatusCode);
        Assert.Equal(before, await SnapshotAsync());
        using var problem = JsonDocument.Parse(await response.Content.ReadAsStringAsync());
        Assert.True(problem.RootElement.GetProperty("errors").TryGetProperty("", out var required));
        Assert.NotEmpty(required.EnumerateArray());
    }

    [Theory]
    [MemberData(nameof(UnexpectedBodies))]
    public async Task NormalHttp_UnexpectedStockMetadataFailureIsNotBlanketBadRequest(string operation)
    {
        using var client = Writer();
        var before = await SnapshotAsync();
        using var response = await SendAsync(client, operation, ProcurementMetadataVectors.Body(Contract(operation), "\"$type\":null,"));
        Assert.Equal(HttpStatusCode.InternalServerError, response.StatusCode);
        Assert.Equal(before, await SnapshotAsync());
        Assert.DoesNotContain(PrivateToken, await response.Content.ReadAsStringAsync(), StringComparison.Ordinal);
    }

    [Theory]
    [MemberData(nameof(DeniedBodies))]
    public async Task NormalHttp_ActorAdmissionStillPrecedesBodyParsing(string operation, bool signed)
    {
        using var client = signed ? fixture.ClientAs(app, "service:procurement-parity", ProcurementPermissions.SuppliersRead) : app.CreateClient();
        var before = await SnapshotAsync();
        using var response = await SendAsync(client, operation, ProcurementMetadataVectors.Body(Contract(operation), "\"$type\":null,"));
        Assert.Equal(signed ? HttpStatusCode.Forbidden : HttpStatusCode.Unauthorized, response.StatusCode);
        Assert.Equal(before, await SnapshotAsync());
    }

    [Theory]
    [MemberData(nameof(MissingBodies))]
    public async Task NormalHttp_BindingFailurePrecedesLookupWhileValidSourceBodyRetainsNotFound(string operation)
    {
        using var client = Writer();
        var body = ProcurementMetadataVectors.Body(Contract(operation));
        var before = await SnapshotAsync();
        using var invalid = await SendAsync(client, operation, ProcurementMetadataVectors.Body(Contract(operation), "\"$ref\":1,"), missing: true);
        Assert.Equal(HttpStatusCode.BadRequest, invalid.StatusCode);
        using var valid = await SendAsync(client, operation, body, missing: true);
        Assert.Equal(HttpStatusCode.NotFound, valid.StatusCode);
        Assert.Equal(before, await SnapshotAsync());
    }

    [Theory]
    [MemberData(nameof(EncodedBodies))]
    public async Task NormalHttp_MediaAndCharsetSelectionRetainsUnsupported415(string operation, bool charset)
    {
        using var client = Writer();
        var before = await SnapshotAsync();
        using var request = Request(operation);
        request.Content = new ByteArrayContent(Encoding.UTF8.GetBytes(ProcurementMetadataVectors.Body(Contract(operation), "\"$type\":null,")));
        request.Content.Headers.ContentType = MediaTypeHeaderValue.Parse(charset ? "application/json; charset=iso-8859-1" : "text/plain");
        using var response = await client.SendAsync(request);
        Assert.Equal(HttpStatusCode.UnsupportedMediaType, response.StatusCode);
        Assert.Equal(before, await SnapshotAsync());
    }

    [Theory]
    [MemberData(nameof(Contracts))]
    public async Task SelectedFormatter_ReturnsGenuineNoValueAndLeavesNativeOptionsUntouched(string contract)
    {
        var type = RequestType(contract);
        var options = app.Services.GetRequiredService<IOptions<Microsoft.AspNetCore.Mvc.JsonOptions>>().Value.JsonSerializerOptions;
        var before = JsonSerializer.Serialize(JsonSerializer.Deserialize(ProcurementMetadataVectors.Body(contract, "\"$ref\":1,"), type, options), type, options);
        using var body = new MemoryStream(Encoding.UTF8.GetBytes("{\"$ref\":\"missing\"}"));
        var context = FormatterContext(type, body);
        var result = await Select(context).ReadAsync(context);
        Assert.False(result.HasError);
        Assert.False(result.IsModelSet);
        Assert.Same(body, context.HttpContext.Request.Body);
        Assert.Equal(0, body.Position);
        Assert.Equal(before, JsonSerializer.Serialize(JsonSerializer.Deserialize(ProcurementMetadataVectors.Body(contract, "\"$ref\":1,"), type, options), type, options));
    }

    [Theory]
    [MemberData(nameof(CursorContracts))]
    public async Task SelectedFormatter_UsesActualStockIdObjectCursorInsteadOfOuterFields(string contract, bool inner)
    {
        var members = inner ? ProcurementMetadataVectors.Members(contract, "inner", 77) : "";
        using var body = new MemoryStream(Encoding.UTF8.GetBytes(ProcurementMetadataVectors.Body(contract, "\"$id\":{" + members + "},")));
        var context = FormatterContext(RequestType(contract), body);
        var result = await Select(context).ReadAsync(context);
        Assert.False(result.HasError);
        Assert.True(result.IsModelSet);
        var property = result.Model!.GetType().GetProperty(ProcurementMetadataVectors.ScalarName(contract))!;
        Assert.Equal(inner ? "inner" : null, property.GetValue(result.Model));
        if (contract is "supplier-address" or "order-address")
            Assert.Equal(inner ? 77 : 0, result.Model.GetType().GetProperty("CountryId")!.GetValue(result.Model));
        Assert.Same(body, context.HttpContext.Request.Body);
        Assert.Equal(0, body.Position);
        Assert.True(body.CanRead);
    }

    [Theory]
    [MemberData(nameof(Contracts))]
    public async Task SelectedFormatter_UnsupportedCharsetNeverReadsTheBody(string contract)
    {
        using var body = new AsyncOnlyRequestBody(ProcurementMetadataVectors.Body(contract));
        var context = FormatterContext(RequestType(contract), body, "application/json; charset=iso-8859-1");
        var result = await Select(context).ReadAsync(context);
        Assert.True(result.HasError);
        Assert.Equal(0, body.AsyncReads);
        Assert.Equal(0, body.SyncReads);
        Assert.Contains(context.ModelState.Values.SelectMany(value => value.Errors), error => error.Exception is UnsupportedContentTypeException);
        Assert.Same(body, context.HttpContext.Request.Body);
        Assert.False(body.Disposed);
    }

    [Theory]
    [MemberData(nameof(Contracts))]
    public async Task SelectedFormatter_DrainsSocketAsynchronouslyAndRestoresOwnedContext(string contract)
    {
        using var body = new AsyncOnlyRequestBody(ProcurementMetadataVectors.Body(contract));
        var context = FormatterContext(RequestType(contract), body);
        var factory = context.ReaderFactory;
        var result = await Select(context).ReadAsync(context);
        Assert.False(result.HasError);
        Assert.True(result.IsModelSet);
        Assert.True(body.AsyncReads > 0);
        Assert.Equal(0, body.SyncReads);
        Assert.False(body.Disposed);
        Assert.Same(body, context.HttpContext.Request.Body);
        Assert.Same(factory, context.ReaderFactory);
    }

    [Fact]
    public async Task NormalHttp_AllResolvedRoutesForFourDtosAreCoveredIncludingAnyVersionAliases()
    {
        var owned = ProcurementMetadataVectors.Contracts.Select(RequestType).ToHashSet();
        var actions = app.Services.GetRequiredService<IActionDescriptorCollectionProvider>().ActionDescriptors.Items
            .OfType<ControllerActionDescriptor>().Where(action => action.Parameters.Any(parameter => owned.Contains(parameter.ParameterType))).ToArray();
        Assert.Equal(7, actions.Select(action => action.MethodInfo).Distinct().Count());
        var endpoints = app.Services.GetRequiredService<EndpointDataSource>().Endpoints.OfType<RouteEndpoint>()
            .Where(endpoint => endpoint.Metadata.GetMetadata<ControllerActionDescriptor>() is { } action
                && action.Parameters.Any(parameter => owned.Contains(parameter.ParameterType))).ToArray();
        Assert.NotEmpty(endpoints);
        Assert.Equal(7, endpoints.Select(endpoint => endpoint.Metadata.GetMetadata<ControllerActionDescriptor>()!.MethodInfo).Distinct().Count());
        var before = await SnapshotAsync();
        using var client = Writer();
        foreach (var endpoint in endpoints)
        {
            var action = endpoint.Metadata.GetMetadata<ControllerActionDescriptor>()!;
            var type = Assert.Single(action.Parameters, parameter => owned.Contains(parameter.ParameterType)).ParameterType;
            var contract = ProcurementMetadataVectors.Contracts.Single(value => RequestType(value) == type);
            var pattern = endpoint.RoutePattern.RawText!;
            var route = System.Text.RegularExpressions.Regex.Replace(pattern, @"\{([^}:]+)(?::[^}]+)?\}", match =>
                match.Groups[1].Value.ToLowerInvariant() switch
                {
                    "version" => "1", "supplierid" => "7002",
                    "addressid" => type == typeof(UpsertSupplierAddressRequest) ? "7001" : "7003",
                    "id" => "7006", _ => throw new InvalidOperationException("Unexpected owned route parameter."),
                });
            using var request = new HttpRequestMessage(new HttpMethod(Assert.Single(endpoint.Metadata.GetMetadata<HttpMethodMetadata>()!.HttpMethods)), "/" + route.TrimStart('/'));
            request.Content = new StringContent(ProcurementMetadataVectors.Body(contract, "\"$ref\":1,"), Encoding.UTF8, "application/json");
            using var response = await client.SendAsync(request);
            Assert.Equal(HttpStatusCode.BadRequest, response.StatusCode);
        }
        Assert.Equal(before, await SnapshotAsync());
    }

    [Fact]
    public async Task NormalHttp_StockTypedGraphFailureDoesNotDiscloseRawValuesOrPersistAnyGraph()
    {
        using var client = Writer();
        var before = await SnapshotAsync();
        using var response = await SendAsync(client, "supplier_put",
            ProcurementMetadataVectors.Body("supplier", "\"Address\":{\"CountryId\":\"" + PrivateToken + "\"},"));
        Assert.Equal(HttpStatusCode.BadRequest, response.StatusCode);
        Assert.Equal(before, await SnapshotAsync());
        Assert.DoesNotContain(PrivateToken, await response.Content.ReadAsStringAsync(), StringComparison.Ordinal);
        Assert.DoesNotContain(logs.Messages, value => value.Contains(PrivateToken, StringComparison.Ordinal));
    }

    [Fact]
    public void NonselectedFinancialAndResponseTypesKeepTheOriginalNativeInputFormatter()
    {
        foreach (var type in new[] { typeof(UpsertPurchaseOrderRequest), typeof(UpsertOrderItemRequest), typeof(SupplierResponse), typeof(PurchaseOrderFileResponse) })
        {
            using var stream = new MemoryStream(Encoding.UTF8.GetBytes("{}"));
            Assert.IsType<SystemTextJsonInputFormatter>(Select(FormatterContext(type, stream)));
        }
    }

    public static IEnumerable<object[]> GrammarBodies => Operations.SelectMany(operation =>
        new[] { "single_quotes", "unquoted_names", "trailing_comma", "comments", "additional_content", "hex_integer", "octal_integer" }
            .Select(kind => new object[] { operation, kind }));
    public static IEnumerable<object[]> GraphBodies => ProcurementMetadataSourceProtocolTests.GraphCases.SelectMany(row =>
        Operations.Where(operation => Contract(operation) == (string)row[0])
            .Select(operation => new object[] { operation, (string)row[1], (bool)row[2] }));
    public static IEnumerable<object[]> UnicodeBodies => Operations.SelectMany(operation =>
        new[] { new object[] { operation, false }, new object[] { operation, true } });
    public static IEnumerable<object[]> ZeroOwnerBodies => ProcurementMetadataSourceProtocolTests.FileOwnerDefaults
        .Where(row => (int)row[1] == 0).Select(row => new object[] { (string)row[0] });
    public static IEnumerable<object[]> SpilledBodies => ProcurementMetadataVectors.Contracts.SelectMany(contract =>
        new[] { "valid", "malformed", "unexpected" }.Select(kind => new object[] { contract, kind }));

    [Theory]
    [MemberData(nameof(GrammarBodies))]
    public async Task NormalHttp_SourceGrammarStillUsesTheSameSevenActions(string operation, string kind)
    {
        var contract = Contract(operation);
        var body = ProcurementMetadataVectors.Body(contract);
        body = kind switch
        {
            "single_quotes" => body.Replace('"', '\''),
            "unquoted_names" => System.Text.RegularExpressions.Regex.Replace(body, "\"([A-Za-z][A-Za-z0-9]*)\":", "$1:"),
            "trailing_comma" => body[..^1] + ",}",
            "comments" => "/*before*/" + body.Insert(1, "/*member*/") + "/*after*/",
            "additional_content" => body + " " + body,
            "hex_integer" => body.Replace(":66", ":0x42", StringComparison.Ordinal).Replace(":7004", ":0x1b5c", StringComparison.Ordinal),
            "octal_integer" => body.Replace(":66", ":0102", StringComparison.Ordinal).Replace(":7004", ":015534", StringComparison.Ordinal),
            _ => throw new InvalidOperationException(),
        };
        using var client = Writer();
        using var response = await SendAsync(client, operation, body);
        Assert.Equal(operation.EndsWith("put", StringComparison.Ordinal) ? HttpStatusCode.NoContent : HttpStatusCode.Created, response.StatusCode);
        await AssertWrittenScalarsAsync(operation, response, "outer", 66);
    }

    [Theory]
    [MemberData(nameof(GraphBodies))]
    public async Task NormalHttp_TypedGraphAdmissionNeverPersistsTheDiscardedGraph(string operation, string prefix, bool valid)
    {
        using var client = Writer();
        var before = await SnapshotAsync();
        var counts = await CountsAsync();
        using var response = await SendAsync(client, operation, ProcurementMetadataVectors.Body(Contract(operation), prefix));
        if (!valid)
        {
            Assert.Equal(HttpStatusCode.BadRequest, response.StatusCode);
            Assert.Equal(before, await SnapshotAsync());
            return;
        }
        Assert.Equal(operation.EndsWith("put", StringComparison.Ordinal) ? HttpStatusCode.NoContent : HttpStatusCode.Created, response.StatusCode);
        var expected = counts.ToArray();
        if (operation == "supplier_post") expected[0]++;
        if (operation == "supplier_address_post") expected[1]++;
        if (operation == "order_address_post") expected[2]++;
        Assert.Equal(expected, await CountsAsync());
        await AssertWrittenScalarsAsync(operation, response, "outer", 66);
    }

    [Theory]
    [MemberData(nameof(UnicodeBodies))]
    public async Task NormalHttp_StockUtf16AdmissionPreservesEncodingAndNoWriteFailures(string operation, bool invalid)
    {
        using var client = Writer();
        using var request = Request(operation);
        var before = await SnapshotAsync();
        request.Content = new StringContent(ProcurementMetadataVectors.Body(Contract(operation), invalid ? "\"$ref\":1," : "\"$id\":\"root\","), Encoding.Unicode, "application/json");
        using var response = await client.SendAsync(request);
        Assert.Equal(invalid ? HttpStatusCode.BadRequest : operation.EndsWith("put", StringComparison.Ordinal) ? HttpStatusCode.NoContent : HttpStatusCode.Created, response.StatusCode);
        if (invalid) Assert.Equal(before, await SnapshotAsync());
        else await AssertWrittenScalarsAsync(operation, response, "outer", 66);
    }

    [Theory]
    [MemberData(nameof(SpilledBodies))]
    public async Task SelectedFormatter_DeletesItsSpillFileOnSuccessFailureAndUnexpectedExit(string contract, string kind)
    {
        var prefix = kind == "unexpected" ? "\"$type\":null," : "";
        var json = ProcurementMetadataVectors.Body(contract, prefix).Replace("outer", new string('x', 40_000), StringComparison.Ordinal);
        if (kind == "malformed") json = json[..^1] + ",\"Id\":{}}";
        using var body = new MemoryStream(Encoding.UTF8.GetBytes(json));
        string? path = null;
        var context = FormatterContext(RequestType(contract), body, readerFactory: (stream, encoding) =>
        {
            var buffer = Assert.IsType<Microsoft.AspNetCore.WebUtilities.FileBufferingReadStream>(stream);
            Assert.False(buffer.InMemory);
            path = buffer.TempFileName;
            Assert.NotNull(path);
            Assert.True(System.IO.File.Exists(path));
            return new StreamReader(stream, encoding, detectEncodingFromByteOrderMarks: true, bufferSize: 1024, leaveOpen: true);
        });
        if (kind == "unexpected")
            await Assert.ThrowsAsync<NullReferenceException>(() => Select(context).ReadAsync(context));
        else
        {
            var result = await Select(context).ReadAsync(context);
            Assert.Equal(kind == "malformed", result.HasError);
        }
        Assert.NotNull(path);
        Assert.False(System.IO.File.Exists(path));
        Assert.Same(body, context.HttpContext.Request.Body);
        Assert.Equal(0, body.Position);
        Assert.True(body.CanRead);
    }

    [Theory]
    [MemberData(nameof(Contracts))]
    public async Task SelectedFormatter_RespectsFiniteRequestLimitAndRestoresBodyOnLimitFailure(string contract)
    {
        using var body = new MemoryStream(Encoding.UTF8.GetBytes(ProcurementMetadataVectors.Body(contract)));
        var context = FormatterContext(RequestType(contract), body);
        context.HttpContext.Features.Set<Microsoft.AspNetCore.Http.Features.IHttpMaxRequestBodySizeFeature>(new BodyLimit(8));
        await Assert.ThrowsAsync<IOException>(() => Select(context).ReadAsync(context));
        Assert.Same(body, context.HttpContext.Request.Body);
        Assert.Equal(0, body.Position);
        Assert.True(body.CanRead);
    }

    [Theory]
    [MemberData(nameof(Contracts))]
    public async Task SelectedFormatter_HonorsAbortBeforeAnySynchronousSocketRead(string contract)
    {
        using var body = new AsyncOnlyRequestBody(ProcurementMetadataVectors.Body(contract));
        var context = FormatterContext(RequestType(contract), body);
        using var cancellation = new CancellationTokenSource();
        cancellation.Cancel();
        context.HttpContext.RequestAborted = cancellation.Token;
        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => Select(context).ReadAsync(context));
        Assert.Same(body, context.HttpContext.Request.Body);
        Assert.Equal(0, body.SyncReads);
        Assert.False(body.Disposed);
    }

    [Theory]
    [MemberData(nameof(ZeroOwnerBodies))]
    public async Task NormalHttp_FileOwnerZeroIsNotExistingOwnerFallback_WhenParentZeroIsAbsent(string members)
    {
        using var client = Writer();
        await SetMarkerAsync();
        var before = await SnapshotAsync();
        using var response = await SendAsync(client, "file_put", "{" + members + "\"Bucket\":\"bucket\",\"ObjectName\":\"object\"}");
        Assert.Equal(HttpStatusCode.InternalServerError, response.StatusCode);
        Assert.Equal(before, await SnapshotAsync());
        Assert.Equal(MarkerValue, await MarkerAsync());
        Assert.DoesNotContain(PrivateToken, await response.Content.ReadAsStringAsync(), StringComparison.Ordinal);
    }

    [Theory]
    [MemberData(nameof(ZeroOwnerBodies))]
    public async Task NormalHttp_FileOwnerZeroCanPersistWhenThatParentExists(string members)
    {
        await using (var scope = app.Services.CreateAsyncScope())
        {
            // Disposable fixture insertion only; no financial API/calculation,
            // FK alteration, migration or production state is involved.
            var orders = scope.ServiceProvider.GetRequiredService<PurchaseOrderDbContext>();
            await orders.Database.ExecuteSqlRawAsync("INSERT INTO public.\"PurchaseOrder\" (\"ID\") VALUES (0)");
        }
        using var client = Writer();
        await SetMarkerAsync();
        var before = await SnapshotAsync(excludeFile: true);
        fixture.Clock.Advance(TimeSpan.FromSeconds(1));
        using var response = await SendAsync(client, "file_put", "{" + members + "\"Bucket\":\"bucket\",\"ObjectName\":\"object\"}");
        Assert.Equal(HttpStatusCode.NoContent, response.StatusCode);
        await using var readScope = app.Services.CreateAsyncScope();
        var db = readScope.ServiceProvider.GetRequiredService<PurchaseOrderDbContext>();
        var row = await db.Files.AsNoTracking().SingleAsync(value => value.Id == 7006);
        Assert.Equal(0, row.PurchaseOrderId);
        Assert.Equal("bucket", row.Bucket);
        Assert.Equal("object", row.ObjectName);
        Assert.Equal(Now(), row.ModifiedDate);
        Assert.Equal(Now().AddSeconds(-1), row.CreatedDate);
        Assert.Equal(before, await SnapshotAsync(excludeFile: true));
        Assert.Equal(MarkerValue, await MarkerAsync());
        using var read = await client.GetAsync("/purchaseorders/files/7006");
        Assert.Equal(HttpStatusCode.OK, read.StatusCode);
        using var wire = JsonDocument.Parse(await read.Content.ReadAsStringAsync());
        Assert.Equal(0, wire.RootElement.GetProperty("PurchaseOrderId").GetInt32());
    }

    [Fact]
    public async Task NormalHttp_ExistingExplicitAddressGuardsRemainAfterSourceBinding()
    {
        using var client = Writer();
        var before = await SnapshotAsync();
        foreach (var body in new[] { "{\"Address1\":\"line\",\"CountryId\":null}", "{\"Address1\":null,\"CountryId\":66}" })
        {
            using var request = await SendAsync(client, "supplier_address_post", body);
            Assert.Equal(HttpStatusCode.BadRequest, request.StatusCode);
        }
        foreach (var operation in new[] { "order_address_post", "order_address_put" })
        {
            using var request = await SendAsync(client, operation, "{\"AddressLine1\":null,\"CountryId\":66}");
            Assert.Equal(HttpStatusCode.BadRequest, request.StatusCode);
        }
        Assert.Equal(before, await SnapshotAsync());
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task NormalHttp_FileLookupAndExistingTextGuardPrecedeForeignKeySave(bool missing)
    {
        using var client = Writer();
        var before = await SnapshotAsync();
        using var response = await SendAsync(client, "file_put",
            "{\"Bucket\":\"" + new string('b', 51) + "\",\"ObjectName\":\"object\"}", missing);
        Assert.Equal(missing ? HttpStatusCode.NotFound : HttpStatusCode.BadRequest, response.StatusCode);
        Assert.Equal(before, await SnapshotAsync());
    }

    private async Task<int[]> CountsAsync()
    {
        await using var scope = app.Services.CreateAsyncScope();
        var suppliers = scope.ServiceProvider.GetRequiredService<SupplierDbContext>();
        var orders = scope.ServiceProvider.GetRequiredService<PurchaseOrderDbContext>();
        return
        [
            await suppliers.Suppliers.CountAsync(), await suppliers.Addresses.CountAsync(),
            await orders.Addresses.CountAsync(), await orders.PurchaseOrders.CountAsync(),
            await orders.OrderItems.CountAsync(), await orders.Files.CountAsync(),
        ];
    }

    private async Task AssertWrittenScalarsAsync(string operation, HttpResponseMessage response, string expected, int country)
    {
        var id = operation switch
        {
            "supplier_put" => 7002, "supplier_address_put" => 7001,
            "order_address_put" => 7003, "file_put" => 7006, _ => 0,
        };
        if (id == 0)
        {
            using var created = JsonDocument.Parse(await response.Content.ReadAsStringAsync());
            id = created.RootElement.GetProperty("Id").GetInt32();
        }
        await using var scope = app.Services.CreateAsyncScope();
        if (operation is "supplier_post" or "supplier_put")
            Assert.Equal(expected, (await scope.ServiceProvider.GetRequiredService<SupplierDbContext>().Suppliers.AsNoTracking().SingleAsync(value => value.Id == id)).Name);
        else if (operation.StartsWith("supplier_address", StringComparison.Ordinal))
        {
            var row = await scope.ServiceProvider.GetRequiredService<SupplierDbContext>().Addresses.AsNoTracking().SingleAsync(value => value.Id == id);
            Assert.Equal(expected, row.Address1);
            Assert.Equal(country, row.CountryId);
        }
        else if (operation.StartsWith("order_address", StringComparison.Ordinal))
        {
            var row = await scope.ServiceProvider.GetRequiredService<PurchaseOrderDbContext>().Addresses.AsNoTracking().SingleAsync(value => value.Id == id);
            Assert.Equal(expected, row.AddressLine1);
            Assert.Equal(country, row.CountryId);
        }
        else
        {
            var row = await scope.ServiceProvider.GetRequiredService<PurchaseOrderDbContext>().Files.AsNoTracking().SingleAsync(value => value.Id == id);
            Assert.Equal(expected, row.Bucket);
            Assert.Equal(7004, row.PurchaseOrderId);
        }
    }

    private sealed class BodyLimit(long? limit) : Microsoft.AspNetCore.Http.Features.IHttpMaxRequestBodySizeFeature
    {
        public bool IsReadOnly => false;
        public long? MaxRequestBodySize { get; set; } = limit;
    }

    private InputFormatterContext FormatterContext(Type type, Stream body, string contentType = "application/json; charset=utf-8", Func<Stream, Encoding, TextReader>? readerFactory = null)
    {
        var context = new DefaultHttpContext { RequestServices = app.Services };
        context.Request.Body = body;
        context.Request.ContentType = contentType;
        var metadata = app.Services.GetRequiredService<IModelMetadataProvider>().GetMetadataForType(type);
        return new InputFormatterContext(context, "", new ModelStateDictionary(), metadata,
            readerFactory ?? ((stream, encoding) => new StreamReader(stream, encoding, detectEncodingFromByteOrderMarks: true, bufferSize: 1024, leaveOpen: true)));
    }

    private IInputFormatter Select(InputFormatterContext context) =>
        app.Services.GetRequiredService<IOptions<MvcOptions>>().Value.InputFormatters.First(formatter => formatter.CanRead(context));
    private static string Contract(string operation) => operation switch
    {
        "supplier_post" or "supplier_put" => "supplier",
        "supplier_address_post" or "supplier_address_put" => "supplier-address",
        "order_address_post" or "order_address_put" => "order-address", _ => "file",
    };
    private static Type RequestType(string contract) => contract switch
    {
        "supplier" => typeof(UpsertSupplierRequest), "supplier-address" => typeof(UpsertSupplierAddressRequest),
        "order-address" => typeof(UpsertPurchaseOrderAddressRequest), _ => typeof(UpsertPurchaseOrderFileRequest),
    };
    private static HttpRequestMessage Request(string operation, bool missing = false)
    {
        var absent = missing ? 999999 : 7002;
        var address = missing ? 999999 : operation.StartsWith("supplier_address", StringComparison.Ordinal) ? 7001 : 7003;
        var file = missing ? 999999 : 7006;
        var path = operation switch
        {
            "supplier_post" => "/suppliers", "supplier_put" => $"/suppliers/{absent}",
            "supplier_address_post" => $"/suppliers/{absent}/addresses", "supplier_address_put" => $"/suppliers/addresses/{address}",
            "order_address_post" => "/purchaseorders/addresses", "order_address_put" => $"/purchaseorders/addresses/{address}",
            _ => $"/purchaseorders/files/{file}",
        };
        return new HttpRequestMessage(operation.EndsWith("put", StringComparison.Ordinal) ? HttpMethod.Put : HttpMethod.Post, path);
    }
    private static async Task<HttpResponseMessage> SendAsync(HttpClient client, string operation, string body, bool missing = false)
    {
        using var request = Request(operation, missing);
        request.Content = new StringContent(body, Encoding.UTF8, "application/json");
        return await client.SendAsync(request);
    }
    private HttpClient Writer() => fixture.ClientAs(app, "service:procurement-parity",
        ProcurementPermissions.SuppliersCreate, ProcurementPermissions.SuppliersUpdate, ProcurementPermissions.SuppliersRead,
        ProcurementPermissions.SupplierAddressesWrite, ProcurementPermissions.SupplierAddressesRead,
        ProcurementPermissions.PurchaseOrderAddressesWrite, ProcurementPermissions.PurchaseOrderAddressesRead,
        ProcurementPermissions.FilesWrite, ProcurementPermissions.FilesRead);
    private DateTime Now() => DateTime.SpecifyKind(fixture.Clock.GetUtcNow().UtcDateTime, DateTimeKind.Unspecified);
    private async Task SetMarkerAsync()
    {
        await using var scope = app.Services.CreateAsyncScope();
        await scope.ServiceProvider.GetRequiredService<IProcurementCache>().SetAsync(MarkerKey, MarkerValue, TimeSpan.FromMinutes(1), CancellationToken.None);
    }
    private async Task<string?> MarkerAsync()
    {
        await using var scope = app.Services.CreateAsyncScope();
        return await scope.ServiceProvider.GetRequiredService<IProcurementCache>().GetAsync<string>(MarkerKey, CancellationToken.None);
    }
    private async Task<string> SnapshotAsync(bool excludeFile = false)
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
                var filter = excludeFile && table == "PurchaseOrderFile" ? " WHERE \"ID\" <> 7006" : "";
                var sql = $"SELECT COALESCE(jsonb_agg(to_jsonb(r) ORDER BY to_jsonb(r)::text)::text,'[]') AS \"Value\" FROM (SELECT *, xmin::text AS \"__xmin\" FROM public.\"{table}\"{filter}) r";
                snapshots.Add(boundary.Context.GetType().Name + ":" + table + ":" + await boundary.Context.Database.SqlQueryRaw<string>(sql).SingleAsync(lifetime.Token));
            }
        return string.Join("\n", snapshots);
    }

    private sealed class AsyncOnlyRequestBody(string body) : Stream
    {
        private readonly MemoryStream inner = new(Encoding.UTF8.GetBytes(body));
        public int SyncReads { get; private set; }
        public int AsyncReads { get; private set; }
        public bool Disposed { get; private set; }
        public override bool CanRead => !Disposed;
        public override bool CanSeek => false;
        public override bool CanWrite => false;
        public override long Length => throw new NotSupportedException();
        public override long Position { get => throw new NotSupportedException(); set => throw new NotSupportedException(); }
        public override int Read(byte[] buffer, int offset, int count) { SyncReads++; throw new InvalidOperationException("Synchronous network read."); }
        public override int Read(Span<byte> buffer) { SyncReads++; throw new InvalidOperationException("Synchronous network read."); }
        public override Task<int> ReadAsync(byte[] buffer, int offset, int count, CancellationToken cancellationToken) { AsyncReads++; return inner.ReadAsync(buffer, offset, count, cancellationToken); }
        public override ValueTask<int> ReadAsync(Memory<byte> buffer, CancellationToken cancellationToken = default) { AsyncReads++; return inner.ReadAsync(buffer, cancellationToken); }
        public override void Flush() => throw new NotSupportedException();
        public override long Seek(long offset, SeekOrigin origin) => throw new NotSupportedException();
        public override void SetLength(long value) => throw new NotSupportedException();
        public override void Write(byte[] buffer, int offset, int count) => throw new NotSupportedException();
        protected override void Dispose(bool disposing) { Disposed = true; if (disposing) inner.Dispose(); base.Dispose(disposing); }
    }

    private sealed class BodyAdmissionLogs : ILoggerProvider
    {
        public ConcurrentQueue<string> Messages { get; } = new();
        public ILogger CreateLogger(string categoryName) => new Captured(Messages);
        public void Dispose() { }
        private sealed class Captured(ConcurrentQueue<string> messages) : ILogger
        {
            public IDisposable? BeginScope<TState>(TState state) where TState : notnull => null;
            public bool IsEnabled(LogLevel logLevel) => true;
            public void Log<TState>(LogLevel logLevel, EventId eventId, TState state, Exception? exception, Func<TState, Exception?, string> formatter) =>
                messages.Enqueue(formatter(state, exception) + (exception is null ? "" : "\n" + exception));
        }
    }
}

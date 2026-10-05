using System.Net;
using System.Net.Http.Json;
using System.Text.Json.Nodes;
using Legacy.Maliev.ProcurementService.Api.Authorization;
using Legacy.Maliev.ProcurementService.Application.Models;
using Legacy.Maliev.ProcurementService.Tests.Integration;
using Microsoft.AspNetCore.Hosting;

namespace Legacy.Maliev.ProcurementService.Tests.Controllers;

public sealed class ProcurementOpenApiHttpContractTests(ProcurementRuntimeFixture fixture)
    : IClassFixture<ProcurementRuntimeFixture>
{
    private async Task<JsonObject> DocumentAsync()
    {
        await using var app = fixture.CreateFactory(false);
        await using var development = app.WithWebHostBuilder(builder => builder.UseEnvironment("Development"));
        using var client = development.CreateClient();
        using var response = await client.GetAsync("/procurement/openapi/v1.json");
        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        Assert.Equal("application/json", response.Content.Headers.ContentType?.MediaType);
        return JsonNode.Parse(await response.Content.ReadAsStringAsync(),
            new JsonNodeOptions { PropertyNameCaseInsensitive = false })!.AsObject();
    }

    private static JsonObject Path(JsonObject document, string expected) =>
        Assert.Single(document["paths"]!.AsObject(),
            path => string.Equals(path.Key, expected, StringComparison.OrdinalIgnoreCase)).Value!.AsObject();

    private static JsonObject Resolve(JsonObject document, JsonObject schema)
    {
        while (schema["$ref"] is JsonValue reference)
        {
            var value = reference.GetValue<string>();
            Assert.StartsWith("#/components/schemas/", value);
            schema = document["components"]!["schemas"]![value["#/components/schemas/".Length..]]!.AsObject();
        }
        return schema;
    }

    [Fact]
    public async Task Production_DocumentationIsUnavailableAndSupplierReadRequiresAuthentication()
    {
        using var client = fixture.Factory.CreateClient();
        using var document = await client.GetAsync("/procurement/openapi/v1.json");
        using var supplier = await client.GetAsync("/Suppliers/1");
        Assert.Equal(HttpStatusCode.NotFound, document.StatusCode);
        Assert.Equal(HttpStatusCode.Unauthorized, supplier.StatusCode);
    }

    [Fact]
    public async Task Development_DocumentPreservesThirtyOperationsQueriesHeadersAndResponses()
    {
        var document = await DocumentAsync();
        Assert.StartsWith("3.", document["openapi"]!.GetValue<string>());
        Assert.Equal("Legacy MALIEV Procurement Service API", document["info"]!["title"]!.GetValue<string>());
        var probes = new[] { "/procurement/aspire-liveness", "/procurement/liveness" };
        foreach (var probe in probes) Assert.NotNull(Path(document, probe)["get"]);
        var operations = document["paths"]!.AsObject()
            .Where(path => !probes.Contains(path.Key, StringComparer.OrdinalIgnoreCase))
            .SelectMany(path => path.Value!.AsObject())
            .Where(entry => entry.Key is "get" or "post" or "put" or "delete" or "patch").ToArray();
        Assert.Equal(30, operations.Length);
        Assert.All(operations, operation => Assert.NotEmpty(operation.Value!["responses"]!.AsObject()));
        foreach (var path in new[] { "/Suppliers", "/PurchaseOrders" })
        {
            foreach (var name in new[] { "sort", "search", "index", "size" })
            {
                var parameter = Assert.Single(Path(document, path)["get"]!["parameters"]!.AsArray(),
                    item => item!["name"]!.GetValue<string>() == name);
                Assert.Equal("query", parameter!["in"]!.GetValue<string>());
            }
            var header = Assert.Single(Path(document, path)["post"]!["parameters"]!.AsArray(),
                item => item!["name"]!.GetValue<string>() == "Idempotency-Key");
            Assert.Equal("header", header!["in"]!.GetValue<string>());
        }
        var concurrency = Assert.Single(Path(document, "/PurchaseOrders/{purchaseOrderId}")["put"]!["parameters"]!.AsArray(),
            item => item!["name"]!.GetValue<string>() == "X-Expected-Modified-Date");
        Assert.Equal("header", concurrency!["in"]!.GetValue<string>());
        var file = Path(document, "/purchaseorders/{purchaseOrderId}/files")["post"]!;
        foreach (var name in new[] { "bucket", "objectName" })
        {
            var parameter = Assert.Single(file["parameters"]!.AsArray(), item => item!["name"]!.GetValue<string>() == name);
            Assert.Equal("query", parameter!["in"]!.GetValue<string>());
            Assert.False(string.IsNullOrWhiteSpace(parameter["description"]?.GetValue<string>()));
            Assert.NotNull(parameter["example"]);
        }
        Assert.Equal("Bucket or object name is blank.", file["responses"]!["400"]!["description"]!.GetValue<string>());
        var supplier = Path(document, "/Suppliers/{supplierId}")["get"]!;
        Assert.Equal("The supplier master record.", supplier["responses"]!["200"]!["description"]!.GetValue<string>());
        Assert.Equal("The supplier does not exist.", supplier["responses"]!["404"]!["description"]!.GetValue<string>());
    }

    [Fact]
    public async Task Development_SchemasMatchActualPascalWireAndKeepAddressAndScalarOwnershipSeparate()
    {
        var document = await DocumentAsync();
        var supplier = Resolve(document, Path(document, "/Suppliers/{supplierId}")["get"]!["responses"]!["200"]!["content"]!["application/json"]!["schema"]!.AsObject());
        var output = supplier["properties"]!.AsObject();
        Assert.True(output.ContainsKey("Id"));
        Assert.True(output.ContainsKey("AddressId"));
        Assert.False(output.ContainsKey("addressId"));
        using var client = fixture.Client(ProcurementPermissions.SuppliersCreate, ProcurementPermissions.SuppliersRead);
        using var created = await client.PostAsJsonAsync("/Suppliers", new { Name = "Schema wire control" });
        Assert.Equal(HttpStatusCode.Created, created.StatusCode);
        var result = (await created.Content.ReadFromJsonAsync<SupplierResponse>())!;
        using var actual = await client.GetAsync($"/Suppliers/{result.Id}");
        Assert.Equal(HttpStatusCode.OK, actual.StatusCode);
        var wire = JsonNode.Parse(await actual.Content.ReadAsStringAsync(),
            new JsonNodeOptions { PropertyNameCaseInsensitive = false })!.AsObject();
        Assert.Equal(result.Id, wire["Id"]!.GetValue<int>());
        Assert.Equal("Schema wire control", wire["Name"]!.GetValue<string>());
        Assert.False(wire.ContainsKey("Email"));
        Assert.All(wire, field => Assert.True(output.ContainsKey(field.Key), $"Wire field {field.Key} is absent from its response schema."));
        var supplierAddress = Resolve(document, Path(document, "/suppliers/addresses/{addressId}")["get"]!["responses"]!["200"]!["content"]!["application/json"]!["schema"]!.AsObject())["properties"]!.AsObject();
        var orderAddress = Resolve(document, Path(document, "/purchaseorders/addresses/{addressId}")["get"]!["responses"]!["200"]!["content"]!["application/json"]!["schema"]!.AsObject())["properties"]!.AsObject();
        Assert.True(supplierAddress.ContainsKey("Address1"));
        Assert.False(supplierAddress.ContainsKey("AddressLine1"));
        Assert.True(orderAddress.ContainsKey("AddressLine1"));
        Assert.False(orderAddress.ContainsKey("Address1"));
        var order = Resolve(document, Path(document, "/PurchaseOrders")["post"]!["requestBody"]!["content"]!["application/json"]!["schema"]!.AsObject())["properties"]!.AsObject();
        Assert.Contains("integer", order["SupplierId"]!.ToJsonString(), StringComparison.Ordinal);
        Assert.Contains("integer", order["EmployeeId"]!.ToJsonString(), StringComparison.Ordinal);
        Assert.False(order.ContainsKey("Supplier"));
        Assert.False(order.ContainsKey("Employee"));
        var item = Resolve(document, Path(document, "/purchaseorders/orderitems/{orderItemId}")["put"]!["requestBody"]!["content"]!["application/json"]!["schema"]!.AsObject())["properties"]!.AsObject();
        Assert.False(item.ContainsKey("Subtotal"));
        Assert.True(item.ContainsKey("UnitPrice"));
    }
}

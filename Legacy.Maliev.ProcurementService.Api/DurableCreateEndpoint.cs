using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Legacy.Maliev.ProcurementService.Application.Interfaces;
using Legacy.Maliev.ProcurementService.Application.Models;
using Microsoft.AspNetCore.Mvc;
using Microsoft.Extensions.Options;

namespace Legacy.Maliev.ProcurementService.Api;

/// <summary>Local, default-off transactional receipt endpoint adapter.</summary>
public sealed class DurableCreateEndpoint(IConfiguration configuration, IDurableProcurementCreates creates, IOptions<JsonOptions> json)
{
    /// <summary>Whether the explicit receipt rollout feature is enabled.</summary>
    public bool Enabled => configuration.GetValue<bool>("Procurement:DurableCreates:Enabled");

    /// <summary>Executes a supplier root create under server-derived binding.</summary>
    public async Task<IActionResult> SupplierAsync(ControllerBase controller, UpsertSupplierRequest request, CancellationToken token)
    {
        if (!TryBinding(controller, request, 1, out var binding)) return controller.BadRequest();
        var result = await creates.CreateSupplierAsync(request, binding!, value => JsonSerializer.SerializeToUtf8Bytes(value, json.Value.JsonSerializerOptions), token);
        return Map(controller, result, "GetSupplier", "supplierId");
    }

    /// <summary>Executes a purchase-order root create without weakening live permissions.</summary>
    public async Task<IActionResult> PurchaseOrderAsync(ControllerBase controller, UpsertPurchaseOrderRequest request, CancellationToken token)
    {
        if (!TryBinding(controller, request, 2, out var binding)) return controller.BadRequest();
        var result = await creates.CreatePurchaseOrderAsync(request, binding!, value => JsonSerializer.SerializeToUtf8Bytes(value, json.Value.JsonSerializerOptions), token);
        return Map(controller, result, "GetPurchaseOrder", "purchaseOrderId");
    }

    private bool TryBinding<T>(ControllerBase controller, T request, short operation, out CreateReceiptBinding? binding)
    {
        binding = null;
        var headers = controller.Request.Headers["Idempotency-Key"];
        if (headers.Count != 1) return false;
        var key = headers[0];
        if (string.IsNullOrWhiteSpace(key) || Encoding.UTF8.GetByteCount(key) > 256 || key.Any(character => character == ',' || char.IsControl(character))) return false;
        var user = controller.User;
        if (user.Identity?.IsAuthenticated != true) return false;
        var issuers = user.FindAll("iss").ToArray();
        var subjects = user.FindAll("sub").ToArray();
        if (issuers.Length != 1 || subjects.Length != 1) return false;
        var issuer = issuers[0].Value; var subject = subjects[0].Value;
        if (string.IsNullOrWhiteSpace(issuer) || Encoding.UTF8.GetByteCount(issuer) > 1024 || string.IsNullOrWhiteSpace(subject) || Encoding.UTF8.GetByteCount(subject) > 512
            || !string.Equals(issuer, configuration["Jwt:Issuer"], StringComparison.Ordinal)) return false;
        // Declared record order and explicit nulls bind the effective typed DTO, not raw JSON.
        var canonical = JsonSerializer.SerializeToUtf8Bytes(request, new JsonSerializerOptions { PropertyNamingPolicy = null });
        var tagged = new byte[canonical.Length + 2]; tagged[0] = 1; tagged[1] = (byte)operation; canonical.CopyTo(tagged, 2);
        binding = new(Hash(issuer), Hash(subject), operation, Hash(key), 1, SHA256.HashData(tagged));
        return true;
    }

    private static byte[] Hash(string value) => SHA256.HashData(Encoding.UTF8.GetBytes(value));
    private static IActionResult Map(ControllerBase controller, DurableCreateResult result, string route, string idName)
    {
        controller.Response.Headers.CacheControl = "no-store";
        if (result.Status == DurableCreateStatus.Conflict) return controller.Conflict();
        if (result.Status != DurableCreateStatus.CreatedOrReplayed || result.Response is null) return controller.StatusCode(StatusCodes.Status503ServiceUnavailable);
        controller.Response.Headers.Location = controller.Url.Link(route, new Dictionary<string, object> { [idName] = result.Response.EntityId });
        return new ContentResult { StatusCode = StatusCodes.Status201Created, ContentType = "application/json; charset=utf-8", Content = Encoding.UTF8.GetString(result.Response.Body) };
    }
}

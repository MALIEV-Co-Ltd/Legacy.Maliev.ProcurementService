using System.Globalization;
using System.Text.Json;
using System.Text.Json.Serialization;
using Legacy.Maliev.ProcurementService.Application.Models;

namespace Legacy.Maliev.ProcurementService.Api.Serialization;

/// <summary>Reads the consumed purchase-order header with ordered primitive and null-ignore semantics.</summary>
public sealed class PurchaseOrderHeaderRequestJsonConverter : JsonConverter<UpsertPurchaseOrderRequest>
{
    /// <inheritdoc />
    public override UpsertPurchaseOrderRequest Read(ref Utf8JsonReader reader, Type typeToConvert, JsonSerializerOptions options)
    {
        using var document = JsonDocument.ParseValue(ref reader);
        if (document.RootElement.ValueKind != JsonValueKind.Object)
            throw new JsonException("Purchase-order header requires a JSON object.");

        int? supplierId = null;
        string? supplierContactPerson = null;
        int? shippingAddressId = null;
        string? shippingContactPerson = null;
        string? shippingTelephone = null;
        string? shippingMobile = null;
        string? shippingFax = null;
        int? billingAddressId = null;
        string? billingContactPerson = null;
        string? billingTelephone = null;
        string? billingMobile = null;
        string? billingFax = null;
        string? fob = null;
        string? terms = null;
        string? shippingMethod = null;
        int? employeeId = null;
        string? notes = null;

        // EnumerateObject preserves duplicates. Every recognized occurrence must be read:
        // later nulls skip assignment, and a later valid value cannot hide an earlier error.
        foreach (var property in document.RootElement.EnumerateObject())
        {
            if (string.Equals(property.Name, "SupplierId", StringComparison.OrdinalIgnoreCase))
                supplierId = ReadReference(property.Value) ?? supplierId;
            else if (string.Equals(property.Name, "SupplierContactPerson", StringComparison.OrdinalIgnoreCase))
                supplierContactPerson = ReadText(property.Value) ?? supplierContactPerson;
            else if (string.Equals(property.Name, "ShippingAddressId", StringComparison.OrdinalIgnoreCase))
                shippingAddressId = ReadReference(property.Value) ?? shippingAddressId;
            else if (string.Equals(property.Name, "ShippingContactPerson", StringComparison.OrdinalIgnoreCase))
                shippingContactPerson = ReadText(property.Value) ?? shippingContactPerson;
            else if (string.Equals(property.Name, "ShippingTelephone", StringComparison.OrdinalIgnoreCase))
                shippingTelephone = ReadText(property.Value) ?? shippingTelephone;
            else if (string.Equals(property.Name, "ShippingMobile", StringComparison.OrdinalIgnoreCase))
                shippingMobile = ReadText(property.Value) ?? shippingMobile;
            else if (string.Equals(property.Name, "ShippingFax", StringComparison.OrdinalIgnoreCase))
                shippingFax = ReadText(property.Value) ?? shippingFax;
            else if (string.Equals(property.Name, "BillingAddressId", StringComparison.OrdinalIgnoreCase))
                billingAddressId = ReadReference(property.Value) ?? billingAddressId;
            else if (string.Equals(property.Name, "BillingContactPerson", StringComparison.OrdinalIgnoreCase))
                billingContactPerson = ReadText(property.Value) ?? billingContactPerson;
            else if (string.Equals(property.Name, "BillingTelephone", StringComparison.OrdinalIgnoreCase))
                billingTelephone = ReadText(property.Value) ?? billingTelephone;
            else if (string.Equals(property.Name, "BillingMobile", StringComparison.OrdinalIgnoreCase))
                billingMobile = ReadText(property.Value) ?? billingMobile;
            else if (string.Equals(property.Name, "BillingFax", StringComparison.OrdinalIgnoreCase))
                billingFax = ReadText(property.Value) ?? billingFax;
            else if (string.Equals(property.Name, "Fob", StringComparison.OrdinalIgnoreCase))
                fob = ReadText(property.Value) ?? fob;
            else if (string.Equals(property.Name, "Terms", StringComparison.OrdinalIgnoreCase))
                terms = ReadText(property.Value) ?? terms;
            else if (string.Equals(property.Name, "ShippingMethod", StringComparison.OrdinalIgnoreCase))
                shippingMethod = ReadText(property.Value) ?? shippingMethod;
            else if (string.Equals(property.Name, "EmployeeId", StringComparison.OrdinalIgnoreCase))
                employeeId = ReadReference(property.Value) ?? employeeId;
            else if (string.Equals(property.Name, "Notes", StringComparison.OrdinalIgnoreCase))
                notes = ReadText(property.Value) ?? notes;
        }

        return new UpsertPurchaseOrderRequest(
            supplierId, supplierContactPerson, shippingAddressId, shippingContactPerson,
            shippingTelephone, shippingMobile, shippingFax, billingAddressId,
            billingContactPerson, billingTelephone, billingMobile, billingFax,
            fob, terms, shippingMethod, employeeId, notes);
    }

    private static string? ReadText(JsonElement value)
    {
        switch (value.ValueKind)
        {
            case JsonValueKind.Null:
                return null;
            case JsonValueKind.String:
                return value.GetString();
            case JsonValueKind.True:
                return "true";
            case JsonValueKind.False:
                return "false";
            case JsonValueKind.Number:
                var lexeme = value.GetRawText();
                // JsonTextReader.ReadAsString validates a standard JSON numeric lexeme
                // as an invariant double while returning its original spelling.
                if (double.TryParse(lexeme, NumberStyles.Float, CultureInfo.InvariantCulture, out _))
                    return lexeme;
                break;
        }
        throw new JsonException("Invalid purchase-order header text token.");
    }

    private static int? ReadReference(JsonElement value)
    {
        if (value.ValueKind == JsonValueKind.Null) return null;
        if (value.ValueKind == JsonValueKind.Number && value.TryGetInt32(out var number)) return number;
        if (value.ValueKind == JsonValueKind.String)
        {
            var text = value.GetString();
            if (string.IsNullOrEmpty(text)) return null;
            if (int.TryParse(text, NumberStyles.Integer, CultureInfo.InvariantCulture, out var parsed)) return parsed;
        }
        throw new JsonException("Invalid purchase-order header reference token.");
    }

    /// <inheritdoc />
    public override void Write(Utf8JsonWriter writer, UpsertPurchaseOrderRequest value, JsonSerializerOptions options)
    {
        var standard = new JsonSerializerOptions(options);
        for (var index = standard.Converters.Count - 1; index >= 0; index--)
            if (standard.Converters[index] is PurchaseOrderHeaderRequestJsonConverter)
                standard.Converters.RemoveAt(index);
        JsonSerializer.Serialize(writer, value, standard);
    }
}

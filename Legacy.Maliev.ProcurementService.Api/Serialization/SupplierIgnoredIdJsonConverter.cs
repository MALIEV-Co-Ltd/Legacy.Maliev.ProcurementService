using System.Globalization;
using System.Text.Json;
using System.Text.Json.Serialization;
using Legacy.Maliev.ProcurementService.Application.Models;

namespace Legacy.Maliev.ProcurementService.Api.Serialization;

/// <summary>Validates and discards the original supplier body's identity, address reference, and audit dates.</summary>
public sealed class SupplierIgnoredIdJsonConverter : JsonConverter<UpsertSupplierRequest>
{
    /// <inheritdoc />
    public override UpsertSupplierRequest Read(ref Utf8JsonReader reader, Type typeToConvert, JsonSerializerOptions options)
    {
        using var document = JsonDocument.ParseValue(ref reader);
        if (document.RootElement.ValueKind != JsonValueKind.Object)
            throw new JsonException("Expected a supplier request object.");
        var comparison = options.PropertyNameCaseInsensitive ? StringComparison.OrdinalIgnoreCase : StringComparison.Ordinal;
        using var buffer = new MemoryStream();
        using (var writer = new Utf8JsonWriter(buffer))
        {
            writer.WriteStartObject();
            foreach (var property in document.RootElement.EnumerateObject())
            {
                if (string.Equals(property.Name, "Id", comparison)
                    || string.Equals(property.Name, "AddressId", comparison))
                {
                    ValidateIgnoredId(property.Value);
                    continue;
                }
                if (string.Equals(property.Name, "CreatedDate", comparison)
                    || string.Equals(property.Name, "ModifiedDate", comparison))
                {
                    ReadIgnoredAuditDate(property.Value);
                    continue;
                }
                writer.WritePropertyName(property.Name);
                writer.WriteRawValue(property.Value.GetRawText());
            }
            writer.WriteEndObject();
        }
        return JsonSerializer.Deserialize<UpsertSupplierRequest>(buffer.ToArray(), InnerOptions(options))
            ?? throw new JsonException("Expected a supplier request object.");
    }

    /// <inheritdoc />
    public override void Write(Utf8JsonWriter writer, UpsertSupplierRequest value, JsonSerializerOptions options) =>
        JsonSerializer.Serialize(writer, value, InnerOptions(options));

    private JsonSerializerOptions InnerOptions(JsonSerializerOptions options)
    {
        var inner = new JsonSerializerOptions(options);
        for (var index = inner.Converters.Count - 1; index >= 0; index--)
            if (ReferenceEquals(inner.Converters[index], this)) inner.Converters.RemoveAt(index);
        return inner;
    }

    private static void ReadIgnoredAuditDate(JsonElement value)
    {
        // Only compatibility with the pinned public reader is claimed.
        // The effective historical deployed Newtonsoft binary remains unknown.
        using var text = new StringReader(value.GetRawText());
        using var legacy = new Newtonsoft.Json.JsonTextReader(text) { Culture = CultureInfo.InvariantCulture };
        try
        {
            _ = legacy.ReadAsDateTime();
        }
        catch (Exception exception) when (exception is Newtonsoft.Json.JsonException or ArgumentOutOfRangeException)
        {
            throw new JsonException("The ignored audit date has an invalid legacy type.", exception);
        }
    }

    private static void ValidateIgnoredId(JsonElement value)
    {
        using var text = new StringReader(value.GetRawText());
        using var legacy = new Newtonsoft.Json.JsonTextReader(text) { Culture = CultureInfo.InvariantCulture };
        try
        {
            // The legacy int property is read before the controller ignores it.
            // Null/empty-string tokens are ignored by the original NullValueHandling.Ignore.
            _ = legacy.ReadAsInt32();
        }
        catch (Newtonsoft.Json.JsonException exception)
        {
            throw new JsonException("The ignored supplier identity has an invalid legacy type.", exception);
        }
    }
}

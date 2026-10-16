using System.Globalization;
using System.Text.Json;
using System.Text.Json.Serialization;
using Legacy.Maliev.ProcurementService.Application.Models;

namespace Legacy.Maliev.ProcurementService.Api.Serialization;

/// <summary>Validates and discards the original supplier body's server-owned identity.</summary>
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
                if (string.Equals(property.Name, "Id", comparison))
                {
                    ValidateIgnoredId(property.Value);
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

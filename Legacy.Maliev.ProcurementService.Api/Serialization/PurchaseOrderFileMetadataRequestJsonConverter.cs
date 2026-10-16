using System.Globalization;
using System.Text.Json;
using System.Text.Json.Serialization;
using Legacy.Maliev.ProcurementService.Application.Models;

namespace Legacy.Maliev.ProcurementService.Api.Serialization;

/// <summary>Preserves ordered source string binding only for file-metadata request text.</summary>
public sealed class PurchaseOrderFileMetadataRequestJsonConverter : JsonConverter<UpsertPurchaseOrderFileRequest>
{
    /// <inheritdoc />
    public override UpsertPurchaseOrderFileRequest Read(ref Utf8JsonReader reader, Type typeToConvert, JsonSerializerOptions options)
    {
        using var document = JsonDocument.ParseValue(ref reader);
        if (document.RootElement.ValueKind != JsonValueKind.Object)
            throw new JsonException("File metadata requires a JSON object.");

        using var buffer = new MemoryStream();
        using (var writer = new Utf8JsonWriter(buffer))
        {
            writer.WriteStartObject();
            foreach (var property in document.RootElement.EnumerateObject())
            {
                var textField = string.Equals(property.Name, "Bucket", StringComparison.OrdinalIgnoreCase)
                    || string.Equals(property.Name, "ObjectName", StringComparison.OrdinalIgnoreCase);
                if (textField && TryReadText(property.Value, out var text))
                {
                    // Preserve ordered text occurrences; a later null skips only this
                    // metadata assignment, without affecting nullable parent semantics.
                    if (text is not null)
                        writer.WriteString(property.Name, text);
                }
                else
                {
                    // Keep unsupported text tokens and every other member on the native
                    // DTO reader, retaining its malformed-field Path and parent policy.
                    // ParseValue has already validated these forwarded raw JSON values.
                    writer.WritePropertyName(property.Name);
                    writer.WriteRawValue(property.Value.GetRawText(), skipInputValidation: true);
                }
            }
            writer.WriteEndObject();
            writer.Flush();
        }

        return JsonSerializer.Deserialize<UpsertPurchaseOrderFileRequest>(
            buffer.GetBuffer().AsSpan(0, checked((int)buffer.Length)), WithoutThisConverter(options))
            ?? throw new JsonException("File metadata requires a JSON object.");
    }

    private static bool TryReadText(JsonElement value, out string? text)
    {
        text = null;
        switch (value.ValueKind)
        {
            case JsonValueKind.Null:
                return true;
            case JsonValueKind.String:
                text = value.GetString();
                return true;
            case JsonValueKind.True:
                text = "true";
                return true;
            case JsonValueKind.False:
                text = "false";
                return true;
            case JsonValueKind.Number:
                var lexeme = value.GetRawText();
                if (double.TryParse(lexeme, NumberStyles.Float, CultureInfo.InvariantCulture, out _))
                {
                    text = lexeme;
                    return true;
                }
                break;
        }
        return false;
    }

    private static JsonSerializerOptions WithoutThisConverter(JsonSerializerOptions options)
    {
        var standard = new JsonSerializerOptions(options);
        for (var index = standard.Converters.Count - 1; index >= 0; index--)
            if (standard.Converters[index] is PurchaseOrderFileMetadataRequestJsonConverter)
                standard.Converters.RemoveAt(index);
        return standard;
    }

    /// <inheritdoc />
    public override void Write(Utf8JsonWriter writer, UpsertPurchaseOrderFileRequest value, JsonSerializerOptions options)
        => JsonSerializer.Serialize(writer, value, WithoutThisConverter(options));
}

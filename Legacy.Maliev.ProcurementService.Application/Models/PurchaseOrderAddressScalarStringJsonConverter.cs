using System.Buffers;
using System.Globalization;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace Legacy.Maliev.ProcurementService.Application.Models;

/// <summary>Preserves standard JSON primitive text accepted by the original purchase-order address reader.</summary>
public sealed class PurchaseOrderAddressScalarStringJsonConverter : JsonConverter<string>
{
    /// <inheritdoc />
    public override string? Read(ref Utf8JsonReader reader, Type typeToConvert, JsonSerializerOptions options)
    {
        switch (reader.TokenType)
        {
            case JsonTokenType.String:
                return reader.GetString();
            case JsonTokenType.Null:
                return null;
            case JsonTokenType.True:
                return "true";
            case JsonTokenType.False:
                return "false";
            case JsonTokenType.Number:
                // ReadAsString validates a number while retaining its original lexeme.
                var text = reader.HasValueSequence
                    ? Encoding.UTF8.GetString(reader.ValueSequence.ToArray())
                    : Encoding.UTF8.GetString(reader.ValueSpan);
                if (double.TryParse(text, NumberStyles.Float, CultureInfo.InvariantCulture, out _))
                    return text;
                throw new JsonException("Invalid purchase-order address text number.");
            default:
                throw new JsonException("Purchase-order address text requires a JSON string, number, Boolean or null.");
        }
    }

    /// <inheritdoc />
    public override void Write(Utf8JsonWriter writer, string value, JsonSerializerOptions options) => writer.WriteStringValue(value);
}

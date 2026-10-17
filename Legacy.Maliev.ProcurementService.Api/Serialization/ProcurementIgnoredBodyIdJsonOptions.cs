using System.Buffers;
using System.Globalization;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;
using System.Text.Json.Serialization.Metadata;
using Legacy.Maliev.ProcurementService.Application.Models;
using Microsoft.AspNetCore.Mvc;
using Microsoft.Extensions.Options;

namespace Legacy.Maliev.ProcurementService.Api.Serialization;

/// <summary>Configures source-compatible ignored body identities on the three metadata request contracts.</summary>
public sealed class ProcurementIgnoredBodyIdJsonOptions : IConfigureOptions<JsonOptions>
{
    /// <summary>Preserves native object traversal while validating identities discarded by the source controllers.</summary>
    /// <param name="options">The MVC JSON options.</param>
    public void Configure(JsonOptions options)
    {
        var serializer = options.JsonSerializerOptions;
        if (serializer.TypeInfoResolver is ProcurementIgnoredBodyIdJsonTypeInfoResolver) return;
        serializer.TypeInfoResolver = new ProcurementIgnoredBodyIdJsonTypeInfoResolver(
            serializer.TypeInfoResolver ?? throw new InvalidOperationException("MVC JSON metadata resolver is required."));
    }
}

/// <summary>Decorates only address and file-metadata request object contracts.</summary>
/// <param name="inner">The existing MVC metadata resolver.</param>
public sealed class ProcurementIgnoredBodyIdJsonTypeInfoResolver(IJsonTypeInfoResolver inner) : IJsonTypeInfoResolver
{
    private static readonly JsonConverter<int?> IdentityReader = new IgnoredBodyInt32JsonConverter();
    private static readonly JsonConverter<string> FileTextReader = new PurchaseOrderFileMetadataRequestJsonConverter();

    /// <summary>The original resolver retained for native object metadata composition.</summary>
    public IJsonTypeInfoResolver Inner { get; } = inner;

    /// <inheritdoc />
    public JsonTypeInfo? GetTypeInfo(Type type, JsonSerializerOptions options)
    {
        var metadata = Inner.GetTypeInfo(type, options);
        if (type != typeof(UpsertSupplierAddressRequest)
            && type != typeof(UpsertPurchaseOrderAddressRequest)
            && type != typeof(UpsertPurchaseOrderFileRequest))
            return metadata;
        if (metadata is null || metadata.Kind != JsonTypeInfoKind.Object)
            throw new InvalidOperationException("Native metadata request object contract is required.");
        if (metadata.Properties.Any(property => string.Equals(property.Name, "Id", StringComparison.OrdinalIgnoreCase)))
            throw new InvalidOperationException("Ignored body identity must not replace a consumed property.");

        if (type == typeof(UpsertPurchaseOrderFileRequest))
        {
            // Match omitted source text/owner defaults. Native setters retain every
            // occurrence; only the two existing text fields skip null assignments.
            metadata.CreateObject = static () => new UpsertPurchaseOrderFileRequest(null, null!, null!);
            var configured = 0;
            foreach (var property in metadata.Properties)
            {
                if (property.Name is not ("Bucket" or "ObjectName")) continue;
                if (property.PropertyType != typeof(string) || property.Set is not { } setter)
                    throw new InvalidOperationException("File metadata string setter is required.");
                property.CustomConverter = FileTextReader;
                property.Set = (target, value) =>
                {
                    if (value is not null) setter(target, value);
                };
                configured++;
            }
            if (configured != 2)
                throw new InvalidOperationException("Exactly two file metadata text properties are required.");
        }

        var identity = metadata.CreateJsonPropertyInfo(typeof(int?), "Id");
        identity.CustomConverter = IdentityReader;
        identity.Set = static (_, _) => { };
        identity.Get = static _ => null;
        identity.ShouldSerialize = static (_, _) => false;
        metadata.Properties.Add(identity);
        return metadata;
    }
}

internal sealed class IgnoredBodyInt32JsonConverter : JsonConverter<int?>
{
    public override int? Read(ref Utf8JsonReader reader, Type typeToConvert, JsonSerializerOptions options)
    {
        string token;
        switch (reader.TokenType)
        {
            case JsonTokenType.Null:
                return null;
            case JsonTokenType.String:
                token = JsonSerializer.Serialize(reader.GetString());
                break;
            case JsonTokenType.Number:
                token = reader.HasValueSequence
                    ? Encoding.UTF8.GetString(reader.ValueSequence.ToArray())
                    : Encoding.UTF8.GetString(reader.ValueSpan);
                break;
            default:
                throw new JsonException("The ignored body identity has an invalid legacy type.");
        }

        using var text = new StringReader(token);
        using var legacy = new Newtonsoft.Json.JsonTextReader(text) { Culture = CultureInfo.InvariantCulture };
        try
        {
            // Public reader compatibility only; the effective historical binary is unknown.
            // Null/empty values are ignored by source NullValueHandling.Ignore.
            return legacy.ReadAsInt32();
        }
        catch (Newtonsoft.Json.JsonException exception)
        {
            // Native outer object traversal supplies the actual property Path.
            throw new JsonException("The ignored body identity has an invalid legacy type.", exception);
        }
    }

    public override void Write(Utf8JsonWriter writer, int? value, JsonSerializerOptions options)
        => throw new NotSupportedException("Ignored body identities must never be serialized.");
}

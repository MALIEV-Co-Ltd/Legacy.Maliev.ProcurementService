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

/// <summary>Configures source-compatible metadata request fields and address country inputs.</summary>
public sealed class ProcurementIgnoredBodyIdJsonOptions : IConfigureOptions<JsonOptions>
{
    /// <summary>Preserves native object traversal while validating identity and audit inputs discarded by source controllers.</summary>
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
    private static readonly JsonConverter<DateTime?> AuditReader = new IgnoredBodyNullableDateTimeJsonConverter();
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
        if (metadata.Properties.Any(property => string.Equals(property.Name, "Id", StringComparison.OrdinalIgnoreCase)
            || string.Equals(property.Name, "CreatedDate", StringComparison.OrdinalIgnoreCase)
            || string.Equals(property.Name, "ModifiedDate", StringComparison.OrdinalIgnoreCase)))
            throw new InvalidOperationException("Discarded body fields must not replace consumed properties.");

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

        if (type != typeof(UpsertPurchaseOrderFileRequest))
            ConfigureAddressCountry(metadata, type, options);

        var identity = metadata.CreateJsonPropertyInfo(typeof(int?), "Id");
        identity.CustomConverter = IdentityReader;
        identity.Set = static (_, _) => { };
        identity.Get = static _ => null;
        identity.ShouldSerialize = static (_, _) => false;
        metadata.Properties.Add(identity);
        foreach (var name in new[] { "CreatedDate", "ModifiedDate" })
        {
            var audit = metadata.CreateJsonPropertyInfo(typeof(DateTime?), name);
            audit.CustomConverter = AuditReader;
            audit.Set = static (_, _) => { };
            audit.Get = static _ => null;
            audit.ShouldSerialize = static (_, _) => false;
            metadata.Properties.Add(audit);
        }
        return metadata;
    }
    private static void ConfigureAddressCountry(JsonTypeInfo metadata, Type type, JsonSerializerOptions options)
    {
        var country = metadata.Properties.Single(property => property.Name == "CountryId");
        if (country.PropertyType != typeof(int) || country.CustomConverter is not null
            || country.Get is not { } getter || country.Set is not { } setter)
            throw new InvalidOperationException("Native address country integer property contract is required.");
        var index = metadata.Properties.IndexOf(country);
        var scalarOptions = country.NumberHandling is { } handling && handling != options.NumberHandling
            ? new JsonSerializerOptions(options) { NumberHandling = handling }
            : options;
        var nullable = metadata.CreateJsonPropertyInfo(typeof(int?), country.Name);
        nullable.CustomConverter = new AddressCountryIdJsonConverter(scalarOptions);
        nullable.Get = getter;
        nullable.Set = (target, value) =>
        {
            if (value is int identifier) setter(target, identifier);
        };
        nullable.ShouldSerialize = country.ShouldSerialize;
        nullable.IsRequired = country.IsRequired;
        nullable.Order = country.Order;
        nullable.AttributeProvider = country.AttributeProvider;
        nullable.IsSetNullable = true;
        nullable.IsGetNullable = false;
        metadata.Properties.RemoveAt(index);
        metadata.Properties.Insert(index, nullable);

        // The read slot may ignore null while the unchanged CLR property remains int.
        // Existing factories are retained; ordinary records start with their native defaults.
        if (metadata.CreateObject is null)
        {
            metadata.CreateObject = type == typeof(UpsertSupplierAddressRequest)
                ? static () => new UpsertSupplierAddressRequest(null, null, null, null, null, null, 0)
                : static () => new UpsertPurchaseOrderAddressRequest(null, null!, null, null, null, null, 0);
        }
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

internal sealed class IgnoredBodyNullableDateTimeJsonConverter : JsonConverter<DateTime?>
{
    public override DateTime? Read(ref Utf8JsonReader reader, Type typeToConvert, JsonSerializerOptions options)
    {
        if (reader.TokenType == JsonTokenType.Null) return null;
        if (reader.TokenType != JsonTokenType.String)
            throw new JsonException("The discarded audit date has an invalid legacy type.");
        using var text = new StringReader(JsonSerializer.Serialize(reader.GetString()));
        using var legacy = new Newtonsoft.Json.JsonTextReader(text) { Culture = CultureInfo.InvariantCulture };
        try
        {
            // Pinned public reader compatibility; the historical deployed binary is unknown.
            return legacy.ReadAsDateTime();
        }
        catch (Exception exception) when (exception is Newtonsoft.Json.JsonException or ArgumentOutOfRangeException)
        {
            // Native object traversal supplies Path/line/position; no payload is echoed.
            throw new JsonException("The discarded audit date has an invalid legacy type.", exception);
        }
    }

    public override void Write(Utf8JsonWriter writer, DateTime? value, JsonSerializerOptions options)
        => throw new NotSupportedException("Discarded audit inputs must never be serialized.");
}

internal sealed class AddressCountryIdJsonConverter(JsonSerializerOptions scalarOptions) : JsonConverter<int?>
{
    private static readonly JsonConverter<int?> PublicReader = new IgnoredBodyInt32JsonConverter();

    public override int? Read(ref Utf8JsonReader reader, Type typeToConvert, JsonSerializerOptions options)
    {
        if (reader.TokenType == JsonTokenType.Null) return null;
        try
        {
            // The source typed Int32 reader also maps empty strings to ignored null.
            return PublicReader.Read(ref reader, typeof(int?), options);
        }
        catch (JsonException exception)
        {
            // Native object traversal supplies CountryId's path without echoing the input.
            throw new JsonException("The address country identifier has an invalid type.", exception);
        }
    }

    public override void Write(Utf8JsonWriter writer, int? value, JsonSerializerOptions options)
    {
        if (value is { } identifier) JsonSerializer.Serialize(writer, identifier, scalarOptions);
        else writer.WriteNullValue();
    }
}

using System.Buffers;
using System.Text;
using Legacy.Maliev.ProcurementService.Application.Models;
using Microsoft.AspNetCore.Http.Features;
using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.Mvc.Formatters;
using Microsoft.AspNetCore.Mvc.ModelBinding;
using Microsoft.AspNetCore.WebUtilities;
using Microsoft.Extensions.ObjectPool;
using Microsoft.Extensions.Options;
using Newtonsoft.Json;
using SourceSupplier = Legacy.Maliev.ProcurementService.Api.Serialization.SourceBodies.SupplierContext.Supplier;
using SourceSupplierAddress = Legacy.Maliev.ProcurementService.Api.Serialization.SourceBodies.SupplierContext.Address;
using SourceOrderAddress = Legacy.Maliev.ProcurementService.Api.Serialization.SourceBodies.PurchaseOrderContext.Address;
using SourceFile = Legacy.Maliev.ProcurementService.Api.Serialization.SourceBodies.PurchaseOrderContext.PurchaseOrderFile;

namespace Legacy.Maliev.ProcurementService.Api.Serialization;

/// <summary>Adds source body admission for the four owned nonfinancial request contracts.</summary>
/// <param name="loggers">The application logger factory.</param>
/// <param name="pools">The application object pool provider.</param>
public sealed class ProcurementSourceBodyInputFormatterSetup(ILoggerFactory loggers, ObjectPoolProvider pools) : IConfigureOptions<MvcOptions>
{
    /// <inheritdoc />
    public void Configure(MvcOptions options)
    {
        if (options.InputFormatters.OfType<ProcurementSourceBodyInputFormatter>().Any()) return;
        var source = new MvcNewtonsoftJsonOptions();
        source.SerializerSettings.NullValueHandling = NullValueHandling.Ignore;
        source.SerializerSettings.ReferenceLoopHandling = ReferenceLoopHandling.Ignore;
        // Stock MVC defaults retain MaxDepth32, TypeNameHandling.None and
        // MetadataPropertyHandling.Default. Never install global Newtonsoft options.
        var logger = new SourceBodyLogger(loggers.CreateLogger<ProcurementSourceBodyInputFormatterSetup>());
        options.InputFormatters.Insert(0, new ProcurementSourceBodyInputFormatter(
            new BufferedSourceFormatter(logger, source, pools, options)));
    }

    private sealed class SourceBodyLogger(ILogger target) : ILogger
    {
        public IDisposable? BeginScope<TState>(TState state) where TState : notnull =>
            target.BeginScope("Procurement source body admission");
        public bool IsEnabled(LogLevel logLevel) => target.IsEnabled(logLevel);
        public void Log<TState>(LogLevel logLevel, EventId eventId, TState state, Exception? exception, Func<TState, Exception?, string> formatter)
        {
            if (target.IsEnabled(logLevel))
                target.Log(logLevel, eventId, "SourceBodyAdmissionFailure ExceptionType={ExceptionType}",
                    exception?.GetType().Name ?? "InputFormatter");
        }
    }

    private sealed class BufferedSourceFormatter(
        ILogger logger, MvcNewtonsoftJsonOptions json, ObjectPoolProvider pools, MvcOptions mvc)
        : NewtonsoftJsonInputFormatter(logger, json.SerializerSettings, ArrayPool<char>.Shared, pools, mvc, json)
    {
        private const long DefaultRequestLimit = 30_000_000;
        private readonly int memoryThreshold = json.InputFormatterMemoryBufferThreshold;

        public override async Task<InputFormatterResult> ReadRequestBodyAsync(InputFormatterContext context, Encoding encoding)
        {
            // TextInputFormatter selected the supported encoding before this method.
            // Drain asynchronously before the stock reader performs synchronous I/O.
            var request = context.HttpContext.Request;
            var original = request.Body;
            var originalPosition = original.CanSeek ? original.Position : (long?)null;
            var limit = context.HttpContext.Features.Get<IHttpMaxRequestBodySizeFeature>()?.MaxRequestBodySize ?? DefaultRequestLimit;
            await using var buffered = new FileBufferingReadStream(original, memoryThreshold, limit,
                static () => Environment.GetEnvironmentVariable("ASPNETCORE_TEMP") ?? Path.GetTempPath());
            try
            {
                request.Body = buffered;
                await buffered.DrainAsync(context.HttpContext.RequestAborted);
                buffered.Position = 0;
                return await base.ReadRequestBodyAsync(context, encoding);
            }
            finally
            {
                request.Body = original;
                if (originalPosition.HasValue) original.Position = originalPosition.Value;
            }
        }
    }
}

internal sealed class ProcurementSourceBodyInputFormatter(NewtonsoftJsonInputFormatter source)
    : IInputFormatter, IInputFormatterExceptionPolicy
{
    // The inner stock formatter is subclassed only for owned buffering. Preserve
    // stock malformed-input exception policy at the actual selected boundary.
    public InputFormatterExceptionPolicy ExceptionPolicy => InputFormatterExceptionPolicy.MalformedInputExceptions;

    public bool CanRead(InputFormatterContext context) => SourceType(context.ModelType) is not null && source.CanRead(context);

    public async Task<InputFormatterResult> ReadAsync(InputFormatterContext context)
    {
        var type = SourceType(context.ModelType)
            ?? throw new InvalidOperationException("The source body formatter received an unowned contract.");
        var metadata = context.HttpContext.RequestServices.GetRequiredService<IModelMetadataProvider>().GetMetadataForType(type);
        var state = new ModelStateDictionary(context.ModelState.MaxAllowedErrors);
        var originalContext = new InputFormatterContext(context.HttpContext, context.ModelName, state, metadata,
            context.ReaderFactory, context.TreatEmptyInputAsDefaultValue);
        var result = await source.ReadAsync(originalContext);
        if (result.HasError)
        {
            // A path or message may contain a literal user-supplied property/value.
            // Keep unsupported-charset classification for MVC's existing 415 filter.
            if (state.Values.SelectMany(value => value.Errors).Any(error => error.Exception is UnsupportedContentTypeException))
                context.ModelState.TryAddModelError(context.ModelName, new UnsupportedContentTypeException("The request content type is unsupported."), context.Metadata);
            else
                context.ModelState.TryAddModelError(context.ModelName, "The request body contains an invalid value.");
            return InputFormatterResult.Failure();
        }
        if (!result.IsModelSet) return result;
        if (result.Model is null) return InputFormatterResult.Success(null);
        return InputFormatterResult.Success(Project(result.Model));
    }

    private static Type? SourceType(Type type)
    {
        if (type == typeof(UpsertSupplierRequest)) return typeof(SourceSupplier);
        if (type == typeof(UpsertSupplierAddressRequest)) return typeof(SourceSupplierAddress);
        if (type == typeof(UpsertPurchaseOrderAddressRequest)) return typeof(SourceOrderAddress);
        return type == typeof(UpsertPurchaseOrderFileRequest) ? typeof(SourceFile) : null;
    }

    private static object Project(object body) => body switch
    {
        SourceSupplier value => new UpsertSupplierRequest(
            value.Name, value.Website, value.TaxNumber, value.Email, value.Note, value.Telephone, value.Mobile, value.Fax),
        SourceSupplierAddress value => new UpsertSupplierAddressRequest(
            value.Building, value.Address1, value.Address2, value.City, value.State, value.PostalCode, value.CountryId),
        SourceOrderAddress value => new UpsertPurchaseOrderAddressRequest(
            value.Building, value.AddressLine1, value.AddressLine2, value.City, value.State, value.PostalCode, value.CountryId),
        SourceFile value => new UpsertPurchaseOrderFileRequest(value.PurchaseOrderId, value.Bucket, value.ObjectName),
        _ => throw new InvalidOperationException("The source body formatter produced an unowned model."),
    };
}

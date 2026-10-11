namespace Legacy.Maliev.ProcurementService.Data;

/// <summary>Checks the source bucket contract before tracked file writes without altering literals.</summary>
internal static class PurchaseOrderFileSourceConstraints
{
    internal static void ValidateBucket(string bucket)
    {
        if (bucket is null || bucket.Length > 50)
            throw new ArgumentException("The request is invalid.", nameof(bucket));
    }
}

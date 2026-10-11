namespace Legacy.Maliev.ProcurementService.Tests.Integration;

public sealed class ProcurementFixtureDiagnosticFailureTests
{
    [Fact]
    public void InspectionAbsenceAndReceiptWriteFailures_RetainEveryOriginalReference()
    {
        var inspection = new IOException("Synthetic inspection failure.");
        var absence = new InvalidOperationException("Synthetic absence failure.");
        var publication = new IOException("Synthetic receipt publication failure.");
        var actual = Assert.Throws<AggregateException>(() => ProcurementFixtureDiagnosticFailures.PublishOrThrow(
            () => throw publication, [inspection, absence]));
        Assert.Equal(3, actual.InnerExceptions.Count);
        Assert.Same(inspection, actual.InnerExceptions[0]);
        Assert.Same(absence, actual.InnerExceptions[1]);
        Assert.Same(publication, actual.InnerExceptions[2]);
    }

    [Fact]
    public void ReceiptWriteFailureWithoutInspectionFailure_PreservesOriginalException()
    {
        var publication = new IOException("Synthetic receipt publication failure.");
        var actual = Assert.Throws<IOException>(() => ProcurementFixtureDiagnosticFailures.PublishOrThrow(
            () => throw publication, []));
        Assert.Same(publication, actual);
    }
}

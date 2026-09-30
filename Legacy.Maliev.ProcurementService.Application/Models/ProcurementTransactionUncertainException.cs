namespace Legacy.Maliev.ProcurementService.Application.Models;

/// <summary>A transaction outcome cannot safely be retried automatically.</summary>
public sealed class ProcurementTransactionUncertainException : Exception
{
    /// <summary>Creates a non-transient, data-free transaction outcome failure.</summary>
    public ProcurementTransactionUncertainException() : base("The operation could not be confirmed.") { }
}

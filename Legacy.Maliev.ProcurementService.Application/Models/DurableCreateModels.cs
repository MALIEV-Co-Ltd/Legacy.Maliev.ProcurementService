namespace Legacy.Maliev.ProcurementService.Application.Models;

/// <summary>Server-derived actor, operation, key and effective request digests.</summary>
public sealed record CreateReceiptBinding(byte[] IssuerDigest, byte[] SubjectDigest, short Operation, byte[] KeyDigest, short CanonicalVersion, byte[] PayloadDigest);
/// <summary>Immutable original JSON response and owning generated identifier.</summary>
public sealed record DurableCreateResponse(int EntityId, byte[] Body);
/// <summary>Non-disclosing durable-create outcomes.</summary>
public enum DurableCreateStatus
{
    /// <summary>A matching committed receipt proves the original create.</summary>
    CreatedOrReplayed,
    /// <summary>The same actor/key was bound to another effective request.</summary>
    Conflict,
    /// <summary>Readiness or transaction outcome cannot be proven safely.</summary>
    Unavailable,
    /// <summary>A file create has no owning purchase order.</summary>
    NotFound
}
/// <summary>Transactional receipt result without browser owner fields.</summary>
public sealed record DurableCreateResult(DurableCreateStatus Status, DurableCreateResponse? Response = null);
